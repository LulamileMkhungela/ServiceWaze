/* ServiceWaze v3 — household resilience network (PWA client)
   No build step, no framework, ~40 kB. Designed for low-end Android and 3G. */
(function () {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (s) => { const d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; };

  const LS = {
    dev: "sw_device", areas: "sw_areas_v3", set: "sw_settings_v3",
    done: "sw_done_v3", lang: "sw_lang", theme: "sw_theme", installed: "sw_intro_v3",
  };

  /* ------------------------------------------------------------------ state */
  const S = {
    device: localStorage.getItem(LS.dev) || (function () {
      const v = "d" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
      localStorage.setItem(LS.dev, v); return v;
    })(),
    areas: JSON.parse(localStorage.getItem(LS.areas) || "[]"),
    active: 0,
    tab: "now",
    data: {},              // areaName -> /api/status bundle
    feed: [], grid: { offers: [], needs: [], points: {}, stokvels: [] },
    receipts: [], scorecard: null, chat: [], health: null,
    you: null, strings: {}, lang: localStorage.getItem(LS.lang) || "en",
    theme: localStorage.getItem(LS.theme) || "dark",
    settings: Object.assign({ dataSaver: false, notify: false, readAloud: true,
      heads60: true, heads15: true, textSize: "normal", contrast: "normal" },
      JSON.parse(localStorage.getItem(LS.set) || "{}")),
    done: JSON.parse(localStorage.getItem(LS.done) || "{}"),
    queue: [], gridTab: "map", forecast: null, scheduleCache: null,
    loading: false,
  };

  /* ------------------------------------------------------------------- i18n */
  function t(k, fallback) {
    return S.strings[k] || fallback || k;
  }
  async function loadI18n(lang) {
    try {
      const r = await fetch("/api/i18n?lang=" + encodeURIComponent(lang));
      const j = await r.json();
      S.strings = j.strings || {};
      S.lang = lang;
      localStorage.setItem(LS.lang, lang);
      document.documentElement.lang = lang;
    } catch (e) { S.strings = {}; }
  }

  /* ------------------------------------------------------------------ helpers */
  function toast(msg, ms) {
    const el = $("#toast"); el.textContent = msg; el.style.display = "block";
    clearTimeout(el._t); el._t = setTimeout(() => { el.style.display = "none"; }, ms || 2600);
  }
  function vibrate(x) { if (navigator.vibrate) try { navigator.vibrate(x || 25); } catch (e) {} }
  function fmtMin(m) {
    if (m == null) return "—";
    if (m <= 0) return "now";
    if (m < 60) return m + " " + t("minutes", "min");
    const h = Math.floor(m / 60), mm = m % 60;
    return h + t("hours", "h") + (mm ? " " + mm + t("minutes", "min") : "");
  }
  function timeAgo(iso) {
    if (!iso) return "";
    const d = new Date(iso), s = (Date.now() - d.getTime()) / 1000;
    if (isNaN(s)) return "";
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  }
  function rand(n, d) { return "R" + Number(n || 0).toLocaleString("en-ZA", { minimumFractionDigits: d == null ? 0 : d, maximumFractionDigits: d == null ? 0 : d }); }
  async function api(path, opts) {
    const r = await fetch(path, Object.assign({ headers: { "X-Device-Id": S.device } }, opts || {}));
    if (!r.ok) throw new Error(path + " " + r.status);
    return r.json();
  }
  async function post(path, body) {
    return api(path, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Device-Id": S.device },
      body: JSON.stringify(body || {}),
    });
  }
  function srcBadge(meta) {
    if (!meta) return "";
    if (meta.live === false || meta.tier === "sim")
      return `<span class="badge sim">${esc(t("demo", "Demo data"))}</span>`;
    if (meta.tier === "cache")
      return `<span class="badge">${esc(t("cached", "Cached"))}</span>`;
    const s = meta.source || "live";
    return `<span class="badge official">${esc(s)}</span>`;
  }
  function speak(text) {
    if (!S.settings.readAloud || !window.speechSynthesis) return;
    try {
      const u = new SpeechSynthesisUtterance(text.replace(/[^\w\s.,!?°%R]/g, " ").slice(0, 400));
      u.lang = ["zu", "xh", "st", "af"].includes(S.lang) ? "en-ZA" : "en-ZA";
      u.rate = 1;
      speechSynthesis.cancel(); speechSynthesis.speak(u);
    } catch (e) {}
  }
  function share(title, text) {
    const payload = { title: "ServiceWaze", text: title + "\n" + text };
    if (navigator.share) navigator.share(payload).catch(() => {});
    else window.open("https://wa.me/?text=" + encodeURIComponent(payload.text), "_blank");
  }

  /* ------------------------------------------------- device-direct live tier
     The PWA can reach CORS-enabled APIs (Open-Meteo, Overpass) even when the
     ServiceWaze host cannot. The phone pulls the reading itself, hands it to
     the server (POST /api/device/data) and the server computes impact, costs
     and advisories from the REAL payload — tagged tier:"device".            */
  const OM_W = "https://api.open-meteo.com/v1/forecast";
  const OM_A = "https://air-quality-api.open-meteo.com/v1/air-quality";
  const OVERPASS = "https://overpass-api.de/api/interpreter";

  async function handToServer(name, url, params, payload, ms) {
    try {
      await post("/api/device/data", { name, url, params, data: payload, latency_ms: ms });
      return true;
    } catch (e) { return false; }
  }

  async function pullDeviceData(a) {
    if (!a || a.lat == null || !navigator.onLine || S.settings.dataSaver) return;
    const wx = {
      latitude: a.lat, longitude: a.lon,
      current: "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_gusts_10m",
      daily: "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_gusts_10m_max,uv_index_max,shortwave_radiation_sum,sunrise,sunset",
      forecast_days: 4, timezone: "Africa/Johannesburg",
    };
    try {
      const t0 = Date.now();
      const r = await fetch(OM_W + "?" + new URLSearchParams(wx), { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      const j = await r.json();
      if (j && j.current) await handToServer("Open-Meteo Forecast", OM_W, wx, j, Date.now() - t0);
    } catch (e) {}
    const aq = {
      latitude: a.lat, longitude: a.lon,
      current: "us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide",
      timezone: "Africa/Johannesburg",
    };
    try {
      const t0 = Date.now();
      const r = await fetch(OM_A + "?" + new URLSearchParams(aq), { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      const j = await r.json();
      if (j && j.current) await handToServer("Open-Meteo Air Quality", OM_A, aq, j, Date.now() - t0);
    } catch (e) {}
  }

  async function overpassDirect(lat, lon, kind, radius) {
    const q = {
      water: `[out:json][timeout:25];(node["amenity"="drinking_water"](around:${radius},${lat},${lon});node["man_made"="water_tap"](around:${radius},${lat},${lon});node["man_made"="water_well"](around:${radius},${lat},${lon});node["amenity"="water_point"](around:${radius},${lat},${lon}););out body 30;`,
      food: `[out:json][timeout:25];(node["shop"~"supermarket|convenience|greengrocer|bakery|butcher"](around:${radius},${lat},${lon});node["amenity"="marketplace"](around:${radius},${lat},${lon});node["amenity"="food_bank"](around:${radius},${lat},${lon}););out body 30;`,
      care: `[out:json][timeout:25];(node["amenity"~"clinic|doctors|hospital|pharmacy|community_centre"](around:${radius},${lat},${lon}););out body 25;`,
    }[kind];
    if (!q) return null;
    try {
      const t0 = Date.now();
      const r = await fetch(OVERPASS, { method: "POST", body: "data=" + encodeURIComponent(q) });
      if (!r.ok) throw new Error(r.status);
      const j = await r.json();
      post("/api/sources/device", { name: "OpenStreetMap Overpass (" + kind + ")", ok: true,
        latency_ms: Date.now() - t0, url: OVERPASS }).catch(() => {});
      return (j.elements || []).map((e) => {
        const tg = e.tags || {};
        return {
          id: "osm-" + e.id, kind,
          name: tg.name || tg.operator || tg.amenity || tg.shop || tg.man_made || "Community point",
          lat: e.lat, lon: e.lon, distance_m: Math.round(haversine(lat, lon, e.lat, e.lon) * 1000),
          opening_hours: tg.opening_hours || "", source: "OpenStreetMap", tier: "device", live: true,
        };
      }).sort((x, y) => x.distance_m - y.distance_m).slice(0, 20);
    } catch (e) { return null; }
  }

  function haversine(a1, o1, a2, o2) {
    const R = 6371, rad = (x) => (x * Math.PI) / 180;
    const dp = rad(a2 - a1), dl = rad(o2 - o1);
    const h = Math.sin(dp / 2) ** 2 + Math.cos(rad(a1)) * Math.cos(rad(a2)) * Math.sin(dl / 2) ** 2;
    return R * 2 * Math.asin(Math.sqrt(h));
  }

  /* --------------------------------------------------------------- areas/UI */
  function saveAreas() { localStorage.setItem(LS.areas, JSON.stringify(S.areas)); }
  function activeArea() { return S.areas[S.active] || null; }

  function renderHeader() {
    const h = S.health && S.health.summary;
    const live = h ? (h.live || h.device_live) : true;
    $("#livePill").className = "pill " + (navigator.onLine ? (live ? "live" : "demo") : "off");
    $("#livePill").innerHTML = `<span class="dot ${live ? "pulse" : ""}"></span><span>${navigator.onLine ? (live ? t("live", "Live") : t("demo", "Demo")) : t("offline", "Offline")}</span>`;
  }

  function renderAreas() {
    const bar = $("#areasBar");
    bar.innerHTML = S.areas.map((a, i) =>
      `<button class="chip ${i === S.active ? "on" : ""}" data-i="${i}">${esc(a.name)}</button>`).join("")
      + `<button class="chip add" id="addChip">＋ ${esc(t("add", "Add"))}</button>`;
    $$("#areasBar .chip[data-i]").forEach(b => b.onclick = () => { S.active = +b.dataset.i; renderAreas(); loadArea(); });
    $("#addChip").onclick = openAdd;
  }

  /* ------------------------------------------------------------- data load */
  async function loadArea(force) {
    const a = activeArea();
    if (!a) { renderNow(); return; }
    if (!force && S.data[a.name]) { render(); return; }
    S.loading = true; renderNow();
    try {
      const dk = a.name + "|" + a.lat + "," + a.lon;
      if (force && (S.deviceKey !== dk || Date.now() - (S.devicePulledAt || 0) > 600000)) {
        S.deviceKey = dk; S.devicePulledAt = Date.now();
        await pullDeviceData(a);
      }
    } catch (e) {}
    try {
      const q = "/api/status?" + (a.lat != null ? `lat=${a.lat}&lon=${a.lon}&q=${encodeURIComponent(a.name)}`
        : `q=${encodeURIComponent(a.name)}`) + `&device=${encodeURIComponent(S.device)}`;
      S.data[a.name] = await api(q);
    } catch (e) { toast("Could not load this area"); }
    S.loading = false;
    render();
  }

  async function loadExtras() {
    const a = activeArea(); if (!a) return;
    const area = a.name.split(",")[0];
    try { const f = await api(`/api/feed?limit=40`); S.feed = f.items || []; } catch (e) {}
    try { S.grid.offers = (await api(`/api/grid?area=${encodeURIComponent(area)}&limit=30`)).offers || []; } catch (e) {}
    try { S.grid.needs = (await api(`/api/grid?area=${encodeURIComponent(area)}&limit=30`)).needs || []; } catch (e) {}
    try { S.grid.stokvels = (await api(`/api/stokvels?area=${encodeURIComponent(area)}`)).stokvels || []; } catch (e) {}
    try { if (a && a.lat != null) S.grid.points = (await api(`/api/grid/points?lat=${a.lat}&lon=${a.lon}`)).points || {}; } catch (e) {}
    try { S.grid.businesses = (await api(`/api/business?area=${encodeURIComponent(area)}`)).businesses || []; } catch (e) {}
    try { S.receipts = (await api(`/api/receipts?area=${encodeURIComponent(area)}&limit=15`)).receipts || []; } catch (e) {}
    try { S.scorecard = await api(`/api/scorecard?area=${encodeURIComponent(area)}`); } catch (e) {}
    try { S.chat = (await api(`/api/chat?q=${encodeURIComponent(area)}`)).messages || []; } catch (e) {}
    try { S.you = await api(`/api/me/summary?device=${encodeURIComponent(S.device)}`); } catch (e) {}
    try { S.health = await api("/api/sources/health"); } catch (e) {}
    render();
  }

  /* ------------------------------------------------------------------ NOW */
  function ring(value, label, sub) {
    const v = Math.max(0, Math.min(100, value || 0));
    const c = 2 * Math.PI * 40;
    return `<div class="ringwrap">
      <svg width="96" height="96" class="ring">
        <defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#ffc247"/><stop offset="100%" stop-color="#ff7a2f"/>
        </linearGradient></defs>
        <circle class="bg" cx="48" cy="48" r="40"></circle>
        <circle class="fg" cx="48" cy="48" r="40" stroke-dasharray="${c}"
          stroke-dashoffset="${c * (1 - v / 100)}"></circle>
      </svg>
      <div class="ringval"><b class="num">${Math.round(v)}</b><span>${esc(label)}</span></div>
    </div>`;
  }

  function serviceTiles(d) {
    const w = d.weather || {}, air = d.air || {}, el = d.electricity || {}, imp = d.impact || {};
    const thr = (imp.threats || []);
    const has = (s) => thr.find(x => x.service === s);
    const st = (s) => {
      const x = has(s);
      if (!x) return { cls: "s-ok", bar: "b-ok", v: "OK", pct: 100 };
      const map = { critical: ["s-bad", "b-bad", 25], high: ["s-warn", "b-warn", 45], medium: ["s-warn", "b-warn", 65], low: ["s-ok", "b-ok", 85] };
      const m = map[x.severity] || map.low;
      return { cls: m[0], bar: m[1], v: fmtMin(x.minutes_to_impact), pct: m[2] };
    };
    const power = st("power"), water = st("water"), tr = st("transport"), food = st("food"), flood = st("flood");
    const stage = (el.status || {}).stage;
    const tile = (ic, lb, val, cls, bar, pct) =>
      `<div class="tile"><span class="ic">${ic}</span><span class="lb">${esc(lb)}</span>
        <div class="vl num ${cls}">${esc(val)}</div>
        <div class="bar"><i class="${bar}" style="width:${pct}%"></i></div></div>`;
    return `<div class="grid3">
      ${tile("⚡", t("power", "Power"), typeof stage === "number" ? (stage ? "S" + stage : "On") : "—", power.cls, power.bar, power.pct)}
      ${tile("🚰", t("water", "Water"), water.v === "OK" ? "OK" : water.v, water.cls, water.bar, water.pct)}
      ${tile("🚌", t("transport", "Transport"), tr.v === "OK" ? "OK" : tr.v, tr.cls, tr.bar, tr.pct)}
      ${tile("🥫", t("food", "Food"), food.v === "OK" ? "OK" : food.v, food.cls, food.bar, food.pct)}
      ${tile("🌊", "Flood", flood.v === "OK" ? "OK" : flood.v, flood.cls, flood.bar, flood.pct)}
      ${tile("😷", t("air", "Air"), air.aqi != null ? ("AQI " + Math.round(air.aqi)) : "—",
        air.aqi > 150 ? "s-bad" : air.aqi > 100 ? "s-warn" : "s-ok",
        air.aqi > 150 ? "b-bad" : air.aqi > 100 ? "b-warn" : "b-ok",
        air.aqi ? Math.max(10, 100 - air.aqi / 2) : 50)}
    </div>`;
  }

  function renderNow() {
    const el = $("#sec-now");
    const a = activeArea();
    if (!a) {
      el.innerHTML = `<div class="card"><div class="empty"><span class="e">📍</span>
        Add your area to see what's coming, and how long you have.<br><br>
        <button class="btn primary" onclick="document.getElementById('addChip').click()">＋ ${esc(t("add", "Add"))} area</button>
      </div></div>`;
      return;
    }
    const d = S.data[a.name] || {};
    if (S.loading && !d.weather) {
      el.innerHTML = `<div class="card"><div class="skeleton" style="height:120px"></div></div>
        <div class="card"><div class="skeleton" style="height:70px"></div></div>`;
      return;
    }
    const imp = d.impact || {}, you = (d.you || {}).score || { score: 0, band: "building" };
    const risks = imp.threats || [];
    const next = risks.length ? risks[0] : null;
    const risk = imp.risk || 4;
    const sev = risk >= 60 ? "critical" : risk >= 35 ? "high" : risk >= 15 ? "medium" : "low";
    const plan = imp.plan || { tasks: [] };
    const todo = plan.tasks.slice(0, 3);

    const cur = (d.weather || {}).current || {};
    const daily = (d.weather || {}).daily || [];
    const reports = (d.water || {}).reports || [];

    el.innerHTML = `
      <div class="hero">
        <div class="row" style="align-items:flex-start">
          ${ring(you.score, t("score", "Resilience"), (you.band || "").toUpperCase())}
          <div style="flex:1">
            <div class="tiny">${esc(t("nextImpact", "Next impact"))}</div>
            <div class="countdown"><b class="num">${next ? fmtMin(next.minutes_to_impact) : "—"}</b>
              <span class="sev ${sev}">${risk >= 60 ? esc(t("riskHigh", "Act now")) : risk >= 35 ? esc(t("riskMed", "Watch")) : risk >= 15 ? esc(t("riskMed", "Watch")) : esc(t("riskLow", "Calm"))}</span></div>
            <div style="font-size:13.5px;font-weight:600">${esc(imp.headline || t("nothing", "Nothing urgent"))}</div>
            <div class="mt8" style="display:flex;gap:6px;flex-wrap:wrap">
              <button class="btn sm cyan" id="readBtn">🔊 ${esc(t("readAloud", "Read aloud"))}</button>
              <button class="btn sm" id="shareBtn">📤 ${esc(t("share", "Share"))}</button>
            </div>
          </div>
        </div>
      </div>

      <div class="card tight">
        <h2>${esc(t("prepareTasks", "Do this before it hits"))}
          <span class="spacer"></span>
          <span class="xp">${plan.xp_available || 0} XP · ${rand(plan.value_at_stake_rand || 0)} ${esc(t("valueAtStake", "at stake"))}</span></h2>
        ${todo.length ? todo.map(taskRow).join("") :
        `<div class="empty"><span class="e">✅</span>${esc(t("nothing", "Nothing urgent — good time to prepare"))}</div>`}
        <button class="btn wide sm mt8" data-goto="prepare">${esc(t("nav.prepare", "Prepare"))} →</button>
      </div>

      ${serviceTilesEl(d)}

      <div class="card tight">
        <h2>🌦️ ${esc(a.name)} ${srcBadge(d.weather)}</h2>
        <div class="between">
          <div><span class="big num">${cur.temp != null ? Math.round(cur.temp) : "—"}°</span>
            <span class="muted">${esc(cur.desc || "")}</span></div>
          <div class="center"><button class="btn sm ghost" id="harvestBtn">💧 ${esc("Harvest calc")}</button></div>
          <div class="muted num">💨 ${cur.wind != null ? Math.round(cur.wind) : "—"} km/h<br>💧 ${cur.humidity != null ? cur.humidity : "—"}%</div>
        </div>
        <div class="scrollx mt8">
          ${daily.map(x => `<div class="tile" style="min-width:74px"><span class="ic">${x.icon || "🌡️"}</span>
            <span class="lb">${esc(x.date)}</span><div class="vl num">${Math.round(x.tmax)}°/${Math.round(x.tmin)}°</div>
            <div class="tiny num">${x.precip_prob || 0}% · ${Math.round(x.precip_sum || 0)}mm</div></div>`).join("")}
        </div>
        ${((d.weather || {}).advisories || []).length ? `<div class="mt8">${(d.weather.advisories || []).map(x =>
        `<div class="item"><span class="sev ${x.level === "severe" ? "critical" : "medium"}">${x.level}</span> ${esc(x.text)}</div>`).join("")}</div>` : ""}
      </div>

      <div class="card tight">
        <h2>🗣️ ${esc(t("community", "Community"))} <span class="spacer"></span>
          <button class="btn sm ghost" data-goto="community">${esc(t("news", "News"))} →</button></h2>
        ${reports.length ? reports.slice(0, 3).map(r =>
        `<div class="item"><div class="between"><span class="t">${esc(r.kind.replace(/_/g, " "))} · ${esc(r.area)}</span>
          <span class="badge">${r.confirms} ✓</span></div>
          <div class="b">${esc(r.message || "—")} · ${timeAgo(r.created)}</div></div>`).join("")
        : `<div class="empty"><span class="e">🤫</span>${esc("No reports near you. If something is broken, report it — neighbours get the warning.")}</div>`}
      </div>

      ${(d.grid && d.grid.count) ? `<div class="card tight">
        <h2>🤝 ${esc(t("nav.grid", "Grid"))} <span class="spacer"></span>
          <button class="btn sm ghost" data-goto="grid">${esc("Open")} →</button></h2>
        <div class="muted">${d.grid.count} neighbour offers/requests near ${esc(a.name.split(",")[0])}.
        ${((d.grid.stats || {}).hand_overs || 0)} hand-overs completed on ServiceWaze.</div>
      </div>` : ""}
    `;
    $("#readBtn").onclick = () => speak(`${a.name}. ${imp.headline || ""}. ${plan.tasks.slice(0, 3).map(x => x.title).join(". ")}`);
    $("#shareBtn").onclick = () => share(a.name, (imp.headline || "") + "\n\n" + (plan.tasks.slice(0, 3).map(x => "• " + x.title).join("\n")) + "\n\n— ServiceWaze");
    $("#harvestBtn").onclick = () => { openHarvest(); };
    $$("[data-goto]").forEach(b => b.onclick = () => go(b.dataset.goto));
    bindTasks(todo);
  }

  function serviceTilesEl(d) { return `<div class="card tight"><h2>📊 ${esc("Services right now")}</h2>${serviceTiles(d)}</div>`; }

  function taskRow(x) {
    const done = !!S.done[x.id];
    return `<div class="task ${done ? "done" : ""}" data-task="${x.id}">
      <div class="tick ${done ? "on" : ""}" data-tick="${x.id}">✓</div>
      <div style="flex:1">
        <div class="tt">${x.icon || "•"} ${esc(x.title)}</div>
        <div class="td">${esc(x.detail || "")}</div>
      </div>
      <div style="text-align:right"><span class="xp">+${x.xp} XP</span>
        <div class="tiny num">${x.minutes}${t("minutes", "min")}</div></div>
    </div>`;
  }

  function bindTasks(tasks) {
    $$("[data-tick]").forEach(el => el.onclick = async () => {
      const id = el.dataset.tick;
      const task = (tasks || []).find(x => x.id === id) || {};
      if (S.done[id]) { delete S.done[id]; }
      else {
        S.done[id] = Date.now();
        vibrate(30);
        try {
          const r = await post("/api/me/action", { device: S.device, action: task.action || "drill", meta: id, area: (activeArea() || {}).name });
          toast(`+${r.xp_earned || 0} XP · ${r.name ? r.name : ""}`, 1800);
        } catch (e) {}
      }
      localStorage.setItem(LS.done, JSON.stringify(S.done));
      render();
    });
  }

  /* -------------------------------------------------------------- PREPARE */
  async function renderPrepare() {
    const el = $("#sec-prepare");
    const a = activeArea();
    if (!a) { el.innerHTML = `<div class="card"><div class="empty">Add an area first.</div></div>`; return; }
    const d = S.data[a.name] || {};
    const imp = d.impact || {}, plan = imp.plan || { tasks: [] };
    const left = plan.minutes_left || 180, need = plan.tasks_minutes || 0;
    const pct = Math.min(100, Math.round(need / Math.max(1, left) * 100));
    const tariffs = d.cost || {};

    el.innerHTML = `
      <div class="hero">
        <div class="between">
          <div><div class="tiny">${esc(t("nextImpact", "Next impact"))}</div>
            <div class="countdown"><b class="num">${fmtMin(left)}</b></div>
            <div class="muted">${esc(imp.headline || "")}</div></div>
          <div style="text-align:right"><div class="tiny">Tasks need</div>
            <div class="big num" style="font-size:22px">${need}${t("minutes", "min")}</div>
            <div class="tiny ${plan.fits ? "s-ok" : "s-warn"}">${plan.fits ? "fits" : "start now"}</div></div>
        </div>
        <div class="bar2 mt8"><i style="width:${pct}%"></i></div>
      </div>

      <div class="card tight">
        <h2>✅ ${esc(t("prepareTasks", "Do this before it hits"))}
          <span class="spacer"></span><span class="xp">${plan.xp_available} XP</span></h2>
        ${plan.tasks.map(taskRow).join("")}
      </div>

      <div class="card tight">
        <h2>💸 ${esc("What it costs you")}</h2>
        <div class="seg mb8" id="costSeg">
          <button class="on" data-c="elec">⚡ ${esc(t("power", "Power"))}</button>
          <button data-c="water">🚰 ${esc(t("water", "Water"))}</button>
          <button data-c="food">🥫 ${esc(t("food", "Food"))}</button>
          <button data-c="shift">⏱️ Shift</button>
        </div>
        <div id="costBox"></div>
      </div>

      <div class="card tight">
        <h2>⚡ ${esc("Load-shedding windows")}</h2>
        <div id="schedBox"><div class="skeleton"></div></div>
      </div>

      <div class="card tight">
        <h2>🏠 ${esc(t("household", "Household"))}</h2>
        <div id="profBox"><div class="skeleton"></div></div>
      </div>

      <div class="card tight">
        <h2>☀️ ${esc("Solar & rain")}</h2>
        <div class="grid2">
          <button class="btn sm" id="solarBtn">☀️ Solar payback</button>
          <button class="btn sm" id="harvestBtn2">🌧️ Rain harvest</button>
        </div>
        <div id="energyBox" class="mt8"></div>
      </div>
    `;
    bindTasks(plan.tasks);
    $$("#costSeg button").forEach(b => b.onclick = () => {
      $$("#costSeg button").forEach(x => x.classList.remove("on")); b.classList.add("on"); loadCost(b.dataset.c);
    });
    loadCost("elec");
    loadProfile();
    renderSchedule();
    $("#solarBtn").onclick = loadSolar;
    $("#harvestBtn2").onclick = openHarvest;
  }

  async function loadCost(kind) {
    const box = $("#costBox"); if (!box) return;
    const a = activeArea(); const area = a ? a.name : "";
    try {
      if (kind === "elec") {
        const j = await api(`/api/cost/electricity?kwh=350&area=${encodeURIComponent(area)}`);
        box.innerHTML = `<div class="muted">${esc(j.tariff)} · 350 kWh/month</div>
          <div class="row mt8"><div class="big num">${rand(j.total, 2)}</div><div class="muted">/month<br>blended ${rand(j.blended_per_kwh, 2)}/kWh</div></div>
          <div class="kv"><span>Energy</span><b>${rand(j.energy, 2)}</b></div>
          <div class="kv"><span>Fixed charges</span><b>${rand(j.fixed, 2)}</b></div>
          <div class="tiny mt8">${esc(j.basis || "")}</div>`;
      } else if (kind === "water") {
        const j = await api(`/api/cost/water?kl=15&area=${encodeURIComponent(area)}`);
        box.innerHTML = `<div class="muted">${esc(j.tariff)} · 15 kl/month</div>
          <div class="row mt8"><div class="big num">${rand(j.total, 2)}</div><div class="muted">/month</div></div>
          ${(j.lines || []).map(l => `<div class="kv"><span>${esc(l.block)} × ${l.kl} kl</span><b>${rand(l.cost, 2)}</b></div>`).join("")}
          <div class="tiny mt8">${esc(j.basis || "")} ${j.free_kl ? "First " + j.free_kl + " kl free." : ""}</div>`;
      } else if (kind === "food") {
        const j = await api(`/api/cost/basket?area=${encodeURIComponent(area)}&people=4`);
        box.innerHTML = `<div class="muted">Household food basket · ${j.people} people</div>
          <div class="row mt8"><div class="big num">${rand(j.monthly, 2)}</div><div class="muted">/month<br>${rand(j.per_person, 2)} per person</div></div>
          <div class="kv"><span>Food poverty line (per person)</span><b>${rand(j.food_poverty_line_per_person, 0)}</b></div>
          <div class="kv"><span>Nutritional basket, family of 4</span><b>${rand(j.nutritional_basket_family_of_4, 0)}</b></div>
          <div class="tiny mt8">${esc(j.basis || "")}</div>`;
      } else {
        const j = await api("/api/cost/tou?tariff=eskom_homeflex");
        box.innerHTML = `<div class="muted">Eskom Homeflex — cheapest hours first. Move your geyser, pool pump and washing into the green hours.</div>
          <div class="grid4 mt8">${(j.windows || []).slice(0, 8).map(w =>
          `<div class="tile"><span class="lb">${esc(w.hour)}</span><div class="vl num ${w.price < 2 ? "s-ok" : w.price < 4 ? "s-warn" : "s-bad"}">${w.price.toFixed(2)}</div></div>`).join("")}</div>
          <div class="tiny mt8">R/kWh incl. VAT, 2026/27.</div>`;
      }
    } catch (e) { box.innerHTML = `<div class="muted">Could not load.</div>`; }
  }

  async function loadProfile() {
    const box = $("#profBox"); if (!box) return;
    const j = await api(`/api/me/profile?device=${encodeURIComponent(S.device)}`);
    const p = j.profile || {};
    const f = (k, label, type, step) => `<div><label class="fl">${esc(label)}</label>
      <input type="number" data-p="${k}" value="${p[k] == null ? 0 : p[k]}" ${step ? `step="${step}"` : ""}></div>`;
    box.innerHTML = `<div class="grid2">
        ${f("people", t("people", "People"), "number")}
        ${f("water_l", t("stored", "Water stored (L)"), "number", "10")}
        ${f("tank_l", "Tank size (L)", "number", "100")}
        ${f("roof_m2", "Roof area (m²)", "number", "5")}
        ${f("food_days", "Days of food", "number")}
      </div>
      <div class="grid3 mt8">
        ${[["backup_light", "🔦 Light"], ["power_bank", "🔋 Power bank"], ["surge_protect", "🔌 Surge plug"],
        ["solar", "☀️ Solar"], ["alt_cooking", "🔥 Gas/other cooking"], ["route_plan", "🚌 Route B"],
        ["contacts_saved", "☎️ Contacts saved"], ["garden", "🥬 Food garden"], ["", ""]]
        .filter(x => x[0]).map(([k, lb]) => `<button class="btn sm ${p[k] ? "cyan" : "ghost"}" data-tog="${k}">${esc(lb)}</button>`).join("")}
      </div>
      <button class="btn primary wide mt8" id="saveProf">${esc(t("save", "Save"))} · ${esc("updates your score")}</button>`;
    $$("[data-tog]").forEach(b => b.onclick = () => b.classList.toggle("cyan"));
    $("#saveProf").onclick = async () => {
      const body = { device: S.device };
      $$("[data-p]").forEach(i => body[i.dataset.p] = parseFloat(i.value || 0));
      $$("[data-tog]").forEach(b => body[b.dataset.tog] = b.classList.contains("cyan") ? 1 : 0);
      const r = await post("/api/me/profile", body);
      toast("Resilience score: " + Math.round(r.score.score), 2600);
      const a = activeArea(); if (a) delete S.data[a.name];
      loadArea(true);
    };
  }

  async function loadSolar() {
    const a = activeArea(); if (!a || a.lat == null) return toast("Pick an area first");
    const j = await api(`/api/cost/solar?lat=${a.lat}&lon=${a.lon}&kwp=3&area=${encodeURIComponent(a.name)}`);
    $("#energyBox").innerHTML = `<div class="kv"><span>3 kWp produces</span><b>${j.kwh_per_day} kWh/day</b></div>
      <div class="kv"><span>Monthly saving</span><b>${rand(j.monthly_saving, 0)}</b></div>
      <div class="kv"><span>Installed cost (est.)</span><b>${rand(j.capex, 0)}</b></div>
      <div class="kv"><span>Payback</span><b>${j.payback_years} years</b></div>
      <div class="tiny mt8">${esc("Yield from local irradiance " + j.irradiance_kwh_per_kwp + " kWh/kWp/day.")} ${j.live ? "" : "(" + t("demo", "Demo data") + ")"}</div>`;
  }

  async function openHarvest() {
    const a = activeArea(); if (!a || a.lat == null) return toast("Pick an area first");
    const roof = parseFloat(prompt("Roof area in m² (e.g. 60):", "60") || "0") || 60;
    const j = await api(`/api/cost/harvest?lat=${a.lat}&lon=${a.lon}&roof_m2=${roof}`);
    toast(`${j.litres} L harvestable from the next ${j.forecast_mm} mm`);
    setTimeout(async () => {
      const b = $("#energyBox"); if (!b) return;
      b.innerHTML = `<div class="kv"><span>Rain forecast (3 days)</span><b>${j.forecast_mm} mm</b></div>
        <div class="kv"><span>You can capture</span><b>${j.litres} L</b></div>
        <div class="kv"><span>That's</span><b>${j.days_for_4_people} days for 4 people</b></div>
        <div class="tiny mt8">${esc(j.basis)}</div>`;
    }, 60);
  }

  /* ----------------------------------------------------------------- GRID */
  async function renderGrid(sub) {
    const el = $("#sec-grid");
    const a = activeArea();
    const cur = sub || S.gridTab || "map";
    S.gridTab = cur;
    const seg = (id, lb) => `<button class="${cur === id ? "on" : ""}" data-g="${id}">${esc(lb)}</button>`;
    el.innerHTML = `
      <div class="card tight">
        <h2>🤝 ${esc("Ubuntu Grid")}</h2>
        <div class="grid2">
          <button class="btn primary" id="offerBtn">🙌 ${esc(t("offer", "I can help"))}</button>
          <button class="btn cyan" id="needBtn">🆘 ${esc(t("need", "I need help"))}</button>
        </div>
        <div class="tiny mt8">${esc("Share water, power, a fridge shelf, a seat or a skill. Everything is time-boxed and neighbour-verified.")}</div>
      </div>
      <div class="seg mb8">${seg("map", "🗺️ Map")}${seg("offers", "🙌 Offers")}${seg("needs", "🆘 Requests")}${seg("nearby", "📍 Points")}${seg("business", "🏪 Business")}${seg("stokvel", "🐷 " + t("stokvel", "Stokvel"))}</div>
      <div id="gridBody"><div class="skeleton" style="height:120px"></div></div>`;
    $("#offerBtn").onclick = () => openGridForm("offer");
    $("#needBtn").onclick = () => openGridForm("need");
    $$("[data-g]").forEach(b => b.onclick = () => renderGrid(b.dataset.g));
    const body = $("#gridBody");
    try {
      if (cur === "map") { return renderMap(); }
      if (cur === "business") { return renderBusiness(); }
      if (cur === "nearby") {
        if (!a || a.lat == null) { body.innerHTML = `<div class="card"><div class="empty">Pick an area with a location.</div></div>`; return; }
        body.innerHTML = `<div class="card"><div class="skeleton"></div></div>`;
        const pts = {};
        const kinds = ["water", "food", "care"];
        const direct = await Promise.all(kinds.map((k) => overpassDirect(a.lat, a.lon, k, 4000)));
        let gotDevice = false;
        kinds.forEach((k, i) => { if (direct[i] && direct[i].length) { pts[k] = direct[i]; gotDevice = true; } });
        if (!gotDevice) {
          const j = await api(`/api/grid/points?lat=${a.lat}&lon=${a.lon}&kinds=water,food,care`);
          Object.assign(pts, j.points || {});
        }
        body.innerHTML = Object.keys(pts).map(k =>
          `<div class="card tight"><h2>${k === "water" ? "🚰 Water points" : k === "food" ? "🥫 Food" : "🏥 Care"} (${(pts[k] || []).length})</h2>
            ${(pts[k] || []).slice(0, 8).map(p => `<div class="prow"><div class="pdot">${k === "water" ? "🚰" : k === "food" ? "🥫" : "🏥"}</div>
              <div style="flex:1"><div class="t">${esc(p.name)}</div>
              <div class="tiny">${p.distance_m} m${p.opening_hours ? " · " + esc(p.opening_hours) : ""}</div></div>
              <a class="btn sm ghost" target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=18/${p.lat}/${p.lon}">Map</a></div>`).join("")
          || `<div class="empty"><span class="e">📍</span>None mapped nearby yet — add one in OpenStreetMap.</div>`}</div>`).join("");
        return;
      }
      if (cur === "stokvel") {
        const j = await api(`/api/stokvels?area=${encodeURIComponent(a ? a.name.split(",")[0] : "")}`);
        const list = j.stokvels || [];
        body.innerHTML = `<div class="card tight"><h2>🐷 ${esc(t("stokvel", "Resilience stokvels"))}</h2>
          ${list.length ? list.map(s => `<div class="item">
            <div class="between"><span class="t">${esc(s.name)}</span><span class="badge">${s.members} ${esc("members")}</span></div>
            <div class="tiny">${esc(s.purpose)} · ${esc(s.area || "")}</div>
            <div class="bar2 mt8"><i style="width:${Math.round((s.progress || 0) * 100)}%"></i></div>
            <div class="between tiny mt8"><span>${rand(s.saved, 0)} of ${rand(s.target, 0)}</span><span>${rand(s.remaining, 0)} to go</span></div>
            <div class="grid2 mt8"><button class="btn sm cyan" data-contrib="${s.id}">${esc(t("contribute", "Contribute"))}</button>
            <button class="btn sm ghost" data-share-s="${s.id}">📤</button></div></div>`).join("")
          : `<div class="empty"><span class="e">🐷</span>${esc("No stokvel here yet. Start one — a tank ends water outages for a whole street.")}</div>`}
          <button class="btn wide sm mt8" id="newStok">＋ ${esc(t("create", "Start a stokvel"))}</button></div>`;
        $("#newStok").onclick = openStokvel;
        $$("[data-contrib]").forEach(b => b.onclick = async () => {
          const amt = parseFloat(prompt("Amount in rand:", "100") || "0") || 0;
          if (amt <= 0) return;
          const r = await post(`/api/stokvels/${b.dataset.contrib}/contribute`, { device: S.device, amount: amt });
          toast("Potted " + rand(amt) + " — " + rand(r.stokvel.saved, 0) + " saved");
          renderGrid("stokvel");
        });
        return;
      }
      const area = a ? a.name.split(",")[0] : "";
      const j = await api(`/api/grid?area=${encodeURIComponent(area)}&limit=30${(a && a.lat != null) ? `&lat=${a.lat}&lon=${a.lon}` : ""}`);
      const list = cur === "offers" ? (j.offers || []) : (j.needs || []);
      body.innerHTML = `<div class="card tight">${list.length ? list.map(o => `
        <div class="item">
          <div class="between"><span class="t">${o.icon || "🤝"} ${esc(o.title)}</span>
            <span class="badge">${esc(o.kind)}</span></div>
          <div class="b">${esc(o.detail || "")}</div>
          <div class="between mt8"><span class="tiny">${esc(o.handle || "Neighbour")} · ${esc(o.area || "")} ${o.availability ? "· " + esc(o.availability) : ""} · ${timeAgo(o.created)}</span>
            <button class="btn sm ${cur === "offers" ? "cyan" : ""}" data-claim="${o.id}">${cur === "offers" ? esc(t("claim", "Claim")) : "🤝 Help them"}</button></div>
        </div>`).join("")
        : `<div class="empty"><span class="e">${cur === "offers" ? "🙌" : "🆘"}</span>${esc(cur === "offers" ? "No open offers yet. Be the first — it earns Ubuntu Points." : "No open requests. That's a good thing.")}</div>`}</div>`;
      $$("[data-claim]").forEach(b => b.onclick = async () => {
        try {
          await post("/api/grid/claim", { device: S.device, id: +b.dataset.claim });
          toast("Claimed — arrange the hand-over safely 🤝");
          vibrate([20, 40, 20]);
          renderGrid(cur);
        } catch (e) { toast("Could not claim (maybe it's yours)"); }
      });
    } catch (e) { body.innerHTML = `<div class="card"><div class="empty">Could not load the grid.</div></div>`; }
  }

  function openGridForm(mode) {
    const sheet = $("#sheet");
    sheet.innerHTML = `<div class="grab"></div>
      <h3>${mode === "offer" ? "🙌 " + t("offer", "I can help") : "🆘 " + t("need", "I need help")}</h3>
      <p class="muted" style="margin:0 0 8px">${esc(mode === "offer" ? "Offer something your neighbours can use during a disruption." : "Ask for what you need. Requests are visible to your area only.")}</p>
      <label class="fl">Kind</label>
      <select id="gKind">${Object.entries({ water: "💧 Water", power: "⚡ Power & charging", food: "🥫 Food & cooking", cold: "🧊 Fridge space", ride: "🚗 Lift", tools: "🧰 Tools & skills", care: "🧓 Check-in", other: "🤝 Other" }).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
      <label class="fl">Title</label><input id="gTitle" placeholder="${mode === "offer" ? "e.g. 200 L borehole water" : "e.g. Drinking water for 5"}" maxlength="80">
      <label class="fl">Detail</label><textarea id="gDetail" rows="3" placeholder="${mode === "offer" ? "When are you available? Any rules?" : "What exactly do you need, and by when?"}"></textarea>
      <label class="fl">Available</label><input id="gAvail" placeholder="e.g. today 16:00–20:00">
      <div class="grid2 mt12"><button class="btn ghost" id="gCancel">${esc(t("cancel", "Cancel"))}</button>
      <button class="btn primary" id="gSend">${esc(t("send", "Send"))}</button></div>`;
    $("#overlay").classList.add("on");
    $("#gCancel").onclick = closeSheet;
    $("#gSend").onclick = async () => {
      const a = activeArea();
      const title = $("#gTitle").value.trim();
      if (title.length < 3) return toast("Add a short title");
      try {
        await post("/api/grid/add", {
          device: S.device, kind: $("#gKind").value, mode, title,
          detail: $("#gDetail").value.trim(), area: a ? a.name.split(",")[0] : "",
          lat: a ? a.lat : null, lon: a ? a.lon : null, availability: $("#gAvail").value.trim(),
        });
        toast(mode === "offer" ? "Listed — thank you 🤝" : "Posted. Neighbours can see it.");
        vibrate(30); closeSheet(); renderGrid(mode === "offer" ? "offers" : "needs");
      } catch (e) { toast("Could not post"); }
    };
    setTimeout(() => $("#gTitle").focus(), 200);
  }

  function openStokvel() {
    const sheet = $("#sheet");
    const purposes = [
      ["tank", "🛢️ JoJo tank & gutters", 4500], ["solar", "☀️ Solar + battery kit", 18000],
      ["gas", "🔥 Gas stove & cylinder", 1200], ["bulk_food", "🛒 Bulk staple buy", 2400],
      ["borehole", "🕳️ Community borehole", 45000],
    ];
    sheet.innerHTML = `<div class="grab"></div><h3>🐷 ${esc(t("create", "Start a stokvel"))}</h3>
      <p class="muted" style="margin:0 0 8px">${esc("Neighbours pool money for the thing that ends the outage for good.")}</p>
      <label class="fl">Name</label><input id="sName" placeholder="e.g. Pimville Water Tank" maxlength="50">
      <label class="fl">Purpose</label><select id="sPurpose">
        ${purposes.map(([k, lb, amt]) => `<option value="${k}" data-amt="${amt}">${lb} — ±R${amt.toLocaleString()}</option>`).join("")}</select>
      <label class="fl">Target (R)</label><input id="sTarget" type="number" value="4500">
      <div class="grid2 mt12"><button class="btn ghost" id="sCancel">${esc(t("cancel", "Cancel"))}</button>
      <button class="btn primary" id="sSend">${esc(t("create", "Create"))}</button></div>`;
    $("#overlay").classList.add("on");
    $("#sPurpose").onchange = () => { const o = $("#sPurpose").selectedOptions[0]; $("#sTarget").value = o.dataset.amt; };
    $("#sCancel").onclick = closeSheet;
    $("#sSend").onclick = async () => {
      const name = $("#sName").value.trim();
      if (name.length < 3) return toast("Give it a name");
      const a = activeArea();
      await post("/api/stokvels", {
        device: S.device, name, purpose: $("#sPurpose").value,
        area: a ? a.name.split(",")[0] : "", target: parseFloat($("#sTarget").value || 0),
      });
      toast("Stokvel created 🎉"); closeSheet(); renderGrid("stokvel");
    };
  }

  /* ------------------------------------------------------------ COMMUNITY */
  async function renderCommunity() {
    const el = $("#sec-community");
    const a = activeArea();
    const cur = S.feedFilter || "all";
    el.innerHTML = `
      <div class="seg mb8" id="feedSeg">
        <button class="${cur === "all" ? "on" : ""}" data-f="all">All</button>
        <button class="${cur === "water" ? "on" : ""}" data-f="water">🚰</button>
        <button class="${cur === "electricity" ? "on" : ""}" data-f="electricity">⚡</button>
        <button class="${cur === "transport" ? "on" : ""}" data-f="transport">🚌</button>
        <button class="${cur === "weather" ? "on" : ""}" data-f="weather">🌦️</button>
      </div>
      <div class="card tight"><h2>📰 ${esc(t("news", "News"))} &amp; ${esc("official notices")}</h2>
        <div id="feedBox"><div class="skeleton"></div></div></div>
      <div class="card tight">
        <h2>🧾 ${esc(t("receipts", "Receipts"))} <span class="spacer"></span>
          <span class="badge">${(S.scorecard && S.scorecard.sla_compliance != null) ? Math.round(S.scorecard.sla_compliance * 100) + "% SLA" : "—"}</span></h2>
        ${S.scorecard ? `<div class="grid4 mb8">
          <div class="tile"><span class="lb">Open</span><div class="vl num">${S.scorecard.open}</div></div>
          <div class="tile"><span class="lb">Fixed</span><div class="vl num s-ok">${S.scorecard.resolved}</div></div>
          <div class="tile"><span class="lb">Overdue</span><div class="vl num s-bad">${S.scorecard.overdue}</div></div>
          <div class="tile"><span class="lb">Avg</span><div class="vl num">${S.scorecard.avg_hours != null ? Math.round(S.scorecard.avg_hours) + "h" : "—"}</div></div>
        </div>` : ""}
        <div id="recBox"></div>
      </div>
      <div class="card tight">
        <h2>👀 ${esc("Look out for each other")}</h2>
        <div id="watchBox"><div class="skeleton"></div></div>
      </div>
      <div class="card tight">
        <h2>🔮 ${esc("24-hour forecast")} <span class="spacer"></span>
          <span class="badge">${esc("self-learning")}</span></h2>
        <div id="insightBox"><div class="skeleton"></div></div>
      </div>
      <div class="card tight">
        <h2>💬 ${esc(t("chat", "Chat"))} · ${esc(a ? a.name.split(",")[0] : "")}</h2>
        <div id="chatBox" style="max-height:240px;overflow:auto"></div>
        <div class="row mt8"><input id="chatIn" placeholder="${esc("Say something helpful…")}">
          <button class="btn sm cyan" id="chatSend">${esc(t("send", "Send"))}</button></div>
        <div class="tiny mt8">${esc("Reading is free. Writing needs a free account (no email).")} <a href="#" id="authLink">${esc(t("logIn", "Log in"))}</a></div>
      </div>
      <div class="card tight">
        <h2>🛰️ ${esc(t("sources", "Live sources"))}</h2>
        <div id="srcBox"></div>
      </div>`;
    $$("#feedSeg button").forEach(b => b.onclick = () => { S.feedFilter = b.dataset.f; renderCommunity(); });
    $("#authLink").onclick = (e) => { e.preventDefault(); openAuth(); };
    $("#chatSend").onclick = sendChat;
    renderFeed(); renderReceipts(); renderChat(); renderSources(); renderInsights(); renderWatch();
  }

  function renderFeed() {
    const box = $("#feedBox"); if (!box) return;
    const f = S.feedFilter || "all";
    const items = (S.feed || []).filter(i => f === "all" || i.category === f).slice(0, 25);
    box.innerHTML = items.length ? items.map(i => `<div class="item">
      <div class="t">${esc(i.title)}</div>
      <div class="b">${esc((i.body || "").slice(0, 150))}</div>
      <div class="between mt8"><span class="tiny">${esc(i.source || "")} · ${timeAgo(i.time)} ${i.official ? '<span class="badge official">official</span>' : ""}</span>
        <button class="btn sm ghost" data-share-n="${esc(i.title)}">📤</button></div>
    </div>`).join("") : `<div class="empty"><span class="e">📰</span>No items right now.</div>`;
    $$("[data-share-n]").forEach(b => b.onclick = () => share("ServiceWaze", b.dataset.shareN));
  }

  function renderReceipts() {
    const box = $("#recBox"); if (!box) return;
    const list = S.receipts || [];
    box.innerHTML = list.length ? list.slice(0, 8).map(r => {
      const over = r.state === "overdue";
      return `<div class="item">
        <div class="between"><span class="t">${esc(r.ref)} · ${esc(r.kind.replace(/_/g, " "))}</span>
          <span class="badge ${over ? "sim" : r.status === "resolved" ? "official" : ""}">${esc(r.state.replace(/_/g, " "))}</span></div>
        <div class="b">${esc(r.area)} — logged with ${esc(r.entity || "municipality")}</div>
        <div class="bar2 mt8"><i class="${over ? "" : "green"}" style="width:${Math.min(100, Math.round(r.elapsed_hours / Math.max(1, r.sla_hours) * 100))}%;${over ? "background:var(--bad)" : ""}"></i></div>
        <div class="between tiny mt8"><span>${r.elapsed_hours}h of ${r.sla_hours}h SLA · ${r.confirms} neighbour confirmations</span>
          <button class="btn sm ghost" data-share-r="${esc(r.share_text)}">📤</button></div>
      </div>`;
    }).join("") : `<div class="empty"><span class="e">🧾</span>${esc("No reports here yet. When you report, you get a receipt with a clock on it.")}</div>`;
    $$("[data-share-r]").forEach(b => b.onclick = () => share("ServiceWaze receipt", b.dataset.shareR));
  }

  function renderChat() {
    const box = $("#chatBox"); if (!box) return;
    const msgs = S.chat || [];
    box.innerHTML = msgs.length ? msgs.slice().reverse().map(m =>
      `<div class="item"><div class="between"><b>${esc(m.author)}</b><span class="tiny">${timeAgo(m.created)}</span></div>
        <div class="b">${esc(m.message)}</div></div>`).join("")
      : `<div class="empty" style="padding:14px"><span class="e">💬</span>${esc("Quiet here. Ask your neighbours anything about services.")}</div>`;
  }

  async function sendChat() {
    const inp = $("#chatIn"); const msg = inp.value.trim();
    if (msg.length < 2) return;
    const a = activeArea(); if (!a) return;
    const token = localStorage.getItem("sw_token");
    try {
      await api("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + (token || "") },
        body: JSON.stringify({ area: a.name.split(",")[0], message: msg, lat: a.lat, lon: a.lon }),
      });
      inp.value = ""; S.chat = (await api(`/api/chat?q=${encodeURIComponent(a.name.split(",")[0])}`)).messages || [];
      renderChat();
    } catch (e) {
      if (e.message.includes("401")) openAuth();
      else toast("Could not send");
    }
  }

  function openAuth() {
    const sheet = $("#sheet");
    sheet.innerHTML = `<div class="grab"></div><h3>🔐 ${esc(t("logIn", "Log in"))}</h3>
      <p class="muted" style="margin:0 0 8px">${esc("Free account, no email. Needed only to write in chat.")}</p>
      <label class="fl">Username</label><input id="aU" autocomplete="username">
      <label class="fl">Password</label><input id="aP" type="password" autocomplete="current-password">
      <div class="grid2 mt12"><button class="btn ghost" id="aCancel">${esc(t("cancel", "Cancel"))}</button>
      <button class="btn primary" id="aReg">${esc("Create account")}</button></div>
      <button class="btn wide mt8" id="aLogin">${esc(t("logIn", "Log in"))}</button>`;
    $("#overlay").classList.add("on");
    $("#aCancel").onclick = closeSheet;
    const doAuth = async (path) => {
      try {
        const r = await api(path, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: $("#aU").value.trim(), password: $("#aP").value }),
        });
        localStorage.setItem("sw_token", r.token);
        toast("Welcome, " + r.username); closeSheet();
      } catch (e) { toast("Check your details"); }
    };
    $("#aReg").onclick = () => doAuth("/api/auth/register");
    $("#aLogin").onclick = () => doAuth("/api/auth/login");
  }

  async function renderSources() {
    const box = $("#srcBox"); if (!box) return;
    let h = S.health;
    if (!h) { try { h = S.health = await api("/api/sources/health"); } catch (e) {} }
    if (!h) { box.innerHTML = `<div class="muted">Source console unavailable.</div>`; return; }
    box.innerHTML = `<div class="tiny mb8">${esc(t("sourcesNote", ""))}</div>
      <div class="between mb8"><span class="badge">${h.summary.up}/${h.summary.total} up</span>
        <button class="btn sm ghost" id="toggleLive">${h.summary.live ? "Force demo data" : "Try live again"}</button></div>
      ${(h.sources || []).map(s => `<div class="srcline">
        <span class="st ${s.status}">${esc(s.status)}</span>
        <span class="nm">${esc(s.name)}</span>
        <span class="tiny num">${s.latency_ms != null ? s.latency_ms + "ms" : ""}</span>
        <span class="tiny">${s.last_ok ? timeAgo(s.last_ok) : ""}</span></div>`).join("")}`;
    $("#toggleLive").onclick = async () => {
      await api(`/api/sources/set-live?flag=${!S.health.summary.live}`, { method: "POST" });
      S.health = await api("/api/sources/health"); renderSources(); renderHeader();
      const a = activeArea(); if (a) { delete S.data[a.name]; loadArea(true); }
    };
  }

  /* ------------------------------------------------------------------- YOU */
  async function renderYou() {
    const el = $("#sec-you");
    let you = S.you;
    try { you = await api(`/api/me/summary?device=${encodeURIComponent(S.device)}`); S.you = you; } catch (e) {}
    const lb = await api("/api/leaderboard").catch(() => ({ areas: [], totals: {} }));
    const ch = await api(`/api/challenges?device=${encodeURIComponent(S.device)}`).catch(() => ({ challenges: [] }));
    const sv = (you && you.savings) || { total: 0, this_month: 0, entries: [] };
    const lv = (you && you.level) || { name: "Seedling", icon: "🌱", xp: 0, to_next: 120, progress: 0 };
    const sc = (you && you.score) || { score: 0, components: [] };

    el.innerHTML = `
      <div class="hero">
        <div class="row">
          <div style="font-size:44px">${lv.icon}</div>
          <div style="flex:1">
            <div class="tiny">${esc(you && you.you ? you.you.handle : "Neighbour")} · ${esc(t("level", "Level"))} ${lv.level}</div>
            <div class="big">${esc(lv.name)}</div>
            <div class="bar2 mt8" style="max-width:200px"><i style="width:${Math.round((lv.progress || 0) * 100)}%"></i></div>
            <div class="tiny mt8">${lv.xp} XP · ${lv.to_next} to next level ${you && you.you ? "· 🔥 " + (you.you.streak || 0) + " " + esc(t("streak", "day streak")) : ""}</div>
          </div>
          <div style="text-align:right"><div class="tiny">Ubuntu</div><div class="big num" style="font-size:24px">${(you && you.you ? you.you.ubuntu : 0) || 0}</div></div>
        </div>
      </div>

      <div class="card tight">
        <h2>🛡️ ${esc(t("score", "Resilience"))} ${sc.score}<span class="spacer"></span><span class="badge">${esc(sc.band || "")}</span></h2>
        ${(sc.components || []).map(c => `<div class="mb8">
          <div class="between tiny"><span>${esc(c.label)}</span><span class="num">${c.value}/${c.max}</span></div>
          <div class="bar2"><i style="width:${Math.round(c.value / Math.max(1, c.max) * 100)}%"></i></div>
          <div class="tiny">${esc(c.detail || "")}</div></div>`).join("")}
        <button class="btn wide sm mt8" data-goto="prepare">${esc("Improve my score")} →</button>
      </div>

      <div class="card tight">
        <h2>🎯 ${esc("This week")}</h2>
        ${(ch.challenges || []).map(c => `<div class="task">
          <div class="tick ${c.done ? "on" : ""}" data-ch="${c.id}">✓</div>
          <div style="flex:1"><div class="tt">${c.icon} ${esc(c.title)}</div><div class="td">${esc(c.detail)}</div></div>
          <span class="xp">+${c.xp}</span></div>`).join("")}
      </div>

      <div class="card tight">
        <h2>🏅 ${esc(t("badges", "Badges"))}</h2>
        <div class="badgegrid">${((you && you.badges) || []).slice(0, 12).map(b =>
        `<div class="bcell ${b.earned ? "" : "off"}" title="${esc(b.how || "")}"><div class="bi">${b.icon}</div><div class="bn">${esc(b.name)}</div></div>`).join("")}</div>
      </div>

      <div class="card tight">
        <h2>💸 ${esc(t("savings", "Saved"))} <span class="spacer"></span><span class="xp">${rand(sv.this_month, 0)} this month</span></h2>
        <div class="big num">${rand(sv.total, 0)}</div>
        <div class="muted">${esc("logged savings since you joined")}</div>
        <div class="grid2 mt8">
          ${[["water", "🚰 Borehole / rain"], ["power", "⚡ Load shifting"], ["food", "🥫 Bulk buy"], ["other", "🤝 Shared"]].map(([k, lb]) =>
          `<button class="btn sm" data-sav="${k}">${esc(lb)}</button>`).join("")}
        </div>
        ${(sv.entries || []).slice(0, 5).map(e => `<div class="kv"><span>${esc(e.kind)} · ${esc(e.note || "")}</span><b>${rand(e.amount, 0)}</b></div>`).join("")}
      </div>

      <div class="card tight">
        <h2>🏆 ${esc(t("leaderboard", "Top areas"))}</h2>
        ${(lb.areas || []).slice(0, 8).map((x, i) => `<div class="prow">
          <div class="pdot">${i < 3 ? ["🥇", "🥈", "🥉"][i] : "📍"}</div>
          <div style="flex:1"><div class="t">${esc(x.area)}</div><div class="tiny">${x.members} neighbours</div></div>
          <div class="num">${x.xp} XP</div></div>`).join("") || `<div class="empty" style="padding:12px">${esc("Be the first in your area.")}</div>`}
        <div class="tiny mt8">${esc("Community totals:")} ${(lb.totals || {}).xp || 0} XP · ${(lb.totals || {}).ubuntu || 0} Ubuntu Points</div>
      </div>

      <div class="card tight">
        <h2>⚙️ ${esc(t("settings", "Settings"))}</h2>
        <label class="fl">${esc(t("language", "Language"))}</label>
        <select id="langSel">${[["en", "English"], ["zu", "isiZulu"], ["xh", "isiXhosa"], ["st", "Sesotho"], ["af", "Afrikaans"]]
        .map(([c, n]) => `<option value="${c}" ${S.lang === c ? "selected" : ""}>${n}</option>`).join("")}</select>
        <div class="grid2 mt8">
          <button class="btn sm ${S.theme === "light" ? "cyan" : "ghost"}" id="themeBtn">🌓 ${esc("Light / dark")}</button>
          <button class="btn sm ${S.settings.dataSaver ? "cyan" : "ghost"}" id="dataBtn">📉 ${esc(t("lowData", "Data saver"))}</button>
          <button class="btn sm" id="pushBtn">🔔 ${esc("Alerts")}</button>
          <button class="btn sm" id="installBtn">📲 ${esc(t("install", "Install app"))}</button>
        </div>
        <div class="grid2 mt8">
          <button class="btn sm ghost" id="waBtn">💬 ${esc(t("whatsapp", "WhatsApp"))}</button>
          <button class="btn sm ghost" id="ussdBtn">📟 USSD</button>
        </div>
        <div class="tiny mt8">${esc("ServiceWaze v3 · no login, no tracking, POPIA-friendly. Data shown with its source.")}</div>
      </div>
      ${a11yControls()}`;

    $$("[data-goto]").forEach(b => b.onclick = () => go(b.dataset.goto));
    $$("[data-ch]").forEach(b => b.onclick = async () => {
      await post("/api/challenges/complete", { device: S.device, id: b.dataset.ch });
      toast("Challenge done 🎉"); renderYou();
    });
    $$("[data-sav]").forEach(b => b.onclick = async () => {
      const amt = parseFloat(prompt("How much did you save (R)?", "50") || "0") || 0;
      if (amt <= 0) return;
      await post("/api/me/savings", { device: S.device, kind: b.dataset.sav, amount: amt, note: "logged in app" });
      toast("Saved " + rand(amt)); renderYou();
    });
    $("#langSel").onchange = async (e) => { await loadI18n(e.target.value); render(); renderHeader(); renderAreas(); };
    $("#themeBtn").onclick = () => { S.theme = S.theme === "dark" ? "light" : "dark"; applyTheme(); renderYou(); };
    $("#dataBtn").onclick = () => { S.settings.dataSaver = !S.settings.dataSaver; saveSettings(); renderYou(); };
    $("#pushBtn").onclick = enablePush;
    $("#installBtn").onclick = installApp;
    $("#waBtn").onclick = () => {
      const n = prompt("Your WhatsApp number (e.g. 0821234567):", "");
      if (!n) return;
      post("/api/whatsapp/optin", { phone: n, area: (activeArea() || {}).name || "" })
        .then(() => toast("Opted in — outbox mode until a provider is configured"));
    };
    $("#ussdBtn").onclick = async () => {
      const j = await api("/api/ussd?session=web&input=");
      alert(j.text + "\n\n(Feature-phone channel: the same logic runs on *134*xxxx#)");
    };
    wireA11y();
  }

  function saveSettings() { localStorage.setItem(LS.set, JSON.stringify(S.settings)); }
  function applyTheme() { document.documentElement.setAttribute("data-theme", S.theme); localStorage.setItem(LS.theme, S.theme); }

  async function enablePush() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return toast("Push not supported here");
    try {
      const reg = await navigator.serviceWorker.ready;
      const vapid = await api("/api/push/vapid");
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlB64(vapid.public_key),
      });
      await post("/api/push/subscribe", { endpoint: sub.endpoint, keys: sub.toJSON().keys, area: (activeArea() || {}).name || "" });
      S.settings.notify = true; saveSettings();
      toast("Alerts on — you'll be warned before impact");
    } catch (e) { toast("Push blocked by the browser"); }
  }
  function urlB64(base64String) {
    const padding = "=".repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(base64); const arr = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; ++i) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  let deferredPrompt = null;
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferredPrompt = e; });
  function installApp() {
    if (deferredPrompt) { deferredPrompt.prompt(); deferredPrompt = null; }
    else toast("Use your browser menu → 'Add to Home screen' / 'Install app'");
  }

  /* --------------------------------------------------------------- report */
  function openReport() {
    const a = activeArea();
    const kinds = [["no_water", "🚫💧 No water"], ["low_pressure", "🚰 Low pressure"], ["leak", "💦 Leak / burst"],
    ["power_out", "⚡ Power out"], ["route", "🚌 Route disrupted"], ["restored", "✅ Restored"], ["other", "❓ Other"]];
    const sheet = $("#sheet");
    sheet.innerHTML = `<div class="grab"></div><h3>📣 ${esc(t("report", "Report"))}</h3>
      <p class="muted" style="margin:0 0 8px">${esc("You'll get a tracked receipt with an SLA clock and the responsible entity.")}</p>
      <label class="fl">Area</label><input id="rArea" value="${esc(a ? a.name.split(",")[0] : "")}">
      <div class="grid3 mt8" id="kinds">${kinds.map(([k, lb], i) =>
      `<button class="btn sm ${i === 0 ? "cyan" : "ghost"}" data-k="${k}">${esc(lb)}</button>`).join("")}</div>
      <label class="fl">What's happening?</label><textarea id="rMsg" rows="2" placeholder="e.g. no water since 06:00, Zone 3"></textarea>
      <label class="fl">Photo (optional)</label><input type="file" id="rPhoto" accept="image/*">
      <div class="grid2 mt12"><button class="btn ghost" id="rCancel">${esc(t("cancel", "Cancel"))}</button>
      <button class="btn primary" id="rSend">${esc(t("send", "Send report"))}</button></div>`;
    $("#overlay").classList.add("on");
    let kind = "no_water";
    $$("#kinds button").forEach(b => b.onclick = () => {
      $$("#kinds button").forEach(x => { x.classList.remove("cyan"); x.classList.add("ghost"); });
      b.classList.add("cyan"); b.classList.remove("ghost"); kind = b.dataset.k;
    });
    $("#rCancel").onclick = closeSheet;
    $("#rSend").onclick = async () => {
      const file = $("#rPhoto").files[0];
      let photo = "";
      if (file && !S.settings.dataSaver) {
        photo = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(file); });
      }
      try {
        const r = await post("/api/report", {
          area: $("#rArea").value.trim(), kind, message: $("#rMsg").value.trim(),
          device: S.device, lat: a ? a.lat : null, lon: a ? a.lon : null, photo,
        });
        toast("Receipt " + r.receipt.ref + " issued — " + r.receipt.entity, 4200);
        vibrate([20, 40, 20]); closeSheet();
        S.receipts = (await api(`/api/receipts?area=${encodeURIComponent($("#rArea").value.trim())}`)).receipts || [];
        if (S.tab === "community") renderReceipts();
      } catch (e) { toast("Could not send"); }
    };
  }

  function closeSheet() { $("#overlay").classList.remove("on"); }

  /* ----------------------------------------------------------------- add */
  function openAdd() {
    const sheet = $("#sheet");
    sheet.innerHTML = `<div class="grab"></div><h3>📍 ${esc("Add an area")}</h3>
      <input id="addQ" placeholder="${esc("Search suburb or town…")}" autocomplete="off">
      <button class="btn wide mt8" id="addGeo">📍 ${esc("Use my location")}</button>
      <div id="addSuggest" class="mt8"></div>
      <div class="tiny mt8">${esc("Add home, work, your child's school and your parents' area.")}</div>`;
    $("#overlay").classList.add("on");
    const inp = $("#addQ"), box = $("#addSuggest");
    let timer;
    inp.oninput = () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const q = inp.value.trim(); if (q.length < 2) return;
        const j = await api("/api/areas?q=" + encodeURIComponent(q));
        box.innerHTML = (j.results || []).map(r =>
          `<button class="btn wide sm mb8" data-add="${esc(r.name)}, ${esc(r.admin1 || "")}" data-lat="${r.lat}" data-lon="${r.lon}">${esc(r.name)}, ${esc(r.admin1 || "")}</button>`).join("")
          || `<div class="muted">No match — try another spelling.</div>`;
        $$("[data-add]").forEach(b => b.onclick = () => pickArea(b.dataset.add, +b.dataset.lat, +b.dataset.lon));
      }, 260);
    };
    $("#addGeo").onclick = () => {
      if (!navigator.geolocation) return toast("No GPS here");
      toast("Locating…");
      navigator.geolocation.getCurrentPosition(async (p) => {
        const lat = +p.coords.latitude.toFixed(5), lon = +p.coords.longitude.toFixed(5);
        const j = await api(`/api/reverse?lat=${lat}&lon=${lon}`);
        const nm = (j.place && j.place.display) || "My location";
        pickArea(nm, lat, lon);
      }, () => toast("Location denied"), { timeout: 9000 });
    };
    setTimeout(() => inp.focus(), 200);
  }
  function pickArea(name, lat, lon) {
    if (!S.areas.some(a => a.name === name)) {
      S.areas.push({ name, lat, lon });
      S.active = S.areas.length - 1;
    } else S.active = S.areas.findIndex(a => a.name === name);
    saveAreas(); closeSheet(); renderAreas(); loadArea(true);
  }

  /* ---------------------------------------------------------------- intro */
  function showIntro() {
    if (localStorage.getItem(LS.installed)) return;
    const sheet = $("#sheet");
    const steps = [
      ["👋", "Know it's coming", "ServiceWaze watches water, power, weather, routes and food prices for your street — and tells you how long you have before it hits."],
      ["⏳", "Prepare in time", "You get a task list sized to the time left and your household. Do it, tap done, earn XP."],
      ["🤝", "Share what you have", "Offer water, power, a fridge shelf or a seat. Neighbours claim it. That's Ubuntu Points — and real savings."],
    ];
    let i = 0;
    const draw = () => {
      const [ic, h, p] = steps[i];
      sheet.innerHTML = `<div class="grab"></div>
        <div style="font-size:40px;text-align:center">${ic}</div>
        <h3 class="center">${esc(h)}</h3>
        <p class="muted center">${esc(p)}</p>
        <button class="btn primary wide mt12" id="introGo">${i < steps.length - 1 ? "Next" : "Start — it's free"}</button>
        <button class="btn ghost wide mt8" id="introSkip">Skip</button>`;
      $("#introGo").onclick = () => {
        if (i < steps.length - 1) { i++; draw(); } else { localStorage.setItem(LS.installed, "1"); closeSheet(); openAdd(); }
      };
      $("#introSkip").onclick = () => { localStorage.setItem(LS.installed, "1"); closeSheet(); };
    };
    draw();
    $("#overlay").classList.add("on");
  }

  /* --------------------------------------------------------------- router */
  function go(tab) {
    S.tab = tab;
    $$("#nav button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
    $$(".section").forEach(s => s.classList.toggle("on", s.id === "sec-" + tab));
    window.scrollTo({ top: 0, behavior: "smooth" });
    render();
  }

  function render() {
    renderHeader();
    if (S.tab === "now") renderNow();
    else if (S.tab === "prepare") renderPrepare();
    else if (S.tab === "grid") renderGrid();
    else if (S.tab === "community") renderCommunity();
    else if (S.tab === "you") renderYou();
  }

  /* ----------------------------------------------------------------- boot */
  async function boot() {
    applyTheme();
    await loadI18n(S.lang);
    renderAreas(); renderHeader();
    $$("#nav button").forEach(b => b.onclick = () => go(b.dataset.tab));
    $("#fab").onclick = openReport;
    $("#overlay").onclick = (e) => { if (e.target.id === "overlay") closeSheet(); };
    $("#langBtn").onclick = async () => {
      const order = ["en", "zu", "xh", "st", "af"];
      const next = order[(order.indexOf(S.lang) + 1) % order.length];
      await loadI18n(next); render(); renderAreas(); renderHeader();
    };
    $("#themeBtnTop").onclick = () => { S.theme = S.theme === "dark" ? "light" : "dark"; applyTheme(); render(); };

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
    loadQueue();
    applyA11y();
    window.addEventListener("online", () => {
      renderHeader(); flushQueue(); loadArea(true);
    });
    // the service worker can wake us to drain the queue even when hidden
    if (navigator.serviceWorker && typeof navigator.serviceWorker.addEventListener === "function") {
      navigator.serviceWorker.addEventListener("message", (ev) => {
        if (ev.data && ev.data.type === "flush-queue") flushQueue();
      });
    }
    window.addEventListener("offline", renderHeader);

    if (!S.areas.length) {
      S.areas.push({ name: "Soweto, Gauteng", lat: -26.2485, lon: 27.8546 });
      saveAreas();
    }
    renderAreas();
    await loadArea(true);
    loadExtras();
    setTimeout(showIntro, 900);
    setInterval(() => { const a = activeArea(); if (a) { S.data[a.name] = null; loadArea(true); } }, 5 * 60 * 1000);
  }


  /* ==================================================================== MAP
     "Waze for services" without a map is not Waze. Leaflet is lazy-loaded
     from a CDN and the tab degrades to a list when tiles are unavailable
     (offline, data-saver, blocked network) — everything else still works. */
  let _leaflet = null;
  function loadLeaflet() {
    if (_leaflet) return _leaflet;
    _leaflet = new Promise((res, rej) => {
      if (window.L) return res(window.L);
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(css);
      const sc = document.createElement("script");
      sc.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      sc.onload = () => res(window.L);
      sc.onerror = rej;
      document.head.appendChild(sc);
    });
    return _leaflet;
  }

  function mapPins(a) {
    const pins = [];
    (S.grid.offers || []).forEach((o) => pins.push({ lat: o.lat, lon: o.lon, icon: "🙌",
      title: o.title, sub: o.availability ? o.availability : "offered", kind: "offer" }));
    (S.grid.needs || []).forEach((o) => pins.push({ lat: o.lat, lon: o.lon, icon: "🆘",
      title: o.title, sub: "needed", kind: "need" }));
    Object.values(S.grid.points || {}).forEach((arr) => arr.forEach((p) =>
      pins.push({ lat: p.lat, lon: p.lon, icon: p.kind === "water" ? "🚰" : p.kind === "food" ? "🥫" : "🏥",
        title: p.name, sub: p.distance_m + " m", kind: "point" })));
    (S.grid.businesses || []).forEach((b) => pins.push({ lat: b.lat, lon: b.lon, icon: b.icon || "🏪",
      title: b.name, sub: b.contact || b.area || "", kind: "business" }));
    (S.receipts || []).slice(0, 12).forEach((r) => pins.push({ lat: r.lat, lon: r.lon, icon: "🧾",
      title: r.kind.replace(/_/g, " ") + " · " + r.area, sub: r.state, kind: "receipt" }));
    return pins.filter((p) => p.lat != null && p.lon != null);
  }

  function renderMapList(a) {
    const box = $("#mapList"); if (!box) return;
    const pins = mapPins(a).slice(0, 20);
    box.innerHTML = pins.length ? pins.map((p) => `<div class="prow">
      <div class="pdot">${p.icon}</div>
      <div style="flex:1"><div class="t">${esc(p.title)}</div><div class="tiny">${esc(p.sub || "")}</div></div>
      <a class="btn sm ghost" target="_blank" rel="noopener"
         href="https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=18/${p.lat}/${p.lon}">Map</a>
    </div>`).join("") : `<div class="empty" style="padding:14px"><span class="e">📍</span>${esc("Nothing with a location yet — add your street to the Grid.")}</div>`;
  }

  async function renderMap() {
    const host = $("#gridBody");
    const a = activeArea();
    host.innerHTML = `<div class="card tight">
      <h2>🗺️ ${esc(a ? a.name : "Live map")}</h2>
      <div id="mapdiv" style="height:320px;border-radius:14px;overflow:hidden;background:var(--card2);border:1px solid var(--line)"></div>
      <div class="tiny mt8" id="mapNote">${esc("Red = reported fault · 🙌 offer · 🆘 request · 🚰 water point · 🏪 business")}</div></div>
      <div class="card tight"><h2>📍 ${esc("On your street")}</h2><div id="mapList"><div class="skeleton"></div></div></div>`;
    if (!a || a.lat == null) {
      $("#mapNote").textContent = "Add an area with a location to see the map.";
      $("#mapList").innerHTML = `<div class="empty" style="padding:12px">No location.</div>`;
      return;
    }
    if (S.settings.dataSaver) {
      $("#mapNote").textContent = "Data saver is on — the map is switched off to save your data.";
      return renderMapList(a);
    }
    let L = null;
    try { L = await loadLeaflet(); } catch (e) { L = null; }
    if (!L) {
      $("#mapNote").textContent = "Map tiles are unavailable right now (offline or blocked). Everything below still works.";
      return renderMapList(a);
    }
    try {
      const map = L.map("mapdiv", { zoomControl: false, attributionControl: false }).setView([a.lat, a.lon], 13);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18 }).addTo(map);
      L.control.zoom({ position: "bottomright" }).addTo(map);
      const divIcon = (emoji) => L.divIcon({
        html: `<div style="font-size:17px;background:var(--card);border:1px solid var(--line);
                 border-radius:10px;width:30px;height:30px;display:grid;place-items:center;
                 box-shadow:0 2px 8px rgba(0,0,0,.3)">${emoji}</div>`,
        className: "", iconSize: [30, 30], iconAnchor: [15, 15],
      });
      const pins = mapPins(a);
      pins.forEach((p) => {
        L.marker([p.lat, p.lon], { icon: divIcon(p.icon) })
          .addTo(map)
          .bindPopup(`<b>${esc(p.title)}</b><br>${esc(p.sub || "")}`);
      });
      if (pins.length) {
        const b = L.latLngBounds(pins.map((p) => [p.lat, p.lon]));
        b.extend([a.lat, a.lon]);
        map.fitBounds(b.pad(0.25));
      }
      $("#mapNote").textContent = `${pins.length} places on the map around ${a.name}.`;
    } catch (e) {
      $("#mapNote").textContent = "Map failed to load — list below still works.";
    }
    renderMapList(a);
  }

  /* =============================================================== BUSINESS
     Climate-smart small business: the trades that keep a township running,
     plus the "we're open on the generator" board — which is food access for
     residents and footfall for the business, in one tap. */
  async function renderBusiness() {
    const host = $("#gridBody");
    const a = activeArea();
    const area = a ? a.name.split(",")[0] : "";
    host.innerHTML = `<div class="card"><div class="skeleton"></div></div>`;
    try {
      const [board, biz] = await Promise.all([
        api(`/api/business/board?area=${encodeURIComponent(area)}`),
        api(`/api/business?area=${encodeURIComponent(area)}`),
      ]);
      S.grid.businesses = biz.businesses || [];
      const openNow = board.open || [], closed = board.closed || [];
      host.innerHTML = `
        <div class="card tight">
          <h2>🏪 ${esc("Open right now")} <span class="spacer"></span>
            <span class="badge">${openNow.length} open</span></h2>
          <div class="grid2 mb8">
            <button class="btn primary sm" id="postOpen">✅ ${esc("We're open")}</button>
            <button class="btn sm ghost" id="postClosed">⛔ ${esc("Had to close")}</button>
          </div>
          ${openNow.length ? openNow.map((b) => `<div class="item">
            <div class="between"><span class="t">🟢 ${esc(b.name)}</span><span class="tiny">${timeAgo(b.created)}</span></div>
            <div class="b">${esc(b.note || "")}</div></div>`).join("")
          : `<div class="empty" style="padding:12px">${esc("Nobody has posted yet. Spaza with a generator? Tell the street.")}</div>`}
          ${closed.length ? `<div class="mt8">${closed.map((b) => `<div class="item">
            <div class="between"><span class="t">⛔ ${esc(b.name)}</span><span class="tiny">${timeAgo(b.created)}</span></div>
            <div class="b">${esc(b.note || "")}</div></div>`).join("")}</div>` : ""}
          <div class="tiny mt8">${esc("Posts expire after " + (board.ttl_hours || 24) + " hours so the board never lies.")}</div>
        </div>

        <div class="card tight">
          <h2>🧰 ${esc("Resilience providers")} <span class="spacer"></span>
            <button class="btn sm ghost" id="addBiz">＋ ${esc(t("add", "Add"))}</button></h2>
          ${(biz.businesses || []).length ? biz.businesses.map((b) => `<div class="item">
            <div class="between"><span class="t">${b.icon} ${esc(b.name)}
              ${b.verified ? `<span class="badge official">${b.verified} ✓ verified</span>` : ""}</span>
              <button class="btn sm ghost" data-verify="${b.id}">👍 ${esc("Vouch")}</button></div>
            <div class="b">${esc(b.detail || "")}</div>
            <div class="tiny mt8">${esc(b.area || "")} ${b.contact ? "· " + esc(b.contact) : ""}</div>
          </div>`).join("")
          : `<div class="empty" style="padding:12px"><span class="e">🧰</span>${esc("No providers listed yet. Add the plumber who actually shows up.")}</div>`}
        </div>

        <div class="card tight">
          <h2>📋 ${esc("Business continuity")}</h2>
          ${(biz.checklist && biz.checklist.steps || []).map((st, i) => `<div class="task">
            <div class="tick" data-bc="${i}">✓</div>
            <div style="flex:1"><div class="tt">${i + 1}. ${esc(st)}</div></div></div>`).join("")}
        </div>`;
      $("#postOpen").onclick = () => postOpenStatus("open");
      $("#postClosed").onclick = () => postOpenStatus("closed");
      $("#addBiz").onclick = openBusinessForm;
      $$("[data-verify]").forEach((b) => b.onclick = async () => {
        const r = await post("/api/business/verify", { device: S.device, id: +b.dataset.verify });
        toast("Vouched — " + r.verified + " neighbours trust this business 🤝");
        renderBusiness();
      });
      $$("[data-bc]").forEach((b) => b.onclick = () => {
        b.classList.toggle("on");
        if (b.classList.contains("on")) {
          post("/api/me/action", { device: S.device, action: "drill", meta: "business-continuity" });
          toast("+45 XP — continuity step done");
        }
      });
    } catch (e) {
      host.innerHTML = `<div class="card"><div class="empty">Could not load the business board.</div></div>`;
    }
  }

  function postOpenStatus(status) {
    const sheet = $("#sheet");
    sheet.innerHTML = `<div class="grab"></div>
      <h3>${status === "open" ? "✅ We're open" : "⛔ Had to close"}</h3>
      <p class="muted" style="margin:0 0 8px">${esc(status === "open"
        ? "Tell neighbours you're trading — generator, gas, stock, hours."
        : "Let customers know why, so they don't walk.")}</p>
      <label class="fl">Business name</label><input id="obName" placeholder="e.g. Mama's Spaza" maxlength="60">
      <label class="fl">Note</label><input id="obNote" placeholder="${status === "open" ? "e.g. generator on until 21:00, cold drinks" : "e.g. no water for cooking, back tomorrow"}" maxlength="120">
      <div class="grid2 mt12"><button class="btn ghost" id="obCancel">${esc(t("cancel", "Cancel"))}</button>
      <button class="btn primary" id="obSend">${esc(t("send", "Post"))}</button></div>`;
    $("#overlay").classList.add("on");
    $("#obCancel").onclick = closeSheet;
    $("#obSend").onclick = async () => {
      const name = $("#obName").value.trim();
      if (name.length < 2) return toast("Add the business name");
      const a = activeArea();
      await post("/api/business/open", { device: S.device, name, status,
        note: $("#obNote").value.trim(), area: a ? a.name.split(",")[0] : "" });
      toast(status === "open" ? "Posted — customers can find you 🏪" : "Posted — thanks for telling the street");
      closeSheet(); renderBusiness();
    };
  }

  function openBusinessForm() {
    const sheet = $("#sheet");
    const cats = { water: "🛢️ Water: tanks, boreholes, delivery", solar: "☀️ Solar & batteries",
      gas: "🔥 Gas & stoves", plumbing: "🔧 Plumbing & leaks", electrical: "⚡ Electrical",
      food: "🥫 Food", cold: "🧊 Cold storage & ice", transport: "🚐 Transport & delivery", other: "🏪 Other" };
    sheet.innerHTML = `<div class="grab"></div><h3>🧰 ${esc("Add a resilience provider")}</h3>
      <p class="muted" style="margin:0 0 8px">${esc("The trades and shops that keep your street running during a disruption.")}</p>
      <label class="fl">Name</label><input id="bzName" placeholder="e.g. Sipho's Plumbing" maxlength="60">
      <label class="fl">Category</label><select id="bzCat">
        ${Object.entries(cats).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
      <label class="fl">Contact (phone or WhatsApp)</label><input id="bzContact" placeholder="082 000 0000">
      <label class="fl">What do they do?</label><textarea id="bzDetail" rows="2" placeholder="e.g. fixes burst pipes, 24h, Soweto only"></textarea>
      <div class="grid2 mt12"><button class="btn ghost" id="bzCancel">${esc(t("cancel", "Cancel"))}</button>
      <button class="btn primary" id="bzSend">${esc(t("add", "Add"))}</button></div>`;
    $("#overlay").classList.add("on");
    $("#bzCancel").onclick = closeSheet;
    $("#bzSend").onclick = async () => {
      const name = $("#bzName").value.trim();
      if (name.length < 3) return toast("Add a name");
      const a = activeArea();
      await post("/api/business/add", { device: S.device, name, category: $("#bzCat").value,
        area: a ? a.name.split(",")[0] : "", contact: $("#bzContact").value.trim(),
        detail: $("#bzDetail").value.trim(), lat: a ? a.lat : null, lon: a ? a.lon : null });
      toast("Listed — neighbours can vouch for them");
      closeSheet(); renderBusiness();
    };
  }

  /* ============================================================== FORECAST
     The model shows its work: probability, the drivers behind it, how many
     events it learned from, and how accurate it has been here before. Then it
     asks the street whether it was right — that answer trains it. */
  async function renderInsights() {
    const box = $("#insightBox"); if (!box) return;
    const a = activeArea(); if (!a) return;
    const area = a.name.split(",")[0];
    box.innerHTML = `<div class="skeleton"></div>`;
    try {
      const [fc, hist] = await Promise.all([
        api(`/api/insights/forecast?area=${encodeURIComponent(area)}&horizon_h=24`),
        api(`/api/insights/history?area=${encodeURIComponent(area)}`),
      ]);
      S.forecast = fc;
      const rows = Object.values(fc.forecasts || {});
      box.innerHTML = `
        <div class="tiny mb8">${esc("Next 24 hours — modelled from " + (hist.total_events || 0) +
          " events in this area over " + (hist.window_days || 120) + " days.")}</div>
        ${rows.map((f) => {
          const pct = Math.round(f.prob * 100);
          const cls = f.prob >= 0.6 ? "b-bad" : f.prob >= 0.3 ? "b-warn" : "b-ok";
          return `<div class="mb8">
            <div class="between"><span class="t">${f.icon} ${esc(f.label)}</span>
              <span class="num"><b>${pct}%</b> · ${esc(f.band)}</span></div>
            <div class="bar2"><i class="${cls}" style="width:${pct}%"></i></div>
            <div class="tiny">${esc((f.drivers || []).map((d) => d.label).join(" · ") || "no signal yet")}</div>
            <div class="tiny">${esc("sample " + f.sample + " · calibration " + (f.calibration && f.calibration.n >= 3
              ? f.calibration.n + " verified, Brier " + f.calibration.brier : "not yet calibrated"))}</div>
            <div class="grid2 mt8">
              <button class="btn sm ghost" data-out="1" data-svc="${f.service}">${esc("Yes, it happened")}</button>
              <button class="btn sm ghost" data-out="0" data-svc="${f.service}">${esc("Nothing happened")}</button>
            </div>
          </div>`;
        }).join("")}
        <div class="mt8">${Object.values(hist.services || {}).map((sv) => `<div class="kv">
          <span>${sv.icon} ${esc(sv.label)}</span>
          <b>${sv.events} events${sv.median_hours_to_fix != null ? " · " + Math.round(sv.median_hours_to_fix) + "h to fix" : ""}</b></div>`).join("")}</div>
        <div class="tiny mt8">${esc("Every answer above trains the model for your street. That is the part nobody else has.")}</div>`;
      $$("[data-out]").forEach((b) => b.onclick = async () => {
        const r = await post("/api/insights/outcome", {
          area, service: b.dataset.svc, happened: b.dataset.out === "1" });
        toast(r.matched ? "Logged — the model just learned something 🙏" : "Logged for the next forecast");
        renderInsights();
      });
    } catch (e) {
      box.innerHTML = `<div class="muted">Forecast unavailable.</div>`;
    }
  }

  /* ============================================================== SCHEDULE
     7-day grid plus the heads-up that status apps are loved for: a warning
     60 and 15 minutes BEFORE the lights go. */
  async function renderSchedule() {
    const box = $("#schedBox"); if (!box) return;
    const a = activeArea(); if (!a) return;
    box.innerHTML = `<div class="skeleton"></div>`;
    try {
      const j = await api(`/api/electricity/schedule?q=${encodeURIComponent(a.name)}` +
        (a.lat != null ? `&lat=${a.lat}&lon=${a.lon}` : ""));
      const sch = j.schedule; S.scheduleCache = sch;
      if (!sch || !sch.upcoming || !sch.upcoming.length) {
        box.innerHTML = `<div class="muted">${esc(j.hint || "No published schedule for this area.")}
          <div class="mt8"><a class="btn sm ghost" target="_blank" rel="noopener"
          href="https://loadshedding.eskom.co.za">Official Eskom schedule</a></div></div>`;
        return;
      }
      const days = {};
      sch.upcoming.forEach((w) => {
        const d = new Date(w.start);
        const key = d.toDateString().slice(0, 10);
        (days[key] = days[key] || []).push({
          start: d, end: new Date(w.end), stage: w.stage,
        });
      });
      const next = sch.upcoming[0];
      const mins = Math.round((new Date(next.start) - Date.now()) / 60000);
      box.innerHTML = `
        <div class="between">
          <div><div class="tiny">${esc("Next switch-off")}</div>
            <div class="countdown"><b class="num">${fmtMin(mins)}</b></div></div>
          <div style="text-align:right"><div class="tiny">${esc(sch.estimated ? "estimated from stage pattern" : "from your area schedule")}</div>
            <span class="badge ${sch.estimated ? "sim" : "official"}">${esc(sch.area || a.name)}</span></div>
        </div>
        <div class="grid2 mt8">
          <button class="btn sm ${S.settings.heads60 ? "cyan" : "ghost"}" id="h60">⏰ 60 min heads-up</button>
          <button class="btn sm ${S.settings.heads15 ? "cyan" : "ghost"}" id="h15">⚡ 15 min heads-up</button>
        </div>
        <div class="scrollx mt8">${Object.entries(days).map(([day, ws]) =>
        `<div class="tile" style="min-width:96px"><span class="lb">${esc(day)}</span>
          ${ws.map((w) => `<div class="vl num" style="font-size:12px">${w.start.toTimeString().slice(0, 5)}–${w.end.toTimeString().slice(0, 5)}</div>`).join("")}
        </div>`).join("")}</div>`;
      $("#h60").onclick = () => { S.settings.heads60 = !S.settings.heads60; saveSettings(); renderSchedule(); scheduleHeadsUps(); };
      $("#h15").onclick = () => { S.settings.heads15 = !S.settings.heads15; saveSettings(); renderSchedule(); scheduleHeadsUps(); };
      scheduleHeadsUps();
    } catch (e) {
      box.innerHTML = `<div class="muted">Schedule unavailable.</div>`;
    }
  }

  function scheduleHeadsUps() {
    const j = S.forecast; // unused guard
    const sch = S.scheduleCache;
    if (!sch || !sch.upcoming) return;
    const fired = JSON.parse(localStorage.getItem("sw_heads") || "{}");
    (sch.upcoming || []).forEach((w) => {
      const start = new Date(w.start).getTime();
      [[60, S.settings.heads60], [15, S.settings.heads15]].forEach(([lead, on]) => {
        if (!on) return;
        const key = w.start + "|" + lead;
        if (fired[key]) return;
        const at = start - lead * 60000 - Date.now();
        if (at <= 0 || at > 6 * 3600 * 1000) return;
        setTimeout(() => {
          fired[key] = Date.now();
          localStorage.setItem("sw_heads", JSON.stringify(fired));
          notify("⚡ Load-shedding in " + lead + " min",
            "Switch off sensitive appliances and charge devices now.");
        }, at);
      });
    });
  }

  function notify(title, body) {
    vibrate([60, 50, 60]);
    if (window.Notification && Notification.permission === "granted") {
      try { new Notification(title, { body }); } catch (e) {}
    }
    toast(title + " — " + body, 6000);
  }

  /* ======================================================== OFFLINE QUEUE
     In a township the network dies exactly when you need to report. Reports,
     offers and chat are queued on the device and sent the moment signal
     returns — the user never loses what they wrote. */
  async function post(path, body) {
    const payload = { path, body: body || {}, at: Date.now() };
    if (!navigator.onLine || S.offlineMode) {
      S.queue.push(payload);
      persistQueue();
      queueBadge();
      toast("Saved on your phone — it will send when you're back online");
      return { ok: true, queued: true };
    }
    try {
      const r = await api(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Device-Id": S.device },
        body: JSON.stringify(payload.body),
      });
      return r;
    } catch (e) {
      S.queue.push(payload);
      persistQueue();
      queueBadge();
      toast("Saved on your phone — it will send when you're back online");
      return { ok: true, queued: true };
    }
  }

  function persistQueue() {
    try { localStorage.setItem("sw_queue", JSON.stringify(S.queue.slice(0, 40))); } catch (e) {}
    queueBadge();
  }
  function loadQueue() {
    try { S.queue = JSON.parse(localStorage.getItem("sw_queue") || "[]"); } catch (e) { S.queue = []; }
    queueBadge();
  }
  function queueBadge() {
    const el = $("#qBadge");
    if (!el) return;
    const n = (S.queue || []).length;
    el.style.display = n ? "grid" : "none";
    el.textContent = n;
    el.setAttribute("aria-label", n + " reports waiting to send");
  }
  async function flushQueue() {
    if (!S.queue || !S.queue.length) return;
    let sent = 0;
    const remaining = [];
    for (const item of S.queue) {
      try {
        await api(item.path, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Device-Id": S.device },
          body: JSON.stringify(item.body),
        });
        sent++;
      } catch (e) {
        remaining.push(item);
      }
    }
    S.queue = remaining;
    persistQueue();
    if (sent) toast(sent + " queued item(s) sent ✅");
  }

  /* =================================================== INTERACTIVE ONBOARD
     People do not learn an app from three slides. They learn it by doing the
     three things that matter, once, and getting rewarded for it. */
  function showIntro() {
    if (localStorage.getItem(LS.installed)) return;
    const steps = [
      { icon: "📍", title: "Add your street",
        body: "ServiceWaze watches water, power, weather, routes and food prices for the place you actually live.",
        cta: "Add my area", act: () => { openAdd(); } },
      { icon: "⏳", title: "Do one preparation task",
        body: "This is the whole point: acting BEFORE the outage. Tap one task on the Prepare tab and watch your score move.",
        cta: "Show me the tasks", act: () => { go("prepare"); } },
      { icon: "🤝", title: "Offer one thing",
        body: "A litre, a plug, a seat, a check-in on a neighbour. The Grid is what turns information into survival.",
        cta: "Open the Grid", act: () => { go("grid"); } },
    ];
    let i = 0;
    const draw = () => {
      const st = steps[i];
      const sheet = $("#sheet");
      sheet.innerHTML = `<div class="grab"></div>
        <div style="font-size:38px;text-align:center">${st.icon}</div>
        <h3 class="center">${esc(st.title)}</h3>
        <p class="muted center">${esc(st.body)}</p>
        <div class="center tiny mb8">${i + 1} of ${steps.length} · ${esc("each step earns XP")}</div>
        <button class="btn primary wide mt8" id="introGo">${esc(st.cta)}</button>
        <button class="btn ghost wide mt8" id="introSkip">${esc("Skip — I'll explore myself")}</button>`;
      $("#overlay").classList.add("on");
      $("#introGo").onclick = async () => {
        try {
          await post("/api/me/action", { device: S.device, action: "checkin",
            meta: "onboarding-" + i, area: (activeArea() || {}).name });
        } catch (e) {}
        st.act();
        if (i < steps.length - 1) { i++; setTimeout(draw, 700); }
        else { localStorage.setItem(LS.installed, "1"); closeSheet(); toast("Welcome to ServiceWaze 🌍"); }
      };
      $("#introSkip").onclick = () => { localStorage.setItem(LS.installed, "1"); closeSheet(); };
    };
    draw();
  }


  /* ========================================================== ACCESSIBILITY
     Accessibility is not a checkbox. Text size, contrast, motion and target
     size are all adjustable from inside the app, and everything is announced. */
  function applyA11y() {
    const st = S.settings || {};
    const root = document.documentElement;
    root.setAttribute("data-text", st.textSize || "normal");
    root.setAttribute("data-contrast", st.contrast || "normal");
    root.setAttribute("data-motion", st.motion || "full");
  }

  function a11yControls() {
    const st = S.settings || {};
    return `
      <div class="card tight">
        <h2>♿ ${esc("Make it easier to use")}</h2>
        <div class="kv"><span>${esc("Text size")}</span>
          <span class="seg sm">${["normal", "large", "xl"].map((k) =>
            `<button class="segbtn ${st.textSize === k ? "on" : ""}" data-text="${k}">${
              k === "normal" ? "A" : k === "large" ? "A+" : "A++"}</button>`).join("")}</span></div>
        <div class="kv"><span>${esc("High contrast")}</span>
          <span class="switchbtn ${st.contrast === "high" ? "on" : ""}" data-contrast="high"><i></i></span></div>
        <div class="kv"><span>${esc("Reduce motion")}</span>
          <span class="switchbtn ${st.motion === "reduced" ? "on" : ""}" data-motion="reduced"><i></i></span></div>
        <div class="tiny mt8">${esc("Every screen is labelled for screen readers and every button is at least 44 px tall.")}</div>
      </div>`;
  }

  function wireA11y() {
    $$("[data-text]").forEach((b) => b.onclick = () => {
      S.settings.textSize = b.dataset.text; saveSettings(); applyA11y(); renderYou();
    });
    $$("[data-contrast]").forEach((b) => b.onclick = () => {
      S.settings.contrast = S.settings.contrast === "high" ? "normal" : "high";
      saveSettings(); applyA11y(); renderYou();
    });
    $$("[data-motion]").forEach((b) => b.onclick = () => {
      S.settings.motion = S.settings.motion === "reduced" ? "full" : "reduced";
      saveSettings(); applyA11y(); renderYou();
    });
  }


  /* ============================================================ WATCH CIRCLE
     "Is she okay?" — the loop no status app closes. You name the neighbours
     you look out for (pseudonyms only), say you are safe, and the street can
     see who has not been heard from so somebody knocks. */
  async function renderWatch() {
    const box = $("#watchBox"); if (!box) return;
    const a = activeArea(); if (!a) return;
    const area = a.name.split(",")[0];
    box.innerHTML = `<div class="skeleton"></div>`;
    try {
      const j = await api(`/api/watch?area=${encodeURIComponent(area)}&device=${encodeURIComponent(S.device)}`);
      const people = j.people || [];
      box.innerHTML = `
        <div class="grid2 mb8">
          <button class="btn primary sm" id="imSafe">✅ ${esc("I'm safe")}</button>
          <button class="btn sm ghost" id="addWatch">＋ ${esc("Watch someone")}</button>
        </div>
        ${people.length ? people.map((p) => `<div class="item">
          <div class="between"><span class="t">${p.icon} ${esc(p.handle)}</span>
            <span class="tiny">${p.hours_since != null ? Math.round(p.hours_since) + "h ago" : esc("no check-in yet")}</span></div>
          <div class="b">${esc(p.state_label)}${p.note ? " · " + esc(p.note) : ""}</div>
          <div class="grid2 mt8">
            <button class="btn sm ghost" data-check="${p.id}">👋 ${esc("I checked on them")}</button>
            <button class="btn sm ${p.state === "needs_help" ? "primary" : "ghost"}" data-help="${p.id}">🆘 ${esc("Needs help")}</button>
          </div></div>`).join("")
        : `<div class="empty" style="padding:12px"><span class="e">👀</span>${esc("Nobody is watching anyone here yet. Add one neighbour you check on.")}</div>`}
        <div class="tiny mt8">${esc(j.privacy || "")} ${esc("After " + (j.ttl_hours || 48) + "h quiet, they turn amber; after " + (j.urgent_hours || 72) + "h, the street is asked to knock.")}</div>`;
      $("#imSafe").onclick = async () => {
        const r = await post("/api/watch/im-safe", { device: S.device, area });
        toast("Marked safe — " + r.handle + " ✅");
        renderWatch();
      };
      $("#addWatch").onclick = () => {
        const sheet = $("#sheet");
        sheet.innerHTML = `<div class="grab"></div><h3>👀 ${esc("Who do you look out for?")}</h3>
          <p class="muted" style="margin:0 0 8px">${esc("Pseudonym only — never a real name, number or address.")}</p>
          <label class="fl">Neighbour</label><input id="wtHandle" placeholder="e.g. Gogo at no. 42" maxlength="40">
          <label class="fl">Note for the street</label><input id="wtNote" placeholder="e.g. uses a walking frame" maxlength="120">
          <div class="grid2 mt12"><button class="btn ghost" id="wtCancel">${esc(t("cancel", "Cancel"))}</button>
          <button class="btn primary" id="wtSend">${esc(t("add", "Add"))}</button></div>`;
        $("#overlay").classList.add("on");
        $("#wtCancel").onclick = closeSheet;
        $("#wtSend").onclick = async () => {
          const h = $("#wtHandle").value.trim();
          if (h.length < 2) return toast("Name them somehow");
          const r = await post("/api/watch/add", { device: S.device, handle: h, area, note: $("#wtNote").value.trim() });
          toast(r.ok ? "Watching " + h + " 👀" : ("Could not add: " + r.error));
          closeSheet(); renderWatch();
        };
      };
      $$("[data-check]").forEach((b) => b.onclick = async () => {
        const r = await post("/api/watch/checkin", { device: S.device, id: +b.dataset.check });
        toast(r.ok ? "Checked on " + r.handle + " — +Ubuntu 🌍" : "Could not record that");
        renderWatch();
      });
      $$("[data-help]").forEach((b) => b.onclick = async () => {
        const r = await post("/api/watch/flag", { device: S.device, id: +b.dataset.help, state: "needs_help" });
        toast(r.ok ? "Flagged — the street will knock 🆘" : "Could not flag");
        renderWatch();
      });
    } catch (e) {
      box.innerHTML = `<div class="muted">Watch circle unavailable.</div>`;
    }
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
