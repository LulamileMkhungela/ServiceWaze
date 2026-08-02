"""Push notifications (Web Push / VAPID) + server-side alert engine.

Sends real push notifications to subscribed browsers (works when the app is
closed), triggered by:
  - new community reports matching the subscriber's area
  - load-shedding stage changes (stage >= 2)

Also exposes a test endpoint to verify the full pipeline.
"""
import asyncio
import base64
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

from pywebpush import webpush

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "servicewaze.db")
VAPID_PATH = os.path.join(DATA_DIR, "vapid.json")
VAPID_CLAIM = {"sub": "mailto:alerts@servicewaze.example"}


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS push_subs(
        endpoint TEXT PRIMARY KEY, p256dh TEXT, auth TEXT, area TEXT, created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)""")
    con.commit()
    return con


def _vapid():
    if not os.path.exists(VAPID_PATH):
        return None
    return json.load(open(VAPID_PATH))


def public_key():
    v = _vapid()
    return v["public"] if v else None


def add_subscription(endpoint, p256dh, auth, area=""):
    con = _db()
    con.execute("INSERT OR REPLACE INTO push_subs(endpoint,p256dh,auth,area,created) VALUES(?,?,?,?,?)",
                (endpoint, p256dh, auth, area, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()
    con.close()


def count_subscriptions():
    con = _db()
    n = con.execute("SELECT COUNT(*) FROM push_subs").fetchone()[0]
    con.close()
    return n


def _match_area(sub_area, report_area):
    if not sub_area:
        return True
    a = {t for t in sub_area.lower().split() if len(t) >= 3}
    b = {t for t in report_area.lower().split() if len(t) >= 3}
    return bool(a & b) or sub_area.lower() in report_area.lower() or report_area.lower() in sub_area.lower()


def send_push(endpoint, p256dh, auth, title, body, url="/"):
    v = _vapid()
    if not v:
        return False
    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=v["private_pem"],
            vapid_claims=VAPID_CLAIM,
            timeout=10,
        )
        return True
    except Exception as e:
        print(f"[push] send failed for {endpoint[:40]}...: {e}")
        return False


def broadcast(title, body, area_filter=None, url="/"):
    """Send to all (or area-matching) subscriptions. Returns sent count."""
    con = _db()
    rows = con.execute("SELECT endpoint,p256dh,auth,area FROM push_subs").fetchall()
    con.close()
    sent = 0
    for endpoint, p256dh, auth, area in rows:
        if area_filter is not None and not _match_area(area, area_filter):
            continue
        if send_push(endpoint, p256dh, auth, title, body, url):
            sent += 1
    return sent


def meta_get(key, default=None):
    con = _db()
    row = con.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
    con.close()
    return row[0] if row else default


def meta_set(key, value):
    con = _db()
    con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (key, str(value)))
    con.commit()
    con.close()


def send_test_push():
    """Send a test push to all subscriptions (for verification)."""
    return broadcast("ServiceWaze", "Test push — notifications work! ✅", url="/")


def run_checks():
    """One pass of the alert engine. Called every 60s by the background loop."""
    import sources

    # 1) load-shedding stage change
    try:
        st = sources.eskom_status().get("stage")
        if isinstance(st, int):
            prev = meta_get("last_stage")
            if prev is None or int(prev) != st:
                meta_set("last_stage", st)
                if st >= 2:
                    n = broadcast(f"⚡ Load-shedding: Stage {st}",
                                  "Load-shedding has started. Check your area schedule.")
                    if n:
                        print(f"[push] stage change -> {n} pushes")
    except Exception as e:
        print("[push] stage check err", e)

    # 2) new community reports
    try:
        last = int(meta_get("last_report_id", 0) or 0)
        con = _db()
        rows = con.execute(
            "SELECT id, area, kind, message FROM reports WHERE id > ? ORDER BY id LIMIT 10", (last,)).fetchall()
        con.close()
        for rid, area, kind, msg in rows:
            meta_set("last_report_id", rid)
            title = f"🚰 {area}"
            body = f"{kind}" + (f": {msg[:120]}" if msg else "")
            n = broadcast(title, body, area_filter=area, url="/")
            if n:
                print(f"[push] report {rid} -> {n} pushes")
    except Exception:
        pass


async def loop():
    while True:
        try:
            await asyncio.to_thread(run_checks)
        except Exception as e:
            print("[push] loop err", e)
        await asyncio.sleep(60)
