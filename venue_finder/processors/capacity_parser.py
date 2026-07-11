from __future__ import annotations

import re


CAPACITY_PATTERNS = (
    re.compile(r"\b(?:für|for|bis zu|max(?:imal)?\.?)\s*(\d{1,3})\s*(?:gäste|gaeste|personen|personen|betten|plätze|plaetze)\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,3})\s*(?:gäste|gaeste|personen|personen|betten|plätze|plaetze)\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,3})\s*(?:bett(?:en)?|sleep(?:ing)? places?)\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,3})\s*\+\s*(?:gäste|gaeste|personen|betten)\b", re.IGNORECASE),
)


def extract_maximum_guests(text: str | None) -> int | None:
    """Best-effort capacity extraction from venue copy.

    We intentionally keep this heuristic conservative: only numbers next to
    capacity-related words are considered.
    """

    if not text:
        return None

    candidates: list[int] = []
    for pattern in CAPACITY_PATTERNS:
        for match in pattern.finditer(text):
            try:
                value = int(match.group(1))
            except ValueError:
                continue
            if 1 <= value <= 2000:
                candidates.append(value)

    if not candidates:
        return None
    return max(candidates)
