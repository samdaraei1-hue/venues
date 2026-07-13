from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import unquote, urlparse


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
    "thuringen",
    "ost",
    "west",
    "nord",
    "sued",
    "sud",
    "tagungshaus",
    "seminarhaus",
    "gruppenhaus",
    "zeltplatz",
    "selbstversorgerhaus",
    "ferienhaus",
    "gaestehaus",
    "gastehaus",
}

CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "frankfurt am main": (50.1109, 8.6821),
    "frankfurt": (50.1109, 8.6821),
    "wiesbaden": (50.0826, 8.24),
    "mainz": (49.9929, 8.2473),
    "darmstadt": (49.8728, 8.6512),
    "kassel": (51.3127, 9.4797),
    "offenbach": (50.0956, 8.7761),
    "offenbach am main": (50.0956, 8.7761),
    "hanau": (50.1218, 8.9283),
    "giessen": (50.584, 8.6784),
    "marburg": (50.8072, 8.7706),
    "fulda": (50.5558, 9.6808),
    "wetzlar": (50.5617, 8.5044),
    "bad homburg": (50.2263, 8.6185),
    "ruesselsheim": (49.991, 8.413),
    "russelsheim": (49.991, 8.413),
    "hohenstein": (50.2, 8.04),
    "hilders": (50.5698, 9.9974),
    "gersfeld": (50.4517, 9.9124),
    "breuberg": (49.8247, 9.0345),
    "alheim": (51.0363, 9.6075),
    "knullwald": (51.0135, 9.5137),
    "schotten": (50.5032, 9.1255),
    "dornburg": (50.5159, 8.0162),
    "schenklengsfeld": (50.8186, 9.8468),
    "oberzent": (49.557, 8.956),
    "homberg": (51.03, 9.4),
    "huenfelden": (50.33, 8.15),
    "huenfeld": (50.5667, 9.7),
    "bad zwesten": (51.04, 9.17),
    "greifenstein": (50.6164, 8.2928),
    "hessen": (50.6667, 9.0),
    "usseln": (51.29, 8.66),
    "willingen": (51.29, 8.61),
    "lauterbach": (50.637, 9.394),
    "ehrenberg rhoen": (50.52, 9.98),
    "schluchtern": (50.35, 9.53),
    "schluechtern": (50.35, 9.53),
    "floersbachtal": (50.12, 9.43),
    "hessisch lichtenau": (51.2, 9.72),
    "schmitten": (50.27, 8.44),
    "hofbieber": (50.58, 9.85),
    "hammersbach": (50.22, 8.98),
    "eschwege": (51.19, 10.05),
    "rosenthal": (50.98, 8.87),
    "meinhard": (51.21, 10.06),
    "braunfels": (50.52, 8.39),
    "muenchhausen": (50.96, 8.72),
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


def _normalize_key(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip().lower()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


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
    # Gruppenhaus URLs end in `-city-name-hs1234`.  Strip the listing ID
    # before reading the city; otherwise the last token is only a number.
    slug = re.sub(r"-hs\d+$", "", slug, flags=re.IGNORECASE)
    slug = slug.replace("-hs", "-").replace("-de", "-")
    parts = [part for part in slug.split("-") if part]
    if not parts:
        return None
    # Prefer a known multi-word city at the end of the slug.  This handles
    # URLs such as `...-frankfurt-frankfurt-am-main-hs3026` correctly.
    for length in range(min(4, len(parts)), 1, -1):
        candidate = " ".join(parts[-length:])
        if coordinates_for_city(candidate) is not None:
            return _clean_city(candidate)

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


def coordinates_for_city(city: str | None) -> tuple[float, float] | None:
    key = _normalize_key(city)
    return CITY_COORDINATES.get(key)
