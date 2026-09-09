# Architecture

## Request flow

```
Browser (PWA)                        FastAPI (servicewaze/app.py)
─────────────                        ───────────────────────────
boot ──► /api/i18n ─────────────────► i18n.bundle(lang)
     ──► /api/status?q=…&device=… ──► sources.weather()      ─┐
                                      sources.eskom_status()  │
                                      feeds.get_air()         │ net.fetched()
                                      feeds.get_feed()        │  ├─ live  (HTTP + cache)
                                      sources.reports_for_area│  ├─ cache (last known good)
                                      impact.assess(...)      │  └─ sim   (deterministic demo)
                                      grid.listings(...)      │
                                      resilience.summary()   ─┘
     ──► /api/sources/health ───────► net.health()   (per-connector status, latency, last ok)
```

One round trip paints the Now tab. Everything below it is second-tier and lazy-loaded per tab.

## Module map

| Module | Responsibility | Owns |
|---|---|---|
| `net.py` | tiered fetch, cache, provenance envelope, health registry, live/demo switch | `fetched()`, `health()`, `mark_device()` |
| `sim.py` | deterministic demo data: weather, AQI, stage, feed, OSM points, 80-place gazetteer | offline rendering |
| `sources.py` | upstream adapters + community report store | geocode, weather, radar, Eskom, ESP, reports, chat |
| `feeds.py` | merged news/social/official stream, classification, area tagging, services directory | `get_feed()`, `get_air()` |
| `impact.py` | **Prepare Window**: threat detection, confidence, evidence, task planning | `assess()`, `build_plan()` |
| `tariffs.py` | **money engine**: real tariffs, bills, TOU, appliances, harvest, solar, leak, food basket | dated reference data |
| `grid.py` | **Ubuntu Grid**: offers/needs/claims, stokvels, OpenStreetMap points | mutual aid + group savings |
| `receipts.py` | receipts, SLA clocks, entity routing, ward scorecard | accountability |
| `resilience.py` | device identity, profile, score, XP/levels, badges, challenges, savings, leaderboards | gamification |
| `i18n.py` | 5 languages, English fallback | `translate()`, `bundle()` |
| `transport.py` | government transport directory + inferred status | mobility |
| `push.py`, `whatsapp.py`, `ussd.py`, `auth.py` | channels & optional login | reach |

## Data tiering (the design decision that matters)

1. **Try live.** `net.fetched()` performs the HTTP call with a short timeout.
2. **Serve cache.** On failure, the last successful payload is returned with `tier: "cache"`.
3. **Serve demo.** With no cache, the deterministic `sim` generator runs and is tagged `tier: "sim"`, `live: false` — and the UI shows a **DEMO** badge.
4. **Device tier.** CORS-enabled APIs (Overpass, Open-Meteo) can also be fetched by the browser itself; the result is reported back with `POST /api/sources/device` so the console reflects it.

The rule: **the app never blocks on a dead upstream and never presents simulated data as real.**

## Storage

SQLite (`servicewaze/data/servicewaze.db`), no server required:

| Table | Holds |
|---|---|
| `neighbours` | pseudonymous device identities: handle, area, XP, Ubuntu Points, streak |
| `profile` | household facts (people, roof, storage, food days, flags) |
| `actions`, `savings`, `badges` | gamification ledger |
| `offers`, `claims` | Ubuntu Grid listings and hand-overs |
| `stokvels`, `stokvel_members` | group savings pots |
| `reports`, `receipt_updates` | community reports + SLA receipts |
| `items` | news/social cache (2 h rolling) |
| `chat`, `users`, `sessions`, `push_subs` | chat, optional login, web-push subscriptions |

## Frontend

* One HTML shell (`templates/index.html`) + `static/css/app.css` + `static/js/app.js` (no framework, no build step, ~45 kB shell).
* State in `localStorage`: device id, areas, settings, done-tasks, language, theme.
* Bottom-tab router (`go(tab)`), sheet-based modals, toast notifications, Web Share, Web Speech.
* Service worker: network-first API + cache-first shell; push handler that deep-links to the Prepare tab.
* `tools/js_smoke.js` runs the real client against a running server under a Node DOM stub, so render-path regressions are caught without a browser.

## Testing

```
pytest -q                 # 34 tests: API contracts, money maths, grid, receipts, gamification, provenance
node tools/js_smoke.js    # headless client render-path smoke test (needs the server running)
```

## Deployment notes

* Stateless — scale by adding uvicorn workers behind any reverse proxy; SQLite can move to Postgres with no code change beyond the connection helper.
* Serve over HTTPS (required for service worker and push).
* Set `ESP_API_TOKEN` for per-area schedules; set `WA_PROVIDER`/`WA_PROVIDER_TOKEN` for live WhatsApp delivery.
* Set `SW_LIVE=1` in production so a transient network failure can never silently switch the product into demo mode.
