"""Run the web app against fake (offline) data sources, for testing the UI.

    APP_PASSWORD=test CRON_TOKEN=tok python tests/run_mock_server.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault("SQLITE_PATH", os.path.join(HERE, "test.db"))

import mocks  # noqa: E402
import signal_hunter as sh  # noqa: E402

sh.http_get = mocks.http_get
sh.http_post_json = lambda url, payload: print("ALERT", payload) or True  # no real alerts
_orig = sh.with_defaults
sh.with_defaults = lambda c: dict(_orig(c), delay_seconds=0)

import webapp  # noqa: E402

webapp.app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8765")), threaded=True)
