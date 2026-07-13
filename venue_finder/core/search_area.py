from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from venue_finder.core.models import AppSetting
from venue_finder.processors.location_parser import coordinates_for_city


SETTING_KEY = "search_area"


@dataclass(frozen=True, slots=True)
class SearchArea:
    city: str = "Frankfurt am Main"
    latitude: float = 50.1109
    longitude: float = 8.6821
    radius_km: float = 250.0


def get_search_area(session: Session) -> SearchArea:
    row = session.get(AppSetting, SETTING_KEY)
    if row is None:
        return SearchArea()
    try:
        value = json.loads(row.value)
        return SearchArea(str(value["city"]), float(value["latitude"]), float(value["longitude"]), max(1.0, float(value["radius_km"])))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return SearchArea()


def _geocode_city(city: str) -> tuple[float, float] | None:
    known = coordinates_for_city(city)
    if known is not None:
        return known
    request = Request(
        "https://nominatim.openstreetmap.org/search?" + urlencode({"q": f"{city}, Germany", "format": "jsonv2", "limit": "1"}),
        headers={"User-Agent": "VenueFinder/1.0 (city search)"},
    )
    try:
        with urlopen(request, timeout=8) as response:  # noqa: S310 - public geocoding API
            results = json.loads(response.read().decode("utf-8"))
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (Exception, IndexError, KeyError, TypeError, ValueError):
        return None


def save_search_area(session: Session, city: str, radius_km: float) -> SearchArea:
    city = " ".join(city.split())
    if not city:
        raise ValueError("Enter a city name.")
    coordinates = _geocode_city(city)
    if coordinates is None:
        raise ValueError(f"Could not locate '{city}'. Try a German city name.")
    area = SearchArea(city, coordinates[0], coordinates[1], max(1.0, radius_km))
    payload = json.dumps({"city": area.city, "latitude": area.latitude, "longitude": area.longitude, "radius_km": area.radius_km})
    row = session.get(AppSetting, SETTING_KEY)
    if row is None:
        session.add(AppSetting(key=SETTING_KEY, value=payload))
    else:
        row.value = payload
    session.flush()
    return area
