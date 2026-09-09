"""Tiered live-data layer for ServiceWaze.

Design goal: ServiceWaze must ALWAYS render, and it must ALWAYS tell the truth
about where a number came from. Every value in the app therefore carries a
provenance envelope:

    {
      "value": 3,                  # the data
      "source": "Eskom GetStatus", # who said it
      "tier":  "live",             # live | device | cache | curated | sim
      "fetched_at": "2026-09-08T…",# when we got it
      "latency_ms": 214,
      "live": true
    }

Tiers
-----
live     fetched by the ServiceWaze server from the upstream API just now
device   fetched by the user's own browser directly from a CORS-enabled API
         (keeps the server out of the critical path and works when the server
         cannot reach the internet)
cache    upstream unreachable, last known good served from the local cache
curated  versioned, human-verified reference data (tariffs, emergency numbers)
sim      deterministic demo data — ONLY used when no real source is reachable.
         Always flagged `live: false` so nobody is ever misled.

The registry in `health()` powers the in-app "Live sources" console: judges,
municipal partners and residents can see exactly which connector is up, how
fast it answered, and when it last succeeded.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
UA = {"User-Agent": "ServiceWaze/3.0 (+https://github.com/LulamileMkhungela/ServiceWaze)"}

# SW_LIVE=0 forces simulation (demo mode), SW_LIVE=1 forces real calls,
# default "auto" probes once at import and falls back to simulation.
LIVE_MODE = os.environ.get("SW_LIVE", "auto").strip().lower()

_cache: dict[str, tuple[float, object, dict]] = {}
_lock = threading.Lock()
_health: dict[str, dict] = {}
_probe_done = {"v": False, "live": None}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Health registry
# ---------------------------------------------------------------------------
def _reg(name: str, **kw):
    h = _health.get(name) or {
        "name": name, "tier": "live", "status": "unknown", "ok": 0, "fail": 0,
        "latency_ms": None, "last_ok": None, "last_try": None, "note": "",
        "url": "", "key_required": False, "channel": "server",
    }
    h.update(kw)
    _health[name] = h
    return h


def touch(name, ok: bool, latency_ms=None, note="", tier="live", url="",
          key_required=False, channel="server"):
    with _lock:
        h = _reg(name, url=url or _reg(name).get("url", ""),
                 key_required=key_required or _reg(name).get("key_required", False),
                 channel=channel or _reg(name).get("channel", "server"))
        h["last_try"] = now_iso()
        if ok:
            h["ok"] += 1
            h["last_ok"] = now_iso()
            h["status"] = "up"
            h["latency_ms"] = latency_ms
            h["tier"] = tier
            h["note"] = note
        else:
            h["fail"] += 1
            h["status"] = "down" if h["ok"] == 0 else "degraded"
            h["note"] = note or "unreachable"
    return _health[name]


def health():
    with _lock:
        items = sorted(_health.values(), key=lambda x: (x["status"] != "up", x["name"]))
        up = sum(1 for i in items if i["status"] == "up")
        # Real data counts even when this host has no internet, as long as the
        # user's own device pulled it (tier "device").
        device_live = any(i.get("tier") == "device" and i["status"] == "up" for i in items)
    live = live_enabled() or device_live
    return {
        "sources": items,
        "summary": {
            "up": up,
            "total": len(items),
            "live": live,
            "device_live": device_live,
            "mode": "live" if live else "demo",
            "generated_at": now_iso(),
        },
    }


# ---------------------------------------------------------------------------
# Live / simulation switch
# ---------------------------------------------------------------------------
PROBE_URL = "https://api.open-meteo.com/v1/forecast?latitude=-26.2&longitude=28.0&current=temperature_2m"


def _probe() -> bool:
    """One-shot reachability probe (cached for the process lifetime)."""
    if _probe_done["v"]:
        return bool(_probe_done["live"])
    _probe_done["v"] = True
    if LIVE_MODE == "1":
        _probe_done["live"] = True
    elif LIVE_MODE == "0":
        _probe_done["live"] = False
    else:
        try:
            r = requests.get(PROBE_URL, headers=UA, timeout=6)
            _probe_done["live"] = r.status_code == 200
        except Exception:
            _probe_done["live"] = False
    return bool(_probe_done["live"])


def live_enabled() -> bool:
    return _probe()


def set_live(flag: bool):
    _probe_done["v"] = True
    _probe_done["live"] = bool(flag)


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------
def fetched(url: str, name: str, ttl: int = 300, params=None, headers=None,
            kind: str = "json", sim=None, timeout: int = 8, channel="server",
            key_required=False):
    """Return a provenance envelope. Never raises.

    sim: callable() -> python object used when the network is unavailable.
    """
    headers = {**UA, **(headers or {})}
    key = name + "|" + url + "|" + json.dumps(params or {}, sort_keys=True)
    t0 = time.time()

    # A fresh cache entry always wins — including one injected by the user's
    # own device (tier "device"), which is how the app stays truly live even
    # when this host has no outbound internet.
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return _env(hit[1], name, hit[2].get("tier", "cache"), url, hit[2].get("latency_ms"))

    if not live_enabled():
        data = sim() if callable(sim) else None
        touch(name, data is not None, None, note="demo mode (no upstream reachability)",
              tier="sim", url=url, key_required=key_required, channel=channel)
        return _env(data, name, "sim", url, None)

    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        data = r.json() if kind == "json" else r.text
        ms = int((time.time() - t0) * 1000)
        with _lock:
            _cache[key] = (time.time(), data, {"tier": "live", "latency_ms": ms})
        touch(name, True, ms, tier="live", url=url, key_required=key_required, channel=channel)
        return _env(data, name, "live", url, ms)
    except Exception as exc:  # network, DNS, TLS, WAF, rate-limit…
        note = type(exc).__name__
        try:
            note = f"HTTP {exc.response.status_code}"  # type: ignore[attr-defined]
        except Exception:
            pass
        with _lock:
            hit = _cache.get(key)
        if hit:
            touch(name, False, None, note=f"{note} — serving cached data", tier="cache",
                  url=url, key_required=key_required, channel=channel)
            return _env(hit[1], name, "cache", url, hit[2].get("latency_ms"))
        data = sim() if callable(sim) else None
        touch(name, False, None, note=f"{note} — serving demo data", tier="sim",
              url=url, key_required=key_required, channel=channel)
        return _env(data, name, "sim", url, None)


def _env(data, source, tier, url, latency_ms):
    return {
        "data": data,
        "source": source,
        "tier": tier,
        "live": tier in ("live", "device"),
        "fetched_at": now_iso(),
        "latency_ms": latency_ms,
        "endpoint": url,
    }


def mark_device(name: str, ok: bool, latency_ms=None, note="", url=""):
    """Record a browser-side (CORS) fetch reported back by the PWA."""
    touch(name, ok, latency_ms, note=note, tier="device" if ok else "sim",
          url=url, channel="device")


# ---------------------------------------------------------------------------
# Deterministic helpers used by the simulation layer
# ---------------------------------------------------------------------------
def stable_hash(*parts) -> int:
    h = 2166136261
    for p in parts:
        for ch in str(p):
            h = (h ^ ord(ch)) * 16777619 % (2 ** 32)
    return h


def jitter(seed, spread: float) -> float:
    """Deterministic pseudo-random in [-spread, spread] — stable per seed."""
    r = random.Random(stable_hash(seed))
    return r.uniform(-spread, spread)


def inject(name: str, url: str, params: dict, data, tier: str = "device", latency_ms=None):
    """Store a payload fetched by the *browser* into the server cache.

    This closes the loop on the device tier: the PWA can reach CORS-enabled
    APIs (Open-Meteo, Overpass) even when the ServiceWaze host cannot, so the
    user's device pulls the reading itself, hands it to the server, and the
    server computes impact, costs and advisories from *real* data — tagged
    `tier: device` so provenance stays honest.
    """
    key = name + "|" + url + "|" + json.dumps(params or {}, sort_keys=True)
    with _lock:
        _cache[key] = (time.time(), data, {"tier": tier, "latency_ms": latency_ms})
    touch(name, data is not None, latency_ms, note="fetched by the device",
          tier=tier if data is not None else "sim", url=url, channel="device")
    return {"ok": True, "cached": key[:48]}
