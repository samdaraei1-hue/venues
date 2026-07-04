# TODO - Venue Finder Vercel 500 Fix

- [x] Identify likely crash area: database initialization / SQLAlchemy connection in serverless.
- [x] Add Vercel-friendly error handling in `api/index.py` so `/` returns HTTP 200 with an error message instead of crashing.

- [ ] Add lightweight DB connectivity check + better error surfacing in `core/database.py`.
- [ ] Ensure `init_db()` is only executed once per cold start (avoid repeated metadata.create_all).
- [x] Redeploy and verify `/` and `/api/venues.json` (after code push).



