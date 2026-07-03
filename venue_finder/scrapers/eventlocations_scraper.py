from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper, ScrapedVenue


class EventlocationsScraper(BaseScraper):
    source_name = "eventlocations"
    base_url = "https://www.eventlocations.com/de"
    allowed_hrefs = ("/de/venues/",)

    def _is_listing_link(self, href: str, text: str) -> bool:
        lowered_text = text.lower()
        lowered_href = href.lower()
        if href in {self.base_url, "/", "https://www.eventlocations.com/de/", "https://www.eventlocations.com/"}:
            return False
        if any(token in lowered_href for token in ("impressum", "datenschutz", "kontakt", "login", "register", "about", "blog")):
            return False
        if not any(token in lowered_href for token in self.allowed_hrefs):
            return False
        return "," in lowered_text or bool(re.search(r"\b[a-zäöüß].*\d", lowered_text))

    def scrape(self) -> list[ScrapedVenue]:
        soup = self.soup_from_url(self.base_url)
        venues: list[ScrapedVenue] = []

        for anchor in soup.select("a[href]"):
            text = self.first_text(anchor.get_text(" ", strip=True))
            href = anchor.get("href")
            if not text or not href:
                continue

            if not self._is_listing_link(href, text):
                continue

            card = anchor.find_parent(["li", "article", "div"]) or anchor.parent
            raw_text = self.first_text(card.get_text(" ", strip=True) if card else text)
            if not raw_text:
                raw_text = text

            if "price on request" not in raw_text.lower() and "preis auf anfrage" not in raw_text.lower() and "person" not in raw_text.lower() and "personen" not in raw_text.lower() and "m2" not in raw_text.lower():
                continue

            source_url = urljoin(self.base_url, href)
            if source_url.rstrip("/") in {self.base_url.rstrip("/"), "https://www.eventlocations.com"}:
                continue
            lowered = raw_text.lower()
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
                        "origin": "recently added cards",
                        "cards_source": "eventlocations.com",
                    },
                )
            )

        return self.limit_results(venues)
