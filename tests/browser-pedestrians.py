"""Optional real-browser NPC check. Requires Playwright and Chromium/Chrome.

Use BROWSER_EXECUTABLE for an existing Chrome/Edge binary. Screenshots are stored
in test-results; a temporary HTTP server never touches the running simulation.
"""
import json
import os
from pathlib import Path
import sys
import threading
import math
import tempfile
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'test-results/browser-tools'))
from playwright.sync_api import sync_playwright
from hadleys.world import World
from hadleys.api.server import make_handler
from hadleys.api.snapshots import house_geometry
from hadleys.domains.citizens import citizens_step, citizen_snapshot
from hadleys.persistence import Store
from hadleys.web import HTML, HTML3D

w = World()
w.t = 478
citizens_step(w)
w.paused = True
context = {'w': w}
server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(
    context, HTML, json.dumps(house_geometry(w)), None, '',
    HTML3D.replace('__THREE_BASE__', '/vendor/three/'), str(ROOT / 'vendor'),
))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
errors = []
output = ROOT / 'test-results'
output.mkdir(exist_ok=True)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get('BROWSER_EXECUTABLE'), args=[
            '--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
        ])
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.route('**/favicon.ico', lambda route: route.fulfill(status=204))
            def wait(expression, timeout=120000):
                return page.wait_for_function(expression, timeout=timeout, polling=100)
            def settle_view():
                wait("document.querySelector('.resident-portrait img')?.naturalWidth > 0")
                page.evaluate('''async () => {
                    const { state } = await import('/static/js/map3d/state.js');
                    await document.querySelector('.resident-portrait img').decode();
                    if (state.flyAnim) state.flyAnim.t0 = performance.now() - 1500;
                    window.__nextFrame(performance.now());
                    window.__nextFrame(performance.now());
                }''')
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            page.add_init_script('window.requestAnimationFrame = fn => { window.__nextFrame = fn; return 1; };')
            page.goto(f'http://127.0.0.1:{server.server_port}/?inspect')
            wait("document.querySelector('#colonist-roster').options.length === 300", timeout=120000)
            page.select_option('#colonist-roster', '0')
            wait("document.querySelector('#infobody').textContent.includes('workshop')", timeout=10000)
            wait("async () => (await import('/static/js/map3d/state.js')).state.npcRouteLine.visible")
            metrics = page.evaluate('''async () => {
                const { state } = await import('/static/js/map3d/state.js');
                const { frame } = await import('/static/js/map3d/render/frame.js');
                if (state.flyAnim) state.flyAnim.t0 = performance.now() - 1500;
                state.renderer.info.autoReset = false;
                state.renderer.info.reset();
                frame();
                const model = state.colonists.get(0);
                const metrics = { residents: state.S.citizens.length, outside: state.colonists.size,
                    routePoints: model.route.length, routeLine: state.npcRouteLine.visible,
                    triangles: state.renderer.info.render.triangles, height: model.height };
                state.renderer.info.autoReset = true;
                return metrics;
            }''')
            assert metrics['residents'] == 300 and metrics['routePoints'] > 2 and metrics['triangles'] > 1000 and metrics['routeLine'], metrics
            wait("document.querySelector('.resident-portrait img')?.naturalWidth > 0")
            assert page.evaluate('''async () => {
                const { state } = await import('/static/js/map3d/state.js');
                return state.npcSelectionMarker.visible && state.S.citizens.filter(c => c.commute_enabled).length === 50
                    && state.S.people.every(p => state.G.houses.sector[p[3]] === 0);
            }''')
            page.screenshot(path=str(output / 'npc-route.png'))
            outfit_residents = {'engineer': 0}
            for profession in ('scientist',):
                resident = next(c.id for c in w.citizens if c.profession == profession and c.state == 'WALK_TO_WORK')
                outfit_residents[profession] = resident
                page.select_option('#colonist-roster', str(resident))
                wait(f"document.querySelector('.resident-portrait img')?.alt.includes('{profession}')")
                settle_view()
                assert page.evaluate("async () => { const {state} = await import('/static/js/map3d/state.js'); return state.colonists.get(state.selected.id).root.userData.profession; }") == profession
                page.screenshot(path=str(output / f'npc-{profession}.png'))
            page.select_option('#colonist-roster', '0')
            settle_view()
            page.click('#panel-toggle')
            page.click('[data-panel="places"]')
            page.click('[data-pedestrian-edge="entrance:workshop"]')
            wait("document.querySelector('[data-pedestrian-edge=\"entrance:workshop\"]').textContent.startsWith('Open')")
            with w.lock:
                # The HTTP command mutates the server synchronously before its response.
                assert 'entrance:workshop' in w.navigation.closed
                before = (w.citizens[0].x, w.citizens[0].y)
                w.paused = False
                w.t = 479
                citizens_step(w)
                w.paused = True
                assert w.citizens[0].wait_reason == 'no_path'
                assert (w.citizens[0].x, w.citizens[0].y) == before
            wait("document.querySelector('#infobody').textContent.includes('No accessible pedestrian route')")
            page.evaluate('window.__nextFrame(performance.now());')
            page.screenshot(path=str(output / 'npc-waiting.png'))
            page.click('[data-pedestrian-edge="entrance:workshop"]')
            wait("document.querySelector('[data-pedestrian-edge=\"entrance:workshop\"]').textContent.startsWith('Close')")
            with w.lock:
                w.paused = False
                w.t = 480
                citizens_step(w)
                w.paused = True
                assert w.citizens[0].wait_reason != 'no_path'
            wait("!document.querySelector('#infobody').textContent.includes('No accessible pedestrian route')")
            page.click('#npc-sector')
            page.evaluate('''async () => {
                const { state } = await import('/static/js/map3d/state.js');
                if (state.flyAnim) state.flyAnim.t0 = performance.now() - 1500;
                window.__nextFrame(performance.now());
            }''')
            page.screenshot(path=str(output / 'npc-sector.png'))

            # Finish a real workday, save during the return trip, reload the server world.
            with w.lock:
                assert w.citizens[0].state == 'AT_WORK'
                w.paused = False
                for minute in range(w.t + 1, w.citizens[0].shift_end + 1):
                    w.t = minute
                    citizens_step(w)
                w.paused = True
                assert w.citizens[0].state == 'WALK_HOME'
                saved_profile = vars(w.citizens[0]).copy()
                saved_profiles = citizen_snapshot(w)
                with tempfile.TemporaryDirectory(dir=output) as directory:
                    store = Store(directory)
                    store.save_world(w)
                    resumed = store.load_world()
                    assert resumed is not None and resumed.paused
                    assert citizen_snapshot(resumed) == saved_profiles
                    assert vars(resumed.citizens[0]) == saved_profile
                    context['w'] = w = resumed
            page.reload()
            wait("document.querySelector('#colonist-roster').options.length === 300")
            page.select_option('#colonist-roster', '0')
            wait("document.querySelector('#infobody').textContent.includes('WALK_HOME')")
            assert page.evaluate('''async () => {
                const { state } = await import('/static/js/map3d/state.js');
                const profile = state.S.citizens[0], model = state.colonists.get(0);
                return state.S.paused && Math.abs(model.progress - profile.progress) < 1e-8
                    && Math.hypot(model.x - profile.x, model.y - profile.y) < 1e-8;
            }''')
            settle_view()
            page.screenshot(path=str(output / 'npc-loaded-return.png'))
            with w.lock:
                w.paused = False
                for _ in range(10):
                    w.t += 1
                    citizens_step(w)
                w.paused = True
                assert w.citizens[0].state == 'HOME'
            wait("document.querySelector('#infobody').textContent.includes('HOME') && !document.querySelector('#infobody').textContent.includes('WALK_HOME')")
            settle_view()
            page.screenshot(path=str(output / 'npc-home.png'))

            # Controlled storm halfway through a naturally scheduled next-day commute.
            resident = max((c for c in w.citizens if int(w.h_sector[c.home]) == 0), key=lambda c: c.route_length)
            walk_per_tick = w.cfg['citizen_walk_mps'] * w.cfg['tick_seconds']
            commute = math.ceil(w.navigation.distance(f'home:{resident.home}', f'work:{resident.workplace}') / walk_per_tick)
            midpoint = 1440 + resident.shift_start - commute + max(1, commute // 2) - 1
            with w.lock:
                w.paused = False
                for minute in range(w.t + 1, midpoint + 1):
                    w.t = minute
                    citizens_step(w)
                assert resident.state == 'WALK_TO_WORK'
                w.paused = True
            page.select_option('#colonist-roster', str(resident.id))
            wait("document.querySelector('#infobody').textContent.includes('WALK_TO_WORK')")
            settle_view()
            outfit_residents[resident.profession] = resident.id
            assert resident.profession == 'electrician'
            page.screenshot(path=str(output / 'npc-electrician.png'))
            page.click('#panel-toggle')
            page.click('[data-panel="operations"]')
            page.get_by_text('Scenario events', exact=True).click()
            page.click('[data-i="storm"]')
            wait("document.querySelector('#toast').textContent.includes('Snowstorm')")
            with w.lock:
                w.paused = False
                assert w.storm_ticks > 0
                w.t += 1
                citizens_step(w)
                w.paused = True
                assert resident.wait_reason == 'seeking_shelter'
            wait("document.querySelector('#infobody').textContent.includes('Heading to shelter')")
            settle_view()
            page.screenshot(path=str(output / 'npc-storm-seeking.png'))
            with w.lock:
                w.paused = False
                for _ in range(commute + 2):
                    w.t += 1
                    citizens_step(w)
                w.paused = True
                assert resident.state in ('HOME', 'AT_WORK') and resident.wait_reason == 'storm'
            wait("document.querySelector('#infobody').textContent.includes('Sheltering from storm')")
            settle_view()
            page.screenshot(path=str(output / 'npc-storm-sheltered.png'))
            with w.lock:
                w.storm_ticks = 0
                w.paused = False
                w.t += 1
                citizens_step(w)
                w.paused = True
                assert resident.wait_reason not in ('storm', 'seeking_shelter', 'no_path')
                assert resident.state in ('WALK_TO_WORK', 'AT_WORK')
            wait("!document.querySelector('#infobody').textContent.includes('Sheltering from storm') && !document.querySelector('#infobody').textContent.includes('Heading to shelter')")
            settle_view()
            page.screenshot(path=str(output / 'npc-storm-resumed.png'))
            page.select_option('#colonist-roster', '50')
            wait("document.querySelector('#infobody').textContent.includes('Not enabled in this sector')")
            page.evaluate('window.__nextFrame(performance.now());')
            assert page.evaluate("async () => !(await import('/static/js/map3d/state.js')).state.npcSelectionMarker.visible")
            assert not errors, errors
            (output / 'npc-acceptance.json').write_text(json.dumps({
                'result': 'passed', 'profiles': 300, 'commuting_profiles': 50,
                'professions': ['engineer', 'electrician', 'scientist'],
                'outfit_residents': outfit_residents,
                'workday': ['HOME', 'WALK_TO_WORK', 'AT_WORK', 'WALK_HOME', 'HOME'],
                'save_load': 'exact profile, route, progress and position; paused on reload',
                'storm_resident': resident.id, 'storm': 'seeking shelter, sheltered, resumed',
                'blocked_entrance': 'waiting and resuming', 'browser_errors': errors,
            }, indent=2), encoding='utf-8')
            print('Browser NPC full workday, three outfits, storm, save/load and route checks passed:', metrics)
        except Exception:
            print('Browser errors:', errors)
            page.screenshot(path=str(output / 'npc-browser-error.png'))
            raise
        finally:
            browser.close()
finally:
    server.shutdown()
    server.server_close()
    thread.join()
