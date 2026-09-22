/** models/houses: procedural colony viewer. */
import { state } from '../state.js';
import { textSprite } from '../render/textures.js';
import { utilityPoint } from './drainage.js';
import { Kit } from './kit.js';
import { material } from './materials.js';
import * as THREE from 'three';
export function makeHouse(i) {
  const [w, h, d] = state.DIM[state.G.houses.type[i]],
    type = state.G.houses.type[i],
    floors = Math.round((h - .45) / 3.4);
  const g = new THREE.Group(),
    shell = new THREE.Group(),
    roof = new THREE.Group(),
    inside = new THREE.Group();
  g.add(shell, inside, roof);
  g.position.copy(state.houseShells[i].base);
  g.quaternion.copy(state.houseShells[i].q);
  state.world.add(g);
  const k = new Kit(shell),
    r = new Kit(roof),
    interiorKit = new Kit(inside),
    accent = [0xaaa18a, 0x8d9e99, 0xa58b62, 0x788681][i % 4];
  const floorH = (h - .45) / floors;
  k.box(state.M.concrete, 0, -.4, 0, w + .8, .8, d + .8);
  // Actual individual brick plinth, running bond, on all four sides.
  for (let side = 0; side < 4; side++) {
    const width = side % 2 ? d : w;
    for (let row = 0; row < 3; row++) for (let j = 0; j < Math.floor(width / .62); j++) {
      const along = -width / 2 + .31 + j * .62 + row % 2 * .29;
      if (along > width / 2 - .12) continue;
      const x = side === 0 ? along : side === 2 ? -along : side === 1 ? w / 2 : -w / 2,
        z = side === 0 ? d / 2 : side === 2 ? -d / 2 : side === 1 ? -along : along;
      k.box(state.M.brick, x, -.69 + row * .23, z, side % 2 ? .24 : .59, .205, side % 2 ? .59 : .24, null, 0x756650 + i % 3 * 0x030303);
    }
  }
  // Hollow four-wall shell: prefab bays assembled around genuine glass apertures.
  for (let side = 0; side < 4; side++) {
    const width = side % 2 ? d : w,
      depth = side % 2 ? w : d;
    const wall = (mat, u, v, ww, hh, thick = .22, offset = 0) => {
      const x = side === 0 ? u : side === 2 ? -u : side === 1 ? depth / 2 + offset : -depth / 2 - offset;
      const z = side === 0 ? depth / 2 + offset : side === 2 ? -depth / 2 - offset : side === 1 ? -u : u;
      k.box(mat, x, v, z, side % 2 ? thick : ww, hh, side % 2 ? ww : thick, null, mat === state.M.panel ? accent : null);
    };
    const bays = Math.floor(width / 3.2),
      bw = width / bays;
    for (let level = 0; level < floors; level++) for (let b = 0; b < bays; b++) {
      const u = -width / 2 + (b + .5) * bw,
        y = level * floorH;
      const door = side === 0 && b === Math.floor(bays / 2) && level === 0;
      wall(state.M.steel, -width / 2 + b * bw, y + floorH / 2, .14, floorH, .34, .05);
      if (door) {
        wall(state.M.panel, u, y + floorH - .35, bw - .12, .7);
        wall(state.M.dark, u, 1.23, 1.65, 2.46, .18, .04);
        wall(state.M.trim, u - 1.02, 1.23, .18, 2.6, .32, .13);
        wall(state.M.trim, u + 1.02, 1.23, .18, 2.6, .32, .13);
        wall(state.M.glass, u, 1.7, .85, .5, .09, .15);
        wall(state.M.amber, u + .58, 1.1, .11, .16, .2, .22);
        continue;
      }
      const sill = .85,
        wh = 1.65,
        ww = bw - .6;
      wall(state.M.panel, u, y + sill / 2, bw - .12, sill);
      wall(state.M.panel, u, y + (sill + wh + floorH) / 2, bw - .12, floorH - sill - wh);
      wall(state.M.panel, u - bw / 2 + .18, y + sill + wh / 2, .32, wh);
      wall(state.M.panel, u + bw / 2 - .18, y + sill + wh / 2, .32, wh);
      wall(state.M.glass, u, y + sill + wh / 2, ww, wh, .055, .04);
      for (const uu of [u - ww / 2, u, u + ww / 2]) wall(state.M.trim, uu, y + sill + wh / 2, .075, wh + .12, .16, .12);
      for (const yy of [y + sill, y + sill + wh]) wall(state.M.trim, u, yy, ww + .16, .09, .23, .15);
      wall(state.M.trim, u, y + sill - .08, ww + .35, .11, .45, .25); // drip sill
      // Bolt heads and shallow corrugations in each modular panel.
      for (const uu of [u - bw / 2 + .1, u + bw / 2 - .1]) for (const yy of [y + .2, y + floorH - .2]) wall(state.M.dark, uu, yy, .065, .065, .06, .19);
      for (let j = 0; j < 5; j++) wall(state.M.trim, u - ww / 2 + j * ww / 4, y + floorH - .42, .035, .56, .06, .14);
    }
    wall(state.M.steel, 0, h - .12, width + .3, .24, .4);
  }
  // Roof shell, parapets, access hatch, vents, HVAC louvers and service walk.
  r.box(state.M.roof, 0, h, 0, w + .55, .3, d + .55);
  for (const z of [-d / 2, d / 2]) r.box(state.M.trim, 0, h + .35, z, w + .55, .65, .2);
  for (const x of [-w / 2, w / 2]) r.box(state.M.trim, x, h + .35, 0, .2, .65, d);
  r.box(state.M.dark, -w * .25, h + .2, 0, 2, .18, 2.8);
  r.box(state.M.trim, -w * .25, h + .32, 0, 1.8, .13, 2.6);
  r.box(state.M.trim, w * .25, h + .8, -d * .15, 3.5, 1.35, 2.5);
  for (let v = 0; v < 11; v++) r.box(state.M.dark, w * .25, h + .28 + v * .1, -d * .15 + 1.27, 3.12, .045, .05);
  for (let v = 0; v < 2; v++) {
    r.add('cyl', state.M.dark, [w * .25 - .85 + v * 1.7, h + 1.53, -d * .15], [.61, .08, .61]);
    for (let j = 0; j < 4; j++) r.box(state.M.trim, w * .25 - .85 + v * 1.7, h + 1.6, -d * .15, 1.1, .04, .09, [0, j * Math.PI / 4, 0]);
  }
  r.pipe(state.M.trim, [w * .25, h + .55, -d * .15 - 1.25], [w * .25, h + .55, -d * .38], .28);
  for (const x of [-w * .28, -w * .1]) {
    r.pipe(state.M.steel, [x, h, -d * .2], [x, h + 1.6, -d * .2], .16);
    r.add('cyl', state.M.trim, [x, h + 1.65, -d * .2], [.35, .13, .35]);
  }
  for (let j = 0; j < 5; j++) r.box(state.M.trim, -w * .25, h + .22, -d * .4 + j * .65, 1.25, .035, .48);
  // Continuous rain gutters, downpipes, clips and discharge boots to storm riser.
  for (const x of [-w / 2 - .22, w / 2 + .22]) {
    k.pipe(state.M.steel, [x, h - .15, -d / 2], [x, h - .15, d / 2], .13);
    k.pipe(state.M.steel, [x, h - .15, d / 2], [x, -1.0, d / 2], .085);
    k.pipe(state.M.steel, [x, -1, d / 2], [0, -1, 6], .085);
    for (let y = .3; y < h; y += 1.2) k.add('ring', state.M.trim, [x, y, d / 2], [.11, .11, .11], [Math.PI / 2, 0, 0]);
  }
  // Six proper treads from sidewalk to porch and guarded side ramp (1:12).
  const doorX = -w / 2 + (Math.floor(Math.floor(w / 3.2) / 2) + .5) * (w / Math.floor(w / 3.2));
  k.box(state.M.concrete, doorX, -.12, d / 2 + 1.1, 3.2, .25, 2.2);
  for (let j = 0; j < 6; j++) k.box(state.M.concrete, doorX, -1.2 + .1 * (j + 1), d / 2 + 4.25 - j * .37, 2.8, .2 * (j + 1), .38);
  for (const x of [doorX - 1.5, doorX + 1.5]) {
    k.pipe(state.M.trim, [x, .85, d / 2 + 1], [x, -.12, d / 2 + 4.4], .045);
    for (const z of [d / 2 + .4, d / 2 + 1.9, d / 2 + 4.3]) k.pipe(state.M.trim, [x, -.9, z], [x, z > d / 2 + 3 ? -.12 : .85, z], .045);
  }
  k.box(state.M.steel, doorX, 2.9, d / 2 + 1, 4, .16, 2.8); // shelter over airlock
  k.box(state.M.glow, doorX, 2.7, d / 2 + .25, 1.6, .08, .14);
  // Accessible ramp runs along the front facade, with landings and twin rails.
  const rampZ = d / 2 + 1.1,
    run = 7.2;
  for (let leg = 0; leg < 2; leg++) {
    const midX = doorX - 1.6 - run / 2,
      yy = leg === 0 ? -.9 : -.3,
      zz = rampZ + leg * 1.6;
    k.box(state.M.concrete, midX, yy, zz, run, .12, 1.3, [0, 0, (leg === 0 ? -1 : 1) * Math.atan(1 / 12)]);
    for (const dz of [-.72, .72]) k.pipe(state.M.trim, [midX - run / 2, yy + (leg === 0 ? .3 : -.3) + .9, zz + dz], [midX + run / 2, yy + (leg === 0 ? -.3 : .3) + .9, zz + dz], .035);
  }
  k.box(state.M.concrete, doorX - 1.6 - run - .65, -.6, rampZ + .8, 1.3, .12, 2.9);
  k.box(state.M.concrete, doorX - 1.6, -1.2, rampZ, 1.3, .12, 1.3);
  // Pavers on frontage, with individual joints and deterministic colour variation.
  for (let row = 0; row < 17; row++) for (let col = 0; col < 4; col++) k.box(state.M.concrete, (col - 1.5) * .57, -1.04, d / 2 + 4.5 + row * .54, .55, .075, .52, null, 0x74766a + (row + col + i) % 4 * 0x030303);
  // Meter, isolator, frost jacket and all three separate wet-core connections.
  k.box(state.M.trim, w / 2 + .35, .6, 2, .7, 1.2, .8);
  k.box(state.M.dark, w / 2 + .72, .8, 2, .02, .3, .35);
  const meter = state.G.utilities.nodes[state.G.utilities.house_nodes[i]];
  const meterLocal = utilityPoint([meter.x, meter.y, meter.z]).sub(state.houseShells[i].base).applyQuaternion(state.houseShells[i].q.clone().invert());
  k.pipe(state.M.blue, meterLocal.toArray(), [0, -1.0, 6], .065);
  k.pipe(state.M.blue, [0, -1.0, 6], [0, .35, 6], .065);
  k.pipe(state.M.blue, [0, .35, 6], [w / 2 + .35, .35, 2], .065);
  k.add('ring', state.M.amber, [w / 2 + .4, .4, 2], [.18, .18, .18], [0, Math.PI / 2, 0]);
  // Underfloor wet services are connected to the common street riser.
  const hot = material('copper', 0xa36b4b, {
    metalness: .78,
    roughness: .36
  });
  k.add('cyl', state.M.white, [w * .36, 1.1, -d * .36], [.5, 2.1, .5]);
  k.pipe(state.M.blue, [0, -.8, 6], [w * .36, -.8, -d * .36], .04);
  k.pipe(state.M.blue, [w * .36, -.8, -d * .36], [w * .36, .25, -d * .36], .04);
  for (const end of [[w / 2 - 1.25, .95, 2.4], [w * .16, .45, -d * .26], [w * .31, .4, -d * .37], [w * .4, 1.8, -d * .12]]) {
    k.pipe(state.M.blue, [0, -.8, 6], [end[0], -.8, end[2]], .025);
    k.pipe(state.M.blue, [end[0], -.8, end[2]], end, .025);
    k.pipe(state.M.steel, [end[0], -.55, end[2]], [0, -1, 6], .055);
    k.pipe(state.M.steel, end, [end[0], -.55, end[2]], .055);
  }
  k.pipe(hot, [w * .36, 2.1, -d * .36], [w / 2 - 1.25, 2.1, 2.4], .023);
  k.pipe(hot, [w / 2 - 1.25, 2.1, 2.4], [w / 2 - 1.25, .95, 2.4], .023);
  // Interior floor plates and stairs. Upper plates remain visible with the translucent roof.
  for (let level = 0; level < floors; level++) {
    const y = level * floorH;
    const f = level === 0 ? interiorKit : r;
    const fk = f;
    if (level === 0) fk.box(state.M.wood, 0, y + .02, 0, w - .35, .12, d - .35);else {
      const left = -w / 2 + .18,
        right = w / 2 - .18,
        back = -d / 2 + .18,
        front = d / 2 - .18;
      fk.box(state.M.wood, (left - .1) / 2, y + .02, 0, -.1 - left, .12, d - .35);
      fk.box(state.M.wood, (1.4 + right) / 2, y + .02, 0, right - 1.4, .12, d - .35);
      fk.box(state.M.wood, .65, y + .02, (back - d * .4 - .25) / 2, 1.5, .12, -d * .4 - .25 - back);
      const stairEnd = -d * .4 + 5.4;
      fk.box(state.M.wood, .65, y + .02, (stairEnd + front) / 2, 1.5, .12, front - stairEnd);
    }
    // Bedroom/bath partitions leave full-height door openings.
    f.box(state.M.panel, -w * .05, y + 1.35, -d * .25, .12, 2.7, d * .46);
    f.box(state.M.panel, -w * .3, y + 1.35, -.6, w * .26, 2.7, .12);
    f.box(state.M.trim, -w * .07, y + 2.5, -.6, 1.1, .28, .12);
    // Bed, separate mattress, blanket, pillow and frame.
    const bx = -w * .29,
      bz = -d * .28;
    f.box(state.M.wood, bx, y + .3, bz, 2.4, .45, 3.8);
    f.box(state.M.white, bx, y + .65, bz, 2.3, .35, 3.7);
    f.box(state.M.fabric, bx, y + .87, bz + .4, 2.32, .12, 2.7, null, accent);
    f.box(state.M.white, bx, y + .96, bz - 1.3, 1.6, .24, .65);
    f.box(state.M.wood, bx, y + .8, bz - 1.95, 2.6, 1.5, .16);
    f.box(state.M.wood, bx + 1.85, y + .5, bz - 1.4, .8, .9, .8);
    f.add('cyl', state.M.glow, [bx + 1.85, y + 1.25, bz - 1.4], [.28, .35, .28]);
    if (type === 0) {
      for (let bunk = 0; bunk < 1; bunk++) {
        const zz = -d * .28 + bunk * 4.6,
          xx = -w * .29;
        f.box(state.M.steel, xx, y + 2.25, zz, 2.4, .12, 3.8);
        f.box(state.M.white, xx, y + 2.47, zz, 2.3, .3, 3.7);
        for (const dx of [-1.17, 1.17]) for (const dz of [-1.82, 1.82]) f.box(state.M.steel, xx + dx, y + 1.35, zz + dz, .08, 2.7, .08);
        if (bunk === 1) {
          f.box(state.M.steel, xx, y + .35, zz, 2.4, .12, 3.8);
          f.box(state.M.white, xx, y + .57, zz, 2.3, .3, 3.7);
        }
        for (let rung = 0; rung < 6; rung++) f.box(state.M.trim, xx + 1.22, y + .3 + rung * .34, zz - .6, .1, .05, .8);
      }
    }
    // Sofa with actual cushions, arms and back; coffee table and rug.
    const sx = -w * .27,
      sz = d * .24;
    f.box(state.M.fabric, sx, y + .48, sz, 3.8, .72, 1.5);
    f.box(state.M.fabric, sx, y + 1.12, sz - .67, 3.9, 1.1, .32);
    for (const dx of [-1.85, 1.85]) f.box(state.M.fabric, sx + dx, y + .95, sz, .35, .7, 1.6);
    for (let j = 0; j < 3; j++) f.box(state.M.white, sx - 1.2 + j * 1.2, y + .91, sz + .1, 1.12, .19, 1.2, null, accent);
    f.box(state.M.fabric, sx, y + .1, sz + 2.1, 4.4, .04, 2.6);
    f.box(state.M.wood, sx, y + .67, sz + 2.1, 2.4, .16, 1.1);
    for (const dx of [-1, 1]) for (const dz of [-.4, .4]) f.box(state.M.steel, sx + dx, y + .36, sz + 2.1 + dz, .08, .6, .08);
    // TV on cabinet, speakers, books.
    f.box(state.M.wood, sx, y + .5, d / 2 - .65, 3.8, .9, .8);
    f.box(state.M.dark, sx, y + 1.85, d / 2 - .67, 2.7, 1.55, .15);
    f.box(state.M.screen, sx, y + 1.86, d / 2 - .77, 2.52, 1.34, .025);
    for (let j = 0; j < 5; j++) f.box(state.M.fabric, sx - 1.5 + j * .18, y + 1.1, d / 2 - .55, .13, .32 + .06 * (j % 3), .3, null, [0x70594a, 0x7d8959, 0x536b78][j % 3]);
    // Kitchen counter, four burners, oven glazing, sink bowl/rim and tap.
    const kx = w / 2 - 1.25;
    f.box(state.M.white, kx, y + .52, 1, 1.8, 1.02, 5.3);
    f.box(state.M.dark, kx, y + 1.1, 1, 1.95, .14, 5.5);
    for (let j = 0; j < 3; j++) {
      f.box(state.M.panel, kx - 0.93, y + .55, -.7 + j * 1.6, .04, .8, 1.42);
      f.box(state.M.steel, kx - .98, y + .82, -.7 + j * 1.6, .06, .04, .4);
    }
    for (const xx of [-.4, .4]) for (const zz of [-.4, .4]) f.add('ring', state.M.trim, [kx + xx, y + 1.2, -.7 + zz], [.23, .23, .23], [Math.PI / 2, 0, 0]);
    f.box(state.M.glass, kx - .97, y + .52, -.7, .02, .57, 1.02);
    f.box(state.M.trim, kx, y + 1.2, 2.4, 1.15, .04, .96);
    f.box(state.M.dark, kx, y + 1.23, 2.4, .95, .04, .76);
    f.pipe(state.M.trim, [kx + .4, y + 1.2, 2.9], [kx + .4, y + 1.7, 2.9], .04);
    f.pipe(state.M.trim, [kx + .4, y + 1.7, 2.9], [kx + .4, y + 1.7, 2.5], .04);
    // Refrigerator, front-loading laundry, bathroom sanitary fixtures.
    f.box(state.M.white, kx, y + 1.12, -d / 2 + 1.1, 1.8, 2.25, 1.8);
    f.box(state.M.steel, kx - .94, y + 1.3, -d / 2 + 1.7, .06, .7, .07);
    f.box(state.M.white, w * .16, y + .63, -d * .26, 1.3, 1.25, 1.3);
    f.add('ring', state.M.steel, [w * .16, y + .65, -d * .26 + .67], [.43, .43, .43]);
    f.add('cyl', state.M.glass, [w * .16, y + .65, -d * .26 + .69], [.35, .03, .35], [Math.PI / 2, 0, 0]);
    f.add('ball', state.M.white, [w * .31, y + .4, -d * .37], [.48, .33, .65]);
    f.box(state.M.white, w * .31, y + .8, -d * .42, .8, 1.1, .32);
    f.box(state.M.white, w * .3, y + .1, -d * .1, 1.6, .18, 1.6);
    f.box(state.M.glass, w * .25, y + 1.2, -d * .1, .04, 2.3, 1.6);
    f.pipe(state.M.trim, [w * .4, y + .3, -d * .12], [w * .4, y + 2.3, -d * .12], .035);
    // Dining table and four chairs, kettle and plates.
    f.box(state.M.wood, w * .14, y + .92, d * .21, 2.4, .15, 1.8);
    for (const dx of [-.9, .9]) for (const dz of [-.6, .6]) f.box(state.M.steel, w * .14 + dx, y + .47, d * .21 + dz, .08, .85, .08);
    for (const dz of [-1.25, 1.25]) for (const dx of [-.7, .7]) {
      f.box(state.M.wood, w * .14 + dx, y + .52, d * .21 + dz, .65, .12, .6);
      f.box(state.M.wood, w * .14 + dx, y + .98, d * .21 + dz + Math.sign(dz) * .25, .65, .9, .08);
    }
    for (const dx of [-.6, .6]) f.add('cyl', state.M.white, [w * .14 + dx, y + 1.02, d * .21], [.23, .025, .23]);
  }
  if (floors > 1) {
    for (let j = 0; j < 16; j++) interiorKit.box(state.M.steel, .65, j * floorH / 16 + .1, -d * .4 + j * .32, 1.3, .12, .34);
  }
  k.finish();
  r.finish();
  interiorKit.finish();
  g.userData.house = i;
  g.traverse(o => o.userData.house = i);
  const label = textSprite(`HH / ${String(i + 1).padStart(3, '0')}   ${['CREW', 'HAB', 'THERMAL', 'ADMIN'][type]}`, '#ddd5b8', 24);
  label.position.set(doorX, 3.4, d / 2 + .2);
  label.scale.set(4.4, .65, 1);
  shell.add(label);
  const litMaterials = [state.M.glow, state.M.screen].map(m => m.clone());
  g.traverse(o => {
    if (o.material === state.M.glow) o.material = litMaterials[0];else if (o.material === state.M.screen) o.material = litMaterials[1];
  });
  return {
    g,
    shell,
    roof,
    inside,
    i,
    litMaterials
  };
}
