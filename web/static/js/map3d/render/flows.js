/** render/flows: procedural colony viewer. */
import { state } from '../state.js';
import { sph, subdiv } from '../geometry/planet.js';
import * as THREE from 'three';
export function flowTube(pts3, radius, len) {
  const t = state.pipeTex.clone();
  t.needsUpdate = true;
  t.repeat.set(Math.max(1, len / 40), 1);
  const mat = new THREE.MeshStandardMaterial({
    map: t,
    roughness: .4,
    metalness: .3
  });
  mat.userData = {
    rate: 0,
    tex: t
  };
  state.pipeMats.push(mat);
  const g = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts3), Math.max(8, pts3.length * 3), radius, 8, false);
  const m = new THREE.Mesh(g, mat);
  m.castShadow = true;
  state.world.add(m);
  return m;
}
export function polyLen(pts3) {
  let L = 0;
  for (let i = 1; i < pts3.length; i++) L += pts3[i].distanceTo(pts3[i - 1]);
  return L;
}
export function flat3(flat, h) {
  return subdiv(flat, 20).map(p => sph(p[0], p[1], h));
}
export function catenary(a3, b3, sag) {
  const out = [];
  const mid = a3.clone().add(b3).multiplyScalar(0.5);
  const n = mid.clone().normalize();
  for (let i = 0; i <= 8; i++) {
    const t = i / 8;
    const p = a3.clone().lerp(b3, t);
    p.addScaledVector(n, -sag * 4 * t * (1 - t));
    out.push(p);
  }
  return out;
}
export class LineLayer {
  // many 3D polylines, colour per polyline
  constructor(polylines3, baseColor) {
    this.ranges = [];
    const pos = [],
      col = [];
    const c = new THREE.Color(baseColor);
    for (const pts of polylines3) {
      const start = pos.length / 3;
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i],
          b = pts[i + 1];
        pos.push(a.x, a.y, a.z, b.x, b.y, b.z);
        col.push(c.r, c.g, c.b, c.r, c.g, c.b);
      }
      this.ranges.push([start, pos.length / 3]);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    this.mesh = new THREE.LineSegments(g, new THREE.LineBasicMaterial({
      vertexColors: true
    }));
    this.polylines = polylines3;
    this.mesh.frustumCulled = false;
    state.world.add(this.mesh);
  }
  setColor(i, color) {
    const c = new THREE.Color(color),
      a = this.mesh.geometry.attributes.color;
    const [s, e] = this.ranges[i];
    for (let k = s; k < e; k++) a.setXYZ(k, c.r, c.g, c.b);
    a.needsUpdate = true;
  }
}
export class FlowLayer {
  // dots moving along 3D polylines
  constructor(polylines3, color, size, perLine = 3, speed = 40) {
    this.pls = polylines3.map(pts => {
      const cum = [0];
      for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + pts[i].distanceTo(pts[i - 1]));
      return {
        pts,
        cum,
        len: cum[cum.length - 1]
      };
    });
    this.active = new Array(polylines3.length).fill(false);
    this.per = perLine;
    this.speed = speed;
    const n = polylines3.length * perLine;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(n * 3), 3));
    this.mesh = new THREE.Points(g, new THREE.PointsMaterial({
      color,
      size,
      map: state.TEX.dot,
      transparent: true,
      depthWrite: false,
      sizeAttenuation: true
    }));
    this.mesh.frustumCulled = false;
    state.world.add(this.mesh);
  }
  update(t) {
    const a = this.mesh.geometry.attributes.position;
    let k = 0;
    for (let i = 0; i < this.pls.length; i++) {
      const pl = this.pls[i];
      for (let j = 0; j < this.per; j++) {
        if (!this.active[i] || pl.len === 0) {
          a.setXYZ(k++, 0, -99999, 0);
          continue;
        }
        const u = (t * this.speed / pl.len + j / this.per) % 1;
        const p = sample(pl, u);
        a.setXYZ(k++, p.x, p.y, p.z);
      }
    }
    a.needsUpdate = true;
  }
}
export function sample(pl, u) {
  const d = u * pl.len;
  let i = 1;
  while (i < pl.cum.length - 1 && pl.cum[i] < d) i++;
  const t = (d - pl.cum[i - 1]) / (pl.cum[i] - pl.cum[i - 1] || 1);
  return pl.pts[i - 1].clone().lerp(pl.pts[i], t);
}
export function initialize() {
  state.pipeTex = (() => {
    const c = document.createElement('canvas');
    c.width = 64;
    c.height = 8;
    const x = c.getContext('2d');
    x.fillStyle = '#3a78c8';
    x.fillRect(0, 0, 64, 8);
    x.fillStyle = '#bfe0ff';
    x.fillRect(0, 0, 14, 8);
    x.fillStyle = '#7ab8ff';
    x.fillRect(14, 0, 10, 8);
    const t = new THREE.CanvasTexture(c);
    t.wrapS = THREE.RepeatWrapping;
    t.wrapT = THREE.ClampToEdgeWrapping;
    return t;
  })();
  state.pipeMats = [];
}
