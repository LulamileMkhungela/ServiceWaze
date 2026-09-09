"""Deterministic demo data for ServiceWaze.

ServiceWaze is a *live* app: every module first tries the real upstream API.
This module exists for one reason only — so the product still works, end to
end, when the host running it cannot reach the internet (an offline demo, a
locked-down corporate network, a judge's laptop on a plane, a CI runner).

Rules:
  * everything here is deterministic (same place + same hour = same numbers)
  * everything returned is clearly labelled `tier: "sim"` / `live: false` by
    net.py, and the UI shows a visible "DEMO DATA" badge
  * NOTHING here invents an official-sounding source name
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from net import jitter, stable_hash

WMO = [(0, "Clear sky", "☀️"), (1, "Mainly clear", "🌤️"), (2, "Partly cloudy", "⛅"),
       (3, "Overcast", "☁️"), (61, "Light rain", "🌧️"), (63, "Rain", "🌧️"),
       (80, "Light showers", "🌦️"), (95, "Thunderstorm", "⛈️")]


def _now():
    return datetime.now(timezone.utc)


def weather(lat, lon):
    n = _now()
    hour_seed = (stable_hash(round(lat, 2), round(lon, 2)), n.strftime("%Y%m%d%H"))
    h = stable_hash(*hour_seed)
    # diurnal temperature curve, southern-hemisphere late-winter flavoured
    hour = (n.hour + 2) % 24  # SAST
    base = 12 + 12 * math.sin(max(0.0, min(1.0, (hour - 6) / 12)) * math.pi)
    temp = round(base + 6 + jitter(("t", hour_seed), 3.0), 1)
    code, desc, icon = WMO[h % len(WMO)]
    daily = []
    for i in range(3):
        d = n + timedelta(days=i)
        tmax = round(temp + 6 + jitter(("mx", hour_seed, i), 3), 1)
        tmin = round(temp - 8 + jitter(("mn", hour_seed, i), 2), 1)
        rain = round(max(0.0, jitter(("pr", hour_seed, i), 9)), 1)
        daily.append({
            "date": d.strftime("%m-%d"), "code": code, "icon": icon,
            "tmax": tmax, "tmin": tmin,
            "precip_prob": int(abs(jitter(("pp", hour_seed, i), 45))),
            "precip_sum": rain,
            "gusts": round(20 + abs(jitter(("gu", hour_seed, i), 35)), 1),
            "uv": round(max(0.0, 6 + jitter(("uv", hour_seed, i), 4)), 1),
            "sunrise": "06:4" + str(i % 3), "sunset": "18:0" + str(i % 4),
        })
    advisories = []
    for d in daily:
        if d["tmax"] >= 35:
            advisories.append({"level": "severe", "icon": "🥵",
                               "text": f"Extreme heat {d['tmax']:.0f}°C on {d['date']} — hydrate, check on the elderly."})
        if d["precip_sum"] >= 25 and d["precip_prob"] >= 60:
            advisories.append({"level": "warn", "icon": "🌊",
                               "text": f"Heavy rain risk on {d['date']} ({d['precip_sum']:.0f}mm) — low-lying areas may flood."})
        if d["tmin"] <= 2:
            advisories.append({"level": "warn", "icon": "🥶",
                               "text": f"Very cold night ({d['tmin']:.0f}°C) on {d['date']} — protect the vulnerable."})
    return {
        "current": {"temp": temp, "feels": round(temp - 1.5, 1), "humidity": 40 + (h % 40),
                    "wind": round(8 + abs(jitter(("w", hour_seed), 12)), 1),
                    "gusts": round(18 + abs(jitter(("g", hour_seed), 25)), 1),
                    "desc": desc, "icon": icon},
        "daily": daily,
        "advisories": advisories,
        "source": "ServiceWaze demo model",
    }


def air(lat, lon):
    h = stable_hash(round(lat, 2), round(lon, 2), _now().strftime("%Y%m%d%H"))
    aqi = 20 + h % 90
    label, band = ("Good", "good") if aqi <= 50 else ("Moderate", "moderate") if aqi <= 100 else ("Unhealthy (sensitive)", "warn")
    return {"aqi": aqi, "label": label, "band": band,
            "pm2_5": round(aqi / 3, 1), "pm10": round(aqi / 2, 1),
            "o3": round(30 + h % 40, 1), "no2": round(5 + h % 25, 1),
            "so2": round(2 + h % 12, 1), "co": round(200 + h % 300, 1),
            "source": "ServiceWaze demo model"}


def eskom_stage() -> str:
    h = stable_hash("eskom", _now().strftime("%Y%m%d"))
    return str(h % 4)  # 0..3


def feed_items(area: str = "Soweto"):
    n = _now()
    seeds = [
        ("Rand Water maintenance — reservoir levels recovering",
         "Bulk supply to the Commando and Eikenhof systems is stabilising after planned maintenance; some suburbs may still experience low pressure.",
         "water", "Demo newsroom"),
        ("City Power warns of network overload in dense suburbs",
         "Illegal connections and illegal load-shedding bypasses continue to trip mini-substations overnight.",
         "electricity", "Demo newsroom"),
        ("Heavy rain warning for the interior",
         "Thunderstorms with hail possible from late afternoon; avoid low-lying bridges.",
         "weather", "Demo newsroom"),
        ("Commuters report delays on the Soweto–CBD corridor",
         "Route disruption reported during the morning peak; alternates suggested.",
         "transport", "Demo newsroom"),
        ("Food prices: maize meal and cooking oil ease",
         "Household food basket tracking shows slight relief on staple items this month.",
         "food", "Demo newsroom"),
    ]
    out = []
    for i, (title, body, cat, src) in enumerate(seeds):
        out.append({
            "id": f"sim{i}", "type": "news", "category": cat, "source": src,
            "title": title, "body": body, "url": "",
            "time": (n - timedelta(hours=i * 3 + 1)).isoformat(timespec="seconds"),
            "official": False,
            "areas": [area.lower()],
        })
    return out


def osm_points(lat, lon, kind="water"):
    """A few plausible community points around a coordinate (demo only)."""
    names = {
        "water": ["Communal standpipe", "JoJo tank (church)", "Borehole — community hall"],
        "food": ["Spaza (open during outages)", "Community food garden", "Soup kitchen"],
        "health": ["Clinic", "Community health worker post"],
        "energy": ["Solar charging kiosk", "Shared battery hub"],
    }.get(kind, ["Community point"])
    out = []
    for i, nm in enumerate(names):
        dlat = jitter(("a", kind, i, round(lat, 3)), 0.012)
        dlon = jitter(("o", kind, i, round(lon, 3)), 0.012)
        out.append({
            "id": f"sim-{kind}-{i}", "name": nm, "kind": kind,
            "lat": round(lat + dlat, 5), "lon": round(lon + dlon, 5),
            "distance_m": int(300 + i * 420 + abs(jitter(("d", kind, i), 250))),
            "open": "unknown", "source": "ServiceWaze demo set",
        })
    return out


# ---------------------------------------------------------------------------
# Offline gazetteer — a real subset of South African places so that search,
# reverse geocoding and every downstream feature still work with no network.
# (Same shape as Open-Meteo's geocoding response.)
# ---------------------------------------------------------------------------
PLACES = [
    ("Soweto", "Gauteng", -26.2485, 27.8546), ("Johannesburg", "Gauteng", -26.2041, 28.0473),
    ("Sandton", "Gauteng", -26.1076, 28.0567), ("Randburg", "Gauteng", -26.0935, 27.9990),
    ("Roodepoort", "Gauteng", -26.1462, 27.8759), ("Midrand", "Gauteng", -25.9421, 28.1400),
    ("Centurion", "Gauteng", -25.8601, 28.1890), ("Pretoria", "Gauteng", -25.7479, 28.2293),
    ("Soshanguve", "Gauteng", -25.5200, 28.1000), ("Mamelodi", "Gauteng", -25.7000, 28.4200),
    ("Tembisa", "Gauteng", -25.9900, 28.2200), ("Alexandra", "Gauteng", -26.1050, 28.1000),
    ("Kempton Park", "Gauteng", -26.1000, 28.2300), ("Benoni", "Gauteng", -26.1870, 28.3200),
    ("Boksburg", "Gauteng", -26.2100, 28.2600), ("Germiston", "Gauteng", -26.2200, 28.1700),
    ("Springs", "Gauteng", -26.2500, 28.4400), ("Vereeniging", "Gauteng", -26.6700, 27.9300),
    ("Vanderbijlpark", "Gauteng", -26.7000, 27.8300), ("Krugersdorp", "Gauteng", -26.1000, 27.7700),
    ("Diepsloot", "Gauteng", -25.9200, 28.0200), ("Orange Farm", "Gauteng", -26.4700, 27.7700),
    ("Lenasia", "Gauteng", -26.3100, 27.8500), ("Mabopane", "Gauteng", -25.5000, 28.0600),
    ("KwaMhlanga", "Mpumalanga", -25.4200, 28.7000), ("Cape Town", "Western Cape", -33.9249, 18.4241),
    ("Khayelitsha", "Western Cape", -34.0400, 18.6700), ("Mitchells Plain", "Western Cape", -34.0500, 18.6200),
    ("Gugulethu", "Western Cape", -33.9800, 18.5700), ("Langa", "Western Cape", -33.9400, 18.5300),
    ("Bellville", "Western Cape", -33.9000, 18.6300), ("Stellenbosch", "Western Cape", -33.9321, 18.8602),
    ("Paarl", "Western Cape", -33.7200, 18.9800), ("George", "Western Cape", -33.9600, 22.4600),
    ("Atlantis", "Western Cape", -33.5700, 18.4800), ("Durban", "KwaZulu-Natal", -29.8587, 31.0218),
    ("Umlazi", "KwaZulu-Natal", -29.9700, 30.9000), ("Pietermaritzburg", "KwaZulu-Natal", -29.6006, 30.3794),
    ("Newcastle", "KwaZulu-Natal", -27.7500, 29.9300), ("Richards Bay", "KwaZulu-Natal", -28.7800, 32.0300),
    ("Mtubatuba", "KwaZulu-Natal", -28.4200, 32.1900), ("Ladysmith", "KwaZulu-Natal", -28.5600, 29.7800),
    ("Gqeberha", "Eastern Cape", -33.9600, 25.6000), ("Port Elizabeth", "Eastern Cape", -33.9600, 25.6000),
    ("East London", "Eastern Cape", -32.9800, 27.8700), ("Mthatha", "Eastern Cape", -31.5900, 28.7800),
    ("Makhanda", "Eastern Cape", -33.3100, 26.5300), ("Queenstown", "Eastern Cape", -31.9000, 26.8800),
    ("Bloemfontein", "Free State", -29.0850, 26.1590), ("Welkom", "Free State", -27.9800, 26.7200),
    ("Bethlehem", "Free State", -28.2300, 28.3100), ("Sasolburg", "Free State", -26.8100, 27.8300),
    ("Polokwane", "Limpopo", -23.9000, 29.4500), ("Thohoyandou", "Limpopo", -22.9500, 30.4800),
    ("Tzaneen", "Limpopo", -23.8300, 30.1600), ("Musina", "Limpopo", -22.3400, 30.0400),
    ("Mokopane", "Limpopo", -24.1900, 29.0100), ("Mbombela", "Mpumalanga", -25.4700, 30.9900),
    ("Nelspruit", "Mpumalanga", -25.4700, 30.9900), ("Emalahleni", "Mpumalanga", -25.8700, 29.2300),
    ("Witbank", "Mpumalanga", -25.8700, 29.2300), ("Secunda", "Mpumalanga", -26.5300, 29.1700),
    ("Middelburg", "Mpumalanga", -25.7700, 29.4600), ("Rustenburg", "North West", -25.6700, 27.2400),
    ("Mahikeng", "North West", -25.8600, 25.6400), ("Klerksdorp", "North West", -26.8700, 26.6700),
    ("Potchefstroom", "North West", -26.7100, 27.1000), ("Brits", "North West", -25.6300, 27.7800),
    ("Kimberley", "Northern Cape", -28.7400, 24.7700), ("Upington", "Northern Cape", -28.4500, 21.2600),
    ("Kuruman", "Northern Cape", -27.4500, 23.4300), ("Springbok", "Northern Cape", -29.6700, 17.8800),
]


def geocode(query: str, count: int = 6):
    q = (query or "").strip().lower()
    if not q:
        return []
    scored = []
    for name, admin1, lat, lon in PLACES:
        n = name.lower()
        if q in n:
            scored.append((0 if n.startswith(q) else 1, name, admin1, lat, lon))
    scored.sort(key=lambda r: (r[0], r[1]))
    return [{"name": r[1], "admin1": r[2], "admin2": r[2], "lat": r[3], "lon": r[4],
             "source": "ServiceWaze offline gazetteer"}
            for r in scored[:count]]


def reverse_geocode(lat, lon):
    best, dist = None, 10 ** 9
    for name, admin1, plat, plon in PLACES:
        d = (plat - lat) ** 2 + (plon - lon) ** 2
        if d < dist:
            best, dist = (name, admin1), d
    if not best:
        return {"name": "My location", "state": "", "display": "My location"}
    name, state = best
    return {"name": name, "state": state, "display": f"{name}, {state}",
            "source": "ServiceWaze offline gazetteer"}
