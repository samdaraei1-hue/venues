from __future__ import annotations

from dataclasses import dataclass
import math

try:
    from geopy.distance import geodesic
except Exception:  # pragma: no cover - optional dependency fallback
    geodesic = None


@dataclass(slots=True)
class DistanceResult:
    distance_km: float | None
    driving_time_minutes: int | None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> DistanceResult:
    if None in (lat1, lon1, lat2, lon2):
        return DistanceResult(None, None)

    if geodesic is not None:
        distance_km = float(geodesic((lat1, lon1), (lat2, lon2)).km)
    else:
        distance_km = _haversine_km(lat1, lon1, lat2, lon2)

    driving_time_minutes = max(1, round(distance_km * 1.35 * 60 / 80))
    return DistanceResult(round(distance_km, 1), driving_time_minutes)

