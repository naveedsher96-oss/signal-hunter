import pytest
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
    assert tiers.count("HOT") < len(tiers)  # not everything is hot


def test_freelancer_and_jobicy_leads(cfg):
    results = {r["company"]["company"]: r for r in sh.discover(cfg)}
    fl = results["Freelancer.com project #40778167"]  # found by two queries, listed once
    assert fl["signals"][0]["kind"] == "ask" and fl["needs"][0] == "GoHighLevel"
    assert len(fl["signals"]) == 1 and "USD 10-15/hr" in fl["signals"][0]["detail"]
    # USD 15/hr -> worth ~300 -> +10 bonus on top of the 50-point ask
    assert fl["signals"][0]["points"] == 60


def test_budget_bonus():
    assert sh.budget_bonus(600, 10) == 20    # real money
    assert sh.budget_bonus(300, 10) == 10
    assert sh.budget_bonus(30, 10) == -15    # tiny budget
    assert sh.budget_bonus(600, 60) == 10    # big but 50+ bids already
    assert sh.budget_bonus(0, None) == 0


def test_freelancer_filtering_and_persons(cfg):
    results = {r["company"]["company"]: r for r in sh.discover(cfg)}
    assert "Freelancer.com project #40778168" not in results  # logo job: not our service
    assert "Freelancer.com project #40778169" not in results  # outside lookback window
    assert "Peak Roofing" in results  # Jobicy feed
    assert sh.is_person("Freelancer.com project #1") and not sh.is_person("Peak Roofing")


def test_freelancer_lead_gets_bid_draft(cfg, tmp_path):
    results = sh.discover(cfg)
    sh.write_outputs(cfg, results, "Discover", seen={}, out_dir=str(tmp_path),
                     emails=False)
    fl = next(r for r in results
              if r["company"]["company"].startswith("Freelancer.com"))
    body = fl["email"]["body"]
    assert body.startswith("Hi Sam!") and cfg["your_name"] in body  # owner's name
    assert "GoHighLevel Agency" in fl["email"]["subject"]
    assert len(body) < 1200 and "Best regards" not in body
    assert "roofpro" in fl["signals"][0]["detail"]  # who posted it, in the evidence


def test_news_discovers_new_companies(cfg):
    results = {r["company"]["company"]: r for r in sh.discover(cfg)}
    hd = results["Harbor Dental"]  # two headlines: GHL adoption + seed funding
    kinds = {s["kind"] for s in hd["signals"]}
    assert {"crm_news", "funding"} <= kinds
    # the contact finder found its site, and the site check saw the GHL script
    assert "tech_ghl" in kinds
    assert hd["company"]["contact_email"] == "amy.chen@harbordental.com"
    assert not any("Top 5 CRM" in n for n in results)  # junk headline filtered


def test_source_health_counts(cfg):
    stats = {}
    sh.discover(cfg, stats=stats)
    src = stats["sources"]
    assert src["Freelancer.com"] > 0 and src["Google News"] > 0
    assert src["Reddit"] > 0 and src["Job boards"] > 0
    assert src["Bluesky"] > 0 and src["Craigslist"] > 0


def test_followup_draft_mirrors_subject(cfg, tmp_path):
    results = sh.discover(cfg)
    sh.write_outputs(cfg, results, "Discover", seen={}, out_dir=str(tmp_path),
                     emails=False)
    comp = next(r for r in results
                if not sh.is_person(r["company"]["company"]) and r.get("followup"))
    assert comp["followup"]["subject"] == "Re: " + comp["email"]["subject"]
    assert "floating this back" in comp["followup"]["body"]
    fl = next(r for r in results
              if r["company"]["company"].startswith("Freelancer.com"))
    assert "followup" not in fl  # bids are answered on-platform, not emailed


def test_tracker_shows_pipeline_status(cfg, tmp_path):
    from openpyxl import load_workbook
    companies = sh.load_companies(os.path.join(HERE, "sample_companies.xlsx"))
    results = sh.run(companies, cfg)
    path, _ = sh.write_outputs(cfg, results, "List", seen={}, out_dir=str(tmp_path),
                               emails=False,
                               statuses={"acme dental": {"status": "contacted",
                                                         "sent": "2026-10-20"}})
    leads = load_workbook(path)["Leads"]
    col = {c.value: i for i, c in enumerate(leads[1])}
    row = next(r for r in leads.iter_rows(min_row=2)
               if r[0].value == "Acme Dental")
    assert row[col["Status"]].value == "Contacted"
    assert str(row[col["Sent date"]].value)[:10] == "2026-10-20"


def test_contact_finder_fills_email(cfg):
    results = {r["company"]["company"]: r for r in sh.discover(cfg)}
    nim = results["Nimbus Realty"]
    assert nim["company"]["contact_email"] == "sarah.lee@nimbusrealty.com"
    assert nim["company"]["contact_name"] == "Sarah Lee"
    assert nim["company"]["website"] == "https://nimbusrealty.com"
    # person leads keep "reply on the post" - no invented contact
    assert not results["Freelancer.com project #40778167"]["company"].get("contact_email")


def test_contact_emails_filters_junk():
    page = ('<a href="mailto:jane.doe@acme.com">x</a> noreply@acme.com '
            'icon@2x.png a@example.com info@acme.com')
    assert sh.contact_emails(page, "acme.com") == ["jane.doe@acme.com",
                                                   "info@acme.com"]


def test_new_sources(cfg):
    results = {r["company"]["company"]: r for r in sh.discover(cfg)}
    assert "River Clinics" in results  # Working Nomads feed
    assert "Craigslist austin - Need virtual assistant 10 hrs/wk for my clinic" in results
    assert not any("Selling my couch" in n for n in results)  # not a service ask
    assert sh.is_person("Craigslist austin - x")  # reply on the post, not an email


def test_reddit_can_be_switched_off(cfg):
    off = dict(cfg)
    off["use_reddit"] = False  # public .rss needs no key, so the default is on
    names = {r["company"]["company"] for r in sh.discover(sh.with_defaults(off))}
    assert not any(n.startswith("Reddit ") for n in names)
    assert any(n.startswith("Reddit ") for n in {r["company"]["company"]
                                                 for r in sh.discover(cfg)})


def test_bluesky_and_arbeitnow_leads(cfg):
    names = {r["company"]["company"] for r in sh.discover(cfg)}
    assert "Bluesky - @salonowner.bsky.social" in names
    assert "Klarheit GmbH" in names          # Arbeitnow remote job
    assert "Berlin Shop" not in names        # onsite job not fetched
    assert not any("dev.bsky" in n for n in names)  # offering services, skipped
    assert sh.is_person("Bluesky - @x")


def test_env_file_loader(tmp_path, monkeypatch):
    import db
    f = tmp_path / ".env"
    f.write_text('# comment\nSH_TEST_A="one"\nSH_TEST_B=two\nnot a pair\n')
    monkeypatch.setenv("SH_TEST_B", "already set")
    db.load_env_file(str(f))
    assert os.environ["SH_TEST_A"] == "one"
    assert os.environ["SH_TEST_B"] == "already set"
    monkeypatch.delenv("SH_TEST_A")


def test_freelancer_budget_bids_and_age_filters(cfg, monkeypatch):
    names = lambda c: {r["company"]["company"] for r in sh.discover(c)}
    assert "Freelancer.com project #40778167" in names(cfg)  # USD 15/hr, 40 bids, 2 days
    assert "Freelancer.com project #40778167" not in names(dict(cfg, min_budget_usd=500))
    assert "Freelancer.com project #40778167" not in names(dict(cfg, max_bids=30))
    assert "Freelancer.com project #40778167" not in names(dict(cfg, max_ask_age_days=1))
    assert "Freelancer.com project #40778167" in names(dict(cfg, max_ask_age_days=0))  # off


def test_freelancer_worth_is_in_usd(monkeypatch):
    fake = {"result": {"projects": [{"id": 1, "title": "CRM", "type": "fixed",
                                     "currency": {"code": "INR", "exchange_rate": 0.012},
                                     "budget": {"minimum": 5000, "maximum": 10000}},
                                    {"id": 2, "title": "CRM", "type": "fixed",
                                     "currency": {"code": "XYZ"},
                                     "budget": {"minimum": 50, "maximum": 100}}]}}
    monkeypatch.setattr(sh, "http_get", lambda url, **k: fake)
    worth = [p["worth"] for p in sh.freelancer_projects("crm")]
    assert worth == [120, 0]  # INR 10,000 is about $120; unknown currency -> 0 (no filter)


def test_first_seen_dates(cfg, tmp_path):
    results = sh.discover(cfg)
    seen = {}
    sh.write_outputs(cfg, results, "T", seen=seen, out_dir=str(tmp_path), emails=False)
    today = sh.datetime.now().strftime("%Y-%m-%d")
    assert all(r["first_seen"] == today for r in results if r["signals"])
    for r in results:
        for s in r["signals"]:
            seen[f"{r['company']['company'].lower()}|{s['kind']}|{s['url'] or s['detail'][:80]}"] = "2026-01-01"
    sh.write_outputs(cfg, results, "T", seen=seen, out_dir=str(tmp_path), emails=False)
    assert all(r["first_seen"] == "2026-01-01" and not r["any_new"]
               for r in results if r["signals"])


def test_list_scan_drafts_every_company_and_maps_phone(cfg, tmp_path, monkeypatch):
    rows = [{"Business": "Quiet Co", "Phone Number": "+1 (555) 010-2000", "Email": ""},
            {"Business": "Nimbus Realty", "Phone Number": "", "Email": ""}]
    mapping = sh.guess_columns(list(rows[0]))
    assert mapping["phone"] == "Phone Number" and mapping["company"] == "Business"
    companies = sh.to_companies(rows, mapping)
    assert companies[0]["phone"] == "+1 (555) 010-2000"
    monkeypatch.setattr(sh, "find_contacts",
                        lambda c, info=None, titles=None: (["hello@quiet.co"], "", "quiet.co")
                        if c["company"] == "Quiet Co" else ([], "", ""))
    by = {r["company"]["company"]: r for r in sh.run(companies, cfg)}
    quiet = by["Quiet Co"]
    assert quiet["tier"] == "COLD" and quiet["track"] == "Cold outreach (your list)"
    assert quiet["company"]["contact_email"] == "hello@quiet.co"  # looked up although COLD
    sh.write_outputs(cfg, list(by.values()), "List", seen={}, out_dir=str(tmp_path),
                     emails=False)
    assert all(r.get("email") and r["email"]["body"] for r in by.values())


def test_discover_still_skips_cold_drafts(cfg, tmp_path):
    results = sh.discover(cfg)
    sh.write_outputs(cfg, results, "D", seen={}, out_dir=str(tmp_path), emails=False)
    assert all(not r.get("email") for r in results if r["tier"] == "COLD")


# ------------------------------------------------- decision makers and emails --

TEAM_PAGE = """<html><title>Bright Smiles Dental</title><a href="/our-team">Team</a>
 <a href="mailto:info@brightsmiles.com">info</a></html>"""
TEAM_SUB = """<html><h2>Meet our team</h2>
 <div><h3>Jane Doe</h3><p>Founder &amp; Lead Dentist</p></div>
 <div><h3>Tom Hill</h3><p>Office Manager</p></div>
 <div><h3>Ann Lee</h3><p>Hygienist</p></div>
 <p>Questions? Email tom.hill@brightsmiles.com</p></html>"""


def lead(name, site="", tier="HOT"):
    return {"company": {"company": name, "website": site}, "tier": tier, "score": 80,
            "signals": [], "newest": ""}


@pytest.fixture
def team_site(monkeypatch):
    import mocks
    monkeypatch.setitem(mocks.R, "https://brightsmiles.com", TEAM_PAGE)
    monkeypatch.setitem(mocks.R, "https://brightsmiles.com/our-team", TEAM_SUB)
    monkeypatch.setitem(mocks.R, "dns.google/resolve?name=brightsmiles.com",
                        {"Status": 0, "Answer": [{"type": 15, "data": "10 mx.brightsmiles.com."}]})
    return mocks


def test_people_on_page_pairs_names_with_titles():
    people = sh.people_on_page(TEAM_SUB, sh.DEFAULT_DECISION_TITLES, "Bright Smiles Dental")
    assert [(p["name"], p["title"]) for p in people] == [
        ("Jane Doe", "Founder & Lead Dentist"), ("Tom Hill", "Office Manager")]
    ld = ('<script type="application/ld+json">{"@graph":[{"@type":"Person",'
          '"name":"Mark Ruiz","jobTitle":"Owner"}]}</script><p>Our Services</p>')
    assert sh.people_on_page(ld, sh.DEFAULT_DECISION_TITLES)[0]["name"] == "Mark Ruiz"


def test_email_pattern_is_learned_from_real_addresses():
    people = [{"name": "Tom Hill"}]
    assert sh.learn_pattern(["tom.hill@acme.com"], people, "acme.com") == "first.last"
    assert sh.learn_pattern(["thill@acme.com"], people, "acme.com") == "flast"
    assert sh.learn_pattern(["info@acme.com"], people, "acme.com") == ""
    assert sh.email_for("José Álvarez", "flast", "acme.com") == "jalvarez@acme.com"


def test_owner_email_is_guessed_from_the_pattern(cfg, team_site):
    r = lead("Bright Smiles Dental", "https://brightsmiles.com")
    sh.enrich_contacts([r], cfg)
    c = r["company"]
    assert (c["contact_name"], c["contact_title"]) == ("Jane Doe", "Founder & Lead Dentist")
    assert c["contact_email"] == "jane.doe@brightsmiles.com"
    assert c["contact_source"] == "guessed" and "first.last" in c["contact_note"]
    assert sh.contact_confidence(c).startswith("Guessed")


def test_no_guess_when_domain_takes_no_mail(cfg, team_site, monkeypatch):
    monkeypatch.setitem(team_site.R, "dns.google/resolve?name=brightsmiles.com",
                        {"Status": 3})
    r = lead("Bright Smiles Dental", "https://brightsmiles.com")
    sh.enrich_contacts([r], cfg)
    assert r["company"]["contact_source"] == "site"   # published address, not a guess
    assert r["company"]["contact_email"] == "tom.hill@brightsmiles.com"


def test_hunter_used_once_per_domain_within_budget(cfg, team_site, monkeypatch):
    calls = []
    real = sh.http_get

    def fake(url, as_json=True, headers=None):
        if "api.hunter.io" in url:
            calls.append((url, headers))
            return {"data": {"email": "jane@brightsmiles.com", "score": 94,
                             "position": "Founder", "verification": {"status": "valid"}}}
        return real(url, as_json, headers)
    monkeypatch.setattr(sh, "http_get", fake)
    cfg.update(hunter_api_key="k" * 30, _hunter_left=1)
    r = lead("Bright Smiles Dental", "https://brightsmiles.com")
    sh.enrich_contacts([r], cfg)
    c = r["company"]
    assert c["contact_email"] == "jane@brightsmiles.com" and c["contact_source"] == "hunter"
    assert "valid" in c["contact_note"] and cfg["_hunter_used"] == 1
    assert "first_name=Jane" in calls[0][0] and calls[0][1] == {"X-API-KEY": "k" * 30}
    # cached: a second scan costs nothing, and WARM leads never spend credits
    again, warm = lead("Bright Smiles Dental", "https://brightsmiles.com"), \
        lead("Bright Smiles Dental", "https://brightsmiles.com", tier="WARM")
    sh.enrich_contacts([again], cfg)
    sh.enrich_contacts([warm], cfg)
    assert len(calls) == 1 and again["company"]["contact_email"] == "jane@brightsmiles.com"
    assert warm["company"]["contact_source"] == "guessed"


def test_hunter_not_called_without_budget_or_key(cfg, team_site, monkeypatch):
    monkeypatch.setattr(sh, "http_get", lambda u, *a, **k: (
        pytest.fail("Hunter called") if "hunter" in u else team_site.http_get(u, *a, **k)))
    sh.enrich_contacts([lead("Bright Smiles Dental", "https://brightsmiles.com")],
                       dict(cfg, hunter_api_key="k" * 30, _hunter_left=0))
    sh.enrich_contacts([lead("Bright Smiles Dental", "https://brightsmiles.com")], cfg)


def test_excel_has_title_and_confidence(cfg, team_site, tmp_path):
    from openpyxl import load_workbook
    r = lead("Bright Smiles Dental", "https://brightsmiles.com")
    r.update(track="x", needs=[], remote_evidence="", intent_count=0, sources="")
    sh.enrich_contacts([r], cfg)
    path, _ = sh.write_outputs(cfg, [r], "T", seen={}, out_dir=str(tmp_path), emails=False)
    ws = load_workbook(path)["Leads"]
    col = {c.value: i for i, c in enumerate(ws[1])}
    row = list(ws.iter_rows(min_row=2, values_only=True))[0]
    assert row[col["Contact title"]] == "Founder & Lead Dentist"
    assert row[col["Email confidence"]].startswith("Guessed")


def test_cold_emails_carry_an_opt_out_line(cfg):
    r = lead("Bright Smiles Dental")
    r.update(track="Pitch", needs=["CRM Automation"], segment="", top_role="")
    _, body = sh.build_email(cfg, r["company"], r)
    assert body.rstrip().endswith(cfg["optout_line"])
    r["email"] = {"subject": "x", "body": body}
    assert cfg["optout_line"] in sh.build_followup(cfg, r["company"], r)[1]
    assert cfg["optout_line"] not in sh.build_email(dict(cfg, optout_line=""),
                                                     r["company"], r)[1]
