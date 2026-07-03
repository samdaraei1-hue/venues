from __future__ import annotations

import re


POSITIVE_PATTERNS: dict[str, tuple[str, ...]] = {
    "camping_allowed": ("camping erlaubt", "camping möglich", "camping möglichkeit", "camping", "zelten erlaubt", "zeltplatz"),
    "parties_allowed": ("party erlaubt", "parties allowed", "feier", "party", "veranstaltung", "eventlocation"),
    "loud_music_allowed": ("laute musik erlaubt", "loud music allowed", "musik bis", "musik erlaubt", "party bis", "open end"),
    "dj_allowed": ("dj", "dj erlaubt", "dj möglich"),
    "sound_system_available": ("sound system", "anlage", "soundanlage", "pa-anlage", "musikanlage"),
    "outdoor_party_area": ("outdoor", "garten", "terrasse", "wiese", "hof", "außenbereich", "aussenbereich"),
    "bbq_available": ("bbq", "grill", "grillen", "barbecue"),
    "fire_place": ("kamin", "feuerstelle", "fire place", "fireplace", "ofen"),
    "swimming_pool": ("pool", "schwimmbad", "swimming pool"),
    "lake_or_river_nearby": ("see", "fluss", "ufer", "seeufer", "river", "lake"),
    "private_property": ("privat", "private", "alleinlage", "exklusiv"),
}

NEGATIVE_PATTERNS: dict[str, tuple[str, ...]] = {
    "camping_allowed": ("camping nicht erlaubt", "kein camping", "ohne camping"),
    "parties_allowed": ("keine party", "no parties", "parties not allowed", "nicht für feiern"),
    "loud_music_allowed": ("keine laute musik", "loud music not allowed", "ruhe", "nachtruhe"),
    "dj_allowed": ("kein dj", "dj nicht erlaubt"),
    "bbq_available": ("kein grill", "bbq nicht erlaubt"),
    "swimming_pool": ("kein pool", "without pool"),
}


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def extract_feature_flags(text: str | None) -> dict[str, bool]:
    lower = (text or "").lower()
    flags: dict[str, bool] = {}
    for field, phrases in POSITIVE_PATTERNS.items():
        flags[field] = _contains_any(lower, phrases) and not _contains_any(lower, NEGATIVE_PATTERNS.get(field, ()))
    return flags


def extract_quiet_hours(text: str | None) -> tuple[str | None, str | None]:
    lower = (text or "").lower()
    start = None
    end = None

    quiet_match = re.search(r"(?:nachtruhe|quiet hours?|ruhe)\s*(?:ab|from|von)?\s*(\d{1,2})(?:[:.](\d{2}))?", lower)
    if quiet_match:
        hour = int(quiet_match.group(1))
        minute = int(quiet_match.group(2) or "00")
        start = f"{hour:02d}:{minute:02d}"

    range_match = re.search(r"(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr)?\s*(?:-|bis|to|until)\s*(\d{1,2})(?:[:.](\d{2}))?", lower)
    if range_match and start is None:
        hour = int(range_match.group(1))
        minute = int(range_match.group(2) or "00")
        start = f"{hour:02d}:{minute:02d}"
        end = f"{int(range_match.group(3)):02d}:{int(range_match.group(4) or '00'):02d}"

    return start, end

