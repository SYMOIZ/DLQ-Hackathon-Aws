"""Layer 1: PII masking for message bodies and attributes."""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# Require a separator or leading + so plain 12-digit runs are not phones (TC-U03).
_PHONE = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[\s\-.]*)?(?:\(?\d{3}\)?[\s\-.]+)\d{3}[\s\-.]?\d{4}(?!\d)"
)
_NUMBER = re.compile(r"(?<!\d)\d{13,19}(?!\d)")


def mask_text(text: str) -> str:
    if not text:
        return text
    out = _EMAIL.sub("[EMAIL]", text)
    out = _NUMBER.sub("[NUMBER]", out)
    out = _PHONE.sub("[PHONE]", out)
    return out
