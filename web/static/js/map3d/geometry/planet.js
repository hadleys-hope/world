/** geometry/planet: procedural colony viewer. */
import { state } from "../state.js";
import { coastHeight } from "../models/ocean.js";
import * as THREE from "three";

export function terrainH(x, y) {
  const r = Math.hypot(x, y);
  const T = state.TER;
  let h;
  if (r < T.hub) h = 8.0;
  else if (r < T.row0 - 30)
    h = 8.0 - 3.0 * state.sstep(T.hub, T.row0 - 30, r); // hub on a mound, sloping to the first street
  else if (r < T.ring) {
    const k = Math.floor((r - (T.row0 - 30)) / T.step);
    const f = (r - (T.row0 - 30)) / T.step - k;
    h = 5.0 + 3.4 * Math.min(T.rows, k + state.sstep(0.62, 1.0, f));
  } // terraces, one per row of houses
  else if (r < T.wall + 20) h = 5.0 + T.rows * 3.4;
  else
    h = (5.0 + T.rows * 3.4) * (1 - state.sstep(T.wall + 20, T.wall + 260, r)); // outside the wall the ground eases down
  let natural =
    22 +
    24 * Math.sin(x * 0.0018) * Math.cos(y * 0.0024) +
    14 * Math.sin(x * 0.004 + y * 0.001);
  for (const [px, py, height, width] of [
    [1250, 850, 180, 280],
    [-450, -1350, 145, 360],
    [-1640, 980, 220, 310],
    [450, 1650, 190, 330],
  ])
    natural +=
      height * Math.exp(-((x - px) ** 2 + (y - py) ** 2) / (width * width));
  return coastHeight(
    x,
    y,
    h +
      state.sstep(T.wall + 20, T.wall + 320, r) * natural +
      0.5 * Math.sin(x * 0.031) * Math.cos(y * 0.027),
  );
}

export function farSurface(x, y) {
  const n = xyNormal(x, y),
    p = Math.atan2(n.z, n.x),
    a = Math.asin(n.y);
  return (
    12 +
    48 * Math.sin(p * 4 + Math.sin(a * 3)) * Math.cos(a * 7) +
    20 * Math.sin(p * 17 + a * 11) +
    8 * Math.sin(p * 53 - a * 37)
  );
}

export function surfaceHeight(x, y) {
  const d = Math.hypot(x, y);
  return d < 4350
    ? terrainH(x, y)
    : THREE.MathUtils.lerp(
        terrainH(x, y),
        farSurface(x, y),
        state.sstep(4350, 4700, d),
      );
}

export function sph(x, y, h = 0) {
  const d = Math.hypot(x, y),
    th = d / state.RP,
    ph = Math.atan2(y, x),
    r = state.RP + h + terrainH(x, y);
  return new THREE.Vector3(
    r * Math.sin(th) * Math.cos(ph),
    r * Math.cos(th),
    r * Math.sin(th) * Math.sin(ph),
  );
}

export function quatAt(x, y, yaw = 0) {
  const n = sph(x, y).normalize();
  const q = new THREE.Quaternion().setFromUnitVectors(state.UP, n);
  if (yaw) q.multiply(new THREE.Quaternion().setFromAxisAngle(state.UP, yaw));
  return q;
}

export function polar(a, r) {
  const t = (a * Math.PI) / 180;
  return [r * Math.cos(t), r * Math.sin(t)];
}

export function subdiv(pts, step = 14) {
  const out = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i],
      [x1, y1] = pts[i + 1];
    const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / step));
    for (let k = 0; k < n; k++)
      out.push([x0 + ((x1 - x0) * k) / n, y0 + ((y1 - y0) * k) / n]);
  }
  out.push(pts[pts.length - 1]);
  return out;
}

export function arcPts(a0, a1, r, n = 24) {
  const out = [];
  for (let i = 0; i <= n; i++) out.push(polar(a0 + ((a1 - a0) * i) / n, r));
  return out;
}

export function offsetArc(a0, a1, r, off, n = 24) {
  return arcPts(a0, a1, r + off, n);
}

export function initialize() {
  state.RP = 4000;
  state.UP = new THREE.Vector3(0, 1, 0);
  state.TER = { hub: 140, row0: 300, step: 60, rows: 5, ring: 640, wall: 690 };
  state.sstep = (e0, e1, t) => {
    t = Math.min(1, Math.max(0, (t - e0) / (e1 - e0)));
    return t * t * (3 - 2 * t);
  };
}

export function xyNormal(x, y) {
  const a = Math.hypot(x, y) / state.RP,
    p = Math.atan2(y, x);
  return new THREE.Vector3(
    Math.sin(a) * Math.cos(p),
    Math.cos(a),
    Math.sin(a) * Math.sin(p),
  );
}

export function normalXY(n) {
  const a = Math.acos(THREE.MathUtils.clamp(n.y, -1, 1)) * state.RP,
    p = Math.atan2(n.z, n.x);
  return [Math.cos(p) * a, Math.sin(p) * a];
}
