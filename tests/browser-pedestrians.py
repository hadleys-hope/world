"""Optional real-browser NPC check. Requires Playwright and Chromium/Chrome.

Use BROWSER_EXECUTABLE for an existing Chrome/Edge binary. Screenshots are stored
in test-results; a temporary HTTP server never touches the running simulation.
"""
import json
import os
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'test-results/browser-tools'))
from playwright.sync_api import sync_playwright
from hadleys.world import World
from hadleys.api.server import make_handler
from hadleys.api.snapshots import house_geometry
from hadleys.domains.citizens import citizens_step
from hadleys.web import HTML, HTML3D

w = World()
w.t = 478
citizens_step(w)
w.paused = True
server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(
    {'w': w}, HTML, json.dumps(house_geometry(w)), None, '',
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
            page.select_option('#colonist-roster', '50')
            wait("document.querySelector('#infobody').textContent.includes('Not enabled in this sector')")
            page.evaluate('window.__nextFrame(performance.now());')
            assert page.evaluate("async () => !(await import('/static/js/map3d/state.js')).state.npcSelectionMarker.visible")
            assert not errors, errors
            print('Browser NPC route, inspector, blocked entrance and resume checks passed:', metrics)
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
