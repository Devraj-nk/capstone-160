from __future__ import annotations

import re

import emoji
import ftfy

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_MENTION_RE = re.compile(r"@\w+")
_UNNECESSARY_SYMBOLS_RE = re.compile(r"[^\w\s.,!?'\"-]")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Fix encoding, decode emojis to their textual meaning, strip URLs/mentions
    and other unnecessary symbols, and collapse whitespace."""
    text = ftfy.fix_text(text)
    text = emoji.demojize(text, delimiters=(" ", " "))
    text = text.replace("_", " ")
    text = _URL_RE.sub(" ", text)
    text = _MENTION_RE.sub(" ", text)
    text = _UNNECESSARY_SYMBOLS_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def is_valid_post(text: str) -> bool:
    """A post is invalid once cleaning leaves nothing but whitespace/punctuation."""
    return bool(re.search(r"\w", text))
