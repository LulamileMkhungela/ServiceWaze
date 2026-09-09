"""The money engine — turning kilowatts, kilolitres and kilograms into rands.

This is the part of ServiceWaze that no status app does: it tells a household
what a disruption *costs* and what a behaviour change *saves*, using the real
published tariffs for the 2026/27 municipal year.

Sources (verified September 2026, all public):
  * Eskom Schedule of Standard Prices 2026/27 (Homepower / Homeflex / Homelight)
    — Homeflex incl. VAT: winter peak R8.4710, winter standard R2.9580,
    winter off-peak R1.9083; summer peak R3.9455, standard R1.9265,
    off-peak R1.3051. Homepower flat R3.2206/kWh, Homepower 4 fixed ≈ R536/m.
  * City of Johannesburg water & sanitation 2026/27 (Mayoral Committee Item 77):
    first 6 kl free; >6–10 R28.91; >10–15 R29.84; >15–20 R35.65; >20–30 R64.53;
    >30–40 R69.45; >40–50 R86.81; >50 R94.92 per kl (VAT excl.).
  * City of Cape Town water 2026/27 (incl. VAT): 0–6 kl R25.42; >6–10.5 R34.92;
    >10.5–35 R52.20; >35 R100.71.
  * Cape Town electricity Home User 2026/27: R3.5595/kWh to 600 units,
    R4.6906/kWh above, R424.30/month fixed.
  * PMBEJD Household Affordability Index (July 2026): average household food
    basket R5 530.52; Pietermaritzburg cheapest (R5 173.57),
    Springbok most expensive (R6 109.75).

Every number returned carries a `basis` string so the UI can show the receipt
behind the maths. If a tariff changes, change it here — one place, dated.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

VAT = 1.15
AS_OF = "2026-09-01"

# ---------------------------------------------------------------------------
# Electricity
# ---------------------------------------------------------------------------
# Homeflex is a time-of-use tariff: price depends on season and time of day.
# High-demand season = June, July, August.
HOMEFLEX = {
    "name": "Eskom Homeflex (time-of-use)",
    "high_season_months": [6, 7, 8],
    "rates": {  # R/kWh, incl. VAT, 2026/27
        "high": {"peak": 8.4710, "standard": 2.9580, "offpeak": 1.9083,
                 "peak_hours": [(7, 10), (18, 20)]},
        "low": {"peak": 3.9455, "standard": 1.9265, "offpeak": 1.3051,
                "peak_hours": [(7, 10), (18, 20)]},
    },
    "fixed_month": 536.0,
    "note": "Residential TOU tariff — needs a smart TOU meter. Winter peak is ~4.4x off-peak.",
}

HOMELIGHT = {
    "name": "Eskom Homelight (subsidised, 20A/60A)",
    "flat": 2.3500, "fixed_month": 0.0,
    "note": "Lowest unit rate, no daily fixed charge; only for eligible small supplies.",
}

ELECTRICITY_TARIFFS = {
    "eskom_homepower": {
        "name": "Eskom Homepower (flat)", "flat": 3.2206, "fixed_month": 536.0,
        "note": "Flat rate all year, plus network/service/capacity fixed charges (~R536/m on Homepower 4).",
    },
    "eskom_homeflex": HOMEFLEX,
    "eskom_homelight": HOMELIGHT,
    "coct_home_user": {
        "name": "City of Cape Town — Home User", "flat": 3.5595, "high_above": 600,
        "flat_high": 4.6906, "fixed_month": 424.30,
        "note": "Cheaper units, high fixed charge. Break-even vs Domestic ≈ 610 kWh/month.",
    },
    "coct_domestic": {
        "name": "City of Cape Town — Domestic", "flat": 4.1990, "fixed_month": 74.20,
        "note": "Lower fixed charge; better below ~610 kWh/month.",
    },
    "city_power_joburg": {
        "name": "City Power Johannesburg (residential)", "flat": 2.9500,
        "fixed_month": 241.50, "note": "Indicative metro residential incl. VAT.",
    },
    "ethekwini": {
        "name": "eThekwini Electricity (residential)", "flat": 2.8600,
        "fixed_month": 190.00, "note": "Indicative metro residential incl. VAT.",
    },
    "tshwane": {
        "name": "Tshwane Electricity (residential)", "flat": 3.0100,
        "fixed_month": 210.00, "note": "Indicative metro residential incl. VAT.",
    },
}

DEFAULT_TARIFF_BY_AREA = [
    (("cape town", "stellenbosch", "paarl", "george", "western cape"), "coct_home_user"),
    (("johannesburg", "soweto", "sandton", "randburg", "joburg", "gauteng", "pretoria",
      "tshwane", "centurion", "midrand", "alexandra"), "city_power_joburg"),
    (("durban", "ethekwini", "pietermaritzburg", "kzn", "kwazulu"), "ethekwini"),
]


def tariff_for_area(area: str) -> str:
    a = (area or "").lower()
    for keys, tid in DEFAULT_TARIFF_BY_AREA:
        if any(k in a for k in keys):
            return tid
    return "eskom_homepower"


def _season(month: int, t: dict) -> str:
    return "high" if month in t.get("high_season_months", []) else "low"


def _tou_slot(hour: int, t: dict, season: str) -> str:
    for start, end in t["rates"][season]["peak_hours"]:
        if start <= hour < end:
            return "peak"
    if 0 <= hour < 6 or 22 <= hour < 24 or hour in (11, 12, 13, 14, 15, 16, 17):
        return "offpeak"
    return "standard"


def unit_price(tariff_id: str, when: datetime | None = None) -> dict:
    """Price of one kWh right now (or at `when`) on a given tariff."""
    when = when or datetime.now(timezone(timedelta(hours=2)))
    t = ELECTRICITY_TARIFFS.get(tariff_id, ELECTRICITY_TARIFFS["eskom_homepower"])
    out = {"tariff": t["name"], "tariff_id": tariff_id, "as_of": AS_OF}
    if tariff_id == "eskom_homeflex":
        season = _season(when.month, t)
        slot = _tou_slot(when.hour, t, season)
        r = t["rates"][season]
        out.update({"price": r[slot], "slot": slot, "season": season,
                    "peak": r["peak"], "standard": r["standard"], "offpeak": r["offpeak"],
                    "basis": f"Eskom Homeflex 2026/27 — {season}-demand season, {slot} period"})
    else:
        price = t.get("flat", 0.0)
        out.update({"price": price, "slot": "flat", "basis": t.get("note", "")})
    return out


def electricity_bill(kwh: float, tariff_id: str = "eskom_homepower",
                     when: datetime | None = None) -> dict:
    t = ELECTRICITY_TARIFFS.get(tariff_id, ELECTRICITY_TARIFFS["eskom_homepower"])
    when = when or datetime.now(timezone(timedelta(hours=2)))
    fixed = float(t.get("fixed_month", 0.0))
    if tariff_id == "coct_home_user":
        cap = float(t.get("high_above", 600))
        energy = min(kwh, cap) * t["flat"] + max(0.0, kwh - cap) * t["flat_high"]
    elif tariff_id == "eskom_homeflex":
        # assume a typical split: 45% standard, 40% off-peak, 15% peak
        season = _season(when.month, t)
        r = t["rates"][season]
        energy = kwh * (0.45 * r["standard"] + 0.40 * r["offpeak"] + 0.15 * r["peak"])
    else:
        energy = kwh * float(t.get("flat", 0.0))
    total = energy + fixed
    return {"kwh": round(kwh, 1), "energy": round(energy, 2), "fixed": round(fixed, 2),
            "total": round(total, 2), "blended_per_kwh": round(total / kwh, 4) if kwh else 0.0,
            "tariff": t["name"], "tariff_id": tariff_id, "as_of": AS_OF,
            "basis": "Published 2026/27 schedule of standard prices; blended rate includes fixed charges."}


def cheapest_windows(tariff_id: str = "eskom_homeflex", when: datetime | None = None,
                     hours: int = 24) -> list[dict]:
    """Next 24h ranked cheapest→most expensive (for load shifting)."""
    when = when or datetime.now(timezone(timedelta(hours=2)))
    rows = []
    for i in range(hours):
        t = when + timedelta(hours=i)
        p = unit_price(tariff_id, t)
        rows.append({"hour": t.strftime("%H:%M"), "price": round(p["price"], 4),
                     "slot": p.get("slot", "flat"), "ts": t.isoformat()})
    rows.sort(key=lambda r: r["price"])
    return rows


# ---------------------------------------------------------------------------
# Water
# ---------------------------------------------------------------------------
WATER_TARIFFS = {
    "johannesburg": {
        "name": "Johannesburg Water 2026/27 (prepayment, VAT excl.)",
        "free_kl": 6.0,
        "blocks": [(6, 10, 28.91), (10, 15, 29.84), (15, 20, 35.65), (20, 30, 64.53),
                   (30, 40, 69.45), (40, 50, 86.81), (50, 10 ** 9, 94.92)],
        "vat_exclusive": True,
        "note": "First 6 kl per household per month free (Free Basic Water).",
    },
    "cape town": {
        "name": "City of Cape Town Water 2026/27 (incl. VAT)",
        "free_kl": 0.0,
        "blocks": [(0, 6, 25.42), (6, 10.5, 34.92), (10.5, 35, 52.20), (35, 10 ** 9, 100.71)],
        "vat_exclusive": False,
        "note": "Step 1 free for registered indigent households.",
    },
    "tshwane": {
        "name": "City of Tshwane Water (indicative, incl. VAT)",
        "free_kl": 6.0,
        "blocks": [(6, 12, 30.10), (12, 20, 38.40), (20, 35, 55.20), (35, 10 ** 9, 78.30)],
        "vat_exclusive": False, "note": "Indicative metro residential.",
    },
    "ethekwini": {
        "name": "eThekwini Water (indicative, incl. VAT)",
        "free_kl": 6.0,
        "blocks": [(6, 12, 27.80), (12, 25, 36.10), (25, 45, 52.70), (45, 10 ** 9, 71.40)],
        "vat_exclusive": False, "note": "Indicative metro residential.",
    },
    "national_average": {
        "name": "National average (modelled)",
        "free_kl": 6.0,
        "blocks": [(6, 12, 29.50), (12, 25, 38.00), (25, 45, 56.00), (45, 10 ** 9, 82.00)],
        "vat_exclusive": False, "note": "Blended estimate for metros without published bands.",
    },
}

WATER_AREA_MAP = [
    (("johannesburg", "soweto", "randburg", "sandton", "joburg", "gauteng", "alexandra",
      "midrand", "roodepoort"), "johannesburg"),
    (("cape town", "stellenbosch", "paarl", "western cape", "khayelitsha"), "cape town"),
    (("pretoria", "tshwane", "centurion", "soshanguve"), "tshwane"),
    (("durban", "ethekwini", "umhlanga", "pietermaritzburg"), "ethekwini"),
]


def water_tariff_for_area(area: str) -> str:
    a = (area or "").lower()
    for keys, tid in WATER_AREA_MAP:
        if any(k in a for k in keys):
            return tid
    return "national_average"


def water_bill(kl: float, city: str = "johannesburg") -> dict:
    t = WATER_TARIFFS.get(city, WATER_TARIFFS["national_average"])
    remaining = max(0.0, float(kl) - float(t.get("free_kl", 0.0)))
    total = 0.0
    lines = []
    for lo, hi, rate in t["blocks"]:
        if remaining <= 0:
            break
        band = min(remaining, hi - lo)
        if band <= 0:
            continue
        cost = band * rate
        total += cost
        lines.append({"block": f"{lo:g}–{hi:g} kl" if hi < 10 ** 9 else f"{lo:g}+ kl",
                      "kl": round(band, 2), "rate": rate, "cost": round(cost, 2)})
        remaining -= band
    if t.get("vat_exclusive"):
        total *= VAT
    return {
        "kl": round(float(kl), 2), "total": round(total, 2), "lines": lines,
        "free_kl": t.get("free_kl", 0.0), "tariff": t["name"], "city": city,
        "vat_included": True, "as_of": AS_OF,
        "basis": "Rising-block municipal tariff, first 6 kl free where applicable.",
    }


# ---------------------------------------------------------------------------
# Appliances, harvesting, solar, food
# ---------------------------------------------------------------------------
APPLIANCES = {
    "kettle": {"w": 2200, "typical_minutes": 3, "label": "Kettle (1.7 L boil)"},
    "geyser": {"w": 3000, "typical_minutes": 120, "label": "Geyser (150 L, full reheat)"},
    "shower_10min": {"w": 8000, "typical_minutes": 10, "label": "Electric shower (10 min)"},
    "fridge_day": {"w": 90, "typical_minutes": 1440, "label": "Fridge (24 h, duty-cycled)"},
    "freezer_day": {"w": 70, "typical_minutes": 1440, "label": "Chest freezer (24 h)"},
    "washing_machine": {"w": 2100, "typical_minutes": 45, "label": "Washing machine (hot wash)"},
    "iron": {"w": 1800, "typical_minutes": 15, "label": "Iron (15 min)"},
    "microwave": {"w": 1200, "typical_minutes": 8, "label": "Microwave (8 min)"},
    "stove_plate": {"w": 2000, "typical_minutes": 30, "label": "Stove plate (30 min)"},
    "heater": {"w": 2000, "typical_minutes": 60, "label": "Fan heater (1 h)"},
    "pool_pump": {"w": 750, "typical_minutes": 240, "label": "Pool pump (4 h)"},
    "tv": {"w": 100, "typical_minutes": 180, "label": "TV (3 h)"},
    "led_lights": {"w": 60, "typical_minutes": 300, "label": "LED lights, whole house (5 h)"},
    "phone_charge": {"w": 10, "typical_minutes": 120, "label": "Phone charge (2 h)"},
    "router": {"w": 12, "typical_minutes": 1440, "label": "Wi-Fi router (24 h)"},
    "wifi_saving_tip": {"w": 0, "typical_minutes": 0, "label": "—"},
}


def appliance_cost(key: str, tariff_id: str = "eskom_homepower",
                   minutes: float | None = None, when: datetime | None = None) -> dict:
    a = APPLIANCES.get(key)
    if not a:
        return {"error": "unknown appliance", "known": sorted(APPLIANCES)}
    mins = float(minutes if minutes is not None else a["typical_minutes"])
    kwh = a["w"] * mins / 60.0 / 1000.0
    p = unit_price(tariff_id, when)
    return {"appliance": key, "label": a["label"], "watts": a["w"], "minutes": mins,
            "kwh": round(kwh, 3), "price_per_kwh": round(p["price"], 4),
            "cost": round(kwh * p["price"], 4), "slot": p.get("slot", "flat"),
            "tariff": p["tariff"], "basis": p["basis"]}


def rain_harvest(roof_m2: float, precip_mm: float, runoff: float = 0.80) -> dict:
    """Litres you can capture from a roof for a given rainfall depth."""
    litres = float(roof_m2) * float(precip_mm) * float(runoff)
    return {"roof_m2": roof_m2, "precip_mm": round(precip_mm, 1), "runoff": runoff,
            "litres": round(litres, 1), "baths": round(litres / 80.0, 1),
            "days_for_4_people": round(litres / (4 * 50.0), 1),
            "basis": "litres = roof area (m²) × rainfall (mm) × runoff coefficient (0.8 typical tile/metal)."}


def solar_estimate(kwp: float, daily_irradiance_kwh_per_kwp: float = 4.6,
                   tariff_id: str = "eskom_homepower", cost_per_kwp: float = 16500.0) -> dict:
    """Rough rooftop solar yield + payback using Open-Meteo radiation when live."""
    daily = kwp * daily_irradiance_kwh_per_kwp
    p = unit_price(tariff_id)
    monthly = daily * 30 * p["price"]
    capex = kwp * cost_per_kwp
    payback = capex / monthly / 12 if monthly else None
    return {"kwp": kwp, "kwh_per_day": round(daily, 2), "kwh_per_month": round(daily * 30, 1),
            "monthly_saving": round(monthly, 2), "capex": round(capex, 2),
            "payback_years": round(payback, 1) if payback else None,
            "co2_kg_per_month": round(daily * 30 * 0.94, 1),
            "basis": "Yield from local solar irradiance; 0.94 kg CO₂/kWh grid factor."}


FOOD_BASKET = {
    "national_average": 5530.52, "johannesburg": 5763.70, "durban": 5309.02,
    "pietermaritzburg": 5173.57, "mthatha": 5669.87, "springbok": 6109.75,
    "mtubatuba": 5649.23,
}
FOOD_BASKET_AS_OF = "2026-07"
FOOD_POVERTY_LINE = 868.0  # per person per month, Stats SA 2026
NUTRITIONAL_BASKET_FAMILY4 = 3667.72  # PMBEJD March 2026


def food_basket(area: str = "national_average", people: int = 4) -> dict:
    a = (area or "").lower()
    key = "national_average"
    for k in FOOD_BASKET:
        if k in a:
            key = k
            break
    base = FOOD_BASKET[key]
    per_person = base / 5.0  # basket is sized for a family of ~5
    return {
        "area": key, "people": people, "monthly": round(per_person * people, 2),
        "per_person": round(per_person, 2), "basket_reference": round(base, 2),
        "as_of": FOOD_BASKET_AS_OF,
        "food_poverty_line_per_person": FOOD_POVERTY_LINE,
        "nutritional_basket_family_of_4": NUTRITIONAL_BASKET_FAMILY4,
        "gap_to_poverty_line": round(per_person - FOOD_POVERTY_LINE, 2),
        "basis": "PMBEJD Household Affordability Index (July 2026) and Stats SA 2026 poverty lines.",
    }


def leak_check(readings: list[dict]) -> dict:
    """Detect a probable leak from consecutive meter readings.

    readings: [{kl_total, at}] ascending. A household that never hits zero flow
    overnight almost certainly has a leak.
    """
    if len(readings) < 2:
        return {"verdict": "unknown", "hint": "Log two readings a day apart to test for a leak."}
    try:
        rows = sorted(readings, key=lambda r: r.get("at", ""))
        first, last = rows[0], rows[-1]
        t0 = datetime.fromisoformat(str(first["at"]).replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(str(last["at"]).replace("Z", "+00:00"))
        hours = max(0.5, (t1 - t0).total_seconds() / 3600.0)
        used = float(last["kl_total"]) - float(first["kl_total"])
        litres_per_hour = used * 1000.0 / hours
    except Exception:
        return {"verdict": "unknown", "hint": "Could not parse readings."}
    verdict = "likely_leak" if litres_per_hour >= 4 else "ok" if litres_per_hour <= 1.5 else "watch"
    return {
        "verdict": verdict, "litres_per_hour": round(litres_per_hour, 2),
        "hours": round(hours, 1), "kl_used": round(used, 3),
        "monthly_kl_if_continuous": round(litres_per_hour * 24 * 30 / 1000.0, 2),
        "hint": {"likely_leak": "Continuous flow >4 L/h — likely a leaking toilet or tap. "
                                "A running toilet can waste 20–40 kl a month.",
                 "watch": "Slight continuous flow — re-test overnight with all taps closed.",
                 "ok": "No continuous flow detected."}.get(verdict, ""),
    }


TARIFF_SOURCES = [
    {"name": "Eskom Schedule of Standard Prices 2026/27 (Homepower / Homeflex / Homelight)",
     "url": "https://www.eskom.co.za/distribution/tariffs-and-charges/"},
    {"name": "City of Johannesburg water & sanitation tariffs FY2026/27",
     "url": "https://www.joburg.org.za/documents_/Pages/Tariffs.aspx"},
    {"name": "City of Cape Town water & sanitation tariffs 2026/27",
     "url": "https://resource.capetown.gov.za/documentcentre/Documents/Forms,%20notices,%20tariffs%20and%20lists/L3-WaterSanitationRestrictionTariffs.pdf"},
    {"name": "PMBEJD Household Affordability Index",
     "url": "https://www.piec.org.za/research-item/household-affordability-index/"},
    {"name": "Stats SA national poverty lines 2026",
     "url": "https://www.statssa.gov.za/?page_id=959"},
]

def prepaid_runway(units_left: float, daily_kwh: float = 10.0, tariff_id: str = "eskom_homepower",
                   area: str = "", outage_hours_per_day: float = 0.0,
                   fbe_kwh_per_month: float = 0.0, topup_rand: float = 0.0,
                   target_days: int = 0) -> dict:
    """How many days of electricity are left on the meter, and when it runs out.

    Prepaid is how most South African households actually buy power, and the
    question everyone asks at the kitchen table is not "what is the tariff?" —
    it is **"how long will these units last, and will they reach month end?"**

    Model:
        daily_net = daily_kwh − (load-shedding displaces part of the day's use)
        days_left = units_left / daily_net
        rand      = kWh × unit price at the current time-of-use slot

    Load shedding *saves* units (a fridge does not run in the dark) but costs
    food, so the displacement factor (0.6) is documented, not hidden.
    """
    try:
        units_left = max(0.0, float(units_left))
    except Exception:
        units_left = 0.0
    try:
        daily_kwh = max(0.2, float(daily_kwh))
    except Exception:
        daily_kwh = 10.0
    try:
        outage = max(0.0, min(24.0, float(outage_hours_per_day or 0)))
    except Exception:
        outage = 0.0

    DISPLACEMENT = 0.6          # share of an average hour's use not consumed during an outage
    daily_displaced = daily_kwh * (outage / 24.0) * DISPLACEMENT
    daily_net = max(0.2, daily_kwh - daily_displaced)

    p = unit_price(tariff_id)
    price = float(p.get("price") or 0.0)
    now = datetime.now(timezone(timedelta(hours=2)))

    days_left = round(units_left / daily_net, 1) if daily_net else 0
    runout = now + timedelta(days=days_left)

    # month-end target — the date every prepaid household is really managing to
    next_month = (now.replace(day=28) + timedelta(days=7)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    days_to_month_end = max(0.0, round((month_end - now).total_seconds() / 86400, 1))
    units_needed_month = round(daily_net * days_to_month_end, 1)
    shortfall = round(max(0.0, units_needed_month - units_left), 1)
    fbe_left = 0.0
    if fbe_kwh_per_month:
        day_of_month = now.day
        days_in_month = (next_month - timedelta(days=1)).day
        fbe_accrued = fbe_kwh_per_month * (day_of_month / days_in_month)
        fbe_left = round(max(0.0, fbe_accrued - max(0.0, fbe_kwh_per_month - units_left)), 1)

    target = int(target_days or 0)
    units_for_target = round(daily_net * target, 1) if target else 0.0
    rand_for_target = round(units_for_target * price, 2) if target else 0.0
    topup_units = round(topup_rand / price, 1) if (topup_rand and price) else 0.0
    topup_days = round(topup_units / daily_net, 1) if daily_net and topup_units else 0.0

    state = "ok"
    if days_left < 2:
        state = "critical"
    elif days_left < 5:
        state = "low"
    elif shortfall > 0:
        state = "short_of_month_end"

    advice = []
    if state == "critical":
        advice.append("Less than two days left — top up today, or move the geyser and stove off electricity now.")
    if shortfall > 0:
        advice.append("You are " + str(shortfall) + " units short of month end — about R" +
                      str(round(shortfall * price, 2)) + ".")
    else:
        advice.append("These units reach month end with about " +
                      str(round(units_left - units_needed_month, 1)) + " units to spare.")
    if outage:
        advice.append("Load shedding is saving you about " + str(round(daily_displaced, 1)) +
                      " units a day — and risking the food in your fridge.")
    if fbe_kwh_per_month:
        advice.append("Free Basic Electricity: " + str(fbe_kwh_per_month) +
                      " kWh/month is applied before your units are used if you are registered.")
    advice.append("Cheapest hours are early morning and late evening — heating water in a peak hour costs several times more.")

    return {
        "tariff": p.get("tariff"), "tariff_id": tariff_id, "price_per_kwh": round(price, 4),
        "slot": p.get("slot"), "as_of": AS_OF,
        "units_left": round(units_left, 1),
        "daily_kwh": round(daily_kwh, 2),
        "daily_net_kwh": round(daily_net, 2),
        "outage_hours_per_day": round(outage, 1),
        "displaced_kwh_per_day": round(daily_displaced, 2),
        "days_left": days_left,
        "runs_out": runout.strftime("%Y-%m-%d %H:%M"),
        "runs_out_in_days": days_left,
        "cost_per_day": round(daily_net * price, 2),
        "cost_per_month": round(daily_net * price * 30.4, 2),
        "month_end": month_end.strftime("%Y-%m-%d"),
        "days_to_month_end": days_to_month_end,
        "units_needed_to_month_end": units_needed_month,
        "shortfall_units": shortfall,
        "shortfall_rand": round(shortfall * price, 2),
        "surplus_units": round(max(0.0, units_left - units_needed_month), 1),
        "topup_rand": round(topup_rand, 2), "topup_units": topup_units, "topup_days": topup_days,
        "units_for_target_days": units_for_target,
        "rand_for_target_days": rand_for_target,
        "fbe_kwh_per_month": fbe_kwh_per_month,
        "state": state,
        "advice": advice,
        "basis": ("days = units ÷ (daily use − load-shedding displacement of 0.6 × outage hours); "
                  "rand = kWh × " + str(round(price, 4)) + " (" + str(p.get("basis", "")) + "). "
                  "Meter service charges and municipal fixed charges are not included; add them if your "
                  "statement shows one."),
        "area": area,
    }
