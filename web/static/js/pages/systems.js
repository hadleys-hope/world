const cv = document.getElementById('c'),
  ctx = cv.getContext('2d');
const tip = document.getElementById('tip');
let G = null,
  S = null,
  nodes = [],
  edges = [],
  byId = {},
  view = {
    x: 0,
    y: 0,
    k: 1
  },
  drag = null,
  hover = null,
  panning = null,
  simOn = true;
const opt = {
  poles: true,
  ctrl: true,
  water: true
};
['lPoles', 'lCtrl', 'lWater', 'lSim'].forEach(id => document.getElementById(id).onchange = e => {
  const k = id.slice(1).toLowerCase();
  if (k === 'sim') simOn = e.target.checked;else {
    opt[k] = e.target.checked;
  }
});
function node(id, type, label, x, y, r) {
  const n = {
    id,
    type,
    label,
    x,
    y,
    vx: 0,
    vy: 0,
    r,
    fixed: false,
    state: 'ok'
  };
  nodes.push(n);
  byId[id] = n;
  return n;
}
function edge(a, b, kind) {
  edges.push({
    a: byId[a],
    b: byId[b],
    kind,
    on: true
  });
}
async function init() {
  G = await (await fetch('/geometry')).json();
  const c = G.cfg;
  const sc = 0.9;
  const P = v => [v[0] * sc, v[1] * sc];
  node('reactor', 'plant', 'reactor', ...P([c.reactor_pos[0], c.reactor_pos[1]]), 16);
  node('solar', 'plant', 'solar field', ...P(c.solar_pos), 9);
  node('wplant', 'plant', 'water plant', ...P(c.water_plant_pos), 10);
  node('substation', 'hub', 'substation', 0, -60, 13);
  node('ups', 'hub', 'UPS center', -70, 10, 9);
  node('comms', 'hub', 'comms node', 70, 10, 10);
  node('tank', 'hub', 'water tank', -50, -40, 9);
  node('ops', 'hub', 'ops center', 0, 70, 9);
  node('tower', 'plant', 'radio mast', ...P(c.tower_pos), 10);
  node('dish', 'plant', 'deep-space dish', c.tower_pos[0] * sc + 70, c.tower_pos[1] * sc + 10, 10);
  edge('reactor', 'substation', 'power');
  edge('solar', 'substation', 'power');
  edge('wplant', 'tank', 'water');
  edge('substation', 'tower', 'power');
  edge('comms', 'tower', 'net');
  edge('tower', 'dish', 'net');
  edge('substation', 'ups', 'power');
  edge('substation', 'ops', 'power');
  edge('substation', 'comms', 'power');
  edge('comms', 'reactor', 'net');
  for (let s = 0; s < c.sectors; s++) {
    const a = (s * 60 + 3) * Math.PI / 180;
    const rp = node('rp' + s, 'sector', `S${s + 1} distribution`, Math.cos(a) * 180, Math.sin(a) * 180, 8);
    node('cab' + s, 'sector', `S${s + 1} cabinet`, Math.cos(a + 0.08) * 180, Math.sin(a + 0.08) * 180, 6);
    node('main' + s, 'sector', `S${s + 1} water main`, Math.cos(a - 0.08) * 180, Math.sin(a - 0.08) * 180, 5);
    edge('substation', 'rp' + s, 'power');
    edge('comms', 'cab' + s, 'net');
    edge('tank', 'main' + s, 'water');
  }
  for (let i = 0; i < G.poles.x.length; i++) {
    node('p' + i, 'pole', 'pole ' + i, G.poles.x[i] * sc, G.poles.y[i] * sc, 2.5);
  }
  for (let i = 0; i < G.poles.x.length; i++) {
    const p = G.poles.parent[i];
    if (p < 0) edge('rp' + G.poles.sector[i], 'p' + i, 'power');else edge('p' + p, 'p' + i, 'power');
    if (p < 0) edge('cab' + G.poles.sector[i], 'p' + i, 'net');else edge('p' + p, 'p' + i, 'net');
  }
  for (let i = 0; i < G.houses.x.length; i++) {
    node('h' + i, 'house', 'house ' + (i + 1), G.houses.x[i] * sc, G.houses.y[i] * sc, 4);
    edge('p' + G.houses.pole[i], 'h' + i, 'power');
    edge('p' + G.houses.pole[i], 'h' + i, 'net');
    edge('main' + G.houses.sector[i], 'h' + i, 'water');
  }
  const progs = ['comfort', 'eco', 'night-setback', 'storm-ready', 'dumb', 'thermostat'];
  progs.forEach((p, k) => {
    const a = k / progs.length * Math.PI * 2;
    node('prog:' + p, 'prog', p, Math.cos(a) * 820, Math.sin(a) * 820, 12);
  });
  view.x = cv.clientWidth / 2;
  view.y = cv.clientHeight / 2;
  view.k = Math.min(cv.clientWidth / 2400, cv.clientHeight / 1500);
  poll();
  loop();
}
let ctrlEdges = [];
async function poll() {
  try {
    S = await (await fetch('/state')).json();
    apply();
  } catch (e) {}
  setTimeout(poll, 1000);
}
function apply() {
  const hs = S.houses,
    pl = S.poles;
  document.getElementById('navtime').textContent = S.time;
  for (let i = 0; i < hs.t.length; i++) {
    const n = byId['h' + i];
    n.state = !hs.power[i] ? 'dead' : hs.ups[i] || hs.limit[i] ? 'warn' : 'ok';
    n.net = !!hs.net[i];
    n.info = `house ${i + 1}: ${hs.t[i]} C, ${hs.power[i] ? hs.ups[i] ? 'UPS' : 'grid' : 'no power'}, ${hs.water[i] ? 'water' : 'no water'}, ${hs.net[i] ? 'online' : 'offline'}, ${S.control.programs[i] || 'thermostat'}`;
  }
  for (let i = 0; i < pl.state.length; i++) {
    const n = byId['p' + i];
    n.state = pl.state[i] === 2 ? 'dead' : pl.span[i] ? 'ok' : 'warn';
    n.info = `pole ${i}: ${['standing', 'tilted', 'fallen'][pl.state[i]]}, span ${pl.span[i] ? 'live' : 'dead'}, cable ${pl.net[i] ? 'ok' : 'cut'}`;
  }
  for (let s = 0; s < S.sectors.length; s++) {
    const x = S.sectors[s];
    byId['rp' + s].state = x.online ? 'ok' : 'dead';
    byId['rp' + s].info = `sector ${s + 1}: ${x.demand_kw} kW, ${x.power_ok}/50 powered, UPS ${x.ups}`;
    byId['cab' + s].state = x.cabinet ? 'ok' : 'dead';
    byId['cab' + s].info = `cabinet: ${x.net_ok}/50 online`;
    byId['main' + s].state = x.water_ok > 0 ? 'ok' : 'dead';
    byId['main' + s].info = `water main: ${x.water_m3_h} m3/h`;
  }
  const r = S.reactor;
  byId.reactor.state = r.mode === 'ONLINE' ? 'ok' : r.mode === 'RUNBACK' ? 'warn' : 'dead';
  byId.reactor.info = `reactor ${r.mode}, ${r.power_mw} MW, core ${r.core_temp} C`;
  byId.substation.state = S.power.substation && S.power.trunk ? 'ok' : 'dead';
  byId.substation.info = `substation ${S.power.available_kw} kW available, ${S.power.demand_kw} kW load, shedding L${S.power.shedding}`;
  byId.solar.info = `solar ${S.power.solar_kw} kW`;
  byId.solar.state = S.power.solar_kw > 0 ? 'ok' : 'warn';
  byId.wplant.state = S.water.plant ? 'ok' : 'dead';
  byId.wplant.info = `water plant ${S.water.plant_m3_h} m3/h`;
  byId.tank.info = `tank ${S.water.tank_m3} m3`;
  byId.tank.state = S.water.tank_m3 > 50 ? 'ok' : 'warn';
  byId.comms.state = S.net.comms ? 'ok' : 'dead';
  byId.comms.info = `comms ${S.net.houses_online}/300 online, ${S.net.packets_per_min} pkt/min`;
  byId.tower.state = S.power.tower_line ? 'ok' : 'dead';
  byId.dish.state = S.net.uplink ? 'ok' : 'dead';
  byId.dish.info = `uplink ${S.net.uplink ? 'OK' : 'LOST'}`;
  byId.ups.info = `UPS center ${S.power.ups_center_kwh} kWh ${S.power.ups_center}`;
  byId.ops.info = 'operations center';
  for (const e of edges) {
    if (e.kind === 'power') {
      if (e.b.type === 'pole') {
        const i = +e.b.id.slice(1);
        e.on = !!pl.span[i];
      } else if (e.b.type === 'house') {
        const i = +e.b.id.slice(1);
        e.on = !!hs.power[i];
      } else if (e.b.type === 'sector') {
        e.on = e.b.state === 'ok';
      } else e.on = S.power.trunk;
    } else if (e.kind === 'net') {
      if (e.b.type === 'pole') {
        const i = +e.b.id.slice(1);
        e.on = !!pl.net[i];
      } else if (e.b.type === 'house') {
        const i = +e.b.id.slice(1);
        e.on = !!hs.net[i];
      } else if (e.b.type === 'sector') {
        e.on = e.b.state === 'ok';
      } else e.on = S.net.uplink;
    } else if (e.kind === 'water') {
      e.on = e.b.type === 'house' ? !!hs.water[+e.b.id.slice(1)] : e.b.state === 'ok';
    }
  }
  ctrlEdges = [];
  for (let i = 0; i < hs.t.length; i++) {
    const p = S.control.ext[i] ? S.control.programs[i] : 'thermostat';
    const pn = byId['prog:' + p];
    if (pn) ctrlEdges.push({
      a: pn,
      b: byId['h' + i],
      kind: 'ctrl',
      on: true
    });
  }
  const counts = {};
  ctrlEdges.forEach(e => counts[e.a.label] = (counts[e.a.label] || 0) + 1);
  for (const n of nodes) if (n.type === 'prog') {
    n.info = `${n.label}: ${counts[n.label] || 0} houses`;
    n.state = counts[n.label] ? 'ok' : 'off';
  }
  document.getElementById('stats').textContent = `${nodes.length} nodes, ${edges.length + ctrlEdges.length} edges, ${S.time}`;
}
function step() {
  if (!simOn) return;
  const K = 0.02;
  for (const n of nodes) {
    n.fx = 0;
    n.fy = 0;
  }
  // repulsion (grid-bucketed), springs along edges, gentle pull to the original layout
  const cell = 60,
    grid = new Map();
  for (const n of nodes) {
    const k = Math.floor(n.x / cell) + ',' + Math.floor(n.y / cell);
    (grid.get(k) || grid.set(k, []).get(k)).push(n);
  }
  for (const n of nodes) {
    const gx = Math.floor(n.x / cell),
      gy = Math.floor(n.y / cell);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      const b = grid.get(gx + dx + ',' + (gy + dy));
      if (!b) continue;
      for (const m of b) {
        if (m === n) continue;
        let ex = n.x - m.x,
          ey = n.y - m.y;
        let d2 = ex * ex + ey * ey + 1;
        if (d2 > 3600) continue;
        const f = 120 / d2;
        n.fx += ex * f;
        n.fy += ey * f;
      }
    }
  }
  const all = opt.ctrl ? edges.concat(ctrlEdges) : edges;
  for (const e of all) {
    if (!opt.poles && (e.a.type === 'pole' || e.b.type === 'pole')) continue;
    if (!opt.water && e.kind === 'water') continue;
    const ex = e.b.x - e.a.x,
      ey = e.b.y - e.a.y,
      d = Math.hypot(ex, ey) || 1;
    const want = e.kind === 'ctrl' ? 600 : e.kind === 'water' ? 40 : 28;
    const f = (d - want) * (e.kind === 'ctrl' ? 0.002 : 0.02);
    e.a.fx += ex / d * f;
    e.a.fy += ey / d * f;
    e.b.fx -= ex / d * f;
    e.b.fy -= ey / d * f;
  }
  for (const n of nodes) {
    if (n.home === undefined) {
      n.home = [n.x, n.y];
    }
    n.fx += (n.home[0] - n.x) * 0.004;
    n.fy += (n.home[1] - n.y) * 0.004;
    if (n.fixed) continue;
    n.vx = (n.vx + n.fx * K) * 0.85;
    n.vy = (n.vy + n.fy * K) * 0.85;
    n.x += n.vx;
    n.y += n.vy;
  }
}
const colors = {
  ok: '#5ec07a',
  warn: '#e0b04a',
  dead: '#e2574d',
  off: '#555'
};
const kindCol = {
  power: '#f2c14e',
  net: '#4fd1c5',
  water: '#5aa9ff',
  ctrl: '#b48ead'
};
function draw() {
  const W = cv.clientWidth,
    H = cv.clientHeight;
  if (cv.width !== W * devicePixelRatio) {
    cv.width = W * devicePixelRatio;
    cv.height = H * devicePixelRatio;
  }
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  ctx.clearRect(0, 0, W, H);
  ctx.save();
  ctx.translate(view.x, view.y);
  ctx.scale(view.k, view.k);
  const all = opt.ctrl ? edges.concat(ctrlEdges) : edges;
  ctx.lineWidth = 1 / view.k;
  for (const e of all) {
    if (!opt.poles && (e.a.type === 'pole' || e.b.type === 'pole')) continue;
    if (!opt.water && e.kind === 'water') continue;
    ctx.strokeStyle = e.on ? kindCol[e.kind] : '#3a2a2a';
    ctx.globalAlpha = e.kind === 'ctrl' ? 0.18 : e.on ? 0.75 : 0.5;
    ctx.beginPath();
    ctx.moveTo(e.a.x, e.a.y);
    ctx.lineTo(e.b.x, e.b.y);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  for (const n of nodes) {
    if (!opt.poles && n.type === 'pole') continue;
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.r, 0, 7);
    ctx.fillStyle = n.type === 'prog' ? '#b48ead' : n.type === 'house' && n.net === false ? '#6a5a7a' : colors[n.state] || '#888';
    ctx.fill();
    if (n.type !== 'pole' && n.type !== 'house') {
      ctx.strokeStyle = '#d9dde6';
      ctx.lineWidth = 1.2 / view.k;
      ctx.stroke();
    }
    if (n === hover) {
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2 / view.k;
      ctx.stroke();
    }
    if (n.type !== 'pole' && n.type !== 'house' && view.k > 0.25) {
      ctx.fillStyle = '#d9dde6';
      ctx.font = `${12 / view.k}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillText(n.label, n.x, n.y - n.r - 4 / view.k);
    }
  }
  ctx.restore();
}
function loop() {
  step();
  draw();
  requestAnimationFrame(loop);
}
function toWorld(ev) {
  const r = cv.getBoundingClientRect();
  return [(ev.clientX - r.left - view.x) / view.k, (ev.clientY - r.top - view.y) / view.k];
}
function pick(x, y) {
  let best = null,
    bd = 1e9;
  for (const n of nodes) {
    if (!opt.poles && n.type === 'pole') continue;
    const d = Math.hypot(n.x - x, n.y - y);
    if (d < Math.max(n.r + 3 / view.k, 6 / view.k) && d < bd) {
      bd = d;
      best = n;
    }
  }
  return best;
}
cv.addEventListener('pointerdown', ev => {
  const [x, y] = toWorld(ev);
  const n = pick(x, y);
  if (n) {
    drag = {
      n,
      moved: false
    };
    n.fixed = true;
  } else panning = {
    x: ev.clientX,
    y: ev.clientY,
    vx: view.x,
    vy: view.y
  };
  cv.setPointerCapture(ev.pointerId);
});
cv.addEventListener('pointermove', ev => {
  const [x, y] = toWorld(ev);
  if (drag) {
    drag.n.x = x;
    drag.n.y = y;
    drag.n.home = [x, y];
    drag.moved = true;
  } else if (panning) {
    view.x = panning.vx + (ev.clientX - panning.x);
    view.y = panning.vy + (ev.clientY - panning.y);
  } else {
    hover = pick(x, y);
    if (hover) {
      const r = cv.getBoundingClientRect();
      tip.style.display = 'block';
      tip.style.left = ev.clientX - r.left + 14 + 'px';
      tip.style.top = ev.clientY - r.top + 14 + 'px';
      tip.textContent = hover.info || hover.label;
    } else tip.style.display = 'none';
  }
});
cv.addEventListener('pointerup', ev => {
  if (drag) {
    const n = drag.n;
    if (!drag.moved) {
      if (n.type === 'house') window.open('/house?id=' + (+n.id.slice(1) + 1), '_blank');
    }
    n.fixed = false;
    drag = null;
  }
  panning = null;
});
cv.addEventListener('wheel', ev => {
  ev.preventDefault();
  const r = cv.getBoundingClientRect();
  const mx = ev.clientX - r.left,
    my = ev.clientY - r.top;
  const f = Math.exp(-ev.deltaY * 0.0015);
  view.x = mx - (mx - view.x) * f;
  view.y = my - (my - view.y) * f;
  view.k *= f;
}, {
  passive: false
});
init();
