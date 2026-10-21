import os

import signal_hunter as sh

HERE = os.path.dirname(os.path.abspath(__file__))


def test_norm_strips_company_suffixes():
    assert sh.norm("Acme Technologies Inc.") == "acme"
    assert sh.same_company("GitLab Inc", "gitlab")
    assert not sh.same_company("Close", "Closeout Deals")


def test_to_date_handles_common_formats():
    assert sh.to_date("2026-10-01T12:00:00Z") == "2026-10-01"
    assert sh.to_date(1790000000) == sh.to_date(1790000000000)
    assert sh.to_date("Wed, 01 Oct 2025 10:00:00 GMT") == "2025-10-01"
    assert sh.to_date("not a date") == ""


def test_remote_status():
    job = lambda loc, wp="Remote": {"location": loc, "workplace": wp}
    assert sh.remote_status(job("Worldwide")) == "Eligible"
    assert sh.remote_status(job("Remote - US")) == "Region-locked"
    assert sh.remote_status(job("Austin", "")) == "Not remote"


def test_classify_real_asks_and_struggles(matchers):
    ask = sh.classify_post("[Hiring] GoHighLevel VA needed for our agency", "", "forhire",
                           matchers)
    assert ask[0] == "ask" and ask[1] == "GoHighLevel"
    struggle = sh.classify_post("Tracking leads in a spreadsheet and they keep falling "
                                "through the cracks", "", "sweatystartup", matchers)
    assert struggle[0] == "struggle" and struggle[1] == "CRM Automation"


def test_classify_skips_competitors(matchers):
    assert sh.classify_post("[For Hire] Experienced virtual assistant available", "",
                            "forhire", matchers) is None
    assert sh.classify_post("Looking for a VA? DM me, I offer services", "",
                            "Entrepreneur", matchers) is None


def test_discover_with_fake_sources(cfg):
    results = sh.discover(cfg)
    names = {r["company"]["company"] for r in results}
    assert "Brightpath Agency" in names
    assert "Reddit r/forhire - u/agencyowner22" in names
    assert not any("va_pro" in n for n in names)  # offering services, skipped
    assert not any("u/old" in n for n in names)  # outside lookback window
    assert all(0 <= r["score"] <= 100 for r in results)
    assert results == sorted(results, key=lambda r: (r["score"], r["newest"]), reverse=True)


def test_scan_list_and_excel(cfg, tmp_path):
    companies = sh.load_companies(os.path.join(HERE, "sample_companies.xlsx"))
    assert len(companies) == 7
    results = sh.run(companies, cfg)
    by = {r["company"]["company"]: r for r in results}
    assert by["Quiet Co"]["tier"] == "COLD"
    assert any(s["kind"] == "tech_ghl" for s in by["Acme Dental"]["signals"])
    seen = {}
    path, new = sh.write_outputs(cfg, results, "List", seen=seen, out_dir=str(tmp_path),
                                 emails=False)
    assert os.path.exists(path) and new == len(seen) > 0
    # second run: nothing is new any more
    _, new2 = sh.write_outputs(cfg, sh.run(companies, cfg), "List", seen=seen,
                               out_dir=str(tmp_path), emails=False)
    assert new2 == 0


def test_build_email_never_empty(cfg):
    for r in sh.discover(cfg):
        subject, body = sh.build_email(cfg, r["company"], r)
        assert subject and cfg["your_name"] in body


def test_ask_needs_the_service_in_the_same_clause(matchers):
    # the junk posts from the review: intent word and service word in different clauses
    junk = sh.classify_post("We are hiring a Rust dev, no sales", "", "startups", matchers)
    assert junk is None or junk[0] != "ask"
    junk = sh.classify_post("Anyone recommend a good pizza place, my sales are fine", "",
                            "Entrepreneur", matchers)
    assert junk is None or junk[0] != "ask"
    # real asks still count, whether the need comes before or after the ask
    assert sh.classify_post("Looking for someone to build GHL snapshots", "", "gohighlevel",
                            matchers)[:2] == ("ask", "GoHighLevel")
    assert sh.classify_post("GoHighLevel expert needed", "", "gohighlevel",
                            matchers)[:2] == ("ask", "GoHighLevel")
    # a [Hiring] tag makes the whole post the ask
    assert sh.classify_post("[Hiring] Help with our agency", "Need someone. Must know HubSpot.",
                            "forhire", matchers)[:2] == ("ask", "CRM Automation")


def test_exclude_words_skip_job_seekers(matchers):
    assert sh.classify_post("Virtual assistant looking for work, need clients", "",
                            "VirtualAssistant", matchers) is None


def test_tiers_need_more_than_one_ageing_post():
    def ev(kind, days, points=50):
        d = (sh.datetime.now() - sh.timedelta(days=days)).strftime("%Y-%m-%d")
        return {"kind": kind, "date": d, "points": points}
    assert sh.tier_of(50, [ev("ask", 3)]) == "HOT"           # fresh direct ask
    assert sh.tier_of(50, [ev("ask", 20)]) == "WARM"         # one older ask
    assert sh.tier_of(50, [ev("struggle", 2)]) == "WARM"     # a struggle alone
    assert sh.tier_of(60, [ev("struggle", 2), ev("tech", 2)]) == "HOT"  # backed up
    assert sh.tier_of(20, [ev("job_locked", 1)]) == "COLD"


def test_discover_tiers_are_spread(cfg):
    tiers = [r["tier"] for r in sh.discover(cfg)]
    assert "HOT" in tiers and "WARM" in tiers
    assert tiers.count("HOT") < len(tiers) / 2
