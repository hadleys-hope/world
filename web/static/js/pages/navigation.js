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
      // the native <select> pops up in the OS's colours (white on Linux); this menu is part of the bar
      const box = document.createElement('div');
      box.className = 'hh-cityp';
      box.innerHTML = '<button type="button" class="hh-citybtn" aria-haspopup="listbox" aria-expanded="false"><span class="pl"></span><b>…</b><span class="n"></span><span class="chev" aria-hidden="true">▾</span></button><div class="hh-citymenu" role="listbox" hidden></div>';
      select.replaceWith(box);
      const btn = box.querySelector('button'), menu = box.querySelector('[role=listbox]');
      const open = (on) => { menu.hidden = !on; btn.setAttribute('aria-expanded', String(on)); if (on) menu.querySelector('[aria-selected=true]')?.focus(); };
      btn.onclick = () => open(menu.hidden);
      document.addEventListener('click', (e) => { if (!box.contains(e.target)) open(false); });
      box.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { open(false); btn.focus(); }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          const items = [...menu.querySelectorAll('[role=option]')], i = items.indexOf(document.activeElement);
          items[(i + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length]?.focus();
          e.preventDefault();
        }
      });
      fetch('/cities.json').then((r) => r.json()).then((cities) => {
        const planets = [...new Set(cities.map((c) => c.planet))];
        menu.innerHTML = planets.map((p) => `<div class="grp"><span class="pl ${p.toLowerCase()}"></span>${p}<span class="n">${cities.filter((c) => c.planet === p).reduce((a, c) => a + c.houses, 0)} houses</span></div>` +
          cities.filter((c) => c.planet === p).map((c) => `<button type="button" role="option" data-id="${c.id}" aria-selected="${c.id === city}"><span>${c.name}</span><span class="n">${c.houses}</span></button>`).join('')).join('');
        menu.querySelectorAll('[role=option]').forEach((o) => (o.onclick = () => { localStorage.setItem('hh_city', o.dataset.id); location.reload(); }));
        const cur = cities.find((c) => c.id === city) || cities[0];
        window.HH_CITY_NAME = cur ? cur.name : '';
        btn.querySelector('b').textContent = cur.name;
        btn.querySelector('.n').textContent = cur.houses;
        btn.querySelector('.pl').className = 'pl ' + cur.planet.toLowerCase();
        const sub = document.getElementById('brand-sub');
        if (sub && cur) sub.textContent = cur.planet === 'Klyaksa' ? `KLYAKSA · ${cur.name.toUpperCase()}` : 'LV-426 · ACHERON';
      }).catch(() => { box.hidden = true; });
    }
    // the bar may wrap to two rows; everything placed under it reads its real height from --hh-bar-bottom
    const bar = document.getElementById('hh-bar');
    if (bar) new ResizeObserver(() => document.documentElement.style.setProperty('--hh-bar-bottom', bar.getBoundingClientRect().bottom + 'px')).observe(bar);
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
