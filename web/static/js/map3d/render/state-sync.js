/** render/state-sync: procedural colony viewer. */
import { state } from "../state.js";
import { build } from "../build.js";
import { xyNormal } from "../geometry/planet.js";
import { setPoints } from "../geometry/objects.js";
import {
  polar,
  quatAt,
  sph,
  surfaceHeight,
  terrainH,
} from "../geometry/planet.js";
import { freightVehicle, updateCargo } from "../models/cargo.js";
import { updatePhysicalState } from "../models/industry.js";
import { updateOcean } from "../models/ocean.js";
import { detailedVehicle } from "../models/vehicles.js";
import { updateMapKey } from "../ui/controls.js";
import { flyTo, renderInfo } from "../ui/inspection.js";
import { retext, textSprite } from "./textures.js";
import { clickable } from "./world.js";
import * as THREE from "three";

export function applyLayers() {
  state.M.roof.opacity = state.layers.cutaway ? 0.62 : 0.84;
  updateMapKey();
  if (!state.markers.issues) return;
  state.spanLines.mesh.visible = true;
  state.netLines.mesh.visible = true;
  for (const key of ["feederLayer", "trunkLayer", "towerLayer", "solarLayer"])
    if (state.hub[key]) state.hub[key].mesh.visible = true;
  if (state.hub.cableTowerLayer) state.hub.cableTowerLayer.mesh.visible = true;
  state.utilityGroup.visible = !!state.layers.underground;
  if (state.utilityDrops) state.utilityDrops.visible = state.layers.water;
  for (const v of state.houseDetails.values()) v.roof.visible = true;
  state.markers.issues.visible = state.layers.issues;
  state.markers.nonet.visible = state.layers.nonet;
  state.markers.ups.visible = state.layers.ups;
  state.markers.heater.visible = state.layers.heater;
  state.flowPower.mesh.visible = state.layers.power;
  if (state.phaseDropFlow)
    state.phaseDropFlow.mesh.visible = state.layers.power;
  state.flowWater.mesh.visible = state.layers.water;
  state.packetsPts.visible = state.layers.packets;
  state.markers.packetsRed.visible = state.layers.packets;
  state.markers.people.visible = state.layers.people;
  state.markers.xenos.visible = state.layers.threats;
  state.markers.marines.visible = state.layers.threats;
  state.labelGroup.visible = state.layers.labels;
  if (state.markers.ctrl) state.markers.ctrl.visible = state.layers.ctrl;
  state.renderer.shadowMap.enabled = state.layers.shadows;
  state.sun.castShadow = state.layers.shadows;
}

export function tempColor(t) {
  const u = Math.max(0, Math.min(1, (t + 40) / 65));
  if (u < 0.6) {
    const k = u / 0.6;
    return state.tmpC.setRGB(
      (60 + 150 * k) / 255,
      (110 + 120 * k) / 255,
      (230 - 20 * k) / 255,
    );
  }
  const k = (u - 0.6) / 0.4;
  return state.tmpC.setRGB(
    (210 + 45 * k) / 255,
    (230 - 90 * k) / 255,
    (210 - 150 * k) / 255,
  );
}

export function onState(s, first) {
  if (!state.G) return;
  if (!state.housesMesh) build();
  const now = performance.now();
  updatePhysicalState(s);
  updateCargo(s);
  updateOcean(s);
  const c = state.G.cfg,
    ns = c.sectors,
    hs = s.houses,
    P = state.G.poles.x.length,
    m4 = new THREE.Matrix4();
  for (let i = 0; i < state.flatHouses.length; i++) {
    const col = new THREE.Color(
      [0x898674, 0x999786, 0x7e8c85, 0xb0a48a][state.G.houses.type[i]],
    );
    if (!hs.power[i]) col.multiplyScalar(0.65);
    state.housesMesh.setColorAt(i, col);
  }
  state.housesMesh.instanceColor.needsUpdate = true;
  {
    const pal = [
      "#f2c14e",
      "#5ec07a",
      "#5aa9ff",
      "#b48ead",
      "#e2574d",
      "#4fd1c5",
    ];
    const names = [...new Set(s.control.programs.filter(Boolean))];
    const a = state.markers.ctrl.geometry.attributes.position,
      cc = state.markers.ctrl.geometry.attributes.color;
    const counts = {};
    for (let i = 0; i < 300; i++) {
      const p = s.control.programs[i];
      if (p && s.control.ext[i]) {
        const pt = sph(
          state.flatHouses[i][0],
          state.flatHouses[i][1],
          state.HSIZE_H(state.G.houses.type[i]) + 6,
        );
        a.setXYZ(i, pt.x, pt.y, pt.z);
        const col = new THREE.Color(pal[names.indexOf(p) % pal.length]);
        cc.setXYZ(i, col.r, col.g, col.b);
        counts[p] = (counts[p] || 0) + 1;
      } else a.setXYZ(i, 0, -99999, 0);
    }
    a.needsUpdate = true;
    cc.needsUpdate = true;
    const mq = s.control.mqtt;
    document.getElementById("ctrl").innerHTML = mq.enabled
      ? `bus ${mq.connected ? '<span class="ok">connected</span>' : '<span class="bad">disconnected</span>'} ${mq.broker}, ${mq.controlled}/300 houses under external programs, ${mq.sent} sensor msgs, ${mq.received} actuator msgs<br>` +
        names
          .map(
            (n, k) =>
              `<span style="color:${pal[k % pal.length]}">&#9679;</span> ${n} ${counts[n] || 0}`,
          )
          .join(" &nbsp; ")
      : "bus off: every house runs the built-in thermostat (start with --mqtt host:port and houses_runtime.py)";
  }
  for (let i = 0; i < P; i++) {
    state.spanLines.setColor(i, s.poles.span[i] ? 0xf2c14e : 0x5a2a2a);
    state.netLines.setColor(i, s.poles.net[i] ? 0x4fd1c5 : 0x5a2a2a);
    state.flowPower.active[i] = !!s.poles.span[i];
  }
  for (let i = 0; i < ns; i++) {
    state.hub.feederLayer.setColor(
      i,
      s.power.feeder[i] && s.sectors[i].online ? 0xf2c14e : 0x5a2a2a,
    );
    state.flowPower.active[P + i] = s.power.feeder[i] && s.sectors[i].online;
  }
  const reactorUp = s.reactor.available_mw > 0;
  const nT = state.trunkCurves.length,
    nTw = state.towerCurves.length;
  for (let i = 0; i < nT; i++) {
    state.hub.trunkLayer.setColor(i, s.power.trunk ? 0xf2c14e : 0x5a2a2a);
    state.flowPower.active[P + ns + i] = s.power.trunk && reactorUp;
  }
  for (let i = 0; i < nTw; i++) {
    state.hub.towerLayer.setColor(i, s.power.tower_line ? 0xf2c14e : 0x5a2a2a);
    state.flowPower.active[P + ns + nT + i] =
      s.power.tower_line && s.power.trunk && reactorUp;
  }
  state.hub.solarLayer.setColor(0, s.power.solar_kw > 0 ? 0xf2c14e : 0x6a5a3a);
  state.flowPower.active[P + ns + nT + nTw] = s.power.solar_kw > 0;
  for (let i = 0; i < state.cableTowerCurves.length; i++)
    state.hub.cableTowerLayer.setColor(i, s.net.uplink ? 0x4fd1c5 : 0x5a2a2a);
  const waterOn = s.water.tank_m3 > 0 && s.water.pump;
  // lamps and poles
  setPoints(
    state.markers.lampGlow,
    state.G.poles.x
      .map((x, i) => (s.poles.lamp[i] ? [x, state.G.poles.y[i]] : null))
      .filter(Boolean),
    9,
  );
  for (let i = 0; i < P; i++) {
    const st = s.poles.state[i];
    if (st === state.prevPole[i]) continue;
    state.prevPole[i] = st;
    const x = state.G.poles.x[i],
      y = state.G.poles.y[i];
    const yaw =
      state.G.poles.kind[i] === 0
        ? (-state.G.poles.angle[i] * Math.PI) / 180 + Math.PI / 2
        : (-state.G.poles.angle[i] * Math.PI) / 180;
    const q = quatAt(x, y, yaw);
    if (st === 2)
      q.multiply(
        new THREE.Quaternion().setFromAxisAngle(
          new THREE.Vector3(1, 0, 0),
          1.45,
        ),
      );
    else if (st === 1)
      q.multiply(
        new THREE.Quaternion().setFromAxisAngle(
          new THREE.Vector3(1, 0, 0),
          0.3,
        ),
      );
    m4.compose(sph(x, y, st === 2 ? 1 : 5.5), q, new THREE.Vector3(1, 1, 1));
    state.polesMesh.setMatrixAt(i, m4);
    m4.compose(
      sph(x, y, st === 2 ? 1 : 10.3),
      q,
      new THREE.Vector3(st === 2 ? 0.01 : 1, 1, 1),
    );
    state.armsMesh.setMatrixAt(i, m4);
    state.lampsMesh.setMatrixAt(i, m4);
    state.polesMesh.instanceMatrix.needsUpdate = true;
    state.armsMesh.instanceMatrix.needsUpdate = true;
    state.lampsMesh.instanceMatrix.needsUpdate = true;
  }
  state.lampsMesh.material.color.setHex(
    s.env.night || s.env.storm ? 0xffe9a8 : 0x777777,
  );
  // markers
  setPoints(
    state.markers.issues,
    s.issues.map((i) => [i.x, i.y]),
    34,
  );
  setPoints(
    state.markers.nonet,
    state.flatHouses.filter((p, i) => !hs.net[i]),
    18,
  );
  setPoints(
    state.markers.heater,
    state.flatHouses.filter((p, i) => hs.heater[i] && hs.power[i]),
    15,
  );
  setPoints(state.markers.people, s.people, 3);
  setPoints(state.markers.marines, s.marines, 6);
  setPoints(
    state.markers.ups,
    s.sectors
      .map((x, i) =>
        x.ups === "DISCHARGING" || x.ups === "CHARGING"
          ? state.G.layout.distribution[i].ups
          : null,
      )
      .filter(Boolean)
      .concat(
        s.power.ups_center === "DISCHARGING" ||
          s.power.ups_center === "CHARGING"
          ? [[-80, 33]]
          : [],
      ),
    30,
  );
  // lockdown: wedge overlay, gate beacons, alert list
  const locked = s.sectors.map((x) => x.lockdown > 0);
  for (let i = 0; i < ns; i++) {
    state.lockWedges[i].visible = locked[i];
  }
  for (let i = 0; i < ns; i++) {
    const on = locked[i] || locked[(i + ns - 1) % ns];
    state.gates[i].beacons.forEach((b) => (b.visible = on));
  }
  {
    const alerts = [];
    s.sectors.forEach((x, i) => {
      if (x.lockdown > 0)
        alerts.push(`LOCKDOWN sector ${i + 1}: ${x.lockdown} min left`);
    });
    if (s.xenos.length)
      alerts.push(
        `${s.xenos.length} xenomorphs on the ground (${[...new Set(s.xenos.map((x) => x.state))].join(", ")})`,
      );
    if (s.squad.state !== "BASE")
      alerts.push(
        `marine squad ${s.squad.state.toLowerCase()} in sector ${s.squad.sector}`,
      );
    if (s.wall_breach.some((a) => a !== null))
      alerts.push(
        "wall breached in sector " +
          s.wall_breach
            .map((a, i) => (a !== null ? i + 1 : null))
            .filter(Boolean)
            .join(", "),
      );
    if (s.reactor.mode !== "ONLINE") alerts.push("reactor " + s.reactor.mode);
    document.getElementById("alerts").innerHTML = alerts
      .map((a) => `<div>${a}</div>`)
      .join("");
    document.getElementById("alerts").style.display = alerts.length
      ? "block"
      : "none";
  }
  // wall breach: the broken panel lies flat
  if (state.wallPanels) {
    for (let i = 0; i < state.wallSegs.length; i++) {
      const [a] = state.wallSegs[i];
      const sec = Math.floor(a / 60);
      const br = s.wall_breach[sec];
      const broken = br !== null && Math.abs(a - br) < 1.3;
      if (broken !== state.wallSegs[i].broken) {
        state.wallSegs[i].broken = broken;
        const [x, y] = polar(a, c.wall_radius + (broken ? 6 : 0));
        const q = quatAt(x, y, (-a * Math.PI) / 180 - Math.PI / 2);
        if (broken)
          q.multiply(
            new THREE.Quaternion().setFromAxisAngle(
              new THREE.Vector3(1, 0, 0),
              1.45,
            ),
          );
        m4.compose(
          sph(x, y, broken ? 1.5 : 6.5),
          q,
          new THREE.Vector3(1, 1, 1),
        );
        state.wallPanels.setMatrixAt(i, m4);
        state.wallPanels.instanceMatrix.needsUpdate = true;
      }
    }
  }
  // xenomorphs and the squad
  {
    const seen = new Set();
    s.xenos.forEach((x, k) => {
      if (k >= state.xenoPool.length) return;
      const p = state.xenoPool[k];
      const to = sph(x.x, x.y, 0.5);
      if (p.id !== x.id || !p.to) {
        p.g.position.copy(to);
        p.from = to;
      } else p.from = p.to;
      p.to = to;
      p.q = quatAt(x.x, x.y, -x.heading + Math.PI / 2);
      p.t0 = now;
      p.id = x.id;
      p.g.visible = state.layers.threats;
      p.state = x.state;
      retext(
        p.lab,
        `xenomorph: ${x.state}${x.state === "hunt" || x.state === "attack" ? " house " + x.target : ""}`,
        x.state === "dying" ? "#888" : "#e2574d",
      );
      seen.add(k);
    });
    state.xenoPool.forEach((p, k) => {
      if (!seen.has(k)) {
        p.g.visible = false;
        p.id = null;
        p.to = null;
      }
    });
    const q = s.squad;
    const vis = q.state !== "BASE";
    state.squadGroup.visible = vis && state.layers.threats;
    if (vis) {
      const to = sph(q.x, q.y, 0.5);
      if (!state.squadGroup.userData.to) state.squadGroup.position.copy(to);
      state.squadGroup.userData.from = state.squadGroup.userData.to || to;
      state.squadGroup.userData.to = to;
      state.squadGroup.userData.q = quatAt(q.x, q.y, -q.heading + Math.PI / 2);
      state.squadGroup.userData.t0 = now;
      retext(
        state.squadGroup.userData.lab,
        `marine squad: ${q.state.toLowerCase()}`,
        "#8be05a",
      );
    } else state.squadGroup.userData.to = null;
  }
  // gates: arm rotates with gate_open
  for (let i = 0; i < ns; i++) {
    const st = s.sectors[i].gate,
      g = state.gates[i];
    g.armTarget = (-Math.PI / 2) * s.sectors[i].gate_open;
    const col =
      st === "LOCKDOWN" ? 0xe2574d : st === "OPEN" ? 0x5ec07a : 0x8a93a6;
    g.lamp.material.color.setHex(col);
  }
  // hub and complex live state
  state.hub.yard.children[0].material.color.setHex(
    s.power.substation ? 0x9aa3b5 : 0xe2574d,
  );
  state.hub.tankLevel.scale.set(
    1,
    Math.max(0.05, (6.12 * s.water.tank_m3) / s.water.tank_cap),
    1,
  );
  state.hub.tankLevel.position.copy(
    sph(-70, -45, 24 + (3.06 * s.water.tank_m3) / s.water.tank_cap),
  );
  for (let i = 0; i < ns; i++) {
    state.cabBoxes[i].material.color.setHex(
      s.sectors[i].cabinet ? 0x3f6a6a : 0x6a3030,
    );
    state.rpBoxes[i].material.color.setHex(
      s.sectors[i].rp_ok ? 0x6a6d78 : 0x6a3030,
    );
  }
  const mc =
    { ONLINE: 0x5ec07a, RUNBACK: 0xe0b04a, STARTING: 0x5aa9ff }[
      s.reactor.mode
    ] || 0xe2574d;
  state.complex.core.material.color.setHex(mc);
  const sol = Math.min(1, s.power.solar_kw / 60);
  state.complex.panels.forEach((p) => {
    p.material.emissiveIntensity = 0.1 + sol * 1.2;
    p.material.emissive.setHex(0x2a5aff);
  });
  state.complex.water.material.color.setHex(
    s.water.plant ? 0x2a4a6a : 0x4a2a2a,
  );
  state.complex.towerLight.material.color.setHex(
    s.net.mobile ? 0xff3b3b : 0x553030,
  );
  state.complex.rings.forEach((r) => (r.visible = !!s.net.mobile));
  state.complex.mine.material.color.setHex(s.power.mine ? 0x4a3a2a : 0x2a2a2a);
  state.complex.steamOn =
    s.reactor.mode === "ONLINE" || s.reactor.mode === "RUNBACK";
  for (let i = 0; i < ns; i++) {
    const it = s.sectors[i].road;
    state.roadMeshes.ring[i].material.color.setHex(
      it < 20 ? 0x8a3a3a : it < 50 ? 0x5a4a3a : 0x30343d,
    );
  }
  // live labels
  for (const l of state.liveLabels) {
    const r = l.userData.role;
    if (r === "sub")
      retext(
        l,
        `substation ${s.power.available_kw} kW available, ${s.power.demand_kw} kW load${s.power.shedding ? ", shedding L" + s.power.shedding : ""}`,
        s.power.substation ? "#f2c14e" : "#e2574d",
      );
    else if (r === "ups")
      retext(
        l,
        `UPS center ${s.power.ups_center_kwh} kWh ${s.power.ups_center.toLowerCase()}`,
        "#4fd1c5",
      );
    else if (r === "comms")
      retext(
        l,
        `comms node ${s.net.houses_online}/300 online, ${s.net.packets_per_min} pkt/min, uplink ${s.net.uplink ? "OK" : "LOST"}`,
        s.net.uplink ? "#4fd1c5" : "#e2574d",
      );
    else if (r === "pump")
      retext(
        l,
        `pump station ${s.water.flow_m3_h} m3/h to the city`,
        s.water.pump ? "#5aa9ff" : "#e2574d",
      );
    else if (r === "tank")
      retext(
        l,
        `water tank ${s.water.tank_m3} / ${s.water.tank_cap} m3`,
        s.water.tank_m3 > 100 ? "#5aa9ff" : "#e2574d",
      );
    else if (r === "reactor")
      retext(
        l,
        `REACTOR ${s.reactor.mode}: ${s.reactor.power_mw} MW el, ${s.reactor.thermal_mw} MW th, core ${s.reactor.core_temp} C`,
        { ONLINE: "#5ec07a", RUNBACK: "#e0b04a", STARTING: "#5aa9ff" }[
          s.reactor.mode
        ] || "#e2574d",
      );
    else if (r === "solar")
      retext(l, `solar field ${s.power.solar_kw} kW`, "#e0b04a");
    else if (r === "wplant")
      retext(
        l,
        `water plant ${s.water.plant ? s.water.plant_m3_h + " m3/h" : "no heat"}`,
        s.water.plant ? "#5aa9ff" : "#e2574d",
      );
    else if (r === "mine")
      retext(
        l,
        `mine ${s.power.infra.mine} kW${s.power.mine_frac < 1 ? " (curtailed)" : ""}`,
        s.power.mine ? "#a08a2a" : "#777",
      );
    else if (r === "wproc")
      retext(
        l,
        `waste processing, ${s.finance.waste_station} loads received`,
        "#9bd36a",
      );
    else if (r === "tower")
      retext(
        l,
        `space uplink ${s.net.uplink ? "OK" : "LOST"}, ${s.net.packets_per_min} pkt/min`,
        s.net.uplink ? "#4fd1c5" : "#e2574d",
      );
  }
  // rovers: interpolate between the last two samples
  for (const r of s.rovers) {
    if (!state.rovers[r.name]) {
      const g = r.name.startsWith("freight")
        ? freightVehicle()
        : detailedVehicle(
            [0x74918b, 0xaaa38b, 0x93664f, 0x6e818c][
              Number(r.name.split("-").at(-1)) % 4
            ],
            r.name,
          );
      const lab = textSprite(r.name, "#ddd", 22);
      lab.position.y = 4;
      lab.scale.multiplyScalar(0.18);
      g.add(lab);
      state.world.add(g);
      clickable(g, "rover:" + r.name, "rover", r.name);
      state.rovers[r.name] = { g, lab, t0: 0 };
    }
    const rv = state.rovers[r.name];
    if (state.drive?.name === r.name) continue;
    if (rv.g.userData.cargo) rv.g.userData.cargo.visible = !!r.load;
    const lane = r.manual ? 0 : r.state === "IDLE" ? 8.5 : 2.2,
      xx = r.x - Math.sin(r.heading) * lane,
      yy = r.y + Math.cos(r.heading) * lane;
    rv.from = rv.g.position.clone();
    rv.to =
      r.manual && r.chassis
        ? xyNormal(xx, yy).multiplyScalar(
            state.RP + surfaceHeight(xx, yy) + r.chassis.height,
          )
        : sph(xx, yy, 1.08);
    rv.q = quatAt(xx, yy, -r.heading);
    const grade = Math.atan2(
      terrainH(r.x + Math.cos(r.heading) * 3, r.y + Math.sin(r.heading) * 3) -
        terrainH(r.x - Math.cos(r.heading) * 3, r.y - Math.sin(r.heading) * 3),
      6,
    );
    rv.q.multiply(
      new THREE.Quaternion().setFromAxisAngle(
        new THREE.Vector3(0, 0, 1),
        grade,
      ),
    );
    if (r.manual && r.chassis)
      rv.q.multiply(
        new THREE.Quaternion().setFromEuler(
          new THREE.Euler(r.chassis.roll, 0, r.chassis.pitch - grade),
        ),
      );
    rv.distanceFrom = rv.distance ?? r.distance_m;
    rv.distanceTo = r.distance_m;
    rv.t0 = now;
    rv.state = r.state;
    if (first || !rv.initialized) {
      rv.g.position.copy(rv.to);
      rv.g.quaternion.copy(rv.q);
      rv.initialized = true;
    }
    rv.lab.visible =
      !r.name.startsWith("transit") &&
      state.camera.position.distanceTo(rv.g.position) < 140;
    retext(
      rv.lab,
      `${r.name} ${r.state.toLowerCase().replace(/_/g, " ")}`,
      "#fff",
    );
  }
  for (const p of s.net.packets) {
    const key = p.t + ":" + p.from + ":" + p.id;
    if (!state.packetsSeen.has(key)) state.packetsSeen.set(key, { t0: now, p });
  }
  const e = s.env;
  document.getElementById("banner").innerHTML =
    `<b>${s.time}</b> &nbsp; ${e.t_out} C, wind ${e.wind} m/s${e.storm ? ' <span class="bad">STORM</span>' : ""}${e.precip === "snow" ? " snow" : ""}${e.night ? " night" : " day"}${s.paused ? ' <span class="warn">PAUSED</span>' : ""} &nbsp; ${s.speed} min/s`;
  const fin = document.getElementById("finished");
  if (s.finished) {
    fin.style.display = "flex";
    fin.textContent =
      "COLONY LOST: " +
      s.finish_reason +
      ". A new colony is founded in two minutes.";
  } else fin.style.display = "none";
  const m = s.time.match(/(\d\d):(\d\d)$/);
  state.clock.hour = m ? +m[1] + +m[2] / 60 : 12;
  state.clock.speed = s.paused ? 0 : s.speed;
  state.clock.at = now;
  state.clock.daylight = e.daylight;
  state.weather.wind = e.wind;
  state.weather.precip = e.precip;
  state.weather.storm = e.storm;
  state.weather.tornadoOn = e.storm && e.wind > 30;
  state.planetMat.uniforms.uCold.value = Math.min(
    1,
    Math.max(0, (-e.t_out - 30) / 35),
  );
  state.planetMat.uniforms.uStorm.value = e.storm
    ? 1
    : e.precip === "snow"
      ? 0.4
      : 0;
  if (first) {
    const focus = Number(new URLSearchParams(location.search).get("house"));
    if (
      Number.isInteger(focus) &&
      focus >= 1 &&
      focus <= state.G.houses.x.length
    ) {
      state.selected = { kind: "house", id: focus - 1 };
      flyTo(state.G.houses.x[focus - 1], state.G.houses.y[focus - 1], 42);
      renderInfo();
    }
    state.speedEl.value = state.speedToSlider(s.speed);
    state.speedV.textContent = s.speed + " min/s";
  }
}

export function initialize() {
  state.tmpC = new THREE.Color();
  state.packetsSeen = new Map();
  state.prevPole = new Array(1000).fill(-1);
  state.HSIZE_H = (t) => state.DIM[t][1] + 2;
  state.clock = { hour: 12, speed: 20, at: 0, night: false, daylight: 0.1 };
  state.sunDir = new THREE.Vector3(1, 0.3, 0);
}
