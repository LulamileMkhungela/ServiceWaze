# Concept: ServiceWaze (working title)
## The service-disruption lifeline for South Africa

*Working names: ServiceWaze · Inkonzo (isiZulu: "service") · Siyazisa (isiXhosa: "we inform")*
*Status: Concept draft · v1.0 · August 2026*
*Category: Infrastructure & Essential Services — "Waze for services"*

---

## 1. One-line pitch

A **zero-rated WhatsApp + USSD service** that tells any South African, in their own language, *what's broken in their area right now* — water, power, transport, strikes — what to do about it, and when it's fixed; and turns every user report into a **tracked receipt** that holds the municipality accountable.

---

## 2. The problem (as of mid-2026)

**Load-shedding is over; the service crisis is not — it has just moved.** South Africa passed 365 days without load-shedding in May 2026, and Eskom projects a stable winter [1](https://www.zawya.com/en/economy/africa/south-africa-a-year-without-loadshedding-but-weak-demand-and-high-tariffs-threaten-jobs-and-eskom-revenue-gkb7azng). But the underlying infrastructure deficit simply relocated:

- **Water is the new load-shedding.** After Rand Water's winter maintenance in May–July 2026, Johannesburg suburbs went **12+ days without water**; reservoirs ran on bypass across eight supply systems; a Claremont school sent learners home because there was no water for sanitation [1](https://www.dailymaverick.co.za/article/2026-06-09-joburg-residents-go-12-days-without-water-after-maintenance-programme/), [3](https://www.dailymaverick.co.za/article/2026-05-28-water-woes-to-hit-large-parts-of-the-city-before-planned-maintenance-schedule/). SA's water system needs **R90-billion a year for a decade**; municipalities spent R2.32-billion on emergency tankers in 2023–24 alone [3](https://scrolla.africa/load-shedding-may-be-over-but-water-cuts-are-the-new-nightmare/).
- **Information is fragmented and pull-only.** The City's channels (Joburg Water WhatsApp line, City Power app, municipal websites, Eskom's line) each require the citizen to *know the channel exists, message it, and read the reply*. Coverage gaps, planned maintenance, and recovery timelines are rarely communicated proactively or in plain language.
- **The poorest are excluded from the information economy.** Official channels are app/website/English-first. The residents most harmed by outages — no storage tanks, no boreholes, no generators, work-from-home alternatives or data bundles — are the least likely to be reached.
- **There is no accountability loop.** Residents report outages into black holes. Nobody receives a "your report, its status, who's responsible, when fixed" receipt — so trust in municipal response stays at rock bottom and every outage becomes a fire-drill of guesswork.
- **Transport/strike disruptions are entirely uncovered.** The July 2023 Gauteng taxi strike (which paralysed the province for a week) and recurring Prasa/municipal strikes show that *nobody* has a single place to learn "is my route running today" across rail, taxi and bus. Workers lose wages when they can't get to work.

**The information deficit is a real-material-harm problem:** households can't store water in time, schools and clinics can't plan, businesses lose perishables and staff, workers miss shifts — all because "which suburb has water/power today" travels by word of mouth and radio, not by design.

---

## 3. Market reality check — the elephant in the room

**EskomSePush (ESP) already owns the app territory — and has pivoted.** ESP added water outage tracking in 2024, launched area-based "ESP Chats" and suburb "area pages" in Version 5 (Dec 2025), reports water outages now generate *the same activity load-shedding used to*, has 6M+ installs, partners with municipalities (Johannesburg, Cape Town), and sells its crowdsourced outage API to utilities and businesses [4](https://bandwidthblog.co.za/2025/12/06/eskomsepush-beyond-loadshedding/), [3](https://scrolla.africa/load-shedding-may-be-over-but-water-cuts-are-the-new-nightmare/), [1](https://allafrica.com/stories/202403250070.html).

**Honest verdict: do NOT build a competitor app.** ESP has the brand, the network effect, the data, and the municipal relationships. Fighting it on app territory is how projects die.

**The defensible white space — what ESP structurally is not:**

| ESP is… | ServiceWaze is… |
|---|---|
| App-first (needs smartphone, install, data, English UI) | **WhatsApp + USSD-first, zero-rated** — works on a R500 feature phone |
| Passive notifications ("your area is affected") | **Actionable + proactive** ("store water now — your system goes on bypass tonight"; "taxi strike — route 45 suspended, alternates here") |
| English-only UI | **Eleven official languages** via chat translation |
| Focused on electricity + water | **Adds the uncovered layer: transport, strikes, roads, municipal services** |
| Community chat (ESP Chats) | **The accountability receipt: report → status → responsible entity → resolution** |
| Sells an outage API to businesses | **B2B API + municipal comms contracts as the core revenue** (ESP's API is "a meaningful part of the business" — the market is proven, and it's opening up map data we can build on) |

**Strategic options (recommend in order):**
1. **Partner/build-on-top:** aggregate *including* ESP's data (they plan to open-source map data) into the WhatsApp layer. Their data in, our reach out. Complementary, not competitive.
2. **Own the underserved channels:** WhatsApp/USSD/multilingual/zero-rated is a *distribution* moat ESP doesn't have.
3. **Own transport/strikes** — a category nobody owns.
4. **Own the receipt/accountability loop** — the civic-tech wedge that builds trust and creates the B2G revenue story.

---

## 4. Target users

| Segment | Who | Job-to-be-done | Willingness to pay |
|---|---|---|---|
| **Primary: metro residents** (Joburg, Tshwane, eThekwini, Cape Town, Nelson Mandela Bay first) | Households in affected suburbs — especially no-reservoir, no-tank homes | "Tell me, in my language, if my water/power/route is affected today, and when it's back" | Free (zero cost — this is the mission) |
| **Primary: businesses & institutions** | Spaza shops, restaurants, laundromats, salons, schools, clinics, crèches | "Give me multi-area alerts + a checklist so I don't lose stock, staff or classes" | **Pays** (freemium → premium) |
| **Secondary: logistics & fleet** | Delivery, courier, e-commerce, security companies | "Route around outages/strikes before my drivers hit them" | **Pays** (API) |
| **Secondary: insurers & disaster-adjacent** | Short-term insurers, business-continuity vendors | "Outage analytics for claims, risk pricing, and proactive policyholder alerts" | **Pays** (data/API) |
| **Tertiary: municipalities & utilities** | Joburg Water, City Power, Rand Water, metros, Prasa, provincial transport | "A citizen-communications channel that works, with receipts that prove we responded" | **Pays** (B2G contracts — they already pay for SMS blasts and PR) |

---

## 5. MVP scope (first 6 months)

### Channels (in priority order)
1. **WhatsApp bot** — the product. Subscribe by suburb/ward → proactive alerts + ask/report flows. Goal: zero-rating via mobile-network partnerships (following the precedent of other zero-rated community services).
2. **USSD fallback** (`*134*xxxx#`) — for feature phones without WhatsApp; query-only ("status of my area").
3. **Lightweight PWA map** — for the app-having minority; shows live status per suburb with the same data.

### Data model: official feeds + crowdsourced ground truth
- **Official layer:** Rand Water maintenance schedules, municipal outage feeds, Eskom load-reduction schedules, Prasa/transit alerts, municipal strike notices. Aggregated by a small ops team + scrapers.
- **Crowdsourced layer:** user reports ("no water since 6am, Pimville Zone 1"), photo-verified where possible, with **trust scoring** (report weight = reporter history, neighbour corroboration, official feed match).
- **Ground-truth confirmation:** "Is the water actually back?" — resolve flow with neighbour confirmations before clearing an alert.

### Core flows (v1)
1. **Subscribe** — "Hi, tell me about: [suburb], [water/power/transport], in [isiZulu/English/isiXhosa/Sesotho]".
2. **Ask** — "What's the status of water in Soweto?" → answer + source + ETA if known.
3. **Alert (push)** — proactive: "⚠️ Planned water shutdown: your system (Eikenhof) goes off Fri 07:00–19:00. Refill tanks by Thu. Re-stabilisation may take days. Full list of suburbs →".
4. **Report** — "No water since 6am" + optional photo + address → assigned an ID (the receipt).
5. **Resolve** — "Is your water back?" → confirmed by ≥2 neighbours → marked resolved, receipt closed.
6. **Receipt (the accountability product)** — "Your report #JW-4821: Pimville Zone 1 · burst pipe · logged with Joburg Water · last update: 'crew dispatched' · status: OPEN 14 days."

### Languages
isiZulu, isiXhosa, Sesotho, English first; Afrikaans, Sepedi, Setswana, Tshivenda, Xitsonga, siSwati, Ndebele progressively. Every alert templated in all languages; free-text answers via translation layer.

### Explicitly OUT of MVP
❌ Native app (defer 12+ months — channel priority is WhatsApp/USSD)  
❌ Anything requiring login, bank account, or email  
❌ Selling ads or user data  
❌ Trying to replace municipal systems — we feed them and mirror them

---

## 6. Trust & anti-misinformation design

- **Source labelling:** every alert carries a source badge (OFFICIAL · VERIFIED COMMUNITY · UNVERIFIED REPORT) — the single most important trust feature.
- **Report weighting:** reputation accrues per phone number; a user who logs 30 accurate reports outranks a brand-new number; mass-reporting attacks get damped.
- **Verification by corroboration:** "resolved" and "new outage" claims need neighbour confirmation before changing official-ish status.
- **Muted by default:** no panic loops, no unverified "crime alert" streams (that's ESP Chats' lane); we do *services*, not crime.
- **POPIA by design:** phone numbers are pseudonymous; no contact lists harvested; no data shared with municipalities without explicit consent (and no PII sold, ever).

---

## 7. Business model

**Mission for residents is free. Money comes from institutions.**

| Revenue stream | Description | Maturity |
|---|---|---|
| **B2G comms contracts** | Municipalities/utilities pay for a citizen channel that works + the receipt/response analytics (they already pay for SMS blasts, PR, call centres). Anchor: "we measurably improved your response visibility" | Pilot: 6–12 mo |
| **B2B API** | Outage + strike feeds for logistics, insurers, security, retail; usage-based pricing (ESP has proven demand for exactly this) | 9–18 mo |
| **Freemium premium** | Businesses pay for multi-area monitoring, checklists, staff alerts (R150–R500/mo) | 6–12 mo |
| **Insights layer** | Aggregated, anonymised outage analytics sold to insurers/researchers/municipal planning — the "where does the city break most" report | 12+ mo |

**Unit-economics sketch:** WhatsApp Business API costs per message (scale discounts + zero-rating negotiations), small ops/verification team (8–12 people at scale), no hardware. The heavy cost is the *ground-truth ops layer* — keeping official feeds clean and reports verified — which is also the moat. Break-even target: 2–3 municipal contracts + 40–60 B2B API clients.

---

## 8. KPIs (what success looks like)

- **North star: Actionable Alert Rate** — % of alerts where the user did something (stored water, rerouted, refilled tanks, notified staff). Measure via micro-polls in the bot ("Did you act on this? Yes/No").
- Coverage: % of metros' suburbs with active subscriptions.
- Delivery: % of alerts read within 30 minutes (WhatsApp read receipts).
- Ground truth: % of reported outages with a verified resolution within 48h.
- Receipt rate: % of reports that receive a status update from the responsible entity.
- Retention: weekly active subscribers; 30-day return rate.

---

## 9. Risks & mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **ESP or a municipal app copies the WhatsApp layer** | High | Move fast on zero-rating + language + transport; build the B2G receipt story early; consider partnership/white-label for ESP instead of rivalry |
| **Municipal data access / procurement inertia** | High | Start with *public* feeds + crowdsourcing (no permission needed for MVP); use receipts as the proof-of-value that opens B2G doors; keep pilot small (1 metro, 3 suburbs) |
| **WhatsApp API costs at scale** | Medium | Zero-rating partnerships; batch digests instead of per-alert messages; USSD for query-only |
| **Misinformation / false reports** | Medium | Source badges, corroboration rules, reputation weighting (Section 6) |
| **Zero-rating agreements shift or end** | Medium | WhatsApp remains cheap even unzero-rated; USSD is the fallback; don't architect around one telco |
| **Load-shedding stays dormant → "why do we need this?"** | Medium | The pitch is *services*, not electricity; water/transport/strikes are the growth vector (and load-reduction persists in parts of Gauteng) |
| **Liability for wrong info** (e.g., a business acts on a false alert) | Low-Med | Clear source labels + disclaimers; B2B contracts with SLA wording |

---

## 10. Roadmap

- **Months 0–3 (Validate):** 30 interviews across 2 metros (residents, spaza owners, school principals, municipal comms officers); confirm the three wedge suburbs; test WhatsApp flows with 200 users; model WhatsApp API costs at 100k subscribers; open talks with ESP re: data sharing.
- **Months 3–9 (MVP):** WhatsApp bot + USSD + PWA in 3 languages, 3 suburbs, water+power+transport alerts; report/receipt/resolve loop; zero-rating pilot with one network.
- **Months 9–18 (Grow):** 2 metro partnerships (comms contract), 10 suburbs, 5 languages; B2B API v1 for logistics; premium tier.
- **Months 18–24 (Scale):** 4–6 metros, transport/strike coverage national, insights layer, 1M+ subscribers target.

---

## 11. The go/no-go questions (before writing any code)

1. **Is the WhatsApp distribution wedge real?** Can we get 10,000 subscribers in one suburb cluster in 90 days with no paid acquisition? (Test: church/household-group seeding, spaza posters, ward councillors.)
2. **Will a municipality actually pay?** Find one comms officer willing to sign a letter of intent for the receipt/response-analytics product.
3. **Will ESP share or sell data?** A partnership conversation in month 1 changes everything (their data in, our reach out).
4. **Do the numbers hold?** WhatsApp API costs per 100k active subscribers vs. 2–3 municipal contracts + 40 B2B clients.

If yes on all four → build. If any is a hard no → pivot the wedge (transport/strikes-only is the most likely pivot).

---

## 12. Appendix — competitive landscape

| Player | What it does | Gap ServiceWaze exploits |
|---|---|---|
| **EskomSePush** | App: load-shedding, water outages, area chats, API | App-first, English, passive; no WhatsApp/USSD/zero-rated, no transport, no receipt loop. **Default partner, not enemy** |
| **Municipal WhatsApp lines & apps** (Joburg Water, City Power, CT Services) | Pull-only, per-utility, per-municipality | Fragmented; citizen must know each channel; no cross-municipality, no proactive multi-service alerts; rarely multilingual |
| **Community WhatsApp groups** | De facto lifeline: tanker locations, rumour control | Unstructured, exclusionary (join by invitation), no verification, no archive, burns data |
| **Radio (community & public)** | Broad announcements | One-way, broadcast-level, not area-specific, not on-demand |
| **Social media (X, Facebook)** | Fast rumour spread, official accounts | Unfiltered, algorithmic, expensive data, no structured verification |

---

## 13. Sources

- Scrolla (Dec 2025): Water cuts the new nightmare; ESP water activity; R90bn/yr figure — scrolla.africa
- Bandwidth Blog (Dec 2025): ESP V5, area pages, API business — bandwidthblog.co.za
- AllAfrica (Mar 2024): ESP water outage tracking — allafrica.com
- Daily Maverick (Jun 2026): Joburg 12 days without water — dailymaverick.co.za
- Daily Maverick (May 2026): Pre-maintenance outages, schools closed — dailymaverick.co.za
- Zawya (May 2026): 365 days without load-shedding; EAF trends — zawya.com
- Mail & Guardian (Apr 2026): Stable winter outlook — mg.co.za
- gov.za (Mar 2026): 300 days without load-shedding — gov.za
