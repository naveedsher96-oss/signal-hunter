"""gunicorn entry point with fake data sources (used to test the production setup)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import mocks  # noqa: E402
import signal_hunter as sh  # noqa: E402

sh.http_get = mocks.http_get
_orig = sh.with_defaults
sh.with_defaults = lambda c: dict(_orig(c), delay_seconds=0)
from webapp import app  # noqa: E402,F401
