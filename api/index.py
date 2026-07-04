"""Flask entry point for Vercel serverless deployment.

Vercel automatically detects the `app` Flask instance in this file.
All routes (dashboard, JSON API, keyword management, scrape trigger)
are wired here. The cron endpoint lives in `api/cron.py`.
"""
from __future__ import annotations

import json
import os
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
from venue_finder.core.repository import (  # noqa: E402
    VenueFilters,
    add_keyword,
    list_keywords,
    list_venues,
    remove_keyword,
    replace_keywords,
    seed_default_keywords,
)
from venue_finder.pipeline import run_once  # noqa: E402
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
        # Avoid raw 500s; return details in page/JSON so we can see what breaks.
        return False, f"DB init failed: {exc}"



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
            message=(message or db_error or "Database error"),
        )

    with session_scope(config.database_url) as session:
        seed_default_keywords(session)
        venues = list_venues(session, filters)
        keywords = list_keywords(session)
    return _render_page(venues, params, keywords, message=message)



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



# Vercel looks for either `app` or `handler`; expose both for safety.
handler = app
