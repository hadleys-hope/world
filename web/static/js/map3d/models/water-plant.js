/** models/water-plant: procedural colony viewer. */
import { state } from '../state.js';
import { localGroup } from '../geometry/objects.js';
import { quatAt, sph } from '../geometry/planet.js';
import { road } from '../geometry/primitives.js';
import { Kit } from './kit.js';
import * as THREE from 'three';
export function plantDetails() {
  const c = state.G.cfg;
  for (const [key, w, h, d] of [['water_plant_pos', 60, 24, 40], ['mine_pos', 60, 20, 44], ['waste_station_pos', 40, 14, 30], ['radwaste_pos', 70, 12, 50]]) {
    const [x, y] = c[key],
      yaw = -Math.atan2(y, x),
      q = quatAt(x, y, yaw),
      g = localGroup(x, y, 0, yaw),
      k = new Kit(g);
    k.box(state.M.concrete, 0, .26, 0, w + 22, .5, d + 24);
    for (const side of [-1, 1]) {
      const z = side * (d / 2 + .08);
      for (let j = -w / 2 + 2; j < w / 2; j += 4) {
        k.box(state.M.steel, j, h / 2, z, .23, h, .25);
        for (let level = 5; level < h - 2; level += 5) {
          k.box(state.M.steel, j + 1.1, level, z + side * .18, 2.35, 1.55, .2);
          k.box(state.M.glass, j + 1.1, level, z + side * .3, 2.16, 1.32, .04);
        }
      }
      k.pipe(state.M.trim, [-w / 2 - 1.2, 1, z], [w / 2 + 1.2, 1, z], .17);
      k.pipe(state.M.trim, [-w / 2 - 1.2, 1, z], [-w / 2 - 1.2, h, z], .17);
      for (let xx = -w / 2 + 1; xx < w / 2; xx += 8) {
        k.box(state.M.steel, xx, 3.8, z + side, .12, 1, .12);
        k.box(state.M.glow, xx, 4.3, z + side, 1.1, .14, .45);
      }
    }
    for (let j = 0; j < 4; j++) {
      const xx = -w / 2 + 8 + j * (w - 16) / 3;
      k.box(state.M.trim, xx, h + 1.1, 0, 4.4, 2.2, 3.6);
      for (let blade = 0; blade < 10; blade++) k.box(state.M.dark, xx - 1.8 + blade * .4, h + 2.24, 0, .23, .06, 3.1);
      k.pipe(state.M.steel, [xx, h + 1, -2], [xx, h + 1, -d * .35], .45);
    }
    k.box(state.M.dark, w / 2 + .12, 3.6, 0, .2, 6, 5.2);
    for (let j = 0; j < 14; j++) k.box(state.M.trim, w / 2 + .24, .7 + j * .42, 0, .12, .08, 5.2);
    for (let y0 = .8; y0 < h + 1.5; y0 += .35) k.pipe(state.M.trim, [w / 2 + .9, y0, d / 2 - 3], [w / 2 + .9, y0, d / 2 - 2.3], .035);
    for (const zz of [d / 2 - 3.05, d / 2 - 2.25]) k.pipe(state.M.steel, [w / 2 + .9, .5, zz], [w / 2 + .9, h + 2, zz], .055);
    for (let y0 = 3; y0 < h + 1; y0 += 1.2) k.add('ring', state.M.trim, [w / 2 + 1.3, y0, d / 2 - 2.65], [.65, .65, .65], [Math.PI / 2, 0, 0]);
    // Protected compound perimeter, a vehicle opening and a separate pedestrian wicket.
    for (const z of [-d / 2 - 10, d / 2 + 10]) for (let xx = -w / 2 - 10; xx < w / 2 + 10; xx += 4) {
      k.pipe(state.M.steel, [xx, .5, z], [xx, 3.8, z], .06);
      for (let yy = 1; yy < 3.8; yy += .45) k.pipe(state.M.trim, [xx, yy, z], [Math.min(xx + 4, w / 2 + 10), yy, z], .014);
      for (let xx2 = xx; xx2 < xx + 4; xx2 += .8) k.add('ring', state.M.steel, [xx2, 4, z], [.27, .27, .27], [0, Math.PI / 2, 0]);
    }
    for (const xx of [-w / 2 - 10, w / 2 + 10]) for (let z = -d / 2 - 10; z < d / 2 + 10; z += 4) {
      if (xx > 0 && Math.abs(z) < 5) continue;
      k.pipe(state.M.steel, [xx, .5, z], [xx, 3.8, z], .06);
      for (let yy = 1; yy < 3.8; yy += .45) k.pipe(state.M.trim, [xx, yy, z], [xx, yy, Math.min(z + 4, d / 2 + 10)], .014);
    }
    k.box(state.M.amber, w / 2 + 10, 1.1, -5.6, .7, 1.4, .7);
    for (let j = 0; j < 10; j++) k.box(j % 2 ? state.M.white : state.M.amber, w / 2 + 10, 2, -5 + j, .13, .13, 1);
    for (let j = 0; j < 7; j++) k.box(state.M.white, w / 2 + 5, .56, -3 + j, .55, .035, .45);
    k.finish();
    const endpoint = sph(x, y).add(new THREE.Vector3(w / 2 + 10, 0, 0).applyQuaternion(q));
    // Site access roads remain outside the footprint; buildings retain their own orientation.
    const ex = x + Math.cos(yaw) * (w / 2 + 10),
      ey = y - Math.sin(yaw) * (w / 2 + 10),
      spine = c.reactor_pos[0] + 70;
    road([[spine, ey], [ex, ey], [ex, y]], 7, 1, 0x454b4d);
  }
}
