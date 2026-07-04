# TODO

- [x] Repo identified current capabilities: dashboard filters + keyword management + scrape/export + conditional Excel formatting.
- [x] Add Venue CRUD backend (add/update/delete) via repository + score recalculation after edits.


- [ ] Extend `venue_finder/webapp.py` dashboard with:


  - [ ] per-row small buttons: `edit` and `delete`
  - [ ] edit mode that turns a row into inline inputs (Excel-like editing)
  - [ ] an empty blank row at the bottom for manual add
  - [ ] “Save” button for the inline edited row and the add row
- [ ] Wire routes in `DashboardHandler` for:
  - [ ] POST `/venues/add`
  - [ ] POST `/venues/update`
  - [ ] POST `/venues/delete`
- [x] Implement deterministic score refresh after manual add/edit using existing `TextAnalyzer` and feature extraction.

- [ ] Ensure exports include the updated records automatically (likely no changes).

- [ ] Smoke test locally:
  - [ ] `python -m venue_finder.main init-db`
  - [ ] `python -m venue_finder.main serve`
  - [ ] add/edit/delete a venue and verify it appears + party score updates

