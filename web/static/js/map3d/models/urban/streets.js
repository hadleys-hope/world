import { streetTexture } from "./materials.js";
import { treeGeometry } from "../life.js";
import { bridgeLift } from "./geography.js";
/** Continuous street meshes, reusable street furniture, collision-aware planting reservations. */
import * as T from "three";
import { state } from "../../state.js";
import {
  Batches,
  Model,
  pole,
  bench,
  bin,
  antenna,
  car,
  palette,
  roofPlant,
  planYaw,
} from "./kit.js";
import { civicGeometry, facadeMaterial } from "./buildings.js";
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
    return !(city.id === "k1" && Math.abs(y) < 34);
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
      ps = points.map(([x, y, h = 0]) => this.point(x, y, h));
    for (const i of [0, 1, 2, 2, 1, 3]) {
      this.p.push(...ps[i].toArray());
      this.uv.push(points[i][0] * 0.5, points[i][1] * 0.5);
      this.c.push(C.r, C.g, C.b);
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
function lineMesh(segments, color) {
  const g = new T.BufferGeometry().setFromPoints(segments);
  return new T.LineSegments(g, new T.LineBasicMaterial({ color }));
}
export function* buildDistrict(c, body, R, globalPoint, env) {
  const point = (x, y, h = 0) => globalPoint(c.at[0] + x, c.at[1] + y, h),
    b = new Batches(body, R, point, env),
    roadPoint = (x, y, h = 0) =>
      point(x, y, h + (c.id === "k1" ? bridgeLift(y) : 0)),
    road = new Surface(roadPoint),
    walk = new Surface(roadPoint),
    wires = [],
    publicGround = new Surface(point),
    ponds = new Surface(point),
    reserve = reservation(c),
    streetPoles = [];
  const occupiedPoles = new Set();
  let roadIndex = 0;
  for (const r of c.roads) {
    if (roadIndex++ % 8 === 0) yield;
    let distance = 0,
      nextLamp = 12;
    for (let j = 1; j < r.points.length; j++) {
      const A = r.points[j - 1],
        B = r.points[j],
        dx = B[0] - A[0],
        dy = B[1] - A[1],
        L = Math.hypot(dx, dy);
      if (!L) continue;
      const n = [-dy / L, dx / L],
        at = (t) => [A[0] + dx * t, A[1] + dy * t];
      road.strip(A, B, r.width, 0.16, 0x303b42);
      road.strip(A, B, 0.16, 0.18, 0xe2debd, r.width / 2 - 0.55);
      road.strip(A, B, 0.16, 0.18, 0xe2debd, -r.width / 2 + 0.55);
      for (let d = Math.ceil(distance / 9) * 9; d < distance + L; d += 9) {
        const a = at(Math.max(0, (d - distance) / L)),
          z = at(Math.min(1, (d + 4 - distance) / L));
        road.strip(a, z, 0.18, 0.19, 0xe2debd);
      }
      for (const side of [-1, 1]) {
        // Raised sidewalks, with vertical curb faces; interrupt at radial junctions.
        const mid = at(0.5),
          angle = Math.atan2(mid[1], mid[0]),
          rad = Math.hypot(...mid),
          junction =
            (Math.abs(Math.sin(angle * 3)) * rad) / 3 < r.width ||
            (Math.abs(rad - 210) < 8 &&
              (Math.abs(Math.cos(angle * 6)) * rad) / 6 < 4);
        if (!junction) {
          walk.strip(A, B, 2.2, 0.39, 0xa8a99f, side * (r.width / 2 + 1.1));
          const off = (side * r.width) / 2;
          walk.quad(
            [
              [A[0] + n[0] * off, A[1] + n[1] * off, 0.16],
              [A[0] + n[0] * off, A[1] + n[1] * off, 0.39],
              [B[0] + n[0] * off, B[1] + n[1] * off, 0.16],
              [B[0] + n[0] * off, B[1] + n[1] * off, 0.39],
            ],
            0xb9bbad,
          );
        }
      }
      while (nextLamp < distance + L) {
        const p = at((nextLamp - distance) / L),
          off = r.width / 2 + 2.8,
          x = p[0] + n[0] * off,
          y = p[1] + n[1] * off,
          k = `${Math.round(x / 10)},${Math.round(y / 10)}`;
        if (!occupiedPoles.has(k) && !(c.id === "k1" && Math.abs(y) < 32)) {
          b.add("lamp", pole, x, y, 0.2, 1, Math.atan2(-dx, dy));
          streetPoles.push([x, y, Math.atan2(-dx, dy)]);
          occupiedPoles.add(k);
        }
        nextLamp += 45;
      }
      distance += L;
    }
  }
  // Exact insulator anchors use the same orientation as the pole instances.
  const up = new T.Vector3(0, 1, 0),
    anchor = (p, phase) => {
      const base = point(p[0], p[1], 0.2),
        n = base.clone().normalize(),
        q = new T.Quaternion()
          .setFromUnitVectors(up, n)
          .multiply(
            new T.Quaternion().setFromAxisAngle(
              up,
              planYaw(point, p[0], p[1], p[2], 0.2),
            ),
          );
      return new T.Vector3(phase, 7.95, 0).applyQuaternion(q).add(base);
    };
  const cable = (A, B, sag) => {
    const n = A.clone().add(B).normalize();
    for (let k = 0; k < 8; k++) {
      const at = (t) =>
        A.clone()
          .lerp(B, t)
          .addScaledVector(n, -sag * 4 * t * (1 - t));
      wires.push(at(k / 8), at((k + 1) / 8));
    }
  };
  for (let i = 1; i < streetPoles.length; i++) {
    const A = streetPoles[i - 1],
      B = streetPoles[i],
      L = Math.hypot(B[0] - A[0], B[1] - A[1]);
    if (L > 65 || L < 10) continue;
    for (const phase of [-1.1, 0, 1.1])
      cable(anchor(A, phase), anchor(B, phase), 1.25);
  }
  const matrix = new T.Matrix4(),
    inverse = new T.Matrix4(),
    offset = state.klyaksaHouseMeta.findIndex((h) => h.city === c.id);
  for (let i = 0; i < c.houses; i++) {
    if (i % 200 === 0) yield;
    let nearest = null,
      dist = Infinity;
    for (const p of streetPoles) {
      const d = (p[0] - c.x[i]) ** 2 + (p[1] - c.y[i]) ** 2;
      if (d < dist) {
        dist = d;
        nearest = p;
      }
    }
    if (!nearest) continue;
    state.klyaksaHouses.getMatrixAt(offset + i, matrix);
    inverse.copy(matrix).invert();
    const p = anchor(nearest, 0).applyMatrix4(inverse);
    const corner = new T.Vector3(
      Math.sign(p.x) * 4.48,
      5 + 6.25 / state.klyaksaHouseMeta[offset + i].height,
      Math.sign(p.z) * 5.43,
    ).applyMatrix4(matrix);
    for (const phase of [-0.12, 0, 0.12])
      cable(
        anchor(nearest, phase),
        corner
          .clone()
          .addScaledVector(
            new T.Vector3(1, 0, 0).transformDirection(matrix),
            phase,
          ),
        Math.min(1, Math.sqrt(dist) * 0.018),
      );
  }
  // Stop lines, pedestrian zebras and signals on every ring/radial junction.
  const radii = [
    ...new Set(
      c.roads
        .filter((r) => r.points.length > 8)
        .map((r) => Math.round(Math.hypot(...r.points[0]))),
    ),
  ];
  const signal = () =>
    new Model()
      .cyl(0, 1.8, 0, 0.07, 3.6)
      .box(0, 3.5, 0, 0.35, 0.9, 0.25, palette.dark)
      .box(0, 3.77, 0.14, 0.16, 0.16, 0.03, 0xd96345)
      .box(0, 3.25, 0.14, 0.16, 0.16, 0.03, 0x72b994)
      .finish();
  for (const r of radii)
    for (let sector = 0; sector < 6; sector++) {
      const a = (sector * Math.PI) / 3,
        co = Math.cos(a),
        si = Math.sin(a),
        x = co * r,
        y = si * r;
      for (const sign of [-1, 1]) {
        const px = x + co * sign * 10,
          py = y + si * sign * 10;
        road.strip(
          [px - si * 4, py + co * 4],
          [px + si * 4, py - co * 4],
          0.45,
          0.2,
          0xe9e5cb,
        );
        for (let k = -3; k <= 3; k++) {
          const cx = px + co * sign * 4 - si * k,
            cy = py + si * sign * 4 + co * k;
          road.strip(
            [cx - co * 1.4, cy - si * 1.4],
            [cx + co * 1.4, cy + si * 1.4],
            0.5,
            0.21,
            0xe9e5cb,
          );
        }
        if (!(c.id === "k1" && Math.abs(py) < 33))
          b.add("signals", signal, px - si * 7, py + co * 7, 0.2, 1, -a);
      }
    }
  body.add(road.mesh(), walk.mesh({ paving: true }), lineMesh(wires, 0x263b44));
  // Deliberate civic plots between the inner ring and residential streets.
  const kinds = [
    "hospital",
    "library",
    "sports",
    "coworking",
    "garage",
    "fire",
    "church",
    "cafe",
    "network",
    "water",
    "bank",
    "bank",
  ];
  state.klyaksaSitesVisual ||= [];
  kinds.forEach((kind, i) => {
    const a = ((i + 0.5) * Math.PI * 2) / kinds.length,
      r = 170,
      x = Math.cos(a) * r,
      y = Math.sin(a) * r;
    if (!reserve.free(x, y, 17)) return;
    reserve.mark(x, y, 23);
    b.add(
      kind,
      () => civicGeometry(kind),
      x,
      y,
      0.4,
      kind === "bank" ? 1 : 0.8,
      0,
    );
    if (kind === "bank" || kind === "network")
      b.add("5G", antenna, x, y, kind === "bank" ? 74 : 10.5, 1);
    b.add("HVAC", roofPlant, x + 5, y, kind === "bank" ? 66 : 9, 0.9);
    state.klyaksaSitesVisual.push({
      city: c.id,
      kind,
      x: c.at[0] + x,
      y: c.at[1] + y,
    });
    const parking = publicGround,
      side = Math.sign(y) || 1;
    parking.quad(
      [
        [x - 16, y + side * 13, 0.18],
        [x + 16, y + side * 13, 0.18],
        [x - 16, y + side * 24, 0.18],
        [x + 16, y + side * 24, 0.18],
      ],
      0x41494c,
    );
    for (let k = -3; k <= 3; k++) {
      parking.strip(
        [x + k * 4, y + side * 15],
        [x + k * 4, y + side * 22],
        0.13,
        0.21,
        0xe2dfc9,
      );
      if (k % 2 === 0)
        b.add("parked", car, x + k * 4 + 1.8, y + side * 18, 0.2, 0.7, 0);
    }
    // A continuous access spur to the adjacent ring instead of an isolated parking rectangle.
    parking.strip(
      [x, y + side * 24],
      [Math.cos(a) * 210, Math.sin(a) * 210],
      5,
      0.2,
      0x41494c,
    );
  });
  // Hub: utilities, two stepped bank towers, reservoir and UPS cabinets, clear of the river axis.
  for (const [kind, x, y] of [
    ["bank", -42, 55],
    ["bank", 37, 58],
    ["network", -20, -57],
    ["tank", 25, -60],
  ]) {
    b.add("hub-" + kind, () => civicGeometry(kind), x, y, 0.4, 1);
    if (kind === "bank") b.add("5G", antenna, x, y, 74, 1);
  }
  for (let i = 0; i < 5; i++)
    b.add(
      "UPS",
      () =>
        new Model()
          .box(0, 1.3, 0, 1.3, 2.6, 1.4, palette.metal)
          .box(0, 1.9, 0.72, 0.7, 0.4, 0.05, 0x78cca7)
          .finish(),
      -10 + i * 3,
      -86,
      0.2,
    );
  // Parks occupy verified vacant plots. Benches, bins, paths and small stages share batches.
  for (let k = 0; k < 100; k++) {
    const a = k * 2.39996,
      r = 245 + ((k * 137) % (c.wall - 280)),
      x = Math.cos(a) * r,
      y = Math.sin(a) * r;
    if (!reserve.free(x, y, 12)) continue;
    reserve.mark(x, y, 12);
    const patch = publicGround;
    for (let j = 0; j < 24; j++) {
      const t = (j * Math.PI) / 12,
        u = ((j + 1) * Math.PI) / 12;
      patch.quad(
        [
          [x, y, 0.09],
          [x + Math.cos(t) * 11, y + Math.sin(t) * 11, 0.09],
          [x, y, 0.09],
          [x + Math.cos(u) * 11, y + Math.sin(u) * 11, 0.09],
        ],
        0x4c7756,
      );
    }
    patch.strip([x - 10, y], [x + 10, y], 2, 0.15, 0xb5ac90);
    b.add("bench", bench, x - 3, y + 2, 0.2, 1);
    b.add("bench", bench, x + 3, y - 2, 0.2, 1, Math.PI);
    b.add("bins", bin, x + 5, y + 2, 0.2, 1);
    for (const dx of [-7, 7])
      b.add("park-tree", () => treeGeometry("broad"), x + dx, y + 5, 0, 1.4);
    if (k % 3 === 0)
      for (let j = 0; j < 24; j++) {
        const a = (j * Math.PI) / 12,
          z = ((j + 1) * Math.PI) / 12;
        ponds.quad(
          [
            [x, y - 5, 0.13],
            [x + Math.cos(a) * 3.5, y - 5 + Math.sin(a) * 3.5, 0.13],
            [x, y - 5, 0.13],
            [x + Math.cos(z) * 3.5, y - 5 + Math.sin(z) * 3.5, 0.13],
          ],
          0x408797,
        );
      }
  }
  body.add(publicGround.mesh());
  const pondMesh = ponds.mesh();
  pondMesh.material.roughness = 0.2;
  pondMesh.material.metalness = 0.35;
  body.add(pondMesh);
  const facades = facadeMaterial(env);
  const furniture = b.finish({
    distance: 3500,
    materialFor: (key) =>
      /^(hub-bank|hub-network|bank|hospital|library|sports|coworking|garage|fire|church|cafe|network|water)$/.test(
        key,
      )
        ? facades
        : null,
  });
  state.klyaksaLod.push(furniture);
  (state.klyaksaReservations ||= new Map()).set(c.id, reserve);
}
