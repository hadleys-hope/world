/** models/drainage: procedural colony viewer. */
import { state } from '../state.js';
import { pointsLayer } from '../geometry/objects.js';
import { quatAt, sph, terrainH } from '../geometry/planet.js';
import { Kit } from './kit.js';
import { material } from './materials.js';
import { makePotable } from './potable.js';
import * as THREE from 'three';
export function utilityPoint(p) {
  return sph(p[0], p[1], p[2] - terrainH(p[0], p[1]));
}
export function buildUtilities() {
  const U = state.G.utilities;
  const kit = new Kit(state.utilityGroup),
    groundKit = new Kit(state.streetDetail),
    potable = new Kit(state.potableGroup);
  const um = (name, color) => material(name, color, {
    metalness: .45,
    roughness: .4,
    depthTest: false,
    transparent: true,
    opacity: .87
  });
  const waterMat = um('potable', 0x4b9bb9),
    sewerMat = um('sewer', 0xb99865),
    stormMat = um('storm', 0x71988b),
    jointMat = um('coupling', 0xabb8b9);
  function run(points, r, mat, tag) {
    const pts = [];
    for (let j = 0; j < points.length - 1; j++) {
      const a = points[j],
        b = points[j + 1],
        len = Math.hypot(b[0] - a[0], b[1] - a[1]),
        steps = Math.max(1, Math.ceil(len / 12));
      for (let t = 0; t < steps; t++) {
        const f = t / steps;
        pts.push(utilityPoint(a.map((v, k) => v + (b[k] - v) * f)));
      }
    }
    pts.push(utilityPoint(points.at(-1)));
    for (const p of points.slice(1, -1)) kit.add("ball", mat, utilityPoint(p).toArray(), [r, r, r], null, null, tag);
    for (let j = 0; j < pts.length - 1; j++) {
      kit.pipe(mat, pts[j].toArray(), pts[j + 1].toArray(), r, tag);
      if (j % 3 === 0) {
        const delta = pts[j + 1].clone().sub(pts[j]).normalize();
        kit.pipe(jointMat, pts[j].clone().addScaledVector(delta, -.13).toArray(), pts[j].clone().addScaledVector(delta, .13).toArray(), r * 1.4, tag);
      }
    }
    pts.cumulative = [0];
    for (let j = 1; j < pts.length; j++) pts.cumulative.push(pts.cumulative[j - 1] + pts[j - 1].distanceTo(pts[j]));
    return pts;
  }
  state.utilityPaths = U.links.map(e => makePotable(e.points, e.diameter_m / 2, {
    system: 'water',
    id: e.id
  }, potable));
  makePotable(U.plant_feed, .34, {
    system: 'feed',
    id: -1
  }, potable);
  for (const system of U.drainage) {
    system.links.forEach((e, i) => run(e.points, e.diameter_m / 2, system.name === 'sanitary' ? sewerMat : stormMat, {
      system: system.name,
      id: i
    }));
    run(system.rising_main, .22, system.name === 'sanitary' ? sewerMat : stormMat, {
      system: system.name,
      id: -1
    });
    for (let j = 0; j < system.nodes.length; j++) {
      const n = system.nodes[j];
      if (n.kind === 'pump' || n.kind === 'tank') continue;
      const cover = sph(n.x, n.y, 1.28),
        bottom = utilityPoint([n.x, n.y, n.z]);
      if (n.kind === 'tee' && j % 3 === 0) {
        const q = quatAt(n.x, n.y);
        groundKit.add('cyl', state.M.steel, cover.toArray(), [.64, .11, .64], q);
        groundKit.add('ring', state.M.trim, cover.clone().addScaledVector(cover.clone().normalize(), .07).toArray(), [.51, .51, .51], q.clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2)));
        kit.pipe(jointMat, bottom.toArray(), cover.toArray(), .54, {
          system: system.name,
          id: -1
        });
        // Ladder rungs in inspection shafts.
        const len = bottom.distanceTo(cover),
          v = cover.clone().sub(bottom).normalize();
        for (let k = .5; k < len; k += .65) {
          const p = bottom.clone().addScaledVector(v, k);
          kit.pipe(stormMat, p.clone().add(new THREE.Vector3(-.23, 0, 0)).toArray(), p.clone().add(new THREE.Vector3(.23, 0, 0)).toArray(), .035);
        }
      }
      if (n.kind === 'meter') {
        // House foul and rain stacks terminate at wet core / downpipe manifold.
        const house = n.house,
          a = state.G.houses.angle[house] * Math.PI / 180;
        const entry = state.houseShells[house].base.clone().add(new THREE.Vector3(0, -1, 6).applyQuaternion(state.houseShells[house].q));
        kit.pipe(system.name === 'storm' ? stormMat : sewerMat, bottom.toArray(), entry.toArray(), .09, {
          system: system.name,
          id: -1
        });
      }
      if (system.name === 'storm' && n.kind === 'tee') {
        const rr = Math.hypot(n.x, n.y),
          a = Math.atan2(n.y, n.x),
          x = n.x + Math.cos(a) * 3.6,
          y = n.y + Math.sin(a) * 3.6,
          q = quatAt(x, y, -a);
        const top = sph(x, y, 1.14);
        groundKit.add('box', state.M.dark, top.toArray(), [1.1, .12, .65], q);
        for (let k = 0; k < 7; k++) {
          const p = top.clone().add(new THREE.Vector3((k - 3) * .145, .08, 0).applyQuaternion(q));
          groundKit.add('box', state.M.trim, p.toArray(), [.055, .055, .63], q);
        }
        kit.pipe(stormMat, top.toArray(), bottom.toArray(), .14, {
          system: 'storm',
          id: -1
        });
      }
    }
  }
  for (const n of U.nodes) {
    if (n.kind === 'tee') {
      const p = utilityPoint([n.x, n.y, n.z]);
      potable.add('ball', state.M.trim, p.toArray(), [.145, .145, .145]);
    }
    if (n.kind === 'isolation' || n.kind === 'meter') {
      const p = utilityPoint([n.x, n.y, n.z]);
      potable.add('ball', state.M.trim, p.toArray(), [.23, .23, .23]);
      const q = quatAt(n.x, n.y);
      const top = p.clone().addScaledVector(p.clone().normalize(), .52);
      potable.pipe(state.M.trim, p.toArray(), top.toArray(), .045);
      potable.add('ring', state.M.amber, top.toArray(), [.28, .28, .28], q.clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2)));
    }
  }
  state.potableBatches = potable.finish();
  for (const m of state.potableBatches) if (m.material === state.MAT['pipe-ice']) {
    m.userData.iceOriginal = m.instanceMatrix.array.slice();
    m.instanceMatrix.array.fill(0);
    m.instanceMatrix.needsUpdate = true;
  }
  state.utilityBatches = kit.finish();
  groundKit.finish();
  state.utilityGroup.renderOrder = 30;
  state.utilityBatches.forEach(m => {
    m.renderOrder = 30;
    m.castShadow = false;
  });
  state.utilityDrops = pointsLayer(U.links.length * 5, state.TEX.dot, 0xc8f6ff, .38, true);
  state.utilityDrops.material.depthTest = true;
  state.utilityDrops.renderOrder = 35;
  state.utilityGroup.visible = !!state.layers.underground;
  state.utilityDrops.visible = state.layers.water;
}
export function updateUtilityFlow(t) {
  if (!state.utilityDrops || !state.S?.hydraulics) return;
  const delta = state.utilityLastTime ? Math.min(.25, t - state.utilityLastTime) : 0;
  state.utilityLastTime = t;
  state.utilityTime += delta * state.clock.speed * 60;
  if (!state.layers.water) return;
  const a = state.utilityDrops.geometry.attributes.position;
  const h = state.S.hydraulics;
  for (let particle = 0; particle < state.utilityPaths.length * 5; particle++) {
    const i = Math.floor(particle / 5);
    const pts = state.utilityPaths[i],
      v = h.velocity_m_s[i],
      L = state.G.utilities.links[i].length_m;
    if (!state.layers.water || Math.abs(v) < 1e-7) {
      a.setXYZ(particle, 0, -99999, 0);
      continue;
    }
    const u = ((state.utilityTime * v / L + i * .381 + particle % 5 / 5) % 1 + 1) % 1;
    // Interpolate by actual segment length, never through a smoothed corner.
    const lengths = pts.cumulative,
      dist = u * lengths.at(-1);
    let j = 1;
    while (j < lengths.length - 1 && dist > lengths[j]) j++;
    const p = pts[j - 1].clone().lerp(pts[j], (dist - lengths[j - 1]) / Math.max(lengths[j] - lengths[j - 1], 1e-8));
    a.setXYZ(particle, p.x, p.y, p.z);
  }
  a.needsUpdate = true;
}
