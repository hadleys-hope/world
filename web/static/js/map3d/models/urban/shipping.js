/** urban/shipping: Klyaksa's sea trade. Container ships, bulk carriers, tankers, ferries, tugs and trawlers sail
 * sea routes between the port cities (state.klyaksaPorts, built by marine.js), berth at the quays, and gantry
 * cranes lift containers off them onto the yard; forklifts and straddle carriers work the yard, trucks and vans
 * run between the port and the city gate. One InstancedMesh per kind of vessel and vehicle; every pose is
 * computed on the client from the clock, so the trade costs the server nothing. */
import { state } from "../../state.js";
import { bodyHeight } from "../../geometry/noise.js";
import { dirAt } from "../klyaksa.js";
import * as T from "three";

const SPEED = 24; // m/s for the big ships on screen (sped up), the small craft faster
const DWELL = 150; // s at the berth while the cranes work
const _n = new T.Vector3(), _e = new T.Vector3(), _no = new T.Vector3(), _f = new T.Vector3(), _r = new T.Vector3();
const _m = new T.Matrix4(), _q = new T.Quaternion(), _s = new T.Vector3(1, 1, 1);

// ---------- geometry: boxes and cylinders merged with vertex colours ----------
function part(geo, color, x, y, z, ry = 0) {
  const g = geo.toNonIndexed().rotateY(ry).translate(x, y, z), c = new T.Color(color), n = g.attributes.position.count;
  const col = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) col.set([c.r, c.g, c.b], i * 3);
  g.setAttribute("color", new T.BufferAttribute(col, 3));
  return g;
}
function merge(parts) {
  const pos = [], nor = [], col = [];
  for (const g of parts) {
    g.computeVertexNormals();
    pos.push(...g.attributes.position.array); nor.push(...g.attributes.normal.array); col.push(...g.attributes.color.array);
  }
  const out = new T.BufferGeometry();
  out.setAttribute("position", new T.Float32BufferAttribute(pos, 3));
  out.setAttribute("normal", new T.Float32BufferAttribute(nor, 3));
  out.setAttribute("color", new T.Float32BufferAttribute(col, 3));
  return out;
}
const B = (w, h, d) => new T.BoxGeometry(w, h, d), C = (r, h, s = 10) => new T.CylinderGeometry(r, r, h, s);
const CONT = [0xb5452f, 0x2f6fa8, 0x3d8a4e, 0xd4a017, 0x8a8f96, 0x7a3e8e, 0xe07b2a];

function hull(length, beam, depth, color, bow = 0.16) {
  const parts = [part(B(beam, depth, length * (1 - bow)), color, 0, depth / 2, -length * bow / 2)];
  for (let k = 0; k < 4; k++) {           // a stepped bow, narrowing to the stem
    const f = 1 - (k + 1) / 5, l = (length * bow) / 4;
    parts.push(part(B(beam * f, depth, l), color, 0, depth / 2, length * (0.5 - bow) + l * (k + 0.5)));
  }
  parts.push(part(B(beam * 1.01, depth * 0.25, length * (1 - bow)), 0x2b2b2b, 0, depth * 0.12, -length * bow / 2)); // boot top
  return parts;
}
const KINDS = {
  container: () => {          // 160 m: stacks of containers forward, the tall bridge aft (needs bridges to open)
    const p = hull(160, 26, 12, 0x24384d);
    for (let row = 0; row < 14; row++) for (let tier = 0; tier < 4; tier++) for (let col = 0; col < 3; col++)
      p.push(part(B(7.6, 2.5, 9.8), CONT[(row * 7 + tier * 3 + col) % CONT.length], -8 + col * 8, 13.3 + tier * 2.6, -50 + row * 10.2));
    p.push(part(B(22, 22, 12), 0xe8e8e2, 0, 23, -70), part(B(26, 3, 10), 0xd8d8d0, 0, 35, -70), part(C(2, 12), 0x333333, 4, 40, -76));
    return merge(p);
  },
  bulk: () => {               // 130 m: hatches and deck cranes
    const p = hull(130, 22, 11, 0x7a2e24);
    for (let k = 0; k < 5; k++) p.push(part(B(15, 1.6, 14), 0x5a5f63, 0, 11.8, -38 + k * 19));
    for (let k = 0; k < 4; k++) p.push(part(C(0.8, 14), 0xd6b03a, 8, 18, -28 + k * 19), part(B(0.8, 0.8, 16), 0xd6b03a, 4, 24, -28 + k * 19, 0.6));
    p.push(part(B(18, 14, 10), 0xeaeae4, 0, 18, -56), part(C(1.6, 8), 0x333333, 0, 28, -60));
    return merge(p);
  },
  tanker: () => {             // 140 m: red hull, pipes along the deck, a manifold amidships
    const p = hull(140, 24, 12, 0x8c1f1f);
    p.push(part(B(20, 1.4, 104), 0x6f7a6f, 0, 12.7, 2));
    for (let k = -1; k <= 1; k += 2) p.push(part(C(0.7, 100).rotateX(Math.PI / 2), 0xb9b2a0, k * 4, 14, 2));
    p.push(part(B(10, 4, 6), 0xb9b2a0, 0, 15, 2), part(B(20, 16, 11), 0xf0efe8, 0, 20, -60), part(C(1.8, 9), 0x2a2a2a, 0, 31, -63));
    return merge(p);
  },
  ferry: () => {              // 90 m: white, three decks of windows
    const p = hull(90, 18, 8, 0xf2f2ee, 0.2);
    for (let d = 0; d < 3; d++) p.push(part(B(16 - d * 2, 3.2, 60 - d * 10), d % 2 ? 0x1f4f7a : 0xf7f7f3, 0, 9.6 + d * 3.3, -2));
    p.push(part(C(1.6, 6), 0xc0392b, 0, 21, -10));
    return merge(p);
  },
  tug: () => {                // 26 m: red and black, a high wheelhouse
    const p = hull(26, 9, 4, 0x1e1e1e, 0.25);
    p.push(part(B(8.6, 1, 26 * 0.75), 0xb22a2a, 0, 4.5, -1), part(B(5, 4, 6), 0xf2f2ee, 0, 7, 2), part(B(5.4, 1.5, 6.4), 0x2b6fa8, 0, 9.6, 2), part(C(0.5, 5), 0x111111, 0, 9, -3));
    return merge(p);
  },
  trawler: () => {            // 32 m: an A-frame over the stern for the nets
    const p = hull(32, 9, 4.5, 0x2d6a4f, 0.22);
    p.push(part(B(6, 4, 7), 0xf0f0e6, 0, 6.5, 6), part(C(0.4, 9), 0xe0a020, -3, 9, -11), part(C(0.4, 9), 0xe0a020, 3, 9, -11), part(B(6.4, 0.5, 0.5), 0xe0a020, 0, 13.5, -11));
    return merge(p);
  },
  forklift: () => merge([part(B(1.4, 1.2, 2.6), 0xe0b020, 0, 0.9, 0), part(B(1.2, 1.4, 1.2), 0x222222, 0, 2.2, -0.4), part(B(0.1, 2.8, 0.1), 0x333333, -0.5, 1.6, 1.4), part(B(0.1, 2.8, 0.1), 0x333333, 0.5, 1.6, 1.4), part(B(1.2, 0.1, 1.2), 0x555555, 0, 0.4, 1.9)]),
  straddle: () => merge([part(B(0.6, 12, 0.6), 0x2b6fa8, -3.4, 6, -5), part(B(0.6, 12, 0.6), 0x2b6fa8, 3.4, 6, -5), part(B(0.6, 12, 0.6), 0x2b6fa8, -3.4, 6, 5), part(B(0.6, 12, 0.6), 0x2b6fa8, 3.4, 6, 5), part(B(7.4, 1.2, 11), 0x2b6fa8, 0, 12.4, 0), part(B(2, 2, 2.4), 0xf2f2ee, 3, 14, 4), part(B(2.4, 2.5, 9.8), 0xb5452f, 0, 7, 0)]),
  truck: () => merge([part(B(2.5, 3, 3), 0xd8d8d8, 0, 2.2, 7.5), part(B(2.5, 1, 13), 0x333333, 0, 1.1, 0), part(B(2.4, 2.6, 12), CONT[1], 0, 2.9, -1), part(C(0.5, 2.6).rotateZ(Math.PI / 2), 0x111111, 0, 0.5, 6), part(C(0.5, 2.6).rotateZ(Math.PI / 2), 0x111111, 0, 0.5, -5)]),
  van: () => merge([part(B(2.1, 2.4, 5.6), 0xf4f4f0, 0, 1.6, 0), part(B(1.9, 0.9, 1.2), 0x2b3b4b, 0, 2.2, 2.3), part(C(0.38, 2.2).rotateZ(Math.PI / 2), 0x111111, 0, 0.4, 1.8), part(C(0.38, 2.2).rotateZ(Math.PI / 2), 0x111111, 0, 0.4, -1.8)]),
  crane: () => merge([           // ship-to-shore gantry crane: four legs, the boom out over the water, the machinery house
    part(B(1.6, 46, 1.6), 0xd94f2a, -8, 23, -8), part(B(1.6, 46, 1.6), 0xd94f2a, 8, 23, -8), part(B(1.6, 46, 1.6), 0xd94f2a, -8, 23, 8), part(B(1.6, 46, 1.6), 0xd94f2a, 8, 23, 8),
    part(B(18, 1.8, 1.8), 0xd94f2a, 0, 30, -8), part(B(18, 1.8, 1.8), 0xd94f2a, 0, 30, 8),
    part(B(4, 3, 90), 0xd94f2a, 0, 48, 20), part(B(8, 6, 10), 0xeeeeee, 0, 52, -16), part(B(0.8, 22, 0.8), 0xd94f2a, 0, 60, -6)]),
  trolley: () => merge([part(B(4.6, 2.2, 4), 0x444444, 0, 0, 0), part(B(2.4, 2, 2.4), 0xf0f0f0, 0, -2, 0)]),
  box: () => merge([part(B(2.4, 2.6, 12), 0xffffff, 0, 1.3, 0)]),
};

// ---------- placement on the planet ----------
function frameAt(R, x, y, heading, h) {
  _n.copy(dirAt(x, y, R));
  _e.copy(dirAt(x + 1, y, R)).sub(_n).normalize();
  _no.copy(dirAt(x, y + 1, R)).sub(_n).normalize();
  _f.copy(_e).multiplyScalar(Math.cos(heading)).addScaledVector(_no, Math.sin(heading)).normalize();
  _r.crossVectors(_n, _f).normalize();
  _f.crossVectors(_r, _n);
  _q.setFromRotationMatrix(_m.makeBasis(_r, _n, _f));
  return _n.multiplyScalar(R + h);
}
const wet = (R, x, y) => { const n = dirAt(x, y, R); return bodyHeight(3, n.x, n.y, n.z) * R < -4; };

function seaLeg(R, a, b) {
  for (let k = 1; k < 40; k++) if (!wet(R, a[0] + ((b[0] - a[0]) * k) / 40, a[1] + ((b[1] - a[1]) * k) / 40)) return false;
  return true;
}
/** Water route between two offshore points: straight, or bent once or twice away from the colony's land. */
function route(R, a, b) {
  if (seaLeg(R, a, b)) return [a, b];
  for (const push of [1.5, 2.2, 3.2]) {
    const mid = [((a[0] + b[0]) / 2) * push, ((a[1] + b[1]) / 2) * push];
    if (wet(R, ...mid) && seaLeg(R, a, mid) && seaLeg(R, mid, b)) return [a, mid, b];
  }
  return null;
}

export function buildShipping(body, R, env) {
  const ports = (state.klyaksaPorts || []).map((p) => {
    const co = Math.cos(p.coast.a), si = Math.sin(p.coast.a);
    const xy = (u, v) => [p.x + co * u - si * v, p.y + si * u + co * v];
    let off = null;
    for (let d = 900; d <= 3200 && !off; d += 300) if (wet(R, ...xy(d, 0))) off = xy(d, 0);
    return { p, xy, co, si, a: p.coast.a, off, berths: [-90, 0, 90].map((v) => ({ v, at: xy(150, v), busy: null })) };
  }).filter((x) => x.off);
  if (!ports.length) return null;
  const routes = new Map();
  for (const A of ports) for (const Bp of ports) if (A !== Bp) routes.set(A.p.city + Bp.p.city, route(R, A.off, Bp.off));
  const mats = {};
  const mesh = (kind, n) => {
    const m = new T.InstancedMesh(KINDS[kind](), mats[kind] ||= new T.MeshStandardMaterial({ vertexColors: true, roughness: 0.6, metalness: 0.15 }), n);
    m.frustumCulled = false; m.castShadow = false;
    body.add(m);
    return m;
  };
  const FLEET = { container: 5, bulk: 2, tanker: 2, ferry: 2, tug: 4, trawler: 4 };
  const meshes = Object.fromEntries(Object.entries(FLEET).map(([k, n]) => [k, mesh(k, n * ports.length)]));
  const ships = [];
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  ports.forEach((home, pi) => {
    for (const [kind, n] of Object.entries(FLEET))
      for (let k = 0; k < n; k++) {
        const s = { kind, idx: pi * n + k, home, x: home.off[0] + rnd() * 600 - 300, y: home.off[1] + rnd() * 600 - 300, heading: rnd() * 6.28, path: [], wait: rnd() * 60, berth: null, phase: rnd() * 6.28 };
        ships.push(s);
      }
  });
  // cranes at every berth, a trolley and a container each
  const cranes = ports.flatMap((P) => P.berths.map((b) => ({ P, b })));
  const craneMesh = mesh("crane", cranes.length), trolleyMesh = mesh("trolley", cranes.length), boxMesh = mesh("box", cranes.length + ports.length * 260);
  cranes.forEach(({ P, b }, i) => {
    const at = P.xy(110, b.v), pos = frameAt(R, at[0], at[1], P.a, 3.7);
    craneMesh.setMatrixAt(i, _m.compose(pos, _q, _s));
  });
  craneMesh.instanceMatrix.needsUpdate = true;
  // the yard: container stacks on the pier
  let bi = cranes.length;
  const tint = new Float32Array((cranes.length + ports.length * 260) * 3).fill(1);
  for (const P of ports)
    for (let k = 0; k < 260; k++) {
      const row = k % 13, col = Math.floor(k / 13) % 10, tier = Math.floor(k / 130);
      const at = P.xy(18 + row * 4.6, -66 + col * 14), pos = frameAt(R, at[0], at[1], P.a + Math.PI / 2, 3.7 + tier * 2.7);
      boxMesh.setMatrixAt(bi, _m.compose(pos, _q, _s));
      const c = new T.Color(CONT[(k * 5 + tier) % CONT.length]);
      tint.set([c.r, c.g, c.b], bi * 3);
      bi++;
    }
  boxMesh.instanceColor = new T.InstancedBufferAttribute(tint, 3);
  boxMesh.instanceMatrix.needsUpdate = true;
  // port vehicles: forklifts and straddle carriers loop the yard, trucks and vans run to the city gate and back
  const VEH = { forklift: 8, straddle: 4, truck: 8, van: 6 };
  const vmesh = Object.fromEntries(Object.entries(VEH).map(([k, n]) => [k, mesh(k, n * ports.length)]));
  const vehicles = [];
  ports.forEach((P, pi) => {
    const road = (P.p.accessPoints || []).map((q) => (Array.isArray(q) ? q : [q.x, q.y]));
    for (const [kind, n] of Object.entries(VEH))
      for (let k = 0; k < n; k++) vehicles.push({ kind, idx: pi * n + k, P, road, t: k / n, speed: kind === "truck" || kind === "van" ? 0.012 + 0.004 * (k % 3) : 0.03 + 0.01 * (k % 2) });
  });
  return { ports, routes, ships, meshes, cranes, craneMesh, trolleyMesh, boxMesh, vehicles, vmesh, R, clock: 0 };
}

function steer(s, tx, ty, dt, speed) {
  const dx = tx - s.x, dy = ty - s.y, d = Math.hypot(dx, dy);
  const want = Math.atan2(dy, dx), turn = Math.atan2(Math.sin(want - s.heading), Math.cos(want - s.heading));
  s.heading += Math.max(-0.12 * dt, Math.min(0.12 * dt, turn));
  const v = Math.min(speed, d) * dt;
  s.x += Math.cos(s.heading) * v; s.y += Math.sin(s.heading) * v;
  return d < speed * 1.5;
}

function plan(sh, s) {
  // a merchant ship: home anchorage -> another port's anchorage (by sea) -> its berth; small craft stay local
  if (s.kind === "tug" || s.kind === "trawler") {
    const P = s.home, r = s.kind === "tug" ? 260 : 1600, a = Math.random() * 6.28;
    s.path = [[P.off[0] + Math.cos(a) * r * (s.kind === "tug" ? 0 : 1) + (s.kind === "tug" ? P.xy(200, (Math.random() - 0.5) * 300)[0] - P.off[0] : 0),
      P.off[1] + Math.sin(a) * r * (s.kind === "tug" ? 0 : 1) + (s.kind === "tug" ? P.xy(200, (Math.random() - 0.5) * 300)[1] - P.off[1] : 0)]];
    s.wait = 20 + Math.random() * 40;
    return;
  }
  const others = sh.ports.filter((P) => P !== s.home && sh.routes.get(s.home.p.city + P.p.city));
  const dest = others.length ? others[Math.floor(Math.random() * others.length)] : s.home;
  const sea = dest === s.home ? [[s.home.off[0] * 1.4, s.home.off[1] * 1.4], s.home.off] : sh.routes.get(s.home.p.city + dest.p.city);
  s.dest = dest;
  s.path = [s.home.off, ...sea.slice(1)];
}

export function updateShipping(sh, dt) {
  if (!sh) return;
  sh.clock += dt;
  const R = sh.R;
  for (const s of sh.ships) {
    const speed = s.kind === "tug" ? 9 : s.kind === "trawler" ? 7 : s.kind === "ferry" ? SPEED * 1.2 : SPEED;
    if (s.wait > 0) { s.wait -= dt; }
    else if (s.berth) {                                  // done at the berth: leave for the anchorage
      s.berth.busy = null; s.berth = null; s.home = s.dest || s.home; plan(sh, s);
    } else if (!s.path.length) {
      if (s.dest && s.kind !== "tug" && s.kind !== "trawler") {
        const free = s.dest.berths.find((b) => !b.busy);
        if (free && !s.approach) { free.busy = s; s.approach = free; s.path = [free.at]; }
        else if (s.approach) { s.berth = s.approach; s.approach = null; s.wait = s.kind === "ferry" ? 40 : DWELL; s.heading = s.dest.a + Math.PI / 2; }
        else s.wait = 30;                                  // all berths taken: wait at anchor
      } else plan(sh, s);
    } else if (steer(s, s.path[0][0], s.path[0][1], dt, speed)) s.path.shift();
    const pos = frameAt(R, s.x, s.y, s.heading, 0.2 + Math.sin(sh.clock * 1.3 + s.phase) * 0.15);
    sh.meshes[s.kind].setMatrixAt(s.idx, _m.compose(pos, _q, _s));
  }
  for (const k in sh.meshes) sh.meshes[k].instanceMatrix.needsUpdate = true;
  // cranes: when their berth holds a ship, the trolley shuttles a container from the ship to the quay
  sh.cranes.forEach(({ P, b }, i) => {
    const work = b.busy && b.busy.berth === b, t = work ? (sh.clock * 0.08 + i * 0.3) % 1 : 0;
    const u = work ? 150 - Math.abs(Math.sin(t * Math.PI)) * 80 : 112;     // out over the ship and back to the quay
    const lift = work ? 30 + 18 * Math.abs(Math.cos(t * Math.PI * 2)) : 46;
    const at = P.xy(u, b.v);
    let pos = frameAt(R, at[0], at[1], P.a, 3.7 + 48);
    sh.trolleyMesh.setMatrixAt(i, _m.compose(pos, _q, _s));
    pos = frameAt(R, at[0], at[1], P.a + Math.PI / 2, 3.7 + lift - 6);
    sh.boxMesh.setMatrixAt(i, _m.compose(pos, _q, work ? _s : new T.Vector3(0.001, 0.001, 0.001)));
  });
  sh.trolleyMesh.instanceMatrix.needsUpdate = true;
  sh.boxMesh.instanceMatrix.needsUpdate = true;
  // the port's vehicles
  for (const v of sh.vehicles) {
    v.t = (v.t + v.speed * dt * 0.1) % 1;
    let x, y, heading;
    if ((v.kind === "truck" || v.kind === "van") && v.road.length > 1) {
      const there = v.t < 0.5, f = there ? v.t * 2 : 2 - v.t * 2, L = v.road.length - 1;
      const k = Math.min(L - 1, Math.floor(f * L)), u = f * L - k, a = v.road[k], b = v.road[k + 1];
      x = a[0] + (b[0] - a[0]) * u; y = a[1] + (b[1] - a[1]) * u;
      heading = Math.atan2(b[1] - a[1], b[0] - a[0]) + (there ? 0 : Math.PI);
      const side = there ? 2.2 : -2.2;
      x += -Math.sin(heading) * side; y += Math.cos(heading) * side;
    } else {                                              // a rounded rectangle round the stacks
      const a = v.t * Math.PI * 2, uu = 50 + Math.cos(a) * 42, vv = Math.sin(a) * 92;
      [x, y] = v.P.xy(uu, vv);
      heading = v.P.a + Math.atan2(Math.cos(a) * 92, -Math.sin(a) * 42);
    }
    const pos = frameAt(R, x, y, heading, 3.75);
    sh.vmesh[v.kind].setMatrixAt(v.idx, _m.compose(pos, _q, _s));
  }
  for (const k in sh.vmesh) sh.vmesh[k].instanceMatrix.needsUpdate = true;
}
