from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from venue_finder.core.models import Keyword, Venue
from venue_finder.processors.duplicate_detector import detect_duplicate
from venue_finder.core.keywords import DEFAULT_SEARCH_KEYWORDS


@dataclass(slots=True)
class VenueFilters:
    max_distance_km: float | None = None
    max_budget: float | None = None
    guest_count: int | None = None
    min_party_score: int | None = None
    camping_only: bool = False
    swimming_pool: bool = False
    bbq: bool = False
    loud_music_allowed: bool = False
    weekend_available: bool = False


def apply_filters(query, filters: VenueFilters):
    if filters.max_distance_km is not None:
        query = query.where(Venue.distance_from_frankfurt_km <= filters.max_distance_km)
    if filters.min_party_score is not None:
        query = query.where(Venue.party_score >= filters.min_party_score)
    if filters.camping_only:
        query = query.where(Venue.camping_allowed.is_(True))
    if filters.swimming_pool:
        query = query.where(Venue.swimming_pool.is_(True))
    if filters.bbq:
        query = query.where(Venue.bbq_available.is_(True))
    if filters.loud_music_allowed:
        query = query.where(Venue.loud_music_allowed.is_(True))
    if filters.guest_count is not None:
        query = query.where(
            or_(
                Venue.maximum_guests.is_(None),
                Venue.maximum_guests >= filters.guest_count,
            )
        )
    if filters.max_budget is not None:
        query = query.where(
            or_(
                Venue.price_per_night.is_(None),
                Venue.price_per_night <= filters.max_budget,
                Venue.price_per_person.is_(None),
                Venue.price_per_person <= filters.max_budget,
            )
        )
    if filters.weekend_available:
        query = query.where(
            or_(
                Venue.available_dates.isnot(None),
                Venue.minimum_nights.is_(None),
                Venue.minimum_nights <= 2,
            )
        )
    return query


def _is_displayable_venue(venue: Venue) -> bool:
    if venue.source_name == "demo":
        return False
    if venue.source_name == "gruppenhaus" and venue.source_url:
        lower = venue.source_url.lower()
        if "gruppenhaus.de" in lower and not re.search(r"-hs\d+\.html(?:\?.*)?$", lower):
            return False
    return True


def list_venues(session: Session, filters: VenueFilters | None = None) -> list[Venue]:
    query = select(Venue).order_by(Venue.party_score.desc().nullslast(), Venue.id.asc())
    if filters is not None:
        query = apply_filters(query, filters)
    venues = list(session.scalars(query).all())
    return [venue for venue in venues if _is_displayable_venue(venue)]


def get_venue_by_id(session: Session, venue_id: int) -> Venue | None:
    return session.scalar(select(Venue).where(Venue.id == venue_id))


def delete_venue_by_id(session: Session, venue_id: int) -> bool:
    venue = get_venue_by_id(session, venue_id)
    if venue is None:
        return False
    session.delete(venue)
    session.flush()
    return True


def upsert_manual_venue(session: Session, venue: Venue) -> tuple[Venue, bool]:
    """Insert or update a venue created/edited from the UI.

    Strategy:
    - Prefer matching by `id` if provided.
    - Else match by `source_url` if it exists.
    - Else insert as new.

    We intentionally DO NOT merge fuzzy duplicates here; manual editing should be
    predictable and user-driven.
    """

    if venue.id is not None:
        existing = get_venue_by_id(session, venue.id)
        if existing is not None:
            _merge_non_null_fields(existing, venue)
            session.flush()
            return existing, False

    if venue.source_url:
        existing = session.scalar(select(Venue).where(Venue.source_url == venue.source_url))
        if existing is not None:
            _merge_non_null_fields(existing, venue)
            session.flush()
            return existing, False

    session.add(venue)
    session.flush()
    return venue, True





def _merge_non_null_fields(target: Venue, source: Venue) -> None:
    for column in Venue.__table__.columns.keys():
        if column in {"id", "created_at", "updated_at", "source_url"}:
            continue
        value = getattr(source, column, None)
        if value is not None:
            setattr(target, column, value)


def _merge_scraped_fields(target: Venue, source: Venue) -> None:
    """Merge freshly scraped data and prefer newer structured values.

    Scrapers often get better at extracting names, cities, and capacities over
    time. For that reason, scraped rows should be allowed to replace older text
    values instead of only filling empty slots.
    """

    for column in Venue.__table__.columns.keys():
        if column in {"id", "created_at", "updated_at", "source_url"}:
            continue

        value = getattr(source, column, None)
        if value is None:
            continue

        if column in {
            "camping_allowed",
            "camper_van_allowed",
            "parties_allowed",
            "loud_music_allowed",
            "dj_allowed",
            "sound_system_available",
            "outdoor_party_area",
            "bbq_available",
            "fire_place",
            "swimming_pool",
            "lake_or_river_nearby",
            "private_property",
        }:
            # A new detail-page scrape is authoritative. Keeping an old `True`
            # here made false positives (for example camping from a footer)
            # impossible to correct on later runs.
            setattr(target, column, bool(value))
            continue

        setattr(target, column, value)


def _venue_similarity(left: Venue, right: Venue) -> tuple[bool, str, float]:
    result = detect_duplicate(
        name_a=left.name,
        name_b=right.name,
        address_a=left.street_address,
        address_b=right.street_address,
        lat_a=left.latitude,
        lon_a=left.longitude,
        lat_b=right.latitude,
        lon_b=right.longitude,
    )
    return result.is_duplicate, result.reason, result.score


def upsert_venue(session: Session, venue: Venue) -> tuple[Venue, bool, str]:
    existing = session.scalar(select(Venue).where(Venue.source_url == venue.source_url))
    if existing is not None:
        _merge_scraped_fields(existing, venue)
        return existing, False, "updated by source_url"
    # Each source URL is an individual listing. Name-based merging incorrectly
    # collapsed distinct venues such as different Jugendherberge locations.
    session.add(venue)
    return venue, True, "inserted"


def upsert_venues(session: Session, venues: Iterable[Venue]) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    seen_source_urls: set[str] = set()
    for venue in venues:
        if venue.source_url in seen_source_urls:
            outcomes.append(
                {
                    "id": None,
                    "source_url": venue.source_url,
                    "created": False,
                    "reason": "skipped duplicate source_url in batch",
                }
            )
            continue
        seen_source_urls.add(venue.source_url)
        saved, created, reason = upsert_venue(session, venue)
        outcomes.append(
            {
                "id": saved.id,
                "source_url": saved.source_url,
                "created": created,
                "reason": reason,
            }
        )
    session.flush()
    return outcomes


def list_keywords(session: Session) -> list[str]:
    keywords = [row.keyword for row in session.scalars(select(Keyword).order_by(Keyword.keyword.asc())).all()]
    return keywords


def seed_default_keywords(session: Session) -> list[str]:
    existing = set(list_keywords(session))
    added = []
    for keyword in DEFAULT_SEARCH_KEYWORDS:
        if keyword not in existing:
            session.add(Keyword(keyword=keyword))
            added.append(keyword)
    if added:
        session.flush()
    return list_keywords(session)


def replace_keywords(session: Session, keywords: Iterable[str]) -> list[str]:
    session.query(Keyword).delete()
    cleaned = []
    seen = set()
    for keyword in keywords:
        value = keyword.strip()
        if value and value not in seen:
            seen.add(value)
            cleaned.append(value)
            session.add(Keyword(keyword=value))
    if not cleaned:
        for keyword in DEFAULT_SEARCH_KEYWORDS:
            if keyword not in seen:
                session.add(Keyword(keyword=keyword))
                cleaned.append(keyword)
    session.flush()
    return list_keywords(session)


def add_keyword(session: Session, keyword: str) -> list[str]:
    value = keyword.strip()
    if value and session.scalar(select(Keyword).where(Keyword.keyword == value)) is None:
        session.add(Keyword(keyword=value))
        session.flush()
    return list_keywords(session)


def remove_keyword(session: Session, keyword: str) -> list[str]:
    value = keyword.strip()
    session.query(Keyword).filter(Keyword.keyword == value).delete()
    remaining = list_keywords(session)
    if not remaining:
        remaining = replace_keywords(session, DEFAULT_SEARCH_KEYWORDS)
    session.flush()
    return remaining


def delete_sample_venues(session: Session) -> int:
    deleted = (
        session.query(Venue)
        .filter(
            or_(
                Venue.source_name == "demo",
                Venue.source_name == "manual",
                Venue.source_url.like("https://example.com/%"),
            )
        )
        .delete(synchronize_session=False)
    )
    session.flush()
    return int(deleted)
