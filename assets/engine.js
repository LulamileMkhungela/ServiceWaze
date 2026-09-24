/* ServiceWaze calculations. No DOM. Safe to run in the browser or Node. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SWEngine = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const VAT = 1.15;
  const TZ = "Africa/Johannesburg";

  const ELECTRICITY = {
    eskom_homelight_20: {
      id: "eskom_homelight_20",
      name: "Eskom Homelight 20A",
      kind: "flat",
      blocks: [{ from: 0, to: Infinity, rate: 2.703 }],
      fixedMonth: 0,
      prepaidDaily: 0,
      who: "Eskom direct, small prepaid supply",
      source: "Eskom Schedule of Standard Prices 2026/27, Homelight 20A, 270.30 c/kWh incl. VAT. Cited by EnergyBee (1 Aug 2026) and EcoFlow from the Eskom tariff booklet.",
      asOf: "2026-04-01"
    },
    eskom_homelight_60: {
      id: "eskom_homelight_60",
      name: "Eskom Homelight 60A",
      kind: "flat",
      blocks: [{ from: 0, to: Infinity, rate: 3.4361 }],
      fixedMonth: 0,
      prepaidDaily: 0,
      who: "Eskom direct, standard prepaid",
      source: "Eskom Schedule of Standard Prices 2026/27, Homelight 60A, 343.61 c/kWh incl. VAT.",
      asOf: "2026-04-01"
    },
    eskom_homepower: {
      id: "eskom_homepower",
      name: "Eskom Homepower 4",
      kind: "flat",
      blocks: [{ from: 0, to: Infinity, rate: 3.5556 }],
      fixedMonth: 536,
      prepaidDaily: 0,
      who: "Eskom direct, post-paid single-phase",
      source: "Eskom 2026/27: energy 322.06 c/kWh + network demand 32.98 c + ancillary 0.52 c = 355.56 c/kWh incl. VAT, plus about R536/month fixed on Homepower 4 (EnergyBee, citing the Schedule of Standard Prices).",
      asOf: "2026-04-01"
    },
    eskom_homeflex: {
      id: "eskom_homeflex",
      name: "Eskom Homeflex (time of use)",
      kind: "tou",
      fixedMonth: 536,
      prepaidDaily: 0,
      who: "Eskom direct, smart TOU meter",
      rates: {
        high: { peak: 8.471, standard: 2.958, offpeak: 1.9083 },
        low: { peak: 3.9455, standard: 1.9265, offpeak: 1.3051 }
      },
      source: "Eskom Homeflex 2026/27 incl. VAT: winter peak R8.4710, standard R2.9580, off-peak R1.9083; low-demand peak R3.9455, standard R1.9265, off-peak R1.3051. Windows follow the long-standing Homeflex/Megaflex shape and should be confirmed on the bill — secondary write-ups differ by about an hour.",
      asOf: "2026-04-01"
    },
    city_power: {
      id: "city_power",
      name: "City Power Johannesburg",
      kind: "block",
      blocks: [
        { from: 0, to: 350, rate: 3.3403 },
        { from: 350, to: 500, rate: 3.8316 },
        { from: 500, to: Infinity, rate: 4.3659 }
      ],
      fixedMonth: 241.5,
      prepaidDaily: 0,
      who: "City of Johannesburg residential",
      source: "City Power 2026/27 residential, incl. VAT: R3.3403 (0–350 kWh), R3.8316 (350–500), R4.3659 (above 500), fixed R241.50/month. EnergyBee, 1 Aug 2026, from the metro schedule. Increase took effect 1 July 2026.",
      asOf: "2026-07-01"
    },
    cape_town_domestic: {
      id: "cape_town_domestic",
      name: "Cape Town Domestic",
      kind: "block",
      blocks: [
        { from: 0, to: 600, rate: 4.1379 },
        { from: 600, to: Infinity, rate: 4.939 }
      ],
      fixedMonth: 74.77,
      prepaidDaily: 2.46,
      who: "City of Cape Town, credit or prepaid domestic",
      source: "City of Cape Town 2026/27 Domestic, incl. VAT, from 1 July 2026: R4.1379/kWh to 600 units, R4.9390 above, service charge R74.77/month on credit meters or R2.46/day on prepaid. EnergyBee and Cape Town Etc.",
      asOf: "2026-07-01"
    },
    cape_town_home_user: {
      id: "cape_town_home_user",
      name: "Cape Town Home User",
      kind: "block",
      blocks: [
        { from: 0, to: 600, rate: 3.5595 },
        { from: 600, to: Infinity, rate: 4.6906 }
      ],
      fixedMonth: 424.3,
      prepaidDaily: 0,
      who: "Cape Town Home User, including solar-registered homes",
      source: "City of Cape Town 2026/27 Home User, incl. VAT: R3.5595 to 600 kWh, R4.6906 above, R424.30/month service and wires. Break-even versus Domestic is about 610 kWh/month.",
      asOf: "2026-07-01"
    },
    cape_town_lifeline: {
      id: "cape_town_lifeline",
      name: "Cape Town Lifeline",
      kind: "flat",
      blocks: [{ from: 0, to: Infinity, rate: 2.83 }],
      fixedMonth: 0,
      prepaidDaily: 0,
      who: "Qualifying Cape Town Lifeline customers only",
      source: "Cape Town Etc, 7 Sep 2026: qualifying Lifeline customers pay about R2.83/kWh with no service charge. Rounded figure — confirm on the bill.",
      asOf: "2026-07-01"
    },
    ethekwini: {
      id: "ethekwini",
      name: "eThekwini domestic",
      kind: "flat",
      blocks: [{ from: 0, to: Infinity, rate: 4.1674 }],
      fixedMonth: 0,
      prepaidDaily: 0,
      who: "Durban residential flat tariff",
      source: "eThekwini 2026/27 domestic flat rate R4.1674/kWh incl. VAT, no fixed charge. EnergyBee, 1 Aug 2026, from the metro schedule. +10.5% from 1 July 2026.",
      asOf: "2026-07-01"
    },
    ekurhuleni: {
      id: "ekurhuleni",
      name: "Ekurhuleni Tariff B",
      kind: "flat",
      blocks: [{ from: 0, to: Infinity, rate: 4.2274 }],
      fixedMonth: 137.62,
      prepaidDaily: 0,
      who: "Ekurhuleni residential Tariff B",
      source: "Ekurhuleni Tariff B 2026/27: R4.2274/kWh incl. VAT, fixed R137.62/month. EnergyBee, 1 Aug 2026. Other Ekurhuleni tariffs differ.",
      asOf: "2026-07-01"
    },
    tshwane_low: {
      id: "tshwane_low",
      name: "Tshwane — first block (low end)",
      kind: "flat",
      blocks: [{ from: 0, to: Infinity, rate: 3.7274 }],
      fixedMonth: 163.88,
      prepaidDaily: 0,
      who: "Pretoria, if you are still in the cheapest block",
      source: "Tshwane 2026/27 has 4 residential blocks from R3.7274 to R5.1234/kWh incl. VAT, fixed R163.88 (EnergyBee, 1 Aug 2026). Block boundaries were not in the scraped summary, so this is the cheap end of the range, not a full bill.",
      asOf: "2026-07-01",
      rangeNote: "Top block is R5.1234/kWh. Enter the unit price from your meter slip if you have it."
    },
    custom: {
      id: "custom",
      name: "My meter slip",
      kind: "flat",
      blocks: [{ from: 0, to: Infinity, rate: 3.5 }],
      fixedMonth: 0,
      prepaidDaily: 0,
      who: "Use the cents-per-unit printed on your last slip",
      source: "Entered by you from your own slip. ServiceWaze does not invent a rate when the metro table was not scraped.",
      asOf: "user"
    }
  };

  const WATER = {
    johannesburg: {
      id: "johannesburg",
      name: "Johannesburg Water 2026/27",
      vatExclusive: true,
      indigentOnlyFree: false,
      blocks: [
        { from: 0, to: 6, rate: 0 },
        { from: 6, to: 10, rate: 28.91 },
        { from: 10, to: 15, rate: 29.84 },
        { from: 15, to: 20, rate: 35.65 },
        { from: 20, to: 30, rate: 64.53 },
        { from: 30, to: 40, rate: 69.45 },
        { from: 40, to: 50, rate: 86.81 },
        { from: 50, to: Infinity, rate: 94.92 }
      ],
      source: "City of Johannesburg residential prepayment water, VAT exclusive, demand levy excluded. Bands from Mayoral Committee Item 77 as republished with the 12.5% FY2026/27 increase (0–6 kl free, then R28.91, R29.84, R35.65, R64.53, R69.45, R86.81, R94.92). City of Johannesburg confirmed the 12.5% water increase from 1 July 2026. This calculator adds 15% VAT. Sanitation is a separate charge and is not included."
    },
    cape_town: {
      id: "cape_town",
      name: "Cape Town water Level 0 (no restriction)",
      vatExclusive: false,
      indigentOnlyFree: true,
      blocks: [
        { from: 0, to: 6, rate: 25.42 },
        { from: 6, to: 10.5, rate: 34.92 },
        { from: 10.5, to: 35, rate: 52.2 },
        { from: 35, to: Infinity, rate: 100.71 }
      ],
      source: "City of Cape Town tariff guide, Level 0 (no restriction) 2026/27, incl. VAT, from 1 July 2026: R25.42 (0–6 kl), R34.92 (>6–10.5), R52.20 (>10.5–35), R100.71 (above 35). Step 1 is free only for registered indigent households. If a water restriction level is in force, these steps are too low — use the prices on your bill."
    },
    custom: {
      id: "custom",
      name: "Price on my bill",
      vatExclusive: false,
      indigentOnlyFree: false,
      blocks: [{ from: 0, to: Infinity, rate: 40 }],
      source: "Flat R/kl you typed from your municipal bill. Use this where a 2026/27 block table was not scraped (Tshwane, eThekwini and smaller municipalities)."
    }
  };

  const FOOD = {
    basket: 5479.8,
    basketMonth: "August 2026",
    basketSource: "PMBEJD Household Affordability Index, August 2026 national average, as cited by SAFTU. July 2026 was R5,530.52 (Business Report, 29 Jul 2026). August city-by-city totals were not in the pages scraped here, so they are not shown.",
    nutritional7: 6597.25,
    child: 961.96,
    nutritionalSource: "SAFTU, citing the August 2026 PMBEJD index: a basic nutritional basket R6,597.25, and about R961.96 to feed one child.",
    fpl: 868,
    lbpl: 1457,
    ubpl: 2962,
    povertySource: "Stats SA National Poverty Lines 2026 (May prices): food poverty line R868 per person per month, lower-bound R1,457, upper-bound R2,962."
  };

  const WMO = {
    0: ["Clear", "Clear"],
    1: ["Mainly clear", "Mainly clear"],
    2: ["Partly cloudy", "Partly cloudy"],
    3: ["Overcast", "Overcast"],
    45: ["Fog", "Fog"],
    48: ["Rime fog", "Rime fog"],
    51: ["Light drizzle", "Light drizzle"],
    53: ["Drizzle", "Drizzle"],
    55: ["Dense drizzle", "Dense drizzle"],
    61: ["Light rain", "Light rain"],
    63: ["Rain", "Rain"],
    65: ["Heavy rain", "Heavy rain"],
    80: ["Showers", "Showers"],
    81: ["Heavy showers", "Heavy showers"],
    82: ["Violent showers", "Violent showers"],
    95: ["Thunderstorm", "Thunderstorm"],
    96: ["Thunderstorm, hail", "Thunderstorm with hail"],
    99: ["Severe thunderstorm", "Severe thunderstorm"]
  };

  function round(n, d) {
    const p = 10 ** (d == null ? 2 : d);
    return Math.round((Number(n) + Number.EPSILON) * p) / p;
  }

  function money(n) {
    const v = round(n, 2);
    const sign = v < 0 ? "-" : "";
    const abs = Math.abs(v).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    return sign + "R" + abs.replace(".", ",");
  }

  function norm(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/['’]/g, "")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }

  function sastParts(date) {
    const d = date instanceof Date ? date : new Date(date || Date.now());
    const fmt = new Intl.DateTimeFormat("en-GB", {
      timeZone: TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      weekday: "short",
      hourCycle: "h23"
    });
    const bag = {};
    for (const p of fmt.formatToParts(d)) bag[p.type] = p.value;
    return {
      year: Number(bag.year),
      month: Number(bag.month),
      day: Number(bag.day),
      hour: Number(bag.hour),
      minute: Number(bag.minute),
      weekday: bag.weekday,
      label: bag.weekday + " " + bag.day + " " + monthName(Number(bag.month)) + " " + bag.hour + ":" + bag.minute
    };
  }

  function monthName(m) {
    return ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m] || "";
  }

  function daysInMonth(year, month) {
    return new Date(Date.UTC(year, month, 0)).getUTCDate();
  }

  function season(month) {
    return month >= 6 && month <= 8 ? "high" : "low";
  }

  function isWeekendName(weekday) {
    return weekday === "Sat" || weekday === "Sun";
  }

  /* Classic Homeflex/Megaflex windows. Public holidays follow the weekday
     they fall on (EnergyBee, Jul 2026) — Heritage Day 2026 is a Thursday. */
  function touSlot(date) {
    const p = sastParts(date);
    const s = season(p.month);
    const h = p.hour;
    let slot = "standard";
    if (p.weekday === "Sun") {
      slot = h >= 18 && h < 20 ? "standard" : "offpeak";
    } else if (p.weekday === "Sat") {
      if (s === "high") slot = (h >= 9 && h < 17) || (h >= 18 && h < 20) ? "standard" : "offpeak";
      else slot = (h >= 7 && h < 12) || (h >= 18 && h < 20) ? "standard" : "offpeak";
    } else if (s === "high") {
      if ((h >= 6 && h < 9) || (h >= 17 && h < 19)) slot = "peak";
      else if (h >= 22 || h < 6) slot = "offpeak";
      else slot = "standard";
    } else {
      if ((h >= 7 && h < 10) || (h >= 18 && h < 20)) slot = "peak";
      else if (h >= 22 || h < 6) slot = "offpeak";
      else slot = "standard";
    }
    const rates = ELECTRICITY.eskom_homeflex.rates[s];
    return {
      slot: slot,
      season: s,
      price: rates[slot],
      peak: rates.peak,
      standard: rates.standard,
      offpeak: rates.offpeak,
      hour: h,
      weekday: p.weekday,
      label: p.label
    };
  }

  function hourStarts(date, count) {
    const p = sastParts(date);
    const utcGuess = Date.UTC(p.year, p.month - 1, p.day, p.hour, 0, 0) - 2 * 3600 * 1000;
    const out = [];
    for (let i = 0; i < (count || 24); i++) out.push(new Date(utcGuess + i * 3600 * 1000));
    return out;
  }

  function cheapestHours(date, count) {
    return hourStarts(date, count || 24)
      .map(function (d) {
        const t = touSlot(d);
        return { ts: d.toISOString(), hour: sastParts(d).hour, label: t.label, slot: t.slot, price: t.price, season: t.season };
      })
      .sort(function (a, b) { return a.price - b.price; });
  }

  function blockBill(kwh, blocks) {
    let left = Math.max(0, Number(kwh) || 0);
    let cost = 0;
    const lines = [];
    for (let i = 0; i < blocks.length && left > 0.0001; i++) {
      const b = blocks[i];
      const width = b.to === Infinity ? left : Math.max(0, b.to - b.from);
      const take = Math.min(left, width);
      if (take <= 0) continue;
      const lineCost = take * b.rate;
      cost += lineCost;
      lines.push({
        from: b.from,
        to: b.to === Infinity ? null : round(b.from + take, 2),
        kwh: round(take, 2),
        rate: b.rate,
        cost: round(lineCost, 2)
      });
      left -= take;
    }
    return { energy: round(cost, 2), lines: lines };
  }

  function marginalRate(tariff, kwh, when) {
    if (!tariff) return 0;
    if (tariff.kind === "tou") return touSlot(when).price;
    const used = Math.max(0, Number(kwh) || 0);
    const blocks = tariff.blocks || [];
    for (let i = 0; i < blocks.length; i++) {
      if (used < blocks[i].to) return blocks[i].rate;
    }
    return blocks.length ? blocks[blocks.length - 1].rate : 0;
  }

  function electricityBill(kwh, tariffId, when, custom) {
    const tariff = Object.assign({}, ELECTRICITY[tariffId] || ELECTRICITY.city_power);
    if (tariffId === "custom" && custom) {
      tariff.blocks = [{ from: 0, to: Infinity, rate: Number(custom.rate) || 0 }];
      tariff.fixedMonth = Number(custom.fixed) || 0;
      tariff.prepaidDaily = Number(custom.daily) || 0;
    }
    const qty = Math.max(0, Number(kwh) || 0);
    let energy, lines, slot;
    if (tariff.kind === "tou") {
      const t = touSlot(when);
      slot = t;
      const split = { peak: 0.15, standard: 0.45, offpeak: 0.4 };
      energy = qty * (split.peak * t.peak + split.standard * t.standard + split.offpeak * t.offpeak);
      lines = ["peak", "standard", "offpeak"].map(function (k) {
        return { slot: k, kwh: round(qty * split[k], 1), rate: t[k], cost: round(qty * split[k] * t[k], 2) };
      });
    } else {
      const b = blockBill(qty, tariff.blocks);
      energy = b.energy;
      lines = b.lines;
    }
    const fixed = Number(tariff.fixedMonth) || 0;
    const total = energy + fixed;
    return {
      kwh: round(qty, 1),
      energy: round(energy, 2),
      fixed: round(fixed, 2),
      total: round(total, 2),
      blended: qty ? round(total / qty, 4) : 0,
      marginal: marginalRate(tariff, qty, when),
      tariff: tariff.name,
      tariffId: tariff.id,
      lines: lines,
      slot: slot || null,
      source: tariff.source,
      asOf: tariff.asOf,
      rangeNote: tariff.rangeNote || "",
      prepaidDaily: tariff.prepaidDaily || 0
    };
  }

  function waterBill(kl, cityId, opts) {
    opts = opts || {};
    const city = WATER[cityId] || WATER.custom;
    const tariff = cityId === "custom"
      ? Object.assign({}, city, { blocks: [{ from: 0, to: Infinity, rate: Number(opts.rate) || 0 }] })
      : city;
    const qty = Math.max(0, Number(kl) || 0);
    const blocks = tariff.blocks.map(function (b) { return Object.assign({}, b); });
    if (opts.indigent && tariff.indigentOnlyFree && blocks[0]) blocks[0].rate = 0;
    const billed = blockBill(qty, blocks);
    const excl = billed.energy;
    const total = tariff.vatExclusive ? excl * VAT : excl;
    return {
      kl: round(qty, 2),
      exclVat: round(excl, 2),
      vat: tariff.vatExclusive ? round(excl * 0.15, 2) : 0,
      total: round(total, 2),
      lines: billed.lines,
      tariff: tariff.name,
      city: tariff.id,
      vatAdded: !!tariff.vatExclusive,
      source: tariff.source,
      indigentApplied: !!(opts.indigent && tariff.indigentOnlyFree)
    };
  }

  function prepaidRunway(input, when) {
    const p = sastParts(when);
    const dim = daysInMonth(p.year, p.month);
    const daysLeft = Math.max(0, dim - p.day + 1);
    const units = Math.max(0, Number(input.units) || 0);
    const fbe = input.fbe ? Math.max(0, Number(input.fbeLeft) || 0) : 0;
    const daily = Math.max(0.1, Number(input.dailyKwh) || 8);
    const price = Math.max(0.01, Number(input.price) || 3.34);
    const dailyFixed = Math.max(0, Number(input.dailyFixed) || 0);
    const fixedUnits = dailyFixed / price;
    const netDaily = daily + fixedUnits;
    const usable = units + fbe;
    const daysCovered = usable / netDaily;
    const runOut = new Date(Date.now() + daysCovered * 86400000);
    const need = netDaily * daysLeft;
    const shortUnits = Math.max(0, need - usable);
    const shortRand = shortUnits * price;
    const buy = Math.max(0, Number(input.buyRand) || 0);
    const buyUnits = price ? buy / price : 0;
    return {
      units: round(units, 1),
      fbe: round(fbe, 1),
      usable: round(usable, 1),
      daily: round(daily, 2),
      netDaily: round(netDaily, 2),
      daysCovered: round(daysCovered, 1),
      daysLeftInMonth: daysLeft,
      runsOut: sastParts(runOut).label,
      reachesMonthEnd: daysCovered + 0.05 >= daysLeft,
      shortUnits: round(shortUnits, 1),
      shortRand: round(shortRand, 2),
      costPerDay: round(netDaily * price, 2),
      buyRand: round(buy, 2),
      buyUnits: round(buyUnits, 1),
      buyDays: round(buyUnits / netDaily, 1),
      price: price,
      basis: "Days left include today. Free Basic Electricity is added only if you tick it (national grant is 50 kWh/month where you are registered — metres vary). A daily fixed charge, if your tariff has one, is converted to units at the energy rate. Load shedding is not subtracting usage: the national stage is 0."
    };
  }

  function rainLitres(roofM2, mm, coeff) {
    const c = coeff == null ? 0.8 : coeff;
    const litres = Math.max(0, Number(roofM2) || 0) * Math.max(0, Number(mm) || 0) * c;
    return {
      litres: round(litres, 0),
      roof: Number(roofM2) || 0,
      mm: round(mm, 1),
      coeff: c,
      basis: "1 mm of rain on 1 m² is 1 litre. 0.8 allows for gutter loss and a dirty roof. This is what you can catch, not what the tap will give you."
    };
  }

  function foodGap(people, spend) {
    const n = Math.max(1, Number(people) || 1);
    const fpl = n * FOOD.fpl;
    const child = n * FOOD.child;
    const proRataNutrition = FOOD.nutritional7 / 7 * n;
    const spendN = Number(spend);
    return {
      people: n,
      foodPovertyLine: round(fpl, 2),
      childCost: round(child, 2),
      basket: FOOD.basket,
      nutritionProRata: round(proRataNutrition, 2),
      spend: Number.isFinite(spendN) ? round(spendN, 2) : null,
      shortOfLine: Number.isFinite(spendN) ? round(fpl - spendN, 2) : null,
      source: FOOD.basketSource,
      povertySource: FOOD.povertySource,
      note: "The PMBEJD basket is one tracked household basket, not a per-person price. The child figure and the food poverty line are the per-person comparisons. A 7-person nutritional basket divided by 7 is only a rough share."
    };
  }

  function leakTest(r1, r2, hours) {
    const a = Number(r1);
    const b = Number(r2);
    const h = Math.max(0.1, Number(hours) || 1);
    if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) {
      return { ok: false, reason: "Second reading must be a higher meter number than the first." };
    }
    const kl = b - a;
    const litres = kl * 1000;
    const perHour = litres / h;
    const perDay = perHour * 24;
    return {
      ok: true,
      kl: round(kl, 3),
      litres: round(litres, 1),
      perHour: round(perHour, 2),
      perDay: round(perDay, 1),
      leak: perHour > 1,
      basis: "Close every tap, note the meter, wait, note it again. More than about 1 litre an hour with everything off is a leak, a toilet cistern, or a dripping geyser. Municipal meters are usually in kilolitres."
    };
  }

  function solarEstimate(kW, radiationMj, price, systemCost) {
    const kw = Math.max(0, Number(kW) || 0);
    const rad = Math.max(0, Number(radiationMj) || 0);
    const m2 = kw * 5;
    const kwh = rad * m2 * 0.18 * 0.75 / 3.6;
    const rate = Math.max(0, Number(price) || 0);
    const save = kwh * rate;
    const cost = Number(systemCost);
    const paybackYears = Number.isFinite(cost) && save > 0 ? cost / (save * 365) : null;
    return {
      kw: kw,
      kwh: round(kwh, 2),
      save: round(save, 2),
      paybackYears: paybackYears == null ? null : round(paybackYears, 1),
      basis: "Rough yield: panel area ≈ 5 m² per kW, 18% module efficiency, 25% system loss, Open-Meteo shortwave radiation in MJ/m². Not an installer quote. Payback ignores batteries, tariffs changing, and cloudy weeks."
    };
  }

  function aqiBand(aqi) {
    const n = Number(aqi);
    if (!Number.isFinite(n)) return { band: "unknown", label: "No reading", level: "muted" };
    if (n <= 50) return { band: "good", label: "Good", level: "ok" };
    if (n <= 100) return { band: "moderate", label: "Moderate", level: "warn" };
    if (n <= 150) return { band: "sensitive", label: "Unhealthy for sensitive groups", level: "bad" };
    if (n <= 200) return { band: "unhealthy", label: "Unhealthy", level: "bad" };
    return { band: "very", label: "Very unhealthy", level: "bad" };
  }

  function weatherLabel(code) {
    return (WMO[code] || ["Weather", "Weather code " + code])[1];
  }

  function placeBlob(place) {
    return norm([place && place.name, place && place.admin1, place && place.admin2, place && place.metro].filter(Boolean).join(" "));
  }

  function isJoburgContext(place) {
    const b = placeBlob(place);
    if (!b) return false;
    if (/cape town|western cape|durban|ethekwini|kwazulu|eastern cape|free state|bloemfontein|mangaung|polokwane|limpopo|mpumalanga|nelspruit|mbombela/.test(b)
        && !/johannesburg|gauteng|soweto|sandton|alexandra|randburg/.test(b)) return false;
    return /johannesburg|gauteng|joburg|soweto|sandton|alexandra|randburg|roodepoort|midrand|ekurhuleni|germiston|pretoria|tshwane/.test(b) || place.metro === "joburg";
  }

  function hits(place, items) {
    const n = norm(place && place.name);
    if (!n) return [];
    return (items || []).filter(function (item) {
      return (item.match || []).some(function (m) {
        const mm = norm(m);
        return mm && n.indexOf(mm) !== -1;
      });
    });
  }

  function weatherThreats(daily) {
    const out = [];
    (daily || []).forEach(function (d) {
      if (Number(d.gusts) >= 60) {
        out.push({
          severity: "warn",
          kind: "wind",
          title: "Strong wind " + d.date,
          detail: "Gusts up to " + Math.round(d.gusts) + " km/h. Secure roof sheets, tanks and loose yard objects. Trees on lines are how a calm national grid still blacks out a street.",
          date: d.date
        });
      }
      if (Number(d.precip_sum) >= 15 && Number(d.precip_prob) >= 50) {
        out.push({
          severity: Number(d.precip_sum) >= 30 ? "bad" : "warn",
          kind: "rain",
          title: "Heavy rain risk " + d.date,
          detail: Math.round(d.precip_prob) + "% chance, about " + round(d.precip_sum, 1) + " mm. Do not cross flooded roads or low bridges. Informal settlements and basements flood first.",
          date: d.date
        });
      } else if (Number(d.precip_prob) >= 70 && Number(d.precip_sum) >= 8) {
        out.push({
          severity: "warn",
          kind: "rain",
          title: "Wet day " + d.date,
          detail: Math.round(d.precip_prob) + "% chance of about " + round(d.precip_sum, 1) + " mm.",
          date: d.date
        });
      }
      if (Number(d.uv) >= 8) {
        out.push({
          severity: "info",
          kind: "uv",
          title: "High UV " + d.date,
          detail: "UV index " + round(d.uv, 1) + ". Hat, shade and water for outdoor work between about 10:00 and 15:00. Children burn faster than the forecast looks.",
          date: d.date
        });
      }
      if (Number(d.tmax) >= 32) {
        out.push({
          severity: "warn",
          kind: "heat",
          title: "Hot day " + d.date,
          detail: "Up to " + Math.round(d.tmax) + "°C. Check on older neighbours. Do heavy work early.",
          date: d.date
        });
      }
    });
    return out;
  }

  function tariffForPlace(place) {
    const b = placeBlob(place);
    if (/cape town|western cape|stellenbosch|khayelitsha|mitchells plain/.test(b)) return { elec: "cape_town_domestic", water: "cape_town" };
    if (/durban|ethekwini|umhlanga|pinetown|kwazulu/.test(b)) return { elec: "ethekwini", water: "custom" };
    if (/pretoria|tshwane|centurion|soshanguve|mamelodi|hammanskraal/.test(b)) return { elec: "tshwane_low", water: "custom" };
    if (/ekurhuleni|germiston|kempton|benoni|boksburg|springs|tembisa|vosloorus|katlehong/.test(b)) return { elec: "ekurhuleni", water: "custom" };
    if (/johannesburg|joburg|soweto|sandton|alexandra|randburg|roodepoort|midrand|gauteng/.test(b) || (place && place.metro === "joburg")) {
      return { elec: "city_power", water: "johannesburg" };
    }
    return { elec: "eskom_homelight_60", water: "custom" };
  }

  function matchService(place, snapshot) {
    const snap = snapshot || {};
    const joburg = isJoburgContext(place) || (place && place.metro === "joburg");
    const name = norm(place && place.name);
    const broadCity = !name || /^(johannesburg|joburg|city of johannesburg|gauteng)$/.test(name);
    if (!joburg || broadCity) {
      return {
        joburg: joburg,
        broad: broadCity,
        water: [],
        power: [],
        planned: [],
        reservoirs: [],
        restored: []
      };
    }
    return {
      joburg: true,
      broad: false,
      water: hits(place, snap.water_outages),
      power: hits(place, snap.power_outages),
      planned: hits(place, snap.planned_power),
      reservoirs: hits(place, snap.reservoir_strain),
      restored: hits(place, snap.power_restored)
    };
  }

  function leadStory(place, snapshot, weather, when) {
    const hit = matchService(place, snapshot);
    const threats = weatherThreats(weather && weather.daily);
    const air = weather && weather.air;
    const airBand = air ? aqiBand(air.us_aqi) : null;
    const stories = [];

    hit.water.forEach(function (w) {
      stories.push({
        severity: w.severity || "bad",
        kind: "water",
        kicker: "Water · " + (place.name || "your suburb"),
        title: w.title,
        detail: w.detail,
        actions: w.actions || [],
        source: w.source,
        via: w.via,
        tel: w.tel,
        telLabel: w.telLabel
      });
    });
    hit.reservoirs.forEach(function (r) {
      stories.push({
        severity: "warn",
        kind: "pressure",
        kicker: "Pressure · " + (place.name || ""),
        title: r.title,
        detail: r.detail,
        actions: r.actions || ["Fill storage while the tap still runs, preferably late at night.", "Expect weaker pressure around 06:00–09:00 and 17:00–21:00."],
        source: r.source,
        via: r.via
      });
    });
    hit.power.forEach(function (p) {
      stories.push({
        severity: p.severity || "bad",
        kind: "power",
        kicker: "City Power · " + (place.name || ""),
        title: p.title,
        detail: p.detail,
        actions: p.actions || [
          "Keep the fridge closed. A full freezer holds for several hours.",
          "Charge a phone from a car or a neighbour if you still can.",
          "Call City Power and ask for the reference number."
        ],
        source: p.source,
        via: p.via,
        tel: "0114907484",
        telLabel: "Call City Power"
      });
    });
    hit.planned.forEach(function (p) {
      stories.push({
        severity: "warn",
        kind: "planned-power",
        kicker: "Planned power",
        title: p.title,
        detail: p.detail,
        actions: [
          "Charge phones and power banks before the window.",
          "If a pump or geyser needs power, run it while the lights are still on.",
          "The scraped notice gave an end time, not a start time. Open the City Power post before you plan the day around it."
        ],
        source: p.source,
        via: p.via,
        end: p.end
      });
    });
    if (hit.restored.length && !hit.power.length) {
      hit.restored.forEach(function (r) {
        stories.push({
          severity: "info",
          kind: "restored",
          kicker: "Power notice",
          title: r.title,
          detail: r.detail,
          actions: ["If your block is still dark, the restoration did not reach you. Call City Power — do not wait on the tweet."],
          source: r.source,
          via: r.via,
          tel: "0114907484",
          telLabel: "Call City Power"
        });
      });
    }
    threats.filter(function (t) { return t.kind !== "uv"; }).forEach(function (t) {
      stories.push({
        severity: t.severity === "bad" ? "bad" : t.severity === "warn" ? "warn" : "info",
        kind: t.kind,
        kicker: "Weather",
        title: t.title,
        detail: t.detail,
        actions: t.kind === "rain"
          ? ["Stay off flooded roads.", "Lift electrics off the floor if you are in a low house.", "Check the neighbour in a shack or a basement flat."]
          : ["Tie down sheets, tanks and trampolines.", "Have a torch ready in case a tree takes the line."],
        source: "Open-Meteo forecast",
        via: weather && weather.source,
        date: t.date
      });
    });
    if (airBand && airBand.level === "bad") {
      stories.push({
        severity: "warn",
        kind: "air",
        kicker: "Air",
        title: "US AQI " + Math.round(air.us_aqi) + " — " + airBand.label,
        detail: "PM2.5 " + air.pm2_5 + " µg/m³. People with asthma, older people and children should ease off outdoor exercise until it drops.",
        actions: ["Keep windows shut if the indoor air is cleaner.", "Do not burn refuse — it makes the street worse."],
        source: "Open-Meteo air quality (CAMS)",
        via: "US AQI scale"
      });
    }

    const rank = { critical: 0, bad: 1, warn: 2, info: 3 };
    stories.sort(function (a, b) { return (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9); });
    const tou = touSlot(when);
    return {
      hit: hit,
      stories: stories,
      top: stories[0] || null,
      tou: tou,
      weatherThreats: threats,
      airBand: airBand,
      when: sastParts(when)
    };
  }

  function preparePlan(place, snapshot, weather, profile, when) {
    const lead = leadStory(place, snapshot, weather, when);
    const people = Math.max(1, Number(profile && profile.people) || 1);
    const stored = Math.max(0, Number(profile && profile.storageL) || 0);
    const drinkNeed = people * 5;
    const washNeed = people * 15;
    const totalNeed = drinkNeed + washNeed;
    const gap = Math.max(0, totalNeed - stored);
    const tasks = [];
    const hasWaterCrisis = lead.stories.some(function (s) { return s.kind === "water" && (s.severity === "critical" || s.severity === "bad"); });
    const contamination = lead.stories.some(function (s) { return s.kind === "water" && /do not use/i.test(s.title); });
    const hasPower = lead.stories.some(function (s) { return s.kind === "power" || s.kind === "planned-power"; });

    if (contamination) {
      tasks.push({ id: "stop-taps", mins: 1, must: true, title: "Stop using the taps for drinking, cooking, teeth and baby bottles", detail: "Johannesburg Water said not to use the water for household purposes. Boiling is not a substitute for that notice." });
      tasks.push({ id: "stored", mins: 5, must: true, title: "Use stored water or the tanker, not the tap", detail: "You have " + stored + " L stored. Drinking need for one day is " + drinkNeed + " L (" + people + " people × 5 L)." });
    } else if (hasWaterCrisis || gap > 0) {
      tasks.push({
        id: "fill",
        mins: gap > 0 ? Math.max(5, Math.round(gap / 8)) : 2,
        must: true,
        title: gap > 0 ? "Fill " + gap + " L while the tap still runs" : "Storage covers one day — top up if pressure is good",
        detail: "One day for " + people + " people: " + drinkNeed + " L drinking + " + washNeed + " L washing = " + totalNeed + " L. You have " + stored + " L. 8 L/min is a healthy tap; a weak tap takes longer."
      });
    }
    if (hasPower) {
      tasks.push({ id: "charge", mins: 20, must: true, title: "Charge phones and a power bank", detail: "A planned or active City Power fault, not national load shedding." });
      tasks.push({ id: "fridge", mins: 5, must: false, title: "Don't open the fridge", detail: "A closed fridge keeps food for a few hours. Eat the leftovers first if the outage runs into tomorrow." });
    }
    lead.weatherThreats.filter(function (t) { return t.kind === "wind" || t.kind === "rain"; }).slice(0, 2).forEach(function (t) {
      tasks.push({ id: t.kind + t.date, mins: 15, must: t.severity !== "info", title: t.title, detail: t.detail });
    });
    if (lead.tou && lead.tou.slot === "offpeak") {
      tasks.push({ id: "geyser", mins: 5, must: false, title: "Homeflex: this hour is off-peak", detail: "If you are on Homeflex, heating the geyser now is the cheap window. A 4 kWh heat costs about " + money(4 * lead.tou.offpeak) + " now versus " + money(4 * lead.tou.peak) + " in tomorrow's peak. Flat-rate meters do not save by waiting." });
    } else if (lead.tou && lead.tou.slot === "peak") {
      tasks.push({ id: "wait-geyser", mins: 1, must: false, title: "Homeflex: delay the geyser", detail: "Peak is " + money(lead.tou.peak) + "/kWh right now. Off-peak (about 22:00–06:00) is " + money(lead.tou.offpeak) + "/kWh. Only matters if your meter is time-of-use." });
    }
    tasks.push({ id: "neighbour", mins: 5, must: false, title: "Tell one neighbour", detail: "The person least likely to have seen the notice. A WhatsApp to the street group counts." });

    const mustMins = tasks.filter(function (t) { return t.must; }).reduce(function (s, t) { return s + t.mins; }, 0);
    return {
      lead: lead,
      tasks: tasks,
      people: people,
      drinkNeed: drinkNeed,
      washNeed: washNeed,
      totalNeed: totalNeed,
      stored: stored,
      gap: gap,
      mustMins: mustMins,
      waterNote: contamination
        ? "Do not fill from the tap. The notice is a quality notice, not a dry-tap notice."
        : gap > 0
          ? "Storage is short by " + gap + " L for one day."
          : "Stored water covers one day at 20 L per person."
    };
  }

  function receiptId(now) {
    const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let n = (now || Date.now()) % 2176782336;
    let s = "";
    for (let i = 0; i < 4; i++) {
      s = alphabet[n % alphabet.length] + s;
      n = Math.floor(n / alphabet.length);
    }
    return "SW-" + s;
  }

  return {
    VAT: VAT,
    TZ: TZ,
    ELECTRICITY: ELECTRICITY,
    WATER: WATER,
    FOOD: FOOD,
    round: round,
    money: money,
    norm: norm,
    sastParts: sastParts,
    season: season,
    touSlot: touSlot,
    cheapestHours: cheapestHours,
    electricityBill: electricityBill,
    waterBill: waterBill,
    prepaidRunway: prepaidRunway,
    rainLitres: rainLitres,
    foodGap: foodGap,
    leakTest: leakTest,
    solarEstimate: solarEstimate,
    aqiBand: aqiBand,
    weatherLabel: weatherLabel,
    tariffForPlace: tariffForPlace,
    matchService: matchService,
    weatherThreats: weatherThreats,
    leadStory: leadStory,
    preparePlan: preparePlan,
    isJoburgContext: isJoburgContext,
    receiptId: receiptId,
    marginalRate: marginalRate
  };
});
