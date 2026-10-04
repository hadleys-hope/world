/** Run with node --experimental-vm-modules tests/colonists.mjs. No browser required. */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SourceTextModule, SyntheticModule } from 'node:vm';
import * as THREE from '../vendor/three/build/three.module.js';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
let checked = 0;
function check(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const file = resolve(dir, entry.name);
    if (entry.isDirectory()) { check(file); continue; }
    if (!file.endsWith('.js')) continue;
    const module = new SourceTextModule(readFileSync(file, 'utf8'));
    for (const name of module.dependencySpecifiers) {
      const target = name.startsWith('.') ? resolve(dirname(file), name)
        : name === 'three' ? resolve(root, 'vendor/three/build/three.module.js')
        : name.startsWith('three/addons/') ? resolve(root, 'vendor/three/examples/jsm', name.slice(13)) : null;
      assert.ok(target && existsSync(target), `${file}: ${name}`);
    }
    checked++;
  }
}
check(resolve(root, 'web/static/js'));
const state = { world: new THREE.Group(), clickables: [], layers: { people: true }, S: { paused: false }, clock: { speed: 1 } };
function exportsModule(values) {
  return new SyntheticModule(Object.keys(values), function () {
    for (const [key, value] of Object.entries(values)) this.setExport(key, value);
  });
}
const dependencies = {
  three: exportsModule(THREE),
  '../state.js': exportsModule({ state }),
  '../geometry/planet.js': exportsModule({ sph: (x, y, h) => new THREE.Vector3(x, h, y), quatAt: (x, y, yaw = 0) => new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), yaw) }),
};
const module = new SourceTextModule(readFileSync(resolve(root, 'web/static/js/map3d/models/colonists.js'), 'utf8'));
await module.link(name => dependencies[name]);
await module.evaluate();
const { createColonist, animateColonist, syncColonists, updateColonists, sampleRoute, PROFESSIONS } = module.namespace;
for (const profession of PROFESSIONS) {
  const model = createColonist(profession);
  model.root.updateMatrixWorld(true);
  assert.ok(Math.abs(new THREE.Box3().setFromObject(model.root).min.y) < 1e-6, 'feet start on ground');
  animateColonist(model, .1, true);
  assert.notEqual(model.legs[0].rotation.x, 0);
  assert.equal(model.legs[0].rotation.x, -model.legs[1].rotation.x);
  model.root.updateMatrixWorld(true);
  assert.ok(Math.abs(new THREE.Box3().setFromObject(model.root).min.y) < 1e-6, 'support boot remains grounded while walking');
  const phase = model.phase;
  animateColonist(model, 0, true);
  assert.equal(model.phase, phase);
  for (let i = 0; i < 100; i++) animateColonist(model, .1, false);
  assert.ok(Math.abs(model.legs[0].rotation.x) < 1e-5, 'walk settles into idle');
}
syncColonists([[0, 0, 1, 0, 7], [1, 0, 2, 0, 8]]);
const first = state.colonists.get(7);
syncColonists([[1, 0, 2, 0, 8], [10, 0, 1, 0, 7]]);
assert.equal(state.colonists.get(7), first, 'identity survives snapshot reorder');
updateColonists(1000); updateColonists(1100);
assert.ok(first.x > 0 && first.x < 10);
assert.ok(first.root.quaternion.y > 0, 'turn towards travel');
state.S.paused = true;
const x = first.x, phase = first.phase;
updateColonists(1200);
assert.equal(first.x, x); assert.equal(first.phase, phase);
syncColonists([]);
assert.equal(state.clickables.length, 0);
assert.equal(state.colonistGroup.children.length, 0);
const bend = [[0, 0, 1.32], [0, 10, 1.32], [10, 10, .65]];
assert.deepEqual(sampleRoute(bend, .25), [0, 5, 1.32]);
const midpoint = sampleRoute(bend, .75);
assert.deepEqual(midpoint.slice(0, 2), [5, 10]);
assert.ok(Math.abs(midpoint[2] - .985) < 1e-10);
state.S.paused = false;
syncColonists([[5, 10, 1, 0, 1, 'electrician', false, .985, bend, .75]]);
const resumed = state.colonists.get(1);
updateColonists(1300);
assert.equal(resumed.x, 5, 'loaded route retains progress');
assert.equal(resumed.y, 10);
assert.ok(Math.abs(resumed.height - .985) < 1e-10);
syncColonists([[10, 10, 1, 0, 1, 'electrician', false, .65, bend, 1]]);
updateColonists(1400);
assert.equal(resumed.y, 10, 'movement follows path, without cutting the corner');
assert.ok(resumed.x > 5 && resumed.x < 10);
console.log(`Parsed ${checked} JS modules; imports resolve. Colonist rig, animation, identity, pause and cleanup checks passed.`);
