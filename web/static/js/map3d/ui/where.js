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
// English unless the interface is in Russian: ПВО and the rest only in the RU version
const ru = () => window.hhI18n?.language === "ru";
const L = (en, rus) => (ru() ? rus : en);
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
    return { place: best ? best.label : r < c.wall_radius + REACH ? L("Outskirts of Hadley's Hope", "Окраины Хэдли") : L("Wilderness", "Дикие земли"), region: "LV-426" };
  }
  if (i === 3 && state.klyaksaPlanData) {
    const plan = state.klyaksaPlanData;
    const dir = worldPointToBody(3, state.camera.position).normalize();
    let best = null;
    for (const c of state.klyaksaPlanData.cities) {
      const d = dir.angleTo(dirAt(c.at[0], c.at[1], R)) * R;
      if (d < c.wall + REACH && (!best || d < best.d)) best = { d, c };
    }
    if (best) return { place: best.c.name, region: "Klyaksa", city: best.c.id, inside: best.d < best.c.wall };
    const port = (state.klyaksaShipping?.ports || []).find((P) => dir.angleTo(dirAt(P.p.x, P.p.y, R)) * R < 700);
    return { place: port ? L(`Port of ${plan.cities.find((c) => c.id === port.p.city)?.name || "Klyaksa"}`, `Порт ${plan.cities.find((c) => c.id === port.p.city)?.name || ""}`) : L("Wilderness", "Дикие земли"), region: L("Klyaksa", "Клякса") };
  }
  return { place: "Surface", region: name };
}

/** The Klyaksa city the camera is at, or the nearest one: where operator commands go on Klyaksa. */
export function klyaksaCityHere() {
  const plan = state.klyaksaPlanData;
  if (!plan || state.activeBody !== 3) return null;
  const R = state.solarSystem.specs[3].radius, dir = worldPointToBody(3, state.camera.position).normalize();
  let best = null;
  for (const c of plan.cities) {
    const d = dir.angleTo(dirAt(c.at[0], c.at[1], R));
    if (!best || d < best.d) best = { d, c };
  }
  return best?.c || null;
}

function hazardsLine(where) {
  const el = document.getElementById("hazards");
  if (!el) return;
  const h = where.city && state.klyaksaState?.cities.find((c) => c.id === where.city)?.hazards;
  if (!h) { el.hidden = true; return; }
  el.hidden = false;
  const pct = (x) => `${Math.round(x * 100)}%`;
  el.innerHTML = [
    `<span>${L("creatine", "креатин")} <b>${h.creatine_t.toFixed(0)} ${L("t", "т")}</b> · ${L("mutation", "мутация")} ${h.mutation.toFixed(1)}</span>`,
    `<span class="${h.aa.on ? "ok" : "bad"}">${L("Air defence", "ПВО")} <b>${h.aa.on ? L("on", "вкл") : L("OFF", "ВЫКЛ")}</b> · ${h.aa.ammo} ${L("shells", "снарядов")} · ${h.aa.kills} ${L("down", "сбито")}</span>`,
    h.migration ? `<span class="warn">${L("herd overhead", "стадо над городом")}: ${h.migrants.filter((m) => m.state === "migrate").length}</span>` : "",
    `<span class="${h.manure_t + h.dome_dirt > 10 ? "warn" : ""}">${L("manure", "навоз")} <b>${h.manure_t.toFixed(1)} ${L("t", "т")}</b> · ${L("dome", "купол")} ${h.dome_dirt.toFixed(0)}% ${L("covered", "в навозе")}</span>`,
    `<span class="${h.plankton > 25 ? "warn" : ""}">${L("plankton", "планктон")} <b>${h.plankton.toFixed(0)}%</b>${h.tide ? L(" · tide", " · прилив") : ""}</span>`,
    `<span class="${h.drunk > 0.5 ? "warn" : ""}">${L("drunk", "пьяны")} <b>${pct(h.drunk)}</b></span>`,
  ].filter(Boolean).join("");
}

function bossBar(where) {
  const box = document.getElementById("boss");
  if (!box) return;
  const city = where.city && state.klyaksaState?.cities.find((c) => c.id === where.city);
  const raid = city?.raid, herd = city?.hazards?.migration;
  const hp = city?.dome_hp ?? 100;
  if (!city || (!raid && !herd && hp >= 99.95)) { box.hidden = true; return; }
  box.hidden = false;
  box.querySelector(".boss-name").textContent = L(`${where.place} dome`, `купол ${where.place}`);
  box.querySelector(".boss-hp").textContent = `${hp.toFixed(1)} %`;
  box.querySelector(".boss-fill").style.width = `${hp}%`;
  box.classList.toggle("low", hp < 30);
  box.querySelector(".boss-info").textContent = !raid
    ? herd ? L(`A migrating herd overhead · ${herd.kills} shot down`, `Над городом стадо · сбито ${herd.kills}`) : L("Repair crews at work", "Ремонт купола")
    : raid.phase === "gather" ? L(`Wild crocodiles gathering: ${raid.size} of them, here in ${raid.left} min`, `Дикие крокодилы собираются: ${raid.size}, здесь через ${raid.left} мин`)
    : raid.phase === "raid" ? L(`Under attack by ${raid.size} crocodiles · ${raid.dome_hits} hits on the glass${raid.hits ? ` · ${raid.hits} things wrecked` : ""}`, `Атака ${raid.size} крокодилов · ${raid.dome_hits} ударов по стеклу${raid.hits ? ` · разрушено ${raid.hits}` : ""}`)
    : L("The flock is flying off", "Стая улетает");
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
