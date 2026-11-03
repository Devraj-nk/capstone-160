from __future__ import annotations

import re
import unicodedata

import emoji
import ftfy

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_MENTION_RE = re.compile(r"@\w+")
_KEPT_PUNCTUATION = set(".,!?'\"-।॥")  # incl. Devanagari danda / double danda
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_symbols(text: str) -> str:
    """Drop symbols but keep letters, digits and combining marks. Not a
    word-character regex: those don't match Indic vowel signs/viramas
    (Unicode Mn/Mc), so they would shred "भारी" into "भ र"."""
    return "".join(
        ch
        if ch.isalnum() or ch.isspace() or ch in _KEPT_PUNCTUATION
        or unicodedata.category(ch)[0] == "M"
        else " "
        for ch in text
    )


def clean_text(text: str) -> str:
    """Fix encoding, decode emojis to their textual meaning, strip URLs/mentions
    and other unnecessary symbols, and collapse whitespace."""
    text = ftfy.fix_text(text)
    text = emoji.demojize(text, delimiters=(" ", " "))
    text = text.replace("_", " ")
    text = _URL_RE.sub(" ", text)
    text = _MENTION_RE.sub(" ", text)
    text = _strip_symbols(text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def is_valid_post(text: str) -> bool:
    """A post is invalid once cleaning leaves nothing but whitespace/punctuation."""
    return bool(re.search(r"\w", text))
