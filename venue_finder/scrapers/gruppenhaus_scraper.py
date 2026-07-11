from __future__ import annotations

import re
from urllib.parse import unquote, urljoin, urlparse

from venue_finder.processors.location_parser import infer_location_hint

from .base import BaseScraper, ScrapedVenue


def _slug_to_name(source_url: str, city: str | None = None) -> str | None:
    path = unquote(urlparse(source_url).path).strip("/")
    if not path:
        return None
    slug = path.rsplit("/", 1)[-1]
    slug = re.sub(r"\.html?$", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"-hs\d+$", "", slug, flags=re.IGNORECASE)
    tokens = [token for token in slug.split("-") if token]
    if not tokens:
        return None

    if city:
        city_tokens = [token for token in re.split(r"[\s\-]+", city.lower()) if token]
        while tokens and city_tokens and tokens[-len(city_tokens):] == city_tokens:
            tokens = tokens[:-len(city_tokens)]

    tokens = [token for token in tokens if token not in {"de", "deutschland", "germany"}]
    if not tokens:
        return None

    name = " ".join(tokens).replace("_", " ").replace("-", " ").strip()
    return name.title() or None


class GruppenhausScraper(BaseScraper):
    source_name = "gruppenhaus"
    base_url = "https://www.gruppenhaus.de/"
    allowed_hrefs = (".html",)
    venue_signals = (
        "gruppenhaus",
        "event",
        "ferienhaus",
        "party",
        "seminar",
        "tagung",
        "haus",
        "zelt",
        "personen",
        "betten",
        "zimmer",
        "uebernacht",
        "uebernachtung",
    )

    def _is_listing_link(self, href: str, text: str) -> bool:
        lowered_text = text.lower()
        lowered_href = href.lower()
        if href in {self.base_url, "/", "https://www.gruppenhaus.de/", "https://www.gruppenhaus.de"}:
            return False
        if not any(token in lowered_href for token in self.allowed_hrefs):
            return False
        if any(token in lowered_href for token in ("impressum", "datenschutz", "kontakt", "agb", "login", "newsletter", "facebook", "instagram")):
            return False
        if any(token in lowered_text for token in ("impressum", "datenschutz", "kontakt", "agb", "login")):
            return False
        return bool(re.search(r"-hs\d+\.html(?:\?.*)?$", lowered_href))

    def scrape(self) -> list[ScrapedVenue]:
        venues: list[ScrapedVenue] = []
        seen: set[str] = set()

        candidate_pages = self.iter_search_pages() or [("", self.base_url)]
        candidate_pages.append(("", self.base_url))

        for keyword, page_url in candidate_pages:
            soup = self.soup_from_url(page_url)
            if not soup:
                continue

            for anchor in soup.select("a[href]"):
                text = self.first_text(anchor.get_text(" ", strip=True))
                href = anchor.get("href")
                if not text or not href:
                    continue

                if not self._is_listing_link(href, text):
                    continue

                source_url = urljoin(page_url, href)
                if source_url.rstrip("/") in {self.base_url.rstrip("/"), "https://www.gruppenhaus.de"}:
                    continue
                if source_url in seen:
                    continue

                card = anchor.find_parent(["li", "article", "div"]) or anchor.parent
                raw_text = self.first_text(card.get_text(" ", strip=True) if card else text) or text
                lowered = raw_text.lower()
                if not any(token in lowered for token in self.venue_signals) and not re.search(
                    r"\b(?:betten|personen|gruppenzimmer|schlafraeume|schlafräume)\b",
                    lowered,
                ):
                    continue

                seen.add(source_url)
                location_hint = infer_location_hint(name=text, raw_text=raw_text, source_url=source_url)
                display_name = _slug_to_name(source_url, city=location_hint.city) or text
                if len(display_name) > 80 or display_name.lower().startswith(("ab ", "auf anfrage", "zur suche")):
                    display_name = _slug_to_name(source_url, city=location_hint.city) or text

                venue_type = "gruppenhaus"
                if "zeltplatz" in lowered or "zelt" in lowered:
                    venue_type = "zeltplatz"
                elif "seminar" in lowered:
                    venue_type = "seminarhaus"
                elif "event" in lowered or "feier" in lowered or "party" in lowered:
                    venue_type = "eventlocation"

                venues.append(
                    ScrapedVenue(
                        source_name=self.source_name,
                        source_url=source_url,
                        name=display_name,
                        website=source_url,
                        venue_type=venue_type,
                        raw_text=raw_text,
                        metadata={
                            "search_keyword": keyword,
                            "page_url": page_url,
                            "origin": "gruppenhaus.de",
                        },
                    )
                )

        return self.limit_results(venues)
