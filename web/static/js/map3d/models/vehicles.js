/** models/vehicles: procedural colony viewer. */
import { state } from '../state.js';
import { Kit } from './kit.js';
import { material } from './materials.js';
import * as THREE from 'three';
export function detailedVehicle(col, name) {
  const g = new THREE.Group(),
    k = new Kit(g),
    paint = material('vehicle-' + name, col, {
      metalness: .55,
      roughness: .37
    }),
    wheels = [];
  k.box(state.M.steel, 0, .7, 0, 7.4, .28, 2.3);
  k.box(paint, -1.1, 1.7, 0, 4.8, 1.8, 2.8);
  k.box(state.M.dark, 2.3, 1.45, 0, 2.1, 1.3, 2.6);
  k.box(paint, 2.3, 2.95, 0, 2.35, .16, 2.85);
  k.box(state.M.glass, 3.37, 2.45, 0, .06, .95, 2.44);
  k.box(paint, 3.38, 1.64, 0, .12, .48, 2.7);
  for (const z of [-1.37, 1.37]) {
    k.box(state.M.glass, 2.3, 2.42, z, 1.88, .95, .06);
    k.box(paint, 2.3, 1.65, z, 2.1, .52, .09);
    for (const x of [1.25, 3.33]) k.box(paint, x, 2.4, z, .11, 1.05, .11);
    k.box(state.M.trim, 1.7, 1.95, z * 1.012, .3, .045, .045);
    k.box(state.M.steel, 2.25, .91, z * 1.06, 1.8, .12, .4);
    k.pipe(state.M.steel, [3, 2.45, z], [3.12, 2.45, z * 1.28], .035);
    k.box(state.M.dark, 3.12, 2.5, z * 1.3, .12, .38, .24);
    k.box(state.M.dark, -.6, .6, z * .8, 1.15, .58, .58);
    k.add('cyl', state.M.trim, [-.6, .63, z * 1.015], [.11, .06, .11], [Math.PI / 2, 0, 0]);
    k.box(state.M.glow, 3.48, 1.55, z * .72, .09, .25, .4);
    k.box(material('brake', 0x913827, {
      emissive: 0x862414,
      emissiveIntensity: .6
    }), -3.55, 1.1, z * .75, .08, .25, .3);
    k.box(state.M.fabric, 2.2, 1.75, z * .43, .7, .55, .6);
    k.box(state.M.fabric, 1.95, 2.08, z * .43, .18, .68, .6);
  }
  k.box(state.M.dark, 3.1, 2.06, 0, .3, .18, 2.3);
  k.add('ring', state.M.rubber, [2.87, 2.15, .62], [.23, .23, .23], [0, Math.PI / 2, 0]);
  k.box(state.M.trim, 3.6, .98, 0, .18, .27, 3);
  k.box(state.M.trim, -3.6, .88, 0, .18, .27, 3);
  for (let j = 0; j < 12; j++) k.box(state.M.trim, 3.47, 1.66, -.6 + j * .11, .035, .33, .04);
  for (let x = -3.3; x < 1; x += .45) k.box(state.M.trim, x, 1.5, 1.42, .06, 1.35, .04);
  if (name === 'sludge') {
    k.add('cyl', state.M.trim, [-1.2, 2.1, 0], [1.15, 4.25, 1.15], [0, 0, Math.PI / 2]);
    k.pipe(state.M.dark, [-3.4, 2.1, 0], [-3.4, .9, 1.4], .09);
  }
  k.box(state.M.amber, 2.2, 3.12, 0, .8, .16, .24);
  k.finish();
  for (const x of [-2.45, -.6, 2.65]) for (const z of [-1.45, 1.45]) {
    const wheel = new THREE.Group();
    wheel.position.set(x, .67, z);
    const wk = new Kit(wheel);
    wk.add('cyl', state.M.rubber, [0, 0, 0], [.66, .38, .66], [Math.PI / 2, 0, 0]);
    wk.add('cyl', state.M.trim, [0, 0, Math.sign(z) * .21], [.37, .045, .37], [Math.PI / 2, 0, 0]);
    for (let j = 0; j < 8; j++) {
      const a = j * Math.PI / 4;
      wk.add('cyl', state.M.dark, [Math.cos(a) * .26, Math.sin(a) * .26, Math.sign(z) * .245], [.045, .035, .045], [Math.PI / 2, 0, 0]);
    }
    for (let j = 0; j < 20; j++) {
      const a = j * Math.PI / 10;
      wk.box(state.M.dark, Math.cos(a) * .65, Math.sin(a) * .65, 0, .13, .045, .4, [0, 0, a - Math.PI / 2]);
    }
    wk.finish();
    g.add(wheel);
    wheels.push(wheel);
  }
  g.userData.wheels = wheels;
  return g;
}
