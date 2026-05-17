"""Phone-number normalisation helpers."""

from __future__ import annotations

import re


def apply_phone_regex(phone: str, pattern: str) -> str:
    """Extract a phone fragment using ``pattern``.

    Returns the first capture group when present, otherwise the whole match.
    Falls back to the original ``phone`` value when the regex does not match
    or is invalid.
    """
    if not phone or not pattern:
        return phone
    try:
        m = re.search(pattern, phone)
        if m:
            return m.group(1) if m.lastindex else m.group(0)
    except re.error:
        pass
    return phone
