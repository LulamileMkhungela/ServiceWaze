/* Real-browser UI audit for ServiceWaze.
   Headless Chrome, mobile viewport. For every tab it reports:
     - console / page errors
     - horizontal overflow and clipped text
     - touch targets smaller than 44 px
     - text smaller than 11 px
     - contrast ratio below 4.5:1
   and writes a screenshot of each tab to ui_audit/.

   Usage:  node tools/ui_audit.js [baseUrl] [--w=390] [--h=844]
*/
const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");

const args = process.argv.slice(2);
const BASE = args.find((a) => /^https?:/.test(a)) || "http://localhost:8000";
const W = +(args.find((a) => a.startsWith("--w=")) || "--w=390").slice(4);
const H = +(args.find((a) => a.startsWith("--h=")) || "--h=844").slice(4);
const OUT = path.join(__dirname, "..", "ui_audit");
fs.mkdirSync(OUT, { recursive: true });

const AUDIT = () => {
  const out = { overflow: null, clipped: [], smallTap: [], smallText: [], lowContrast: [] };
  const px = (v) => parseFloat(v) || 0;
  const lum = (c) => {
    const [r, g, b] = c;
    const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const parse = (s) => {
    const m = /rgba?\(([^)]+)\)/.exec(s || "");
    if (!m) return null;
    const p = m[1].split(",").map((x) => parseFloat(x));
    return { rgb: [p[0], p[1], p[2]], a: p.length > 3 ? p[3] : 1 };
  };
  const bgOf = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0.6) return c.rgb;
      n = n.parentElement;
    }
    return [0, 0, 0];
  };
  const label = (el) =>
    el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") +
    (el.className && typeof el.className === "string" ? "." + el.className.split(" ")[0] : "");

  const se = document.scrollingElement;
  if (se && se.scrollWidth > window.innerWidth + 1)
    out.overflow = { scrollWidth: se.scrollWidth, innerWidth: window.innerWidth };

  document.querySelectorAll("body *").forEach((el) => {
    const st = getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden" || px(st.opacity) === 0) return;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;

    // horizontally off-screen content
    if (r.right > window.innerWidth + 2 && !el.closest(".scrollx, .seg, #areasBar, .hero, .leaflet-container"))
      out.clipped.push({ el: label(el), right: Math.round(r.right), vw: window.innerWidth });

    // clipped text
    const hasText = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
    if (hasText && el.scrollWidth > el.clientWidth + 2 && st.overflowX !== "auto" && st.overflowX !== "scroll")
      out.clipped.push({ el: label(el), kind: "text-clip", scrollW: el.scrollWidth, clientW: el.clientWidth });

    // tap targets
    if (el.matches("button, a, select, input, [role=button], .tick, .switchbtn") && (r.height < 44 || r.width < 32))
      out.smallTap.push({ el: label(el), w: Math.round(r.width), h: Math.round(r.height) });

    // tiny text
    if (hasText && px(st.fontSize) < 11)
      out.smallText.push({ el: label(el), size: st.fontSize });

    // contrast
    if (hasText && r.height < 400) {
      const fg = parse(st.color);
      if (fg && fg.a > 0.5) {
        const bg = bgOf(el);
        const l1 = lum(fg.rgb), l2 = lum(bg);
        const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        const size = px(st.fontSize), bold = px(st.fontWeight) >= 700;
        const need = size >= 18.66 || (size >= 14 && bold) ? 3 : 4.5;
        if (ratio < need)
          out.lowContrast.push({ el: label(el), ratio: +ratio.toFixed(2), need, size: st.fontSize,
                                 text: (el.textContent || "").trim().slice(0, 40) });
      }
    }
  });
  const dedupe = (arr) => {
    const seen = new Set();
    return arr.filter((x) => { const k = x.el + (x.kind || "") + (x.text || ""); if (seen.has(k)) return false; seen.add(k); return true; });
  };
  out.clipped = dedupe(out.clipped).slice(0, 12);
  out.smallTap = dedupe(out.smallTap).slice(0, 12);
  out.smallText = dedupe(out.smallText).slice(0, 12);
  out.lowContrast = dedupe(out.lowContrast).slice(0, 12);
  return out;
};

(async () => {
  const browser = await puppeteer.launch({ args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  const page = await browser.newPage();
  await page.setViewport({ width: W, height: H, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => errors.push("PAGEERROR: " + e.message.slice(0, 200)));

  await page.goto(BASE, { waitUntil: "networkidle2", timeout: 60000 });
  await new Promise((r) => setTimeout(r, 3500));

  // dismiss onboarding / splash if present
  try {
    const skip = await page.$("#introSkip");
    if (skip) { await skip.click(); await new Promise((r) => setTimeout(r, 800)); }
  } catch (e) {}

  const report = { base: BASE, viewport: [W, H], tabs: {}, errors: [] };
  const tabs = ["now", "prepare", "grid", "community", "you"];
  for (const t of tabs) {
    try { await page.click(`#nav button[data-tab="${t}"]`); } catch (e) { errors.push("no nav for " + t); }
    await new Promise((r) => setTimeout(r, 3000));
    const res = await page.evaluate(AUDIT);
    const html = await page.evaluate((tab) => {
      const el = document.querySelector("#sec-" + tab);
      return el ? el.innerHTML.length : 0;
    }, t);
    report.tabs[t] = { ...res, htmlChars: html };
    await page.screenshot({ path: path.join(OUT, `${t}.png`), fullPage: false });
    await page.screenshot({ path: path.join(OUT, `${t}-full.png`), fullPage: true });
  }
  report.errors = errors.slice(0, 15);
  fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 2));

  let bad = 0;
  for (const [t, r] of Object.entries(report.tabs)) {
    const issues = (r.overflow ? 1 : 0) + r.clipped.length + r.smallTap.length + r.smallText.length + r.lowContrast.length;
    bad += issues;
    console.log(`${t.padEnd(10)} html ${String(r.htmlChars).padStart(5)}  issues ${issues}` +
      (r.overflow ? `  OVERFLOW ${r.overflow.scrollWidth}>${r.overflow.innerWidth}` : ""));
  }
  if (report.errors.length) { console.log("\nCONSOLE ERRORS:"); report.errors.forEach((e) => console.log(" -", e)); }
  console.log("\nscreenshots in ui_audit/ · full report ui_audit/report.json");
  console.log(bad === 0 && !report.errors.length ? "UI AUDIT CLEAN" : `UI AUDIT: ${bad} layout issues`);
  await browser.close();
  process.exit(0);
})();
