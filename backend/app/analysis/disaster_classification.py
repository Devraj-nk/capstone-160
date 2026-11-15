from __future__ import annotations

MODEL_PATH = "Favaz-07/disaster-classifier-xlmr"
DEFAULT_THRESHOLD = 0.5

# Per-language decision thresholds (tuned separately for each language rather
# than one fixed 0.5 cutoff, per the handoff doc). The doc references this
# tuning but doesn't hand off the actual tuned values — populate this dict
# once those are available; every language falls back to DEFAULT_THRESHOLD
# until then.
PER_LANG_THRESHOLDS: dict[str, float] = {}

_tokenizer = None
_model = None


def _load_model():
    global _tokenizer, _model
    if _model is None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        from .model_store import model_source

        _tokenizer = AutoTokenizer.from_pretrained(model_source(MODEL_PATH))
        _model = AutoModelForSequenceClassification.from_pretrained(model_source(MODEL_PATH))
        _model.eval()
    return _tokenizer, _model


def _predict_disaster_probability(text: str) -> float:
    """Runs the fine-tuned classifier and returns P(is_disaster). Isolated so
    tests can monkeypatch just this and verify the thresholding logic in
    classify_disaster() without downloading the model.

    Binary classifier; index 1 is assumed to be the "disaster" class (mirrors
    the sentiment model's LABEL_MAP convention of 0=negative/1=positive from
    the same handoff doc). Falls back to that assumption via config.id2label
    when available, without hardcoding it."""
    import torch

    tokenizer, model = _load_model()
    inputs = tokenizer(text, truncation=True, padding="max_length", max_length=128, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=1).squeeze().tolist()

    id2label = getattr(model.config, "id2label", None) or {}
    disaster_idx = next(
        (i for i, label in id2label.items() if "disaster" in str(label).lower()),
        1,
    )
    return float(probs[disaster_idx])


def classify_disaster(text: str, lang: str | None) -> dict:
    """Step 3 — per-language threshold gate. Everything downstream is meant
    to only run on tweets that pass this gate, but that decision is left to
    the caller (this just reports is_disaster/disaster_confidence)."""
    confidence = _predict_disaster_probability(text)
    threshold = PER_LANG_THRESHOLDS.get(lang, DEFAULT_THRESHOLD) if lang else DEFAULT_THRESHOLD
    return {
        "is_disaster": confidence >= threshold,
        "disaster_confidence": round(confidence, 4),
    }
