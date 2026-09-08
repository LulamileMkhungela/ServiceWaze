"""Resilience Score, Ubuntu Points, badges, challenges and the savings ledger.

Why this exists
---------------
Status apps tell you what broke. ServiceWaze has to change behaviour *before*
something breaks — and behaviour change is a game-design problem, not a data
problem. So every useful action in the app is worth something:

    prepare  →  the app tells you what to do before impact
    act      →  you do it, tap "done", earn XP
    help     →  you share / confirm / report, earn Ubuntu Points
    save     →  the app converts the action into rands saved, on the record

Identity is device-based and pseudonymous: no email, no phone, no name
required (POPIA-friendly). A device ID is hashed server-side; the user gets a
friendly handle like "Neighbour uMkhozi". Optional password-less upgrade can
sync the same handle across devices later.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "servicewaze.db")

LEVELS = [
    (0, "Seedling", "🌱"), (120, "Sprout", "🌿"), (360, "Umthi", "🌳"),
    (800, "Baobab", "🌴"), (1600, "Ubuntu Legend", "🦁"),
]

XP_TABLE = {
    "stored_water": 40, "backup_light": 25, "power_bank": 20, "surge_protect": 15,
    "emergency_contacts": 25, "food_stock": 35, "alt_cooking": 20,
    "route_plan": 20, "shared_resource": 60, "offered_ride": 40,
    "report": 30, "confirm": 15, "resolved_report": 50,
    "meter_reading": 20, "savings_logged": 15, "drill": 45,
    "stokvel_join": 30, "stokvel_contribute": 25, "checkin": 5,
    "helped_elderly": 70, "garden_plant": 35, "harvest_water": 30,
}

BADGES = {
    "water_wise": {"icon": "💧", "name": "Water Wise", "how": "Store 3 days of water for your household"},
    "first_responder": {"icon": "🚨", "name": "First Responder", "how": "File 5 verified community reports"},
    "grid_guardian": {"icon": "🤝", "name": "Grid Guardian", "how": "Share a resource 5 times"},
    "stokvel_star": {"icon": "🐷", "name": "Stokvel Star", "how": "Join and contribute to a resilience stokvel"},
    "night_owl": {"icon": "🦉", "name": "Night Owl", "how": "Report an outage between 22:00 and 04:00"},
    "money_mindful": {"icon": "💸", "name": "Money Mindful", "how": "Log R200 or more in household savings"},
    "green_thumb": {"icon": "🥬", "name": "Green Thumb", "how": "Start a food garden or water-harvesting setup"},
    "street_captain": {"icon": "🧭", "name": "Street Captain", "how": "Reach 800 XP"},
    "ubuntu_legend": {"icon": "🦁", "name": "Ubuntu Legend", "how": "Reach 1600 XP"},
}

WEEKLY_CHALLENGES = [
    {"id": "water", "icon": "💧", "title": "Store 40 litres", "detail": "Fill bottles, buckets or a JoJo before the next interruption window.", "xp": 60},
    {"id": "share", "icon": "🤝", "title": "Share one thing", "detail": "Offer water, power, a fridge shelf or a seat to a neighbour.", "xp": 60},
    {"id": "meter", "icon": "🔢", "title": "Log your meter", "detail": "Record your electricity or water reading to unlock leak and usage insights.", "xp": 40},
    {"id": "drill", "icon": "⏱️", "title": "Run a 5-minute drill", "detail": "Practise your blackout/borehole plan with the household.", "xp": 90},
    {"id": "elderly", "icon": "🧓", "title": "Check on someone", "detail": "Check on an elderly or sick neighbour and log it.", "xp": 80},
    {"id": "route", "icon": "🚌", "title": "Plan route B", "detail": "Save an alternative route for your most important weekly trip.", "xp": 50},
    {"id": "food", "icon": "🥫", "title": "Stock 3 days of food", "detail": "Non-perishables that need no cooking or refrigeration.", "xp": 70},
]


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS neighbours(
        device TEXT PRIMARY KEY, handle TEXT, area TEXT, lang TEXT,
        xp INTEGER DEFAULT 0, ubuntu INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0, last_day TEXT, created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS profile(
        device TEXT PRIMARY KEY, people INTEGER DEFAULT 4, roof_m2 REAL DEFAULT 60,
        water_l REAL DEFAULT 0, backup_light INTEGER DEFAULT 0, power_bank INTEGER DEFAULT 0,
        surge_protect INTEGER DEFAULT 0, solar INTEGER DEFAULT 0, food_days INTEGER DEFAULT 0,
        alt_cooking INTEGER DEFAULT 0, route_plan INTEGER DEFAULT 0, contacts_saved INTEGER DEFAULT 0,
        garden INTEGER DEFAULT 0, tank_l REAL DEFAULT 0, updated TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS actions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, device TEXT, action TEXT, xp INTEGER,
        meta TEXT, created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS savings(
        id INTEGER PRIMARY KEY AUTOINCREMENT, device TEXT, kind TEXT,
        amount REAL, note TEXT, created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS badges(
        device TEXT, code TEXT, created TEXT, PRIMARY KEY(device, code))""")
    con.commit()
    return con


HANDLE_ADjectives = ["Brave", "Swift", "Kind", "Bright", "Calm", "Bold", "Wise", "Steady"]
HANDLE_BIRDS = ["uMkhozi", "LeSedi", "iNdlovu", "Pelo", "Themba", "Naledi", "uKhozi", "Sizwe"]


def _handle(device: str) -> str:
    h = int(hashlib.sha256(device.encode()).hexdigest(), 16)
    return f"Neighbour {HANDLE_ADjectives[h % len(HANDLE_ADjectives)]} {HANDLE_BIRDS[(h // 7) % len(HANDLE_BIRDS)]}"


def identify(device: str, area: str = "", lang: str = "en") -> dict:
    dev = (device or "").strip()[:64] or "anon"
    key = hashlib.sha256(dev.encode()).hexdigest()
    con = _db()
    row = con.execute("SELECT device, handle, area, xp, ubuntu, streak FROM neighbours WHERE device=?", (key,)).fetchone()
    if not row:
        handle = _handle(dev)
        con.execute("INSERT INTO neighbours(device, handle, area, lang, xp, ubuntu, streak, last_day, created)"
                    " VALUES(?,?,?,?,0,0,0,'',?)",
                    (key, handle, area[:80], lang, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        con.commit()
        row = (key, handle, area, 0, 0, 0)
    elif area and row[2] != area[:80]:
        con.execute("UPDATE neighbours SET area=? WHERE device=?", (area[:80], key))
        con.commit()
    con.close()
    return {"device": dev, "handle": row[1], "area": row[2], "xp": row[3],
            "ubuntu": row[4], "streak": row[5]}


get_profile_sql = "SELECT people, roof_m2, water_l, backup_light, power_bank, surge_protect, solar, food_days, alt_cooking, route_plan, contacts_saved, garden, tank_l FROM profile WHERE device=?"


def _devkey(device: str) -> str:
    return hashlib.sha256((device or "anon").encode()).hexdigest()


def get_profile(device: str) -> dict:
    con = _db()
    row = con.execute(get_profile_sql, (_devkey(device),)).fetchone()
    con.close()
    keys = ["people", "roof_m2", "water_l", "backup_light", "power_bank", "surge_protect",
            "solar", "food_days", "alt_cooking", "route_plan", "contacts_saved", "garden", "tank_l"]
    return dict(zip(keys, row)) if row else dict(zip(keys, [4, 60, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]))


def save_profile(device: str, p: dict) -> dict:
    keys = ["people", "roof_m2", "water_l", "backup_light", "power_bank", "surge_protect",
            "solar", "food_days", "alt_cooking", "route_plan", "contacts_saved", "garden", "tank_l"]
    cur = get_profile(device)
    for k in keys:
        if k in p and p[k] is not None:
            try:
                cur[k] = type(cur[k])(p[k]) if not isinstance(cur[k], bool) else int(bool(p[k]))
            except Exception:
                pass
    con = _db()
    con.execute("INSERT OR REPLACE INTO profile(device, people, roof_m2, water_l, backup_light,"
                " power_bank, surge_protect, solar, food_days, alt_cooking, route_plan,"
                " contacts_saved, garden, tank_l, updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_devkey(device), cur["people"], cur["roof_m2"], cur["water_l"], int(cur["backup_light"]),
                 int(cur["power_bank"]), int(cur["surge_protect"]), int(cur["solar"]), int(cur["food_days"]),
                 int(cur["alt_cooking"]), int(cur["route_plan"]), int(cur["contacts_saved"]),
                 int(cur["garden"]), cur["tank_l"], datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()
    con.close()
    return cur


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------
def score(device: str) -> dict:
    """0–100 Household Resilience Score with a transparent component breakdown."""
    p = get_profile(device)
    people = max(1, int(p["people"] or 1))
    stored = float(p["water_l"] or 0) + float(p["tank_l"] or 0)
    per_person = stored / people
    water = min(30.0, (per_person / 75.0) * 30.0)  # 25 L/person/day × 3 days
    power = (6.0 * int(p["backup_light"]) + 5.0 * int(p["power_bank"]) +
             4.0 * int(p["surge_protect"]) + 5.0 * int(p["solar"]))
    food = min(15.0, (float(p["food_days"] or 0) / 3.0) * 10.0 + 5.0 * int(p["alt_cooking"]))
    transport = 10.0 * int(p["route_plan"])
    safety = 4.0 * int(p["contacts_saved"]) + 3.0 * int(p["garden"])
    u = identify(device)
    community = min(15.0, (u["ubuntu"] / 200.0) * 15.0)
    total = round(water + power + food + transport + safety + community, 1)
    band = ("critical" if total < 30 else "building" if total < 55 else
            "strong" if total < 78 else "excellent")
    return {
        "score": total, "band": band,
        "components": [
            {"key": "water", "label": "Water stored", "value": round(water, 1), "max": 30,
             "detail": f"{per_person:.0f} L per person (target 75 L = 3 days)"},
            {"key": "power", "label": "Backup power & light", "value": round(power, 1), "max": 20,
             "detail": "Light, power bank, surge protection, solar/generator"},
            {"key": "food", "label": "Food buffer", "value": round(food, 1), "max": 15,
             "detail": f"{p['food_days']} days of food + alternative cooking"},
            {"key": "transport", "label": "Route B planned", "value": round(transport, 1), "max": 10,
             "detail": "Alternative route saved for essential trips"},
            {"key": "safety", "label": "Contacts & garden", "value": round(safety, 1), "max": 7,
             "detail": "Emergency numbers saved, food garden"},
            {"key": "community", "label": "Ubuntu (helping others)", "value": round(community, 1), "max": 15,
             "detail": f"{u['ubuntu']} Ubuntu Points earned by helping neighbours"},
        ],
        "stored_litres": round(stored, 1), "litres_per_person": round(per_person, 1),
        "people": people,
    }


def level(xp: int) -> dict:
    idx = 0
    for i, (threshold, _, _) in enumerate(LEVELS):
        if xp >= threshold:
            idx = i
    name, icon = LEVELS[idx][1], LEVELS[idx][2]
    nxt = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None
    return {"xp": xp, "level": idx + 1, "name": name, "icon": icon,
            "next_at": nxt, "to_next": (nxt - xp) if nxt else 0,
            "progress": 0 if not nxt else max(0.0, min(1.0, (xp - LEVELS[idx][0]) / max(1, nxt - LEVELS[idx][0])))}


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def act(device: str, action: str, meta: str = "", area: str = "") -> dict:
    xp = int(XP_TABLE.get(action, 10))
    ubuntu = xp if action in ("shared_resource", "offered_ride", "confirm", "resolved_report",
                              "helped_elderly", "report") else 0
    key = _devkey(device)
    con = _db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("INSERT INTO actions(device, action, xp, meta, created) VALUES(?,?,?,?,?)",
                (key, action, xp, meta[:300], now))
    con.execute("UPDATE neighbours SET xp = xp + ?, ubuntu = ubuntu + ? WHERE device=?", (xp, ubuntu, key))
    if area:
        con.execute("UPDATE neighbours SET area=? WHERE device=?", (area[:80], key))
    con.commit()
    con.close()
    _check_badges(device)
    _check_streak(device)
    return {"xp_earned": xp, "ubuntu_earned": ubuntu, "action": action, **level(identify(device)["xp"])}


def _check_streak(device: str):
    key = _devkey(device)
    today = datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d")
    con = _db()
    row = con.execute("SELECT last_day, streak FROM neighbours WHERE device=?", (key,)).fetchone()
    if not row:
        con.close()
        return
    last, streak = row
    if last == today:
        con.close()
        return
    yest = (datetime.now(timezone(timedelta(hours=2))) - timedelta(days=1)).strftime("%Y-%m-%d")
    streak = (streak + 1) if last == yest else 1
    con.execute("UPDATE neighbours SET last_day=?, streak=? WHERE device=?", (today, streak, key))
    con.commit()
    con.close()


def _check_badges(device: str):
    key = _devkey(device)
    con = _db()
    u = con.execute("SELECT xp, ubuntu FROM neighbours WHERE device=?", (key,)).fetchone() or (0, 0)
    p = get_profile(device)
    counts = {a: c for a, c in con.execute(
        "SELECT action, COUNT(*) FROM actions WHERE device=? GROUP BY action", (key,)).fetchall()}
    saved = con.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE device=?", (key,)).fetchone()[0]
    earned = {
        "water_wise": (float(p["water_l"]) + float(p["tank_l"])) >= 75 * max(1, p["people"]),
        "first_responder": counts.get("report", 0) >= 5,
        "grid_guardian": counts.get("shared_resource", 0) >= 5,
        "stokvel_star": counts.get("stokvel_contribute", 0) >= 1,
        "night_owl": _night_report(con, key),
        "money_mindful": saved >= 200,
        "green_thumb": bool(p["garden"]),
        "street_captain": u[0] >= 800,
        "ubuntu_legend": u[0] >= 1600,
    }
    new = []
    for code, ok in earned.items():
        if not ok:
            continue
        cur = con.execute("INSERT OR IGNORE INTO badges(device, code, created) VALUES(?,?,?)",
                          (key, code, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        if cur.rowcount:
            new.append(code)
    con.commit()
    con.close()
    return new


def _night_report(con, key) -> bool:
    row = con.execute("SELECT created FROM actions WHERE device=? AND action='report'", (key,)).fetchall()
    for (ts,) in row:
        try:
            h = datetime.fromisoformat(ts).astimezone(timezone(timedelta(hours=2))).hour
            if h >= 22 or h < 4:
                return True
        except Exception:
            continue
    return False


def badges(device: str) -> list[dict]:
    key = _devkey(device)
    con = _db()
    rows = con.execute("SELECT code, created FROM badges WHERE device=?", (key,)).fetchall()
    con.close()
    out = []
    for code, created in rows:
        b = BADGES.get(code, {"icon": "🏅", "name": code, "how": ""})
        out.append({"code": code, **b, "earned": created})
    missing = [{"code": c, **b, "earned": None} for c, b in BADGES.items()
               if c not in {r[0] for r in rows}]
    return out + missing


def challenges(device: str) -> dict:
    now = datetime.now(timezone(timedelta(hours=2)))
    week = now.isocalendar()[1]
    picks = [WEEKLY_CHALLENGES[(week + i) % len(WEEKLY_CHALLENGES)] for i in range(3)]
    key = _devkey(device)
    con = _db()
    done = {a for (a,) in con.execute(
        "SELECT meta FROM actions WHERE device=? AND created > ?",
        (key, (now - timedelta(days=7)).isoformat())).fetchall()}
    con.close()
    for c in picks:
        c = dict(c)
        c["done"] = c["id"] in done
    return {"week": week, "challenges": picks,
            "resets_in_days": 7 - now.weekday()}


def complete_challenge(device: str, cid: str) -> dict:
    return act(device, "drill", meta=cid, area="")


# ---------------------------------------------------------------------------
# Savings ledger
# ---------------------------------------------------------------------------
def log_saving(device: str, kind: str, amount: float, note: str = "") -> dict:
    key = _devkey(device)
    con = _db()
    con.execute("INSERT INTO savings(device, kind, amount, note, created) VALUES(?,?,?,?,?)",
                (key, kind[:40], float(amount), note[:200],
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()
    con.close()
    act(device, "savings_logged", f"{kind}:{amount}")
    return savings(device)


def savings(device: str) -> dict:
    key = _devkey(device)
    con = _db()
    rows = con.execute("SELECT kind, amount, note, created FROM savings WHERE device=? "
                       "ORDER BY id DESC LIMIT 50", (key,)).fetchall()
    by_kind = {}
    for kind, amount, note, created in rows:
        by_kind[kind] = by_kind.get(kind, 0.0) + amount
    con.close()
    total = sum(v for v in by_kind.values())
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    this_month = sum(a for k, a, n, c in rows if str(c).startswith(month))
    return {"total": round(total, 2), "this_month": round(this_month, 2),
            "by_kind": {k: round(v, 2) for k, v in by_kind.items()},
            "entries": [{"kind": k, "amount": round(a, 2), "note": n, "created": c}
                        for k, a, n, c in rows[:20]]}


# ---------------------------------------------------------------------------
# Leaderboard (community sport, not vanity: teams are places)
# ---------------------------------------------------------------------------
def leaderboard(area: str = "", limit: int = 12) -> dict:
    con = _db()
    rows = con.execute("SELECT handle, area, xp, ubuntu, streak FROM neighbours").fetchall()
    con.close()
    people = [{"handle": h, "area": a or "—", "xp": x, "ubuntu": ub, "streak": st}
              for h, a, x, ub, st in rows]
    people.sort(key=lambda r: (-r["xp"], r["handle"]))
    areas = {}
    for p in people:
        d = areas.setdefault(p["area"], {"area": p["area"], "members": 0, "xp": 0, "ubuntu": 0})
        d["members"] += 1
        d["xp"] += p["xp"]
        d["ubuntu"] += p["ubuntu"]
    area_rows = sorted(areas.values(), key=lambda r: -r["xp"])
    return {
        "neighbours": people[:limit],
        "areas": area_rows[:limit],
        "totals": {"neighbours": len(people), "areas": len(area_rows),
                   "xp": sum(p["xp"] for p in people),
                   "ubuntu": sum(p["ubuntu"] for p in people)},
        "you_area": area,
    }


def summary(device: str, area: str = "") -> dict:
    u = identify(device, area)
    return {"you": u, "level": level(u["xp"]), "score": score(device),
            "badges": badges(device), "savings": savings(device)}
