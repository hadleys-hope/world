/** ui/where: where the camera is, as an open-world game shows it (a city, a plant, the wilderness, orbit,
 * space), and, inside a Klyaksa city under a crocodile raid, its dome's health as a boss bar. */
import { state } from "../state.js";
import { activeCentre } from "../camera.js";
import { normalXY } from "../geometry/planet.js";
import { worldPointToBody } from "../geometry/body-frame.js";
import { dirAt } from "../models/klyaksa.js";
import * as THREE from "three";

const FACILITIES = [
  ["reactor_pos", "Reactor"], ["solar_pos", "Solar field"], ["water_plant_pos", "Water plant"], ["radwaste_pos", "Radwaste store"],
  ["mine_pos", "Mine"], ["waste_station_pos", "Waste station"], ["tower_pos", "Comms tower"],
];
const REACH = 600; // a city's area reaches this far past its wall: crossing it hands over to the next city
const title = (s) => s.charAt(0) + s.slice(1).toLowerCase();
let last = 0, shown = "";
const _v = new THREE.Vector3();

function locate() {
  if (state.systemView) return { place: "Space", region: "solar system" };
  const ss = state.solarSystem, i = state.activeBody;
  const name = i === 2 ? "LV-426" : title(ss?.specs[i]?.name || "planet");
  const R = i === 2 ? state.RP : ss?.specs[i]?.radius || 1;
  const centre = activeCentre();
  const alt = state.camera.position.distanceTo(centre) - R;
  if (alt > Math.max(R * 0.6, 3000)) return { place: "Orbit", region: name };
  if (i === 2 && state.G) {
    _v.copy(state.camera.position).sub(centre).normalize();
    const [x, y] = normalXY(_v), c = state.G.cfg, r = Math.hypot(x, y);
    if (r < c.wall_radius) return { place: "Hadley's Hope", region: "LV-426" };
    let best = null;
    for (const [key, label] of FACILITIES) {
      const p = c[key];
      if (!p) continue;
      const d = Math.hypot(p[0] - x, p[1] - y);
      if (d < 320 && (!best || d < best.d)) best = { d, label };
    }
    return { place: best ? best.label : r < c.wall_radius + REACH ? "Outskirts of Hadley's Hope" : "Wilderness", region: "LV-426" };
  }
  if (i === 3 && state.klyaksaPlanData) {
    const dir = worldPointToBody(3, state.camera.position).normalize();
    let best = null;
    for (const c of state.klyaksaPlanData.cities) {
      const d = dir.angleTo(dirAt(c.at[0], c.at[1], R)) * R;
      if (d < c.wall + REACH && (!best || d < best.d)) best = { d, c };
    }
    if (best) return { place: best.c.name, region: "Klyaksa", city: best.c.id, inside: best.d < best.c.wall };
    return { place: "Wilderness", region: "Klyaksa" };
  }
  return { place: "Surface", region: name };
}

function hazardsLine(where) {
  const el = document.getElementById("hazards");
  if (!el) return;
  const h = where.city && state.klyaksaState?.cities.find((c) => c.id === where.city)?.hazards;
  if (!h) { el.hidden = true; return; }
  el.hidden = false;
  const pct = (x) => `${Math.round(x * 100)}%`;
  el.innerHTML = [
    `<span title="creatine mined; the fauna mutates with it">creatine <b>${h.creatine_t.toFixed(0)} t</b> · mutation ${h.mutation.toFixed(1)}</span>`,
    `<span class="${h.aa.on ? "ok" : "bad"}" title="air defence">ПВО <b>${h.aa.on ? "on" : "OFF"}</b> · ${h.aa.ammo} shells · ${h.aa.kills} down</span>`,
    h.migration ? `<span class="warn">herd overhead: ${h.migrants.filter((m) => m.state === "migrate").length}</span>` : "",
    `<span class="${h.manure_t + h.dome_dirt > 10 ? "warn" : ""}">manure <b>${h.manure_t.toFixed(1)} t</b> · dome ${h.dome_dirt.toFixed(0)}% covered</span>`,
    `<span class="${h.plankton > 25 ? "warn" : ""}">plankton <b>${h.plankton.toFixed(0)}%</b>${h.tide ? " · tide" : ""}</span>`,
    `<span class="${h.drunk > 0.5 ? "warn" : ""}">drunk <b>${pct(h.drunk)}</b></span>`,
  ].filter(Boolean).join("");
}

function bossBar(where) {
  const box = document.getElementById("boss");
  if (!box) return;
  const city = where.city && state.klyaksaState?.cities.find((c) => c.id === where.city);
  const raid = city?.raid;
  if (!raid) { box.hidden = true; return; }
  const hp = city.dome_hp ?? 100;
  box.hidden = false;
  box.querySelector(".boss-name").textContent = `${where.place} dome`;
  box.querySelector(".boss-hp").textContent = `${hp.toFixed(1)} %`;
  box.querySelector(".boss-fill").style.width = `${hp}%`;
  box.classList.toggle("low", hp < 30);
  box.querySelector(".boss-info").textContent =
    raid.phase === "gather" ? `Wild crocodiles gathering: ${raid.size} of them, here in ${raid.left} min`
    : raid.phase === "raid" ? `Under attack by ${raid.size} crocodiles · ${raid.dome_hits} hits on the glass${raid.hits ? ` · ${raid.hits} things wrecked` : ""}`
    : "The flock is flying off";
}

export function updateWhere(now) {
  if (now - last < 250) return;
  last = now;
  const where = locate();
  const text = `${where.place} · ${where.region}`;
  const el = document.getElementById("where");
  if (el && text !== shown) {
    el.querySelector("b").textContent = where.place;
    el.querySelector("span").textContent = where.region;
    el.classList.remove("enter");
    void el.offsetWidth;            // restart the fade-in when the place changes
    el.classList.add("enter");
    shown = text;
  }
  bossBar(where);
  hazardsLine(where);
}
