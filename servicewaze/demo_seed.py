"""Seed ServiceWaze with a realistic demo neighbourhood.

    python demo_seed.py          # add demo data
    python demo_seed.py --reset  # clear demo data first

Everything inserted here is DEMO DATA and is labelled as such in the app
(source console shows `demo`). It exists so that judges, partners and new
users can see the product working end-to-end on a machine with no municipal
API keys and no internet — the same code paths run with live data in
production; only the numbers change.
"""
from __future__ import annotations

import os
import hashlib
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import grid as grid_mod  # noqa: E402
import receipts  # noqa: E402
import resilience  # noqa: E402
import sources  # noqa: E402

DB = sources.DB_PATH
random.seed(7)

NEIGHBOURS = [
    ("demo-thabo", "Soweto", 1180, 240, 9), ("demo-nomsa", "Soweto", 820, 410, 5),
    ("demo-lerato", "Alexandra", 640, 180, 4), ("demo-sipho", "Soweto", 310, 95, 2),
    ("demo-ayanda", "Cape Town", 900, 260, 7), ("demo-johan", "Pretoria", 520, 60, 3),
    ("demo-fikile", "Durban", 470, 150, 6), ("demo-marie", "Soweto", 1210, 520, 12),
    ("demo-bongani", "Soweto", 250, 70, 1), ("demo-zanele", "Gqeberha", 380, 110, 3),
]

OFFERS = [
    ("water", "200 L borehole water", "Borehole runs off a small solar pump. Bring containers, today 16:00–20:00.", "Soweto", "today 16:00–20:00"),
    ("water", "5000 L JoJo tank — half full", "Street tank behind the church. Please bring your own bottles.", "Soweto", "daily 06:00–20:00"),
    ("power", "Charge phones & power banks", "Generator runs 18:00–21:00. Six plugs, bring your own cable.", "Soweto", "daily 18:00–21:00"),
    ("cold", "Chest freezer space", "Half a shelf free — good for insulin or meat during a long cut.", "Alexandra", "this week"),
    ("food", "Gas stove — cook a pot", "Two-plate gas stove, happy to heat a pot for neighbours.", "Soweto", "evenings"),
    ("ride", "Bakkie to town, Tuesdays", "I drive to town every Tuesday 07:00. Two seats spare.", "Soweto", "Tue 07:00"),
    ("tools", "Plumber — burst pipes", "15 years' experience. I'll look at a burst pipe for free on my street.", "Alexandra", "weekends"),
    ("care", "Check-in on elderly neighbours", "I visit four gogos on my block every morning. Add a name.", "Soweto", "daily 08:00"),
    ("water", "Rainwater tank, 2 500 L", "Filled from the last storm — drinking water only, please.", "Cape Town", "until it runs out"),
    ("power", "Solar — 3 kW with battery", "Can run a fridge or CPAP machine overnight in an emergency.", "Durban", "by arrangement"),
]

NEEDS = [
    ("water", "Drinking water for 5", "No water since 04:00, Zone 3. Two small children.", "Soweto", "today"),
    ("water", "Help filling containers", "Gogo next door cannot carry 25 L bottles.", "Soweto", "today"),
    ("food", "Baby formula — stage 2", "Shop closed during the outage, willing to pay back.", "Alexandra", "today"),
    ("power", "Charge a phone for work", "Need to log in for a shift at 18:00.", "Soweto", "today 15:00–18:00"),
    ("ride", "Lift to clinic Thursday", "Antenatal appointment 09:00, taxi route suspended.", "Soweto", "Thu 08:30"),
]

REPORTS = [
    ("Soweto", "no_water", "No water since 04:00, Pimville Zone 3 — taps dry, nothing on the standpipe.", 40, 6, "open"),
    ("Soweto", "low_pressure", "Pressure very low in Zone 1, second floor has nothing.", 8, 3, "open"),
    ("Soweto", "leak", "Burst pipe at the corner of Vilakazi & Khumalo, running since Tuesday.", 96, 11, "open"),
    ("Alexandra", "no_water", "Whole block dry after the main burst, tanker hasn't come.", 26, 8, "resolved"),
    ("Soweto", "power_out", "Mini-substation tripped again — third time this week.", 5, 4, "resolved"),
    ("Soweto", "route", "Rea Vaya suspended on the Soweto–CBD trunk this morning.", 3, 2, "open"),
    ("Cape Town", "no_water", "Khayelitsha Site B: no supply since yesterday evening.", 30, 7, "open"),
    ("Durban", "low_pressure", "Umlazi low pressure for four days now.", 70, 9, "open"),
]

STOKVELS = [
    ("Pimville Street Tank", "tank", "Soweto", 4500, [
        ("demo-thabo", 800), ("demo-nomsa", 600), ("demo-marie", 1500), ("demo-sipho", 250)]),
    ("Zone 3 Bulk Staples", "bulk_food", "Soweto", 2400, [
        ("demo-nomsa", 400), ("demo-marie", 350), ("demo-bongani", 200)]),
    ("Alex Solar Co-op", "solar", "Alexandra", 18000, [
        ("demo-lerato", 1200), ("demo-fikile", 900)]),
]


def reset():
    con = sqlite3.connect(DB)
    for tbl, col in [("offers", "device"), ("claims", "device"), ("stokvels", "device"),
                     ("stokvel_members", "handle"), ("reports", "reporter"),
                     ("actions", "device"), ("savings", "device"), ("badges", "device"),
                     ("neighbours", "device"), ("profile", "device")]:
        try:
            con.execute(f"DELETE FROM {tbl} WHERE {col} LIKE 'demo-%'")
        except Exception as e:
            print("skip", tbl, e)
    try:
        con.execute("DELETE FROM stokvels WHERE device LIKE 'demo-%'")
        con.execute("DELETE FROM reports WHERE reporter LIKE 'demo%' OR reporter LIKE 'demo-%'")
    except Exception:
        pass
    con.commit()
    con.close()


def seed():
    if "--reset" in sys.argv:
        reset()
    now = datetime.now(timezone.utc)

    # neighbours with history
    for dev, area, xp, ubuntu, streak in NEIGHBOURS:
        resilience.identify(dev, area)
        con = sqlite3.connect(DB)
        con.execute("UPDATE neighbours SET xp=?, ubuntu=?, streak=? WHERE device=?",
                    (xp, ubuntu, streak, hashlib.sha256(dev.encode()).hexdigest()))
        con.commit()
        con.close()
        resilience.save_profile(dev, {
            "people": random.choice([3, 4, 5, 6]), "roof_m2": random.choice([40, 60, 80, 120]),
            "water_l": random.choice([0, 20, 40, 75, 120]), "tank_l": random.choice([0, 0, 2500, 5000]),
            "backup_light": random.choice([0, 1, 1, 1]), "power_bank": random.choice([0, 1, 1]),
            "surge_protect": random.choice([0, 1]), "solar": random.choice([0, 0, 1]),
            "food_days": random.choice([0, 1, 3, 5]), "alt_cooking": random.choice([0, 1, 1]),
            "route_plan": random.choice([0, 1]), "contacts_saved": random.choice([0, 1, 1]),
            "garden": random.choice([0, 0, 1]),
        })
        for action in random.sample(["stored_water", "backup_light", "report", "shared_resource",
                                     "drill", "meter_reading", "helped_elderly"],
                                    k=random.randint(2, 6)):
            resilience.act(dev, action, meta="demo", area=area)
        if random.random() < 0.7:
            resilience.log_saving(dev, random.choice(["water", "power", "food", "other"]),
                                  round(random.uniform(40, 480), 2), "demo history")

    # grid
    for i, (kind, title, detail, area, avail) in enumerate(OFFERS):
        dev = "demo-" + ["thabo", "nomsa", "marie", "lerato", "sipho", "ayanda", "fikile", "bongani"][i % 8]
        you = resilience.identify(dev, area)
        grid_mod.add(kind, "offer", title, detail, area, None, None, dev, you["handle"], avail)
    for i, (kind, title, detail, area, avail) in enumerate(NEEDS):
        dev = "demo-" + ["sipho", "bongani", "lerato", "thabo", "nomsa"][i % 5]
        you = resilience.identify(dev, area)
        grid_mod.add(kind, "need", title, detail, area, None, None, dev, you["handle"], avail)

    # stokvels
    for name, purpose, area, target, members in STOKVELS:
        dev = "demo-" + members[0][0].split("-")[1]
        you = resilience.identify(dev, area)
        out = grid_mod.stokvel_create(name, purpose, area, target, dev, you["handle"])
        for mdev, amt in members:
            h = resilience.identify(mdev, area)["handle"]
            grid_mod.stokvel_contribute(out["id"], amt, mdev, h)

    # reports → receipts
    for area, kind, msg, hours_ago, confirms, status in REPORTS:
        rid = sources.add_report(area, kind, msg, "demo-neighbour", None, None)
        con = sqlite3.connect(DB)
        con.execute("UPDATE reports SET confirms=?, created=? WHERE id=?",
                    (confirms, (now - timedelta(hours=hours_ago)).isoformat(timespec="seconds"), rid))
        con.commit()
        con.close()
        r = receipts.issue(rid, area, kind)
        if status == "resolved":
            receipts.update(rid, "Crew dispatched and supply restored", "demo")
            receipts.resolve(rid, "demo")
        elif hours_ago > 24:
            receipts.update(rid, "Logged with the depot — awaiting crew", "demo")

    print("Seeded demo data:")
    print("  neighbours :", len(NEIGHBOURS))
    print("  grid       :", len(OFFERS), "offers /", len(NEEDS), "requests")
    print("  stokvels   :", len(STOKVELS))
    print("  receipts   :", len(REPORTS))
    print("Run: uvicorn app:app --port 8000")


if __name__ == "__main__":
    seed()
