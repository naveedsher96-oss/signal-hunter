"""Shared pytest setup: fake network sources and a throwaway database."""
import os
import sys
import tempfile
import time
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

# Must be set before db / webapp are imported
os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = ""  # empty, so a developer's .env can't point tests at Supabase
os.environ["APP_PASSWORD"] = "test"
os.environ["CRON_TOKEN"] = "tok"

import mocks  # noqa: E402
import signal_hunter as sh  # noqa: E402

sh.http_get = mocks.http_get
POSTS = []  # phone alerts "sent" during tests
sh.http_post_json = lambda url, payload: POSTS.append((url, payload)) or True
# No polite pauses between fake requests
sh.time = types.SimpleNamespace(time=time.time, sleep=lambda s: None)


@pytest.fixture
def cfg():
    return dict(sh.load_config(), delay_seconds=0, use_reddit=True)


@pytest.fixture
def matchers(cfg):
    return sh.Matchers(cfg)


@pytest.fixture
def posts():
    POSTS.clear()
    return POSTS
