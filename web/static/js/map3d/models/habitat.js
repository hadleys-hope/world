/** models/habitat: procedural colony viewer. */
import { state } from '../state.js';
import { quatAt, sph, terrainH } from '../geometry/planet.js';
import { cap } from '../geometry/primitives.js';
import { Kit } from './kit.js';
import * as THREE from 'three';
export function buildLandscape() {
  const land = cap(3850, -.12, 0xffffff, 290, 420, .08),
    positions = land.geometry.attributes.position,
    colors = [];
  for (let i = 0; i < positions.count; i++) {
    const px = positions.getX(i),
      py = positions.getY(i),
      pz = positions.getZ(i),
      rr = state.RP * Math.atan2(Math.hypot(px, pz), py),
      angle = Math.atan2(pz, px),
      x = rr * Math.cos(angle),
      y = rr * Math.sin(angle),
      h = terrainH(x, y);
    const grain = .5 + .25 * Math.sin(x * .052 + y * .043) * Math.cos(y * .081 - x * .027) + .12 * Math.sin(x * .29 + y * .37);
    const frost = state.sstep(70, 190, h),
      color = new THREE.Color().setRGB(.24 + grain * .12 + frost * .24, .255 + grain * .115 + frost * .27, .25 + grain * .11 + frost * .30);
    colors.push(color.r, color.g, color.b);
  }
  land.geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  land.material.vertexColors = true;
  const k = new Kit(state.world);
  for (const [px, py, height, width] of [[1250, 850, 180, 280], [-450, -1350, 145, 360], [-1640, 980, 220, 310], [450, 1650, 190, 330]]) {
    for (let n = 0; n < 160; n++) {
      const a = n * 2.39996,
        r = width * Math.sqrt((n + .5) / 160),
        x = px + Math.cos(a) * r,
        y = py + Math.sin(a) * r,
        sz = 2.5 + n % 9 * 1.3;
      k.add('ball', state.M.concrete, sph(x, y, sz * .22).toArray(), [sz, sz * .7, sz * .55], quatAt(x, y, a), 0x676b68);
    }
  }
  k.finish();
}
export function mediumHomes() {
  const kit = new Kit(state.world);
  for (let i = 0; i < state.houseShells.length; i++) {
    const {
        base,
        q
      } = state.houseShells[i],
      [w, h, d] = state.DIM[state.G.houses.type[i]],
      floors = Math.round((h - .45) / 3.4);
    const put = (mat, p, scale, rot = null) => kit.add('box', mat, base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(), scale, rot ? q.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(...rot))) : q, null, i);
    put(state.M.concrete, [0, -.4, 0], [w + .8, .8, d + .8]);
    put(state.M.panel, [0, h / 2, 0], [w, h, d]);
    put(state.M.roof, [0, h + .05, 0], [w + .3, .2, d + .3]);
    for (const z of [-d / 2, d / 2]) {
      put(state.M.trim, [0, h + .38, z], [w + .5, .7, .16]);
      for (let f = 0; f < floors; f++) {
        const fy = f * 3.4;
        put(state.M.steel, [0, fy + .12, z * 1.012], [w, .24, .26]);
        for (let x = -w / 2 + 1.8; x < w / 2 - 1; x += 3.2) {
          put(state.M.steel, [x, fy + 2, z * 1.015], [2.52, 1.95, .16]);
          put(state.M.glass, [x, fy + 2, z * 1.026], [2.3, 1.7, .065]);
          put(state.M.glow, [x, fy + 2, z * 1.02], [2.18, 1.58, .03]);
          put(state.M.trim, [x, fy + 2, z * 1.033], [.08, 1.75, .06]);
        }
      }
      for (let x = -w / 2; x <= w / 2; x += 3.2) put(state.M.steel, [x, h / 2, z * 1.034], [.13, h, .19]);
    }
    for (const x of [-w / 2, w / 2]) {
      put(state.M.trim, [x, h + .38, 0], [.16, .7, d + .5]);
      for (let f = 0; f < floors; f++) for (let z = -d / 2 + 2; z < d / 2 - 1; z += 3.2) {
        put(state.M.steel, [x * 1.013, f * 3.4 + 2, z], [.13, 1.9, 2.5]);
        put(state.M.glow, [x * 1.022, f * 3.4 + 2, z], [.035, 1.65, 2.15]);
        put(state.M.glass, [x * 1.032, f * 3.4 + 2, z], [.055, 1.7, 2.3]);
      }
      put(state.M.trim, [x * 1.024, h / 2, -d / 2 + .5], [.12, h, .12]);
    }
    put(state.M.steel, [0, 1.35, d / 2 + .32], [1.6, 2.7, .25]);
    put(state.M.glass, [0, 1.75, d / 2 + .47], [1.16, 1.45, .06]);
    put(state.M.steel, [0, 2.95, d / 2 + 1.1], [3.2, .16, 2.8]);
    for (let step = 0; step < 7; step++) put(state.M.concrete, [0, -.9 - step * .2, d / 2 + .65 + step * .35], [2.6, .2, .38]);
    put(state.M.trim, [w * .25, h + .85, -d * .15], [3.5, 1.4, 2.5]);
    for (let j = 0; j < 7; j++) put(state.M.dark, [w * .25 - 1.35 + j * .45, h + 1.58, -d * .15], [.21, .035, 2.1]);
    for (const x of [-w * .28, w * .08]) {
      put(state.M.steel, [x, h + 1.05, -d * .27], [.5, 2.1, .5]);
      put(state.M.trim, [x, h + 2.1, -d * .27], [.8, .18, .8]);
    }
    put(state.M.amber, [w / 2 + .11, 1.8, 0], [.24, .8, .55]);
  }
  state.mediumBatches = kit.finish();
  for (const m of state.mediumBatches) {
    m.userData.original = m.instanceMatrix.array.slice();
  }
}
export function syncMedium(wanted) {
  if (wanted.size === state.mediumHidden.size && [...wanted].every(i => state.mediumHidden.has(i))) return;
  for (const m of state.mediumBatches) {
    const src = m.userData.original,
      dst = m.instanceMatrix.array;
    m.userData.tags.forEach((id, j) => {
      if (wanted.has(id)) {
        dst.fill(0, j * 16, j * 16 + 16);
      } else if (state.mediumHidden.has(id)) {
        dst.set(src.subarray(j * 16, j * 16 + 16), j * 16);
      }
    });
    m.instanceMatrix.needsUpdate = true;
  }
  state.mediumHidden = new Set(wanted);
}
export function initialize() {
  state.mediumBatches = [];
  state.mediumHidden = new Set();
  state.potableGroup = new THREE.Group();
  state.potableBatches = [];
  state.netSpanPaths = [];
  state.houseNetDrops = [];
  state.cabinetMeters = [];
  state.phaseDrops = [];
  state.phaseDropFlow = null;
  state.roadSignals = [];
  state.vehicleModels = [];
  state.world.add(state.potableGroup);
}
