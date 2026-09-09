"""Bilingual-by-default UI strings for ServiceWaze.

English first, then isiZulu, isiXhosa, Sesotho and Afrikaans — the home
languages of the majority of South African households. Any missing key falls
back to English, so the product never shows a raw key to a user.

Disruption information is useless if it arrives in a language you have to
translate in your head at 05:00.
"""
from __future__ import annotations

LANGS = {
    "en": {"name": "English", "flag": "🇬🇧"},
    "zu": {"name": "isiZulu", "flag": "🇿🇦"},
    "xh": {"name": "isiXhosa", "flag": "🇿🇦"},
    "st": {"name": "Sesotho", "flag": "🇿🇦"},
    "af": {"name": "Afrikaans", "flag": "🇿🇦"},
}

T = {
    "tagline": {
        "en": "Know it's coming. Be ready. Share what you have.",
        "zu": "Yazi ukuthi kuyeza. Lungela. Yabelana ngalokho onakho.",
        "xh": "Yazi ukuba kuyeza. Lungela. Yabelana ngoko unako.",
        "st": "Tseba hore ea tla. Ittokisetse. Arolelana seo u nang le sona.",
        "af": "Weet dit kom. Wees gereed. Deel wat jy het.",
    },
    "nav.now": {"en": "Now", "zu": "Manje", "xh": "Ngoku", "st": "Hona joale", "af": "Nou"},
    "nav.prepare": {"en": "Prepare", "zu": "Lungiselela", "xh": "Lungiselela", "st": "Ittokisetse", "af": "Berei"},
    "nav.grid": {"en": "Grid", "zu": "Usizo", "xh": "Uncedo", "st": "Thuso", "af": "Netwerk"},
    "nav.community": {"en": "Community", "zu": "Umphakathi", "xh": "Uluntu", "st": "Sechaba", "af": "Gemeenskap"},
    "nav.you": {"en": "You", "zu": "Wena", "xh": "Wena", "st": "Uena", "af": "Jy"},
    "score": {"en": "Resilience", "zu": "Ukuqina", "xh": "Ukomelela", "st": "Mamello", "af": "Weerbaarheid"},
    "nextImpact": {"en": "Next impact", "zu": "Okulandelayo", "xh": "Okulandelayo", "st": "Se latelang", "af": "Volgende"},
    "riskLow": {"en": "Calm", "zu": "Kuthulile", "xh": "Kuzolile", "st": "Khotso", "af": "Kalm"},
    "riskMed": {"en": "Watch", "zu": "Qaphela", "xh": "Qaphela", "st": "Ela hloko", "af": "Let op"},
    "riskHigh": {"en": "Act now", "zu": "Thatha isinyathelo", "xh": "Thatha inyathelo", "st": "Nka bohato", "af": "Tree op"},
    "riskSevere": {"en": "Act now", "zu": "Shesha", "xh": "Khawuleza", "st": "Potlaka", "af": "Tree op"},
    "power": {"en": "Power", "zu": "Ugesi", "xh": "Umbane", "st": "Motlakase", "af": "Krag"},
    "water": {"en": "Water", "zu": "Amanzi", "xh": "Amanzi", "st": "Metsi", "af": "Water"},
    "transport": {"en": "Transport", "zu": "Ezokuthutha", "xh": "Ezothutho", "st": "Dipalango", "af": "Vervoer"},
    "food": {"en": "Food", "zu": "Ukudla", "xh": "Ukutya", "st": "Dijo", "af": "Kos"},
    "air": {"en": "Air", "zu": "Umoya", "xh": "Umoya", "st": "Moea", "af": "Lug"},
    "live": {"en": "Live", "zu": "Bukhoma", "xh": "Bukhoma", "st": "Phelang", "af": "Lewendig"},
    "demo": {"en": "Demo data", "zu": "Idatha yesibonelo", "xh": "Idatha yomzekelo", "st": "Boitsebiso ba pontsho", "af": "Demodata"},
    "cached": {"en": "Cached", "zu": "Kugciniwe", "xh": "Igcinwe", "st": "Bolokilwe", "af": "Kas"},
    "offline": {"en": "Offline", "zu": "Akuxhunyiwe", "xh": "Akuxhumekanga", "st": "Ha o na inthanete", "af": "Vanlyn af"},
    "report": {"en": "Report", "zu": "Bika", "xh": "Bika", "st": "Tlaleha", "af": "Rapporteer"},
    "share": {"en": "Share", "zu": "Yabelana", "xh": "Yabelana", "st": "Arolelana", "af": "Deel"},
    "done": {"en": "Done", "zu": "Kwenziwe", "xh": "Kwenziwe", "st": "Entsoe", "af": "Klaar"},
    "save": {"en": "Save", "zu": "Gcina", "xh": "Gcina", "st": "Boloka", "af": "Stoor"},
    "cancel": {"en": "Cancel", "zu": "Khansela", "xh": "Rhoxisa", "st": "Hlakola", "af": "Kanselleer"},
    "send": {"en": "Send", "zu": "Thumela", "xh": "Thumela", "st": "Romela", "af": "Stuur"},
    "add": {"en": "Add", "zu": "Engeza", "xh": "Yongeza", "st": "Kenya", "af": "Voeg by"},
    "minutes": {"en": "min", "zu": "imiz", "xh": "imiz", "st": "mets", "af": "min"},
    "hours": {"en": "h", "zu": "h", "xh": "h", "st": "h", "af": "u"},
    "offer": {"en": "I can help", "zu": "Ngingasiza", "xh": "Ndinganceda", "st": "Ke ka thusa", "af": "Ek kan help"},
    "need": {"en": "I need help", "zu": "Ngidinga usizo", "xh": "Ndidinga uncedo", "st": "Ke hloka thuso", "af": "Ek het hulp nodig"},
    "claim": {"en": "Claim", "zu": "Thatha", "xh": "Thatha", "st": "Nka", "af": "Neem"},
    "stokvel": {"en": "Stokvel", "zu": "Isitokvel", "xh": "Isitokhwe", "st": "Setokofele", "af": "Stokvel"},
    "contribute": {"en": "Contribute", "zu": "Faka imali", "xh": "Faka imali", "st": "Kenya tjhelete", "af": "Dra by"},
    "create": {"en": "Create", "zu": "Dala", "xh": "Yenza", "st": "Etsa", "af": "Skep"},
    "level": {"en": "Level", "zu": "Izinga", "xh": "Inqanaba", "st": "Boemo", "af": "Vlak"},
    "badges": {"en": "Badges", "zu": "Amabheji", "xh": "Amabheji", "st": "Dibeche", "af": "Kentekens"},
    "savings": {"en": "Saved", "zu": "Kongiwe", "xh": "Kugciniwe", "st": "Bolokiloe", "af": "Gespaar"},
    "leaderboard": {"en": "Top areas", "zu": "Izindawo eziphezulu", "xh": "Iindawo eziphezulu", "st": "Dibaka tse ka pele", "af": "Top-gebiede"},
    "settings": {"en": "Settings", "zu": "Izilungiselelo", "xh": "Iisetingi", "st": "Di-setting", "af": "Instellings"},
    "language": {"en": "Language", "zu": "Ulimi", "xh": "Ulwimi", "st": "Puo", "af": "Taal"},
    "receipts": {"en": "Receipts", "zu": "Amarisidi", "xh": "Amaliti", "st": "Diresiti", "af": "Kwitansies"},
    "news": {"en": "News", "zu": "Izindaba", "xh": "Iindaba", "st": "Ditaba", "af": "Nuus"},
    "chat": {"en": "Chat", "zu": "Ingxoxo", "xh": "Incoko", "st": "Puisano", "af": "Gesels"},
    "sources": {"en": "Live sources", "zu": "Imithombo", "xh": "Imithombo", "st": "Mehloli", "af": "Bronne"},
    "install": {"en": "Install app", "zu": "Faka uhlelo", "xh": "Faka usetyenziso", "st": "Kenya app", "af": "Installeer"},
    "readAloud": {"en": "Read aloud", "zu": "Fundela", "xh": "Fundela", "st": "Balla", "af": "Lees hardop"},
    "lowData": {"en": "Data saver", "zu": "Yonga idatha", "xh": "Gcina idatha", "st": "Boloka data", "af": "Dataspaar"},
    "prepareTasks": {"en": "Do this before it hits", "zu": "Yenza lokhu ngaphambi kokuba kwenzeke",
                     "xh": "Yenza oku ngaphambi kokuba kwenzeke",
                     "st": "Etsa sena pele se etsahala", "af": "Doen dit voor dit tref"},
    "nothing": {"en": "Nothing urgent — good time to prepare", "zu": "Akukho okuphuthumayo",
                "xh": "Akukho nto ingxamisekileyo", "st": "Ha ho na ntho e potlakileng",
                "af": "Niks dringend nie"},
    "valueAtStake": {"en": "at stake", "zu": "okusengozini", "xh": "okusengozini", "st": "kotsing", "af": "op die spel"},
    "household": {"en": "Household", "zu": "Umndeni", "xh": "Usapho", "st": "Lelapa", "af": "Huishouding"},
    "people": {"en": "People", "zu": "Abantu", "xh": "Abantu", "st": "Batho", "af": "Mense"},
    "stored": {"en": "Water stored", "zu": "Amanzi agciniwe", "xh": "Amanzi agciniwe", "st": "Metsi a bolokiloeng", "af": "Water gestoor"},
    "checkin": {"en": "Check in", "zu": "Ngena", "xh": "Ngena", "st": "Kena", "af": "Teken in"},
    "sourcesTitle": {"en": "Where this data comes from", "zu": "Ivelaphi le datha",
                     "xh": "Ivelaphi le datha", "st": "Boitsebiso bo tswa kae", "af": "Waar die data vandaan kom"},
    "sourcesNote": {"en": "ServiceWaze never invents a number. Every reading shows its source, "
                          "when it was fetched and whether it is live, cached or demo data.",
                    "zu": "I-ServiceWaze ayiqambi izinombolo. Yonke imininingwane ikhombisa umthombo wayo.",
                    "xh": "I-ServiceWaze ayenzi manani. Lonke ulwazi lubonisa umthombo walo.",
                    "st": "ServiceWaze ha iqampe dinomoro. Boitsebiso bohle bo bontsha mohloli.",
                    "af": "ServiceWaze maak nie syfers op nie. Elke lesing wys sy bron."},
    "emergency": {"en": "Emergency", "zu": "Isimo esiphuthumayo", "xh": "Imeko engxamisekileyo",
                  "st": "Boemo ba tshohanyetso", "af": "Noodgeval"},
    "call": {"en": "Call", "zu": "Shayela", "xh": "Fowunela", "st": "Letsetsa", "af": "Bel"},
    "whatsapp": {"en": "WhatsApp", "zu": "WhatsApp", "xh": "WhatsApp", "st": "WhatsApp", "af": "WhatsApp"},
    "nearby": {"en": "Nearby", "zu": "Eduze", "xh": "Kufuphi", "st": "Haufi", "af": "Naby"},
    "openIn": {"en": "Open in", "zu": "Vula ku", "xh": "Vula ku", "st": "Bula ho", "af": "Open in"},
    "logIn": {"en": "Log in", "zu": "Ngena", "xh": "Ngena", "st": "Kena", "af": "Meld aan"},
    "streak": {"en": "day streak", "zu": "izinsuku zilandelana", "xh": "iintsuku zilandelelana",
               "st": "matsatsi a latellanang", "af": "dae-agtereenvolgens"},
}


def translate(key: str, lang: str = "en") -> str:
    entry = T.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("en") or key


def bundle(lang: str = "en") -> dict:
    return {k: (v.get(lang) or v.get("en") or k) for k, v in T.items()}


def languages() -> list[dict]:
    return [{"code": c, **meta} for c, meta in LANGS.items()]
