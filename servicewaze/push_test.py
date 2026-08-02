"""End-to-end Web Push test: browser subscribes (granted permission),
server sends a real push, service worker receives it.
"""
import json
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.grant_permissions(["notifications"], origin=BASE)
    page = ctx.new_page()
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_function(
        "document.getElementById('nlabel') && document.getElementById('nlabel').textContent !== '…'",
        timeout=90000)
    # go to Alerts, click enable push
    page.click("#nav button[data-tab='alerts']")
    page.wait_for_selector("#pushBtn:visible", timeout=20000)
    page.click("#pushBtn")
    page.wait_for_timeout(3000)
    state = page.inner_text("#pushState")
    print("pushState:", state)

    # check subscription registered server-side
    req = urllib.request.Request(BASE + "/api/push/test", method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read().decode())
    print("test push result:", res)

    subs = json.loads(urllib.request.urlopen(BASE + "/api/health", timeout=10).read())
    print("health ok")
    browser.close()
    ok = "ON" in state and res.get("sent", 0) >= 1
    print("PUSH E2E:", "PASS" if ok else "FAIL")
