# Competitive analysis — who we beat, what we borrow

*Researched September 2026. The point of this document is not to be flattering to us: it is to name the incumbents' real strengths, show where ServiceWaze is structurally different, and list the exact endpoints we reuse rather than rebuild.*

---

## 1. The field

### 1.1 EskomSePush (ESP) — the category king
**What it is:** 6M+ installs; load-shedding schedules, water outage tracking, area pages, "ESP Chats", municipal partnerships (Johannesburg, Cape Town), and a **paid API business** selling crowdsourced outage data.

| Strength | Weakness (our opening) |
|---|---|
| Brand, network effect, municipal relationships | **Notify-at-impact.** It tells you when you're *in* an outage, not how long you have *before* one |
| Per-area schedules that actually work | **English-first, app-first** — needs a smartphone, an install, data |
| Community reports at scale (ground truth) | No cost/rand layer — nothing tells a household what the outage costs or how to cut it |
| Proven B2B API demand | No structured neighbour **capacity** sharing (chat ≠ a grid) |
| Dec 2025 v5: area pages, chats | No accountability artefact: no SLA clock, no public scorecard |

**Our move:** *reuse, don't fight.* ServiceWaze implements ESP's documented endpoints — `GET /status`, `/areas_search?text=`, `/areas_nearby?lat&lon`, `/area_information/{id}/allowance`, `/area_information/{id}/event` — activated by `ESP_API_TOKEN`. Their data in, our reach out (WhatsApp, USSD, 5 languages, offline PWA). We are complementary infrastructure, and that is a deliberate, defensible position.

### 1.2 Municipal apps & WhatsApp lines (Joburg Water, City Power, CoCT, eThekwini)
**Strengths:** authoritative, free, official reference numbers.
**Weaknesses:** pull-only (the citizen must know the channel exists and ask), one utility per channel, English-first, no cross-service picture, no proactive countdown, no memory of whether the promise was kept.
**Our move:** we *link and route* to them (every service card is a tappable `tel:`/URL), and we add the layer they don't have — the receipt with a clock, and the cross-service countdown.

### 1.3 Community WhatsApp & street groups
**Strengths:** zero-friction, trusted, already the real lifeline (tanker locations, "is it just me?").
**Weaknesses:** invitation-only, unstructured, no archive, burns data, rumour amplification, invisible to outsiders.
**Our move:** keep the warmth, add structure — scoped to a street, time-boxed, claimable, and visible to anyone on the street without an invitation.

### 1.4 StokFella / Stokvel Marketplace (FNB Best Financial Solution 2025)
**Strengths:** digitised a deeply South African financial behaviour; trust and group mechanics.
**Weaknesses:** savings for savings' sake — not tied to a survival outcome.
**Our move:** **resilience stokvels** — the pot has a purpose with a physical result: a tank, a solar kit, a bulk staple buy. The contribution is the means; ending the outage is the product.

### 1.5 iER — Integrated Emergency Response (FNB Most Innovative + Best South African 2025)
**Strengths:** proves judges reward **locally-relevant, bold, real-world problem solving**; emergency response coordination.
**Our move:** adjacent, not overlapping. iER responds to the emergency; **ServiceWaze prevents the household from being in one** — and hands the accountability data back to the city.

### 1.6 Vula Medical (FNB App of the Year 2025)
**Strengths:** built for rural/underserved reality, clinician-to-specialist, works where the infrastructure doesn't.
**Lesson we applied:** design for the *worst* device and the *weakest* connection first; make the core loop work offline. (Our PWA shell, data-saver, USSD and read-aloud exist for exactly this reason.)

### 1.7 GridCars / solar & energy apps, load-shedding widgets
**Strengths:** EV/solar telemetry, accurate schedules.
**Weaknesses:** single-domain (electricity), aimed at households that can afford solar.
**Our move:** multi-service, and aimed at the household that cannot.

---

## 2. Where ServiceWaze is structurally different (the moat)

| # | Moat | Why it's hard to copy fast |
|---|---|---|
| 1 | **Prepare Window** (countdown *to* impact + time-budgeted plan) | Requires fusing weather + utility status + schedules + community signal + household profile; incumbents are optimised around notification-at-impact |
| 2 | **Ubuntu Grid + reputation** | Network effect at *street* level; worthless until a street is dense, then unreplaceable |
| 3 | **Receipts + ward scorecard** | The B2G wedge: it is the artefact municipalities buy, and it compounds with history |
| 4 | **Money engine on curated, dated tariffs** | Boring, unglamorous, constantly maintained — exactly why nobody does it, and exactly why it saves real money |
| 5 | **Distribution**: USSD + WhatsApp + 5 languages + offline + zero-login | A distribution moat, not a feature |
| 6 | **Provenance-first design** | Every value tagged and inspectable; trust is the product in a misinformation-heavy space |

---

## 3. Competitor endpoints & services we deliberately reuse

| Provider | Endpoint / service | Used for | Key |
|---|---|---|---|
| **EskomSePush** | `https://api.eskomsepush.org/status` | national stage | `ESP_API_TOKEN` (free tier) |
| | `/areas_search?text=`, `/areas_nearby?lat&lon` | area resolution | same |
| | `/area_information/{id}/allowance` | per-area schedule windows | same |
| | `/area_information/{id}/event` | future events | same |
| **Eskom** | `https://loadshedding.eskom.co.za/loadshedding/GetStatus` | national stage (keyless fallback) | none |
| **Open-Meteo** | `api.open-meteo.com/v1/forecast` | weather, advisories, sunrise, radiation | none |
| | `air-quality-api.open-meteo.com/v1/air-quality` | US AQI and pollutants | none |
| | `geocoding-api.open-meteo.com/v1/search` | SA place search | none |
| **Nominatim** | `nominatim.openstreetmap.org/reverse` | GPS → suburb name | none (throttled) |
| **RainViewer** | `api.rainviewer.com/public/weather-maps.json` | live radar tiles | none |
| **OpenStreetMap Overpass** | `overpass-api.de/api/interpreter` | standpipes, boreholes, clinics, markets, food banks | none |
| **Johannesburg Water** | `johannesburgwater.co.za/feed/` | official water notices (scrape — no API exists) | none |
| **Google News SA / The Citizen / BusinessTech / Mastodon** | RSS & tag timelines | merged news + social + official stream | none |
| **City of Cape Town** | Open Data Portal (`odp.capetown.gov.za`) & load-shedding API | roadmap: CoCT-native stage & area schedule | portal token |

**Roadmap integrations** (documented, not yet wired): CoCT open-data loadshedding, Rand Water maintenance calendar, Joburg Water ArcGIS outage map, City Power faults, SAWS warnings feed, Municipal Money / National Treasury data.

---

## 4. Risks and honest answers

| Risk | Severity | Answer |
|---|---|---|
| ESP ships a WhatsApp/USSD layer | High | Our wedge is the Prepare Window + Grid + receipts, not the channel; and we already consume their API, which makes partnership cheaper than competition |
| Municipal data access never materialises | High | Community ground truth + curated tariffs + OSM work with **zero** permissions; receipts are the proof-of-value that opens the B2G door |
| Wrong information causes harm | Medium | Confidence scores, evidence lists, source badges, demo-data labels, and never inventing an official-sounding value |
| False reports / abuse | Medium | Time-decayed weighting, neighbour corroboration, rate limits, flags, pseudonymous reputation |
| WhatsApp cost at scale | Medium | Digest batching, USSD fallback, zero-rating negotiation, device-side push for smartphone users |

---

## 5. One-paragraph summary for a judge

Everyone in this category is a **mirror**: they show you the outage. ServiceWaze is a **windscreen**: it shows you what's coming, how long you have, and the road around it — then it puts the neighbour with the borehole in touch with the family with the empty bath, shows both of them what the outage is costing in rands, and hands the street a receipt proving whether the city kept its promise. That is not a feature list; it is a different category.
