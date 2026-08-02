# ServiceWaze — Live Status Hub for South African Services (PWA)

**Electricity · Water · Weather & Air Quality · Government Transport · News & Social · Community Reports — all merged into one real-time feed.**

ServiceWaze answers the question people actually ask during service disruptions in South Africa: *"What's broken in my area right now, what do I do, and who do I report it to?"*

---

## 🚀 Quickstart & Guide for Running the App

### 1. Repository Structure
All backend, PWA frontend, and data pipeline code is located in the **`servicewaze/`** directory:

```
ServiceWaze/
├── README.md                           # This document (Overview & instructions)
├── concepts/                           # Concept notes & design documentation
└── servicewaze/                        # Main application directory
    ├── app.py                          # FastAPI backend & PWA routes
    ├── sources.py                      # Official live data sources (Eskom, Open-Meteo, geocoding)
    ├── feeds.py                        # Merged news & social RSS/Mastodon pipeline
    ├── transport.py                    # Government transport operator directory & status
    ├── auth.py                         # Optional authentication & user sessions (for chat)
    ├── push.py                         # Web Push notification service
    ├── whatsapp.py & ussd.py           # WhatsApp outbox & USSD menu simulator
    ├── requirements.txt                # Python dependencies
    ├── test_app.py                     # Automated API & PWA tests
    ├── static/                         # PWA manifest, service worker (sw.js), icons
    └── templates/index.html            # Mobile-first PWA dashboard template
```

### 2. Running the App Locally

Ensure you have **Python 3.9+** installed.

```bash
# 1. Clone the repository and enter the application directory
git clone https://github.com/LulamileMkhungela/ServiceWaze.git
cd ServiceWaze/servicewaze

# 2. (Optional) Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the FastAPI server
uvicorn app:app --port 8000
```

Once the server is running:
- Open your browser to **[http://localhost:8000](http://localhost:8000)** to view and install the PWA.
- Interactive **OpenAPI / Swagger documentation** is available at **[http://localhost:8000/docs](http://localhost:8000/docs)**.

### 3. Running Automated Tests

Run automated backend and endpoint tests from the repository root:

```bash
pytest --ignore=servicewaze/browser_test.py --ignore=servicewaze/push_test.py --ignore=servicewaze/verify_asks.py
```
*(Note: `browser_test.py`, `push_test.py`, and `verify_asks.py` are end-to-end Playwright browser automation scripts that require a running server on port 8000).*

### 4. Generating a Static Snapshot Preview

You can bake live data into a standalone static HTML file (`preview.html`) that can be viewed offline without a server:

```bash
cd servicewaze
# While the server is running on port 8000:
python snapshot.py "Soweto"
```

---

## 🌟 What the App Does

ServiceWaze merges scattered South African utility and municipal data into a single, location-scoped dashboard:

- **📍 Multi-Location Watchlist & GPS-First:** Add any suburb or town in South Africa (e.g., *Soweto*, *Johannesburg*, *Cape Town*, *Durban*) or tap **"My location"** to auto-detect and reverse-geocode your GPS coordinates. Switch between areas with a single tap.
- **⚡ Official Live Data Without API Keys:**
  - **Load-shedding:** National Eskom stage via Eskom's `GetStatus` endpoint (with optional per-area schedules via `ESP_API_TOKEN`).
  - **Weather & Forecasts:** Real-time temperatures, 3-day forecasts, sunrise/sunset, and automated advisories (heatwaves, heavy rain, wind) via Open-Meteo.
  - **Air Quality (AQI):** Live PM2.5, PM10, ozone, and nitrogen dioxide levels via Open-Meteo Air Quality.
  - **Rain Radar:** Direct link to live RainViewer radar tiles for your selected area.
- **🚆 Dedicated Government Transport Tracking:**
  - Comprehensive coverage across all provinces: **Prasa Metrorail** (Gauteng, Western Cape, KZN, Eastern Cape), **Gautrain & Gautrain Bus**, **Rea Vaya** (Joburg BRT), **A Re Yeng** (Tshwane BRT), **MyCiTi** (Cape Town BRT), **GO!Durban**, and **Shosholoza Meyl**.
  - Displays live operator status badges, phone numbers, and timetable links.
  - Smart Area Scoping: If a smaller suburb has no direct municipal transport hub, ServiceWaze suggests nearby major transport nodes.
- **📰 Merged News & Social Stream:**
  - Normalises updates from Google News SA, The Citizen, BusinessTech, and South African Mastodon hashtags (`#loadshedding`, `#randwater`, `#eskom`, `#prasa`, etc.) into a chronological feed.
  - Strictly filtered by relevance (electricity, water, weather, transport, safety, municipal services).
- **🗣️ Community Reports (Ground Truth):**
  - Users can report real-time outages (no water, low pressure, power out, route disruption, leak) with optional photos.
  - Neighbours can **confirm** reports, creating crowd-verified ground truth where official municipal APIs do not exist.
  - Rate-limited and anonymous by default.
- **💬 Free Reading & Account-Based Chat:**
  - All status feeds, reports, and community chat messages can be read by anyone **without logging in** (POPIA-friendly).
  - Users who wish to post in the chat can register a free account (no email required; PBKDF2-SHA256 password hashing).
- **🌐 Multilingual & Accessible:**
  - Available in **4 South African languages**: English (`EN`), isiZulu (`ZU`), isiXhosa (`XH`), and Sesotho (`ST`).
  - Features **Text-to-Speech (Read Aloud)** using the Web Speech API to narrate area alerts and advisories hands-free.
- **📱 Multi-Channel Reach:**
  - **Progressive Web App (PWA):** ~30KB offline-capable app shell.
  - **WhatsApp Sharing:** One-tap buttons to share formatted status updates or daily digests to WhatsApp contacts or groups.
  - **USSD Simulator:** Feature-phone menu flow implemented in `ussd.py` (`GET /api/ussd?session=A&input=1`).

---

## 🔌 API Reference

When running `uvicorn app:app --port 8000`, the following REST endpoints are available:

| Endpoint | Method | Description |
|---|---|---|
| `/api/status?q=Soweto` | `GET` | Returns full status bundle (place, weather, air quality, electricity, water, transport, reports) |
| `/api/feed?areas=gauteng&limit=80` | `GET` | Returns merged news, social, and official notices feed |
| `/api/services` | `GET` | Returns clickable emergency contacts, municipal directory, and preparedness checklists |
| `/api/areas?q=Soweto` | `GET` | Search suburbs / reverse geocoding |
| `/api/air?lat=-26.2&lon=27.9` | `GET` | Live air quality index and pollutant breakdown |
| `/api/report` | `POST` | Submit a community report (`{area, kind, message, reporter, photo}`) |
| `/api/confirm` | `POST` | Confirm a neighbour's report (`{id}`) |
| `/api/ussd?session=A&input=1` | `GET` | USSD feature-phone menu simulator |
| `/docs` | `GET` | OpenAPI / Swagger interactive documentation |
