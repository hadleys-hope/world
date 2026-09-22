/** ui/inspection: procedural colony viewer. */
import { state } from '../state.js';
import { focusPoint, focusSelection } from '../camera.js';
import { polar, sph } from '../geometry/planet.js';
import * as THREE from 'three';
export function flyTo(x, y, dist) {
  const p = sph(x, y),
    n = p.clone().normalize();
  const side = new THREE.Vector3().crossVectors(n, new THREE.Vector3(0, 0, 1)).normalize();
  if (side.lengthSq() < 1e-6) side.set(1, 0, 0);
  const back = new THREE.Vector3().crossVectors(side, n).normalize();
  const pos = p.clone().add(n.multiplyScalar(dist * 0.85)).add(back.multiplyScalar(dist * 0.55));
  state.flyAnim = {
    from: state.camera.position.clone(),
    to: pos,
    tfrom: state.controls.target.clone(),
    tto: p,
    t0: performance.now()
  };
}
export function setMouse(ev) {
  const r = state.renderer.domElement.getBoundingClientRect();
  state.mouse.set((ev.clientX - r.left) / r.width * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  return [ev.clientX - r.left, ev.clientY - r.top];
}
export function pick(ev, click) {
  const [mx, my] = setMouse(ev),
    tip = document.getElementById('tip');
  if (!state.housesMesh || !state.S) return;
  state.ray.setFromCamera(state.mouse, state.camera);
  const candidates = [];
  const add = (hits, decode) => {
    if (hits.length) {
      const item = decode(hits[0]);
      if (item) candidates.push({
        ...item,
        hit: hits[0]
      });
    }
  };
  add(state.ray.intersectObjects([state.polePickMesh, ...state.cabinetMeters].filter(Boolean), false), h => ({
    kind: 'pole',
    id: h.object === state.polePickMesh ? h.instanceId : h.object.userData.pole
  }));
  add(state.ray.intersectObjects([...state.houseDetails.values()].map(v => v.g), true), h => ({
    kind: 'house',
    id: h.object.userData.house
  }));
  add(state.ray.intersectObject(state.housesMesh, false), h => ({
    kind: 'house',
    id: h.instanceId
  }));
  add(state.ray.intersectObjects(state.clickables, true), h => h.object.userData.click || h.object.parent?.userData.click);
  if (click || document.querySelector('[data-view="water"]').getAttribute('aria-pressed') === 'true') {
    const meshes = state.potableBatches.filter(m => m.material === state.MAT['pipe-steel']);
    if (state.layers.underground) meshes.push(...state.utilityBatches);
    add(state.ray.intersectObjects(meshes, false), h => {
      const tag = h.object.userData.tags[h.instanceId];
      return tag && tag.id >= 0 ? {
        kind: 'pipe',
        id: tag.id,
        extra: tag.system
      } : null;
    });
  }
  candidates.sort((a, b) => a.hit.distance - b.hit.distance);
  const result = candidates[0];
  if (!result) {
    tip.style.display = 'none';
    return;
  }
  if (click) {
    state.selected = {
      kind: result.kind,
      id: result.id,
      extra: result.extra
    };
    renderInfo();
  }
  const html = result.kind === 'house' ? houseInfo(result.id, true) : result.kind === 'pole' ? `<b>POLE ${String(result.id + 1).padStart(3, '0')} · L1 / L2 / L3 / N</b><br>${((state.poleLoads[result.id] || 0) / 1000).toFixed(1)} kW · ${state.S.poles.span[result.id] ? 'energized' : 'isolated'}<br>F / double-click: inspect meter` : `<b>${result.kind} ${result.id}</b><br>F / double-click: focus`;
  tipHtml(tip, mx, my, html);
}
export function tipHtml(tip, mx, my, html) {
  tip.innerHTML = html;
  tip.style.display = 'block';
  tip.style.left = mx + 14 + 'px';
  tip.style.top = my + 14 + 'px';
}
export function houseInfo(i, short) {
  const h = state.S.houses,
    ctl = state.S.control;
  const prog = ctl.ext[i] ? `${ctl.programs[i]}: ${ctl.reasons[i]} (target ${ctl.targets[i]} C)` : `built-in thermostat, target ${ctl.targets[i]} C`;
  return `<b>House ${i + 1}</b> (Sector ${state.G.houses.sector[i] + 1}, ${state.G.types[state.G.houses.type[i]]}, ${state.G.houses.residents[i]} residents)<br>indoor ${h.t[i]} C, heater ${h.heater[i] ? 'on' : 'off'}, draw ${h.draw[i]} W${h.limit[i] ? ' (limit ' + h.limit[i] + ' W)' : ''}<br>power ${h.power[i] ? h.ups[i] ? 'sector UPS' : 'grid' : '<span class="bad">none</span>'}, water ${h.water[i] ? 'ok' : '<span class="bad">no</span>'}${h.burst[i] ? ', <span class="bad">pipes burst</span>' : ''}<br>pressure ${state.S.hydraulics.pressure_kpa[i]} kPa · delivered ${state.S.hydraulics.delivered_l[i]} L/tick · leak ${state.S.hydraulics.leak_l[i]} L/tick<br>internet ${h.net[i] ? 'online' : '<span class="warn">offline</span>'}, aeration sludge ${Math.round(h.sludge[i] * 100)}%<br><span class="dim">program:</span> ${prog}` + (short ? '' : `<br>pole ${state.G.houses.pole[i]}`);
}
export function personInfo(per) {
  const st = ['at home', 'walking to the hub', 'at the hub', 'walking home'][per[2]];
  return `<b>Colonist</b> from house ${per[3] + 1}, ${st}`;
}
export function rows(pairs) {
  return '<table>' + pairs.map(([k, v]) => `<tr><td class="dim">${k}</td><td><b>${v}</b></td></tr>`).join('') + '</table>';
}
export function renderInfo() {
  const box = document.getElementById('info');
  if (!state.selected || !state.S) {
    box.style.display = 'none';
    return;
  }
  const s = state.S,
    c = state.G.cfg;
  let title = '',
    body = '';
  const k = state.selected.kind,
    x = state.selected.extra;
  if (k === 'house') {
    title = `House ${state.selected.id + 1}`;
    body = houseInfo(state.selected.id, false) + `<div style="margin-top:6px"><a href="/house?id=${state.selected.id + 1}" target="_blank" style="color:#5aa9ff">open the house page: gauges, history, log</a></div>`;
  } else if (k === 'pole') {
    title = `Pole ${Number(state.selected.id) + 1} · distribution board`;
    body = rows([['circuit', 'L1 / L2 / L3 + neutral'], ['load', ((state.poleLoads[state.selected.id] || 0) / 1000).toFixed(2) + ' kW'], ['grid', s.poles.span[state.selected.id] ? 'energized' : 'isolated'], ['fibre', s.poles.net[state.selected.id] ? 'online' : 'offline'], ['inspect', 'F / double-click to focus the meter']]);
  } else if (k === 'pipe') {
    const e = x === 'water' ? state.G.utilities.links[state.selected.id] : state.G.utilities.drainage.find(d => d.name === x)?.links[state.selected.id];
    title = `${x} / pipe ${state.selected.id + 1}`;
    if (e) {
      body = rows([['material', e.material], ['internal diameter', Math.round(e.diameter_m * 1000) + ' mm'], ['length', e.length_m.toFixed(2) + ' m'], ...(x === 'water' ? [['flow', s.hydraulics.flow_l_s[state.selected.id] + ' L/s'], ['velocity', s.hydraulics.velocity_m_s[state.selected.id] + ' m/s'], ['head loss', s.hydraulics.headloss_m[state.selected.id] + ' m'], ['insulation', e.insulation_mm + ' mm / heat traced']] : [['inflow', s.hydraulics.drainage_l_s[x === 'sanitary' ? 0 : 1][state.selected.id] + ' L/s'], ['grade', (e.slope * 100).toFixed(1) + ' %'], ['full-bore capacity', (e.capacity_m3_s * 1000).toFixed(2) + ' L/s']])]);
    }
  } else if (k === 'person') {
    const per = s.people[state.selected.id];
    title = 'Colonist';
    body = per ? personInfo(per) : 'went home';
  } else if (k === 'substation') {
    title = 'Main substation';
    body = rows([['available', s.power.available_kw + ' kW'], ['load', s.power.demand_kw + ' kW'], ['deficit', s.power.deficit_kw + ' kW'], ['shedding level', s.power.shedding], ['trunk line', s.power.trunk ? 'ok' : 'CUT'], ['feeders online', s.power.feeder.filter(Boolean).length + '/6'], ['solar in', s.power.solar_kw + ' kW'], ['mine', s.power.infra.mine + ' kW'], ['road heating', s.power.infra.road_heating + ' kW'], ['lamps', s.power.infra.lamps + ' kW'], ['ups charging', s.power.infra.ups_charge + ' kW']]);
  } else if (k === 'upsc') {
    title = 'UPS center';
    body = rows([['state', s.power.ups_center], ['charge', s.power.ups_center_kwh + ' / 800 kWh'], ['feeds', 'ops center, comms node, pump station']]);
  } else if (k === 'ups') {
    const sec = s.sectors[x];
    title = `Sector ${x + 1} UPS`;
    body = rows([['state', sec.ups], ['charge', sec.ups_kwh + ' / 400 kWh'], ['sector load', sec.demand_kw + ' kW'], ['houses on power', sec.power_ok + '/50']]);
  } else if (k === 'rp') {
    const sec = s.sectors[x];
    title = `Sector ${x + 1} distribution point`;
    body = rows([['feeder', sec.feeder_ok ? 'ok' : 'BROKEN'], ['distribution point', sec.rp_ok ? 'ok' : 'DAMAGED'], ['sector fed', sec.online ? 'yes' : 'no (shed or cut)'], ['load', sec.demand_kw + ' kW'], ['lamps on', sec.lamps_on]]);
  } else if (k === 'cabinet') {
    const sec = s.sectors[x];
    title = `Sector ${x + 1} internet cabinet`;
    body = rows([['online', sec.cabinet ? 'yes' : 'no'], ['cabinet ups', sec.cabinet_ups_h + ' h'], ['houses online', sec.net_ok + '/50']]);
  } else if (k === 'comms') {
    title = 'Comms node';
    body = rows([['houses online', s.net.houses_online + '/300'], ['traffic', s.net.packets_per_min + ' packets/min'], ['uplink', s.net.uplink ? 'OK' : 'LOST'], ['reactor link', s.net.reactor_link ? 'ok' : 'lost'], ['tower line power', s.power.tower_line ? 'ok' : 'cut']]);
  } else if (k === 'ops') {
    title = 'Operations center';
    body = rows([['time', s.time], ['open issues', s.issues_total], ['colony budget', s.finance.colony + ' cr'], ['month income', s.finance.month_income + ' cr'], ['month expense', s.finance.month_expense + ' cr']]);
  } else if (k === 'pump' || k === 'tank') {
    title = k === 'pump' ? 'Pump station' : 'Water tank';
    body = rows([['tank', s.water.tank_m3 + ' / ' + s.water.tank_cap + ' m3'], ['hydraulic solve', s.hydraulics.converged ? 'converged' : 'residual ' + s.hydraulics.residual_m.toFixed(3) + ' m'], ['sewage held', s.hydraulics.sewer_storage_m3 + ' m3'], ['storm water held', s.hydraulics.storm_storage_m3 + ' m3'], ['overflow total', s.hydraulics.overflow_m3 + ' m3'], ['flow to houses', s.water.flow_m3_h + ' m3/h'], ['from the plant', s.water.plant_m3_h + ' m3/h'], ['pump power', s.water.pump ? 'ok' : 'NONE'], ['houses with water', s.water.houses_ok + '/300'], ['frozen / burst', s.water.frozen + ' / ' + s.water.burst]].concat(s.water.sector_m3_h.map((v, i) => ['sector ' + (i + 1), v + ' m3/h'])));
  } else if (k === 'reactor') {
    const r = s.reactor;
    title = 'Reactor, atmosphere processor';
    body = rows([['mode', r.mode], ['electric', r.power_mw + ' MW (setpoint ' + r.setpoint_mw + ')'], ['thermal', r.thermal_mw + ' MW'], ['to grid', r.available_mw + ' MW'], ['core', r.core_temp + ' C'], ['coolant', r.coolant_temp + ' C, flow ' + Math.round(r.flow * 100) + '%'], ['decay heat', r.decay_mw + ' MW'], ['pumps A / B', r.pump_a + ' / ' + r.pump_b], ['heat exchanger', r.hx], ['pump batteries', r.battery_h + ' h'], ['control link', r.link ? 'ok' : 'LOST'], ['faults', r.faults.join(', ') || 'none'], ['marines', r.marines ? 'in the sublevels' : 'no']]);
  } else if (k === 'solar') {
    title = 'Solar field';
    body = rows([['output', s.power.solar_kw + ' kW'], ['daylight', Math.round(s.env.daylight / 0.3 * 100) + '% of a clear day'], ['dust', Math.round(s.env.dust * 100) + '%']]);
  } else if (k === 'wplant' || k === 'intake') {
    title = k === 'intake' ? 'Ocean intake / heated well' : 'Ocean water treatment';
    body = rows([['source', 'frozen saline ocean'], ['state', s.water.plant ? 'melting / filtering / desalinating' : 'stopped'], ['raw intake', s.water.raw_m3_h + ' m³/h'], ['treated water', s.water.plant_m3_h + ' m³/h'], ['brine return', s.water.brine_m3_h + ' m³/h'], ['heat used / available', s.water.heat_kw + ' / ' + s.water.heat_available_kw + ' kW'], ['recovery', '85%'], ['tank in the city', s.water.tank_m3 + ' m³']]);
  } else if (k === 'rad') {
    title = 'Radioactive waste storage';
    body = rows([['load', s.power.infra.waste_storage + ' kW'], ['state', 'sealed'], ['upkeep', '3000 cr/month, colony']]);
  } else if (k === 'mine') {
    title = 'Mine';
    body = rows([['load', s.power.infra.mine + ' kW'], ['state', s.power.mine ? s.power.mine_frac < 1 ? 'curtailed to ' + Math.round(s.power.mine_frac * 100) + '%' : 'working' : 'stopped'], ['income', '3 cr/min to the colony while powered']]);
  } else if (k === 'wproc') {
    title = 'Waste processing';
    body = rows([['loads received', s.finance.waste_station], ['sector bins', s.sectors.map(x => Math.round(x.waste * 100) + '%').join(' ')]]);
  } else if (k === 'tower') {
    title = 'Cellular / 5G base station';
    body = rows([['role', 'local mobile communications'], ['coverage', s.net.mobile ? 'online' : 'offline'], ['line power', s.power.tower_line ? 'ok' : 'cut']]);
  } else if (k === 'dish') {
    title = 'Deep-space tracking complex';
    body = rows([['reflector', '64 m / parabolic'], ['role', 'Weyland-Yutani space uplink'], ['uplink', s.net.uplink ? 'OK' : 'LOST'], ['traffic', s.net.packets_per_min + ' packets/min']]);
  } else if (k === 'garage') {
    title = 'Vehicle bay';
    body = rows(s.rovers.map(r => [r.name, r.state.toLowerCase().replace(/_/g, ' ') + (r.job ? ' (' + r.job + ')' : '')]));
  } else if (k === 'medlab') {
    title = 'Med lab';
    body = rows([['load', 'part of ops center'], ['cold houses', s.sectors.reduce((a, x) => a + (x.min_t < 10 ? 1 : 0), 0) + ' sectors with houses below 10 C']]);
  } else if (k === 'school') {
    title = 'School';
    body = rows([['residents walking now', s.people.length], ['storm', s.env.storm ? 'closed' : 'open']]);
  } else if (k === 'pad') {
    title = 'Landing field';
    body = rows([['next dropship', 'end of month'], ['uplink', s.net.uplink ? 'OK' : 'LOST']]);
  } else if (k === 'xeno') {
    const x = s.xenos[state.selected.extra];
    title = 'Xenomorph';
    body = x ? rows([['state', x.state], ['sector', x.sector], ['target house', x.target > 0 ? x.target : 'none']]) : 'gone';
  } else if (k === 'squad') {
    const q = s.squad;
    title = 'Marine squad';
    body = rows([['state', q.state.toLowerCase()], ['sector', q.sector > 0 ? q.sector : 'base'], ['position', q.x + ', ' + q.y]]);
  } else if (k === 'gate') {
    const sec = s.sectors[x];
    title = `Gate ${x + 1}`;
    body = rows([['state', sec.gate], ['open', Math.round(sec.gate_open * 100) + '%'], ['hardware', sec.gate_ok ? 'ok' : 'DAMAGED'], ['lockdown left', sec.lockdown ? sec.lockdown + ' min' : 'none']]);
  } else if (k === 'rover') {
    const r = s.rovers.find(r => r.name === x);
    title = x;
    body = r ? rows([['state', r.state.toLowerCase().replace(/_/g, ' ')], ['load', Math.round(r.load * 100) + '%'], ['job', r.job || 'none'], ['fuel', r.fuel_l + ' L'], ['distance', (r.distance_m / 1000).toFixed(2) + ' km'], ['position', r.x + ', ' + r.y]]) : '';
  }
  document.getElementById('infotitle').textContent = title;
  document.getElementById('infobody').innerHTML = body;
  box.style.display = 'block';
}
export function initialize() {
  state.flyAnim = null;
  document.querySelectorAll('#fly button').forEach(b => b.onclick = () => {
    const c = state.G.cfg;
    const f = b.dataset.f;
    if (f === 'home') {
      const i = state.selected?.kind === 'house' ? state.selected.id : 0;
      state.selected = {
        kind: 'house',
        id: i
      };
      flyTo(state.G.houses.x[i], state.G.houses.y[i], 42);
      renderInfo();
    } else if (f === 'street') flyTo(...polar(17, 270), 90);else if (f === 'hub') flyTo(0, 0, 420);else if (f === 'gate') flyTo(-c.wall_radius, 0, 300);else if (f === 'reactor') flyTo(c.reactor_pos[0], c.reactor_pos[1], 420);else if (f === 'solar') flyTo(c.solar_pos[0], c.solar_pos[1], 320);else if (f === 'dish') flyTo(...c.dish_pos, 210);else if (f === 'intake') flyTo(...c.ocean_intake_pos, 240);else if (f === 'cargo') flyTo(...polar(...c.cargo_depot), 140);else if (f === 'tower') flyTo(c.tower_pos[0], c.tower_pos[1], 320);else if (f === 'mine') flyTo(c.mine_pos[0], c.mine_pos[1], 320);else if (f === 'city') flyTo(0, 0, 1500);else state.flyAnim = {
      from: state.camera.position.clone(),
      to: new THREE.Vector3(1200, state.RP + 4200, 3800),
      tfrom: state.controls.target.clone(),
      tto: new THREE.Vector3(0, state.RP, 0),
      t0: performance.now()
    };
  });
  state.ray = new THREE.Raycaster();
  state.mouse = new THREE.Vector2();
  state.ray.params.Points.threshold = 8;
  state.downAt = null;
  state.renderer.domElement.addEventListener('pointerdown', ev => {
    state.downAt = [ev.clientX, ev.clientY];
  });
  state.renderer.domElement.addEventListener('pointerup', ev => {
    if (!state.downAt) return;
    const moved = Math.hypot(ev.clientX - state.downAt[0], ev.clientY - state.downAt[1]);
    state.downAt = null;
    if (moved > 4) return;
    pick(ev, true);
  });
  state.renderer.domElement.addEventListener('dblclick', ev => {
    pick(ev, true);
    if (state.selected) focusSelection();else {
      setMouse(ev);
      state.ray.setFromCamera(state.mouse, state.camera);
      const hit = state.ray.intersectObject(state.planetMesh, false)[0];
      if (hit) focusPoint(hit.point, Math.min(150, state.camera.position.distanceTo(hit.point) * .5));
    }
  });
  state.lastHover = 0;
  state.renderer.domElement.addEventListener('mousemove', ev => {
    const now = performance.now();
    if (state.downAt || now - state.lastHover < 200) return;
    state.lastHover = now;
    pick(ev, false);
  });
  state.selected = null;
  document.getElementById('infoclose').onclick = () => {
    state.selected = null;
    renderInfo();
  };
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      state.selected = null;
      renderInfo();
    }
  });
}
