from __future__ import annotations

from typing import Any


EMBEDDING_MODEL_PATH = "l3cube-pune/indic-sentence-similarity-sbert"

_embedding_model: Any = None


def _load_embedding_model() -> Any:
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_PATH)
    return _embedding_model


def generate_embedding(text: str) -> list[float]:
    """Generate one normalized IndicSBERT embedding for a post."""
    if not text.strip():
        raise ValueError("Cannot embed empty text")
    embedding = _load_embedding_model().encode(text, normalize_embeddings=True)
    return embedding.tolist()
