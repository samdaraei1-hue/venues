from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from math import radians, sin, cos, sqrt, atan2


@dataclass(slots=True)
class DuplicateMatch:
    is_duplicate: bool
    reason: str
    score: float


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text


def similarity_score(a: str | None, b: str | None) -> float:
    left = _normalize(a)
    right = _normalize(b)
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    token_overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return max(sequence, token_overlap)


def _distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    radius_km = 6371.0
    d_lat = radians(lat_b - lat_a)
    d_lon = radians(lon_b - lon_a)
    lat_a = radians(lat_a)
    lat_b = radians(lat_b)

    a = sin(d_lat / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(d_lon / 2) ** 2
    return 2 * radius_km * atan2(sqrt(a), sqrt(1 - a))


def detect_duplicate(
    *,
    name_a: str | None,
    name_b: str | None,
    address_a: str | None,
    address_b: str | None,
    lat_a: float | None,
    lon_a: float | None,
    lat_b: float | None,
    lon_b: float | None,
) -> DuplicateMatch:
    name_similarity = similarity_score(name_a, name_b)
    address_similarity = similarity_score(address_a, address_b)

    coordinate_match = False
    geographic_distance = None
    if None not in (lat_a, lon_a, lat_b, lon_b):
        geographic_distance = _distance_km(lat_a, lon_a, lat_b, lon_b)
        coordinate_match = geographic_distance <= 0.3

    score = max(name_similarity, address_similarity)
    if coordinate_match:
        score = max(score, 0.95)
    elif geographic_distance is not None and geographic_distance <= 0.1:
        score = max(score, 0.9)

    is_duplicate = coordinate_match or score >= 0.88
    if coordinate_match:
        reason = f"Matching GPS coordinates ({geographic_distance:.2f} km)"
    elif geographic_distance is not None and geographic_distance <= 0.1:
        reason = f"Very close GPS coordinates ({geographic_distance:.2f} km)"
    elif address_similarity >= 0.9:
        reason = "Highly similar addresses"
    elif name_similarity >= 0.92:
        reason = "Highly similar names"
    else:
        reason = "No duplicate signal strong enough"

    return DuplicateMatch(is_duplicate=is_duplicate, reason=reason, score=round(score, 3))
