"""
Scheduled scan without a web server (runs in GitHub Actions every 2 hours, free).

Each run does "Find warm companies" and stores it in the database (DATABASE_URL =
Supabase), so it shows up under History in the app on your computer. New HOT leads
are pushed to your phone when an ntfy topic is set. Your saved list is re-scanned
once a day (the 08:00 Pakistan run), and scans older than 30 days are cleaned up.

    python cron_scan.py              # SCAN_SAVED_LIST=1 forces the saved-list scan
"""

import os
import sys
from datetime import datetime, timezone

import db
import webapp

DAILY_HOURS_UTC = (3, 4)  # the 03:15 UTC run, even if GitHub starts it a bit late


def main():
    tasks = [("discover", [], "Auto: Find warm companies")]
    saved = webapp.saved_list_task()
    daily = (os.environ.get("SCAN_SAVED_LIST") == "1"
             or datetime.now(timezone.utc).hour in DAILY_HOURS_UTC)
    if saved and daily:
        tasks.append((saved[0], saved[1], "Daily: " + saved[2].replace("Saved list: ", "")))
    ok = True
    for mode, companies, label in tasks:
        print(f"== {label}", flush=True)
        ok = webapp.run_one(mode, companies, label) and ok
        print(f"   {webapp.JOB['current']} - {len(webapp.JOB['results'])} leads, "
              f"{webapp.JOB['new']} new signals" if not webapp.JOB["error"]
              else f"   failed: {webapp.JOB['error']}", flush=True)
        if not webapp.JOB["error"] and webapp.JOB.get("alerted"):
            print(f"   phone alerts: {webapp.JOB['alerted']} new HOT leads", flush=True)
    db.prune_runs(30)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
