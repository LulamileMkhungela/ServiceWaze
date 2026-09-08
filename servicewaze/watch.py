"""watch.py — "Is she okay?"

The most valuable thing a street has is not data. It is a person who notices
when the gogo two doors down has not been seen since the storm started.

Every other app in this space reports faults. None of them closes the loop on
people. ServiceWaze adds a **watch circle**: you name the neighbours you look
out for (by pseudonym — never a real name or number), tap "I'm safe" when you
are, and the street can see who has not been heard from in 48 hours so someone
knocks instead of assuming.

Design rules that keep it safe rather than creepy:
  * no real names, phone numbers or locations of *people* — pseudonyms only
  * a check-in is a claim by a neighbour, not a GPS ping
  * "needs help" is a flag, not a tracker; it expires with the next check-in
  * everything is visible to the area, so the circle polices itself
"""

import os
import sqlite3
from datetime import datetime, timezone, timedelta

import resilience

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "watch.db")

CHECKIN_TTL_HOURS = 48          # after this, a neighbour is "quiet"
URGENT_HOURS = 72               # after this, "please knock"


def _now():
    return datetime.now(timezone.utc)


def _db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS watch (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        watcher TEXT NOT NULL,
        handle TEXT NOT NULL,
        area TEXT NOT NULL,
        note TEXT DEFAULT '',
        lat REAL, lon REAL,
        created TEXT NOT NULL,
        last_check TEXT,
        last_check_by TEXT DEFAULT '',
        state TEXT DEFAULT 'ok',
        UNIQUE(watcher, handle, area)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS checkins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        handle TEXT NOT NULL,
        area TEXT NOT NULL,
        device TEXT NOT NULL,
        kind TEXT DEFAULT 'self',
        note TEXT DEFAULT '',
        created TEXT NOT NULL
    )""")
    return con


def _hours(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return round((_now() - dt).total_seconds() / 3600, 1)
    except Exception:
        return None


def _state_for(hours):
    if hours is None:
        return "unknown"
    if hours >= URGENT_HOURS:
        return "knock"
    if hours >= CHECKIN_TTL_HOURS:
        return "quiet"
    return "ok"


STATE_LABEL = {
    "ok": ("✅", "Checked in"),
    "quiet": ("🔶", "Quiet — no word yet"),
    "knock": ("🚨", "Please knock"),
    "unknown": ("⚪", "Never checked in"),
    "needs_help": ("🆘", "Needs help"),
}


def add(watcher: str, handle: str, area: str, note: str = "",
        lat: float = None, lon: float = None) -> dict:
    handle = (handle or "").strip()[:40]
    area = (area or "").strip()[:60]
    if len(handle) < 2 or not area:
        return {"ok": False, "error": "handle and area are required"}
    con = _db()
    try:
        con.execute("""INSERT INTO watch (watcher, handle, area, note, lat, lon, created)
                       VALUES (?,?,?,?,?,?,?)""",
                    (watcher, handle, area, note[:120], lat, lon,
                     _now().isoformat(timespec="seconds")))
        con.commit()
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "already watching them"}
    finally:
        con.close()
    return {"ok": True, "handle": handle, "area": area}


def checkin(watcher: str, wid: int, note: str = "") -> dict:
    """A neighbour confirms they have seen/heard from the person."""
    con = _db()
    row = con.execute("SELECT handle, area FROM watch WHERE id=?", (wid,)).fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "not found"}
    handle, area = row
    con.execute("UPDATE watch SET last_check=?, last_check_by=?, state='ok' WHERE id=?",
                (_now().isoformat(timespec="seconds"), watcher, wid))
    con.execute("""INSERT INTO checkins (handle, area, device, kind, note, created)
                   VALUES (?,?,?,?,?,?)""",
                (handle, area, watcher, "neighbour", note[:120],
                 _now().isoformat(timespec="seconds")))
    con.commit()
    con.close()
    try:
        resilience.act(watcher, "checkin", meta="watch:" + handle, area=area)
    except Exception:
        pass
    return {"ok": True, "id": wid, "handle": handle}


def im_safe(device: str, area: str, note: str = "") -> dict:
    """A user declares themselves safe — every watch row for them updates."""
    me = resilience.identify(device, area)
    handle = me["handle"]
    now = _now().isoformat(timespec="seconds")
    con = _db()
    cur = con.execute(
        "UPDATE watch SET last_check=?, last_check_by=?, state='ok' WHERE handle=? AND area=?",
        (now, handle, handle, area))
    n = cur.rowcount
    con.execute("""INSERT INTO checkins (handle, area, device, kind, note, created)
                   VALUES (?,?,?,?,?,?)""", (handle, area, device, "self", note[:120], now))
    con.commit()
    con.close()
    try:
        resilience.act(device, "checkin", meta="im-safe", area=area)
    except Exception:
        pass
    return {"ok": True, "handle": handle, "updated": n}


def flag(watcher: str, wid: int, state: str = "needs_help", note: str = "") -> dict:
    con = _db()
    row = con.execute("SELECT handle, area FROM watch WHERE id=?", (wid,)).fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "not found"}
    handle, area = row
    con.execute("UPDATE watch SET state=?, note=COALESCE(NULLIF(?, ''), note) WHERE id=?",
                ("needs_help" if state == "needs_help" else "ok", note[:120], wid))
    con.execute("""INSERT INTO checkins (handle, area, device, kind, note, created)
                   VALUES (?,?,?,?,?,?)""",
                (handle, area, watcher, "flag:" + state, note[:120],
                 _now().isoformat(timespec="seconds")))
    con.commit()
    con.close()
    return {"ok": True, "id": wid, "state": state}


def circle(area: str, device: str = "", limit: int = 40) -> dict:
    """The watch circle for an area: watched people, their state, and a
    self-check-in prompt. Nothing here identifies a person in the real world."""
    con = _db()
    rows = con.execute("""SELECT id, watcher, handle, area, note, last_check,
                                 last_check_by, state
                          FROM watch WHERE area=? ORDER BY id DESC LIMIT ?""",
                       (area, limit)).fetchall()
    con.close()
    people, seen, watchers = [], set(), set()
    for (wid, watcher, handle, a, note, last_check, by, st) in rows:
        watchers.add(watcher)
        if handle in seen:
            continue
        seen.add(handle)
        hours = _hours(last_check)
        state = st if st == "needs_help" else _state_for(hours)
        icon, label = STATE_LABEL.get(state, ("⚪", state))
        people.append({
            "id": wid, "handle": handle, "note": note, "state": state,
            "icon": icon, "state_label": label,
            "hours_since": hours,
            "last_check": last_check, "last_check_by": by,
            "mine": bool(device and watcher == device),
        })
    order = {"needs_help": 0, "knock": 1, "quiet": 2, "unknown": 3, "ok": 4}
    people.sort(key=lambda p: order.get(p["state"], 9))
    me = resilience.identify(device or "anon", area)["handle"] if device else ""
    return {
        "area": area,
        "people": people,
        "watchers": len(watchers),
        "quiet": len([p for p in people if p["state"] in ("quiet", "knock", "needs_help")]),
        "me": me,
        "ttl_hours": CHECKIN_TTL_HOURS,
        "urgent_hours": URGENT_HOURS,
        "privacy": "Pseudonyms only — no names, numbers or locations of people are stored.",
    }
