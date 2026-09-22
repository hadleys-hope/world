/** geometry/primitives: procedural colony viewer. */
import { state } from '../state.js';
import { polar, sph, subdiv } from './planet.js';
import { markedRoad } from './roads.js';
import * as THREE from 'three';
export function ribbon(flat, width, h, color, opts = {}) {
  const pts = subdiv(flat, 3),
    cols = Math.max(1, Math.ceil(width / 3)),
    pos = [],
    idx = [],
    uv = [];
  let distance = 0;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i],
      q = pts[Math.min(i + 1, pts.length - 1)],
      o = pts[Math.max(i - 1, 0)],
      dx = q[0] - o[0],
      dy = q[1] - o[1],
      L = Math.hypot(dx, dy) || 1;
    if (i) distance += Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]);
    for (let col = 0; col <= cols; col++) {
      const offset = width * (.5 - col / cols),
        v = sph(p[0] - dy / L * offset, p[1] + dx / L * offset, h);
      pos.push(v.x, v.y, v.z);
      uv.push(col * width / cols / 4, distance / 4);
      if (i < pts.length - 1 && col < cols) {
        const k = i * (cols + 1) + col;
        idx.push(k, k + cols + 1, k + 1, k + 1, k + cols + 1, k + cols + 2);
      }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
    color,
    roughness: 1,
    metalness: 0,
    polygonOffset: false,
    ...opts
  }));
  state.world.add(m);
  return m;
}
export function tube(pts3, radius, color, opts = {}) {
  const g = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts3), Math.max(8, pts3.length * 3), radius, 6, false);
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
    color,
    roughness: .5,
    metalness: .3,
    ...opts
  }));
  state.world.add(m);
  return m;
}
export function cap(radius, h, color, rings = 24, segs = 96, bump = 0, cx = 0, cy = 0) {
  const pos = [],
    idx = [];
  for (let r = 0; r <= rings; r++) {
    const rr = radius * r / rings;
    for (let s = 0; s < segs; s++) {
      const [x, y] = polar(s * 360 / segs, rr);
      const b = bump * (Math.sin(x * 0.07) * Math.cos(y * 0.05) + 0.6 * Math.sin(x * 0.19 + y * 0.13));
      const p = sph(x + cx, y + cy, h + b);
      pos.push(p.x, p.y, p.z);
    }
  }
  for (let r = 0; r < rings; r++) for (let s = 0; s < segs; s++) {
    const a = r * segs + s,
      b = r * segs + (s + 1) % segs,
      c2 = (r + 1) * segs + s,
      d = (r + 1) * segs + (s + 1) % segs;
    idx.push(a, c2, b, b, c2, d);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
    color,
    roughness: 1,
    side: THREE.DoubleSide
  }));
  m.receiveShadow = true;
  state.world.add(m);
  return m;
}
export function road(flat, width, h, color) {
  return markedRoad(flat, width, h);
}
