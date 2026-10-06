import {
  riverLevel,
  riverWidth,
  riverCentre,
  riverContains,
} from "./geography.js";
import { buildRiverSceneSteps, updateRiverFlow } from "./river-scene.js";
import {
  bodyPointToWorld,
  bodyDirectionToWorld,
} from "../../geometry/body-frame.js";
/** Klyaksa waterfronts and local exploration vessels. No server-domain updates or synthetic telemetry. */
import * as T from "three";
import { state } from "../../state.js";
import { bodyHeight, PLATEAU } from "../../geometry/noise.js";
import { dirAt } from "../klyaksa.js";
import {
  Model,
  Batches,
  palette,
  car,
  pole,
  bench,
  bin,
  planYaw,
} from "./kit.js";
import { Surface } from "./streets.js";
import { civicGeometry } from "./buildings.js";
import { buildPortWaterExtension } from "./utilities.js";
function cargoGeometry() {
  const m = new Model(),
    shape = new T.Shape();
  shape.moveTo(-9, -42);
  shape.lineTo(9, -42);
  shape.lineTo(9, 31);
  shape.quadraticCurveTo(8, 44, 0, 50);
  shape.quadraticCurveTo(-8, 44, -9, 31);
  shape.closePath();
  const hull = new T.ExtrudeGeometry(shape, {
    depth: 7,
    bevelEnabled: true,
    bevelSegments: 2,
    bevelSize: 1,
    bevelThickness: 0.7,
    steps: 1,
  })
    .rotateX(Math.PI / 2)
    .translate(0, 4, 0);
  m.parts.push([hull, 0x304c5a]);
  m.box(0, 4.2, -1, 17, 0.35, 80, 0x8d9488)
    .box(0, 7, -32, 15, 6, 15, palette.white)
    .box(0, 11, -34, 12, 3, 11, palette.white)
    .box(0, 13, -34, 16, 1, 13, palette.white);
  for (const side of [-1, 1]) {
    for (let z = -38; z <= 38; z += 4)
      m.beam([side * 8, 4.4, z], [side * 8, 5.7, z], 0.07, palette.white);
    m.beam([side * 8, 5.7, -38], [side * 8, 5.7, 38], 0.08, palette.white);
    for (let z = -39; z < -25; z += 2)
      m.box(side * 7.55, 8.1, z, 0.1, 1, 1.3, palette.glass);
    m.box(side * 6.1, 11.4, -34, 0.1, 1.2, 8, palette.glass);
    for (let z = -35; z < -25; z += 6)
      m.box(side * 9.1, 6, z, 2.3, 1.2, 4.6, 0xdc7645);
  }
  for (let x = -5; x <= 5; x += 2)
    m.box(x, 11.4, -28.4, 1.4, 1.2, 0.12, palette.glass);
  for (let row = 0; row < 5; row++)
    for (let col = 0; col < 3; col++)
      for (let level = 0; level < 2 + (row % 2); level++) {
        const x = (col - 1) * 4.6,
          z = -16 + row * 10,
          y = 5.7 + level * 3.1,
          color = [0x9f653f, 0x688b8d, 0xaaa273, 0x854b40][
            (row + col + level) % 4
          ];
        m.box(x, y, z, 4.3, 3, 9, color);
        for (let k = -4; k <= 4; k += 1)
          m.box(x - 2.18, y, z + k, 0.07, 2.7, 0.09, palette.metal).box(
            x + 2.18,
            y,
            z + k,
            0.07,
            2.7,
            0.09,
            palette.metal,
          );
      }
  m.cyl(3, 15, -34, 0.8, 4, 0xb08351).cyl(
    3,
    17.1,
    -34,
    0.95,
    0.25,
    palette.dark,
  );
  m.beam([-3, 13, -34], [-3, 21, -34], 0.13, palette.metal).beam(
    [-6, 20, -34],
    [0, 20, -34],
    0.11,
    palette.white,
  );
  m.box(-3, 21, -34, 3, 0.3, 0.6, palette.white);
  for (const x of [-5, 5])
    m.cyl(x, 4.8, 40, 0.6, 1.2, palette.dark).beam(
      [x, 4.2, 39],
      [x, 4.2, 32],
      0.12,
      palette.metal,
    );
  m.box(-8.5, 12, -28, 0.3, 0.25, 0.6, 0xe96354).box(
    8.5,
    12,
    -28,
    0.3,
    0.25,
    0.6,
    0x62d194,
  );
  return m.finish();
}
export function vesselGeometry(kind) {
  if (kind === "ship") return cargoGeometry();
  const m = new Model(),
    ship = false,
    scale = 1;
  const hull = new T.Shape();
  hull.moveTo(-2, -5);
  hull.lineTo(2, -5);
  hull.lineTo(2, 3);
  hull.quadraticCurveTo(1.8, 5, 0, 6);
  hull.quadraticCurveTo(-1.8, 5, -2, 3);
  hull.closePath();
  const g = new T.ExtrudeGeometry(hull, {
    depth: 1.8,
    bevelEnabled: true,
    bevelSegments: 1,
    steps: 1,
    bevelSize: 0.25,
    bevelThickness: 0.2,
  })
    .rotateX(Math.PI / 2)
    .translate(0, 1.2, 0);
  m.parts.push([g, ship ? 0x284c5b : 0xe9e4d3]);
  m.box(0, 1.4, 0, 3.5, 0.2, 7, palette.wood)
    .box(0, 2.25, 1, 2.6, 1.4, 3, palette.glass)
    .box(0, 3.02, 1, 2.8, 0.15, 3.3, palette.white)
    .cyl(0, 3.6, 0.2, 0.07, 1.2);
  for (const x of [-1.6, 1.6]) {
    for (let z = -3; z <= 3; z += 1.5) m.beam([x, 1.5, z], [x, 2.3, z], 0.025);
    m.beam([x, 2.3, -3], [x, 2.3, 3], 0.025, palette.white);
    m.box(x, 2, 2, 0.1, 0.12, 0.16, x < 0 ? 0xe25443 : 0x71c493);
  }
  if (kind === "yacht") {
    m.beam([0, 1.7, 0], [0, 11, 0], 0.07);
    const sail = new T.BufferGeometry();
    sail.setAttribute(
      "position",
      new T.Float32BufferAttribute([0.05, 3, 0, 0.05, 10, 0, 0.05, 3, -4], 3),
    );
    sail.computeVertexNormals();
    m.parts.push([sail, palette.white]);
  }
  if (ship) {
    for (let k = -1; k <= 1; k++)
      m.box(
        0,
        2,
        -2 + k * 1.5,
        3,
        1.3,
        1.25,
        [0xaf6345, 0x697f81, 0xb9ad79][k + 1],
      );
  }
  return m.finish().scale(scale, scale, scale);
}
function* findCoastSteps(c, R) {
  let best = null;
  const wet = (x, y) => {
    const n = dirAt(x, y, R);
    return !riverContains(x, y, 220) && bodyHeight(3, n.x, n.y, n.z) * R < -6;
  };
  for (let k = 0; k < 48; k++) {
    if (k % 4 === 0) yield;
    const a = (k * Math.PI) / 24,
      co = Math.cos(a),
      si = Math.sin(a);
    for (let d = c.wall + 200; d < 8000; d += 80) {
      const x = c.at[0] + co * d,
        y = c.at[1] + si * d;
      if (!wet(x, y)) continue;
      // Entire quay and berth envelope must be water, not merely one sampled point.
      let clear = true;
      for (const u of [-80, 0, 180, 300])
        for (const v of [-220, -100, 0, 100, 220])
          if (!wet(x + co * u - si * v, y + si * u + co * v)) clear = false;
      if (clear) {
        if (!best || d < best.score) best = { x, y, a, score: d };
        break;
      }
    }
  }
  return best;
}
/** Follow an existing dome gate, then turn outside the protected city footprint. */
export function harbourAccess(city, coast) {
  const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
  const gates = city.gates || [];
  const gate = [...gates].sort(
    (a, b) =>
      Math.abs(wrap(Math.atan2(a.y, a.x) - coast.a)) -
      Math.abs(wrap(Math.atan2(b.y, b.x) - coast.a)),
  )[0];
  if (!gate) return [];
  const start = [city.at[0] + gate.x, city.at[1] + gate.y],
    angle = Math.atan2(gate.y, gate.x),
    delta = wrap(coast.a - angle),
    radius = Math.min(
      city.wall + 145,
      (coast.score ?? Math.hypot(coast.x - city.at[0], coast.y - city.at[1])) -
        110,
    );
  const points = [start];
  const count = Math.max(2, Math.ceil((Math.abs(delta) * radius) / 90));
  for (let i = 0; i <= count; i++) {
    const a = angle + (delta * i) / count;
    points.push([
      city.at[0] + Math.cos(a) * radius,
      city.at[1] + Math.sin(a) * radius,
    ]);
  }
  const end = [
    coast.x - Math.cos(coast.a) * 80,
    coast.y - Math.sin(coast.a) * 80,
  ];
  points.push(end);
  const curve = new T.CatmullRomCurve3(
    points.map(([x, y]) => new T.Vector3(x, 0, y)),
    false,
    "centripetal",
  );
  curve.arcLengthDivisions = Math.max(1600, points.length * 48);
  const sampled = curve.getSpacedPoints(Math.ceil(curve.getLength() / 4)),
    result = [[sampled[0].x, sampled[0].z]];
  for (let i = 1; i < sampled.length; i++) {
    const a = sampled[i - 1],
      b = sampled[i],
      count = Math.ceil(a.distanceTo(b) / 4);
    for (let j = 1; j <= count; j++) {
      const t = j / count;
      result.push([a.x + (b.x - a.x) * t, a.z + (b.z - a.z) * t]);
    }
  }
  return result;
}
/** Curved deck and caissons share the same spherical sampling; no planet-tangent 400m box. */
export function quayMeshes(point) {
  const deck = new Surface(point),
    foundation = new Surface(point);
  for (let u = -80; u < 0; u += 8)
    for (let v = -200; v < 200; v += 8) {
      const quad = (h) => [
        [u, v, h],
        [u + 8, v, h],
        [u, v + 8, h],
        [u + 8, v + 8, h],
      ];
      deck.quad(quad(4), 0x959e98);
      foundation.quad(quad(3.4), 0x727f80);
    }
  for (let v = -200; v < 200; v += 8)
    for (const u of [-80, 0])
      foundation.quad(
        [
          [u, v, -6],
          [u, v, 3.8],
          [u, v + 8, -6],
          [u, v + 8, 3.8],
        ],
        0x727f80,
      );
  for (let u = -80; u < 0; u += 8)
    for (const v of [-200, 200])
      foundation.quad(
        [
          [u, v, -6],
          [u, v, 3.8],
          [u + 8, v, -6],
          [u + 8, v, 3.8],
        ],
        0x727f80,
      );
  return { deck: deck.mesh({ paving: true }), foundation: foundation.mesh() };
}
function shortStrip(surface, a, b, w, h, color, offset = 0) {
  const count = Math.max(
      1,
      Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 8),
    ),
    at = (t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  for (let i = 0; i < count; i++)
    surface.strip(at(i / count), at((i + 1) / count), w, h, color, offset);
}
export function* buildWaterfrontSteps(body, R, plan, env, cityPoint) {
  const seaPoint = (x, y, h = 0) => dirAt(x, y, R).multiplyScalar(R + h),
    ships = [],
    vesselModels = new Map();
  state.klyaksaPorts = [];
  for (const id of ["k3", "k2", "k6"]) {
    const city = plan.cities.find((c) => c.id === id),
      coast = yield* findCoastSteps(city, R);
    if (!coast) continue;
    yield; // Finish coast discovery before allocating the terminal models.
    const { x, y, a } = coast,
      co = Math.cos(a),
      si = Math.sin(a),
      xy = (u, v) => [x + co * u - si * v, y + si * u + co * v],
      point = (u, v, h = 0) => seaPoint(...xy(u, v), h),
      b = new Batches(body, R, point, env),
      surface = new Surface(point);
    const quay = quayMeshes(point);
    body.add(quay.deck, quay.foundation);
    for (let j = -2; j <= 2; j++) {
      shortStrip(surface, [0, j * 35], [95, j * 35], 7, 3.7, 0xb4ad91);
      for (let u = 5; u < 95; u += 15) {
        b.add(
          "bollard",
          () => new Model().cyl(0, 0.35, 0, 0.22, 0.7, palette.dark).finish(),
          u,
          j * 35 + 3,
          3.7,
        );
        b.add(
          "pier-pile",
          () => new Model().cyl(0, -4, 0, 0.5, 8, palette.metal).finish(),
          u,
          j * 35,
          3.7,
        );
      }
    }
    for (let j = -2; j <= 2; j++)
      b.add(
        "pier-fenders",
        () =>
          new Model()
            .box(47.5, -0.25, -3.4, 95, 0.5, 0.25, palette.dark)
            .box(47.5, -0.25, 3.4, 95, 0.5, 0.25, palette.dark)
            .finish(),
        0,
        j * 35,
        3.7,
      );
    yield; // Quay and marina piles form an independent construction chunk.
    const container = () => {
      const m = new Model().box(0, 1.35, 0, 2.45, 2.7, 6.05, 0xa86445);
      for (let z = -2.8; z <= 2.8; z += 0.4)
        for (const side of [-1, 1])
          m.box(side * 1.24, 1.35, z, 0.05, 2.5, 0.08, 0xc58159);
      for (const x of [-1.1, 0, 1.1])
        m.box(x, 1.35, 3.05, 0.06, 2.6, 0.08, palette.metal);
      return m.finish();
    };
    for (let k = 0; k < 36; k++) {
      if (Math.abs(-158 + k * 9) < 18) continue; // Keep the customs access throat clear.
      b.add("shipping-containers", container, -65, -158 + k * 9, 4);
      if (k % 4 === 0)
        b.add("shipping-containers", container, -65, -158 + k * 9, 6.7);
    }
    // Warehouse, repair shed and cranes stand on the quay, never on the access lane.
    b.add("warehouse", () => civicGeometry("garage"), -28, -55, 4, 0.9);
    b.add("repair", () => civicGeometry("garage"), -28, 55, 4, 0.8);
    const crane = () => {
      const m = new Model();
      for (const v of [-4, 4]) m.beam([v, 0, 0], [v, 24, 0], 0.5, 0xd7aa4f);
      m.beam([-4, 24, 0], [4, 24, 0], 0.4, 0xd7aa4f)
        .beam([0, 24, -6], [0, 24, 24], 0.45, 0xd7aa4f)
        .beam([0, 24, 20], [0, 6, 20], 0.05);
      for (let z = -6; z < 22; z += 4) {
        m.beam([-1, 24, z], [1, 24, z + 4], 0.08, palette.brass).beam(
          [1, 24, z],
          [-1, 24, z + 4],
          0.08,
          palette.brass,
        );
      }
      m.box(0, 24, 16, 2, 1.1, 2, palette.dark)
        .box(2, 22, -2, 2.4, 2.8, 3, palette.glass)
        .cyl(0, 5.7, 20, 0.3, 0.5, palette.dark);
      for (let y = 1; y < 24; y++)
        m.box(-4, y, 0.2, 0.65, 0.06, 0.2, palette.metal);
      return m.finish();
    };
    for (const v of [-170, -125, 125, 170])
      b.add("crane", crane, -10, v, 4, 1.65, -a);
    yield; // Warehouses, containers and cranes are now staged.
    // Container terminal: tractor lanes, customs gate, workshop apron and quay-edge safety rails.
    shortStrip(surface, [-56, -188], [-56, 188], 12, 4.08, 0x38454b);
    shortStrip(surface, [-56, -188], [-56, 188], 0.18, 4.12, 0xead9a1);
    shortStrip(surface, [-80, 0], [-56, 0], 12, 4.09, 0x38454b);
    b.add(
      "port-gate",
      () =>
        new Model()
          .box(0, 2, 0, 7, 4, 5, palette.concrete)
          .box(0, 3, 2.55, 5, 1.1, 0.1, palette.glass)
          .beam([0, 0, -7], [0, 2, -7], 0.14, palette.metal)
          .beam([0, 2, -7], [0, 7, -10], 0.14, 0xdfba63)
          .finish(),
      -72,
      14,
      4,
    );
    for (let v = -180; v <= 180; v += 30) {
      b.add(
        "bollard-heavy",
        () =>
          new Model()
            .cyl(0, 0.65, 0, 0.45, 1.3, palette.dark)
            .box(0, 1.3, 0, 1.8, 0.3, 0.7, palette.dark)
            .finish(),
        -1,
        v,
        4,
      );
      b.add(
        "quay-fender",
        () => new Model().box(0, 0, 0, 0.7, 2, 3, palette.dark).finish(),
        0.3,
        v,
        2.2,
      );
    }
    for (let k = 0; k < 7; k++) {
      b.add("quay-lamp", pole, -5, -90 + k * 30, 4);
      b.add("bench", bench, -10, -80 + k * 27, 4);
      b.add("bin", bin, -12, -80 + k * 27, 4);
    }
    for (let k = 0; k < 6; k++)
      b.add("parked", car, -30, -22 + k * 8, 4, 0.9, -a);
    body.add(surface.mesh());
    state.klyaksaLod.push(b.finish({ distance: 5000 }));
    yield;
    const accessPoint = (X, Y, h = 0) => {
      const n = dirAt(X, Y, R),
        alt = state.klyaksaGroundAt?.(X, Y) ?? bodyHeight(3, n.x, n.y, n.z) * R;
      return n.multiplyScalar(R + Math.max(4, alt + 0.35) + h);
    };
    const access = new Surface(accessPoint),
      accessPoints = harbourAccess(city, coast),
      roadside = new Batches(body, R, accessPoint, env),
      cables = [];
    const sourcePole = (state.klyaksaUtilityGraphs?.get(city.id)?.nodes || [])
      .filter((n) => n.kind !== "house")
      .sort(
        (a, b) =>
          Math.hypot(
            city.at[0] + a.x - accessPoints[0][0],
            city.at[1] + a.y - accessPoints[0][1],
          ) -
          Math.hypot(
            city.at[0] + b.x - accessPoints[0][0],
            city.at[1] + b.y - accessPoints[0][1],
          ),
      )[0];
    let accumulated = 0,
      nextPole = 20,
      previousPole = sourcePole
        ? [city.at[0] + sourcePole.x, city.at[1] + sourcePole.y, 1, 0, 10.39]
        : null;
    for (let k = 1; k < accessPoints.length; k++) {
      if (k % 120 === 0) yield;
      const A = accessPoints[k - 1],
        B = accessPoints[k],
        len = Math.hypot(B[0] - A[0], B[1] - A[1]),
        nx = -(B[1] - A[1]) / len,
        ny = (B[0] - A[0]) / len;
      state.klyaksaReservations
        ?.get(city.id)
        ?.mark(A[0] - city.at[0], A[1] - city.at[1], 18);
      access.strip(A, B, 12, 0, 0x38474c);
      access.strip(A, B, 0.18, 0.02, 0xe4d8a9, -5.4);
      access.strip(A, B, 0.18, 0.02, 0xe4d8a9, 5.4);
      if (Math.floor(accumulated / 7) % 2 === 0)
        access.strip(A, B, 0.2, 0.025, 0xe4d8a9);
      accumulated += len;
      if (accumulated >= nextPole) {
        const p = [A[0] + nx * 8, A[1] + ny * 8];
        roadside.add("port-road-pole", pole, ...p, 0, 1, Math.atan2(ny, nx));
        if (previousPole)
          for (let phase = -1; phase <= 1; phase++) {
            let last = null;
            for (let j = 0; j <= 10; j++) {
              const t = j / 10,
                X =
                  previousPole[0] +
                  (p[0] - previousPole[0]) * t +
                  (previousPole[2] * (1 - t) + nx * t) * phase * 1.1,
                Y =
                  previousPole[1] +
                  (p[1] - previousPole[1]) * t +
                  (previousPole[3] * (1 - t) + ny * t) * phase * 1.1,
                point = accessPoint(
                  X,
                  Y,
                  (previousPole[4] ?? 8.08) * (1 - t) +
                    8.08 * t -
                    1.1 * 4 * t * (1 - t),
                );
              if (last) cables.push(last, point);
              last = point;
            }
          }
        previousPole = [...p, nx, ny];
        nextPole = accumulated + 45;
      }
    }
    yield; // Keep access triangulation and utility extension out of the sampling chunk.
    body.add(access.mesh());
    yield;
    buildPortWaterExtension(city, accessPoints, body, R, env, accessPoint);
    yield;
    state.klyaksaLod.push(roadside.finish({ distance: 4200 }));
    body.add(
      new T.LineSegments(
        new T.BufferGeometry().setFromPoints(cables),
        new T.LineBasicMaterial({ color: 0x303b42 }),
      ),
    );
    for (let k = 0; k < 8; k++) {
      if (k % 2 === 0) yield;
      const kind = k >= 6 ? "ship" : k % 2 ? "yacht" : "boat",
        p =
          k >= 6
            ? xy(210, k === 6 ? -135 : 135)
            : xy(40 + (k % 2) * 35, -87.5 + k * 35),
        n = dirAt(...p, R);
      if (bodyHeight(3, n.x, n.y, n.z) > -0.0002) continue;
      if (!vesselModels.has(kind)) vesselModels.set(kind, vesselGeometry(kind));
      const mesh = new T.Mesh(
        vesselModels.get(kind),
        new T.MeshStandardMaterial({
          vertexColors: false,
          color: 0xc2d4d3,
          roughness: 0.48,
          metalness: 0.2,
          side: T.DoubleSide,
        }),
      );
      // Reuse authored vertex colours with a standard material for a modest specular highlight.
      mesh.geometry.setAttribute("color", mesh.geometry.getAttribute("aCol"));
      mesh.material.vertexColors = true;
      body.add(mesh);
      const boat = {
        id: ships.length,
        name: `${city.name} · ${kind} ${k + 1}`,
        kind,
        mesh,
        x: p[0],
        y: p[1],
        heading: k >= 6 ? a + Math.PI / 2 : a,
        speed: 0,
        steer: 0,
        R,
        body,
      };
      mesh.userData.boat = boat;
      ships.push(boat);
      pose(boat, 0);
    }
    (state.klyaksaPorts ||= []).push({
      city: id,
      x,
      y,
      coast,
      quay: xy(-40, 0),
      access: [accessPoints[0], accessPoints[accessPoints.length - 1]],
      accessPoints,
    });
  }
  state.klyaksaBoats = ships;
  yield;
  yield* buildRiverSceneSteps(body, R, plan, env);
}

/** Synchronous compatibility entry point for geometry tests/exporters. */
export function buildWaterfronts(...args) {
  for (const _ of buildWaterfrontSteps(...args)) void _;
}

function waterLevel(x, y) {
  return riverContains(x, y) ? riverLevel(x) : 0;
}
function pose(b, t) {
  const n = dirAt(b.x, b.y, b.R),
    north = dirAt(b.x, b.y + 1, b.R)
      .addScaledVector(n, -dirAt(b.x, b.y + 1, b.R).dot(n))
      .normalize(),
    east = new T.Vector3().crossVectors(north, n).normalize();
  const f = east
      .clone()
      .multiplyScalar(Math.cos(b.heading))
      .addScaledVector(north, Math.sin(b.heading)),
    right = new T.Vector3().crossVectors(n, f).normalize();
  const matrix = new T.Matrix4().makeBasis(right, n, f);
  b.mesh.quaternion.setFromRotationMatrix(matrix);
  b.mesh.rotateZ(Math.sin(t * 1.8 + b.id) * 0.012);
  b.mesh.position
    .copy(n)
    .multiplyScalar(
      b.R + waterLevel(b.x, b.y) + 0.1 + Math.sin(t * 1.4 + b.id) * 0.08,
    );
}
export function startSailing(boat) {
  if (state.drive) return;
  state.clearInput();
  state.selected = null;
  state.flyAnim = null;
  state.drive = {
    marine: true,
    boat,
    camYaw: 0,
    camPitch: 0.28,
    camDistance: boat.kind === "ship" ? 115 : 23,
  };
  state.cameraMode = "drive";
  document.getElementById("info").style.display = "none";
}
export function stopSailing() {
  state.drive = null;
  state.cameraMode = "flight";
  state.cameraKeys.clear();
  state.flightVelocity.set(0, 0, 0);
}
export function blockedBerth(x, y, boat) {
  const margin = boat.kind === "ship" ? 46 : 6;
  for (const p of state.klyaksaPorts || []) {
    const co = Math.cos(p.coast.a),
      si = Math.sin(p.coast.a),
      u = (x - p.x) * co + (y - p.y) * si,
      v = -(x - p.x) * si + (y - p.y) * co;
    if (u > -80 - margin && u < margin && Math.abs(v) < 200 + margin)
      return true;
    if (u > -margin && u < 95 + margin)
      for (let j = -2; j <= 2; j++)
        if (Math.abs(v - j * 35) < 3.5 + margin) return true;
  }
  const halfWidth = boat.kind === "ship" ? 9 : 2,
    co = Math.abs(Math.cos(boat.heading)),
    si = Math.abs(Math.sin(boat.heading)),
    extentX = co * margin + si * halfWidth,
    extentY = si * margin + co * halfWidth;
  if (
    (state.klyaksaRiverPiers || []).some(
      (p) =>
        Math.abs(x - p.x) < p.width / 2 + extentX &&
        Math.abs(y - p.y) < p.depth / 2 + extentY,
    )
  )
    return true;
  return (state.klyaksaBoats || []).some(
    (b) =>
      b !== boat &&
      Math.hypot(x - b.x, y - b.y) < margin + (b.kind === "ship" ? 46 : 6),
  );
}
export function vesselWaterClearance(boat, x = boat.x, y = boat.y) {
  const ship = boat.kind === "ship",
    draft = ship ? 4.5 : 1.8,
    co = Math.cos(boat.heading),
    si = Math.sin(boat.heading);
  for (const [forward, side] of [
    [0, 0],
    [ship ? 49 : 5, 0],
    [ship ? -41 : -5, 0],
    [0, ship ? 9 : 2],
    [0, ship ? -9 : -2],
  ]) {
    const X = x + co * forward - si * side,
      Y = y + si * forward + co * side,
      n = dirAt(X, Y, boat.R);
    if (
      Math.abs(X) < 1100 &&
      riverContains(X, Y) &&
      Math.abs(Y - riverCentre(X)) > riverWidth(X) - 4.5
    )
      return false;
    if (bodyHeight(3, n.x, n.y, n.z) * boat.R >= waterLevel(X, Y) - draft)
      return false;
  }
  return true;
}
export function stepBoat(b, input, dt) {
  const thrust = (input.forward ? 1 : 0) - (input.back ? 0.45 : 0);
  b.speed +=
    (thrust * (b.kind === "ship" ? 0.8 : 3.5) -
      b.speed * 0.1 -
      b.speed * Math.abs(b.speed) * 0.018) *
    dt;
  b.steer +=
    ((input.left ? 1 : 0) - (input.right ? 1 : 0) - b.steer) *
    Math.min(1, dt * 4);
  b.heading += b.steer * b.speed * (b.kind === "ship" ? 0.008 : 0.035) * dt;
  const reach = state.klyaksaRiverFlow,
    current =
      reach && riverContains(b.x, b.y)
        ? reach.flow.sample(b.x - reach.source).speed
        : 0,
    slope = (riverCentre(b.x + 1) - riverCentre(b.x - 1)) / 2,
    scale = 1 / Math.hypot(1, slope);
  const x = b.x + (Math.cos(b.heading) * b.speed + current * scale) * dt,
    y = b.y + (Math.sin(b.heading) * b.speed + current * scale * slope) * dt;
  if (vesselWaterClearance(b, x, y) && !blockedBerth(x, y, b)) {
    b.x = x;
    b.y = y;
  } else b.speed *= Math.exp(-12 * dt);
}
export function updateMarine(now) {
  if (!state.klyaksaBoats || state.activeBody !== 3) return;
  const dt = Math.min(
    0.05,
    Math.max(0, (now - (state.marineAt || now)) / 1000),
  );
  state.marineAt = now;
  updateRiverFlow(dt);
  const drive = state.drive;
  if (drive?.marine) {
    const b = drive.boat,
      keys = state.cameraKeys;
    stepBoat(
      b,
      {
        forward: keys.has("w") || keys.has("arrowup"),
        back: keys.has("s") || keys.has("arrowdown"),
        left: keys.has("a") || keys.has("arrowleft"),
        right: keys.has("d") || keys.has("arrowright"),
      },
      dt,
    );
    pose(b, now / 1000);
    const n = bodyDirectionToWorld(3, b.mesh.position.clone().normalize()),
      f = bodyDirectionToWorld(
        3,
        new T.Vector3(0, 0, 1).applyQuaternion(b.mesh.quaternion),
      ).applyAxisAngle(n, drive.camYaw),
      target = bodyPointToWorld(3, b.mesh.position).addScaledVector(n, 3),
      cam = target
        .clone()
        .addScaledVector(f, -Math.cos(drive.camPitch) * drive.camDistance)
        .addScaledVector(n, Math.sin(drive.camPitch) * drive.camDistance + 3);
    state.camera.position.lerp(cam, drive.ready ? 1 - Math.exp(-8 * dt) : 1);
    state.camera.up.copy(n);
    state.controls.target.copy(target);
    state.camera.lookAt(target);
    drive.ready = true;
    document.getElementById("drive-speed").textContent = Math.round(
      Math.abs(b.speed) * 3.6,
    );
    document.getElementById("drive-rpm").textContent =
      `${Math.round(700 + Math.abs(b.speed) * 230)} RPM`;
    document.getElementById("drive-gear").textContent =
      b.speed < -0.1 ? "R" : "D";
    document.getElementById("drive-surface").textContent = "KLYAKSA · WATER";
    document.getElementById("rpm-fill").style.width =
      Math.min(100, 20 + Math.abs(b.speed) * 5) + "%";
  }
  for (const b of state.klyaksaBoats)
    if (drive?.boat !== b) pose(b, now / 1000);
  const bridge = state.klyaksaDrawbridge;
  if (bridge) {
    const near = state.klyaksaBoats.some(
      (b) => Math.hypot(b.x - bridge.x, b.y - bridge.y) < 160,
    );
    bridge.open += (Number(near) * 1.05 - bridge.open) * Math.min(1, dt * 0.8);
    for (const { hinge, sign } of bridge.hinges)
      hinge.rotation.x = sign * bridge.open;
  }
}
