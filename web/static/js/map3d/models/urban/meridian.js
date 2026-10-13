/** urban/meridian: Meridian's waterfront from plan.waterways. The canal and the port basin as water with granite
 * walls; the port's cranes, yard and vehicles; two angled cable-stayed bridges and two bascule bridges that open
 * for ships (traffic lights, barriers, the leaves lifting); Neva-style landing stages and the canal's private
 * moorings; ships to the port, river boats and canal boats with navigation lights; the estuary, where the river's
 * current fans out into the sea. Lights come on with Klyaksa's night. */
import { state } from "../../state.js";
import { PLATEAU } from "../../geometry/noise.js";
import { dirAt } from "../klyaksa.js";
import { waterMaterial } from "../waters.js";
import { Surface } from "./streets.js";
import { bridgeLift, riverBounds, riverCentre, riverLevel, riverWidth } from "./geography.js";
import { KINDS, poseAt } from "./shipping.js";
import * as T from "three";

const _m = new T.Matrix4(), _one = new T.Vector3(1, 1, 1);
const lerp = (a, b, t) => a + (b - a) * t;

export function buildMeridian(body, R, plan, env) {
  const c = plan.cities.find((x) => x.waterways);
  if (!c) return null;
  const ww = c.waterways, ground = R + R * PLATEAU + 0.25, level = riverLevel(0);
  const P = (x, y, h = 0) => dirAt(x, y, R).multiplyScalar(ground + h);      // land
  const W = (x, y, h = 0) => dirAt(x, y, R).multiplyScalar(R + level + h);   // water
  const glowMats = [], ledMats = [];

  // ---- water: the canal strip and the basin, with a depth for the shader
  const water = (quads) => {
    const pos = [], depth = [];
    for (const q of quads) for (const [x, y, d] of q) { pos.push(...W(x, y).toArray()); depth.push(d); }
    const g = new T.BufferGeometry();
    g.setAttribute("position", new T.Float32BufferAttribute(pos, 3));
    g.setAttribute("aDepth", new T.Float32BufferAttribute(depth, 1));
    g.setAttribute("aLiquid", new T.Float32BufferAttribute(new Float32Array(depth.length).fill(1), 1));
    g.setAttribute("aWarm", new T.Float32BufferAttribute(new Float32Array(depth.length), 1));
    const m = new T.Mesh(g, waterMaterial(env, { tint: [0.05, 0.27, 0.3] }));
    m.renderOrder = 3;
    body.add(m);
  };
  const cl = ww.canal, hw = ww.canal_half_width, side = (i, s) => {
    const a = cl[Math.max(0, i - 1)], b = cl[Math.min(cl.length - 1, i + 1)], dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
    return [cl[i][0] - (dy / L) * s, cl[i][1] + (dx / L) * s];
  };
  const canalTris = [];
  for (let i = 1; i < cl.length; i++) {
    const a0 = side(i - 1, -hw), a1 = side(i - 1, hw), b0 = side(i, -hw), b1 = side(i, hw);
    canalTris.push([[...a0, 0.3], [...b0, 0.3], [...a1, 0.3]], [[...a1, 0.3], [...b0, 0.3], [...b1, 0.3]]);
  }
  const [x0, y0, x1, y1] = ww.basin, basinTris = [];
  for (let x = x0; x < x1; x += 25) for (let y = y0; y < y1; y += 25) {
    const xa = Math.min(x + 25, x1), ya = Math.min(y + 25, y1), d = (yy) => 5 + 3 * Math.min(1, (yy - y0) / 60);
    basinTris.push([[x, y, d(y)], [xa, y, d(y)], [x, ya, d(ya)]], [[xa, y, d(y)], [xa, ya, d(ya)], [x, ya, d(ya)]]);
  }
  water([...canalTris, ...basinTris]);

  // ---- granite walls along the canal and round the basin, a railing on top
  const stone = new Surface((x, y, h) => (h <= -0.01 ? W(x, y, h + 0.5) : P(x, y, h)));
  const wall = (ax, ay, bx, by) => stone.quad([[ax, ay, -1.2], [bx, by, -1.2], [ax, ay, 1.0], [bx, by, 1.0]], 0x8a8278);
  for (const s of [-hw, hw]) for (let i = 1; i < cl.length; i++) wall(...side(i - 1, s), ...side(i, s));
  wall(x0, y0, x1, y0); wall(x0, y0, x0, y1); wall(x1, y0, x1, y1);
  body.add(stone.mesh());

  // ---- lamps along both embankments, the canal and the bridges: pole, head, a glow at night
  const lampAt = [];
  for (let x = -680; x <= 680; x += 40) for (const s of [1, -1]) {
    const y = riverCentre(x) + s * (ww.embankment - 9);
    if (!(s < 0 && x > ww.port[0] && x < ww.port[2])) lampAt.push([x, y]);
  }
  for (let i = 2; i < cl.length - 2; i += 4) lampAt.push(side(i, hw + 2.5), side(i, -hw - 2.5));
  const pole = new T.InstancedMesh(new T.CylinderGeometry(0.12, 0.16, 7, 6).translate(0, 3.5, 0), new T.MeshStandardMaterial({ color: 0x2b2f33, roughness: 0.5 }), lampAt.length);
  const glow = new T.InstancedMesh(new T.SphereGeometry(1.6, 10, 8), new T.MeshBasicMaterial({ color: 0xffd9a0, transparent: true, opacity: 0.5, blending: T.AdditiveBlending, depthWrite: false }), lampAt.length);
  glowMats.push(glow.material);
  lampAt.forEach(([x, y], i) => {
    pole.setMatrixAt(i, poseAt(R, x, y, 0, R * PLATEAU + 0.25));
    glow.setMatrixAt(i, poseAt(R, x, y, 0, R * PLATEAU + 7.4));
  });
  body.add(pole, glow);

  // ---- the river port: cranes on the basin's quays, a container yard, its vehicles
  const kinds = {};
  const inst = (kind, n, mat) => {
    const geo = KINDS[kind]();
    const m = new T.InstancedMesh(geo, mat || new T.MeshStandardMaterial({ vertexColors: true, roughness: 0.6, metalness: 0.15 }), n);
    m.frustumCulled = false;
    body.add(m);
    return (kinds[kind] = m);
  };
  const cranes = [[x0 - 14, -110, 0], [x0 - 14, -230, 0], [x1 + 14, -110, Math.PI], [x1 + 14, -230, Math.PI]];
  const craneMesh = inst("crane", cranes.length), trolleys = inst("trolley", cranes.length);
  cranes.forEach(([x, y, a], i) => craneMesh.setMatrixAt(i, poseAt(R, x, y, a, R * PLATEAU + 0.25)));
  const boxes = inst("box", cranes.length + 160);
  const tint = new Float32Array((cranes.length + 160) * 3).fill(1);
  for (let k = 0; k < 160; k++) {
    const sideX = k < 80 ? x0 - 55 : x1 + 55, kk = k % 80, row = kk % 8, col = Math.floor(kk / 8) % 5, tier = Math.floor(kk / 40);
    boxes.setMatrixAt(cranes.length + k, poseAt(R, sideX + (row - 4) * 3, -320 + col * 52, Math.PI / 2, R * PLATEAU + 0.25 + tier * 2.7));
    const col3 = new T.Color([0xb5452f, 0x2f6fa8, 0x3d8a4e, 0xd4a017, 0x8a8f96][(k * 3) % 5]);
    tint.set([col3.r, col3.g, col3.b], (cranes.length + k) * 3);
  }
  boxes.instanceColor = new T.InstancedBufferAttribute(tint, 3);
  const portVans = inst("truck", 10), lifts = inst("forklift", 8);

  // ---- bridges
  const bridges = [];
  const roadOf = (id) => c.roads.find((r) => r.id === "bridge-" + id);
  const steel = new T.MeshStandardMaterial({ color: 0xd9dde0, roughness: 0.35, metalness: 0.6 });
  const deckMat = new T.MeshStandardMaterial({ color: 0x3a3e42, roughness: 0.8 });
  for (const b of ww.bridges) {
    const [nx, ny] = b.n, [sx, sy] = b.s, len = Math.hypot(nx - sx, ny - sy), heading = Math.atan2(ny - sy, nx - sx);
    const ux = (nx - sx) / len, uy = (ny - sy) / len, vx = -uy, vy = ux, width = 18;
    const at = (t, off = 0) => [sx + ux * len * t + vx * off, sy + uy * len * t + vy * off];
    const lift = (t) => bridgeLift(at(t)[1], at(t)[0]);
    if (b.kind === "cable") {
      // the deck rides the road's own lift; one or two A-pylons, stays fanned to both edges, LED strips at night
      const deck = new Surface(P);
      for (let k = 0; k < 40; k++) {
        const t0 = k / 40, t1 = (k + 1) / 40;
        deck.quad([[...at(t0, -width / 2), lift(t0) - 0.4], [...at(t1, -width / 2), lift(t1) - 0.4], [...at(t0, width / 2), lift(t0) - 0.4], [...at(t1, width / 2), lift(t1) - 0.4]], 0x4a4f54);
        deck.quad([[...at(t0, -width / 2), lift(t0) - 2.6], [...at(t1, -width / 2), lift(t1) - 2.6], [...at(t0, -width / 2), lift(t0) - 0.4], [...at(t1, -width / 2), lift(t1) - 0.4]], 0xc9cdd1);
        deck.quad([[...at(t0, width / 2), lift(t0) - 2.6], [...at(t1, width / 2), lift(t1) - 2.6], [...at(t0, width / 2), lift(t0) - 0.4], [...at(t1, width / 2), lift(t1) - 0.4]], 0xc9cdd1);
      }
      body.add(deck.mesh());
      const pylons = b.id === "cable-west" ? [0.33, 0.67] : [0.5];
      const cables = [], leds = [];
      for (const tp of pylons) {
        const top = P(...at(tp), lift(tp) + 62);
        for (const s of [-1, 1]) {   // the A: two legs from the deck edges, leaning in to the top
          const foot = P(...at(tp, s * (width / 2 + 1)), lift(tp) - 3);
          const leg = new T.Mesh(new T.CylinderGeometry(0.9, 1.4, foot.distanceTo(top), 8), steel);
          leg.position.copy(foot).add(top).multiplyScalar(0.5);
          leg.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), top.clone().sub(foot).normalize());
          body.add(leg);
          leds.push(foot, top);
        }
        for (let k = 1; k <= 12; k++)
          for (const dir of [-1, 1]) {
            const t = tp + dir * k * (0.3 / 12);
            if (t <= 0.02 || t >= 0.98) continue;
            for (const s of [-1, 1]) cables.push(top, P(...at(t, s * width / 2), lift(t) - 0.4));
          }
      }
      for (const s of [-1, 1]) for (let k = 0; k < 40; k++) leds.push(P(...at(k / 40, s * width / 2), lift(k / 40) - 0.3), P(...at((k + 1) / 40, s * width / 2), lift((k + 1) / 40) - 0.3));
      body.add(new T.LineSegments(new T.BufferGeometry().setFromPoints(cables), new T.LineBasicMaterial({ color: 0xe8ecef })));
      const led = new T.LineSegments(new T.BufferGeometry().setFromPoints([...cables, ...leds]), new T.LineBasicMaterial({ color: 0x8fd8ff, transparent: true, opacity: 0, blending: T.AdditiveBlending, depthWrite: false }));
      ledMats.push(led.material);
      body.add(led);
      bridges.push({ ...b, len });
    } else {
      // bascule: two leaves hinged at the river's banks; towers with counterweights; lights and barriers
      const half = riverWidth(0) + 4, mid = 0.5, hingeT = [mid - half / len, mid + half / len];
      const leaves = [];
      hingeT.forEach((th, li) => {
        const sign = li === 0 ? 1 : -1;     // each leaf reaches from its hinge towards the middle
        const g = new T.Group();
        g.position.copy(P(...at(th), lift(th) - 0.4));
        const up = g.position.clone().normalize(), fwd = new T.Vector3().subVectors(P(...at(mid), lift(mid)), g.position).normalize();
        fwd.addScaledVector(up, -fwd.dot(up)).normalize();
        const right = new T.Vector3().crossVectors(up, fwd).normalize();
        g.quaternion.setFromRotationMatrix(new T.Matrix4().makeBasis(right, up, fwd));
        const leaf = new T.Mesh(new T.BoxGeometry(width, 1.4, half).translate(0, -0.7, half / 2), deckMat);
        const rail = new T.Mesh(new T.BoxGeometry(width + 0.6, 1.2, half).translate(0, 0.6, half / 2), new T.MeshStandardMaterial({ color: 0xb03a2e, roughness: 0.6, wireframe: true }));
        g.add(leaf, rail);
        body.add(g);
        // the tower over the hinge: stone, a lit window band
        const tower = new T.Mesh(new T.BoxGeometry(width + 6, 22, 10), new T.MeshStandardMaterial({ color: 0x9a8f80, roughness: 0.9 }));
        tower.position.copy(P(...at(th - sign * 6 / len), lift(th) + 9));
        tower.quaternion.copy(g.quaternion);
        body.add(tower);
        leaves.push({ g, base: g.quaternion.clone(), right });
      });
      const lightMats = [0, 1].map(() => new T.MeshBasicMaterial({ color: 0x29d36a }));
      for (const [t, s] of [[0.12, 1], [0.88, -1]]) {
        const lamp = new T.Mesh(new T.SphereGeometry(0.8, 8, 6), lightMats[0]);
        lamp.position.copy(P(...at(t, width / 2 + 2), lift(t) + 5));
        body.add(lamp);
      }
      bridges.push({ ...b, len, leaves, open: 0, stop: false, red: 0, lightMats, at, lift, road: roadOf(b.id)?.id || "bridge-" + b.id });
    }
  }

  // ---- landing stages: pontoons by the embankments (Neva-style) and private moorings on the canal
  const pontoonGeo = new T.BoxGeometry(32, 1.4, 9), kiosk = new T.BoxGeometry(6, 3, 4);
  const pontoonMat = new T.MeshStandardMaterial({ color: 0x5b6b73, roughness: 0.7 }), kioskMat = new T.MeshStandardMaterial({ color: 0xe9e4d8, roughness: 0.8 });
  const moorings = [];
  for (const p of ww.piers) {
    let x, y, h;
    if (p.kind === "canal") {
      const i = Math.round(p.t * (cl.length - 1));
      [x, y] = side(i, hw - 3);
      const a = cl[Math.max(0, i - 1)], b2 = cl[Math.min(cl.length - 1, i + 1)];
      h = Math.atan2(b2[1] - a[1], b2[0] - a[0]);
    } else { x = p.x; y = p.y; h = p.heading; }
    const m = new T.Mesh(p.kind === "canal" ? new T.BoxGeometry(18, 0.8, 4) : pontoonGeo, p.kind === "canal" ? new T.MeshStandardMaterial({ color: 0x8b6a45, roughness: 0.9 }) : pontoonMat);
    m.position.copy(W(x, y, 0.6));
    m.quaternion.copy(frameFor(x, y, h));
    body.add(m);
    if (p.kind !== "canal") { const k = new T.Mesh(kiosk, kioskMat); k.position.copy(W(x, y, 2.6)); k.quaternion.copy(m.quaternion); body.add(k); }
    moorings.push({ x, y, h, kind: p.kind });
  }
  function frameFor(x, y, h) { const q = new T.Quaternion(); poseAt(R, x, y, h, 0).decompose(new T.Vector3(), q, new T.Vector3()); return q; }

  // ---- vessels: ships to the port from the sea, river boats between the stages, boats on the canal
  const { mouth } = riverBounds();
  const shipMesh = inst("container", 2), boatGeo = (() => {
    const hull = new T.BoxGeometry(4, 1.4, 14).translate(0, 0.7, 0), cabin = new T.BoxGeometry(3.2, 1.8, 6).translate(0, 2.3, -1);
    const out = new T.BufferGeometry(), parts = [hull, cabin].map((g) => g.toNonIndexed());
    out.setAttribute("position", new T.Float32BufferAttribute(parts.flatMap((g) => [...g.attributes.position.array]), 3));
    out.computeVertexNormals();
    return out;
  })();
  const boats = new T.InstancedMesh(boatGeo, new T.MeshStandardMaterial({ color: 0xf2efe6, roughness: 0.5 }), 18);
  boats.frustumCulled = false; body.add(boats);
  const navLights = new T.InstancedMesh(new T.SphereGeometry(0.7, 6, 4), new T.MeshBasicMaterial({ color: 0xffffff }), (2 + 18) * 3);
  navLights.frustumCulled = false; body.add(navLights);
  const navColor = new Float32Array(navLights.count * 3);
  for (let i = 0; i < navLights.count; i++) navColor.set(i % 3 === 0 ? [1, 0.15, 0.1] : i % 3 === 1 ? [0.2, 1, 0.3] : [1, 1, 0.95], i * 3);
  navLights.instanceColor = new T.InstancedBufferAttribute(navColor, 3);
  // the first ship is already on its way up the river, the second comes in from the sea a little later
  const ships = [0, 1].map((k) => ({ k, phase: "in", x: k ? mouth - 40 : 1100, y: riverCentre(k ? mouth - 40 : 1100), heading: Math.PI, wait: k * 60, t: 0 }));
  const riverBoats = [...Array(12)].map((_, k) => ({ k, x: -700 + k * 120, dir: k % 2 ? 1 : -1, lane: (k % 3 - 1) * 12, speed: 4 + (k % 4) }));
  const canalBoats = [...Array(6)].map((_, k) => ({ k, s: 0.08 + k * 0.15, dir: k % 2 ? 1 : -1, speed: 0.004 + 0.001 * (k % 3) }));

  // ---- the estuary: the current fans out into the sea in streaks, curling at the edges
  const { mouth: mx } = riverBounds();
  const streaks = new T.InstancedMesh(new T.PlaneGeometry(1.2, 9).rotateX(-Math.PI / 2), new T.MeshBasicMaterial({ color: 0xdff4f2, transparent: true, opacity: 0.35, depthWrite: false }), 260);
  streaks.frustumCulled = false; body.add(streaks);
  const flow = [...Array(260)].map((_, i) => ({ x: mx - 260 + Math.random() * 260, y: riverCentre(mx) + (Math.random() - 0.5) * 2 * riverWidth(mx - 1), age: Math.random() * 60, seed: i }));

  return { R, P, W, kinds, cranes, trolleys, boxes, portVans, lifts, bridges, ships, shipMesh, boats, riverBoats, canalBoats, cl, side, hw, navLights, flow, streaks, mx, glowMats, ledMats, x0, x1, clock: 0 };
}

const pose = (R, x, y, heading, h) => poseAt(R, x, y, heading, h);

export function updateMeridian(md, dt) {
  if (!md) return;
  md.clock += dt;
  const night = state.klyaksaNight ?? 0, R = md.R, lvl = riverLevel(0);
  for (const m of md.glowMats) m.opacity = 0.05 + 0.55 * night;
  for (const m of md.ledMats) m.opacity = 0.75 * night;
  // ships: in from the sea along the river, into the basin to a berth, unload, back out to sea
  md.ships.forEach((s, i) => {
    if (s.wait > 0) { s.wait -= dt; }
    else {
      const go = (tx, ty, v) => { const dx = tx - s.x, dy = ty - s.y, d = Math.hypot(dx, dy); s.heading = Math.atan2(dy, dx); const st = Math.min(d, v * dt); s.x += (dx / (d || 1)) * st; s.y += (dy / (d || 1)) * st; return d < 3; };
      if (s.phase === "in") { { go(s.x - 16, riverCentre(s.x - 16), 14); if (s.x < 4) s.phase = "dock"; } }
      else if (s.phase === "dock") { if (go(i ? 60 : -60, -170, 4)) { s.phase = "unload"; s.wait = 90; } }
      else if (s.phase === "unload") s.phase = "undock";
      else if (s.phase === "undock") { if (go(0, riverCentre(0), 4)) s.phase = "out"; }
      else if (s.phase === "out") { { go(s.x + 16, riverCentre(s.x + 16), 14); if (s.x > md.mx - 50) { s.phase = "in"; s.wait = 90; } } }
    }
    md.shipMesh.setMatrixAt(i, pose(R, s.x, s.y, s.heading, lvl + 0.2).multiply(new T.Matrix4().makeScale(0.7, 0.7, 0.7)));
  });
  md.shipMesh.instanceMatrix.needsUpdate = true;
  // bascule bridges: a ship within 320 m of one, or under it, stops the traffic and lifts the leaves
  for (const b of md.bridges) {
    if (!b.leaves) continue;
    const cx = (b.n[0] + b.s[0]) / 2, near = md.ships.some((s) => s.phase !== "unload" && s.wait <= 0 && Math.abs(s.x - cx) < 320);
    b.red = near ? Math.min(1, b.red + dt / 4) : b.open > 0.01 ? b.red : Math.max(0, b.red - dt / 3);
    b.stop = b.red > 0;
    const target = near && b.red >= 1 ? 1 : 0;           // lights red and barriers down first, then the leaves rise
    b.open += Math.sign(target - b.open) * Math.min(Math.abs(target - b.open), dt / 9);
    for (const L of b.leaves) L.g.quaternion.copy(L.base).multiply(new T.Quaternion().setFromAxisAngle(new T.Vector3(1, 0, 0), -b.open * 1.25));
    for (const m of b.lightMats) m.color.setHex(b.stop ? 0xff2a1a : 0x29d36a);
  }
  state.meridianStops = new Set(md.bridges.filter((b) => b.stop).map((b) => b.road));
  // cranes work while a ship is at its berth
  const working = md.ships.some((s) => s.phase === "unload");
  md.cranes.forEach(([x, y, a], i) => {
    const t = working ? (md.clock * 0.1 + i * 0.25) % 1 : 0, reach = working ? Math.abs(Math.sin(t * Math.PI)) * 45 : 0;
    const dirx = a === 0 ? 1 : -1;
    md.trolleys.setMatrixAt(i, pose(R, x + dirx * (8 + reach), y, a, R * PLATEAU + 48.5));
    md.boxes.setMatrixAt(i, working ? pose(R, x + dirx * (8 + reach), y, a + Math.PI / 2, R * PLATEAU + 30 + 15 * Math.abs(Math.cos(t * Math.PI * 2))) : new T.Matrix4().makeScale(0, 0, 0));
  });
  md.trolleys.instanceMatrix.needsUpdate = true; md.boxes.instanceMatrix.needsUpdate = true;
  // the port's trucks shuttle between the quays and the port road; forklifts loop the stacks
  for (let i = 0; i < 10; i++) {
    const t = (md.clock * 0.02 + i / 10) % 1, x = (i % 2 ? md.x1 + 40 : md.x0 - 40), y = -420 + Math.abs(t * 2 - 1) * 360;
    md.portVans.setMatrixAt(i, pose(R, x, y, t < 0.5 ? Math.PI / 2 : -Math.PI / 2, R * PLATEAU + 0.3));
  }
  for (let i = 0; i < 8; i++) {
    const a = md.clock * 0.25 + i * 0.8, x = (i % 2 ? md.x1 + 55 : md.x0 - 55) + Math.cos(a) * 14, y = -250 + Math.sin(a) * 60;
    md.lifts.setMatrixAt(i, pose(R, x, y, a + Math.PI / 2, R * PLATEAU + 0.3));
  }
  md.portVans.instanceMatrix.needsUpdate = true; md.lifts.instanceMatrix.needsUpdate = true;
  // river boats go up and down between the stages; canal boats along the canal
  let li = 0;
  const lights = (x, y, h, z) => {
    for (const [dx, dy, dz] of [[-2.2, 0, 1.6], [2.2, 0, 1.6], [0, 2, 4.5]]) {
      const ox = x + Math.cos(h) * dy - Math.sin(h) * dx, oy = y + Math.sin(h) * dy + Math.cos(h) * dx;
      md.navLights.setMatrixAt(li++, night > 0.2 ? pose(R, ox, oy, h, z + dz) : new T.Matrix4().makeScale(0, 0, 0));
    }
  };
  md.riverBoats.forEach((b, i) => {
    b.x += b.dir * b.speed * dt;
    if (Math.abs(b.x) > 760) b.dir = -b.dir;
    const y = riverCentre(b.x) + b.lane * b.dir, h = b.dir > 0 ? Math.atan2(riverCentre(b.x + 5) - riverCentre(b.x), 5) : Math.atan2(riverCentre(b.x) - riverCentre(b.x + 5), -5);
    md.boats.setMatrixAt(i, pose(R, b.x, y, h, lvl + 0.1));
    lights(b.x, y, h, lvl);
  });
  md.canalBoats.forEach((b, i) => {
    b.s += b.dir * b.speed * dt;
    if (b.s > 0.98 || b.s < 0.02) { b.dir = -b.dir; b.s = Math.min(0.98, Math.max(0.02, b.s)); }
    const f = b.s * (md.cl.length - 1), k = Math.floor(f), u = f - k, a = md.cl[k], c = md.cl[Math.min(md.cl.length - 1, k + 1)];
    const lane = b.dir * 3, dx = c[0] - a[0], dy = c[1] - a[1], L = Math.hypot(dx, dy) || 1;
    const x = lerp(a[0], c[0], u) - (dy / L) * lane, y = lerp(a[1], c[1], u) + (dx / L) * lane, h = Math.atan2(dy, dx) + (b.dir < 0 ? Math.PI : 0);
    md.boats.setMatrixAt(12 + i, pose(R, x, y, h, lvl + 0.1).multiply(new T.Matrix4().makeScale(0.7, 0.7, 0.7)));
    lights(x, y, h, lvl);
  });
  md.ships.forEach((s) => lights(s.x, s.y, s.heading, lvl + 26));
  md.boats.instanceMatrix.needsUpdate = true; md.navLights.instanceMatrix.needsUpdate = true;
  // the estuary: streaks ride a current that fans out past the mouth and curls at its edges
  md.flow.forEach((p, i) => {
    const rc = riverCentre(Math.min(p.x, md.mx)), off = p.y - rc, past = Math.max(0, p.x - md.mx);
    const vx = 3.2 - past * 0.004, vy = off * (0.004 + past * 0.00006) + Math.sin(p.seed * 1.7 + md.clock * 0.2) * past * 0.006;
    p.x += vx * dt; p.y += vy * dt; p.age += dt;
    if (p.age > 70 || past > 520) { p.x = md.mx - 260 + Math.random() * 200; p.y = riverCentre(p.x) + (Math.random() - 0.5) * 2 * riverWidth(md.mx - 1); p.age = 0; }
    md.streaks.setMatrixAt(i, pose(R, p.x, p.y, Math.atan2(vy, vx) + Math.PI / 2, lvl + 0.25));
  });
  md.streaks.instanceMatrix.needsUpdate = true;
  md.streaks.material.opacity = 0.18 + 0.2 * (1 - night);
}
