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


def test_cron_scan_script_stores_runs():
    import cron_scan
    before = len(webapp.db.list_runs(100))
    assert cron_scan.main() == 0
    runs = webapp.db.list_runs(100)
    assert len(runs) == before + 1 and runs[0]["label"] == "Auto: Find warm companies"
    assert runs[0]["status"] == "done"


def test_cron_scans_saved_list_only_once_a_day(monkeypatch):
    import cron_scan
    webapp.db.set_setting("saved_list", {"name": "Mine", "companies": [
        {"company": "Acme Dental", "website": "https://acmedental.com", "ats_slug": "",
         "contact_name": "", "contact_email": ""}]})
    try:
        monkeypatch.delenv("SCAN_SAVED_LIST", raising=False)
        monkeypatch.setattr(cron_scan, "DAILY_HOURS_UTC", ())
        before = len(webapp.db.list_runs(100))
        assert cron_scan.main() == 0
        assert len(webapp.db.list_runs(100)) == before + 1  # 2-hourly run: discover only
        monkeypatch.setenv("SCAN_SAVED_LIST", "1")
        assert cron_scan.main() == 0
        labels = [r["label"] for r in webapp.db.list_runs(2)]
        assert labels == ["Daily: Mine", "Auto: Find warm companies"]
    finally:
        webapp.db.execute("DELETE FROM settings WHERE k = ?", ("saved_list",))


def test_prune_runs_drops_old_scans():
    rid = webapp.db.create_run("discover", "old one")
    webapp.db.finish_run(rid, {}, [], b"x", "x.xlsx")
    webapp.db.execute("UPDATE runs SET created = ? WHERE id = ?", ("2020-01-01 00:00", rid))
    webapp.db.prune_runs(30)
    assert webapp.db.get_run(rid) is None


def test_filter_and_alert_settings_are_validated(client):
    login(client)
    c = client.post("/config", json={"min_budget_usd": "150", "max_bids": -3,
                                     "max_ask_age_days": "7"}).get_json()
    assert (c["min_budget_usd"], c["max_bids"], c["max_ask_age_days"]) == (150, 0, 7)
    assert client.post("/config", json={"max_bids": "lots"}).status_code == 400
    assert client.post("/config", json={"ntfy_topic": "bad topic!"}).status_code == 400
    assert client.post("/config", json={"ntfy_topic": "sh-naveed-7f3k9q"}).get_json()[
        "ntfy_topic"] == "sh-naveed-7f3k9q"
    client.post("/config", json={"ntfy_topic": "", "min_budget_usd": 0,
                                 "max_ask_age_days": 14})


def row(name, tier="HOT", new=True, ids=()):
    return {"company": name, "tier": tier, "new": new, "track": "Pitch", "to": "",
            "url": "https://post/" + name, "ids": list(ids),
            "signals": [{"detail": f"{name} needs GHL", "url": "https://post/" + name}]}


def test_alerts_only_new_unhandled_hot_leads(posts, monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    rows = [row("A"), row("B", tier="WARM"), row("C", new=False),
            row("D", ids=["d@x.com"]), row("E")]
    statuses = {"e": {"status": "contacted"},  # handled by name
                "other name": {"status": "contacted", "ids": ["d@x.com"]}}  # by email
    assert webapp.notify_hot(rows, {}, statuses) == 0 and not posts  # no topic, no alert
    assert webapp.notify_hot(rows, {"ntfy_topic": "sh-test-topic"}, statuses) == 1
    url, body = posts[0]
    assert url == "https://ntfy.sh/" and body["topic"] == "sh-test-topic"
    assert body["title"] == "HOT lead: A" and body["click"] == "https://post/A"


def test_many_alerts_are_summarised(posts):
    n = webapp.notify_hot([row(f"L{i}") for i in range(11)], {"ntfy_topic": "sh-test-topic"},
                          {})
    assert n == 11 and len(posts) == 9 and posts[-1][1]["title"] == "3 more HOT leads"


def test_junk_status_and_ids_roundtrip(client):
    login(client)
    assert client.post("/lead-status", json={
        "key": "craigslist austin - va", "name": "Craigslist austin - VA", "status": "junk",
        "note": "Too cheap", "ids": ["https://austin.craigslist.org/ggg/1.html"]}
    ).status_code == 200
    st = client.get("/lead-statuses").get_json()["craigslist austin - va"]
    assert st["status"] == "junk" and st["note"] == "Too cheap"
    assert st["ids"] == ["https://austin.craigslist.org/ggg/1.html"]
    client.post("/lead-status", json={"key": "craigslist austin - va", "status": ""})


def test_lead_ids_and_handled_match():
    assert webapp.lead_ids("Sarah@Nimbus.com", "https://www.nimbusrealty.com/x", "") == [
        "sarah@nimbus.com", "nimbusrealty.com"]
    st = {"nimbus": {"status": "contacted", "ids": ["nimbusrealty.com"]}}
    assert webapp.handled({"company": "Nimbus Realty LLC", "ids": ["nimbusrealty.com"]}, st)
    assert not webapp.handled({"company": "Other", "ids": ["other.com"]}, st)


def test_test_alert_endpoint(client, posts):
    login(client)
    assert client.post("/test-alert", json={"topic": "x"}).status_code == 400
    assert client.post("/test-alert", json={"topic": "sh-test-topic"}).status_code == 200
    assert posts[0][1]["topic"] == "sh-test-topic"
