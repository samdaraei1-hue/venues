from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import BaseScraper, ScrapedVenue


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
        "übernacht",
        "uebernacht",
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
        if bool(re.search(r"-hs\d+\.html(?:\?.*)?$", lowered_href)):
            return True
        return ".html" in lowered_href and any(token in lowered_text for token in self.venue_signals)


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

                card = anchor.find_parent(["li", "article", "div"]) or anchor.parent
                raw_text = self.first_text(card.get_text(" ", strip=True) if card else text) or text
                lowered = raw_text.lower()
                if not any(token in lowered for token in self.venue_signals):
                    continue

                source_url = urljoin(page_url, href)
                if source_url.rstrip("/") in {self.base_url.rstrip("/"), "https://www.gruppenhaus.de"}:
                    continue
                if source_url in seen:
                    continue
                seen.add(source_url)

                venue_type = "gruppenhaus"
                if "zeltplatz" in lowered:
                    venue_type = "zeltplatz"
                elif "seminar" in lowered:
                    venue_type = "seminarhaus"
                elif "event" in lowered or "feier" in lowered or "party" in lowered:
                    venue_type = "eventlocation"

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
                            "origin": "gruppenhaus.de",
                        },
                    )
                )

        return self.limit_results(venues)
