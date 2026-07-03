from __future__ import annotations

from .base import BaseScraper, ScrapedVenue


class AirbnbScraper(BaseScraper):
    source_name = "airbnb"

    def scrape(self) -> list[ScrapedVenue]:
        # Airbnb scraping usually requires careful site-specific handling.
        # This MVP leaves the implementation explicit so it can be tuned without changing the pipeline.
        return []

