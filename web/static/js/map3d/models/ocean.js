/** models/ocean: procedural colony viewer. */
import { state } from "../state.js";
import { localGroup } from "../geometry/objects.js";
import { quatAt, sph, subdiv, terrainH } from "../geometry/planet.js";
import { onRoad } from "../geometry/roads.js";
import { FlowLayer, LineLayer, flat3 } from "../render/flows.js";
import { addLabel, clickable } from "../render/world.js";
import { industrialPipe } from "./campus.js";
import { utilityPoint } from "./drainage.js";
import { Kit } from "./kit.js";
import { parkingLot } from "./service-sites.js";
import * as THREE from "three";

export function coastHeight(x, y, height) {
  if (Math.hypot(x, y) < 900) return height;
  const az = Math.atan2((y - 600) / 1380, (x + 2450) / 1080),
    q =
      Math.hypot((x + 2450) / 1080, (y - 600) / 1380) /
      (1 +
        0.08 * Math.sin(3 * az) +
        0.05 * Math.sin(7 * az) +
        0.025 * Math.sin(11 * az)),
    coast = state.sstep(0, 1, Math.max(0, Math.min(1, (1.1 - q) / 0.16)));
  height += (-26 - 22 * Math.max(0, 1 - q * q) - height) * coast;
  const river = [
    [500, 1550, 46],
    [50, 1490, 34],
    [-410, 1250, 23],
    [-900, 1060, 12],
    [-1450, 840, 1],
    [-2050, 740, -8],
  ];
  for (let i = 1; i < river.length; i++) {
    const a = river[i - 1],
      b = river[i],
      dx = b[0] - a[0],
      dy = b[1] - a[1],
      t = THREE.MathUtils.clamp(
        ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy),
        0,
        1,
      ),
      dist = Math.hypot(x - a[0] - dx * t, y - a[1] - dy * t),
      blend = state.sstep(0, 1, THREE.MathUtils.clamp((95 - dist) / 70, 0, 1));
    height += (a[2] + (b[2] - a[2]) * t - 2 - height) * blend;
  }
  return height;
}

export function seaPoint(x, y, level = -8) {
  return sph(x, y, level - terrainH(x, y));
}

export function metalRing(k, mat, center, radius, thickness = 0.09) {
  for (let i = 0; i < 64; i++) {
    const a = (i * Math.PI) / 32,
      b = ((i + 1) * Math.PI) / 32;
    k.pipe(
      mat,
      [
        center[0] + Math.cos(a) * radius,
        center[1],
        center[2] + Math.sin(a) * radius,
      ],
      [
        center[0] + Math.cos(b) * radius,
        center[1],
        center[2] + Math.sin(b) * radius,
      ],
      thickness,
    );
  }
}

export function buildOcean() {
  const c = state.G.cfg,
    [cx, cy] = c.ocean_center,
    [rx, ry] = c.ocean_radii,
    level = c.ocean_level_m,
    pos = [],
    idx = [],
    rings = 50,
    segs = 160;
  for (let r = 0; r <= rings; r++)
    for (let j = 0; j < segs; j++) {
      const a = (j * Math.PI * 2) / segs,
        x = cx + ((rx * 1.2 * r) / rings) * Math.cos(a),
        y = cy + ((ry * 1.2 * r) / rings) * Math.sin(a),
        p = seaPoint(x, y, level);
      pos.push(p.x, p.y, p.z);
    }
  for (let r = 0; r < rings; r++)
    for (let j = 0; j < segs; j++) {
      const a = r * segs + j,
        b = r * segs + ((j + 1) % segs),
        cc = (r + 1) * segs + j,
        d = (r + 1) * segs + ((j + 1) % segs);
      idx.push(a, cc, b, b, cc, d);
    }
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geom.setIndex(idx);
  geom.computeVertexNormals();
  const ice = new THREE.Mesh(
    geom,
    new THREE.MeshStandardMaterial({
      color: 0x7cabb4,
      metalness: 0.18,
      roughness: 0.32,
      side: THREE.DoubleSide,
      envMapIntensity: 0.75,
    }),
  );
  state.world.add(ice);
  state.complex.ocean = ice;
  // Pressure ridges and branching fractures in the frozen sea, grounded at sea level.
  const cracks = [],
    k = new Kit(state.world);
  for (let n = 0; n < 110; n++) {
    const a = n * 2.39996,
      r = Math.sqrt((n + 0.5) / 110) * 0.92,
      x = cx + Math.cos(a) * rx * r,
      y = cy + Math.sin(a) * ry * r;
    const path = [];
    for (let j = 0; j < 7; j++)
      path.push(
        seaPoint(x + j * 13, y + Math.sin(n + j * 1.7) * 12, level + 0.11),
      );
    cracks.push(path);
    if (n % 3 === 0)
      k.add(
        "ball",
        state.M.white,
        seaPoint(x, y, level + 0.3).toArray(),
        [12, 1.4, 4],
        quatAt(x, y, a),
        0xb5ced0,
      );
  }
  new LineLayer(cracks, 0x335f70);
  // Frozen river follows an explicit descending hydraulic profile, from highlands to sea.
  const points = state.G.river || [
      [500, 1550, 46],
      [50, 1490, 34],
      [-410, 1250, 23],
      [-900, 1060, 12],
      [-1450, 840, 1],
      [-2050, 740, -8],
    ],
    riverPos = [],
    riverIdx = [];
  for (let segment = 1; segment < points.length; segment++) {
    const a = points[segment - 1],
      b = points[segment],
      dx = b[0] - a[0],
      dy = b[1] - a[1],
      L = Math.hypot(dx, dy),
      N = Math.ceil(L / 14);
    for (let j = 0; j <= N; j++) {
      const t = j / N,
        x = a[0] + dx * t,
        y = a[1] + dy * t,
        h = a[2] + (b[2] - a[2]) * t + 0.08,
        width = 12 + segment * 1.5,
        base = riverPos.length / 3;
      for (const sign of [-1, 1]) {
        const p = seaPoint(
          x - (dy / L) * width * sign,
          y + (dx / L) * width * sign,
          h,
        );
        riverPos.push(p.x, p.y, p.z);
      }
      if (j < N)
        riverIdx.push(base, base + 2, base + 1, base + 1, base + 2, base + 3);
    }
  }
  const rg = new THREE.BufferGeometry();
  rg.setAttribute("position", new THREE.Float32BufferAttribute(riverPos, 3));
  rg.setIndex(riverIdx);
  rg.computeVertexNormals();
  state.world.add(
    new THREE.Mesh(
      rg,
      new THREE.MeshStandardMaterial({
        color: 0x97c0c5,
        metalness: 0.22,
        roughness: 0.28,
        side: THREE.DoubleSide,
      }),
    ),
  );
  // Sparse, frost-encrusted columnar organisms and low tundra; no temperate grass at -50 C.
  for (let n = 0; n < 760; n++) {
    const a = n * 2.39996,
      r = 950 + ((n * 137) % 2200),
      x = Math.cos(a) * r,
      y = Math.sin(a) * r,
      h = terrainH(x, y);
    if (h < 2 || h > 125 || (x < -750 && Math.abs(y) < 700)) continue;
    const q = quatAt(x, y, a),
      base = sph(x, y),
      height = 1.2 + (n % 7) * 0.4,
      tip = base
        .clone()
        .add(new THREE.Vector3(0, height, 0).applyQuaternion(q));
    k.pipe(state.M.fabric, base.toArray(), tip.toArray(), 0.17);
    for (let branch = 0; branch < 3; branch++) {
      const p = base
        .clone()
        .add(
          new THREE.Vector3(
            Math.sin(branch * 2.1) * 0.6,
            height * 0.7,
            Math.cos(branch * 2.1) * 0.6,
          ).applyQuaternion(q),
        );
      k.pipe(state.M.white, tip.toArray(), p.toArray(), 0.08);
    }
    k.add(
      "ball",
      state.M.fabric,
      base.toArray(),
      [1.8, 0.15, 1.1],
      q,
      0x6e7969,
    );
  }
  k.finish();
  buildIntake();
}

export function buildIntake() {
  const c = state.G.cfg,
    [ix, iy] = c.ocean_intake_pos,
    [wx, wy] = c.water_plant_pos,
    [rx, ry] = c.reactor_pos,
    level = c.ocean_level_m;
  const head = localGroup(ix, iy, level - terrainH(ix, iy) + 0.7, 0),
    k = new Kit(head);
  k.box(state.M.steel, 0, 1.8, 0, 22, 0.55, 18);
  for (const x of [-9, 9])
    for (const z of [-7, 7])
      k.pipe(state.M.concrete, [x, -14, z], [x, 1.5, z], 0.65);
  for (let x = -10; x <= 10; x += 2)
    for (const z of [-8, 8]) {
      k.pipe(state.M.trim, [x, 2, z], [x, 3.3, z], 0.045);
      if (x < 10) k.pipe(state.M.trim, [x, 3.3, z], [x + 2, 3.3, z], 0.035);
    }
  for (let n = -1; n <= 1; n++) {
    k.add("cyl", state.M.trim, [n * 5, 3.5, 0], [1.2, 3.1, 1.2]);
    industrialPipe(
      k,
      [
        [n * 5, 3.5, 0],
        [n * 5, -4, 0],
      ],
      0.45,
      state.M.blue,
    );
    k.box(state.M.dark, n * 5, -3.3, 0, 2.2, 2.2, 2.2);
    for (let grille = 0; grille < 10; grille++)
      k.box(
        state.M.trim,
        n * 5 - 1 + grille * 0.22,
        -3.3,
        1.13,
        0.07,
        2.3,
        0.08,
      );
  }
  for (const z of [-6, 6]) {
    industrialPipe(
      k,
      [
        [-11, -0.1, z],
        [11, -0.1, z],
      ],
      0.18,
      state.M.amber,
    );
    for (let n = -4; n <= 4; n++) {
      const heater = new THREE.Mesh(
        new THREE.BoxGeometry(1.3, 0.12, 0.2),
        new THREE.MeshStandardMaterial({
          color: 0xb77232,
          emissive: 0xe25913,
          emissiveIntensity: 0.3,
        }),
      );
      heater.position.set(n * 2.3, -0.1, z);
      head.add(heater);
      state.intakeHeaters.push(heater);
    }
  }
  k.finish();
  const pg = new THREE.CircleGeometry(21, 64);
  state.intakePool = new THREE.Mesh(
    pg,
    new THREE.MeshPhysicalMaterial({
      color: 0x245465,
      metalness: 0.35,
      roughness: 0.15,
      transparent: true,
      opacity: 0.96,
      side: THREE.DoubleSide,
    }),
  );
  state.intakePool.position.copy(seaPoint(ix, iy, level + 0.2));
  state.intakePool.quaternion.copy(quatAt(ix, iy));
  state.intakePool.rotateX(-Math.PI / 2);
  state.world.add(state.intakePool);
  // Separate maintenance grating and insulated raw-water / brine lines.
  const route = [
      [ix, iy],
      [ix + 18, iy],
      [ix + 18, iy - 60],
      [wx - 60, wy - 60],
      [wx - 60, wy],
      [wx - 30, wy],
    ],
    pts = subdiv(route, 5),
    k2 = new Kit(state.world),
    line = [];
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i],
      h = Math.max(level + 4.1, terrainH(...p) + 7.2);
    line.push(seaPoint(...p, h));
  }
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1],
      b = pts[i],
      dx = b[0] - a[0],
      dy = b[1] - a[1],
      L = Math.hypot(dx, dy) || 1,
      n = new THREE.Vector3(-dy / L, 0, dx / L).applyQuaternion(quatAt(...b)),
      pa = line[i - 1],
      pb = line[i],
      up = pb.clone().normalize(),
      side = 3.1;
    k2.pipe(state.M.blue, pa.toArray(), pb.toArray(), 0.66);
    k2.pipe(
      state.M.steel,
      pa.clone().addScaledVector(n, 1.5).toArray(),
      pb.clone().addScaledVector(n, 1.5).toArray(),
      0.3,
    );
    const qa = pa.clone().addScaledVector(n, side).addScaledVector(up, -1.3),
      qb = pb.clone().addScaledVector(n, side).addScaledVector(up, -1.3),
      forward = qb.clone().sub(qa).normalize(),
      right = forward.clone().cross(up).normalize(),
      q = new THREE.Quaternion().setFromRotationMatrix(
        new THREE.Matrix4().makeBasis(forward, up, right),
      );
    k2.add(
      "box",
      state.M.steel,
      qa.clone().lerp(qb, 0.5).toArray(),
      [qa.distanceTo(qb), 0.1, 1.6],
      q,
    );
    for (let f = 0; f < 1; f += 0.08) {
      const p = qa.clone().lerp(qb, f);
      k2.pipe(
        state.M.trim,
        p.clone().addScaledVector(right, -0.7).toArray(),
        p.clone().addScaledVector(right, 0.7).toArray(),
        0.026,
      );
    }
    for (const sign of [-1, 1]) {
      const a = qa.clone().addScaledVector(right, sign * 0.8),
        b = qb.clone().addScaledVector(right, sign * 0.8);
      k2.pipe(
        state.M.amber,
        a.toArray(),
        a.clone().addScaledVector(up, 1.1).toArray(),
        0.033,
      );
      k2.pipe(
        state.M.amber,
        a.clone().addScaledVector(up, 1.1).toArray(),
        b.clone().addScaledVector(up, 1.1).toArray(),
        0.03,
      );
    }
    if (i % 2 === 0 && !onRoad(...b, 1)) {
      k2.pipe(state.M.steel, sph(...b, 0.15).toArray(), pb.toArray(), 0.13);
      k2.pipe(
        state.M.steel,
        sph(b[0] - (dy / L) * side, b[1] + (dx / L) * side, 0.15).toArray(),
        qb.toArray(),
        0.13,
      );
    }
  }
  k2.finish();
  state.oceanFlow = new FlowLayer([line], 0x9bdeed, 0.8, 20, 8);
  addLabel(
    "INTAKE SERVICE WALKWAY / RAW WATER + BRINE",
    wx - 125,
    wy - 60,
    10,
    "#d2c79e",
    "near",
  );
  const hotPath = flat3(
      [
        [rx - 52, ry - 131],
        [rx - 52, ry - 112],
        [rx + 70, ry - 112],
        [rx + 70, wy - 30],
        [wx + 15, wy - 30],
        [wx + 15, wy - 20],
      ],
      8.5,
    ),
    hotKit = new Kit(state.world);
  for (let i = 1; i < hotPath.length; i++) {
    hotKit.pipe(
      state.M.trim,
      hotPath[i - 1].toArray(),
      hotPath[i].toArray(),
      0.65,
    );
    const up = hotPath[i].clone().normalize();
    hotKit.pipe(
      state.M.steel,
      hotPath[i - 1].clone().addScaledVector(up, -1.5).toArray(),
      hotPath[i].clone().addScaledVector(up, -1.5).toArray(),
      0.58,
    );
  }
  hotKit.finish();
  state.thermalFlow = new FlowLayer([hotPath], 0xeac47e, 1, 12, 9);
  // Membrane filters, pressure vessels and a real delivery main into the elevated city tank.
  const plantKit = new Kit(state.world),
    plantG = localGroup(wx, wy, 0, 0),
    pk = new Kit(plantG);
  for (let n = 0; n < 5; n++) {
    const xx = -21 + n * 10;
    pk.add(
      "cyl",
      state.M.trim,
      [xx, 27, -6],
      [1.7, 7, 1.7],
      [Math.PI / 2, 0, 0],
    );
    industrialPipe(
      pk,
      [
        [xx, 27, -9.5],
        [xx, 27, -15],
        [25, 27, -15],
        [25, 5, -15],
      ],
      0.2,
      state.M.blue,
    );
  }
  industrialPipe(
    pk,
    [
      [-28, 3.5, 20],
      [-42, 3.5, 28],
      [-42, 3.5, 54],
    ],
    0.34,
    state.M.blue,
  );
  pk.finish();
  parkingLot(wx + 20, wy + 68, 40, 20, 0, 10);
  const delivery = state.G.utilities.plant_feed.map(utilityPoint);
  state.complex.deliveryFlow = new FlowLayer(
    [delivery],
    0x8dd4eb,
    0.75,
    28,
    10,
  );
  addLabel(
    "OCEAN INTAKE / HEATED ICE WELL",
    ix,
    iy,
    level - terrainH(ix, iy) + 14,
    "#afd5da",
    "mid",
  );
  clickable(head, "intake", "intake");
}

export function updateOcean(s) {
  if (!state.oceanFlow) return;
  const on = s.water.plant && s.water.raw_m3_h > 0;
  state.oceanFlow.active[0] = on;
  state.thermalFlow.active[0] = s.water.heat_kw > 0;
  state.complex.deliveryFlow.active[0] = on;
  state.intakeHeaters.forEach(
    (m) => (m.material.emissiveIntensity = on ? 1.7 : 0.05),
  );
  state.intakePool.material.color.setHex(on ? 0x245465 : 0x88b5c3);
  state.intakePool.material.roughness = on ? 0.15 : 0.5;
}

export function initialize() {
  state.oceanFlow = null;
  state.intakePool = null;
  state.intakeHeaters = [];
  state.thermalFlow = null;
}
