/** models/reactor: procedural colony viewer. */
import { state } from '../state.js';
import { localGroup } from '../geometry/objects.js';
import { quatAt, sph } from '../geometry/planet.js';
import { addLabel } from '../render/world.js';
import { facility, industrialPipe } from './campus.js';
import { Kit } from './kit.js';
import { metalRing } from './ocean.js';
import { parkingLot } from './service-sites.js';
import * as THREE from 'three';
export function reactorIndustry() {
  const c = state.G.cfg,
    [rx, ry] = c.reactor_pos,
    g = localGroup(rx, ry, 0, 0),
    k = new Kit(g);
  // Pressurised containment seams, access galleries and cable ladders.
  for (const h of [4, 18, 34, 49]) metalRing(k, state.M.trim, [0, h, 0], 46.35, .16);
  for (let n = 0; n < 24; n++) {
    const a = n * Math.PI / 12,
      x = Math.cos(a) * 46.3,
      z = Math.sin(a) * 46.3;
    k.pipe(state.M.trim, [x, 0, z], [x, 49, z], .13);
    if (n % 3 === 0) {
      k.box(state.M.steel, x, 18, z, 4, .25, 3, [0, -a, 0]);
    }
  }
  for (let yy = 5; yy < 50; yy += .36) k.pipe(state.M.trim, [47, yy, -.4], [47, yy, .4], .04);
  for (const z of [-.45, .45]) k.pipe(state.M.steel, [47, 1, z], [47, 52, z], .07);
  for (const side of [-1, 1]) {
    industrialPipe(k, [[-87, 8, side * 60], [-67, 8, side * 60], [-67, 8, side * 26], [-41, 8, side * 26]], 1.7, state.M.trim);
    industrialPipe(k, [[-84, 13, side * 60], [-60, 13, side * 60], [-60, 13, side * 18], [-41, 13, side * 18]], 1.25, state.M.steel);
    for (let x = -84; x <= -47; x += 9) {
      k.box(state.M.concrete, x, 2, side * 30, 3, 4, 3);
      k.box(state.M.steel, x, 5, side * 30, 3.6, .6, 5);
    }
  }
  industrialPipe(k, [[18, 18, 40], [18, 18, 88], [18, 12, 100]], 1.4, state.M.trim);
  industrialPipe(k, [[26, 14, 38], [26, 14, 91], [26, 7, 100]], 1, state.M.steel);
  for (const xx of [0, 30, 60]) {
    k.box(state.M.concrete, xx, .4, -95, 14, .8, 12);
    k.box(state.M.steel, xx, 4.8, -95, 10, 8, 7);
    for (const z of [-100, -90]) for (let fin = 0; fin < 18; fin++) k.box(state.M.trim, xx - 4.5 + fin * .5, 4.4, z, .11, 6.5, 2);
    k.add('cyl', state.M.trim, [xx, 9.7, -95], [1.3, 8, 1.3], [0, 0, Math.PI / 2]);
    for (let phase = -1; phase <= 1; phase++) for (let disc = 0; disc < 9; disc++) k.add('cyl', state.M.white, [xx + phase * 3, 10.5 + disc * .45, -95], [.75, .16, .75]);
    industrialPipe(k, [[xx, 14.8, -95], [xx, 16.5, -88], [30, 16.5, -88]], .18, state.M.trim);
  }
  k.finish();
  state.complex.tw1.visible = false;
  state.complex.tw2.visible = false;
  for (const z of [-60, 60]) {
    const points = [];
    for (let i = 0; i <= 24; i++) {
      const h = i / 24 * 90,
        r = 13 + 10 * ((h - 55) / 55) ** 2;
      points.push(new THREE.Vector2(r, h));
    }
    const tower = new THREE.Mesh(new THREE.LatheGeometry(points, 40), new THREE.MeshStandardMaterial({
      color: 0x999b91,
      roughness: .93,
      side: THREE.DoubleSide
    }));
    tower.position.copy(sph(rx - 90, ry + z));
    tower.quaternion.copy(quatAt(rx - 90, ry + z));
    state.world.add(tower);
    const tk = new Kit(state.world),
      q = quatAt(rx - 90, ry + z);
    for (let n = 0; n < 20; n++) {
      const a = n * Math.PI / 10;
      tk.pipe(state.M.concrete, sph(rx - 90 + Math.cos(a) * 23, ry + z + Math.sin(a) * 23, 0).toArray(), sph(rx - 90 + Math.cos(a) * 21, ry + z + Math.sin(a) * 21, 8).toArray(), .6);
    }
    tk.finish();
  }
  state.layoutFootprints.push({
    name: 'reactor-containment',
    x: rx,
    y: ry,
    w: 96,
    d: 96,
    yaw: 0
  }, {
    name: 'cooling-north',
    x: rx - 90,
    y: ry - 60,
    w: 48,
    d: 48,
    yaw: 0
  }, {
    name: 'cooling-south',
    x: rx - 90,
    y: ry + 60,
    w: 48,
    d: 48,
    yaw: 0
  }, {
    name: 'reactor-switchyard',
    x: rx + 30,
    y: ry - 95,
    w: 94,
    d: 42,
    yaw: 0
  });
  const hall = facility('TURBINE / GENERATOR HALL', rx - 2, ry + 117, 76, 22, 34, {
    type: 'power',
    color: 0x8d9389
  });
  state.complex.turbine.visible = false;
  facility('HEAT RECOVERY / EXCHANGERS', rx - 52, ry - 145, 56, 15, 28, {
    type: 'power',
    color: 0x7b8c86
  });
  facility('REACTOR MAINTENANCE', rx + 145, ry + 113, 58, 17, 38, {
    type: 'workshop',
    color: 0x9a9581
  });
  parkingLot(rx + 150, ry + 52, 50, 26, 0, 10);
  const yard = localGroup(rx + 30, ry - 95, 1.1, 0),
    fence = new Kit(yard);
  fence.box(state.M.concrete, 0, -.2, 0, 90, .4, 38);
  for (const z of [-20, 20]) for (let x = -46; x <= 46; x += 3) {
    fence.pipe(state.M.steel, [x, 0, z], [x, 3, z], .05);
    for (let h = .4; h < 3; h += .4) fence.pipe(state.M.trim, [x, h, z], [Math.min(x + 3, 46), h, z], .013);
  }
  for (const x of [-46, 46]) for (let z = -20; z < 20; z += 3) {
    if (x > 0 && Math.abs(z) < 5) continue;
    fence.pipe(state.M.steel, [x, 0, z], [x, 3, z], .05);
    for (let h = .4; h < 3; h += .4) fence.pipe(state.M.trim, [x, h, z], [x, h, Math.min(z + 3, 20)], .013);
  }
  fence.finish();
  addLabel('SWITCHYARD / STEP-UP TRANSFORMERS', rx + 30, ry - 95, 18, '#cbbd8a', 'near');
}
