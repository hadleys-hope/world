import { createPlacement } from "./placement.js";
import { roadElevation } from "./streets.js";
import {
  roadNetwork,
  createVehicle,
  retargetVehicle,
  advanceVehicle,
  updateTrafficSignals,
} from "./traffic.js";
import { bridgeLift } from "./geography.js";
/** Read-only presentation of existing facilities, tank levels and rover poses. */
import * as T from "three";
import { state } from "../../state.js";
import { bodyHeight } from "../../geometry/noise.js";
import { dirAt } from "../klyaksa.js";
import {
  Batches,
  Model,
  pole,
  car,
  palette,
  antenna,
  planYaw,
  lettering,
} from "./kit.js";
import { civicGeometry } from "./buildings.js";
import { Surface } from "./streets.js";
function valve(m, x, y, z, r = 0.45) {
  const g = new T.TorusGeometry(r, 0.055, 5, 12)
    .rotateX(Math.PI / 2)
    .translate(x, y, z);
  m.parts.push([g, 0xcda76b]);
  m.beam([x - r, y, z], [x + r, y, z], 0.035, 0xcda76b).beam(
    [x, y, z - r],
    [x, y, z + r],
    0.035,
    0xcda76b,
  );
}
export function transformerGeometry() {
  const m = new Model()
    .box(0, 1.8, 0, 3.8, 3.2, 2.7, palette.metal)
    .box(0, 0.25, 0, 5, 0.5, 3.5, palette.concrete);
  for (let k = 0; k < 12; k++) {
    m.box(-2.15 + k * 0.39, 1.7, -1.65, 0.12, 2.8, 0.45, palette.dark);
    m.box(-2.15 + k * 0.39, 1.7, 1.65, 0.12, 2.8, 0.45, palette.dark);
  }
  for (const x of [-1.25, 0, 1.25]) {
    m.cyl(x, 4.15, 0, 0.16, 1.4, palette.white, 0.12, 8);
    for (let y = 3.65; y < 4.7; y += 0.2)
      m.cyl(x, y, 0, 0.24, 0.06, palette.white, 0.24, 8);
  }
  m.cyl(0, 4.5, -1.1, 0.6, 2.5, palette.metal);
  lettering(m, "GRID", 0, 2, 1.82, 0.09);
  return m.finish();
}
function transformerFeed(distance = 8) {
  const m = new Model();
  for (let phase = -1; phase <= 1; phase++) {
    const A = [phase * 1.25, 4.85, 0],
      B = [distance + phase * 1.1, 10.49, 0],
      mid = [(A[0] + B[0]) / 2, 6.85, 0];
    m.beam(A, mid, 0.045, palette.dark).beam(mid, B, 0.045, palette.dark);
  }
  return m.finish();
}
function reactorGeometry() {
  const m = new Model();
  m.box(-12, 10, 0, 24, 20, 30, 0xacaeaa)
    .box(13, 7, 0, 26, 14, 40, 0x879996)
    .box(13, 14.25, 0, 27, 0.5, 41, palette.dark);
  const dome = new T.SphereGeometry(
    12,
    20,
    10,
    0,
    Math.PI * 2,
    0,
    Math.PI / 2,
  ).translate(-12, 20, 0);
  m.parts.push([dome, 0xc6c9c1]);
  for (let x = 2; x < 25; x += 4) {
    m.box(x, 8, 20.05, 2.8, 9, 0.12, palette.glass);
    m.box(x, 12, -20.08, 2.8, 2, 0.12, palette.dark);
    for (let z = -16; z <= 16; z += 8)
      m.cyl(x, 14.9, z, 0.85, 0.8, palette.metal);
  }
  for (const z of [-24, 24]) {
    m.beam([-25, 3, z], [25, 3, z], 0.65, 0x899a9a);
    for (const x of [-23, -8, 8, 23]) {
      m.box(x, 1.4, z, 0.45, 2.8, 0.5, palette.concrete);
      valve(m, x, 3.6, z, 0.6);
    }
    m.beam([25, 3, z], [25, 12, z], 0.65, 0x899a9a).beam(
      [25, 12, z],
      [15, 12, z * 0.75],
      0.65,
      0x899a9a,
    );
  }
  for (const x of [-28, -22]) {
    m.cyl(x, 15, -24, 0.65, 30, palette.white, 0.45, 10);
    m.cyl(x, 29, -24, 0.7, 1.5, 0xb55343);
  }
  for (const x of [-8, 4, 16])
    m.box(x, 1.8, 20.18, 3.6, 3.6, 0.13, palette.dark);
  for (let h = 2; h < 19; h += 0.45)
    m.box(-24.15, h, 9, 0.08, 0.06, 1, palette.metal);
  m.beam([-24.4, 2, 8.45], [-24.4, 20, 8.45], 0.05).beam(
    [-24.4, 2, 9.55],
    [-24.4, 20, 9.55],
    0.05,
  );
  lettering(m, "KLYAKSA POWER", 0, 17, 15.08, 0.15);
  return m.finish();
}
function coolingTower() {
  const m = new Model(),
    p = [];
  for (let i = 0; i <= 12; i++) {
    const y = i * 2.6,
      r = 5.8 + 3.5 * ((y - 20) / 22) ** 2;
    p.push(new T.Vector2(r, y + 2));
  }
  m.parts.push([new T.LatheGeometry(p, 20), 0xadb5b0]);
  for (let i = 0; i < 12; i++) {
    const a = (i * Math.PI) / 6;
    m.beam(
      [Math.cos(a) * 8, 0, Math.sin(a) * 8],
      [Math.cos(a) * 7.4, 3, Math.sin(a) * 7.4],
      0.24,
      palette.concrete,
    );
  }
  m.cyl(0, 0.2, 0, 9, 0.4, palette.concrete, 9, 20);
  return m.finish();
}
function waterTowerFrame() {
  const m = new Model();
  for (const x of [-5.5, 5.5])
    for (const z of [-5.5, 5.5]) {
      m.box(x, 0.15, z, 2, 0.3, 2, palette.concrete);
      m.beam([x, 0, z], [x * 0.85, 20.1, z * 0.85], 0.28, palette.metal);
    }
  for (const h of [6, 12, 18]) {
    for (const s of [-1, 1]) {
      m.beam([-5.5, h, s * 5.5], [5.5, h, s * 5.5], 0.1)
        .beam([s * 5.5, h, -5.5], [s * 5.5, h, 5.5], 0.1)
        .beam([-5.5, h - 6, s * 5.5], [5.5, h, s * 5.5], 0.09)
        .beam([s * 5.5, h - 6, -5.5], [s * 5.5, h, 5.5], 0.09);
    }
  }
  m.cyl(0, 20, 0, 8, 0.3, palette.metal, 8, 24)
    .cyl(0, 28.1, 0, 7.6, 0.4, palette.white, 7.2, 24)
    .cyl(0, 28.55, 0, 7.2, 0.5, palette.white, 5.8, 24);
  for (let k = 0; k < 24; k++) {
    const a = (k * Math.PI) / 12,
      x = Math.cos(a) * 7.8,
      z = Math.sin(a) * 7.8;
    m.cyl(x, 20.6, z, 0.04, 1.2);
    m.beam(
      [x, 21.2, z],
      [
        Math.cos(a + Math.PI / 12) * 7.8,
        21.2,
        Math.sin(a + Math.PI / 12) * 7.8,
      ],
      0.04,
    );
  }
  m.beam([5.8, 0.6, 3], [5.8, 20.4, 3], 0.33, 0x4b9299).beam(
    [5.8, 20.4, 3],
    [0, 20.4, 0],
    0.33,
    0x4b9299,
  );
  valve(m, 5.8, 2.4, 3, 0.58);
  m.beam([5.8, 2.8, 3], [0, 2.8, 0], 0.33, 0x4b9299);
  for (let h = 0.5; h <= 21; h += 0.35)
    m.box(-6.35, h, 0, 0.08, 0.05, 0.9, palette.metal);
  m.beam([-6.35, 0.3, -0.5], [-6.35, 21, -0.5], 0.06).beam(
    [-6.35, 0.3, 0.5],
    [-6.35, 21, 0.5],
    0.06,
  );
  for (let h = 3; h <= 21; h += 1.2) {
    const g = new T.TorusGeometry(0.66, 0.035, 4, 10)
      .rotateX(Math.PI / 2)
      .translate(-6.6, h, 0);
    m.parts.push([g, palette.metal]);
  }
  lettering(m, "WATER", 0, 23.8, 7.2, 0.25);
  return m.finish();
}
function driveCurve(points) {
  const result = [points[0]];
  for (let i = 1; i < points.length - 1; i++) {
    const a = points[i - 1],
      b = points[i],
      c = points[i + 1],
      l1 = Math.hypot(b[0] - a[0], b[1] - a[1]),
      l2 = Math.hypot(c[0] - b[0], c[1] - b[1]),
      r = Math.min(8, l1 / 3, l2 / 3);
    if (r < 0.05) {
      result.push(b);
      continue;
    }
    const A = [
        b[0] + ((a[0] - b[0]) * r) / l1,
        b[1] + ((a[1] - b[1]) * r) / l1,
      ],
      C = [b[0] + ((c[0] - b[0]) * r) / l2, b[1] + ((c[1] - b[1]) * r) / l2];
    result.push(A);
    for (let k = 1; k <= 6; k++) {
      const t = k / 6;
      result.push([
        (1 - t) ** 2 * A[0] + 2 * (1 - t) * t * b[0] + t * t * C[0],
        (1 - t) ** 2 * A[1] + 2 * (1 - t) * t * b[1] + t * t * C[1],
      ]);
    }
  }
  result.push(points.at(-1));
  return result;
}
function nearAccess(x, y, roads) {
  return roads.some((r) =>
    r.points.slice(1).some((B, i) => {
      const A = r.points[i],
        dx = B[0] - A[0],
        dy = B[1] - A[1],
        t = Math.max(
          0,
          Math.min(
            1,
            ((x - A[0]) * dx + (y - A[1]) * dy) / (dx * dx + dy * dy || 1),
          ),
        );
      return (
        Math.hypot(x - A[0] - dx * t, y - A[1] - dy * t) <
        (r.width || 8) / 2 + 3
      );
    }),
  );
}
export function buildIndustry(c, body, R, env) {
  const worldPoint = createPlacement(R),
    point = (x, y, h = 0) => worldPoint(c.at[0] + x, c.at[1] + y, h),
    b = new Batches(body, R, point, env),
    drive = new Surface(point);
  const foundation = (x, y, w = 76, d = 70) =>
    b.add(
      `industrial-pad-${w}-${d}`,
      () => new Model().box(0, -0.12, 0, w, 0.24, d, 0x778583).finish(),
      x,
      y,
    );
  for (const [key, xy] of Object.entries(c.facilities || {})) {
    const [x, y] = xy;
    if (key === "tower_pos") continue;
    if (key === "solar_pos") {
      const panel = () => {
        const m = new Model().box(0, 0.8, 0, 0.13, 1.6, 0.13, palette.metal);
        for (let i = 0; i < 18; i++) {
          const row = Math.floor(i / 6),
            col = i % 6;
          m.box(
            (col - 2.5) * 1.5,
            2 + row * 0.3,
            (row - 1) * 2,
            1.45,
            0.1,
            1.94,
            0x234e70,
          );
          for (let k = 0; k < 5; k++)
            m.box(
              (col - 2.5) * 1.5 - 0.6 + k * 0.3,
              2.06 + row * 0.3,
              (row - 1) * 2,
              0.025,
              0.02,
              1.9,
              0x7dacc8,
            );
        }
        return m.finish();
      };
      for (let i = 0; i < 24; i++)
        b.add(
          "photovoltaic-rack",
          panel,
          x + (i % 6) * 11 - 27.5,
          y + Math.floor(i / 6) * 10 - 15,
        );
      continue;
    }
    const reactor = key === "reactor_pos",
      water = key === "water_plant_pos";
    foundation(x, reactor ? y - 20 : y, reactor ? 110 : 90, reactor ? 146 : 86);
    if (reactor) {
      b.add("pressurised-reactor-and-turbine-hall", reactorGeometry, x, y);
      for (const dx of [-14, 14])
        b.add("natural-draft-cooling-tower", coolingTower, x + dx, y - 58);
      for (const dy of [-10, 0, 10])
        b.add("reactor-switchgear", transformerGeometry, x + 35, y + dy);
      b.add("reactor-grid-feed", () => transformerFeed(5), x + 35, y + 10);
    } else {
      b.add(
        water ? "water-treatment-hall" : "sludge-recovery-works",
        () => civicGeometry(water ? "water" : "garage"),
        x,
        y,
      );
      for (const dx of [-22, 0, 22])
        b.add(
          "industrial-filter-vessel",
          () => {
            const m = new Model()
              .cyl(0, 4, 0, 4.6, 8, 0x78a0a6, 4.6, 16)
              .cyl(0, 8.2, 0, 4.8, 0.4, palette.white, 4.8, 16);
            m.beam([6, 1.3, 0], [6, 2.8, 0], 0.28)
              .beam([-6, 1.3, 0], [6, 1.3, 0], 0.28)
              .beam([0, 1.3, 0], [0, 8.5, 0], 0.22);
            for (let h = 0; h < 8; h += 0.35)
              m.box(4.8, h, 0, 0.08, 0.05, 0.9, palette.metal);
            valve(m, 5.5, 1.6, 0);
            return m.finish();
          },
          x + dx,
          y - 29,
        );
    }
    if (!reactor)
      b.add(
        "process-water-header",
        () =>
          new Model()
            .beam([-28, 2.8, 29], [28, 2.8, 29], 0.28, 0x4f8791)
            .finish(),
        x,
        y,
      );
    for (let i = 0; i < 4; i++)
      b.add(
        "plant-parked-service-truck",
        () => car(true),
        x - 26 + i * 7,
        y + 33,
      );
    const fence = () =>
      new Model()
        .box(0, 1.2, 0, 0.09, 2.4, 0.09, palette.metal)
        .box(0, 0.5, 0, 5, 0.045, 0.04, palette.metal)
        .box(0, 1.3, 0, 5, 0.045, 0.04, palette.metal)
        .box(0, 2.3, 0, 5, 0.045, 0.04, palette.metal)
        .finish();
    const side = reactor ? 53 : 43,
      rear = reactor ? -90 : -41,
      access = c.facility_access?.[key],
      sideX = x + (access?.x < x ? -1 : 1) * (side + 8),
      path = access
        ? driveCurve([
            [access.x, access.y],
            [sideX, access.y],
            [sideX, y + 49],
            [x, y + 49],
            [x, y + 25],
          ])
        : [],
      gaps = [...(c.service_roads || []), { points: path, width: 8 }];
    for (let i = -Math.floor(side / 5); i <= Math.floor(side / 5); i++) {
      if (!nearAccess(x + i * 5, y + rear, gaps))
        b.add("plant-fence", fence, x + i * 5, y + rear);
      if (Math.abs(i) > 1 && !nearAccess(x + i * 5, y + 41, gaps))
        b.add("plant-fence", fence, x + i * 5, y + 41);
    }
    for (let z = rear; z <= 41; z += 5)
      for (const sign of [-1, 1])
        if (!nearAccess(x + sign * side, y + z, gaps))
          b.add(
            "plant-fence",
            fence,
            x + sign * side,
            y + z,
            0,
            1,
            Math.PI / 2,
          );
    if (access) {
      for (let i = 1; i < path.length; i++) {
        drive.strip(path[i - 1], path[i], 8, 0.24, 0x39444b);
        drive.strip(path[i - 1], path[i], 0.13, 0.27, 0xd2c9a4);
      }
      b.add(
        "industrial-open-barrier",
        () =>
          new Model()
            .box(-4, 0.8, 0, 0.5, 1.6, 0.5, 0xd6bb77)
            .box(-4, 3.5, 0, 0.16, 5, 0.16, palette.white)
            .box(5, 1.5, 1, 2, 3, 2.5, palette.concrete)
            .box(5, 2.1, 2.3, 1.7, 0.9, 0.06, palette.glass)
            .finish(),
        x,
        y + 41,
      );
    }
  }
  const transformer = (c.parcels || []).find((p) => p.kind === "transformer");
  if (transformer) {
    foundation(transformer.x, transformer.y, 50, 40);
    b.add(
      "substation-grid-feed",
      () => transformerFeed(8),
      transformer.x + 14,
      transformer.y,
    );
    for (const x of [-14, 0, 14])
      b.add(
        "city-transformer",
        transformerGeometry,
        transformer.x + x,
        transformer.y,
      );
    b.add(
      "substation-control-room",
      () =>
        new Model()
          .box(0, 2, 0, 15, 4, 8, palette.concrete)
          .box(0, 4.15, 0, 16, 0.3, 9, palette.metal)
          .box(0, 1.2, 4.1, 1.4, 2.4, 0.1, palette.dark)
          .finish(),
      transformer.x,
      transformer.y + 14,
    );
  }
  const q = (c.parcels || []).find((p) => p.kind === "water") || {
    x: 25,
    y: -60,
  };
  foundation(q.x, q.y, 58, 50);
  b.add("braced-water-tower", waterTowerFrame, q.x, q.y);
  b.add(
    "tower-pumping-and-valve-house",
    () => {
      const m = new Model()
        .box(0, 2.4, 0, 13, 4.8, 9, palette.concrete)
        .box(0, 4.95, 0, 14, 0.3, 10, palette.metal)
        .box(0, 1.3, 4.56, 1.6, 2.6, 0.12, palette.dark);
      for (const x of [-4, 4]) m.box(x, 3, 4.58, 2, 1.4, 0.1, palette.glass);
      for (const z of [-2, 2]) {
        m.beam([-6.8, 2.8, z], [-19, 2.8, z], 0.3, 0x4f8791);
        valve(m, -10, 3.2, z);
        m.beam([-19, 2.8, z], [-22, 2.8, 0], 0.3, 0x4f8791);
      }
      return m.finish();
    },
    q.x + 22,
    q.y,
  );
  b.finish();
  body.add(drive.mesh());
  const tank = new T.Group(),
    P = point(q.x, q.y),
    normal = P.clone().normalize();
  tank.position.copy(P);
  tank.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), normal);
  const shell = new T.Mesh(
    new T.CylinderGeometry(7.05, 7.05, 7.8, 24, 1, true),
    new T.MeshPhysicalMaterial({
      color: 0xb9d9df,
      transparent: true,
      opacity: 0.2,
      roughness: 0.24,
      metalness: 0.2,
      depthWrite: false,
      side: T.DoubleSide,
    }),
  );
  shell.position.y = 24;
  tank.add(shell);
  const fill = new T.Mesh(
    new T.CylinderGeometry(6.85, 6.85, 1, 24),
    new T.MeshStandardMaterial({
      color: 0x318da4,
      roughness: 0.23,
      metalness: 0.3,
    }),
  );
  fill.position.y = 24;
  fill.scale.y = 7.8;
  tank.add(fill);
  tank.name = c.name + " · live elevated water reservoir";
  body.add(tank);
  (state.klyaksaTanks ||= new Map()).set(c.id, fill);
}
const _matrix = new T.Matrix4(),
  _quaternion = new T.Quaternion(),
  _scale = new T.Vector3(1, 1, 1),
  _up = new T.Vector3(0, 1, 0);
function nameSeed(name) {
  let n = 0;
  for (const ch of name) n = (n * 31 + ch.charCodeAt(0)) >>> 0;
  return n;
}
function mappedTarget(city, r) {
  if (r.visual_target) return r.visual_target;
  // Compatibility with older API data: choose corresponding visual house, never
  // treat old radial domain coordinates as a pose in the new street plan.
  let nearest = 0,
    distance = Infinity;
  for (let i = 0; i < city.houses; i++) {
    const d =
      ((city.sim_x || city.x)[i] - r.x) ** 2 +
      ((city.sim_y || city.y)[i] - r.y) ** 2;
    if (d < distance) {
      distance = d;
      nearest = i;
    }
  }
  return { x: city.x[nearest], y: city.y[nearest] };
}
export function syncCityVisuals(snapshot, body, R) {
  const groups = [[], []],
    now = performance.now(),
    point = createPlacement(R, state.klyaksaPlanData);
  state.klyaksaVehicleHistory ||= new Map();
  for (const c of snapshot.cities) {
    const city = state.klyaksaPlanData.cities.find((x) => x.id === c.id);
    if (!city) continue;
    const waterVisual = state.klyaksaWaterMaterials?.get(c.id);
    if (waterVisual)
      waterVisual.uniforms.uFlow.value = c.water?.tank_m3 > 0 ? 1 : 0;
    const fill = state.klyaksaTanks?.get(c.id);
    if (fill && c.water) {
      const h = Math.max(
        0.02,
        Math.min(1, c.water.tank_m3 / c.water.capacity_m3) * 7.8,
      );
      fill.scale.y = h;
      fill.position.y = 20.1 + h / 2;
    }
    const network = roadNetwork(city);
    for (const r of c.rovers || []) {
      const key = c.id + "/" + r.name,
        target = mappedTarget(city, r);
      let entry = state.klyaksaVehicleHistory.get(key);
      if (!entry) {
        const origin = r.visual_origin || target,
          motion = createVehicle(network, origin, nameSeed(key));
        if (!motion) continue;
        entry = {
          motion,
          city,
          point,
          quaternion: new T.Quaternion(),
          initial: true,
        };
        state.klyaksaVehicleHistory.set(key, entry);
      }
      entry.paused = !!c.paused;
      entry.moving = r.moving ?? (r.velocity > 0 || r.state !== "IDLE");
      entry.circulating = !!r.circulating;
      if (entry.circulating && !entry.motion.route.length) {
        const roads = network.edges,
          edge = roads[(entry.motion.seed++ * 17) % roads.length];
        retargetVehicle(entry.motion, {
          x: edge.b.point[0],
          y: edge.b.point[1],
        });
      } else if (entry.moving) retargetVehicle(entry.motion, target);
      groups[/sludge|waste|garbage/.test(r.kind) ? 1 : 0].push(entry);
    }
  }
  state.klyaksaVehicleBatches ||= [];
  for (let k = 0; k < 2; k++) {
    let batch = state.klyaksaVehicleBatches[k];
    if (!batch || batch.capacity < groups[k].length) {
      if (batch) {
        body.remove(batch.mesh);
        batch.mesh.geometry.dispose();
        batch.mesh.material.dispose();
      }
      const capacity = Math.max(
          16,
          2 ** Math.ceil(Math.log2(groups[k].length || 1)),
        ),
        g = car(k === 1);
      g.setAttribute("color", g.getAttribute("aCol"));
      const mesh = new T.InstancedMesh(
        g,
        new T.MeshStandardMaterial({ vertexColors: true, roughness: 0.65 }),
        capacity,
      );
      mesh.instanceMatrix.setUsage(T.DynamicDrawUsage);
      mesh.frustumCulled = false;
      body.add(mesh);
      batch = { mesh, capacity, at: now };
      state.klyaksaVehicleBatches[k] = batch;
    }
    batch.items = groups[k];
    batch.mesh.count = groups[k].length;
  }
  updateCityVehicles(now);
}
export function updateCityVehicles(now) {
  const dtClock = Math.min(
    0.15,
    Math.max(0, (now - (state.klyaksaTrafficAt ?? now)) / 1000),
  );
  state.klyaksaTrafficAt = now;
  const entries = (state.klyaksaVehicleBatches || []).flatMap(
    (b) => b.items || [],
  );
  if (!state.S?.paused && entries.some((v) => !v.paused))
    state.klyaksaTrafficClock = (state.klyaksaTrafficClock || 0) + dtClock;
  const clock = state.klyaksaTrafficClock || 0;
  updateTrafficSignals(clock);
  for (const entry of entries) {
    const v = entry.motion,
      sign =
        Math.cos(
          v.pose.heading -
            Math.atan2(
              v.anchor.edge.points.at(-1)[1] - v.anchor.edge.points[0][1],
              v.anchor.edge.points.at(-1)[0] - v.anchor.edge.points[0][0],
            ),
        ) >= 0
          ? 1
          : -1;
    let gap = Infinity;
    for (const other of entries) {
      const q = other.motion;
      if (
        q === v ||
        q.anchor.edge !== v.anchor.edge ||
        Math.cos(q.pose.heading - v.pose.heading) < 0.7
      )
        continue;
      const d = (q.anchor.distance - v.anchor.distance) * sign;
      if (d > 0) gap = Math.min(gap, d);
    }
    v.followGap = Math.max(0, gap - 7);
    v.followSpeed = Math.sqrt(2 * 3.5 * Math.max(0, gap - 9));
  }
  for (const batch of state.klyaksaVehicleBatches || []) {
    const dt = Math.min(0.15, Math.max(0, (now - batch.at) / 1000));
    batch.at = now;
    for (let i = 0; i < batch.items.length; i++) {
      const v = batch.items[i];
      if (v.circulating && !v.motion.route.length) {
        const edges = v.motion.network.edges,
          edge = edges[(v.motion.seed++ * 17) % edges.length];
        retargetVehicle(v.motion, { x: edge.b.point[0], y: edge.b.point[1] });
      }
      const pose = advanceVehicle(
          v.motion,
          v.paused || state.S?.paused ? 0 : dt,
          clock,
          v.moving || v.motion.route.length > 0,
        ),
        x = v.city.at[0] + pose.x,
        y = v.city.at[1] + pose.y,
        height = roadElevation(v.city, pose.edge.road, pose.x, pose.y);
      const position = v.point(x, y, 0.3 + height),
        normal = position.clone().normalize();
      _quaternion
        .setFromUnitVectors(_up, normal)
        .multiply(
          new T.Quaternion().setFromAxisAngle(
            _up,
            planYaw(v.point, x, y, pose.heading + Math.PI / 2),
          ),
        );
      if (v.initial) {
        v.quaternion.copy(_quaternion);
        v.initial = false;
      } else v.quaternion.slerp(_quaternion, 1 - Math.exp(-dt * 9));
      batch.mesh.setMatrixAt(
        i,
        _matrix.compose(position, v.quaternion, _scale),
      );
    }
    batch.mesh.instanceMatrix.needsUpdate = true;
  }
}
