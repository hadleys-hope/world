/** ui/controls: procedural colony viewer. */
import { state } from "../state.js";
import { focusSelection } from '../camera.js';
import { polar, sph } from "../geometry/planet.js";
import { resize } from "../render/frame.js";
import { applyLayers, onState } from "../render/state-sync.js";
import { flyTo, renderInfo } from "./inspection.js";
import { renderSide } from "./telemetry.js";

export async function checkToken() {
  const r = await (
    await fetch("/cmd", {
      method: "POST",
      body: JSON.stringify({ cmd: "auth", token: state.ADMIN }),
    })
  ).json();
  state.tokenState.textContent = !r.protected
    ? "open server"
    : r.ok
      ? "control enabled"
      : "view only";
  state.tokenState.className = r.ok ? "ok" : "warn";
}

export function toast(text) {
  const t = document.getElementById("toast");
  t.textContent = text;
  t.style.display = "block";
  clearTimeout(t._h);
  t._h = setTimeout(() => {
    t.style.display = "none";
  }, 3500);
}

export function selectPanel(name) {
  document.querySelectorAll("[data-panel]").forEach((b) => {
    const on = b.dataset.panel === name;
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
  });
  document
    .querySelectorAll(".hud-panel")
    .forEach((p) => (p.hidden = p.id !== "panel-" + name));
}

export function updateMapKey() {
  const items = [];
  const add = (color, label) =>
    items.push(`<span><i style="--swatch:${color}"></i>${label}</span>`);
  if (state.layers.underground) {
    add("#4b9bb9", "Potable");
    add("#b99865", "Sanitary");
    add("#71988b", "Storm");
    if (state.layers.water) add("#c8f6ff", "Flow direction");
  }
  if (state.layers.power) add("#f2c14e", "3φ power / moving load");
  if (state.layers.packets) add("#4fd1c5", "Fibre / data packets");
  if (state.layers.water && !state.layers.underground) {
    add("#64c6d4", "Water / direction of flow");
    add("#b6dfff", "Ice / supply blocked");
  }
  if (state.layers.issues) add("#e2574d", "Fault");
  if (state.layers.nonet) add("#d98082", "Offline");
  if (state.layers.ups) add("#4fd1c5", "UPS");
  if (
    !state.layers.underground &&
    !state.layers.power &&
    !state.layers.packets
  ) {
    add("#a7af94", "Habitat");
    add("#ffd18c", "Lighting");
  }
  document.getElementById("map-key").innerHTML = items.join("");
}

export function sectorCards(s) {
  const total = state.G.houses.x.length / state.G.cfg.sectors;
  document.getElementById("sector-cards").innerHTML = s.sectors
    .map(
      (x, i) =>
        `<button class="sector-card" data-district="${i}" title="Fly to district ${i + 1}"><strong>District ${String(i + 1).padStart(2, "0")} <span class="${x.min_t < 0 ? "bad" : x.avg_t < 15 ? "warn" : "ok"}">${x.avg_t}°</span></strong><small>Power ${x.power_ok}/${total} · Water ${x.water_ok}/${total}</small><span class="service-bars" aria-hidden="true"><span class="${x.power_ok === total ? "good" : "warn"}"></span><span class="${x.water_ok === total ? "good" : "warn"}"></span><span class="${x.net_ok === total ? "good" : "warn"}"></span></span></button>`,
    )
    .join("");
}

export async function loadGeom() {
  state.G = await (await fetch("/geometry")).json();
  state.TER = {
    hub: state.G.cfg.hub_radius,
    row0: state.G.cfg.house_radius_min,
    step: state.G.cfg.house_ring_step,
    rows: state.G.cfg.house_rows,
    ring: state.G.cfg.ring_road_radius,
    wall: state.G.cfg.wall_radius,
  };
}

export async function poll() {
  try {
    const s = await (await fetch("/state")).json();
    const first = !state.S;
    state.prevS = state.S;
    state.S = s;
    const now = performance.now();
    state.pollGap = state.lastPoll ? Math.min(1200, now - state.lastPoll) : 300;
    state.lastPoll = now;
    renderSide(s);
    onState(s, first);
    const roster = document.getElementById('colonist-roster');
    if (s.citizens) {
      if (roster.options.length !== s.citizens.length) {
        roster.replaceChildren(...s.citizens.map(c => new Option('', String(c.id))));
      }
      s.citizens.forEach((c, i) => {
        const label = `#${c.id} · ${c.profession} · ${c.state}`;
        if (roster.options[i].text !== label) roster.options[i].text = label;
      });
      if (state.selected?.kind === 'person') roster.value = String(state.selected.id);
    }
    renderInfo();
  } catch (e) {
    console.error("poll failed", e);
    document.getElementById("banner").textContent =
      "update failed: " + ((e && e.message) || e);
  }
  setTimeout(poll, 300);
}

export function initialize() {
  state.ADMIN =
    new URLSearchParams(location.search).get("admin") ||
    localStorage.getItem("hh_admin") ||
    "";
  if (state.ADMIN) localStorage.setItem("hh_admin", state.ADMIN);
  state.G = null;
  state.S = null;
  state.prevS = null;
  state.lastPoll = 0;
  state.pollGap = 300;
  state.tokenEl = document.getElementById("token");
  state.tokenState = document.getElementById("tokenstate");
  state.tokenEl.value = state.ADMIN;
  document.getElementById("tokenbtn").onclick = () => {
    state.ADMIN = state.tokenEl.value.trim();
    localStorage.setItem("hh_admin", state.ADMIN);
    checkToken();
  };
  checkToken();
  state.post = async (o) => {
    const r = await fetch("/cmd", {
      method: "POST",
      body: JSON.stringify({ ...o, token: state.ADMIN }),
    });
    if (r.status === 403) {
      state.tokenState.textContent = "view only: paste the admin token above";
      state.tokenState.className = "bad";
    }
    return r;
  };
  document.getElementById("pause").onclick = () => state.post({ cmd: "pause" });
  document.getElementById('npc-sector').onclick = () => flyTo(...polar(32, 254), 260);
  document.querySelectorAll('[data-pedestrian-edge]').forEach(button => {
    button.onclick = async () => {
      const edge = button.dataset.pedestrianEdge;
      try {
        const response = await state.post({ cmd: 'pedestrian_connection', edge, closed: !state.S?.pedestrians?.closed.includes(edge) });
        if (!response.ok) toast(response.status === 403 ? 'Нужен токен управления.' : 'Не удалось изменить доступность пути.');
      } catch { toast('Не удалось связаться с сервером.'); }
    };
  });
  const timeCommand = async command => {
    try {
      const response = await state.post(command);
      if (!response.ok) toast(response.status === 403 ? 'Нужен токен управления.' : 'Проверьте время: формат ЧЧ:ММ.');
    } catch { toast('Не удалось связаться с сервером.'); }
  };
  document.getElementById('run-until').onclick = () => {
    const input = document.getElementById('pause-at-time');
    if (input.reportValidity()) timeCommand({ cmd: 'pause_at', value: input.value });
  };
  document.getElementById('cancel-time-stop').onclick = () => timeCommand({ cmd: 'pause_at', value: null });
  document.getElementById('slow-resume').onclick = () => timeCommand({ cmd: 'speed', value: 1 });
  const stopFollowing = () => {
    state.followColonist = null;
    document.getElementById('stop-colonist-follow').hidden = true;
  };
  document.getElementById('stop-colonist-follow').onclick = stopFollowing;
  const inspectCitizen = id => {
    if (state.drive) { toast('Park the vehicle before inspecting a colonist.'); return; }
    const profile = state.S?.citizens?.find(c => c.id === id);
    if (!profile) { toast('Residents are loading.'); return; }
    state.activeBody = 2;
    state.systemView = false;
    state.world.visible = true;
    state.layers.people = true;
    document.querySelector('[data-l="people"]').checked = true;
    state.colonistGroup.visible = true;
    state.selected = { kind: 'person', id };
    const model = state.colonists.get(id);
    if (model) focusSelection();
    else flyTo(profile.x, profile.y, 35);
    state.followColonist = { id, position: model ? model.root.position.clone() : sph(profile.x, profile.y, profile.height ?? .1) };
    document.getElementById('colonist-roster').value = String(id);
    document.getElementById('stop-colonist-follow').hidden = false;
    renderInfo();
    toast(profile.indoors ? `Resident #${id} is inside. Profile remains available; Escape stops following.` : 'Following colonist. Click Inspect colonist again for the next one. Escape stops following.');
  };
  document.getElementById('colonist-roster').onchange = e => inspectCitizen(Number(e.target.value));
  document.getElementById('inspect-colonist').onclick = () => {
    const outdoors = [...(state.colonists?.keys() || [])].sort((a, b) => a - b);
    const ids = outdoors.length ? outdoors : (state.S?.citizens || []).map(c => c.id);
    const current = state.selected?.kind === 'person' ? ids.indexOf(state.selected.id) : -1;
    inspectCitizen(ids[(current + 1) % ids.length]);
  };
  document.querySelectorAll("button[data-i]").forEach(
    (b) =>
      (b.onclick = async () => {
        const r = await fetch("/cmd", {
          method: "POST",
          body: JSON.stringify({
            cmd: "inject",
            value: b.dataset.i,
            token: state.ADMIN,
          }),
        });
        if (r.status === 403) {
          toast("view only: paste the admin token");
          return;
        }
        const info = await r.json();
        toast(info.text || b.dataset.i);
        if (info.x !== undefined && state.G) flyTo(info.x, info.y, 420);
      }),
  );
  document.getElementById("reset").onclick = () => {
    if (confirm("Abandon this colony and found a new one? History is kept.")) {
      state.post({ cmd: "reset" });
      state.selected = null;
    }
  };
  state.speedEl = document.getElementById("speed");
  state.speedV = document.getElementById("speedv");
  state.sliderToSpeed = (v) =>
    v === 0 ? 0 : Math.round(Math.exp((Math.log(600) * v) / 100));
  state.speedToSlider = (s) =>
    s <= 0 ? 0 : Math.round((Math.log(Math.max(1, s)) / Math.log(600)) * 100);
  state.speedEl.oninput = () => {
    state.speedV.textContent =
      state.sliderToSpeed(+state.speedEl.value) + " min/s";
  };
  state.speedEl.onchange = () =>
    state.post({
      cmd: "speed",
      value: state.sliderToSpeed(+state.speedEl.value),
    });
  state.layers = {};
  document.querySelectorAll("#layers input").forEach((c) => {
    state.layers[c.dataset.l] = c.checked;
    c.onchange = () => {
      state.layers[c.dataset.l] = c.checked;
      applyLayers();
    };
  });
  document.querySelectorAll("[data-panel]").forEach((b) => {
    b.onclick = () => selectPanel(b.dataset.panel);
    b.onkeydown = (e) => {
      const names = ["overview", "layers", "places", "operations"];
      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
        e.preventDefault();
        let i = names.indexOf(b.dataset.panel);
        i =
          e.key === "Home"
            ? 0
            : e.key === "End"
              ? 3
              : (i + (e.key === "ArrowRight" ? 1 : 3)) % 4;
        selectPanel(names[i]);
        document.querySelector('[data-panel="' + names[i] + '"]').focus();
      }
    };
  });
  document.getElementById("panel-toggle").onclick = () => {
    const hidden = document.body.classList.toggle("panel-collapsed");
    document
      .getElementById("panel-toggle")
      .setAttribute("aria-expanded", String(!hidden));
    resize();
  };
  state.VIEW_PRESETS = {
    colony: {
      power: true,
      packets: true,
      underground: false,
      nonet: false,
      ups: false,
      heater: false,
      ctrl: false,
      labels: false,
    },
    water: {
      power: false,
      packets: false,
      underground: true,
      water: true,
      nonet: false,
      ups: false,
      ctrl: false,
      labels: false,
    },
    power: {
      power: true,
      packets: false,
      underground: false,
      nonet: false,
      ups: true,
      ctrl: false,
      labels: false,
    },
    network: {
      power: false,
      packets: true,
      underground: false,
      nonet: true,
      ups: false,
      ctrl: true,
      labels: false,
    },
  };
  document.querySelectorAll("[data-view]").forEach(
    (b) =>
      (b.onclick = () => {
        Object.assign(state.layers, state.VIEW_PRESETS[b.dataset.view]);
        document
          .querySelectorAll("#layers input")
          .forEach((c) => (c.checked = !!state.layers[c.dataset.l]));
        document
          .querySelectorAll("[data-view]")
          .forEach((t) => t.setAttribute("aria-pressed", String(t === b)));
        applyLayers();
      }),
  );
  document.querySelectorAll("#layers input").forEach((c) =>
    c.addEventListener("change", () => {
      document
        .querySelectorAll("[data-view]")
        .forEach((b) => b.setAttribute("aria-pressed", "false"));
      updateMapKey();
    }),
  );
  document.addEventListener("keydown", (e) => {
    if (
      e.target.matches("input,textarea,select") ||
      e.ctrlKey ||
      e.metaKey ||
      e.altKey
    )
      return;
    const k = e.key.toLowerCase();
    if (['escape', 'w', 'a', 's', 'd', 'q', 'e', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'home', '0', '1', '2', '3', '4'].includes(k)) stopFollowing();
    if (k === "m") {
      document.getElementById("panel-toggle").click();
    }
    if (k === "c") {
      const box = document.querySelector('[data-l="cutaway"]');
      box.checked = !box.checked;
      box.dispatchEvent(new Event("change"));
    }
  });
  document.getElementById("sector-cards").onclick = (e) => {
    const b = e.target.closest("[data-district]");
    if (b) flyTo(...polar(+b.dataset.district * 60 + 30, 420), 380);
  };
}
