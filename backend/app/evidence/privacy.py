from __future__ import annotations

import re
from typing import Any

_DIGIT_RUN_RE = re.compile(r"\+?\d[\d\-.\s]{5,}\d")

_ADDRESS_KEY_HINTS = ("address", "location")


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
