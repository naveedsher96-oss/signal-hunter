"""
Signal Hunter - web app

Local:   python webapp.py            (opens http://127.0.0.1:8765, SQLite, no login)
Server:  gunicorn webapp:app         (optional; Postgres via DATABASE_URL; password login)

DATABASE_URL can also come from a local .env file (see db.load_env_file).

Environment variables (all optional locally):
  APP_PASSWORD          password for the login page (login is off when not set)
  SECRET_KEY            signs the login cookie
  DATABASE_URL          Postgres connection string (Supabase "Session pooler" URI)
  CRON_TOKEN            secret the scheduled GitHub Action sends to /api/cron
  REDDIT_CLIENT_ID      free Reddit "script" app - keeps Reddit working on servers
  REDDIT_CLIENT_SECRET
  NTFY_TOPIC            ntfy.sh topic for phone alerts (overrides the setting)
"""

import hmac
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import time
import traceback
import uuid
from datetime import timedelta

from flask import (Flask, Response, jsonify, redirect, request, send_file, session,
                   url_for)

import db
import signal_hunter as sh

BASE = os.path.dirname(os.path.abspath(__file__))
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
CRON_TOKEN = os.environ.get("CRON_TOKEN", "")
ALLOWED = (".xlsx", ".xlsm", ".csv")
EDITABLE = {"your_name", "headline", "email", "linkedin", "portfolio", "years", "tools",
            "proof_point", "hiring_manager_titles", "lookback_days", "categories",
            "subreddits", "pain_signals", "smallbiz_words", "exclude_words",
            "freelancer_queries", "use_reddit", "min_budget_usd", "max_bids",
            "max_ask_age_days", "ntfy_topic", "news_queries", "use_bluesky",
            "bsky_queries"}
NUMBERS = {"min_budget_usd": 100000, "max_bids": 1000, "max_ask_age_days": 180}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(PERMANENT_SESSION_LIFETIME=timedelta(days=30),
                  SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
                  MAX_CONTENT_LENGTH=10 * 1024 * 1024)

db.init()
db.mark_stale_runs()

JOB = {"state": "idle", "mode": "", "done": 0, "total": 0, "current": "", "results": [],
       "run_id": None, "error": "", "new": 0, "stop": False, "label": "",
       "queue": []}
LOCK = threading.Lock()
UPLOADS = {}  # upload_id -> {"name", "headers", "rows"} (kept in memory, newest 10)

# ------------------------------------------------------------------ helpers --

def get_cfg():
    cfg = db.get_setting("config")
    if not cfg:
        with open(os.path.join(BASE, "defaults.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        db.set_setting("config", cfg)
    return sh.with_defaults(cfg)


def summarise(r):
    c = r["company"]
    top = r["signals"][0] if r["signals"] else None
    return {"company": c["company"], "tier": r["tier"], "score": r["score"],
            "track": r["track"], "remote": r["remote_evidence"], "needs": r["needs"],
            "segment": r.get("segment", ""), "count": r["intent_count"],
            "newest": r["newest"], "sources": r.get("sources", ""),
            "new": r.get("any_new", False), "first_seen": r.get("first_seen", ""),
            "to": c.get("contact_email", ""), "website": c.get("website", ""),
            "phone": c.get("phone", ""), "contact": c.get("contact_name", ""),
            "person": sh.is_person(c["company"]),
            "url": top["url"] if top else "", "email": r.get("email"),
            "followup": r.get("followup"),
            "signals": [{"label": s["label"], "detail": s["detail"], "url": s["url"],
                         "date": s["date"], "points": s["points"]}
                        for s in r["signals"][:6]],
            "ids": lead_ids(c.get("contact_email", ""), c.get("website", ""),
                            top["url"] if top else "")}


def lead_ids(email="", website="", url=""):
    """Ways to recognise the same lead under another name: email, domain, post link."""
    out = [(email or "").strip().lower(), sh.domain_of(website or "") if website else "",
           (url or "").strip().lower().rstrip("/")]
    return [x for x in out if x]


def handled(row, statuses):
    """The saved pipeline status that matches this lead (by name or by an id)."""
    st = statuses.get((row.get("company") or "").lower())
    if st:
        return st
    ids = set(row.get("ids") or [])
    return next((st for st in statuses.values() if ids & set(st.get("ids") or [])), None)


def notify_hot(rows, cfg, statuses=None):
    """Phone alert (free, ntfy.sh) for each HOT lead seen for the first time and not
    handled yet. Returns how many leads were announced."""
    topic = (os.environ.get("NTFY_TOPIC") or cfg.get("ntfy_topic") or "").strip()
    if not topic:
        return 0
    statuses = db.get_lead_statuses() if statuses is None else statuses
    fresh = [r for r in rows if r["tier"] == "HOT" and r.get("new")
             and not handled(r, statuses)]
    for r in fresh[:8]:
        top = r["signals"][0] if r["signals"] else {}
        sh.http_post_json("https://ntfy.sh/", {
            "topic": topic, "title": f"HOT lead: {r['company']}"[:120],
            "message": (top.get("detail") or r["track"])[:300]
                       + (f"\nEmail: {r['to']}" if r.get("to") else ""),
            "click": r.get("url") or top.get("url") or "", "tags": ["fire"],
            "priority": 4})
    if len(fresh) > 8:
        sh.http_post_json("https://ntfy.sh/", {
            "topic": topic, "title": f"{len(fresh) - 8} more HOT leads",
            "message": "Open Signal Hunter to see them all.", "tags": ["fire"]})
    return len(fresh)


def file_info(upload_id):
    u = UPLOADS[upload_id]
    return {"id": upload_id, "name": u["name"], "headers": u["headers"],
            "rows": len(u["rows"]), "guess": sh.guess_columns(u["headers"]),
            "preview": [[r.get(h, "") for h in u["headers"]] for r in u["rows"][:5]]}


def remember_upload(name, headers, rows):
    uid = uuid.uuid4().hex[:12]
    UPLOADS[uid] = {"name": name, "headers": headers, "rows": rows}
    while len(UPLOADS) > 10:
        UPLOADS.pop(next(iter(UPLOADS)))
    return uid

# -------------------------------------------------------------------- jobs --

def run_one(mode, companies, label):
    """Run one scan and store it. Must be called with JOB already 'running'."""
    run_id = db.create_run(mode, label)
    with LOCK:
        JOB.update(run_id=run_id, mode=mode, label=label, done=0, total=len(companies),
                   current="Starting...", results=[], error="")
    try:
        cfg = get_cfg()

        def progress(i, total, step_label, res):
            with LOCK:
                JOB["done"], JOB["total"], JOB["current"] = i, total, step_label
                if res is not None:
                    JOB["results"].append(summarise(res))

        stop = lambda: JOB["stop"]
        stats = {}
        if mode == "discover":
            results = sh.discover(cfg, on_progress=progress, should_stop=stop,
                                  stats=stats)
        else:
            results = sh.run(companies, cfg, on_progress=progress, should_stop=stop,
                             stats=stats)

        seen = db.get_seen()
        before = set(seen)
        with tempfile.TemporaryDirectory() as td:
            path, new = sh.write_outputs(cfg, results, "Discover" if mode == "discover"
                                         else "List", seen=seen, out_dir=td, emails=False,
                                         statuses=db.get_lead_statuses())
            with open(path, "rb") as f:
                xlsx = f.read()
            name = os.path.basename(path)
        db.add_seen({k: v for k, v in seen.items() if k not in before})
        rows = [summarise(r) for r in results]
        tiers = {t: sum(r["tier"] == t for r in rows) for t in ("HOT", "WARM", "COLD")}
        summary = {"label": label, "count": len(rows), "new": new, **tiers,
                   "sources": stats.get("sources") or {}}
        db.finish_run(run_id, summary, rows, xlsx, name)
        try:
            alerted = notify_hot(rows, cfg)
        except Exception:
            traceback.print_exc()  # an alert failing must never fail the scan
            alerted = 0
        with LOCK:
            JOB.update(results=rows, new=new, alerted=alerted, current="Done")
        return True
    except Exception as e:
        traceback.print_exc()
        db.fail_run(run_id, e)
        with LOCK:
            JOB["error"] = str(e)
        return False


def worker(tasks):
    """tasks: list of (mode, companies, label), run one after another."""
    ok = True
    for mode, companies, label in tasks:
        if JOB["stop"]:
            break
        ok = run_one(mode, companies, label) and ok
    with LOCK:
        JOB["state"] = "done" if ok else "error"


def start_job(tasks):
    with LOCK:
        if JOB["state"] == "running":
            return False
        JOB.update(state="running", stop=False, error="", new=0, results=[], run_id=None,
                   started=time.time())
    threading.Thread(target=worker, args=(tasks,), daemon=True).start()
    return True


def saved_list_task():
    saved = db.get_setting("saved_list")
    if saved and saved.get("companies"):
        return ("list", saved["companies"], f"Saved list: {saved.get('name', 'saved')}")
    return None

# -------------------------------------------------------------------- auth --

PUBLIC = {"login", "healthz", "cron", "cron_status", "static"}


@app.before_request
def require_login():
    if not APP_PASSWORD or request.endpoint in PUBLIC:
        return None
    if session.get("ok"):
        return None
    if request.path.startswith(("/api/", "/runs", "/status", "/config", "/upload",
                                "/paste", "/start", "/stop", "/saved-list",
                                "/lead-status", "/test-alert")):
        return jsonify(error="Please log in again."), 401
    return redirect(url_for("login"))


FAILS = {}  # ip -> [failed login times]
MAX_FAILS, FAIL_WINDOW = 5, 15 * 60


def _client_ip():
    # The last X-Forwarded-For entry is added by Render's proxy; earlier ones can be faked
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[-1].strip() if fwd else (request.remote_addr or "")


@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        ip, t = _client_ip(), time.time()
        with LOCK:
            recent = [f for f in FAILS.get(ip, []) if t - f < FAIL_WINDOW]
            FAILS[ip] = recent
        if len(recent) >= MAX_FAILS:
            err = "Too many wrong passwords. Try again in 15 minutes."
        elif hmac.compare_digest(request.form.get("password", ""), APP_PASSWORD):
            with LOCK:
                FAILS.pop(ip, None)
            session.permanent = True
            session["ok"] = True
            return redirect(url_for("index"))
        else:
            with LOCK:
                FAILS.setdefault(ip, []).append(t)
            time.sleep(1.5)  # slow down guessing
            err = "Wrong password."
    return Response(LOGIN_PAGE.replace("{{ERR}}", err), mimetype="text/html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/healthz")
def healthz():
    return "ok"

# --------------------------------------------------------------------- api --

@app.route("/")
def index():
    return Response(PAGE.replace("{{LOGOUT}}", "1" if APP_PASSWORD else ""),
                    mimetype="text/html")


@app.route("/status")
def status():
    with LOCK:
        return jsonify({k: v for k, v in JOB.items() if k not in ("stop", "queue")})


@app.route("/config", methods=["GET", "POST"])
def config():
    cfg = get_cfg()
    if request.method == "POST":
        for k, v in (request.get_json(silent=True) or {}).items():
            if k not in EDITABLE:
                continue
            if k == "lookback_days":
                try:
                    v = max(7, min(180, int(v or 45)))
                except (TypeError, ValueError):
                    return jsonify(error="Lookback days must be a number."), 400
            if k in NUMBERS:
                try:
                    v = max(0, min(NUMBERS[k], int(float(v or 0))))
                except (TypeError, ValueError):
                    return jsonify(error=f"{k} must be a number."), 400
            if k == "ntfy_topic":
                v = (v or "").strip()
                if v and not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", v):
                    return jsonify(error="Alert topic: 8-64 letters, digits, - or _."), 400
            cfg[k] = v
        db.set_setting("config", cfg)
    return jsonify(cfg)


@app.route("/upload", methods=["POST"])
def upload():
    name = os.path.basename(request.headers.get("X-Filename", "list.xlsx"))
    try:
        from urllib.parse import unquote
        name = unquote(name)
    except Exception:
        pass
    if not name.lower().endswith(ALLOWED):
        return jsonify(error="Please use an .xlsx or .csv file."), 400
    suffix = os.path.splitext(name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        tf.write(request.get_data())
        tmp = tf.name
    try:
        headers, rows = sh.read_table(tmp)
    except Exception as e:
        return jsonify(error=f"Couldn't read that file: {e}"), 400
    finally:
        os.unlink(tmp)
    if not headers:
        return jsonify(error="That file looks empty."), 400
    return jsonify(file_info(remember_upload(name, headers, rows)))


@app.route("/paste", methods=["POST"])
def paste():
    text = (request.get_json(silent=True) or {}).get("text", "")
    rows = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.replace("\t", ",").split(",") if p.strip()]
        if parts:
            rows.append({"Company": parts[0], "Website": parts[1] if len(parts) > 1 else ""})
    if not rows:
        return jsonify(error="Paste at least one company name."), 400
    return jsonify(file_info(remember_upload("Pasted list", ["Company", "Website"], rows)))


@app.route("/start", methods=["POST"])
def start():
    b = request.get_json(silent=True) or {}
    mode = b.get("mode", "list")
    if mode == "discover":
        tasks = [("discover", [], "Find warm companies")]
    elif mode == "saved":
        t = saved_list_task()
        if not t:
            return jsonify(error="You have no saved list yet."), 400
        tasks = [t]
    else:
        u = UPLOADS.get(b.get("upload_id", ""))
        if not u:
            return jsonify(error="Please add your list again (the upload expired)."), 400
        companies = sh.to_companies(u["rows"], b.get("mapping") or {})
        if not companies:
            return jsonify(error="No company names found in the column you picked."), 400
        if b.get("save_list"):
            db.set_setting("saved_list", {"name": u["name"], "companies": companies,
                                          "saved": db.now()})
        tasks = [("list", companies, u["name"])]
    if not start_job(tasks):
        return jsonify(error="A scan is already running."), 409
    return jsonify(ok=True)


@app.route("/stop", methods=["POST"])
def stop():
    with LOCK:
        JOB["stop"] = True
    return jsonify(ok=True)


@app.route("/saved-list", methods=["GET", "DELETE"])
def saved_list():
    if request.method == "DELETE":
        db.set_setting("saved_list", {})
        return jsonify(ok=True)
    s = db.get_setting("saved_list") or {}
    return jsonify({"name": s.get("name"), "count": len(s.get("companies") or []),
                    "saved": s.get("saved")} if s.get("companies") else {})


LEAD_STATUSES = {"contacted", "replied", "call", "proposal", "won", "dead", "junk"}


@app.route("/lead-statuses", endpoint="lead_statuses")
def lead_statuses():
    return jsonify(db.get_lead_statuses())


@app.route("/lead-status", methods=["POST"], endpoint="lead_status")
def lead_status():
    d = request.get_json(silent=True) or {}
    key = (d.get("key") or "").strip().lower()[:200]
    status = (d.get("status") or "").strip().lower()
    name = (d.get("name") or key).strip()[:200]
    if not key or (status and status not in LEAD_STATUSES):
        return jsonify(error="Bad status"), 400
    if not status:
        db.clear_lead_status(key)
        return jsonify(ok=True)
    sent = (d.get("sent") or "").strip()[:10]
    if status == "contacted" and not sent:
        sent = db.now()[:10]
    ids = [str(x).strip().lower()[:200] for x in (d.get("ids") or [])[:5] if str(x).strip()]
    db.set_lead_status(key, name, status, sent, (d.get("note") or "")[:500], ids)
    return jsonify(ok=True)


@app.route("/test-alert", methods=["POST"], endpoint="test_alert")
def test_alert():
    topic = ((request.get_json(silent=True) or {}).get("topic") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", topic):
        return jsonify(error="Make or type a topic name first (8-64 letters/digits)."), 400
    ok = sh.http_post_json("https://ntfy.sh/", {
        "topic": topic, "title": "Signal Hunter test alert", "tags": ["white_check_mark"],
        "message": "Alerts work. New HOT leads will show up here."})
    return (jsonify(ok=True) if ok
            else (jsonify(error="ntfy.sh didn't answer. Try again in a minute."), 502))


@app.route("/runs")
def runs():
    return jsonify(db.list_runs(int(request.args.get("limit", 30))))


@app.route("/runs/<int:run_id>")
def run_detail(run_id):
    r = db.get_run(run_id)
    return (jsonify(r), 200) if r else (jsonify(error="Not found"), 404)


@app.route("/runs/<int:run_id>/xlsx")
def run_xlsx(run_id):
    data, name = db.get_run_xlsx(run_id)
    if not data:
        return jsonify(error="No tracker for this scan"), 404
    import io
    return send_file(io.BytesIO(data), as_attachment=True, download_name=name,
                     mimetype="application/vnd.openxmlformats-officedocument."
                              "spreadsheetml.sheet")

# -------------------------------------------------------------------- cron --

def _cron_ok():
    # Header only: a token in the URL would end up in server logs
    token = request.headers.get("X-Cron-Token", "")
    return bool(CRON_TOKEN) and hmac.compare_digest(token, CRON_TOKEN)


@app.route("/api/cron", methods=["POST", "GET"], endpoint="cron")
def cron():
    if not _cron_ok():
        return jsonify(error="Bad token"), 403
    tasks = [("discover", [], "Daily: Find warm companies")]
    t = saved_list_task()
    if t:
        tasks.append((t[0], t[1], "Daily: " + t[2].replace("Saved list: ", "")))
    if not start_job(tasks):
        return jsonify(started=False, reason="A scan is already running."), 409
    return jsonify(started=True, scans=len(tasks)), 202


@app.route("/api/cron/status", endpoint="cron_status")
def cron_status():
    if not _cron_ok():
        return jsonify(error="Bad token"), 403
    return jsonify(state=JOB["state"], current=JOB["current"], label=JOB["label"])

# -------------------------------------------------------------------- pages --

with open(os.path.join(BASE, "page.html"), encoding="utf-8") as f:
    PAGE = f.read()
with open(os.path.join(BASE, "login.html"), encoding="utf-8") as f:
    LOGIN_PAGE = f.read()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    url = f"http://127.0.0.1:{port}"
    print(f"Signal Hunter is running at {url}  (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
