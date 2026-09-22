const cv = document.getElementById('c'),
  ctx = cv.getContext('2d');
let G = null,
  S = null,
  packetsSeen = new Map(),
  lastFetch = 0,
  animT = 0;
const ADMIN = new URLSearchParams(location.search).get('admin') || localStorage.getItem('hh_admin') || '';
if (ADMIN) localStorage.setItem('hh_admin', ADMIN);
const post = async o => {
  const r = await fetch('/cmd', {
    method: 'POST',
    body: JSON.stringify({
      ...o,
      token: ADMIN
    })
  });
  if (r.status === 403 && !window.__ro) {
    window.__ro = true;
    alert('View only. Open the page as /?admin=TOKEN to control the colony.');
  }
};
document.getElementById('pause').onclick = () => post({
  cmd: 'pause'
});
document.querySelectorAll('button[data-s]').forEach(b => b.onclick = () => post({
  cmd: 'speed',
  value: +b.dataset.s
}));
document.querySelectorAll('button[data-i]').forEach(b => b.onclick = () => post({
  cmd: 'inject',
  value: b.dataset.i
}));
async function loadGeom() {
  G = await (await fetch('/geometry')).json();
}
async function poll() {
  try {
    const s = await (await fetch('/state')).json();
    S = s;
    lastFetch = performance.now();
    renderSide(s);
  } catch (e) {
    document.getElementById('banner').textContent = 'no connection';
  }
  setTimeout(poll, 250);
}

// ---------- coordinate transform ----------
let sc = 1,
  ox = 0,
  oy = 0;
function fit() {
  const W = cv.clientWidth,
    H = cv.clientHeight;
  cv.width = W * devicePixelRatio;
  cv.height = H * devicePixelRatio;
  const x0 = -1620,
    x1 = 800,
    y0 = -800,
    y1 = 800;
  sc = Math.min(W / (x1 - x0), H / (y1 - y0));
  ox = W / 2 - sc * (x0 + x1) / 2;
  oy = H / 2 - sc * (y0 + y1) / 2;
}
const X = x => ox + sc * x,
  Y = y => oy + sc * y;
function polar(a, r) {
  const t = a * Math.PI / 180;
  return [r * Math.cos(t), r * Math.sin(t)];
}

// ---------- colours ----------
function tempColor(t) {
  // -60..25 -> blue..white..orange
  const u = Math.max(0, Math.min(1, (t + 40) / 65));
  if (u < 0.6) {
    const k = u / 0.6;
    return `rgb(${Math.round(60 + 150 * k)},${Math.round(110 + 120 * k)},${Math.round(230 - 20 * k)})`;
  }
  const k = (u - 0.6) / 0.4;
  return `rgb(${Math.round(210 + 45 * k)},${Math.round(230 - 90 * k)},${Math.round(210 - 150 * k)})`;
}
const modeColor = {
  ONLINE: '#5ec07a',
  RUNBACK: '#e0b04a',
  SCRAM: '#e2574d',
  COOLING: '#e2574d',
  EMERGENCY: '#ff2a2a',
  CORE_DAMAGE: '#ff0000',
  STARTING: '#5aa9ff'
};

// ---------- drawing helpers ----------
function line(x0, y0, x1, y1, color, w, dash, off) {
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = w;
  ctx.setLineDash(dash || []);
  ctx.lineDashOffset = off || 0;
  ctx.moveTo(X(x0), Y(y0));
  ctx.lineTo(X(x1), Y(y1));
  ctx.stroke();
  ctx.setLineDash([]);
}
function flow(x0, y0, x1, y1, color, w, on, speed) {
  line(x0, y0, x1, y1, on ? color : '#3a3f4a', w);
  if (on) line(x0, y0, x1, y1, '#ffffff', Math.max(1, w - 1), [3, 9], -animT * speed);
}
function dot(x, y, r, color) {
  ctx.beginPath();
  ctx.fillStyle = color;
  ctx.arc(X(x), Y(y), r, 0, Math.PI * 2);
  ctx.fill();
}
function text(x, y, s, color, size, align) {
  ctx.fillStyle = color || '#d9dde6';
  ctx.font = `${size || 11}px sans-serif`;
  ctx.textAlign = align || 'center';
  ctx.fillText(s, X(x), Y(y));
}
function box(x, y, w, h, fill, stroke, label, sub) {
  ctx.fillStyle = fill;
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(X(x) - w / 2, Y(y) - h / 2, w, h, 6);else ctx.rect(X(x) - w / 2, Y(y) - h / 2, w, h);
  ctx.fill();
  ctx.stroke();
  if (label) text(x, y - 3, label, '#e8ecf3', 11);
  if (sub) text(x, y + 10, sub, '#9aa3b5', 10);
}
function draw() {
  fit();
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  ctx.clearRect(0, 0, cv.clientWidth, cv.clientHeight);
  animT = performance.now() / 40;
  if (!G || !S) {
    requestAnimationFrame(draw);
    return;
  }
  const c = G.cfg,
    R = c.ring_road_radius,
    WR = c.wall_radius,
    HR = c.hub_radius,
    ns = c.sectors;
  // sectors
  for (let s = 0; s < ns; s++) {
    const a0 = s * 60 * Math.PI / 180,
      a1 = (s + 1) * 60 * Math.PI / 180;
    ctx.beginPath();
    ctx.arc(X(0), Y(0), sc * WR, a0, a1);
    ctx.arc(X(0), Y(0), sc * (HR + 10), a1, a0, true);
    ctx.closePath();
    const sec = S.sectors[s];
    ctx.fillStyle = sec.lockdown ? 'rgba(226,87,77,.10)' : !sec.online ? 'rgba(226,87,77,.05)' : sec.dark ? 'rgba(0,0,0,.35)' : 'rgba(255,255,255,.025)';
    ctx.fill();
    const [lx, ly] = polar(s * 60 + 30, WR + 40);
    text(lx, ly, `S${s + 1}`, '#6d7689', 12);
  }
  // wall
  ctx.beginPath();
  ctx.strokeStyle = '#7c766e';
  ctx.lineWidth = 4;
  ctx.arc(X(0), Y(0), sc * WR, 0, Math.PI * 2);
  ctx.stroke();
  // roads: ring, boundary streets through the gates, row streets, trunk road, tower road, service road
  for (let s = 0; s < ns; s++) {
    const integ = S.sectors[s].road;
    const col = integ < 20 ? '#e2574d' : integ < 50 ? '#8a6a2a' : '#3d4350';
    ctx.beginPath();
    ctx.strokeStyle = col;
    ctx.lineWidth = S.power.road_heating ? 5 : 4;
    ctx.arc(X(0), Y(0), sc * R, s * 60 * Math.PI / 180, (s + 1) * 60 * Math.PI / 180);
    ctx.stroke();
    const [sx, sy] = polar(s * 60, HR),
      [ex, ey] = polar(s * 60, WR + 70);
    line(sx, sy, ex, ey, '#2e3440', 2);
    for (let k = 0; k <= c.house_rows; k++) {
      const r = c.house_radius_min - 30 + k * c.house_ring_step;
      ctx.beginPath();
      ctx.strokeStyle = '#262b36';
      ctx.lineWidth = 1.5;
      ctx.arc(X(0), Y(0), sc * r, (s * 60 + 2.5) * Math.PI / 180, (s * 60 + 57.5) * Math.PI / 180);
      ctx.stroke();
    }
  }
  line(-WR - 70, 0, c.reactor_pos[0] + 70, 0, '#3d4350', 4);
  line(c.tower_junction[0], c.tower_junction[1], c.tower_pos[0], c.tower_pos[1] + 40, '#2e3440', 2);
  line(c.reactor_pos[0] + 70, -40, c.reactor_pos[0] + 70, c.mine_pos[1] + 40, '#2e3440', 2);
  // gates in the wall at the sector boundaries
  for (let s = 0; s < ns; s++) {
    const [gx, gy] = polar(s * 60, WR);
    const st = S.sectors[s].gate;
    const col = st === 'LOCKDOWN' ? '#e2574d' : st === 'OPEN' ? '#5ec07a' : '#8a93a6';
    ctx.save();
    ctx.translate(X(gx), Y(gy));
    ctx.rotate(s * 60 * Math.PI / 180);
    ctx.fillStyle = col;
    ctx.fillRect(-3, -9, 6, 18);
    ctx.restore();
    if (!S.sectors[s].gate_ok) text(gx, gy - 12, '!', '#e2574d', 12);
  }
  // Both views consume the same utility graph.
  const waterOn = S.water.tank_m3 > 0 && S.water.pump;
  for (const e of G.utilities.links) {
    const pts = e.points;
    const on = (S.hydraulics.flow_l_s[e.id] || 0) > 0;
    for (let j = 0; j < pts.length - 1; j++) flow(pts[j][0], pts[j][1], pts[j + 1][0], pts[j + 1][1], on ? '#65bbd1' : '#344c54', e.kind === 'service' ? .55 : 1.15, on, .5);
  }

  // power: trunk, tower line, solar line, feeders, spans along the pole tree
  const reactorUp = S.reactor.available_mw > 0;
  flow(c.reactor_pos[0] + 70, 8, -HR + 10, 8, '#f2c14e', 3, S.power.trunk && reactorUp, 2.5);
  flow(c.tower_junction[0] + 7, 8, c.tower_pos[0] + 7, c.tower_pos[1] + 40, '#f2c14e', 1.2, S.power.tower_line && S.power.trunk && reactorUp, 2);
  flow(c.solar_pos[0] + 70, c.solar_pos[1] + 30, c.reactor_pos[0] + 40, -60, '#f2c14e', 1.2, S.power.solar_kw > 0, 2);
  for (let s = 0; s < ns; s++) {
    const [x1, y1] = polar(s * 60 + 1.6, HR + 20);
    flow(0, -40, x1, y1, '#f2c14e', 2, S.power.feeder[s] && S.sectors[s].online, 2);
  }
  for (let i = 0; i < G.poles.x.length; i++) {
    const p = G.poles.parent[i],
      s = G.poles.sector[i];
    let px0, py0;
    if (p < 0) {
      [px0, py0] = polar(s * 60 + 1.6, HR + 20);
    } else {
      px0 = G.poles.x[p];
      py0 = G.poles.y[p];
    }
    const px1 = G.poles.x[i],
      py1 = G.poles.y[i];
    flow(px0, py0, px1, py1, '#f2c14e', 1.6, S.poles.span[i] === 1, 2);
    const dx = px1 - px0,
      dy = py1 - py0,
      L = Math.hypot(dx, dy) || 1,
      nx = -dy / L * 5,
      ny = dx / L * 5;
    line(px0 + nx, py0 + ny, px1 + nx, py1 + ny, S.poles.net[i] === 1 ? '#4fd1c5' : '#4a3030', 1);
  }
  for (let i = 0; i < G.houses.x.length; i++) {
    const p = G.houses.pole[i];
    line(G.houses.x[i], G.houses.y[i], G.poles.x[p], G.poles.y[p], 'rgba(242,193,78,.12)', 1);
  }
  line(-HR + 10, 12, -WR - 40, 12, S.net.uplink ? '#4fd1c5' : '#4a3030', 1);
  line(-WR - 40, 12, c.tower_junction[0] - 6, 12, S.net.uplink ? '#4fd1c5' : '#4a3030', 1);
  line(c.tower_junction[0] - 6, 12, c.tower_pos[0] - 6, c.tower_pos[1] + 40, S.net.uplink ? '#4fd1c5' : '#4a3030', 1);
  // hub
  dot(0, 0, sc * HR, '#1c2028');
  ctx.beginPath();
  ctx.strokeStyle = S.power.substation ? '#f2c14e' : '#e2574d';
  ctx.lineWidth = 2;
  ctx.arc(X(0), Y(0), sc * HR, 0, Math.PI * 2);
  ctx.stroke();
  text(0, -60, 'substation', S.power.substation ? '#f2c14e' : '#e2574d', 11);
  text(0, -42, `${S.power.available_kw} / ${S.power.demand_kw} kW`, '#9aa3b5', 10);
  text(0, -16, `UPS center ${S.power.ups_center_kwh} kWh`, '#4fd1c5', 10);
  text(0, 4, S.net.comms ? `comms node, ${S.net.packets_per_min} pkt/min` : 'comms DOWN', S.net.comms && S.net.uplink ? '#4fd1c5' : '#e2574d', 11);
  text(0, 24, 'ops center, pump station', '#9aa3b5', 10);
  text(0, 44, `tank ${S.water.tank_m3} m3, ${S.water.flow_m3_h} m3/h`, waterOn ? '#5aa9ff' : '#e2574d', 10);
  // reactor complex
  const rc = modeColor[S.reactor.mode] || '#888';
  const rx = c.reactor_pos[0],
    ry = c.reactor_pos[1];
  box(c.solar_pos[0], c.solar_pos[1], 120, 34, '#20242e', '#7a6a2a', 'solar field', `${S.power.solar_kw} kW`);
  box(rx, ry, 150, 54, '#20242e', rc, `REACTOR ${S.reactor.mode}`, `${S.reactor.power_mw} MW el, core ${S.reactor.core_temp} C`);
  if (S.reactor.marines) text(rx, ry - 38, 'MARINES IN THE SUBLEVELS', '#e2574d', 10);
  box(c.water_plant_pos[0], c.water_plant_pos[1], 120, 34, '#20242e', S.water.plant ? '#5aa9ff' : '#e2574d', 'water plant', S.water.plant ? `${S.water.plant_m3_h} m3/h` : 'no heat');
  box(c.radwaste_pos[0], c.radwaste_pos[1], 150, 34, '#20242e', '#e8d34a', 'radioactive waste storage', `${S.power.infra.waste_storage} kW`);
  box(c.mine_pos[0], c.mine_pos[1], 110, 34, '#20242e', S.power.mine ? '#a08a2a' : '#5a5a5a', 'mine', S.power.mine ? `${S.power.infra.mine} kW` : 'stopped');
  box(c.waste_station_pos[0], c.waste_station_pos[1], 120, 30, '#20242e', '#9bd36a', 'waste processing', `${S.finance.waste_station} loads`);
  // tower
  const [tx, ty] = [c.tower_pos[0], c.tower_pos[1]];
  ctx.beginPath();
  ctx.strokeStyle = S.net.uplink ? '#4fd1c5' : '#e2574d';
  ctx.lineWidth = 2;
  ctx.moveTo(X(tx) - 10, Y(ty) + 18);
  ctx.lineTo(X(tx), Y(ty) - 18);
  ctx.lineTo(X(tx) + 10, Y(ty) + 18);
  ctx.stroke();
  text(tx, ty + 32, S.net.uplink ? 'uplink OK' : 'uplink LOST', S.net.uplink ? '#4fd1c5' : '#e2574d', 10);
  if (S.net.uplink) {
    for (let k = 0; k < 3; k++) {
      ctx.beginPath();
      ctx.strokeStyle = `rgba(79,209,197,${0.5 - 0.15 * k})`;
      ctx.arc(X(tx), Y(ty) - 14, 8 + 6 * k + animT * 2 % 6, -2.2, -0.9);
      ctx.stroke();
    }
  }
  // poles and lamps
  for (let i = 0; i < G.poles.x.length; i++) {
    const x = G.poles.x[i],
      y = G.poles.y[i],
      st = S.poles.state[i];
    if (S.poles.lamp[i] === 1) {
      const g = ctx.createRadialGradient(X(x), Y(y), 0, X(x), Y(y), sc * 22);
      g.addColorStop(0, 'rgba(255,230,140,.35)');
      g.addColorStop(1, 'rgba(255,230,140,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(X(x), Y(y), sc * 22, 0, Math.PI * 2);
      ctx.fill();
    }
    if (st === 2) {
      text(x, y + 4, 'x', '#e2574d', 13);
    } else dot(x, y, 2.2, st === 1 ? '#e0b04a' : '#c9cfdb');
  }
  // houses
  const hs = S.houses;
  const sz = Math.max(4, sc * 12);
  for (let i = 0; i < G.houses.x.length; i++) {
    const x = X(G.houses.x[i]),
      y = Y(G.houses.y[i]);
    ctx.fillStyle = tempColor(hs.t[i]);
    ctx.fillRect(x - sz / 2, y - sz / 2, sz, sz);
    if (!hs.power[i]) {
      ctx.strokeStyle = '#e2574d';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x - sz / 2, y - sz / 2, sz, sz);
    } else if (hs.ups[i]) {
      ctx.strokeStyle = '#5aa9ff';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x - sz / 2, y - sz / 2, sz, sz);
    } else if (hs.limit[i] > 0) {
      ctx.strokeStyle = '#e0b04a';
      ctx.lineWidth = 1;
      ctx.strokeRect(x - sz / 2, y - sz / 2, sz, sz);
    }
    if (hs.heater[i] && hs.power[i]) {
      ctx.fillStyle = '#ff7a30';
      ctx.fillRect(x - 1.5, y - 1.5, 3, 3);
    }
    if (hs.burst[i]) {
      ctx.strokeStyle = '#5aa9ff';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x - sz / 2, y - sz / 2);
      ctx.lineTo(x + sz / 2, y + sz / 2);
      ctx.moveTo(x + sz / 2, y - sz / 2);
      ctx.lineTo(x - sz / 2, y + sz / 2);
      ctx.stroke();
    }
  }
  // people
  for (const p of S.people) dot(p[0], p[1], 1.6, '#ffffff');
  // internet packets along the pole tree
  const now = performance.now();
  for (const p of S.net.packets) {
    const key = p.t + ':' + p.from + ':' + p.id;
    if (!packetsSeen.has(key)) packetsSeen.set(key, now);
  }
  for (const [key, t0] of packetsSeen) {
    if (now - t0 > 1800) {
      packetsSeen.delete(key);
      continue;
    }
    const [t, from, id] = key.split(':');
    const pk = S.net.packets.find(q => q.t + ':' + q.from + ':' + q.id === key);
    if (!pk) continue;
    let path = [];
    if (from === 'house') {
      const i = +id;
      let p = G.houses.pole[i],
        s = G.houses.sector[i];
      path.push([G.houses.x[i], G.houses.y[i]]);
      let guard = 0;
      while (p >= 0 && guard++ < 40) {
        path.push([G.poles.x[p], G.poles.y[p]]);
        p = G.poles.parent[p];
      }
      path.push(polar(s * 60 + 4.5, HR + 20));
      path.push([0, 0]);
    } else {
      path.push([0, 0]);
    }
    if (pk.kind === 'reactor' || pk.kind === 'lost') {
      path.push([-HR + 10, 8]);
      path.push([-WR - 40, 8]);
      path.push([rx + 70, 8]);
    } else if (pk.uplink) path.push([-HR + 10, 12], [-WR - 40, 12], [c.tower_junction[0] - 6, 12], [tx - 6, ty + 40]);
    const u = (now - t0) / 1800;
    let seg = Math.floor(u * (path.length - 1)),
      f = u * (path.length - 1) - seg;
    if (seg >= path.length - 1) {
      seg = path.length - 2;
      f = 1;
    }
    const [ax, ay] = path[seg],
      [bx, by] = path[seg + 1];
    dot(ax + (bx - ax) * f, ay + (by - ay) * f, 2.5, pk.uplink ? pk.kind === 'reactor' ? '#f2c14e' : '#4fd1c5' : '#e2574d');
  }
  // waste bins at the ring
  for (let s = 0; s < ns; s++) {
    const [bx, by] = polar(s * 60 + 30, R + 22);
    const w = S.sectors[s].waste;
    ctx.fillStyle = w >= 1 ? '#e2574d' : w >= 0.9 ? '#e0b04a' : '#3d4350';
    ctx.fillRect(X(bx) - 5, Y(by) - 5, 10, 10);
    ctx.fillStyle = '#8a93a6';
    ctx.fillRect(X(bx) - 4, Y(by) + 4 - 8 * Math.min(1, w), 8, 8 * Math.min(1, w));
  }
  // rovers
  const rc2 = {
    garbage: ['G', '#9bd36a'],
    sludge: ['S', '#b48ead'],
    repair: ['E', '#f2c14e'],
    plumber: ['P', '#5aa9ff']
  };
  for (const r of S.rovers) {
    const [l, col] = rc2[r.kind] || ['?', '#fff'];
    dot(r.x, r.y, 7, col);
    text(r.x, r.y + 4, l, '#111', 10);
    text(r.x, r.y + 16, r.state.toLowerCase().replace('_', ' '), '#9aa3b5', 9);
  }
  // xenomorphs and marines
  for (const x of S.xenos) {
    ctx.save();
    ctx.translate(X(x.x), Y(x.y));
    ctx.rotate(Math.PI / 4);
    ctx.fillStyle = '#e2574d';
    ctx.fillRect(-5, -5, 10, 10);
    ctx.restore();
  }
  for (const m of S.marines) dot(m[0], m[1], 2.5, '#8be05a');
  // issues
  for (const i of S.issues) {
    const col = i.sev === 'critical' ? '#e2574d' : i.sev === 'warning' ? '#e0b04a' : '#8a93a6';
    dot(i.x + 8, i.y - 8, 6, col);
    text(i.x + 8, i.y - 4, '!', '#111', 10);
  }
  // banner
  const e = S.env;
  document.getElementById('banner').innerHTML = `<b>${S.time}</b> &nbsp; ${e.t_out} C, wind ${e.wind} m/s${e.storm ? ' <span class="bad">STORM</span>' : ''}${e.precip === 'snow' ? ' snow' : ''}${e.night ? ' night' : ' day'}${S.paused ? ' <span class="warn">PAUSED</span>' : ''} &nbsp; ${S.speed} min/s`;
  const fin = document.getElementById('finished');
  if (S.finished) {
    fin.style.display = 'flex';
    fin.textContent = 'COLONY LOST: ' + S.finish_reason + '. A new colony is founded in two minutes.';
  } else fin.style.display = 'none';
  requestAnimationFrame(draw);
}
function cls(ok, warn) {
  return ok ? 'ok' : warn ? 'warn' : 'bad';
}
function renderSide(s) {
  document.getElementById('time').textContent = s.time;
  document.getElementById('pause').textContent = s.paused ? 'Resume' : 'Pause';
  document.querySelectorAll('button[data-s]').forEach(b => b.classList.toggle('on', +b.dataset.s === s.speed));
  const p = s.power,
    r = s.reactor,
    w = s.water,
    f = s.finance;
  const kp = [['Colony budget', f.colony.toLocaleString() + ' cr', f.colony > 20000 ? 'ok' : f.colony > 0 ? 'warn' : 'bad'], ['Sector budgets', f.sectors.map(x => Math.round(x / 1000) + 'k').join(' '), Math.min(...f.sectors) > 2000 ? 'ok' : 'warn'], ['Power available', p.available_kw + ' kW', p.available_kw > p.demand_kw ? 'ok' : 'bad'], ['Power demand', p.demand_kw + ' kW' + (p.shedding ? ` / shedding L${p.shedding}` : ''), p.shedding ? 'warn' : 'ok'], ['Water tank', w.tank_m3 + ' m3, ' + w.houses_ok + '/300 houses', w.tank_m3 > 100 && w.houses_ok > 280 ? 'ok' : 'warn'], ['Pipes', `${w.frozen} frozen, ${w.burst} burst`, w.burst === 0 ? 'ok' : 'bad'], ['Internet', `${s.net.houses_online}/300 online, uplink ${s.net.uplink ? 'OK' : 'LOST'}`, s.net.uplink && s.net.houses_online > 280 ? 'ok' : 'warn'], ['Open issues', s.issues_total + (f.unpaid ? ` (unpaid ${f.unpaid} cr)` : ''), s.issues_total < 5 ? 'ok' : 'warn'], ['Month income (colony)', f.month_income.toLocaleString() + ' cr', 'dim'], ['Month expense (colony)', f.month_expense.toLocaleString() + ' cr', 'dim']];
  document.getElementById('kpi').innerHTML = kp.map(([l, v, c]) => `<div class="card"><div class="v ${c}">${v}</div><div class="l">${l}</div></div>`).join('');
  const inf = p.infra;
  document.getElementById('reactor').innerHTML = `<div><b class="${r.mode === 'ONLINE' ? 'ok' : r.mode === 'RUNBACK' || r.mode === 'STARTING' ? 'warn' : 'bad'}">${r.mode}</b> &nbsp; ${r.power_mw} MW gross, ${r.available_mw} MW to grid, core ${r.core_temp} C${r.decay_mw ? `, decay ${r.decay_mw} MW` : ''}</div>
    <div class="dim">pumps A ${r.pump_a} B ${r.pump_b}, heat exchanger ${r.hx}, batteries ${r.battery_h} h, link ${r.link ? 'ok' : '<span class="bad">lost</span>'}${r.faults.length ? ', faults: ' + r.faults.join(', ') : ''}</div>
    <div class="dim">solar ${p.solar_kw} kW; loads: mine ${inf.mine}, houses ${Math.round(p.demand_kw - Object.values(inf).reduce((a, b) => a + b, 0))}, water plant ${inf.water_plant}, road heating ${inf.road_heating}, lamps ${inf.lamps}, comms ${inf.comms}, ups charge ${inf.ups_charge} kW</div>
    <div class="dim">trunk ${p.trunk ? 'ok' : '<span class="bad">CUT</span>'}, substation ${p.substation ? 'ok' : '<span class="bad">DOWN</span>'}, UPS center ${p.ups_center} ${p.ups_center_kwh} kWh</div>`;
  document.querySelector('#sectors tbody').innerHTML = s.sectors.map(x => `<tr><td>${x.id}${x.dark ? ' <span class="warn">dark</span>' : ''}</td><td>${x.budget}</td><td>${x.demand_kw}</td><td class="${x.avg_t > 15 ? 'ok' : x.avg_t > 4 ? 'warn' : 'bad'}">${x.avg_t}</td><td class="${x.min_t > 4 ? 'ok' : 'bad'}">${x.min_t}</td><td class="${cls(x.power_ok === 50, x.power_ok > 30)}">${x.power_ok}</td><td class="${cls(x.water_ok === 50, x.water_ok > 30)}">${x.water_ok}</td><td class="${cls(x.net_ok === 50, x.net_ok > 30)}">${x.net_ok}</td><td class="${x.ups === 'DISCHARGING' ? 'warn' : x.ups === 'DEPLETED' ? 'bad' : 'dim'}">${x.ups.slice(0, 4)} ${x.ups_kwh}</td><td class="${x.waste >= 1 ? 'bad' : x.waste >= 0.9 ? 'warn' : 'dim'}">${Math.round(x.waste * 100)}%</td><td class="${x.sanitary > 70 ? 'ok' : 'bad'}">${x.sanitary}</td><td class="${x.gate === 'OPEN' ? 'ok' : x.gate === 'LOCKDOWN' ? 'bad' : 'warn'}">${x.gate.slice(0, 4)}</td><td class="${x.road > 20 ? 'dim' : 'bad'}">${x.road}%</td></tr>`).join('');
  document.getElementById('nissues').textContent = `(${s.issues_total})`;
  document.getElementById('issues').innerHTML = s.issues.slice().reverse().map(i => `<div><span class="${i.sev === 'critical' ? 'bad' : i.sev === 'warning' ? 'warn' : 'dim'}">${i.kind}</span> ${i.target} ${i.sector > 0 ? 'S' + i.sector : ''} ${i.cause}, ${i.cost} cr (${i.payer}) <span class="dim">${i.status}, ${Math.round(i.age / 60)} h</span></div>`).join('') || '<div>none</div>';
  document.getElementById('log').innerHTML = s.events.map(e => `<div class="${e.level}">${String(e.t).padStart(6)} ${e.text}</div>`).join('');
  const rp = s.report;
  if (rp) {
    document.getElementById('report').textContent = `Month ${rp.month}: owners paid ${Math.round(rp.houses_total)} cr (energy ${Math.round(rp.energy_total)}, water ${Math.round(rp.water_total)}, repairs ${Math.round(rp.repairs_total)}), ${Math.round(rp.kwh_total)} kWh\n` + `colony: income ${rp.colony_income}, expense ${rp.colony_expense}, budget ${rp.colony_budget}, unpaid ${rp.unpaid}\n` + `sector income ${rp.sector_income.join(' | ')}\nsector expense ${rp.sector_expense.join(' | ')}\n` + `expense by cause: ${Object.entries(rp.by_cause).map(([k, v]) => k + ' ' + v).join(', ')}\n` + `top houses: ${rp.top_houses.map(h => `#${h.house} (S${h.sector}) ${h.total}`).join(', ')}`;
  }
}
cv.addEventListener('mousemove', ev => {
  const tip = document.getElementById('tip');
  if (!G || !S) {
    tip.style.display = 'none';
    return;
  }
  const r = cv.getBoundingClientRect(),
    mx = ev.clientX - r.left,
    my = ev.clientY - r.top;
  let best = -1,
    bd = 10;
  for (let i = 0; i < G.houses.x.length; i++) {
    const d = Math.hypot(X(G.houses.x[i]) - mx, Y(G.houses.y[i]) - my);
    if (d < bd) {
      bd = d;
      best = i;
    }
  }
  if (best < 0) {
    tip.style.display = 'none';
    return;
  }
  const h = S.houses,
    i = best;
  tip.innerHTML = `<b>House ${i + 1}</b> (S${G.houses.sector[i] + 1}, ${G.types[G.houses.type[i]]})<br>indoor ${h.t[i]} C, heater ${h.heater[i] ? 'on' : 'off'}<br>power ${h.power[i] ? h.ups[i] ? 'UPS' : 'grid' : '<span class="bad">none</span>'}${h.limit[i] ? ', limit ' + h.limit[i] + ' W' : ''}<br>water ${h.water[i] ? 'ok' : '<span class="bad">no</span>'}${h.burst[i] ? ', <span class="bad">pipes burst</span>' : ''}<br>internet ${h.net[i] ? 'online' : 'offline'}, sludge ${Math.round(h.sludge[i] * 100)}%`;
  tip.style.display = 'block';
  tip.style.left = mx + 14 + 'px';
  tip.style.top = my + 14 + 'px';
});
loadGeom().then(() => {
  poll();
  draw();
});
window.addEventListener('resize', fit);
