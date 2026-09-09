"""End-to-end browser test for ServiceWaze v3 (Playwright + Chromium).

Run the server first, then:

    pip install playwright && playwright install chromium
    python browser_test.py

It exercises the five tabs, the gamified task tick, the Ubuntu Grid, a report
→ receipt, and the live-source console, and saves screenshots to shots/.
"""
import os
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SW_BASE", "http://127.0.0.1:8000")
SHOTS = "shots"
os.makedirs(SHOTS, exist_ok=True)

results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {extra}" if extra else ""))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        print("=== LOAD ===")
        page.goto(BASE, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_selector("#sec-now .hero", timeout=45000)
        # dismiss the intro sheet if it is showing
        if page.locator("#introSkip").count():
            page.click("#introSkip")
        page.wait_for_timeout(1200)
        check("app boots with no console errors", not errors, errors[:2] if errors else "")
        check("Now hero renders", page.locator("#sec-now .hero").count() == 1)
        page.screenshot(path=f"{SHOTS}/v3-01-now.png")

        print("=== PREPARE ===")
        page.click('#nav button[data-tab="prepare"]')
        page.wait_for_timeout(1500)
        tasks = page.locator("#sec-prepare .task")
        check("prepare list has tasks", tasks.count() > 0, f"{tasks.count()} tasks")
        cost = page.locator("#costBox").inner_text()
        check("cost engine returns rands", "R" in cost, cost[:48].replace("\n", " "))
        if tasks.count():
            tasks.first.locator(".tick").click()
            page.wait_for_timeout(900)
            check("ticking a task marks it done", page.locator("#sec-prepare .task.done").count() >= 1)
        page.screenshot(path=f"{SHOTS}/v3-02-prepare.png")

        print("=== GRID ===")
        page.click('#nav button[data-tab="grid"]')
        page.wait_for_timeout(2500)
        body = page.locator("#gridBody").inner_text()
        check("grid lists neighbours or empty state", len(body.strip()) > 10)
        page.click('[data-g="stokvel"]')
        page.wait_for_timeout(1500)
        check("stokvel tab renders", "R" in page.locator("#gridBody").inner_text())
        page.screenshot(path=f"{SHOTS}/v3-03-grid.png")

        print("=== COMMUNITY ===")
        page.click('#nav button[data-tab="community"]')
        page.wait_for_timeout(2500)
        check("receipts render", len(page.locator("#recBox").inner_text().strip()) > 10)
        check("news feed renders", len(page.locator("#feedBox").inner_text().strip()) > 10)
        src = page.locator("#srcBox").inner_text()
        check("live-source console renders", "up" in src.lower(), src[:40].replace("\n", " "))
        page.screenshot(path=f"{SHOTS}/v3-04-community.png")

        print("=== YOU ===")
        page.click('#nav button[data-tab="you"]')
        page.wait_for_timeout(2500)
        you = page.locator("#sec-you").inner_text()
        check("profile + score render", "Resilience" in you or "score" in you.lower())
        check("badges render", page.locator("#sec-you .bcell").count() >= 4)
        page.screenshot(path=f"{SHOTS}/v3-05-you.png")

        print("=== REPORT → RECEIPT ===")
        page.click("#fab")
        page.wait_for_timeout(600)
        page.fill("#rArea", "Soweto")
        page.fill("#rMsg", "Automated test report")
        page.click("#rSend")
        page.wait_for_timeout(2500)
        toast = page.locator("#toast").inner_text()
        check("report issues a receipt", "SW-" in toast, toast[:70])
        page.screenshot(path=f"{SHOTS}/v3-06-receipt.png")

        print("=== OFFLINE ===")
        ctx.set_offline(True)
        page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
        check("offline shell still renders", page.locator("#sec-now").count() == 1)
        page.screenshot(path=f"{SHOTS}/v3-07-offline.png")
        ctx.set_offline(False)

        check("no runtime errors during the whole run", not errors, errors[:3] if errors else "")
        browser.close()

    bad = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed")
    if bad:
        print("FAILED:", bad)


if __name__ == "__main__":
    main()
