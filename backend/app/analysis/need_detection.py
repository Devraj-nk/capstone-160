from __future__ import annotations

NEED_MODEL_PATH = "Favaz-07/need-detection-xlmr"
LABEL_COLS = ["is_healthcare", "is_municipal", "is_tourism", "is_law"]

# Per-label decision thresholds, tuned on a held-out validation set (not used
# to filter the `needs` dict itself — the raw probabilities are what the
# Combine step and downstream evidence/routing consume — but exposed here for
# whichever stage ends up deciding "is this need active enough to act on").
THRESHOLDS = {"healthcare": 0.65, "municipal": 0.80, "tourism": 0.75, "law": 0.65}

_tokenizer = None
_model = None


def _load_model():
    global _tokenizer, _model
    if _model is None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(NEED_MODEL_PATH)
        _model = AutoModelForSequenceClassification.from_pretrained(NEED_MODEL_PATH)
        _model.eval()
    return _tokenizer, _model


def _predict_need_probs(text: str) -> dict[str, float]:
    """Runs the multi-label XLM-RoBERTa need classifier (sigmoid output — a
    tweet can hit 0, 1, or several departments at once). Isolated so tests
    can monkeypatch just this and verify the schema logic in detect_needs()
    without the real model."""
    import torch

    tokenizer, model = _load_model()
    enc = tokenizer(text, max_length=128, padding="max_length", truncation=True, return_tensors="pt")
    with torch.no_grad():
        probs = torch.sigmoid(model(**enc).logits).squeeze(0).tolist()
    return {name.replace("is_", ""): float(p) for name, p in zip(LABEL_COLS, probs)}


def active_needs(needs: dict[str, float]) -> list[str]:
    """Which needs clear their per-label threshold. Not used by detect_needs()
    itself (the handoff doc's output schema keeps raw probabilities), but
    available for whichever stage (routing?) needs a boolean decision."""
    return [name for name, prob in needs.items() if prob >= THRESHOLDS.get(name, 0.5)]


def detect_needs(text: str) -> dict:
    """Step 5b. Output fields match the handoff doc's schema exactly: raw
    per-department probabilities plus need_confidence (max of the four),
    which the Combine step's severity formula consumes directly."""
    probs = _predict_need_probs(text)
    needs = {name: round(p, 4) for name, p in probs.items()}
    return {
        "needs": needs,
        "need_confidence": round(max(needs.values()), 4) if needs else 0.0,
    }
