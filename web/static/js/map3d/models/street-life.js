/** models/street-life: procedural colony viewer. */
import { state } from '../state.js';
import { arcPts, polar, quatAt, sph } from '../geometry/planet.js';
import { raisedWalk } from '../geometry/roads.js';
import { addLabel } from '../render/world.js';
import { Kit } from './kit.js';
import * as THREE from 'three';
export function buildStreetLife() {
  const c = state.G.cfg,
    k = new Kit(state.streetDetail);
  // Streets share exact spine endpoints. Curbs stop at intersections, not across them.
  for (let s = 0; s < c.sectors; s++) for (let row = 0; row <= c.house_rows; row++) {
    const radius = c.house_radius_min - 30 + row * c.house_ring_step;
    for (let b = 0; b < 3; b++) {
      const a = s * 60 + 13 + b * 17,
        [x, y] = polar(a, radius + 10.2),
        q = quatAt(x, y, -a * Math.PI / 180 - Math.PI / 2),
        base = sph(x, y, 1.2);
      const local = (shape, mat, p, sz, rot = null) => k.add(shape, mat, base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(), sz, rot ? q.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(...rot))) : q);
      for (let j = 0; j < 5; j++) {
        local('box', state.M.wood, [0, .65, -.4 + j * .2], [2.8, .12, .15]);
        local('box', state.M.wood, [0, 1.0 + j * .17, -.46], [2.8, .12, .12]);
      }
      for (const xx of [-1, 1]) local('box', state.M.steel, [xx, .34, 0], [.12, .65, .85]);
      local('cyl', state.M.steel, [2.4, .7, 0], [.36, 1.25, .36]);
      local('cyl', state.M.dark, [2.4, 1.36, 0], [.3, .08, .3]);
      // Pedestrian luminaires with base bolts, outreach and warm shielded heads.
      local('cyl', state.M.steel, [-3.8, 2.9, 0], [.09, 5.8, .09]);
      local('box', state.M.steel, [-3.4, 5.75, 0], [.9, .1, .12]);
      local('box', state.M.glow, [-3, 5.65, 0], [.58, .1, .34]);
      local('box', state.M.concrete, [-3.8, .12, 0], [.55, .24, .55]);
    }
  }
  // Tangential neighbourhood promenades, retaining walls and human-scale plazas.
  const names = ['COMMISSARY / CANTEEN', 'SOCIAL CLUB', 'MAINTENANCE', 'COLONY MARKET', 'LAUNDRY / BATHS', 'RECREATION'];
  for (let s = 0; s < c.sectors; s++) {
    const a = s * 60 + 38,
      [x, y] = polar(a, 244),
      q = quatAt(x, y, -a * Math.PI / 180 - Math.PI / 2);
    const plaza = sph(x, y, .95);
    k.add('box', state.M.concrete, plaza.toArray(), [38, .22, 27], q);
    // Low modular civic frontage with awning, doors and sheltered waiting area.
    const base = sph(x, y, 1.1),
      put = (mat, p, sz) => k.add('box', mat, base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(), sz, q);
    put(state.M.panel, [0, 3.1, -7], [28, 6.2, 10]);
    put(state.M.steel, [0, 6.3, -7], [29, .35, 11]);
    put(state.M.steel, [0, 3.4, .2], [30, .25, 5]);
    for (let j = -3; j <= 3; j++) {
      put(state.M.glass, [j * 3.7, 2.1, -1.9], [2.7, 2.1, .06]);
      put(state.M.steel, [j * 4.6, 1.7, 2.3], [.13, 3.4, .13]);
    }
    const label = addLabel(names[s], x, y, 10, '#c5b992', 'near');
    raisedWalk(arcPts(s * 60 + 3, a, 226, 30), 2.8);
  }
  k.finish();
}
