"""WhatsApp alert integration (provider-agnostic).

Real sending requires a WhatsApp Business API provider credential
(Clickatell / 360dialog / CM.com). Without one, the module runs in
DRY-RUN mode: messages are recorded to the outbox (DB + log file) and the
API still works — so the whole flow is testable end to end, then flips to
real delivery by setting WA_PROVIDER and WA_PROVIDER_TOKEN.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "servicewaze.db")
OUTBOX_LOG = os.path.join(DATA_DIR, "whatsapp_outbox.log")

PROVIDER = os.environ.get("WA_PROVIDER", "dryrun")          # clickatell | dryrun
TOKEN = os.environ.get("WA_PROVIDER_TOKEN", "")


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS wa_optins(
        phone TEXT PRIMARY KEY, area TEXT, enabled INTEGER DEFAULT 1, created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS wa_outbox(
        id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, title TEXT, body TEXT,
        status TEXT, created TEXT)""")
    con.commit()
    return con


def opt_in(phone, area=""):
    con = _db()
    con.execute("INSERT OR REPLACE INTO wa_optins(phone,area,enabled,created) VALUES(?,?,1,?)",
                (phone, area, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()
    con.close()


def opt_out(phone):
    con = _db()
    con.execute("UPDATE wa_optins SET enabled=0 WHERE phone=?", (phone,))
    con.commit()
    con.close()


def list_optins():
    con = _db()
    rows = con.execute("SELECT phone, area, enabled FROM wa_optins WHERE enabled=1").fetchall()
    con.close()
    return [{"phone": r[0], "area": r[1] or ""} for r in rows]


def outbox(limit=20):
    con = _db()
    rows = con.execute(
        "SELECT id, phone, title, body, status, created FROM wa_outbox ORDER BY id DESC LIMIT ?",
        (limit,)).fetchall()
    con.close()
    return [{"id": r[0], "phone": r[1], "title": r[2], "body": r[3],
             "status": r[4], "created": r[5]} for r in rows]


def send(phone, title, body):
    """Send a message: real provider if configured, else dry-run record."""
    message = f"{title}\n{body}" if title and title not in body else body
    if PROVIDER == "clickatell" and TOKEN:
        try:
            r = requests.post(
                "https://platform.clickatell.com/messages",
                headers={"Authorization": TOKEN, "Content-Type": "application/json"},
                json={"channel": "whatsapp", "to": phone, "content": message},
                timeout=15)
            status = "sent" if r.ok else f"error:{r.status_code}"
        except Exception as e:
            status = f"error:{e}"
    else:
        status = "dryrun"
    con = _db()
    cur = con.execute(
        "INSERT INTO wa_outbox(phone,title,body,status,created) VALUES(?,?,?,?,?)",
        (phone, title, body, status, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()
    rid = cur.lastrowid
    con.close()
    with open(OUTBOX_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": rid, "phone": phone, "title": title, "body": body,
                            "status": status, "mode": PROVIDER}) + "\n")
    return {"id": rid, "status": status, "mode": PROVIDER}


def send_test(phone):
    """Send a sample digest to one number (dry-run verified)."""
    return send(phone, "ServiceWaze", "Test message — WhatsApp alerts are working ✅\n"
                                      "Live status for your area: electricity, water, weather, transport.")
