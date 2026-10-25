# Signal Hunter

Warm leads for remote **GoHighLevel, CRM automation, Sales/BD, Customer Success and VA/admin** work.
Signal Hunter finds companies, small-business owners and new founders who have **publicly shown a need**, ranks them, and drafts an email that answers that specific need.

**Nothing is ever sent automatically.** You review each draft, then send it with **Open in Mail app** (your default mail program, on PC or phone), **Open in Gmail**, or reply on the post. Every lead also has a shorter **follow-up draft** for the second touch.

## What it does
- **Scan my list:** upload an Excel or CSV file, or paste company names. You can save the list as your **saved list**, which is re-scanned every day.
- **Find warm companies:** no list needed. It finds open Freelancer.com projects (with the owner's name, so bids greet a person), Craigslist gigs, Hacker News posts asking for help, remote job posts, and Google News about companies that just adopted a CRM, hired sales leaders or raised money. Reddit can be switched on once you have an API key.
- **History:** every scan is saved, and each one comes with an Excel tracker to download (it opens showing your current pipeline status per lead).
- **Pipeline:** mark each lead Contacted / Replied / Call booked / Proposal / Won / Dead; the **Pipeline** view shows the funnel and which follow-ups are due (4 days after Contacted). A source count under the results shows how much each site returned - a 0 means that source is down or blocked.

Signals, points and keywords are explained in the app under **Profile & keywords**. Everything you set there is editable.

---

## Set it up (free, no card, about 15 minutes, once)

Everything here is free and none of it asks for a payment card:

- **Supabase** stores your scans, history and settings.
- **GitHub Actions** runs the scan every morning, right here in this repository.
- **Your computer** runs the app itself when you want to look at leads or start a scan.

### 1. Database: Supabase
1. Go to https://supabase.com, sign up with GitHub, and click **New project**. Name it `signal-hunter`, pick a database password (letters and numbers only: `@ # / :` break the link) and save it somewhere. For region, choose **Singapore** or **Mumbai**.
2. When the project is ready, click **Connect** at the top of the page.
3. Under **Session pooler**, copy the **URI**. It looks like this:
   `postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`
4. Replace `[YOUR-PASSWORD]` with your database password. This full string is your **DATABASE_URL**. Keep it private.

The app creates its tables by itself on first start.

> Supabase pauses free projects after about 7 days without activity. The daily scan keeps it awake. If it ever does pause, open the project in Supabase and click **Restore**.

### 2. Daily automatic scan: GitHub
1. In GitHub, open this repository → **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `DATABASE_URL`. Secret: the string from step 1. Click **Add secret**.
3. Test it: open the **Actions** tab → **Daily scan** → **Run workflow**. It takes a few minutes, and the run turns green when it's done.

From then on, "Find warm companies" runs **every 2 hours**, and your saved list is re-scanned once a day at about 8:15 AM Pakistan time. Scans older than 30 days are deleted automatically so the free database stays small (your lead statuses are kept).

### Phone alerts for new HOT leads (free, optional)
1. Install the free **ntfy** app (Android or iPhone). No account needed.
2. In Signal Hunter, open **Profile & keywords** → **Phone alerts**, click **Make one for me**, then **Save**.
3. In the ntfy app tap **+** and subscribe to that same topic name, then click **Send test alert**.

Each scan then pushes every HOT lead it sees for the first time, unless you've already marked it. Keep the topic name private: anyone who knows it can read your alerts.

> GitHub pauses scheduled runs if a repository has had no activity for 60 days. If that happens, re-enable the workflow in the Actions tab.

### 3. The app on your computer
1. Install Python from https://www.python.org/downloads/ and tick **Add Python to PATH**.
2. Download this repository (green **Code** button → **Download ZIP**) and unzip it.
3. In that folder, create a text file named `.env` (no other name, no `.txt`) containing one line:
   `DATABASE_URL=` followed by your string from step 1.
4. Double-click **`Run locally.bat`**. It opens http://127.0.0.1:8765 in your browser, with your daily scans under **History**.

Without a `.env` file the app still works, but it keeps its data in a local `signal_hunter.db` file instead of Supabase.

### Reddit (optional, later)
Reddit needs an approved API key. Once Reddit approves yours, add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` as repository secrets (and to `.env`), then tick **Search Reddit** under **Profile & keywords**.

---

## Project layout (for developers / Claude Code)
| File | What it is |
|---|---|
| `signal_hunter.py` | The scanning engine: sources, signal rules, scoring, email drafts, Excel export. It also works as a CLI: `python signal_hunter.py list.xlsx` or `--discover` |
| `webapp.py` | Flask web app: login, API routes, background scan jobs, cron endpoint |
| `db.py` | Storage. SQLite locally, Postgres when `DATABASE_URL` is set |
| `page.html`, `login.html` | The interface (plain HTML and JS) |
| `defaults.json` | Default profile and keywords (copied into the database on first run) |
| `cron_scan.py` | The daily scan without a web server (what GitHub Actions runs) |
| `.github/workflows/daily-scan.yml` | Daily scan on GitHub Actions |
| `tests/` | Automated tests (`python -m pytest -q tests`) and an offline UI harness with fake sources: `APP_PASSWORD=test CRON_TOKEN=tok python tests/run_mock_server.py` |
