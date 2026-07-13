from __future__ import annotations

import re


_PRICE_RE = re.compile(
    r"(?:ab\s*)?(?P<amount>\d{1,5}(?:[.,]\d{1,2})?)\s*(?:\u20ac|eur)"
    r"(?:\s*(?:bis|-)\s*\d{1,5}(?:[.,]\d{1,2})?\s*(?:\u20ac|eur)?)?\s*(?:(?:/|pro)\s*)?"
    r"(?P<unit>nacht|tag|person|personen|pax)",
    re.IGNORECASE,
)


def extract_prices(text: str | None) -> tuple[float | None, float | None]:
    """Return the lowest explicitly stated nightly and per-person prices."""
    per_night: list[float] = []
    per_person: list[float] = []
    for match in _PRICE_RE.finditer(text or ""):
        amount = float(match.group("amount").replace(",", "."))
        unit = match.group("unit").lower()
        if unit in {"nacht", "tag"}:
            per_night.append(amount)
        else:
            per_person.append(amount)
    return (min(per_night) if per_night else None, min(per_person) if per_person else None)
