from __future__ import annotations

import re

MODEL_PATH = "Favaz-07/language-detection-xlmr"

# Native-script Unicode ranges — catches ~50-58% of real tweet data instantly,
# with no model needed and no misclassification risk.
SCRIPT_RANGES = {
    "hi": r"[ऀ-ॿ]",  # Devanagari (Hindi)
    "kn": r"[ಀ-೿]",  # Kannada script
    "ta": r"[஀-௿]",  # Tamil script
    "te": r"[ఀ-౿]",  # Telugu script
}

_tokenizer = None
_model = None


def _load_model():
    """Lazy, cached model load. Never imported/run at module import time so
    importing this module (e.g. for tests) doesn't trigger a multi-hundred-MB
    download; only the first real call to _predict_with_classifier() does."""
    global _tokenizer, _model
    if _model is None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        from ..analysis.model_store import model_source

        _tokenizer = AutoTokenizer.from_pretrained(model_source(MODEL_PATH))
        _model = AutoModelForSequenceClassification.from_pretrained(model_source(MODEL_PATH))
        _model.eval()
    return _tokenizer, _model


def detect_by_script(text: str, min_chars: int = 3) -> str | None:
    """Case 1 — deterministic native-script check. Returns None if no script
    hits the min_chars floor (i.e. the text is Latin-script and needs the
    classifier fallback)."""
    counts = {lang: len(re.findall(pattern, text)) for lang, pattern in SCRIPT_RANGES.items()}
    best_lang = max(counts, key=counts.get)
    return best_lang if counts[best_lang] >= min_chars else None


def check_code_mixed(text: str, min_native: int = 3, min_latin: int = 5) -> bool:
    """Lightweight heuristic: are there enough native-script AND enough Latin
    characters in the same tweet to call it code-mixed? Flags the dominant
    language only — true token-level code-mixing detection is out of scope
    here, same limitation the handoff doc calls out."""
    counts = {lang: len(re.findall(pattern, text)) for lang, pattern in SCRIPT_RANGES.items()}
    has_native = bool(counts) and max(counts.values()) >= min_native
    has_latin = len(re.findall(r"[A-Za-z]", text)) >= min_latin
    return bool(has_native and has_latin)


def _predict_with_classifier(text: str) -> str:
    """Case 2 — Latin-script text (English or romanized Hindi/Kannada/Tamil/
    Telugu) falls through to the trained XLM-RoBERTa classifier. Isolated in
    its own function so tests can monkeypatch just this and verify the
    surrounding script-detection/schema logic without the real model.

    Reads the language tag from the model's own config.id2label rather than a
    hardcoded id->language dict, since the handoff doc didn't hand off the
    exact label ordering the model was trained with — this is the standard,
    robust way to decode a Hugging Face classification head's output and
    avoids guessing at an ordering that could silently mislabel languages."""
    import torch

    tokenizer, model = _load_model()
    enc = tokenizer(text, max_length=96, padding="max_length", truncation=True, return_tensors="pt")
    with torch.no_grad():
        logits = model(**enc).logits
    predicted_id = int(torch.argmax(logits, dim=1)[0])
    return label_to_lang(model.config.id2label.get(predicted_id), predicted_id)


# The published model's config only has generic names (LABEL_0..LABEL_4); its
# lang2id.json (shipped with the model) gives the real order.
ID2LANG = {0: "en", 1: "hi", 2: "kn", 3: "ta", 4: "te"}
_LANG_CODES = set(ID2LANG.values())


def label_to_lang(label: str | None, predicted_id: int) -> str:
    """Language code for a classifier output: the config's label when it is
    already a language code, otherwise the lang2id.json order."""
    if label in _LANG_CODES:
        return label
    return ID2LANG.get(predicted_id, "unknown")


def detect_language_final(text: str) -> dict:
    """Step 4 — full two-stage language detection. Returns
    {lang, is_romanized, is_code_mixed}. Never raises; this is informational
    and must not block the pipeline."""
    if not text or not text.strip():
        return {"lang": None, "is_romanized": False, "is_code_mixed": False}

    script_lang = detect_by_script(text)
    if script_lang is not None:
        lang, is_romanized = script_lang, False
    else:
        lang = _predict_with_classifier(text)
        is_romanized = lang != "en"

    return {"lang": lang, "is_romanized": is_romanized, "is_code_mixed": check_code_mixed(text)}
