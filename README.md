# ServiceWaze — South Africa's household resilience network

> **Load-shedding ended. The service crisis didn't — it moved into water, roads, food prices and tariffs.**
> ServiceWaze is the app that tells a household **what is coming, how long they have, what to do before it hits, who can help, what it costs, and whether anyone is going to fix it.**

A free, offline-capable PWA. No login, no tracking, no data selling. Five South African languages, WhatsApp and USSD channels, and every number on screen carries its source.

```bash
pip install -r requirements.txt
cd servicewaze
uvicorn app:app --port 8000
# open http://localhost:8000  →  installable PWA
```

To see it with a populated neighbourhood: `python demo_seed.py` first (**demo data**, clearly labelled).

---

## 1. The problem this actually solves

| Reality (2026) | Source |
|---|---|
| Joburg suburbs went **12+ days without water** after Rand Water maintenance | Daily Maverick, Jun 2026 |
| SA's water system needs **R90-billion a year for a decade**; municipalities spent **R2.32bn** on emergency tankers in 2023/24 | Scrolla / Daily Maverick |
| A household food basket costs **R5 530/month**; the food poverty line is **R868 per person** | PMBEJD (Jul 2026), Stats SA (2026) |
| Electricity went up **8.76%** in April 2026; Homeflex winter peak is **R8.47/kWh** — 4.4× off-peak | Eskom Schedule of Standard Prices 2026/27 |
| Municipal water rose **12.5%** (Joburg, FY2026/27) with a rising-block tariff: above 50 kl you pay **R94.92/kl** | CoJ Mayoral Committee Item 77 |

The information exists. It is spread across a utility website, a WhatsApp line, a councillor's voice note and a neighbour's shout over the wall — and it arrives **after** the taps run dry.

**ServiceWaze's bet:** the valuable moment is not the outage. It is the **two hours before** the outage, when a family can still fill a bath, charge a phone, move the meat into a cooler box, and warn the gogo next door.

---

## 2. What it does — the five loops

```
  PREDICT  →  PREPARE  →  SHARE  →  SAVE  →  PROVE  →  LEARN
  "in 3h"     "do now"    "I have"   "R saved"  "receipt #"  "was it right?"
```

### PREDICT — the Prepare Window (`impact.py`)
Fuses five signals into **one countdown per service**: weather forecasts, national load-shedding status, per-area schedules, time-decayed community reports, and official municipal notices. Every threat carries a **confidence score and its evidence**, because telling a family to fill 40 litres on a rumour is worse than silence.

### PREPARE — a task list that fits the time left (`impact.py`)
Not a generic checklist: the app computes **minutes available vs minutes needed** for *your* household (people, storage, roof, tank) and sizes the water-storage task from your actual tap flow. It tells you plainly when the plan **doesn't fit** — and what to drop.

### SHARE — the Ubuntu Grid (`grid.py`)
During a disruption the scarce resource is **capacity**, not information. Someone on your street has a borehole, a 5 000 L tank, a generator, a gas stove, a chest freezer, a bakkie, a spare seat or a plumber's wrench.
* **OFFER** – "200 L borehole water, today 16:00–20:00"
* **NEED** – "Drinking water for 5, two small children"
* **CLAIM** – one tap, neighbour-verified, earns Ubuntu Points
* **STOKVEL** – neighbours pool money for the thing that *ends* the outage: a tank, a solar kit, a bulk staple buy
* **NEARBY** – real standpipes, clinics, food banks and markets pulled live from OpenStreetMap

### SAVE — the money engine (`tariffs.py`)
The only service app that shows you the **rand value** of a disruption and of a behaviour change, using the real published 2026/27 tariffs:
* electricity bill breakdown (energy + fixed, blended R/kWh) across 8 tariffs
* **time-of-use load shifting** — the cheapest hours ranked, with the real Homeflex peak/standard/off-peak rates
* water bill against the real rising-block tariff, first 6 kl free
* **rainwater harvesting**: roof area × live 3-day rainfall forecast = litres you can catch this week
* **solar payback** from local irradiance, **appliance cost per use**, **leak detection** from two meter readings
* food basket cost vs the food poverty line, per city
* a **savings ledger** where users log what they avoided spending

### PROVE — the accountability receipt (`receipts.py`)
Every report becomes a tracked promise:

```
SW-7K3Q · Pimville Zone 1 · Burst pipe
Logged with: Johannesburg Water · 0860 562 874
SLA 24 h · Elapsed 31 h 12 min · OVERDUE
```

Receipts aggregate into a **ward scorecard**: open / fixed / overdue / average hours / SLA compliance by entity and by fault type. That is the artefact a municipality can be handed, and the reason this becomes a B2G product rather than another complaint box.

### LEARN — the forecast that gets better every time it is wrong (`insights.py`)

Status apps tell you the schedule. ServiceWaze tells you the **probability**, shows you **why**, and then
**asks the street whether it was right** — and retrains on the answer.

```
Water · 29% in the next 24 h · sample 3 events · calibration 6 verified, Brier 0.18
  ↑ 3 neighbours report no/low water now
  ↑ median gap between water events here: 2 days
  ↑ heavy rain (28 mm) forecast in 24 h
[ Yes, it happened ]   [ Nothing happened ]
```

* Poisson baseline `p = 1 − exp(−λ·h)`, λ learned per area × service from the event history
* driver boosts stack **with their weights exposed** — nothing is a black box
* outcomes are recorded by **two non-admin neighbours** (the same anti-gaming rule as receipts), then
  folded into a per-area calibration factor
* accuracy is published as a **Brier score** and shown to the user — the model's honesty is a feature

This is the answer to the question the judges actually ask: *"Can the app think for itself, forecast, and
predict likely future behaviour from patterns in data?"*

---

## 2b. Depth beyond the brief

| Capability | Where | Why it matters |
|---|---|---|
| **Live resilience map** (`grid.py` + Leaflet) | Grid → Map | "Waze for services" without a map is not Waze. Offers, requests, faults, standpipes, clinics and businesses on one map, degrading to a list offline or on data-saver. |
| **Climate-smart small business mode** (`grid.py`) | Grid → Business | The township economy *is* the resilience infrastructure. Providers are listed and peer-vouched; the **"Open right now" board** (24 h TTL) tells neighbours which spaza is running on a generator — footfall for the business, food access for the street. |
| **7-day schedule grid + heads-up alarms** | Prepare | 60-minute and 15-minute warnings **before** the lights go, with the 7-day window grid. Without a per-area feed it falls back to an explicitly-labelled estimate derived from the national stage. |
| **Offline report queue** (`static/js/app.js`) | everywhere | Reports, offers and chat are queued on the device when signal dies and flushed automatically on reconnect — the network fails exactly when you need to report. |
| **Accessibility controls** | You → Make it easier to use | Text size A/A+/A++, high contrast, reduced motion, 44 px targets, focus rings, screen-reader labels — adjustable **inside** the app, not buried in OS settings. |
| **Interactive onboarding** | first run | Three *do it now* steps (add your street → tick a prep task → offer something) that earn XP, instead of three slides nobody reads. |

---

## 3. Gamification that changes behaviour (`resilience.py`)

| Mechanic | Why it exists |
|---|---|
| **Resilience Score (0–100)** | Six transparent components (water stored, backup power, food buffer, route B, contacts/garden, community help). Shows exactly which action moves it. |
| **XP + levels** | Seedling → Sprout → Umthi → Baobab → **Ubuntu Legend** |
| **Ubuntu Points** | Earned by *helping others*: sharing, confirming, reporting, checking on the elderly |
| **Weekly challenges** | Store 40 L · Share one thing · Log your meter · Run a 5-minute drill · Check on someone · Plan route B · Stock 3 days of food |
| **9 badges** | Water Wise, First Responder, Grid Guardian, Stokvel Star, Night Owl, Money Mindful, Green Thumb, Street Captain, Ubuntu Legend |
| **Area leaderboards** | Teams are *places*, not individuals — preparedness becomes a street competition, not vanity |
| **Streaks & drills** | Quiet weeks are when preparation should happen |

Identity is a hashed **device ID** with a friendly pseudonym ("Neighbour Brave uKhozi"). No email, no phone, no name. POPIA-friendly by construction.

---

## 4. Live data, with receipts

Every value in the app carries a provenance envelope: `{value, source, tier, fetched_at, latency_ms, live}`.

| Tier | Meaning |
|---|---|
| `live` | fetched by the ServiceWaze server from the upstream API now |
| `device` | fetched by the **user's own browser** directly from a CORS-enabled API (keeps the server out of the critical path; works when the server's network is locked down) |
| `cache` | upstream unreachable, last known good served |
| `curated` | versioned, human-verified reference data (tariffs, emergency numbers) — every table is dated and cited |
| `sim` | deterministic demo data, **always** badged `DEMO` in the UI |

The in-app **Live sources** console (`/api/sources/health`) shows each connector's status, latency and last success. **ServiceWaze never invents a number and never hides where a number came from.**

Connectors: Open-Meteo (forecast, air quality, geocoding), Nominatim (reverse geocode), RainViewer (radar), Eskom `GetStatus`, **EskomSePush** (`/status`, `/areas_search`, `/areas_nearby`, `/area_information/{id}/allowance|/event` — the same endpoints the category leader uses; set `ESP_API_TOKEN`), Johannesburg Water RSS, Google News SA, The Citizen, BusinessTech, Mastodon hashtags, **OpenStreetMap Overpass** (standpipes, clinics, markets).

See **[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)** for the full table, keys and fallbacks.

---

## 5. Why this is not another status app

| | EskomSePush & status apps | Municipal apps/lines | Community WhatsApp groups | **ServiceWaze** |
|---|---|---|---|---|
| Tells you **before** impact | ⚠️ schedule only | ❌ | ❌ | ✅ **Prepare Window countdown + task plan** |
| Sized to your household | ❌ | ❌ | n/a | ✅ people, storage, roof, tank |
| Cuts household cost | ❌ | ❌ | ❌ | ✅ real tariffs, load shifting, harvest, solar, leak detection |
| Neighbour capacity sharing | ❌ | ❌ | ✅ but invisible/unstructured | ✅ **Ubuntu Grid + stokvels** |
| Accountability receipt + SLA | ❌ | ⚠️ reference numbers only | ❌ | ✅ **public receipts + ward scorecard** |
| Food access & food prices | ❌ | ❌ | ❌ | ✅ basket cost, food points, gardens |
| Works on a R500 phone / no data | ❌ app-first | ⚠️ | ✅ | ✅ **PWA + USSD + WhatsApp, offline, data-saver** |
| 11-language country | ❌ English | ⚠️ | ✅ | ✅ **5 languages shipped, 11 designed for** |
| No login, no tracking | ✅ | ❌ | n/a | ✅ |

Full analysis, including what we deliberately reuse from competitors: **[docs/COMPETITIVE_ANALYSIS.md](docs/COMPETITIVE_ANALYSIS.md)**.

---

## 6. Built for how South Africa actually connects

* **PWA** — installable, ~45 kB app shell, service worker caches the shell and the last good data; works offline
* **Low-data mode** — drops images, radar and non-essential calls
* **USSD** (`*134*xxx#` logic in `ussd.py`) and **WhatsApp** (`whatsapp.py`, provider-agnostic) for feature phones
* **Read aloud** — Web Speech API, for low-literacy and hands-free use
* **Push** — Web Push/VAPID, fired *before* impact
* **No login** for anything except writing in chat

---

## 7. Quickstart

```bash
git clone https://github.com/LulamileMkhungela/ServiceWaze.git
cd ServiceWaze
pip install -r requirements.txt
cd servicewaze
python demo_seed.py          # optional: populate a demo neighbourhood
uvicorn app:app --port 8000  # → http://localhost:8000  |  /docs for OpenAPI
```

Environment (all optional — the app degrades gracefully without every one):

| Variable | Effect |
|---|---|
| `ESP_API_TOKEN` | per-area load-shedding schedules & events (free tier at eskomsepush.org) |
| `SW_LIVE=0` / `1` | force demo data / force live calls (default: auto-probe) |
| `WA_PROVIDER`, `WA_PROVIDER_TOKEN` | real WhatsApp Business API delivery (otherwise dry-run outbox) |

Tests: `pytest -q` (34 tests, no network required).

---

## 8. API (selection)

| Endpoint | Purpose |
|---|---|
| `GET /api/status?q=Soweto&device=…` | **the whole Now tab**: place, weather, air, power, water, transport, impact+countdown, grid, cost, you |
| `GET /api/impact?q=…` | threats, confidence, evidence, task plan, minutes-left vs minutes-needed |
| `GET /api/cost/electricity?kwh=350&area=…` · `/cost/water` · `/cost/basket` · `/cost/tou` · `/cost/harvest` · `/cost/solar` · `/cost/appliance` · `POST /cost/leak` | money engine |
| `GET /api/grid?area=…` · `POST /api/grid/add` · `POST /api/grid/claim` · `GET /api/grid/points?lat=&lon=` | Ubuntu Grid + real OSM points |
| `GET/POST /api/stokvels` · `POST /api/stokvels/{id}/contribute` | community savings pots |
| `POST /api/report` → receipt · `GET /api/receipt/{id}` · `POST /api/receipt/{id}/resolve` · `GET /api/scorecard?area=` | accountability loop |
| `GET /api/me/profile` · `POST /api/me/action` · `GET /api/me/summary` · `/api/badges` · `/api/challenges` · `/api/leaderboard` | resilience & gamification |
| `GET /api/sources/health` · `GET /api/i18n?lang=zu` | transparency console, translations |

---

## 9. Repository layout

```
ServiceWaze/
├── README.md                     ← you are here
├── docs/
│   ├── PITCH.md                  competition entry, judging-criteria mapping, demo script
│   ├── COMPETITIVE_ANALYSIS.md   rivals, their strengths, what we reuse
│   ├── DATA_SOURCES.md           every connector, endpoint, key, fallback
│   └── ARCHITECTURE.md           request flow, data tiering, design decisions
├── concepts/servicewaze-concept.md   original product thesis (2026)
└── servicewaze/
    ├── app.py                FastAPI app (82 endpoints) + PWA shell
    ├── net.py                tiered live-data layer + provenance + health registry
    ├── sim.py                deterministic demo data for offline operation
    ├── impact.py             ★ Prepare Window: threats, confidence, task plan
    ├── tariffs.py            ★ money engine: real 2026/27 tariffs, harvest, solar, food
    ├── grid.py               ★ Ubuntu Grid + stokvels + OpenStreetMap points
    ├── receipts.py           ★ accountability receipts, SLAs, ward scorecard
    ├── resilience.py         ★ score, XP, levels, badges, challenges, savings ledger
    ├── i18n.py               5 languages
    ├── sources.py            weather, air, geocoding, Eskom, ESP, crowd reports
    ├── feeds.py              merged news + social + official notices
    ├── transport.py          government transport directory & status
    ├── push.py / whatsapp.py / ussd.py / auth.py
    ├── demo_seed.py          populate a demo neighbourhood
    ├── static/{css,js,icons,sw.js,manifest.webmanifest}
    └── templates/index.html  app shell
```

---

## 10. Impact model & business model

**North-star metric:** the **Actionable Alert Rate** — the share of alerts where the household actually did something (stored water, shifted load, rerouted, warned a neighbour), measured by the in-app "done" taps.

**Free for residents forever.** Revenue comes from institutions:
1. **B2G comms contracts** — a citizen channel that works, plus response analytics from the receipts
2. **B2B API** — outage, disruption and cost feeds for logistics, insurers, retailers, security
3. **Freemium for businesses** — multi-area monitoring, staff alerts, continuity checklists
4. **Group-buy margin** — stokvel purchases (tanks, solar, staples) negotiated at volume

---

## 11. Honest limitations

* No South African water utility publishes a real-time outage API. Water status is **community-verified ground truth + official notices**, never pretended to be an official feed.
* Per-area load-shedding schedules need a free `ESP_API_TOKEN`; without it the app degrades to the national stage.
* Prasa, Gautrain and BRT operators publish no open real-time feed — they are linked, with status inferred from news and community reports.
* Tariff tables are curated and dated (`tariffs.AS_OF`); they must be refreshed each municipal year.
* When no upstream is reachable, data is simulated and **labelled DEMO** in the UI.

---

*Built in South Africa, for the way South Africa actually lives — on a prepaid meter, a shared street and a phone that has to last until payday.*
