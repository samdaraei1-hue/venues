from __future__ import annotations

import argparse
import time

from venue_finder.core.config import get_config
from venue_finder.core.database import init_from_config, session_scope
from venue_finder.core.repository import VenueFilters, list_venues, upsert_venues
from venue_finder.pipeline import export_reports, persist_venues, run_continuous, run_once, seed_demo_data, scrape_venues
from venue_finder.webapp import run_server


def run_scheduler(interval: str) -> None:
    seconds = 24 * 60 * 60 if interval == "daily" else 7 * 24 * 60 * 60
    while True:
        run_once()
        time.sleep(seconds)


def search_venues(args: argparse.Namespace) -> None:
    config = get_config()
    init_from_config(config)
    filters = VenueFilters(
        max_distance_km=args.max_distance_km,
        max_budget=args.max_budget,
        guest_count=args.guest_count,
        min_party_score=args.min_party_score,
        camping_only=args.camping_only,
        swimming_pool=args.swimming_pool,
        bbq=args.bbq,
        loud_music_allowed=args.loud_music_allowed,
        weekend_available=args.weekend_available,
    )
    with session_scope(config.database_url) as session:
        venues = list_venues(session, filters)

    for venue in venues:
        print(
            f"{venue.id}\t{venue.party_score or 0}\t{venue.name or ''}\t{venue.city or ''}\t"
            f"{venue.maximum_guests or ''}\t{venue.distance_from_frankfurt_km or ''}\t{venue.source_url}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Venue Finder MVP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create the database schema")

    scrape_parser = subparsers.add_parser("scrape", help="Run the scrapers and update the database")
    scrape_parser.add_argument("--no-live-scrapers", action="store_true", help="Skip scraper execution")

    subparsers.add_parser("export", help="Export the current database to CSV and Excel")

    subparsers.add_parser("seed-demo", help="Populate the database with sample venues")

    search_parser = subparsers.add_parser("search", help="Search the venue database with filters")
    search_parser.add_argument("--max-distance-km", type=float)
    search_parser.add_argument("--max-budget", type=float)
    search_parser.add_argument("--guest-count", type=int)
    search_parser.add_argument("--min-party-score", type=int)
    search_parser.add_argument("--camping-only", action="store_true")
    search_parser.add_argument("--swimming-pool", action="store_true")
    search_parser.add_argument("--bbq", action="store_true")
    search_parser.add_argument("--loud-music-allowed", action="store_true")
    search_parser.add_argument("--weekend-available", action="store_true")

    schedule_parser = subparsers.add_parser("schedule", help="Run the pipeline on a schedule")
    schedule_parser.add_argument("--interval", choices=["daily", "weekly"], default="daily")

    watch_parser = subparsers.add_parser("watch", help="Keep scraping on a fixed interval")
    watch_parser.add_argument("--interval-minutes", type=int, default=30)

    serve_parser = subparsers.add_parser("serve", help="Run the local dashboard website")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--auto-scrape-minutes", type=int, default=0)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = get_config()

    if args.command == "init-db":
        init_from_config(config)
        print("Database initialized")
        return

    if args.command == "scrape":
        init_from_config(config)
        venues = scrape_venues(config, use_live_scrapers=not args.no_live_scrapers)
        inserted = persist_venues(config.database_url, venues)
        csv_path, xlsx_path = export_reports(config.database_url, config.output_dir)
        print(f"Inserted {inserted} new venues")
        print(f"CSV export: {csv_path}")
        print(f"Excel export: {xlsx_path}")
        return

    if args.command == "export":
        init_from_config(config)
        csv_path, xlsx_path = export_reports(config.database_url, config.output_dir)
        print(f"CSV export: {csv_path}")
        print(f"Excel export: {xlsx_path}")
        return

    if args.command == "seed-demo":
        inserted, csv_path, xlsx_path = seed_demo_data()
        print(f"Inserted {inserted} demo venues")
        print(f"CSV export: {csv_path}")
        print(f"Excel export: {xlsx_path}")
        return

    if args.command == "search":
        search_venues(args)
        return

    if args.command == "schedule":
        init_from_config(config)
        run_scheduler(args.interval)
        return

    if args.command == "watch":
        init_from_config(config)
        run_continuous(args.interval_minutes)
        return

    if args.command == "serve":
        run_server(host=args.host, port=args.port, auto_scrape_minutes=args.auto_scrape_minutes)
        return


if __name__ == "__main__":
    main()
