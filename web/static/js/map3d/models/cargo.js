/** models/cargo: procedural colony viewer. */
import { state } from '../state.js';
import { localGroup } from '../geometry/objects.js';
import { polar, quatAt, sph } from '../geometry/planet.js';
import { textSprite } from '../render/textures.js';
import { facility } from './campus.js';
import { Kit } from './kit.js';
import { material } from './materials.js';
import { detailedVehicle } from './vehicles.js';
import * as THREE from 'three';
export function containerModel(color = 0x985139, code = 'WY-426', long = true) {
  const g = new THREE.Group(),
    k = new Kit(g),
    length = long ? 12.2 : 6.1,
    paint = material('container-' + color, color, {
      metalness: .65,
      roughness: .56
    });
  k.box(state.M.steel, 0, .12, 0, length, .24, 2.44);
  k.box(paint, 0, 1.5, 0, length, 2.65, 2.4);
  k.box(paint, 0, 2.87, 0, length, .12, 2.44);
  for (const side of [-1, 1]) {
    for (let x = -length / 2 + .15; x < length / 2; x += .27) k.box(state.M.trim, x, 1.48, side * 1.22, .055, 2.55, .045);
    for (const yy of [.2, 2.78]) k.box(state.M.steel, 0, yy, side * 1.25, length, .14, .12);
  }
  for (const x of [-length / 2, length / 2]) {
    for (const z of [-1.16, 1.16]) k.box(state.M.trim, x, 1.45, z, .16, 2.9, .16);
    for (const z of [-.62, .62]) {
      k.box(paint, x + Math.sign(x) * .08, 1.5, z, .11, 2.5, 1.08);
      k.pipe(state.M.trim, [x + Math.sign(x) * .17, .3, z], [x + Math.sign(x) * .17, 2.65, z], .035);
      for (const yy of [.65, 1.9]) k.box(state.M.steel, x + Math.sign(x) * .2, yy, z, .08, .09, .3);
    }
    for (const z of [-1.13, 1.13]) for (const yy of [.15, 2.78]) k.box(state.M.dark, x + Math.sign(x) * .11, yy, z, .07, .09, .11);
  }
  k.finish();
  const label = textSprite(code, '#e7d9b5', 28);
  label.position.set(0, 2, 1.275);
  label.scale.set(3, .4, 1);
  label.material.depthTest = true;
  g.add(label);
  return g;
}
export function freightVehicle() {
  const g = detailedVehicle(0xb79053, 'freight-cab'),
    k = new Kit(g);
  g.scale.set(.95, .95, .95);
  k.box(state.M.steel, -6, .82, 0, 14, .3, 2.75);
  for (const x of [-10, -8.5, -7]) for (const z of [-1.5, 1.5]) {
    k.add('cyl', state.M.rubber, [x, .68, z], [.66, .38, .66], [Math.PI / 2, 0, 0]);
    k.add('cyl', state.M.trim, [x, .68, z * 1.12], [.35, .04, .35], [Math.PI / 2, 0, 0]);
  }
  k.finish();
  const load = containerModel(0x995636, 'WY / CARGO', false);
  load.position.set(-7, 1.04, 0);
  load.visible = false;
  g.add(load);
  g.userData.cargo = load;
  return g;
}
export function buildCargoDepot() {
  const [angle, radius] = state.G.cfg.cargo_depot,
    [x, y] = polar(angle, radius + 30),
    yaw = -angle * Math.PI / 180 - Math.PI / 2;
  state.cargoYard = localGroup(x, y, .9, yaw);
  const k = new Kit(state.cargoYard);
  state.layoutFootprints.push({
    name: 'cargo-depot',
    x,
    y,
    w: 68,
    d: 41,
    yaw
  });
  k.box(state.M.concrete, 0, .05, 0, 68, .1, 41);
  for (let n = 0; n < 24; n++) {
    const col = n % 8,
      row = [2, 0, 1][Math.floor(n / 8)],
      c = containerModel([0x975537, 0xa56a39, 0x737e75, 0x47616b][n % 4], 'WY ' + String(60400 + n));
    c.position.set((col - 3.5) * 7.5, .14 + Math.floor(row / 2) * 2.92, -8 + row % 2 * 3.1);
    if (n % 2) c.rotation.y = Math.PI;
    c.scale.x = .5;
    state.cargoYard.add(c);
    state.cargoContainers.push(c);
  }
  for (const z of [-17, 21]) {
    k.box(state.M.steel, 0, .21, z, 68, .18, .18);
    for (let x = -33; x < 34; x += 2) k.box(state.M.concrete, x, .08, z, 1, .15, 1.6);
  }
  for (let x = -31; x < 32; x += 4) {
    k.box(state.M.white, x, .13, 15, 2, .03, .14);
    k.box(state.M.amber, x, .13, 22, 1.2, .03, .14);
  }
  state.cargoCrane = new THREE.Group();
  const ck = new Kit(state.cargoCrane);
  for (const z of [-17, 21]) for (const xx of [-3, 3]) {
    ck.box(state.M.amber, xx, 9.5, z, .7, 19, .7);
    ck.pipe(state.M.steel, [xx, .5, z], [xx, 12, z + (z < 0 ? 5 : -5)], .2);
    ck.add('cyl', state.M.dark, [xx, .7, z], [.62, .5, .62], [Math.PI / 2, 0, 0]);
  }
  for (const xx of [-3, 3]) {
    ck.box(state.M.amber, xx, 19.5, 8, .8, 1.2, 54);
    for (let z = -17; z < 21; z += 3) ck.pipe(state.M.steel, [xx, 19, z], [xx, 20.1, z + 3], .07);
  }
  for (let z = -17; z <= 34; z += 3) {
    ck.box(state.M.amber, 0, 20.1, z, 7, .3, .25);
    ck.pipe(state.M.trim, [-3, 20.3, z], [3, 20.3, Math.min(z + 3, 34)], .09);
  }
  for (const xx of [-3.5, 3.5]) ck.box(state.M.steel, xx, 21, 8, .35, .15, 54);
  ck.box(state.M.glass, 3.5, 18.6, 15, 3, 2.1, 3);
  ck.finish();
  state.cargoYard.add(state.cargoCrane);
  const trolley = new THREE.Group(),
    tk = new Kit(trolley);
  tk.box(state.M.steel, 0, 20.6, 0, 4.5, 1, 3);
  tk.add('cyl', state.M.trim, [0, 20.4, 0], [.55, 3, .55], [0, 0, Math.PI / 2]);
  tk.finish();
  state.cargoCrane.add(trolley);
  state.cargoCrane.userData.trolley = trolley;
  const hook = new THREE.Group(),
    hk = new Kit(hook);
  hk.box(state.M.amber, 0, 0, 0, 6.4, .35, 2.7);
  hk.pipe(state.M.trim, [0, .2, 0], [0, 1.1, 0], .14);
  hk.finish();
  state.cargoCrane.add(hook);
  state.cargoCrane.userData.hook = hook;
  const cables = new THREE.Mesh(new THREE.CylinderGeometry(.035, .035, 1, 5), state.M.dark);
  state.cargoCrane.add(cables);
  state.cargoCrane.userData.cable = cables;
  state.cargoPayload = containerModel(0x975537, 'WY / LIFT', false);
  state.cargoCrane.add(state.cargoPayload);
  state.cargoPayload.visible = false;
  k.finish();
  facility('FREIGHT / DISPATCH', ...polar(angle + 13.5, radius + 34), 18, 9, 14, {
    yaw,
    color: 0x968369,
    type: 'office'
  });
}
export function updateCargo(s) {
  if (!state.cargoCrane || !s.cargo) return;
  const c = s.cargo,
    on = c.phase !== 'WAIT',
    t = c.progress,
    idx = c.loaded % state.cargoContainers.length,
    source = state.cargoContainers[idx],
    sx = source.position.x,
    sz = source.position.z,
    sy = source.position.y;
  state.cargoContainers.forEach((g, i) => g.visible = i >= c.loaded && !(on && i === idx));
  state.cargoPayload.visible = on;
  const lifted = THREE.MathUtils.smoothstep(t, 0, .25),
    travel = THREE.MathUtils.smoothstep(t, .25, .68),
    lower = THREE.MathUtils.smoothstep(t, .7, .98);
  const r = s.rovers.find(v => v.name === 'freight-' + (c.truck - s.rovers.filter(v => v.name.startsWith('transit')).length + 1)),
    target = new THREE.Vector3(7, 1.1, 24.2);
  if (r) {
    const q = quatAt(r.x, r.y, -r.heading),
      p = sph(r.x - Math.sin(r.heading) * 2.2, r.y + Math.cos(r.heading) * 2.2, 1.08).add(new THREE.Vector3(-7 * .95, 1.04 * .95, 0).applyQuaternion(q));
    state.cargoYard.updateMatrixWorld(true);
    target.copy(state.cargoYard.worldToLocal(p));
  }
  const xx = sx + (target.x - sx) * travel,
    zz = sz + (target.z - sz) * travel,
    yy = sy + (14 - sy) * lifted - (14 - target.y) * lower;
  state.cargoCrane.position.x = xx;
  state.cargoPayload.position.set(0, yy, zz);
  state.cargoCrane.userData.hook.position.set(0, yy + 3.05, zz);
  state.cargoCrane.userData.trolley.position.z = zz;
  const cable = state.cargoCrane.userData.cable,
    hookY = yy + 4.1;
  cable.position.set(0, (20.4 + hookY) / 2, zz);
  cable.scale.y = Math.max(.1, 20.4 - hookY);
}
