from __future__ import annotations

from typing import Any


EMBEDDING_MODEL_PATH = "l3cube-pune/indic-sentence-similarity-sbert"
# Identifies the vector space of stored embeddings/centroids; the offline
# backend overrides it. Vectors from different models are never mixed.
EMBEDDING_MODEL_ID = EMBEDDING_MODEL_PATH

_embedding_model: Any = None


def _load_embedding_model() -> Any:
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        from .model_store import model_source

        _embedding_model = SentenceTransformer(model_source(EMBEDDING_MODEL_PATH))
    return _embedding_model


def generate_embedding(text: str) -> list[float]:
    """Generate one normalized IndicSBERT embedding for a post."""
    if not text.strip():
        raise ValueError("Cannot embed empty text")
    embedding = _load_embedding_model().encode(text, normalize_embeddings=True, show_progress_bar=False)
    return embedding.tolist()
