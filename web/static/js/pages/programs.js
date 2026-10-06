/* Programs: what every house runs, three ways. The Hope source (editable here, highlighted), the bytecode the
   compiler made of it (from hope-runtime's own disassembler), and real runs recorded inside the VM: every
   instruction executed, every call out of the program with its arguments and result, and the message that
   went to the bus. Data: /programs.json, which the world fills from hope-runtime's hh/runtime/* topics. */
(function () {
  const $ = (id) => document.getElementById(id);
  let D = null, prog = null, trace = null, step = 0, playing = false, edited = {};
  const KEYWORDS = /\b(program|var|def|on|end|if|elif|else|while|for|in|return|event|emit|every|at|struct|and|or|not|of|true|false)\b/g;
  const TYPES = /\b(int|real|bool|string|time)\b/g;

  function highlight(src, hot) {
    const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    return src.split('\n').map((line, i) => {
      let html = esc(line);
      const cm = html.indexOf('//');
      let comment = '';
      if (cm >= 0) { comment = `<span class="c">${html.slice(cm)}</span>`; html = html.slice(0, cm); }
      html = html.replace(/"[^"]*"/g, (m) => `\u0001${m}\u0002`)
        .replace(KEYWORDS, '<span class="k">$1</span>').replace(TYPES, '<span class="t">$1</span>')
        .replace(/\b(sense|act|act_text|house_id|log|metric|clamp|random_real|random_int)\b(?=\()/g, '<span class="h">$1</span>')
        .replace(/\b(\d+(\.\d+)?)\b/g, '<span class="n">$1</span>')
        .replace(/\u0001([^\u0002]*)\u0002/g, '<span class="s">$1</span>');
      return `<span class="ln${hot && hot(i, line) ? ' hot' : ''}">${html}${comment || ''}\n</span>`;
    }).join('');
  }

  // source lines of the function a step is in: "def name" ... "end", or the handler "on Event"
  function linesOf(fnName) {
    const src = $('src').value.split('\n');
    const base = fnName.replace(/^__?(on_?)?/i, '').replace(/[$@#].*$/, '');
    let start = src.findIndex((l) => new RegExp(`^\\s*def\\s+${base}\\b`).test(l));
    if (start < 0) start = src.findIndex((l) => new RegExp(`^\\s*on\\s+${base}`, 'i').test(l) || (/on\s+Sensors/.test(l) && /sensors/i.test(fnName)));
    if (start < 0) return null;
    let end = start + 1, depth = 1;
    for (; end < src.length && depth > 0; end++) {
      if (/^\s*(if|while|for|def|on)\b/.test(src[end]) && !/^\s*on\s/.test(src[end]) || /^\s*(if|while|for)\b/.test(src[end])) depth++;
      if (/^\s*end\s*$/.test(src[end])) depth--;
    }
    return [start, end - 1];
  }

  function renderSource(hotFn) {
    const range = hotFn ? linesOf(hotFn) : null;
    $('src-hl').innerHTML = highlight($('src').value, range ? (i) => i >= range[0] && i <= range[1] : null);
  }

  function selectProgram(name) {
    prog = D.programs.find((p) => p.name === name) || D.programs[0];
    if (!prog) return;
    document.querySelectorAll('#plist button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.name === prog.name)));
    $('src-title').textContent = prog.name + '.hope';
    $('src').value = edited[prog.name] ?? prog.source ?? '';
    renderSource();
    $('bc-size').textContent = `${prog.bytes} bytes · ${prog.functions.length} functions`;
    $('bc').innerHTML = prog.functions.map((f, fi) => `<div class="fn">${f.name}(${f.params}) · ${f.locals} locals</div>` +
      f.code.map(([ip, op, arg]) => `<div class="ins" data-k="${fi}:${ip}"><span class="ip">${String(ip).padStart(4, '0')}</span><span class="op">${op}</span><span class="arg">${arg.replace(/</g, '&lt;')}</span></div>`).join('')).join('');
    const mine = D.traces.filter((t) => t.program === prog.name);
    if (mine.length && (!trace || trace.program !== prog.name)) showTrace(mine[mine.length - 1]);
  }

  function showTrace(t) {
    trace = t; step = 0; playing = false; $('run-play').textContent = 'Play';
    if (prog?.name !== t.program) { selectProgram(t.program); trace = t; }
    $('run-title').textContent = `House ${t.house} · ${t.program} · tick ${t.tick} · ${t.steps.length} instructions in ${t.us} µs`;
    $('run-scrub').max = Math.max(0, t.steps.length - 1);
    $('run-in').innerHTML = Object.entries(t.sensors).filter(([k]) => !['id', 'sector'].includes(k))
      .map(([k, v]) => `<div><span>${k}</span><span>${+v.toFixed(2)}</span></div>`).join('');
    $('run-calls').innerHTML = t.calls.map((c, i) => `<div data-i="${i}"><span><span class="fn">${c.name}</span>(${c.args.replace(/</g, '&lt;')})</span><span class="res">${c.result ? '→ ' + c.result : ''}</span></div>`).join('') || '<div class="done">no calls</div>';
    $('run-out').innerHTML = `<div class="topic">${t.topic}</div><pre>${JSON.stringify(t.actuators, null, 1)}</pre>`;
    document.querySelectorAll('#tlist button').forEach((b) => b.setAttribute('aria-pressed', String(+b.dataset.house === t.house && +b.dataset.tick === t.tick)));
    seek(0);
  }

  function seek(i) {
    if (!trace || !prog) return;
    step = Math.max(0, Math.min(trace.steps.length - 1, i));
    $('run-scrub').value = step;
    $('run-step').textContent = `${step + 1} / ${trace.steps.length}`;
    document.querySelectorAll('#bc .ins.now').forEach((e) => e.classList.remove('now'));
    const [fn, ip] = trace.steps[step] || [0, 0];
    const el = document.querySelector(`#bc .ins[data-k="${fn}:${ip}"]`);
    if (el) {
      el.classList.add('now', 'ran');
      const box = $('bc');
      if (el.offsetTop < box.scrollTop || el.offsetTop > box.scrollTop + box.clientHeight - 30) box.scrollTop = el.offsetTop - box.clientHeight / 2;
    }
    renderSource(prog.functions[fn]?.name);
    let last = -1;
    trace.calls.forEach((c, k) => { if (c.step <= step) last = k; });
    document.querySelectorAll('#run-calls div').forEach((d, k) => { d.classList.toggle('done', k <= last); d.classList.toggle('now', k === last); });
    $('run-out').querySelector('pre')?.classList.toggle('sent', step >= trace.steps.length - 1);
  }

  function tick() {
    if (playing && trace) {
      if (step >= trace.steps.length - 1) { playing = false; $('run-play').textContent = 'Replay'; }
      else seek(step + 1);
    }
    setTimeout(tick, trace && trace.steps.length > 400 ? 15 : 45);
  }

  function render() {
    const s = D.status;
    $('kpis').innerHTML = (s ? [
      [s.houses, 'VMs, one per house'], [D.programs.length, 'programs'], [Math.round(s.handled_per_s), 'handler runs / s'],
      [s.handler_us_p50 + ' µs', 'run time p50'], [s.handler_us_p99 + ' µs', 'run time p99'], [s.faults, 'faults'],
      [s.quarantined, 'quarantined'], [s.rss_mb + ' MB', 'runtime memory'],
    ] : [['—', 'hope-runtime not on the bus yet']]).map(([v, l]) => `<div class="card"><b>${v}</b><span>${l}</span></div>`).join('');
    if (!$('plist').children.length || $('plist').children.length !== D.programs.length) {
      $('plist').innerHTML = D.programs.map((p) => `<button data-name="${p.name}"><b>${p.name}</b><span>${p.houses} houses · ${p.bytes} B</span></button>`).join('');
      document.querySelectorAll('#plist button').forEach((b) => (b.onclick = () => selectProgram(b.dataset.name)));
      if (!prog && D.programs.length) selectProgram(D.programs[0].name);
    }
    $('tlist').innerHTML = D.traces.slice().reverse().slice(0, 12).map((t) => `<button data-house="${t.house}" data-tick="${t.tick}"><b>#${t.house}</b><span>${t.program} · ${t.steps.length} ins · ${t.us} µs</span></button>`).join('');
    document.querySelectorAll('#tlist button').forEach((b) => (b.onclick = () => showTrace(D.traces.find((t) => t.house === +b.dataset.house && t.tick === +b.dataset.tick))));
    if (trace) document.querySelectorAll('#tlist button').forEach((b) => b.setAttribute('aria-pressed', String(+b.dataset.house === trace.house && +b.dataset.tick === trace.tick)));
  }

  async function poll() {
    try { D = await (await fetch('/programs.json')).json(); render(); } catch (e) { /* keep showing what we have */ }
    setTimeout(poll, 1500);
  }

  $('src').addEventListener('input', () => { edited[prog.name] = $('src').value; renderSource(); });
  $('src').addEventListener('scroll', () => { $('src-hl').scrollTop = $('src').scrollTop; $('src-hl').scrollLeft = $('src').scrollLeft; });
  $('src-reset').onclick = () => { delete edited[prog.name]; selectProgram(prog.name); };
  $('src-save').onclick = () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([$('src').value], { type: 'text/plain' }));
    a.download = prog.name + '.hope';
    a.click();
  };
  $('run-play').onclick = () => { if (!trace) return; if (step >= trace.steps.length - 1) seek(0); playing = !playing; $('run-play').textContent = playing ? 'Pause' : 'Play'; };
  $('run-scrub').oninput = () => { playing = false; $('run-play').textContent = 'Play'; seek(+$('run-scrub').value); };
  $('watch-go').onclick = async () => {
    const house = +$('watch-id').value;
    await fetch('/cmd', { method: 'POST', body: JSON.stringify({ cmd: 'trace', house }) });
    $('watch-note').textContent = `asked for house ${house}'s next run`;
    const want = (t) => t.house === house;
    const wait = async (n) => {
      if (n <= 0) { $('watch-note').textContent = `no run of house ${house} yet`; return; }
      const d = await (await fetch('/programs.json')).json();
      const t = d.traces.filter(want).pop();
      if (t) { D = d; render(); showTrace(t); $('watch-note').textContent = `house ${house}, tick ${t.tick}`; } else setTimeout(() => wait(n - 1), 700);
    };
    wait(20);
  };
  poll();
  tick();
})();
