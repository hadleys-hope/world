const $ = id => document.getElementById(id);
const BG = $('bg'),
  TR = $('trail'),
  TP = $('top'),
  bgc = BG.getContext('2d'),
  trc = TR.getContext('2d'),
  tpc = TP.getContext('2d'),
  tip = $('tip');
const COL = ['#5ec07a', '#e0b04a', '#e2574d', '#8a7aa6'],
  DUST = ['rgba(79,209,197,', 'rgba(224,176,74,', 'rgba(226,87,77,', 'rgba(138,122,166,'];
const TMIN = -58,
  TMAX = 35,
  RMIN = -3.2,
  RMAX = 2.2,
  C0 = 21,
  SQ = 1.5;
let A = null,
  H = null,
  W = 0,
  Hh = 0,
  dpr = 1,
  pad = {
    l: 46,
    r: 18,
    t: 100,
    b: 34
  },
  pollN = 0,
  dirty = true;
const opt = {
  dust: true,
  curves: true,
  houses: true
};
[['oDust', 'dust'], ['oCurves', 'curves'], ['oHouses', 'houses']].forEach(([id, k]) => $(id).onchange = e => {
  opt[k] = e.target.checked;
  dirty = true;
  if (k === 'dust') {
    trc.fillStyle = '#0f1115';
    trc.fillRect(0, 0, W, Hh);
  }
});
const asinh = Math.asinh,
  u0 = asinh((TMIN - C0) / SQ),
  u1 = asinh((TMAX - C0) / SQ);
const X = T => pad.l + (asinh((Math.max(TMIN, Math.min(TMAX, T)) - C0) / SQ) - u0) / (u1 - u0) * (W - pad.l - pad.r);
const Y = r => pad.t + (RMAX - Math.max(RMIN, Math.min(RMAX, r))) / (RMAX - RMIN) * (Hh - pad.t - pad.b);
function resize() {
  const r = $('wrap').getBoundingClientRect();
  dpr = devicePixelRatio || 1;
  W = r.width;
  Hh = r.height;
  for (const c of [BG, TR, TP]) {
    c.width = W * dpr;
    c.height = Hh * dpr;
    c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  dirty = true;
}
addEventListener('resize', resize);
function med(a) {
  const s = [...a].sort((x, y) => x - y);
  return s[s.length >> 1];
}
function drawBg() {
  const c = bgc;
  c.clearRect(0, 0, W, Hh);
  if (!A) return;
  const h = A.houses;
  c.font = '10.5px sans-serif';
  c.lineWidth = 1;
  for (const T of [-50, -20, 0, 10, 15, 18, 20, 21, 22, 24, 30]) {
    const x = X(T);
    c.strokeStyle = T === 21 ? '#24402f' : '#1a1f29';
    c.beginPath();
    c.moveTo(x, pad.t);
    c.lineTo(x, Hh - pad.b);
    c.stroke();
    c.fillStyle = '#5d6576';
    c.textAlign = 'center';
    c.fillText(T + '°', x, Hh - pad.b + 14);
  }
  for (let r = -3; r <= 2; r++) {
    const y = Y(r);
    c.strokeStyle = r === 0 ? '#39414f' : '#1a1f29';
    c.beginPath();
    c.moveTo(pad.l, y);
    c.lineTo(W - pad.r, y);
    c.stroke();
    c.fillStyle = '#5d6576';
    c.textAlign = 'right';
    c.fillText((r > 0 ? '+' : '') + r, pad.l - 6, y + 3);
  }
  c.fillStyle = '#5d6576';
  c.textAlign = 'left';
  c.fillText('°C per hour', 4, pad.t - 4);
  c.textAlign = 'right';
  c.fillText('indoor °C (stretched around the 21° target)', W - pad.r, Hh - 6);
  c.strokeStyle = 'rgba(226,87,77,.45)';
  c.setLineDash([4, 5]);
  c.beginPath();
  c.moveTo(X(0), pad.t);
  c.lineTo(X(0), Hh - pad.b);
  c.stroke();
  c.setLineDash([]);
  c.fillStyle = 'rgba(226,87,77,.7)';
  c.textAlign = 'left';
  c.fillText('pipes freeze below 0°', X(0) + 5, pad.t + 12);
  if (opt.curves) {
    const eqOn = med(h.eq_on),
      eqOff = med(h.eq_off),
      tau = med(h.tau),
      t0 = A.t_out;
    const curve = (eq, col, lab) => {
      c.strokeStyle = col;
      c.lineWidth = 1.5;
      c.beginPath();
      let first = true,
        lx = 0,
        ly = 0;
      for (let T = TMIN; T <= TMAX; T += 0.25) {
        const r = (eq - T) / tau;
        const x = X(T),
          y = Y(r);
        if (r > RMAX || r < RMIN) {
          first = true;
          continue;
        }
        first ? c.moveTo(x, y) : c.lineTo(x, y);
        first = false;
        lx = x;
        ly = y;
      }
      c.stroke();
      c.lineWidth = 1;
    };
    curve(eqOn, 'rgba(255,122,48,.45)');
    curve(eqOff, 'rgba(79,209,197,.35)');
    curve(t0 + 1, 'rgba(226,87,77,.35)');
    c.font = '11px sans-serif';
    c.textAlign = 'left';
    c.fillStyle = 'rgba(255,122,48,.8)';
    c.fillText('heater on', X(-35), Y((eqOn + 35) / tau) - 6);
    c.fillStyle = 'rgba(79,209,197,.75)';
    c.fillText('heater off', X(26), Y((eqOff - 26) / tau) + 14);
    c.fillStyle = 'rgba(226,87,77,.75)';
    c.fillText('no power', X(-10), Y((t0 + 1 + 10) / tau) + 14);
  }
  dirty = false;
}
let dust = [];
function seedDust(n) {
  dust = [];
  for (let i = 0; i < n; i++) dust.push(spawn({}));
}
function spawn(p) {
  p.j = Math.random() * (A?.houses.t.length || 300) | 0;
  p.T = TMIN + Math.random() * (TMAX - TMIN);
  p.on = Math.random() < .5;
  p.age = 0;
  p.life = 200 + Math.random() * 500;
  p.x = null;
  if (A) {
    const h = A.houses,
      j = p.j;
    if (h.eq_on[j] < h.target[j]) p.on = true;
    p.r = ((p.on ? h.eq_on[j] : h.eq_off[j]) - p.T) / h.tau[j];
  } else p.r = 0;
  return p;
}
function stepDust() {
  if (!A || A.paused) return;
  const h = A.houses,
    dt = 0.07;
  const c = trc;
  c.globalCompositeOperation = 'source-over';
  c.fillStyle = 'rgba(15,17,21,0.085)';
  c.fillRect(0, 0, W, Hh);
  c.globalCompositeOperation = 'lighter';
  if (!opt.dust) {
    c.globalCompositeOperation = 'source-over';
    return;
  }
  for (const p of dust) {
    const j = p.j,
      tg = h.target[j],
      eqOn = h.eq_on[j],
      eqOff = h.eq_off[j],
      tau = h.tau[j];
    if (p.T < tg - 0.5) p.on = true;else if (p.T > tg + 0.5) p.on = false;
    if (eqOn < tg) p.on = true;
    const want = ((p.on ? eqOn : eqOff) - p.T) / tau;
    const eq = p.on ? eqOn : eqOff;
    p.T = eq + (p.T - eq) * Math.exp(-dt / tau);
    p.r = (eq - p.T) / tau;
    p.age++;
    const x = X(p.T),
      y = Y(p.r);
    if (p.x !== null) {
      const a = Math.min(1, p.age / 40) * Math.min(1, (p.life - p.age) / 60) * 0.55;
      c.strokeStyle = DUST[h.basin[j]] + a + ')';
      c.beginPath();
      c.moveTo(p.x, p.y);
      c.lineTo(x, y);
      c.stroke();
    }
    p.x = x;
    p.y = y;
    if (p.age > p.life) spawn(p);
  }
  c.globalCompositeOperation = 'source-over';
}
let hp = [],
  hover = -1,
  pulse = 0;
function drawTop() {
  const c = tpc;
  c.clearRect(0, 0, W, Hh);
  if (!A) return;
  const h = A.houses;
  pulse += 0.03;
  const glow = (x, y, col, r0) => {
    for (let k = 3; k >= 1; k--) {
      c.beginPath();
      c.arc(x, y, r0 * k * (1 + 0.12 * Math.sin(pulse * 2)), 0, 7);
      c.fillStyle = col.replace('1)', 0.07 * (4 - k) + ')');
      c.fill();
    }
  };
  const tg = med(h.target);
  glow(X(tg), Y(0), 'rgba(94,192,122,1)', 14);
  c.strokeStyle = '#5ec07a';
  c.lineWidth = 1.5;
  c.beginPath();
  c.arc(X(tg), Y(0), 6, 0, 7);
  c.stroke();
  c.fillStyle = '#5ec07a';
  c.font = '600 11.5px sans-serif';
  c.textAlign = 'center';
  c.textAlign = 'left';
  c.fillText('comfort attractor ' + tg + '°', X(tg) + 62, Y(0) + 4);
  c.textAlign = 'center';
  glow(X(A.t_out + 1), Y(0), 'rgba(226,87,77,1)', 14);
  c.strokeStyle = '#e2574d';
  c.beginPath();
  c.arc(X(A.t_out + 1), Y(0), 6, 0, 7);
  c.stroke();
  c.fillStyle = '#e2574d';
  c.textAlign = 'left';
  c.fillText('freeze attractor ' + Math.round(A.t_out) + '°', Math.max(4, X(A.t_out + 1) - 20), Y(0) + 30);
  c.lineWidth = 1;
  if (!opt.houses) return;
  for (let i = 0; i < h.t.length; i++) {
    const tx = X(h.t[i]),
      ty = Y(h.rate[i]);
    if (!hp[i]) hp[i] = {
      x: tx,
      y: ty
    };
    const q = hp[i];
    q.x += (tx - q.x) * 0.12;
    q.y += (ty - q.y) * 0.12;
    const col = phaseColor(i);
    c.beginPath();
    c.arc(q.x, q.y, i === hover ? 6 : 3.2, 0, 7);
    c.fillStyle = col;
    c.globalAlpha = 0.95;
    c.fill();
    c.globalAlpha = 0.18;
    c.beginPath();
    c.arc(q.x, q.y, 8, 0, 7);
    c.fill();
    c.globalAlpha = 1;
  }
  if (hover >= 0) {
    const q = hp[hover];
    c.strokeStyle = '#fff';
    c.beginPath();
    c.arc(q.x, q.y, 7, 0, 7);
    c.stroke();
  }
}
const BASIN = ['warm: settles at its target', 'target cannot be maintained at the current heat gains', 'freezing: no heat to hold it above 0°', 'pipes burst, waiting for the plumber'];
TP.addEventListener('pointermove', ev => {
  if (!A || !opt.houses || phaseDrag) return;
  const r = TP.getBoundingClientRect(),
    mx = ev.clientX - r.left,
    my = ev.clientY - r.top;
  let best = -1,
    bd = 10;
  hp.forEach((q, i) => {
    const d = Math.hypot(q.x - mx, q.y - my);
    if (d < bd) {
      bd = d;
      best = i;
    }
  });
  hover = best;
  TP.style.cursor = best >= 0 ? 'pointer' : 'default';
  if (best < 0) {
    tip.style.display = 'none';
    return;
  }
  const h = A.houses,
    i = best;
  tip.innerHTML = `<b>House ${i + 1}</b>, sector ${h.sector[i] + 1}<br>${h.t[i].toFixed(1)}° now, ${h.rate[i] > 0 ? '+' : ''}${h.rate[i].toFixed(2)}°/h<br>water <b>${h.pressure_kpa[i]} kPa</b>, ${h.water_l_min[i]} L/min<br>conditional equilibrium <b>${h.att[i]}°</b> (heater on ${h.eq_on[i]}°, off ${h.eq_off[i]}°, time constant ${h.tau[i]} h)<br><span style="color:${COL[h.basin[i]]}">${BASIN[h.basin[i]]}</span>${h.ttf[i] > 0 ? `<br>reaches 0° in <b>${h.ttf[i]} h</b>` : ''}`;
  tip.style.display = 'block';
  tip.style.left = Math.min(mx + 14, W - 310) + 'px';
  tip.style.top = my + 14 + 'px';
});
TP.addEventListener('pointerleave', () => {
  hover = -1;
  tip.style.display = 'none';
});
TP.addEventListener('click', () => {
  if (!phaseMoved && hover >= 0) window.open('/house?id=' + (hover + 1), '_blank');
});
function panel(id) {
  const cv = $(id),
    r = cv.getBoundingClientRect();
  const d = devicePixelRatio || 1;
  if (cv.width !== Math.round(r.width * d) || cv.height !== Math.round(r.height * d)) {
    cv.width = Math.round(r.width * d);
    cv.height = Math.round(r.height * d);
  }
  const c = cv.getContext('2d');
  c.setTransform(d, 0, 0, d, 0, 0);
  c.clearRect(0, 0, r.width, r.height);
  return [c, r.width, r.height];
}
function frame(c, w, h, xr, yr, xl, yl) {
  const P = {
    l: 34,
    r: 8,
    t: 8,
    b: 16
  };
  const sx = v => P.l + (v - xr[0]) / (xr[1] - xr[0]) * (w - P.l - P.r),
    sy = v => P.t + (yr[1] - v) / (yr[1] - yr[0]) * (h - P.t - P.b);
  c.strokeStyle = '#222834';
  c.lineWidth = 1;
  c.strokeRect(P.l, P.t, w - P.l - P.r, h - P.t - P.b);
  c.fillStyle = '#5d6576';
  c.font = '10px sans-serif';
  c.textAlign = 'right';
  c.fillText(yl(yr[1]), P.l - 4, P.t + 8);
  c.fillText(yl(yr[0]), P.l - 4, h - P.b);
  c.textAlign = 'left';
  c.fillText(xl(xr[0]), P.l, h - 3);
  c.textAlign = 'right';
  c.fillText(xl(xr[1]), w - P.r, h - 3);
  if (yr[0] < 0 && yr[1] > 0) {
    c.strokeStyle = '#343b49';
    c.beginPath();
    c.moveTo(P.l, sy(0));
    c.lineTo(w - P.r, sy(0));
    c.stroke();
  }
  return [sx, sy];
}
function comet(c, pts, sx, sy, col) {
  if (pts.length < 2) return;
  for (let k = 1; k < pts.length; k++) {
    const a = k / pts.length;
    c.strokeStyle = col.replace('A', (0.08 + 0.8 * a * a).toFixed(3));
    c.lineWidth = 0.6 + 1.6 * a;
    c.beginPath();
    c.moveTo(sx(pts[k - 1][0]), sy(pts[k - 1][1]));
    c.lineTo(sx(pts[k][0]), sy(pts[k][1]));
    c.stroke();
  }
  const [x, y] = pts[pts.length - 1];
  c.fillStyle = col.replace('A', '0.25');
  c.beginPath();
  c.arc(sx(x), sy(y), 7 + 2 * Math.sin(pulse * 3), 0, 7);
  c.fill();
  c.fillStyle = col.replace('A', '1');
  c.beginPath();
  c.arc(sx(x), sy(y), 3, 0, 7);
  c.fill();
  c.lineWidth = 1;
}
function ring(c, x, y, col, lab) {
  c.strokeStyle = col;
  c.lineWidth = 1.5;
  c.beginPath();
  c.arc(x, y, 6, 0, 7);
  c.stroke();
  c.lineWidth = 1;
  if (lab) {
    c.fillStyle = col;
    c.font = '10px sans-serif';
    c.textAlign = 'center';
    c.fillText(lab, x, y - 10);
  }
}
function zone(c, sx, sy, x0, x1, y0, y1, col) {
  c.fillStyle = col;
  c.fillRect(sx(x0), sy(y1), sx(x1) - sx(x0), sy(y0) - sy(y1));
}
function setPill(id, v) {
  const e = $(id);
  e.className = 'pill ' + v[0];
  e.textContent = {
    ok: 'attractor',
    warn: 'drifting',
    bad: 'collapse basin'
  }[v[0]];
}
function col(k) {
  return H && H.fast_keys ? H.fast_keys.indexOf(k) : -1;
}
function drawPanels() {
  if (!A) return;
  const F = H && H.fast || [],
    S = H && H.slow || [];
  {
    const [c, w, h] = panel('cw');
    const wa = A.water,
      iT = col('tank'),
      iI = col('water_in'),
      iU = col('water_use');
    const pts = F.map(r => [r[iT], r[iI] - r[iU]]);
    const m = Math.max(3, ...pts.map(p => Math.abs(p[1]))) * 1.2;
    const xsw = pts.map(p => p[0]).concat([wa.v_star, wa.tank]);
    const wx0 = Math.max(0, Math.min(...xsw) - 15),
      wx1 = Math.min(wa.cap, Math.max(...xsw) + 8);
    const [sx, sy] = frame(c, w, h, [wx0, wx1], [-m, m], v => Math.round(v) + '', v => v.toFixed(0));
    c.strokeStyle = 'rgba(90,169,255,.35)';
    c.beginPath();
    for (let v = wx0; v <= wx1; v += (wx1 - wx0) / 120) {
      const inflow = wa.plant_ok ? Math.min(wa.max_m3_h * Math.max(.15, Math.min(1, (wa.cap - v) / 60)), Math.max(0, (wa.cap - v) * 60)) : 0;
      const y = sy(Math.max(-m, Math.min(m, inflow - wa.use)));
      v > wx0 ? c.lineTo(sx(v), y) : c.moveTo(sx(v), y);
    }
    c.stroke();
    comet(c, pts, sx, sy, 'rgba(90,169,255,A)');
    if (wa.v_star > 0) ring(c, sx(wa.v_star), sy(0), '#5ec07a', 'settles ' + Math.round(wa.v_star));else ring(c, sx(0), sy(0), '#e2574d', 'empty');
    setPill('pw', wa.verdict);
    $('vw').textContent = wa.verdict[1];
  }
  {
    const [c, w, h] = panel('cp');
    const iA = col('avail_kw'),
      iD = col('demand_kw'),
      iU = col('ups');
    const pts = F.map(r => [r[iA] - r[iD], r[iU] * 100]);
    const m = Math.max(500, ...pts.map(p => Math.abs(p[0]))) * 1.15;
    const [sx, sy] = frame(c, w, h, [-m, m], [0, 105], v => Math.round(v) + '', v => Math.round(v) + '%');
    zone(c, sx, sy, 0, m, 90, 105, 'rgba(94,192,122,.10)');
    zone(c, sx, sy, -m, 0, 0, 20, 'rgba(226,87,77,.12)');
    c.fillStyle = 'rgba(94,192,122,.7)';
    c.font = '10px sans-serif';
    c.textAlign = 'right';
    c.fillText('healthy', sx(m) - 4, sy(95));
    c.fillStyle = 'rgba(226,87,77,.7)';
    c.textAlign = 'left';
    c.fillText('blackout', sx(-m) + 4, sy(8));
    comet(c, pts, sx, sy, 'rgba(242,193,78,A)');
    setPill('pp', A.power.verdict);
    $('vp').textContent = A.power.verdict[1];
  }
  {
    const [c, w, h] = panel('cr');
    const iO = col('open'),
      iB = col('burst');
    const pts = F.map(r => [r[iO], r[iB]]);
    const mx = Math.max(8, ...pts.map(p => p[0])) * 1.15,
      my = Math.max(5, ...pts.map(p => p[1])) * 1.15;
    const [sx, sy] = frame(c, w, h, [0, mx], [0, my], v => Math.round(v) + '', v => Math.round(v) + '');
    const rho = A.repairs.rho;
    if (rho < 1) {
      const L = rho / (1 - rho);
      ring(c, sx(Math.min(mx, L)), sy(0), '#5ec07a', 'queue settles');
    }
    comet(c, pts, sx, sy, 'rgba(180,142,173,A)');
    setPill('pr', A.repairs.verdict);
    $('vr').textContent = `${A.repairs.verdict[1]} (${A.repairs.lam} new a day, crews close about ${A.repairs.mu})`;
  }
  {
    const [c, w, h] = panel('cm');
    const pts = [],
      G = r => r.length > 3 ? r[3] : r[1];
    for (let k = 4; k < S.length; k++) {
      pts.push([S[k][1] / 1000, (G(S[k]) - G(S[k - 4])) / 1000]);
    }
    const mo = A.money;
    const xs = pts.map(p => p[0]).concat([mo.colony / 1000, mo.target / 1000].concat(mo.colony < 30000 ? [0] : [])),
      ys = pts.map(p => Math.abs(p[1])).concat([2]);
    const x0 = Math.min(...xs) - 10,
      x1 = Math.max(...xs) + 10,
      m = Math.max(...ys) * 1.15;
    const [sx, sy] = frame(c, w, h, [x0, x1], [-m, m], v => Math.round(v) + 'k', v => v.toFixed(0));
    if (x0 < 0) zone(c, sx, sy, x0, 0, -m, m, 'rgba(226,87,77,.12)');
    c.strokeStyle = 'rgba(94,192,122,.35)';
    c.setLineDash([3, 4]);
    c.beginPath();
    c.moveTo(sx(mo.target / 1000), sy(m));
    c.lineTo(sx(mo.target / 1000), sy(-m));
    c.stroke();
    c.setLineDash([]);
    comet(c, pts, sx, sy, 'rgba(94,192,122,A)');
    if (mo.b_star) ring(c, sx(mo.b_star / 1000), sy(0), '#5ec07a', 'settles ' + Math.round(mo.b_star / 1000) + 'k');
    setPill('pm', mo.verdict);
    $('vm').textContent = mo.verdict[1] + (mo.last_levy ? `, last levy ${Math.round(mo.last_levy / 1000)}k` : '');
  }
}
function counts() {
  const h = A.houses,
    k = h.counts;
  $('counts').innerHTML = `<span class="ok">${k[0]} warm</span>, <span class="warn">${k[1]} cool</span>, <span class="bad">${k[2]} freezing</span>, ${k[3]} burst${h.first_freeze_h > 0 ? `; first pipes freeze in <b class="bad">${h.first_freeze_h} h</b>` : ''}. Outside ${A.t_out}°, wind ${A.wind} m/s.`;
  $('navtime').textContent = A.time;
}
// The original thermal phase portrait remains the default. The 3D view plots
// measured state dimensions, rather than adding an unrelated chaotic oscillator.
const BASIN_KEY = $('phase-colour-key').innerHTML;
let phaseView = 'thermal',
  phaseColour = 'basin',
  phaseYaw = -.65,
  phasePitch = .35,
  phaseDrag = null,
  phaseMoved = false,
  phaseSamples = [],
  phaseLastTick = -1;
const SECTOR_COL = ['#72c6ba', '#b3bd80', '#e0ad72', '#b394c7', '#7aaee2', '#cc929b'];
function phaseColor(i) {
  const h = A.houses;
  if (phaseColour === 'sector') return SECTOR_COL[h.sector[i] % 6];
  if (phaseColour === 'pressure') {
    const t = Math.max(0, Math.min(1, h.pressure_kpa[i] / 600));
    return `hsl(${12 + t * 173},65%,${56 + t * 8}%)`;
  }
  return COL[h.basin[i]];
}
function phasePoint(T, rate, pressure) {
  const x = (T - 10) / 35,
    y = rate / 2.4,
    z = pressure / 300 - 1;
  const xx = x * Math.cos(phaseYaw) - z * Math.sin(phaseYaw),
    zz = x * Math.sin(phaseYaw) + z * Math.cos(phaseYaw),
    yy = y * Math.cos(phasePitch) - zz * Math.sin(phasePitch),
    depth = y * Math.sin(phasePitch) + zz * Math.cos(phasePitch);
  const scale = Math.min(W * .23, Hh * .28),
    perspective = 3.8 / (3.8 + depth * .28);
  return {
    x: W * .5 + xx * scale * perspective,
    y: Hh * .47 - yy * scale * perspective,
    depth
  };
}
function setPhaseView(name) {
  phaseView = name;
  phaseMoved = false;
  dirty = true;
  hp = [];
  hover = -1;
  tip.style.display = 'none';
  trc.clearRect(0, 0, W, Hh);
  bgc.clearRect(0, 0, W, Hh);
  document.querySelectorAll('[data-phase]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.phase === name)));
  $('oDust').disabled = name === 'coupled';
  $('oCurves').disabled = name === 'coupled';
  $('phase-help').textContent = name === 'thermal' ? 'Thermal phase portrait · click a house to open its details' : 'Temperature × thermal rate × pressure · drag to rotate · click a house to inspect';
}
document.querySelectorAll('[data-phase]').forEach(b => b.onclick = () => setPhaseView(b.dataset.phase));
$('phase-colour').onchange = e => {
  phaseColour = e.target.value;
  dirty = true;
  $('phase-colour-key').innerHTML = phaseColour === 'pressure' ? 'Colour: red 0 kPa → cyan 600 kPa' : phaseColour === 'sector' ? SECTOR_COL.map((c, i) => `<span style="color:${c}">● District ${i + 1}</span>`).join(' · ') : BASIN_KEY;
};
function capturePhase(d) {
  if (d.t === phaseLastTick) return;
  if (d.t < phaseLastTick) phaseSamples = [];
  phaseLastTick = d.t;
  phaseSamples.push({
    t: d.t,
    T: d.houses.t,
    R: d.houses.rate,
    P: d.houses.pressure_kpa
  });
  if (phaseSamples.length > 90) phaseSamples.shift();
}
function drawCoupled() {
  const c = tpc;
  c.clearRect(0, 0, W, Hh);
  bgc.clearRect(0, 0, W, Hh);
  if (!A) return;
  const line = (a, b, color, width = 1) => {
    const p = phasePoint(...a),
      q = phasePoint(...b);
    c.beginPath();
    c.moveTo(p.x, p.y);
    c.lineTo(q.x, q.y);
    c.strokeStyle = color;
    c.lineWidth = width;
    c.stroke();
  };
  for (let t = -40; t <= 40; t += 20) line([t, 0, 0], [t, 0, 600], '#243637');
  for (let p = 0; p <= 600; p += 150) line([-40, 0, p], [40, 0, p], '#243637');
  line([-40, 0, 0], [40, 0, 0], '#b2ba86', 1.5);
  line([-40, -2.4, 0], [-40, 2.4, 0], '#b3a0cb', 1.5);
  line([-40, 0, 0], [-40, 0, 600], '#73bfc4', 1.5);
  c.font = '11px sans-serif';
  c.textAlign = 'center';
  for (const [pt, label, color] of [[[43, 0, 0], 'Temperature °C', '#b2ba86'], [[-40, 2.6, 0], 'Change °C / h', '#b3a0cb'], [[-40, 0, 650], 'Pressure kPa', '#73bfc4']]) {
    const q = phasePoint(...pt);
    c.fillStyle = color;
    c.fillText(label, q.x, q.y - 8);
  }
  for (const T of [-40, 0, 40]) {
    const q = phasePoint(T, 0, 0);
    c.fillStyle = '#b2ba86';
    c.fillText(String(T), q.x, q.y + 15);
  }
  for (const rate of [-2, 0, 2]) {
    const q = phasePoint(-40, rate, 0);
    c.fillStyle = '#b3a0cb';
    c.fillText(String(rate), q.x - 12, q.y);
  }
  for (const pressure of [0, 300, 600]) {
    const p = phasePoint(-40, 0, pressure);
    c.fillStyle = '#92a7a3';
    c.fillText(String(pressure), p.x - 10, p.y + 15);
  }
  // Recent real trajectories for the hovered house (or six district exemplars).
  const focus = hover >= 0 ? [hover] : Array.from({
    length: 6
  }, (_, k) => k * Math.floor(A.houses.t.length / 6));
  for (const i of focus) for (let k = 1; k < phaseSamples.length; k++) {
    const a = phaseSamples[k - 1],
      b = phaseSamples[k];
    if (b.t - a.t > Math.max(120, A.speed * 4)) continue;
    const p = phasePoint(a.T[i], a.R[i], a.P[i]),
      q = phasePoint(b.T[i], b.R[i], b.P[i]);
    c.globalAlpha = .08 + .48 * k / phaseSamples.length;
    c.strokeStyle = phaseColor(i);
    c.lineWidth = i === hover ? 2 : 1;
    c.beginPath();
    c.moveTo(p.x, p.y);
    c.lineTo(q.x, q.y);
    c.stroke();
  }
  c.globalAlpha = 1;
  const h = A.houses;
  hp = h.t.map((t, i) => phasePoint(t, h.rate[i], h.pressure_kpa[i]));
  if (opt.houses) hp.map((p, i) => ({
    p,
    i
  })).sort((a, b) => b.p.depth - a.p.depth).forEach(({
    p,
    i
  }) => {
    const color = phaseColor(i);
    c.fillStyle = color;
    c.globalAlpha = .13;
    c.beginPath();
    c.arc(p.x, p.y, i === hover ? 12 : 7, 0, Math.PI * 2);
    c.fill();
    c.globalAlpha = .95;
    c.beginPath();
    c.arc(p.x, p.y, i === hover ? 5.5 : 3.3, 0, Math.PI * 2);
    c.fill();
    if (i === hover) {
      c.strokeStyle = '#fff';
      c.stroke();
    }
  });
  c.globalAlpha = 1;
  c.fillStyle = '#8ca49b';
  c.font = '10px sans-serif';
  c.textAlign = 'left';
  c.fillText(`${phaseSamples.length} observed samples · trails ${hover >= 0 ? 'selected house' : 'one house per district'}`, pad.l, 54);
}
TP.addEventListener('pointerdown', e => {
  if (phaseView !== 'coupled') return;
  phaseDrag = {
    x: e.clientX,
    y: e.clientY,
    yaw: phaseYaw,
    pitch: phasePitch
  };
  phaseMoved = false;
  TP.setPointerCapture(e.pointerId);
});
TP.addEventListener('pointermove', e => {
  if (!phaseDrag) return;
  const dx = e.clientX - phaseDrag.x,
    dy = e.clientY - phaseDrag.y;
  if (Math.hypot(dx, dy) > 4) phaseMoved = true;
  phaseYaw = phaseDrag.yaw + dx * .006;
  phasePitch = Math.max(-1.1, Math.min(1.1, phaseDrag.pitch + dy * .005));
  tip.style.display = 'none';
});
TP.addEventListener('pointerup', () => {
  phaseDrag = null;
});
TP.addEventListener('pointercancel', () => {
  phaseDrag = null;
  phaseMoved = true;
});
async function poll() {
  try {
    const want = pollN++ % 10 === 0;
    const d = await (await fetch('/attractors.json' + (want ? '?hist=1' : ''))).json();
    if (want) H = d;
    const first = !A;
    A = d;
    capturePhase(d);
    $("connection").textContent = d.paused ? "Simulation paused" : "Live · tick " + d.t;
    if (first) seedDust(2600);
    dirty = true;
    counts();
  } catch (e) {
    $("connection").textContent = "Connection lost · retrying";
  }
  setTimeout(poll, 1000);
}
let fr = 0,
  lastFrame = 0;
function loop(now = 0) {
  requestAnimationFrame(loop);
  if (now - lastFrame < 33) return;
  lastFrame = now;
  if (phaseView === 'thermal') {
    if (dirty) drawBg();
    stepDust();
    drawTop();
  } else drawCoupled();
  if (fr++ % 3 === 0) drawPanels();
}
resize();
poll();
loop();
