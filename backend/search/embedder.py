"""
Local embedding using BAAI/bge-small-en-v1.5 (33M params, 384 dims).
Model is loaded once at import time and reused across requests.
"""
import json
import logging
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from backend.db.models import Transaction

logger = logging.getLogger(__name__)

_MODEL = None  # type: SentenceTransformer


def get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        logger.info("Loading BAAI/bge-small-en-v1.5...")
        _MODEL = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _MODEL


def tx_to_text(tx: Transaction) -> str:
    """Build a rich text representation of a transaction for embedding."""
    parts = [tx.description.strip()]

    if tx.category:
        parts.append(tx.category)

    parts.append(f"${tx.amount:.2f}")
    parts.append(str(tx.date))
    parts.append(tx.source)

    if tx.metadata_:
        try:
            meta = json.loads(tx.metadata_)
            if meta.get("City/State"):
                parts.append(meta["City/State"].replace("\n", " "))
            if meta.get("Country") and meta["Country"] != "UNITED STATES":
                parts.append(meta["Country"])
            # Bank-provided category adds semantic signal
            if meta.get("Category"):
                parts.append(meta["Category"])
        except (json.JSONDecodeError, KeyError):
            pass

    return " | ".join(parts)


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
