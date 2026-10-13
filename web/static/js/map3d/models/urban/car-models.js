/** urban/car-models: the private cars on Klyaksa's streets, a dozen body styles of our own design (no real
 * makes or models): each a side profile extruded to the car's width, with a glasshouse, wheels and lights. */
import * as T from "three";

// [length, width, side profile as (x along the car 0..1, height in m) from the front bumper over the roof]
export const STYLES = [
  ["sports saloon", 4.9, 1.9, [[0, 0.5], [0.04, 0.75], [0.27, 0.86], [0.38, 1.38], [0.66, 1.42], [0.86, 1.05], [1, 0.9], [1, 0.45]]],
  ["compact hatch", 4.2, 1.8, [[0, 0.5], [0.05, 0.8], [0.3, 0.92], [0.42, 1.45], [0.86, 1.46], [0.98, 1.2], [1, 0.5]]],
  ["low coupe", 4.4, 1.85, [[0, 0.45], [0.05, 0.7], [0.33, 0.8], [0.47, 1.28], [0.64, 1.3], [0.92, 0.95], [1, 0.85], [1, 0.42]]],
  ["mid-engine supercar", 4.5, 2.0, [[0, 0.35], [0.06, 0.55], [0.3, 0.75], [0.42, 1.12], [0.56, 1.15], [0.82, 0.95], [1, 0.9], [1, 0.4]]],
  ["hypercar", 4.6, 2.05, [[0, 0.32], [0.08, 0.5], [0.33, 0.7], [0.45, 1.08], [0.58, 1.1], [0.78, 0.98], [0.95, 1.0], [1, 0.95], [1, 0.38]]],
  ["grand tourer", 4.8, 1.95, [[0, 0.45], [0.05, 0.72], [0.35, 0.86], [0.48, 1.3], [0.66, 1.32], [0.9, 1.0], [1, 0.9], [1, 0.45]]],
  ["compact SUV", 4.5, 1.85, [[0, 0.6], [0.05, 0.95], [0.28, 1.05], [0.38, 1.62], [0.88, 1.64], [0.99, 1.35], [1, 0.6]]],
  ["large SUV", 4.95, 2.0, [[0, 0.65], [0.04, 1.05], [0.26, 1.15], [0.35, 1.78], [0.9, 1.8], [1, 1.5], [1, 0.62]]],
  ["pickup", 5.4, 2.0, [[0, 0.7], [0.04, 1.1], [0.24, 1.2], [0.32, 1.85], [0.56, 1.86], [0.6, 1.25], [1, 1.25], [1, 0.7]]],
  ["city car", 3.6, 1.65, [[0, 0.5], [0.06, 0.8], [0.24, 0.9], [0.36, 1.5], [0.9, 1.5], [1, 1.2], [1, 0.5]]],
  ["round retro compact", 4.1, 1.75, [[0, 0.5], [0.05, 0.8], [0.22, 0.95], [0.4, 1.48], [0.62, 1.5], [0.86, 1.2], [1, 0.75], [1, 0.48]]],
  ["family estate", 4.8, 1.82, [[0, 0.5], [0.04, 0.78], [0.27, 0.9], [0.37, 1.45], [0.92, 1.46], [0.99, 1.25], [1, 0.5]]],
];
export const PAINT = [0xf2f2f0, 0x1c1c1e, 0x9aa1a8, 0x2a4f8a, 0xb3261e, 0xe0b11e, 0x2f6b46, 0x6b6f75, 0xd8572a, 0x5a2a6e, 0x88a9c3, 0xc9b28d];

export function carStyle(k) {
  const [, L, W, prof] = STYLES[k % STYLES.length];
  const shape = new T.Shape();
  prof.forEach(([x, h], i) => (i ? shape.lineTo((0.5 - x) * L, h) : shape.moveTo((0.5 - x) * L, h)));
  shape.lineTo(-0.5 * L, 0.32);
  shape.lineTo(0.5 * L, 0.32);
  shape.closePath();
  const body = new T.ExtrudeGeometry(shape, { depth: W, bevelEnabled: true, bevelSize: 0.06, bevelThickness: 0.06, bevelSegments: 1 })
    .translate(0, 0, -W / 2).rotateY(Math.PI / 2).toNonIndexed();
  const parts = [[body, 0xffffff]];
  // the glasshouse: a darker band just under the roof line
  const roofTop = Math.max(...prof.map((p) => p[1]));
  parts.push([new T.BoxGeometry(W * 0.86, (roofTop - 0.95) * 0.55, L * 0.32).translate(0, roofTop - (roofTop - 0.95) * 0.35, -L * 0.03), 0x1d2731]);
  for (const sx of [-1, 1]) for (const sz of [-1, 1])
    parts.push([new T.CylinderGeometry(0.34, 0.34, 0.26, 12).rotateZ(Math.PI / 2).translate(sx * (W / 2 - 0.05), 0.34, sz * L * 0.32), 0x151515]);
  parts.push([new T.BoxGeometry(W * 0.7, 0.12, 0.05).translate(0, 0.72, L / 2 + 0.06), 0xfff6d8], [new T.BoxGeometry(W * 0.7, 0.12, 0.05).translate(0, 0.78, -L / 2 - 0.06), 0xc0201a]);
  const pos = [], nor = [], col = [];
  for (const [g0, color] of parts) {
    const g = g0.index ? g0.toNonIndexed() : g0;
    g.computeVertexNormals();
    const c = new T.Color(color), p = g.attributes.position, n = g.attributes.normal;
    for (let i = 0; i < p.count; i++) { pos.push(p.getX(i), p.getY(i), p.getZ(i)); nor.push(n.getX(i), n.getY(i), n.getZ(i)); col.push(c.r, c.g, c.b); }
  }
  const out = new T.BufferGeometry();
  out.setAttribute("position", new T.Float32BufferAttribute(pos, 3));
  out.setAttribute("normal", new T.Float32BufferAttribute(nor, 3));
  out.setAttribute("aCol", new T.Float32BufferAttribute(col, 3));
  return out;
}
