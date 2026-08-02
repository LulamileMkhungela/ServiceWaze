# ServiceWaze — live status hub for South African services (PWA)

**Electricity · Water · Weather & Air · Transport · News & Social · Community reports — all merged into one feed.**

Answers the question people actually ask during disruptions: *"what's broken in my area right now, what do I do, who do I report it to?"*

## Quickstart

```bash
pip install -r requirements.txt
uvicorn app:app --port 8000
# open http://localhost:8000  (mobile-first; installable PWA)
```

## Features

- **Multi-location watchlist** — add any suburb/town (search) or your GPS location; switch areas with one tap; each area gets its own live dashboard.
- **Merged single feed** — news + social + advisories + reports normalised into one shape, filterable by **category** (electricity / water / weather / transport / safety / economy), **area** (province tags, national items included) and **keyword**.
- **Live official data (no keys):**
  - Load-shedding stage — Eskom `GetStatus` endpoint
  - Weather + 3-day forecast + advisories engine (heat/cold/heavy rain/wind) — Open-Meteo
  - Air quality (AQI, PM2.5, PM10, O₃, NO₂, SO₂) — Open-Meteo Air Quality
  - Suburb geocoding — Open-Meteo Geocoding
- **News & social (merged):** Google News RSS (SA edition — 6 topic queries, hundreds of publishers), The Citizen RSS, BusinessTech RSS, Mastodon hashtags (SA-relevance filtered so only South African posts show). Optional: set `ESP_API_TOKEN` for the EskomSePush schedule feed.
- **Community reports** — users report what the app missed (no water, low pressure, leak, restored, power out, route, other) with optional **photo**; neighbours **confirm**; reports appear for the matching area automatically. Rate-limited, anonymous by default.
- **Notifications & WhatsApp** — in-app notification centre with thresholds (load-shedding stage ≥2, severe weather, new reports in your areas, news for your areas) via the browser Notification API; one-tap **"send to WhatsApp"** buttons that build a ready-made status/digest message (works with no account — real WhatsApp Business API delivery is a deployment step, see roadmap).
- **PWA** — installable, offline-capable (service worker caches shell + last data), 4 languages (EN / isiZulu / isiXhosa / Sesotho).
- **No login needed.** Areas, settings and notification history live on the device (localStorage). POPIA-friendly: no account, no contact harvesting, no data selling.

## Government transport (v2.2)

A dedicated **Transport tab** shows ALL government transport for the selected area:
- **Gauteng**: Prasa Metrorail (Joburg/Pretoria incl. Soweto lines), Gautrain (train), **Gautrain Bus** (feeder), Rea Vaya (Joburg BRT), A Re Yeng (Tshwane BRT), Shosholoza Meyl (long-distance)
- **Western Cape**: Prasa Metrorail (Cape Town), MyCiTi (BRT), Shosholoza Meyl
- **KwaZulu-Natal**: Prasa Metrorail (Durban), GO!Durban (BRT)
- **Eastern Cape / Free State / Limpopo / Mpumalanga / North West / Northern Cape**: Prasa Metrorail where applicable + provincial transport info
- Each operator: mode icon, operator, **live status badge** (green = no disruptions reported / red = disruption reported, from the merged news+social feed + community route reports), phone, official site/timetable link.
- **Area scoping**: if the selected area has no local government transport, the app does NOT show an empty page — it asks "Want to see government transport for nearby areas?" with one-tap area chips (e.g., Malamulele → Polokwane, Thohoyandou, Tzaneen…; Soweto nodes → Soweto + province cities).
- Honest note: no SA transit operator exposes a public realtime API, so status comes from news/social + community reports (same model as ESP's water tracking) and timetables are linked to official apps.

## Area scoping + GPS (v2.2)

- **GPS-first**: on first use the app tries to detect your current location ("My location" chip); added chips are the OTHER locations you want updates for.
- **Selected chip drives everything**: Home (weather/air/outages/reports), Transport (govt transport for that area), News (defaults to "My area" scope — the selected chip + national stories, with All-areas override), Alerts and More all follow the selected area chip.

## Chat: read free, write with login (v2.6)

- **Everyone can read the community chat** (and all feeds/status) with no login.
- **Writing requires a (free) account**: username + password, hashed with PBKDF2-SHA256 (salted), session tokens with 7-day expiry. No email needed.
- Chat author shows the username; flagging messages also requires login (anti-abuse).
- UI: chat card shows a "🔐 Log in to join the chat" button when logged out; auth modal (login / create account) opens in-app; More tab shows "Signed in as …" + Log out.
- Endpoints: `/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`. `POST /api/chat` and `POST /api/chat/report` return 401 without a valid `Authorization: Bearer <token>`.
- Everything else (status, news, reports, chat read) stays open — POPIA-friendly, no email/phone required.

## Water data: API-less scraping (v2.5)

No SA water API exists, so where there's no API we scrape official pages/RSS:
- **Johannesburg Water official RSS** (`johannesburgwater.co.za/feed/`) — pulled every feed refresh, water-relevant posts only, shown in the water card as **🏛️ Official notices** AND in the newsfeed flagged with an official badge.
- **City Power & Rand Water** — probed; unreachable from this environment (documented stubs; wire them where reachable).
- Community reports remain the ground-truth layer for everything else (same model ESP uses).

## Social updates in the newsfeed (v2.5)

If Eskom/Rand Water/PRASA (or anyone) shares on socials, it lands in the merged feed:
- **Mastodon hashtags** (free, keyless): `eskom`, `loadshedding`, `randwater`, `wateroutage`, `citypower`, `loadreduction`, `prasa`, `metrorail`, `gautrain`, `floods`, `saws`, `taxi`, `johannesburgwater`, `myciti`, `reavaya`, `gauteng` — SA-relevance filtered.
- Filter hardening: WMATA (Washington "Metrorail") leaks blocked, Polish "Prasa" (press) leaks blocked, on-topic gate applies to social too. Verified: 0 US leaks, 0 Polish leaks, 25 SA social items.
- News tab: "Social" filter shows only social posts; official items get a 🏛️ badge.
- (Twitter/X & Instagram have no free API — noted in roadmap; Bluesky/Reddit blocked from this network.)

## Polish & UX (v2.5)

- First-run **intro modal** (3 steps) — dismissible, shown once.
- Hero **quick actions**: Report · WhatsApp · Share · Read aloud (one-thumb access).
- **Official-notice cards** in the water section; official badge in news.
- **Vibration** on report send & confirm (mobile).
- aria-labels on navigation & FAB; keep original dark+sky design (no competitor styling).

## Extra features (v2.3) — beyond any competitor

- **Live rain radar** — RainViewer (free, keyless): real-time radar tile for your area with last-frame time + "open live radar" link.
- **GPS auto-naming** — after detecting your location, the app reverse-geocodes it (Nominatim, free) so the chip shows the actual suburb (e.g. "Senaoane, Gauteng") instead of "My location".
- **Sunrise/sunset** in the 3-day forecast (Open-Meteo).
- **🔊 Read alerts aloud** — Web Speech API reads the area status + advisories in English (great for low literacy / hands-free).
- **📤 Download area data (JSON)** in More — export any area's full status for offline use/sharing.
- **News relevance gate (verified)**: every news item must match the app's domains (electricity, water, weather, transport, safety, municipal services, household economy). Live check: 52/52 news items on-topic, 0 off-topic.

## ESP Business API — full coverage

All documented EskomSePush Business API endpoints are implemented (active when `ESP_API_TOKEN` is set):
- `GET /status` — national load-shedding stage (`sources.eskomsepush_status`)
- `GET /areas_search?text=` — area lookup (`esp_area_id`)
- `GET /areas_nearby?lat&lon` — GPS → area (`esp_area_id`)
- `GET /area_information/{id}/allowance` — per-area schedules (`esp_area_schedule` → next-window countdown + 55-min heads-up)
- `GET /area_information/{id}/event` — future events (`esp_area_events`, `/api/electricity/events`)

Free token: eskomsepush.org / developer.sepush.co.za (free tier 50 req/day). Graceful fallback without a token.

## Free APIs checked (aggressively, this session)

| Source | Status | Used for |
|---|---|---|
| Eskom GetStatus + legacy endpoints | ✅ live | national stage (legacy schedule endpoints WAF-locked) |
| Open-Meteo (forecast + air + geocoding + sunrise) | ✅ live | weather/AQI/geo |
| RainViewer radar | ✅ live | rain radar tiles |
| Nominatim reverse geocode | ✅ live | GPS auto-naming (throttled+cached) |
| Google News SA / Citizen / BusinessTech / Mastodon | ✅ live | merged news+social |
| ESP Business API | ⚠️ needs free token | schedules/events |
| what3words, Google Maps, MDB ward boundaries, WhereIsMyTransport, MyCiTi ArcGIS | 🔒 need key/signup or unreachable from sandbox | roadmap |

## Push, WhatsApp & USSD (v2.1)

- **Web Push (works when the app is closed)**: VAPID keys auto-generated on first run (`data/vapid.json`). Alerts tab → "Enable push" subscribes the browser; a server-side engine (runs every 60s) pushes on **load-shedding stage changes (stage ≥ 2)** and **new community reports matching your area**. `POST /api/push/test` sends a test push; `GET /api/push/vapid` serves the public key.
- **WhatsApp alerts**: provider-agnostic module (`whatsapp.py`). Opt in with your number in the Alerts tab → messages recorded to an **outbox** (dry-run mode, verified) — flip to real delivery with `WA_PROVIDER=clickatell` + `WA_PROVIDER_TOKEN`. Endpoints: `/api/whatsapp/optin`, `/api/whatsapp/test`, `/api/whatsapp/outbox`.
- **USSD** (feature-phone channel): full menu flow implemented (`ussd.py`) — area status (live), report an issue (saves to the same community DB), emergency numbers. Test it: `GET /api/ussd?session=A&input=1` then `input=Soweto`. Real deployment wires the same logic to a carrier aggregator.

## API

- `GET /api/status?q=Soweto` — full bundle: place, weather, air, electricity, water (official + reports), transport
- `GET /api/feed?areas=gauteng&categories=water&q=…&limit=80` — merged news+social feed, filterable
- `GET /api/news` · `GET /api/social` — feed subsets
- `GET /api/services` — services directory (contacts/links, all clickable) + preparedness checklists
- `GET /api/areas?q=…` — suburb search · `GET /api/air?lat&lon` — air quality
- `POST /api/report` `{area, kind, message?, reporter?, photo?, lat?, lon?}` · `POST /api/confirm` `{id}` · `GET /api/photo/{id}`
- `GET /docs` — OpenAPI docs · `GET /snapshot.html?q=Cape Town` — static snapshot

## Static preview (no server needed to view)

```bash
uvicorn app:app --port 8000      # terminal 1
python snapshot.py "Soweto"      # terminal 2 → writes preview.html
```

## How ServiceWaze compares to EskomSePush (the model)

Yes — ServiceWaze deliberately uses the **EskomSePush model**: live status from official sources + community-sourced ground truth, free for users, no login. That model is proven (ESP: ~10M users). ServiceWaze keeps it and adds more.

**Adopted from the ESP model**
- Load-shedding status from official Eskom sources (national stage live; per-area schedules via the free ESP API when `ESP_API_TOKEN` is set)
- Community reports as ground truth for water/outages (ESP's own model — tanker locations, reservoir status)
- Free, no login, area-based experience, follow multiple areas

**Added beyond ESP**
- **WhatsApp-first reach + USSD fallback** — ESP is native-app-only; we meet users where they already are (web PWA now, WhatsApp/USSD in roadmap)
- **Multilingual UI** — EN / isiZulu / isiXhosa / Sesotho (ESP is English-only)
- **Merged news + social feed** — Google News SA, Citizen, BusinessTech, Mastodon, relevance-filtered and merged into ONE feed (ESP has neighbourhood chat, not news)
- **Weather forecasts + advisories + air quality** — heat/cold/flood/wind alerts and live AQI per area (ESP has basic weather in area alerts, no AQI)
- **Richer reporting** — photo + voice-note reports, neighbour confirmations (ESP's reports live inside chat)
- **Services directory** — clickable tel:/WhatsApp/official links for electricity, water, transport, weather, emergency + preparedness checklists
- **Merged incident timeline** — advisories + reports + news in one chronological stream (ESP has area pages, not a merged multi-source timeline)
- **PWA, offline-capable, ~30KB, no install needed, no login**
- **Notification centre + one-tap WhatsApp status/digest sharing** + streak gamification

**Where ESP is still ahead (honest gaps)**
- Per-area load-shedding **schedules** out of the box (we need the free ESP API key; scaffold is in place)
- **Push notifications with 55-min/15-min heads-up** before a slot
- **Community chats** per suburb ("is it just me?", AI-moderated) — we deliberately skip chat moderation for v1
- **Live load-reduction feed** (targeted cuts in Gauteng)
- **Service-delivery stats** (outage frequency/duration per area)
- Native app stores + 10M-user network effect and brand



```
app.py              FastAPI backend (API + PWA routes + UI)
feeds.py            merged data layer: Google News, Citizen, BusinessTech, Mastodon,
                    air quality, category classifier, SA area tagging, services directory
sources.py          live sources: Eskom status, Open-Meteo weather/geocode, community reports DB
templates/index.html  PWA UI (single page, tabs, multi-area, i18n)
static/sw.js        service worker (offline shell + stale data cache)
static/manifest.webmanifest, static/icons/  PWA install assets (icons generated by make_icons.py)
snapshot.py         bakes live data into a static preview.html
```

## Roadmap to production (what a real launch adds)

1. **Per-area load-shedding schedules** — get the free EskomSePush API token (`ESP_API_TOKEN`, form at eskomsepush.org, ~2 days) and the schedule feature lights up automatically: next-window countdown on the Home card, a 7-day window list, and **55-minute + 15-minute heads-up notifications** before each window (client-side scheduler, tracked per window). Without a token it degrades gracefully to the national stage. (Eskom's own public schedule endpoints are WAF-locked; ESP's API is the standard free source.)
2. **WhatsApp Business API** (BSP: Clickatell / CM.com / Massivedynamics) + Meta template approval → real proactive WhatsApp alerts; service conversations are free, utility templates ~$0.0076 in SA.
3. **USSD** fallback (`*134*xxx#`) for feature phones.
4. **Official municipal feeds**: Rand Water maintenance calendar, Joburg Water ArcGIS outage map, City Power faults, SAWS warnings — replacing crowdsourced-only water status with official ground truth where it exists.
5. **Zero-rating** talks with MTN / Vodacom / Cell C.
6. **Crowd trust layer**: phone-linked reputation, corroboration thresholds, moderation queue.
7. **B2G/B2B revenue**: municipal comms contracts + outage/feed API for logistics and insurers.

## UI design notes (original, not a clone)

The interface follows common status-app usability patterns (glanceable status chips, big numbers, card sections) — the same *patterns* any good status app uses — but it is an original design: dark theme, sky-blue accent, custom layout and flow. No competitor branding, colours or layout are copied; the quick-status bar, merged timeline and multi-source cards are ServiceWaze-specific.

## Honest limitations

- Water status is **community-reported + official links**, not an official realtime feed (municipal APIs aren't public). Treat as "neighbours' reports" — verify with official channels.
- Advisories derive from forecast data, not official SAWS warnings (SAWS has no public feed; its site is linked).
- Gautrain/Prasa live APIs are not public — linked, not integrated.
- Mastodon social is SA-relevance filtered but community-sourced; Bluesky/X need keys or reachable endpoints (adapters degrade gracefully).
- News recency depends on publisher feeds (some carry older articles).
