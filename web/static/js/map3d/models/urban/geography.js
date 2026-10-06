/** Shared, finite visual river corridor. Coordinates are metres in the Klyaksa settlement chart. */
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
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const smooth = (v) => {
  v = clamp(v);
  return v * v * (3 - 2 * v);
};
let radius = 12000,
  enabled = false;
export const RIVER_SOURCE = -1900;
let mouth = 3180;
export function enableCityRiver(R) {
  radius = R;
  enabled = true;
}
export function planPosition(nx, ny, nz, R = radius) {
  const n = [nx, ny, nz],
    dot = (a) => n.reduce((v, x, i) => v + x * a[i], 0),
    d = Math.acos(clamp(dot(C), -1, 1)),
    s = Math.sin(d);
  return s < 1e-8 ? [0, 0] : [(dot(E) * d * R) / s, (dot(N) * d * R) / s];
}
export function riverCentre(x) {
  const downstream = Math.max(0, x - 1050);
  return (
    12 * Math.sin(x / 300) -
    (0.85 * downstream * downstream) / (downstream + 400) -
    240 * smooth((-x - 1100) / 400)
  );
}
/** Scan the *unmodified* landscape once, before terrain construction. Stop at the first fully wet mouth. */
export function configureCityRiver(R, terrain) {
  enableCityRiver(R);
  mouth = 3180;
  for (let x = 1750; x <= 5900; x += 20) {
    const w = riverWidth(x),
      y = riverCentre(x);
    if (
      [-1, 0, 1].every((t) => terrain(x, y + t * w) < -2) &&
      terrain(x + 60, riverCentre(x + 60)) < -2
    ) {
      mouth = x;
      break;
    }
  }
  return riverBounds();
}
export function riverBounds() {
  return { source: RIVER_SOURCE, mouth };
}
export function riverWidth(x) {
  if (x < RIVER_SOURCE || x > mouth) return 0;
  const source = smooth((x - RIVER_SOURCE) / 460),
    estuary = smooth((x - 1350) / (mouth - 1350));
  return source * (40 + 38 * estuary);
}
export function riverContains(x, y, margin = 0) {
  return (
    enabled &&
    x >= RIVER_SOURCE &&
    x <= mouth &&
    Math.abs(y - riverCentre(x)) < riverWidth(x) + margin
  );
}
export function riverLevel(x) {
  if (x < -1100) return radius * 0.0035 - 6 + 5 * smooth((-x - 1100) / 800);
  if (x <= 1100) return radius * 0.0035 - 6 - (x + 1100) * 0.0007;
  return (radius * 0.0035 - 7.54) * (1 - smooth((x - 1100) / (mouth - 1100)));
}
/** 24m road clearance: callers apply only to a road which actually crosses the channel. */
export function bridgeLift(y, x = 0) {
  return 24 * (1 - smooth((Math.abs(y - riverCentre(x)) - 58) / 162));
}
export function riverDepth(x, lateral = 0) {
  const shoal = x < -1200 ? 2.4 * Math.exp(-(((x + 1540) / 85) ** 2)) : 0;
  return Math.max(2, 10 - shoal - 5.5 * Math.pow(Math.abs(lateral), 6));
}
export function riverHeight(nx, ny, nz, h) {
  if (!enabled) return h;
  const [x, y] = planPosition(nx, ny, nz);
  if (x < RIVER_SOURCE || x > mouth) return h;
  const width = riverWidth(x),
    d = Math.abs(y - riverCentre(x)),
    urban = Math.abs(x) < 1100,
    bank = urban ? 7 : 32;
  if (d > width + bank) return h;
  const bed = (riverLevel(x) - riverDepth(x, d / Math.max(1, width))) / radius;
  const shore = Math.max(h, (riverLevel(x) + (urban ? 6 : 2.7)) / radius);
  // A deep channel with actual embankments; never an infinite water ribbon across the ocean.
  return d < width ? bed : bed + (shore - bed) * smooth((d - width) / bank);
}
