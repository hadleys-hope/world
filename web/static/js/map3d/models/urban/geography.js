/** Visual geography only. This module never changes simulation coordinates or domain state. */
const C = [-0.66, 0.32, -0.68],
  length = Math.hypot(...C);
C.forEach((v, i) => (C[i] /= length));
const E = [C[2], 0, -C[0]],
  el = Math.hypot(...E);
E.forEach((v, i) => (E[i] /= el));
const N = [
  C[1] * E[2] - C[2] * E[1],
  C[2] * E[0] - C[0] * E[2],
  C[0] * E[1] - C[1] * E[0],
];
let radius = 12000,
  enabled = false;
export function enableCityRiver(R) {
  radius = R;
  enabled = true;
}
export function planPosition(nx, ny, nz, R = radius) {
  const n = [nx, ny, nz],
    dot = (a) => n.reduce((v, x, i) => v + x * a[i], 0),
    d = Math.acos(Math.max(-1, Math.min(1, dot(C)))),
    s = Math.sin(d);
  return s < 1e-8 ? [0, 0] : [(dot(E) * d * R) / s, (dot(N) * d * R) / s];
}
export function riverCentre(x) {
  const t = Math.max(0, Math.min(1, (-x - 1100) / 350));
  return -260 * t * t * (3 - 2 * t);
}
export function bridgeLift(y) {
  const t = Math.max(0, Math.min(1, (Math.abs(y) - 34) / 126));
  return 12 * (1 - t * t * (3 - 2 * t));
}
export function riverLevel(x) {
  return (
    (radius * 0.0035 - 4) *
    Math.max(0, Math.min(1, (2600 - Math.abs(x)) / 1500))
  );
}
export function riverWidth(x) {
  return 28 + Math.max(0, Math.min(1, (Math.abs(x) - 1050) / 700)) * 55;
}
export function riverHeight(nx, ny, nz, h) {
  if (!enabled) return h;
  const [x, y] = planPosition(nx, ny, nz);
  if (Math.abs(x) > 10500) return h;
  const width = riverWidth(x),
    bank = Math.abs(x) < 1100 ? 3 : 100,
    d = Math.abs(y - riverCentre(x));
  if (d > width + bank) return h;
  const k = Math.max(0, Math.min(1, (d - width) / bank));
  const t = k * k * (3 - 2 * k);
  return ((riverLevel(x) - 7) / radius) * (1 - t) + h * t;
}
