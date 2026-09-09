# Live data sources & provenance

ServiceWaze is a live-data product, and a live-data product that lies is worse than no product.
Every value returned by the API carries a provenance envelope:

```json
{
  "data": { "temp": 20.8, "desc": "Clear sky" },
  "source": "Open-Meteo Forecast",
  "tier": "live",
  "live": true,
  "fetched_at": "2026-09-08T21:49:58+00:00",
  "latency_ms": 214,
  "endpoint": "https://api.open-meteo.com/v1/forecast"
}
```

## Tiers

| Tier | Meaning | UI badge |
|---|---|---|
| `live` | fetched server-side from the upstream API now | green *source name* |
| `device` | fetched by the user's browser directly from a CORS-enabled API and reported back via `POST /api/sources/device` | green *source name* |
| `cache` | upstream unreachable; last known good served | grey *Cached* |
| `curated` | versioned, human-verified reference data (tariffs, emergency numbers, operator directory) | grey *source name* + `as_of` date |
| `sim` | deterministic demo data, generated because no upstream was reachable | amber **DEMO** |

The switch is automatic (`SW_LIVE=auto` probes once at startup) and overridable:
`SW_LIVE=1` forces live calls, `SW_LIVE=0` forces demo data, and the in-app source console can flip it at runtime (`POST /api/sources/set-live`).

---

## Connectors

| # | Source | Endpoint | Data | Key | TTL | Fallback |
|---|---|---|---|---|---|---|
| 1 | Open-Meteo Forecast | `api.open-meteo.com/v1/forecast` | current weather, 4-day forecast, advisories, UV, sunrise/sunset, shortwave radiation | none | 10 min | `sim.weather()` |
| 2 | Open-Meteo Air Quality | `air-quality-api.open-meteo.com/v1/air-quality` | US AQI, PM2.5, PM10, O₃, NO₂, SO₂, CO | none | 30 min | `sim.air()` |
| 3 | Open-Meteo Geocoding | `geocoding-api.open-meteo.com/v1/search` | SA place search (lat/lon, province) | none | 24 h | offline gazetteer (80 places) |
| 4 | Nominatim | `nominatim.openstreetmap.org/reverse` | GPS → suburb (throttled to 1 req/s) | none | 24 h | nearest place |
| 5 | RainViewer | `api.rainviewer.com/public/weather-maps.json` | live radar tile for the area | none | 5 min | none (card hidden) |
| 6 | Eskom GetStatus | `loadshedding.eskom.co.za/loadshedding/GetStatus` | national load-shedding stage | none | 5 min (last-known-good) | `sim.eskom_stage()` |
| 7 | EskomSePush | `api.eskomsepush.org/status` | national stage (authoritative) | `ESP_API_TOKEN` | 5 min | Eskom GetStatus |
| 8 | EskomSePush | `/areas_search`, `/areas_nearby` | area resolution | `ESP_API_TOKEN` | 24 h | name matching |
| 9 | EskomSePush | `/area_information/{id}/allowance` | per-area schedule windows | `ESP_API_TOKEN` | 12 h | national stage only |
| 10 | EskomSePush | `/area_information/{id}/event` | future events | `ESP_API_TOKEN` | 12 h | none |
| 11 | Johannesburg Water | `johannesburgwater.co.za/feed/` | official outage/maintenance notices | none (scrape) | 15 min | none |
| 12 | Google News SA | `news.google.com/rss/search?…hl=en-ZA&gl=ZA` | 6 topic queries, hundreds of publishers | none | 15 min | demo feed |
| 13 | The Citizen / BusinessTech | RSS | general & business SA news | none | 15 min | demo feed |
| 14 | Mastodon | `mastodon.social/api/v1/timelines/tag/{tag}` | social signal on 16 SA service hashtags | none | 15 min | demo feed |
| 15 | OpenStreetMap Overpass | `overpass-api.de/api/interpreter` | standpipes, boreholes, wells, water points, markets, food banks, clinics, pharmacies, charging stations | none | 30 min | demo points |
| 16 | Community reports | local SQLite | ground truth: no water, low pressure, leak, power out, route, restored | n/a | live | — |
| 17 | Curated tariffs | `tariffs.py` | Eskom Homepower/Homeflex/Homelight, CoCT, City Power, eThekwini, Tshwane; Joburg & Cape Town water blocks; PMBEJD food basket | n/a | dated (`AS_OF`) | — |

### Relevance & safety filters
* **On-topic gate** — every news and social item must match the app's domains (electricity, water, weather, transport, safety, municipal services, household economy). Verified: 0 off-topic items in the shipped corpus.
* **South-Africa relevance gate** for social posts — blocks non-SA noise (e.g. Polish *prasa* = "press", Washington WMATA *Metrorail*).
* **Time-decayed community signal** — reports weight `0.5^(hours/6)`, boosted by neighbour confirmations, so a week-old complaint can't trigger a countdown.

---

## Curated reference data (dated & cited)

All in `tariffs.py`, `as_of = 2026-09-01`:

| Dataset | Values | Source |
|---|---|---|
| Eskom Homeflex (incl. VAT) | winter peak **R8.4710**, standard R2.9580, off-peak R1.9083; summer peak R3.9455, standard R1.9265, off-peak R1.3051 | Eskom Schedule of Standard Prices 2026/27 |
| Eskom Homepower | flat **R3.2206**/kWh + ≈R536/month fixed (Homepower 4) | same |
| City Power Johannesburg | R2.9500/kWh + R241.50 fixed | metro schedule (indicative) |
| Cape Town Home User | R3.5595 to 600 units, R4.6906 above, R424.30 fixed; Domestic R4.1990 + R74.20 | CoCT 2026/27 |
| Johannesburg water (VAT excl.) | first **6 kl free**; >6–10 R28.91; >10–15 R29.84; >15–20 R35.65; >20–30 R64.53; >30–40 R69.45; >40–50 R86.81; >50 R94.92 | CoJ Mayoral Committee Item 77 |
| Cape Town water (incl. VAT) | 0–6 kl R25.42; >6–10.5 R34.92; >10.5–35 R52.20; >35 R100.71 | CoCT water & sanitation tariffs 2026/27 |
| Food basket | national avg **R5 530.52**; JHB R5 763.70; Durban R5 309.02; PMB R5 173.57; Springbok R6 109.75 | PMBEJD Household Affordability Index, Jul 2026 |
| Poverty lines | food poverty line **R868**/person/month; nutritional basket for 4 = R3 667.72 | Stats SA 2026; PMBEJD Mar 2026 |

---

## Adding a connector

1. Add the fetch with `net.fetched(url, "Source name", ttl=…, sim=lambda: …)`.
2. Return the provenance envelope into the response (`sources._place_meta(env)`).
3. Provide a deterministic `sim` fallback so the product still renders offline.
4. Document it in this table and in the README connector list.
5. Add a test asserting the `tier`/`live`/`source` keys exist (see `test_data_is_provenance_tagged`).

That is the whole contract: **live when it can be, honest when it can't.**
