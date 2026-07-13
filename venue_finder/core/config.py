from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass(slots=True)
class AppConfig:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///venue_finder.db"))
    frankfurt_latitude: float = 50.1109
    frankfurt_longitude: float = 8.6821
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("VENUE_FINDER_OUTPUT_DIR", "exports")))
    keywords_file: Path = field(default_factory=lambda: Path(os.getenv("VENUE_FINDER_KEYWORDS_FILE", "venue_keywords.json")))
    sources_file: Path = field(default_factory=lambda: Path(os.getenv("VENUE_FINDER_SOURCES_FILE", "venue_sources.json")))
    max_search_results: int = 300
    min_party_score_to_keep: int = 40


def get_config() -> AppConfig:
    return AppConfig()
