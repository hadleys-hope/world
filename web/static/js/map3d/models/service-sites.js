/** models/service-sites: procedural colony viewer. */
import { state } from '../state.js';
import { localGroup } from '../geometry/objects.js';
import { polar, quatAt, sph } from '../geometry/planet.js';
import { ribbon } from '../geometry/primitives.js';
import { onRoad } from '../geometry/roads.js';
import { textSprite } from '../render/textures.js';
import { addLabel, clickable } from '../render/world.js';
import { equipmentCabinet, industrialPipe } from './campus.js';
import { Kit } from './kit.js';
import { material } from './materials.js';
import { metalRing } from './ocean.js';
import { detailedVehicle } from './vehicles.js';
import * as THREE from 'three';
export function parkingLot(x, y, w, d, yaw = 0, count = 6) {
  const g = localGroup(x, y, 0, yaw),
    k = new Kit(g),
    local = (a, b) => [x + Math.cos(yaw) * a + Math.sin(yaw) * b, y - Math.sin(yaw) * a + Math.cos(yaw) * b];
  state.layoutFootprints.push({
    name: 'parking',
    x,
    y,
    w,
    d,
    yaw,
    parking: true
  });
  // Surface follows the graded site; markings share its elevation and cannot sink below paving.
  const corners = [local(-w / 2, 0), local(w / 2, 0)];
  ribbon(corners, d, 1.015, 0x3d4648, {
    bumpMap: state.asphaltTexture
  });
  const bays = count,
    bw = w / bays,
    parkDepth = Math.min(6, d * .4);
  const add = (mat, xx, zz, ww, dd, h = .035) => {
    const p = local(xx, zz);
    k.add('box', mat, sph(...p, 1.06 + h / 2).sub(g.position).applyQuaternion(g.quaternion.clone().invert()).toArray(), [ww, h, dd]);
  };
  for (let i = 0; i <= bays; i++) add(state.M.white, -w / 2 + i * bw, -d / 2 + parkDepth / 2, .11, parkDepth);
  for (let i = 0; i < bays; i++) {
    add(state.M.concrete, -w / 2 + (i + .5) * bw, -d / 2 + .7, bw * .7, .25, .2);
    if (i % 3 !== 0) {
      const p = local(-w / 2 + (i + .5) * bw, -d / 2 + 3.3),
        car = detailedVehicle([0x8c9785, 0x9b8e76, 0x657f88][i % 3], 'parked-' + x + '-' + i);
      car.scale.set(.7, .7, .7);
      car.position.copy(sph(...p, 1.06));
      car.quaternion.copy(quatAt(...p, yaw + Math.PI / 2));
      state.world.add(car);
    }
  }
  for (const xx of [-w / 2, w / 2]) {
    const p = local(xx, -d / 2);
    k.pipe(state.M.steel, [xx, 1.1, -d / 2], [xx, 7.1, -d / 2], .06);
    k.box(state.M.glow, xx, 7, -d / 2 + 1, .45, .08, 1.8);
  }
  const curb = new Kit(state.world);
  for (const side of [-1, 1]) {
    for (let u = -w / 2; u < w / 2; u += 1) {
      const pp = local(u, side * d / 2);
      if (!onRoad(...pp, .3)) curb.add('box', state.M.concrete, sph(...pp, 1.12).toArray(), [.97, .25, .18], quatAt(...pp, yaw));
    }
    for (let v = -d / 2; v < d / 2; v += 1) {
      const pp = local(side * w / 2, v);
      if (!onRoad(...pp, .3)) curb.add('box', state.M.concrete, sph(...pp, 1.12).toArray(), [.18, .25, .97], quatAt(...pp, yaw));
    }
  }
  curb.finish();
  k.finish();
  return g;
}
export function storageVessel(name, x, y, r = 5, h = 14, color = 0xafb8b0) {
  const g = localGroup(x, y, 1.15, 0),
    k = new Kit(g),
    steel = material('tank-' + name, color, {
      metalness: .62,
      roughness: .43
    });
  state.layoutFootprints.push({
    name,
    x,
    y,
    w: r * 2 + 3,
    d: r * 2 + 3,
    yaw: 0
  });
  k.add('tankcyl', state.M.concrete, [0, -.3, 0], [r + 1.1, .6, r + 1.1]);
  k.add('tankcyl', steel, [0, h / 2, 0], [r, h, r]);
  k.add('cone', steel, [0, h + .45, 0], [r, .9, r]);
  for (let yy = 1; yy < h; yy += 2.4) metalRing(k, state.M.trim, [0, yy, 0], r + .025, .035);
  for (let n = 0; n < 24; n++) {
    const a = n * Math.PI / 12;
    k.pipe(state.M.trim, [Math.cos(a) * r, .3, Math.sin(a) * r], [Math.cos(a) * r, h, Math.sin(a) * r], .023);
  }
  for (const zz of [-.42, .42]) k.pipe(state.M.trim, [r + .55, 0, zz], [r + .55, h + 1.2, zz], .05);
  for (let yy = .3; yy < h + 1; yy += .32) k.pipe(state.M.trim, [r + .55, yy, -.42], [r + .55, yy, .42], .035);
  for (let yy = 2; yy < h; yy += 1.3) metalRing(k, state.M.steel, [r + .8, yy, 0], .6, .026);
  metalRing(k, state.M.trim, [0, h + 1.0, 0], r + .25, .03);
  for (let n = 0; n < 24; n++) {
    const a = n * Math.PI / 12;
    k.pipe(state.M.trim, [Math.cos(a) * (r + .25), h, Math.sin(a) * (r + .25)], [Math.cos(a) * (r + .25), h + 1, Math.sin(a) * (r + .25)], .025);
  }
  industrialPipe(k, [[0, 1, r], [0, 1, r + 2], [2, 1, r + 2]], .23, state.M.blue);
  k.add('ring', state.M.amber, [1, 1.4, r + 2], [.3, .3, .3], [Math.PI / 2, 0, 0]);
  k.box(state.M.amber, 0, h * .55, r + .07, r * 1.05, 1.5, .07);
  k.finish();
  const label = textSprite(name, '#172221', 28);
  label.position.set(0, h * .55, r + .14);
  label.scale.set(r, 1, 1);
  label.material.depthTest = true;
  g.add(label);
  g.material = steel;
  return g;
}
export function buildSolarFarm() {
  const c = state.G.cfg,
    [sx, sy] = c.solar_pos,
    k = new Kit(state.world),
    glass = material('photovoltaic-cell', 0x1a3555, {
      metalness: .55,
      roughness: .16,
      emissive: 0x102743,
      emissiveIntensity: .1
    });
  state.complex.panels = [{
    material: glass
  }];
  for (let col = 0; col < 12; col++) for (let row = 0; row < 8; row++) {
    const x = sx + (col - 5.5) * 16,
      y = sy + (row - 3.5) * 20,
      base = sph(x, y, 3.8),
      q = quatAt(x, y).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -.42));
    const put = (mat, p, size) => k.add('box', mat, base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(), size, q);
    put(state.M.steel, [0, -.13, 0], [14.6, .25, 9]);
    put(state.M.trim, [0, -.28, -2.7], [15, .16, .15]);
    put(state.M.trim, [0, -.28, 2.7], [15, .16, .15]);
    for (let a = 0; a < 12; a++) for (let b = 0; b < 6; b++) {
      const xx = -6.6 + a * 1.2,
        zz = -3.68 + b * 1.47;
      put(glass, [xx, .02, zz], [1.12, .07, 1.38]);
      put(state.M.trim, [xx, .063, zz], [.018, .008, 1.32]);
    }
    for (const xx of [-5, 5]) for (const zz of [-2.8, 2.8]) {
      const top = base.clone().add(new THREE.Vector3(xx, -.27, zz).applyQuaternion(q));
      k.pipe(state.M.steel, sph(x + xx, y + zz, .2).toArray(), top.toArray(), .12);
      k.add('box', state.M.concrete, sph(x + xx, y + zz, .16).toArray(), [.75, .32, .75], quatAt(x + xx, y + zz));
    }
    const end = base.clone().add(new THREE.Vector3(5, -.45, 0).applyQuaternion(q));
    k.pipe(state.M.dark, end.toArray(), sph(x + 5, y, .25).toArray(), .035);
    state.layoutFootprints.push({
      name: 'solar-table',
      x,
      y,
      w: 14.6,
      d: 9,
      yaw: 0
    });
  }
  k.finish();
  equipmentCabinet(sx + 112, sy + 10, 5, 3.4, 3, 0x849285);
  addLabel('SOLAR ARRAY / 96 CELL TABLES', sx, sy, 8, '#c8c49e', 'near');
}
export function buildServiceHangar() {
  const [a, r] = state.G.cfg.garage,
    [x, y] = polar(a, r),
    yaw = -a * Math.PI / 180 - Math.PI / 2,
    g = localGroup(x, y, 1.1, yaw),
    k = new Kit(g),
    w = 56,
    d = 24,
    h = 13;
  state.layoutFootprints.push({
    name: 'vehicle-hangar',
    x,
    y,
    w: w + 2,
    d: d + 2,
    yaw
  });
  k.box(state.M.concrete, 0, -.25, 0, w + 2, .5, d + 2);
  for (const xx of [-w / 2, w / 2]) {
    k.box(state.M.panel, xx, h / 2, 0, .22, h, d);
    for (let z = -d / 2; z <= d / 2; z += .65) k.box(state.M.trim, xx, 6.5, z, .35, 12.7, .08);
  }
  k.box(state.M.panel, 0, h / 2, -d / 2, w, h, .25);
  for (let xx = -w / 2; xx < w / 2; xx += .6) k.box(state.M.trim, xx, 6.5, -d / 2 - .1, .08, 12.7, .18);
  for (let xx = -28; xx <= 28; xx += 9.3) {
    k.box(state.M.steel, xx, 6.5, 12, .3, 13, .45);
    k.pipe(state.M.steel, [xx, 12.7, -12], [xx, 14, 0], .13);
    k.pipe(state.M.steel, [xx, 14, 0], [xx, 12.7, 12], .13);
  }
  k.box(state.M.roof, 0, 13.1, 0, 57, .28, 25);
  k.box(state.M.steel, 0, 11.5, 12, 56, 3, .3);
  for (const xx of [-18.6, 0, 18.6]) {
    for (let j = 0; j < 5; j++) k.box(state.M.trim, xx, 10.1 + j * .26, 12.3, 15, .12, .2);
    for (const side of [-1, 1]) {
      k.box(state.M.amber, xx + side * 3.1, 2.1, 0, .45, 4.2, .65);
      k.box(state.M.steel, xx + side * 2.2, 1.6, 0, 1.9, .2, .4);
      k.box(state.M.trim, xx + side * 1.0, 1.75, 0, .55, .12, 7);
    }
    const car = detailedVehicle(0x83978c, 'service-bay');
    car.position.set(xx, 2, 0);
    car.rotation.y = Math.PI / 2;
    g.add(car);
    for (let n = 0; n < 7; n++) k.box(state.M.dark, xx - 5 + n * .55, .8, -10, .45, 1.5, .5);
    k.box(state.M.amber, xx + 5, 1, -9, 3, 2, 1.3);
  }
  for (const xx of [-18, 0, 18]) {
    k.box(state.M.trim, xx, 14, 0, 4, 1.4, 2.7);
    for (let n = 0; n < 8; n++) k.box(state.M.dark, xx - 1.5 + n * .43, 14.74, 0, .18, .04, 2.3);
  }
  k.finish();
  const lab = textSprite('VEHICLE MAINTENANCE / SERVICE BAYS', '#e2d3ad', 32);
  lab.position.set(0, 11.4, 12.4);
  lab.scale.set(34, 1.4, 1);
  lab.material.depthTest = true;
  g.add(lab);
  const apron = polar(a, 224);
  ribbon([polar(a - 7.1, 224), polar(a + 7.1, 224)], 12, 1.02, 0x454b4d, {
    bumpMap: state.asphaltTexture
  });
  state.complex.garage = clickable(g, 'garage', 'garage');
  const side = polar(a + 9.5, 246);
  parkingLot(...side, 16, 18, yaw, 4);
}
export function rebuildHydroponics() {
  for (let n = 0; n < 3; n++) {
    const a = 248 + n * 9,
      [x, y] = polar(a, 244),
      g = localGroup(x, y, 1.1, 0),
      k = new Kit(g),
      r = 10;
    state.layoutFootprints.push({
      name: 'hydroponics',
      x,
      y,
      w: 22,
      d: 22,
      yaw: 0
    });
    k.add('cyl', state.M.concrete, [0, 0, 0], [11, .5, 11]);
    const dome = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), state.M.glass);
    g.add(dome);
    for (let meridian = 0; meridian < 16; meridian++) {
      const a = meridian * Math.PI / 8;
      for (let j = 0; j < 16; j++) {
        const aa = j * Math.PI / 32,
          bb = (j + 1) * Math.PI / 32;
        k.pipe(state.M.trim, [Math.cos(aa) * r * Math.cos(a), Math.sin(aa) * r, Math.cos(aa) * r * Math.sin(a)], [Math.cos(bb) * r * Math.cos(a), Math.sin(bb) * r, Math.cos(bb) * r * Math.sin(a)], .045);
      }
    }
    for (let row = -3; row <= 3; row++) {
      k.box(state.M.steel, row * 2, .8, 0, 1.3, .12, 13);
      for (let col = -5; col <= 5; col++) k.add('ball', state.M.fabric, [row * 2, 1.1, col], [.5, .6, .5]);
    }
    k.finish();
    addLabel('HYDROPONICS ' + (n + 1), x, y, 12, '#a5b898', 'near');
  }
}
