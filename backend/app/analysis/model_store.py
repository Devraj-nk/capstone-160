"""Where the Hugging Face models are loaded from.

Each model can live as a plain folder in backend/models/<repo name>/ (fill it
with `python tools/download_models.py`). When that folder holds the model, it
is loaded from disk with no network access; otherwise the Hugging Face repo id
is used as before (downloaded into the usual Hugging Face cache).
"""
from __future__ import annotations

import os
from pathlib import Path

MODELS_DIR = Path(os.getenv("MODELS_DIR") or Path(__file__).resolve().parents[2] / "models")

# Every model the pipeline uses (repo id -> what it does).
MODEL_REPOS = {
    "Favaz-07/language-detection-xlmr": "language detection",
    "Favaz-07/disaster-classifier-xlmr": "disaster classification",
    "Favaz-07/need-detection-xlmr": "need detection",
    "akshataudaganve/xlmr-sentiment-disaster": "sentiment",
    "l3cube-pune/indic-sentence-similarity-sbert": "IndicSBERT embeddings (clustering)",
}

_WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")


def local_dir(repo_id: str) -> Path:
    return MODELS_DIR / repo_id.split("/")[-1]


def is_downloaded(repo_id: str) -> bool:
    folder = local_dir(repo_id)
    return (folder / "config.json").is_file() and any((folder / name).is_file() for name in _WEIGHT_FILES)


def model_source(repo_id: str) -> str:
    """The local folder if the model is there, otherwise the repo id."""
    return str(local_dir(repo_id)) if is_downloaded(repo_id) else repo_id
