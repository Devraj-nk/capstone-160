from __future__ import annotations

import hashlib
import re
from typing import Any

from ..config import AUTHOR_HASH_SALT

_DIGIT_RUN_RE = re.compile(r"\+?\d[\d\-.\s]{5,}\d")

_ADDRESS_KEY_HINTS = ("address", "location")

# Source fields that identify the author; replaced by one salted hash.
_AUTHOR_KEYS = ("user_id", "userid", "username", "user_name", "user", "screen_name", "handle",
                "author", "author_id")


def hash_author(value: Any) -> str:
    """Salted, one-way author reference: enough to count distinct authors,
    nothing more."""
    digest = hashlib.sha256(f"{AUTHOR_HASH_SALT}:{value}".encode("utf-8")).hexdigest()
    return f"hash:{digest[:16]}"


def pseudonymize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Drop every username/handle/user-id field, keeping only `author_ref`."""
    cleaned = {k: v for k, v in attributes.items() if k.lower() not in _AUTHOR_KEYS}
    author = next((attributes[k] for k in attributes if k.lower() in _AUTHOR_KEYS and attributes[k]), None)
    if author is not None:
        cleaned["author_ref"] = hash_author(author)
    return cleaned


def _mask_if_phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    return "[PHONE_REDACTED]" if len(digits) >= 7 else match.group()


def mask_personal_details(text: str) -> str:
    return _DIGIT_RUN_RE.sub(_mask_if_phone, text)


def mask_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, str) and any(hint in key.lower() for hint in _ADDRESS_KEY_HINTS):
            masked[key] = "[ADDRESS_REDACTED]"
        elif isinstance(value, str):
            masked[key] = mask_personal_details(value)
        elif isinstance(value, dict):
            masked[key] = mask_metadata(value)
        else:
            masked[key] = value
    return masked
