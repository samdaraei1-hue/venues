from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

from venue_finder.core.config import AppConfig, get_config

from venue_finder.core.database import init_from_config, session_scope
from venue_finder.core.models import Venue
from venue_finder.core.repository import list_keywords, list_venues, seed_default_keywords, upsert_venues
# Exports are optional in serverless environments (e.g. Vercel) where writing files
# may be restricted or some modules may not be bundled correctly.
try:
    from venue_finder.exports.csv_export import export_csv  # type: ignore
    from venue_finder.exports.excel_export import export_excel  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    export_csv = None  # type: ignore
    export_excel = None  # type: ignore

from venue_finder.processors.feature_extractor import extract_feature_flags, extract_quiet_hours
from venue_finder.processors.distance_calculator import calculate_distance
from venue_finder.processors.location_parser import infer_location_hint
from venue_finder.processors.text_analyzer import TextAnalyzer
from venue_finder.samples import sample_venues
from venue_finder.scrapers.airbnb_scraper import AirbnbScraper
from venue_finder.scrapers.eventlocations_scraper import EventlocationsScraper
from venue_finder.scrapers.gruppenhaus_scraper import GruppenhausScraper


SCRAPER_CLASSES = [GruppenhausScraper, EventlocationsScraper, AirbnbScraper]


def build_scrapers(*, max_results: int, search_keywords: list[str]) -> list:
    return [scraper_class(max_results=max_results, search_keywords=search_keywords) for scraper_class in SCRAPER_CLASSES]


def collect_text(venue: Venue) -> str:
    parts = [
        venue.name,
        venue.venue_type,
        venue.street_address,
        venue.city,
        venue.review_summary,
        venue.raw_text,
    ]
    return " ".join(part for part in parts if part)


def enrich_venue(venue: Venue, analyzer: TextAnalyzer, frankfurt_lat: float, frankfurt_lon: float) -> Venue:
    text = collect_text(venue)

    location_hint = infer_location_hint(name=venue.name, raw_text=venue.raw_text, source_url=venue.source_url)
    current_city = (venue.city or "").strip().lower()
    generic_city_values = {"", "hessen", "deutschland", "germany", "tagungshaus", "seminarhaus", "gruppenhaus", "zeltplatz"}
    if venue.city is None or current_city in generic_city_values:
        venue.city = location_hint.city
        if venue.city is None and current_city in generic_city_values:
            venue.city = None
    if venue.postal_code is None:
        venue.postal_code = location_hint.postal_code
    if venue.country is None:
        venue.country = location_hint.country

    feature_flags = extract_feature_flags(text)
    venue.camping_allowed = venue.camping_allowed or feature_flags.get("camping_allowed", False)
    venue.parties_allowed = venue.parties_allowed or feature_flags.get("parties_allowed", False)
    venue.loud_music_allowed = venue.loud_music_allowed or feature_flags.get("loud_music_allowed", False)
    venue.dj_allowed = venue.dj_allowed or feature_flags.get("dj_allowed", False)
    venue.sound_system_available = venue.sound_system_available or feature_flags.get("sound_system_available", False)
    venue.outdoor_party_area = venue.outdoor_party_area or feature_flags.get("outdoor_party_area", False)
    venue.bbq_available = venue.bbq_available or feature_flags.get("bbq_available", False)
    venue.fire_place = venue.fire_place or feature_flags.get("fire_place", False)
    venue.swimming_pool = venue.swimming_pool or feature_flags.get("swimming_pool", False)
    venue.lake_or_river_nearby = venue.lake_or_river_nearby or feature_flags.get("lake_or_river_nearby", False)
    venue.private_property = venue.private_property or feature_flags.get("private_property", False)

    quiet_start, quiet_end = extract_quiet_hours(text)
    if venue.quiet_hours_start is None:
        venue.quiet_hours_start = quiet_start
    if venue.quiet_hours_end is None:
        venue.quiet_hours_end = quiet_end

    analysis = analyzer.analyze(text, venue=venue)
    venue.party_score = analysis.party_score
    venue.parties_allowed = venue.parties_allowed or analysis.suitable_for_party
    venue.camping_allowed = venue.camping_allowed or analysis.camping_possible
    venue.private_property = venue.private_property or analysis.private_venue
    if venue.quiet_hours_start is None:
        venue.quiet_hours_start = analysis.quiet_hours_start
    if venue.quiet_hours_end is None:
        venue.quiet_hours_end = analysis.quiet_hours_end
    venue.suitability_summary = analysis.suitability_summary
    venue.restrictions_summary = analysis.restrictions_summary

    if venue.latitude is not None and venue.longitude is not None:
        distance = calculate_distance(frankfurt_lat, frankfurt_lon, venue.latitude, venue.longitude)
        venue.distance_from_frankfurt_km = distance.distance_km
        venue.driving_time_minutes = distance.driving_time_minutes

    return venue


def scrape_venues(config, *, use_live_scrapers: bool = True) -> list[Venue]:
    analyzer = TextAnalyzer(openai_api_key=config.openai_api_key)
    scraped: list[Venue] = []

    if not use_live_scrapers:
        return scraped

    with session_scope(config.database_url) as session:
        keywords = list_keywords(session)
        if not keywords:
            keywords = seed_default_keywords(session)

    for scraper in build_scrapers(max_results=config.max_search_results, search_keywords=keywords):
        for item in scraper.scrape():
            venue = Venue(
                source_name=item.source_name,
                source_url=item.source_url,
                name=item.name,
                website=item.website,
                venue_type=item.venue_type,
                raw_text=item.raw_text,
                extra_metadata=item.metadata,
            )
            enrich_venue(venue, analyzer, config.frankfurt_latitude, config.frankfurt_longitude)
            scraped.append(venue)

    return scraped


def persist_venues(database_url: str, venues: list[Venue]) -> int:
    """Persist scraped venues.

    Return a count that reflects work done.

    Note: `upsert_venues()` may return `created=False` for two cases:
    - `updated by source_url` (existing row merged)
    - `merged duplicate (...)` (similar row merged)

    The UI label "Inserted" previously only counted `created=True`, which
    often resulted in `0` even when scraping successfully updated records.
    """

    with session_scope(database_url) as session:
        outcomes = upsert_venues(session, venues)

    # Count anything except skipped duplicates in the same batch.
    # This keeps the number meaningful for users.
    return sum(1 for outcome in outcomes if outcome.get("reason") != "skipped duplicate source_url in batch")



def export_reports(database_url: str, output_dir: Path) -> tuple[Path, Path]:
    """Export to CSV/XLSX when filesystem allows it.

    Some serverless environments (e.g. Vercel) mount the repo directory as
    read-only. In that case we still want scraping + DB persistence to work.

    If exports fail, we write nothing and return best-effort paths.
    """

    with session_scope(database_url) as session:
        venues = list_venues(session)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"venues_{timestamp}.csv"
    xlsx_path = output_dir / f"venues_{timestamp}.xlsx"

    if export_csv is not None:
        try:
            export_csv(venues, csv_path)
        except OSError:
            # Ignore export failures (read-only FS, etc.)
            pass

    if export_excel is not None:
        try:
            export_excel(venues, xlsx_path)
        except OSError:
            pass

    return csv_path, xlsx_path



def run_once() -> tuple[int, Path, Path]:
    config = get_config()
    init_from_config(config)
    with session_scope(config.database_url) as session:
        seed_default_keywords(session)
    venues = scrape_venues(config, use_live_scrapers=True)
    inserted = persist_venues(config.database_url, venues)
    csv_path, xlsx_path = export_reports(config.database_url, config.output_dir)
    return inserted, csv_path, xlsx_path


def run_continuous(interval_minutes: int) -> None:
    delay = max(1, interval_minutes) * 60
    while True:
        inserted, csv_path, xlsx_path = run_once()
        print(f"Inserted {inserted} new venues")
        print(f"CSV export: {csv_path}")
        print(f"Excel export: {xlsx_path}")
        time.sleep(delay)


def recalculate_scores(venue: Venue, config: AppConfig) -> Venue:
    """Recompute feature flags + quiet hours + party score for a single venue."""

    analyzer = TextAnalyzer(openai_api_key=config.openai_api_key)

    # Refresh feature flags + quiet hours from current text.
    text = collect_text(venue)
    feature_flags = extract_feature_flags(text)


    venue.camping_allowed = venue.camping_allowed or feature_flags.get("camping_allowed", False)

    venue.parties_allowed = venue.parties_allowed or feature_flags.get("parties_allowed", False)
    venue.loud_music_allowed = venue.loud_music_allowed or feature_flags.get("loud_music_allowed", False)
    venue.dj_allowed = venue.dj_allowed or feature_flags.get("dj_allowed", False)
    venue.sound_system_available = venue.sound_system_available or feature_flags.get("sound_system_available", False)
    venue.outdoor_party_area = venue.outdoor_party_area or feature_flags.get("outdoor_party_area", False)
    venue.bbq_available = venue.bbq_available or feature_flags.get("bbq_available", False)
    venue.fire_place = venue.fire_place or feature_flags.get("fire_place", False)
    venue.swimming_pool = venue.swimming_pool or feature_flags.get("swimming_pool", False)
    venue.lake_or_river_nearby = venue.lake_or_river_nearby or feature_flags.get("lake_or_river_nearby", False)
    venue.private_property = venue.private_property or feature_flags.get("private_property", False)

    quiet_start, quiet_end = extract_quiet_hours(text)
    if venue.quiet_hours_start is None and quiet_start is not None:
        venue.quiet_hours_start = quiet_start
    if venue.quiet_hours_end is None and quiet_end is not None:
        venue.quiet_hours_end = quiet_end

    # Run deterministic text analyzer.
    enriched = analyzer.analyze(collect_text(venue), venue=venue)
    venue.party_score = enriched.party_score
    venue.parties_allowed = venue.parties_allowed or enriched.suitable_for_party
    venue.camping_allowed = venue.camping_allowed or enriched.camping_possible
    venue.private_property = venue.private_property or enriched.private_venue

    # Keep user-provided quiet hours; only fill if missing.
    if venue.quiet_hours_start is None:
        venue.quiet_hours_start = enriched.quiet_hours_start
    if venue.quiet_hours_end is None:
        venue.quiet_hours_end = enriched.quiet_hours_end



    venue.suitability_summary = enriched.suitability_summary
    venue.restrictions_summary = enriched.restrictions_summary

    # Distance (if lat/lon already provided/updated)
    if venue.latitude is not None and venue.longitude is not None:
        distance = calculate_distance(config.frankfurt_latitude, config.frankfurt_longitude, venue.latitude, venue.longitude)
        venue.distance_from_frankfurt_km = distance.distance_km
        venue.driving_time_minutes = distance.driving_time_minutes

    return venue


def seed_demo_data() -> tuple[int, Path, Path]:
    config = get_config()
    init_from_config(config)
    with session_scope(config.database_url) as session:
        seed_default_keywords(session)
    venues = sample_venues()
    analyzer = TextAnalyzer(openai_api_key=config.openai_api_key)
    for venue in venues:
        enrich_venue(venue, analyzer, config.frankfurt_latitude, config.frankfurt_longitude)
    inserted = persist_venues(config.database_url, venues)
    csv_path, xlsx_path = export_reports(config.database_url, config.output_dir)
    return inserted, csv_path, xlsx_path

