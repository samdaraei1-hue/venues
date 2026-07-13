from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
import json
import webbrowser
from uuid import uuid4

from venue_finder.core.config import get_config
from venue_finder.core.database import init_from_config, session_scope
from venue_finder.core.keywords import DEFAULT_SEARCH_KEYWORDS
from venue_finder.core.sources import (
    DEFAULT_SOURCES,
    add_source,
    list_sources,
    remove_source,
    reset_default_sources,
    set_source_enabled,
)
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
from venue_finder.core.search_area import SearchArea, get_search_area, save_search_area
from venue_finder.processors.feature_extractor import normalize_quiet_time


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


def _source_label(source_name: str) -> str:
    labels = {
        "gruppenhaus": "Gruppenhaus",
        "eventlocations": "Eventlocations",
        "airbnb": "Airbnb",
    }
    return labels.get(source_name, source_name)


def _render_source_pills(sources) -> str:
    if not sources:
        return '<span class="small">No sources configured.</span>'
    return " ".join(
        f'<span class="chip keyword-chip">[{"on" if source.enabled else "off"}] {escape(_source_label(source.source_name))} '
        f'<a href="/sources/toggle?source_name={escape(source.source_name)}&enabled={"0" if source.enabled else "1"}" title="toggle">toggle</a> '
        f'<a href="/sources/remove?source_name={escape(source.source_name)}" title="remove">x</a></span>'
        for source in sources
    )


def _render_page(
    venues,
    params: dict[str, list[str]],
    keywords: list[str],
    sources,
    search_area: SearchArea | None = None,
    message: str | None = None,
    edit_id: int | None = None,
    add_defaults: dict[str, str] | None = None,
) -> str:
    search_area = search_area or SearchArea()
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
        beds_html = str(venue.number_of_beds or "")
        rooms_html = str(venue.number_of_rooms or "")
        camping_capacity_html = str(venue.camping_capacity or "")
        quiet_start_display = normalize_quiet_time(venue.quiet_hours_start) or ""
        quiet_end_display = normalize_quiet_time(venue.quiet_hours_end) or ""
        camping_label = "yes" if venue.camping_allowed and venue.camping_capacity is not None else "possible; cap unknown" if venue.camping_allowed else "no"

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
            f"<input name='quiet_hours_start' value='{escape(quiet_start_display)}' />" if is_edit else escape(quiet_start_display)
        )
        quiet_end_html = (
            f"<input name='quiet_hours_end' value='{escape(quiet_end_display)}' />" if is_edit else escape(quiet_end_display)
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
            "<article class='venue-card'>"
            "<div class='venue-head'>"
            f"<span class='score-pill {score_class}'>{score}</span>"
            f"<div><h3>{name_html or 'Unnamed venue'}</h3><p>{city_html or 'City unknown'} · {source_name_html or 'source unknown'}</p></div>"
            f"<span class='distance'>{venue.distance_from_frankfurt_km or '?'} km</span>"
            "</div>"
            "<div class='metric-row'>"
            f"<span><b>{guests_html or '?'}</b> guests</span><span><b>{beds_html or '?'}</b> beds</span>"
            f"<span><b>{venue.price_per_night or '?'}</b> EUR/night</span><span><b>{venue.price_per_person or '?'}</b> EUR/person</span>"
            "</div>"
            "<div class='tag-row'>"
            f"<span class='tag'>{camping_label}</span><span class='tag'>party: {parties_html}</span><span class='tag'>BBQ: {bbq_html}</span><span class='tag'>music: {loud_music_html}</span>"
            "</div>"
            f"<p class='summary'>{suitability_html}</p>"
            "<details><summary>Details and actions</summary><div class='detail-grid'>"
            f"<span>Rooms <b>{rooms_html or '?'}</b></span><span>Camping capacity <b>{camping_capacity_html or 'unknown'}</b></span>"
            f"<span>Quiet start <b>{quiet_start_html or 'not stated'}</b></span><span>Quiet end <b>{quiet_end_html or 'not stated'}</b></span>"
            f"<span>Record ID <b>{venue.id}</b></span>"
            f"<div class='venue-actions'>{delete_form}{edit_or_save}<a class='button secondary' href='{escape(venue.source_url)}' target='_blank' rel='noreferrer'>open source</a></div>"
            "</div></details></article>"
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
    .venue-list {{ display: grid; gap: 14px; }}
    .venue-card {{ background: rgba(255,255,255,.94); border: 1px solid var(--line); border-radius: 18px; padding: 16px 18px; box-shadow: 0 8px 22px rgba(31,41,55,.05); }}
    .venue-head {{ display: grid; grid-template-columns: auto 1fr auto; gap: 12px; align-items: start; }}
    .venue-head h3 {{ margin: 0; font-size: 19px; }}
    .venue-head p {{ margin: 4px 0 0; color: var(--muted); font-size: 13px; }}
    .score-pill {{ border-radius: 999px; padding: 7px 9px; font-weight: 800; font-size: 13px; }}
    .score-pill.good {{ background: var(--good); }} .score-pill.mid {{ background: var(--mid); }} .score-pill.bad {{ background: var(--bad); }}
    .distance {{ color: var(--accent-2); font-weight: 800; white-space: nowrap; }}
    .metric-row, .tag-row {{ display: flex; flex-wrap: wrap; gap: 8px 16px; margin-top: 13px; font-size: 13px; }}
    .metric-row span {{ color: var(--muted); }} .metric-row b {{ color: var(--ink); font-size: 15px; }}
    .tag {{ background: #f7f2e9; border: 1px solid var(--line); border-radius: 999px; padding: 5px 9px; }}
    .summary {{ margin: 12px 0 0; color: #4b5563; font-size: 13px; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    details {{ margin-top: 12px; border-top: 1px dashed var(--line); padding-top: 10px; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 700; font-size: 13px; }}
    .detail-grid {{ display: flex; flex-wrap: wrap; gap: 10px 20px; margin-top: 12px; font-size: 13px; color: var(--muted); }}
    .detail-grid b {{ color: var(--ink); }}
    .venue-actions {{ display: flex; gap: 8px; flex-wrap: wrap; width: 100%; align-items: center; }}
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
    @media (max-width: 560px) {{
      .wrap {{ padding: 14px; }} .panel {{ padding: 16px; border-radius: 16px; }} h1 {{ font-size: 34px; }}
      .venue-card {{ padding: 14px; }} .venue-head {{ grid-template-columns: auto 1fr; }} .distance {{ grid-column: 2; }}
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
        <p class="small">If the table is empty, run a scrape. Demo seed data is intentionally not shown here.</p>
      </div>
    </div>
    <div class="panel" style="margin-bottom:24px;">
      <h2 style="margin-top:0;">Search area</h2>
      <p class="small">Only venues with a resolved location inside this radius are saved.</p>
      <form method="post" action="/search-area" style="display:flex;gap:10px;flex-wrap:wrap;align-items:end;">
        <div class="field" style="min-width:260px;flex:1;"><label>Starting city</label><input type="text" name="city" value="{escape(search_area.city)}" placeholder="e.g. Frankfurt am Main"></div>
        <div class="field" style="min-width:160px;"><label>Radius (km)</label><input type="number" min="1" step="1" name="radius_km" value="{search_area.radius_km:g}"></div>
        <button class="button primary" type="submit">Save search area</button>
      </form>
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
    <div class="panel" style="margin-bottom:24px;">
      <h2 style="margin-top:0;">Source websites</h2>
      <p class="small">Enable or disable the sites that should be scraped on the next run.</p>
      <div class="chips" style="margin-bottom:12px;">{_render_source_pills(sources)}</div>
      <form method="post" action="/sources/add" style="display:flex;gap:10px;flex-wrap:wrap;align-items:end;">
        <div class="field" style="min-width:320px;flex:1;">
          <label>Add supported source</label>
          <select name="source_name">
            {''.join(f'<option value="{escape(item["source_name"])}">{escape(_source_label(item["source_name"]))}</option>' for item in DEFAULT_SOURCES)}
          </select>
        </div>
        <button class="button primary" type="submit">Add source</button>
        <a class="button secondary" href="/sources/reset">Reset defaults</a>
      </form>
    </div>
    <div class="panel" style="margin-bottom:24px;">
      <h2 style="margin-top:0;">Add venue manually</h2>
      <form method="post" action="/venues/add">
        <div class="grid">
          <div class="field"><label>Name</label><input name="name" required></div>
          <div class="field"><label>City</label><input name="city" required></div>
          <div class="field"><label>Source link</label><input name="source_url" type="url"></div>
          <div class="field"><label>Guests</label><input name="maximum_guests" type="number"></div>
          <div class="field"><label>Beds</label><input name="number_of_beds" type="number"></div>
          <div class="field"><label>Rooms</label><input name="number_of_rooms" type="number"></div>
          <div class="field"><label>EUR per night</label><input name="price_per_night" type="number" step="0.01"></div>
          <div class="field"><label>EUR per person</label><input name="price_per_person" type="number" step="0.01"></div>
        </div>
        <div class="actions" style="margin-top:12px;"><button class="button primary" type="submit">Add venue</button></div>
      </form>
    </div>
    <div class="venue-list">
      {''.join(rows) if rows else '<div class="panel">No venues found. Run scrape to populate the list.</div>'}
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
                "number_of_beds": venue.number_of_beds,
                "number_of_rooms": venue.number_of_rooms,
                "camping_capacity": venue.camping_capacity,
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

        if parsed.path == "/search-area":
            city = (form.get("city") or [""])[0]
            try:
                radius_km = float((form.get("radius_km") or ["250"])[0])
                with session_scope(config.database_url) as session:
                    save_search_area(session, city, radius_km)
            except (ValueError, OSError) as exc:
                self._redirect("/?message=" + urlencode({"m": str(exc)}))
                return
            self._redirect("/")
            return

        if parsed.path == "/sources/add":
            source_name = (form.get("source_name") or [""])[0].strip()
            if source_name:
                add_source(config.sources_file, source_name, enabled=True)
            self._redirect("/")
            return

        if parsed.path == "/sources/toggle":
            source_name = params.get("source_name", [""])[0].strip()
            enabled = _bool_param(params.get("enabled", []), default=True)
            if source_name:
                set_source_enabled(config.sources_file, source_name, enabled)
            self._redirect("/")
            return

        if parsed.path == "/scrape-now":
            processed, _, _ = run_once()
            self._redirect("/?message=" + urlencode({"m": f"Scrape finished: {processed} venues inserted or refreshed."}))
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
                    source_name=_get_form_str(form, "source_name") or "manual",
                    city=_get_form_str(form, "city"),
                    maximum_guests=_get_form_int(form, "maximum_guests"),
                    number_of_beds=_get_form_int(form, "number_of_beds"),
                    number_of_rooms=_get_form_int(form, "number_of_rooms"),
                    price_per_night=_get_form_float(form, "price_per_night"),
                    price_per_person=_get_form_float(form, "price_per_person"),
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
                    source_url=_get_form_str(form, "source_url") or f"manual://{uuid4().hex}",
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

        if parsed.path == "/sources/remove":
            source_name = params.get("source_name", [""])[0].strip()
            if source_name:
                remove_source(config.sources_file, source_name)
            self._redirect("/")
            return

        if parsed.path == "/sources/reset":
            reset_default_sources(config.sources_file)
            self._redirect("/")
            return

        filters = _build_filters(params)
        with session_scope(config.database_url) as session:
            seed_default_keywords(session)
            search_area = get_search_area(session)
            if filters.max_distance_km is None:
                filters.max_distance_km = search_area.radius_km
            venues = list_venues(session, filters)

            keywords = list_keywords(session)
        sources = list_sources(config.sources_file)

        body_message = "No venues yet. Run scrape to populate the table." if not venues else None
        body = _render_page(venues, params, keywords, sources, search_area, message=body_message).encode("utf-8")

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
