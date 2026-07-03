from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json


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
class KeywordStore:
    search_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_SEARCH_KEYWORDS))


def load_keywords(path: Path) -> KeywordStore:
    if not path.exists():
        return KeywordStore()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return KeywordStore()

    keywords = data.get("search_keywords")
    if not isinstance(keywords, list):
        return KeywordStore()

    cleaned = []
    for keyword in keywords:
        if isinstance(keyword, str):
            value = keyword.strip()
            if value:
                cleaned.append(value)

    return KeywordStore(search_keywords=cleaned or list(DEFAULT_SEARCH_KEYWORDS))


def save_keywords(path: Path, store: KeywordStore) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"search_keywords": store.search_keywords}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def add_keyword(path: Path, keyword: str) -> KeywordStore:
    store = load_keywords(path)
    cleaned = keyword.strip()
    if cleaned and cleaned not in store.search_keywords:
        store.search_keywords.append(cleaned)
        save_keywords(path, store)
    return store


def remove_keyword(path: Path, keyword: str) -> KeywordStore:
    store = load_keywords(path)
    cleaned = keyword.strip()
    store.search_keywords = [item for item in store.search_keywords if item != cleaned]
    if not store.search_keywords:
        store.search_keywords = list(DEFAULT_SEARCH_KEYWORDS)
    save_keywords(path, store)
    return store

