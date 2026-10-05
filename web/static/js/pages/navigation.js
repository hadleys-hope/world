/* Shared top bar: the active page, the theme, and (outside the 3D view, which wires its own) the clock,
   pause and speed controls. Handlers are assigned as properties, so a page script may replace them. */
(function () {
  const root = document.documentElement;
  const saved = localStorage.getItem('hh_theme');
  if (saved) root.dataset.theme = saved;

  function setup() {
    const path = location.pathname.replace(/\/$/, '') || '/';
    document.querySelectorAll('.hh-nav a').forEach((a) => {
      if (a.dataset.page === path) a.setAttribute('aria-current', 'page');
    });
    const toggle = document.getElementById('theme-toggle');
    if (toggle) {
      toggle.onclick = () => {
        const next = root.dataset.theme === 'light' ? 'dark' : 'light';
        root.dataset.theme = next;
        localStorage.setItem('hh_theme', next);
        toggle.blur();
      };
    }
    if (document.body.dataset.page === '3d') return;

    const token = () => localStorage.getItem('hh_admin') || '';
    const post = (o) => fetch('/cmd', { method: 'POST', body: JSON.stringify({ ...o, token: token() }) })
      .then((r) => { if (r.status === 403) document.getElementById('pause').title = 'View only: open /?admin=TOKEN once'; });
    const speedEl = document.getElementById('speed');
    const speedV = document.getElementById('speedv');
    const toSpeed = (v) => (v === 0 ? 0 : Math.round(Math.exp((Math.log(600) * v) / 100)));
    const toSlider = (s) => (s <= 0 ? 0 : Math.round((Math.log(Math.max(1, s)) / Math.log(600)) * 100));
    document.getElementById('pause').onclick = () => post({ cmd: 'pause' });
    speedEl.oninput = () => { speedV.textContent = toSpeed(+speedEl.value) + ' min/s'; };
    speedEl.onchange = () => post({ cmd: 'speed', value: toSpeed(+speedEl.value) });
    let dragging = false;
    speedEl.addEventListener('pointerdown', () => { dragging = true; });
    speedEl.addEventListener('pointerup', () => { dragging = false; });
    async function tick() {
      try {
        const c = await (await fetch('/clock.json')).json();
        document.getElementById('time').textContent = c.time;
        document.getElementById('pause').textContent = c.paused ? 'Resume' : 'Pause';
        if (!dragging) { speedEl.value = toSlider(c.speed); speedV.textContent = c.speed + ' min/s'; }
      } catch (e) { /* the page keeps working without the clock */ }
      setTimeout(tick, 1000);
    }
    tick();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup);
  else setup();
})();
