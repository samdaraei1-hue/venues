from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from .base import BaseScraper, ScrapedVenue


class AirbnbScraper(BaseScraper):
    source_name = "airbnb"
    base_url = "https://www.airbnb.com"

    def search_url_for_keyword(self, keyword: str) -> str:
        # Airbnb search pages are location oriented. We still keep the query
        # string keyword so discovery has a deterministic entry point.
        return f"{self.base_url}/s/{quote_plus(keyword)}"

    def scrape(self) -> list[ScrapedVenue]:
        venues: list[ScrapedVenue] = []
        seen: set[str] = set()

        for keyword, search_url in self.iter_search_pages():
            soup = self.soup_from_url(search_url)
            if not soup:
                continue

            for anchor in soup.select("a[href]"):
                href = anchor.get("href")
                text = self.first_text(anchor.get_text(" ", strip=True))
                if not href or not text:
                    continue
                if "/rooms/" not in href and "/homes/" not in href and "/listings/" not in href:
                    continue

                source_url = urljoin(search_url, href)
                if source_url in seen:
                    continue
                seen.add(source_url)

                card = anchor.find_parent(["li", "article", "div"]) or anchor.parent
                raw_text = self.first_text(card.get_text(" ", strip=True) if card else text) or text
                if len(raw_text) < 20:
                    continue

                venues.append(
                    ScrapedVenue(
                        source_name=self.source_name,
                        source_url=source_url,
                        name=text,
                        website=source_url,
                        venue_type="airbnb",
                        raw_text=raw_text,
                        metadata={
                            "search_keyword": keyword,
                            "search_url": search_url,
                        },
                    )
                )

        return self.limit_results(venues)
