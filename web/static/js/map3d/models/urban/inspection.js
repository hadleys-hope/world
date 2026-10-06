import { dirAt } from "../klyaksa.js";
/** Reuse the existing inspector and navigation controls; no new HUD layout. */
import * as T from "three";
import { state } from "../../state.js";
import { startSailing } from "./marine.js";
import { navigationHUD, focusPoint } from "../../camera.js";
export function pickKlyaksa(ev, click) {
  const el = state.renderer.domElement,
    r = el.getBoundingClientRect(),
    mouse = new T.Vector2(
      ((ev.clientX - r.left) / r.width) * 2 - 1,
      (-(ev.clientY - r.top) / r.height) * 2 + 1,
    );
  state.ray.setFromCamera(mouse, state.camera);
  const candidates = [
      state.klyaksaHouses,
      ...(state.klyaksaBoats || []).map((b) => b.mesh),
    ].filter(Boolean),
    hit = state.ray.intersectObjects(candidates, false)[0],
    tip = document.getElementById("tip");
  if (!hit) {
    tip.style.display = "none";
    return;
  }
  const boat = hit.object.userData.boat,
    meta = boat ? null : state.klyaksaHouseMeta[hit.instanceId];
  const label = boat
    ? boat.name
    : `${meta.city.toUpperCase()} · House ${meta.id + 1} · ${meta.floors} floors`;
  tip.textContent = label;
  tip.style.display = "block";
  tip.style.left = ev.clientX - r.left + 14 + "px";
  tip.style.top = ev.clientY - r.top + 14 + "px";
  if (click) {
    state.selected = {
      kind: boat ? "boat" : "klyaksa-house",
      id: boat ? boat.id : hit.instanceId,
      localPoint: hit.point.clone().sub(state.solarSystem.bodies[3].position),
    };
    renderKlyaksaInfo();
  }
}
export function renderKlyaksaInfo() {
  const selected = state.selected;
  if (!["boat", "klyaksa-house"].includes(selected?.kind)) return false;
  const box = document.getElementById("info"),
    title = document.getElementById("infotitle"),
    body = document.getElementById("infobody");
  body.replaceChildren();
  const row = (name, value) => {
    const p = document.createElement("p");
    p.textContent = `${name}: ${value}`;
    body.append(p);
  };
  if (selected.kind === "boat") {
    const b = state.klyaksaBoats[selected.id];
    title.textContent = b.name;
    row("Control", "WASD / arrows · Esc to exit");
    row("Mode", "Local exploration");
    const button = document.createElement("button");
    button.textContent = "ENTER · Sail";
    button.onclick = () => {
      startSailing(b);
      navigationHUD();
    };
    body.append(button);
  } else {
    const h = state.klyaksaHouseMeta[selected.id],
      c = state.klyaksaPlanData.cities.find((c) => c.id === h.city),
      s = state.klyaksaState?.cities.find((c) => c.id === h.city);
    title.textContent = `${c.name} · House ${h.id + 1}`;
    row("Floors", h.floors);
    row(
      "Indoor temperature",
      s ? `${s.t_in[h.index]} °C` : "Waiting for telemetry",
    );
    row(
      "Electricity",
      s
        ? s.flags[h.index] & 1
          ? "Grid connected"
          : "Power lost"
        : "Waiting for telemetry",
    );
    row(
      "Heating",
      s ? (s.flags[h.index] & 2 ? "On" : "Off") : "Waiting for telemetry",
    );
    row(
      "Controller",
      s
        ? s.flags[h.index] & 4
          ? "External"
          : "Built-in"
        : "Waiting for telemetry",
    );
  }
  box.style.display = "block";
  return true;
}
export function focusKlyaksa() {
  if (!state.selected?.localPoint) return false;
  focusPoint(
    state.selected.localPoint.clone().add(state.solarSystem.bodies[3].position),
    state.selected.kind === "boat" ? 25 : 18,
  );
  return true;
}

/** Navigation shortcuts expose the new locations without changing the authored HUD. */
export function visitKlyaksa(port = false, step = 1) {
  if (state.activeBody !== 3 || state.drive || !state.klyaksaPlanData) return;
  const choices = port ? state.klyaksaPorts : state.klyaksaPlanData.cities;
  if (!choices?.length) return;
  const field = port ? "klyaksaPortVisit" : "klyaksaCityVisit";
  state[field] =
    ((state[field] ?? -1) + step + choices.length) % choices.length;
  const c = choices[state[field]],
    R = state.solarSystem.specs[3].radius,
    x = port ? c.x : c.at[0],
    y = port ? c.y : c.at[1],
    n = dirAt(x, y, R),
    north = dirAt(x, y + 1, R)
      .sub(n)
      .normalize();
  const p = n
    .clone()
    .multiplyScalar(R + (port ? 4 : R * 0.0035 + 12))
    .add(state.solarSystem.bodies[3].position);
  state.systemView = false;
  state.selected = null;
  document.getElementById("info").style.display = "none";
  focusPoint(
    p,
    port ? 240 : c.wall * 1.25,
    n.clone().multiplyScalar(0.8).addScaledVector(north, -0.6),
  );
}
