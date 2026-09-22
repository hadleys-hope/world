/** models/campus: procedural colony viewer. */
import { state } from '../state.js';
import { localGroup } from '../geometry/objects.js';
import { quatAt, sph } from '../geometry/planet.js';
import { raisedWalk } from '../geometry/roads.js';
import { textSprite } from '../render/textures.js';
import { Kit } from './kit.js';
import { material } from './materials.js';
import { parkingLot } from './service-sites.js';
import * as THREE from 'three';
export function facility(name, x, y, w, h, d, opts = {}) {
  const g = localGroup(x, y, .65, opts.yaw || 0),
    k = new Kit(g),
    wall = material('facade-' + name, opts.color || 0x8c9387, {
      metalness: .28,
      roughness: .68
    }),
    floors = Math.max(1, Math.round(h / 4)),
    fh = h / floors;
  g.material = wall;
  g.userData.facility = name;
  state.layoutFootprints.push({
    name,
    x,
    y,
    w: w + 2.6,
    d: d + 4.4,
    yaw: opts.yaw || 0
  });
  k.box(state.M.concrete, 0, -.35, 0, w + 2.6, .7, d + 2.6);
  for (let level = 0; level < floors; level++) {
    const yy = level * fh;
    k.box(state.M.concrete, 0, yy, 0, w, .22, d);
    for (let side = 0; side < 4; side++) {
      const width = side % 2 ? d : w,
        depth = side % 2 ? w : d,
        bays = Math.max(2, Math.round(width / 4.2)),
        bw = width / bays;
      const box = (mat, u, v, ww, hh, th = .2, off = 0) => k.box(mat, side === 0 ? u : side === 2 ? -u : side === 1 ? depth / 2 + off : -depth / 2 - off, v, side === 0 ? depth / 2 + off : side === 2 ? -depth / 2 - off : side === 1 ? -u : u, side % 2 ? th : ww, hh, side % 2 ? ww : th);
      for (let bay = 0; bay < bays; bay++) {
        const u = -width / 2 + (bay + .5) * bw,
          door = level === 0 && side === (opts.front === -1 ? 2 : 0) && bay === Math.floor(bays / 2);
        box(state.M.steel, u - bw / 2, yy + fh / 2, .18, fh, .32, .12);
        if (door) {
          box(state.M.dark, u, 1.55, bw - .25, 3.1, .14);
          box(state.M.glass, u, 1.7, bw - .55, 2.35, .08, .13);
          box(state.M.trim, u, 3.25, bw + .35, .18, .3, .24);
          box(state.M.trim, u, 1.6, .08, 2.8, .16, .22);
        } else {
          box(wall, u, yy + .65, bw - .16, 1.3, .25);
          box(wall, u, yy + fh - .42, bw - .16, .84, .25);
          box(state.M.glass, u, yy + (fh + .45) / 2, bw - .35, fh - 2.12, .055, .02);
          box(state.M.trim, u, yy + 1.32, bw - .1, .11, .35, .11);
          box(state.M.trim, u, yy + fh - .84, bw - .1, .09, .2, .12);
          box(state.M.trim, u, yy + (fh + .45) / 2, .075, fh - 2.12, .12, .1);
          if ((bay + level) % 3 !== 1) box(state.M.glow, u, yy + fh - .98, bw - .9, .08, .09, -.25);
        }
        for (const du of [-bw / 2 + .22, bw / 2 - .22]) box(state.M.dark, u + du, yy + .4, .075, .075, .04, .17);
        if (level === 0 && !door) for (let rib = 0; rib < 6; rib++) box(state.M.trim, u - bw * .35 + rib * bw * .14, .67, .035, .8, .04, .15);
      }
      box(state.M.steel, 0, yy + fh - .06, width + .45, .17, .3, .1);
    }
  }
  k.box(state.M.roof, 0, h + .12, 0, w + .8, .32, d + .8);
  for (const z of [-d / 2, d / 2]) k.box(state.M.trim, 0, h + .7, z, w + .9, 1.1, .18);
  for (const x of [-w / 2, w / 2]) k.box(state.M.trim, x, h + .7, 0, .18, 1.1, d);
  const units = Math.max(2, Math.round(w / 12));
  for (let n = 0; n < units; n++) {
    const xx = (n - (units - 1) / 2) * 8;
    k.box(state.M.trim, xx, h + 1.35, -d * .18, 5, 2.1, 3.4);
    k.box(state.M.steel, xx, h + .4, -d * .18, 5.6, .25, 4);
    for (let l = 0; l < 13; l++) k.box(state.M.dark, xx, h + .48 + l * .14, -d * .18 + 1.73, 4.55, .065, .045);
    for (const fx of [-1.2, 1.2]) {
      k.add('cyl', state.M.dark, [xx + fx, h + 2.47, -d * .18], [.82, .1, .82]);
      for (let blade = 0; blade < 5; blade++) k.box(state.M.trim, xx + fx, h + 2.56, -d * .18, 1.45, .05, .12, [0, blade * Math.PI / 5, 0]);
    }
    industrialPipe(k, [[xx, h + .9, -d * .18 - 1.7], [xx, h + .9, -d * .4], [xx, h + 3, -d * .4]], .35, state.M.trim);
  }
  for (const x of [-w / 2 - .28, w / 2 + .28]) {
    k.pipe(state.M.steel, [x, h, -d / 2], [x, h, d / 2], .12);
    k.pipe(state.M.steel, [x, h, d / 2], [x, -.25, d / 2], .09);
    for (let yy = 1; yy < h; yy += 2) k.box(state.M.trim, x, yy, d / 2, .32, .055, .2);
  }
  const front = (opts.front === -1 ? -1 : 1) * d / 2;
  k.box(state.M.steel, 0, 3.65, front + Math.sign(front) * 1.5, 9, .22, 3.5);
  for (let j = 0; j < 4; j++) k.box(state.M.concrete, 0, -.25 - j * .12, front + Math.sign(front) * (1 + j * .45), 8, .18, .48);
  // Furnished ground floor / visible server hall, according to the facility's purpose.
  for (let row = 0; row < 2; row++) for (let col = 0; col < Math.min(6, Math.floor(w / 4)); col++) {
    const xx = -w / 2 + 3 + col * 4,
      zz = -d * .25 + row * d * .32;
    if (opts.type === 'network' || opts.type === 'power') {
      k.box(state.M.dark, xx, 1.3, zz, 1.4, 2.6, 1.1);
      for (let slot = 0; slot < 9; slot++) {
        k.box(state.M.steel, xx, .3 + slot * .25, zz + .57, 1.3, .17, .04);
        k.box(state.M.screen, xx + .42, .3 + slot * .25, zz + .61, .25, .05, .03);
      }
      k.pipe(state.M.blue, [xx, 2.8, zz], [xx, h - 1, zz], .06);
    } else {
      k.box(state.M.wood, xx, .95, zz, 2.2, .14, 1.2);
      k.box(state.M.fabric, xx, 1, zz - .85, .72, .8, .65);
      k.box(state.M.screen, xx, 1.42, zz + .1, .8, .5, .08);
    }
  }
  const gate = opts.type === 'workshop';
  if (gate) {
    for (let j = -1; j <= 1; j++) {
      const xx = j * w * .27;
      k.box(state.M.dark, xx, 3.1, -d / 2 - .1, 8, 6.2, .1);
      for (let slat = 0; slat < 18; slat++) k.box(state.M.trim, xx, .25 + slat * .32, -d / 2 - .18, 7.7, .07, .07);
      k.box(state.M.amber, xx, 6.45, -d / 2 - .26, 8.5, .2, .18);
    }
  }
  k.finish();
  const label = textSprite(name, '#e0d8b1', 32);
  label.position.set(0, 3.2, front + Math.sign(front) * .3);
  label.scale.set(Math.min(w * .7, 18), 1.25, 1);
  label.material.depthTest = true;
  g.add(label);
  state.campusObjects.push(g);
  return g;
}
export function industrialPipe(kit, points, r, mat = state.M.trim) {
  const path = [new THREE.Vector3(...points[0])];
  for (let i = 1; i < points.length - 1; i++) {
    const a = new THREE.Vector3(...points[i - 1]),
      b = new THREE.Vector3(...points[i]),
      c = new THREE.Vector3(...points[i + 1]),
      bend = Math.min(r * 3, a.distanceTo(b) * .3, b.distanceTo(c) * .3),
      entry = b.clone().addScaledVector(a.clone().sub(b).normalize(), bend),
      exit = b.clone().addScaledVector(c.clone().sub(b).normalize(), bend);
    path.push(entry);
    for (let step = 1; step <= 6; step++) {
      const t = step / 6;
      path.push(entry.clone().multiplyScalar((1 - t) ** 2).addScaledVector(b, 2 * (1 - t) * t).addScaledVector(exit, t * t));
    }
  }
  path.push(new THREE.Vector3(...points.at(-1)));
  for (let i = 1; i < path.length; i++) kit.pipe(mat, path[i - 1].toArray(), path[i].toArray(), r);
  for (let i = 1; i < points.length; i++) {
    const p = new THREE.Vector3(...points[i - 1]),
      v = new THREE.Vector3(...points[i]).sub(p).normalize();
    kit.pipe(state.M.steel, p.clone().addScaledVector(v, .2).toArray(), p.clone().addScaledVector(v, .2 + r * .45).toArray(), r * 1.18);
  }
}
export function civicFurniture(k, x, y, width = 24, depth = 12, yaw = 0) {
  const base = sph(x, y, 1.12),
    q = quatAt(x, y, yaw),
    put = (mat, p, sz) => k.add('box', mat, base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(), sz, q);
  for (let px = -width / 2; px < width / 2; px += 1.2) for (let pz = -depth / 2; pz < depth / 2; pz += 1.2) put(state.M.concrete, [px, .025, pz], [1.17, .08, 1.17]);
  for (const xx of [-width / 2 + 2, width / 2 - 2]) {
    for (let slat = 0; slat < 5; slat++) put(state.M.wood, [xx, .65, -2 + slat * .19], [3, .1, .16]);
    put(state.M.wood, [xx, 1.1, -2.2], [3, .85, .12]);
    for (const dx of [-1.1, 1.1]) put(state.M.steel, [xx + dx, .32, -1.6], [.12, .64, .85]);
    put(state.M.steel, [xx, 3.4, depth / 2], [.12, 6.8, .12]);
    put(state.M.trim, [xx, 6.72, depth / 2], [.75, .18, .75]);
    put(state.M.glow, [xx, 6.62, depth / 2], [.6, .07, .6]);
    put(state.M.concrete, [xx, .45, 2], [3.6, .9, 2]);
    for (let twig = 0; twig < 8; twig++) put(state.M.fabric, [xx - 1.4 + twig * .4, 1.15, 2], [.13, .6 + twig % 3 * .18, .13]);
  }
}
export function equipmentCabinet(x, y, w, h, d, color, yaw = 0) {
  state.layoutFootprints.push({
    name: 'distribution',
    x,
    y,
    w: w + 1.2,
    d: d + 1.2,
    yaw
  });
  const g = localGroup(x, y, 1.1, yaw),
    k = new Kit(g),
    paint = material('cabinet-' + color, color, {
      metalness: .5,
      roughness: .5
    });
  g.material = paint;
  k.box(state.M.concrete, 0, 0, 0, w + .8, .5, d + .8);
  k.box(paint, 0, h / 2, 0, w, h, d);
  k.box(state.M.trim, 0, h + .15, 0, w + .3, .25, d + .3);
  const n = Math.max(2, Math.round(w / 2));
  for (let j = 0; j < n; j++) {
    const xx = -w / 2 + (j + .5) * w / n;
    k.box(state.M.steel, xx, h / 2, d / 2 + .06, w / n - .15, h - .24, .08);
    k.box(state.M.trim, xx + w / n * .3, h * .45, d / 2 + .14, .08, .35, .09);
    for (let slot = 0; slot < 10; slot++) k.box(state.M.dark, xx, h * .2 + slot * .11, d / 2 + .12, w / n * .75, .045, .045);
    k.box(state.M.screen, xx, h * .76, d / 2 + .15, .42, .26, .04);
  }
  for (const side of [-1, 1]) {
    for (let fin = 0; fin < 12; fin++) k.box(state.M.trim, side * (w / 2 + .2), h * .5, -d * .4 + fin * d * .07, .4, h * .65, .08);
    industrialPipe(k, [[side * w * .3, 0, -d / 2 - .3], [side * w * .3, h * .7, -d / 2 - .3], [side * w * .3, h * .7, -d / 2]], .11, state.M.trim);
  }
  k.finish();
  return g;
}
export function buildCampus() {
  const k = new Kit(state.world);
  for (const path of [[[0, 95], [0, 109]], [[88, 46], [88, 69], [97, 76]], [[-88, 47], [-88, 65], [-98, 72]], [[-38, 29], [-38, 9]], [[43, 47], [43, 9]], [[-40, -31], [-40, -8]]]) raisedWalk(path, 3);
  for (const [x, y, w, d] of [[0, 53, 44, 16], [44, 20, 25, 16], [-43, 18, 23, 14], [-84, 58, 24, 10], [88, 57, 22, 10]]) civicFurniture(k, x, y, w, d);
  parkingLot(-80, -22, 26, 18, 0, 7);
  parkingLot(80, -22, 26, 18, 0, 7);
  facility('COLONY ADMINISTRATION', -38, 43, 27, 76, 25, {
    color: 0x81948d,
    type: 'office',
    front: -1
  });
  facility('SCIENCE / HABITAT TOWER', 43, 60, 25, 92, 24, {
    color: 0x8d8f7e,
    type: 'office',
    front: -1
  });
  // Tower roof crowns and external bracing create a recognisable skyline.
  for (const [x, y, h, w] of [[-38, 43, 76, 27], [43, 60, 92, 25]]) {
    const g = localGroup(x, y, .65, 0),
      kk = new Kit(g);
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) kk.pipe(state.M.steel, [sx * (w / 2 + .3), 0, sz * 12.8], [sx * (w / 2 + .3), h + 3, sz * 12.8], .18);
    kk.pipe(state.M.trim, [0, h, 0], [0, h + 16, 0], .15);
    kk.add('ball', state.M.glow, [0, h + 16, 0], [.24, .24, .24]);
    kk.finish();
  }
  // Heated paving strips share the power domain, with joints and inspection panels.
  for (let x = -110; x <= 110; x += 8) {
    const q = quatAt(x, 9);
    k.add('box', state.M.amber, sph(x, 9, 1.25).toArray(), [5.8, .025, .045], q);
  }
  for (const [x, y] of [[-58, -45], [55, -40], [110, 0], [-110, 0]]) {
    const q = quatAt(x, y);
    k.add('box', state.M.steel, sph(x, y, 2).toArray(), [1.2, 1.8, .7], q);
    k.add('box', state.M.screen, sph(x, y + .36, 2.4).toArray(), [.65, .22, .025], q);
  }
  k.finish();
}
export function initialize() {
  state.campusObjects = [];
  state.cargoYard = null;
  state.cargoCrane = null;
  state.cargoContainers = [];
  state.cargoPayload = null;
  state.externalFiber = [];
  state.spaceFiberPath = [];
}
