"""
Local embedding using BAAI/bge-small-en-v1.5 (33M params, 384 dims).
Model is loaded on first use and reused across requests.
"""
from __future__ import annotations

import json
import hashlib
import logging
from typing import List

import numpy as np

from backend.db.models import Transaction

logger = logging.getLogger(__name__)

_MODEL = None


def get_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading BAAI/bge-small-en-v1.5...")
        _MODEL = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _MODEL


EMBEDDING_TEXT_VERSION = "transaction-v2"
EMBEDDING_MODEL_VERSION = "BAAI/bge-small-en-v1.5"

def tx_to_text(tx: Transaction, merchant_aliases: dict[str, str] | None = None) -> str:
    """Build a rich text representation of a transaction for embedding."""
    parts = [tx.description.strip()]

    if tx.merchant_name:
        merchant = tx.merchant_name
        seen = set()
        aliases = merchant_aliases or {}
        while merchant in aliases and merchant not in seen:
            seen.add(merchant)
            merchant = aliases[merchant]
        parts.append(f"Merchant: {merchant}")
    if tx.city:
        parts.append(f"City: {tx.city}")
    if tx.merchant_type:
        parts.append(f"Merchant type: {tx.merchant_type}")
    if tx.category:
        parts.append(f"Category: {tx.category}")

    parts.append(f"${tx.amount:.2f}")
    parts.append(str(tx.date))
    parts.append(tx.source)

    if tx.metadata_:
        try:
            meta = json.loads(tx.metadata_)
            city_state = meta.get("City/State")
            if isinstance(city_state, str) and city_state.strip():
                parts.append(city_state.replace("\n", " "))
            country = meta.get("Country")
            if isinstance(country, str) and country and country != "UNITED STATES":
                parts.append(country)
            bank_category = meta.get("Category")
            if isinstance(bank_category, str) and bank_category:
                parts.append(bank_category)
        except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
            pass

    return " | ".join(parts)


def embedding_input_hash(tx: Transaction, merchant_aliases: dict[str, str] | None = None) -> str:
    payload = f"{EMBEDDING_TEXT_VERSION}\0{tx_to_text(tx, merchant_aliases)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def embedding_is_current(tx: Transaction, merchant_aliases: dict[str, str] | None = None) -> bool:
    return bool(tx.embedding and tx.embedding_model_version == EMBEDDING_MODEL_VERSION
                and tx.embedding_input_hash == embedding_input_hash(tx, merchant_aliases))


def embed_texts(texts: List[str]) -> np.ndarray:
    """Return normalized embeddings, shape (N, 384)."""
    model = get_model()
    # BGE models benefit from a query prefix
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)


def embed_query(query: str) -> np.ndarray:
    """Embed a search query with BGE's recommended query prefix."""
    model = get_model()
    prefixed = f"Represent this sentence for searching relevant passages: {query}"
    return model.encode([prefixed], normalize_embeddings=True, show_progress_bar=False)[0]


def cosine_similarity_bulk(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Fast vectorized cosine similarity. Both inputs must be L2-normalised."""
    return matrix @ query_vec  # dot product of unit vectors = cosine similarity
