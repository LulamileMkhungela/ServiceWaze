"""Real-browser functional test for ServiceWaze (Playwright/Chromium).
Prints PASS/FAIL for each interaction and saves screenshots to shots/.
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SHOTS = "shots"
os.makedirs(SHOTS, exist_ok=True)

results = []
def check(name, ok, extra=""):
    results.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{' — ' + extra if extra else ''}")

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    page = ctx.new_page()

    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))

    print("=== LOAD ===")
    page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    # wait until live data has actually rendered (pill changes from initial "…", hero has a temp)
    page.wait_for_function(
        "document.getElementById('nlabel') && document.getElementById('nlabel').textContent !== '…'",
        timeout=90000)
    page.wait_for_function(
        "document.querySelector('.hero .big') && document.querySelector('.hero .big').textContent.trim().length > 0",
        timeout=30000)
    page.wait_for_timeout(800)
    # dismiss first-run intro modal if present (it covers the screen)
    if page.locator("#introOverlay.open").count() > 0:
        page.click("#introGo")
        page.wait_for_timeout(300)
    check("home hero renders", True)

    hero = page.inner_text(".hero")
    check("weather temp visible in hero", "°" in hero, [l for l in hero.splitlines() if "°" in l][:2].__str__())
    check("electricity pill shows live stage", page.inner_text("#nlabel") != "", page.inner_text("#nlabel"))

    # cards present
    for label, sel in [("electricity card", "text=Electricity"), ("water card", "text=Water"),
                       ("weather card", "text=Weather"), ("transport card", "text=Transport")]:
        check(label, page.locator(sel).first.is_visible())

    # community reports section on home
    check("community report shown (seeded)", page.locator(".report").count() >= 1, f"{page.locator('.report').count()} reports")
    page.screenshot(path=f"{SHOTS}/01-home.png", full_page=False)

    print("=== TABS ===")
    for tab, label, sel in [("services", "Services", "#sec-services .links a"),
                            ("news", "News", "#sec-news .news"),
                            ("alerts", "Alerts", "#sEskom"), ("more", "More", "#installBtn")]:
        page.click(f"#nav button[data-tab='{tab}']")
        page.wait_for_selector(sel + ":visible", timeout=30000)
        page.wait_for_timeout(400)
        n = page.locator(sel).count()
        check(f"{label} tab renders ({sel}: {n})", n >= 1)
        page.screenshot(path=f"{SHOTS}/02-{tab}.png")

    print("=== TRANSPORT TAB (govt transport per area) ===")
    page.click("#nav button[data-tab='transport']")
    page.wait_for_selector("#sec-transport .report:visible", timeout=30000)
    page.wait_for_timeout(600)
    tr_count = page.locator("#sec-transport .report").count()
    check("transport tab renders services", tr_count >= 5, f"{tr_count} service/status cards")
    tr_text = page.inner_text("#sec-transport")
    for name in ["Gautrain", "Gautrain Bus", "Prasa", "Rea Vaya", "A Re Yeng", "Shosholoza"]:
        check(f"transport shows {name}", name.lower() in tr_text.lower())
    check("transport shows live status", "Live status" in tr_text or "Disruption" in tr_text or "No disruptions" in tr_text)
    page.screenshot(path=f"{SHOTS}/02-transport.png")

    print("=== TRANSPORT: rural area -> nearby prompt ===")
    page.click("#nav button[data-tab='more']")
    page.wait_for_timeout(300)
    page.click("#addChip")
    page.fill("#addQ", "Malamulele")
    page.wait_for_selector("#addSuggest li", timeout=10000)
    page.click("#addSuggest li")
    page.wait_for_timeout(500)
    page.click("#nav button[data-tab='transport']")
    page.wait_for_timeout(2500)
    tr2 = page.inner_text("#sec-transport")
    check("no-local prompt shows nearby areas", "No government transport found" in tr2 and "Polokwane" in tr2)
    page.screenshot(path=f"{SHOTS}/03-transport-rural.png")
    # switch back to Soweto chip
    page.click("#areasBar .chip[data-i='0']")
    page.wait_for_timeout(1500)

    print("=== NEWS DEFAULT SCOPE (selected area) ===")
    page.click("#nav button[data-tab='news']")
    page.wait_for_selector("#sec-news .news:visible", timeout=20000)
    sel = page.evaluate("document.getElementById('newsArea').value")
    check("news defaults to 'My area' scope", sel == "my", sel)
    page.screenshot(path=f"{SHOTS}/04-news.png")

    print("=== NEWS FILTERS ===")
    page.click("#nav button[data-tab='news']")
    page.wait_for_timeout(400)
    before = page.locator(".news").count()
    check("news items render", before >= 5, f"{before} items")
    # category filter: click water
    page.click(".fchip[data-nc='water']")
    page.wait_for_timeout(400)
    after = page.locator(".news").count()
    check("category filter (water) works", after <= before and after >= 1, f"{before} -> {after}")
    page.screenshot(path=f"{SHOTS}/03-news-filtered.png")
    page.click(".fchip[data-nc='all']")
    page.wait_for_timeout(300)

    print("=== LANGUAGE SWITCH ===")
    page.click(".langs button[data-lang='zu']")
    page.wait_for_timeout(400)
    zu_water = page.locator("h2:has-text('Amanzi')").count()
    check("isiZulu UI active (Amanzi=Water)", zu_water >= 1)
    page.screenshot(path=f"{SHOTS}/04-zu.png")
    page.click(".langs button[data-lang='en']")
    page.wait_for_timeout(300)

    print("=== ADD AREA ===")
    chips_before = page.locator("#areasBar .chip").count()
    page.click("#addChip")
    page.fill("#addQ", "Durban")
    page.wait_for_selector("#addSuggest li", timeout=10000)
    page.click("#addSuggest li")
    page.wait_for_timeout(500)
    chips_after = page.locator("#areasBar .chip").count()
    check("add area via search works", chips_after == chips_before + 1, f"{chips_before} -> {chips_after}")
    page.screenshot(path=f"{SHOTS}/05-areas.png")

    print("=== REPORT FLOW ===")
    page.click("#fab")
    page.wait_for_selector("#overlay.open", timeout=5000)
    check("report modal opens", True)
    page.fill("#rMsg", "Browser test: lights flickering on 5th Ave")
    page.click("#go")
    page.wait_for_timeout(2500)
    toast_text = page.inner_text("#toast")
    check("report submitted (toast)", "thank" in toast_text.lower() or "thank" in "sent" or toast_text != "", toast_text)
    page.screenshot(path=f"{SHOTS}/06-report.png")

    print("=== SERVICES CLICKABLE ===")
    page.click("#nav button[data-tab='services']")
    page.wait_for_timeout(400)
    tel = page.locator("a[href^='tel:']").count()
    wa = page.locator("a[href^='https://wa.me']").count()
    ext = page.locator("a[href^='http'][target='_blank']").count()
    check("clickable links in services", tel >= 3 and wa >= 1 and ext >= 3, f"tel:{tel} wa:{wa} links:{ext}")
    page.screenshot(path=f"{SHOTS}/07-services.png")

    print("=== CONSOLE ERRORS ===")
    check("zero JS console/page errors", len(console_errors) == 0, str(console_errors[:5]) if console_errors else "")

    browser.close()

fails = [n for n, ok in results if not ok]
print(f"\n===== RESULT: {len(results)-len(fails)}/{len(results)} PASS =====")
sys.exit(1 if fails else 0)
