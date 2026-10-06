import { bridgeLift } from "./geography.js";
/** Read-only presentation of existing facilities, tank levels and rover poses. */
import * as T from "three";
import { state } from "../../state.js";
import { bodyHeight } from "../../geometry/noise.js";
import { dirAt } from "../klyaksa.js";
import { Batches, Model, pole, car, palette, antenna, planYaw } from "./kit.js";
import { civicGeometry } from "./buildings.js";
import { Surface } from "./streets.js";
export function buildIndustry(c, body, R, env) {
  const point = (x, y, h = 0) => {
      const n = dirAt(c.at[0] + x, c.at[1] + y, R);
      return n.multiplyScalar(R * (1 + bodyHeight(3, n.x, n.y, n.z)) + h);
    },
    b = new Batches(body, R, point, env),
    road = new Surface((x, y, h = 0) => {
      const X = c.at[0] + x,
        Y = c.at[1] + y,
        n = dirAt(X, Y, R),
        alt = state.klyaksaGroundAt?.(X, Y) ?? bodyHeight(3, n.x, n.y, n.z) * R;
      return n.multiplyScalar(R + alt + h + 0.2);
    });
  for (const r of c.service_roads || [])
    for (let j = 1; j < r.points.length; j++) {
      const A = r.points[j - 1],
        B = r.points[j],
        L = Math.hypot(B[0] - A[0], B[1] - A[1]);
      if (!L) continue;
      const steps = Math.ceil(L / 4);
      for (let k = 0; k < steps; k++) {
        const at = (t) => [A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t],
          a = at(k / steps),
          z = at((k + 1) / steps);
        road.strip(a, z, r.width, 0.16, 0x38434b);
        road.strip(a, z, 0.18, 0.19, 0xddd7b7, r.width / 2 - 0.4);
        road.strip(a, z, 0.18, 0.19, 0xddd7b7, -r.width / 2 + 0.4);
        if (k % 2 === 0) road.strip(a, z, 0.18, 0.19, 0xddd7b7);
      }
    }
  for (const [key, xy] of Object.entries(c.facilities || {})) {
    const [x, y] = xy;
    if (key === "solar_pos") {
      const panel = () => {
        const m = new Model();
        m.box(0, 1, 0, 0.12, 2, 0.12, palette.metal);
        for (let k = 0; k < 6; k++)
          m.box(
            ((k % 3) - 1) * 1.3,
            2 + (k % 3) * 0.15,
            Math.floor(k / 3) * 1.5,
            1.22,
            0.12,
            1.42,
            0x244b72,
          );
        return m.finish();
      };
      for (let i = 0; i < 35; i++)
        b.add(
          "solar",
          panel,
          x + (i % 7) * 7 - 21,
          y + Math.floor(i / 7) * 6 - 12,
          0,
        );
      continue;
    }
    const kind =
      key === "reactor_pos"
        ? "reactor"
        : key === "tower_pos"
          ? "network"
          : key === "waste_station_pos"
            ? "garage"
            : "water";
    // Facility foundations and apron keep small terrain deviations out of walls.
    b.add(
      "foundation",
      () => new Model().box(0, -1, 0, 76, 2, 70, 0x747e7d).finish(),
      x,
      y,
      1,
    );
    b.add("plant-" + kind, () => civicGeometry(kind), x, y, 1);
    if (kind === "network") b.add("network-mast", antenna, x, y, 10, 3);
    const transformer = () => {
      const m = new Model().box(0, 1.5, 0, 3, 3, 2, palette.metal);
      for (let i = 0; i < 8; i++)
        m.box(-1.6 + i * 0.45, 1.4, 0, 0.1, 2.6, 2.5, palette.dark);
      for (let k = -1; k <= 1; k++) m.cyl(k, 3.4, 0, 0.18, 0.8, palette.white);
      return m.finish();
    };
    for (let k = 0; k < 3; k++)
      b.add("transformer", transformer, x + 26, y - 15 + k * 10, 1);
    for (let k = 0; k < 4; k++) {
      b.add("lamp", pole, x - 33 + k * 22, y + 31, 1);
      b.add("service-vehicle", () => car(true), x - 25 + k * 6, y + 25, 1);
    }
    // Fenced compounds with an open vehicle gate.
    const fence = () => {
      const m = new Model().box(0, 1.2, 0, 0.07, 2.4, 0.07, palette.metal);
      for (const h of [0.4, 1.3, 2.2])
        m.box(0, h, 0, 4.8, 0.035, 0.035, palette.metal);
      return m.finish();
    };
    for (let k = -7; k <= 7; k++) {
      b.add("fence", fence, x + k * 5, y - 34, 1);
      if (Math.abs(k) > 1) b.add("fence", fence, x + k * 5, y + 34, 1);
    }
    if (kind === "water") {
      for (const dx of [-9, 9])
        b.add(
          "filter",
          () =>
            new Model()
              .cyl(0, 3, 0, 4, 6, 0x789fa7)
              .cyl(0, 6.2, 0, 4.3, 0.4, palette.white)
              .finish(),
          x + dx,
          y - 23,
          1,
        );
    }
  }
  body.add(road.mesh());
  state.klyaksaLod.push(b.finish({ distance: 5000 }));
  // The transparent upper tank shows the actual fill fraction supplied by the existing water domain.
  const tank = new T.Group(),
    framePoint = dirAt(c.at[0] + 25, c.at[1] - 60, R);
  tank.position.copy(framePoint).multiplyScalar(R * 1.0035 + 0.4);
  tank.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), framePoint);
  const shell = new T.Mesh(
    new T.CylinderGeometry(7.05, 7.05, 7.8, 24, 1, true),
    new T.MeshPhysicalMaterial({
      color: 0xb9d9df,
      transparent: true,
      opacity: 0.18,
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
  fill.scale.y = 7;
  tank.add(fill);
  body.add(tank);
  (state.klyaksaTanks ||= new Map()).set(c.id, fill);
}
const _matrix = new T.Matrix4(),
  _position = new T.Vector3(),
  _quaternion = new T.Quaternion(),
  _scale = new T.Vector3(1, 1, 1);
export function syncCityVisuals(snapshot, body, R) {
  const groups = [[], []],
    now = performance.now();
  state.klyaksaVehicleHistory ||= new Map();
  for (const c of snapshot.cities) {
    const city = state.klyaksaPlanData.cities.find((x) => x.id === c.id);
    if (!city) continue;
    const fill = state.klyaksaTanks?.get(c.id);
    if (fill && c.water) {
      const h = Math.max(
        0.02,
        Math.min(1, c.water.tank_m3 / c.water.capacity_m3) * 7.8,
      );
      fill.scale.y = h;
      fill.position.y = 20.1 + h / 2;
    }
    for (const r of c.rovers || []) {
      const key = c.id + "/" + r.name,
        previous = state.klyaksaVehicleHistory.get(key),
        x = city.at[0] + r.x,
        y = city.at[1] + r.y,
        n = dirAt(x, y, R),
        inside = Math.hypot(r.x, r.y) < city.wall + 150;
      const h = inside
          ? R * 0.0035
          : Math.max(0, bodyHeight(3, n.x, n.y, n.z) * R),
        position = n
          .clone()
          .multiplyScalar(
            R + h + 0.2 + (city.id === "k1" && inside ? bridgeLift(r.y) : 0),
          );
      const quaternion = new T.Quaternion()
        .setFromUnitVectors(new T.Vector3(0, 1, 0), n)
        .multiply(
          new T.Quaternion().setFromAxisAngle(
            new T.Vector3(0, 1, 0),
            planYaw(
              (X, Y) => dirAt(X, Y, R).multiplyScalar(R),
              x,
              y,
              r.heading + Math.PI / 2,
            ),
          ),
        );
      const entry = {
        from: previous?.position.clone() || position.clone(),
        position,
        qfrom: previous?.quaternion.clone() || quaternion.clone(),
        quaternion,
      };
      state.klyaksaVehicleHistory.set(key, entry);
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
      body.add(mesh);
      batch = { mesh, capacity };
      state.klyaksaVehicleBatches[k] = batch;
    }
    batch.items = groups[k];
    batch.mesh.count = groups[k].length;
    batch.at = now;
  }
  updateCityVehicles(now);
}
export function updateCityVehicles(now) {
  for (const b of state.klyaksaVehicleBatches || []) {
    const t = Math.min(1, Math.max(0, (now - b.at) / 1800));
    for (let i = 0; i < b.items.length; i++) {
      const v = b.items[i];
      _position.lerpVectors(v.from, v.position, t);
      _quaternion.slerpQuaternions(v.qfrom, v.quaternion, t);
      b.mesh.setMatrixAt(i, _matrix.compose(_position, _quaternion, _scale));
    }
    b.mesh.instanceMatrix.needsUpdate = true;
    b.mesh.computeBoundingSphere();
  }
}
