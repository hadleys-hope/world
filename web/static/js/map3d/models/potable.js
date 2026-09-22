/** models/potable: procedural colony viewer. */
import { state } from '../state.js';
import { terrainH } from '../geometry/planet.js';
import { onRoad } from '../geometry/roads.js';
import { utilityPoint } from './drainage.js';
import { material } from './materials.js';
import * as THREE from 'three';
export function makePotable(points, r, tag, kit) {
  const pts = [],
    flat = [];
  for (let j = 1; j < points.length; j++) {
    const a = points[j - 1],
      b = points[j],
      steps = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 7));
    for (let k = 0; k < steps; k++) {
      const p = a.map((v, c) => v + (b[c] - v) * k / steps);
      flat.push(p);
      pts.push(utilityPoint(p));
    }
  }
  flat.push(points.at(-1));
  pts.push(utilityPoint(points.at(-1)));
  const metal = material('pipe-steel', 0xa1aaa6, {
      metalness: .75,
      roughness: .36
    }),
    glass = material('pipe-sightglass', 0xb2d9db, {
      transparent: true,
      opacity: .18,
      depthWrite: false,
      metalness: .1,
      roughness: .08,
      side: THREE.DoubleSide
    });
  const fluid = material('water-core', 0x3aa8c1, {
    transparent: true,
    opacity: .73,
    depthWrite: false,
    roughness: .16,
    metalness: .05
  });
  if (!state.UNIT.lowerPipe) {
    state.UNIT.lowerPipe = new THREE.CylinderGeometry(1, 1, 1, 10, 1, true, Math.PI / 2, Math.PI);
    state.UNIT.upperPipe = new THREE.CylinderGeometry(1, 1, 1, 10, 1, true, -Math.PI / 2, Math.PI);
  }
  const radius = Math.max(.16, r + .08); // cutaway jacket includes insulation; hydraulic bore stays authoritative
  for (let j = 1; j < pts.length; j++) {
    const a = pts[j - 1],
      b = pts[j],
      dir = b.clone().sub(a).normalize(),
      up = a.clone().normalize();
    up.addScaledVector(dir, -up.dot(dir)).normalize();
    if (up.length() < .1) up.set(0, 0, 1).addScaledVector(dir, -dir.z).normalize();
    const right = dir.clone().cross(up).normalize(),
      q = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(right, dir, up));
    const middle = a.clone().add(b).multiplyScalar(.5),
      len = a.distanceTo(b);
    kit.add('lowerPipe', metal, middle.toArray(), [radius, len, radius], q, null, tag);
    kit.add('upperPipe', glass, middle.toArray(), [radius, len, radius], q, null, tag);
    kit.pipe(fluid, a.toArray(), b.toArray(), radius * .79, tag);
    kit.pipe(material('pipe-ice', 0x98c8ec, {
      roughness: .24,
      metalness: .08
    }), a.toArray(), b.toArray(), radius * 1.17, tag);
    kit.pipe(state.M.trim, a.clone().addScaledVector(dir, -.12).toArray(), a.clone().addScaledVector(dir, .12).toArray(), radius * 1.25, tag);
    for (let bolt = 0; bolt < 6; bolt++) {
      const an = bolt * Math.PI / 3,
        off = right.clone().multiplyScalar(Math.cos(an) * radius * 1.15).addScaledVector(up, Math.sin(an) * radius * 1.15);
      kit.pipe(state.M.dark, a.clone().add(off).addScaledVector(dir, -.15).toArray(), a.clone().add(off).addScaledVector(dir, .15).toArray(), .027, tag);
    }
    if (j % 2 === 1 && !onRoad((flat[j - 1][0] + flat[j][0]) / 2, (flat[j - 1][1] + flat[j][1]) / 2, 1.4)) {
      const worldP = flat[j].map((v, k) => (v + flat[j - 1][k]) / 2);
      // Project support to the same spherical ground, directly below its saddle.
      const n = middle.clone().normalize(),
        ground = middle.clone().addScaledVector(n, -Math.max(1, worldP[2] - terrainH(worldP[0], worldP[1]) - .2));
      kit.pipe(state.M.steel, ground.toArray(), middle.clone().addScaledVector(n, -radius).toArray(), .07);
      kit.add('box', state.M.concrete, ground.toArray(), [.7, .22, .7], new THREE.Quaternion().setFromUnitVectors(state.UP, n));
    }
  }
  for (const point of points) {
    const p = utilityPoint(point);
    kit.add('ball', state.M.trim, p.toArray(), [radius * 1.05, radius * 1.05, radius * 1.05], null, null, tag);
  }
  pts.cumulative = [0];
  for (let j = 1; j < pts.length; j++) pts.cumulative.push(pts.cumulative[j - 1] + pts[j].distanceTo(pts[j - 1]));
  return pts;
}
