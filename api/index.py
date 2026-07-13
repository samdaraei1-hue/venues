"""Flask entry point for Vercel serverless deployment.

Vercel automatically detects the `app` Flask instance in this file.
All routes (dashboard, JSON API, keyword management, scrape trigger)
are wired here. The cron endpoint lives in `api/cron.py`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlencode

# Make project root importable so `venue_finder.*` resolves on Vercel.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from flask import Flask, redirect, request  # noqa: E402

from venue_finder.core.config import get_config  # noqa: E402
from venue_finder.core.database import init_from_config, session_scope  # noqa: E402
from venue_finder.core.keywords import DEFAULT_SEARCH_KEYWORDS  # noqa: E402
from venue_finder.core.models import Venue  # noqa: E402
from venue_finder.core.search_area import SearchArea, get_search_area, save_search_area  # noqa: E402
from venue_finder.core.sources import (  # noqa: E402
    add_source,
    list_sources,
    remove_source,
    reset_default_sources,
    set_source_enabled,
)
from venue_finder.core.repository import (  # noqa: E402
    VenueFilters,
    add_keyword,
    delete_venue_by_id,
    get_venue_by_id,
    list_keywords,
    list_venues,
    remove_keyword,
    replace_keywords,
    seed_default_keywords,
    upsert_manual_venue,
)
from venue_finder.pipeline import recalculate_scores, run_once  # noqa: E402
from venue_finder.webapp import (  # noqa: E402
    _build_filters,
    _handle_json,
    _render_page,
)

app = Flask(__name__)


def _params() -> dict[str, list[str]]:
    """Flask gives us MultiDict; build the {key: [values]} shape webapp expects."""
    return {key: request.args.getlist(key) for key in request.args.keys()}


def _form_params() -> dict[str, list[str]]:
    return {key: request.form.getlist(key) for key in request.form.keys()}


def _bootstrap() -> tuple[bool, str | None]:
    config = get_config()
    try:
        init_from_config(config)
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"DB init failed: {exc}"


def _int_param(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _float_param(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _bool_param(value: str | None) -> bool:
    if not value:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


@app.route("/", methods=["GET"])
def dashboard():
    ok, db_error = _bootstrap()
    config = get_config()
    params = _params()
    filters = _build_filters(params)
    message = request.args.get("message")

    if not ok:
        return _render_page(
            [],
            params,
            [],
            list_sources(config.sources_file),
            SearchArea(),
            message=(message or db_error or "Database error"),
        )

    with session_scope(config.database_url) as session:
        seed_default_keywords(session)
        search_area = get_search_area(session)
        if filters.max_distance_km is None:
            filters.max_distance_km = search_area.radius_km
        venues = list_venues(session, filters)

        keywords = list_keywords(session)

    sources = list_sources(config.sources_file)
    body_message = message or ("No venues yet. Run scrape to populate the table." if not venues else None)
    return _render_page(venues, params, keywords, sources, search_area, message=body_message)



@app.route("/api/venues.json", methods=["GET"])
def venues_json():
    ok, db_error = _bootstrap()
    if not ok:
        return (
            json.dumps({"ok": False, "error": db_error or "Database error"}, ensure_ascii=False, indent=2),
            200,
            {"Content-Type": "application/json; charset=utf-8"},
        )
    return _handle_json(_params()), 200, {"Content-Type": "application/json; charset=utf-8"}


@app.route("/scrape-now", methods=["POST"])
def scrape_now():
    ok, db_error = _bootstrap()
    if not ok:
        message = db_error or "Database error"
        return redirect(f"/?message={urlencode({'m': message})[2:]}")

    try:
        run_once()
        message = "Scrape finished."
    except Exception as exc:  # noqa: BLE001
        message = f"Scrape failed: {exc}"
    return redirect(f"/?message={urlencode({'m': message})[2:]}")


@app.route("/keywords/add", methods=["POST"])
def keywords_add():
    ok, db_error = _bootstrap()
    if not ok:
        return redirect(f"/?message={urlencode({'m': db_error or 'Database error'})[2:]}")

    config = get_config()
    keyword = (request.form.get("keyword") or "").strip()
    if keyword:
        with session_scope(config.database_url) as session:
            seed_default_keywords(session)
            add_keyword(session, keyword)
    return redirect("/")


@app.route("/keywords/remove", methods=["GET"])
def keywords_remove():
    ok, db_error = _bootstrap()
    if not ok:
        return redirect(f"/?message={urlencode({'m': db_error or 'Database error'})[2:]}")

    config = get_config()
    keyword = (request.args.get("keyword") or "").strip()
    if keyword:
        with session_scope(config.database_url) as session:
            seed_default_keywords(session)
            remove_keyword(session, keyword)
    return redirect("/")


@app.route("/keywords/reset", methods=["GET"])
def keywords_reset():
    ok, db_error = _bootstrap()
    if not ok:
        return redirect(f"/?message={urlencode({'m': db_error or 'Database error'})[2:]}")

    config = get_config()
    with session_scope(config.database_url) as session:
        replace_keywords(session, DEFAULT_SEARCH_KEYWORDS)
    return redirect("/")


@app.route("/search-area", methods=["POST"])
def search_area():
    ok, db_error = _bootstrap()
    if not ok:
        return redirect(f"/?message={urlencode({'m': db_error or 'Database error'})[2:]}")
    city = (request.form.get("city") or "").strip()
    try:
        radius_km = float(request.form.get("radius_km") or "250")
        with session_scope(get_config().database_url) as session:
            save_search_area(session, city, radius_km)
    except (ValueError, OSError) as exc:
        return redirect(f"/?message={urlencode({'m': str(exc)})[2:]}")
    return redirect("/")


@app.route("/sources/add", methods=["POST"])
def sources_add():
    config = get_config()
    source_name = (request.form.get("source_name") or "").strip()
    if source_name:
        try:
            add_source(config.sources_file, source_name)
        except OSError as exc:
            return redirect(f"/?message={urlencode({'m': f'Could not save source settings: {exc}'})[2:]}")
    return redirect("/")


@app.route("/sources/toggle", methods=["GET"])
def sources_toggle():
    config = get_config()
    source_name = (request.args.get("source_name") or "").strip()
    enabled = (request.args.get("enabled") or "").lower() in {"1", "true", "yes", "on"}
    if source_name:
        try:
            set_source_enabled(config.sources_file, source_name, enabled)
        except OSError as exc:
            return redirect(f"/?message={urlencode({'m': f'Could not save source settings: {exc}'})[2:]}")
    return redirect("/")


@app.route("/sources/remove", methods=["GET"])
def sources_remove():
    config = get_config()
    source_name = (request.args.get("source_name") or "").strip()
    if source_name:
        try:
            remove_source(config.sources_file, source_name)
        except OSError as exc:
            return redirect(f"/?message={urlencode({'m': f'Could not save source settings: {exc}'})[2:]}")
    return redirect("/")


@app.route("/sources/reset", methods=["GET"])
def sources_reset():
    config = get_config()
    try:
        reset_default_sources(config.sources_file)
    except OSError as exc:
        return redirect(f"/?message={urlencode({'m': f'Could not save source settings: {exc}'})[2:]}")
    return redirect("/")


@app.route("/venues/delete", methods=["POST"])
def venues_delete():
    ok, db_error = _bootstrap()
    if not ok:
        return (f"Database error: {db_error or 'Database error'}", 200)

    config = get_config()
    venue_id = _int_param(request.form.get("venue_id"))
    if venue_id is not None:
        with session_scope(config.database_url) as session:
            delete_venue_by_id(session, venue_id)
    return redirect("/")


@app.route("/venues/add", methods=["POST"])
def venues_add():
    ok, db_error = _bootstrap()
    if not ok:
        return (f"Database error: {db_error or 'Database error'}", 200)

    config = get_config()

    name = (request.form.get("name") or "").strip() or None
    source_name = (request.form.get("source_name") or "").strip() or None
    city = (request.form.get("city") or "").strip() or None

    source_url = (request.form.get("source_url") or "").strip() or "manual://unknown"
    raw_text = (request.form.get("raw_text") or "").strip() or None

    venue = Venue(
        name=name,
        source_name=source_name,
        city=city,
        maximum_guests=_int_param(request.form.get("maximum_guests")),
        camping_allowed=_bool_param(request.form.get("camping_allowed")),
        parties_allowed=_bool_param(request.form.get("parties_allowed")),
        bbq_available=_bool_param(request.form.get("bbq_available")),
        loud_music_allowed=_bool_param(request.form.get("loud_music_allowed")),
        private_property=_bool_param(request.form.get("private_property")),
        quiet_hours_start=(request.form.get("quiet_hours_start") or "").strip() or None,
        quiet_hours_end=(request.form.get("quiet_hours_end") or "").strip() or None,
        suitability_summary=(request.form.get("suitability_summary") or "").strip() or None,
        restrictions_summary=None,
        website=None,
        venue_type=None,
        source_url=source_url,
        street_address=None,
        latitude=_float_param(request.form.get("latitude")),
        longitude=_float_param(request.form.get("longitude")),
        raw_text=raw_text,
    )

    with session_scope(config.database_url) as session:
        recalculate_scores(venue, config)
        upsert_manual_venue(session, venue)

    return redirect("/")


@app.route("/venues/update", methods=["POST"])
def venues_update():
    ok, db_error = _bootstrap()
    if not ok:
        return (f"Database error: {db_error or 'Database error'}", 200)

    config = get_config()
    venue_id = _int_param(request.form.get("venue_id"))
    if venue_id is None:
        return redirect("/")

    with session_scope(config.database_url) as session:
        existing = get_venue_by_id(session, venue_id)
        if existing is None:
            return redirect("/")

        existing.name = (request.form.get("name") or "").strip() or existing.name
        existing.source_name = (request.form.get("source_name") or "").strip() or existing.source_name
        existing.city = (request.form.get("city") or "").strip() or existing.city
        existing.maximum_guests = _int_param(request.form.get("maximum_guests"))
        existing.camping_allowed = _bool_param(request.form.get("camping_allowed"))
        existing.parties_allowed = _bool_param(request.form.get("parties_allowed"))
        existing.bbq_available = _bool_param(request.form.get("bbq_available"))
        existing.loud_music_allowed = _bool_param(request.form.get("loud_music_allowed"))
        existing.private_property = _bool_param(request.form.get("private_property"))
        existing.quiet_hours_start = (request.form.get("quiet_hours_start") or "").strip() or None
        existing.quiet_hours_end = (request.form.get("quiet_hours_end") or "").strip() or None
        existing.suitability_summary = (request.form.get("suitability_summary") or "").strip() or None
        existing.raw_text = (request.form.get("raw_text") or "").strip() or existing.raw_text

        recalculate_scores(existing, config)

    return redirect("/")


# Vercel looks for either `app` or `handler`; expose both for safety.
handler = app

