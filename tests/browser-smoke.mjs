/** Real HTTP/browser smoke, including GPU initialization; no production endpoints. */
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdirSync } from 'node:fs';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const port = 18761, base = `http://127.0.0.1:${port}`;
const child = spawn(process.env.PYTHON || 'python3', ['hadleys_hope.py', '--port', String(port), '--speed', '0'], {
  cwd: root, env: { ...process.env, MQTT_URL: '', DATA_DIR: '', ADMIN_TOKEN: 'browser-test', PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe']
});
let log = ''; child.stdout.on('data', b => log += b); child.stderr.on('data', b => log += b);
let browser;
const errors = [];
try {
  for (let i = 0; i < 100; i++) {
    if (child.exitCode !== null) throw new Error(log);
    try { if ((await fetch(base+'/geometry')).ok) break; } catch {}
    await new Promise(r => setTimeout(r, 100));
    if (i === 99) throw new Error('Server timeout: '+log);
  }
  browser = await chromium.launch({ headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}),
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--disable-gpu-sandbox', '--single-process', '--no-zygote', '--in-process-gpu'] });
  const page = await browser.newPage({ viewport: {width: 1280, height: 800} });
  page.on('pageerror', e => { errors.push(e.message); console.error(e.stack); });
  page.on('console', m => { if (m.type() === 'error') { errors.push(m.text()); console.error(m.text()); } });
  page.on('response', r => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
  await page.addInitScript(() => { window.requestAnimationFrame = fn => { window.__nextFrame=fn; return 1; }; });
  await page.goto(base+'/?inspect&admin=browser-test');
  await page.waitForFunction(() => window.HH?.state?.houses && window.HH?.geometry, null, { timeout: 120000, polling: 100 });
  const metrics = await page.evaluate(async () => {
    const { state } = await import('/static/js/map3d/state.js');
    const { updateDetail } = await import('/static/js/map3d/render/lod.js');
    HH.flyTo(HH.geometry.houses.x[0], HH.geometry.houses.y[0], 90);
    state.camera.position.copy(state.flyAnim.to); state.controls.target.copy(state.flyAnim.tto); state.flyAnim=null;
    state.controls.update();
    for(let i=0;i<30;i++) updateDetail();
    HH.renderer.render(HH.scene,HH.camera);
    return { houses: HH.geometry.houses.x.length, detailed: HH.houseDetails.size, drawCalls: HH.renderer.info.render.calls, triangles: HH.renderer.info.render.triangles };
  });
  if (metrics.houses !== 300 || metrics.detailed < 1 || !metrics.triangles) throw new Error(JSON.stringify(metrics));
  mkdirSync(resolve(root,'test-results'), {recursive:true});
  await page.screenshot({path:resolve(root,'test-results/map3d.png')});
  console.log('3D scene:', metrics);
  for (const route of ['/flat','/attractors','/house?id=1','/graph','/bus']) {
    await page.goto(base+route);
    await page.waitForTimeout(700);
    await page.evaluate(() => { for(let i=0;i<6;i++) window.__nextFrame?.(performance.now()+i*40); });
    const canvases = await page.locator('canvas').count();
    if (route==='/attractors') {
      if (canvases < 2) throw new Error('Attractor panels missing');
      await page.screenshot({path:resolve(root,'test-results/attractors.png')});
      await page.locator('[data-phase="coupled"]').click();
      await page.evaluate(() => { for(let i=0;i<4;i++) window.__nextFrame?.(performance.now()+i*40); });
      await page.screenshot({path:resolve(root,'test-results/attractors-coupled.png')});
    }
    console.log('Page:',route,'canvases:',canvases);
  }
  if(errors.length) throw new Error(errors.join('\n'));
  console.log('All pages loaded through the real HTTP server; no browser errors.');
} finally {
  if(browser) await browser.close();
  child.kill('SIGTERM');
  if(child.exitCode===null) await once(child,'exit');
}
