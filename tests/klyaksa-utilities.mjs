/** Deterministic connected service graph, one connection per real house and bounded supported geometry. */
import assert from "node:assert/strict";
import fs from "node:fs";
import * as T from "three";
import {
  utilityPlan,
  buildUtilities,
} from "../web/static/js/map3d/models/urban/utilities.js";
import { buildTelecom } from "../web/static/js/map3d/models/urban/telecom.js";
import { buildIndustry } from "../web/static/js/map3d/models/urban/industry.js";
import { state } from "../web/static/js/map3d/state.js";
import { klyaksaSites, dirAt } from "../web/static/js/map3d/models/klyaksa.js";
const fixture = JSON.parse(
    fs.readFileSync(
      new URL("../test-results/visual-fixture.json", import.meta.url),
    ),
  ),
  plan = fixture.geometry;
let services = 0;
for (const c of plan.cities) {
  const g = utilityPlan(c),
    nodes = new Map(g.nodes.map((n) => [n.id, n])),
    adj = new Map(g.nodes.map((n) => [n.id, []]));
  for (const e of g.edges) {
    assert(nodes.has(e.a) && nodes.has(e.b), "No dangling utility ends");
    adj.get(e.a).push(e.b);
    adj.get(e.b).push(e.a);
  }
  for (const start of Object.values(g.sources)) {
    const seen = new Set([start]),
      queue = [start];
    for (let i = 0; i < queue.length; i++)
      for (const to of adj.get(queue[i]))
        if (!seen.has(to)) {
          seen.add(to);
          queue.push(to);
        }
    for (const h of g.homes)
      assert(seen.has(h.id), `${c.id}: ${start} disconnected from ${h.id}`);
    assert(seen.has(g.tank), "Central tank must connect to supply");
  }
  assert.equal(g.homes.length, c.houses);
  assert.equal(new Set(g.homes.map((h) => h.houseId)).size, c.houses);
  for (const n of g.nodes) {
    assert(Number.isFinite(n.x) && Number.isFinite(n.y));
    if (n.kind === "junction")
      assert(
        n.clearance >= 1,
        `${c.id} electrical pole inside road at ${n.x},${n.y}`,
      );
  }
  services += g.homes.length;
}
assert.equal(services, 5010);
state.klyaksaPlan = Promise.resolve(plan);
state.klyaksaPlanData = await klyaksaSites(12000);
state.klyaksaLod = [];
state.klyaksaHouseMeta = plan.cities.flatMap((c) =>
  Array.from({ length: c.houses }, (_, i) => ({
    id: c.first_id + i,
    height: 10,
  })),
);
state.klyaksaTelecomRoofs = [
  {
    cityId: plan.cities[0].id,
    kind: "bank",
    x: plan.cities[0].at[0] + 10,
    y: plan.cities[0].at[1] + 15,
    h: 142,
  },
];
const body = new T.Group(),
  env = { uTime: { value: 0 }, uSun: { value: dirAt(100, 100, 12000) } };
const start = performance.now();
buildIndustry(plan.cities[0], body, 12000, env);
buildUtilities(plan.cities[0], body, 12000, env);
buildTelecom(plan.cities[0], body, 12000, env);
let triangles = 0,
  meshes = 0;
for (const lod of state.klyaksaLod)
  lod.userData.update(dirAt(...plan.cities[0].at, 12000).multiplyScalar(13500));
body.traverse((o) => {
  if (!o.isMesh) return;
  if (o.visible) meshes++;
  const p = o.geometry.attributes.position;
  for (let i = 0; i < p.array.length; i++) assert(Number.isFinite(p.array[i]));
  if (o.instanceMatrix)
    for (const v of o.instanceMatrix.array) assert(Number.isFinite(v));
  if (o.visible)
    triangles +=
      ((o.geometry.index?.count ?? p.count) / 3) *
      (o.isInstancedMesh ? o.count : 1);
});
assert(state.klyaksaTanks.has(plan.cities[0].id));
assert.equal(state.klyaksaTelecomSites.get(plan.cities[0].id).length, 2);
assert(meshes < 60, "Utility details must be batched");
console.log(
  JSON.stringify({
    homes: services,
    cityBuildMs: Math.round(performance.now() - start),
    meshes,
    triangles,
  }),
);
