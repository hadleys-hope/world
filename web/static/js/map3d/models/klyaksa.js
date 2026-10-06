import { buildUtilitiesSteps } from "./urban/utilities.js";
import { buildTelecom } from "./urban/telecom.js";
import { buildConnections } from "./urban/connections.js";
import { worldPointToBody } from "../geometry/body-frame.js";
import { createPlacement, roadClearance } from "./urban/placement.js";
import {
  buildIndustry,
  syncCityVisuals,
  updateCityVehicles,
} from "./urban/industry.js";
import {
  enableCityRiver,
  configureCityRiver,
  riverContains,
} from "./urban/geography.js";
import { buildWaterfrontSteps, updateMarine } from "./urban/marine.js";
/** models/klyaksa: the new colony on Klyaksa. A branching chain of glass domes, each a city with the structure
 * of Hadley's Hope (rows of houses, roads, the towers of the hub), linked by glass corridors; forests, meadows
 * and flowers in the valleys around them; gardens inside. Plans come from /klyaksa/geometry.json once, the
 * state of every house from /klyaksa/state.json every two seconds while you look at Klyaksa.
 * What keeps it cheap: every house of every city is one InstancedMesh (one draw call for 5010 houses), every
 * road one mesh, the vegetation is chunked and only the chunks near the camera are drawn. */
import { buildHomes } from "./urban/buildings.js";
import { buildDistrict, reservation } from "./urban/streets.js";
import { state } from "../state.js";
import { bodyHeight, fbm3, PLATEAU, setSites } from "../geometry/noise.js";
import {
  chunkedInstances,
  instances,
  lifeMaterial,
  rockGeometry,
  treeGeometry,
  tuftGeometry,
} from "./life.js";
import * as THREE from "three";

const CENTRE = new THREE.Vector3(-0.66, 0.32, -0.68).normalize(); // the landing coast
const EAST = new THREE.Vector3(0, 1, 0).cross(CENTRE).normalize();
const NORTH = CENTRE.clone().cross(EAST).normalize();

function rng(seed) {
  let s = seed >>> 0;
  return () =>
    ((s = Math.imul(s ^ (s >>> 15), 2246822507) + 0x9e3779b9) >>> 0) /
    4294967296;
}

/** The unit direction of a plan position (metres east and north of the colony centre). */
export function dirAt(X, Y, R) {
  const d = Math.hypot(X, Y) / R;
  if (d < 1e-9) return CENTRE.clone();
  return CENTRE.clone()
    .multiplyScalar(Math.cos(d))
    .addScaledVector(
      EAST.clone().multiplyScalar(X).addScaledVector(NORTH, Y).normalize(),
      Math.sin(d),
    );
}

export function loadKlyaksa() {
  state.klyaksaPlan = fetch("/klyaksa/geometry.json")
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
}

/** Before Klyaksa's surface is built: the plateaus under the cities. */
export async function klyaksaSites(R) {
  const plan = await state.klyaksaPlan;
  if (!plan) return null;
  enableCityRiver(R);
  const sites = plan.cities.flatMap((c) => [
    { dir: dirAt(...c.at, R).toArray(), r: (c.wall + 160) / R },
    ...Object.entries(c.facilities || {}).map(([kind, [x, y]]) => ({
      dir: dirAt(c.at[0] + x, c.at[1] + y, R).toArray(),
      r: (kind === "reactor_pos" ? 128 : 65) / R,
    })),
  ]);
  const byId = Object.fromEntries(plan.cities.map((c) => [c.id, c]));
  for (const [a, b] of plan.branches) {
    const A = byId[a],
      B = byId[b],
      dx = B.at[0] - A.at[0],
      dy = B.at[1] - A.at[1],
      L = Math.hypot(dx, dy);
    for (let d = A.wall; d < L - B.wall; d += 70)
      sites.push({
        dir: dirAt(A.at[0] + (dx * d) / L, A.at[1] + (dy * d) / L, R).toArray(),
        r: 40 / R,
      });
  }
  // Prepare connected service corridors before the terrain mesh is sampled.
  for (const c of plan.cities)
    for (const road of c.service_roads || []) {
      for (let i = 1; i < road.points.length; i++) {
        const A = road.points[i - 1],
          B = road.points[i];
        const L = Math.hypot(B[0] - A[0], B[1] - A[1]);
        const count = Math.max(1, Math.ceil(L / 50));
        for (let j = 0; j <= count; j++)
          sites.push({
            dir: dirAt(
              c.at[0] + A[0] + ((B[0] - A[0]) * j) / count,
              c.at[1] + A[1] + ((B[1] - A[1]) * j) / count,
              R,
            ).toArray(),
            r: 36 / R,
          });
      }
    }
  const distinctSites = new Map();
  for (const site of sites) {
    const key = site.dir.map((n) => Math.round((n * R) / 25)).join(",");
    if (!distinctSites.has(key) || distinctSites.get(key).r < site.r)
      distinctSites.set(key, site);
  }
  setSites([...distinctSites.values()]);
  configureCityRiver(R, (x, y) => {
    const n = dirAt(x, y, R);
    return bodyHeight(3, n.x, n.y, n.z, true) * R;
  });
  return plan;
}

export function buildKlyaksa(steps, body, R, uniforms) {
  const plan = state.klyaksaPlanData;
  const ground = R * (1 + PLATEAU);
  const env = { uTime: uniforms.uTime, uSun: uniforms.uLight };
  const rand = rng(5010);
  // The same gate coordinates terminate both the road graph and the open galleries.
  steps.push(() => buildConnections(plan, body, R, { uSun: uniforms.uLight }));
  const globalPoint = createPlacement(R, plan);
  steps.push(() => buildHomes(body, R, plan, globalPoint, env));
  for (const c of plan.cities)
    steps.push(() => {
      const build = buildDistrict(c, body, R, globalPoint, env);
      const next = () => {
        if (!build.next().done) steps.unshift(next);
      };
      next.task = `district/${c.id}`;
      next();
    });
  for (const c of plan.cities) {
    steps.push(() => buildIndustry(c, body, R, env));
    steps.push(() => {
      const build = buildUtilitiesSteps(c, body, R, env);
      const next = () => {
        if (!build.next().done) steps.unshift(next);
      };
      next.task = `utilities/${c.id}`;
      next();
    });
    steps.push(() => buildTelecom(c, body, R, env));
  }
  steps.push(() => {
    const build = buildWaterfrontSteps(body, R, plan, env, globalPoint);
    const next = () => {
      if (!build.next().done) steps.unshift(next);
    };
    next.task = "waterfront";
    next();
  });
  // 3. gardens inside the domes, one city per idle task.
  for (const gardenCity of plan.cities)
    steps.push(() => {
      const grass = [],
        flowers = [],
        trees = [],
        giants = [];
      for (const c of [gardenCity]) {
        const reserved = state.klyaksaReservations?.get(c.id) || reservation(c);
        const free = (x, y) =>
          reserved.free(x, y, 3) &&
          !riverContains(c.at[0] + x, c.at[1] + y, 20) &&
          Math.hypot(x, y) > c.hub + 70 &&
          Math.hypot(x, y) < c.wall - 12;
        const area = (c.wall / 690) ** 2;
        for (let k = 0; k < 26000 * area; k++) {
          const d = Math.sqrt(rand()) * c.wall,
            a = rand() * Math.PI * 2,
            x = d * Math.cos(a),
            y = d * Math.sin(a);
          if (!free(x, y)) continue;
          const n = dirAt(c.at[0] + x, c.at[1] + y, R).toArray(),
            r = rand();
          if (r < 0.04)
            trees.push({
              n,
              h: ground - R - 0.2,
              s: 2 + rand() * 2,
              tint: [0.9 + rand() * 0.2, 1, 0.85],
            });
          else if (r < 0.042)
            giants.push({
              n,
              h: ground - R - 0.4,
              s: 6 + rand() * 3,
              tint: [0.9, 1, 0.85],
            });
          else if (r < 0.2)
            flowers.push({
              n,
              h: ground - R - 0.03,
              s: 0.5 + rand() * 0.3,
              tint: [
                [1.6, 0.6, 1.1],
                [1.7, 1.5, 0.4],
                [1.2, 0.8, 1.7],
                [1.8, 1.8, 1.8],
              ][Math.floor(rand() * 4)],
            });
          else
            grass.push({
              n,
              h: ground - R - 0.05,
              s: 0.6 + rand() * 0.8,
              tint: [0.9 + rand() * 0.2, 1, 0.8],
            });
        }
      }
      const lod = state.klyaksaLod;
      const add = (g) => {
        body.add(g);
        lod.push(g);
      };
      add(
        chunkedInstances(
          () => tuftGeometry(0x2a4d1c, 0x8cc456),
          lifeMaterial(env, { sway: 0.16, indoor: 1 }),
          grass,
          R,
          { cell: 0.06, maxDist: 1600 },
        ),
      );
      add(
        chunkedInstances(
          () => tuftGeometry(0x2a4d1c, 0xffffff),
          lifeMaterial(env, { sway: 0.16, indoor: 1 }),
          flowers,
          R,
          { cell: 0.06, maxDist: 1600 },
        ),
      );
      add(
        chunkedInstances(
          () => treeGeometry("broad"),
          lifeMaterial(env, { sway: 0.004, indoor: 1 }),
          trees,
          R,
          { cell: 0.12, maxDist: 4500 },
        ),
      );
      body.add(
        instances(
          treeGeometry("broad"),
          lifeMaterial(env, { sway: 0.0015, indoor: 1 }),
          giants,
          R,
        ),
      );
    });
  // 4. the valleys: forests on the slopes, meadows and flowers on the floors, boulders on the heights;
  // Preserve eight spatial sectors while yielding during sampling and geometry assembly.
  let nearPortRoad;
  for (let part = 0; part < 8; part++) {
    const build = (function* () {
      nearPortRoad ||= roadClearance(
        (state.klyaksaPorts || []).map(
          (port) => port.accessPoints || port.access,
        ),
      );
      const pines = [],
        broad = [],
        meadow = [],
        bloom = [],
        rocks = [];
      const domes = plan.cities.map((c) => ({
        d: dirAt(c.at[0], c.at[1], R),
        r: (c.wall + 70) / R,
      }));
      const inDome = (v) => domes.some((x) => v.angleTo(x.d) < x.r);
      const reach = 11000 / R;
      for (let k = 0; k < 52500 && pines.length + broad.length < 7500; k++) {
        if (k && k % 2048 === 0) yield;
        const d = Math.sqrt(rand()) * reach,
          a = ((part + rand()) * Math.PI) / 4;
        const v = dirAt(Math.cos(a) * d * R, Math.sin(a) * d * R, R);
        if (inDome(v)) continue;
        const X = Math.cos(a) * d * R,
          Y = Math.sin(a) * d * R;
        if (riverContains(X, Y, 45)) continue;
        // Keep crowns and offset meadow tufts out of the maritime access roads.
        if (nearPortRoad(X, Y)) continue;
        if (
          plan.cities.some(
            (c) =>
              Math.hypot(X - c.at[0], Y - c.at[1]) < c.wall + 1900 &&
              !state.klyaksaReservations
                .get(c.id)
                .free(X - c.at[0], Y - c.at[1], 4),
          )
        )
          continue;
        if (
          plan.branches.some(([a, b]) => {
            const A = plan.cities.find((c) => c.id === a).at,
              B = plan.cities.find((c) => c.id === b).at,
              dx = B[0] - A[0],
              dy = B[1] - A[1],
              t = Math.max(
                0,
                Math.min(
                  1,
                  ((X - A[0]) * dx + (Y - A[1]) * dy) / (dx * dx + dy * dy),
                ),
              );
            return Math.hypot(X - A[0] - dx * t, Y - A[1] - dy * t) < 45;
          })
        )
          continue;
        const h = bodyHeight(3, v.x, v.y, v.z);
        if (h < 0.0004) continue; // water, beach
        const forest = fbm3(v.x * 40, v.y * 40, v.z * 40, 3);
        const n = v.toArray(),
          hm = h * R;
        if (forest > 0.04 && h < 0.02)
          (h > 0.009 || rand() < 0.4 ? pines : broad).push({
            n,
            h: hm - 0.3,
            s: 2.2 + rand() * 2.4,
            tint: [0.85 + rand() * 0.3, 0.9 + rand() * 0.2, 0.85],
          });
        else if (h < 0.006 && meadow.length < 15000) {
          for (let m = 0; m < 6; m++) {
            const gx = Math.cos(a) * d * R + (rand() - 0.5) * 30;
            const gy = Math.sin(a) * d * R + (rand() - 0.5) * 30;
            if (riverContains(gx, gy, 20)) continue;
            const w = dirAt(gx, gy, R);
            const hh = bodyHeight(3, w.x, w.y, w.z) * R;
            if (hh < 4) continue;
            (rand() < 0.12 ? bloom : meadow).push({
              n: w.toArray(),
              h: hh - 0.05,
              s: 0.8 + rand() * 1.2,
              tint:
                rand() < 0.12 ? [1.7, 1.4, 0.4] : [0.9 + rand() * 0.2, 1, 0.8],
            });
          }
        } else if (h > 0.014 && rocks.length < 1250)
          rocks.push({
            n,
            h: hm - 0.5,
            s: 1 + Math.pow(rand(), 3) * 12,
            sy: 0.7 + rand() * 0.6,
            tint: [0.95, 0.95, 0.95],
          });
      }
      const lod = state.klyaksaLod;
      const add = (g) => {
        body.add(g);
        lod.push(g);
      };
      yield;
      add(
        chunkedInstances(
          () => treeGeometry("pine"),
          lifeMaterial(env, { sway: 0.004 }),
          pines,
          R,
          {
            cell: 0.12,
            maxDist: 5500,
            farGeometry: () => treeGeometry("pine", true),
          },
        ),
      );
      yield;
      add(
        chunkedInstances(
          () => treeGeometry("broad"),
          lifeMaterial(env, { sway: 0.004 }),
          broad,
          R,
          {
            cell: 0.12,
            maxDist: 5500,
            farGeometry: () => treeGeometry("broad", true),
          },
        ),
      );
      yield;
      add(
        chunkedInstances(
          () => tuftGeometry(0x2f5a1e, 0x9cc95a),
          lifeMaterial(env, { sway: 0.12 }),
          meadow,
          R,
          { cell: 0.06, maxDist: 1800 },
        ),
      );
      yield;
      add(
        chunkedInstances(
          () => tuftGeometry(0x2f5a1e, 0xffffff),
          lifeMaterial(env, { sway: 0.12 }),
          bloom,
          R,
          { cell: 0.06, maxDist: 1800 },
        ),
      );
      yield;
      add(
        chunkedInstances(rockGeometry, lifeMaterial(env), rocks, R, {
          cell: 0.12,
          maxDist: 6000,
        }),
      );
      const c = (state.klyaksaCounts ||= {
        pines: 0,
        broad: 0,
        meadow: 0,
        bloom: 0,
        rocks: 0,
      });
      c.pines += pines.length;
      c.broad += broad.length;
      c.meadow += meadow.length;
      c.bloom += bloom.length;
      c.rocks += rocks.length;
    })();
    const next = () => {
      if (!build.next().done) steps.unshift(next);
    };
    next.task = `wilderness/${part}`;
    steps.push(next);
  }
}

/** Houses take the colour of their state: cold blue to warm amber, dark without power. */
export function updateKlyaksa(now) {
  updateMarine(now);
  const lod = state.klyaksaLod;
  if (!lod || state.activeBody !== 3 || state.systemView) return;
  const body = state.solarSystem.bodies[3];
  updateCityVehicles(now);
  if (state.klyaksaFrame === undefined || ++state.klyaksaFrame % 12 === 0) {
    const cam = worldPointToBody(3, state.camera.position);
    for (const g of lod) g.userData.update(cam);
    state.klyaksaFrame = state.klyaksaFrame || 0;
  }
  if (
    !state.klyaksaHouses ||
    state.klyaksaPolling ||
    now - (state.klyaksaPolled || 0) < 2000
  )
    return;
  state.klyaksaPolling = true;
  state.klyaksaPolled = now;
  fetch("/klyaksa/state.json")
    .then((r) => r.json())
    .then((s) => {
      const tint = state.klyaksaHouses.geometry.attributes.aTint;
      let i = 0;
      for (const c of s.cities)
        for (let k = 0; k < c.t_in.length; k++, i++) {
          const t = Math.min(1, Math.max(0, (c.t_in[k] - 8) / 16)),
            powered = c.flags[k] & 1;
          const r = 0.55 + 0.6 * t,
            g = 0.7 + 0.15 * t,
            b = 1.25 - 0.55 * t,
            dim = powered ? 1 : 0.45;
          const base = state.klyaksaBaseTint;
          tint.setXYZ(
            i,
            r * dim * (base?.[i * 3] ?? 1),
            g * dim * (base?.[i * 3 + 1] ?? 1),
            b * dim * (base?.[i * 3 + 2] ?? 1),
          );
        }
      tint.needsUpdate = true;
      state.klyaksaState = s;
      syncCityVisuals(s, body, state.solarSystem.specs[3].radius);
    })
    .catch(() => {})
    .finally(() => {
      state.klyaksaPolling = false;
    });
}
