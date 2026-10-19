import json
import threading
from typing import List, Optional

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select, or_

from backend.db.database import get_session
from backend.db.models import Transaction
from backend.analysis.merchant_normalizer import active_aliases, canonical_merchant
from backend.transaction_filters import transaction_query
from backend.search.embedder import tx_to_text, embedding_input_hash, embedding_is_current, EMBEDDING_MODEL_VERSION, embed_texts, embed_query, cosine_similarity_bulk

router = APIRouter()

SEMANTIC_THRESHOLD = 0.35   # minimum cosine similarity to include a result
KEYWORD_SCORE = 1.0          # keyword matches always score 1.0
TOP_K = 50
_embed_lock = threading.Lock()


def _index_status(txs, aliases=None):
    aliases = aliases or {}
    current = sum(embedding_is_current(tx, aliases) for tx in txs)
    total = len(txs)
    return {
        "embedded_count": current,
        "stale_embedding_count": total - current,
        "total_transactions": total,
        "index_status": "empty" if total == 0 else "ready" if current == total else "stale",
    }


@router.get("/search/index-status")
def search_index_status():
    with get_session() as session:
        txs = session.execute(select(Transaction)).scalars().all()
        aliases = active_aliases(session)
        return _index_status(txs, aliases)


@router.get("/search")
def search_transactions(
    q: str,
    mode: str = "hybrid",  # "keyword" | "semantic" | "hybrid"
    query=Depends(transaction_query),
):
    q = q.strip()
    if not q:
        return {"results": [], "mode": mode}

    with get_session() as session:
        all_txs = session.execute(query).scalars().all()
        aliases = active_aliases(session)

        keyword_ids: set = set()
        if mode in ("keyword", "hybrid"):
            ql = q.lower()
            keyword_ids = {
                tx.id for tx in all_txs
                if ql in (tx.description or "").lower()
                or ql in (tx.category or "").lower()
                or ql in (tx.metadata_ or "").lower()
                or ql in (canonical_merchant(tx.merchant_name, aliases) or "").lower()
                or ql in (tx.merchant_type or "").lower()
                or ql in (tx.city or "").lower()
                or ql in str(tx.amount)
            }

        semantic_scores: dict = {}
        if mode in ("semantic", "hybrid"):
            # Only embed transactions that have embeddings stored
            embedded = [tx for tx in all_txs if embedding_is_current(tx, aliases)]
            if embedded:
                matrix = np.array([json.loads(tx.embedding) for tx in embedded], dtype=np.float32)
                q_vec = embed_query(q)
                scores = cosine_similarity_bulk(q_vec, matrix)
                for tx, score in zip(embedded, scores):
                    if float(score) >= SEMANTIC_THRESHOLD:
                        semantic_scores[tx.id] = float(score)

        # Merge: keyword hits score 1.0, semantic hits score by similarity, overlap gets max
        scored: dict = {}
        for tid in keyword_ids:
            scored[tid] = max(scored.get(tid, 0.0), KEYWORD_SCORE)
        for tid, score in semantic_scores.items():
            scored[tid] = max(scored.get(tid, 0.0), score)

        if not scored:
            return {"results": [], "mode": mode, **_index_status(all_txs, aliases)}

        tx_map = {tx.id: tx for tx in all_txs}
        results = sorted(scored.items(), key=lambda x: -x[1])[:TOP_K]

        return {
            "results": [
                {
                    "id": tx_map[tid].id,
                    "source": tx_map[tid].source,
                    "date": tx_map[tid].date.isoformat(),
                    "description": tx_map[tid].description,
                    "amount": tx_map[tid].amount,
                    "category": tx_map[tid].category,
                    "merchant_name": canonical_merchant(tx_map[tid].merchant_name, aliases),
                    "merchant_type": tx_map[tid].merchant_type,
                    "city": tx_map[tid].city,
                    "is_online": tx_map[tid].is_online,
                    "is_subscription": tx_map[tid].is_subscription,
                    "score": round(score, 3),
                    "match_type": "keyword" if tid in keyword_ids and tid not in semantic_scores
                                  else "semantic" if tid not in keyword_ids
                                  else "both",
                }
                for tid, score in results
                if tid in tx_map
            ],
            "mode": mode,
            **_index_status(all_txs, aliases),
        }


@router.post("/search/embed")
def generate_embeddings(background_tasks: BackgroundTasks):
    """Trigger embedding generation for missing or stale transaction vectors."""
    background_tasks.add_task(_embed_all, get_session)
    return {"status": "started"}


def _embed_all(session_factory=None):
    """Rebuild stale vectors without holding database transactions during model work."""
    session_factory = session_factory or get_session
    _embed_lock.acquire()
    try:
        with session_factory() as session:
            aliases = active_aliases(session)
            rows = session.execute(select(Transaction)).scalars().all()
            snapshots = [(tx.id, tx_to_text(tx, aliases), embedding_input_hash(tx, aliases))
                         for tx in rows if not embedding_is_current(tx, aliases)]

        for start in range(0, len(snapshots), 64):
            batch = snapshots[start:start + 64]
            vectors = embed_texts([text for _, text, _ in batch])
            with session_factory() as session:
                aliases = active_aliases(session)
                for (tx_id, _text, expected_hash), vector in zip(batch, vectors):
                    tx = session.get(Transaction, tx_id)
                    if tx is None or embedding_input_hash(tx, aliases) != expected_hash:
                        continue
                    tx.embedding = json.dumps(vector.tolist())
                    tx.embedding_input_hash = expected_hash
                    tx.embedding_model_version = EMBEDDING_MODEL_VERSION
    finally:
        _embed_lock.release()
