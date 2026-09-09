"""The Prepare Window — ServiceWaze's core invention.

Every status app answers "am I affected?". That question is asked too late: by
the time the tap runs dry, the bath is empty. ServiceWaze answers the question
that actually saves a household money, food and sleep:

    "How long do I have, and what must I do before then?"

It fuses five signals into one countdown per service:
  1. weather forecasts and advisories (Open-Meteo)
  2. live national load-shedding / load-reduction status (Eskom + EskomSePush)
  3. per-area schedules (EskomSePush, when a token is configured)
  4. community ground truth (reports + confirmations, time-decayed)
  5. official notices (municipal RSS, curated maintenance calendars)

…then converts the highest-value threat into a *task list that fits inside the
time you have left*, sized to your actual household (people, roof, storage).

Every threat carries `confidence` and `evidence`, because telling a family to
fill 40 litres of water on a rumour is worse than not telling them at all.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

SAST = timezone(timedelta(hours=2))


def _now():
    return datetime.now(SAST)


def _iso(dt: datetime):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Task library — each task knows how long it takes and what it costs to skip
# ---------------------------------------------------------------------------
def water_tasks(people: int, litres_target: int = 75, have_litres: float = 0.0,
                tap_l_per_min: float = 8.0):
    need = max(0.0, litres_target * max(1, people) - float(have_litres or 0))
    minutes = max(3, round(need / tap_l_per_min))
    return [{
        "id": "store_water", "icon": "🪣",
        "title": f"Store {round(need)} L of water",
        "detail": f"Fill the bath, buckets and bottles — {tap_l_per_min:.0f} L/min from your tap, "
                  f"about {minutes} min. Cover containers to keep out dust.",
        "minutes": minutes, "xp": 40, "action": "stored_water",
        "value_rand": round(need / 1000 * 30, 2),
    }, {
        "id": "flask_hot", "icon": "☕", "title": "Fill flasks with hot water",
        "detail": "Boil now while you still can — hot water means no cooking gas needed later.",
        "minutes": 5, "xp": 15, "action": "food_stock", "value_rand": 6.0,
    }, {
        "id": "pets_plants", "icon": "🐕", "title": "Fill pet bowls and water plants",
        "detail": "Use grey water for plants; keep drinking water for people.",
        "minutes": 3, "xp": 5, "action": "checkin", "value_rand": 0.0,
    }]


def power_tasks(hours: float = 2.5):
    return [{
        "id": "charge", "icon": "🔋", "title": "Charge phones and power banks",
        "detail": "Top up every device now, including the kids' tablets and the gate remote battery.",
        "minutes": 10, "xp": 20, "action": "power_bank", "value_rand": 0.0,
    }, {
        "id": "fridge", "icon": "🧊", "title": "Freeze a bottle, cool the fridge down",
        "detail": "Set the fridge to coldest now — it buys you 4–6 extra safe hours. "
                  f"Keep doors shut for the full {hours:g} h.",
        "minutes": 4, "xp": 25, "action": "food_stock", "value_rand": 120.0,
    }, {
        "id": "unplug", "icon": "🔌", "title": "Unplug sensitive electronics",
        "detail": "Surges when power returns are what kills TVs and routers.",
        "minutes": 3, "xp": 15, "action": "surge_protect", "value_rand": 800.0,
    }, {
        "id": "lights", "icon": "🔦", "title": "Put lights where you'll need them",
        "detail": "Lanterns in the bathroom and kitchen. Never leave a candle unattended.",
        "minutes": 4, "xp": 15, "action": "backup_light", "value_rand": 0.0,
    }]


def flood_tasks():
    return [{
        "id": "raise", "icon": "📦", "title": "Move valuables and appliances up",
        "detail": "Lift electronics, documents and stock off the floor; move cars to high ground.",
        "minutes": 20, "xp": 30, "action": "drill", "value_rand": 2500.0,
    }, {
        "id": "drains", "icon": "🧹", "title": "Clear gutters and storm drains",
        "detail": "Most flood damage in townships is blocked drainage, not the rain itself.",
        "minutes": 15, "xp": 25, "action": "drill", "value_rand": 900.0,
    }, {
        "id": "route_flood", "icon": "🚗", "title": "Avoid low-lying routes",
        "detail": "Never drive through water — 30 cm of moving water floats a small car.",
        "minutes": 2, "xp": 10, "action": "route_plan", "value_rand": 0.0,
    }]


def heat_tasks():
    return [{
        "id": "hydrate", "icon": "🥤", "title": "Pre-cool and pre-hydrate",
        "detail": "Drink water now, wet a cloth for the neck, close curtains on the sun side.",
        "minutes": 5, "xp": 15, "action": "stored_water", "value_rand": 0.0,
    }, {
        "id": "check_vulnerable", "icon": "🧓", "title": "Check on elderly neighbours",
        "detail": "Heat kills quietly. A 5-minute knock on the door is the highest-value thing you do today.",
        "minutes": 10, "xp": 70, "action": "helped_elderly", "value_rand": 0.0,
    }]


def transport_tasks():
    return [{
        "id": "route_b", "icon": "🚌", "title": "Plan route B for tomorrow's trip",
        "detail": "Save an alternative operator, or a lift-share with someone on your street.",
        "minutes": 6, "xp": 50, "action": "route_plan", "value_rand": 80.0,
    }, {
        "id": "wfh", "icon": "🏠", "title": "Move what can wait to tomorrow",
        "detail": "Shift errands a day rather than losing a day's wages in a queue.",
        "minutes": 3, "xp": 10, "action": "checkin", "value_rand": 150.0,
    }]


# ---------------------------------------------------------------------------
# Threat detection
# ---------------------------------------------------------------------------
def _decay_weight(created_iso: str, half_life_h: float = 6.0) -> float:
    try:
        dt = datetime.fromisoformat(str(created_iso).replace("Z", "+00:00"))
    except Exception:
        return 0.0
    hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    if hours < 0:
        hours = 0.0
    return 0.5 ** (hours / half_life_h)


def _cluster(reports, kinds, window_h: float = 12.0) -> tuple[float, int]:
    """Time-decayed weight of reports of given kinds, plus raw count."""
    w, n = 0.0, 0
    for r in reports or []:
        if r.get("kind") in kinds:
            w += _decay_weight(r.get("created"), window_h) * (1 + 0.5 * int(r.get("confirms") or 0))
            n += 1
    return round(w, 2), n


def _planned_window(text: str):
    """Best-effort parse of a planned maintenance window from a notice."""
    t = (text or "").lower()
    m = re.search(r"(\d{1,2})[:h](\d{2})?\s*(?:-|to|–|until)\s*(\d{1,2})[:h](\d{2})?", t)
    day = None
    for i, d in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]):
        if d in t:
            day = i
            break
    start_h = int(m.group(1)) if m else None
    end_h = int(m.group(3)) if m and m.group(3) else None
    if start_h is None:
        return None
    now = _now()
    target = now
    if day is not None:
        delta = (day - now.weekday()) % 7
        target = (now + timedelta(days=delta)).replace(hour=start_h, minute=0, second=0, microsecond=0)
        if target < now and delta == 0:
            target += timedelta(days=7)
    else:
        target = now.replace(hour=start_h, minute=0, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
    end = target.replace(hour=end_h) if end_h else target + timedelta(hours=10)
    return {"start": _iso(target), "end": _iso(end), "parsed": True}


def assess(place: str, lat, lon, weather=None, air=None, power=None,
           water_reports=None, feed_items=None, profile=None, schedule=None) -> dict:
    """Build the threat picture + a task plan that fits the time available."""
    now = _now()
    profile = profile or {}
    people = int(profile.get("people") or 4)
    threats: list[dict] = []
    daily = ((weather or {}).get("daily") or [])
    advisories = (weather or {}).get("advisories") or []
    cur = (weather or {}).get("current") or {}

    # --- WATER -------------------------------------------------------------
    w_w, w_n = _cluster(water_reports, {"no_water", "low_pressure", "leak"})
    official = [i for i in (feed_items or []) if i.get("official") and i.get("category") == "water"]
    planned = None
    for o in official[:4]:
        planned = _planned_window(f"{o.get('title','')} {o.get('body','')}")
        if planned:
            break
    if planned:
        start = datetime.fromisoformat(planned["start"])
        mins = int((start - now).total_seconds() // 60)
        threats.append({
            "id": "water_planned", "service": "water", "icon": "🚰",
            "severity": "high" if mins < 720 else "medium",
            "confidence": 0.85,
            "title": f"Planned water interruption in {max(0, mins // 60)} h {max(0, mins % 60)} min",
            "starts_at": planned["start"], "ends_at": planned["end"],
            "minutes_to_impact": mins,
            "evidence": [{"source": o.get("source", "Official notice"), "text": o.get("title", "")[:160]}
                         for o in official[:2]],
            "source_tier": (official[0].get("tier") if official else "curated"),
        })
    if w_w >= 1.5:
        threats.append({
            "id": "water_crowd", "service": "water", "icon": "🚰",
            "severity": "critical" if w_w >= 4 else "high",
            "confidence": min(0.9, 0.45 + 0.12 * w_n),
            "title": f"{w_n} neighbour{'s' if w_n != 1 else ''} report no/low water near you",
            "starts_at": _iso(now), "minutes_to_impact": 0,
            "evidence": [{"source": "Community reports (decayed 6 h half-life)",
                          "text": f"weighted signal {w_w} from {w_n} reports"}],
            "source_tier": "community",
        })
    elif w_w > 0:
        threats.append({
            "id": "water_watch", "service": "water", "icon": "🚰",
            "severity": "medium", "confidence": 0.35,
            "title": "Possible water problem — one unverified report nearby",
            "starts_at": _iso(now), "minutes_to_impact": 60,
            "evidence": [{"source": "Community report", "text": "single report, needs confirmation"}],
            "source_tier": "community",
        })

    # --- POWER -------------------------------------------------------------
    stage = None
    try:
        stage = int((power or {}).get("status", {}).get("stage"))
    except Exception:
        stage = None
    wins = ((schedule or {}).get("upcoming") or []) if schedule else []
    next_win = None
    for w in wins:
        try:
            s = datetime.fromisoformat(str(w["start"]).replace("Z", "+00:00"))
            if s > now.astimezone(timezone.utc):
                next_win = (s, w)
                break
        except Exception:
            continue
    if next_win:
        s, w = next_win
        mins = int((s - now.astimezone(timezone.utc)).total_seconds() // 60)
        threats.append({
            "id": "power_slot", "service": "power", "icon": "⚡",
            "severity": "high" if mins < 180 else "medium",
            "confidence": 0.92, "title": f"Load-shedding in {mins // 60} h {mins % 60} min",
            "starts_at": w.get("start"), "ends_at": w.get("end"), "minutes_to_impact": mins,
            "evidence": [{"source": "EskomSePush area schedule", "text": f"stage {w.get('stage', '?')} slot"}],
            "source_tier": "live",
        })
    elif stage and stage >= 1:
        threats.append({
            "id": "power_stage", "service": "power", "icon": "⚡",
            "severity": "medium", "confidence": 0.6,
            "title": f"National load-shedding Stage {stage} — your slot may not be published",
            "starts_at": _iso(now + timedelta(hours=2)), "minutes_to_impact": 120,
            "evidence": [{"source": "Eskom GetStatus", "text": f"stage {stage}"}],
            "source_tier": "live",
        })
    storm_power = any(a.get("level") == "severe" for a in advisories) or \
        any((d.get("gusts") or 0) >= 60 for d in daily)
    if storm_power:
        threats.append({
            "id": "power_storm", "service": "power", "icon": "⚡",
            "severity": "medium", "confidence": 0.5,
            "title": "Storm damage could cut power unexpectedly",
            "starts_at": _iso(now + timedelta(hours=6)), "minutes_to_impact": 360,
            "evidence": [{"source": "Open-Meteo forecast", "text": "severe advisory or gusts ≥ 60 km/h"}],
            "source_tier": "live",
        })

    # --- WEATHER -----------------------------------------------------------
    for d in daily:
        if (d.get("precip_sum") or 0) >= 25 and (d.get("precip_prob") or 0) >= 60:
            threats.append({
                "id": f"flood_{d['date']}", "service": "flood", "icon": "🌊",
                "severity": "high" if (d.get("precip_sum") or 0) >= 40 else "medium",
                "confidence": min(0.85, 0.4 + (d.get("precip_prob") or 0) / 200),
                "title": f"Heavy rain {d.get('precip_sum'):.0f} mm expected on {d['date']}",
                "starts_at": _iso(now + timedelta(days=max(0, daily.index(d)))),
                "minutes_to_impact": int(max(0, daily.index(d)) * 24 * 60 + 240),
                "evidence": [{"source": "Open-Meteo", "text": f"{d.get('precip_prob')}% chance, {d.get('precip_sum')} mm"}],
                "source_tier": "live",
            })
            break
    for d in daily:
        if (d.get("tmax") or 0) >= 35:
            threats.append({
                "id": f"heat_{d['date']}", "service": "heat", "icon": "🥵",
                "severity": "high", "confidence": 0.8,
                "title": f"Extreme heat {d.get('tmax'):.0f}°C on {d['date']}",
                "starts_at": _iso(now), "minutes_to_impact": 180,
                "evidence": [{"source": "Open-Meteo", "text": f"max {d.get('tmax')} °C"}],
                "source_tier": "live",
            })
            break
    if air and (air.get("aqi") or 0) > 100:
        threats.append({
            "id": "air", "service": "air", "icon": "😷", "severity": "medium", "confidence": 0.9,
            "title": f"Air quality unhealthy (AQI {air.get('aqi')})", "starts_at": _iso(now),
            "minutes_to_impact": 0,
            "evidence": [{"source": "Open-Meteo Air Quality", "text": air.get("label", "")}],
            "source_tier": "live",
        })

    # --- TRANSPORT ---------------------------------------------------------
    t_w, t_n = _cluster(water_reports, {"route"})
    strike_words = ("strike", "shutdown", "stay away", "blockade", "suspend")
    strike_hits = [i for i in (feed_items or [])
                   if i.get("category") == "transport" and any(w in (i.get("title", "") + i.get("body", "")).lower()
                                                               for w in strike_words)]
    if strike_hits:
        threats.append({
            "id": "transport_news", "service": "transport", "icon": "🚌",
            "severity": "high", "confidence": 0.7,
            "title": "Possible transport disruption reported in the news",
            "starts_at": _iso(now + timedelta(hours=12)), "minutes_to_impact": 720,
            "evidence": [{"source": i.get("source", "news"), "text": i.get("title", "")[:150]}
                         for i in strike_hits[:2]],
            "source_tier": "live",
        })
    if t_w >= 1.0:
        threats.append({
            "id": "transport_crowd", "service": "transport", "icon": "🚌",
            "severity": "medium", "confidence": min(0.8, 0.4 + 0.15 * t_n),
            "title": f"{t_n} route disruption report(s) near you",
            "starts_at": _iso(now), "minutes_to_impact": 0,
            "evidence": [{"source": "Community reports", "text": f"weighted {t_w}"}],
            "source_tier": "community",
        })

    # --- FOOD (spoilage economics) ----------------------------------------
    fridge_risk = any(t["service"] == "power" and t["severity"] in ("high", "critical") for t in threats)
    if fridge_risk:
        threats.append({
            "id": "food_spoilage", "service": "food", "icon": "🥫",
            "severity": "medium", "confidence": 0.75,
            "title": "R400+ of fridge food is at risk while the power is off",
            "starts_at": _iso(now), "minutes_to_impact": 0,
            "evidence": [{"source": "Derived", "text": "power interruption × average fridge contents"}],
            "source_tier": "derived",
        })

    threats.sort(key=lambda t: (t["minutes_to_impact"], -t["confidence"]))
    plan = build_plan(threats, people, profile)
    return {
        "place": place,
        "generated_at": _iso(now),
        "threats": threats,
        "plan": plan,
        "next_impact_minutes": threats[0]["minutes_to_impact"] if threats else None,
        "risk": risk_index(threats),
        "headline": headline(threats),
    }


def build_plan(threats: list[dict], people: int, profile: dict) -> dict:
    """Turn threats into a de-duplicated task list that fits the time left."""
    lead = next((t for t in threats if t["minutes_to_impact"] > 0), None)
    minutes_left = lead["minutes_to_impact"] if lead else 180
    have_l = float(profile.get("water_l") or 0) + float(profile.get("tank_l") or 0)
    tasks, seen = [], set()
    services = {t["service"] for t in threats}
    if "water" in services:
        for t in water_tasks(people, 75, have_l):
            if t["id"] not in seen:
                tasks.append(t)
                seen.add(t["id"])
    if "water" in services:
        tasks.append({
            "id": "tell_neighbours", "icon": "📣", "title": "Tell two neighbours",
            "detail": "Especially anyone elderly, sick or with a baby. Share this countdown on WhatsApp.",
            "minutes": 3, "xp": 30, "action": "helped_elderly", "value_rand": 0.0,
        })
    if "power" in services:
        for t in power_tasks((lead["minutes_to_impact"] / 60) if lead else 2.5):
            if t["id"] not in seen:
                tasks.append(t)
                seen.add(t["id"])
    if "flood" in services:
        for t in flood_tasks():
            if t["id"] not in seen:
                tasks.append(t)
                seen.add(t["id"])
    if "heat" in services:
        for t in heat_tasks():
            if t["id"] not in seen:
                tasks.append(t)
                seen.add(t["id"])
    if "transport" in services:
        for t in transport_tasks():
            if t["id"] not in seen:
                tasks.append(t)
                seen.add(t["id"])
    if "food" in services:
        tasks.append({"id": "freeze_water_bottles", "icon": "🧊",
                      "title": "Freeze 2 litres in bottles",
                      "detail": "Frozen bottles keep the fridge cold and give you cold water to drink.",
                      "minutes": 3, "xp": 10, "action": "food_stock", "value_rand": 60.0})
    if not tasks:
        tasks = [{
            "id": "drill", "icon": "✅", "title": "Nothing urgent — run a 5-minute drill",
            "detail": "Quiet weeks are the best weeks to prepare. Practise your plan while it's calm.",
            "minutes": 5, "xp": 45, "action": "drill", "value_rand": 0.0,
        }]
    total_min = sum(t["minutes"] for t in tasks)
    return {
        "minutes_left": minutes_left,
        "tasks_minutes": total_min,
        "fits": total_min <= minutes_left,
        "tasks": tasks,
        "value_at_stake_rand": round(sum(t.get("value_rand", 0) for t in tasks), 2),
        "xp_available": sum(t.get("xp", 0) for t in tasks),
    }


def risk_index(threats: list[dict]) -> int:
    if not threats:
        return 4
    score = 0.0
    for t in threats:
        w = {"critical": 42, "high": 26, "medium": 12, "low": 5}[t.get("severity", "low")]
        imminence = 1.0 if t["minutes_to_impact"] <= 60 else 0.7 if t["minutes_to_impact"] <= 360 else 0.45
        score += w * imminence * float(t.get("confidence", 0.5))
    return int(max(2, min(98, round(score))))


def headline(threats: list[dict]) -> str:
    if not threats:
        return "No disruption expected in your area in the next 24 hours."
    t = threats[0]
    mins = t["minutes_to_impact"]
    when = "now" if mins <= 0 else (f"in {mins//60} h {mins%60} min" if mins >= 60 else f"in {mins} min")
    return f"{t['title']} — {when}."
