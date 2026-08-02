"""Data source adapters for ServiceWaze.
Every adapter degrades gracefully: if a source is unreachable or unconfigured,
we return None / empty data rather than failing the whole request.

Sources:
  - Open-Meteo (weather + geocoding)  : free, no key
  - Eskom GetStatus                   : free, no key (load-shedding stage)
  - EskomSePush API                   : free, needs ESP_API_TOKEN env var (optional)
  - Crowd reports (local sqlite)      : our own verified community layer
"""
import math
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import requests

UA = {"User-Agent": "ServiceWaze/1.0 (community status hub; contact: admin@localhost)"}
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "servicewaze.db")

# --------------------------------------------------------------------------
# Geocoding (Open-Meteo, keyless)
# --------------------------------------------------------------------------
def geocode(query: str, count: int = 6):
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": count, "language": "en", "format": "json"},
            headers=UA, timeout=10,
        )
        j = r.json()
        results = []
        for item in j.get("results", []):
            if item.get("country_code") != "ZA":
                continue
            results.append({
                "name": item.get("name"),
                "admin1": item.get("admin1", ""),
                "admin2": item.get("admin2", ""),
                "lat": item.get("latitude"),
                "lon": item.get("longitude"),
            })
        return results
    except Exception:
        return []

# --------------------------------------------------------------------------
# Weather (Open-Meteo, keyless)
# --------------------------------------------------------------------------
WMO = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"), 45: ("Fog", "🌫️"), 48: ("Depositing rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"), 55: ("Dense drizzle", "🌧️"),
    56: ("Freezing drizzle", "🌧️"), 57: ("Dense freezing drizzle", "🌧️"),
    61: ("Light rain", "🌧️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🌧️"), 67: ("Heavy freezing rain", "⛈️"),
    71: ("Light snow", "❄️"), 73: ("Snow", "❄️"), 75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "❄️"), 80: ("Light showers", "🌦️"), 81: ("Showers", "🌧️"),
    82: ("Violent showers", "⛈️"), 85: ("Snow showers", "❄️"), 86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm with hail", "⛈️"), 99: ("Severe thunderstorm with hail", "⛈️"),
}

def _advise(daily):
    advisories = []
    for d in daily:
        date = d["date"]
        if d["tmax"] >= 35:
            advisories.append({"level": "severe", "icon": "🥵", "text": f"Extreme heat {d['tmax']:.0f}°C on {date} — stay hydrated, check the elderly and infants."})
        elif d["tmax"] >= 32:
            advisories.append({"level": "warn", "icon": "🌡️", "text": f"Hot day {d['tmax']:.0f}°C on {date} — plan outdoor work for early morning."})
        if d["tmin"] <= 2:
            advisories.append({"level": "warn", "icon": "🥶", "text": f"Cold night ({d['tmin']:.0f}°C) on {date} — protect the vulnerable, watch for frost."})
        if d["precip_prob"] >= 60 and d["precip_sum"] >= 20:
            level = "severe" if d["precip_sum"] >= 40 else "warn"
            advisories.append({"level": level, "icon": "🌊", "text": f"Heavy rain risk {d['precip_prob']:.0f}% ({d['precip_sum']:.0f}mm) on {date} — low-lying and informal settlements may flood; don't cross flooded roads/bridges."})
        if d["gusts"] >= 60:
            advisories.append({"level": "warn", "icon": "💨", "text": f"Strong gusts up to {d['gusts']:.0f} km/h on {date} — secure loose structures, be careful near trees."})
    return advisories

def weather(lat, lon):
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_gusts_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_gusts_10m_max,uv_index_max,sunrise,sunset",
                "forecast_days": 3, "timezone": "Africa/Johannesburg",
            },
            headers=UA, timeout=12,
        )
        j = r.json()
        cur = j.get("current", {})
        code = cur.get("weather_code", 0)
        desc, icon = WMO.get(code, ("Unknown", "🌡️"))
        daily = []
        for i, day in enumerate(j.get("daily", {}).get("time", [])):
            sr = j["daily"].get("sunrise", [None] * 10)[i]
            ss = j["daily"].get("sunset", [None] * 10)[i]
            daily.append({
                "date": day[5:],
                "code": j["daily"]["weather_code"][i],
                "icon": WMO.get(j["daily"]["weather_code"][i], ("", "🌡️"))[1],
                "tmax": j["daily"]["temperature_2m_max"][i],
                "tmin": j["daily"]["temperature_2m_min"][i],
                "precip_prob": j["daily"]["precipitation_probability_max"][i],
                "precip_sum": j["daily"]["precipitation_sum"][i],
                "gusts": j["daily"]["wind_gusts_10m_max"][i],
                "sunrise": sr[11:16] if sr else None,
                "sunset": ss[11:16] if ss else None,
            })
        return {
            "current": {
                "temp": cur.get("temperature_2m"),
                "feels": cur.get("apparent_temperature"),
                "humidity": cur.get("relative_humidity_2m"),
                "wind": cur.get("wind_speed_10m"),
                "gusts": cur.get("wind_gusts_10m"),
                "desc": desc, "icon": icon,
            },
            "daily": daily,
            "advisories": _advise(daily),
            "source": "Open-Meteo",
        }
    except Exception:
        return None

# --------------------------------------------------------------------------
# Reverse geocoding (Nominatim, free — cached + throttled)
# --------------------------------------------------------------------------
_rev_cache = {}
_last_nom = [0.0]

def reverse_geocode(lat, lon):
    key = (round(lat, 4), round(lon, 4))
    if key in _rev_cache and time.time() - _rev_cache[key][0] < 24 * 3600:
        return _rev_cache[key][1]
    now = time.time()
    if now - _last_nom[0] < 1.1:
        time.sleep(1.1 - (now - _last_nom[0]))
    _last_nom[0] = time.time()
    try:
        r = requests.get("https://nominatim.openstreetmap.org/reverse",
                         params={"lat": lat, "lon": lon, "format": "json", "zoom": 16,
                                 "addressdetails": 1},
                         headers=UA, timeout=10)
        j = r.json()
        a = j.get("address", {})
        name = (a.get("suburb") or a.get("neighbourhood") or a.get("town")
                or a.get("city") or a.get("village") or a.get("hamlet") or "My location")
        state = a.get("state", "")
        out = {"name": name, "state": state,
               "display": f"{name}, {state}" if state else name}
        _rev_cache[key] = (time.time(), out)
        return out
    except Exception:
        return {"name": "My location", "state": "", "display": "My location"}

# --------------------------------------------------------------------------
# Rain radar (RainViewer, free keyless)
# --------------------------------------------------------------------------
_radar_cache = {}

def radar(lat, lon, zoom=7):
    global _radar_cache
    if _radar_cache and time.time() - _radar_cache[0] < 5 * 60:
        manifest = _radar_cache[1]
    else:
        try:
            m = requests.get("https://api.rainviewer.com/public/weather-maps.json",
                             headers=UA, timeout=10).json()
            manifest = {"host": m.get("host"), "radar": m.get("radar", {}),
                        "generated": m.get("generated")}
            _radar_cache = (time.time(), manifest)
        except Exception:
            return None
    frames = manifest.get("radar", {})
    past = frames.get("past", [])
    nowcast = frames.get("nowcast", [])
    latest = (nowcast[-1] if nowcast else None) or (past[-1] if past else None)
    if not latest:
        return None
    path = latest["path"]
    t = latest["time"]
    # slippy tile coords at zoom
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    tile = f"{manifest['host']}{path}/512/{zoom}/{x}/{y}/2/1_1.png"
    from datetime import datetime as _dt, timezone as _tz
    return {
        "time": t, "tile": tile,
        "label": _dt.fromtimestamp(t, _tz.utc).strftime("%H:%M"),
        "host": manifest["host"], "path": path,
        "source": "RainViewer",
    }

# --------------------------------------------------------------------------
# Electricity (Eskom status endpoint, keyless; ESP API optional)
# --------------------------------------------------------------------------
_eskom_cache = {"t": 0, "val": None}

def eskom_status():
    # last-known-good cache (5 min) — Eskom's endpoint is occasionally flaky
    if time.time() - _eskom_cache["t"] < 300 and _eskom_cache["val"] is not None:
        return _eskom_cache["val"]
    try:
        r = requests.get("https://loadshedding.eskom.co.za/loadshedding/GetStatus", headers=UA, timeout=8)
        raw = r.text.strip()
        try:
            stage = int(raw)
        except ValueError:
            stage = None
        if stage is None:
            out = {"stage": "unknown", "label": "Status unavailable", "source": "Eskom"}
        elif stage in (-1, 0):
            out = {"stage": 0, "label": "No load-shedding", "source": "Eskom"}
        else:
            out = {"stage": stage, "label": f"Stage {stage}", "source": "Eskom"}
        _eskom_cache.update({"t": time.time(), "val": out})
        return out
    except Exception:
        if _eskom_cache["val"] is not None:
            return _eskom_cache["val"]  # serve last known good on failure
        return {"stage": "unknown", "label": "Status unavailable", "source": "Eskom"}

def eskomsepush_status():
    token = os.environ.get("ESP_API_TOKEN")
    if not token:
        return None
    try:
        r = requests.get("https://api.eskomsepush.org/status", headers={"token": token}, timeout=8)
        j = r.json().get("status", {})
        return {"stage": j.get("stage", "unknown"), "updated": j.get("updated"), "source": "EskomSePush"}
    except Exception:
        return None

# --------------------------------------------------------------------------
# Per-area load-shedding SCHEDULE via the free EskomSePush API (ESP model,
# optional). Lights up when ESP_API_TOKEN is set; degrades gracefully.
# Results are cached 12h to avoid hammering the API.
# --------------------------------------------------------------------------
_sched_cache = {}

def esp_area_schedule(q: str, lat=None, lon=None, force=False):
    """Return today's/tomorrow's load-shedding windows for a place, or None."""
    token = os.environ.get("ESP_API_TOKEN")
    if not token:
        return None
    key = (q.strip().lower(), round(lat or 0, 2), round(lon or 0, 2))
    if not force and key in _sched_cache and time.time() - _sched_cache[key][0] < 12 * 3600:
        return _sched_cache[key][1]
    try:
        h = {"token": token}
        area = None
        if lat is not None and lon is not None:
            r = requests.get("https://api.eskomsepush.org/areas_nearby",
                             params={"latitude": lat, "longitude": lon}, headers=h, timeout=8)
            areas = r.json().get("areas", [])
            if areas:
                area = areas[0]
        if area is None:
            r = requests.get("https://api.eskomsepush.org/areas_search",
                             params={"text": q}, headers=h, timeout=8)
            areas = r.json().get("areas", [])
            if areas:
                area = areas[0]
        if area is None:
            return None
        r = requests.get(f"https://api.eskomsepush.org/area_information/{area['id']}/allowance",
                         headers=h, timeout=8)
        j = r.json()
        events = []
        for ev in j.get("events", [])[:40]:
            events.append({
                "start": ev.get("start"), "end": ev.get("end"),
                "stage": ev.get("stage"), "note": ev.get("note", ""),
            })
        out = {"area": area.get("name"), "area_id": area.get("id"), "events": events,
               "source": "EskomSePush API"}
        _sched_cache[key] = (time.time(), out)
        return out
    except Exception:
        return None

def next_windows(schedule, stage=None, now=None, horizon_days=7):
    """Return upcoming windows from a schedule (sorted), optionally filtered by stage.
    Events carry ISO start/end; windows in the past are dropped."""
    if not schedule or not schedule.get("events"):
        return []
    from datetime import datetime, timedelta, timezone
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(days=horizon_days)
    wins = []
    for ev in schedule["events"]:
        try:
            start = datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(ev["end"].replace("Z", "+00:00"))
        except Exception:
            continue
        if end <= now or start > horizon:
            continue
        if stage is not None and ev.get("stage") not in (None, stage, str(stage)):
            continue
        wins.append({"start": start.isoformat(), "end": end.isoformat(),
                     "stage": ev.get("stage")})
    wins.sort(key=lambda w: w["start"])
    return wins

# --------------------------------------------------------------------------
# ESP Business API — full client (all documented v2/v3 endpoints).
# Requires ESP_API_TOKEN. Covers: /status, /areas_search, /areas_nearby,
# /area_information/{id}/allowance (schedules) and /area_information/{id}/event.
# --------------------------------------------------------------------------
_esp_area_cache = {}

def esp_area_id(q: str, lat=None, lon=None):
    """Resolve a place to its ESP area ID (searches + nearby), cached 24h."""
    key = (q.strip().lower(), round(lat or 0, 2), round(lon or 0, 2))
    if key in _esp_area_cache and time.time() - _esp_area_cache[key][0] < 24 * 3600:
        return _esp_area_cache[key][1]
    token = os.environ.get("ESP_API_TOKEN")
    if not token:
        return None
    h = {"token": token}
    area = None
    try:
        if lat is not None and lon is not None:
            r = requests.get("https://api.eskomsepush.org/areas_nearby",
                             params={"latitude": lat, "longitude": lon}, headers=h, timeout=8)
            areas = r.json().get("areas", [])
            if areas:
                area = areas[0]
        if area is None and q.strip():
            r = requests.get("https://api.eskomsepush.org/areas_search",
                             params={"text": q.strip()}, headers=h, timeout=8)
            areas = r.json().get("areas", [])
            if areas:
                area = areas[0]
    except Exception:
        return None
    if area is None:
        return None
    out = {"id": area["id"], "name": area.get("name")}
    _esp_area_cache[key] = (time.time(), out)
    return out

def esp_area_events(q: str, lat=None, lon=None):
    """Future load-shedding events for an area via /area_information/{id}/event."""
    token = os.environ.get("ESP_API_TOKEN")
    area = esp_area_id(q, lat, lon)
    if not token or not area:
        return None
    try:
        r = requests.get(f"https://api.eskomsepush.org/area_information/{area['id']}/event",
                         headers={"token": token}, timeout=8)
        j = r.json()
        events = [{"start": e.get("start"), "end": e.get("end"),
                   "stage": e.get("stage")} for e in j.get("events", [])[:20]]
        return {"area": area, "events": events, "source": "EskomSePush API"}
    except Exception:
        return None

# --------------------------------------------------------------------------
# Crowd reports (sqlite)
# --------------------------------------------------------------------------
REPORT_KINDS = {"no_water", "low_pressure", "leak", "restored", "power_out", "route", "other"}

def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        area TEXT NOT NULL, lat REAL, lon REAL,
        kind TEXT NOT NULL, message TEXT, reporter TEXT,
        confirms INTEGER DEFAULT 0, created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS chat(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        area TEXT NOT NULL, lat REAL, lon REAL,
        message TEXT NOT NULL, author TEXT,
        flags INTEGER DEFAULT 0, created TEXT)""")
    con.commit()
    for col, ddl in [("photo", "TEXT"), ("audio", "TEXT"), ("audio_mime", "TEXT")]:
        try:
            con.execute(f"ALTER TABLE reports ADD COLUMN {col} {ddl}")
            con.commit()
        except Exception:
            pass
    return con

def add_report(area, kind, message="", reporter="", lat=None, lon=None):
    con = _db()
    cur = con.execute(
        "INSERT INTO reports(area, lat, lon, kind, message, reporter, confirms, created) VALUES(?,?,?,?,?,?,0,?)",
        (area, lat, lon, kind, message, reporter, datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid

def confirm_report(rid):
    con = _db()
    cur = con.execute("UPDATE reports SET confirms = confirms + 1 WHERE id = ?", (rid,))
    con.commit()
    ok = cur.rowcount == 1
    con.close()
    return ok

def attach_media(rid, photo_hex=None, audio_hex=None, audio_mime=None):
    con = _db()
    if photo_hex is not None:
        con.execute("UPDATE reports SET photo=? WHERE id=?", (photo_hex, rid))
    if audio_hex is not None:
        con.execute("UPDATE reports SET audio=?, audio_mime=? WHERE id=?", (audio_hex, audio_mime or "audio/ogg", rid))
    con.commit()
    ok = con.total_changes > 0
    con.close()
    return ok

def recent_reports(limit=60):
    con = _db()
    rows = con.execute(
        """SELECT id, area, lat, lon, kind, message, reporter, confirms, created,
                  CASE WHEN photo IS NULL OR photo='' THEN 0 ELSE 1 END,
                  audio_mime
           FROM reports ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    con.close()
    return [
        {"id": r[0], "area": r[1], "lat": r[2], "lon": r[3], "kind": r[4],
         "message": r[5], "reporter": r[6] or "anonymous", "confirms": r[7], "created": r[8],
         "has_photo": bool(r[9]), "audio_mime": r[10] or "", "has_audio": bool(r[10])}
        for r in rows
    ]

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))

def reports_for_area(lat, lon, q, radius_km=15.0):
    """Match by distance when coords exist; else by name-token overlap."""
    out = []
    q_tokens = {t for t in q.lower().split() if len(t) >= 3}
    for r in recent_reports():
        if lat is not None and lon is not None and r["lat"] is not None and r["lon"] is not None:
            if _haversine(lat, lon, r["lat"], r["lon"]) <= radius_km:
                out.append(r)
                continue
        area_tokens = {t for t in r["area"].lower().split() if len(t) >= 3}
        if q_tokens and (q_tokens & area_tokens):
            out.append(r)
    return out

# --------------------------------------------------------------------------
# Community chat (area-scoped, moderated)
# --------------------------------------------------------------------------
BAD_WORDS = ["fuck", "shit", "bitch", "cunt", "kak", "poes", "domkop", "idiot", "stupid",
             "racist", "rape ", "kill ", "bomb", "die "]

def _clean_chat(text):
    t = " ".join(text.split())[:300]
    low = t.lower()
    for w in BAD_WORDS:
        if w in low:
            t = re.sub(r"(?i)" + re.escape(w.strip()), "***", t)
    return t

def add_chat(area, message, author="", lat=None, lon=None):
    msg = _clean_chat(message)
    if len(msg) < 2:
        return None
    con = _db()
    cur = con.execute(
        "INSERT INTO chat(area, lat, lon, message, author, flags, created) VALUES(?,?,?,?,?,0,?)",
        (area, lat, lon, msg, author[:40] or "Neighbour",
         datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid

def recent_chats(limit=60):
    con = _db()
    rows = con.execute(
        "SELECT id, area, lat, lon, message, author, flags, created FROM chat "
        "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    return [{"id": r[0], "area": r[1], "lat": r[2], "lon": r[3], "message": r[4],
             "author": r[5] or "Neighbour", "flags": r[6], "created": r[7]} for r in rows]

def chats_for_area(lat, lon, q, radius_km=15.0):
    """Area-scoped chat (like reports): distance match, else token match.
    Messages flagged 3+ times are hidden."""
    out = []
    q_tokens = {t for t in q.lower().split() if len(t) >= 3}
    for c in recent_chats():
        if c["flags"] >= 3:
            continue
        if lat is not None and lon is not None and c["lat"] is not None and c["lon"] is not None:
            if _haversine(lat, lon, c["lat"], c["lon"]) <= radius_km:
                out.append(c)
                continue
        area_tokens = {t for t in c["area"].lower().split() if len(t) >= 3}
        if q_tokens and (q_tokens & area_tokens):
            out.append(c)
    return out

def report_chat(cid):
    con = _db()
    cur = con.execute("UPDATE chat SET flags = flags + 1 WHERE id = ?", (cid,))
    con.commit()
    ok = cur.rowcount == 1
    con.close()
    return ok

# --------------------------------------------------------------------------
# Static / seeded content (verified from public reporting, Aug 2026)
# --------------------------------------------------------------------------
WATER_OFFICIAL = [
    {"name": "Joburg Water fault line", "type": "call", "value": "0860 562 874", "note": "Report bursts/leaks (24h)"},
    {"name": "Joburg Water WhatsApp", "type": "whatsapp", "value": "079 769 1333", "note": "SMS/WhatsApp for logged faults"},
    {"name": "Joburg Water website", "type": "link", "value": "https://www.johannesburgwater.co.za", "note": "Outage notices & map"},
    {"name": "Rand Water", "type": "link", "value": "https://www.randwater.co.za", "note": "Bulk supply & maintenance schedules"},
    {"name": "City of Joburg", "type": "link", "value": "https://www.joburg.org.za", "note": "Municipal service updates"},
]

WATER_CONTEXT = (
    "Context (verified from public reporting, Aug 2026): Rand Water ran two winter maintenance phases "
    "in May–Jul 2026 affecting the Central, Commando, Deep South, Midrand, Randburg, Roodepoort, Sandton and "
    "Soweto systems; after phase 2 (17 Jul) supply stabilisation took several days and parts of Joburg went "
    "12+ days without water in June. Always verify current status with the official channels above."
)

ELECTRICITY_NOTE = (
    "South Africa passed 365 days without load-shedding in May 2026 and the winter outlook (Apr–Aug 2026) is "
    "stable. Note: 'load reduction' (targeted cuts) still occurs in some Gauteng areas with illegal connections "
    "or overloaded lines. Stage shown is the live national status."
)

TRANSPORT_NOTICES = [
    {"title": "No active strike notices on record", "detail": "Last major disruption: Gauteng taxi strike, July 2023 (province-wide, ~7 days).", "source": "public reporting"},
    {"title": "Rail services", "detail": "Prasa/ Gautrain run their own timetables — verify before travelling.", "source": "prasa.com / gautrain.co.za"},
]

TRANSPORT_LINKS = [
    {"name": "Gautrain", "url": "https://www.gautrain.co.za", "note": "Live departures in app"},
    {"name": "Prasa (Metrorail)", "url": "https://www.prasa.com", "note": "Service notices"},
    {"name": "JRA roadworks", "url": "https://www.jra.org.za", "note": "Road closures & repairs"},
]
