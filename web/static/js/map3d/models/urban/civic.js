/** Reserved civic parcels: useful public space and service yards in every city.
 * All instances share geometry/materials and every parcel stays within the layout reservation. */
import * as T from "three";
import { state } from "../../state.js";
import { treeGeometry, lifeMaterial } from "../life.js";
import { Surface } from "./streets.js";
import {
  Batches,
  Model,
  bench,
  bin,
  pole,
  car,
  roofPlant,
  lettering,
  palette,
} from "./kit.js";
import { civicGeometry, civicRoofHeight, facadeMaterial } from "./buildings.js";

function fountain() {
  const m = new Model()
    .cyl(0, 0.3, 0, 3.4, 0.6, palette.concrete, 3.4, 20)
    .cyl(0, 0.63, 0, 3, 0.08, 0x589da6, 3, 20)
    .cyl(0, 1.2, 0, 0.35, 1.3, palette.white)
    .cyl(0, 1.9, 0, 1.4, 0.25, palette.white, 1.4, 14);
  for (let k = 0; k < 8; k++) {
    const a = (k * Math.PI) / 4;
    m.beam(
      [Math.cos(a) * 1.1, 1.9, Math.sin(a) * 1.1],
      [Math.cos(a) * 2.3, 0.75, Math.sin(a) * 2.3],
      0.025,
      0x83bac0,
    );
  }
  return m.finish();
}
function planter() {
  const m = new Model()
    .box(0, 0.35, 0, 3.2, 0.7, 1.8, 0xa7aba2)
    .box(0, 0.72, 0, 2.9, 0.1, 1.5, 0x4b543c);
  for (let k = 0; k < 12; k++) {
    const x = -0.95 + (k % 4) * 0.62,
      z = -0.45 + Math.floor(k / 4) * 0.44;
    m.cyl(x, 0.95, z, 0.05, 0.5, palette.green, 0.04, 4).cyl(
      x,
      1.22,
      z,
      0.16,
      0.09,
      [0xbd778b, 0xe2c56b, 0x877eb6][k % 3],
      0.12,
      5,
    );
  }
  return m.finish();
}
function bikeRack() {
  const m = new Model();
  for (let k = 0; k < 4; k++) {
    const x = (k - 1.5) * 0.65;
    m.beam([x, 0, -0.6], [x, 0.8, -0.6], 0.045)
      .beam([x, 0.8, -0.6], [x, 0.8, 0.6], 0.045)
      .beam([x, 0.8, 0.6], [x, 0, 0.6], 0.045);
  }
  return m.finish();
}
function pavilion() {
  const m = new Model().cyl(0, 0.2, 0, 4.5, 0.4, palette.white, 4.5, 8);
  for (let k = 0; k < 6; k++) {
    const a = (k * Math.PI) / 3;
    m.cyl(
      Math.cos(a) * 3.5,
      1.8,
      Math.sin(a) * 3.5,
      0.1,
      3.3,
      palette.white,
      0.1,
      6,
    );
  }
  m.cyl(0, 4, 0, 4.8, 1.2, 0x4d6b63, 0.6, 8);
  return m.finish();
}
function fuelCanopy() {
  const m = new Model()
    .box(0, 5.4, 0, 21, 0.7, 19, palette.white)
    .box(0, 5.47, 9.6, 21.2, 0.5, 0.25, 0x4d9996);
  for (const x of [-7, 7])
    for (const z of [-6, 6]) m.box(x, 2.6, z, 0.3, 5.2, 0.3, palette.metal);
  for (const x of [-4, 4])
    for (const z of [-4, 4]) {
      m.box(x, 0.14, z, 2.4, 0.28, 1.4, palette.white)
        .box(x, 1, z, 0.8, 1.5, 0.65, 0x528c89)
        .box(x, 1.3, z + 0.34, 0.56, 0.36, 0.035, palette.dark)
        .box(x, 1.36, z + 0.37, 0.42, 0.06, 0.025, 0x87d8b2);
      m.beam([x + 0.43, 1.65, z], [x + 0.83, 1.2, z], 0.05, palette.dark)
        .beam([x + 0.83, 1.2, z], [x + 0.73, 0.3, z], 0.05, palette.dark)
        .beam([x + 0.73, 0.3, z], [x + 0.4, 0.85, z], 0.05, palette.dark);
    }
  return m.finish();
}
function workshopLift() {
  const m = new Model().box(0, 0.12, 0, 4, 0.24, 6, palette.concrete);
  for (const x of [-1.4, 1.4]) {
    m.box(x, 1.7, 0, 0.25, 3.4, 0.4, 0x6b8f91)
      .box(x / 2, 0.8, 0, 1.7, 0.2, 0.3, palette.dark)
      .box(x, 0.05, 0, 0.8, 0.1, 1, palette.metal);
  }
  return m.finish();
}
function workshopTools() {
  const m = new Model()
    .box(-1, 0.65, 0, 1.8, 1.3, 0.8, 0xa54d3f)
    .box(1, 1.1, 0, 1.4, 0.12, 0.8, palette.metal)
    .cyl(2.2, 0.75, 0, 0.35, 1.5, palette.white);
  for (let k = 0; k < 5; k++)
    m.box(-1, 0.25 + k * 0.2, 0.41, 1.65, 0.025, 0.04, palette.dark);
  for (let k = 0; k < 3; k++)
    m.cyl(-2.5, 0.2 + k * 0.35, 0, 0.5, 0.3, palette.dark, 0.5, 10);
  return m.finish();
}
function signBoard(kind) {
  const m = new Model().box(0, 2.9, 0, 5.2, 1.2, 0.2, palette.dark);
  for (const x of [-2, 2]) m.box(x, 1.5, 0, 0.12, 3, 0.12, palette.metal);
  if (kind === "hospital")
    m.box(0, 2.9, 0.13, 0.24, 0.9, 0.1, 0xece8db).box(
      0,
      2.9,
      0.13,
      1.1,
      0.24,
      0.1,
      0xece8db,
    );
  else if (kind === "sector_service") {
    m.box(-1.5, 2.8, 0.13, 0.45, 0.65, 0.08, 0x8ad7c0).box(
      -1.2,
      3.05,
      0.13,
      0.4,
      0.2,
      0.08,
      0x8ad7c0,
    );
    for (let k = 0; k < 3; k++)
      m.box(0.3 + k * 0.6, 2.8, 0.13, 0.35, 0.12, 0.06, 0xe0b764);
  } else
    for (let k = -2; k <= 2; k++)
      m.box(k * 0.75, 2.9, 0.13, 0.4, 0.3, 0.06, palette.white);
  if (kind !== "hospital" && kind !== "sector_service") {
    // Caption is above the service icon at a readable pedestrian scale.
    const text =
      {
        bigtech: "TECH",
        government: "CITY HALL",
        coworking: "WORK",
        network: "NETWORK",
      }[kind] || kind.toUpperCase();
    m.box(0, 3.9, 0, 5.2, 0.85, 0.2, palette.dark);
    lettering(
      m,
      text,
      0,
      3.9,
      0.13,
      Math.min(0.1, 4.8 / (text.length * 6)),
      palette.white,
    );
  }
  return m.finish();
}
function ups() {
  const m = new Model()
    .box(0, 1.3, 0, 1.3, 2.6, 1.4, palette.metal)
    .box(0, 1.9, 0.72, 0.7, 0.4, 0.05, 0x78cca7);
  for (let i = 0; i < 8; i++)
    m.box(0, 0.3 + i * 0.12, 0.72, 1, 0.035, 0.04, palette.dark);
  return m.finish();
}
function addParcelSurface(surface, parcel, points, color) {
  const co = Math.cos(parcel.yaw || 0),
    si = Math.sin(parcel.yaw || 0);
  surface.quad(
    points.map(([u, v, h]) => [
      parcel.x + co * u - si * v,
      parcel.y + si * u + co * v,
      h,
    ]),
    color,
  );
}

export function* buildCivicDistrict(c, body, R, globalPoint, env) {
  const point = (x, y, h = 0) => globalPoint(c.at[0] + x, c.at[1] + y, h);
  const architecture = new Batches(body, R, point, env),
    detail = new Batches(body, R, point, env);
  const landscape = new Batches(body, R, point, env),
    ground = new Surface(point);
  const parcels = c.parcels || [
    ...(c.civic_plots || []),
    ...(c.parks || []),
    ...(c.sector_services || []),
  ];
  const summary = {
    city: c.id,
    parks: 0,
    sectorServices: 0,
    civic: [],
    roofs: [],
  };
  state.klyaksaSitesVisual ||= [];
  state.klyaksaTelecomRoofs ||= [];
  for (const p of parcels) {
    yield;
    let yaw = p.yaw || 0;
    if (p.access && p.kind !== "park") {
      const access = Array.isArray(p.access)
        ? p.access
        : [p.access.x, p.access.y];
      const normalDistance =
        -(access[0] - p.x) * Math.sin(yaw) + (access[1] - p.y) * Math.cos(yaw);
      // Workshop doors and the clear forecourt face the connected street, not a random plot edge.
      if (normalDistance > 0) yaw += Math.PI;
    }
    const frame = { ...p, yaw },
      co = Math.cos(yaw),
      si = Math.sin(yaw),
      w = p.w || 76,
      d = p.d || 66;
    const xy = (u, v) => [p.x + co * u - si * v, p.y + si * u + co * v];
    const add = (b, key, model, u, v, h = 0.35, size = 1, angle = 0) => {
      const q = xy(u, v);
      b.add(key, model, q[0], q[1], h, size, yaw + angle);
    };
    const quad = (u0, v0, u1, v1, h, color) =>
      addParcelSurface(
        ground,
        frame,
        [
          [u0, v0, h],
          [u1, v0, h],
          [u0, v1, h],
          [u1, v1, h],
        ],
        color,
      );
    const path = (a, b, width, color = 0xb6b09a, h = 0.22) =>
      ground.strip(xy(...a), xy(...b), width, h, color);
    const benches = (list) =>
      list.forEach(([u, v, angle = 0]) => {
        add(detail, "civic-bench", bench, u, v, 0.3, 1, angle);
        add(detail, "civic-bin", bin, u + 2, v, 0.3);
      });
    if (p.kind === "park") {
      summary.parks++;
      quad(-w / 2 + 1, -d / 2 + 1, w / 2 - 1, d / 2 - 1, 0.1, 0x668655);
      path([-w / 2 + 2, 0], [w / 2 - 2, 0], 3.3);
      path([0, -d / 2 + 2], [0, d / 2 - 2], 3.3);
      for (let k = 0; k < 32; k++) {
        const a = (k * Math.PI) / 16,
          b = ((k + 1) * Math.PI) / 16;
        path(
          [Math.cos(a) * w * 0.36, Math.sin(a) * d * 0.35],
          [Math.cos(b) * w * 0.36, Math.sin(b) * d * 0.35],
          1.8,
        );
        path(
          [Math.cos(a) * w * 0.45, Math.sin(a) * d * 0.44],
          [Math.cos(b) * w * 0.45, Math.sin(b) * d * 0.44],
          1.8,
          0x577f81,
          0.2,
        );
      }
      for (const u of [-w * 0.33, w * 0.33])
        for (const v of [-d * 0.32, d * 0.32]) {
          add(
            landscape,
            "civic-tree",
            () => treeGeometry("broad"),
            u,
            v,
            0.12,
            1.15 + (summary.parks % 3) * 0.18,
          );
          add(
            detail,
            "civic-planter",
            planter,
            u * 0.52,
            v * 0.55,
            0.2,
            1,
            Math.PI / 2,
          );
        }
      const variant = (summary.parks + Number(c.id.slice(1))) % 3;
      if (variant === 0) add(detail, "civic-fountain", fountain, -10, 9, 0.2);
      if (variant === 1) add(detail, "civic-pavilion", pavilion, -10, 9, 0.2);
      if (variant === 2) {
        quad(-17, 6, -4, 17, 0.28, 0x987953);
        add(
          detail,
          "civic-stage",
          () => new Model().box(0, 0.5, 0, 9, 1, 5, palette.wood).finish(),
          -11,
          13,
          0.15,
        );
      }
      benches([
        [-8, -3],
        [7, 3, Math.PI],
        [-w * 0.4, 5, Math.PI / 2],
        [w * 0.4, -5, -Math.PI / 2],
        [7, d * 0.38, Math.PI],
        [-7, -d * 0.38],
      ]);
      for (const u of [-w * 0.4, w * 0.4])
        add(detail, "civic-lamp", pole, u, -3, 0.15, 0.65);
      add(detail, "civic-bike-rack", bikeRack, 6, -d * 0.4, 0.3);
    } else if (p.kind === "sector_service") {
      summary.sectorServices++;
      quad(-w / 2, -d / 2, w / 2, d / 2, 0.17, 0x424b4e);
      add(
        architecture,
        "civic-garage",
        () => civicGeometry("garage"),
        -17,
        15,
        0.35,
      );
      add(architecture, "civic-fuel", fuelCanopy, 19, 15, 0.3);
      add(detail, "civic-garage-HVAC", roofPlant, -20, 15, 9.4);
      add(detail, "civic-service-lift", workshopLift, -17, -0.5, 0.2);
      add(detail, "civic-service-tools", workshopTools, -28, 2, 0.2);
      for (let k = 0; k < 9; k++) {
        const u = -30 + k * 7.3;
        path([u, -29], [u, -22], 0.12, 0xe5dfbe, 0.2);
        path([u, -13], [u, -6], 0.12, 0xe5dfbe, 0.2);
        if (k % 3 !== 1 && Math.abs(u + 2.6) > 6)
          add(detail, "civic-parked", car, u + 2.6, -25.5, 0.24, 0.93);
        if (k % 2 === 0 && Math.abs(u) > 6)
          add(detail, "civic-parked", car, u + 2.5, -9.5, 0.24, 0.93, Math.PI);
      }
      for (let k = 0; k < 4; k++)
        path(
          [-w / 2 + k * 20, -18],
          [-w / 2 + k * 20 + 8, -18],
          0.13,
          0xe1dbbc,
          0.2,
        );
      for (const u of [-w / 2 + 3, w / 2 - 3])
        add(detail, "civic-yard-lamp", pole, u, -17, 0.2);
      add(
        detail,
        "civic-service-sign",
        () => signBoard("sector_service"),
        28,
        -31,
        0.2,
      );
      add(detail, "civic-bike-rack", bikeRack, -31, -31, 0.2);
      benches([
        [-28, 28, Math.PI],
        [17, 28, Math.PI],
      ]);
    } else if (!["water", "transformer"].includes(p.kind)) {
      summary.civic.push(p.kind);
      const roof = civicRoofHeight[p.kind] || 9;
      quad(-w / 2, -d / 2, w / 2, d / 2, 0.15, 0xa4a89e);
      add(
        architecture,
        "civic-" + p.kind,
        () => civicGeometry(p.kind),
        0,
        5,
        0.35,
      );
      const tall = ["bank", "bigtech", "government"].includes(p.kind);
      const anchor =
        p.kind === "bigtech"
          ? [-10, 4]
          : p.kind === "bank"
            ? [-2.5, 5]
            : [0, 5];
      if (tall || p.kind === "network") {
        const q = xy(...anchor),
          record = {
            cityId: c.id,
            kind: p.kind,
            x: c.at[0] + q[0],
            y: c.at[1] + q[1],
            h: roof + 0.35,
          };
        state.klyaksaTelecomRoofs.push(record);
        summary.roofs.push(record);
      }
      if (!["church", "sports"].includes(p.kind))
        add(
          detail,
          "civic-HVAC",
          roofPlant,
          anchor[0] + 3,
          anchor[1],
          roof + 0.4,
          1.1,
        );
      for (const u of [-w / 2 + 3, w / 2 - 3])
        for (const v of [-d / 2 + 3, d / 2 - 3]) {
          add(detail, "civic-planter", planter, u, v, 0.2);
          add(detail, "civic-lamp", pole, u, v + 3, 0.2, 0.75);
        }
      benches([
        [-w * 0.34, -d * 0.3],
        [w * 0.34, -d * 0.3],
      ]);
      for (let k = -3; k <= 3; k++) {
        path(
          [k * 4.2, -d / 2 + 2],
          [k * 4.2, -d / 2 + 8],
          0.14,
          0xf0e9cb,
          0.21,
        );
        if (k % 2 === 0 && Math.abs(k * 4.2 + 1.9) > 4 && p.kind !== "hospital")
          add(
            detail,
            "civic-parked",
            car,
            k * 4.2 + 1.9,
            -d / 2 + 5,
            0.23,
            0.86,
          );
      }
      add(
        detail,
        "civic-sign-" + p.kind,
        () => signBoard(p.kind),
        -w / 2 + 7,
        -d / 2 + 7,
        0.2,
      );
      add(detail, "civic-bike-rack", bikeRack, w / 2 - 7, -d / 2 + 7, 0.2);
      if (p.kind === "network")
        for (let k = 0; k < 6; k++)
          add(detail, "civic-UPS", ups, -10 + k * 4, 22, 0.3);
      if (p.kind === "fire")
        for (let k = -1; k <= 1; k++)
          add(
            detail,
            "civic-fire-truck",
            () => car(true),
            k * 8,
            -9,
            0.2,
            1.15,
          );
      if (p.kind === "hospital")
        for (const u of [-7, 7])
          add(detail, "civic-ambulance", () => car(true), u, -13, 0.2, 1.1);
    }
    if (p.access) {
      const access = Array.isArray(p.access)
        ? p.access
        : [p.access.x, p.access.y];
      const dx = access[0] - p.x,
        dy = access[1] - p.y;
      const u = co * dx + si * dy,
        v = -si * dx + co * dy;
      const divisor = Math.max(Math.abs(u) / (w / 2), Math.abs(v) / (d / 2), 1);
      const edge = [u / divisor, v / divisor];
      ground.strip(
        xy(...edge),
        access,
        p.kind === "sector_service" ? 8 : p.kind === "park" ? 3 : 6,
        0.19,
        p.kind === "park" ? 0xb6b09a : 0x424b4e,
      );
    }
    state.klyaksaSitesVisual.push({
      city: c.id,
      id: p.id,
      kind: p.kind,
      x: c.at[0] + p.x,
      y: c.at[1] + p.y,
      w,
      d,
    });
  }
  const mat = facadeMaterial(env);
  const buildings = architecture.finish({
    distance: 11000,
    materialFor: (key) => (key === "civic-fuel" ? null : mat),
  });
  buildings.name = `${c.id} civic skyline`;
  const close = detail.finish({ distance: 1500 });
  close.name = `${c.id} civic furniture`;
  const trees = landscape.finish({
    distance: 3000,
    materialFor: () => lifeMaterial(env, { indoor: 1, sway: 0.15 }),
  });
  const pavement = ground.mesh({ paving: true });
  pavement.name = `${c.id} civic parcel surfaces`;
  body.add(pavement);
  state.klyaksaLod.push(buildings, close, trees);
  (state.klyaksaCivicSummary ||= []).push(summary);
  return summary;
}
