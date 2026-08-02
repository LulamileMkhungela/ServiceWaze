"""USSD menu flow (feature-phone channel).

Real USSD requires a carrier aggregator (MTN/Vodacom/Cell C). This module
implements the exact menu logic that would be wired to an aggregator, and
exposes it at /api/ussd for testing/simulation.
"""
import time

import sources

SESSIONS = {}


def _summary(area_name):
    geo = sources.geocode(area_name, count=1)
    if not geo:
        return "Area not found. Try another name.\n0. Back"
    g = geo[0]
    w = sources.weather(g["lat"], g["lon"])
    elec = sources.eskom_status()
    reps = sources.reports_for_area(g["lat"], g["lon"], area_name)
    lines = [f"AREA: {g['name']}, {g['admin1']}"]
    if w and w.get("current"):
        c = w["current"]
        lines.append(f"Weather: {c['temp']}C {c['desc']}")
    lines.append(f"Electricity: {elec['label']}")
    lines.append(f"Community reports: {len(reps)}")
    if reps:
        r = reps[0]
        lines.append(f"Latest: {r['kind']} ({r['area']})")
    lines.append("")
    lines.append("1. Refresh")
    lines.append("2. Report an issue")
    lines.append("3. Emergency numbers")
    lines.append("0. Back")
    return "\n".join(lines)


def handle(session_id, user_input, msisdn=""):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"state": "menu", "kind": None, "area": None}
    s = SESSIONS[session_id]
    inp = (user_input or "").strip()
    t = time.time()
    # expire sessions after 5 min
    if "ts" in s and t - s["ts"] > 300:
        s = {"state": "menu", "kind": None, "area": None}
        SESSIONS[session_id] = s
    s["ts"] = t

    state = s["state"]

    if state == "menu":
        if inp == "1":
            s["state"] = "ask_area"
            return "Enter your suburb or town:\ne.g. Soweto, Durban, Khayelitsha\n0. Back"
        if inp == "2":
            s["state"] = "ask_kind"
            return ("Report an issue. What kind?\n"
                    "1. No water\n2. Power out\n3. Leak / burst pipe\n4. Water restored\n5. Other\n0. Back")
        if inp == "3":
            return ("EMERGENCY:\nPolice: 10111\nAmbulance: 10177\nMobile: 112\nGBV: 0800 428 428\n\n0. Back")
        if inp == "0":
            return "Thank you. Goodbye."
        return ("ServiceWaze\n1. Area status\n2. Report an issue\n3. Emergency numbers\n0. Exit")

    if state == "ask_area":
        if inp == "0":
            s["state"] = "menu"
            return "1. Area status\n2. Report an issue\n3. Emergency numbers\n0. Exit"
        if not inp:
            return "Enter your suburb or town:\n0. Back"
        s["area"] = inp
        s["state"] = "menu"
        return _summary(inp)

    if state == "ask_kind":
        if inp == "0":
            s["state"] = "menu"
            return "1. Area status\n2. Report an issue\n3. Emergency numbers\n0. Exit"
        kinds = {"1": "no_water", "2": "power_out", "3": "leak", "4": "restored", "5": "other"}
        if inp not in kinds:
            return "Choose 1-5:\n1. No water\n2. Power out\n3. Leak\n4. Restored\n5. Other\n0. Back"
        s["kind"] = kinds[inp]
        s["state"] = "ask_area_rep"
        return "Which area? (e.g. Pimville, Soweto)\n0. Back"

    if state == "ask_area_rep":
        if inp == "0":
            s["state"] = "menu"
            return "1. Area status\n2. Report an issue\n3. Emergency numbers\n0. Exit"
        if not inp:
            return "Which area?\n0. Back"
        s["area"] = inp
        s["state"] = "ask_msg"
        return "Short description (max 40 chars):\n0. Back"

    if state == "ask_msg":
        if inp == "0":
            s["state"] = "menu"
            return "1. Area status\n2. Report an issue\n3. Emergency numbers\n0. Exit"
        if not inp:
            return "Short description:\n0. Back"
        rid = sources.add_report(s["area"], s["kind"], inp[:40], "ussd")
        s["state"] = "menu"
        return f"Report saved (ID {rid}). Thank you!\n\n1. Area status\n0. Exit"

    s["state"] = "menu"
    return "1. Area status\n2. Report an issue\n3. Emergency numbers\n0. Exit"
