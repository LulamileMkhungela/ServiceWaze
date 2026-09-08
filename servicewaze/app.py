"""ServiceWaze — South Africa's household resilience network (PWA, v3).

Run:  uvicorn app:app --host 0.0.0.0 --port 8000
Docs: /docs  (OpenAPI)

What changed from v2 (status hub) → v3 (resilience network)
-----------------------------------------------------------
v2 answered "what is broken near me?"  v3 answers:
  * how long do I have before it hits me?        → impact.py   (Prepare Window)
  * what must I do, in the time left?            → impact.py   (task plan)
  * what will it cost me, and how do I cut it?   → tariffs.py  (money engine)
  * who near me can help, and who needs help?    → grid.py     (Ubuntu Grid)
  * will this ever get fixed, and by when?       → receipts.py (SLA receipts)
  * am I getting better at this?                 → resilience.py (score, XP, badges)

Everything is provenance-tagged (net.py): live / device / cache / curated / sim.
"""
import asyncio
import base64
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import auth
import feeds
import grid as grid_mod
import i18n
import impact
import insights
import watch as watch_mod
import net
import push
import receipts
import resilience
import sources
import tariffs
import transport
import ussd
import whatsapp

VERSION = "3.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(push.loop())
    yield
    task.cancel()


app = FastAPI(
    title="ServiceWaze",
    version=VERSION,
    description=("Household resilience network for South Africa: predict disruptions, prepare in "
                 "time, share capacity with neighbours, cut household costs, and hold service "
                 "delivery accountable."),
    lifespan=lifespan,
)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

_report_ips = {}


def _throttle(request: Request, ip_key: str, limit: int, window: int = 3600):
    ip = (request.client.host if request.client else "?") + "|" + ip_key
    now = time.time()
    _report_ips[ip] = [t for t in _report_ips.get(ip, []) if now - t < window]
    if len(_report_ips[ip]) >= limit:
        raise HTTPException(429, f"Slow down — max {limit} per hour.")
    _report_ips[ip].append(now)


def _device(request: Request, device: str = "") -> str:
    return (device or request.headers.get("X-Device-Id") or "").strip()[:64] or "anon"


# ---------------------------------------------------------------------------
# PWA shell
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "boot": {"langs": i18n.languages(), "version": VERSION},
    })


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(os.path.join(BASE_DIR, "static/manifest.webmanifest"),
                        media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def sw():
    return FileResponse(os.path.join(BASE_DIR, "static/sw.js"), media_type="application/javascript")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(os.path.join(BASE_DIR, "static/icons/icon-192.png"), media_type="image/png")


@app.get("/offline.html", response_class=HTMLResponse, include_in_schema=False)
def offline(request: Request):
    return templates.TemplateResponse(request, "index.html", {"boot": {"langs": i18n.languages()}})


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "version": VERSION, "time": datetime.now(timezone.utc).isoformat(),
            "live": net.live_enabled()}


@app.get("/api/areas")
def areas(q: str):
    return {"results": sources.geocode(q)}


@app.get("/api/reverse")
def reverse(lat: float, lon: float):
    return {"place": sources.reverse_geocode(lat, lon)}


@app.get("/api/radar")
def radar(lat: float, lon: float):
    r = sources.radar(lat, lon)
    if not r:
        return {"radar": None, "note": "Radar unavailable (offline or upstream down)"}
    return {"radar": r}


def _resolve_place(q: str = "", lat=None, lon=None) -> dict:
    place = {"name": (q or "").strip() or "Selected location", "lat": lat, "lon": lon, "admin1": ""}
    if ((lat is None or lon is None) and q.strip()) or (q.strip() and not place.get("admin1")):
        geo = sources.geocode(q.strip(), count=1)
        if geo:
            g = geo[0]
            place = {"name": f"{g['name']}, {g.get('admin1', '')}".strip(", "),
                     "lat": g["lat"], "lon": g["lon"], "admin1": g.get("admin1", ""),
                     "match": g}
    return place


# ---------------------------------------------------------------------------
# THE BUNDLE — everything the "Now" tab needs in one round trip
# ---------------------------------------------------------------------------
@app.get("/api/status")
def status(request: Request, q: str = "", lat: Optional[float] = None, lon: Optional[float] = None,
           device: str = ""):
    dev = _device(request, device)
    place = _resolve_place(q, lat, lon)
    w = sources.weather(place["lat"], place["lon"]) if place["lat"] is not None else None
    elec = sources.eskom_status()
    esp = sources.eskomsepush_status()
    sched = sources.esp_area_schedule(q.strip(), place["lat"], place["lon"]) if (q or place["lat"]) else None
    wins = sources.next_windows(sched) if sched else []
    reports = sources.reports_for_area(place["lat"], place["lon"], q.strip()) if (
        place["lat"] is not None or q.strip()) else []
    aq = feeds.get_air(place["lat"], place["lon"]) if place["lat"] is not None else None
    notices = [i for i in feeds.get_feed(categories=["water"], limit=12) if i.get("official")]
    feed_items = feeds.get_feed(limit=40)
    prof = resilience.get_profile(dev)
    imp = impact.assess(place["name"], place["lat"], place["lon"], weather=w, air=aq,
                        power={"status": elec}, water_reports=reports,
                        feed_items=feed_items, profile=prof,
                        schedule={"upcoming": wins} if wins else None)
    glist = grid_mod.listings(area=place["name"].split(",")[0], lat=place["lat"], lon=place["lon"], limit=12)
    return {
        "place": place,
        "weather": w,
        "air": aq,
        "electricity": {"status": elec, "esp": esp, "note": sources.ELECTRICITY_NOTE,
                        "schedule": {"area": (sched or {}).get("area"), "upcoming": wins} if sched else None},
        "water": {"official": sources.WATER_OFFICIAL, "context": sources.WATER_CONTEXT,
                  "reports": reports, "official_notices": notices},
        "transport": {"notices": sources.TRANSPORT_NOTICES, "links": sources.TRANSPORT_LINKS},
        "impact": imp,
        "grid": {"offers": glist["offers"][:6], "needs": glist["needs"][:6],
                 "count": glist["count"], "stats": grid_mod.stats()},
        "cost": {
            "electricity_tariff": tariffs.tariff_for_area(place["name"]),
            "water_city": tariffs.water_tariff_for_area(place["name"]),
        },
        "you": resilience.summary(dev, place["name"]) if dev else None,
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "live": net.live_enabled(),
            "version": VERSION,
        },
    }


@app.get("/api/impact")
def api_impact(q: str = "", lat: Optional[float] = None, lon: Optional[float] = None, device: str = ""):
    place = _resolve_place(q, lat, lon)
    w = sources.weather(place["lat"], place["lon"]) if place["lat"] is not None else None
    reports = sources.reports_for_area(place["lat"], place["lon"], q.strip())
    prof = resilience.get_profile(device or "anon")
    sched = sources.esp_area_schedule(q.strip(), place["lat"], place["lon"]) if (q or place["lat"]) else None
    return impact.assess(place["name"], place["lat"], place["lon"], weather=w,
                         air=feeds.get_air(place["lat"], place["lon"]) if place["lat"] is not None else None,
                         power={"status": sources.eskom_status()}, water_reports=reports,
                         feed_items=feeds.get_feed(limit=40), profile=prof,
                         schedule={"upcoming": sources.next_windows(sched)} if sched else None)


# ---------------------------------------------------------------------------
# Service endpoints (single-purpose, used by the detail cards)
# ---------------------------------------------------------------------------
@app.get("/api/weather")
def weather(lat: float, lon: float):
    w = sources.weather(lat, lon)
    if not w:
        raise HTTPException(502, "Weather source unavailable")
    return w


@app.get("/api/air")
def air(lat: float, lon: float):
    return {"air": feeds.get_air(lat, lon)}


@app.get("/api/electricity")
def electricity():
    return {"status": sources.eskom_status(), "esp": sources.eskomsepush_status(),
            "note": sources.ELECTRICITY_NOTE}


@app.get("/api/electricity/schedule")
def electricity_schedule(q: str = "", lat: Optional[float] = None, lon: Optional[float] = None,
                         stage: Optional[int] = None, force: bool = False):
    sched = sources.esp_area_schedule(q.strip(), lat, lon, force=force)
    if sched is not None:
        return {"schedule": {**sched, "upcoming": sources.next_windows(sched, stage=stage)}}
    # No per-area feed configured: estimate from the national stage, clearly
    # labelled, rather than showing an empty card.
    st = sources.eskomsepush_status() or {}
    level = stage if stage is not None else (st.get("stage") or sources.eskom_status().get("stage") or 0)
    est = sources.estimated_schedule(q.strip() or "your area", level)
    if est is None:
        return {"schedule": None, "hint": "No load shedding scheduled right now. Add ESP_API_TOKEN (free, eskomsepush.org) for per-area times.",
                "official": "https://loadshedding.eskom.co.za"}
    return {"schedule": est}


@app.get("/api/electricity/events")
def electricity_events(q: str = "", lat: Optional[float] = None, lon: Optional[float] = None):
    ev = sources.esp_area_events(q.strip(), lat, lon)
    if ev is None:
        return {"events": None, "hint": "Set ESP_API_TOKEN for area events",
                "official": "https://loadshedding.eskom.co.za"}
    return ev


@app.get("/api/water")
def water():
    return {"official": sources.WATER_OFFICIAL, "context": sources.WATER_CONTEXT,
            "reports": sources.recent_reports(40)}


@app.get("/api/transport")
def transport_api(q: str = "", lat: Optional[float] = None, lon: Optional[float] = None):
    place = _resolve_place(q, lat, lon)
    feed_items = feeds.get_feed(categories=["transport"], limit=40)
    reps = sources.reports_for_area(place["lat"], place["lon"], q.strip())
    data = transport.transport_for_area(place["name"], place.get("admin1", ""),
                                        feed_items=feed_items, route_reports=reps)
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return data


@app.get("/api/services")
def services():
    svc = {k: dict(v) for k, v in feeds.SERVICES.items()}
    svc["food"] = {
        "title": "Food access", "icon": "🥫",
        "items": [
            {"name": "SASSA (grants & pay points)", "type": "link",
             "value": "https://www.sassa.gov.za", "note": "Grant dates & pay points"},
            {"name": "SASSA toll-free", "type": "call", "value": "0800 60 10 11", "note": " Grants & queries"},
            {"name": "FoodForward SA", "type": "link", "value": "https://www.foodforward.org.za",
             "note": "Food bank network"},
            {"name": "Department of Social Development", "type": "link",
             "value": "https://www.gov.za/services/social-benefits", "note": "Social relief of distress"},
            {"name": "Childline (child hunger/safety)", "type": "call", "value": "116", "note": "Free, 24h"},
        ]}
    svc["money"] = {
        "title": "Household money", "icon": "💸",
        "items": [
            {"name": "National Credit Regulator", "type": "call", "value": "0860 627 627",
             "note": "Free debt advice & reckless lending"},
            {"name": "Debt counselling (NCR)", "type": "link", "value": "https://www.ncr.org.za",
             "note": "Registered debt counsellors"},
            {"name": "NERSA", "type": "link", "value": "https://www.nersa.org.za",
             "note": "Electricity tariff regulator — dispute a tariff"},
            {"name": "Consumer Goods & Services Ombud", "type": "call", "value": "0860 000 272",
             "note": "Retail & food price complaints"},
        ]}
    return {"services": svc, "checklists": feeds.CHECKLISTS}


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------
@app.get("/api/news")
def news(limit: int = 40):
    return {"items": feeds.get_feed(types=["news"], limit=limit), "meta": feeds.feed_meta()}


@app.get("/api/social")
def social(limit: int = 20):
    return {"items": feeds.get_feed(types=["social"], limit=limit), "meta": feeds.feed_meta()}


@app.get("/api/feed")
def feed(areas: str = "", categories: str = "", q: str = "", limit: int = 80):
    a = [x for x in areas.split(",") if x.strip()] if areas else None
    c = [x for x in categories.split(",") if x.strip()] if categories else None
    items = feeds.get_feed(areas=a, categories=c, q=q.strip() or None, limit=limit)
    return {"items": items, "meta": feeds.feed_meta()}


# ---------------------------------------------------------------------------
# Money engine
# ---------------------------------------------------------------------------
@app.get("/api/cost/electricity")
def cost_electricity(kwh: float = 350, tariff: str = "", area: str = ""):
    tid = tariff or tariffs.tariff_for_area(area)
    return tariffs.electricity_bill(kwh, tid)


@app.get("/api/cost/water")
def cost_water(kl: float = 12, city: str = "", area: str = ""):
    cid = city or tariffs.water_tariff_for_area(area)
    return tariffs.water_bill(kl, cid)


@app.get("/api/cost/appliance")
def cost_appliance(key: str = "kettle", minutes: Optional[float] = None,
                   tariff: str = "", area: str = ""):
    tid = tariff or tariffs.tariff_for_area(area)
    out = tariffs.appliance_cost(key, tid, minutes)
    if "error" in out:
        raise HTTPException(404, "unknown appliance")
    return out


@app.get("/api/cost/tou")
def cost_tou(tariff: str = "eskom_homeflex"):
    return {"windows": tariffs.cheapest_windows(tariff), "tariff": tariff,
            "note": "Cheapest hours first — shift geyser, pool pump and washing into them."}


@app.get("/api/cost/harvest")
def cost_harvest(lat: float, lon: float, roof_m2: float = 60, runoff: float = 0.8):
    w = sources.weather(lat, lon) or {}
    daily = w.get("daily") or []
    week_mm = sum(float(d.get("precip_sum") or 0) for d in daily)
    out = tariffs.rain_harvest(roof_m2, week_mm, runoff)
    out["forecast_mm"] = round(week_mm, 1)
    out["daily"] = [{"date": d.get("date"), "mm": d.get("precip_sum"), "prob": d.get("precip_prob")}
                    for d in daily]
    out["tier"] = w.get("tier")
    out["live"] = w.get("live")
    return out


@app.get("/api/cost/solar")
def cost_solar(lat: float, lon: float, kwp: float = 3.0, tariff: str = "", area: str = ""):
    tid = tariff or tariffs.tariff_for_area(area)
    w = sources.weather(lat, lon) or {}
    daily = w.get("daily") or []
    rad = [float(d.get("radiation") or 0) for d in daily if d.get("radiation")]
    # MJ/m² → kWh/kWp per day (÷3.6)
    kwh_per_kwp = (sum(rad) / len(rad) / 3.6) if rad else 4.6
    out = tariffs.solar_estimate(kwp, kwh_per_kwp, tid)
    out["irradiance_kwh_per_kwp"] = round(kwh_per_kwp, 2)
    out["tier"] = w.get("tier")
    out["live"] = w.get("live")
    return out


@app.get("/api/cost/basket")
def cost_basket(area: str = "", people: int = 4):
    return tariffs.food_basket(area, people)


class LeakIn(BaseModel):
    readings: list[dict]


@app.post("/api/cost/leak")
def cost_leak(body: LeakIn):
    return tariffs.leak_check(body.readings)


@app.get("/api/cost/tariffs")
def cost_tariffs():
    return {"electricity": tariffs.ELECTRICITY_TARIFFS, "water": tariffs.WATER_TARIFFS,
            "appliances": tariffs.APPLIANCES, "sources": tariffs.TARIFF_SOURCES,
            "as_of": tariffs.AS_OF}


# ---------------------------------------------------------------------------
# Identity, profile, gamification
# ---------------------------------------------------------------------------
@app.post("/api/me/identify")
def me_identify(request: Request, device: str = "", area: str = "", lang: str = "en"):
    dev = _device(request, device)
    return resilience.identify(dev, area, lang)


class ProfileIn(BaseModel):
    device: str = ""
    people: Optional[int] = None
    roof_m2: Optional[float] = None
    water_l: Optional[float] = None
    tank_l: Optional[float] = None
    backup_light: Optional[int] = None
    power_bank: Optional[int] = None
    surge_protect: Optional[int] = None
    solar: Optional[int] = None
    food_days: Optional[int] = None
    alt_cooking: Optional[int] = None
    route_plan: Optional[int] = None
    contacts_saved: Optional[int] = None
    garden: Optional[int] = None


@app.get("/api/me/profile")
def me_profile(request: Request, device: str = ""):
    dev = _device(request, device)
    return {"device": dev, "profile": resilience.get_profile(dev),
            "score": resilience.score(dev), "you": resilience.identify(dev)}


@app.post("/api/me/profile")
def me_profile_save(body: ProfileIn, request: Request):
    dev = _device(request, body.device)
    data = {k: v for k, v in body.model_dump().items() if k != "device" and v is not None}
    prof = resilience.save_profile(dev, data)
    return {"ok": True, "profile": prof, "score": resilience.score(dev)}


class ActionIn(BaseModel):
    device: str = ""
    action: str
    meta: str = ""
    area: str = ""


@app.post("/api/me/action")
def me_action(body: ActionIn, request: Request):
    dev = _device(request, body.device)
    return {"ok": True, **resilience.act(dev, body.action.strip(), body.meta, body.area)}


@app.get("/api/me/summary")
def me_summary(request: Request, device: str = "", area: str = ""):
    return resilience.summary(_device(request, device), area)


class SavingIn(BaseModel):
    device: str = ""
    kind: str = "other"
    amount: float = 0.0
    note: str = ""


@app.post("/api/me/savings")
def me_savings_post(body: SavingIn, request: Request):
    return resilience.log_saving(_device(request, body.device), body.kind,
                                 body.amount, body.note)


@app.get("/api/me/savings")
def me_savings_get(request: Request, device: str = ""):
    return resilience.savings(_device(request, device))


@app.get("/api/badges")
def badges(request: Request, device: str = ""):
    return {"badges": resilience.badges(_device(request, device))}


@app.get("/api/challenges")
def challenges(request: Request, device: str = ""):
    return resilience.challenges(_device(request, device))


class ChallengeIn(BaseModel):
    device: str = ""
    id: str


@app.post("/api/challenges/complete")
def challenge_complete(body: ChallengeIn, request: Request):
    return {"ok": True, **(resilience.complete_challenge(_device(request, body.device), body.id)
                          or {})}


@app.get("/api/leaderboard")
def leaderboard(area: str = ""):
    return resilience.leaderboard(area)


# ---------------------------------------------------------------------------
# Ubuntu Grid + stokvels
# ---------------------------------------------------------------------------
@app.get("/api/grid")
def grid_listings(area: str = "", lat: Optional[float] = None, lon: Optional[float] = None,
                  kind: str = "", limit: int = 40):
    return grid_mod.listings(area, lat, lon, kind, limit)


class GridIn(BaseModel):
    device: str = ""
    kind: str = "other"
    mode: str = "offer"
    title: str
    detail: str = ""
    area: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    availability: str = ""


@app.post("/api/grid/add")
def grid_add(body: GridIn, request: Request):
    dev = _device(request, body.device)
    if len(body.title.strip()) < 3:
        raise HTTPException(400, "title too short")
    _throttle(request, "grid", 20)
    you = resilience.identify(dev, body.area)
    out = grid_mod.add(body.kind, body.mode, body.title.strip(), body.detail.strip(),
                       body.area.strip(), body.lat, body.lon, dev, you["handle"], body.availability)
    resilience.act(dev, "shared_resource" if body.mode == "offer" else "report",
                   meta=body.title[:80], area=body.area)
    return out


@app.get("/api/grid/mine")
def grid_mine(request: Request, device: str = ""):
    return grid_mod.mine(_device(request, device))


class ClaimIn(BaseModel):
    device: str = ""
    id: int


@app.post("/api/grid/claim")
def grid_claim(body: ClaimIn, request: Request):
    dev = _device(request, body.device)
    you = resilience.identify(dev)
    out = grid_mod.claim(body.id, dev, you["handle"])
    if not out.get("ok"):
        raise HTTPException(400, out.get("error", "could not claim"))
    resilience.act(dev, "shared_resource", meta=f"claimed #{body.id}")
    return out


@app.post("/api/grid/close")
def grid_close(body: ClaimIn, request: Request):
    return grid_mod.close(body.id, _device(request, body.device))


@app.get("/api/grid/points")
def grid_points(lat: float, lon: float, kinds: str = "water,food,care", radius: int = 4000):
    return grid_mod.nearby(lat, lon, kinds, radius)


@app.get("/api/grid/stats")
def grid_stats():
    return grid_mod.stats()


@app.get("/api/stokvels")
def stokvels(area: str = ""):
    return grid_mod.stokvel_list(area)


class StokvelIn(BaseModel):
    device: str = ""
    name: str
    purpose: str = "tank"
    area: str = ""
    target: float = 4500


@app.post("/api/stokvels")
def stokvel_create(body: StokvelIn, request: Request):
    dev = _device(request, body.device)
    if len(body.name.strip()) < 3:
        raise HTTPException(400, "name too short")
    you = resilience.identify(dev, body.area)
    out = grid_mod.stokvel_create(body.name.strip(), body.purpose, body.area.strip(),
                                  body.target, dev, you["handle"])
    resilience.act(dev, "stokvel_join", meta=body.name[:60], area=body.area)
    return out


class ContribIn(BaseModel):
    device: str = ""
    amount: float = 0


@app.post("/api/stokvels/{sid}/contribute")
def stokvel_contribute(sid: int, body: ContribIn, request: Request):
    dev = _device(request, body.device)
    if body.amount <= 0:
        raise HTTPException(400, "amount must be positive")
    you = resilience.identify(dev)
    out = grid_mod.stokvel_contribute(sid, body.amount, dev, you["handle"])
    if not out.get("ok"):
        raise HTTPException(404, out.get("error", "not found"))
    resilience.act(dev, "stokvel_contribute", meta=f"R{body.amount}", area="")
    return out


@app.get("/api/stokvels/{sid}")
def stokvel_detail(sid: int):
    return grid_mod.stokvel_detail(sid)




# ---------------------------------------------------------------------------
# Watch circle — "is she okay?" (public safety, the human loop)
# ---------------------------------------------------------------------------
@app.get("/api/watch")
def watch_api(area: str = "", device: str = ""):
    return watch_mod.circle(area.strip() or "Soweto", device.strip())


class WatchIn(BaseModel):
    device: str = ""
    handle: str = ""
    area: str = ""
    note: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None


@app.post("/api/watch/add")
def watch_add(body: WatchIn, request: Request):
    _throttle(request, "watch", 20)
    return watch_mod.add(_device(request, body.device), body.handle,
                         body.area.strip(), body.note.strip(), body.lat, body.lon)


class WatchCheckIn(BaseModel):
    device: str = ""
    id: int = 0
    note: str = ""


@app.post("/api/watch/checkin")
def watch_checkin(body: WatchCheckIn, request: Request):
    return watch_mod.checkin(_device(request, body.device), body.id, body.note.strip())


class ImSafeIn(BaseModel):
    device: str = ""
    area: str = ""
    note: str = ""


@app.post("/api/watch/im-safe")
def watch_im_safe(body: ImSafeIn, request: Request):
    return watch_mod.im_safe(_device(request, body.device), body.area.strip(), body.note.strip())


class WatchFlag(BaseModel):
    device: str = ""
    id: int = 0
    state: str = "needs_help"
    note: str = ""


@app.post("/api/watch/flag")
def watch_flag(body: WatchFlag, request: Request):
    return watch_mod.flag(_device(request, body.device), body.id, body.state, body.note.strip())



# ---------------------------------------------------------------------------
# Area insights & the self-calibrating forecast
# ---------------------------------------------------------------------------
@app.get("/api/insights/history")
def insights_history(area: str = "", days: int = 120):
    """Service-delivery record for an area — the B2G artefact."""
    return insights.history(area or "Soweto", days)


@app.get("/api/insights/forecast")
def insights_forecast(area: str = "", horizon_h: int = 24, log: bool = True):
    """Probability that water / power / transport fail in this area within the
    horizon, with drivers, sample size and the model's own calibration."""
    place = _resolve_place(area)
    w = sources.weather(place["lat"], place["lon"]) if place["lat"] is not None else None
    notices = [i for i in feeds.get_feed(categories=["water"], limit=10) if i.get("official")]
    return insights.predict(area or place["name"], horizon_h, weather=w,
                            official_notices=notices, log=log)


class OutcomeIn(BaseModel):
    area: str
    service: str
    happened: bool
    note: str = ""


@app.post("/api/insights/outcome")
def insights_outcome(body: OutcomeIn):
    """The street tells us whether the forecast was right. The model learns."""
    return insights.record_outcome(body.area, body.service, body.happened, body.note)


@app.get("/api/insights/accuracy")
def insights_accuracy(area: str = ""):
    return insights.forecast_accuracy(area)


# ---------------------------------------------------------------------------
# Climate-smart small business: providers + the "who's open" board
# ---------------------------------------------------------------------------
@app.get("/api/business")
def business_api(area: str = "", category: str = ""):
    return grid_mod.business_list(area, category)


class BusinessIn(BaseModel):
    device: str = ""
    name: str
    category: str = "other"
    area: str = ""
    contact: str = ""
    detail: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None


@app.post("/api/business/add")
def business_add(body: BusinessIn, request: Request):
    if len(body.name.strip()) < 3:
        raise HTTPException(400, "name too short")
    _throttle(request, "business", 20)
    out = grid_mod.business_add(body.name.strip(), body.category, body.area.strip(),
                                body.contact.strip(), body.detail.strip(),
                                body.lat, body.lon, _device(request, body.device))
    resilience.act(_device(request, body.device), "shared_resource",
                   meta="business:" + body.name[:40], area=body.area)
    return out


class VerifyIn(BaseModel):
    device: str = ""
    id: int


@app.post("/api/business/verify")
def business_verify(body: VerifyIn, request: Request):
    return grid_mod.business_verify(body.id, _device(request, body.device))


@app.get("/api/business/board")
def business_board(area: str = ""):
    return grid_mod.open_board(area)


class OpenIn(BaseModel):
    device: str = ""
    name: str
    area: str = ""
    status: str = "open"
    note: str = ""


@app.post("/api/business/open")
def business_open(body: OpenIn, request: Request):
    if len(body.name.strip()) < 2:
        raise HTTPException(400, "name too short")
    _throttle(request, "openboard", 30)
    grid_mod.post_open(body.name.strip(), body.area.strip(), body.status,
                       body.note.strip(), _device(request, body.device))
    return {"ok": True}

# ---------------------------------------------------------------------------
# Reports → receipts → scorecard
# ---------------------------------------------------------------------------
class ReportIn(BaseModel):
    area: str
    kind: str
    message: str = ""
    reporter: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    photo: str = ""
    audio: str = ""
    device: str = ""


@app.post("/api/report")
def report(body: ReportIn, request: Request):
    if body.kind not in sources.REPORT_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(sources.REPORT_KINDS)}")
    if len(body.area.strip()) < 3:
        raise HTTPException(400, "area too short")
    dev = _device(request, body.device)
    _throttle(request, "report", 8)

    photo_hex = None
    if body.photo:
        try:
            raw = body.photo.split(",", 1)[1] if "," in body.photo else body.photo
            photo_hex = base64.b64decode(raw)[:350000].hex()
        except Exception:
            photo_hex = None
    audio_hex, audio_mime = None, None
    if body.audio:
        try:
            prefix, _, raw = body.audio.partition(",")
            audio_mime = prefix.replace("data:", "").split(";")[0] or "audio/ogg"
            audio_hex = base64.b64decode(raw)[:500000].hex()
        except Exception:
            audio_hex, audio_mime = None, None

    rid = sources.add_report(body.area.strip(), body.kind, body.message.strip(),
                             body.reporter.strip(), body.lat, body.lon)
    sources.attach_media(rid, photo_hex=photo_hex, audio_hex=audio_hex, audio_mime=audio_mime)
    resilience.act(dev, "report", meta=f"{body.kind}:{body.area[:40]}", area=body.area.strip())
    return {"id": rid, "ok": True, "receipt": receipts.issue(rid, body.area.strip(), body.kind)}


class ConfirmIn(BaseModel):
    id: int
    device: str = ""


@app.post("/api/confirm")
def confirm(body: ConfirmIn, request: Request):
    if not sources.confirm_report(body.id):
        raise HTTPException(404, "report not found")
    resilience.act(_device(request, body.device), "confirm", meta=f"#{body.id}")
    return {"ok": True, "receipt": receipts.receipt(body.id)}


@app.get("/api/photo/{rid}")
def photo(rid: int):
    import sqlite3
    from fastapi.responses import Response
    con = sqlite3.connect(sources.DB_PATH)
    row = con.execute("SELECT photo FROM reports WHERE id=?", (rid,)).fetchone()
    con.close()
    if not row or not row[0]:
        raise HTTPException(404, "no photo")
    return Response(content=bytes.fromhex(row[0]), media_type="image/jpeg")


@app.get("/api/audio/{rid}")
def audio(rid: int):
    import sqlite3
    from fastapi.responses import Response
    con = sqlite3.connect(sources.DB_PATH)
    row = con.execute("SELECT audio, audio_mime FROM reports WHERE id=?", (rid,)).fetchone()
    con.close()
    if not row or not row[0]:
        raise HTTPException(404, "no voice note")
    return Response(content=bytes.fromhex(row[0]), media_type=row[1] or "audio/ogg")


@app.get("/api/receipts")
def api_receipts(area: str = "", limit: int = 25):
    return {"receipts": receipts.list_receipts(area, limit)}


@app.get("/api/receipt/{rid}")
def api_receipt(rid: int):
    r = receipts.receipt(rid)
    if not r:
        raise HTTPException(404, "not found")
    return r


class UpdateIn(BaseModel):
    text: str
    by: str = "community"


@app.post("/api/receipt/{rid}/update")
def api_receipt_update(rid: int, body: UpdateIn):
    out = receipts.update(rid, body.text.strip(), body.by[:40])
    if not out.get("ok"):
        raise HTTPException(404, "not found")
    return out


class ResolveIn(BaseModel):
    by: str = "community"
    device: str = ""


@app.post("/api/receipt/{rid}/resolve")
def api_receipt_resolve(rid: int, body: ResolveIn, request: Request):
    out = receipts.resolve(rid, body.by[:40])
    if not out.get("ok"):
        raise HTTPException(404, "not found")
    resilience.act(_device(request, body.device), "resolved_report", meta=f"#{rid}")
    return out


@app.get("/api/scorecard")
def api_scorecard(area: str = ""):
    return receipts.scorecard(area)


# ---------------------------------------------------------------------------
# Source transparency console
# ---------------------------------------------------------------------------
@app.get("/api/sources/health")
def sources_health():
    return net.health()


@app.post("/api/sources/set-live")
def sources_set_live(flag: bool = True):
    """Manual override of the live/demo switch (used by the in-app console)."""
    net.set_live(flag)
    return {"live": net.live_enabled()}


class DeviceFetchIn(BaseModel):
    name: str
    ok: bool
    latency_ms: Optional[int] = None
    note: str = ""
    url: str = ""


@app.post("/api/sources/device")
def sources_device(body: DeviceFetchIn):
    """The PWA reports a browser-side (CORS) fetch back to the server so the
    source console reflects what the device itself pulled live."""
    net.mark_device(body.name, body.ok, body.latency_ms, body.note, body.url)
    return {"ok": True}


class DeviceDataIn(BaseModel):
    name: str
    url: str
    params: dict = {}
    data: dict = {}
    latency_ms: Optional[int] = None


@app.post("/api/device/data")
def device_data(body: DeviceDataIn):
    """A CORS-enabled reading pulled by the user's own browser, handed to the
    server so that impact, costs and advisories are computed from real data
    even when the ServiceWaze host has no outbound internet."""
    if not body.name or not body.url:
        raise HTTPException(400, "name and url are required")
    return net.inject(body.name, body.url, body.params, body.data,
                      tier="device", latency_ms=body.latency_ms)


@app.get("/api/i18n")
def api_i18n(lang: str = "en"):
    return {"lang": lang, "strings": i18n.bundle(lang), "languages": i18n.languages()}


# ---------------------------------------------------------------------------
# Chat (read free, write with login) — unchanged from v2.6
# ---------------------------------------------------------------------------
class ChatIn(BaseModel):
    area: str
    message: str
    lat: Optional[float] = None
    lon: Optional[float] = None


def _token_from(request: Request):
    h = request.headers.get("Authorization", "")
    return h[7:].strip() if h.lower().startswith("bearer ") else None


@app.get("/api/chat")
def chat_get(q: str = "", lat: Optional[float] = None, lon: Optional[float] = None, limit: int = 40):
    msgs = sources.chats_for_area(lat, lon, q.strip()) if (lat is not None or q.strip()) else []
    return {"messages": msgs[:limit]}


@app.post("/api/chat")
def chat_post(body: ChatIn, request: Request):
    username = auth.verify_token(_token_from(request))
    if not username:
        raise HTTPException(401, "Login required to write in chat")
    if len(body.area.strip()) < 3 or len(body.message.strip()) < 2:
        raise HTTPException(400, "area or message too short")
    _throttle(request, "chat", 10)
    rid = sources.add_chat(body.area.strip(), body.message, username, body.lat, body.lon)
    if rid is None:
        raise HTTPException(400, "message could not be saved")
    return {"id": rid, "ok": True}


class ChatReportIn(BaseModel):
    id: int


@app.post("/api/chat/report")
def chat_report(body: ChatReportIn, request: Request):
    if not auth.verify_token(_token_from(request)):
        raise HTTPException(401, "Login required to flag messages")
    if not sources.report_chat(body.id):
        raise HTTPException(404, "message not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class AuthIn(BaseModel):
    username: str
    password: str


@app.post("/api/auth/register")
def auth_register(body: AuthIn):
    username, err = auth.register(body.username, body.password)
    if err:
        raise HTTPException(400, err)
    return {"ok": True, "token": auth.login(username, body.password), "username": username}


@app.post("/api/auth/login")
def auth_login(body: AuthIn):
    token = auth.login(body.username, body.password)
    if not token:
        raise HTTPException(401, "Invalid username or password")
    return {"ok": True, "token": token, "username": body.username.strip()}


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    auth.logout(_token_from(request))
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(request: Request):
    username = auth.verify_token(_token_from(request))
    if not username:
        raise HTTPException(401, "Not logged in")
    return {"username": username}


# ---------------------------------------------------------------------------
# Push, WhatsApp, USSD — multi-channel reach
# ---------------------------------------------------------------------------
@app.get("/api/push/vapid")
def push_vapid():
    key = push.public_key()
    if not key:
        raise HTTPException(503, "VAPID not configured")
    return {"public_key": key}


class PushSubIn(BaseModel):
    endpoint: str
    keys: dict
    area: str = ""


@app.post("/api/push/subscribe")
def push_subscribe(body: PushSubIn):
    push.add_subscription(body.endpoint, body.keys.get("p256dh", ""),
                          body.keys.get("auth", ""), body.area.strip())
    return {"ok": True}


@app.post("/api/push/test")
def push_test():
    return {"ok": True, "sent": push.send_test_push(), "subscribers": push.count_subscriptions()}


class WAOptIn(BaseModel):
    phone: str
    area: str = ""


@app.post("/api/whatsapp/optin")
def wa_optin(body: WAOptIn):
    digits = "".join(ch for ch in body.phone if ch.isdigit())
    if len(digits) < 9:
        raise HTTPException(400, "Invalid phone number")
    whatsapp.opt_in(digits, body.area.strip())
    return {"ok": True}


class WATest(BaseModel):
    phone: str = ""


@app.post("/api/whatsapp/test")
def wa_test(body: WATest):
    digits = "".join(ch for ch in body.phone if ch.isdigit())
    if not digits:
        ins = whatsapp.list_optins()
        digits = ins[0]["phone"] if ins else "27000000000"
    return {"ok": True, **whatsapp.send_test(digits)}


@app.get("/api/whatsapp/outbox")
def wa_outbox(limit: int = 20):
    return {"items": whatsapp.outbox(limit), "mode": whatsapp.PROVIDER}


@app.get("/api/ussd")
def ussd_menu(session: str = "", input: str = "", msisdn: str = ""):
    return {"session": session or "test",
            "text": ussd.handle(session or "test", input or "", msisdn or "")}
