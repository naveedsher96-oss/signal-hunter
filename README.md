# Signal Hunter

Warm leads for remote **GoHighLevel, CRM automation, Sales/BD, Customer Success and VA/admin** work.
Signal Hunter finds companies, small-business owners and new founders who have **publicly shown a need**, ranks them, and drafts an email that answers that specific need.

**Nothing is ever sent automatically.** You review each draft, then send it with **Open in Gmail** or reply on the post.

## What it does
- **Scan my list:** upload an Excel or CSV file, or paste company names. You can save the list as your **weekly list**, which is re-scanned every Monday.
- **Find warm companies:** no list needed. It finds Reddit and Hacker News posts asking for help or describing a struggle, plus remote job posts.
- **History:** every scan is saved, and each one comes with an Excel tracker to download.
- **Works on phone and laptop**, behind a password.

Signals, points and keywords are explained in the app under **Profile & keywords**. Everything you set there is editable.

---

## Put it online (free, about 20 minutes, once)

You need three free accounts: **Supabase** (the database), **Render** (hosting) and, optionally, a **Reddit app key**.

### 1. Database: Supabase
1. Go to https://supabase.com → **New project**. Name it `signal-hunter`, pick a database password and save the password somewhere. For region, choose **Singapore** or **Mumbai**.
2. When the project is ready, click **Connect** at the top of the page.
3. Under **Session pooler**, copy the **URI**. It looks like this:
   `postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`
4. Replace `[YOUR-PASSWORD]` with your database password. This full string is your **DATABASE_URL**.

> Use the **Session pooler** string, not "Direct connection". Render's servers can't reach the direct one.

The app creates its tables by itself on first start.

### 2. Reddit key (recommended)
Reddit often blocks apps that run on cloud servers. A free key fixes that.
1. Log in to Reddit, then open https://www.reddit.com/prefs/apps.
2. Click **create another app**.
3. Fill it in:
   - Name: `Signal Hunter`
   - Type: **script**
   - Redirect URI: `http://localhost:8080`
4. Click **Create app**.
5. Copy two values:
   - The **client ID**: the short code under the app name.
   - The **secret**.

If Reddit asks you to request API access first, submit that request. Until you're approved, the app still works, but Reddit results may be empty on the server.

### 3. Hosting: Render
1. Go to https://render.com and **sign up with GitHub**.
2. Click **New → Blueprint**, pick the **signal-hunter** repository, then click **Connect**.
3. Render reads `render.yaml` and asks you for these values:
   - `APP_PASSWORD`: the password you'll use to log in to the app
   - `DATABASE_URL`: the string from step 1
   - `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`: from step 2 (leave them empty if you skipped that step)
4. Click **Apply**. The first deploy takes about 3–5 minutes.
5. Open your app at the link Render shows, for example `https://signal-hunter-xxxx.onrender.com`.

> **Free plan:** the app goes to sleep after 15 minutes without visits, so the first load after that takes about 30–50 seconds. Upgrading to Render's $7/month plan keeps it awake.

### 4. Weekly automatic scan: GitHub
1. In Render, open your service → **Environment** and copy the value of **CRON_TOKEN**.
2. In GitHub, open this repository → **Settings → Secrets and variables → Actions → New repository secret**, and add two secrets:
   - `APP_URL`: your Render link, without a slash at the end
   - `CRON_TOKEN`: the value you copied
3. Test it: open the **Actions** tab → **Weekly scan** → **Run workflow**. Within a few minutes a new scan appears in the app's **History**.

From then on, the scan runs every **Monday at 8:00 AM Pakistan time**, and new leads are waiting when you open the app.

> GitHub pauses scheduled runs if a repository has had no activity for 60 days. If that happens, re-enable the workflow in the Actions tab.

---

## Run it on your own computer (optional)
Double-click **`Run locally.bat`** on Windows, or run:
```
pip install -r requirements.txt
python webapp.py
```
This opens http://127.0.0.1:8765 in your browser. Locally the data is stored in `signal_hunter.db` and there's no login.

## Project layout (for developers / Claude Code)
| File | What it is |
|---|---|
| `signal_hunter.py` | The scanning engine: sources, signal rules, scoring, email drafts, Excel export. It also works as a CLI: `python signal_hunter.py list.xlsx` or `--discover` |
| `webapp.py` | Flask web app: login, API routes, background scan jobs, weekly cron endpoint |
| `db.py` | Storage. SQLite locally, Postgres when `DATABASE_URL` is set |
| `page.html`, `login.html` | The interface (plain HTML and JS) |
| `defaults.json` | Default profile and keywords (copied into the database on first run) |
| `render.yaml` | Render deployment |
| `.github/workflows/weekly-scan.yml` | Monday scan |
| `tests/` | Automated tests (`python -m pytest -q tests`) and an offline UI harness with fake sources: `APP_PASSWORD=test CRON_TOKEN=tok python tests/run_mock_server.py` |
