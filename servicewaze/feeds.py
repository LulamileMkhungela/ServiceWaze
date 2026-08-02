"""Merged data layer for ServiceWaze.

Pulls from multiple public sources and normalises everything into ONE item shape:
    {id, type, category, source, title, body, url, time, areas}

Sources:
  - Google News RSS (SA edition)  : 6 category queries -> merged news from hundreds of publishers
  - Citizen RSS                   : general SA news
  - BusinessTech RSS              : business/tech/economy news
  - Mastodon public API           : social posts by hashtag (works keyless)
  - Open-Meteo Air Quality        : keyless AQI

Every source degrades gracefully (fail = empty, never an error).
"""
import hashlib
import html as html_mod
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) ServiceWaze/1.0"}
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "servicewaze.db")
REFRESH_SECONDS = 900  # 15 min

# --------------------------------------------------------------------------
# DB cache (dedupe + freshness)
# --------------------------------------------------------------------------
def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS items(
        hash TEXT PRIMARY KEY, type TEXT, category TEXT, source TEXT,
        title TEXT, body TEXT, url TEXT, time TEXT, raw TEXT, fetched REAL)""")
    return con

def _cache_get(stale_ok=True):
    con = _db()
    rows = con.execute("SELECT type,category,source,title,body,url,time,hash,raw FROM items").fetchall()
    con.close()
    out = []
    for r in rows:
        title, body = r[3], r[4]
        official = False
        try:
            official = bool(json.loads(r[8] or "{}").get("official"))
        except Exception:
            pass
        out.append({"id": r[7][:12], "type": r[0], "category": r[1], "source": r[2],
                    "title": title, "body": body, "url": r[5], "time": r[6],
                    "official": official,
                    "areas": tag_areas(title, body)})
    return out

def _cache_store(items, fetched):
    con = _db()
    for it in items:
        h = hashlib.sha1((it["url"] + "|" + it["title"]).encode()).hexdigest()
        con.execute("""INSERT OR REPLACE INTO items(hash,type,category,source,title,body,url,time,raw,fetched)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (h, it["type"], it["category"], it["source"], it["title"], it["body"],
                     it["url"], it["time"], json.dumps(it), fetched))
    con.execute("DELETE FROM items WHERE fetched < ?", (time.time() - 2 * 3600,))
    con.commit()
    con.close()

def _last_fetch():
    con = _db()
    row = con.execute("SELECT MAX(fetched) FROM items").fetchone()
    con.close()
    return row[0] or 0

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html_mod.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:600]

def _ago(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().isoformat(timespec="seconds")
    except Exception:
        return iso

# --------------------------------------------------------------------------
# Category classifier
# --------------------------------------------------------------------------
CAT_KEYWORDS = {
    "electricity": ["loadshedding", "load shedding", "eskom", "city power", "electricity", "power cut",
                    "power outage", "stage 6", "stage 4", "stage 2", "energy crisis", "nuclear", "megawatt", "mw", "grid"],
    "water": ["water", "rand water", "dam level", "reservoir", "water tanker", "sewage", "sewer", "drought",
              "borehole", "water outage", "water crisis", "water supply", "purify"],
    "weather": ["storm", "flood", "flooding", "heatwave", "heat wave", "cold front", "snow", "hail", "tornado",
                "weather", "heavy rain", "gale", "disaster", "wildfire", "fire danger", "snowfall", "rainfall"],
    "transport": ["taxi", "strike", "gautrain", "prasa", "metrorail", "rail", "bus ", "road closure", "traffic",
                  "n1 ", "n2 ", "n3 ", "n4 ", "n12", "bridge", "flight", "airport", "bike lane", "roadworks",
                  "rea vaya", "myciti", "brt", "shutdown", "sanral"],
    "safety": ["crime", "police", "murder", "robbery", "hijack", "gbv", "gender-based", "assault", "rape",
               "shooting", "gang", "protest", "looting", "arson", "kidnap"],
    "economy": ["spaza", "jobs", "unemployment", "economy", "rand", "petrol", "inflation", "shop", "retail",
                "funding", "grant", "sassa", "business", "small business", "interest rate", "vat", "tariff"],
}

# Strict relevance gate: the newsfeed must only contain stories about what the app
# does (services, outages, weather, transport, safety, household economy) — not
# generic/world/sport/celebrity news. An item passes if ANY token appears in title+body.
ON_TOPIC = [
    # electricity / energy
    "eskom", "city power", "electricity", "load shedding", "loadshedding", "load reduction",
    "power cut", "power outage", "power failure", "blackout", "energy", "grid", "transformer",
    "substation", "solar", "stage 6", "stage 4", "stage 2", "megawatt",
    # water
    "water", "rand water", "dam", "reservoir", "sewer", "sewage", "drain", "borehole", "drought",
    "tanker", "burst pipe", "purification", "water outage", "water crisis", "water supply",
    # weather / disasters
    "storm", "flood", "flooding", "heatwave", "heat wave", "cold front", "snow", "hail", "tornado",
    "thunderstorm", "heavy rain", "rainfall", "gale", "wildfire", "fire danger", "firefighters",
    "weather warning", "extreme weather", "temperature", "frost", "icy", "disaster management", "ndmc", "saws ",
    # transport
    "taxi", "gautrain", "prasa", "metrorail", "rail", "road closure", "roadworks", "traffic",
    "bridge", "flight", "airport", "rea vaya", "myciti", "brt", "shutdown", "sanral", "n3 ",
    "n1 ", "n2 ", "road ",
    # safety / emergency
    "police", "saps", "crime", "murder", "robbery", "hijack", "gbv", "gender-based violence",
    "assault", "rape", "shooting", "gang", "protest", "looting", "arson", "kidnap", "emergency",
    "ambulance", "childline", "10111", "112 ", "gbv command centre",
    # municipal / government services
    "municipal", "municipality", "service delivery", "ward councillor", "city of johannesburg",
    "city of cape town", "tshwane", "ekurhuleni", "infrastructure", "maintenance", "outage",
    "outages", "sassa", "social grant", "vat", "tariff",
    # household economy
    "petrol", "fuel price", "inflation", "interest rate", "small business", "spaza", "retail",
    "jobs", "unemployment", "food price", "economy",
]

def on_topic(title, body=""):
    text = (" " + title.lower() + " " + (body or "").lower() + " ")
    for tok in ON_TOPIC:
        if tok in text:
            return True
    return False

def classify(title, body=""):
    text = (title + " " + body).lower()
    scores = {}
    for cat, kws in CAT_KEYWORDS.items():
        s = 0
        for kw in kws:
            if kw in text:
                s += 1
        if s:
            scores[cat] = s
    return max(scores, key=scores.get) if scores else "other"

# --------------------------------------------------------------------------
# Area relevance (match item against user's saved areas / SA regions)
# --------------------------------------------------------------------------
REGION_TOKENS = {
    "gauteng": ["gauteng", "joburg", "johannesburg", "jhb", "pretoria", "tshwane", "ekurhuleni", "soweto",
                "sandton", "randburg", "alexandra", "midrand", "roodepoort", "lenasia", "centurion", "krugersdorp",
                "benoni", "boksburg", "germiston", "kempton", "vanderbijlpark", "vereeniging"],
    "western cape": ["cape town", "western cape", "stellenbosch", "paarl", "george", "knysna", "myciti", "atlantic seaboard"],
    "kwa-zulu natal": ["durban", "kzn", "kwa-zulu", "kwazulu", "ethekwini", "pietermaritzburg", "richards bay", "newcastle", "ladysmith", "umhlanga"],
    "eastern cape": ["gqeberha", "port elizabeth", "east london", "buffalo city", "nelson mandela bay", "makhanda", "eastern cape", "king william"],
    "free state": ["bloemfontein", "mangaung", "free state", "welkom", "bethlehem"],
    "limpopo": ["polokwane", "limpopo", "thohoyandou", "lepelle", "musina"],
    "mpumalanga": ["nelspruit", "mbombela", "mpumalanga", "witbank", "emalahleni", "secunda", "middelburg"],
    "north west": ["rustenburg", "mahikeng", "north west", "klerksdorp", "potchefstroom", "brits"],
    "northern cape": ["kimberley", "northern cape", "upington", "kuruman"],
    "south africa": ["south africa", "south african", "sa ", "sa's", "national", "countrywide", "nationwide",
                     "ramaphosa", "president", "rand water", "eskom", "saps", "prasa", "sassa", "sabc",
                     "sanral", "parliament", "treasury", "load reduction"],
}

def tag_areas(title, body=""):
    text = (title + " " + body).lower()
    hits = []
    for region, toks in REGION_TOKENS.items():
        for t in toks:
            if t in text:
                hits.append(region)
                break
    return hits

# --------------------------------------------------------------------------
# Source adapters
# --------------------------------------------------------------------------
def _fetch_rss(url, limit=25, label=None):
    try:
        import feedparser
        r = feedparser.parse(requests.get(url, headers=UA, timeout=12).content)
        items = []
        for e in r.entries[:limit]:
            title = _clean(e.get("title", ""))
            if not title:
                continue
            items.append({
                "type": "news", "source": label or (r.feed.get("title", "News")),
                "category": classify(title),
                "title": title[:160],
                "body": _clean(e.get("summary", ""))[:300],
                "url": e.get("link", ""),
                "time": _ago(e.get("published", e.get("updated", ""))),
            })
        return items
    except Exception:
        return []

def fetch_google_news():
    """6 category queries merged — hundreds of SA publishers in one feed."""
    queries = {
        "electricity": "load shedding OR eskom OR city power South Africa",
        "water": "water outage OR rand water OR dam levels South Africa",
        "transport": "taxi strike OR gautrain OR prasa OR metrorail South Africa",
        "weather": "storm OR flood OR heatwave OR cold front South Africa",
        "safety": "crime OR police OR GBV South Africa",
        "economy": "spaza OR small business OR jobs OR unemployment South Africa",
    }
    items = []
    for cat, q in queries.items():
        url = ("https://news.google.com/rss/search?q=" + requests.utils.quote(q) +
               "&hl=en-ZA&gl=ZA&ceid=ZA:en")
        try:
            import feedparser
            r = feedparser.parse(requests.get(url, headers=UA, timeout=12).content)
            for e in r.entries[:8]:
                title = _clean(e.get("title", ""))
                if not title:
                    continue
                # Google News titles look like "Headline - Publisher"
                src = e.get("source", {}).get("title", "") if isinstance(e.get("source"), dict) else ""
                if src and title.endswith(" - " + src):
                    title = title[: -(len(src) + 3)]
                items.append({
                    "type": "news", "source": src or "Google News",
                    "category": cat, "title": title[:160],
                    "body": _clean(e.get("summary", ""))[:200],
                    "url": e.get("link", ""),
                    "time": _ago(e.get("published", "")),
                })
        except Exception:
            continue
    return items

def fetch_mastodon():
    tags = {"loadshedding": "electricity", "randwater": "water", "gautrain": "transport",
            "floods": "weather", "taxi": "transport", "eskom": "electricity",
            "wateroutage": "water", "citypower": "electricity", "loadreduction": "electricity",
            "metrorail": "transport", "prasa": "transport", "saws": "weather",
            "johannesburgwater": "water", "myciti": "transport", "reavaya": "transport",
            "gauteng": "other"}
    items = []
    for tag, cat in tags.items():
        try:
            r = requests.get(f"https://mastodon.social/api/v1/timelines/tag/{tag}?limit=8",
                             headers=UA, timeout=10)
            for p in r.json():
                text = _clean(p.get("content", "")) or _clean(p.get("text", ""))
                if not text:
                    continue
                if not _sa_relevant(text):
                    continue  # drop non-South-Africa social noise
                acct = p.get("account", {}).get("acct", "mastodon")
                items.append({
                    "type": "social", "source": "@" + acct,
                    "category": cat, "title": text[:140],
                    "body": text[:280],
                    "url": p.get("uri", ""),
                    "time": _ago(p.get("created_at", "")),
                    "official": False,
                })
        except Exception:
            continue
    return items

def fetch_jw_water():
    """Scrape Johannesburg Water's official RSS feed (no API exists) for water
    notices & outages. WordPress feed — reliable, includes outages/maintenance."""
    items = []
    try:
        import feedparser
        r = feedparser.parse(requests.get("https://www.johannesburgwater.co.za/feed/",
                                          headers=UA, timeout=12).content)
        for e in r.entries[:15]:
            title = _clean(e.get("title", ""))
            if not title:
                continue
            if not any(k in title.lower() for k in ["water", "outage", "maintenance",
                                                    "supply", "interruption", "reservoir",
                                                    "pipe", "notice"]):
                continue
            body = _clean(e.get("summary", ""))[:250]
            items.append({
                "type": "news", "source": "Johannesburg Water (official)",
                "category": "water",
                "title": title[:160],
                "body": body,
                "url": e.get("link", ""),
                "time": _ago(e.get("published", e.get("updated", ""))),
                "official": True,
            })
    except Exception:
        pass
    return items

SA_TOKENS = ["south africa", "south african", "eskom", "rand water", "randwater", "gauteng", "joburg",
             "johannesburg", "pretoria", "tshwane", "durban", "ethekwini", "cape town", "soweto", "alexandra",
             "gautrain", "prasa", "saps", "sassa", "sabc", "ewn", "weathersa", "ramaphosa",
             "santaco", "mzansi", "emfuleni", "ekurhuleni", "kzn", "kwazulu", "kwa-zulu", "sanral",
             "parliament", "load reduction", "vuk uzenzele"]

import re as _re

def _sa_relevant(text):
    t = (" " + text.lower() + " ")
    if _re.search(r"[łżąćęśńź]", t):
        return False  # Polish text ("prasa" = press in Polish, not our PRASA)
    for tok in SA_TOKENS:
        if tok in t:
            return True
    return False

# --------------------------------------------------------------------------
# Public entry point: merged feed, always fresh enough
# --------------------------------------------------------------------------
def get_feed(areas=None, categories=None, q=None, limit=80, types=None):
    if time.time() - _last_fetch() > REFRESH_SECONDS:
        merged = []
        merged += fetch_google_news()
        merged += _fetch_rss("https://citizen.co.za/feed/", limit=20, label="The Citizen")
        merged += _fetch_rss("https://businesstech.co.za/news/feed/", limit=20, label="BusinessTech")
        merged += fetch_jw_water()          # official water notices (scrape, no API exists)
        merged += fetch_mastodon()          # social updates (hashtags, SA-filtered)
        seen = set()
        deduped = []
        for it in merged:
            k = (it["title"].lower()[:80], it["source"])
            if k in seen:
                continue
            seen.add(k)
            if not on_topic(it["title"], it.get("body", "")):
                continue  # keep the newsfeed strictly about what the app does (news AND social)
            it["areas"] = tag_areas(it["title"], it.get("body", ""))
            deduped.append(it)
        _cache_store(deduped, time.time())

    items = _cache_get()
    if types:
        items = [i for i in items if i["type"] in types]
    if categories:
        cats = set(categories)
        items = [i for i in items if i["category"] in cats]
    if areas:
        wanted = set(a.strip().lower() for a in areas if a.strip())
        items = [i for i in items
                 if wanted & set(i.get("areas", []))
                 or ("south africa" in i.get("areas", []) and "south africa" not in wanted)]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["title"].lower() or ql in i.get("body", "").lower()]
    items.sort(key=lambda i: i.get("time", ""), reverse=True)
    return items[:limit]

def feed_meta():
    return {"cached_items": len(_cache_get()), "last_fetch": _last_fetch(),
            "refresh_seconds": REFRESH_SECONDS}

# --------------------------------------------------------------------------
# Air quality (Open-Meteo, keyless) — cached 30 min
# --------------------------------------------------------------------------
_air_cache = {}
def get_air(lat, lon):
    key = (round(lat, 2), round(lon, 2))
    if key in _air_cache and time.time() - _air_cache[key][0] < 1800:
        return _air_cache[key][1]
    try:
        r = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality",
                         params={"latitude": lat, "longitude": lon,
                                 "current": "us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide",
                                 "timezone": "Africa/Johannesburg"}, headers=UA, timeout=12)
        c = r.json().get("current", {})
        aqi = c.get("us_aqi")
        if aqi is None:
            return None
        if aqi <= 50: label, band = "Good", "good"
        elif aqi <= 100: label, band = "Moderate", "moderate"
        elif aqi <= 150: label, band = "Unhealthy (sensitive)", "warn"
        elif aqi <= 200: label, band = "Unhealthy", "severe"
        else: label, band = "Very unhealthy", "severe"
        out = {"aqi": aqi, "label": label, "band": band,
               "pm2_5": c.get("pm2_5"), "pm10": c.get("pm10"),
               "o3": c.get("ozone"), "no2": c.get("nitrogen_dioxide"),
               "so2": c.get("sulphur_dioxide"), "co": c.get("carbon_monoxide"),
               "source": "Open-Meteo Air Quality"}
        _air_cache[key] = (time.time(), out)
        return out
    except Exception:
        return None

# --------------------------------------------------------------------------
# Services directory (curated, verified Aug 2026) + emergency numbers
# --------------------------------------------------------------------------
SERVICES = {
    "electricity": {
        "title": "Electricity",
        "icon": "⚡",
        "items": [
            {"name": "Eskom (national)", "type": "call", "value": "0860 037 566", "note": "Faults & load-shedding queries"},
            {"name": "Eskom load-shedding status", "type": "link", "value": "https://loadshedding.eskom.co.za", "note": "Official status page"},
            {"name": "City Power (Johannesburg)", "type": "call", "value": "0860 562 874", "note": "Faults"},
            {"name": "City of Cape Town", "type": "call", "value": "0860 103 089", "note": "Electricity faults"},
            {"name": "eThekwini Electricity", "type": "call", "value": "0800 311 1111", "note": "Durban metro"},
            {"name": "Tshwane Electricity", "type": "call", "value": "012 358 9999", "note": "Pretoria metro"},
            {"name": "Ekurhuleni", "type": "call", "value": "0860 543 000", "note": "East Rand metro"},
        ]},
    "water": {
        "title": "Water",
        "icon": "🚰",
        "items": [
            {"name": "Johannesburg Water", "type": "call", "value": "0860 562 874", "note": "Faults (24h)"},
            {"name": "Johannesburg Water WhatsApp", "type": "whatsapp", "value": "0797691333", "note": "SMS/WhatsApp logged faults"},
            {"name": "Johannesburg Water", "type": "link", "value": "https://www.johannesburgwater.co.za", "note": "Outage notices"},
            {"name": "Rand Water", "type": "link", "value": "https://www.randwater.co.za", "note": "Bulk supply & maintenance"},
            {"name": "Cape Town Water", "type": "call", "value": "0860 103 089", "note": "Faults"},
            {"name": "eThekwini Water", "type": "call", "value": "0800 131 3013", "note": "Durban metro"},
            {"name": "Tshwane Water", "type": "call", "value": "012 358 9999", "note": "Pretoria metro"},
            {"name": "Ekurhuleni Water", "type": "call", "value": "0860 543 000", "note": "East Rand metro"},
            {"name": "Nelson Mandela Bay", "type": "link", "value": "https://www.nelsonmandelabay.gov.za", "note": "Gqeberha water updates"},
        ]},
    "transport": {
        "title": "Transport",
        "icon": "🚌",
        "items": [
            {"name": "Gautrain", "type": "call", "value": "0800 428 7246", "note": "Call centre"},
            {"name": "Gautrain live departures", "type": "link", "value": "https://www.gautrain.co.za", "note": "App + web"},
            {"name": "Prasa / Metrorail", "type": "link", "value": "https://www.prasa.com", "note": "Service notices"},
            {"name": "Rea Vaya (Joburg BRT)", "type": "link", "value": "https://www.reavaya.org.za", "note": "Routes & disruptions"},
            {"name": "MyCiTi (Cape Town)", "type": "link", "value": "https://www.myciti.org.za", "note": "Routes & disruptions"},
            {"name": "JRA roadworks", "type": "link", "value": "https://www.jra.org.za", "note": "Joburg roads"},
            {"name": "SANRAL", "type": "link", "value": "https://www.sanral.co.za", "note": "National roads & tolls"},
        ]},
    "weather": {
        "title": "Weather & Disasters",
        "icon": "🌦️",
        "items": [
            {"name": "SA Weather Service", "type": "link", "value": "https://www.weathersa.co.za", "note": "Official warnings"},
            {"name": "SAWS WhatsApp", "type": "whatsapp", "value": "0636060001", "note": "Official warning line"},
        ]},
    "emergency": {
        "title": "Emergency & Safety",
        "icon": "🆘",
        "items": [
            {"name": "SAPS (police)", "type": "call", "value": "10111", "note": "Emergencies"},
            {"name": "Mobile emergency (all networks)", "type": "call", "value": "112", "note": "Works without airtime"},
            {"name": "Ambulance / Fire (varies by province)", "type": "call", "value": "10177", "note": "Check your province"},
            {"name": "GBV Command Centre", "type": "call", "value": "0800 428 428", "note": "Gender-based violence, 24h, free"},
            {"name": "Crime Stop", "type": "call", "value": "08600 10111", "note": "Anonymous crime tip-offs"},
            {"name": "Childline", "type": "call", "value": "116", "note": "Free, 24h"},
            {"name": "Disaster Management (national)", "type": "link", "value": "https://www.ndmc.gov.za", "note": "NDMC"},
        ]},
}

CHECKLISTS = {
    "water_outage": {
        "title": "During a water outage",
        "steps": [
            "Store water in clean containers BEFORE the outage (bath tubs, buckets, bottles).",
            "Boil stored water before drinking if the outage is unplanned.",
            "Report the outage to your municipality — every report counts.",
            "Don't open taps repeatedly — airlocks slow restoration.",
            "Check for tanker schedules in your area; share locations on the app.",
        ]},
    "load_shedding": {
        "title": "During load-shedding / power cuts",
        "steps": [
            "Keep phones and power banks charged before the cut.",
            "Unplug sensitive electronics to protect against surges when power returns.",
            "Keep fridge doors closed to preserve food (lasts 4-6 hours).",
            "Use LED lights / solar lanterns — never candles near flammable material.",
            "Report extended outages (longer than the schedule) to your supplier.",
        ]},
    "storm_flood": {
        "title": "During storms & floods",
        "steps": [
            "Never walk or drive through flooded roads or bridges — turn around.",
            "Move valuables and livestock to high ground early.",
            "Stay indoors during lightning; unplug electronics.",
            "Keep emergency numbers saved: 10111, 112, 10177.",
            "Check on elderly neighbours and children.",
        ]},
    "heatwave": {
        "title": "During extreme heat",
        "steps": [
            "Drink water regularly — don't wait until you're thirsty.",
            "Stay out of the sun between 11:00-15:00.",
            "Never leave children or pets in parked cars.",
            "Check on the elderly, infants and outdoor workers.",
            "Watch for signs of heatstroke: confusion, rapid pulse, no sweating.",
        ]},
}
