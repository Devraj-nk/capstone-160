from __future__ import annotations

import re

MAX_SUMMARY_CHARS = 280

_SENTENCE_END_RE = re.compile(r"(?<=[.!?।])\s+")


def _first_sentence(text: str) -> str:
    return _SENTENCE_END_RE.split(text.strip(), maxsplit=1)[0]


def summarize_texts(texts: list[str], max_chars: int = MAX_SUMMARY_CHARS) -> str:
    """Extractive summary of arbitrary texts for /summarization/summarize: the
    lead sentence of each, in the order given, skipping repeats, until
    max_chars. Situation summaries in the pipeline use the step-10 template
    instead (app.scoring.summary_evidence)."""
    pieces: list[str] = []
    seen: set[str] = set()
    for text in texts:
        sentence = _first_sentence(text).rstrip(" .!?।")
        key = sentence.lower()
        if not sentence or key in seen:
            continue
        candidate = "; ".join(pieces + [sentence])
        if pieces and len(candidate) > max_chars:
            break
        pieces.append(sentence)
        seen.add(key)
    return "; ".join(pieces)[:max_chars]
