import { riverLevel, riverWidth, riverCentre } from "./geography.js";
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
export function vesselGeometry(kind) {
  const m = new Model(),
    ship = kind === "ship",
    scale = ship ? 3 : 1;
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
function findCoast(c, R) {
  let best = null;
  const wet = (x, y) => {
    const n = dirAt(x, y, R);
    return (
      Math.abs(y) > riverWidth(x) + 200 && bodyHeight(3, n.x, n.y, n.z) * R < -4
    );
  };
  for (let k = 0; k < 48; k++) {
    const a = (k * Math.PI) / 24,
      co = Math.cos(a),
      si = Math.sin(a);
    for (let d = c.wall + 200; d < 8000; d += 80) {
      const x = c.at[0] + co * d,
        y = c.at[1] + si * d;
      if (!wet(x, y)) continue;
      // Entire quay and berth envelope must be water, not merely one sampled point.
      let clear = true;
      for (const u of [-60, 0, 110])
        for (const v of [-110, 0, 110])
          if (!wet(x + co * u - si * v, y + si * u + co * v)) clear = false;
      if (clear) {
        if (!best || d < best.score) best = { x, y, a, score: d };
        break;
      }
    }
  }
  return best;
}
export function buildWaterfronts(body, R, plan, env, cityPoint) {
  const seaPoint = (x, y, h = 0) => dirAt(x, y, R).multiplyScalar(R + h),
    ships = [];
  for (const id of ["k3", "k2"]) {
    const city = plan.cities.find((c) => c.id === id),
      coast = findCoast(city, R);
    if (!coast) continue;
    const { x, y, a } = coast,
      co = Math.cos(a),
      si = Math.sin(a),
      xy = (u, v) => [x + co * u - si * v, y + si * u + co * v],
      point = (u, v, h = 0) => seaPoint(...xy(u, v), h),
      b = new Batches(body, R, point, env),
      surface = new Surface(point);
    b.add(
      "quay-wall",
      () => new Model().box(-25, 1.8, 0, 50, 4.4, 200, 0x727f80).finish(),
      0,
      0,
      0,
    );
    surface.quad(
      [
        [-50, -100, 4],
        [-50, 100, 4],
        [0, -100, 4],
        [0, 100, 4],
      ],
      0x959e98,
    );
    for (let j = -2; j <= 2; j++) {
      surface.strip([0, j * 35], [95, j * 35], 7, 3.7, 0xb4ad91);
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
    const container = () => {
      const m = new Model().box(0, 1.35, 0, 2.45, 2.7, 6.05, 0xa86445);
      for (let z = -2.8; z <= 2.8; z += 0.4)
        for (const side of [-1, 1])
          m.box(side * 1.24, 1.35, z, 0.05, 2.5, 0.08, 0xc58159);
      for (const x of [-1.1, 0, 1.1])
        m.box(x, 1.35, 3.05, 0.06, 2.6, 0.08, palette.metal);
      return m.finish();
    };
    for (let k = 0; k < 18; k++) {
      b.add("shipping-containers", container, -44, -78 + k * 9, 4);
      if (k % 4 === 0)
        b.add("shipping-containers", container, -44, -78 + k * 9, 6.7);
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
    b.add("crane", crane, -10, -85, 4, 1, -a);
    b.add("crane", crane, -10, 85, 4, 1, -a);
    for (let k = 0; k < 7; k++) {
      b.add("quay-lamp", pole, -5, -90 + k * 30, 4);
      b.add("bench", bench, -10, -80 + k * 27, 4);
      b.add("bin", bin, -12, -80 + k * 27, 4);
    }
    for (let k = 0; k < 6; k++)
      b.add("parked", car, -30, -22 + k * 8, 4, 0.9, -a);
    body.add(surface.mesh());
    state.klyaksaLod.push(b.finish({ distance: 5000 }));
    const access = new Surface((X, Y, h = 0) => {
      const n = dirAt(X, Y, R),
        alt = state.klyaksaGroundAt?.(X, Y) ?? bodyHeight(3, n.x, n.y, n.z) * R;
      return n.multiplyScalar(R + Math.max(4, alt + 0.35) + h);
    });
    const start = [
        city.at[0] + Math.cos(a) * (city.wall - 50),
        city.at[1] + Math.sin(a) * (city.wall - 50),
      ],
      end = xy(-50, 0),
      D = Math.hypot(end[0] - start[0], end[1] - start[1]),
      N = Math.ceil(D / 4);
    for (let k = 0; k < N; k++) {
      const at = (t) => [
          start[0] + (end[0] - start[0]) * t,
          start[1] + (end[1] - start[1]) * t,
        ],
        A = at(k / N),
        B = at((k + 1) / N);
      state.klyaksaReservations
        ?.get(city.id)
        ?.mark(A[0] - city.at[0], A[1] - city.at[1], 18);
      access.strip(A, B, 10, 0, 0x38474c);
      access.strip(A, B, 0.2, 0.02, 0xe4d8a9);
    }
    body.add(access.mesh());
    for (let k = 0; k < 7; k++) {
      const kind = k === 6 ? "ship" : k % 2 ? "yacht" : "boat",
        p = k === 6 ? xy(135, 0) : xy(40 + (k % 2) * 35, -87.5 + k * 35),
        n = dirAt(...p, R);
      if (bodyHeight(3, n.x, n.y, n.z) > -0.0002) continue;
      const mesh = new T.Mesh(
        vesselGeometry(kind),
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
        heading: a,
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
      quay: xy(-25, 0),
      access: [start, end],
    });
  }
  state.klyaksaBoats = ships;
  const river = new Surface((x, y, h = 0) => seaPoint(x, y, riverLevel(x) + h));
  for (let x = -10480; x < 10480; x += 20) {
    const w = riverWidth(x);
    river.quad(
      [
        [x, riverCentre(x) - w, 0],
        [x, riverCentre(x) + w, 0],
        [x + 20, riverCentre(x + 20) - riverWidth(x + 20), 0],
        [x + 20, riverCentre(x + 20) + riverWidth(x + 20), 0],
      ],
      0x2d8791,
    );
  }
  const water = river.mesh();
  water.material = new T.ShaderMaterial({
    uniforms: env,
    side: T.DoubleSide,
    vertexShader: `varying vec3 vW,vN;void main(){vN=normalize(mat3(modelMatrix)*normal);vec4 w=modelMatrix*vec4(position,1.);vW=w.xyz;gl_Position=projectionMatrix*viewMatrix*w;}`,
    fragmentShader: `uniform float uTime;uniform vec3 uSun;varying vec3 vW,vN;void main(){vec3 n=normalize(vN+vec3(sin(vW.x*.5+uTime*1.6),sin(vW.y*.4-uTime),cos(vW.z*.5+uTime))*.06);vec3 v=normalize(cameraPosition-vW);float f=pow(1.-abs(dot(n,v)),3.);float spec=pow(max(dot(reflect(-normalize(uSun),n),v),0.),96.);gl_FragColor=vec4(mix(vec3(.025,.19,.22),vec3(.30,.55,.62),f)+spec*.75,1.);}`,
  });
  body.add(water);
  // Cable-stayed river crossings at the Meridian rings. Decks retain the server road coordinates.
  const city = plan.cities[0],
    b = new Batches(body, R, (x, y, h = 0) => cityPoint(x, y, h), env);
  for (const x of [-870, -510, 510, 870]) {
    const m = new Model();
    for (const y of [-42, 42]) {
      for (const side of [-7, 7]) {
        m.box(side, 23, y, 1.1, 46, 1.2, palette.white).box(
          side,
          -6,
          y,
          1.1,
          12,
          1.2,
          palette.concrete,
        );
        for (let z = -30; z <= 30; z += 10)
          m.beam([side, 43, y], [side, 1, z], 0.085, palette.metal);
      }
      m.beam([-7, 42, y], [7, 42, y], 0.35, palette.white);
    }
    m.box(0, -0.35, 0, 15, 0.7, 65, palette.metal);
    b.add("cable-bridge", () => m.finish(), x, 0, 12.1);
  }
  body.add(b.finish());
}
function waterLevel(x, y) {
  return Math.abs(y - riverCentre(x)) < riverWidth(x) ? riverLevel(x) : 0;
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
    camDistance: boat.kind === "ship" ? 65 : 23,
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
  const margin = boat.kind === "ship" ? 18 : 6;
  for (const p of state.klyaksaPorts || []) {
    const co = Math.cos(p.coast.a),
      si = Math.sin(p.coast.a),
      u = (x - p.x) * co + (y - p.y) * si,
      v = -(x - p.x) * si + (y - p.y) * co;
    if (u > -50 - margin && u < margin && Math.abs(v) < 100 + margin)
      return true;
    if (u > -margin && u < 95 + margin)
      for (let j = -2; j <= 2; j++)
        if (Math.abs(v - j * 35) < 3.5 + margin) return true;
  }
  return (state.klyaksaBoats || []).some(
    (b) =>
      b !== boat &&
      Math.hypot(x - b.x, y - b.y) < margin + (b.kind === "ship" ? 18 : 6),
  );
}
export function stepBoat(b, input, dt) {
  const thrust = (input.forward ? 1 : 0) - (input.back ? 0.45 : 0);
  b.speed +=
    (thrust * 3.5 - b.speed * 0.16 - b.speed * Math.abs(b.speed) * 0.025) * dt;
  b.steer +=
    ((input.left ? 1 : 0) - (input.right ? 1 : 0) - b.steer) *
    Math.min(1, dt * 4);
  b.heading += b.steer * b.speed * 0.035 * dt;
  const x = b.x + Math.cos(b.heading) * b.speed * dt,
    y = b.y + Math.sin(b.heading) * b.speed * dt,
    n = dirAt(x, y, b.R);
  if (
    bodyHeight(3, n.x, n.y, n.z) * b.R < waterLevel(x, y) - 1.8 &&
    !blockedBerth(x, y, b)
  ) {
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
    const n = b.mesh.position.clone().normalize(),
      f = new T.Vector3(0, 0, 1)
        .applyQuaternion(b.mesh.quaternion)
        .applyAxisAngle(n, drive.camYaw),
      target = b.mesh.position
        .clone()
        .add(b.body.position)
        .addScaledVector(n, 3),
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
