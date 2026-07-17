from __future__ import annotations

import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseScraper, ScrapedVenue


class EventlocationsScraper(BaseScraper):
    source_name = "eventlocations"
    base_url = "https://www.eventlocations.com/de"
    allowed_hrefs = ("/de/venues/",)
    venue_signals = (
        "eventlocation",
        "location",
        "venue",
        "veranstaltung",
        "party",
        "raum",
        "saal",
        "person",
        "personen",
        "m2",
        "m²",
        "price on request",
        "preis auf anfrage",
    )

    def search_url_for_keyword(self, keyword: str) -> str:
        # Eventlocations uses city landing pages rather than a ?q= endpoint.
        city = keyword.strip().lower().split(" am ", 1)[0]
        normalized = unicodedata.normalize("NFKD", city).encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
        return f"{self.base_url}/{slug}" if slug else self.base_url

    def _is_listing_link(self, href: str, text: str) -> bool:
        lowered_href = href.lower()
        if href in {self.base_url, "/", "https://www.eventlocations.com/de/", "https://www.eventlocations.com/"}:
            return False
        if any(token in lowered_href for token in ("impressum", "datenschutz", "kontakt", "login", "register", "about", "blog")):
            return False
        if not any(token in lowered_href for token in self.allowed_hrefs):
            return False
        # The /de/venues/ path is the stable listing contract. Requiring words
        # such as "venue" in the title rejected valid venue links.
        return True

    def scrape(self) -> list[ScrapedVenue]:
        venues: list[ScrapedVenue] = []
        seen: set[str] = set()

        # The first keyword is always the configured search-area city. One city
        # page contains the venue inventory; generic keyword pages do not exist.
        candidate_pages = (self.iter_search_pages() or [("", self.base_url)])[:1]

        for keyword, page_url in candidate_pages:
            html = self._fetch_html_with_request(page_url, timeout=20)
            if not html:
                html = self.fetch_html(page_url, timeout=15, prefer_browser=True)
            soup = BeautifulSoup(html, "html.parser")
            if not soup:
                continue

            for anchor in soup.select("a[href]"):
                text = self.first_text(anchor.get_text(" ", strip=True))
                href = anchor.get("href")
                if not text or not href:
                    continue

                if not self._is_listing_link(href, text):
                    continue

                card = anchor.find_parent(["li", "article", "div"]) or anchor.parent
                raw_text = self.first_text(card.get_text(" ", strip=True) if card else text) or text
                lowered = raw_text.lower()
                source_url = urljoin(page_url, href)
                if source_url.rstrip("/") in {self.base_url.rstrip("/"), "https://www.eventlocations.com"}:
                    continue
                if source_url in seen:
                    continue
                seen.add(source_url)

                venue_type = "eventlocation"
                if "party room" in lowered or "partyraum" in lowered or "partykeller" in lowered:
                    venue_type = "partyroom"
                elif "rooftop" in lowered or "dachterrasse" in lowered:
                    venue_type = "rooftop"
                elif "restaurant" in lowered:
                    venue_type = "restaurant"

                venues.append(
                    ScrapedVenue(
                        source_name=self.source_name,
                        source_url=source_url,
                        name=text,
                        website=source_url,
                        venue_type=venue_type,
                        raw_text=raw_text,
                        metadata={
                            "search_keyword": keyword,
                            "page_url": page_url,
                            "origin": "eventlocations.com",
                        },
                    )
                )

        return self.limit_results(venues)
