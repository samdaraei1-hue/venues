from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse, unquote


POSTAL_CITY_RE = re.compile(r"\b(?P<postal>\d{5})\s+(?P<city>[A-ZÄÖÜ][^,;/\n]+)", re.UNICODE)
COMMA_CITY_RE = re.compile(r"(?P<city>[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-\s\.]{1,60})\s*,\s*(?:Deutschland|Germany)", re.UNICODE)
GENERIC_CITY_TOKENS = {
    "deutschland",
    "germany",
    "hessen",
    "bayern",
    "berlin",
    "brandenburg",
    "bremen",
    "hamburg",
    "niedersachsen",
    "nrw",
    "nordrhein-westfalen",
    "rheinland-pfalz",
    "saarland",
    "sachsen",
    "sachsen-anhalt",
    "schleswig-holstein",
    "thueringen",
    "thüringen",
    "ost",
    "west",
    "nord",
    "sued",
    "süd",
    "tagungshaus",
    "seminarhaus",
    "gruppenhaus",
    "zeltplatz",
    "selbstversorgerhaus",
    "ferienhaus",
    "gaestehaus",
    "gästehaus",
}


@dataclass(slots=True)
class LocationHint:
    city: str | None = None
    postal_code: str | None = None
    street_address: str | None = None
    state: str | None = None
    country: str | None = None


def _clean_city(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.split()).strip(" ,.;")
    return cleaned or None


def _clean_postal(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value if re.fullmatch(r"\d{5}", value) else None


def _city_from_slug(source_url: str | None) -> str | None:
    if not source_url:
        return None
    path = unquote(urlparse(source_url).path).strip("/")
    if not path:
        return None
    slug = path.split("/")[-1]
    slug = slug.split("?")[0]
    if "-" not in slug:
        return None
    slug = slug.rsplit(".", 1)[0]
    slug = slug.replace("-hs", "-").replace("-de", "-")
    parts = [part for part in slug.split("-") if part]
    if not parts:
        return None
    tail = parts[-1]
    if tail.isdigit():
        return None
    if tail.lower() in GENERIC_CITY_TOKENS:
        return None
    if len(parts) >= 2 and parts[-2].lower() in {"de", "deutschland", "germany"}:
        candidate = parts[-3] if len(parts) >= 3 else parts[-1]
        return None if candidate.lower() in GENERIC_CITY_TOKENS else _clean_city(candidate)
    return _clean_city(tail)


def infer_location_hint(*, name: str | None = None, raw_text: str | None = None, source_url: str | None = None) -> LocationHint:
    text = " ".join(part for part in (name, raw_text) if part)
    hint = LocationHint()

    postal_match = POSTAL_CITY_RE.search(text)
    if postal_match:
        hint.postal_code = _clean_postal(postal_match.group("postal"))
        hint.city = _clean_city(postal_match.group("city"))

    if hint.city is None:
        comma_match = COMMA_CITY_RE.search(text)
        if comma_match:
            hint.city = _clean_city(comma_match.group("city"))

    if hint.city is None:
        hint.city = _city_from_slug(source_url)

    if hint.city is None and raw_text:
        # Look for strings like "Ort: Mainz" or "Location: Hamburg".
        for pattern in (r"(?:Ort|Location|City|Stadt)\s*[:\-]\s*([A-ZÄÖÜ][^,\n;]+)",):
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                candidate = _clean_city(match.group(1))
                if candidate and candidate.lower() not in GENERIC_CITY_TOKENS:
                    hint.city = candidate
                break

    if hint.city and not hint.country:
        hint.country = "Germany"

    return hint
