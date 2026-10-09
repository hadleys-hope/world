/* The bus, live: who publishes which topic and who listens. Publishers on the left, the broker's topics in
   the middle, subscribers on the right. Dots run along the lanes at the topic's real message rate (log-scaled
   so a quiet topic still shows); the messages sampled in the bus tail run as bright labelled packets.
   Data: /bus.json (rates, tail) and /clock.json (simulation speed, which sets the per-tick topics' rate). */
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const $ = (id) => document.getElementById(id);
  const PARTIES = {
    world: { name: 'World', sub: 'the simulation', tone: '#7fd1b9' },
    programs: { name: 'House programs', sub: 'one per house', tone: '#e8b86b' },
    watchers: { name: 'Watchers', sub: 'monitoring, mosquitto_sub, this page', tone: '#9fb6c9' },
  };
  // pattern: how the topic appears in the tail; from/to: who publishes and who subscribes
  const TOPICS = [
    { id: 'sensors', name: 'hh/house/{id}/sensors', re: /^hh\/house\/\d+\/sensors$/, from: 'world', to: ['programs', 'watchers'], retained: true,
      what: 'one house reports what it measures, on change or every 10 minutes',
      fields: ['t', 'id', 'sector', 't_in', 'power_ok', 'on_ups', 'limit_w', 'water_ok', 'pipes_ok', 'burst', 'net_online', 'sludge', 'draw_w', 'heater_on', 'residents', 'pressure_kpa', 'water_l_min', 'leak_l_min'] },
    { id: 'actuators', name: 'hh/house/{id}/actuators', re: /^hh\/house\/\d+\/actuators$/, from: 'programs', to: ['world', 'watchers'],
      what: 'the house\'s program tells the world what to do',
      fields: ['t', 'target_c', 'heater_on', 'valve_open', 'appliances_on', 'program', 'reason'] },
    { id: 'bsensors', name: 'hh/batch/sensors', re: /^hh\/batch\/sensors$/, from: 'world', to: ['programs', 'watchers'], batch: true,
      what: 'every house due this tick in one message, as columns (--mqtt-batch)', fields: ['t', 'id[]', 't_in[]', 'power_ok[]', '…'] },
    { id: 'bactuators', name: 'hh/batch/actuators', re: /^hh\/batch\/actuators$/, from: 'programs', to: ['world', 'watchers'], batch: true,
      what: 'answers for many houses in one message, as rows', fields: ['rows[{id, target_c, heater_on, …}]'] },
    { id: 'weather', name: 'hh/env/weather', re: /^hh\/env\/weather$/, from: 'world', to: ['programs', 'watchers'], perTick: true,
      what: 'the weather every house sees', fields: ['t', 't_out', 'wind', 'storm', 'precip', 'hour', 'night', 'daylight'] },
    { id: 'power', name: 'hh/env/power', re: /^hh\/env\/power$/, from: 'world', to: ['programs', 'watchers'], perTick: true,
      what: 'the state of the grid', fields: ['t', 'available_kw', 'demand_kw', 'shedding', 'reactor_mode', 'tariff_kwh'] },
    { id: 'tick', name: 'hh/tick', re: /^hh\/tick$/, from: 'world', to: ['watchers'], perTick: true, what: 'the simulation clock', fields: ['t', 'time'] },
  ];
  let D = null, clock = { speed: 0, paused: true }, focus = 'sensors', lanes = [], packets = [], W = 0, H = 0, layoutKey = '';
  const seenTopics = new Set();      // a batch topic, once seen, stays on the picture (no rebuild when the tail rolls)
  let seenMsgs = new Set();          // tail entries already sent as packets
  const MAX_PACKETS = 160, MAX_LABELS = 24;

  function rate(t) {
    if (!D || !D.mqtt.enabled || clock.paused) return 0;
    const m = D.mqtt;
    if (t.perTick) return clock.speed;                       // one message per tick, a tick is one simulated minute
    const seen = D.tail.some((x) => t.re.test(x.topic));
    if (t.batch) return seen ? (clock.speed || 0) : 0;
    if (t.id === 'sensors') return D.tail.some((x) => /^hh\/batch/.test(x.topic)) ? 0 : m.out_per_s;
    if (t.id === 'actuators') return D.tail.some((x) => /^hh\/batch/.test(x.topic)) ? 0 : m.in_per_s;
    return 0;
  }
  const visible = () => {
    for (const x of D?.tail || []) for (const t of TOPICS) if (t.batch && t.re.test(x.topic)) seenTopics.add(t.id);
    return TOPICS.filter((t) => !t.batch || seenTopics.has(t.id));
  };

  function layout() {
    if (!W || !H) return;                       // size comes from the ResizeObserver, never read in the loop
    const topics = visible();
    const key = topics.map((t) => t.id).join() + W + 'x' + H;
    if (key === layoutKey) return;
    layoutKey = key;
    const svg = $('live-svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.innerHTML = '';
    const nodes = $('live-nodes');
    nodes.innerHTML = '';
    const left = { world: 0.3, programs: 0.72 }, right = { programs: 0.22, world: 0.52, watchers: 0.82 };
    const at = (side, id) => [side === 'L' ? 0.11 * W : 0.89 * W, (side === 'L' ? left : right)[id] * H];
    for (const [side, ids] of [['L', Object.keys(left)], ['R', Object.keys(right)]])
      for (const id of ids) {
        const p = PARTIES[id], [x, y] = at(side, id);
        const card = document.createElement('div');
        card.className = 'party';
        card.style.left = x + 'px'; card.style.top = y + 'px'; card.style.borderColor = p.tone;
        card.innerHTML = `<b>${p.name}</b><span>${side === 'L' ? 'publishes' : 'subscribes'} · ${p.sub}</span>`;
        nodes.append(card);
      }
    const colX = 0.5 * W, top = 0.1 * H, step = (0.8 * H) / Math.max(1, topics.length - 1);
    lanes = [];
    topics.forEach((t, k) => {
      const ty = topics.length === 1 ? H / 2 : top + k * step;
      const pill = document.createElement('button');
      pill.className = 'topic';
      pill.style.left = colX + 'px'; pill.style.top = ty + 'px';
      pill.setAttribute('aria-pressed', String(focus === t.id));
      pill.innerHTML = `<code>${t.name}</code><span class="rate" data-rate="${t.id}"></span>`;
      pill.onclick = () => { focus = t.id; layoutKey = ''; layout(); details(); tail(); };
      nodes.append(pill);
      const tone = PARTIES[t.from].tone;
      const segs = [[at('L', t.from), [colX - 130, ty]], ...t.to.map((to) => [[colX + 130, ty], at('R', to)])];
      segs.forEach(([a, b], j) => {
        const path = document.createElementNS(NS, 'path');
        const mx = (a[0] + b[0]) / 2;
        path.setAttribute('d', `M ${a[0]} ${a[1]} C ${mx} ${a[1]}, ${mx} ${b[1]}, ${b[0]} ${b[1]}`);
        path.setAttribute('class', 'lane');
        path.setAttribute('stroke', tone);
        path.style.opacity = focus === t.id ? 0.55 : 0.14;
        svg.append(path);
        // sample the curve once; packets then move along the samples with no SVG queries per frame
        const len = path.getTotalLength(), pts = new Float32Array(2 * 65);
        for (let k = 0; k <= 64; k++) { const q = path.getPointAtLength((len * k) / 64); pts[2 * k] = q.x; pts[2 * k + 1] = q.y; }
        lanes.push({ topic: t, part: j, path, len, pts, tone, acc: Math.random() });
      });
    });
  }

  function spawn(lane, bright, label) {
    if (packets.length >= MAX_PACKETS) return;          // a busy bus shows as a full lane, not as a frozen page
    if (label && packets.filter((p) => p.tag).length >= MAX_LABELS) label = null;
    const c = document.createElementNS(NS, 'circle');
    c.setAttribute('r', bright ? 4.5 : 2.4);
    c.setAttribute('fill', bright ? '#fff' : lane.tone);
    c.style.color = lane.tone;
    c.setAttribute('class', bright ? 'pkt bright' : 'pkt');
    $('live-svg').append(c);
    let tag = null;
    if (label) {
      tag = document.createElementNS(NS, 'text');
      tag.setAttribute('class', 'pkt-label');
      tag.textContent = label;
      $('live-svg').append(tag);
    }
    packets.push({ lane, t: 0, c, tag, speed: bright ? 0.32 : 0.45 + Math.random() * 0.1 });
  }

  let last = performance.now();
  function animate(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    for (const l of lanes) {
      const r = rate(l.topic);
      const visual = r > 0 ? 1.2 + 2.6 * Math.log10(1 + r) : 0;     // dots per second on screen
      l.acc += visual * dt;
      if (l.part === 0) while (l.acc >= 1) { l.acc -= 1; spawn(l, false); }
    }
    packets = packets.filter((p) => {
      p.t += (p.speed * dt * 300) / Math.max(120, p.lane.len);
      if (p.t >= 1) {
        // a message reaching the broker goes on to every subscriber of its topic
        if (p.lane.part === 0) for (const next of lanes.filter((x) => x.topic === p.lane.topic && x.part > 0)) spawn(next, p.c.classList.contains('bright'), p.tag?.textContent);
        p.c.remove(); p.tag?.remove();
        return false;
      }
      const f = p.t * 64, k = Math.min(63, Math.floor(f)), u = f - k, a = p.lane.pts;
      const pt = { x: a[2 * k] + (a[2 * k + 2] - a[2 * k]) * u, y: a[2 * k + 1] + (a[2 * k + 3] - a[2 * k + 1]) * u };
      p.c.setAttribute('cx', pt.x); p.c.setAttribute('cy', pt.y);
      p.c.style.opacity = p.lane.topic.id === focus || p.c.classList.contains('bright') ? 1 : 0.35;
      if (p.tag) { p.tag.setAttribute('x', pt.x + 7); p.tag.setAttribute('y', pt.y - 7); }
      return true;
    });
    requestAnimationFrame(animate);
  }

  function pretty(body) {
    try { return JSON.stringify(JSON.parse(body), null, 1); } catch (e) { return body + (body.length >= 160 ? ' …' : ''); }
  }
  function details() {
    const t = TOPICS.find((x) => x.id === focus);
    if (!t) return;
    const r = rate(t), lastMsg = D?.tail.slice().reverse().find((x) => t.re.test(x.topic));
    $('topic-card').innerHTML = `
      <div class="live-head"><h2><code class="tname">${t.name}</code></h2><span class="big">${r ? (r < 10 ? r.toFixed(1) : Math.round(r)) + ' msg/s' : 'quiet'}</span></div>
      <p class="what">${t.what}.</p>
      <div class="route"><span class="who" style="border-color:${PARTIES[t.from].tone}">${PARTIES[t.from].name}</span><span class="arrow">→ broker →</span>${t.to.map((x) => `<span class="who" style="border-color:${PARTIES[x].tone}">${PARTIES[x].name}</span>`).join('')}</div>
      <div class="facts"><span>QoS 0</span><span>${t.retained ? 'retained: a new subscriber gets the last value at once' : 'not retained'}</span></div>
      <h3>Fields</h3><div class="fields">${t.fields.map((f) => `<code>${f}</code>`).join('')}</div>
      <h3>Last message</h3><pre class="msg">${lastMsg ? `${lastMsg.topic}\n${pretty(lastMsg.body)}` : 'none in the tail yet'}</pre>`;
  }
  function tail() {
    const t = TOPICS.find((x) => x.id === focus);
    const rows = (D?.tail || []).slice().reverse().filter((x) => !t || t.re.test(x.topic));
    $('tail-filter').textContent = t ? '· ' + t.name : '';
    $('tail-all').hidden = !t;
    $('tail').innerHTML = rows.slice(0, 60).map((x) => `<div class="${x.dir}"><span class="arr">${x.dir === 'out' ? '→' : '←'}</span><code>${x.topic}</code> <span class="dim">${x.body}</span></div>`).join('') || '<div class="dim">nothing on this topic yet</div>';
  }
  $('tail-all').onclick = () => { focus = ''; layoutKey = ''; layout(); tail(); $('topic-card').innerHTML = '<div class="dim">Click a topic in the picture above.</div>'; };

  let clockAt = 0;
  async function onData(d) {
    try {
      if (performance.now() - clockAt > 3000) { clock = await (await fetch('/clock.json')).json(); clockAt = performance.now(); }
      D = d;
      layout();
      const now = new Set(), fresh = [];
      for (const x of d.tail) {
        const key = (x.at ?? '') + x.topic + x.body;
        now.add(key);
        if (!seenMsgs.has(key)) fresh.push(x);
      }
      const firstPoll = seenMsgs.size === 0;
      seenMsgs = now;
      for (const x of firstPoll ? [] : fresh.slice(-12)) {
        const t = TOPICS.find((y) => y.re.test(x.topic));
        const lane = lanes.find((l) => l.topic === t && l.part === 0);
        const id = (x.topic.match(/house\/(\d+)/) || [])[1];
        if (lane) spawn(lane, true, id ? '#' + id : x.topic.split('/').pop());
      }
      document.querySelectorAll('[data-rate]').forEach((el) => {
        const r = rate(TOPICS.find((t) => t.id === el.dataset.rate));
        el.textContent = r ? (r < 10 ? r.toFixed(1) : Math.round(r)) + '/s' : '–';
      });
      details(); tail();
    } catch (e) { /* the picture keeps moving with what it has */ }
  }
  window.addEventListener('bus-data', (e) => onData(e.detail));   // controllers.js downloads /bus.json once a second
  new ResizeObserver(([e]) => { W = e.contentRect.width; H = e.contentRect.height; layoutKey = ''; layout(); }).observe($('live-stage'));
  requestAnimationFrame(animate);
})();
