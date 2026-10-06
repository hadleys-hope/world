/** A road link must terminate on the city graph and pass through an actual dome opening. */
import assert from "node:assert/strict";
import fs from "node:fs";
import * as T from "three";
import { state } from "../web/static/js/map3d/state.js";
import { buildConnections } from "../web/static/js/map3d/models/urban/connections.js";
import { harbourAccess } from "../web/static/js/map3d/models/urban/marine.js";
import { roadClearance } from "../web/static/js/map3d/models/urban/placement.js";
import { dirAt } from "../web/static/js/map3d/models/klyaksa.js";
const plan = JSON.parse(
  fs.readFileSync(
    new URL("../test-results/visual-fixture.json", import.meta.url),
  ),
).geometry;
const R = 12000,
  body = new T.Group(),
  ray = new T.Raycaster();
buildConnections(plan, body, R, { uSun: { value: new T.Vector3(0, 1, 0) } });
body.updateMatrixWorld(true);
assert.equal(state.klyaksaConnections.links.length, plan.branches.length);
let portals = 0;
for (const city of plan.cities) {
  for (const gate of city.gates) {
    assert(city.nodes.some((n) => n.id === gate.node));
    const at = (d) =>
      dirAt(
        city.at[0] + gate.x + Math.cos(gate.angle) * d,
        city.at[1] + gate.y + Math.sin(gate.angle) * d,
        R,
      ).multiplyScalar(R * 1.0035 + 6);
    const a = at(35),
      b = at(-35);
    ray.set(a, b.clone().sub(a).normalize());
    const dome = body.getObjectByName(`Dome ${city.id}`);
    assert(dome, "named dome exists");
    assert(
      !ray.intersectObject(dome).some((hit) => hit.distance < a.distanceTo(b)),
      `${city.name}: road blocked by dome glass`,
    );
    portals++;
  }
  // Representative coast in another direction must still leave through an existing gate.
  const coast = {
    x: city.at[0] + city.wall + 1100,
    y: city.at[1] - 700,
    a: Math.atan2(-700, city.wall + 1100),
    score: Math.hypot(city.wall + 1100, 700),
  };
  const access = harbourAccess(city, coast);
  assert(
    city.gates.some(
      (g) =>
        Math.hypot(
          access[0][0] - city.at[0] - g.x,
          access[0][1] - city.at[1] - g.y,
        ) < 0.01,
    ),
  );
  for (const p of access.slice(2))
    assert(
      Math.hypot(p[0] - city.at[0], p[1] - city.at[1]) >= city.wall + 25,
      "port access must stay outside occupied city blocks",
    );
  const reserved = roadClearance([access]);
  for (const p of access)
    assert(
      reserved(...p),
      "port road must exclude vegetation along its complete curve",
    );
  assert(
    !reserved(...city.at),
    "curved access reservation must leave city interior available",
  );
}
console.log(
  JSON.stringify({
    connectedIntercityLinks: plan.branches.length,
    openDomePortals: portals,
  }),
);
