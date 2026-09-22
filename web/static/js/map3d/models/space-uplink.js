/** models/space-uplink: procedural colony viewer. */
import { state } from '../state.js';
import { localGroup } from '../geometry/objects.js';
import { quatAt, sph } from '../geometry/planet.js';
import { ribbon } from '../geometry/primitives.js';
import { addLabel, clickable } from '../render/world.js';
import { facility } from './campus.js';
import { Kit } from './kit.js';
import { metalRing } from './ocean.js';
import { parkingLot } from './service-sites.js';
import * as THREE from 'three';
export function secureCompound(x, y, w, d, entrance = 1) {
  const g = new THREE.Group(),
    k = new Kit(state.world);
  state.world.add(g);
  ribbon([[x - w / 2, y], [x + w / 2, y]], d, .65, 0x737a72);
  const post = (xx, zz) => k.pipe(state.M.steel, sph(x + xx, y + zz, .65).toArray(), sph(x + xx, y + zz, 3.75).toArray(), .055);
  const fence = (a, b) => {
    post(...a);
    for (let h = .95; h < 3.65; h += .42) k.pipe(state.M.trim, sph(x + a[0], y + a[1], h).toArray(), sph(x + b[0], y + b[1], h).toArray(), .014);
    k.pipe(state.M.steel, sph(x + a[0], y + a[1], 3.75).toArray(), sph(x + b[0], y + b[1], 3.75).toArray(), .025);
  };
  for (const z of [-d / 2, d / 2]) for (let xx = -w / 2; xx < w / 2; xx += 4) fence([xx, z], [Math.min(w / 2, xx + 4), z]);
  for (const xx of [-w / 2, w / 2]) for (let z = -d / 2; z < d / 2; z += 4) {
    if (xx > 0 && z < 8 && z + 4 > -8) continue;
    fence([xx, z], [xx, Math.min(d / 2, z + 4)]);
  }
  for (let j = 0; j < 12; j++) k.add('box', j % 2 ? state.M.white : state.M.amber, sph(x + w / 2, y - 6 + j, 2.7).toArray(), [.16, .16, 1], quatAt(x + w / 2, y - 6 + j));
  for (const z of [-7, 7]) {
    k.add('box', state.M.amber, sph(x + w / 2, y + z, 1.8).toArray(), [.65, 1.5, .65], quatAt(x + w / 2, y + z));
    k.add('box', state.M.glow, sph(x + w / 2, y + z, 2.8).toArray(), [.26, .22, .26], quatAt(x + w / 2, y + z));
  }
  k.finish();
  facility('SECURITY / ACCESS', x + w / 2 - 14, y + 13, 7, 4, 6, {
    color: 0x8d947f
  });
  parkingLot(x + w / 2 - 21, y - 18, 26, 13, 0, 6);
  return g;
}
export function buildSpaceDish() {
  const [x, y] = state.G.cfg.dish_pos;
  secureCompound(x, y, 160, 128);
  const base = localGroup(x, y, 0, 0),
    k = new Kit(base);
  k.add('cyl', state.M.concrete, [0, 1, 0], [17, 2, 17]);
  k.add('cyl', state.M.steel, [0, 3, 0], [12, 4, 12]);
  for (let n = 0; n < 48; n++) {
    const a = n * Math.PI / 24;
    k.add('box', state.M.trim, [Math.cos(a) * 12.2, 3, Math.sin(a) * 12.2], [.55, 2.5, .55], [0, -a, 0]);
  }
  const az = new THREE.Group();
  base.add(az);
  const yoke = new Kit(az);
  for (const side of [-1, 1]) {
    yoke.box(state.M.trim, side * 12, 18, 0, 4, 30, 8);
    yoke.pipe(state.M.steel, [side * 12, 5, -7], [side * 12, 31, 0], .75);
    yoke.pipe(state.M.steel, [side * 12, 5, 7], [side * 12, 31, 0], .75);
    yoke.add('cyl', state.M.dark, [side * 12, 32, 0], [2.8, 4.5, 2.8], [0, 0, Math.PI / 2]);
  }
  yoke.box(state.M.steel, 0, 10, 0, 28, 2, 12);
  yoke.finish();
  const dish = new THREE.Group();
  dish.position.y = 34;
  dish.rotation.x = -.55;
  az.add(dish);
  const R = 32,
    F = 23.68,
    pos = [],
    idx = [],
    rings = 20,
    segs = 96;
  for (let ring = 0; ring <= rings; ring++) for (let j = 0; j < segs; j++) {
    const r = R * ring / rings,
      a = j * Math.PI * 2 / segs;
    pos.push(r * Math.cos(a), r * r / (4 * F), r * Math.sin(a));
  }
  for (let r = 0; r < rings; r++) for (let j = 0; j < segs; j++) {
    const a = r * segs + j,
      b = r * segs + (j + 1) % segs,
      c = (r + 1) * segs + j,
      d = (r + 1) * segs + (j + 1) % segs;
    idx.push(a, b, c, b, d, c);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  dish.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
    color: 0xc5ceca,
    metalness: .63,
    roughness: .33,
    side: THREE.DoubleSide
  })));
  const frame = new Kit(dish);
  for (let radial = 0; radial < 48; radial++) {
    const a = radial * Math.PI / 24;
    for (let j = 1; j <= 12; j++) {
      const r0 = R * (j - 1) / 12,
        r1 = R * j / 12;
      frame.pipe(state.M.steel, [r0 * Math.cos(a), r0 * r0 / (4 * F) - .65, r0 * Math.sin(a)], [r1 * Math.cos(a), r1 * r1 / (4 * F) - .65, r1 * Math.sin(a)], .1);
    }
  }
  for (let ring = 1; ring <= 8; ring++) {
    const r = ring * 4,
      height = r * r / (4 * F);
    metalRing(frame, state.M.trim, [0, height - .3, 0], r, .085);
  }
  for (let n = 0; n < 4; n++) {
    const a = n * Math.PI / 2 + Math.PI / 4;
    frame.pipe(state.M.trim, [Math.cos(a) * 29, 29 * 29 / (4 * F), Math.sin(a) * 29], [Math.cos(a) * 2.5, F - 2, Math.sin(a) * 2.5], .19);
  }
  frame.add('cyl', state.M.steel, [0, F - 1, 0], [3, .55, 3]);
  frame.add('cyl', state.M.trim, [0, F - 2, 0], [1.2, 2, 1.2]);
  frame.box(state.M.dark, 0, -2, 0, 8, 3.5, 7);
  frame.finish();
  for (let h = 4; h < 31; h += .4) k.pipe(state.M.trim, [14, h, -.5], [14, h, .5], .035);
  for (const z of [-.55, .55]) k.pipe(state.M.steel, [14, 3, z], [14, 32, z], .055);
  k.finish();
  state.complex.dishGroup = clickable(base, 'dish', 'dish');
  state.complex.dishAzimuth = az;
  facility('DEEP SPACE / TRACKING', x + 48, y + 30, 26, 10, 18, {
    type: 'network',
    color: 0x85938e
  });
  addLabel('DEEP-SPACE ARRAY / 64 m', x, y, 82, '#b5cec5', 'mid');
}
