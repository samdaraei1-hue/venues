from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper, ScrapedVenue


class GruppenhausScraper(BaseScraper):
    source_name = "gruppenhaus"
    base_url = "https://www.gruppenhaus.de/"
    allowed_hrefs = ("-hs",)

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
        return bool(re.search(r"\b\d{5}\b", lowered_text))

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
            source_url = urljoin(self.base_url, href)
            if source_url.rstrip("/") in {self.base_url.rstrip("/"), "https://www.gruppenhaus.de"}:
                continue
            venue_type = "gruppenhaus"
            if "zeltplatz" in text.lower():
                venue_type = "zeltplatz"
            elif "seminar" in text.lower():
                venue_type = "seminarhaus"

            venues.append(
                ScrapedVenue(
                    source_name=self.source_name,
                    source_url=source_url,
                    name=text,
                    website=source_url,
                    venue_type=venue_type,
                    raw_text=raw_text,
                    metadata={
                        "origin": "hessen listing",
                        "cards_source": "gruppenhaus.de",
                    },
                )
            )

        return self.limit_results(venues)
