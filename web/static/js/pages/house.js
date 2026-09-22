const q = new URLSearchParams(location.search);
let id = Math.max(1, Math.min(300, +(q.get('id') || 1)));
document.getElementById('hid').value = id;
const setId = v => {
  id = Math.max(1, Math.min(300, v));
  document.getElementById('hid').value = id;
  history.replaceState(null, '', '/house?id=' + id);
  poll(true);
};
document.getElementById('prev').onclick = () => setId(id - 1);
document.getElementById('next').onclick = () => setId(id + 1);
document.getElementById('go').onclick = () => setId(+document.getElementById('hid').value || 1);
document.getElementById('hid').onkeydown = e => {
  if (e.key === 'Enter') setId(+e.target.value || 1);
};
let timer = null;
async function poll(now) {
  if (timer) clearTimeout(timer);
  try {
    const d = await (await fetch('/house.json?id=' + id)).json();
    render(d);
  } catch (e) {
    document.getElementById('sub').textContent = 'update failed';
  }
  timer = setTimeout(poll, 1000);
}
function thermo(t, target) {
  const u = Math.max(0, Math.min(1, (t + 50) / 80));
  const y = 120 - 90 * u;
  const ty = 120 - 90 * Math.max(0, Math.min(1, (target + 50) / 80));
  const col = t > 19 ? '#5ec07a' : t > 10 ? '#e0b04a' : '#e2574d';
  return `<svg viewBox="0 0 80 150"><rect x="30" y="20" width="20" height="110" rx="10" fill="#0b0e13" stroke="#8a93a6"/><rect x="34" y="${y}" width="12" height="${130 - y}" rx="6" fill="${col}"/><circle cx="40" cy="128" r="14" fill="${col}"/><line x1="22" y1="${ty}" x2="58" y2="${ty}" stroke="#5aa9ff" stroke-width="2"/><text x="62" y="${ty + 4}" fill="#5aa9ff" font-size="9">${target}</text>${[-40, -20, 0, 20].map(v => `<text x="10" y="${124 - 90 * (v + 50) / 80}" fill="#8a93a6" font-size="8">${v}</text>`).join('')}</svg>`;
}
function tank(frac, ok) {
  const h = 90 * Math.max(0, Math.min(1, frac));
  const col = ok ? '#5aa9ff' : '#e2574d';
  return `<svg viewBox="0 0 120 150"><rect x="20" y="25" width="80" height="100" rx="8" fill="#0b0e13" stroke="#8a93a6"/><rect x="24" y="${121 - h}" width="72" height="${h}" rx="6" fill="${col}" opacity=".8"/><path d="M60 8 v14" stroke="${col}" stroke-width="6"/><rect x="40" y="128" width="40" height="8" fill="#5a6070"/>${ok ? '' : '<text x="60" y="80" fill="#fff" font-size="12" text-anchor="middle">NO WATER</text>'}</svg>`;
}
function bolt(ok, ups, limit, upsFrac) {
  const col = !ok ? '#e2574d' : ups ? '#4fd1c5' : '#f2c14e';
  return `<svg viewBox="0 0 120 150"><circle cx="60" cy="70" r="46" fill="#0b0e13" stroke="${col}" stroke-width="3"/><path d="M68 28 L44 76 H62 L52 112 L82 60 H64 Z" fill="${col}"/>${ups ? `<rect x="20" y="126" width="80" height="10" rx="3" fill="#0b0e13" stroke="#8a93a6"/><rect x="22" y="128" width="${76 * upsFrac}" height="6" rx="2" fill="#4fd1c5"/>` : ''}${limit ? `<text x="60" y="145" fill="#e0b04a" font-size="10" text-anchor="middle">limit ${limit} W</text>` : ''}</svg>`;
}
function wifi(ok, cab) {
  const col = ok ? '#4fd1c5' : '#e2574d';
  return `<svg viewBox="0 0 120 150">${[46, 34, 22].map((r, k) => `<path d="M${60 - r} 90 A${r} ${r} 0 0 1 ${60 + r} 90" fill="none" stroke="${k < (ok ? 3 : 1) ? col : '#2a2f3a'}" stroke-width="6" stroke-linecap="round"/>`).join('')}<circle cx="60" cy="100" r="6" fill="${col}"/>${ok ? '' : `<line x1="30" y1="40" x2="90" y2="115" stroke="#e2574d" stroke-width="5"/>`}<text x="60" y="140" fill="#8a93a6" font-size="10" text-anchor="middle">${cab ? 'cabinet up' : 'cabinet down'}</text></svg>`;
}
function sludge(frac, ok) {
  const h = 90 * Math.max(0, Math.min(1, frac));
  const col = frac > 0.9 ? '#e2574d' : frac > 0.7 ? '#e0b04a' : '#9bd36a';
  return `<svg viewBox="0 0 120 150"><rect x="30" y="25" width="60" height="100" rx="30" fill="#0b0e13" stroke="#8a93a6"/><rect x="34" y="${121 - h}" width="52" height="${h}" rx="20" fill="${col}" opacity=".85"/><circle cx="60" cy="30" r="6" fill="${ok ? '#5ec07a' : '#e2574d'}"/><text x="60" y="145" fill="#8a93a6" font-size="10" text-anchor="middle">${ok ? 'aeration on' : 'aeration broken'}</text></svg>`;
}
function render(d) {
  document.getElementById('title').textContent = `House ${d.id}, sector ${d.sector}, ${d.type}, ${d.residents} residents`;
  document.getElementById('sub').textContent = d.time + (d.shedding ? ' (grid shedding L' + d.shedding + ')' : '');
  document.getElementById('navtime').textContent = d.time;
  document.getElementById('gauges').innerHTML = [['indoor', thermo(d.t_in, d.target), d.t_in + ' C', 'outside ' + d.t_out + ' C, target ' + d.target], ['power', bolt(d.power_ok, d.on_ups, d.limit_w, d.ups_kwh / d.ups_cap), d.power_ok ? (d.on_ups ? 'sector UPS' : 'grid') + ' ' + d.draw_w + ' W' : 'no power', d.on_ups ? 'UPS ' + d.ups_kwh + ' / ' + d.ups_cap + ' kWh' : d.limit_w ? 'limited by the grid' : 'heater ' + (d.heater_on ? 'on' : 'off')], ['water', tank(d.tank_m3 / d.tank_cap, d.water_ok), d.water_ok ? 'flowing' : 'none', 'city tank ' + d.tank_m3 + ' m3' + (d.burst ? ', pipes burst' : !d.pipes_ok ? ', pipes frozen' : '') + (d.valve_open ? '' : ', valve closed')], ['network', wifi(d.net_online, d.cabinet), d.net_online ? 'online' : 'offline', d.terminal_ok ? 'terminal ok' : 'terminal broken'], ['sewage', sludge(d.sludge, d.aeration_ok), Math.round(d.sludge * 100) + '% sludge', d.sludge > 0.9 ? 'hauler requested' : 'ok']].map(([l, svg, v, s]) => `<div class="card gauge">${svg}<div class="v">${v}</div><div class="l">${l}: ${s}</div></div>`).join('');
  // pie of the draw
  const c = document.getElementById('pie').getContext('2d');
  c.clearRect(0, 0, 180, 180);
  const parts = [['heater', d.split.heater, '#ff7a30'], ['appliances', d.split.appliances, '#f2c14e'], ['aeration', d.split.aeration, '#9bd36a'], ['fridge', d.split.fridge, '#5aa9ff']];
  const tot = parts.reduce((a, p) => a + p[1], 0) || 1;
  let a0 = -Math.PI / 2;
  for (const [n, v, col] of parts) {
    const a1 = a0 + 2 * Math.PI * v / tot;
    c.beginPath();
    c.moveTo(90, 90);
    c.arc(90, 90, 80, a0, a1);
    c.closePath();
    c.fillStyle = col;
    c.fill();
    a0 = a1;
  }
  c.beginPath();
  c.arc(90, 90, 48, 0, 7);
  c.fillStyle = '#1a1f2a';
  c.fill();
  c.fillStyle = '#d9dde6';
  c.font = '600 15px sans-serif';
  c.textAlign = 'center';
  c.fillText(d.draw_w + ' W', 90, 95);
  document.getElementById('pielegend').innerHTML = parts.map(([n, v, col]) => `<div><span style="display:inline-block;width:10px;height:10px;background:${col};border-radius:2px;margin-right:6px"></span>${n} <b>${v} W</b> <span class="dim">${Math.round(v / tot * 100)}%</span></div>`).join('') + `<div class="dim" style="margin-top:6px">this month ${d.kwh_month} kWh, bill so far ${d.bill_month} cr</div>`;
  spark('spark', d.hist_t, '#5ec07a', -50, 30, d.target);
  spark('spark2', d.hist_w, '#f2c14e', 0, Math.max(1000, Math.max(...d.hist_w)), null);
  document.getElementById('facts').innerHTML = [['program', d.program], ['pole', d.pole + (d.pole_online ? ' (energised)' : ' (dead)')], ['water this month', d.water_month_m3 + ' m3'], ['energy total', d.kwh_total + ' kWh'], ['appliances', d.appliances_on ? 'on' : 'switched off by the program'], ['open issues', d.issues.length ? d.issues.map(i => i.kind + ' (' + i.status + ', ' + i.cost + ' cr)').join(', ') : 'none']].map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
  document.getElementById('ctrl').innerHTML = `<div><b>${d.program}</b>${d.ctrl_age >= 0 ? ` <span class="dim">decided ${d.ctrl_age} min ago</span>` : ''}</div><div>${d.reason}</div><div class="dim">target ${d.target} C, heater ${d.heater_on ? 'on' : 'off'} (${d.heater_w} W rated, ${d.heat_w} W delivered)</div>`;
  document.getElementById('log').innerHTML = [...d.log.map(e => `<div><span class="dim">${e.t}</span> ${e.text}</div>`), ...d.events.map(e => `<div><span class="dim">${e.t}</span> <span class="warn">${e.text}</span></div>`)].join('') || '<div class="dim">nothing yet</div>';
}
function spark(id, arr, col, lo, hi, ref) {
  const cv = document.getElementById(id),
    c = cv.getContext('2d');
  const W = cv.width,
    H = cv.height;
  c.clearRect(0, 0, W, H);
  c.strokeStyle = '#2a2f3a';
  c.beginPath();
  for (let k = 0; k <= 4; k++) {
    const y = H - 1 - (H - 2) * k / 4;
    c.moveTo(0, y);
    c.lineTo(W, y);
  }
  c.stroke();
  if (ref !== null) {
    const y = H - 1 - (H - 2) * (ref - lo) / (hi - lo);
    c.strokeStyle = '#5aa9ff';
    c.setLineDash([4, 4]);
    c.beginPath();
    c.moveTo(0, y);
    c.lineTo(W, y);
    c.stroke();
    c.setLineDash([]);
  }
  c.strokeStyle = col;
  c.lineWidth = 2;
  c.beginPath();
  arr.forEach((v, i) => {
    const x = i / (arr.length - 1) * W,
      y = H - 1 - (H - 2) * Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    i ? c.lineTo(x, y) : c.moveTo(x, y);
  });
  c.stroke();
  c.fillStyle = '#8a93a6';
  c.font = '10px sans-serif';
  c.fillText(lo, 2, H - 3);
  c.fillText(hi, 2, 10);
}
poll();
