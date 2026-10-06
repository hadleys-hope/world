/** Regression for the orbital-position LOD failure and reserved civic completeness. */
import assert from "node:assert/strict";
import fs from "node:fs";
import * as T from "three";
import {
  Batches,
  Model,
  bodyLocalSphere,
} from "../web/static/js/map3d/models/urban/kit.js";
import {
  civicGeometry,
  civicRoofHeight,
  facadeMaterial,
} from "../web/static/js/map3d/models/urban/buildings.js";
import { buildCivicDistrict } from "../web/static/js/map3d/models/urban/civic.js";
import { state } from "../web/static/js/map3d/state.js";
const env = { uTime: { value: 0 }, uSun: { value: new T.Vector3(0, 1, 0) } },
  R = 12000;
const point = (x, y, h = 0) =>
  new T.Vector3(x / R, 1, y / R).normalize().multiplyScalar(R + h);
const body = new T.Group();
body.position.set(480000, -980000, 630000);
body.rotation.set(0.7, 1.3, -0.45);
body.updateMatrixWorld(true);
const batch = new Batches(body, R, point, env);
batch.add(
  "visible pole",
  () => new Model().box(0, 4, 0, 1, 8, 1).finish(),
  100,
  50,
);
const root = batch.finish({ distance: 350 });
const before = root.userData.localBounds.clone();
for (let i = 0; i < 4; i++) {
  body.position.set(480000 + i * 13500, -980000 - i * 2000, 630000 + i * 5000);
  body.rotateY(0.4);
  body.updateMatrixWorld(true);
  const localCamera = point(100, 50, 20);
  const worldCamera = body.localToWorld(localCamera.clone());
  root.userData.update(body.worldToLocal(worldCamera));
  assert(
    root.visible,
    "near civic geometry must survive translated AND rotated planet transforms",
  );
  assert(bodyLocalSphere(root, body).center.distanceTo(before.center) < 1e-8);
  assert(Math.abs(bodyLocalSphere(root, body).radius - before.radius) < 1e-8);
  root.userData.update(point(5000, 5000, 5000));
  assert(!root.visible, "distance culling must still work away from the city");
}
for (const kind of ["bank", "bigtech", "government"]) {
  const geometry = civicGeometry(kind);
  geometry.computeBoundingBox();
  assert(geometry.boundingBox.max.y >= civicRoofHeight[kind]);
  assert(geometry.boundingBox.max.y > 100, `${kind} must be a real skyscraper`);
  assert(geometry.boundingBox.max.x - geometry.boundingBox.min.x < 76);
  assert(geometry.boundingBox.max.z - geometry.boundingBox.min.z < 66);
  geometry.dispose();
}
const fixture = JSON.parse(
  fs.readFileSync(
    new URL("../test-results/visual-fixture.json", import.meta.url),
  ),
);
state.klyaksaLod = [];
state.klyaksaTelecomRoofs = [];
state.klyaksaCivicSummary = [];
state.klyaksaSitesVisual = [];
for (const city of fixture.geometry.cities) {
  const result = buildCivicDistrict(city, body, R, point, env);
  for (let step = result.next(); !step.done; step = result.next()) {}
  const summary = state.klyaksaCivicSummary.at(-1);
  assert(summary.parks >= 10, `${city.name}: ten reserved usable parks`);
  assert.equal(
    summary.sectorServices,
    6,
    `${city.name}: a workshop/fuel/parking lot in each sector`,
  );
  for (const kind of [
    "bank",
    "bigtech",
    "government",
    "hospital",
    "fire",
    "library",
    "network",
  ])
    assert(summary.civic.includes(kind), `${city.name}: missing ${kind}`);
  assert(summary.roofs.filter((r) => r.h > 100).length >= 3);
}
const shader = facadeMaterial(env);
assert(
  shader.fragmentShader.includes("hitBox"),
  "close windows expose parallax rooms with bounded ray-box furniture",
);
assert(
  shader.fragmentShader.includes("smoothstep(100.,260.,length(vView))"),
  "interiors must fade out at city distance",
);
console.log(
  JSON.stringify(
    {
      transformCases: 4,
      cities: state.klyaksaCivicSummary.map((c) => ({
        id: c.city,
        parks: c.parks,
        serviceLots: c.sectorServices,
        civic: c.civic.length,
        rooftopTelecom: c.roofs.length,
      })),
    },
    null,
    2,
  ),
);
