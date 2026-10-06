/** Continuous, terrain-tessellated streets driven by the same graph as traffic and utilities. */
import * as T from "three";
import { state } from "../../state.js";
import { streetTexture } from "./materials.js";
import { riverContains, riverCentre } from "./geography.js";
import { Batches, Model, bench, bin, palette } from "./kit.js";
import { buildCivicDistrict } from "./civic.js";
import { roadNetwork, registerTrafficSignals } from "./traffic.js";

export function reservation(city) {
  const cell = 16,
    grid = new Map(),
    key = (x, y) => `${Math.floor(x / cell)},${Math.floor(y / cell)}`;
  const mark = (x, y, r) => {
    for (
      let a = Math.floor((x - r) / cell);
      a <= Math.floor((x + r) / cell);
      a++
    )
      for (
        let b = Math.floor((y - r) / cell);
        b <= Math.floor((y + r) / cell);
        b++
      ) {
        const k = `${a},${b}`;
        if (!grid.has(k)) grid.set(k, []);
        grid.get(k).push({ x, y, r });
      }
  };
  for (let i = 0; i < city.houses; i++) mark(city.x[i], city.y[i], 8);
  for (const road of [...city.roads, ...(city.service_roads || [])])
    for (let j = 1; j < road.points.length; j++) {
      const a = road.points[j - 1],
        b = road.points[j],
        L = Math.hypot(b[0] - a[0], b[1] - a[1]);
      for (let d = 0; d <= L; d += 4)
        mark(
          a[0] + ((b[0] - a[0]) * d) / L,
          a[1] + ((b[1] - a[1]) * d) / L,
          road.width / 2 + 3.5,
        );
    }
  for (const [x, y] of Object.values(city.facilities || {})) mark(x, y, 58);
  for (const q of [
    ...(city.civic_plots || []),
    ...(city.sector_services || []),
  ])
    mark(q.x, q.y, Math.hypot(q.w || 30, q.d || 30) / 2 + 3);
  for (const q of city.parks || [])
    mark(q.x, q.y, Math.hypot(q.w || 25, q.d || 25) / 2);
  const free = (x, y, r = 0) => {
    for (
      let a = Math.floor((x - r) / cell);
      a <= Math.floor((x + r) / cell);
      a++
    )
      for (
        let b = Math.floor((y - r) / cell);
        b <= Math.floor((y + r) / cell);
        b++
      )
        for (const q of grid.get(`${a},${b}`) || [])
          if (Math.hypot(x - q.x, y - q.y) < r + q.r) return false;
    return !riverContains(city.at[0] + x, city.at[1] + y, r + 3);
  };
  return { mark, free };
}
export class Surface {
  constructor(point) {
    this.point = point;
    this.p = [];
    this.c = [];
    this.uv = [];
  }
  quad(points, color) {
    const C = new T.Color(color),
      length = (a, b) =>
        Math.hypot(a[0] - b[0], a[1] - b[1], (a[2] || 0) - (b[2] || 0));
    const nu = Math.max(
      1,
      Math.ceil(
        Math.max(length(points[0], points[1]), length(points[2], points[3])) /
          4,
      ),
    );
    const nv = Math.max(
      1,
      Math.ceil(
        Math.max(length(points[0], points[2]), length(points[1], points[3])) /
          4,
      ),
    );
    const at = (u, v) =>
      [0, 1, 2].map(
        (k) =>
          (points[0][k] || 0) * (1 - u) * (1 - v) +
          (points[1][k] || 0) * u * (1 - v) +
          (points[2][k] || 0) * (1 - u) * v +
          (points[3][k] || 0) * u * v,
      );
    for (let v = 0; v < nv; v++)
      for (let u = 0; u < nu; u++) {
        const flat = [
            at(u / nu, v / nv),
            at((u + 1) / nu, v / nv),
            at(u / nu, (v + 1) / nv),
            at((u + 1) / nu, (v + 1) / nv),
          ],
          ps = flat.map(([x, y, h]) => this.point(x, y, h));
        for (const i of [0, 1, 2, 2, 1, 3]) {
          this.p.push(...ps[i].toArray());
          this.uv.push(flat[i][0] * 0.5, flat[i][1] * 0.5);
          this.c.push(C.r, C.g, C.b);
        }
      }
  }
  strip(a, b, w, h, color, offset = 0) {
    const L = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (L < 0.01) return;
    const x = -(b[1] - a[1]) / L,
      y = (b[0] - a[0]) / L;
    const count = Math.max(1, Math.ceil(w / 3)),
      piece = w / count;
    for (let i = 0; i < count; i++) {
      const low = offset - w / 2 + i * piece,
        high = low + piece;
      this.quad(
        [
          [a[0] + x * low, a[1] + y * low, h],
          [a[0] + x * high, a[1] + y * high, h],
          [b[0] + x * low, b[1] + y * low, h],
          [b[0] + x * high, b[1] + y * high, h],
        ],
        color,
      );
    }
  }

  mesh({ paving = false } = {}) {
    const g = new T.BufferGeometry();
    g.setAttribute("position", new T.Float32BufferAttribute(this.p, 3));
    g.setAttribute("color", new T.Float32BufferAttribute(this.c, 3));
    g.setAttribute("uv", new T.Float32BufferAttribute(this.uv, 2));
    g.computeVertexNormals();
    return new T.Mesh(
      g,
      new T.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.92,
        map: streetTexture(paving),
        bumpMap: streetTexture(paving),
        bumpScale: paving ? 0.025 : 0.008,
        side: T.DoubleSide,
      }),
    );
  }
}
const crossingCache = new WeakMap();
export function roadCrossesRiver(c, r) {
  if (r.bridge) return true;
  if (crossingCache.has(r)) return crossingCache.get(r);
  if (c.id !== "k1") return false;
  let wet = false,
    positive = false,
    negative = false;
  for (const p of r.points) {
    wet ||= riverContains(c.at[0] + p[0], c.at[1] + p[1], 0);
    positive ||= p[1] > 18;
    negative ||= p[1] < -18;
  }
  const crossing = wet && positive && negative;
  crossingCache.set(r, crossing);
  return crossing;
}
/** Kept on each graph edge so traffic, markings and utility underpasses share a deck height. */
export function roadElevation(c, r, x, y) {
  if (!roadCrossesRiver(c, r)) return 0;
  const a = r.points[0],
    b = r.points.at(-1),
    delta = (px, py) => py + c.at[1] - riverCentre(px + c.at[0]),
    d = delta(x, y);
  const endpoint = Math.sign(d) === Math.sign(delta(...a)) ? a : b,
    end = Math.min(220, Math.abs(delta(...endpoint)));
  const t = Math.max(
    0,
    Math.min(1, (Math.abs(d) - 58) / Math.max(1, end - 58)),
  );
  return 24 * (1 - t * t * (3 - 2 * t));
}
export function roadDeckHeight(c, x, y, R) {
  let lift = 0;
  for (const r of [...c.roads, ...(c.service_roads || [])]) {
    if (!roadCrossesRiver(c, r)) continue;
    for (let i = 1; i < r.points.length; i++) {
      const a = r.points[i - 1],
        b = r.points[i],
        dx = b[0] - a[0],
        dy = b[1] - a[1],
        t = Math.max(
          0,
          Math.min(
            1,
            ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy || 1),
          ),
        );
      if (Math.hypot(x - a[0] - dx * t, y - a[1] - dy * t) < r.width / 2 + 9)
        lift = Math.max(lift, roadElevation(c, r, x, y));
    }
  }
  return R * 0.0035 + 0.25 + lift;
}
const signalPost = () =>
  new Model()
    .cyl(0, 1.9, 0, 0.075, 3.8)
    .box(0, 3.45, 0, 0.4, 1.08, 0.3, palette.dark)
    .box(0, 4.02, 0.07, 0.5, 0.08, 0.5, palette.dark)
    .finish();
const bollard = () =>
  new Model()
    .cyl(0, 0.55, 0, 0.075, 1.1, palette.dark)
    .cyl(0, 0.92, 0, 0.09, 0.12, 0xe6daba)
    .finish();
function disk(surface, x, y, r, h, color) {
  for (let i = 0; i < 24; i++) {
    const a = (i * Math.PI) / 12,
      b = ((i + 1) * Math.PI) / 12;
    surface.quad(
      [
        [x, y, h],
        [x + Math.cos(a) * r, y + Math.sin(a) * r, h],
        [x, y, h],
        [x + Math.cos(b) * r, y + Math.sin(b) * r, h],
      ],
      color,
    );
  }
}
function curveDashes(surface, A, B, C, h) {
  const length =
    Math.hypot(B[0] - A[0], B[1] - A[1]) + Math.hypot(C[0] - B[0], C[1] - B[1]);
  const at = (t) => [
    (1 - t) ** 2 * A[0] + 2 * (1 - t) * t * B[0] + t * t * C[0],
    (1 - t) ** 2 * A[1] + 2 * (1 - t) * t * B[1] + t * t * C[1],
  ];
  const steps = Math.max(4, Math.ceil(length / 1.3));
  for (let i = 0; i < steps; i += 3)
    surface.strip(
      at(i / steps),
      at(Math.min(1, (i + 1.35) / steps)),
      0.12,
      h,
      0xd4d5c8,
    );
}
export function* buildDistrict(c, body, R, globalPoint, env) {
  const point = (x, y, h = 0) => globalPoint(c.at[0] + x, c.at[1] + y, h),
    network = roadNetwork(c),
    b = new Batches(body, R, point, env),
    reserve = reservation(c),
    furniturePositions = [],
    accesses = (c.parcels || []).filter((p) => p.access).map((p) => p.access);
  const lights = [],
    allRoads = new Surface(point),
    allWalks = new Surface(point);
  let counter = 0;
  const houseClear = (x, y) =>
    !c.x.some((hx, i) => Math.abs(hx - x) < 8 && Math.abs(c.y[i] - y) < 8);
  const placed = (x, y) => {
    if (furniturePositions.some((p) => Math.hypot(p[0] - x, p[1] - y) < 5))
      return false;
    furniturePositions.push([x, y]);
    return true;
  };
  for (const edge of network.edges) {
    if (counter++ % 6 === 0) yield;
    const r = edge.road,
      deck = (x, y, h = 0) => point(x, y, h + roadElevation(c, r, x, y)),
      asphalt = allRoads,
      walk = allWalks;
    asphalt.point = deck;
    walk.point = deck;
    const crossing = roadCrossesRiver(c, r),
      endpointGap = (n) =>
        n.edges.length > 2
          ? Math.max(...n.edges.map((e) => e.road.width)) * 0.75 + 3
          : 0;
    const gapA = endpointGap(edge.a),
      gapB = endpointGap(edge.b),
      cycle = r.width >= 12 && r.kind !== "service",
      width = r.width;
    let distance = 0,
      nextFurniture = 28;
    for (let j = 1; j < r.points.length; j++) {
      const A = r.points[j - 1],
        B = r.points[j],
        dx = B[0] - A[0],
        dy = B[1] - A[1],
        L = Math.hypot(dx, dy);
      if (L < 0.001) continue;
      const n = [-dy / L, dx / L],
        at = (t) => [A[0] + dx * t, A[1] + dy * t];
      asphalt.strip(A, B, width, 0.24, 0x293339);
      const pieces = Math.max(1, Math.ceil(L / 3.5));
      for (let k = 0; k < pieces; k++) {
        const a = at(k / pieces),
          z = at((k + 1) / pieces),
          d = distance + ((k + 0.5) * L) / pieces;
        if (d < gapA || edge.length - d < gapB) continue;
        const midpoint = [(a[0] + z[0]) / 2, (a[1] + z[1]) / 2];
        if (
          accesses.some(
            (p) => Math.hypot(p.x - midpoint[0], p.y - midpoint[1]) < 6,
          )
        )
          continue;
        for (const side of [-1, 1]) {
          asphalt.strip(a, z, 0.16, 0.27, 0xe1debe, side * (width / 2 - 0.45));
          walk.strip(a, z, 2.2, 0.46, 0xa9aaa1, side * (width / 2 + 1.1));
          const off = (side * width) / 2;
          walk.quad(
            [
              [a[0] + n[0] * off, a[1] + n[1] * off, 0.24],
              [a[0] + n[0] * off, a[1] + n[1] * off, 0.46],
              [z[0] + n[0] * off, z[1] + n[1] * off, 0.24],
              [z[0] + n[0] * off, z[1] + n[1] * off, 0.46],
            ],
            0xd0cbb9,
          );
          if (cycle) {
            walk.strip(a, z, 1.8, 0.45, 0x567d72, side * (width / 2 + 3.3));
            walk.strip(a, z, 0.1, 0.48, 0xc6d6b0, side * (width / 2 + 4.13));
          }
        }
      }
      for (let d = Math.ceil(distance / 9) * 9; d < distance + L; d += 9) {
        if (d < gapA || edge.length - d < gapB) continue;
        asphalt.strip(
          at(Math.max(0, (d - distance) / L)),
          at(Math.min(1, (d + 4 - distance) / L)),
          0.17,
          0.28,
          0xe1debe,
        );
      }
      while (nextFurniture < distance + L) {
        const p = at((nextFurniture - distance) / L),
          off = width / 2 + (cycle ? 5 : 3),
          x = p[0] + n[0] * off,
          y = p[1] + n[1] * off;
        if (
          nextFurniture > gapA + 5 &&
          edge.length - nextFurniture > gapB + 5 &&
          !crossing &&
          houseClear(x, y) &&
          placed(x, y)
        ) {
          b.add("street-benches", bench, x, y, 0.46, 1, -Math.atan2(dy, dx));
          b.add("street-bins", bin, x + n[0] * 2.5, y + n[1] * 2.5, 0.46, 1);
        }
        nextFurniture += 72;
      }
      distance += L;
    }
  }
  // Junction islands are asphalt. Curbs are cut back above; no pavement crosses a live lane.
  const junctionSurface = new Surface(point);
  for (const node of network.junctions) {
    const [x, y] = node.point;
    if (riverContains(c.at[0] + x, c.at[1] + y, 4)) continue;
    const radius = Math.max(...node.edges.map((e) => e.road.width)) * 0.62;
    disk(junctionSurface, x, y, radius, 0.235, 0x293339);
    const approaches = [];
    for (const edge of node.edges) {
      const start = edge.a === node,
        p = edge.points[start ? 1 : edge.points.length - 2],
        dx = p[0] - x,
        dy = p[1] - y,
        L = Math.hypot(dx, dy),
        u = [dx / L, dy / L],
        n = [-u[1], u[0]],
        half = edge.road.width / 2,
        stop = radius + 3.5;
      const deck = (xx, yy, h) =>
          point(xx, yy, h + roadElevation(c, edge.road, xx, yy)),
        paint = allRoads;
      paint.point = deck;
      const A = [x + u[0] * stop, y + u[1] * stop];
      // Stop line only on incoming half; opposite lane retains a clear exit.
      paint.strip(
        [A[0], A[1]],
        [A[0] + n[0] * (half - 0.3), A[1] + n[1] * (half - 0.3)],
        0.4,
        0.285,
        0xefe6ce,
      );
      const zebra = stop + 4.5;
      for (let lane = -half + 0.5; lane < half - 0.2; lane += 1.05) {
        const Z = [
          x + u[0] * zebra + n[0] * lane,
          y + u[1] * zebra + n[1] * lane,
        ];
        paint.strip(
          [Z[0] - u[0] * 1.5, Z[1] - u[1] * 1.5],
          [Z[0] + u[0] * 1.5, Z[1] + u[1] * 1.5],
          0.53,
          0.285,
          0xefe6ce,
        );
      }
      const sx = A[0] + n[0] * (half + 0.6),
        sy = A[1] + n[1] * (half + 0.6),
        angle = Math.atan2(u[1], u[0]),
        height = roadElevation(c, edge.road, sx, sy);
      b.add(
        "traffic-posts",
        signalPost,
        sx,
        sy,
        0.25 + height,
        1,
        -angle - Math.PI / 2,
      );
      lights.push({
        node,
        heading: angle + Math.PI,
        positions: [3.78, 3.45, 3.12].map((h) =>
          point(sx + u[0] * 0.19, sy + u[1] * 0.19, h + 0.25 + height),
        ),
      });
      for (const sign of [-1, 1])
        b.add(
          "crossing-bollards",
          bollard,
          x + u[0] * (zebra + 2) + n[0] * (half + 0.4) * sign,
          y + u[1] * (zebra + 2) + n[1] * (half + 0.4) * sign,
          0.3,
          1,
        );
      approaches.push({ u, n, half });
    }
    for (let a = 0; a < approaches.length; a++)
      for (let z = a + 1; z < approaches.length; z++) {
        const A = approaches[a],
          Z = approaches[z],
          dot = A.u[0] * Z.u[0] + A.u[1] * Z.u[1];
        if (dot < -0.8) continue;
        const from = [
            x + A.u[0] * (radius + 2) + A.n[0] * A.half * 0.48,
            y + A.u[1] * (radius + 2) + A.n[1] * A.half * 0.48,
          ],
          to = [
            x + Z.u[0] * (radius + 2) - Z.n[0] * Z.half * 0.48,
            y + Z.u[1] * (radius + 2) - Z.n[1] * Z.half * 0.48,
          ];
        curveDashes(junctionSurface, from, [x, y], to, 0.29);
      }
  }
  body.add(
    allRoads.mesh(),
    allWalks.mesh({ paving: true }),
    junctionSurface.mesh(),
  );
  registerTrafficSignals(body, lights);
  const furniture = b.finish({ distance: 3500 });
  state.klyaksaLod.push(furniture);
  (state.klyaksaReservations ||= new Map()).set(c.id, reserve);
  yield* buildCivicDistrict(c, body, R, globalPoint, env);
}
