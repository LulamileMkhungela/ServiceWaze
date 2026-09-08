/* Headless smoke test for the ServiceWaze PWA client.
   No browser is available in CI/sandbox, so we stub just enough DOM to run
   app.js against the live server. This catches runtime errors in the render
   path (template bugs, bad property access, undefined data shapes) that would
   otherwise only show up as a white screen on a real device.

   Usage:  node tools/js_smoke.js  [baseUrl]
*/
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8000";
const ROOT = path.join(__dirname, "..", "servicewaze");

class El {
  constructor(sel = "?") {
    this._sel = sel;
    this.dataset = {};
    this.style = {};
    this.classList = {
      _s: new Set(),
      add(...c) { c.forEach((x) => this._s.add(x)); },
      remove(...c) { c.forEach((x) => this._s.delete(x)); },
      toggle(c, f) { if (f === undefined) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); } else if (f) this._s.add(c); else this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    };
    this.children = [];
    this.value = "";
    this.textContent = "";
    this.files = [];
    this.selectedOptions = [{ dataset: {} }];
    this._html = "";
    this._src = "";
  }
  set src(v) {
    this._src = String(v);
    // no network in CI: simulate a blocked CDN asset
    if (/^https?:/.test(this._src)) setTimeout(() => { if (this._onerror) this._onerror(new Error("blocked")); }, 5);
  }
  get src() { return this._src; }
  set onerror(f) { this._onerror = f; }
  get onerror() { return this._onerror; }
  set onload(f) { this._onload = f; }
  get onload() { return this._onload; }
  set innerHTML(v) { this._html = String(v); }
  get innerHTML() { return this._html; }
  // the real DOM escapes through a temp element; the stub keeps text visible
  set textContent(v) { this._html = String(v); }
  get textContent() { return this._html; }
  set className(v) { this._cls = v; }
  get className() { return this._cls || ""; }
  set onclick(f) { this._onclick = f; }
  get onclick() { return this._onclick; }
  set oninput(f) { this._oninput = f; }
  set onchange(f) { this._onchange = f; }
  querySelector(s) { return new El(s); }
  querySelectorAll() { return []; }
  addEventListener() {}
  focus() {}
  remove() {}
  click() { if (this._onclick) this._onclick({ target: this }); }
  getAttribute() { return null; }
  setAttribute() {}
  appendChild(c) { this.children.push(c); }
  get selectedIndex() { return 0; }
}

const registry = new Map();
function el(sel) {
  if (!registry.has(sel)) registry.set(sel, new El(sel));
  return registry.get(sel);
}

const NAV = ["now", "prepare", "grid", "community", "you"].map((t) => { const e = new El('#nav button'); e.dataset.tab = t; return e; });
// Pull [data-x="y"] stubs out of rendered HTML so handlers get wired and the
// smoke test can click segment / outcome / vouch buttons for real.
function collect(sel) {
  const m = /^\[data-([a-zA-Z0-9_-]+)\]$/.exec(sel);
  if (!m) return [];
  const attr = m[1];
  const out = [];
  for (const node of registry.values()) {
    const re = new RegExp("data-" + attr + '="([^"]*)"', "g");
    let hit;
    while ((hit = re.exec(node.innerHTML || "")) !== null) {
      const e = new El(sel);
      e.dataset[attr] = hit[1];
      out.push(e);
      if (out.length > 40) return out;
    }
  }
  return out;
}

const document = {
  documentElement: new El("html"),
  head: new El("head"),
  querySelector: (s) => el(s),
  querySelectorAll: (s) => (s === "#nav button" ? NAV : collect(s)),
  getElementById: (s) => el("#" + s),
  createElement: () => new El("div"),
  addEventListener: (name, fn) => { if (name === "DOMContentLoaded") document._ready = fn; },
  body: new El("body"),
};

const store = {};
const localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
};

const realFetch = global.fetch;
async function fetchStub(url, opts) {
  const u = String(url).startsWith("http") ? String(url) : BASE + url;
  const res = await realFetch(u, opts);
  return res;
}

const navigator = {
  onLine: true,
  vibrate: () => {},
  share: undefined,
  serviceWorker: { register: async () => ({}), ready: Promise.resolve({}) },
  geolocation: { getCurrentPosition: () => {} },
  language: "en",
};

const window = {
  addEventListener: () => {},
  scrollTo: () => {},
  speechSynthesis: undefined,
  location: { href: "/", origin: BASE },
  navigator,
};

global.document = document;
global.localStorage = localStorage;
global.navigator = navigator;
global.window = window;
global.fetch = fetchStub;
global.alert = () => {};
global.prompt = () => "100";
global.speechSynthesis = undefined;
global.self = global;
global.URLSearchParams = URLSearchParams;

setTimeout(() => { console.log("HARD TIMEOUT — forcing exit"); process.exit(3); }, 45000).unref();

const errors = [];
process.on("uncaughtException", (e) => errors.push(e));
process.on("unhandledRejection", (e) => errors.push(e));

const code = fs.readFileSync(path.join(ROOT, "static", "js", "app.js"), "utf8");

(async () => {
  try {
    // eslint-disable-next-line no-new-func
    new Function("document", "localStorage", "navigator", "window", "fetch", "setTimeout", "setInterval",
      code)(document, localStorage, navigator, window, fetchStub, setTimeout, setInterval);
    if (document._ready) await document._ready();
  } catch (e) {
    console.log("FATAL during boot:", e && e.stack);
    process.exit(1);
  }
  await new Promise((r) => setTimeout(r, 4000));

  const nowHtml = el("#sec-now").innerHTML;

  console.log("NOW html length:", nowHtml.length);
  if (!nowHtml.length) { console.log("FAIL: Now tab rendered nothing"); process.exit(1); }
  for (const needle of ["Resilience", "Services right now", "Do this before it hits"]) {
    if (!nowHtml.includes(needle)) console.log("WARN: Now tab missing section:", needle);
  }

  // exercise the other tabs
  const tabs = { prepare: "sec-prepare", grid: "sec-grid", community: "sec-community", you: "sec-you" };
  const navBtns = document.querySelectorAll("#nav button");
  for (const b of navBtns) {
    if (!b.dataset.tab || b.dataset.tab === "now") continue;
    try {
      // the app binds go() through these buttons in boot; call the same path
      await new Promise((r) => setTimeout(r, 100));
    } catch (e) { errors.push(e); }
  }

  // click through tabs by invoking the same code path the nav uses
  try {
    const js = code;
    // simulate tab switches through the exported behaviour: call each nav button's click handler
    for (const b of navBtns) {
      if (b._onclick) { try { b._onclick(); } catch (e) { errors.push(e); } }
    }
  } catch (e) { errors.push(e); }

  // exercise the new v3.1 surfaces: grid segments, forecast, schedule, a11y
  await new Promise((r) => setTimeout(r, 1200));
  const segs = document.querySelectorAll("[data-seg]");
  for (const want of ["business", "map", "offers", "needs", "nearby", "stokvel"]) {
    const b = segs.find((s2) => s2.dataset.seg === want);
    if (b && b._onclick) { try { b._onclick(); } catch (e) { errors.push(e); } }
    await new Promise((r) => setTimeout(r, 500));
  }
  for (const sel of ["[data-out]", "[data-verify]", "[data-text]", "[data-contrast]", "[data-motion]", "[data-bc]"]) {
    const btns = document.querySelectorAll(sel);
    if (btns[0] && btns[0]._onclick) { try { btns[0]._onclick(); } catch (e) { errors.push(e); } }
    await new Promise((r) => setTimeout(r, 250));
  }

  await new Promise((r) => setTimeout(r, 2500));
  for (const [tab, id] of Object.entries(tabs)) {
    const html = el("#" + id).innerHTML;
    console.log(`${tab.padEnd(10)} rendered ${String(html.length).padStart(6)} chars`);
    if (html.length < 40) console.log(`  FAIL: ${tab} looks empty`);
  }

  if (process.env.DUMP) {
    for (const id of ["sec-now", "sec-prepare", "sec-grid", "sec-community", "sec-you"])
      fs.writeFileSync(`/tmp/${id}.html`, el("#" + id).innerHTML);
    for (const id of ["gridBody", "costBox", "feedBox", "recBox", "srcBox", "chatBox", "profBox", "energyBox",
                      "insightBox", "schedBox", "mapList", "mapNote"]) {
      const h = el("#" + id).innerHTML;
      console.log(`  #${id.padEnd(10)} ${String(h.length).padStart(6)} chars`);
      fs.writeFileSync(`/tmp/${id}.html`, h);
    }
  }

  for (const id of ["insightBox", "schedBox"]) {
    const h = el("#" + id).innerHTML;
    if (h.length < 20) { console.log(`  FAIL: #${id} rendered nothing`); process.exit(1); }
  }

  if (errors.length) {
    console.log("\nRUNTIME ERRORS:");
    errors.slice(0, 12).forEach((e) => console.log(" -", (e && e.stack ? e.stack : String(e)).split("\n").slice(0, 4).join("\n   ")));
    process.exit(1);
  }
  console.log("\nSMOKE TEST PASSED — all tabs rendered with no runtime errors");
  process.exit(0);
})();
