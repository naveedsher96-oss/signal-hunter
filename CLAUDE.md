# Signal Hunter: notes for Claude Code

Personal lead-finding web app for Naveed (remote CRM, GHL, Sales and VA services). It finds public "intent" signals (posts asking for help, owners describing struggles, remote job posts, CRM tools on websites, news), scores them, and drafts outreach emails. It never sends email itself.

## Architecture
- `signal_hunter.py`: the engine. **All network access goes through `http_get()`**, so tests can patch it. The main entry points are `run(companies, cfg, on_progress, should_stop)` and `discover(cfg, ...)`. Both return result dicts, and `write_outputs(cfg, results, label, seen=dict, out_dir=..., emails=False)` builds the Excel file.
- Scoring constants: `KIND_POINTS` / `KIND_LABEL`, recency in `recency()`, per-category cap `CATEGORY_CAP`, small-business bonus `SMALLBIZ_BONUS`. Tiers come from `tier_of()`: HOT needs the score plus either 2+ signals or one fresh ask / eligible job (`HOT_FRESH_DAYS`). Lead types: `SEG_SMALL`.
- Post classification: `classify_post()`. It uses `OFFER_RE` and the `exclude_words` setting to skip competitors and job seekers, `ask_need()` (an `INTENT_RE` hit with a service keyword or pain phrase in the same clause) to detect "ask", pain phrases to detect "struggle", and keywords to detect "mention".
- Email copy: `build_email()`, which uses `NEED_PHRASE`, `QUICK_WINS`, `SMALL_WINS`, `PAIN_*`. `build_bid()` is the short Freelancer.com proposal variant; `build_followup()` is the second-touch draft (runs after `build_email`, reuses its subject as `Re:`). Both live on the result dict as `email` / `followup` and flow to the UI through `summarise()`.
- `webapp.py`: Flask app. Keep it to one process (e.g. 1 gunicorn worker) because the live job state (`JOB`) lives in memory. Scans run in a background thread. Results are persisted through `db.py`.
- Contact finding: `enrich_contacts()` runs at the end of `run()`/`discover()` on the top `contact_limit` non-COLD, non-person leads. `find_contacts()` uses the company's own site (`guess_site()` verifies a guessed `<slug>.com/.io/.co` by matching the company name on the page), follows contact/about/team links, and `contact_emails()` ranks same-domain + personal-looking addresses. Settings: `find_contacts`, `contact_limit`.
- `db.py`: SQLite or Postgres via `DATABASE_URL`. The `?` placeholders are converted to `%s` for Postgres. Keep SQL portable between the two (`ON CONFLICT`, `RETURNING` work on both). `lead_status` tracks each lead's pipeline stage (key = lowercased lead name, so it survives across runs); `POST /lead-status` sets it, `GET /lead-statuses` feeds the row dropdowns, the "Hide contacted" filter and the Pipeline dialog in page.html. Sent date auto-fills when status becomes `contacted`; follow-up due = sent + 4 days (same rule as the Excel). `write_outputs(..., statuses=...)` stamps Status/Sent date into the tracker so it mirrors the app.
- PWA: `pwa/` holds `manifest.json`, `sw.js` (caches only the icons - live data always goes to network) and the app icons. Served at `/manifest.json`, `/sw.js` and `/pwa/<file>`; those endpoints must stay in `PUBLIC` so install works before login. `sw.js` must stay at the root path (scope `/`).
- Hosting is zero-cost on purpose (the user won't add a payment card anywhere): Supabase for the database, GitHub Actions for the daily scan (`cron_scan.py`, which calls `webapp.run_one`), and the Flask app runs on the user's own computer, reading `DATABASE_URL` from a git-ignored `.env` (`db.load_env_file()`). Don't add anything that needs a paid plan or a card.
- Sources: Reddit is off unless the `use_reddit` setting is on (it needs an approved API key). Freelancer.com's public projects API (`freelancer_projects()`, searches in `freelancer_queries`) is the main "asking for help" source; Craigslist gig posts come from public RSS (`craigslist_cities` x `craigslist_queries`, `use_craigslist` to switch off) and are classified like asks; Jobicy and Working Nomads are among the remote job `FEEDS`. Single-post leads are named with a `PERSON_PREFIXES` prefix (`is_person()`).
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
