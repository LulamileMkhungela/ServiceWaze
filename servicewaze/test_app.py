"""Automated tests for ServiceWaze v3 — backend, PWA shell and the money engine."""
import os
import sys
import pytest
import time
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as app_module            # noqa: E402
import auth                          # noqa: E402
import feeds                         # noqa: E402
import grid as grid_mod              # noqa: E402
import i18n                          # noqa: E402
import impact                        # noqa: E402
import insights                      # noqa: E402
import push                          # noqa: E402
import receipts                      # noqa: E402
import resilience                    # noqa: E402
import sources                       # noqa: E402
import tariffs                       # noqa: E402
import transport                     # noqa: E402
import ussd                          # noqa: E402
import safety                        # noqa: E402
import watch                         # noqa: E402
import whatsapp                      # noqa: E402

DEVICE = "pytest-device"


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c


# ----------------------------------------------------------------- modules
def test_module_imports():
    for m in (app_module, auth, feeds, grid_mod, i18n, impact, insights, push,
              receipts, resilience, safety, sources, tariffs, transport, ussd, watch, whatsapp):
        assert m is not None


# -------------------------------------------------------------------- PWA
def test_root_pwa_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "ServiceWaze" in r.text
    assert "/static/js/app.js" in r.text
    assert "/manifest.webmanifest" in r.text


def test_manifest_endpoint(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert "application/manifest+json" in r.headers.get("content-type", "")
    data = r.json()
    assert data.get("short_name") == "ServiceWaze"
    assert data.get("display") == "standalone"
    assert any(i["purpose"] == "maskable" for i in data["icons"])
    assert len(data.get("shortcuts", [])) >= 2


def test_service_worker_and_assets(client):
    for path, needle in [("/sw.js", "sw-v3"), ("/static/css/app.css", "--accent"),
                         ("/static/js/app.js", "ServiceWaze"),
                         ("/static/icons/icon-192.png", None)]:
        r = client.get(path)
        assert r.status_code == 200, path
        if needle:
            assert needle in r.text, path


def test_openapi_docs(client):
    assert client.get("/docs").status_code == 200


# ----------------------------------------------------------------- core API
def test_health(client):
    d = client.get("/api/health").json()
    assert d["ok"] is True and "version" in d


def test_areas_search(client):
    d = client.get("/api/areas?q=Soweto").json()
    assert any("Soweto" in r["name"] for r in d["results"])
    assert d["results"][0]["lat"] and d["results"][0]["lon"]


def test_status_bundle(client):
    d = client.get(f"/api/status?q=Soweto&device={DEVICE}").json()
    for key in ("place", "weather", "electricity", "water", "impact", "grid", "cost", "meta"):
        assert key in d, key
    imp = d["impact"]
    assert "threats" in imp and "plan" in imp and "risk" in imp
    assert isinstance(imp["plan"]["tasks"], list)
    assert d["place"]["name"].startswith("Soweto")


def test_impact_produces_a_plan_that_fits(client):
    d = client.get("/api/impact?q=Soweto").json()
    plan = d["plan"]
    assert plan["tasks"], "impact always returns at least one preparation task"
    assert plan["minutes_left"] >= 0
    assert plan["value_at_stake_rand"] >= 0
    for t in plan["tasks"]:
        assert {"id", "title", "minutes", "xp"} <= set(t)


def test_services_directory(client):
    d = client.get("/api/services").json()
    for key in ("electricity", "water", "transport", "emergency", "food", "money"):
        assert key in d["services"], key


def test_ussd_simulation_api(client):
    r = client.get("/api/ussd?session=test-123&input=1")
    assert r.status_code == 200
    assert "ServiceWaze" in r.text or "Soweto" in r.text


# ------------------------------------------------------------- money engine
def test_electricity_bill_uses_published_tariff(client):
    d = client.get("/api/cost/electricity?kwh=350&tariff=eskom_homepower").json()
    assert d["total"] > d["energy"]           # fixed charges included
    assert 2.0 < d["blended_per_kwh"] < 6.0   # plausible rand/kWh for 2026/27


def test_water_bill_honours_free_basic_water(client):
    d = client.get("/api/cost/water?kl=6&city=johannesburg").json()
    assert d["total"] == 0, "first 6 kl are free in Johannesburg"
    more = client.get("/api/cost/water?kl=15&city=johannesburg").json()
    assert more["total"] > 0
    assert sum(l["kl"] for l in more["lines"]) == 9  # 15 kl used − 6 kl free


def test_appliance_cost(client):
    d = client.get("/api/cost/appliance?key=kettle&tariff=eskom_homepower").json()
    assert d["kwh"] > 0 and d["cost"] > 0 and d["appliance"] == "kettle"


def test_time_of_use_returns_cheapest_first(client):
    d = client.get("/api/cost/tou?tariff=eskom_homeflex").json()
    prices = [w["price"] for w in d["windows"]]
    assert prices == sorted(prices)


def test_food_basket(client):
    d = client.get("/api/cost/basket?area=Johannesburg&people=4").json()
    assert d["monthly"] > 0 and d["food_poverty_line_per_person"] > 0


def test_harvest_and_solar(client):
    h = client.get("/api/cost/harvest?lat=-26.2&lon=27.9&roof_m2=80").json()
    assert h["litres"] >= 0 and "forecast_mm" in h
    s = client.get("/api/cost/solar?lat=-26.2&lon=27.9&kwp=3").json()
    assert s["kwh_per_day"] > 0 and s["payback_years"]


def test_leak_detection():
    # 10 L overnight with all taps closed = 1 L/h: normal (a toilet that is
    # barely weeping) → "ok"
    ok = [{"kl_total": 100.000, "at": "2026-09-01T20:00:00+00:00"},
          {"kl_total": 100.010, "at": "2026-09-02T06:00:00+00:00"}]
    assert tariffs.leak_check(ok)["verdict"] == "ok"
    # 400 L overnight = 40 L/h continuous flow → almost certainly a leak
    leaky = [{"kl_total": 100.0, "at": "2026-09-01T20:00:00+00:00"},
             {"kl_total": 100.4, "at": "2026-09-02T06:00:00+00:00"}]
    out = tariffs.leak_check(leaky)
    assert out["verdict"] == "likely_leak"
    assert out["monthly_kl_if_continuous"] > 20, "a leak this size wastes 20+ kl a month"


# ------------------------------------------------------------- resilience
def test_identity_is_pseudonymous_and_stable(client):
    a = client.post(f"/api/me/identify?device={DEVICE}&area=Soweto").json()
    b = client.post(f"/api/me/identify?device={DEVICE}&area=Soweto").json()
    assert a["handle"] == b["handle"] and a["handle"].startswith("Neighbour ")


def test_profile_updates_score(client):
    before = client.get(f"/api/me/profile?device={DEVICE}").json()["score"]["score"]
    r = client.post("/api/me/profile", json={"device": DEVICE, "people": 4, "water_l": 300,
                                             "backup_light": 1, "food_days": 3, "route_plan": 1}).json()
    assert r["score"]["score"] >= before


def test_action_awards_xp(client):
    before = client.get(f"/api/me/summary?device={DEVICE}").json()["level"]["xp"]
    r = client.post("/api/me/action", json={"device": DEVICE, "action": "stored_water"}).json()
    assert r["xp_earned"] > 0
    after = client.get(f"/api/me/summary?device={DEVICE}").json()["level"]["xp"]
    assert after == before + r["xp_earned"]


def test_savings_ledger(client):
    r = client.post("/api/me/savings", json={"device": DEVICE, "kind": "water",
                                             "amount": 120.5, "note": "test"}).json()
    assert r["total"] >= 120.5
    assert any(e["kind"] == "water" for e in r["entries"])


def test_badges_and_challenges(client):
    assert client.get(f"/api/badges?device={DEVICE}").json()["badges"]
    ch = client.get(f"/api/challenges?device={DEVICE}").json()
    assert len(ch["challenges"]) == 3


def test_leaderboard_aggregates_by_area(client):
    d = client.get("/api/leaderboard").json()
    assert "areas" in d and "neighbours" in d and d["totals"]["neighbours"] >= 1


# ------------------------------------------------------------------- grid
def test_grid_offer_claim_cycle(client):
    title = "Pytest water offer"
    r = client.post("/api/grid/add", json={"device": DEVICE, "kind": "water", "mode": "offer",
                                           "title": title, "detail": "test", "area": "Testville"}).json()
    assert r["ok"] and r["id"]
    mine = client.get(f"/api/grid/mine?device={DEVICE}").json()
    assert any(o["id"] == r["id"] for o in mine["mine"])
    claimed = client.post("/api/grid/claim", json={"device": "pytest-other", "id": r["id"]}).json()
    assert claimed["ok"]
    dupe = client.post("/api/grid/claim", json={"device": DEVICE, "id": r["id"]})
    assert dupe.status_code == 400, "you cannot claim your own listing"
    assert client.post("/api/grid/close", json={"device": DEVICE, "id": r["id"]}).json()["ok"]


def test_grid_is_area_scoped(client):
    client.post("/api/grid/add", json={"device": DEVICE, "kind": "water", "mode": "offer",
                                       "title": "Soweto only", "area": "Soweto"})
    soweto = client.get("/api/grid?area=Soweto").json()
    cape = client.get("/api/grid?area=Cape%20Town").json()
    assert any("Soweto only" in o["title"] for o in soweto["offers"])
    assert not any("Soweto only" in o["title"] for o in cape["offers"])


def test_grid_points(client):
    d = client.get("/api/grid/points?lat=-26.2485&lon=27.8546&kinds=water").json()
    assert "points" in d


def test_stokvel_flow(client):
    name = "Pytest Tank Fund"
    s = client.post("/api/stokvels", json={"device": DEVICE, "name": name, "purpose": "tank",
                                           "area": "Testville", "target": 4500}).json()
    assert s["id"]
    c = client.post(f"/api/stokvels/{s['id']}/contribute",
                    json={"device": DEVICE, "amount": 250}).json()
    assert c["stokvel"]["saved"] == 250
    detail = client.get(f"/api/stokvels/{s['id']}").json()["stokvel"]
    assert detail["progress"] > 0 and detail["members_list"]


def test_grid_stats(client):
    d = client.get("/api/grid/stats").json()
    assert "open_offers" in d and d["stokvel_rand"] >= 0


# --------------------------------------------------------------- receipts
def test_report_issues_receipt_with_sla(client):
    r = client.post("/api/report", json={"area": "Testville", "kind": "no_water",
                                         "message": "pytest", "device": DEVICE}).json()
    assert r["id"] and r["receipt"]["ref"].startswith("SW-")
    assert r["receipt"]["sla_hours"] == 24
    assert r["receipt"]["entity"]


def test_receipt_update_resolve_and_scorecard(client):
    rid = client.post("/api/report", json={"area": "Testville", "kind": "leak",
                                           "message": "pytest leak", "device": DEVICE}).json()["id"]
    up = client.post(f"/api/receipt/{rid}/update", json={"text": "crew dispatched"}).json()
    assert any("crew dispatched" in u["text"] for u in up["updates"])
    res = client.post(f"/api/receipt/{rid}/resolve", json={"by": "pytest"}).json()
    assert res["state"] == "resolved"
    card = client.get("/api/scorecard?area=Testville").json()
    assert card["total"] >= 1 and "sla_compliance" in card


# ----------------------------------------------------------- transparency
def test_source_health_console(client):
    d = client.get("/api/sources/health").json()
    assert "sources" in d and "summary" in d
    assert isinstance(d["summary"]["total"], int)


def test_i18n_bundle(client):
    en = client.get("/api/i18n?lang=en").json()
    zu = client.get("/api/i18n?lang=zu").json()
    assert en["strings"]["water"] == "Water"
    assert zu["strings"]["water"] == "Amanzi"
    assert len(zu["languages"]) == 5


def test_data_is_provenance_tagged(client):
    d = client.get("/api/status?q=Soweto").json()
    w = d["weather"]
    assert "tier" in w and "live" in w and "source" in w
    assert w["tier"] in ("live", "device", "cache", "sim")


# ------------------------------------------------- self-calibrating forecast
def test_insights_forecast_is_explainable():
    j = insights.predict("Pytestville", 24, log=False)
    assert "forecasts" in j
    for svc, f in j["forecasts"].items():
        assert 0.03 <= f["prob"] <= 0.97, svc
        assert f["band"] in ("unlikely", "possible", "likely", "very likely")
        assert isinstance(f["drivers"], list)
        assert "sample" in f and "calibration" in f


def test_insights_outcome_trains_the_model():
    insights.record_outcome("Pytestville", "water", True, "test")
    insights.record_outcome("Pytestville", "water", False, "test")
    acc = insights.forecast_accuracy("Pytestville")
    assert "n" in acc and "brier" in acc
    hist = insights.history("Pytestville")
    assert hist["area"] == "Pytestville"


def test_forecast_endpoints(client):
    f = client.get("/api/insights/forecast?area=Soweto&horizon_h=12").json()
    assert "forecasts" in f
    h = client.get("/api/insights/history?area=Soweto").json()
    assert "services" in h
    r = client.post("/api/insights/outcome",
                    json={"area": "Pytestville", "service": "power", "happened": True}).json()
    assert r["ok"] is True
    a = client.get("/api/insights/accuracy?area=Pytestville").json()
    assert "n" in a


# ------------------------------------------------- climate-smart small business
def test_business_list_add_and_vouch():
    grid_mod.business_add("Pytest Welding", "other", "Pytestville", "082 000 0000",
                          "Fixes tanks and gates", None, None, "pytest-biz")
    out = grid_mod.business_list("Pytestville")
    names = [b["name"] for b in out["businesses"]]
    assert "Pytest Welding" in names
    bid = [b for b in out["businesses"] if b["name"] == "Pytest Welding"][0]["id"]
    grid_mod.business_verify(bid, "pytest-other")
    after = grid_mod.business_list("Pytestville")
    row = [b for b in after["businesses"] if b["id"] == bid][0]
    assert row["verified"] >= 1
    assert out["checklist"]["title"]


def test_open_board_round_trip():
    grid_mod.post_open("Pytest Spaza", "Pytestville", "open", "Generator on", "pytest-biz")
    board = grid_mod.open_board("Pytestville")
    assert any(b["name"] == "Pytest Spaza" for b in board["open"])
    assert board["ttl_hours"] == 24
    grid_mod.post_open("Pytest Spaza", "Pytestville", "closed", "No stock", "pytest-biz")
    board = grid_mod.open_board("Pytestville")
    assert any(b["name"] == "Pytest Spaza" for b in board["closed"])


def test_business_endpoints(client):
    r = client.post("/api/business/add", json={"device": DEVICE, "name": "Pytest Solar Co",
                                               "category": "solar", "area": "Pytestville",
                                               "detail": "Panels and batteries"}).json()
    assert r["ok"] is True
    biz = client.get("/api/business?area=Pytestville").json()["businesses"]
    assert any(b["name"] == "Pytest Solar Co" for b in biz)
    open_r = client.get("/api/business/board?area=Pytestville").json()
    assert "open" in open_r and "closed" in open_r


# ------------------------------------------------------ estimated schedules
def test_estimated_schedule_is_labelled():
    est = sources.estimated_schedule("Soweto", 4)
    assert est["estimated"] is True
    assert est["stage"] == 4
    assert len(est["upcoming"]) > 0
    assert sources.estimated_schedule("Soweto", 0) is None


def test_schedule_endpoint(client):
    j = client.get("/api/electricity/schedule?q=Soweto").json()
    assert "schedule" in j
    sch = j["schedule"]
    if sch is not None:
        assert "estimated" in sch or "windows" in sch


# --------------------------------------------------------------- watch circle
def test_watch_circle_states():
    watch.add("pytest-w1", "Gogo at no. 7", "Pytestville", "walking frame")
    before = watch.circle("Pytestville", "pytest-w1")
    assert any(p["handle"] == "Gogo at no. 7" for p in before["people"])
    row = [p for p in before["people"] if p["handle"] == "Gogo at no. 7"][0]
    assert row["state"] in ("unknown", "quiet", "knock", "ok")
    watch.checkin("pytest-w2", row["id"])
    after = watch.circle("Pytestville", "pytest-w1")
    row2 = [p for p in after["people"] if p["handle"] == "Gogo at no. 7"][0]
    assert row2["state"] == "ok" and row2["hours_since"] < 1


def test_watch_im_safe_and_flag():
    assert watch.im_safe("pytest-w1", "Pytestville")["ok"] is True
    watch.add("pytest-w3", "Uncle at no. 9", "Pytestville")
    row = [p for p in watch.circle("Pytestville")["people"] if p["handle"] == "Uncle at no. 9"][0]
    watch.flag("pytest-w3", row["id"], "needs_help", "no water for medication")
    flagged = [p for p in watch.circle("Pytestville")["people"] if p["handle"] == "Uncle at no. 9"][0]
    assert flagged["state"] == "needs_help"


def test_watch_endpoints(client):
    area = "Pytestville-%d" % int(time.time())          # unique per run
    r = client.post("/api/watch/add", json={"device": DEVICE, "handle": "Test Neighbour",
                                            "area": area, "note": "test"}).json()
    assert r["ok"] is True
    c = client.get(f"/api/watch?area={area}&device={DEVICE}").json()
    assert c["area"] == area and "privacy" in c
    row = [p for p in c["people"] if p["handle"] == "Test Neighbour"][0]
    assert client.post("/api/watch/checkin", json={"device": DEVICE, "id": row["id"]}).json()["ok"] is True
    assert client.post("/api/watch/im-safe", json={"device": DEVICE, "area": area}).json()["ok"] is True
    dup = client.post("/api/watch/add", json={"device": DEVICE, "handle": "Test Neighbour",
                                              "area": area}).json()
    assert dup["ok"] is False          # you cannot watch the same person twice


# ------------------------------------------------------------------- safety
def test_curated_helplines_are_sourced():
    r = safety.resources()
    assert r["tier"] == "curated"
    nums = {c["tel"] for c in r["resources"]}
    assert "0800 428 428" in nums          # GBV Command Centre
    assert "10111" in nums and "112" in nums
    assert all(c.get("source") for c in r["resources"]), "every number must cite a source"
    assert any(k["id"] == "streetlight" for k in r["unsafe_kinds"])


def test_safewalk_arrive_and_overdue():
    w = safety.walk_start("pytest-s1", "Pytestville", "home", 20)
    assert w["ok"] is True and w["due_minutes"] == 20
    assert safety.walk_arrive(w["id"], "pytest-s1")["status"] == "arrived"
    # a second walk pushed into the past must read as overdue
    w2 = safety.walk_start("pytest-s2", "Pytestville", "shop", 5)
    import sqlite3 as _sq
    con = _sq.connect(safety.DB)
    con.execute("UPDATE walks SET due=? WHERE id=?",
                ((datetime.now(timezone.utc) - timedelta(minutes=9)).isoformat(timespec="seconds"), w2["id"]))
    con.commit(); con.close()
    rows = [x for x in safety.walks("Pytestville", "pytest-s2")["walks"] if x["id"] == w2["id"]]
    assert rows and rows[0]["overdue_by"] > 0
    assert safety.walk_check(w2["id"], "pytest-s3")["ok"] is True
    assert safety.walk_alert(w2["id"], "pytest-s2")["status"] == "alerted"


def test_sos_raises_an_alert():
    r = safety.sos("pytest-s4", "Pytestville", "being followed", -26.2, 27.8)
    assert r["ok"] is True and r["notified"] >= 0
    assert any(c["id"] == "gbvcc" for c in r["resources"])
    a = safety.alerts("Pytestville")
    assert any(x["handle"] == r["handle"] for x in a["alerts"])


def test_unsafe_place_becomes_a_receipt():
    out = safety.report_unsafe("Soweto", "streetlight", "Pole 14 dark for three weeks", "pytest-s5")
    assert out["ok"] is True
    rec = out["receipt"]
    assert rec["ref"].startswith("SW-")
    assert "safety" in (rec.get("entity") or "").lower() or "public safety" in (rec.get("entity") or "").lower()
    assert rec["sla_hours"] == 72


def test_safety_endpoints(client):
    res = client.get("/api/safety/resources").json()
    assert res["tier"] == "curated"
    w = client.post("/api/safety/walk", json={"device": DEVICE, "area": "Pytestville",
                                              "dest": "home", "minutes": 15}).json()
    assert w["ok"] is True
    assert client.post("/api/safety/walk/arrive", json={"device": DEVICE, "id": w["id"]}).json()["ok"] is True
    s = client.post("/api/safety/sos", json={"device": DEVICE, "area": "Pytestville",
                                             "note": "test"}).json()
    assert s["ok"] is True
    assert client.get("/api/safety/alerts?area=Pytestville").json()["alerts"]
    u = client.post("/api/safety/unsafe", json={"device": DEVICE, "area": "Soweto",
                                                "kind": "streetlight",
                                                "message": "dark corner by the shop"}).json()
    assert u["ok"] is True and u["receipt"]["ref"].startswith("SW-")


# --------------------------------------------------- prepaid runway + council
def test_prepaid_runway_math():
    j = tariffs.prepaid_runway(120, daily_kwh=12, tariff_id="eskom_homepower",
                               outage_hours_per_day=0, topup_rand=100)
    assert abs(j["daily_net_kwh"] - 12) < 0.01
    assert abs(j["days_left"] - 10.0) < 0.2
    assert j["cost_per_day"] > 0 and j["topup_units"] > 0
    assert j["shortfall_units"] >= 0 and j["state"] in ("ok", "low", "critical", "short_of_month_end")
    # load shedding saves units, so the runway gets longer
    with_out = tariffs.prepaid_runway(120, daily_kwh=12, outage_hours_per_day=6)
    assert with_out["days_left"] > j["days_left"]


def test_prepaid_endpoint(client):
    d = client.get("/api/cost/prepaid?units=50&daily=10&area=Soweto&target_days=7").json()
    assert d["units_left"] == 50 and d["days_left"] > 0
    assert d["units_for_target_days"] > 0 and d["rand_for_target_days"] > 0


def test_council_dashboard_renders(client):
    r = client.get("/council?area=Soweto")
    assert r.status_code == 200
    html = r.text
    assert "Service delivery report" in html
    assert "SLA compliance" in html and "Download CSV" in html


def test_scorecard_csv_export(client):
    r = client.get("/api/scorecard/export?area=Soweto")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("ref,area,kind")
    j = client.get("/api/scorecard/export?area=Soweto&format=json").json()
    assert "receipts" in j and "scorecard" in j
