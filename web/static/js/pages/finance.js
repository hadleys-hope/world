let timer = null;
async function poll() {
  if (timer) clearTimeout(timer);
  try {
    render(await (await fetch('/finance.json')).json());
  } catch (e) {
    document.getElementById('sub').textContent = 'update failed';
  }
  timer = setTimeout(poll, 2000);
}
const cr = v => Math.round(v).toLocaleString() + ' cr';
const cls = st => (st === 'normal' ? 'ok' : st === 'overdue' ? 'warn' : 'bad');
function render(d) {
  const s = d.summary;
  document.getElementById('sub').textContent = d.time + (d.mine_closed_until ? `, mine flooded until ${d.mine_closed_until}` : '');
  document.getElementById('navtime').textContent = d.time;
  document.getElementById('kpi').innerHTML = [
    [cr(s.cash), `cash of ${s.households} households (${s.vacant} vacant houses are company housing)`, 'ok'],
    [cr(s.debt), `total debt: loans ${cr(s.principal)}, interest ${cr(s.interest)}, unpaid bills ${cr(s.arrears)}`, s.debt > 0 ? 'warn' : 'ok'],
    [s.debtors, `households in debt, ${s.borrowers} with loans`, s.debtors ? 'warn' : 'ok'],
    [s.overdue, 'households overdue', s.overdue ? 'warn' : 'ok'],
    [s.bankrupt, 'households bankrupt', s.bankrupt ? 'bad' : 'ok']
  ].map(([v, l, c]) => `<div class="card gauge"><div class="v ${c}">${v}</div><div class="l">${l}</div></div>`).join('');
  const k = name => d.series_keys.indexOf(name);
  const col = name => d.series.map(r => r[k(name)]);
  const cash = col('cash'),
    debt = col('principal').map((p, i) => p + col('interest')[i] + col('arrears')[i]);
  spark('sparkc', cash, '#5ec07a', 0, Math.ceil(Math.max(100, ...cash)));
  spark('sparkd', debt, '#e0b04a', 0, Math.ceil(Math.max(100, ...debt)));
  const debtors = col('debtors'),
    bankrupt = col('bankrupt');
  const top = Math.max(5, ...debtors);
  spark('sparkn', debtors, '#e0b04a', 0, top);
  spark('sparkn', bankrupt, '#e2574d', 0, top, true);
  document.getElementById('scen').innerHTML = d.scenario.length ? d.scenario.map(h => `<tr><td><a href="/house?id=${h.house}">house ${h.house}</a> ${h.label}</td><td><b class="${cls(h.status)}">${h.status}</b>, cash ${h.cash.toFixed(2)} cr, debt ${h.debt.toFixed(2)} cr</td></tr>`).join('') : '<tr><td>none</td><td class="dim">start with --scenario finance-demo</td></tr>';
  document.getElementById('trouble').innerHTML = d.trouble.length ? d.trouble.map(h => `<tr><td><a href="/house?id=${h.house}">house ${h.house}</a> <span class="dim">S${h.sector}, ${h.employer}${h.label ? ', ' + h.label : ''}</span></td><td><b class="${cls(h.status)}">${h.status}</b>, loans ${h.principal.toFixed(2)}, interest ${h.interest.toFixed(2)}, unpaid bills ${h.arrears.toFixed(2)}, cash ${h.cash.toFixed(2)}</td></tr>`).join('') : '<tr><td>nobody</td><td class="dim">every household is paid up</td></tr>';
  document.getElementById('rules').innerHTML = d.rules.map(r => `<tr><td>${r.meaning}</td><td>${typeof r.value === 'object' ? Object.entries(r.value).map(([a, b]) => a + ' ' + b).join(', ') : r.value}</td></tr>`).join('');
  document.getElementById('flows').innerHTML = d.flows_month.slice(0, 24).map(f => `<tr><td>${f.from} → ${f.to} <span class="dim">${f.what}</span></td><td>${f.amount.toLocaleString()} cr</td></tr>`).join('') || '<tr><td>nothing yet this month</td><td></td></tr>';
  const c = d.check;
  document.getElementById('check').innerHTML = [
    ['colony + sectors + household cash', c.internal_total.toLocaleString() + ' cr'],
    ['at the start', c.baseline.toLocaleString() + ' cr'],
    ['net from outside (Company, ore buyer, bank, suppliers)', c.external_net.toLocaleString() + ' cr'],
    ['unexplained', `<b class="${Math.abs(c.unexplained) < 0.01 ? 'ok' : 'bad'}">${c.unexplained} cr</b>`]
  ].map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join('');
}
// the same drawing as spark() on the house page; `over` draws on top of the previous series
function spark(id, arr, col, lo, hi, over) {
  const cv = document.getElementById(id),
    c = cv.getContext('2d');
  const W = cv.width,
    H = cv.height;
  if (!over) {
    c.clearRect(0, 0, W, H);
    c.strokeStyle = '#2a2f3a';
    c.lineWidth = 1;
    c.beginPath();
    for (let k = 0; k <= 4; k++) {
      const y = H - 1 - (H - 2) * k / 4;
      c.moveTo(0, y);
      c.lineTo(W, y);
    }
    c.stroke();
  }
  c.strokeStyle = col;
  c.lineWidth = 2;
  c.beginPath();
  arr.forEach((v, i) => {
    const x = arr.length > 1 ? i / (arr.length - 1) * W : 0,
      y = H - 1 - (H - 2) * Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    i ? c.lineTo(x, y) : c.moveTo(x, y);
  });
  c.stroke();
  if (!over) {
    c.fillStyle = '#8a93a6';
    c.font = '10px sans-serif';
    c.fillText(lo, 2, H - 3);
    c.fillText(hi.toLocaleString(), 2, 10);
  }
}
poll();
