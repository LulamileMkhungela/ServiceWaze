import fs from "fs";
import E from "../assets/engine.js";

const snap = JSON.parse(fs.readFileSync(new URL("../data/snapshot.json", import.meta.url), "utf8"));
let failed = 0;
function ok(name, cond) {
  if (!cond) { failed += 1; console.error("FAIL", name); }
  else console.log("ok", name);
}
const w = E.waterBill(20, "johannesburg");
ok("joburg 20kl", Math.abs(w.total - 509.55) < 0.02);
const e = E.electricityBill(600, "city_power");
ok("city power 600", Math.abs(e.total - 2421.94) < 0.05);
ok("cape town 15", Math.abs(E.waterBill(15, "cape_town").total - 544.56) < 0.05);
ok("offpeak", E.touSlot(new Date("2026-09-24T20:30:00Z")).slot === "offpeak");
ok("peak", E.touSlot(new Date("2026-09-25T06:00:00Z")).slot === "peak");
const bez = E.leadStory({ name: "Bezuidenhout Valley", admin1: "Gauteng", metro: "joburg" }, snap, null, new Date("2026-09-24T20:30:00Z"));
ok("bez critical", bez.top && bez.top.severity === "critical");
const alex = E.leadStory({ name: "Alexandra", admin1: "Gauteng", metro: "joburg" }, snap, { daily: snap.weather_snapshot.cities.johannesburg.daily }, new Date("2026-09-24T20:30:00Z"));
ok("alex water", alex.stories.some((s) => s.kind === "water"));
ok("alex planned", alex.stories.some((s) => s.kind === "planned-power"));
const cpt = E.leadStory({ name: "Cape Town", admin1: "Western Cape" }, snap, { daily: snap.weather_snapshot.cities["cape town"].daily, air: snap.air_snapshot.cities["cape town"] }, new Date());
ok("cpt no joburg water", !cpt.stories.some((s) => s.kind === "water"));
ok("cpt air", cpt.stories.some((s) => s.kind === "air"));
const plan = E.preparePlan({ name: "Bezuidenhout Valley", metro: "joburg", admin1: "Gauteng" }, snap, { daily: [] }, { people: 4, storageL: 0 }, new Date());
ok("do not fill", /Do not fill/.test(plan.waterNote));
if (failed) process.exit(1);
