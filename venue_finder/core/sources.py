from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json


DEFAULT_SOURCES = [
    {"source_name": "gruppenhaus", "enabled": True},
    {"source_name": "eventlocations", "enabled": True},
    {"source_name": "airbnb", "enabled": False},
]

SUPPORTED_SOURCE_NAMES = {item["source_name"] for item in DEFAULT_SOURCES}


@dataclass(slots=True)
class SourceEntry:
    source_name: str
    enabled: bool = True


@dataclass(slots=True)
class SourceStore:
    sources: list[SourceEntry] = field(default_factory=lambda: [SourceEntry(**item) for item in DEFAULT_SOURCES])


def _clean_source_name(value: str) -> str:
    return value.strip().lower()


def load_sources(path: Path) -> SourceStore:
    if not path.exists():
        return SourceStore()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return SourceStore()

    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list):
        return SourceStore()

    sources: list[SourceEntry] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        source_name = item.get("source_name")
        if not isinstance(source_name, str):
            continue
        cleaned = _clean_source_name(source_name)
        if not cleaned:
            continue
        enabled = bool(item.get("enabled", True))
        sources.append(SourceEntry(source_name=cleaned, enabled=enabled))

    if not sources:
        return SourceStore()
    return SourceStore(sources=sources)


def save_sources(path: Path, store: SourceStore) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sources": [
            {"source_name": entry.source_name, "enabled": bool(entry.enabled)}
            for entry in store.sources
        ]
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def list_sources(path: Path) -> list[SourceEntry]:
    return load_sources(path).sources


def add_source(path: Path, source_name: str, *, enabled: bool = True) -> SourceStore:
    store = load_sources(path)
    cleaned = _clean_source_name(source_name)
    if cleaned and cleaned not in {entry.source_name for entry in store.sources}:
        store.sources.append(SourceEntry(source_name=cleaned, enabled=enabled))
        save_sources(path, store)
    return store


def remove_source(path: Path, source_name: str) -> SourceStore:
    store = load_sources(path)
    cleaned = _clean_source_name(source_name)
    store.sources = [entry for entry in store.sources if entry.source_name != cleaned]
    if not store.sources:
        store = SourceStore()
    save_sources(path, store)
    return store


def set_source_enabled(path: Path, source_name: str, enabled: bool) -> SourceStore:
    store = load_sources(path)
    cleaned = _clean_source_name(source_name)
    changed = False
    for entry in store.sources:
        if entry.source_name == cleaned:
            entry.enabled = enabled
            changed = True
            break
    if not changed:
        store.sources.append(SourceEntry(source_name=cleaned, enabled=enabled))
    save_sources(path, store)
    return store


def reset_default_sources(path: Path) -> SourceStore:
    store = SourceStore()
    save_sources(path, store)
    return store
