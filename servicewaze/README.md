# ServiceWaze — application

**South Africa's household resilience network: predict disruptions, prepare in time, share capacity with neighbours, cut household costs, and hold service delivery accountable.**

Everything in the repository runs from this directory.

```bash
pip install -r requirements.txt
python demo_seed.py          # optional: a populated demo neighbourhood (clearly badged DEMO)
uvicorn app:app --port 8000  # → http://localhost:8000   ·   /docs for OpenAPI
pytest -q                    # from the repository root: 42 tests, no network needed
```

---

## The five loops

| Loop | Module | What it answers |
|---|---|---|
| **Predict** | `impact.py` | "How long do I have before water/power/routes/food are hit?" — threats with confidence + evidence |
| **Prepare** | `impact.py` | "What must I do in the time left?" — task list sized to minutes available and to my household |
| **Share** | `grid.py` | "Who near me can help, and who needs help?" — Ubuntu Grid, stokvels, real OSM points |
| **Save** | `tariffs.py` | "What does this cost, and how do I cut it?" — real 2026/27 tariffs, load shifting, harvest, solar, leak detection, food basket |
| **Prove** | `receipts.py` | "Will anyone fix it, and by when?" — tracked receipt with an SLA clock, plus a ward scorecard |
| **Learn** | `insights.py` | "How likely is this, and was I right?" — Poisson forecast with exposed drivers, peer-verified outcomes, per-area calibration, published Brier score |

Gamification lives in `resilience.py`: Resilience Score (0–100), XP and levels, Ubuntu Points, 9 badges, weekly challenges, streaks, area leaderboards.

Built for the network as it really is: every write is queued on the device when signal is lost and flushed
on reconnect; the map, chat and reports degrade gracefully offline; data-saver mode switches off images,
tiles and social embeds.

---

## Screens

| Tab | Content |
|---|---|
| **Now** | Resilience ring · countdown to next impact · top three tasks · six service tiles (power, water, transport, food, flood, air) · weather + advisories · nearby reports |
| **Prepare** | **7-day load-shedding grid with 60/15-minute heads-up alarms** · minutes-left vs minutes-needed · full task checklist · cost tools · household profile · solar & rainwater calculators |
| **Grid** | **Map** (offers, requests, faults, OSM points, businesses) · Offers · Requests · Nearby · **Business (providers + "open right now" board)** · Stokvels |
| **Community** | **24-hour forecast with drivers + "was it right?" buttons** · history stats per service · merged news + social + official notices · receipts with SLA bars · ward scorecard · area chat · **Live sources console** |
| **You** | level & XP · score breakdown · weekly challenges · badges · savings ledger · leaderboards · **accessibility controls (text size, contrast, motion)** · settings (language, theme, data-saver, push, install, WhatsApp, USSD) |

---

## Live data (tiered, always honest)

`net.py` wraps every upstream call in a provenance envelope — `{data, source, tier, live, fetched_at, latency_ms}`:

`live` → `device` (browser-side CORS fetch) → `cache` (last known good) → `curated` (dated reference data) → `sim` (deterministic demo, **badged DEMO** in the UI).

| Source | Endpoint / data | Key |
|---|---|---|
| Open-Meteo | forecast, air quality, geocoding | none |
| Nominatim | reverse geocode | none |
| RainViewer | radar tiles | none |
| Eskom | `GetStatus` (national stage) | none |
| EskomSePush | `/status`, `/areas_search`, `/areas_nearby`, `/area_information/{id}/allowance`, `/area_information/{id}/event` | `ESP_API_TOKEN` |
| Johannesburg Water | official notices (RSS) | none |
| Google News SA, The Citizen, BusinessTech, Mastodon | merged feed | none |
| OpenStreetMap Overpass | water points, markets, clinics | none |

Full table, keys, TTLs and fallbacks: `../docs/DATA_SOURCES.md`.

---

## Environment

| Variable | Effect |
|---|---|
| `ESP_API_TOKEN` | per-area load-shedding schedules & events (free tier, eskomsepush.org) |
| `SW_LIVE` | `1` force live · `0` force demo · `auto` (default) probes once at startup |
| `WA_PROVIDER`, `WA_PROVIDER_TOKEN` | live WhatsApp Business API delivery (dry-run outbox otherwise) |

---

## API surface — highlights

```
GET  /api/status?q=Soweto&device=…      whole Now tab in one call
GET  /api/impact?q=…                    threats + confidence + task plan
GET  /api/cost/{electricity|water|basket|tou|harvest|solar|appliance}
POST /api/cost/leak                     two readings → leak verdict
GET  /api/grid?area=…   POST /api/grid/add   POST /api/grid/claim
GET  /api/grid/points?lat=&lon=         real OpenStreetMap points
GET  /api/stokvels   POST /api/stokvels   POST /api/stokvels/{id}/contribute
POST /api/report → receipt   GET /api/receipt/{id}   GET /api/scorecard?area=
GET  /api/me/profile   POST /api/me/action   GET /api/me/summary
GET  /api/challenges   /api/badges   /api/leaderboard
GET  /api/sources/health                per-connector status & latency
GET  /api/i18n?lang=zu                  translations
GET  /api/ussd?session=A&input=1        feature-phone menu simulator
```

---

## Files

```
app.py            FastAPI app (82 endpoints) + PWA shell routes
net.py            tiered fetch, provenance, health registry
sim.py            deterministic demo data + offline gazetteer
impact.py         ★ Prepare Window
tariffs.py        ★ money engine (real 2026/27 tariffs)
grid.py           ★ Ubuntu Grid, stokvels, OSM points
receipts.py       ★ SLA receipts, ward scorecard
resilience.py     ★ score, XP, badges, challenges, savings
i18n.py           5 languages
sources.py        weather, air, geo, Eskom, ESP, community reports
feeds.py          merged news + social + official notices, services directory
transport.py      government transport directory
push.py / whatsapp.py / ussd.py / auth.py
demo_seed.py      populate a demo neighbourhood
make_icons.py     build the PWA icon set from assets/icon-1024.png
static/           css, js, service worker, manifest, icons
templates/        index.html (app shell)
test_app.py       the automated suite
```

---

## Honest limitations

* No South African water utility exposes a real-time outage API — water status is community-verified ground truth plus official notices, never presented as an official feed.
* Per-area load-shedding schedules need `ESP_API_TOKEN`; without it the app degrades to the national stage.
* Prasa, Gautrain and BRT operators publish no open real-time feed; they are linked, with status inferred from news and community reports.
* Tariff tables are curated and dated (`tariffs.AS_OF`) — refresh them each municipal year.
* When an upstream is unreachable, data is simulated and labelled **DEMO** in the interface.
