from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
import json
import webbrowser

from venue_finder.core.config import get_config
from venue_finder.core.database import init_from_config, session_scope
from venue_finder.core.keywords import DEFAULT_SEARCH_KEYWORDS
from venue_finder.core.repository import (
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


from venue_finder.pipeline import recalculate_scores, run_continuous, run_once
from venue_finder.core.models import Venue


import threading


def _bool_param(value: list[str], default: bool = False) -> bool:
    if not value:
        return default
    return value[0].lower() in {"1", "true", "yes", "on"}


def _float_param(value: list[str]) -> float | None:
    if not value:
        return None
    try:
        return float(value[0])
    except ValueError:
        return None


def _int_param(value: list[str]) -> int | None:
    if not value:
        return None
    try:
        return int(value[0])
    except ValueError:
        return None


def _get_form_str(form: dict[str, list[str]], key: str, default: str = "") -> str:
    values = form.get(key)
    if not values:
        return default
    return (values[0] or "").strip()


def _get_form_int(form: dict[str, list[str]], key: str) -> int | None:
    value = _get_form_str(form, key, default="")
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _get_form_float(form: dict[str, list[str]], key: str) -> float | None:
    value = _get_form_str(form, key, default="")
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _get_form_bool(form: dict[str, list[str]], key: str) -> bool:
    values = form.get(key)
    if not values:
        return False
    return values[0].lower() in {"1", "true", "yes", "on"}


def _build_filters(params: dict[str, list[str]]) -> VenueFilters:
    return VenueFilters(
        max_distance_km=_float_param(params.get("max_distance_km", [])),
        max_budget=_float_param(params.get("max_budget", [])),
        guest_count=_int_param(params.get("guest_count", [])),
        min_party_score=_int_param(params.get("min_party_score", [])),
        camping_only=_bool_param(params.get("camping_only", [])),
        swimming_pool=_bool_param(params.get("swimming_pool", [])),
        bbq=_bool_param(params.get("bbq", [])),
        loud_music_allowed=_bool_param(params.get("loud_music_allowed", [])),
        weekend_available=_bool_param(params.get("weekend_available", [])),
    )



def _render_checkbox(name: str, label: str, checked: bool) -> str:
    return (
        f'<label class="chip"><input type="checkbox" name="{escape(name)}" value="1" '
        f'{"checked" if checked else ""}> {escape(label)}</label>'
    )


def _render_keyword_pills(keywords: list[str]) -> str:
    return " ".join(
        f'<span class="chip keyword-chip">{escape(keyword)} '
        f'<a href="/keywords/remove?keyword={escape(keyword)}" title="remove">x</a></span>'
        for keyword in keywords
    ) or '<span class="small">No keywords configured.</span>'


def _render_page(
    venues,
    params: dict[str, list[str]],
    keywords: list[str],
    message: str | None = None,
    edit_id: int | None = None,
    add_defaults: dict[str, str] | None = None,
) -> str:

    filters = _build_filters(params)
    total = len(venues)
    avg_score = round(sum((venue.party_score or 0) for venue in venues) / total, 1) if total else 0
    camping_count = sum(1 for venue in venues if venue.camping_allowed)
    party_ready = sum(1 for venue in venues if (venue.party_score or 0) >= 80)

    rows = []
    for venue in venues:
        score = venue.party_score or 0
        score_class = "good" if score >= 80 else "mid" if score >= 50 else "bad"
        is_edit = edit_id is not None and venue.id == edit_id

        name_html = f"<input name='name' value='{escape(venue.name or '')}' />" if is_edit else escape(venue.name or "")
        source_name_html = (
            f"<input name='source_name' value='{escape(venue.source_name or '')}' />" if is_edit else escape(venue.source_name or "")
        )
        city_html = f"<input name='city' value='{escape(venue.city or '')}' />" if is_edit else escape(venue.city or "")
        guests_html = (
            f"<input type='number' name='maximum_guests' value='{venue.maximum_guests or ''}' />" if is_edit else (str(venue.maximum_guests or ""))
        )

        camping_html = (
            "<select name='camping_allowed'>"
            f"<option value='1' {'selected' if venue.camping_allowed else ''}>yes</option>"
            f"<option value='0' {'selected' if not venue.camping_allowed else ''}>no</option>"
            "</select>"
            if is_edit
            else ('yes' if venue.camping_allowed else 'no')
        )
        parties_html = (
            "<select name='parties_allowed'>"
            f"<option value='1' {'selected' if venue.parties_allowed else ''}>yes</option>"
            f"<option value='0' {'selected' if not venue.parties_allowed else ''}>no</option>"
            "</select>"
            if is_edit
            else ('yes' if venue.parties_allowed else 'no')
        )
        bbq_html = (
            "<select name='bbq_available'>"
            f"<option value='1' {'selected' if venue.bbq_available else ''}>yes</option>"
            f"<option value='0' {'selected' if not venue.bbq_available else ''}>no</option>"
            "</select>"
            if is_edit
            else ('yes' if venue.bbq_available else 'no')
        )
        loud_music_html = (
            "<select name='loud_music_allowed'>"
            f"<option value='1' {'selected' if venue.loud_music_allowed else ''}>yes</option>"
            f"<option value='0' {'selected' if not venue.loud_music_allowed else ''}>no</option>"
            "</select>"
            if is_edit
            else ('yes' if venue.loud_music_allowed else 'no')
        )

        quiet_start_html = (
            f"<input name='quiet_hours_start' value='{escape(venue.quiet_hours_start or '')}' />" if is_edit else escape(venue.quiet_hours_start or "")
        )
        quiet_end_html = (
            f"<input name='quiet_hours_end' value='{escape(venue.quiet_hours_end or '')}' />" if is_edit else escape(venue.quiet_hours_end or "")
        )

        suitability_html = f"<input name='suitability_summary' value='{escape(venue.suitability_summary or '')}' />" if is_edit else escape(venue.suitability_summary or "")

        actions_html = "" if not is_edit else ""
        edit_or_save = (
            f"<form method='post' action='/venues/update'>"
            f"<input type='hidden' name='venue_id' value='{venue.id}' />"
            f"<input type='hidden' name='return_to' value='{escape(str(params.get('return_to', [''])[0]) if params else '')}' />"
            f"<button class='button primary' type='submit'>save</button>"
            f"</form>"
            if is_edit
            else f"<a class='button secondary' href='/?edit={venue.id}'>edit</a>"
        )

        delete_form = (
            f"<form method='post' action='/venues/delete' style='margin:0;'>"
            f"<input type='hidden' name='venue_id' value='{venue.id}' />"
            f"<button class='button secondary' type='submit' onclick=\"return confirm('Delete venue {venue.id}?')\">delete</button>"
            f"</form>"
        )

        rows.append(
            "<tr>"
            f"<td>{venue.id}</td>"
            f"<td class='score {score_class}'>{score}</td>"
            f"<td>{name_html}</td>"
            f"<td>{source_name_html}</td>"
            f"<td>{city_html}</td>"
            f"<td>{guests_html}</td>"
            f"<td>{venue.distance_from_frankfurt_km or ''}</td>"
            f"<td>{camping_html}</td>"
            f"<td>{parties_html}</td>"
            f"<td>{bbq_html}</td>"
            f"<td>{loud_music_html}</td>"
            f"<td>{quiet_start_html}</td>"
            f"<td>{quiet_end_html}</td>"
            f"<td>{suitability_html}</td>"
            f"<td><div style='display:flex;flex-direction:column;gap:6px;align-items:flex-start;'>{delete_form}{edit_or_save}<a href='{escape(venue.source_url)}' target='_blank' rel='noreferrer'>open</a></div></td>"
            "</tr>"
        )


    checkbox = " ".join(
        [
            _render_checkbox("camping_only", "Camping only", filters.camping_only),
            _render_checkbox("swimming_pool", "Pool", filters.swimming_pool),
            _render_checkbox("bbq", "BBQ", filters.bbq),
            _render_checkbox("loud_music_allowed", "Loud music", filters.loud_music_allowed),
            _render_checkbox("weekend_available", "Weekend available", filters.weekend_available),
        ]
    )

    query_string = urlencode({key: value[0] for key, value in params.items() if value})
    message_html = f'<div class="notice">{escape(message)}</div>' if message else ""

    return f"""<!doctype html>
<html lang="de">
<head>

  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Venue Finder Dashboard</title>
  <style>
    :root {{
      --bg: #f4f1ea;
      --panel: #fffaf0;
      --ink: #1f2937;
      --muted: #6b7280;
      --accent: #b45309;
      --accent-2: #065f46;
      --line: #e5d7c3;
      --good: #d1fae5;
      --mid: #fef3c7;
      --bad: #fee2e2;
    }}
    body {{
      margin: 0;
      font-family: Georgia, 'Times New Roman', serif;
      background: radial-gradient(circle at top left, #fffaf0, #f4f1ea 45%, #ede4d8 100%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1600px;
      margin: 0 auto;
      padding: 28px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 20px;
      margin-bottom: 24px;
    }}
    .panel {{
      background: rgba(255, 250, 240, 0.9);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: 0 18px 50px rgba(31, 41, 55, 0.08);
      padding: 22px;
      backdrop-filter: blur(8px);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 44px;
      line-height: 1.05;
    }}
    .lede {{
      color: var(--muted);
      font-size: 18px;
      max-width: 60ch;
      margin-bottom: 18px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .stat {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
    }}
    .stat .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }}
    .stat .value {{ font-size: 30px; font-weight: 700; margin-top: 6px; }}
    .filters form {{
      display: grid;
      gap: 14px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .field label {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .field input {{
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 15px;
      background: #fff;
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      background: #fff;
      font-size: 14px;
    }}
    .keyword-chip a {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 700;
    }}
    .notice {{
      margin-top: 14px;
      padding: 10px 12px;
      border-radius: 12px;
      background: #ecfccb;
      border: 1px solid #bbf7d0;
      color: #166534;
      font-size: 14px;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 10px 16px;
      border-radius: 999px;
      text-decoration: none;
      border: 0;
      font-weight: 700;
      cursor: pointer;
    }}
    .button.primary {{ background: var(--accent); color: white; }}
    .button.secondary {{ background: #111827; color: white; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: rgba(255,255,255,0.92);
      border-radius: 20px;
      overflow: hidden;
      border: 1px solid var(--line);
    }}
    th, td {{
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
      font-size: 14px;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f8f2e7;
      text-transform: uppercase;
      letter-spacing: .06em;
      font-size: 12px;
    }}
    .score.good {{ background: var(--good); font-weight: 700; }}
    .score.mid {{ background: var(--mid); font-weight: 700; }}
    .score.bad {{ background: var(--bad); font-weight: 700; }}
    .table-wrap {{ overflow: auto; border-radius: 20px; }}
    .small {{
      color: var(--muted);
      font-size: 13px;
    }}
    code {{
      background: #f3f4f6;
      border-radius: 6px;
      padding: 2px 6px;
    }}
    @media (max-width: 1100px) {{
      .hero, .grid, .stats {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="panel">
        <h1>Venue Finder</h1>
        <p class="lede">This page shows exactly what is currently stored in the database. You can inspect party score, camping, restrictions, capacity, and the original source link for each venue.</p>
        <div class="stats">
          <div class="stat"><div class="label">Venues</div><div class="value">{total}</div></div>
          <div class="stat"><div class="label">Average score</div><div class="value">{avg_score}</div></div>
          <div class="stat"><div class="label">Party-ready</div><div class="value">{party_ready}</div></div>
          <div class="stat"><div class="label">Camping</div><div class="value">{camping_count}</div></div>
        </div>
      </div>
      <div class="panel filters">
        {message_html}
        <form method="post" action="/scrape-now" style="margin-bottom:14px;">
          <div class="actions">
            <button class="button primary" type="submit">Run scrape now</button>
            <span class="small">This uses the current keyword list and updates the database.</span>
          </div>
        </form>
        <form method="get">
          <div class="grid">
            <div class="field"><label>Min party score</label><input type="number" name="min_party_score" value="{escape(params.get('min_party_score', [''])[0]) if params.get('min_party_score') else ''}"></div>
            <div class="field"><label>Max distance km</label><input type="number" step="0.1" name="max_distance_km" value="{escape(params.get('max_distance_km', [''])[0]) if params.get('max_distance_km') else ''}"></div>
            <div class="field"><label>Max budget</label><input type="number" step="0.01" name="max_budget" value="{escape(params.get('max_budget', [''])[0]) if params.get('max_budget') else ''}"></div>
            <div class="field"><label>Guest count</label><input type="number" name="guest_count" value="{escape(params.get('guest_count', [''])[0]) if params.get('guest_count') else ''}"></div>
          </div>
          <div class="chips">{checkbox}</div>
          <div class="actions">
            <button class="button primary" type="submit">Apply filters</button>
            <a class="button secondary" href="/">Reset</a>
            <a class="button secondary" href="/api/venues.json?{query_string}">JSON</a>
          </div>
        </form>
        <p class="small">Tip: run <code>python -m venue_finder.main seed-demo</code> once, then refresh this page to see sample venues.</p>
      </div>
    </div>
    <div class="panel" style="margin-bottom:24px;">
      <h2 style="margin-top:0;">Search keywords</h2>
      <p class="small">These keywords are used by the scrapers on the next run.</p>
      <div class="chips" style="margin-bottom:12px;">{_render_keyword_pills(keywords)}</div>
      <form method="post" action="/keywords/add" style="display:flex;gap:10px;flex-wrap:wrap;align-items:end;">
        <div class="field" style="min-width:320px;flex:1;">
          <label>New keyword</label>
          <input type="text" name="keyword" placeholder="e.g. Partyhaus am See">
        </div>
        <button class="button primary" type="submit">Add keyword</button>
        <a class="button secondary" href="/keywords/reset">Reset defaults</a>
      </form>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Score</th>
            <th>Name</th>
            <th>Source</th>
            <th>City</th>
            <th>Guests</th>
            <th>Km from Frankfurt</th>
            <th>Camping</th>
            <th>Parties</th>
            <th>BBQ</th>
            <th>Music</th>
            <th>Quiet start</th>
            <th>Quiet end</th>
            <th>Summary</th>
            <th>Link</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows) if rows else '<tr><td colspan="15">No venues found. Seed demo data first.</td></tr>'}

        </tbody>
      </table>
    </div>
  </div>
</body>
</html>"""


def _handle_json(params: dict[str, list[str]]) -> str:
    config = get_config()
    filters = _build_filters(params)
    with session_scope(config.database_url) as session:
        venues = list_venues(session, filters)
    return json.dumps(
        [
            {
                "id": venue.id,
                "name": venue.name,
                "source_name": venue.source_name,
                "source_url": venue.source_url,
                "city": venue.city,
                "maximum_guests": venue.maximum_guests,
                "party_score": venue.party_score,
                "camping_allowed": venue.camping_allowed,
                "loud_music_allowed": venue.loud_music_allowed,
                "bbq_available": venue.bbq_available,
                "quiet_hours_start": venue.quiet_hours_start,
                "quiet_hours_end": venue.quiet_hours_end,
                "distance_from_frankfurt_km": venue.distance_from_frankfurt_km,
                "suitability_summary": venue.suitability_summary,
                "restrictions_summary": venue.restrictions_summary,
            }
            for venue in venues
        ],
        ensure_ascii=False,
        indent=2,
    )


class DashboardHandler(BaseHTTPRequestHandler):
    def _redirect(self, location: str = "/") -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        form = parse_qs(body)
        config = get_config()
        init_from_config(config)

        if parsed.path == "/keywords/add":
            keyword = (form.get("keyword") or [""])[0].strip()
            if keyword:
                with session_scope(config.database_url) as session:
                    seed_default_keywords(session)
                    add_keyword(session, keyword)
            self._redirect("/")
            return

        if parsed.path == "/scrape-now":
            run_once()
            self._redirect("/")
            return

        if parsed.path == "/venues/delete":
            venue_id = _int_param(form.get("venue_id", []))
            if venue_id is not None:
                with session_scope(config.database_url) as session:
                    delete_venue_by_id(session, venue_id)
            self._redirect("/")
            return

        if parsed.path == "/venues/add":
            with session_scope(config.database_url) as session:
                venue = Venue(
                    name=_get_form_str(form, "name"),
                    source_name=_get_form_str(form, "source_name"),
                    city=_get_form_str(form, "city"),
                    maximum_guests=_get_form_int(form, "maximum_guests"),
                    camping_allowed=_get_form_bool(form, "camping_allowed"),
                    parties_allowed=_get_form_bool(form, "parties_allowed"),
                    bbq_available=_get_form_bool(form, "bbq_available"),
                    loud_music_allowed=_get_form_bool(form, "loud_music_allowed"),
                    private_property=_get_form_bool(form, "private_property"),
                    quiet_hours_start=_get_form_str(form, "quiet_hours_start") or None,
                    quiet_hours_end=_get_form_str(form, "quiet_hours_end") or None,
                    suitability_summary=_get_form_str(form, "suitability_summary") or None,
                    restrictions_summary=None,
                    website=None,
                    venue_type=None,
                    source_url=_get_form_str(form, "source_url") or "manual://unknown",
                    street_address=None,
                    latitude=_get_form_float(form, "latitude"),
                    longitude=_get_form_float(form, "longitude"),
                    raw_text=_get_form_str(form, "raw_text") or None,
                )
                # Ensure deterministic score refresh.
                recalculate_scores(venue, config)
                # Manual insert/update by source_url to avoid accidental duplicates.
                saved, created = upsert_manual_venue(session, venue)
                _ = (saved, created)
            self._redirect("/")
            return

        if parsed.path == "/venues/update":
            venue_id = _int_param(form.get("venue_id", []))
            if venue_id is not None:
                with session_scope(config.database_url) as session:
                    existing = get_venue_by_id(session, venue_id)
                    if existing is not None:
                        existing.name = _get_form_str(form, "name", default=existing.name or "")
                        existing.source_name = _get_form_str(form, "source_name", default=existing.source_name or "")
                        existing.city = _get_form_str(form, "city", default=existing.city or "")
                        existing.maximum_guests = _get_form_int(form, "maximum_guests")
                        existing.camping_allowed = _get_form_bool(form, "camping_allowed")
                        existing.parties_allowed = _get_form_bool(form, "parties_allowed")
                        existing.bbq_available = _get_form_bool(form, "bbq_available")
                        existing.loud_music_allowed = _get_form_bool(form, "loud_music_allowed")
                        existing.private_property = _get_form_bool(form, "private_property")
                        existing.quiet_hours_start = _get_form_str(form, "quiet_hours_start") or None
                        existing.quiet_hours_end = _get_form_str(form, "quiet_hours_end") or None
                        existing.suitability_summary = _get_form_str(form, "suitability_summary") or None
                        existing.raw_text = _get_form_str(form, "raw_text") or existing.raw_text

                        recalculate_scores(existing, config)
            self._redirect("/")
            return


        self._redirect("/")


    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        config = get_config()
        init_from_config(config)

        if parsed.path == "/api/venues.json":
            body = _handle_json(params).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/cron":
            inserted, csv_path, xlsx_path = run_once()
            payload = json.dumps(
                {
                    "ok": True,
                    "inserted": inserted,
                    "csv_path": str(csv_path),
                    "xlsx_path": str(xlsx_path),
                },
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == "/keywords/remove":
            keyword = params.get("keyword", [""])[0].strip()
            if keyword:
                with session_scope(config.database_url) as session:
                    seed_default_keywords(session)
                    remove_keyword(session, keyword)
            self._redirect("/")
            return

        if parsed.path == "/keywords/reset":
            with session_scope(config.database_url) as session:
                replace_keywords(session, DEFAULT_SEARCH_KEYWORDS)
            self._redirect("/")
            return

        filters = _build_filters(params)
        with session_scope(config.database_url) as session:
            seed_default_keywords(session)
            venues = list_venues(session, filters)
            keywords = list_keywords(session)

        body = _render_page(venues, params, keywords).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    open_browser: bool = False,
    auto_scrape_minutes: int | None = None,
) -> None:
    config = get_config()
    init_from_config(config)
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    url = f"http://{host}:{port}/"
    print(f"Venue dashboard running at {url}")
    print("Open /api/venues.json for raw data.")
    if auto_scrape_minutes and auto_scrape_minutes > 0:
        worker = threading.Thread(target=run_continuous, args=(auto_scrape_minutes,), daemon=True)
        worker.start()
        print(f"Auto scrape enabled every {auto_scrape_minutes} minute(s).")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard...")
    finally:
        server.server_close()


def main() -> None:
    run_server()


if __name__ == "__main__":
    main()
