/** geometry/objects: procedural colony viewer. */
import { state } from '../state.js';
import { quatAt, sph } from './planet.js';
import * as THREE from 'three';
export function box(x, y, w, h, d, color, edge, yaw) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), new THREE.MeshStandardMaterial({
    color,
    roughness: .8
  }));
  m.position.copy(sph(x, y, h / 2));
  m.quaternion.copy(quatAt(x, y, yaw === undefined ? -Math.atan2(y, x) : yaw));
  state.world.add(m);
  if (edge) {
    m.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry), new THREE.LineBasicMaterial({
      color: edge
    })));
  }
  return m;
}
export function cyl(x, y, r, h, color, opts = {}) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 18), new THREE.MeshStandardMaterial({
    color,
    roughness: .7,
    ...opts
  }));
  m.position.copy(sph(x, y, h / 2));
  m.quaternion.copy(quatAt(x, y));
  state.world.add(m);
  return m;
}
export function localGroup(x, y, h, yaw) {
  const g = new THREE.Group();
  g.position.copy(sph(x, y, h));
  g.quaternion.copy(quatAt(x, y, yaw || 0));
  state.world.add(g);
  return g;
}
export function pointsLayer(n, map, color, size, additive) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(n * 3).fill(-99999), 3));
  const m = new THREE.Points(g, new THREE.PointsMaterial({
    map,
    color,
    size,
    transparent: true,
    depthWrite: false,
    blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    sizeAttenuation: true
  }));
  m.frustumCulled = false;
  state.world.add(m);
  return m;
}
export function setPoints(layer, flatPts, h) {
  const a = layer.geometry.attributes.position;
  const n = a.count;
  for (let i = 0; i < n; i++) {
    if (i < flatPts.length) {
      const p = sph(flatPts[i][0], flatPts[i][1], h);
      a.setXYZ(i, p.x, p.y, p.z);
    } else a.setXYZ(i, 0, -99999, 0);
  }
  a.needsUpdate = true;
}
