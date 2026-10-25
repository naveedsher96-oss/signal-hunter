import time

import pytest

import webapp


@pytest.fixture
def client():
    webapp.FAILS.clear()
    return webapp.app.test_client()


def login(c, pw="test"):
    return c.post("/login", data={"password": pw})


def test_login_required(client):
    assert client.get("/status").status_code == 401
    assert client.get("/").status_code == 302
    assert login(client).status_code == 302
    assert client.get("/status").status_code == 200


def test_login_lockout(client, monkeypatch):
    monkeypatch.setattr(webapp.time, "sleep", lambda s: None)
    for _ in range(webapp.MAX_FAILS):
        assert b"Wrong password" in login(client, "nope").data
    r = login(client)  # even the right password is refused while locked out
    assert r.status_code == 200 and b"Too many" in r.data


def test_cron_token_header_only(client):
    assert client.get("/api/cron/status?token=tok").status_code == 403
    assert client.get("/api/cron/status", headers={"X-Cron-Token": "bad"}).status_code == 403
    assert client.get("/api/cron/status", headers={"X-Cron-Token": "tok"}).status_code == 200


def test_bad_lookback_is_400(client):
    login(client)
    assert client.post("/config", json={"lookback_days": "abc"}).status_code == 400
    assert client.post("/config", json={"lookback_days": 500}).get_json()["lookback_days"] == 180


def test_discover_job_end_to_end(client):
    login(client)
    assert client.post("/start", json={"mode": "discover"}).status_code == 200
    for _ in range(100):
        if client.get("/status").get_json()["state"] != "running":
            break
        time.sleep(0.1)
    st = client.get("/status").get_json()
    assert st["state"] == "done" and st["results"]
    runs = client.get("/runs").get_json()
    assert runs[0]["status"] == "done"
    assert client.get(f"/runs/{runs[0]['id']}/xlsx").status_code == 200


def test_lead_status_roundtrip(client):
    login(client)
    r = client.post("/lead-status", json={"key": "acme dental", "name": "Acme Dental",
                                          "status": "contacted"})
    assert r.status_code == 200
    st = client.get("/lead-statuses").get_json()
    assert st["acme dental"]["status"] == "contacted" and st["acme dental"]["sent"]
    assert client.post("/lead-status", json={"key": "acme dental",
                                             "status": "bogus"}).status_code == 400
    assert client.post("/lead-status", json={"key": "acme dental",
                                             "status": ""}).status_code == 200
    assert "acme dental" not in client.get("/lead-statuses").get_json()


def test_pwa_files_are_public(client):
    # manifest/sw/icons must be reachable before login so install works
    for url, kind in [("/manifest.json", "json"), ("/sw.js", "javascript"),
                      ("/pwa/icon-192.png", "png")]:
        r = client.get(url)
        assert r.status_code == 200 and kind in r.mimetype


def test_cron_scan_script_stores_runs():
    import cron_scan
    before = len(webapp.db.list_runs(100))
    assert cron_scan.main() == 0
    runs = webapp.db.list_runs(100)
    assert len(runs) == before + 1 and runs[0]["label"] == "Daily: Find warm companies"
    assert runs[0]["status"] == "done"
