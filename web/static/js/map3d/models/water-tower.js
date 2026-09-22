/** models/water-tower: procedural colony viewer. */
import { state } from '../state.js';
import { localGroup } from '../geometry/objects.js';
import { quatAt } from '../geometry/planet.js';
import { clickable } from '../render/world.js';
import { Kit } from './kit.js';
import { material } from './materials.js';
import { metalRing } from './ocean.js';
import * as THREE from 'three';
export function buildWaterTower() {
  const group = localGroup(-70, -45, 0, 0),
    k = new Kit(group),
    R = 5.1,
    H = 6.12;
  for (let i = 0; i < 4; i++) {
    const a = i * Math.PI / 2 + Math.PI / 4,
      x = Math.cos(a) * R,
      z = Math.sin(a) * R;
    k.pipe(state.M.steel, [x * 1.3, 0, z * 1.3], [x, 24, z], .22);
    k.box(state.M.concrete, x * 1.3, .2, z * 1.3, 1.8, .4, 1.8);
    const b = (i + 1) * Math.PI / 2 + Math.PI / 4,
      nx = Math.cos(b) * R,
      nz = Math.sin(b) * R;
    for (let y = 4; y < 23; y += 5) {
      k.pipe(state.M.trim, [x, y, z], [nx, y + 5, nz], .09);
      k.pipe(state.M.trim, [nx, y, nz], [x, y + 5, z], .09);
    }
  }
  k.add('cyl', state.M.steel, [0, 24, 0], [R + .15, .35, R + .15]);
  k.add('cyl', state.M.trim, [0, 30.3, 0], [R + .35, .4, R + .35]);
  k.pipe(state.M.trim, [0, .4, 0], [0, 24, 0], .26);
  for (let y = 0; y < 32; y += .36) k.pipe(state.M.trim, [R + .4, y, -.32], [R + .4, y, .32], .034);
  for (const z of [-.36, .36]) k.pipe(state.M.steel, [R + .4, 0, z], [R + .4, 32, z], .05);
  for (let i = 0; i < 36; i++) {
    const a = i * Math.PI / 18,
      x = Math.cos(a) * (R + .65),
      z = Math.sin(a) * (R + .65);
    k.pipe(state.M.trim, [x, 30.5, z], [x, 31.55, z], .025);
  }
  for (const y of [30.5, 31.55]) metalRing(k, state.M.trim, [0, y, 0], R + .65, .035);
  for (let y = 24; y < 30; y += .5) k.box(state.M.white, R + .18, y, 0, .06, .04, .4);
  k.finish();
  const shell = new THREE.Mesh(new THREE.CylinderGeometry(R, R, H, 40, 1, true), state.M.glass);
  shell.position.y = 24 + H / 2;
  group.add(shell);
  state.hub.tank = clickable(group, 'tank', 'tank');
  state.hub.tankLevel = new THREE.Mesh(new THREE.CylinderGeometry(R - .12, R - .12, 1, 40), material('tankwater', 0x3399b4, {
    transparent: true,
    opacity: .72,
    roughness: .1,
    metalness: .15
  }));
  state.hub.tankLevel.quaternion.copy(quatAt(-70, -45));
  state.world.add(state.hub.tankLevel);
}
