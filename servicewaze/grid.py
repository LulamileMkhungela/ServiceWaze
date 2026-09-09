"""Ubuntu Grid — the neighbourhood mutual-aid layer, plus community stokvels.

The insight the status apps miss: during a disruption the scarce resource is
not *information*, it is *capacity*. Somebody on your street has a borehole, a
5000 L tank, a generator, a gas stove, a chest freezer, a bakkie, or simply a
spare seat. Most of that capacity is shared already — by word of mouth, inside
a church or a street WhatsApp group — but it is invisible to the people who
need it most, and it never accumulates into anything.

Ubuntu Grid makes it visible, time-boxed and trusted:
  * OFFER  – "I have 200 L of borehole water, today 16:00–20:00"
  * NEED   – "Family of 5 needs drinking water today"
  * CLAIM  – one-tap, creates a private hand-over record, awards Ubuntu Points
  * STOKVEL– neighbours pool money for the thing that ends the outage for good
             (a tank, a solar kit, a bulk food buy) with a visible target

Public infrastructure (standpipes, clinics, feeding schemes, markets) is pulled
live from OpenStreetMap via Overpass — real data, anywhere in South Africa, no
API key.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import net
import sim

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "servicewaze.db")

KINDS = {
    "water": {"icon": "💧", "label": "Water"},
    "power": {"icon": "⚡", "label": "Power & charging"},
    "food": {"icon": "🥫", "label": "Food & cooking"},
    "cold": {"icon": "🧊", "label": "Fridge / freezer space"},
    "ride": {"icon": "🚗", "label": "Lift / transport"},
    "tools": {"icon": "🧰", "label": "Tools & skills"},
    "care": {"icon": "🧓", "label": "Check-in / care"},
    "other": {"icon": "🤝", "label": "Anything else"},
}

STOKVEL_PURPOSES = [
    {"id": "tank", "icon": "🛢️", "label": "JoJo tank & gutter kit", "typical": 4500,
     "why": "2 500 L ends water outages for a street, not just a house."},
    {"id": "solar", "icon": "☀️", "label": "Solar + battery kit", "typical": 18000,
     "why": "Lights, router and phone charging through any outage."},
    {"id": "gas", "icon": "🔥", "label": "Gas stove & cylinder", "typical": 1200,
     "why": "Hot food without electricity, at a fraction of the cost."},
    {"id": "bulk_food", "icon": "🛒", "label": "Bulk staple buy (maize, oil, rice)", "typical": 2400,
     "why": "Buying as a group cuts the staple bill by 15–25%."},
    {"id": "borehole", "icon": "🕳️", "label": "Community borehole", "typical": 45000,
     "why": "The endgame for a ward that is always dry."},
]

OVERPASS = "https://overpass-api.de/api/interpreter"

OSM_QUERIES = {
    "water": '''[out:json][timeout:25];
(
 node["amenity"="drinking_water"](around:{r},{lat},{lon});
 node["man_made"="water_tap"](around:{r},{lat},{lon});
 node["man_made"="water_well"](around:{r},{lat},{lon});
 node["amenity"="water_point"](around:{r},{lat},{lon});
);
out body 30;''',
    "food": '''[out:json][timeout:25];
(
 node["shop"~"supermarket|convenience|greengrocer|bakery|butcher"](around:{r},{lat},{lon});
 node["amenity"="marketplace"](around:{r},{lat},{lon});
 node["amenity"="food_bank"](around:{r},{lat},{lon});
);
out body 30;''',
    "care": '''[out:json][timeout:25];
(
 node["amenity"~"clinic|doctors|hospital|pharmacy|community_centre"](around:{r},{lat},{lon});
);
out body 25;''',
    "power": '''[out:json][timeout:25];
(
 node["amenity"="charging_station"](around:{r},{lat},{lon});
 node["shop"~"hardware|doityourself"](around:{r},{lat},{lon});
);
out body 20;''',
}


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS offers(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, mode TEXT, title TEXT, detail TEXT,
        area TEXT, lat REAL, lon REAL, device TEXT, handle TEXT, availability TEXT,
        status TEXT DEFAULT 'open', claims INTEGER DEFAULT 0, created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS claims(
        id INTEGER PRIMARY KEY AUTOINCREMENT, offer_id INTEGER, device TEXT, handle TEXT, created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS stokvels(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, purpose TEXT, area TEXT,
        target REAL, saved REAL DEFAULT 0, members INTEGER DEFAULT 0,
        device TEXT, created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS stokvel_members(
        stokvel_id INTEGER, device TEXT, handle TEXT, contributed REAL DEFAULT 0,
        joined TEXT, PRIMARY KEY(stokvel_id, device))""")
    con.commit()
    return con


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Public infrastructure from OpenStreetMap (live, keyless, CORS-enabled)
# ---------------------------------------------------------------------------
def _osm(lat, lon, kind: str, radius: int = 4000) -> list[dict]:
    q = OSM_QUERIES[kind].format(r=radius, lat=lat, lon=lon)
    env = net.fetched(OVERPASS, f"OpenStreetMap Overpass ({kind})", ttl=1800,
                      params={"data": q}, sim=lambda: {"elements": [
                          {"id": i, "lat": lat, "lon": lon,
                           "tags": {"name": p["name"], "amenity": kind}}
                          for i, p in enumerate(sim.osm_points(lat, lon, kind))]},
                      timeout=25, channel="server")
    elements = (env.get("data") or {}).get("elements", []) if isinstance(env.get("data"), dict) else []
    out = []
    for e in elements:
        tags = e.get("tags", {}) or {}
        nm = (tags.get("name") or tags.get("operator") or
              tags.get("amenity") or tags.get("shop") or tags.get("man_made") or "Community point")
        d = _haversine(lat, lon, e.get("lat", lat), e.get("lon", lon))
        out.append({
            "id": f"osm-{e.get('id')}",
            "name": str(nm)[:60], "kind": kind,
            "lat": e.get("lat"), "lon": e.get("lon"),
            "distance_m": int(d * 1000),
            "sub": ", ".join([tags.get("amenity", ""), tags.get("shop", ""),
                              tags.get("man_made", "")]).strip(", "),
            "wheelchair": tags.get("wheelchair", ""),
            "opening_hours": tags.get("opening_hours", ""),
            "source": "OpenStreetMap", "tier": env.get("tier"), "live": env.get("live"),
        })
    out.sort(key=lambda x: x["distance_m"])
    return out[:20]


def _haversine(lat1, lon1, lat2, lon2):
    from math import asin, cos, radians, sin, sqrt
    R = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return R * 2 * asin(sqrt(a))


def nearby(lat, lon, kinds: str = "water,food,care", radius: int = 4000) -> dict:
    out = {}
    for k in [x.strip() for x in kinds.split(",") if x.strip()]:
        if k in OSM_QUERIES and lat is not None and lon is not None:
            out[k] = _osm(lat, lon, k, radius)
    return {"points": out, "generated_at": _now()}


# ---------------------------------------------------------------------------
# Offers & needs
# ---------------------------------------------------------------------------
def add(kind: str, mode: str, title: str, detail: str, area: str, lat, lon,
        device: str, handle: str, availability: str = "") -> dict:
    kind = kind if kind in KINDS else "other"
    mode = "need" if mode == "need" else "offer"
    con = _db()
    cur = con.execute("INSERT INTO offers(kind, mode, title, detail, area, lat, lon, device,"
                      " handle, availability, status, claims, created)"
                      " VALUES(?,?,?,?,?,?,?,?,?,?,'open',0,?)",
                      (kind, mode, title[:90], detail[:400], area[:80], lat, lon,
                       device[:64], handle[:60], availability[:80], _now()))
    con.commit()
    rid = cur.lastrowid
    con.close()
    return {"id": rid, "ok": True}


def _rows_to_dicts(rows):
    return [{"id": r[0], "kind": r[1], "mode": r[2], "title": r[3], "detail": r[4],
             "area": r[5], "lat": r[6], "lon": r[7], "handle": r[9],
             "availability": r[10], "status": r[11], "claims": r[12], "created": r[13],
             "icon": KINDS.get(r[1], KINDS["other"])["icon"]} for r in rows]


def listings(area: str = "", lat=None, lon=None, kind: str = "", limit: int = 40) -> dict:
    con = _db()
    q = "SELECT * FROM offers WHERE status='open'"
    args = []
    if kind and kind in KINDS:
        q += " AND kind=?"
        args.append(kind)
    if area:
        # Scope strictly to the area text — a street-level grid is only useful
        # if it is actually your street. National/blank listings still match.
        q += " AND (area LIKE ? OR area IS NULL OR area = '')"
        args.append(f"%{area[:40]}%")
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    rows = con.execute(q, args).fetchall()
    con.close()
    items = _rows_to_dicts(rows)
    if lat is not None and lon is not None:
        for it in items:
            if it["lat"] is not None and it["lon"] is not None:
                it["distance_km"] = round(_haversine(lat, lon, it["lat"], it["lon"]), 2)
        items.sort(key=lambda x: x.get("distance_km", 999))
    offers = [i for i in items if i["mode"] == "offer"]
    needs = [i for i in items if i["mode"] == "need"]
    return {"offers": offers, "needs": needs, "count": len(items)}


def mine(device: str) -> dict:
    con = _db()
    rows = con.execute("SELECT * FROM offers WHERE device=? ORDER BY id DESC LIMIT 40",
                       (device[:64],)).fetchall()
    claimed = con.execute("SELECT offer_id FROM claims WHERE device=?", (device[:64],)).fetchall()
    con.close()
    ids = tuple(c[0] for c in claimed) or (0,)
    con = _db()
    crow = con.execute(f"SELECT * FROM offers WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
    con.close()
    return {"mine": _rows_to_dicts(rows), "claimed": _rows_to_dicts(crow)}


def claim(offer_id: int, device: str, handle: str) -> dict:
    con = _db()
    row = con.execute("SELECT id, device FROM offers WHERE id=?", (offer_id,)).fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "not found"}
    if row[1] == device[:64]:
        con.close()
        return {"ok": False, "error": "you cannot claim your own listing"}
    con.execute("INSERT INTO claims(offer_id, device, handle, created) VALUES(?,?,?,?)",
                (offer_id, device[:64], handle[:60], _now()))
    con.execute("UPDATE offers SET claims = claims + 1 WHERE id=?", (offer_id,))
    con.commit()
    con.close()
    return {"ok": True, "id": offer_id}


def close(offer_id: int, device: str) -> dict:
    con = _db()
    cur = con.execute("UPDATE offers SET status='closed' WHERE id=? AND device=?",
                      (offer_id, device[:64]))
    con.commit()
    ok = cur.rowcount == 1
    con.close()
    return {"ok": ok}


# ---------------------------------------------------------------------------
# Resilience stokvels
# ---------------------------------------------------------------------------
def stokvel_list(area: str = "", limit: int = 20) -> dict:
    con = _db()
    if area:
        rows = con.execute("SELECT * FROM stokvels WHERE area LIKE ? ORDER BY id DESC LIMIT ?",
                           (f"%{area[:40]}%", limit)).fetchall()
    else:
        rows = con.execute("SELECT * FROM stokvels ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    items = []
    for r in rows:
        target = float(r[4] or 0)
        saved = float(r[5] or 0)
        items.append({
            "id": r[0], "name": r[1], "purpose": r[2], "area": r[3],
            "target": target, "saved": round(saved, 2), "members": r[6],
            "progress": round(min(1.0, saved / target), 3) if target else 0.0,
            "remaining": round(max(0.0, target - saved), 2),
            "created": r[8],
        })
    return {"stokvels": items, "purposes": STOKVEL_PURPOSES}


def stokvel_create(name: str, purpose: str, area: str, target: float,
                   device: str, handle: str) -> dict:
    con = _db()
    cur = con.execute("INSERT INTO stokvels(name, purpose, area, target, saved, members, device, created)"
                      " VALUES(?,?,?,?,0,1,?,?)",
                      (name[:60], purpose[:40], area[:80], float(target), device[:64], _now()))
    sid = cur.lastrowid
    con.execute("INSERT OR IGNORE INTO stokvel_members(stokvel_id, device, handle, contributed, joined)"
                " VALUES(?,?,?,0,?)", (sid, device[:64], handle[:60], _now()))
    con.commit()
    con.close()
    return {"id": sid, "ok": True}


def stokvel_contribute(sid: int, amount: float, device: str, handle: str) -> dict:
    con = _db()
    row = con.execute("SELECT members FROM stokvels WHERE id=?", (sid,)).fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "not found"}
    joined = con.execute("SELECT 1 FROM stokvel_members WHERE stokvel_id=? AND device=?",
                         (sid, device[:64])).fetchone()
    if not joined:
        con.execute("INSERT INTO stokvel_members(stokvel_id, device, handle, contributed, joined)"
                    " VALUES(?,?,?,0,?)", (sid, device[:64], handle[:60], _now()))
        con.execute("UPDATE stokvels SET members = members + 1 WHERE id=?", (sid,))
    con.execute("UPDATE stokvels SET saved = saved + ? WHERE id=?", (float(amount), sid))
    con.execute("UPDATE stokvel_members SET contributed = contributed + ? WHERE stokvel_id=? AND device=?",
                (float(amount), sid, device[:64]))
    con.commit()
    row = con.execute("SELECT id,name,purpose,area,target,saved,members FROM stokvels WHERE id=?", (sid,)).fetchone()
    con.close()
    return {"ok": True, "stokvel": {"id": row[0], "name": row[1], "purpose": row[2], "area": row[3],
                                    "target": row[4], "saved": round(row[5], 2), "members": row[6]}}


def stokvel_detail(sid: int) -> dict:
    con = _db()
    row = con.execute("SELECT * FROM stokvels WHERE id=?", (sid,)).fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "not found"}
    mem = con.execute("SELECT handle, contributed, joined FROM stokvel_members WHERE stokvel_id=?"
                      " ORDER BY contributed DESC", (sid,)).fetchall()
    con.close()
    target = float(row[4] or 0)
    saved = float(row[5] or 0)
    return {"ok": True, "stokvel": {
        "id": row[0], "name": row[1], "purpose": row[2], "area": row[3], "target": target,
        "saved": round(saved, 2), "members": row[6],
        "progress": round(min(1.0, saved / target), 3) if target else 0.0,
        "members_list": [{"handle": m[0], "contributed": round(m[1], 2), "joined": m[2]} for m in mem],
    }}


def stats() -> dict:
    con = _db()
    offers = con.execute("SELECT COUNT(*) FROM offers WHERE mode='offer' AND status='open'").fetchone()[0]
    needs = con.execute("SELECT COUNT(*) FROM offers WHERE mode='need' AND status='open'").fetchone()[0]
    claimed = con.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    pots = con.execute("SELECT COUNT(*), COALESCE(SUM(saved),0) FROM stokvels").fetchone()
    con.close()
    return {"open_offers": offers, "open_needs": needs, "hand_overs": claimed,
            "stokvels": pots[0], "stokvel_rand": round(pots[1] or 0, 2)}


# ---------------------------------------------------------------------------
# Climate-smart small business: the local resilience economy
#
# A disruption is also an economy. The plumber who fixes the burst pipe, the
# spaza with a generator, the installer putting up JoJo tanks, the woman who
# sells ice during load-shedding — these are the businesses that keep a
# township running, and they are invisible online.
#
# Two surfaces:
#   * PROVIDERS  — a verified directory of resilience trades and services
#   * OPEN BOARD — "we're open / closed / generator on right now", which is
#                  simultaneously food access for residents and footfall for
#                  the business. Entries expire after 24 h so the board never
#                  lies.
# ---------------------------------------------------------------------------
BUSINESS_CATEGORIES = {
    "water": {"icon": "🛢️", "label": "Water: tanks, boreholes, delivery"},
    "solar": {"icon": "☀️", "label": "Solar, batteries, inverters"},
    "gas": {"icon": "🔥", "label": "Gas, stoves, cylinders"},
    "plumbing": {"icon": "🔧", "label": "Plumbing & leaks"},
    "electrical": {"icon": "⚡", "label": "Electrical & wiring"},
    "food": {"icon": "🥫", "label": "Food: spaza, bakery, cooked food"},
    "cold": {"icon": "🧊", "label": "Cold storage & ice"},
    "transport": {"icon": "🚐", "label": "Transport & delivery"},
    "other": {"icon": "🏪", "label": "Other services"},
}

BUSINESS_CHECKLIST = {
    "title": "Business continuity in 6 moves",
    "steps": [
        "Know your interruption windows: log the last 90 days of outages for your block (ServiceWaze does this for you).",
        "Protect the till: a small UPS keeps a card machine, router and light alive for 4 hours.",
        "Protect the stock: a cooler box and a frozen bottle buys 6 hours for perishables.",
        "Post your status: 'open on generator' on the Open board brings customers through the door.",
        "Have one alternative supplier for water and one for power, tested before you need them.",
        "Insure and document: photograph stock before and after a long outage — you will need it for a claim.",
    ],
}

OPEN_TTL_HOURS = 24


def _db_business(con):
    con.execute("""CREATE TABLE IF NOT EXISTS businesses(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT, area TEXT,
        lat REAL, lon REAL, contact TEXT, detail TEXT, verified INTEGER DEFAULT 0,
        device TEXT, created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS open_board(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, area TEXT, status TEXT,
        note TEXT, device TEXT, created TEXT)""")
    con.commit()


def business_list(area: str = "", category: str = "", limit: int = 40) -> dict:
    con = _db()
    _db_business(con)
    q = "SELECT id,name,category,area,lat,lon,contact,detail,verified FROM businesses"
    args = []
    where = []
    if area:
        where.append("area LIKE ?")
        args.append(f"%{area[:40]}%")
    if category and category in BUSINESS_CATEGORIES:
        where.append("category=?")
        args.append(category)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY verified DESC, id DESC LIMIT ?"
    args.append(limit)
    rows = con.execute(q, args).fetchall()
    con.close()
    return {"businesses": [
        {"id": r[0], "name": r[1], "category": r[2], "area": r[3], "lat": r[4], "lon": r[5],
         "contact": r[6], "detail": r[7], "verified": r[8],
         "icon": BUSINESS_CATEGORIES.get(r[2], BUSINESS_CATEGORIES["other"])["icon"]}
        for r in rows],
        "categories": BUSINESS_CATEGORIES, "checklist": BUSINESS_CHECKLIST}


def business_add(name, category, area, contact, detail, lat, lon, device) -> dict:
    con = _db()
    _db_business(con)
    cur = con.execute("INSERT INTO businesses(name, category, area, lat, lon, contact, detail,"
                      " verified, device, created) VALUES(?,?,?,?,?,?,?,0,?,?)",
                      (name[:80], category if category in BUSINESS_CATEGORIES else "other",
                       area[:80], lat, lon, contact[:60], detail[:300], device[:64], _now()))
    con.commit()
    rid = cur.lastrowid
    con.close()
    return {"id": rid, "ok": True}


def business_verify(bid: int, device: str) -> dict:
    """Neighbour verification — one verified-by count per device, ever."""
    con = _db()
    _db_business(con)
    con.execute("""CREATE TABLE IF NOT EXISTS business_verifiers(
        business_id INTEGER, device TEXT, created TEXT, PRIMARY KEY(business_id, device))""")
    cur = con.execute("INSERT OR IGNORE INTO business_verifiers(business_id, device, created)"
                      " VALUES(?,?,?)", (bid, device[:64], _now()))
    con.commit()
    if cur.rowcount:
        con.execute("UPDATE businesses SET verified = verified + 1 WHERE id=?", (bid,))
        con.commit()
    row = con.execute("SELECT verified FROM businesses WHERE id=?", (bid,)).fetchone()
    con.close()
    return {"ok": True, "verified": row[0] if row else 0}


def open_board(area: str = "", limit: int = 30) -> dict:
    """Who is open right now, and who had to close. Entries expire in 24 h."""
    con = _db()
    _db_business(con)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=OPEN_TTL_HOURS)).isoformat(timespec="seconds")
    con.execute("DELETE FROM open_board WHERE created < ?", (cutoff,))
    con.commit()
    if area:
        rows = con.execute("SELECT id,name,area,status,note,created FROM open_board"
                           " WHERE area LIKE ? ORDER BY id DESC LIMIT ?",
                           (f"%{area[:40]}%", limit)).fetchall()
    else:
        rows = con.execute("SELECT id,name,area,status,note,created FROM open_board"
                           " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    items = [{"id": r[0], "name": r[1], "area": r[2], "status": r[3], "note": r[4],
              "created": r[5]} for r in rows]
    return {"board": items,
            "open": [i for i in items if i["status"] == "open"],
            "closed": [i for i in items if i["status"] == "closed"],
            "ttl_hours": OPEN_TTL_HOURS}


def post_open(name, area, status, note, device) -> dict:
    con = _db()
    _db_business(con)
    con.execute("INSERT INTO open_board(name, area, status, note, device, created)"
                " VALUES(?,?,?,?,?,?)",
                (name[:80], area[:80], "open" if status == "open" else "closed",
                 note[:200], device[:64], _now()))
    con.commit()
    con.close()
    return {"ok": True}
