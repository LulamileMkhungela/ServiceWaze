"""Area insights and the self-calibrating disruption forecast.

Why this exists
---------------
"Predict" is the easiest word to fake in this category. A rule that says
"3 reports = high risk" is not a prediction, it is a threshold. This module is
a *model*: it estimates the probability that a service fails in your area
within a horizon, shows the drivers behind the number, states its sample size,
and — the important part — **learns from whether it was right**.

Every forecast is logged. When the street reports "yes, the water went off" or
"no, nothing happened", that outcome is matched back to the forecast and the
model's calibration factor for that area and service is updated. ServiceWaze
therefore gets measurably better the longer a community uses it, and can
*prove* its accuracy per area — which is exactly the claim a municipality or
an insurer will ask for before they buy anything.

Model (deliberately simple, inspectable, no black box):
    p = 1 - exp(-λ · h)                      Poisson baseline from event rate
    p = p + Σ driver boosts                  official notice, weather, recency
    p = clamp(p · calibration, 0.03, 0.97)   learned per area × service
"""
from __future__ import annotations

import math
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "servicewaze.db")

SERVICES = {
    "water": {"kinds": ("no_water", "low_pressure", "leak"), "icon": "🚰", "label": "Water"},
    "power": {"kinds": ("power_out",), "icon": "⚡", "label": "Power"},
    "transport": {"kinds": ("route",), "icon": "🚌", "label": "Transport"},
}

HORIZON_HOURS = 24


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS predictions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, area TEXT, service TEXT,
        prob REAL, horizon_h INTEGER, drivers TEXT, sample INTEGER,
        created TEXT, outcome INTEGER, resolved_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS outcomes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, area TEXT, service TEXT,
        happened INTEGER, note TEXT, created TEXT)""")
    con.commit()
    return con


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def _reports(area: str, days: int = 120):
    con = _db()
    con.execute("""CREATE TABLE IF NOT EXISTS reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT, area TEXT NOT NULL, lat REAL, lon REAL,
        kind TEXT NOT NULL, message TEXT, reporter TEXT, confirms INTEGER DEFAULT 0, created TEXT)""")
    rows = con.execute(
        "SELECT id, kind, created, confirms, status, resolved_at FROM reports "
        "WHERE area LIKE ? ORDER BY id DESC", (f"%{area[:40]}%",)).fetchall()
    con.close()
    out = []
    for rid, kind, created, confirms, status, resolved_at in rows:
        dt = _parse(created)
        if not dt:
            continue
        if (_now() - dt).days > days:
            continue
        out.append({"id": rid, "kind": kind, "created": dt, "confirms": confirms or 0,
                    "status": status or "open", "resolved_at": resolved_at})
    return out


def history(area: str, days: int = 120) -> dict:
    """Service-delivery stats for an area: the B2G artefact."""
    reps = _reports(area, days)
    by_service = defaultdict(list)
    for r in reps:
        for svc, meta in SERVICES.items():
            if r["kind"] in meta["kinds"]:
                by_service[svc].append(r)
    out_services = {}
    for svc, items in by_service.items():
        resolved = [r for r in items if r["status"] == "resolved" and r["resolved_at"]]
        hours = []
        for r in resolved:
            rd = _parse(r["resolved_at"])
            if rd:
                hours.append((rd - r["created"]).total_seconds() / 3600.0)
        hours.sort()
        median_fix = round(hours[len(hours) // 2], 1) if hours else None
        created_sorted = sorted(r["created"] for r in items)
        gaps = [(created_sorted[i + 1] - created_sorted[i]).days
                for i in range(len(created_sorted) - 1)]
        gaps.sort()
        out_services[svc] = {
            "icon": SERVICES[svc]["icon"], "label": SERVICES[svc]["label"],
            "events": len(items),
            "open": sum(1 for r in items if r["status"] != "resolved"),
            "resolved": len(resolved),
            "median_hours_to_fix": median_fix,
            "avg_hours_to_fix": round(sum(hours) / len(hours), 1) if hours else None,
            "median_days_between": gaps[len(gaps) // 2] if gaps else None,
            "last_event": created_sorted[-1].isoformat() if created_sorted else None,
            "days_since_last": (int((_now() - created_sorted[-1]).days)
                                if created_sorted else None),
            "confirmations": sum(r["confirms"] for r in items),
        }
    return {
        "area": area, "window_days": days, "total_events": len(reps),
        "services": out_services,
        "worst_service": (max(out_services.items(),
                              key=lambda kv: kv[1]["events"])[0] if out_services else None),
        "generated_at": _now().isoformat(timespec="seconds"),
    }


def calibration(area: str, service: str) -> dict:
    """Model honesty: how good have our forecasts been here?"""
    con = _db()
    rows = con.execute(
        "SELECT prob, outcome FROM predictions WHERE area=? AND service=? AND outcome IS NOT NULL",
        (area[:40], service)).fetchall()
    con.close()
    if len(rows) < 3:
        return {"service": service, "n": len(rows), "factor": 1.0,
                "hit_rate": None, "mean_prob": None,
                "note": "Not enough verified forecasts yet — using the uncalibrated model."}
    probs = [p for p, _ in rows]
    outs = [1 if o else 0 for _, o in rows]
    hit = sum(outs) / len(outs)
    mean_p = sum(probs) / len(probs)
    factor = max(0.4, min(2.5, hit / mean_p)) if mean_p else 1.0
    # Brier score: lower is better (0 = perfect, 0.25 = coin flip)
    brier = sum((p - o) ** 2 for p, o in zip(probs, outs)) / len(rows)
    return {"service": service, "n": len(rows), "factor": round(factor, 3),
            "hit_rate": round(hit, 3), "mean_prob": round(mean_p, 3),
            "brier": round(brier, 3),
            "note": f"{len(rows)} verified forecasts · Brier {brier:.2f} (0.25 = coin flip)"}


def predict(area: str, horizon_h: int = HORIZON_HOURS, weather=None,
            official_notices=None, log: bool = True) -> dict:
    """Probability that each service is disrupted within the horizon."""
    reps = _reports(area, 120)
    now = _now()
    out = {}
    for svc, meta in SERVICES.items():
        items = [r for r in reps if r["kind"] in meta["kinds"]]
        n = len(items)
        lookback_days = 120
        lam = n / float(lookback_days)                      # events per day
        base = 1 - math.exp(-lam * (horizon_h / 24.0))       # Poisson baseline
        drivers = [{"label": f"{n} report(s) in {lookback_days} days",
                    "effect": round(base, 3)}]
        boost = 0.0
        if items:
            last = max(items, key=lambda r: r["created"])
            hours_since = (now - last["created"]).total_seconds() / 3600.0
            if last["status"] != "resolved" and hours_since < 72:
                b = 0.30 * (0.5 ** (hours_since / 48.0))
                boost += b
                drivers.append({"label": f"an unresolved report {hours_since:.0f} h ago",
                                "effect": round(b, 3)})
            if len(items) >= 3:
                created_sorted = sorted(r["created"] for r in items)
                gaps = [(created_sorted[i + 1] - created_sorted[i]).days
                        for i in range(len(created_sorted) - 1)]
                med_gap = sorted(gaps)[len(gaps) // 2] if gaps else None
                days_since = (now - created_sorted[-1]).days
                if med_gap and days_since >= med_gap * 0.8:
                    b = min(0.20, 0.05 * (days_since / max(1, med_gap)))
                    boost += b
                    drivers.append({"label": f"typical gap here is every {med_gap} days",
                                    "effect": round(b, 3)})
        if official_notices and svc == "water":
            b = 0.25
            boost += b
            drivers.append({"label": "an official notice mentions maintenance", "effect": b})
        if weather and svc in ("power", "transport"):
            adv = (weather.get("advisories") or [])
            if any(a.get("level") == "severe" for a in adv):
                b = 0.18
                boost += b
                drivers.append({"label": "severe weather advisory", "effect": b})
        cal = calibration(area, svc)
        raw = min(0.97, base + boost)
        prob = round(max(0.03, min(0.97, raw * cal["factor"])), 3)
        out[svc] = {
            "service": svc, "icon": meta["icon"], "label": meta["label"],
            "prob": prob, "horizon_hours": horizon_h,
            "sample": n, "drivers": drivers,
            "calibration": cal,
            "confidence": "high" if n >= 6 and cal["n"] >= 5 else "medium" if n >= 2 else "low",
            "band": ("likely" if prob >= 0.6 else "possible" if prob >= 0.3 else "unlikely"),
        }
        if log:
            con = _db()
            con.execute("INSERT INTO predictions(area, service, prob, horizon_h, drivers,"
                        " sample, created) VALUES(?,?,?,?,?,?,?)",
                        (area[:40], svc, prob, horizon_h, str(drivers)[:400], n,
                         now.isoformat(timespec="seconds")))
            con.commit()
            con.close()
    return {
        "area": area, "horizon_hours": horizon_h,
        "forecasts": out,
        "top": max(out.values(), key=lambda x: x["prob"])["service"] if out else None,
        "generated_at": now.isoformat(timespec="seconds"),
    }


def record_outcome(area: str, service: str, happened: bool, note: str = "") -> dict:
    """The street tells us whether the forecast was right → the model learns."""
    con = _db()
    con.execute("INSERT INTO outcomes(area, service, happened, note, created) VALUES(?,?,?,?,?)",
                (area[:40], service, 1 if happened else 0, note[:200],
                 _now().isoformat(timespec="seconds")))
    # match the most recent unresolved forecast for this area + service
    row = con.execute("SELECT id FROM predictions WHERE area=? AND service=? AND outcome IS NULL"
                      " ORDER BY id DESC LIMIT 1", (area[:40], service)).fetchone()
    if row:
        con.execute("UPDATE predictions SET outcome=?, resolved_at=? WHERE id=?",
                    (1 if happened else 0, _now().isoformat(timespec="seconds"), row[0]))
    con.commit()
    con.close()
    return {"ok": True, "matched": bool(row), **calibration(area, service)}


def forecast_accuracy(area: str = "") -> dict:
    con = _db()
    if area:
        rows = con.execute("SELECT service, prob, outcome FROM predictions WHERE area=?"
                           " AND outcome IS NOT NULL", (area[:40],)).fetchall()
    else:
        rows = con.execute("SELECT service, prob, outcome FROM predictions"
                           " WHERE outcome IS NOT NULL").fetchall()
    con.close()
    if not rows:
        return {"n": 0, "brier": None, "hit_rate": None, "note": "no verified forecasts yet"}
    probs = [p for _, p, _ in rows]
    outs = [1 if o else 0 for *_, o in rows]
    brier = sum((p - o) ** 2 for p, o in zip(probs, outs)) / len(rows)
    correct = sum(1 for p, o in zip(probs, outs) if (p >= 0.5) == bool(o))
    return {"n": len(rows), "brier": round(brier, 3),
            "hit_rate": round(sum(outs) / len(rows), 3),
            "directional_accuracy": round(correct / len(rows), 3),
            "note": f"{len(rows)} verified forecasts"}
