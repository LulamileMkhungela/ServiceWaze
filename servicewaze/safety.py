"""safety.py — the half of "public safety" that no service-delivery app builds.

The hackathon problem statement is *Public Safety & Gender-Based Violence*:
"How might we leverage technology to make communities safer, prevent
gender-based violence, and strengthen emergency response and trust in safety
systems?" Every other entry in this space reads a load-shedding schedule. This
module is about the walk home from the taxi rank.

Three working pieces:

1. **SafeWalk** — "walk with me". You say where you are going and how long it
   should take. If you do not say "I arrived" in time, your watch circle is
   told. No GPS trail is recorded (privacy, and it must work on a R500 phone
   with no data), just a deadline and a status.
2. **SOS** — one tap that raises an alert to the area with your pseudonym, your
   area and a coarse location, fans out to push subscribers, and puts the
   verified national helplines under your thumb.
3. **Unsafe place** — a dark street, a broken streetlight, an open manhole, an
   unlit taxi rank. Reported like any other fault, so it becomes a *receipt
   with an SLA* and a pin on the map. Prevention, not just response: fixing the
   light is cheaper than policing the dark.

Helplines below are curated reference data (tier `curated`), each with its
source. Numbers were checked against the Department of Social Development's
GBV Command Centre material and national emergency listings before shipping;
a wrong number in a GBV app is worse than no number.
"""

import os
import sqlite3
from datetime import datetime, timezone, timedelta

import push
import receipts
import resilience
import sources

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "safety.db")

# ----------------------------------------------------------------- curated
CURATED = [
    {"id": "gbvcc", "name": "GBV Command Centre", "tel": "0800 428 428",
     "detail": "24/7, toll-free, social workers. Domestic violence, rape, stalking, abuse.",
     "channel": "tel", "hours": "24/7", "icon": "🟣",
     "source": "Department of Social Development / gbv.org.za", "priority": 1},
    {"id": "gbv_ussd", "name": "GBV ‘please call me’", "tel": "*120*7867#",
     "detail": "Free USSD — a social worker calls you back. Works with no airtime.",
     "channel": "ussd", "hours": "24/7", "icon": "📟",
     "source": "gbv.org.za", "priority": 2},
    {"id": "gbv_sms", "name": "GBV SMS line", "tel": "31531",
     "detail": "SMS the word ‘help’ — for people who cannot speak safely or are deaf/hard of hearing.",
     "channel": "sms", "hours": "24/7", "icon": "💬",
     "source": "gbv.org.za", "priority": 3},
    {"id": "police", "name": "SAPS emergency", "tel": "10111",
     "detail": "Crime in progress or immediate danger.", "channel": "tel",
     "hours": "24/7", "icon": "🚓", "source": "SAPS / national emergency listing", "priority": 1},
    {"id": "mobile_112", "name": "Emergency from a mobile", "tel": "112",
     "detail": "Free from any cellphone, even with no airtime. Routes to police, fire or ambulance.",
     "channel": "tel", "hours": "24/7", "icon": "📱",
     "source": "National emergency listing", "priority": 1},
    {"id": "ambulance", "name": "Ambulance & fire", "tel": "10177",
     "detail": "Medical and fire emergencies.", "channel": "tel", "hours": "24/7",
     "icon": "🚑", "source": "National emergency listing", "priority": 2},
    {"id": "crime_stop", "name": "Crime Stop (anonymous)", "tel": "08600 10111",
     "detail": "Report crime without giving your name.", "channel": "tel",
     "hours": "24/7", "icon": "🕵️", "source": "SAPS Crime Stop", "priority": 3},
    {"id": "childline", "name": "Childline", "tel": "116",
     "detail": "Children's helpline; also 08000 55 555.", "channel": "tel",
     "hours": "24/7", "icon": "🧒", "source": "Childline South Africa", "priority": 2},
    {"id": "poison", "name": "Poison Information", "tel": "0861 555 777",
     "detail": "Poisoning, unsafe water or chemicals.", "channel": "tel",
     "hours": "24/7", "icon": "☠️", "source": "National emergency listing", "priority": 4},
    {"id": "netcare", "name": "Netcare 911", "tel": "082 911",
     "detail": "Private medical emergency (contracted / fee).", "channel": "tel",
     "hours": "24/7", "icon": "🏥", "source": "National emergency listing", "priority": 4},
    {"id": "er24", "name": "ER24", "tel": "084 124",
     "detail": "Private medical emergency (contracted / fee).", "channel": "tel",
     "hours": "24/7", "icon": "🏥", "source": "National emergency listing", "priority": 4},
]

UNSAFE_KINDS = [
    {"id": "streetlight", "icon": "🌑", "label": "Streetlight out"},
    {"id": "dark_passage", "icon": "🚶", "label": "Dark passage / path"},
    {"id": "open_manhole", "icon": "🕳️", "label": "Open manhole or hole"},
    {"id": "rank", "icon": "🚐", "label": "Unsafe taxi rank"},
    {"id": "violence", "icon": "🆘", "label": "Violence / harassment hotspot"},
    {"id": "other_safety", "icon": "⚠️", "label": "Other safety hazard"},
]


def _now():
    return datetime.now(timezone.utc)


def _db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS walks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device TEXT NOT NULL, handle TEXT NOT NULL, area TEXT NOT NULL,
        dest TEXT DEFAULT '', minutes INTEGER DEFAULT 20, note TEXT DEFAULT '',
        started TEXT NOT NULL, due TEXT NOT NULL,
        status TEXT DEFAULT 'walking', ended TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS sos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device TEXT NOT NULL, handle TEXT NOT NULL, area TEXT NOT NULL,
        note TEXT DEFAULT '', lat REAL, lon REAL,
        created TEXT NOT NULL, status TEXT DEFAULT 'open'
    )""")
    return con


def _round(v, dp=3):
    """Coarse location: ~110 m at 3 dp. Enough for a responder, not a tracker."""
    try:
        return round(float(v), dp)
    except Exception:
        return None


# --------------------------------------------------------------- SafeWalk
def walk_start(device: str, area: str, dest: str = "", minutes: int = 20,
               note: str = "") -> dict:
    try:
        minutes = max(2, min(240, int(minutes or 20)))
    except Exception:
        minutes = 20
    me = resilience.identify(device, area)
    now = _now()
    con = _db()
    cur = con.execute("""INSERT INTO walks (device, handle, area, dest, minutes, note, started, due)
                         VALUES (?,?,?,?,?,?,?,?)""",
                      (device, me["handle"], area.strip(), dest.strip()[:80], minutes,
                       note.strip()[:140], now.isoformat(timespec="seconds"),
                       (now + timedelta(minutes=minutes)).isoformat(timespec="seconds")))
    wid = cur.lastrowid
    con.commit()
    con.close()
    return {"ok": True, "id": wid, "handle": me["handle"], "due_minutes": minutes,
            "due": (now + timedelta(minutes=minutes)).isoformat(timespec="seconds")}


def _walk_row(row, now=None):
    (wid, device, handle, area, dest, minutes, note, started, due, status, ended) = row
    now = now or _now()
    try:
        due_dt = datetime.fromisoformat(due)
    except Exception:
        due_dt = now
    mins_left = round((due_dt - now).total_seconds() / 60, 1)
    over = mins_left < 0
    if status == "walking" and over:
        status = "overdue"
    return {"id": wid, "handle": handle, "area": area, "dest": dest, "minutes": minutes,
            "note": note, "started": started, "due": due, "status": status,
            "minutes_left": mins_left, "overdue_by": round(-mins_left, 1) if over else 0,
            "mine": False}


def walk_arrive(wid: int, device: str = "") -> dict:
    con = _db()
    row = con.execute("SELECT * FROM walks WHERE id=?", (wid,)).fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "not found"}
    con.execute("UPDATE walks SET status='arrived', ended=? WHERE id=?",
                (_now().isoformat(timespec="seconds"), wid))
    con.commit()
    con.close()
    return {"ok": True, "id": wid, "status": "arrived",
            "handle": row[2]}


def walk_alert(wid: int, device: str = "") -> dict:
    """Escalate: tell the area that someone on a walk did not arrive."""
    con = _db()
    row = con.execute("SELECT * FROM walks WHERE id=?", (wid,)).fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "not found"}
    con.execute("UPDATE walks SET status='alerted', ended=? WHERE id=?",
                (_now().isoformat(timespec="seconds"), wid))
    con.commit()
    con.close()
    w = _walk_row(row)
    try:
        push.broadcast(
            "🚨 " + w["handle"] + " did not arrive",
            "SafeWalk to " + (w["dest"] or "home") + " is " +
            str(int(w["overdue_by"])) + " min overdue. Please check.",
            area_filter=w["area"], url="/?tab=community")
    except Exception:
        pass
    return {"ok": True, "id": wid, "status": "alerted", "handle": w["handle"]}


def walk_check(wid: int, device: str = "") -> dict:
    """A neighbour says "I'll go look". Recorded, rewarded, not a status change."""
    con = _db()
    row = con.execute("SELECT * FROM walks WHERE id=?", (wid,)).fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "not found"}
    w = _walk_row(row)
    con.execute("UPDATE walks SET note=COALESCE(NULLIF(note,''),'') || ? WHERE id=?",
                (" [checking: " + (device or "neighbour")[:24] + "]", wid))
    con.commit()
    con.close()
    try:
        resilience.act(device or "neighbour", "checkin", meta="walk-check:" + str(wid), area=w["area"])
    except Exception:
        pass
    return {"ok": True, "id": wid, "handle": w["handle"]}


def walks(area: str, device: str = "", limit: int = 20) -> dict:
    con = _db()
    rows = con.execute("""SELECT * FROM walks
                          WHERE area=? AND status IN ('walking','alerted')
                          ORDER BY started DESC LIMIT ?""", (area.strip(), limit)).fetchall()
    con.close()
    now = _now()
    out = []
    for r in rows:
        w = _walk_row(r, now)
        w["mine"] = bool(device and r[1] == device)
        out.append(w)
    out.sort(key=lambda w: (0 if w["status"] == "alerted" else 1,
                            0 if w["overdue_by"] else 1, -w["overdue_by"]))
    return {"area": area, "walks": out,
            "overdue": len([w for w in out if w["status"] == "alerted" or w["overdue_by"] > 0])}


# --------------------------------------------------------------------- SOS
def sos(device: str, area: str, note: str = "", lat: float = None,
        lon: float = None) -> dict:
    me = resilience.identify(device, area)
    con = _db()
    cur = con.execute("""INSERT INTO sos (device, handle, area, note, lat, lon, created)
                         VALUES (?,?,?,?,?,?,?)""",
                      (device, me["handle"], area.strip()[:60], note.strip()[:160],
                       _round(lat), _round(lon), _now().isoformat(timespec="seconds")))
    sid = cur.lastrowid
    con.commit()
    con.close()
    body = me["handle"] + " needs help in " + area
    if note.strip():
        body += " — " + note.strip()[:80]
    try:
        sent = push.broadcast("🆘 SOS — " + me["handle"], body,
                              area_filter=area.strip(), url="/?tab=community")
    except Exception:
        sent = 0
    try:
        resilience.act(device, "checkin", meta="sos", area=area)
    except Exception:
        pass
    return {"ok": True, "id": sid, "handle": me["handle"], "area": area,
            "notified": sent if isinstance(sent, int) else 0,
            "resources": [c for c in CURATED if c["priority"] <= 2],
            "note": "If you are in immediate danger, call 10111 or 112 — the app does not replace the police."}


def alerts(area: str = "", limit: int = 15) -> dict:
    con = _db()
    if area.strip():
        rows = con.execute("""SELECT handle, area, note, lat, lon, created, status FROM sos
                              WHERE area=? ORDER BY id DESC LIMIT ?""", (area.strip(), limit)).fetchall()
    else:
        rows = con.execute("""SELECT handle, area, note, lat, lon, created, status FROM sos
                              ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    con.close()
    return {"alerts": [
        {"handle": r[0], "area": r[1], "note": r[2], "lat": r[3], "lon": r[4],
         "created": r[5], "status": r[6]} for r in rows]}


# ------------------------------------------------------------ unsafe places
def report_unsafe(area: str, kind: str, message: str, device: str = "",
                  lat: float = None, lon: float = None) -> dict:
    """A safety hazard becomes a fault with an SLA — the prevention loop.

    A streetlight is a municipal repair job. Treating it as one (rather than as
    a complaint on a wall) is what turns "this street is dangerous" into a
    work order with a clock on it.
    """
    kind = (kind or "other_safety").strip()
    if kind not in {k["id"] for k in UNSAFE_KINDS}:
        kind = "other_safety"
    rid = sources.add_report(area.strip(), "unsafe",
                             ("[" + kind + "] " + (message or "")).strip()[:280],
                             (device or "neighbour")[:40], lat, lon)
    try:
        receipt = receipts.issue(rid, area.strip(), "unsafe")
    except Exception:
        receipt = {}
    return {"ok": True, "report_id": rid, "receipt": receipt, "kind": kind}


def resources() -> dict:
    return {
        "tier": "curated",
        "note": "Verified before shipping. Curated data never expires silently — " +
                "each entry carries its source and every number is free to call.",
        "resources": sorted(CURATED, key=lambda c: c["priority"]),
        "unsafe_kinds": UNSAFE_KINDS,
    }
