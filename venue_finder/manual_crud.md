# Manual CRUD (design notes)

- UI: Excel-like inline editing.
- Table columns (shown today): id, score, name, source, city, guests, km, camping, parties, bbq, music, quiet start, quiet end, summary, link.

Proposed minimal editable fields:
- name
- source_name
- city
- maximum_guests
- latitude/longitude (optional)
- camping_allowed
- parties_allowed
- bbq_available
- loud_music_allowed
- private_property
- quiet_hours_start / quiet_hours_end
- raw_text (optional)
- website/source_url/source link

Score refresh:
- If raw_text is present or quiet/private/feature booleans are edited, re-run:
  - extract_feature_flags() based on collected text (name + raw_text + summaries)
  - extract_quiet_hours() (for quiet start/end)
  - TextAnalyzer.analyze(text, venue=venue)

Backend routes (POST):
- /venues/add
- /venues/update
- /venues/delete

Repository functions needed:
- get_venue_by_id
- create/update venue
- delete venue

