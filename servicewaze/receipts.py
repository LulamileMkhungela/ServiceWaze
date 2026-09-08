"""The accountability receipt — turning a complaint into a tracked promise.

South Africans do not distrust municipalities because outages happen. They
distrust them because nothing comes back: you report a burst pipe and the
report disappears into a call centre. There is no reference number you own, no
clock anyone can see, no public record of whether the city kept its promise.

ServiceWaze issues a receipt for every report:

    SW-7K3Q  ·  Pimville Zone 1  ·  Burst pipe
    Logged with: Johannesburg Water   ·  Channel: 0860 562 874
    SLA: 24 h   ·   Elapsed: 31 h 12 min  ·  Status: OVERDUE
    Updates: [crew dispatched] [still open on day 2]

Receipts are public (never personal), aggregate into a ward scorecard, and
give community organisers — and municipal partners — a shared fact base.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "servicewaze.db")

SLA_HOURS = {
    "no_water": 24, "low_pressure": 24, "leak": 72, "power_out": 6,
    "route": 12, "restored": 0, "other": 48,
}

ENTITY_BY_AREA = [
    (("johannesburg", "soweto", "randburg", "sandton", "joburg", "alexandra", "midrand",
      "roodepoort", "gauteng"), {
        "water": ("Johannesburg Water", "0860 562 874", "https://www.johannesburgwater.co.za"),
        "power": ("City Power Johannesburg", "0860 562 874", "https://www.citypower.co.za"),
        "route": ("Johannesburg Roads Agency", "0860 562 874", "https://www.jra.org.za"),
    }),
    (("cape town", "khayelitsha", "stellenbosch", "paarl", "western cape"), {
        "water": ("City of Cape Town Water & Sanitation", "0860 103 089", "https://www.capetown.gov.za"),
        "power": ("City of Cape Town Electricity", "0860 103 089", "https://www.capetown.gov.za"),
        "route": ("Transport for Cape Town", "0800 656 463", "https://www.tct.gov.za"),
    }),
    (("pretoria", "tshwane", "centurion", "soshanguve"), {
        "water": ("City of Tshwane Water", "012 358 9999", "https://www.tshwane.gov.za"),
        "power": ("City of Tshwane Electricity", "012 358 9999", "https://www.tshwane.gov.za"),
        "route": ("City of Tshwane Transport", "012 358 9999", "https://www.tshwane.gov.za"),
    }),
    (("durban", "ethekwini", "umhlanga", "pietermaritzburg"), {
        "water": ("eThekwini Water", "0800 131 3013", "https://www.durban.gov.za"),
        "power": ("eThekwini Electricity", "0800 311 1111", "https://www.durban.gov.za"),
        "route": ("eThekwini Transport Authority", "0800 131 3013", "https://www.durban.gov.za"),
    }),
]

SERVICE_OF_KIND = {
    "no_water": "water", "low_pressure": "water", "leak": "water", "restored": "water",
    "power_out": "power", "route": "route", "other": "water",
}


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT, area TEXT NOT NULL, lat REAL, lon REAL,
        kind TEXT NOT NULL, message TEXT, reporter TEXT, confirms INTEGER DEFAULT 0, created TEXT)""")
    for col, ddl in [("photo", "TEXT"), ("audio", "TEXT"), ("audio_mime", "TEXT"),
                     ("ref", "TEXT"), ("status", "TEXT DEFAULT 'open'"),
                     ("entity", "TEXT"), ("channel", "TEXT"), ("sla_hours", "INTEGER"),
                     ("resolved_at", "TEXT"), ("updates", "TEXT"),
                     ("contact", "TEXT"), ("severity", "TEXT DEFAULT 'normal'")]:
        try:
            con.execute(f"ALTER TABLE reports ADD COLUMN {col} {ddl}")
            con.commit()
        except Exception:
            pass
    con.execute("""CREATE TABLE IF NOT EXISTS receipt_updates(
        id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER, text TEXT,
        by TEXT, created TEXT)""")
    con.commit()
    return con


def _now():
    return datetime.now(timezone.utc)


def _ref(rid: int) -> str:
    h = hashlib.sha256(f"sw-{rid}-{int(_now().timestamp() // 3600)}".encode()).hexdigest()
    return "SW-" + h[:4].upper()


def entity_for(area: str, kind: str) -> tuple[str, str, str]:
    service = SERVICE_OF_KIND.get(kind, "water")
    a = (area or "").lower()
    for keys, mapping in ENTITY_BY_AREA:
        if any(k in a for k in keys):
            name, tel, url = mapping.get(service, mapping["water"])
            return name, tel, url
    return ("Your municipality", "0860 562 874", "https://www.gov.za")


def issue(rid: int, area: str, kind: str) -> dict:
    """Attach a receipt to a freshly created report."""
    ref = _ref(rid)
    sla = int(SLA_HOURS.get(kind, 48))
    name, tel, url = entity_for(area, kind)
    con = _db()
    con.execute("UPDATE reports SET ref=?, status='open', entity=?, channel=?, sla_hours=?,"
                " updates=? WHERE id=?", (ref, name, f"{tel} · {url}", sla, "", rid))
    con.commit()
    con.close()
    return receipt(rid) or {"ref": ref}


def receipt(rid: int) -> dict | None:
    con = _db()
    row = con.execute("SELECT id, area, kind, message, reporter, confirms, created, ref, status,"
                      " entity, channel, sla_hours, resolved_at FROM reports WHERE id=?", (rid,)).fetchone()
    if not row:
        con.close()
        return None
    ups = con.execute("SELECT text, by, created FROM receipt_updates WHERE report_id=?"
                      " ORDER BY id", (rid,)).fetchall()
    con.close()
    return _shape(row, ups)


def _shape(row, ups) -> dict:
    (rid, area, kind, message, reporter, confirms, created, ref, status, entity,
     channel, sla_hours, resolved_at) = row
    try:
        created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
    except Exception:
        created_dt = _now()
    elapsed_h = (_now() - created_dt).total_seconds() / 3600.0
    sla = int(sla_hours or 48)
    if status == "resolved":
        state, remaining = "resolved", 0.0
    elif elapsed_h <= sla:
        state, remaining = "on_time", sla - elapsed_h
    else:
        state, remaining = "overdue", 0.0
    return {
        "id": rid, "ref": ref or _ref(rid), "area": area, "kind": kind,
        "message": message or "", "reporter": reporter or "anonymous",
        "confirms": confirms or 0, "created": created,
        "elapsed_hours": round(elapsed_h, 1), "sla_hours": sla,
        "remaining_hours": round(remaining, 1), "state": state,
        "status": status or "open", "entity": entity, "channel": channel,
        "resolved_at": resolved_at,
        "updates": [{"text": t, "by": b, "created": c} for t, b, c in ups],
        "share_text": (f"{ref or 'SW'} — {area} · {kind.replace('_',' ')} · "
                       f"logged with {entity} · {state.replace('_',' ')} "
                       f"({elapsed_h:.1f}h of {sla}h SLA) — ServiceWaze"),
    }


def update(rid: int, text: str, by: str = "community") -> dict:
    con = _db()
    row = con.execute("SELECT id FROM reports WHERE id=?", (rid,)).fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "not found"}
    con.execute("INSERT INTO receipt_updates(report_id, text, by, created) VALUES(?,?,?,?)",
                (rid, text[:300], by[:40], _now().isoformat(timespec="seconds")))
    con.commit()
    con.close()
    return {"ok": True, **receipt(rid)}


def resolve(rid: int, by: str = "community") -> dict:
    con = _db()
    cur = con.execute("UPDATE reports SET status='resolved', resolved_at=? WHERE id=?",
                      (_now().isoformat(timespec="seconds"), rid))
    con.commit()
    con.close()
    if not cur.rowcount:
        return {"ok": False, "error": "not found"}
    update(rid, "Marked resolved by neighbours", by)
    return {"ok": True, **receipt(rid)}


def list_receipts(area: str = "", limit: int = 25) -> list[dict]:
    con = _db()
    if area:
        rows = con.execute("SELECT id FROM reports WHERE area LIKE ? ORDER BY id DESC LIMIT ?",
                           (f"%{area[:40]}%", limit)).fetchall()
    else:
        rows = con.execute("SELECT id FROM reports ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    out = []
    for (rid,) in rows:
        r = receipt(rid)
        if r:
            out.append(r)
    return out


def scorecard(area: str = "") -> dict:
    """Ward accountability: how many promises were kept, and how fast."""
    items = list_receipts(area, 200)
    if not items:
        return {"area": area or "all areas", "open": 0, "resolved": 0, "overdue": 0,
                "on_time": 0, "avg_hours": None, "sla_compliance": None,
                "by_entity": {}, "by_kind": {}}
    resolved = [i for i in items if i["status"] == "resolved"]
    overdue = [i for i in items if i["state"] == "overdue"]
    on_time = [i for i in resolved if i["elapsed_hours"] <= i["sla_hours"]]
    avg = sum(i["elapsed_hours"] for i in resolved) / len(resolved) if resolved else None
    by_entity, by_kind = {}, {}
    for i in items:
        e = by_entity.setdefault(i["entity"] or "Unknown", {"total": 0, "resolved": 0, "overdue": 0})
        e["total"] += 1
        e["resolved"] += 1 if i["status"] == "resolved" else 0
        e["overdue"] += 1 if i["state"] == "overdue" else 0
        k = by_kind.setdefault(i["kind"], {"total": 0, "resolved": 0, "overdue": 0})
        k["total"] += 1
        k["resolved"] += 1 if i["status"] == "resolved" else 0
        k["overdue"] += 1 if i["state"] == "overdue" else 0
    return {
        "area": area or "all areas", "total": len(items),
        "open": sum(1 for i in items if i["status"] == "open"),
        "resolved": len(resolved), "overdue": len(overdue), "on_time": len(on_time),
        "avg_hours": round(avg, 1) if avg else None,
        "sla_compliance": round(len(on_time) / len(resolved), 3) if resolved else None,
        "by_entity": by_entity, "by_kind": by_kind,
        "note": "SLA targets are ServiceWaze's published service expectations, not municipal policy.",
    }
