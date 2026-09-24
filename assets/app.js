/* ServiceWaze static app. Works at / and at /ServiceWaze/ on GitHub Pages. */
(function () {
  "use strict";
  var E = window.SWEngine;
  var KEY = "servicewaze.v1";
  var TABS = [
    { id: "now", label: "Now", zu: "Manje", af: "Nou", xh: "Ngoku", st: "Jwale" },
    { id: "prepare", label: "Prepare", zu: "Lungiselela", af: "Berei", xh: "Lungiselela", st: "Itokisetse" },
    { id: "money", label: "Money", zu: "Imali", af: "Geld", xh: "Imali", st: "Chelete" },
    { id: "share", label: "Share", zu: "Yabelana", af: "Deel", xh: "Yabelana", st: "Arolelana" },
    { id: "you", label: "You", zu: "Wena", af: "Jy", xh: "Wena", st: "Wena" }
  ];
  var CRITICAL = {
    zu: "Ungawasebenzisi amanzi ompompi ukuze uphuze, upheke, noma uhlambe amazinyo.",
    af: "Moenie kraanwater drink, kook of tande borsel nie.",
    xh: "Ungawasebenzisi amanzi ompompi ukusela, ukupheka, nokuxukuxa.",
    st: "Se ke wa sebedisa metsi a pompo ho nwa, ho pheha kapa ho hlatswa meno."
  };

  var state = load();
  var paintQueued = false;
  var searchTimer = 0;
  var mapReady = false;

  function load() {
    var base = {
      saved: [],
      place: null,
      tab: "now",
      profile: {
        people: 4, storageL: 25, roofM2: 50, kwh: 450, kl: 15,
        units: "", dailyKwh: 10, fbe: false, tariff: "city_power", water: "johannesburg",
        customRate: 3.5, customFixed: 0, waterRate: 40, indigent: false, spend: "",
        kw: 3, systemCost: "", buyRand: 200, tariffTouched: false, waterTouched: false
      },
      checks: {},
      offers: [],
      needs: [],
      receipts: [],
      ledger: [],
      walk: null,
      watch: [],
      a11y: { theme: "dark", size: "md", contrast: false, simple: false, lang: "en" },
      live: { weather: "pending", air: "pending", eskom: "snapshot", radar: "snapshot", overpass: "idle" }
    };
    try {
      var raw = JSON.parse(localStorage.getItem(KEY) || "null");
      if (raw) {
        base.saved = raw.saved || [];
        base.place = raw.place || null;
        base.tab = raw.tab || "now";
        base.profile = Object.assign(base.profile, raw.profile || {});
        base.checks = raw.checks || {};
        base.offers = raw.offers || [];
        base.needs = raw.needs || [];
        base.receipts = raw.receipts || [];
        base.ledger = raw.ledger || [];
        base.walk = raw.walk || null;
        base.watch = raw.watch || [];
        base.a11y = Object.assign(base.a11y, raw.a11y || {});
      }
    } catch (e) {}
    base.snapshot = null;
    base.weather = null;
    base.air = null;
    base.radarPath = null;
    base.nearby = [];
    return base;
  }

  function save() {
    var copy = {
      saved: state.saved, place: state.place, tab: state.tab, profile: state.profile,
      checks: state.checks, offers: state.offers, needs: state.needs, receipts: state.receipts,
      ledger: state.ledger, walk: state.walk, watch: state.watch, a11y: state.a11y
    };
    try { localStorage.setItem(KEY, JSON.stringify(copy)); } catch (e) {}
    applyA11y();
  }

  function applyA11y() {
    var a = state.a11y;
    document.documentElement.dataset.theme = a.theme || "dark";
    document.documentElement.dataset.size = a.size || "md";
    if (a.contrast) document.documentElement.dataset.contrast = "1";
    else delete document.documentElement.dataset.contrast;
    document.documentElement.classList.toggle("simple", !!a.simple);
    document.documentElement.lang = a.lang === "en" ? "en" : a.lang;
  }

  function tabLabel(tab) {
    var lang = state.a11y.lang;
    return (lang !== "en" && tab[lang]) || tab.label;
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function safeUrl(u) {
    try {
      var x = new URL(u, location.href);
      if (x.protocol === "http:" || x.protocol === "https:") return esc(x.href);
    } catch (e) {}
    return "#";
  }

  function tel(n) {
    return "tel:" + String(n || "").replace(/[^\d+*#]/g, "");
  }

  function toast(msg) {
    var el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.add("on");
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { el.classList.remove("on"); }, 3200);
  }

  function haversine(aLat, aLon, bLat, bLon) {
    var R = 6371;
    var dLat = (bLat - aLat) * Math.PI / 180;
    var dLon = (bLon - aLon) * Math.PI / 180;
    var s = Math.sin(dLat / 2) ** 2 + Math.cos(aLat * Math.PI / 180) * Math.cos(bLat * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(s)));
  }

  function snap() { return state.snapshot || {}; }

  function weatherFor(place) {
    if (state.weather && state.weather.placeKey === placeKey(place)) return state.weather;
    var cities = (snap().weather_snapshot || {}).cities || {};
    var direct = cities[E.norm(place.name)];
    if (direct) return Object.assign({ tier: "snapshot", source: "Open-Meteo snapshot 24 Sep 2026 22:30 SAST" }, direct);
    var best = null, bestD = 1e9;
    Object.keys(cities).forEach(function (k) {
      var c = cities[k];
      if (place.lat == null) return;
      var d = haversine(place.lat, place.lon, c.lat, c.lon);
      if (d < bestD) { best = c; bestD = d; }
    });
    if (best && bestD < 60) return Object.assign({ tier: "snapshot", source: "Nearest scraped forecast (" + best.name + ", " + Math.round(bestD) + " km)" }, best);
    return null;
  }

  function airFor(place) {
    if (state.air && state.air.placeKey === placeKey(place)) return state.air;
    var cities = (snap().air_snapshot || {}).cities || {};
    var key = E.norm(place.name);
    var hit = cities[key];
    if (!hit && place.lat != null) {
      var map = { johannesburg: [-26.2, 28], "cape town": [-33.9, 18.4], durban: [-29.86, 31.02], pretoria: [-25.75, 28.23] };
      var best = null, bestD = 80;
      Object.keys(map).forEach(function (k) {
        var d = haversine(place.lat, place.lon, map[k][0], map[k][1]);
        if (d < bestD && cities[k]) { best = cities[k]; bestD = d; }
      });
      hit = best;
    }
    return hit ? Object.assign({ tier: "snapshot", source: "Open-Meteo air snapshot 24 Sep 2026 22:00 SAST" }, hit) : null;
  }

  function placeKey(p) { return p ? E.norm(p.name) + "@" + (p.lat || "") : ""; }

  function bundle(place) {
    var w = place ? weatherFor(place) : null;
    var air = place ? airFor(place) : null;
    return {
      daily: w && w.daily,
      source: w && w.source,
      air: air,
      current: w && w.current,
      tier: w && w.tier
    };
  }

  function setTab(id) {
    state.tab = id;
    if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
    save();
    render();
  }

  function setPlace(p) {
    if (!p || p.lat == null) return;
    state.place = {
      name: p.name, admin1: p.admin1 || "", admin2: p.admin2 || "",
      lat: Number(p.lat), lon: Number(p.lon), metro: p.metro || ""
    };
    state.saved = [state.place].concat(state.saved.filter(function (s) {
      return E.norm(s.name) !== E.norm(state.place.name);
    })).slice(0, 8);
    var tf = E.tariffForPlace(state.place);
    if (!state.profile.tariffTouched) state.profile.tariff = tf.elec;
    if (!state.profile.waterTouched) state.profile.water = tf.water;
    state.weather = null;
    state.air = null;
    state.nearby = [];
    save();
    render();
    refreshLive();
  }

  function knownPlace(name) {
    var n = E.norm(name);
    var list = (snap().places || []).concat(state.saved || []);
    for (var i = 0; i < list.length; i++) if (E.norm(list[i].name) === n) return list[i];
    return null;
  }

  function loadJSON(url, ms) {
    if (typeof fetch === "function") {
      var ctrl = new AbortController();
      var t = setTimeout(function () { ctrl.abort(); }, ms || 8000);
      return fetch(url, { signal: ctrl.signal }).then(function (res) {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      }).finally(function () { clearTimeout(t); });
    }
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open("GET", url);
      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch (e) { reject(e); }
        } else reject(new Error(String(xhr.status)));
      };
      xhr.onerror = function () { reject(new Error("network")); };
      xhr.send();
    });
  }

  async function getJSON(url, ms) {
    return loadJSON(url, ms);
  }

  function parseWeather(j) {
    var cur = j.current || {};
    var d = j.daily || {};
    var daily = (d.time || []).map(function (day, i) {
      return {
        date: String(day).slice(5),
        code: d.weather_code[i],
        tmax: d.temperature_2m_max[i],
        tmin: d.temperature_2m_min[i],
        precip_prob: d.precipitation_probability_max[i],
        precip_sum: d.precipitation_sum[i],
        gusts: d.wind_gusts_10m_max[i],
        uv: d.uv_index_max[i],
        radiation: d.shortwave_radiation_sum[i]
      };
    });
    return {
      current: {
        temp: cur.temperature_2m, feels: cur.apparent_temperature,
        humidity: cur.relative_humidity_2m, wind: cur.wind_speed_10m, code: cur.weather_code
      },
      daily: daily
    };
  }

  async function refreshLive() {
    var place = state.place;
    if (!place) return;
    var key = placeKey(place);
    state.live.weather = "loading";
    paintPill();
    var wx = "https://api.open-meteo.com/v1/forecast?latitude=" + place.lat + "&longitude=" + place.lon +
      "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m" +
      "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_gusts_10m_max,uv_index_max,shortwave_radiation_sum" +
      "&forecast_days=7&timezone=Africa%2FJohannesburg";
    var aq = "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=" + place.lat + "&longitude=" + place.lon +
      "&current=us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide&timezone=Africa%2FJohannesburg";
    try {
      var wj = await getJSON(wx, 9000);
      if (placeKey(state.place) !== key) return;
      state.weather = Object.assign(parseWeather(wj), {
        placeKey: key, tier: "live", source: "Open-Meteo forecast, just fetched by this browser",
        name: place.name, lat: place.lat, lon: place.lon
      });
      state.live.weather = "live";
    } catch (e) {
      state.live.weather = "snapshot";
    }
    try {
      var aj = await getJSON(aq, 8000);
      if (placeKey(state.place) === key && aj.current) {
        state.air = {
          placeKey: key, tier: "live", us_aqi: aj.current.us_aqi, pm2_5: aj.current.pm2_5,
          pm10: aj.current.pm10, ozone: aj.current.ozone, no2: aj.current.nitrogen_dioxide,
          source: "Open-Meteo air quality, just fetched"
        };
        state.live.air = "live";
      }
    } catch (e2) { state.live.air = "snapshot"; }
    try {
      var radar = await getJSON("https://api.rainviewer.com/public/weather-maps.json", 7000);
      var past = (((radar || {}).radar || {}).past || []);
      if (past.length) {
        state.radarPath = past[past.length - 1].path;
        state.live.radar = "live";
      }
    } catch (e3) {}
    try {
      var raw = await getJSON("https://api.allorigins.win/raw?url=" + encodeURIComponent("https://loadshedding.eskom.co.za/LoadShedding/GetStatus"), 7000);
      var n = parseInt(typeof raw === "number" ? raw : String(raw).trim(), 10);
      if (Number.isFinite(n)) {
        state.live.eskom = "live";
        state.live.eskomStage = n <= 0 ? null : n - 1;
        state.live.eskomRaw = n;
      }
    } catch (e4) {}
    paint();
  }

  function typing() {
    var el = document.activeElement;
    return el && el.matches && el.matches("input, textarea, select");
  }

  function paint() {
    if (typing()) { paintQueued = true; paintPill(); return; }
    render();
  }

  function paintPill() {
    var el = document.getElementById("liveText");
    var pill = document.getElementById("livePill");
    if (!el) return;
    var live = state.live.weather === "live";
    pill.className = "pill " + (live ? "live" : "snap");
    el.textContent = live ? "Weather live" : (state.live.weather === "loading" ? "Updating" : "Notices scraped");
  }

  function renderNav() {
    var html = TABS.map(function (tab) {
      return '<button type="button" data-tab="' + tab.id + '" class="' + (state.tab === tab.id ? "on" : "") + '"><span>' +
        ({ now: "◎", prepare: "⏳", money: "R", share: "🤝", you: "👤" }[tab.id]) + "</span>" + esc(tabLabel(tab)) + "</button>";
    }).join("");
    document.getElementById("tabbar").innerHTML = html;
    document.getElementById("side").innerHTML = "<strong style='padding:8px 12px'>ServiceWaze</strong>" + html;
    var chips = "";
    var list = state.saved.length ? state.saved : (snap().places || []).slice(0, 6);
    list.forEach(function (p) {
      var on = state.place && E.norm(state.place.name) === E.norm(p.name);
      chips += '<button type="button" class="chip' + (on ? " on" : "") + '" data-place="' + esc(p.name) + '">' + esc(p.name) + "</button>";
    });
    document.getElementById("chips").innerHTML = chips;
    paintPill();
  }

  function storyCard(s, big) {
    var lang = state.a11y.lang;
    var extra = "";
    if (s.severity === "critical" && lang !== "en" && CRITICAL[lang]) {
      extra = '<p class="banner"><b>' + esc(CRITICAL[lang]) + "</b></p>";
    }
    var actions = (s.actions || []).map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("");
    var buttons = '<div class="btn-row">';
    if (s.tel) buttons += '<a class="danger" href="' + tel(s.tel) + '">' + esc(s.telLabel || "Call") + "</a>";
    if (s.source) buttons += '<a href="' + safeUrl(s.source) + '" target="_blank" rel="noopener">Source</a>';
    buttons += '<button type="button" class="btn" data-wa="story">WhatsApp this</button>';
    buttons += '<button type="button" class="btn" data-speak="1">Read aloud</button></div>';
    return '<article class="' + (big ? "hero" : "card") + " sev-" + esc(s.severity) + '">' +
      '<p class="kicker">' + esc(s.kicker || "") + "</p>" +
      "<h" + (big ? "1" : "2") + ">" + esc(s.title) + "</h" + (big ? "1" : "2") + ">" +
      extra +
      "<p>" + esc(s.detail || "") + "</p>" +
      (actions ? '<ol class="actions">' + actions + "</ol>" : "") +
      buttons +
      '<p class="src">' + esc([s.via, s.source].filter(Boolean).join(" · ")) + "</p></article>";
  }

  function forecastHtml(daily) {
    if (!daily || !daily.length) return "";
    return '<div class="forecast">' + daily.slice(0, 7).map(function (d) {
      return '<div class="day"><b>' + esc(d.date) + "</b>" + esc(E.weatherLabel(d.code)) +
        "<div>" + Math.round(d.tmax) + "° / " + Math.round(d.tmin) + "°</div>" +
        "<div class='fine'>" + Math.round(d.precip_prob || 0) + "% · " + E.round(d.precip_sum || 0, 1) + " mm</div>" +
        (d.uv ? "<div class='fine'>UV " + E.round(d.uv, 1) + "</div>" : "") +
        "</div>";
    }).join("") + "</div>";
  }

  function currentHtml(w) {
    if (!w || !w.current || w.current.temp == null) return "";
    var c = w.current;
    return '<div class="grid3">' +
      '<div class="stat"><span class="fine">Now</span><b>' + E.round(c.temp, 1) + "°</b><span class='fine'>" + esc(E.weatherLabel(c.code)) + "</span></div>" +
      '<div class="stat"><span class="fine">Feels</span><b>' + (c.feels == null ? "—" : E.round(c.feels, 1) + "°") + "</b><span class='fine'>" + (c.humidity == null ? "" : c.humidity + "% humidity") + "</span></div>" +
      '<div class="stat"><span class="fine">Wind</span><b>' + (c.wind == null ? "—" : Math.round(c.wind)) + "</b><span class='fine'>km/h</span></div></div>";
  }

  function stageText() {
    if (state.live.eskom === "live" && state.live.eskomStage != null) {
      return { stage: state.live.eskomStage, tier: "live", text: state.live.eskomStage === 0 ? "No load shedding" : "Stage " + state.live.eskomStage };
    }
    var n = (snap().electricity_national || {});
    return { stage: n.stage, tier: "snapshot", text: n.meaning || "No load shedding", raw: n.raw };
  }

  function renderNow() {
    var place = state.place;
    if (!place) return renderChooser();
    var b = bundle(place);
    var lead = E.leadStory(place, snap(), b, new Date());
    var stage = stageText();
    var broad = lead.hit.broad && lead.hit.joburg;
    var html = '<div class="search"><label for="q" class="fine">Change suburb</label><input id="q" placeholder="Alexandra, Cape Town, Gqeberha…" autocomplete="off"><div class="results" id="results" hidden></div></div>';
    if (!broad && lead.top) html += storyCard(lead.top, true);
    html += '<section class="card"><div class="between"><div><p class="kicker">' + esc(place.name) + (place.admin1 ? " · " + esc(place.admin1) : "") + '</p><h2>' + esc(stage.text) + '</h2></div><div class="stat"><span class="fine">Eskom stage</span><b>' + esc(String(stage.stage)) + "</b><span class='fine'>" + (stage.tier === "live" ? "live check" : "GetStatus scrape") + "</span></div></div>";
    html += '<p class="fine">' + esc((snap().electricity_national || {}).context || "") + "</p>";
    html += '<p class="src">GetStatus returned ' + esc(String((snap().electricity_national || {}).raw)) + " at " + esc((snap().scraped_at_sast || "")) + ". " + esc((snap().electricity_national || {}).decode || "") + " National stage 0 does not mean City Power is quiet.</p></section>";

    if (broad) html += renderRollup();
    else if (lead.stories.length > 1) {
      lead.stories.slice(1, 4).forEach(function (s) { html += storyCard(s, false); });
    } else if (!lead.top) {
      html += '<section class="hero"><p class="kicker">No scraped fault for this place</p><h1>Nothing on the 24 Sep board matches ' + esc(place.name) + '</h1><p>That is not a promise the taps will run. It means this scrape had no Johannesburg Water or City Power line for this name. Use the weather, the bill tools, and call your own municipality if the street is dry.</p></section>';
    }

    var tou = E.touSlot(new Date());
    var hol = E.sastParts(new Date());
    html += '<section class="card"><div class="between"><h2>Tonight</h2><span class="tag ' + (tou.slot === "peak" ? "bad" : tou.slot === "offpeak" ? "ok" : "warn") + '">' + esc(tou.slot) + " · " + E.money(tou.price) + "/kWh</span></div>";
    html += "<p>Homeflex low-demand " + esc(tou.slot) + " is " + E.money(tou.price) + "/kWh right now. Off-peak is " + E.money(tou.offpeak) + ", peak is " + E.money(tou.peak) + ". A flat-rate meter does not care what the clock says.</p>";
    if (hol.month === 9 && hol.day === 24) html += "<p>Today is Heritage Day, a " + esc(hol.weekday) + ". Homeflex charges the public holiday as the weekday it falls on, so Thursday windows still apply.</p>";
    html += currentHtml(b);
    html += forecastHtml(b.daily);
    var uv = (b.daily || []).find(function (d) { return Number(d.uv) >= 8; });
    if (uv) html += '<p class="fine">UV ' + E.round(uv.uv, 1) + " on " + esc(uv.date) + " — hat and shade from about 10:00 to 15:00.</p>";
    html += '<p class="src">' + esc(b.source || "Weather not loaded") + "</p></section>";

    if (b.air && b.air.us_aqi != null) {
      var band = E.aqiBand(b.air.us_aqi);
      html += '<section class="card"><h2>Air · US AQI ' + Math.round(b.air.us_aqi) + " · " + esc(band.label) + "</h2>";
      html += "<p>PM2.5 " + E.round(b.air.pm2_5, 1) + " µg/m³ · PM10 " + E.round(b.air.pm10, 1) + " · ozone " + E.round(b.air.ozone, 0) + " · NO₂ " + E.round(b.air.no2, 1) + ".</p>";
      if (band.level === "bad") html += "<p>Sensitive groups should ease outdoor exercise. This is a forecast-model reading, not a government monitoring station on your corner.</p>";
      html += '<p class="src">' + esc(b.air.source || b.air.tier || "") + "</p></section>";
    }

    html += radarCard(place);
    html += newsCard();
    html += '<section class="card"><h2>Prepaid runway</h2><p class="fine">The question most meters actually ask: will these units reach month end?</p>' +
      '<label for="unitsNow">Units on the meter</label><input id="unitsNow" data-field="units" inputmode="decimal" value="' + esc(state.profile.units) + '" placeholder="e.g. 40">' +
      '<p id="runwayNow"></p><div class="btn-row"><button type="button" class="btn" data-voice="units">Speak the units</button><button type="button" class="btn" data-tab="money">Open the full bill</button></div></section>';
    return html;
  }

  function renderChooser() {
    var picks = [
      ["Alexandra", "Burst pipe today"],
      ["Bezuidenhout Valley", "Do not use tap water"],
      ["Honeydew", "Part of the suburb still dark"],
      ["Fleurhof", "City Power on site"],
      ["Cape Town", "Wind + poor air"],
      ["Gqeberha", "Thunderstorm Saturday"],
      ["Durban", "eThekwini tariff"],
      ["Pretoria", "Hot, no Joburg fault feed"]
    ];
    var html = '<section class="hero"><p class="kicker">Pick the street, not the country</p><h1>The warning is not the same in Alexandra and in Cape Town.</h1><p>National load shedding is off. Joburg water and City Power are not. Search a suburb or tap one that is on tonight\'s board.</p>';
    html += '<div class="search"><label for="q">Suburb or town</label><input id="q" placeholder="Alexandra, Khayelitsha, Gqeberha…" autocomplete="off"><div class="results" id="results" hidden></div></div>';
    html += '<div class="btn-row"><button type="button" class="btn primary" id="geoBtn">Use this phone\'s location</button></div></section>';
    html += '<div class="grid2">';
    picks.forEach(function (p) {
      html += '<button type="button" class="card" data-place="' + esc(p[0]) + '" style="text-align:left"><b>' + esc(p[0]) + '</b><div class="fine">' + esc(p[1]) + "</div></button>";
    });
    html += "</div>";
    html += '<section class="card"><h2>What was scraped at 22:40 SAST, 24 Sep 2026</h2><ul class="actions"><li>Eskom GetStatus = 1, which means stage 0.</li><li>Alexandra burst pipe, isolated, no published restoration time.</li><li>Bezuidenhout Valley quality notice still listed active. Do not use the taps.</li><li>19 Joburg reservoirs on bypass, Lawley running low.</li><li>20 City Power outages, including a partial Honeydew restoration.</li><li>Open-Meteo weather and air for the metros. Cape Town AQI 138 at 22:00.</li></ul><p class="src">Bryanston was listed on the water index and cleared on its own suburb page, so it is not shown as a water outage. Sandton meter closures are a News24 headline only — the article body was not scraped.</p></section>';
    return html;
  }

  function renderRollup() {
    var water = snap().water_outages || [];
    var html = '<section class="hero sev-bad"><p class="kicker">Johannesburg · pick a suburb</p><h1>' + water.length + ' confirmed water notices, plus a City Power board that is not national load shedding.</h1><p>A city-wide page cannot tell you if your tap is the burst pipe or just a bypassed reservoir. Tap the suburb.</p></section>';
    water.forEach(function (w) {
      html += '<button type="button" class="card sev-' + esc(w.severity) + '" data-place="' + esc(w.match[0]) + '" style="text-align:left;width:100%"><p class="kicker">Water</p><h2>' + esc(w.title) + "</h2><p>" + esc(w.detail) + "</p></button>";
    });
    var rs = snap().reservoir_summary || {};
    html += '<section class="card"><h2>Reservoirs</h2><div class="grid3"><div class="stat"><b>' + (rs.running_low || 0) + '</b><span class="fine">running low</span></div><div class="stat"><b>' + (rs.on_bypass || 0) + '</b><span class="fine">on bypass</span></div><div class="stat"><b>' + (rs.normal || 0) + "/" + (rs.tracked || 0) + '</b><span class="fine">normal</span></div></div><p class="fine">Board dated ' + esc(rs.as_of_board || "") + ". Bypass means weaker pressure, not automatically a dry tap.</p></section>";
    html += '<section class="card"><h2>City Power</h2><p>20 active outages were on the board, including Honeydew (about 80% restored, trees on the lines) and parts of Fleurhof. Pennyville and Noordgesig had a morning "restored" post and a later "still off" card — trust the lights in the room.</p><div class="btn-row"><a href="https://www.ourpower.co.za/power-outages/jhb-city-power" target="_blank" rel="noopener">Open the live power tracker</a><a href="https://www.ourpower.co.za/water-outages/jhb-water" target="_blank" rel="noopener">Open the live water tracker</a></div></section>';
    return html;
  }

  function radarCard(place) {
    var path = state.radarPath || (snap().radar || {}).latest_path;
    if (!path || place.lat == null) return "";
    var z = 6, n = 64;
    var x = Math.floor((place.lon + 180) / 360 * n);
    var latRad = place.lat * Math.PI / 180;
    var y = Math.floor((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n);
    var host = (snap().radar || {}).host || "https://tilecache.rainviewer.com";
    var src = host + path + "/256/" + z + "/" + x + "/" + y + "/2/1_1.png";
    return '<section class="card"><h2>Rain radar</h2><img class="radar" alt="RainViewer radar tile for this area" src="' + esc(src) + '"><p class="src">RainViewer tile ' + esc(path) + ". One tile, not a full national map. " + (state.live.radar === "live" ? "Path refreshed just now." : "Path from the 24 Sep scrape until the browser can refresh it.") + "</p></section>";
  }

  function newsCard() {
    var items = snap().news || [];
    if (!items.length) return "";
    return '<section class="card"><h2>Reported this week</h2>' + items.map(function (n) {
      return '<p><a href="' + safeUrl(n.href) + '" target="_blank" rel="noopener">' + esc(n.title) + "</a><br><span class='fine'>" + esc(n.publisher) + " · " + esc(n.published) + (n.note ? " · " + esc(n.note) : "") + "</span></p>";
    }).join("") + "</section>";
  }

  function renderPrepare() {
    if (!state.place) return '<section class="card"><h2>Choose a place first</h2><button type="button" class="btn primary" data-tab="now">Go to Now</button></section>';
    var plan = E.preparePlan(state.place, snap(), bundle(state.place), state.profile, new Date());
    var html = '<section class="card"><h2>Your household</h2><div class="grid2">';
    html += field("People", "people", state.profile.people, "number");
    html += field("Water stored (L)", "storageL", state.profile.storageL, "number");
    html += "</div><p>" + esc(plan.waterNote) + "</p><p class='fine'>Must-do tasks need about " + plan.mustMins + " minutes. There is no fake countdown when the utility did not publish a restoration time.</p></section>";
    html += '<section class="checks">';
    plan.tasks.forEach(function (t) {
      var id = E.norm(state.place.name) + ":" + t.id;
      var on = !!state.checks[id];
      html += '<label><input type="checkbox" data-check="' + esc(id) + '"' + (on ? " checked" : "") + "><span><b>" + esc(t.title) + "</b><br><span class='fine'>" + t.mins + " min · " + esc(t.detail) + "</span></span></label>";
    });
    html += "</section>";
    html += '<section class="card"><h2>Forecast</h2>' + forecastHtml((bundle(state.place).daily)) + "</section>";
    return html;
  }

  function field(label, name, value, type) {
    return '<div><label for="' + name + '">' + esc(label) + '</label><input id="' + name + '" data-field="' + name + '" type="' + (type || "text") + '" inputmode="decimal" value="' + esc(value) + '"></div>';
  }

  function renderMoney() {
    var p = state.profile;
    var tariffs = Object.keys(E.ELECTRICITY).map(function (id) {
      return '<option value="' + id + '"' + (p.tariff === id ? " selected" : "") + ">" + esc(E.ELECTRICITY[id].name) + "</option>";
    }).join("");
    var waters = Object.keys(E.WATER).map(function (id) {
      return '<option value="' + id + '"' + (p.water === id ? " selected" : "") + ">" + esc(E.WATER[id].name) + "</option>";
    }).join("");
    var html = "";
    html += '<section class="card"><h2>Prepaid runway</h2><div class="grid2">' +
      field("Units left", "units", p.units, "number") + field("kWh you use per day", "dailyKwh", p.dailyKwh, "number") +
      field("If I buy (R)", "buyRand", p.buyRand, "number") +
      '</div><label><input type="checkbox" data-field="fbe" style="width:auto"' + (p.fbe ? " checked" : "") + "> Registered for Free Basic Electricity (50 kWh left this month)</label>" +
      '<div id="runwayOut"></div><p class="fine" id="runwayBasis"></p></section>';
    html += '<section class="card"><h2>Electricity bill</h2><label for="tariff">Tariff</label><select id="tariff" data-field="tariff">' + tariffs + "</select>" +
      '<div class="grid2">' + field("kWh this month", "kwh", p.kwh, "number") + field("My unit price (R), if custom", "customRate", p.customRate, "number") + "</div>" +
      field("My fixed charge (R/month), if custom", "customFixed", p.customFixed, "number") +
      '<div id="elecOut"></div><div class="hours" id="hours"></div><p class="fine" id="elecSrc"></p></section>';
    html += '<section class="card"><h2>Water bill</h2><label for="water">Tariff</label><select id="water" data-field="water">' + waters + "</select>" +
      '<div class="grid2">' + field("Kilolitres this month", "kl", p.kl, "number") + field("My R/kl, if custom", "waterRate", p.waterRate, "number") + "</div>" +
      '<label><input type="checkbox" data-field="indigent" style="width:auto"' + (p.indigent ? " checked" : "") + "> Registered indigent (Cape Town step 1 free)</label>" +
      '<div id="waterOut"></div><p class="fine" id="waterSrc"></p></section>';
    html += '<section class="card"><h2>Rain you can catch</h2>' + field("Roof area (m²)", "roofM2", p.roofM2, "number") + '<div id="rainOut"></div></section>';
    html += '<section class="card"><h2>Food</h2>' + field("People", "people", p.people, "number") + field("What you spend on food (R)", "spend", p.spend, "number") + '<div id="foodOut"></div></section>';
    html += '<section class="card"><h2>Leak test</h2><p class="fine">Close every tap. Write the meter. Wait. Write it again.</p><div class="grid3">' +
      '<div><label>First reading (kl)</label><input id="leak1" inputmode="decimal"></div>' +
      '<div><label>Second reading</label><input id="leak2" inputmode="decimal"></div>' +
      '<div><label>Hours between</label><input id="leakH" inputmode="decimal" value="8"></div></div><div id="leakOut"></div></section>';
    html += '<section class="card"><h2>Solar, roughly</h2><div class="grid2">' + field("System kW", "kw", p.kw, "number") + field("Installed cost (R)", "systemCost", p.systemCost, "number") + '</div><div id="solarOut"></div></section>';
    html += '<section class="card"><h2>Savings ledger</h2><div class="grid2"><div><label>What you avoided</label><input id="ledNote" placeholder="Geyser on off-peak"></div><div><label>Rand</label><input id="ledRand" inputmode="decimal"></div></div><div class="btn-row"><button type="button" class="btn primary" id="ledAdd">Log it</button></div><div id="ledList"></div></section>';
    return html;
  }

  function fillMoney() {
    if (state.tab !== "money" && !document.getElementById("runwayOut")) {
      fillRunwayInline();
      return;
    }
    fillRunwayInline();
    var p = readProfile();
    var when = new Date();
    var elec = E.electricityBill(p.kwh, p.tariff, when, { rate: p.customRate, fixed: p.customFixed });
    var price = p.tariff === "custom" ? Number(p.customRate) || elec.marginal : elec.marginal;
    var dailyFixed = (E.ELECTRICITY[p.tariff] || {}).prepaidDaily || 0;
    var run = E.prepaidRunway({
      units: p.units === "" ? 0 : p.units, dailyKwh: p.dailyKwh, price: price,
      fbe: p.fbe, fbeLeft: p.fbe ? 50 : 0, dailyFixed: dailyFixed, buyRand: p.buyRand
    }, when);
    var runHost = document.getElementById("runwayOut") || document.getElementById("runwayNow");
    if (runHost) {
      if (p.units === "" || p.units == null) {
        runHost.innerHTML = "<p>Type the units on the meter. A guessed number would be a lie.</p>";
      } else {
        runHost.innerHTML = '<div class="grid3"><div class="stat"><b>' + run.daysCovered + '</b><span class="fine">days of units</span></div><div class="stat"><b>' + E.money(run.costPerDay) + '</b><span class="fine">per day</span></div><div class="stat"><b>' + (run.reachesMonthEnd ? "Yes" : E.money(run.shortRand)) + '</b><span class="fine">' + (run.reachesMonthEnd ? "reaches month end" : "short of month end") + "</span></div></div>" +
          "<p>About " + run.netDaily + " kWh/day leaves the meter. Runs out around " + esc(run.runsOut) + ". " + run.daysLeftInMonth + " days left in this month, including today. R" + p.buyRand + " buys about " + run.buyUnits + " units (" + run.buyDays + " days) at " + E.money(price) + "/kWh.</p>";
      }
    }
    var basis = document.getElementById("runwayBasis");
    if (basis) basis.textContent = run.basis + (dailyFixed ? " Cape Town prepaid Domestic also deducts about R" + dailyFixed + " a day." : "");
    var elecOut = document.getElementById("elecOut");
    if (elecOut) {
      var lines = (elec.lines || []).map(function (ln) {
        if (ln.slot) return "<li>" + ln.slot + ": " + ln.kwh + " kWh × " + E.money(ln.rate) + " = " + E.money(ln.cost) + "</li>";
        return "<li>" + ln.kwh + " kWh × " + E.money(ln.rate) + " = " + E.money(ln.cost) + "</li>";
      }).join("");
      elecOut.innerHTML = '<p class="big">' + E.money(elec.total) + '</p><p>Energy ' + E.money(elec.energy) + " + fixed " + E.money(elec.fixed) + ". Marginal next unit " + E.money(elec.marginal) + "/kWh.</p><ul class='actions'>" + lines + "</ul>" +
        (elec.rangeNote ? "<p>" + esc(elec.rangeNote) + "</p>" : "");
      var src = document.getElementById("elecSrc");
      if (src) src.textContent = elec.source;
      drawHours(p.tariff);
    }
    var water = E.waterBill(p.kl, p.water, { rate: p.waterRate, indigent: p.indigent });
    var waterOut = document.getElementById("waterOut");
    if (waterOut) {
      waterOut.innerHTML = '<p class="big">' + E.money(water.total) + "</p><ul class='actions'>" + water.lines.map(function (ln) {
        return "<li>" + ln.kwh + " kl × " + E.money(ln.rate) + " = " + E.money(ln.cost) + (water.vatAdded ? " excl. VAT" : "") + "</li>";
      }).join("") + "</ul>" + (water.vatAdded ? "<p>VAT " + E.money(water.vat) + " added. Demand levy and sanitation are not in this total.</p>" : "");
      var ws = document.getElementById("waterSrc");
      if (ws) ws.textContent = water.source;
    }
    var rainHost = document.getElementById("rainOut");
    if (rainHost) {
      var daily = (bundle(state.place || { name: "Johannesburg", lat: -26.2, lon: 28.05 }).daily) || [];
      var mm3 = daily.slice(0, 3).reduce(function (s, d) { return s + (Number(d.precip_sum) || 0); }, 0);
      var mm7 = daily.reduce(function (s, d) { return s + (Number(d.precip_sum) || 0); }, 0);
      var r3 = E.rainLitres(p.roofM2, mm3);
      var r7 = E.rainLitres(p.roofM2, mm7);
      rainHost.innerHTML = "<p>Next " + Math.min(3, daily.length) + " days: about " + r3.mm + " mm → <b>" + r3.litres + " L</b> off a " + p.roofM2 + " m² roof. Full forecast window: " + r7.litres + " L.</p><p class='fine'>" + esc(r3.basis) + "</p>";
    }
    var foodHost = document.getElementById("foodOut");
    if (foodHost) {
      var food = E.foodGap(p.people, p.spend === "" ? NaN : p.spend);
      foodHost.innerHTML = "<p>Food poverty line for " + food.people + " people: <b>" + E.money(food.foodPovertyLine) + "</b> (" + E.money(E.FOOD.fpl) + " each).</p>" +
        "<p>August 2026 household food basket: <b>" + E.money(food.basket) + "</b>. A rough nutritional share: " + E.money(food.nutritionProRata) + ". Feeding a child the PMBEJD way is about " + E.money(E.FOOD.child) + ".</p>" +
        (food.spend != null ? "<p>Against the food poverty line you are " + (food.shortOfLine > 0 ? E.money(food.shortOfLine) + " short" : E.money(-food.shortOfLine) + " above") + ".</p>" : "") +
        "<p class='fine'>" + esc(food.note) + " " + esc(food.source) + " " + esc(food.povertySource) + "</p>";
    }
    var solarHost = document.getElementById("solarOut");
    if (solarHost) {
      var rad = ((bundle(state.place || { name: "x" }).daily || [])[1] || {}).radiation || 20;
      var sol = E.solarEstimate(p.kw, rad, price, p.systemCost === "" ? NaN : Number(p.systemCost));
      solarHost.innerHTML = "<p>About <b>" + sol.kwh + " kWh</b> on a day with " + E.round(rad, 1) + " MJ/m², worth " + E.money(sol.save) + " at the marginal rate.</p>" +
        (sol.paybackYears != null ? "<p>Simple payback " + sol.paybackYears + " years if every day looked like this. It will not.</p>" : "<p>Type an installed cost to see a simple payback.</p>") +
        "<p class='fine'>" + esc(sol.basis) + "</p>";
    }
    var led = document.getElementById("ledList");
    if (led) {
      var sum = state.ledger.reduce(function (s, r) { return s + Number(r.rand || 0); }, 0);
      led.innerHTML = "<p>Logged " + E.money(sum) + ".</p>" + state.ledger.slice(0, 8).map(function (r) {
        return "<p>" + E.money(r.rand) + " · " + esc(r.note) + "</p>";
      }).join("");
    }
  }

  function fillRunwayInline() {
    if (state.tab === "money") return;
    var host = document.getElementById("runwayNow");
    if (!host) return;
    var p = readProfile();
    if (p.units === "" || p.units == null) { host.innerHTML = "<p>Type the units. The app will not invent them.</p>"; return; }
    var elec = E.electricityBill(p.kwh, p.tariff, new Date(), { rate: p.customRate, fixed: p.customFixed });
    var price = p.tariff === "custom" ? Number(p.customRate) || elec.marginal : elec.marginal;
    var run = E.prepaidRunway({ units: p.units, dailyKwh: p.dailyKwh, price: price, fbe: p.fbe, fbeLeft: p.fbe ? 50 : 0, buyRand: p.buyRand }, new Date());
    host.innerHTML = "<p class='big'>" + run.daysCovered + " days</p><p>" + (run.reachesMonthEnd ? "These units reach month end." : "Short of month end by " + E.money(run.shortRand) + ".") + " About " + E.money(run.costPerDay) + " a day at " + E.money(price) + "/kWh.</p>";
  }

  function drawHours(tariffId) {
    var host = document.getElementById("hours");
    if (!host) return;
    if (tariffId !== "eskom_homeflex") {
      host.innerHTML = "<p class='fine'>This tariff is not time-of-use. Moving the geyser does not change the unit price.</p>";
      return;
    }
    var hours = [];
    for (var i = 0; i < 24; i++) {
      var t = E.touSlot(new Date(Date.now() + i * 3600 * 1000));
      hours.push(t);
    }
    var max = Math.max.apply(null, hours.map(function (h) { return h.price; }));
    host.innerHTML = hours.map(function (h) {
      var ht = Math.max(8, Math.round(h.price / max * 70));
      return "<span><i class='" + h.slot + "' style='height:" + ht + "px'></i>" + h.hour + "</span>";
    }).join("");
  }

  function readProfile() {
    var p = Object.assign({}, state.profile);
    document.querySelectorAll("[data-field]").forEach(function (el) {
      if (el.type === "checkbox") p[el.dataset.field] = el.checked;
      else p[el.dataset.field] = el.value;
    });
    ["people", "storageL", "roofM2", "kwh", "kl", "dailyKwh", "customRate", "customFixed", "waterRate", "kw", "buyRand"].forEach(function (k) {
      if (p[k] !== "" && p[k] != null) p[k] = Number(p[k]);
    });
    return p;
  }

  function renderShare() {
    var html = '<section class="card"><h2>Tell the street</h2><p>Offers stay on this phone. WhatsApp is where the neighbours actually are. ServiceWaze does not pretend to have a live neighbourhood feed.</p>';
    html += '<label>I can offer</label><input id="offerText" placeholder="200 L from the borehole, 16:00–20:00">';
    html += '<div class="btn-row"><button type="button" class="btn primary" id="addOffer">Save offer</button><button type="button" class="btn" id="addNeed">Save a need</button><button type="button" class="btn" id="waOffer">WhatsApp it</button></div>';
    html += '<div id="offerList"></div></section>';
    html += '<section class="card"><h2>Stokvel for the thing that ends the outage</h2><div class="grid3"><div><label>Target (R)</label><input id="stokTarget" value="8000" inputmode="decimal"></div><div><label>People</label><input id="stokPeople" value="10" inputmode="decimal"></div><div><label>Weeks</label><input id="stokWeeks" value="8" inputmode="decimal"></div></div><p id="stokOut"></p><p class="fine">A tank, a jojo stand, or a bulk maize buy. This is arithmetic, not a bank.</p></section>';
    html += '<section class="card"><h2>Nearby help</h2><p class="fine">OpenStreetMap, ODbL. Tags are sometimes wrong — phone before you walk.</p><div id="map" class="map" role="region" aria-label="Map"></div><div id="poiList"></div><div class="btn-row"><button type="button" class="btn" id="loadPoi">Load clinics and water points near me</button></div></section>';
    return html;
  }

  function fillShare() {
    var list = document.getElementById("offerList");
    if (list) {
      var rows = state.offers.map(function (o) { return "<p>Offer · " + esc(o.text) + "</p>"; }).concat(state.needs.map(function (o) { return "<p>Need · " + esc(o.text) + "</p>"; }));
      list.innerHTML = rows.join("") || "<p class='fine'>Nothing saved on this phone yet.</p>";
    }
    var st = document.getElementById("stokOut");
    if (st) {
      var target = Number((document.getElementById("stokTarget") || {}).value || 0);
      var people = Math.max(1, Number((document.getElementById("stokPeople") || {}).value || 1));
      var weeks = Math.max(1, Number((document.getElementById("stokWeeks") || {}).value || 1));
      st.innerHTML = "Each person: <b>" + E.money(target / people) + "</b> total, <b>" + E.money(target / people / weeks) + "</b> a week.";
    }
    var pois = document.getElementById("poiList");
    if (pois) {
      var pts = nearbyPoints();
      pois.innerHTML = pts.slice(0, 8).map(function (p) {
        var km = state.place ? haversine(state.place.lat, state.place.lon, p.lat, p.lon) : null;
        return "<p><b>" + esc(p.name) + "</b> · " + esc(p.kind || "") + (km != null ? " · " + km.toFixed(1) + " km" : "") +
          (p.phone ? " · <a href='" + tel(p.phone) + "'>" + esc(p.phone) + "</a>" : "") +
          (p.address ? "<br><span class='fine'>" + esc(p.address) + "</span>" : "") + "</p>";
      }).join("") || "<p class='fine'>No points yet. Load them, or the Joburg scrape had only a handful of mapped taps.</p>";
    }
    drawMap();
  }

  function nearbyPoints() {
    var osm = (snap().osm || {});
    var base = (osm.health || []).concat(osm.drinking_water || []).concat(state.nearby || []);
    if (!state.place) return base;
    return base.slice().sort(function (a, b) {
      return haversine(state.place.lat, state.place.lon, a.lat, a.lon) - haversine(state.place.lat, state.place.lon, b.lat, b.lon);
    });
  }

  function drawMap() {
    var el = document.getElementById("map");
    if (!el || !window.L || !state.place) return;
    if (el._map && el.dataset.place === placeKey(state.place)) { el._map.invalidateSize(); return; }
    if (el._map) { el._map.remove(); el._map = null; }
    el.dataset.place = placeKey(state.place);
    var map = L.map(el).setView([state.place.lat, state.place.lon], 12);
    el._map = map;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18, attribution: "&copy; OpenStreetMap"
    }).addTo(map);
    L.marker([state.place.lat, state.place.lon]).addTo(map).bindPopup(esc(state.place.name));
    nearbyPoints().slice(0, 12).forEach(function (p) {
      if (p.lat == null) return;
      L.circleMarker([p.lat, p.lon], { radius: 6, color: "#3ec6e0" }).addTo(map).bindPopup(esc(p.name));
    });
    setTimeout(function () { map.invalidateSize(); }, 200);
  }

  function ensureLeaflet() {
    if (window.L) { drawMap(); return; }
    if (mapReady) return;
    mapReady = true;
    var css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css";
    document.head.appendChild(css);
    var s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js";
    s.onload = drawMap;
    s.onerror = function () {
      var el = document.getElementById("map");
      if (el) el.textContent = "Map tiles did not load. The list below still works.";
    };
    document.body.appendChild(s);
  }

  async function loadPois() {
    if (!state.place) { toast("Choose a place first"); return; }
    state.live.overpass = "loading";
    toast("Asking OpenStreetMap…");
    var q = "[out:json][timeout:20];(node[\"amenity\"~\"clinic|hospital|pharmacy|drinking_water\"](around:5000," +
      state.place.lat + "," + state.place.lon + "););out body 25;";
    try {
      var data = await getJSON("https://overpass-api.de/api/interpreter?data=" + encodeURIComponent(q), 22000);
      state.nearby = (data.elements || []).filter(function (e) { return e.lat && e.tags; }).map(function (e) {
        return {
          lat: e.lat, lon: e.lon, name: (e.tags && e.tags.name) || e.tags.amenity,
          kind: e.tags.amenity, phone: e.tags.phone || e.tags["contact:phone"] || "",
          address: e.tags["addr:street"] || ""
        };
      });
      state.live.overpass = "live";
      toast(state.nearby.length + " places from OpenStreetMap");
      fillShare();
      drawMap();
    } catch (e) {
      state.live.overpass = "failed";
      toast("Overpass did not answer. Showing the scraped Joburg points.");
      fillShare();
    }
  }

  function renderYou() {
    var a = state.a11y;
    var html = '<section class="card"><h2>Make it easier</h2><div class="btn-row">';
    html += '<button type="button" class="btn" data-size="md">A</button><button type="button" class="btn" data-size="lg">A+</button><button type="button" class="btn" data-size="xl">A++</button>';
    html += '<button type="button" class="btn" id="contrastBtn">' + (a.contrast ? "Contrast on" : "High contrast") + "</button>";
    html += '<button type="button" class="btn" id="simpleBtn">' + (a.simple ? "Simple on" : "Simple mode") + "</button></div>";
    html += '<label for="lang">Language of the buttons</label><select id="lang">';
    [["en", "English"], ["zu", "isiZulu"], ["af", "Afrikaans"], ["xh", "isiXhosa"], ["st", "Sesotho"]].forEach(function (pair) {
      html += '<option value="' + pair[0] + '"' + (a.lang === pair[0] ? " selected" : "") + ">" + pair[1] + "</option>";
    });
    html += '</select><p class="fine">Safety instructions stay in English as well, so a translation cannot hide the warning. Button labels switch.</p></section>';
    html += '<section class="card"><h2>Watch circle</h2><p class="fine">Names stay on this phone. A check-in is a tap, not a GPS trail.</p><div class="row"><input id="watchName" placeholder="Gogo two doors down"><button type="button" class="btn" id="watchAdd">Add</button></div><div id="watchList"></div><div class="btn-row"><button type="button" class="btn primary" id="imSafe">I\'m safe</button></div></section>';
    html += renderReceipts();
    html += '<section class="card"><h2>Sources</h2><div id="sourceList"></div><div class="btn-row"><button type="button" class="btn" id="selfCheck">Check the maths</button><button type="button" class="btn" id="refreshBtn">Refresh live weather</button></div><div id="checkOut"></div></section>';
    html += '<section class="card"><h2>This phone</h2><div class="btn-row"><button type="button" class="btn" id="exportBtn">Download my data</button><label class="btn">Import<input id="importFile" type="file" accept="application/json" hidden></label></div>';
    html += '<p class="fine">GitHub Pages cannot file a fault with the municipality, call the police, or show your neighbour\'s offer. It can show the scraped notice, do the tariff maths, and open the phone app.</p></section>';
    return html;
  }

  function renderReceipts() {
    var open = state.receipts.filter(function (r) { return r.status !== "fixed"; }).length;
    var html = '<section class="card"><h2>Fault receipt</h2><p>Open ' + open + " · logged " + state.receipts.length + ". This is your record. It is not lodged until you phone and they give you their reference.</p>";
    html += '<label>What is wrong</label><input id="faultText" placeholder="Burst pipe, 14th Avenue">';
    html += '<label>Their reference, once you have it</label><input id="faultRef" placeholder="Optional">';
    html += '<div class="btn-row"><button type="button" class="btn primary" id="addReceipt">Make a receipt</button><button type="button" class="btn" id="exportCsv">Download CSV</button></div>';
    state.receipts.slice(0, 6).forEach(function (r) {
      var hours = (Date.now() - new Date(r.at).getTime()) / 36e5;
      html += '<div class="ticket">' + esc(r.id) + "\n" + esc(r.place) + "\n" + esc(r.text) + "\nLogged " + esc(E.sastParts(r.at).label) +
        "\nElapsed " + E.round(hours, 1) + " h" + (hours > 24 ? " — follow up. 24 h is a community expectation, not an official SLA." : "") +
        (r.ref ? "\nTheir ref " + esc(r.ref) : "") + "</div>";
      html += '<div class="btn-row"><button type="button" class="btn" data-fixed="' + esc(r.id) + '">Mark fixed</button><a class="btn" href="' + waLink(receiptText(r)) + '">WhatsApp</a></div>';
    });
    html += "</section>";
    return html;
  }

  function receiptText(r) {
    return r.id + " " + r.place + ": " + r.text + ". Logged " + r.at + ". Call Johannesburg Water 0860 562 874 or City Power 011 490 7484 and ask for their reference.";
  }

  function waLink(text) {
    return "https://wa.me/?text=" + encodeURIComponent(text);
  }

  function storyText() {
    var place = state.place;
    var lead = place ? E.leadStory(place, snap(), bundle(place), new Date()) : null;
    var top = lead && lead.top;
    if (!top) return "ServiceWaze: national load shedding is off. Check your suburb before you assume the taps are fine. " + location.href;
    return "ServiceWaze — " + (place ? place.name : "") + "\n" + top.title + "\n" + top.detail + "\n" + (top.actions || []).slice(0, 2).join(" ") + "\n" + (snap().scraped_at_sast || "");
  }

  function render() {
  try {
    renderInner();
  } catch (err) {
    var main = document.getElementById("main");
    if (main) main.innerHTML = "<section class='card'><h1>This screen hit an error</h1><pre>" + esc(err && err.stack || err) + "</pre></section>";
  }
}

function renderInner() {
    applyA11y();
    renderNav();
    var main = document.getElementById("main");
    var html = state.tab === "now" ? renderNow()
      : state.tab === "prepare" ? renderPrepare()
      : state.tab === "money" ? renderMoney()
      : state.tab === "share" ? renderShare()
      : renderYou();
    main.innerHTML = html;
    if (state.tab === "money" || document.getElementById("runwayNow")) fillMoney();
    if (state.tab === "share") { fillShare(); ensureLeaflet(); }
    if (state.tab === "you") fillYou();
    var q = document.getElementById("q");
    if (q) q.focus();
  }

  function fillYou() {
    var watch = document.getElementById("watchList");
    if (watch) {
      watch.innerHTML = state.watch.map(function (w, i) {
        var hrs = w.at ? (Date.now() - new Date(w.at).getTime()) / 36e5 : 999;
        var tag = hrs > 72 ? "please knock" : hrs > 48 ? "quiet" : "recent";
        return '<p>' + esc(w.name) + ' · <span class="tag ' + (hrs > 48 ? "warn" : "ok") + '">' + tag + '</span> <button type="button" data-watch="' + i + '">Checked</button></p>';
      }).join("") || "<p class='fine'>Add someone you look out for.</p>";
    }
    var src = document.getElementById("sourceList");
    if (!src) return;
    var s = snap();
    var rows = [
      ["Eskom GetStatus", (s.electricity_national || {}).endpoint, state.live.eskom === "live" ? "live " + state.live.eskomRaw : "scraped raw " + (s.electricity_national || {}).raw],
      ["Weather", "https://api.open-meteo.com/v1/forecast", state.live.weather],
      ["Air", "https://air-quality-api.open-meteo.com/v1/air-quality", state.live.air],
      ["Radar", "https://api.rainviewer.com/public/weather-maps.json", state.live.radar],
      ["Joburg water", "https://www.ourpower.co.za/water-outages/jhb-water", "scraped " + (s.scraped_at_sast || "")],
      ["City Power", "https://www.ourpower.co.za/power-outages/jhb-city-power", "scraped"],
      ["OSM", "https://overpass-api.de/api/interpreter", state.live.overpass]
    ];
    src.innerHTML = rows.map(function (r) {
      return "<p><b>" + esc(r[0]) + "</b> · " + esc(r[2]) + "<br><a href='" + safeUrl(r[1]) + "' target='_blank' rel='noopener'>" + esc(r[1]) + "</a></p>";
    }).join("");
  }

  function selfCheck() {
    var out = [];
    function ok(name, cond, extra) { out.push((cond ? "Pass" : "FAIL") + " · " + name + (extra != null ? " (" + extra + ")" : "")); }
    var w = E.waterBill(20, "johannesburg");
    ok("Joburg 20 kl excl VAT R443.09", Math.abs(w.exclVat - 443.09) < 0.02, w.exclVat);
    ok("Joburg 20 kl incl VAT R509.55", Math.abs(w.total - 509.55) < 0.02, w.total);
    var e = E.electricityBill(600, "city_power");
    ok("City Power 600 kWh energy", Math.abs(e.energy - 2180.44) < 0.05, e.energy);
    var c = E.waterBill(15, "cape_town");
    ok("Cape Town 15 kl", Math.abs(c.total - 544.56) < 0.05, c.total);
    var tou = E.touSlot(new Date("2026-09-24T20:30:00Z"));
    ok("Thu 22:30 is off-peak", tou.slot === "offpeak" && tou.price === 1.3051, tou.slot);
    var peak = E.touSlot(new Date("2026-09-25T06:00:00Z"));
    ok("Fri 08:00 is peak", peak.slot === "peak", peak.slot);
    var bez = E.leadStory({ name: "Bezuidenhout Valley", admin1: "Gauteng", metro: "joburg" }, snap(), null, new Date());
    ok("Bez Valley is do-not-use", bez.top && bez.top.severity === "critical");
    var cpt = E.leadStory({ name: "Cape Town", admin1: "Western Cape" }, snap(), null, new Date());
    ok("Cape Town does not inherit Joburg faults", !cpt.stories.some(function (s) { return s.kind === "water"; }));
    var host = document.getElementById("checkOut");
    if (host) host.innerHTML = "<div class='ticket'>" + out.join("\n") + "</div>";
    toast(out.every(function (l) { return l.indexOf("FAIL") !== 0; }) ? "Maths checks passed" : "A check failed");
  }

  function openSheet(html) {
    document.getElementById("sheetHost").innerHTML = '<div class="sheet-back" id="sheetBack"><div class="sheet" role="dialog" aria-modal="true">' + html + "</div></div>";
  }

  function sosSheet() {
    var lines = (snap().helplines || []).map(function (h) {
      return '<a class="btn danger block" href="' + tel(h.tel) + '" style="margin-top:8px">' + esc(h.name) + " · " + esc(h.phone) + "</a><p class='fine'>" + esc(h.detail) + (h.extra ? " " + esc(h.extra) : "") + "</p>";
    }).join("");
    var utils = snap().utilities || {};
    openSheet('<div class="between"><h2>SOS</h2><button type="button" class="iconbtn" id="closeSheet">Close</button></div>' +
      '<p class="banner"><b>This button does not call the police.</b> It puts the numbers under your thumb. You tap one.</p>' +
      lines +
      '<p class="fine">USSD: dial *120*7867# for a GBV please-call-me. SMS HELP to 31531.</p>' +
      '<hr class="soft"><h3>Walk timer</h3><p class="fine">No GPS trail is stored. If you do not tap "I arrived", this phone reminds you. Tell someone on WhatsApp as well.</p>' +
      '<label>Where are you going</label><input id="walkDest" placeholder="Taxi rank to home">' +
      '<label>Minutes</label><input id="walkMins" value="25" inputmode="decimal">' +
      '<div class="btn-row"><button type="button" class="btn primary" id="walkStart">Start walk</button><button type="button" class="btn" id="walkArrive">I arrived</button><button type="button" class="btn" id="walkWa">WhatsApp the plan</button></div>' +
      '<p id="walkStatus"></p>' +
      '<hr class="soft"><h3>Utilities</h3>' +
      '<a class="btn block" href="' + tel(utils.johannesburg_water && utils.johannesburg_water.tel) + '">Johannesburg Water ' + esc(utils.johannesburg_water && utils.johannesburg_water.phone) + "</a>" +
      '<a class="btn block" style="margin-top:8px" href="' + tel(utils.city_power && utils.city_power.tel) + '">City Power ' + esc(utils.city_power && utils.city_power.phone) + "</a>" +
      '<button type="button" class="btn block" style="margin-top:8px" id="unsafeBtn">Log an unsafe place</button>');
    paintWalk();
  }

  function paintWalk() {
    var el = document.getElementById("walkStatus");
    if (!el || !state.walk) return;
    var left = state.walk.deadline - Date.now();
    el.textContent = left > 0
      ? "Walking to " + state.walk.dest + ". " + Math.ceil(left / 60000) + " min left."
      : "Time is up for " + state.walk.dest + ". This phone did not call anyone. Call them, or tap I arrived.";
  }

  function checkWalk() {
    if (!state.walk || state.walk.arrived) return;
    if (Date.now() > state.walk.deadline && !state.walk.alerted) {
      state.walk.alerted = true;
      save();
      toast("Walk timer ended. Call someone — this app did not.");
      if (window.Notification && Notification.permission === "granted") {
        new Notification("ServiceWaze walk timer", { body: "Time is up. This app did not call the police." });
      }
    }
  }

  function speak(text) {
    if (!window.speechSynthesis) { toast("This browser has no read-aloud."); return; }
    window.speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(text);
    u.lang = "en-ZA";
    window.speechSynthesis.speak(u);
  }

  function listenInto(field) {
    var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Rec) { toast("Voice input is not in this browser."); return; }
    var rec = new Rec();
    rec.lang = "en-ZA";
    rec.onresult = function (ev) {
      var said = ev.results[0][0].transcript;
      var num = (said.match(/[0-9]+([.,][0-9]+)?/) || [])[0];
      if (!num) { toast("Heard: " + said); return; }
      state.profile[field] = num.replace(",", ".");
      save();
      render();
      toast("Heard " + num);
    };
    rec.start();
  }

  function onClick(ev) {
    var t = ev.target.closest("button, a");
    if (!t) return;
    if (t.dataset.tab) { setTab(t.dataset.tab); return; }
    if (t.dataset.place) {
      var known = knownPlace(t.dataset.place);
      if (known) setPlace(known);
      else geocodePick(t.dataset.place);
      return;
    }
    if (t.dataset.wa === "story") {
      var card = t.closest("article");
      location.href = waLink((card ? card.innerText : storyText()).slice(0, 700));
      return;
    }
    if (t.dataset.speak) {
      var card = t.closest("article, section");
      speak(card ? card.innerText.slice(0, 500) : storyText());
      return;
    }
    if (t.dataset.voice) { listenInto(t.dataset.voice); return; }
    if (t.dataset.fixed) {
      state.receipts.forEach(function (r) { if (r.id === t.dataset.fixed) r.status = "fixed"; });
      save(); render(); return;
    }
    if (t.dataset.watch) {
      state.watch[Number(t.dataset.watch)].at = new Date().toISOString();
      save(); fillYou(); return;
    }
    if (t.dataset.size) { state.a11y.size = t.dataset.size; save(); return; }
    if (t.id === "sosBtn") { sosSheet(); return; }
    if (t.id === "closeSheet" || t.id === "sheetBack") {
      if (t.id === "sheetBack" && ev.target !== t) return;
      document.getElementById("sheetHost").innerHTML = "";
      return;
    }
    if (t.id === "themeBtn") {
      state.a11y.theme = state.a11y.theme === "light" ? "dark" : "light";
      save(); return;
    }
    if (t.id === "geoBtn") { geo(); return; }
    if (t.id === "addOffer" || t.id === "addNeed") {
      var text = (document.getElementById("offerText") || {}).value || "";
      if (!text.trim()) return;
      var bucket = t.id === "addOffer" ? state.offers : state.needs;
      bucket.unshift({ text: text.trim(), at: new Date().toISOString(), place: state.place && state.place.name });
      save(); fillShare(); toast("Saved on this phone");
      return;
    }
    if (t.id === "waOffer") {
      var offer = (state.offers[0] && state.offers[0].text) || (document.getElementById("offerText") || {}).value || "I can help";
      location.href = waLink((state.place ? state.place.name + ": " : "") + offer);
      return;
    }
    if (t.id === "loadPoi") { loadPois(); return; }
    if (t.id === "ledAdd") {
      var note = (document.getElementById("ledNote") || {}).value || "Saved";
      var rand = Number((document.getElementById("ledRand") || {}).value || 0);
      if (!rand) return;
      state.ledger.unshift({ note: note, rand: rand, at: new Date().toISOString() });
      save(); fillMoney(); return;
    }
    if (t.id === "contrastBtn") { state.a11y.contrast = !state.a11y.contrast; save(); render(); return; }
    if (t.id === "simpleBtn") { state.a11y.simple = !state.a11y.simple; save(); render(); return; }
    if (t.id === "watchAdd") {
      var name = (document.getElementById("watchName") || {}).value || "";
      if (!name.trim()) return;
      state.watch.push({ name: name.trim(), at: null });
      save(); fillYou(); return;
    }
    if (t.id === "imSafe") {
      state.watch.forEach(function (w) { if (!w.at) w.at = new Date().toISOString(); });
      state.ledger.unshift({ note: "Checked in safe", rand: 0, at: new Date().toISOString() });
      save(); toast("Marked safe on this phone"); fillYou(); return;
    }
    if (t.id === "addReceipt" || t.id === "unsafeBtn") {
      var text = t.id === "unsafeBtn" ? "Unsafe place" : ((document.getElementById("faultText") || {}).value || "Fault");
      var rec = {
        id: E.receiptId(Date.now()),
        place: (state.place && state.place.name) || "Unspecified",
        text: text,
        ref: (document.getElementById("faultRef") || {}).value || "",
        at: new Date().toISOString(),
        status: "open"
      };
      state.receipts.unshift(rec);
      save();
      toast(rec.id + " saved on this phone");
      if (t.id === "unsafeBtn") document.getElementById("sheetHost").innerHTML = "";
      render();
      return;
    }
    if (t.id === "exportCsv") {
      var csv = "id,place,text,at,status,ref\n" + state.receipts.map(function (r) {
        return [r.id, r.place, r.text, r.at, r.status, r.ref].map(function (c) { return '"' + String(c || "").replace(/"/g, '""') + '"'; }).join(",");
      }).join("\n");
      download("servicewaze-receipts.csv", csv, "text/csv");
      return;
    }
    if (t.id === "exportBtn") {
      download("servicewaze-data.json", JSON.stringify({ profile: state.profile, receipts: state.receipts, offers: state.offers, needs: state.needs, ledger: state.ledger, watch: state.watch }, null, 2), "application/json");
      return;
    }
    if (t.id === "selfCheck") { selfCheck(); return; }
    if (t.id === "refreshBtn") { refreshLive(); toast("Refreshing weather"); return; }
    if (t.id === "walkStart") {
      var mins = Math.max(5, Number((document.getElementById("walkMins") || {}).value || 25));
      state.walk = {
        dest: (document.getElementById("walkDest") || {}).value || "home",
        mins: mins, started: Date.now(), deadline: Date.now() + mins * 60000, alerted: false
      };
      save();
      if (window.Notification && Notification.permission === "default") Notification.requestPermission();
      paintWalk();
      toast("Timer started. It will not call anyone.");
      return;
    }
    if (t.id === "walkArrive") {
      if (state.walk) state.walk.arrived = true;
      save(); toast("Arrived. Timer stopped."); paintWalk(); return;
    }
    if (t.id === "walkWa") {
      var dest = (document.getElementById("walkDest") || {}).value || "home";
      var mins = (document.getElementById("walkMins") || {}).value || "25";
      location.href = waLink("I'm walking to " + dest + ". If I don't message in " + mins + " minutes, check on me. This is a message, not a tracker.");
    }
  }

  function download(name, text, type) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: type }));
    a.download = name;
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  function onInput(ev) {
    var el = ev.target;
    if (el.dataset && el.dataset.field) {
      if (el.dataset.field === "tariff") state.profile.tariffTouched = true;
      if (el.dataset.field === "water") state.profile.waterTouched = true;
      state.profile[el.dataset.field] = el.type === "checkbox" ? el.checked : el.value;
      save();
      if (state.tab === "money" || el.id === "unitsNow") fillMoney();
      if (state.tab === "prepare" && (el.dataset.field === "people" || el.dataset.field === "storageL")) paintQueued = true;
    }
    if (el.id === "q") {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () { search(el.value); }, 250);
    }
    if (el.id === "stokTarget" || el.id === "stokPeople" || el.id === "stokWeeks") fillShare();
    if (el.id === "leak1" || el.id === "leak2" || el.id === "leakH") {
      var host = document.getElementById("leakOut");
      if (!host) return;
      var res = E.leakTest(el.form ? 0 : document.getElementById("leak1").value, document.getElementById("leak2").value, document.getElementById("leakH").value);
      host.innerHTML = res.ok
        ? "<p>" + (res.leak ? "Looks like a leak or a running cistern. " : "Little or no movement. ") + res.perHour + " L/hour, about " + res.perDay + " L/day.</p><p class='fine'>" + esc(res.basis) + "</p>"
        : "<p class='fine'>" + esc(res.reason || "") + "</p>";
    }
    if (el.id === "lang") {
      state.a11y.lang = el.value;
      save(); render();
    }
  }

  function onChange(ev) {
    var el = ev.target;
    if (el.dataset && el.dataset.field) onInput(ev);
    if (el.dataset && el.dataset.check) {
      state.checks[el.dataset.check] = el.checked;
      save();
    }
    if (el.id === "importFile" && el.files && el.files[0]) {
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var data = JSON.parse(reader.result);
          ["profile", "receipts", "offers", "needs", "ledger", "watch"].forEach(function (k) {
            if (data[k]) state[k] = k === "profile" ? Object.assign(state.profile, data[k]) : data[k];
          });
          save(); render(); toast("Imported");
        } catch (e) { toast("That file was not ServiceWaze JSON"); }
      };
      reader.readAsText(el.files[0]);
    }
  }

  async function search(q) {
    var box = document.getElementById("results");
    if (!box) return;
    var query = E.norm(q);
    if (query.length < 2) { box.hidden = true; return; }
    var local = (snap().places || []).filter(function (p) { return E.norm(p.name).indexOf(query) !== -1; }).slice(0, 6);
    box.hidden = false;
    box.innerHTML = local.map(placeButton).join("") || "<p class='fine' style='padding:10px'>Searching…</p>";
    try {
      var data = await getJSON("https://geocoding-api.open-meteo.com/v1/search?name=" + encodeURIComponent(q) + "&count=6&language=en&format=json", 7000);
      var remote = ((data && data.results) || []).filter(function (r) { return r.country_code === "ZA"; }).map(function (r) {
        return { name: r.name, admin1: r.admin1 || "", lat: r.latitude, lon: r.longitude };
      });
      var merged = local.slice();
      remote.forEach(function (r) {
        if (!merged.some(function (m) { return E.norm(m.name) === E.norm(r.name) && E.norm(m.admin1) === E.norm(r.admin1); })) merged.push(r);
      });
      box.innerHTML = merged.slice(0, 8).map(placeButton).join("") || "<p class='fine' style='padding:10px'>No South African match.</p>";
    } catch (e) {
      if (!local.length) box.innerHTML = "<p class='fine' style='padding:10px'>Search failed. Tap a place on the board.</p>";
    }
  }

  function placeButton(p) {
    return '<button type="button" data-geo="' + esc(p.name) + "|" + esc(p.admin1 || "") + "|" + p.lat + "|" + p.lon + '">' +
      esc(p.name) + (p.admin1 ? ", " + esc(p.admin1) : "") + "</button>";
  }

  function geocodePick(name) {
    var known = knownPlace(name);
    if (known) { setPlace(known); return; }
    search(name);
  }

  async function geo() {
    if (!navigator.geolocation) { toast("This phone has no location."); return; }
    toast("Finding you…");
    navigator.geolocation.getCurrentPosition(async function (pos) {
      var lat = pos.coords.latitude, lon = pos.coords.longitude;
      try {
        var rev = await getJSON("https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=" + lat + "&longitude=" + lon + "&localityLanguage=en", 8000);
        var name = rev.locality || rev.city || rev.principalSubdivision || "This location";
        setPlace({ name: name, admin1: rev.principalSubdivision || "", lat: lat, lon: lon });
      } catch (e) {
        setPlace({ name: "This location", lat: lat, lon: lon });
      }
    }, function () { toast("Location was blocked. Search the suburb instead."); }, { enableHighAccuracy: false, timeout: 8000 });
  }

  document.addEventListener("click", function (ev) {
    if (ev.target.id === "sheetBack") {
      document.getElementById("sheetHost").innerHTML = "";
      return;
    }
    var geoBtn = ev.target.closest("[data-geo]");
    if (geoBtn) {
      var parts = geoBtn.dataset.geo.split("|");
      setPlace({ name: parts[0], admin1: parts[1], lat: Number(parts[2]), lon: Number(parts[3]) });
      return;
    }
    onClick(ev);
  });
  document.addEventListener("input", onInput);
  document.addEventListener("change", onChange);
  document.addEventListener("focusout", function () {
    if (paintQueued) { paintQueued = false; render(); }
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") document.getElementById("sheetHost").innerHTML = "";
  });
  window.addEventListener("hashchange", function () {
    var id = location.hash.replace("#", "");
    if (TABS.some(function (t) { return t.id === id; }) && id !== state.tab) setTab(id);
  });

  async function boot() {
    applyA11y();
    try {
      state.snapshot = await loadJSON("data/snapshot.json", 8000);
    } catch (e) {
      document.getElementById("main").innerHTML = "<section class='card'><h1>Could not load scraped data.</h1><p>Check that data/snapshot.json is next to this page.</p><p class='fine'>" + esc(e && (e.message || e)) + "</p></section>";
      return;
    }
    if (location.hash) {
      var id = location.hash.replace("#", "");
      if (TABS.some(function (t) { return t.id === id; })) state.tab = id;
    }
    render();
    if (state.place) refreshLive();
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("sw.js").catch(function () {});
    }
    setInterval(checkWalk, 15000);
    checkWalk();
  }

  if (!E) {
    document.getElementById("main").innerHTML = "<p>Calculator failed to load.</p>";
  } else {
    boot();
  }
})();
