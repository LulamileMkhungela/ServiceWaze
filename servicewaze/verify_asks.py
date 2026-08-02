"""Targeted verification of the user's exact requirements, in a real browser."""
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
results = []
def check(name, ok, extra=""):
    results.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{' — ' + extra if extra else ''}")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    pg.wait_for_function("document.getElementById('nlabel')&&document.getElementById('nlabel').textContent!=='…'", timeout=90000)
    pg.wait_for_timeout(1200)
    # dismiss first-run intro modal if present (it covers the screen)
    if pg.locator("#introOverlay.open").count()>0:
        pg.click("#introGo"); pg.wait_for_timeout(300)

    # --- 1. chips: Soweto + Johannesburg present ---
    chips = pg.evaluate("Array.from(document.querySelectorAll('#areasBar .chip')).map(c=>c.innerText)")
    check("default chips: Soweto + Johannesburg",
          any("Soweto" in c for c in chips) and any("Johannesburg" in c for c in chips), str(chips))

    # --- 2. Soweto chip selected -> home data for Soweto ---
    pg.click("#areasBar .chip:has-text('Soweto')")
    pg.wait_for_timeout(1500)
    hero = pg.inner_text(".hero")
    check("home shows Soweto", "Soweto" in hero, [l for l in hero.splitlines() if "Soweto" in l][:1].__str__())
    check("home has weather temp", any("°" in l for l in hero.splitlines()))
    check("home has electricity", "No load-shedding" in hero or "Stage" in hero or "Status" in hero)
    check("home shows community reports for Soweto", pg.locator(".report").count() >= 1, f"{pg.locator('.report').count()} reports")

    # --- 3. Transport tab for Soweto: all govt operators ---
    pg.click("#nav button[data-tab='transport']")
    pg.wait_for_selector("#sec-transport .report:visible", timeout=30000)
    pg.wait_for_timeout(1000)
    tr = pg.inner_text("#sec-transport")
    for name in ["Gautrain", "Gautrain Bus", "Prasa", "Metrorail", "Rea Vaya", "A Re Yeng", "Shosholoza"]:
        check(f"Soweto transport shows {name}", name.lower() in tr.lower())
    check("Soweto transport marks services that serve it", "serves this area" in tr.lower())
    pg.screenshot(path="shots/v-soweto-transport.png")

    # --- 4. Add Mofolo (Soweto sub-area) -> no local govt transport -> ask about Soweto areas ---
    pg.click("#nav button[data-tab='more']"); pg.wait_for_timeout(300)
    pg.click("#addChip")
    pg.fill("#addQ", "Mofolo")
    pg.wait_for_selector("#addSuggest li", timeout=10000)
    pg.click("#addSuggest li")
    pg.wait_for_timeout(800)
    pg.click("#nav button[data-tab='transport']")
    pg.wait_for_timeout(2500)
    tr2 = pg.inner_text("#sec-transport")
    check("Mofolo: 'No government transport found' prompt", "No government transport found" in tr2)
    check("Mofolo: asks about Soweto areas", "Soweto" in tr2, [l for l in tr2.splitlines() if "Soweto" in l][:2].__str__())
    pg.screenshot(path="shots/v-mofolo-prompt.png")

    # --- 5. Tap the Soweto suggestion -> transport re-renders for Soweto ---
    pg.click("#sec-transport .chip:has-text('Soweto')")
    pg.wait_for_timeout(2000)
    tr3 = pg.inner_text("#sec-transport")
    check("tapping Soweto suggestion shows its transport", "Gautrain" in tr3 and "Metrorail" in tr3)

    # --- 6. Selected chip drives news scope ---
    pg.click("#nav button[data-tab='news']")
    pg.wait_for_selector("#sec-news .news:visible", timeout=20000)
    sel = pg.evaluate("document.getElementById('newsArea').value")
    check("news defaults to My area", sel == "my", sel)
    check("news items render", pg.locator("#sec-news .news").count() >= 5)

    # --- 7. Alerts + More follow the selected area ---
    pg.click("#nav button[data-tab='alerts']")
    pg.wait_for_selector("#sEskom:visible", timeout=10000)
    check("alerts tab renders", True)
    pg.click("#nav button[data-tab='more']")
    pg.wait_for_selector("#installBtn:visible", timeout=10000)
    more = pg.inner_text("#sec-more")
    check("more shows active area (Soweto)", "Soweto" in more)

    # --- 8. Everything clickable: report flow still works ---
    pg.click("#fab")
    pg.wait_for_selector("#overlay.open", timeout=5000)
    pg.fill("#rMsg", "Verification test")
    pg.click("#go")
    pg.wait_for_timeout(2500)
    check("report submit works", "Report sent" in pg.inner_text("#toast"))

    check("zero JS errors", len(errs) == 0, str(errs[:3]))
    b.close()

fails = [n for n, ok in results if not ok]
print(f"\n===== {len(results)-len(fails)}/{len(results)} PASS =====")
