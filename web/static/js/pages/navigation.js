/* Shared top bar: the active page, the theme, and (outside the 3D view, which wires its own) the clock,
   pause and speed controls. Handlers are assigned as properties, so a page script may replace them. */
(function () {
  const root = document.documentElement;
  const saved = localStorage.getItem('hh_theme');
  if (saved) root.dataset.theme = saved;

  // The city the 2D pages show: LV-426's Hadley's Hope (""), or one of Klyaksa's domes ("k1".."k6").
  // Every request to the simulation's endpoints carries it, so the pages need no changes of their own.
  const city = localStorage.getItem('hh_city') || '';
  const CITY_PATHS = /^\/(state|geometry|bus\.json|house\.json|finance\.json|attractors\.json|water\.json|clock\.json|cmd)/;
  const is3d = location.pathname === '/' || location.pathname.startsWith('/index');
  if (city && !is3d) {
    const plain = window.fetch.bind(window);
    window.fetch = (input, init) => {
      if (typeof input === 'string' && CITY_PATHS.test(input)) {
        if (input.startsWith('/cmd') && init && init.body) {
          try { init = { ...init, body: JSON.stringify({ ...JSON.parse(init.body), city }) }; } catch (e) { /* not JSON */ }
        } else input += (input.includes('?') ? '&' : '?') + 'city=' + encodeURIComponent(city);
      }
      return plain(input, init);
    };
  }

  function setup() {
    const path = location.pathname.replace(/\/$/, '') || '/';
    const select = document.getElementById('city-select');
    if (select) {
      fetch('/cities.json').then((r) => r.json()).then((cities) => {
        const planets = [...new Set(cities.map((c) => c.planet))];
        select.innerHTML = planets.map((p) => `<optgroup label="${p}">` + cities.filter((c) => c.planet === p)
          .map((c) => `<option value="${c.id}">${c.name} · ${c.houses}</option>`).join('') + '</optgroup>').join('');
        select.value = city;
        const cur = cities.find((c) => c.id === city) || cities[0];
        window.HH_CITY_NAME = cur ? cur.name : '';
        const sub = document.getElementById('brand-sub');
        if (sub && cur) sub.textContent = cur.planet === 'Klyaksa' ? `KLYAKSA · ${cur.name.toUpperCase()}` : 'LV-426 · ACHERON';
      }).catch(() => { select.hidden = true; });
      select.onchange = () => { localStorage.setItem('hh_city', select.value); location.reload(); };
    }
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
