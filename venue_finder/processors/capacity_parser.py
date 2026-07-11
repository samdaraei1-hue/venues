from __future__ import annotations

import re


CAPACITY_PATTERNS = (
    re.compile(r"\b(?:für|for|bis zu|max(?:imal)?\.?)\s*(\d{1,3})\s*(?:gäste|gaeste|personen|personen|betten|plätze|plaetze)\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,3})\s*(?:gäste|gaeste|personen|personen|betten|plätze|plaetze)\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,3})\s*(?:bett(?:en)?|sleep(?:ing)? places?)\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,3})\s*\+\s*(?:gäste|gaeste|personen|betten)\b", re.IGNORECASE),
)

BED_PATTERNS = (
    re.compile(r"\b(\d{1,3})\s*(?:betten|beds?|schlafplätze|schlafplaetze)\b", re.IGNORECASE),
)

ROOM_PATTERNS = (
    re.compile(r"\b(\d{1,3})\s*(?:gruppenräume|gruppenraeume|gruppenzimmer|schlafräume|schlafraeume|zimmer|rooms?)\b", re.IGNORECASE),
)

CAMPING_PATTERNS = (
    re.compile(r"\b(\d{1,3})\s*(?:campingplätze|campingplaetze|zeltplätze|zeltplaetze|stellplätze|stellplaetze)\b", re.IGNORECASE),
    re.compile(r"\bcamping(?:\s+für|\s+for)?\s*(\d{1,3})\s*(?:personen|gäste|gaeste|plätze|plaetze)?\b", re.IGNORECASE),
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


def _extract_max_from_patterns(text: str | None, patterns: tuple[re.Pattern[str], ...]) -> int | None:
    if not text:
        return None

    candidates: list[int] = []
    for pattern in patterns:
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


def extract_number_of_beds(text: str | None) -> int | None:
    return _extract_max_from_patterns(text, BED_PATTERNS)


def extract_number_of_rooms(text: str | None) -> int | None:
    return _extract_max_from_patterns(text, ROOM_PATTERNS)


def extract_camping_capacity(text: str | None) -> int | None:
    return _extract_max_from_patterns(text, CAMPING_PATTERNS)
