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
    window.dispatchEvent(new CustomEvent('bus-data', { detail: D }));   // the live picture uses the same download
    render();
  } catch (e) {
    document.getElementById('time').textContent = 'update failed';
  }
  setTimeout(poll, 1000);
}
function render() {
  if (!D) return;
  document.getElementById('time').textContent = D.time;   // the shared bar shows only the date; storms and load shedding are cards below
  const m = D.mqtt;
  const names = [...new Set(D.houses.map(h => h[2]))].sort();
  const col = n => pal[names.indexOf(n) % pal.length];
  document.getElementById('kpi').innerHTML = [['bus', m.enabled ? m.connected ? '<span class="ok">connected</span> ' + m.broker : '<span class="bad">disconnected</span>' : '<span class="warn">off</span>'], ['houses under programs', (m.enabled ? m.controlled : 0) + ' / ' + D.houses.length], ['grid', D.env.shedding ? `<span class="warn">shedding level ${D.env.shedding}</span>` : '<span class="ok">no shedding</span>'], ['sensor messages', m.enabled ? m.sent.toLocaleString() + ' (' + m.out_per_s.toFixed(0) + '/s)' : '0'], ['actuator messages', m.enabled ? m.received.toLocaleString() + ' (' + m.in_per_s.toFixed(0) + '/s)' : '0'], ['outdoor', D.env.t_out + ' C']].map(([l, v]) => `<div class="card"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
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
  // Only the rows in view are built (a 1500-house city made the old 400-row rebuild take 0.3-0.5 s every
  // second); spacer rows keep the scrollbar honest. Scrolling redraws the window, polling redraws it too.
  window.__busRows = rows;
  window.__busRow = h => `<tr><td><a href="/house?id=${h[0]}" target="_blank">${h[0]}</a></td><td>${h[1]}</td><td class="l"><span class="prog" style="background:${col(h[2])}"></span>${h[2]}</td><td class="l dim">${h[3]}</td><td>${h[4]}</td><td class="${h[5] > 19 ? 'ok' : h[5] > 15 ? 'warn' : 'bad'}">${h[5]}</td><td>${h[6] ? '<span class="warn">on</span>' : 'off'}</td><td>${h[7]}</td><td>${h[8] ? h[9] ? '<span class="warn">ups</span>' : '<span class="ok">grid</span>' : '<span class="bad">none</span>'}</td><td>${h[10] || ''}</td><td>${flag(h[11])}</td><td>${flag(h[12], 'ok', 'warn')}</td><td>${h[15] ? 'on' : '<span class="warn">off</span>'}</td><td>${h[16] ? 'open' : '<span class="warn">closed</span>'}</td><td class="dim">${h[13] < 0 ? '' : h[13] + ' min'}</td><td class="dim">${h[14] < 0 ? '' : h[14] + ' min'}</td></tr>`;
  drawRows();
  // the tail is drawn by bus-live.js, filtered by the selected topic
}
const ROW_H = 21;
function drawRows() {
  const rows = window.__busRows || [], box = document.getElementById('houses'), body = document.querySelector('#ht tbody');
  if (!box || !body) return;
  const first = Math.max(0, Math.floor(box.scrollTop / ROW_H) - 10), last = Math.min(rows.length, first + Math.ceil(box.clientHeight / ROW_H) + 20);
  const cols = document.querySelectorAll('#ht thead th').length || 16;
  const pad = (n) => n > 0 ? `<tr aria-hidden="true" style="height:${n * ROW_H}px"><td colspan="${cols}"></td></tr>` : '';
  body.innerHTML = pad(first) + rows.slice(first, last).map(window.__busRow).join('') + pad(rows.length - last);
}
document.getElementById('houses').addEventListener('scroll', () => requestAnimationFrame(drawRows), { passive: true });
poll();
