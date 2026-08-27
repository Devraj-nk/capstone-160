from __future__ import annotations

from langdetect import LangDetectException, detect


def detect_language(text: str) -> str | None:
    """Best-effort ISO 639-1 language tag; None if detection isn't possible.
    This is informational only and never blocks the pipeline."""
    if not text or not text.strip():
        return None
    try:
        return detect(text)
    except LangDetectException:
        return None
