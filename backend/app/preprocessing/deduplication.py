from __future__ import annotations

import hashlib
import re
from collections import Counter

_RT_PREFIX_RE = re.compile(r"^rt\b[:\s]*", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")

_repost_counts: Counter[str] = Counter()


def fingerprint(cleaned_text: str) -> str:
    """Canonical hash of a cleaned post, with any leading retweet marker
    stripped, so a retweet of the same content hashes identically to the
    original. Exact-match only — similar-but-not-identical posts must NOT
    collapse to the same fingerprint, since they're needed downstream for
    clustering."""
    normalized = _RT_PREFIX_RE.sub("", cleaned_text.strip().lower())
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def register_repost(cleaned_text: str) -> int:
    """Record one more sighting of this exact post (by fingerprint) and
    return how many times it's now been seen in total. 1 = first sighting
    (an original post); 2+ = a repost/retweet of an already-seen post."""
    fp = fingerprint(cleaned_text)
    _repost_counts[fp] += 1
    return _repost_counts[fp]
