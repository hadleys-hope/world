/** Geometry, identity, picking, marine motion and render-budget regression checks; no DOM or GPU needed. */
import assert from "node:assert/strict";
import fs from "node:fs";
import * as T from "three";
import { state } from "../web/static/js/map3d/state.js";
import {
  buildKlyaksa,
  klyaksaSites,
  dirAt,
} from "../web/static/js/map3d/models/klyaksa.js";
import { bodyHeight } from "../web/static/js/map3d/geometry/noise.js";
import {
  riverLevel,
  riverCentre,
  riverWidth,
} from "../web/static/js/map3d/models/urban/geography.js";
import {
  stepBoat,
  blockedBerth,
} from "../web/static/js/map3d/models/urban/marine.js";
import { syncCityVisuals } from "../web/static/js/map3d/models/urban/industry.js";
import { klyaksaPatch } from "../web/static/js/map3d/models/worlds.js";
const fixture = JSON.parse(
  fs.readFileSync(
    new URL("../test-results/visual-fixture.json", import.meta.url),
  ),
);
const R = 12000,
  body = new T.Group(),
  steps = [],
  env = { uTime: { value: 0 }, uLight: { value: dirAt(-2000, 3000, R) } };
state.klyaksaPlan = Promise.resolve(fixture.geometry);
state.klyaksaPlanData = await klyaksaSites(R);
state.klyaksaLod = [];
// Production builds its terrain sampler before placing service and port roads.
// Keep terrain outside the object-only draw budget, but use its actual triangles.
const terrainMaterial = new T.MeshBasicMaterial({ side: T.DoubleSide });
terrainMaterial.userData.hi = 0.05;
klyaksaPatch({ radius: R }, terrainMaterial, {
  uTime: env.uTime,
  uSun: env.uLight,
});
buildKlyaksa(steps, body, R, env);
const costs = [],
  stepNames = [];
while (steps.length) {
  assert(costs.length < 5000, "Build queue must terminate");
  const start = performance.now();
  const step = steps.shift();
  step();
  stepNames.push(step.task || step.toString().slice(0, 100));
  costs.push(performance.now() - start);
}
syncCityVisuals(fixture.state, body, R);
body.updateMatrixWorld(true);
const expected = fixture.geometry.cities.reduce((sum, c) => sum + c.houses, 0);
assert.equal(state.klyaksaHouses.count, expected);
assert.equal(expected, 5010);
assert.equal(new Set(state.klyaksaHouseMeta.map((h) => h.id)).size, expected);
assert.equal(Math.min(...state.klyaksaHouseMeta.map((h) => h.floors)), 1);
assert.equal(Math.max(...state.klyaksaHouseMeta.map((h) => h.floors)), 10);
const ray = new T.Raycaster();
let offset = 0;
for (const city of fixture.geometry.cities) {
  for (const i of [0, Math.floor(city.houses / 2), city.houses - 1]) {
    const meta = state.klyaksaHouseMeta[offset + i],
      normal = dirAt(meta.x, meta.z, R);
    ray.set(
      normal.clone().multiplyScalar(R * 1.0035 + meta.height + 55),
      normal.clone().negate(),
    );
    const hit = ray.intersectObject(state.klyaksaHouses)[0];
    assert.equal(
      hit?.instanceId,
      offset + i,
      `${city.id} house ${i} must be pickable`,
    );
  }
  offset += city.houses;
}
assert.equal(state.klyaksaPorts.length, 3);
assert.equal(state.klyaksaBoats.length, 24);
for (const boat of state.klyaksaBoats) {
  assert(
    !blockedBerth(boat.x, boat.y, boat),
    `${boat.name} intersects a berth`,
  );
  const n = dirAt(boat.x, boat.y, R);
  assert(bodyHeight(3, n.x, n.y, n.z) * R < -1.8);
  const copy = { ...boat },
    old = [copy.x, copy.y];
  const peers = state.klyaksaBoats;
  state.klyaksaBoats = peers.filter((b) => b !== boat);
  for (let i = 0; i < 120; i++) stepBoat(copy, { forward: true }, 1 / 60);
  state.klyaksaBoats = peers;
  assert(
    Math.hypot(copy.x - old[0], copy.y - old[1]) > 1,
    "Throttle must actually move the vessel",
  );
  assert(Number.isFinite(copy.x) && Number.isFinite(copy.speed));
  /* other moored boats remain fixed */ assert.deepEqual([boat.x, boat.y], old);
}
const boat = state.klyaksaBoats[0],
  saved = state.klyaksaBoats;
state.klyaksaBoats = [];
const a = {
    ...boat,
    x: boat.x + Math.cos(boat.heading) * 200,
    y: boat.y + Math.sin(boat.heading) * 200,
    speed: 0,
    steer: 0,
  },
  b = { ...a };
for (let i = 0; i < 120; i++)
  stepBoat(a, { forward: true, left: true }, 1 / 60);
for (let i = 0; i < 240; i++)
  stepBoat(b, { forward: true, left: true }, 1 / 120);
assert(
  Math.hypot(a.x - b.x, a.y - b.y) < 0.25,
  "Boat motion should not depend materially on frame rate",
);
state.klyaksaBoats = saved;
for (const x of [-900, -450, 0, 450, 900]) {
  const n = dirAt(x, riverCentre(x), R);
  assert(
    bodyHeight(3, n.x, n.y, n.z) * R < riverLevel(x) - 3,
    "River water must have a channel beneath it",
  );
  const bank = dirAt(x, riverCentre(x) + riverWidth(x) + 6, R);
  assert(bodyHeight(3, bank.x, bank.y, bank.z) * R > riverLevel(x));
}
let meshes = 0;
body.traverse((o) => {
  if (!o.geometry) return;
  meshes++;
  for (const a of Object.values(o.geometry.attributes))
    for (const x of a.array)
      assert(Number.isFinite(x), "No NaN/Infinity in geometry");
  if (o.instanceMatrix)
    for (const x of o.instanceMatrix.array) assert(Number.isFinite(x));
});
assert.equal(
  state.klyaksaVehicleBatches.filter((b) => b.mesh.count).length,
  2,
  "Real vehicles must remain batched",
);
const reports = [];
for (const view of [
  { name: "city", x: 0, y: 0, alt: 1500, back: 500 },
  { name: "street", x: 293, y: 70, alt: 42, back: 85 },
]) {
  const target = dirAt(view.x, view.y, R).multiplyScalar(R + 50),
    normal = target.clone().normalize(),
    north = dirAt(view.x, view.y + 1, R)
      .sub(dirAt(view.x, view.y, R))
      .normalize(),
    camera = new T.PerspectiveCamera(48, 1.5, 0.1, 50000);
  camera.position
    .copy(target)
    .addScaledVector(normal, view.alt)
    .addScaledVector(north, -view.back);
  camera.up.copy(normal);
  camera.lookAt(target);
  camera.updateMatrixWorld();
  for (const group of state.klyaksaLod) group.userData.update(camera.position);
  const frustum = new T.Frustum().setFromProjectionMatrix(
    new T.Matrix4().multiplyMatrices(
      camera.projectionMatrix,
      camera.matrixWorldInverse,
    ),
  );
  let calls = 0,
    triangles = 0;
  body.traverseVisible((o) => {
    if (!o.geometry || !frustum.intersectsObject(o)) return;
    calls++;
    if (!o.isLine)
      triangles +=
        ((o.geometry.index?.count || o.geometry.attributes.position.count) /
          3) *
        (o.count ?? 1);
  });
  assert(
    calls < 350,
    `${view.name}: draw submissions exceeded the budget (${calls})`,
  );
  assert(
    triangles < 3500000,
    `${view.name}: triangle budget exceeded (${triangles})`,
  );
  reports.push({ view: view.name, calls, triangles });
}
console.log(
  JSON.stringify(
    {
      houses: expected,
      ports: state.klyaksaPorts.length,
      vessels: state.klyaksaBoats.length,
      pickChecks: 18,
      meshes,
      views: reports,
      buildSteps: costs.length,
      maxBuildStepMs: Math.round(Math.max(...costs)),
      slowSteps: costs
        .map((ms, i) => ({ ms: Math.round(ms), step: stepNames[i] }))
        .sort((a, b) => b.ms - a.ms)
        .slice(0, 5),
    },
    null,
    2,
  ),
);

const { initialize: initializePlanet } = await import(
  "../web/static/js/map3d/geometry/planet.js"
);
const { buildOasis } = await import("../web/static/js/map3d/models/oasis.js");
initializePlanet();
state.G = fixture.acheron;
state.world = new T.Group();
state.envUniforms = {
  uSun: { value: new T.Vector3(0.4, 1, 0.3).normalize() },
  uTime: { value: 0 },
};
const garden = [];
buildOasis(garden);
while (garden.length) garden.shift()();
assert(
  state.acheronPublicSpaces >= 5,
  "Acheron must contain usable new public spaces",
);
console.log("Acheron public spaces:", state.acheronPublicSpaces);

// Road height must agree with the triangles seen by the GPU, not an unrelated noise sample.
const { groundSampler } = await import(
  "../web/static/js/map3d/models/worlds.js"
);
const ringCount = 8,
  segments = 64,
  reach = 1500,
  vertices = [],
  indices = [];
for (let row = 0; row <= ringCount; row++)
  for (let col = 0; col < segments; col++) {
    const d = (reach * row) / ringCount,
      a = (col / segments) * Math.PI * 2,
      h = 42 + (d / 500) * Math.sin(a * 2) * 10;
    vertices.push(
      ...dirAt(d * Math.cos(a), d * Math.sin(a), R)
        .multiplyScalar(R + h)
        .toArray(),
    );
  }
for (let row = 0; row < ringCount; row++)
  for (let col = 0; col < segments; col++) {
    const a = row * segments + col,
      b = row * segments + ((col + 1) % segments);
    indices.push(a, a + segments, b, b, a + segments, b + segments);
  }
const terrain = new T.BufferGeometry().setAttribute(
  "position",
  new T.Float32BufferAttribute(vertices, 3),
);
terrain.setIndex(indices);
const terrainMesh = new T.Mesh(
    terrain,
    new T.MeshBasicMaterial({ side: T.DoubleSide }),
  ),
  sample = groundSampler(terrain, R, ringCount, segments, reach);
terrainMesh.updateMatrixWorld();
for (let i = 0; i < 24; i++) {
  const a = i * 2.39996,
    d = 50 + i * 51,
    x = Math.cos(a) * d,
    y = Math.sin(a) * d;
  ray.set(new T.Vector3(), dirAt(x, y, R));
  const h = ray.intersectObject(terrainMesh)[0].distance - R;
  assert(
    Math.abs(sample(x, y) - h) < 0.0001,
    "Road must sit on rendered terrain",
  );
}

for (let row = 1; row < ringCount; row++)
  for (const epsilon of [-0.001, 0.001]) {
    const d = (reach * row) / ringCount + epsilon,
      a = 0.123,
      x = Math.cos(a) * d,
      y = Math.sin(a) * d;
    ray.set(new T.Vector3(), dirAt(x, y, R));
    const h = ray.intersectObject(terrainMesh)[0].distance - R;
    assert(
      Math.abs(sample(x, y) - h) < 0.0001,
      "Terrain sampling must stay continuous at ring boundaries",
    );
  }

console.log(
  "Rendered terrain sampling: 38 rays passed, including ring boundaries",
);
