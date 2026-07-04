# TODO

## Fix Vercel 500 (site not loading)
- [x] Inspect serverless entrypoints: `api/index.py`, `api/cron.py`, `venue_finder/core/database.py`, `venue_finder/core/config.py`.
- [x] Identify likely crash causes (DB init/connectivity, missing env vars, packaging/import issues).
- [x] Remove unused/possibly problematic import (`os`) from `api/index.py` (no logic change).
- [ ] Add structured logging + surface DB connection error details in JSON and HTML.
- [ ] Ensure `DATABASE_URL` works in Vercel (fallback behavior when env is missing).
- [ ] Add `VENUE_FINDER_OUTPUT_DIR` / filesystem write safeguards for serverless.
- [ ] Run local smoke tests that mimic Vercel entrypoint: `python api/index.py` (if applicable) and `flask`/handler invocation.
- [ ] After fixes, redeploy and verify `/` and `/api/venues.json` return 200.

