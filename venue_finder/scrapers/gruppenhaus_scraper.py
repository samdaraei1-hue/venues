from __future__ import annotations

import re
from urllib.parse import quote_plus, unquote, urljoin, urlparse

from venue_finder.processors.capacity_parser import (
    extract_camping_capacity,
    extract_maximum_guests,
    extract_number_of_beds,
    extract_number_of_rooms,
)
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

    return " ".join(tokens).replace("_", " ").replace("-", " ").title()


class GruppenhausScraper(BaseScraper):
    source_name = "gruppenhaus"
    base_url = "https://www.gruppenhaus.de/uebersicht.php"
    allowed_hrefs = (".html",)

    def search_url_for_keyword(self, keyword: str) -> str:
        """Use Gruppenhaus' real results page, not the homepage query string."""
        return f"{self.base_url}?q={quote_plus(keyword)}"

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

    def _fetch_detail_text(self, url: str) -> str:
        html = self.fetch_html(url)
        if not html:
            return ""
        return self.extract_text(html)

    def _is_party_friendly(self, text: str) -> bool:
        lowered = text.lower()
        return any(term in lowered for term in ("private feiern", "familienfeiern", "feiern", "party", "fest", "veranstaltung"))

    def build_scraped_venue(
        self,
        *,
        source_url: str,
        keyword: str = "",
        page_url: str | None = None,
        fallback_text: str | None = None,
        fallback_name: str | None = None,
    ) -> ScrapedVenue | None:
        detail_text = self._fetch_detail_text(source_url)
        combined_text = "\n".join(part for part in (fallback_text, detail_text) if part)
        if not combined_text:
            return None

        lowered = combined_text.lower()
        if "gruppenhaus.de" not in source_url.lower():
            return None
        if not any(
            token in lowered
            for token in (
                "betten",
                "personen",
                "gruppenräume",
                "gruppenraeume",
                "schlafräume",
                "schlafraeume",
                "zeltplatz",
                "seminar",
                "freizeit",
                "feier",
                "party",
            )
        ):
            return None

        location_hint = infer_location_hint(name=fallback_name, raw_text=combined_text, source_url=source_url)
        display_name = _slug_to_name(source_url, city=location_hint.city) or fallback_name or source_url.rsplit("/", 1)[-1]
        if len(display_name) > 80 or display_name.lower().startswith(("ab ", "auf anfrage", "zur suche")):
            display_name = _slug_to_name(source_url, city=location_hint.city) or display_name

        venue_type = "gruppenhaus"
        if "zeltplatz" in lowered or "zelt" in lowered:
            venue_type = "zeltplatz"
        elif "seminar" in lowered:
            venue_type = "seminarhaus"
        elif "event" in lowered or "feier" in lowered or "party" in lowered:
            venue_type = "eventlocation"

        maximum_guests = extract_maximum_guests(combined_text)
        number_of_beds = extract_number_of_beds(combined_text)
        number_of_rooms = extract_number_of_rooms(combined_text)
        camping_capacity = extract_camping_capacity(combined_text)
        camping_allowed = any(term in lowered for term in ("zeltplatz", "camping", "zelten"))
        parties_allowed = self._is_party_friendly(combined_text)

        return ScrapedVenue(
            source_name=self.source_name,
            source_url=source_url,
            name=display_name,
            website=source_url,
            venue_type=venue_type,
            raw_text=combined_text,
            metadata={
                "search_keyword": keyword,
                "page_url": page_url,
                "origin": "gruppenhaus.de",
                "maximum_guests": maximum_guests,
                "number_of_beds": number_of_beds,
                "number_of_rooms": number_of_rooms,
                "camping_capacity": camping_capacity,
                "camping_allowed": camping_allowed,
                "parties_allowed": parties_allowed,
                "city_hint": location_hint.city,
                "postal_code_hint": location_hint.postal_code,
            },
        )

    def scrape(self) -> list[ScrapedVenue]:
        venues: list[ScrapedVenue] = []
        seen: set[str] = set()

        candidate_pages = self.iter_search_pages() or [("", self.base_url)]

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
                seen.add(source_url)

                card = anchor.find_parent(["li", "article", "div"]) or anchor.parent
                card_text = self.first_text(card.get_text(" ", strip=True) if card else text) or text
                scraped = self.build_scraped_venue(
                    source_url=source_url,
                    keyword=keyword,
                    page_url=page_url,
                    fallback_text=card_text,
                    fallback_name=text,
                )
                if scraped is not None:
                    venues.append(scraped)
                    if len(venues) >= self.max_results:
                        return venues

        return self.limit_results(venues)
