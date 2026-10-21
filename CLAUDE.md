# Signal Hunter: notes for Claude Code

Personal lead-finding web app for Naveed (remote CRM, GHL, Sales and VA services). It finds public "intent" signals (posts asking for help, owners describing struggles, remote job posts, CRM tools on websites, news), scores them, and drafts outreach emails. It never sends email itself.

## Architecture
- `signal_hunter.py`: the engine. **All network access goes through `http_get()`**, so tests can patch it. The main entry points are `run(companies, cfg, on_progress, should_stop)` and `discover(cfg, ...)`. Both return result dicts, and `write_outputs(cfg, results, label, seen=dict, out_dir=..., emails=False)` builds the Excel file.
- Scoring constants: `KIND_POINTS` / `KIND_LABEL`, recency in `recency()`, per-category cap `CATEGORY_CAP`, small-business bonus `SMALLBIZ_BONUS`. Tiers come from `tier_of()`: HOT needs the score plus either 2+ signals or one fresh ask / eligible job (`HOT_FRESH_DAYS`). Lead types: `SEG_SMALL`.
- Post classification: `classify_post()`. It uses `OFFER_RE` and the `exclude_words` setting to skip competitors and job seekers, `ask_need()` (an `INTENT_RE` hit with a service keyword or pain phrase in the same clause) to detect "ask", pain phrases to detect "struggle", and keywords to detect "mention".
- Email copy: `build_email()`, which uses `NEED_PHRASE`, `QUICK_WINS`, `SMALL_WINS`, `PAIN_*`.
- `webapp.py`: Flask app. It runs **1 gunicorn worker** on purpose, because the live job state (`JOB`) lives in memory. Scans run in a background thread. Results are persisted through `db.py`.
- `db.py`: SQLite or Postgres via `DATABASE_URL`. The `?` placeholders are converted to `%s` for Postgres. Keep SQL portable between the two (`ON CONFLICT`, `RETURNING` work on both).
- User settings are stored in the database under the setting `config`. `defaults.json` only seeds that setting. `sh.with_defaults()` fills in any missing keys.

## Testing
- Automated tests: `pip install pytest && python -m pytest -q tests` (offline, under a second). CI runs them on every push and PR (`.github/workflows/tests.yml`). `tests/conftest.py` patches `http_get` with the fakes and skips the polite sleeps.
- Offline UI test: `APP_PASSWORD=test CRON_TOKEN=tok python tests/run_mock_server.py`, then open http://127.0.0.1:8765 (password `test`).
- Fake sources live in `tests/mocks.py`, keyed by URL substring, with real API response shapes.
- Production-like test: `gunicorn --chdir tests mock_wsgi:app --workers 1 --threads 8` with `DATABASE_URL` pointing at a Postgres server.

## Rules
- Don't add automatic email sending. The user reviews every message.
- Don't scrape LinkedIn or Facebook.
- Keep anything the user can edit (keywords, pain phrases, subreddits) in config, not hard-coded.
