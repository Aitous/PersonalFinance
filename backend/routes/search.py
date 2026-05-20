import json
from typing import List, Optional

import numpy as np
from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select, or_

from backend.db.database import get_session
from backend.db.models import Transaction
from backend.search.embedder import tx_to_text, embed_texts, embed_query, cosine_similarity_bulk

router = APIRouter()

SEMANTIC_THRESHOLD = 0.35   # minimum cosine similarity to include a result
KEYWORD_SCORE = 1.0          # keyword matches always score 1.0
TOP_K = 50


@router.get("/search")
def search_transactions(
    q: str,
    mode: str = "hybrid",  # "keyword" | "semantic" | "hybrid"
):
    q = q.strip()
    if not q:
        return {"results": [], "mode": mode}

    with get_session() as session:
        all_txs = session.execute(select(Transaction)).scalars().all()

        keyword_ids: set = set()
        if mode in ("keyword", "hybrid"):
            ql = q.lower()
            keyword_ids = {
                tx.id for tx in all_txs
                if ql in (tx.description or "").lower()
                or ql in (tx.category or "").lower()
                or ql in (tx.metadata_ or "").lower()
                or ql in (tx.merchant_name or "").lower()
                or ql in (tx.merchant_type or "").lower()
                or ql in (tx.city or "").lower()
                or ql in str(tx.amount)
            }

        semantic_scores: dict = {}
        if mode in ("semantic", "hybrid"):
            # Only embed transactions that have embeddings stored
            embedded = [tx for tx in all_txs if tx.embedding]
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
            return {"results": [], "mode": mode, "embedded_count": len([t for t in all_txs if t.embedding])}

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
                    "merchant_name": tx_map[tid].merchant_name,
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
            "embedded_count": len([t for t in all_txs if t.embedding]),
            "total_transactions": len(all_txs),
        }


@router.post("/search/embed")
def generate_embeddings(background_tasks: BackgroundTasks):
    """Trigger embedding generation for all unembedded transactions."""
    background_tasks.add_task(_embed_all)
    return {"status": "started"}


def _embed_all():
    """Background task: embed all transactions that don't have embeddings yet."""
    with get_session() as session:
        txs = session.execute(
            select(Transaction).where(Transaction.embedding.is_(None))
        ).scalars().all()

        if not txs:
            return

        BATCH = 64
        for i in range(0, len(txs), BATCH):
            batch = txs[i:i + BATCH]
            texts = [tx_to_text(tx) for tx in batch]
            vecs = embed_texts(texts)
            for tx, vec in zip(batch, vecs):
                tx.embedding = json.dumps(vec.tolist())
            session.commit()
