"""Government transport directory + live status for ServiceWaze.

No official SA transit API is public (Gautrain/PRASA/BRT systems don't expose
realtime feeds), so this module combines:
  1. A curated directory of ALL government/public transport per province
     (Metrorail/PRASA, Shosholoza Meyl, Gautrain train + bus, Rea Vaya,
     A Re Yeng, MyCiTi, GO!Durban, provincial links).
  2. LIVE status pulled from the merged news/social feed (strikes,
     shutdowns, delays) + community 'route' reports — same model as the rest
     of the app.
  3. Official timetable/contact links for each operator.
  4. "Nearby areas" suggestions when the selected area has no local service.
"""
import re

# province admin1 -> key
ADMIN1_MAP = {
    "gauteng": "gauteng",
    "western cape": "western_cape",
    "kwa-zulu natal": "kzn",
    "kwa-zulu-natal": "kzn",
    "eastern cape": "eastern_cape",
    "free state": "free_state",
    "limpopo": "limpopo",
    "mpumalanga": "mpumalanga",
    "north west": "north_west",
    "northern cape": "northern_cape",
}

TRANSPORT = {
    "gauteng": {
        "name": "Gauteng",
        "cities": ["Johannesburg", "Pretoria", "Tshwane", "Midrand", "Centurion", "Soweto",
                   "Sandton", "Randburg", "Roodepoort", "Ekurhuleni", "Kempton Park", "Benoni",
                   "Boksburg", "Germiston", "Vereeniging", "Vanderbijlpark", "Alexandra", "Diepsloot"],
        "services": [
            {"name": "Gautrain", "mode": "train", "operator": "Bombela (Gautrain)",
             "phone": "0800 428 7246", "url": "https://www.gautrain.co.za",
             "areas": ["Johannesburg", "Pretoria", "Sandton", "Midrand", "Centurion", "Park Station",
                       "Rosebank", "Hatfield", "Marlboro", "Rhodesfield", "O.R. Tambo"],
             "keywords": ["gautrain", "gautrain strike", "gautrain delay", "gautrain shutdown"],
             "note": "Rail: Park Station – Hatfield & O.R. Tambo lines. App has live departures."},
            {"name": "Gautrain Bus", "mode": "bus", "operator": "Bombela (Gautrain)",
             "phone": "0800 428 7246", "url": "https://www.gautrain.co.za",
             "areas": ["Johannesburg", "Pretoria", "Sandton", "Midrand", "Centurion",
                       "Rivonia", "Rosebank", "Fourways", "Hatfield", "Menlyn", "Sunninghill"],
             "keywords": ["gautrain bus", "gautrain feeder"],
             "note": "Feeder buses connect stations to surrounding suburbs (Soweto, Midrand, etc.)."},
            {"name": "Prasa Metrorail (Joburg/Pretoria)", "mode": "train", "operator": "PRASA",
             "phone": "0800 872 2380", "url": "https://www.prasa.com",
             "areas": ["Johannesburg", "Pretoria", "Soweto", "Mabopane", "Tembisa", "KwaMhlanga",
                       "Germiston", "Kempton Park", "Vereeniging", "Daveyton", "Naledi", "Pimville",
                       "Meadowlands", "Kliptown", "Dobsonville", "Orlando"],
             "keywords": ["prasa", "metrorail", "train service", "rail", "mabopane", "tembisa"],
             "note": "Commuter rail network incl. Soweto lines. Verify before travelling — frequent suspensions."},
            {"name": "Rea Vaya (Joburg BRT)", "mode": "brt", "operator": "City of Johannesburg",
             "url": "https://www.reavaya.org.za",
             "areas": ["Johannesburg", "Soweto", "Alexandra", "Sandton", "Ellis Park", "CBD"],
             "keywords": ["rea vaya", "brt", "bus rapid"],
             "note": "BRT trunk & feeder routes across Joburg incl. Soweto–CBD."},
            {"name": "A Re Yeng (Tshwane BRT)", "mode": "brt", "operator": "City of Tshwane",
             "url": "https://www.tshwane.gov.za",
             "areas": ["Pretoria", "Tshwane", "Hatfield", "Menlyn", "Soshanguve"],
             "keywords": ["a re yeng", "tshwane brt"],
             "note": "BRT network in Pretoria/Tshwane."},
            {"name": "Shosholoza Meyl (long-distance rail)", "mode": "train", "operator": "PRASA",
             "url": "https://www.shosholozameyl.co.za",
             "areas": ["Johannesburg", "Pretoria"],
             "keywords": ["shosholoza meyl", "long distance train"],
             "note": "Long-distance overnight trains from Joburg/Pretoria."},
        ],
    },
    "western_cape": {
        "name": "Western Cape",
        "cities": ["Cape Town", "Stellenbosch", "Paarl", "George", "Knysna", "Bellville",
                   "Khayelitsha", "Mitchells Plain", "Athlone", "Somerset West"],
        "services": [
            {"name": "Prasa Metrorail (Cape Town)", "mode": "train", "operator": "PRASA",
             "phone": "0800 872 2380", "url": "https://www.prasa.com",
             "areas": ["Cape Town", "Bellville", "Khayelitsha", "Mitchells Plain", "Athlone",
                       "Stellenbosch", "Paarl", "Somerset West", "Simon's Town"],
             "keywords": ["prasa", "metrorail", "train service", "rail", "cape town"],
             "note": "Northern, Southern & Cape Flats lines."},
            {"name": "MyCiTi (Cape Town BRT)", "mode": "brt", "operator": "City of Cape Town",
             "url": "https://www.myciti.org.za",
             "areas": ["Cape Town", "Khayelitsha", "Mitchells Plain", "Atlantis", "Bellville", "Dunoon"],
             "keywords": ["myciti", "brt"],
             "note": "Bus rapid transit + feeder network."},
            {"name": "Shosholoza Meyl (long-distance rail)", "mode": "train", "operator": "PRASA",
             "url": "https://www.shosholozameyl.co.za",
             "areas": ["Cape Town"],
             "keywords": ["shosholoza meyl"],
             "note": "Long-distance overnight trains from Cape Town."},
        ],
    },
    "kzn": {
        "name": "KwaZulu-Natal",
        "cities": ["Durban", "Pietermaritzburg", "Richards Bay", "Newcastle", "Umhlanga", "Pinetown"],
        "services": [
            {"name": "Prasa Metrorail (Durban)", "mode": "train", "operator": "PRASA",
             "phone": "0800 872 2380", "url": "https://www.prasa.com",
             "areas": ["Durban", "Pinetown", "KwaMashu", "Umlazi", "Chatsworth", "Phoenix", "Umhlanga"],
             "keywords": ["prasa", "metrorail", "train service", "durban"],
             "note": "Durban commuter network incl. KwaMashu & Umlazi lines."},
            {"name": "GO!Durban (eThekwini BRT)", "mode": "brt", "operator": "eThekwini Municipality",
             "url": "https://godurban.co.za",
             "areas": ["Durban", "Pinetown", "Bridge City", "Umhlanga"],
             "keywords": ["go!durban", "go durban", "brt"],
             "note": "BRT system in eThekwini."},
            {"name": "Shosholoza Meyl (long-distance rail)", "mode": "train", "operator": "PRASA",
             "url": "https://www.shosholozameyl.co.za",
             "areas": ["Durban", "Pietermaritzburg"],
             "keywords": ["shosholoza meyl"],
             "note": "Long-distance rail via Durban/Pietermaritzburg."},
        ],
    },
    "eastern_cape": {
        "name": "Eastern Cape",
        "cities": ["Gqeberha", "East London", "Makhanda", "King William's Town", "Mthatha"],
        "services": [
            {"name": "Prasa Metrorail (Gqeberha & East London)", "mode": "train", "operator": "PRASA",
             "phone": "0800 872 2380", "url": "https://www.prasa.com",
             "areas": ["Gqeberha", "Port Elizabeth", "East London", "KwaZakhele", "Mdantsane"],
             "keywords": ["prasa", "metrorail", "gqeberha", "east london"],
             "note": "Local commuter services."},
            {"name": "Shosholoza Meyl (long-distance rail)", "mode": "train", "operator": "PRASA",
             "url": "https://www.shosholozameyl.co.za",
             "areas": ["Gqeberha", "East London"],
             "keywords": ["shosholoza meyl"],
             "note": "Long-distance rail."},
        ],
    },
    "free_state": {
        "name": "Free State",
        "cities": ["Bloemfontein", "Welkom", "Bethlehem", "Kroonstad"],
        "services": [
            {"name": "Prasa Metrorail (Bloemfontein)", "mode": "train", "operator": "PRASA",
             "phone": "0800 872 2380", "url": "https://www.prasa.com",
             "areas": ["Bloemfontein", "Botshabelo", "Thaba Nchu"],
             "keywords": ["prasa", "metrorail", "bloemfontein"],
             "note": "Local commuter services."},
            {"name": "Shosholoza Meyl (long-distance rail)", "mode": "train", "operator": "PRASA",
             "url": "https://www.shosholozameyl.co.za",
             "areas": ["Bloemfontein"],
             "keywords": ["shosholoza meyl"],
             "note": "Long-distance rail."},
        ],
    },
    "limpopo": {
        "name": "Limpopo",
        "cities": ["Polokwane", "Thohoyandou", "Tzaneen", "Lephalale", "Mokopane", "Musina"],
        "services": [
            {"name": "Prasa Metrorail (Polokwane area)", "mode": "train", "operator": "PRASA",
             "phone": "0800 872 2380", "url": "https://www.prasa.com",
             "areas": ["Polokwane", "Mokopane"],
             "keywords": ["prasa", "metrorail", "polokwane"],
             "note": "Limited commuter services."},
            {"name": "Shosholoza Meyl (long-distance rail)", "mode": "train", "operator": "PRASA",
             "url": "https://www.shosholozameyl.co.za",
             "areas": ["Polokwane", "Musina"],
             "keywords": ["shosholoza meyl"],
             "note": "Long-distance rail."},
            {"name": "Limpopo Dept of Transport", "mode": "info", "operator": "Provincial government",
             "url": "https://www.limpopo.gov.za",
             "areas": [],
             "keywords": [],
             "note": "Provincial public transport info & taxi routes."},
        ],
    },
    "mpumalanga": {
        "name": "Mpumalanga",
        "cities": ["Mbombela", "Nelspruit", "Witbank", "Emalahleni", "Secunda", "Middelburg"],
        "services": [
            {"name": "Prasa Metrorail (Emalahleni area)", "mode": "train", "operator": "PRASA",
             "phone": "0800 872 2380", "url": "https://www.prasa.com",
             "areas": ["Emalahleni", "Witbank", "Middelburg"],
             "keywords": ["prasa", "metrorail", "emalahleni"],
             "note": "Limited commuter services."},
            {"name": "Shosholoza Meyl (long-distance rail)", "mode": "train", "operator": "PRASA",
             "url": "https://www.shosholozameyl.co.za",
             "areas": ["Mbombela", "Nelspruit"],
             "keywords": ["shosholoza meyl"],
             "note": "Long-distance rail."},
        ],
    },
    "north_west": {
        "name": "North West",
        "cities": ["Rustenburg", "Mahikeng", "Klerksdorp", "Potchefstroom", "Brits"],
        "services": [
            {"name": "Shosholoza Meyl (long-distance rail)", "mode": "train", "operator": "PRASA",
             "url": "https://www.shosholozameyl.co.za",
             "areas": ["Klerksdorp", "Potchefstroom"],
             "keywords": ["shosholoza meyl"],
             "note": "Long-distance rail."},
            {"name": "North West Dept of Transport", "mode": "info", "operator": "Provincial government",
             "url": "https://www.nwpg.gov.za",
             "areas": [],
             "keywords": [],
             "note": "Provincial public transport info."},
        ],
    },
    "northern_cape": {
        "name": "Northern Cape",
        "cities": ["Kimberley", "Upington", "Kuruman"],
        "services": [
            {"name": "Shosholoza Meyl (long-distance rail)", "mode": "train", "operator": "PRASA",
             "url": "https://www.shosholozameyl.co.za",
             "areas": ["Kimberley", "De Aar"],
             "keywords": ["shosholoza meyl"],
             "note": "Long-distance rail."},
            {"name": "Northern Cape Dept of Transport", "mode": "info", "operator": "Provincial government",
             "url": "https://www.northern-cape.gov.za",
             "areas": [],
             "keywords": [],
             "note": "Provincial public transport info."},
        ],
    },
}

# Soweto sub-areas used for "nearby" suggestions when a Soweto node is selected
SOWETO_SUBAREAS = ["Pimville", "Meadowlands", "Kliptown", "Dobsonville", "Orlando", "Diepkloof",
                   "Zola", "Jabulani", "Chiawelo", "Protea", "Naledi", "Eldorado Park", "Mofolo",
                   "Dube", "Moletsane", "Rockville"]

MODE_ICONS = {"train": "🚆", "brt": "🚌", "bus": "🚌", "info": "ℹ️"}


def province_for(name, admin1=""):
    if admin1:
        key = ADMIN1_MAP.get(admin1.strip().lower())
        if key:
            return key
    t = (" " + name.lower() + " ")
    for admin, key in ADMIN1_MAP.items():
        if admin.split()[0] in t or (admin == "kwa-zulu natal" and ("kzn" in t or "kwa" in t or "zulu" in t)):
            return key
    return "gauteng"  # sensible default


def _tok(name):
    return {x for x in name.lower().split() if len(x) >= 3}


def _match_area(area, name):
    """Does a service area string match the selected place name?"""
    a = area.lower()
    n = name.lower()
    return a in n or n in a or bool(_tok(n) & _tok(a))


def transport_for_area(name, admin1="", feed_items=None, route_reports=None):
    """Build the transport view for a selected area."""
    base = name.split(",")[0].strip()          # strip ", Gauteng" etc.
    key = province_for(name, admin1)
    prov = TRANSPORT.get(key, TRANSPORT["gauteng"])
    services = prov["services"]
    tokens = _tok(base)

    # local = services whose served areas match the selected place
    local = [s for s in services if any(_match_area(a, base) for a in s.get("areas", []))]
    nearby_areas = []
    if not local:
        # suggest same-province cities (and Soweto itself for Soweto nodes)
        if any(base.lower() in s.lower() for s in SOWETO_SUBAREAS):
            nearby_areas = ["Soweto"] + [c for c in prov["cities"] if c.lower() != "soweto"][:4]
        else:
            nearby_areas = [c for c in prov["cities"] if c.lower() not in base.lower()][:5]

    # live status from merged feed (strikes, shutdowns, delays)
    status_items = []
    kw_hits = {}
    for it in feed_items or []:
        text = (it.get("title", "") + " " + it.get("body", "")).lower()
        matched_kw = [s["name"] for s in services
                      if any(k in text for k in s.get("keywords", []))]
        if not matched_kw:
            continue
        area_ok = (not tokens) or any(t in text for t in tokens) \
                  or "south africa" in it.get("areas", []) \
                  or key.replace("_", " ") in it.get("areas", [])
        if not area_ok:
            continue
        status_items.append({"title": it["title"], "url": it.get("url"),
                             "time": it.get("time"), "source": it.get("source"),
                             "operators": matched_kw[:2]})
        for m in matched_kw:
            kw_hits[m] = kw_hits.get(m, 0) + 1
        if len(status_items) >= 6:
            break

    # community route reports
    reports = [r for r in (route_reports or []) if r.get("kind") == "route"]

    # per-service status flag (enrich copies, never mutate module data)
    enriched = []
    for s in services:
        e = dict(s)
        e["has_local"] = any(_match_area(a, base) for a in s.get("areas", []))
        e["status"] = "alert" if kw_hits.get(s["name"]) else ("clear" if s.get("keywords") else "none")
        e["mode_icon"] = MODE_ICONS.get(s.get("mode"), "🚏")
        e["alerts"] = kw_hits.get(s["name"], 0)
        enriched.append(e)

    return {
        "area": name, "province": prov["name"],
        "services": enriched, "local_services": len(local),
        "status_items": status_items, "reports": reports,
        "nearby_areas": nearby_areas,
        "has_local": len(local) > 0,
        "official": [{"name": "PRASA / Metrorail", "url": "https://www.prasa.com"},
                     {"name": "Gautrain (app & live departures)", "url": "https://www.gautrain.co.za"}],
    }
