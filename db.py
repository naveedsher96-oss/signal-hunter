"""
Tiny storage layer.

  * DATABASE_URL set (postgres://...)  -> Postgres (e.g. Supabase, free tier)
  * otherwise                          -> local SQLite file (signal_hunter.db)

Tables:
  settings(k, v)            profile, keywords, saved company list (JSON)
  runs(id, ...)             every scan: summary, results (JSON) and the Excel file
  seen(k, d)                signals already reported, so NEW only flags fresh ones
"""

import json
import os
import sqlite3
import threading
from datetime import datetime

def load_env_file(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """KEY=VALUE lines from a local .env file (never committed). Real environment
    variables win. Lets "Run locally.bat" use the shared Supabase database."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.strip().partition("=")
                if sep and k and not k.startswith("#"):
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


load_env_file()
URL = os.environ.get("DATABASE_URL", "").strip()
IS_PG = URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = os.environ.get("SQLITE_PATH",
                             os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "signal_hunter.db"))
_lock = threading.Lock()

if IS_PG:
    import psycopg

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS seen (k TEXT PRIMARY KEY, d TEXT NOT NULL)",
    ("CREATE TABLE IF NOT EXISTS runs (id {pk}, mode TEXT NOT NULL, label TEXT, "
     "created TEXT NOT NULL, status TEXT NOT NULL, summary TEXT, results TEXT, "
     "xlsx {blob}, xlsx_name TEXT, error TEXT)"),
    ("CREATE TABLE IF NOT EXISTS lead_status (k TEXT PRIMARY KEY, name TEXT NOT NULL, "
     "status TEXT NOT NULL, sent TEXT NOT NULL, note TEXT NOT NULL, "
     "updated TEXT NOT NULL)"),
]


def _connect():
    if IS_PG:
        # prepare_threshold=None keeps Supabase's connection pooler happy
        return psycopg.connect(URL, prepare_threshold=None, connect_timeout=15)
    con = sqlite3.connect(SQLITE_PATH, timeout=30)
    return con


def _q(sql):
    return sql.replace("?", "%s") if IS_PG else sql


def execute(sql, params=(), fetch=None):
    with _lock:
        con = _connect()
        try:
            cur = con.cursor()
            cur.execute(_q(sql), params)
            out = None
            if fetch == "one":
                out = cur.fetchone()
            elif fetch == "all":
                out = cur.fetchall()
            con.commit()
            return out
        finally:
            con.close()


def init():
    pk = "SERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    blob = "BYTEA" if IS_PG else "BLOB"
    for s in SCHEMA:
        execute(s.format(pk=pk, blob=blob))


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

# ----------------------------------------------------------------- settings --

def get_setting(k, default=None):
    row = execute("SELECT v FROM settings WHERE k = ?", (k,), fetch="one")
    return json.loads(row[0]) if row else default


def set_setting(k, v):
    execute("INSERT INTO settings (k, v) VALUES (?, ?) "
            "ON CONFLICT (k) DO UPDATE SET v = excluded.v", (k, json.dumps(v)))

# --------------------------------------------------------------------- seen --

def get_seen():
    return {k: d for k, d in execute("SELECT k, d FROM seen", fetch="all") or []}


def add_seen(new_items):
    """new_items: {key: date}. Only inserts keys that are not stored yet."""
    if not new_items:
        return
    with _lock:
        con = _connect()
        try:
            cur = con.cursor()
            sql = _q("INSERT INTO seen (k, d) VALUES (?, ?) ON CONFLICT (k) DO NOTHING")
            cur.executemany(sql, list(new_items.items()))
            con.commit()
        finally:
            con.close()

# --------------------------------------------------------------------- runs --

def create_run(mode, label):
    row = execute("INSERT INTO runs (mode, label, created, status) VALUES (?, ?, ?, ?) "
                  "RETURNING id", (mode, label, now(), "running"), fetch="one")
    return row[0]


def finish_run(run_id, summary, results, xlsx_bytes, xlsx_name):
    execute("UPDATE runs SET status = ?, summary = ?, results = ?, xlsx = ?, xlsx_name = ? "
            "WHERE id = ?", ("done", json.dumps(summary), json.dumps(results),
                             xlsx_bytes, xlsx_name, run_id))


def fail_run(run_id, error):
    execute("UPDATE runs SET status = ?, error = ? WHERE id = ?",
            ("error", str(error)[:1000], run_id))


def list_runs(limit=30):
    rows = execute("SELECT id, mode, label, created, status, summary, error FROM runs "
                   "ORDER BY id DESC LIMIT ?", (limit,), fetch="all") or []
    return [{"id": r[0], "mode": r[1], "label": r[2], "created": r[3], "status": r[4],
             "summary": json.loads(r[5]) if r[5] else {}, "error": r[6]} for r in rows]


def get_run(run_id):
    r = execute("SELECT id, mode, label, created, status, summary, results, error "
                "FROM runs WHERE id = ?", (run_id,), fetch="one")
    if not r:
        return None
    return {"id": r[0], "mode": r[1], "label": r[2], "created": r[3], "status": r[4],
            "summary": json.loads(r[5]) if r[5] else {},
            "results": json.loads(r[6]) if r[6] else [], "error": r[7]}


def get_run_xlsx(run_id):
    r = execute("SELECT xlsx, xlsx_name FROM runs WHERE id = ?", (run_id,), fetch="one")
    if not r or r[0] is None:
        return None, None
    return bytes(r[0]), r[1]


# ------------------------------------------------------------ lead status --

def set_lead_status(k, name, status, sent, note):
    execute("INSERT INTO lead_status (k, name, status, sent, note, updated) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (k) DO UPDATE SET name = excluded.name, "
            "status = excluded.status, sent = excluded.sent, "
            "note = excluded.note, updated = excluded.updated",
            (k, name, status, sent, note, now()))


def get_lead_statuses():
    return {r[0]: {"name": r[1], "status": r[2], "sent": r[3], "note": r[4],
                   "updated": r[5]}
            for r in execute("SELECT k, name, status, sent, note, updated "
                             "FROM lead_status", fetch="all") or []}


def clear_lead_status(k):
    execute("DELETE FROM lead_status WHERE k = ?", (k,))


def mark_stale_runs():
    """A restart kills running scans; don't leave them 'running' forever."""
    execute("UPDATE runs SET status = ?, error = ? WHERE status = ?",
            ("error", "Interrupted (the server restarted). Please run it again.",
             "running"))
