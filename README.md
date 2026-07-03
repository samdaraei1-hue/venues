# Venue Finder

MVP for the Energy Travel venue discovery system.

## What this includes

- SQLAlchemy venue model that works with SQLite now and PostgreSQL later
- Common scraper interface with three source-specific scraper stubs
- Text analysis and party scoring with optional OpenAI support
- Distance and duplicate detection helpers
- CSV and Excel exports with score-based formatting
- CLI entrypoint for initialize, scrape, export, and schedule flows

## Quick start

1. Create a virtual environment.
2. Install dependencies from `requirements.txt`.
3. Run `python -m venue_finder.main init-db`.
4. Run `python -m venue_finder.main serve --auto-scrape-minutes 60` and open the local dashboard in your browser.

## Deploy online

This project now includes Vercel entrypoints:

- `index.py` for the main dashboard
- `api/cron.py` for scheduled scrapes
- `vercel.json` for cron configuration

For production, use a managed PostgreSQL database and set `DATABASE_URL` in Vercel. The site can be deployed as a Vercel Python function, while the scraper is triggered through the cron endpoint.

Example environment setup:

```bash
DATABASE_URL=postgresql://user:password@host/database?sslmode=require&channel_binding=require
```

## See what has been done

Use these commands from the project root:

1. `git status` to see which files changed.
2. `git diff --stat` to get a compact summary.
3. `python -m venue_finder.main seed-demo` to populate the database with sample venues and generate exports.
4. Open the newest files in `exports/` to inspect the CSV and Excel reports.
5. Run `python -m venue_finder.main search --min-party-score 60` to query the database from the CLI.
6. Open `http://127.0.0.1:8000/` after running `python -m venue_finder.main serve` to see the database in a browser.
7. Run `python -m venue_finder.main watch --interval-minutes 60` to keep scraping continuously.

## Notes

- The scraper classes are intentionally built as a shared framework, so each new website should only need a new subclass.
- Site selectors and crawl rules still need to be tuned per target website.
- If `OPENAI_API_KEY` is not set, the analyzer falls back to deterministic heuristics.
- Live scraping may be blocked in some sandboxed environments; the demo seed path still works and produces exports.
