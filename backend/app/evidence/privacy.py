from __future__ import annotations

import re
from typing import Any

_DIGIT_RUN_RE = re.compile(r"\+?\d[\d\-.\s]{5,}\d")

_ADDRESS_RE = re.compile(
    r"\b\d{1,5}[A-Za-z]?\s*,?\s*(?:[A-Z][a-zA-Z]*\s+){0,4}"
    r"(?:Road|Rd|Street|St|Avenue|Ave|Lane|Ln|Nagar|Colony|Block|Apartment|Apt|"
    r"Flat|Sector|Layout|Marg|Cross|Circle)\b[^,.\n]*",
    re.IGNORECASE,
)


def _mask_if_phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    return "[PHONE_REDACTED]" if len(digits) >= 7 else match.group()


def mask_personal_details(text: str) -> str:
    """Basic PII redaction applied before evidence is persisted long-term:
    phone numbers and street-address-shaped text. Heuristic (regex-based),
    not exhaustive PII detection."""
    text = _DIGIT_RUN_RE.sub(_mask_if_phone, text)
    text = _ADDRESS_RE.sub("[ADDRESS_REDACTED]", text)
    return text


def mask_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, str):
            masked[key] = mask_personal_details(value)
        elif isinstance(value, dict):
            masked[key] = mask_metadata(value)
        else:
            masked[key] = value
    return masked
