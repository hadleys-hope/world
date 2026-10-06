/** Shared low-cost architectural kit. Geometry is shared; no per-window objects or point lights. */
import * as T from "three";
import { instances, lifeMaterial } from "../life.js";
export const palette = {
  concrete: 0xb8b6aa,
  metal: 0x566971,
  dark: 0x27353d,
  brass: 0xc99b58,
  glass: 0x518594,
  wood: 0x826142,
  white: 0xe7e5d5,
  green: 0x497552,
};
export function merge(parts) {
  const p = [],
    n = [],
    c = [],
    facade = [];
  for (const [source, color, surface = 0] of parts) {
    const g = source.index ? source.toNonIndexed() : source;
    const a = g.attributes.position,
      b = g.attributes.normal,
      col = new T.Color(color);
    for (let i = 0; i < a.count; i++) {
      p.push(a.getX(i), a.getY(i), a.getZ(i));
      n.push(b.getX(i), b.getY(i), b.getZ(i));
      const own = g.attributes.aCol;
      if (color === null && own) c.push(own.getX(i), own.getY(i), own.getZ(i));
      else c.push(col.r, col.g, col.b);
      facade.push(surface);
    }
    if (g !== source) g.dispose();
    source.dispose();
  }
  const g = new T.BufferGeometry();
  g.setAttribute("position", new T.Float32BufferAttribute(p, 3));
  g.setAttribute("normal", new T.Float32BufferAttribute(n, 3));
  g.setAttribute("aCol", new T.Float32BufferAttribute(c, 3));
  g.setAttribute("aFacade", new T.Float32BufferAttribute(facade, 1));
  g.computeBoundingSphere();
  return g;
}
export class Model {
  constructor() {
    this.parts = [];
  }
  box(x, y, z, w, h, d, c = palette.concrete, facade = 0) {
    this.parts.push([new T.BoxGeometry(w, h, d).translate(x, y, z), c, facade]);
    return this;
  }
  cyl(x, y, z, r, h, c = palette.metal, top = r, segments = 10) {
    this.parts.push([
      new T.CylinderGeometry(top, r, h, segments).translate(x, y, z),
      c,
    ]);
    return this;
  }
  beam(a, b, r = 0.1, c = palette.metal) {
    const A = new T.Vector3(...a),
      B = new T.Vector3(...b),
      v = B.clone().sub(A);
    const g = new T.CylinderGeometry(r, r, v.length(), 6);
    g.applyQuaternion(
      new T.Quaternion().setFromUnitVectors(
        new T.Vector3(0, 1, 0),
        v.normalize(),
      ),
    );
    g.translate(...A.add(B).multiplyScalar(0.5).toArray());
    this.parts.push([g, c]);
    return this;
  }
  finish() {
    return merge(this.parts);
  }
}
export function roofPlant() {
  const m = new Model();
  m.box(0, 0.45, 0, 2.3, 0.9, 1.6, palette.metal).box(
    0,
    0.94,
    0,
    2.1,
    0.08,
    1.4,
    palette.dark,
  );
  for (const x of [-0.65, 0.65]) {
    m.cyl(x, 1.01, 0, 0.46, 0.12, palette.dark);
    for (let k = 0; k < 3; k++) {
      const a = (k * Math.PI) / 3;
      m.beam(
        [x - Math.cos(a) * 0.4, 1.08, -Math.sin(a) * 0.4],
        [x + Math.cos(a) * 0.4, 1.08, Math.sin(a) * 0.4],
        0.035,
        palette.white,
      );
    }
  }
  m.box(2, 0.25, 0, 2, 0.45, 0.55, palette.metal)
    .cyl(3, 1, 0, 0.3, 1.7)
    .cyl(3, 1.9, 0, 0.48, 0.15);
  return m.finish();
}
export function pole() {
  const m = new Model();
  m.cyl(0, 4.3, 0, 0.15, 8.6)
    .box(0, 7.7, 0, 3, 0.15, 0.2)
    .box(0.22, 2.1, 0, 0.45, 0.7, 0.4, palette.dark);
  for (let k = -1; k <= 1; k++) {
    m.cyl(k * 1.1, 7.92, 0, 0.13, 0.3, palette.white, 0.1, 6);
    m.box(
      0.46,
      2.15 + k * 0.14,
      0.12,
      0.03,
      0.08,
      0.08,
      k === 0 ? 0x55ef9d : 0xdabb67,
    );
  }
  m.beam([0, 7.4, 0], [0, 8.1, 2.1], 0.06)
    .box(0, 8.05, 2.2, 0.55, 0.12, 1.1, palette.brass)
    .box(0, 7.98, 2.2, 0.45, 0.03, 0.9, 0xffe2a2);
  return m.finish();
}
export function bench() {
  const m = new Model();
  for (let k = 0; k < 4; k++)
    m.box(0, 0.52, k * 0.15, 1.9, 0.07, 0.12, palette.wood);
  for (let k = 0; k < 3; k++)
    m.box(0, 0.72 + k * 0.14, -0.12, 1.9, 0.1, 0.08, palette.wood);
  for (const x of [-0.7, 0.7])
    m.box(x, 0.25, 0.2, 0.09, 0.5, 0.5, palette.dark);
  return m.finish();
}
export function bin() {
  return new Model()
    .cyl(0, 0.48, 0, 0.3, 0.9, palette.dark)
    .cyl(0, 0.98, 0, 0.35, 0.1, palette.metal)
    .box(0, 0.8, 0.29, 0.25, 0.14, 0.04, palette.brass)
    .finish();
}
export function antenna() {
  const m = new Model();
  m.cyl(0, 3, 0, 0.09, 6);
  for (let k = 0; k < 3; k++) {
    const a = (k * 2 * Math.PI) / 3;
    m.box(
      Math.cos(a) * 0.55,
      4.6,
      Math.sin(a) * 0.55,
      0.35,
      1.8,
      0.3,
      palette.white,
    );
    m.beam([0, 2, 0], [Math.cos(a) * 2, 0, Math.sin(a) * 2], 0.035);
  }
  return m.finish();
}
export function car(tanker = false) {
  const m = new Model();
  m.box(0, 0.8, 0, 2.05, 0.65, 4.6, tanker ? 0xbebba2 : 0x537985)
    .box(0, 1.45, 0.5, 1.85, 0.85, 2.1, palette.glass)
    .box(0, 1.9, 0.5, 1.9, 0.12, 2.2, palette.metal);
  if (tanker) {
    m.box(0, 1.6, -1.1, 1.8, 1.4, 2.3, palette.white);
    for (let k = 0; k < 3; k++)
      m.box(0, 1.7, -1.9 + k * 0.7, 1.88, 0.15, 0.1, palette.metal);
  }
  for (const x of [-1.04, 1.04])
    for (const z of [-1.4, 1.4]) {
      const g = new T.CylinderGeometry(0.4, 0.4, 0.25, 10)
        .rotateZ(Math.PI / 2)
        .translate(x, 0.45, z);
      m.parts.push([g, 0x171d22]);
      m.box(x * 1.04, 0.45, z, 0.05, 0.28, 0.28, palette.metal);
    }
  for (const x of [-0.65, 0.65])
    m.box(x, 0.87, 2.34, 0.4, 0.16, 0.08, 0xffe3ac);
  return m.finish();
}
/** Spherical batches grouped by material/prototype; persistent instance IDs for picking. */
export function planYaw(point, x, y, yaw = 0, h = 0) {
  const p = point(x, y, h),
    n = p.clone().normalize(),
    q = new T.Quaternion().setFromUnitVectors(new T.Vector3(0, 1, 0), n);
  const east = point(x + 1, y, h)
    .sub(p)
    .normalize()
    .applyQuaternion(q.invert());
  return Math.atan2(-east.z, east.x) + yaw;
}
export class Batches {
  constructor(body, R, point, env) {
    this.body = body;
    this.R = R;
    this.point = point;
    this.env = env;
    this.groups = new Map();
  }
  add(key, geometry, x, z, h = 0, s = 1, yaw = 0, sy = 1, tint = [1, 1, 1]) {
    let b = this.groups.get(key);
    if (!b) {
      b = {
        geometry: typeof geometry === "function" ? geometry() : geometry,
        items: [],
      };
      this.groups.set(key, b);
    }
    const p = this.point(x, z, h);
    b.items.push({
      n: p.clone().normalize().toArray(),
      h: p.length() - this.R,
      s,
      sy,
      yaw: planYaw(this.point, x, z, yaw, h),
      tint,
    });
  }
  finish({ distance = 0, materialFor = () => null } = {}) {
    const root = new T.Group();
    for (const [key, b] of this.groups) {
      const m = instances(
        b.geometry,
        materialFor(key) ||
          lifeMaterial(this.env, {
            indoor: 1,
            glow: key === "lamp" ? 0.12 : 0,
          }),
        b.items,
        this.R,
      );
      m.name = key;
      root.add(m);
    }
    this.body.add(root);
    if (distance) {
      const sphere = new T.Box3()
        .setFromObject(root)
        .getBoundingSphere(new T.Sphere());
      root.userData.update = (cam) =>
        (root.visible =
          cam.distanceTo(sphere.center) < sphere.radius + distance);
    }
    return root;
  }
}
