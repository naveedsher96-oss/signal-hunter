"""
Weekly scan without a web server (runs in GitHub Actions, free).

Does what the app's /api/cron endpoint does: "Find warm companies" plus a re-scan of
your saved weekly list, and stores both in the database (DATABASE_URL = Supabase),
so they show up under History in the app on your computer.

    python cron_scan.py
"""

import sys

import webapp


def main():
    tasks = [("discover", [], "Weekly: Find warm companies")]
    saved = webapp.saved_list_task()
    if saved:
        tasks.append((saved[0], saved[1], "Weekly: " + saved[2].replace("Weekly list: ", "")))
    ok = True
    for mode, companies, label in tasks:
        print(f"== {label}", flush=True)
        ok = webapp.run_one(mode, companies, label) and ok
        print(f"   {webapp.JOB['current']} - {len(webapp.JOB['results'])} leads, "
              f"{webapp.JOB['new']} new signals" if not webapp.JOB["error"]
              else f"   failed: {webapp.JOB['error']}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
