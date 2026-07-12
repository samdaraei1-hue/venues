from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re
from pathlib import Path
import shutil
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

    def _browser_executable_candidates(self) -> list[str]:
        candidates = [
            shutil.which("chrome.exe"),
            shutil.which("msedge.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        return [candidate for candidate in candidates if candidate and Path(candidate).exists()]

    def _fetch_html_with_playwright(self, url: str, *, timeout: int = 10) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return ""

        last_error: Exception | None = None
        with sync_playwright() as p:
            executable_candidates = self._browser_executable_candidates()
            launch_kwargs: dict[str, Any] = {
                "headless": True,
                "args": [
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-dev-shm-usage",
                ],
            }

            for executable_path in executable_candidates or [None]:
                try:
                    if executable_path:
                        launch_kwargs["executable_path"] = executable_path
                    else:
                        launch_kwargs.pop("executable_path", None)

                    browser = p.chromium.launch(**launch_kwargs)
                    context = browser.new_context(
                        locale="de-DE",
                        java_script_enabled=True,
                        ignore_https_errors=True,
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                        ),
                    )
                    page = context.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=timeout * 1000)
                    except Exception:
                        pass
                    html = page.content()
                    context.close()
                    browser.close()
                    return html
                except Exception as exc:  # pragma: no cover - browser/network dependent
                    last_error = exc
                    continue

        if last_error is not None:
            return ""
        return ""

    def fetch_html(self, url: str, *, timeout: int = 10) -> str:
        html = self._fetch_html_with_playwright(url, timeout=timeout)
        if html:
            return html

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

    def slug_to_name(self, url: str | None, *, city: str | None = None) -> str | None:
        if not url:
            return None
        path = url.split("?", 1)[0].rstrip("/")
        slug = path.rsplit("/", 1)[-1]
        slug = re.sub(r"\.html?$", "", slug, flags=re.IGNORECASE)
        slug = re.sub(r"-hs\d+$", "", slug, flags=re.IGNORECASE)
        slug = slug.replace("-deutschland", "").replace("-germany", "")
        tokens = [token for token in slug.split("-") if token]
        if not tokens:
            return None

        if city:
            city_tokens = [token for token in re.split(r"[\s\-]+", city.lower()) if token]
            while tokens and city_tokens and tokens[-len(city_tokens):] == city_tokens:
                tokens = tokens[:-len(city_tokens)]

        if tokens and tokens[-1].isdigit():
            tokens = tokens[:-1]

        tokens = [token for token in tokens if token not in {"de", "deutschland", "germany"}]
        if not tokens:
            return None

        cleaned = " ".join(token.replace("ue", "ü").replace("ae", "ä").replace("oe", "ö") for token in tokens)
        return cleaned.title()

    def limit_results(self, venues: list[ScrapedVenue]) -> list[ScrapedVenue]:
        return venues[: self.max_results]

    @abstractmethod
    def scrape(self) -> list[ScrapedVenue]:
        raise NotImplementedError
