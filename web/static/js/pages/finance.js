/* Finance: the month's ledger as a living picture. Every flow between two parties is a lane; coins run
   along it, more coins for more money, so you see where the money goes. Data: /finance.json (the ledger the
   world keeps) and /state (each house's cash). */
const NODES = [
  { id: 'company', name: 'Company', sub: 'wages and company housing', x: 0.11, y: 0.22, tone: '#9fb6c9' },
  { id: 'ore', name: 'Ore buyers', sub: 'pay for the mine output', x: 0.11, y: 0.55, tone: '#9fb6c9' },
  { id: 'bank', name: 'Bank', sub: 'household loans', x: 0.11, y: 0.86, tone: '#9fb6c9' },
  { id: 'colony', name: 'Colony treasury', sub: 'budget', x: 0.44, y: 0.22, tone: '#e8b86b' },
  { id: 'sectors', name: 'Sectors', sub: 'six district budgets', x: 0.44, y: 0.78, tone: '#b9a7d6' },
  { id: 'house', name: 'Households', sub: 'occupied houses', x: 0.76, y: 0.52, tone: '#7fd1b9' },
  { id: 'suppliers', name: 'Suppliers', sub: 'materials, shipments, waste', x: 0.88, y: 0.14, tone: '#9fb6c9' },
];
const byId = Object.fromEntries(NODES.map((n) => [n.id, n]));
const party = (p) => (p.startsWith('ext:') ? p.slice(4) : p.startsWith('sector:') ? 'sectors' : p);
const cr = (v) => (Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : Math.round(v).toLocaleString('en-US').replace(/,/g, ' ')) + ' cr';
const $ = (id) => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';

let D = null, cash = [], period = 'month', focus = 'house', bin = -1;
let lanes = [];          // {key, from, to, amount, whats, path, len, coins: [{el, t}], dash, label}
let W = 0, H = 0;

document.querySelectorAll('[data-period]').forEach((b) => (b.onclick = () => {
  period = b.dataset.period;
  signature = '';
  document.querySelectorAll('[data-period]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  build();
}));

function flows() {
  const f = period === 'month' ? D.flows_month : D.flows_prev_month;
  const agg = new Map();
  for (const x of f) {
    const a = party(x.from), b = party(x.to);
    if (!byId[a] || !byId[b] || a === b) continue;
    const key = a + '>' + b;
    const e = agg.get(key) || { key, from: a, to: b, amount: 0, whats: new Map() };
    e.amount += x.amount;
    e.whats.set(x.what, (e.whats.get(x.what) || 0) + x.amount);
    agg.set(key, e);
  }
  return [...agg.values()].sort((p, q) => q.amount - p.amount);
}

function geometry(e, back) {
  const A = byId[e.from], B = byId[e.to];
  const x1 = A.x * W, y1 = A.y * H, x2 = B.x * W, y2 = B.y * H;
  const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1;
  const bend = (back ? -1 : 1) * Math.min(90, L * 0.18);   // two-way pairs bow apart
  const mx = (x1 + x2) / 2 - (dy / L) * bend, my = (y1 + y2) / 2 + (dx / L) * bend;
  // the label sits on the curve, nearer the source, so the two labels of a two-way pair never meet
  const t = 0.38, u = 1 - t;
  return { d: `M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`, lx: u * u * x1 + 2 * u * t * mx + t * t * x2, ly: u * u * y1 + 2 * u * t * my + t * t * y2 };
}

function build() {
  const stage = $('flow-stage');
  W = stage.clientWidth; H = stage.clientHeight;
  const svg = $('flow-svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = '';
  lanes = [];
  const list = flows();
  $('flow-empty').hidden = list.length > 0;
  const max = Math.max(1, ...list.map((e) => e.amount));
  const keys = new Set(list.map((e) => e.key));
  for (const e of list) {
    const g = geometry(e, keys.has(e.to + '>' + e.from) && e.from > e.to);
    const width = 2 + 14 * Math.sqrt(e.amount / max);
    const tone = byId[e.from].tone;
    const lane = document.createElementNS(NS, 'path');
    lane.setAttribute('d', g.d); lane.setAttribute('class', 'lane');
    lane.setAttribute('stroke', tone); lane.setAttribute('stroke-width', width); lane.setAttribute('stroke-opacity', '0.18');
    const dash = document.createElementNS(NS, 'path');
    dash.setAttribute('d', g.d); dash.setAttribute('class', 'lane-dash');
    dash.setAttribute('stroke', tone); dash.setAttribute('stroke-width', Math.max(1, width / 3)); dash.setAttribute('stroke-opacity', '0.55');
    const label = document.createElementNS(NS, 'text');
    label.setAttribute('x', g.lx); label.setAttribute('y', g.ly - 8); label.setAttribute('text-anchor', 'middle'); label.setAttribute('class', 'lane-label');
    label.textContent = cr(e.amount);
    svg.append(lane, dash);
    const len = lane.getTotalLength();
    // more money, more coins: from 2 to 16 coins on a lane, all moving at the same speed
    const n = Math.round(2 + 14 * Math.sqrt(e.amount / max));
    const coins = [];
    for (let i = 0; i < n; i++) {
      const c = document.createElementNS(NS, 'circle');
      c.setAttribute('r', 2.2 + 2.6 * Math.sqrt(e.amount / max)); c.setAttribute('class', 'coin');
      c.setAttribute('fill', tone); c.style.color = tone;
      svg.append(c);
      coins.push({ el: c, t: i / n + Math.random() * 0.02 });
    }
    svg.append(label);
    lanes.push({ ...e, path: lane, dash, label, len, coins });
  }
  nodes(list);
  highlight();
  detail(list);
}

function nodes(list) {
  const box = $('flow-nodes');
  box.innerHTML = '';
  for (const n of NODES) {
    const inn = list.filter((e) => e.to === n.id).reduce((s, e) => s + e.amount, 0);
    const out = list.filter((e) => e.from === n.id).reduce((s, e) => s + e.amount, 0);
    if (!inn && !out) continue;
    const b = document.createElement('button');
    b.style.left = (n.x * 100) + '%'; b.style.top = (n.y * 100) + '%';
    b.setAttribute('aria-pressed', String(focus === n.id));
    const net = inn - out;
    b.innerHTML = `<b>${n.name}</b><span class="bal" style="color:${net >= 0 ? 'var(--hh-ok)' : 'var(--hh-bad)'}">${net >= 0 ? '+' : '−'}${cr(Math.abs(net))}</span><span class="sub">${n.sub}</span>`;
    b.onclick = () => { focus = n.id; build(); };
    box.append(b);
  }
}

function highlight() {
  for (const l of lanes) {
    const on = l.from === focus || l.to === focus;
    const op = on ? 1 : 0.18;
    l.path.style.opacity = op; l.dash.style.opacity = op; l.label.style.opacity = on ? 1 : 0;
    l.coins.forEach((c) => (c.el.style.opacity = op));
  }
}

function detail(list) {
  const n = byId[focus];
  $('node-name').textContent = n.name;
  const rows = [];
  let net = 0;
  for (const e of list) {
    if (e.from !== focus && e.to !== focus) continue;
    const incoming = e.to === focus;
    const other = byId[incoming ? e.from : e.to].name.toLowerCase();
    for (const [what, v] of [...e.whats.entries()].sort((a, b) => b[1] - a[1])) {
      rows.push(`<div class="row-f"><span>${incoming ? 'from' : 'to'} ${other}: ${what}</span><span class="${incoming ? 'in' : 'out'}">${incoming ? '+' : '−'}${cr(v)}</span></div>`);
    }
    net += incoming ? e.amount : -e.amount;
  }
  $('node-net').textContent = (net >= 0 ? '+' : '−') + cr(Math.abs(net));
  $('node-net').style.color = net >= 0 ? 'var(--hh-ok)' : 'var(--hh-bad)';
  $('node-rows').innerHTML = rows.join('') || '<div class="row-f"><span>nothing this period</span><span></span></div>';
}

let last = performance.now();
function animate(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  for (const l of lanes) {
    const step = (70 * dt) / Math.max(60, l.len);   // the same 70 px/s on every lane
    for (const c of l.coins) {
      c.t = (c.t + step) % 1;
      const p = l.path.getPointAtLength(c.t * l.len);
      c.el.setAttribute('cx', p.x); c.el.setAttribute('cy', p.y);
    }
  }
  requestAnimationFrame(animate);
}

function series() {
  const k = (n) => D.series_keys.indexOf(n);
  const rows = D.series.slice(-30);
  const svg = $('series-svg');
  if (rows.length < 2) { svg.innerHTML = ''; return; }
  const w = 1000, h = 100;
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  const cols = {
    colony: rows.map((r) => r[k('colony')]),
    cash: rows.map((r) => r[k('cash')]),
    debt: rows.map((r) => r[k('principal')] + r[k('interest')] + r[k('arrears')]),
  };
  const all = [...cols.colony, ...cols.cash, ...cols.debt, 0];
  const lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1;
  const pts = (v) => v.map((y, i) => `${(i / (v.length - 1)) * w},${h - 4 - ((y - lo) / span) * (h - 8)}`).join(' L ');
  const zero = h - 4 - ((0 - lo) / span) * (h - 8);
  const sig = rows.length + ':' + rows[rows.length - 1][0];
  const fresh = svg.dataset.sig !== sig;
  svg.dataset.sig = sig;
  svg.innerHTML = `<line x1="0" x2="${w}" y1="${zero}" y2="${zero}" stroke="var(--hh-line-strong)" stroke-dasharray="4 6" vector-effect="non-scaling-stroke"/>
    <path class="line${fresh ? ' draw' : ''}" stroke="#ff8a72" d="M ${pts(cols.colony)}"/>
    <path class="line${fresh ? ' draw' : ''}" stroke="#7fd1b9" d="M ${pts(cols.cash)}"/>
    <path class="line${fresh ? ' draw' : ''}" stroke="#e8b86b" d="M ${pts(cols.debt)}"/>`;
  const read = (i) => {
    $('series-read').textContent = `day ${Math.round(rows[i][0] / 1440)}: colony ${cr(cols.colony[i])} · households ${cr(cols.cash[i])} · debt ${cr(cols.debt[i])}`;
  };
  read(rows.length - 1);
  svg.onmousemove = (ev) => {
    const r = svg.getBoundingClientRect();
    read(Math.max(0, Math.min(rows.length - 1, Math.round(((ev.clientX - r.left) / r.width) * (rows.length - 1)))));
  };
  svg.onmouseleave = () => read(rows.length - 1);
}

function histogram() {
  const held = cash.map((v, i) => [v, i]).filter(([v]) => v > 0);
  const top = Math.max(100, ...held.map(([v]) => v));
  const step = Math.ceil(top / 8 / 50) * 50;
  const bins = Array.from({ length: 8 }, () => []);
  held.forEach(([v, i]) => bins[Math.min(7, Math.floor(v / step))].push(i));
  const most = Math.max(1, ...bins.map((b) => b.length));
  const box = $('hist');
  if (box.children.length !== 8) box.innerHTML = Array.from({ length: 8 }, () => '<button></button>').join('');
  [...box.children].forEach((b, j) => {
    b.style.height = Math.max(2, (bins[j].length / most) * 100) + '%';
    b.setAttribute('aria-pressed', String(bin === j));
    b.setAttribute('aria-label', `${bins[j].length} households with ${j * step}–${(j + 1) * step - 1} cr`);
    b.onclick = () => { bin = bin === j ? -1 : j; histogram(); };
  });
  $('hist-total').textContent = `${held.length} with cash`;
  $('hist-mid').textContent = cr(step * 4);
  $('hist-max').textContent = cr(step * 8) + '+';
  $('hist-read').innerHTML = bin < 0 ? 'Click a bar to see who is in it.'
    : `${bins[bin].length} households with ${bin * step}–${(bin + 1) * step - 1} cr: ` +
      bins[bin].slice(0, 12).map((i) => `<a href="/house?id=${i + 1}">#${i + 1}</a>`).join('') + (bins[bin].length > 12 ? ' …' : '');
}

function tables() {
  const s = D.summary;
  $('tiles').innerHTML = [[s.debtors, 'in debt'], [s.overdue, 'overdue'], [s.bankrupt, 'bankrupt']]
    .map(([v, l]) => `<div><b style="color:${v ? 'var(--hh-bad)' : 'var(--hh-ok)'}">${v}</b><span>${l}</span></div>`).join('');
  const cls = (st) => (st === 'normal' ? 'ok' : st === 'overdue' ? 'warn' : 'bad');
  $('debt-count').textContent = D.trouble.length ? `(${D.trouble.length})` : '';
  $('trouble').innerHTML = D.trouble.length ? D.trouble.map((h) => `<tr><td><a href="/house?id=${h.house}">house ${h.house}</a> <span class="dim">S${h.sector}, ${h.employer}</span></td><td class="${cls(h.status)}">${h.status}</td><td>${cr(h.principal + h.interest + h.arrears)}</td></tr>`).join('') : '<tr><td class="dim">Every household is paid up.</td></tr>';
  $('scen').innerHTML = D.scenario.map((h) => `<tr><td><a href="/house?id=${h.house}">house ${h.house}</a> ${h.label}</td><td class="${cls(h.status)}">${h.status}</td></tr>`).join('');
  $('rules').innerHTML = D.rules.map((r) => `<tr><td>${r.meaning}</td><td>${typeof r.value === 'object' ? Object.entries(r.value).map(([a, b]) => a + ' ' + b).join(', ') : r.value}</td></tr>`).join('');
  const c = D.check, off = Math.abs(c.unexplained) > 0.01;
  $('books').textContent = off ? `books off by ${cr(c.unexplained)}` : 'books balance';
  $('books').className = 'books' + (off ? ' off' : '');
  $('books').title = `money inside the colony ${cr(c.internal_total)} = starting money ${cr(c.baseline)} + net from outside ${cr(c.external_net)}`;
}

let signature = '';
async function poll() {
  try {
    const [d, s] = await Promise.all([fetch('/finance.json').then((r) => r.json()), fetch('/state').then((r) => r.json())]);
    D = d; cash = s.houses.cash || [];
    $('navtime').textContent = d.time;
    // New lanes rebuild the picture; otherwise only the numbers change, and the coins keep running.
    const list = flows();
    const sig = list.map((e) => e.key).join(',') + '|' + period;
    if (sig !== signature || !lanes.length) { signature = sig; build(); }
    else {
      const byKey = new Map(list.map((e) => [e.key, e]));
      lanes.forEach((l) => { const e = byKey.get(l.key); l.amount = e.amount; l.whats = e.whats; l.label.textContent = cr(e.amount); });
      nodes(list); detail(list);
    }
    series(); histogram(); tables();
  } catch (e) { /* keep animating what we have */ }
  setTimeout(poll, 3000);
}
window.addEventListener('resize', () => D && build());
requestAnimationFrame(animate);
poll();
