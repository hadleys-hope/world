/** ui/telemetry: procedural colony viewer. */
import { state } from '../state.js';
import { polar } from '../geometry/planet.js';
import { sectorCards } from './controls.js';
import { flyTo } from './inspection.js';
export function cls(ok, warn) {
  return ok ? 'ok' : warn ? 'warn' : 'bad';
}
export function renderSide(s) {
  if (state.G) sectorCards(s);
  document.getElementById('time').textContent = s.time;
  document.getElementById('pause').textContent = s.paused ? 'Resume' : 'Pause';
  if (document.activeElement !== state.speedEl) {
    state.speedEl.value = state.speedToSlider(s.speed);
    state.speedV.textContent = s.speed + ' min/s';
  }
  const p = s.power,
    r = s.reactor,
    w = s.water,
    f = s.finance;
  const kp = [['Colony budget', f.colony.toLocaleString() + ' cr', f.colony > 20000 ? 'ok' : f.colony > 0 ? 'warn' : 'bad'], ['Sector budgets', f.sectors.map(x => Math.round(x / 1000) + 'k').join(' '), Math.min(...f.sectors) > 2000 ? 'ok' : 'warn'], ['Power available', p.available_kw + ' kW', p.available_kw > p.demand_kw ? 'ok' : 'bad'], ['Power demand', p.demand_kw + ' kW' + (p.shedding ? ` / shedding L${p.shedding}` : ''), p.shedding ? 'warn' : 'ok'], ['Water tank', w.tank_m3 + ' m3, ' + w.houses_ok + '/300 houses', w.tank_m3 > 100 && w.houses_ok > 280 ? 'ok' : 'warn'], ['Pipes', `${w.frozen} frozen, ${w.burst} burst`, w.burst === 0 ? 'ok' : 'bad'], ['Internet', `${s.net.houses_online}/300 online, uplink ${s.net.uplink ? 'OK' : 'LOST'}`, s.net.uplink && s.net.houses_online > 280 ? 'ok' : 'warn'], ['Open issues', s.issues_total + (f.unpaid ? ` (unpaid ${f.unpaid} cr)` : ''), s.issues_total < 5 ? 'ok' : 'warn'], ['Month income (colony)', f.month_income.toLocaleString() + ' cr', 'dim'], ['Month expense (colony)', f.month_expense.toLocaleString() + ' cr', 'dim']];
  document.getElementById('kpi').innerHTML = kp.map(([l, v, c]) => `<div class="card"><div class="v ${c}">${v}</div><div class="l">${l}</div></div>`).join('');
  const inf = p.infra;
  document.getElementById('reactor').innerHTML = `<div><b class="${r.mode === 'ONLINE' ? 'ok' : r.mode === 'RUNBACK' || r.mode === 'STARTING' ? 'warn' : 'bad'}">${r.mode}</b> &nbsp; ${r.power_mw} MW el (setpoint ${r.setpoint_mw}), ${r.thermal_mw} MW th, ${r.available_mw} MW to grid, core ${r.core_temp} C, coolant ${r.coolant_temp} C${r.decay_mw ? `, decay ${r.decay_mw} MW` : ''}${r.marines ? ' <span class="bad">marines in the sublevels</span>' : ''}</div>
    <div class="dim">pumps A ${r.pump_a} B ${r.pump_b}, flow ${Math.round(r.flow * 100)} %, heat exchanger ${r.hx}, batteries ${r.battery_h} h, link ${r.link ? 'ok' : '<span class="bad">lost</span>'}${r.faults.length ? ', faults: ' + r.faults.join(', ') : ''}</div>
    <div class="dim">solar ${p.solar_kw} kW (${Math.round(s.env.daylight * 100 / 0.3)} % of a clear day); loads: mine ${inf.mine}, houses ${Math.round(p.demand_kw - Object.values(inf).reduce((a, b) => a + b, 0))}, water plant ${inf.water_plant}, radioactive waste storage ${inf.waste_storage}, road heating ${inf.road_heating}, lamps ${inf.lamps}, comms ${inf.comms}, ups charge ${inf.ups_charge} kW</div>
    <div class="dim">trunk ${p.trunk ? 'ok' : '<span class="bad">CUT</span>'}, substation ${p.substation ? 'ok' : '<span class="bad">DOWN</span>'}, UPS center ${p.ups_center} ${p.ups_center_kwh} kWh, water plant ${w.plant_m3_h} m3/h, city draws ${w.flow_m3_h} m3/h</div>`;
  document.querySelector('#sectors tbody').innerHTML = s.sectors.map((x, i) => `<tr class="sec" data-s="${i}"><td>${x.id}${x.dark ? ' <span class="warn">dark</span>' : ''}</td><td>${x.budget}</td><td>${x.demand_kw}</td><td class="${x.avg_t > 15 ? 'ok' : x.avg_t > 4 ? 'warn' : 'bad'}">${x.avg_t}</td><td class="${x.min_t > 4 ? 'ok' : 'bad'}">${x.min_t}</td><td class="${cls(x.power_ok === 50, x.power_ok > 30)}">${x.power_ok}</td><td class="${cls(x.water_ok === 50, x.water_ok > 30)}">${x.water_ok}</td><td class="${cls(x.net_ok === 50, x.net_ok > 30)}">${x.net_ok}</td><td class="${x.ups === 'DISCHARGING' ? 'warn' : x.ups === 'DEPLETED' ? 'bad' : 'dim'}">${x.ups.slice(0, 4)} ${x.ups_kwh}</td><td class="${x.waste >= 1 ? 'bad' : x.waste >= 0.9 ? 'warn' : 'dim'}">${Math.round(x.waste * 100)}%</td><td class="${x.sanitary > 70 ? 'ok' : 'bad'}">${x.sanitary}</td><td class="${x.gate === 'OPEN' ? 'ok' : x.gate === 'LOCKDOWN' ? 'bad' : 'warn'}">${x.gate.slice(0, 4)}</td><td class="${x.road > 20 ? 'dim' : 'bad'}">${x.road}%</td></tr>`).join('');
  document.querySelectorAll('#sectors tr.sec').forEach(tr => tr.onclick = () => {
    const [x, y] = polar(+tr.dataset.s * 60 + 30, 450);
    flyTo(x, y, 520);
  });
  document.getElementById('nissues').textContent = `(${s.issues_total})`;
  document.getElementById('issues').innerHTML = s.issues.slice().reverse().map(i => `<div><span class="${i.sev === 'critical' ? 'bad' : i.sev === 'warning' ? 'warn' : 'dim'}">${i.kind}</span> ${i.target} ${i.sector > 0 ? 'S' + i.sector : ''} ${i.cause}, ${i.cost} cr (${i.payer}) <span class="dim">${i.status}, ${Math.round(i.age / 60)} h</span></div>`).join('') || '<div>none</div>';
  document.getElementById('log').innerHTML = s.events.map(e => `<div class="${e.level}">${String(e.t).padStart(6)} ${e.text}</div>`).join('');
  const mp = s.month_progress;
  if (mp && !s.report) {
    document.getElementById('report').textContent = `month ${s.finance.month} in progress, day ${mp.day} of ${mp.days} (the report closes on day ${mp.days})\nso far: ${mp.kwh} kWh, ${mp.water_m3} m3 water, repairs billed to owners ${mp.repairs} cr\nsector income ${mp.sector_income.join(' | ')}\nsector expense ${mp.sector_expense.join(' | ')}\ncolony income ${mp.colony_income}, expense ${mp.colony_expense}`;
  }
  const rp = s.report;
  if (rp) {
    document.getElementById('report').textContent = `Month ${rp.month}: owners paid ${Math.round(rp.houses_total)} cr (energy ${Math.round(rp.energy_total)}, water ${Math.round(rp.water_total)}, repairs ${Math.round(rp.repairs_total)}), ${Math.round(rp.kwh_total)} kWh\ncolony: income ${rp.colony_income}, expense ${rp.colony_expense}, budget ${rp.colony_budget}, unpaid ${rp.unpaid}\nsector income ${rp.sector_income.join(' | ')}\nsector expense ${rp.sector_expense.join(' | ')}\nexpense by cause: ${Object.entries(rp.by_cause).map(([k, v]) => k + ' ' + v).join(', ')}\ntop houses: ${rp.top_houses.map(h => `#${h.house} (S${h.sector}) ${h.total}`).join(', ')}`;
  }
}
