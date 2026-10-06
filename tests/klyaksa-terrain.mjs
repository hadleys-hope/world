/** Verify the rendered river channel, not just the analytic landscape function. */
import assert from "node:assert/strict";
import fs from "node:fs";
import * as T from "three";
import { state } from "../web/static/js/map3d/state.js";
import { klyaksaSites, dirAt } from "../web/static/js/map3d/models/klyaksa.js";
import { klyaksaPatch } from "../web/static/js/map3d/models/worlds.js";
import {
  riverCentre,
  riverLevel,
  riverWidth,
  riverBounds,
  riverContains,
} from "../web/static/js/map3d/models/urban/geography.js";
const fixture = JSON.parse(
  fs.readFileSync(
    new URL("../test-results/visual-fixture.json", import.meta.url),
  ),
);
state.klyaksaPlan = Promise.resolve(fixture.geometry);
state.klyaksaPlanData = await klyaksaSites(12000);
const material = new T.MeshBasicMaterial({ side: T.DoubleSide });
material.userData.hi = 0.05;
const [land] = klyaksaPatch({ radius: 12000 }, material, {
  uTime: { value: 0 },
  uSun: { value: new T.Vector3(0, 1, 0) },
});
land.updateMatrixWorld();
const ray = new T.Raycaster(),
  R = 12000,
  bounds = riverBounds();
let checks = 0;
for (let x = bounds.source + 250; x < bounds.mouth - 160; x += 145) {
  for (const offset of [-0.45, 0, 0.45]) {
    const y = riverCentre(x) + riverWidth(x) * offset;
    const normal = dirAt(x, y, R);
    ray.set(new T.Vector3(), normal);
    const intersections = ray.intersectObject(land);
    assert(intersections.length, "channel must have rendered terrain");
    const actual = intersections[0].distance - R;
    assert(
      actual < riverLevel(x) - 2,
      `terrain must not cover river at ${x},${y}: ${actual}`,
    );
    assert(
      Math.abs(actual - state.klyaksaGroundAt(x, y)) < 0.008,
      "road sampler must see refined triangles",
    );
    checks++;
  }
}
assert(
  !riverContains(bounds.mouth + 10, riverCentre(bounds.mouth + 10)),
  "river ends at ocean mouth",
);
assert(
  state.klyaksaTerrainStats.triangles < 600000,
  "river detail must stay spatially bounded",
);
console.log(
  JSON.stringify({
    renderedChannelChecks: checks,
    ...state.klyaksaTerrainStats,
  }),
);
