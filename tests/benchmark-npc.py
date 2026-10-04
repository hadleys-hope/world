"""NPC capacity benchmark in an isolated world and Chrome. Requires Playwright.

Synthetic 100/300-person scenes never change the production Sector 1 limit.
Use BROWSER_EXECUTABLE for Chrome/Edge. Software WebGL is the reproducible default;
set NPC_BENCH_HARDWARE=1 to request the browser's default GPU instead.
"""
import copy
import json
import os
from pathlib import Path
import pickle
import platform
import statistics
import sys
import threading
import time
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'test-results/browser-tools'))
from playwright.sync_api import sync_playwright
from hadleys.world import World
from hadleys.api.server import make_handler
from hadleys.api.snapshots import house_geometry
from hadleys.domains.citizens import citizens_step, update_position
from hadleys.simulation import world_tick
from hadleys.web import HTML, HTML3D


def summary(samples):
    ordered = sorted(samples)
    return {'median_ms': round(statistics.median(samples), 3),
            'mean_ms': round(statistics.mean(samples), 3),
            'p95_ms': round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 3)}


base = World()
base.t, base.paused = 470, True
templates = base.citizens[:50]
payload = pickle.dumps(base)
report = {'platform': platform.platform(), 'python': platform.python_version(),
          'viewport': [1440, 900], 'server_ticks_per_case': 240,
          'frame_samples_per_case': 12, 'production_commuting_residents': 50,
          'note': 'Synthetic capacity scenes. Software GPU by default. FPS is derived from measured complete-frame time, not a real laptop FPS claim.',
          'server': {}, 'browser': {}}
for count in (0, 50, 100, 300):
    w = pickle.loads(payload)
    w.citizens = [copy.deepcopy(templates[i % 50]) for i in range(count)]
    for i, c in enumerate(w.citizens):
        c.id = i
        c.state, c.progress, c.duty_day = 'WALK_TO_WORK', .3, 0
        update_position(c)
    w.paused = False
    isolated = []
    for _ in range(240):
        started = time.perf_counter()
        citizens_step(w)
        isolated.append((time.perf_counter()-started)*1000)
    full = []
    for _ in range(240):
        started = time.perf_counter()
        world_tick(w)
        full.append((time.perf_counter()-started)*1000)
    report['server'][str(count)] = {'npc_step': summary(isolated), 'full_world_step': summary(full)}
    print(f'Server {count}: {report["server"][str(count)]}', flush=True)

server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(
    {'w': base}, HTML, json.dumps(house_geometry(base)), None, '',
    HTML3D.replace('__THREE_BASE__', '/vendor/three/'), str(ROOT / 'vendor'),
))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
errors = []
try:
    with sync_playwright() as p:
        args = ['--no-sandbox']
        if os.environ.get('NPC_BENCH_HARDWARE') != '1':
            args += ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get('BROWSER_EXECUTABLE'), args=args)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.route('**/favicon.ico', lambda route: route.fulfill(status=204))
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda message: print('Browser error:', message.text, flush=True) if message.type == 'error' else None)
            page.add_init_script('window.requestAnimationFrame = fn => { window.__nextFrame = fn; return 1; };')
            page.goto(f'http://127.0.0.1:{server.server_port}/?inspect')
            try:
                page.wait_for_function("document.querySelector('#colonist-roster').options.length === 300", polling=100, timeout=120000)
            except Exception:
                print('Browser initialization errors:', errors, flush=True)
                print('Banner:', page.locator('#banner').inner_text(), flush=True)
                page.screenshot(path=str(ROOT / 'test-results/npc-benchmark-error.png'))
                raise
            fixtures = []
            for c in templates:
                resident = copy.deepcopy(c)
                resident.progress = .3
                update_position(resident)
                fixtures.append([resident.x, resident.y, 1, resident.home, resident.id,
                                 resident.profession, False, resident.height, resident.route, resident.progress])
            metadata = page.evaluate('''async () => {
                const { state } = await import('/static/js/map3d/state.js');
                const { flyTo } = await import('/static/js/map3d/ui/inspection.js');
                const { polar } = await import('/static/js/map3d/geometry/planet.js');
                const { frame } = await import('/static/js/map3d/render/frame.js');
                flyTo(...polar(32, 254), 260);
                state.flyAnim.t0 = performance.now()-1500;
                frame();
                const gl = state.renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info');
                return {renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
                        bloom: state.layers.bloom, shadows: state.layers.shadows, browser: navigator.userAgent};
            }''')
            report['environment'] = metadata
            for count in (0, 50, 100, 300):
                result = page.evaluate('''async ({count, fixtures}) => {
                    const { state } = await import('/static/js/map3d/state.js');
                    const { syncColonists, updateColonists } = await import('/static/js/map3d/models/colonists.js');
                    const { frame } = await import('/static/js/map3d/render/frame.js');
                    // Remove the preceding capacity scene before creating this one.
                    state.S.paused = true;
                    syncColonists([]);
                    const people = Array.from({length: count}, (_,i) => {
                        const row = [...fixtures[i % fixtures.length]]; row[4] = i; return row;
                    });
                    syncColonists(people);
                    state.S.paused = false; state.clock.speed = 1;
                    state.selected = null; state.followColonist = null;
                    const gl = state.renderer.getContext();
                    state.renderer.info.autoReset = false;
                    const samples = [], calls = [], triangles = [], update = [];
                    for (let i=0; i<15; i++) {
                        for (const model of state.colonists.values()) model.targetProgress = Math.min(1,model.progress+.01);
                        state.renderer.info.reset();
                        const start = performance.now();
                        frame(); gl.finish();
                        if (i >= 3) {
                            samples.push(performance.now()-start);
                            calls.push(state.renderer.info.render.calls);
                            triangles.push(state.renderer.info.render.triangles);
                        }
                    }
                    for (let i=0; i<120; i++) {
                        const start=performance.now(); updateColonists(start); update.push(performance.now()-start);
                    }
                    state.renderer.info.autoReset = true;
                    state.S.paused = true;
                    const summarize = values => {
                        const ordered=[...values].sort((a,b)=>a-b);
                        return {median_ms: ordered[Math.floor(ordered.length/2)],
                                mean_ms: values.reduce((a,b)=>a+b,0)/values.length,
                                p95_ms: ordered[Math.min(ordered.length-1,Math.floor(ordered.length*.95))]};
                    };
                    return {visible_models: state.colonists.size, frame: summarize(samples),
                            npc_update: summarize(update), derived_fps: 1000/summarize(samples).mean_ms,
                            draw_calls: calls[Math.floor(calls.length/2)], triangles: triangles[Math.floor(triangles.length/2)]};
                }''', {'count': count, 'fixtures': fixtures})
                assert result['visible_models'] == count
                report['browser'][str(count)] = result
                print(f'Browser {count}: {json.dumps(result)}', flush=True)
            assert not errors, errors
        finally:
            browser.close()
finally:
    server.shutdown()
    server.server_close()
    thread.join()
output = ROOT / 'test-results/npc-performance.json'
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(f'Report: {output}', flush=True)
