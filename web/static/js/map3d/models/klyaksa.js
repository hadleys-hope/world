/** models/klyaksa: the new colony on Klyaksa. A branching chain of glass domes, each a city with the structure
 * of Hadley's Hope (rows of houses, roads, the towers of the hub), linked by glass corridors; forests, meadows
 * and flowers in the valleys around them; gardens inside. Plans come from /klyaksa/geometry.json once, the
 * state of every house from /klyaksa/state.json every two seconds while you look at Klyaksa.
 * What keeps it cheap: every house of every city is one InstancedMesh (one draw call for 5010 houses), every
 * road one mesh, the vegetation is chunked and only the chunks near the camera are drawn. */
import { state } from "../state.js";
import { bodyHeight, fbm3, PLATEAU, setSites } from "../geometry/noise.js";
import { chunkedInstances, instances, lifeMaterial, rockGeometry, treeGeometry, tuftGeometry } from "./life.js";
import { glassMaterial, makeDome } from "./oasis.js";
import * as THREE from "three";

const CENTRE = new THREE.Vector3(-0.66, 0.32, -0.68).normalize();   // the landing coast
const EAST = new THREE.Vector3(0, 1, 0).cross(CENTRE).normalize();
const NORTH = CENTRE.clone().cross(EAST).normalize();

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = Math.imul(s ^ (s >>> 15), 2246822507) + 0x9e3779b9) >>> 0) / 4294967296;
}

/** The unit direction of a plan position (metres east and north of the colony centre). */
export function dirAt(X, Y, R) {
  const d = Math.hypot(X, Y) / R;
  if (d < 1e-9) return CENTRE.clone();
  return CENTRE.clone().multiplyScalar(Math.cos(d)).addScaledVector(EAST.clone().multiplyScalar(X).addScaledVector(NORTH, Y).normalize(), Math.sin(d));
}

export function loadKlyaksa() {
  state.klyaksaPlan = fetch("/klyaksa/geometry.json").then((r) => (r.ok ? r.json() : null)).catch(() => null);
}

/** Before Klyaksa's surface is built: the plateaus under the cities. */
export async function klyaksaSites(R) {
  const plan = await state.klyaksaPlan;
  if (!plan) return null;
  setSites(plan.cities.map((c) => ({ dir: dirAt(c.at[0], c.at[1], R).toArray(), r: (c.wall + 160) / R })));
  return plan;
}

export function buildKlyaksa(steps, body, R, uniforms) {
  const plan = state.klyaksaPlanData;
  const ground = R * (1 + PLATEAU);
  const cityPoint = (c, x, y, h) => dirAt(c.at[0] + x, c.at[1] + y, R).multiplyScalar(ground + h);
  const env = { uTime: uniforms.uTime, uSun: uniforms.uLight };
  const rand = rng(5010);
  // 1. domes, corridors, roads
  steps.push(() => {
    const byId = Object.fromEntries(plan.cities.map((c) => [c.id, c]));
    for (const c of plan.cities) {
      const r = c.wall + 45;
      body.add(makeDome((x, y, up) => cityPoint(c, x, y, up - 0.5), r, r * 0.42, { uSun: uniforms.uLight }, 160));
    }
    // glass corridors along the branches, half sunk into the plateau, edge to edge
    const pos = [], uv = [], idx = [];
    for (const [a, b] of plan.branches) {
      const A = byId[a], B = byId[b], dx = B.at[0] - A.at[0], dy = B.at[1] - A.at[1], L = Math.hypot(dx, dy);
      const ux = dx / L, uy = dy / L, from = A.wall + 40, to = L - B.wall - 40, steps = Math.ceil((to - from) / 20);
      const base = pos.length / 3;
      for (let k = 0; k <= steps; k++) {
        const s = from + ((to - from) * k) / steps;
        for (let j = 0; j <= 12; j++) {
          const t = (j / 12) * Math.PI;
          const X = A.at[0] + ux * s - uy * Math.cos(t) * 32, Y = A.at[1] + uy * s + ux * Math.cos(t) * 32;
          const p = dirAt(X, Y, R).multiplyScalar(ground + Math.sin(t) * 26);
          pos.push(p.x, p.y, p.z);
          uv.push(j / 12 / 3, (s - from) / 400);
        }
        if (k < steps) for (let j = 0; j < 12; j++) {
          const q = base + k * 13 + j;
          idx.push(q, q + 13, q + 1, q + 1, q + 13, q + 14);
        }
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("aUV", new THREE.Float32BufferAttribute(uv, 2));
    g.setIndex(idx);
    g.computeVertexNormals();
    const tubes = new THREE.Mesh(g, glassMaterial({ uSun: uniforms.uLight }));
    tubes.renderOrder = 3;
    body.add(tubes);
    // roads of every city in one mesh
    const rp = [], ri = [];
    for (const c of plan.cities)
      for (const road of c.roads) {
        const w = road.width / 2;
        for (let k = 1; k < road.points.length; k++) {
          const [x0, y0] = road.points[k - 1], [x1, y1] = road.points[k], L = Math.hypot(x1 - x0, y1 - y0) || 1;
          const nx = -(y1 - y0) / L * w, ny = (x1 - x0) / L * w, b = rp.length / 3;
          for (const [x, y] of [[x0 + nx, y0 + ny], [x0 - nx, y0 - ny], [x1 + nx, y1 + ny], [x1 - nx, y1 - ny]]) {
            const p = cityPoint(c, x, y, 0.12);
            rp.push(p.x, p.y, p.z);
          }
          ri.push(b, b + 2, b + 1, b + 1, b + 2, b + 3);
        }
      }
    const rg = new THREE.BufferGeometry();
    rg.setAttribute("position", new THREE.Float32BufferAttribute(rp, 3));
    rg.setIndex(ri);
    rg.computeVertexNormals();
    body.add(new THREE.Mesh(rg, new THREE.MeshLambertMaterial({ color: 0x2a2d31, side: THREE.DoubleSide })));
  });
  // 2. the houses (one InstancedMesh for all) and the towers of every hub
  steps.push(() => {
    const items = [], towers = [];
    for (const c of plan.cities) {
      for (let i = 0; i < c.houses; i++) {
        const X = c.at[0] + c.x[i], Y = c.at[1] + c.y[i];
        items.push({ n: dirAt(X, Y, R).toArray(), h: ground - R, s: 1, sy: 0.8 + 0.25 * c.type[i], yaw: Math.atan2(c.y[i], c.x[i]) + Math.PI / 2, tint: [1, 1, 1] });
      }
      const tall = 60 + c.houses / 9;
      for (let k = 0; k < 7; k++) {
        const a = k * 2.39996, d = k === 0 ? 0 : 30 + (k % 3) * 22;
        towers.push({ n: dirAt(c.at[0] + Math.cos(a) * d, c.at[1] + Math.sin(a) * d, R).toArray(), h: ground - R, s: 1, sy: 1, yaw: a, tint: [1, 1, 1], height: tall * (k === 0 ? 1 : 0.45 + 0.35 * rand()) });
      }
    }
    const house = new THREE.BoxGeometry(9, 5, 11).translate(0, 2.5, 0);
    const roof = new THREE.ConeGeometry(7.6, 3, 4, 1).rotateY(Math.PI / 4).scale(1, 1, 1.25).translate(0, 6.5, 0);
    const hg = mergeColored([[house, 0xc9c2b4], [roof, 0x5b4038]]);
    state.klyaksaHouses = instances(hg, lifeMaterial(env, { indoor: 1, glow: 0.08 }), items, R);
    body.add(state.klyaksaHouses);
    const tg = mergeColored([[new THREE.BoxGeometry(18, 1, 18).translate(0, 0.5, 0), 0x8fa6b8]]);
    const towerMesh = instances(tg, lifeMaterial(env, { glow: 0.25 }), towers.map((t) => ({ ...t, s: 1, sy: t.height })), R);
    body.add(towerMesh);
  });
  // 3. gardens inside the domes: lawns, flowerbeds, trees, giant trees
  steps.push(() => {
    const grass = [], flowers = [], trees = [], giants = [];
    for (const c of plan.cities) {
      const near = new Set();
      const key = (x, y) => `${Math.round(x / 12)},${Math.round(y / 12)}`;
      for (let i = 0; i < c.houses; i++) near.add(key(c.x[i], c.y[i]));
      for (const road of c.roads) for (const [x, y] of road.points) near.add(key(x, y));
      const free = (x, y) => !near.has(key(x, y)) && Math.hypot(x, y) > c.hub + 10 && Math.hypot(x, y) < c.wall - 12;
      const area = (c.wall / 690) ** 2;
      for (let k = 0; k < 26000 * area; k++) {
        const d = Math.sqrt(rand()) * c.wall, a = rand() * Math.PI * 2, x = d * Math.cos(a), y = d * Math.sin(a);
        if (!free(x, y)) continue;
        const n = dirAt(c.at[0] + x, c.at[1] + y, R).toArray(), r = rand();
        if (r < 0.04) trees.push({ n, h: ground - R - 0.2, s: 2 + rand() * 2, tint: [0.9 + rand() * 0.2, 1, 0.85] });
        else if (r < 0.042) giants.push({ n, h: ground - R - 0.4, s: 6 + rand() * 3, tint: [0.9, 1, 0.85] });
        else if (r < 0.2) flowers.push({ n, h: ground - R - 0.03, s: 0.5 + rand() * 0.3, tint: [[1.6, 0.6, 1.1], [1.7, 1.5, 0.4], [1.2, 0.8, 1.7], [1.8, 1.8, 1.8]][Math.floor(rand() * 4)] });
        else grass.push({ n, h: ground - R - 0.05, s: 0.6 + rand() * 0.8, tint: [0.9 + rand() * 0.2, 1, 0.8] });
      }
    }
    const lod = state.klyaksaLod;
    const add = (g) => { body.add(g); lod.push(g); };
    add(chunkedInstances(() => tuftGeometry(0x2a4d1c, 0x8cc456), lifeMaterial(env, { sway: 0.16, indoor: 1 }), grass, R, { cell: 0.06, maxDist: 1600 }));
    add(chunkedInstances(() => tuftGeometry(0x2a4d1c, 0xffffff), lifeMaterial(env, { sway: 0.16, indoor: 1 }), flowers, R, { cell: 0.06, maxDist: 1600 }));
    add(chunkedInstances(() => treeGeometry("broad"), lifeMaterial(env, { sway: 0.004, indoor: 1 }), trees, R, { cell: 0.12, maxDist: 4500 }));
    body.add(instances(treeGeometry("broad"), lifeMaterial(env, { sway: 0.0015, indoor: 1 }), giants, R));
  });
  // 4. the valleys: forests on the slopes, meadows and flowers on the floors, boulders on the heights;
  // four steps, a quarter of the land each, so no single step holds the page for long
  for (let part = 0; part < 4; part++) steps.push(() => {
    const pines = [], broad = [], meadow = [], bloom = [], rocks = [];
    const domes = plan.cities.map((c) => ({ d: dirAt(c.at[0], c.at[1], R), r: (c.wall + 70) / R }));
    const inDome = (v) => domes.some((x) => v.angleTo(x.d) < x.r);
    const reach = 11000 / R;
    for (let k = 0; k < 105000 && pines.length + broad.length < 15000; k++) {
      const d = Math.sqrt(rand()) * reach, a = (part + rand()) * Math.PI / 2;
      const v = dirAt(Math.cos(a) * d * R, Math.sin(a) * d * R, R);
      if (inDome(v)) continue;
      const h = bodyHeight(3, v.x, v.y, v.z);
      if (h < 0.0004) continue;                                         // water, beach
      const forest = fbm3(v.x * 40, v.y * 40, v.z * 40, 3);
      const n = v.toArray(), hm = h * R;
      if (forest > 0.04 && h < 0.02) (h > 0.009 || rand() < 0.4 ? pines : broad).push({ n, h: hm - 0.3, s: 2.2 + rand() * 2.4, tint: [0.85 + rand() * 0.3, 0.9 + rand() * 0.2, 0.85] });
      else if (h < 0.006 && meadow.length < 30000) {
        for (let m = 0; m < 6; m++) {
          const w = dirAt(Math.cos(a) * d * R + (rand() - 0.5) * 30, Math.sin(a) * d * R + (rand() - 0.5) * 30, R);
          const hh = bodyHeight(3, w.x, w.y, w.z) * R;
          if (hh < 4) continue;
          (rand() < 0.12 ? bloom : meadow).push({ n: w.toArray(), h: hh - 0.05, s: 0.8 + rand() * 1.2, tint: rand() < 0.12 ? [1.7, 1.4, 0.4] : [0.9 + rand() * 0.2, 1, 0.8] });
        }
      } else if (h > 0.014 && rocks.length < 2500) rocks.push({ n, h: hm - 0.5, s: 1 + Math.pow(rand(), 3) * 12, sy: 0.7 + rand() * 0.6, tint: [0.95, 0.95, 0.95] });
    }
    const lod = state.klyaksaLod;
    const add = (g) => { body.add(g); lod.push(g); };
    add(chunkedInstances(() => treeGeometry("pine"), lifeMaterial(env, { sway: 0.004 }), pines, R, { cell: 0.12, maxDist: 5500 }));
    add(chunkedInstances(() => treeGeometry("broad"), lifeMaterial(env, { sway: 0.004 }), broad, R, { cell: 0.12, maxDist: 5500 }));
    add(chunkedInstances(() => tuftGeometry(0x2f5a1e, 0x9cc95a), lifeMaterial(env, { sway: 0.12 }), meadow, R, { cell: 0.06, maxDist: 1800 }));
    add(chunkedInstances(() => tuftGeometry(0x2f5a1e, 0xffffff), lifeMaterial(env, { sway: 0.12 }), bloom, R, { cell: 0.06, maxDist: 1800 }));
    add(chunkedInstances(rockGeometry, lifeMaterial(env), rocks, R, { cell: 0.12, maxDist: 6000 }));
    const c = (state.klyaksaCounts ||= { pines: 0, broad: 0, meadow: 0, bloom: 0, rocks: 0 });
    c.pines += pines.length; c.broad += broad.length; c.meadow += meadow.length; c.bloom += bloom.length; c.rocks += rocks.length;
  });
}

function mergeColored(parts) {
  const pos = [], nor = [], col = [];
  for (const [g, color] of parts) {
    const geo = g.toNonIndexed();
    geo.computeVertexNormals();
    const c = new THREE.Color(color), p = geo.attributes.position, n = geo.attributes.normal;
    for (let i = 0; i < p.count; i++) {
      pos.push(p.getX(i), p.getY(i), p.getZ(i));
      nor.push(n.getX(i), n.getY(i), n.getZ(i));
      col.push(c.r, c.g, c.b);
    }
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  out.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  out.setAttribute("aCol", new THREE.Float32BufferAttribute(col, 3));
  return out;
}

/** Houses take the colour of their state: cold blue to warm amber, dark without power. */
export function updateKlyaksa(now) {
  const lod = state.klyaksaLod;
  if (!lod || state.activeBody !== 3 || state.systemView) return;
  const body = state.solarSystem.bodies[3];
  if (state.klyaksaFrame === undefined || ++state.klyaksaFrame % 12 === 0) {
    const cam = state.camera.position.clone().sub(body.position);
    for (const g of lod) g.userData.update(cam);
    state.klyaksaFrame = state.klyaksaFrame || 0;
  }
  if (!state.klyaksaHouses || now - (state.klyaksaPolled || 0) < 2000) return;
  state.klyaksaPolled = now;
  fetch("/klyaksa/state.json").then((r) => r.json()).then((s) => {
    const tint = state.klyaksaHouses.geometry.attributes.aTint;
    let i = 0;
    for (const c of s.cities)
      for (let k = 0; k < c.t_in.length; k++, i++) {
        const t = Math.min(1, Math.max(0, (c.t_in[k] - 8) / 16)), powered = c.flags[k] & 1;
        const r = 0.55 + 0.6 * t, g = 0.7 + 0.15 * t, b = 1.25 - 0.55 * t, dim = powered ? 1 : 0.45;
        tint.setXYZ(i, r * dim, g * dim, b * dim);
      }
    tint.needsUpdate = true;
    state.klyaksaState = s;
  }).catch(() => {});
}
