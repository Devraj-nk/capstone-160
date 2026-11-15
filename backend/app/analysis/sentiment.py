from __future__ import annotations

from datetime import datetime, timezone

SENTIMENT_MODEL_PATH = "akshataudaganve/xlmr-sentiment-disaster"
LABEL_MAP = {0: "negative", 1: "positive"}

_tokenizer = None
_model = None


def _load_model():
    global _tokenizer, _model
    if _model is None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        from .model_store import model_source

        _tokenizer = AutoTokenizer.from_pretrained(model_source(SENTIMENT_MODEL_PATH))
        _model = AutoModelForSequenceClassification.from_pretrained(model_source(SENTIMENT_MODEL_PATH))
        _model.eval()
    return _tokenizer, _model


def _predict_sentiment_probs(text: str) -> list[float]:
    """Runs the fine-tuned XLM-RoBERTa sentiment classifier and returns the
    softmax probabilities [P(negative), P(positive)]. Isolated so tests can
    monkeypatch just this and verify the schema-building logic in
    analyze_sentiment() without the real model."""
    import torch

    tokenizer, model = _load_model()
    inputs = tokenizer(text, truncation=True, padding="max_length", max_length=128, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=1).squeeze().tolist()
    return probs


def analyze_sentiment(text: str) -> dict:
    """Step 5a. Input: cleaned post text. Output fields match the handoff
    doc's schema exactly, including sentiment_negativity — the value the
    Combine step (severity formula) and downstream evidence work consume."""
    probs = _predict_sentiment_probs(text)
    pred_class = max(range(len(probs)), key=lambda i: probs[i])

    return {
        "sentiment_label": LABEL_MAP[pred_class],
        "sentiment_confidence": round(probs[pred_class], 4),
        "sentiment_probabilities": {LABEL_MAP[i]: round(p, 4) for i, p in enumerate(probs)},
        "sentiment_negativity": round(probs[0], 4),
        "sentiment_model": SENTIMENT_MODEL_PATH,
        "sentiment_predicted_at": datetime.now(timezone.utc).isoformat(),
    }


def analyze_sentiment_batch(texts: list[str], batch_size: int = 32) -> list[dict]:
    """Batched version for processing many posts at once. Not yet called by
    any router (the /analysis/analyze and /analysis/pipeline endpoints are
    single-post), but kept available since batching is how this is meant to
    run at real ingestion volume."""
    import torch

    tokenizer, model = _load_model()
    results: list[dict] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        inputs = tokenizer(batch, truncation=True, padding=True, max_length=128, return_tensors="pt")
        with torch.no_grad():
            logits = model(**inputs).logits
            batch_probs = torch.softmax(logits, dim=1).tolist()

        for probs in batch_probs:
            pred_class = max(range(len(probs)), key=lambda i: probs[i])
            results.append(
                {
                    "sentiment_label": LABEL_MAP[pred_class],
                    "sentiment_confidence": round(probs[pred_class], 4),
                    "sentiment_probabilities": {LABEL_MAP[i]: round(p, 4) for i, p in enumerate(probs)},
                    "sentiment_negativity": round(probs[0], 4),
                    "sentiment_model": SENTIMENT_MODEL_PATH,
                    "sentiment_predicted_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    return results
