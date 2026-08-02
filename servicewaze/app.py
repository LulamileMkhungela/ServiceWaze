"""ServiceWaze — live status hub for South African services (PWA edition).

Run:  uvicorn app:app --port 8000
Docs: /docs  (OpenAPI)
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
import push
import sources
import transport
import ussd
import whatsapp

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(push.loop())
    yield
    task.cancel()

app = FastAPI(title="ServiceWaze", version="2.1.0",
              description="Live status for electricity, water, weather, transport, news & community reports — merged into one feed.",
              lifespan=lifespan)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# naive per-IP throttle for crowd reports
_report_ips = {}

# --------------------------------------------------------------------------
# PWA files
# --------------------------------------------------------------------------
@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(os.path.join(BASE_DIR, "static/manifest.webmanifest"), media_type="application/manifest+json")

@app.get("/sw.js", include_in_schema=False)
def sw():
    return FileResponse(os.path.join(BASE_DIR, "static/sw.js"), media_type="application/javascript")

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(os.path.join(BASE_DIR, "static/icons/icon-192.png"), media_type="image/png")

# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}

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
        raise HTTPException(502, "Radar source unavailable")
    return {"radar": r}

@app.get("/api/electricity/events")
def electricity_events(q: str = "", lat: Optional[float] = None, lon: Optional[float] = None):
    """Future load-shedding events for an area (needs ESP_API_TOKEN; graceful fallback)."""
    ev = sources.esp_area_events(q.strip(), lat, lon)
    if ev is None:
        return {"events": None,
                "hint": "Set ESP_API_TOKEN (free, eskomsepush.org) for area events",
                "official": "https://loadshedding.eskom.co.za"}
    return ev

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
    """Per-area load-shedding schedule (needs ESP_API_TOKEN; graceful fallback).
    Returns upcoming windows within 7 days, optionally filtered by stage."""
    sched = sources.esp_area_schedule(q.strip(), lat, lon, force=force)
    if sched is None:
        return {"schedule": None,
                "hint": "Set ESP_API_TOKEN (free, eskomsepush.org) for per-area schedules",
                "official": "https://loadshedding.eskom.co.za"}
    wins = sources.next_windows(sched, stage=stage)
    return {"schedule": {**sched, "upcoming": wins}}

@app.get("/api/water")
def water():
    return {"official": sources.WATER_OFFICIAL, "context": sources.WATER_CONTEXT,
            "reports": sources.recent_reports(40)}

@app.get("/api/transport")
def transport_api(q: str = "", lat: Optional[float] = None, lon: Optional[float] = None):
    """Government transport for an area: services, live status from the merged
    feed, community route reports, and nearby-area suggestions."""
    place = {"name": q.strip() or "Selected location", "lat": lat, "lon": lon, "admin1": ""}
    if q.strip():
        geo = sources.geocode(q.strip(), count=1)
        if geo:
            place = {"name": f"{geo[0]['name']}, {geo[0]['admin1']}",
                     "lat": geo[0]["lat"], "lon": geo[0]["lon"],
                     "admin1": geo[0].get("admin1", "")}
    feed_items = feeds.get_feed(categories=["transport"], limit=40)
    reps = sources.reports_for_area(place["lat"], place["lon"], q.strip()) if place["lat"] is not None or q.strip() else []
    data = transport.transport_for_area(place["name"], place.get("admin1", ""),
                                        feed_items=feed_items, route_reports=reps)
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return data

@app.get("/api/services")
def services():
    return {"services": feeds.SERVICES, "checklists": feeds.CHECKLISTS}

# --------------------------------------------------------------------------
# Push notifications (Web Push / VAPID)
# --------------------------------------------------------------------------
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
    n = push.send_test_push()
    return {"ok": True, "sent": n, "subscribers": push.count_subscriptions()}

# --------------------------------------------------------------------------
# WhatsApp alerts (provider-agnostic; dry-run without credentials)
# --------------------------------------------------------------------------
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
        # test with first opt-in or a sample number
        ins = whatsapp.list_optins()
        digits = ins[0]["phone"] if ins else "27000000000"
    res = whatsapp.send_test(digits)
    return {"ok": True, **res}

@app.get("/api/whatsapp/outbox")
def wa_outbox(limit: int = 20):
    return {"items": whatsapp.outbox(limit), "mode": whatsapp.PROVIDER}

# --------------------------------------------------------------------------
# USSD simulator (feature-phone channel)
# --------------------------------------------------------------------------
@app.get("/api/ussd")
def ussd_menu(session: str = "", input: str = "", msisdn: str = ""):
    text = ussd.handle(session or "test", input or "", msisdn or "")
    return {"session": session or "test", "text": text}

@app.get("/api/news")
def news(limit: int = 40):
    return {"items": feeds.get_feed(types=["news"], limit=limit), "meta": feeds.feed_meta()}

@app.get("/api/social")
def social(limit: int = 20):
    return {"items": feeds.get_feed(types=["social"], limit=limit), "meta": feeds.feed_meta()}

@app.get("/api/feed")
def feed(areas: str = "", categories: str = "", q: str = "", limit: int = 80):
    """The merged feed: news + social + everything, filterable."""
    a = [x for x in areas.split(",") if x.strip()] if areas else None
    c = [x for x in categories.split(",") if x.strip()] if categories else None
    items = feeds.get_feed(areas=a, categories=c, q=q.strip() or None, limit=limit)
    return {"items": items, "meta": feeds.feed_meta()}

@app.get("/api/status")
def status(q: str = "", lat: Optional[float] = None, lon: Optional[float] = None):
    place = {"name": q.strip() or "Selected location", "lat": lat, "lon": lon}
    if (lat is None or lon is None) and q.strip():
        geo = sources.geocode(q.strip(), count=1)
        if geo:
            place = {"name": f"{geo[0]['name']}, {geo[0]['admin1']}",
                     "lat": geo[0]["lat"], "lon": geo[0]["lon"], "match": geo[0]}
    w = sources.weather(place["lat"], place["lon"]) if place["lat"] is not None else None
    elec = sources.eskom_status()
    esp = sources.eskomsepush_status()
    reports = sources.reports_for_area(place["lat"], place["lon"], q.strip()) if place["lat"] is not None or q.strip() else []
    aq = feeds.get_air(place["lat"], place["lon"]) if place["lat"] is not None else None
    official_notices = [i for i in feeds.get_feed(categories=["water"], limit=10)
                        if i.get("official")]
    return {
        "place": place,
        "weather": w,
        "air": aq,
        "electricity": {"status": elec, "esp": esp, "note": sources.ELECTRICITY_NOTE},
        "water": {"official": sources.WATER_OFFICIAL, "context": sources.WATER_CONTEXT,
                  "reports": reports, "official_notices": official_notices},
        "transport": {"notices": sources.TRANSPORT_NOTICES, "links": sources.TRANSPORT_LINKS},
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

class ReportIn(BaseModel):
    area: str
    kind: str
    message: str = ""
    reporter: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    photo: str = ""   # optional data URL (small)
    audio: str = ""   # optional voice-note data URL

@app.post("/api/report")
def report(body: ReportIn, request: Request):
    if body.kind not in sources.REPORT_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(sources.REPORT_KINDS)}")
    if len(body.area.strip()) < 3:
        raise HTTPException(400, "area too short")
    ip = request.client.host if request.client else "?"
    now = time.time()
    _report_ips[ip] = [t for t in _report_ips.get(ip, []) if now - t < 3600]
    if len(_report_ips[ip]) >= 8:
        raise HTTPException(429, "Too many reports — slow down (max 8/hour).")
    _report_ips[ip].append(now)

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
    return {"id": rid, "ok": True}

@app.get("/api/photo/{rid}")
def photo(rid: int):
    import sqlite3
    from fastapi.responses import Response
    con = sqlite3.connect(sources.DB_PATH)
    row = con.execute("SELECT photo FROM reports WHERE id=?", (rid,)).fetchone()
    con.close()
    if not row or not row[0]:
        raise HTTPException(404, "no photo")
    img = bytes.fromhex(row[0])
    return Response(content=img, media_type="image/jpeg")

@app.get("/api/audio/{rid}")
def audio(rid: int):
    import sqlite3
    from fastapi.responses import Response
    con = sqlite3.connect(sources.DB_PATH)
    row = con.execute("SELECT audio, audio_mime FROM reports WHERE id=?", (rid,)).fetchone()
    con.close()
    if not row or not row[0]:
        raise HTTPException(404, "no voice note")
    data = bytes.fromhex(row[0])
    return Response(content=data, media_type=row[1] or "audio/ogg")

class ConfirmIn(BaseModel):
    id: int

@app.post("/api/confirm")
def confirm(body: ConfirmIn):
    ok = sources.confirm_report(body.id)
    if not ok:
        raise HTTPException(404, "report not found")
    return {"ok": True}

# --------------------------------------------------------------------------
# Community chat (area-scoped, moderated; writing requires login)
# --------------------------------------------------------------------------
class ChatIn(BaseModel):
    area: str
    message: str
    lat: Optional[float] = None
    lon: Optional[float] = None

def _token_from(request: Request):
    h = request.headers.get("Authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return None

@app.post("/api/chat")
def chat_post(body: ChatIn, request: Request):
    username = auth.verify_token(_token_from(request))
    if not username:
        raise HTTPException(401, "Login required to write in chat")
    if len(body.area.strip()) < 3:
        raise HTTPException(400, "area too short")
    if len(body.message.strip()) < 2:
        raise HTTPException(400, "message too short")
    ip = request.client.host if request.client else "?"
    now = time.time()
    _report_ips[ip] = [t for t in _report_ips.get(ip, []) if now - t < 3600]
    if len(_report_ips[ip]) >= 10:
        raise HTTPException(429, "Too many messages — slow down (max 10/hour).")
    _report_ips[ip].append(now)
    rid = sources.add_chat(body.area.strip(), body.message, username,
                           body.lat, body.lon)
    if rid is None:
        raise HTTPException(400, "message could not be saved")
    return {"id": rid, "ok": True}

@app.get("/api/chat")
def chat_get(q: str = "", lat: Optional[float] = None, lon: Optional[float] = None, limit: int = 40):
    msgs = sources.chats_for_area(lat, lon, q.strip()) if (lat is not None or q.strip()) else []
    return {"messages": msgs[:limit]}

class ChatReportIn(BaseModel):
    id: int

@app.post("/api/chat/report")
def chat_report(body: ChatReportIn, request: Request):
    if not auth.verify_token(_token_from(request)):
        raise HTTPException(401, "Login required to flag messages")
    ok = sources.report_chat(body.id)
    if not ok:
        raise HTTPException(404, "message not found")
    return {"ok": True}

# --------------------------------------------------------------------------
# Auth (username + password; login needed to WRITE in chat)
# --------------------------------------------------------------------------
class AuthIn(BaseModel):
    username: str
    password: str

@app.post("/api/auth/register")
def auth_register(body: AuthIn):
    username, err = auth.register(body.username, body.password)
    if err:
        raise HTTPException(400, err)
    token = auth.login(username, body.password)
    return {"ok": True, "token": token, "username": username}

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

# --------------------------------------------------------------------------
# Web UI
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html",
                                      {"boot": {}, "static_mode": False})

@app.get("/snapshot.html", response_class=HTMLResponse)
def snapshot(request: Request):
    """Static snapshot (data baked in) for offline preview."""
    try:
        from urllib.parse import urlencode
        import urllib.request
        port = request.url.port or 8000
        q = request.query_params.get("q", "Soweto")
        base = f"http://127.0.0.1:{port}"
        def get(path):
            with urllib.request.urlopen(base + path, timeout=12) as r:
                return r.read().decode()
        status_data = json_loads(get("/api/status?" + urlencode({"q": q})))
        feed_data = json_loads(get("/api/feed?limit=60"))
        svc_data = json_loads(get("/api/services"))
        boot = {"status": status_data, "feed": feed_data, "services": svc_data}
        return templates.TemplateResponse(request, "index.html",
                                          {"boot": boot, "static_mode": True})
    except Exception:
        return templates.TemplateResponse(request, "index.html",
                                          {"boot": {}, "static_mode": True})

import json as _json
def json_loads(s):
    return _json.loads(s)
