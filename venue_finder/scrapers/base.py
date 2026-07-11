from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


DEFAULT_SEARCH_KEYWORDS = [
    "Partyhaus",
    "Gruppenhaus",
    "Eventlocation",
    "Ferienhaus für Gruppen",
    "Haus für 50 Personen",
    "Feier mit Übernachtung",
    "Zelten erlaubt",
    "Camping möglich",
    "Alleinlage",
    "Party venue",
    "Group accommodation",
    "Large holiday house",
    "Camping allowed",
]


@dataclass(slots=True)
class ScrapedVenue:
    source_name: str
    source_url: str
    name: str | None = None
    website: str | None = None
    venue_type: str | None = None
    raw_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseScraper(ABC):
    source_name: str
    search_keywords: list[str]
    base_url: str | None = None

    def __init__(self, *, max_results: int = 100, search_keywords: list[str] | None = None) -> None:
        self.max_results = max_results
        self.search_keywords = list(search_keywords or DEFAULT_SEARCH_KEYWORDS)

    def build_search_urls(self) -> list[str]:
        if self.base_url is None:
            return []
        return [self.search_url_for_keyword(keyword) for keyword in self.search_keywords]

    def iter_search_pages(self) -> list[tuple[str, str]]:
        """Return the keyword and URL pair used for discovery.

        Site-specific scrapers can iterate these pages and fall back to the
        source homepage if a search URL does not exist or returns nothing.
        """

        if self.base_url is None:
            return []
        return [(keyword, self.search_url_for_keyword(keyword)) for keyword in self.search_keywords]

    def search_url_for_keyword(self, keyword: str) -> str:
        if self.base_url is None:
            return keyword
        return f"{self.base_url}?q={quote_plus(keyword)}"

    def normalize_url(self, url: str | None, *, page_url: str | None = None) -> str | None:
        if url is None:
            return None
        if page_url and url.startswith("/"):
            return urljoin(page_url, url)
        return url

    def extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return " ".join(soup.stripped_strings)

    def fetch_html(self, url: str, *, timeout: int = 30) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - trusted venue sources only
                return response.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    def soup_from_url(self, url: str) -> BeautifulSoup:
        return BeautifulSoup(self.fetch_html(url), "html.parser")

    def first_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    def limit_results(self, venues: list[ScrapedVenue]) -> list[ScrapedVenue]:
        return venues[: self.max_results]

    @abstractmethod
    def scrape(self) -> list[ScrapedVenue]:
        raise NotImplementedError
