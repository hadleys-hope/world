let sortCol = 0,
  sortDir = 1,
  D = null;
const COLS = 16;
const pal = ['#f2c14e', '#5ec07a', '#5aa9ff', '#b48ead', '#e2574d', '#4fd1c5', '#9aa3b5'];
document.querySelectorAll('#ht th').forEach((th, i) => th.onclick = () => {
  if (sortCol === i) sortDir = -sortDir;else {
    sortCol = i;
    sortDir = 1;
  }
  render();
});
['fsec', 'fprog', 'fid'].forEach(id => document.getElementById(id).oninput = render);
async function poll() {
  try {
    D = await (await fetch('/bus.json')).json();
    render();
  } catch (e) {
    document.getElementById('time').textContent = 'update failed';
  }
  setTimeout(poll, 1000);
}
function render() {
  if (!D) return;
  document.getElementById('time').textContent = D.time + (D.env.storm ? ' STORM' : '') + (D.env.shedding ? ' shedding L' + D.env.shedding : '');
  const m = D.mqtt;
  const names = [...new Set(D.houses.map(h => h[2]))].sort();
  const col = n => pal[names.indexOf(n) % pal.length];
  document.getElementById('kpi').innerHTML = [['bus', m.enabled ? m.connected ? '<span class="ok">connected</span> ' + m.broker : '<span class="bad">disconnected</span>' : '<span class="warn">off</span>'], ['houses under programs', m.enabled ? m.controlled + ' / 300' : '0 / 300'], ['sensor messages', m.enabled ? m.sent.toLocaleString() + ' (' + m.out_per_s.toFixed(0) + '/s)' : '0'], ['actuator messages', m.enabled ? m.received.toLocaleString() + ' (' + m.in_per_s.toFixed(0) + '/s)' : '0'], ['outdoor', D.env.t_out + ' C']].map(([l, v]) => `<div class="card"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
  document.querySelector('#progs tbody').innerHTML = D.programs.map(p => `<tr><td class="l"><span class="prog" style="background:${col(p.program)}"></span>${p.program}</td><td>${p.houses}</td><td class="${p.avg_t > 19 ? 'ok' : p.avg_t > 15 ? 'warn' : 'bad'}">${p.avg_t}</td><td>${p.kwh_per_house_day}</td><td>${p.cost_per_house_day}</td><td class="${p.cold_share < 1 ? 'ok' : 'warn'}">${p.cold_share} %</td></tr>`).join('');
  const sel = document.getElementById('fprog');
  const cur = sel.value;
  if (sel.options.length !== names.length + 1) {
    sel.innerHTML = '<option value="">all</option>' + names.map(n => `<option>${n}</option>`).join('');
    sel.value = cur;
  }
  const fs = document.getElementById('fsec').value,
    fp = sel.value,
    fi = document.getElementById('fid').value.trim();
  let rows = D.houses.filter(h => (!fs || String(h[1]) === fs) && (!fp || h[2] === fp) && (!fi || String(h[0]) === fi));
  rows.sort((a, b) => {
    const x = a[sortCol],
      y = b[sortCol];
    return (typeof x === 'number' ? x - y : String(x).localeCompare(String(y))) * sortDir;
  });
  document.getElementById('count').textContent = rows.length + ' houses';
  const flag = (v, good = 'ok', bad = 'bad') => v ? `<span class="${good}">yes</span>` : `<span class="${bad}">no</span>`;
  document.querySelector('#ht tbody').innerHTML = rows.slice(0, 400).map(h => `<tr><td><a href="/house?id=${h[0]}" target="_blank">${h[0]}</a></td><td>${h[1]}</td><td class="l"><span class="prog" style="background:${col(h[2])}"></span>${h[2]}</td><td class="l dim">${h[3]}</td><td>${h[4]}</td><td class="${h[5] > 19 ? 'ok' : h[5] > 15 ? 'warn' : 'bad'}">${h[5]}</td><td>${h[6] ? '<span class="warn">on</span>' : 'off'}</td><td>${h[7]}</td><td>${h[8] ? h[9] ? '<span class="warn">ups</span>' : '<span class="ok">grid</span>' : '<span class="bad">none</span>'}</td><td>${h[10] || ''}</td><td>${flag(h[11])}</td><td>${flag(h[12], 'ok', 'warn')}</td><td>${h[15] ? 'on' : '<span class="warn">off</span>'}</td><td>${h[16] ? 'open' : '<span class="warn">closed</span>'}</td><td class="dim">${h[13] < 0 ? '' : h[13] + ' min'}</td><td class="dim">${h[14] < 0 ? '' : h[14] + ' min'}</td></tr>`).join('');
  document.getElementById('tail').innerHTML = D.tail.slice().reverse().map(x => `<div class="${x.dir}">${x.dir === 'out' ? '&rarr;' : '&larr;'} ${x.topic} <span class="dim">${x.body}</span></div>`).join('') || '<div class="dim">bus off or nothing yet</div>';
}
poll();
