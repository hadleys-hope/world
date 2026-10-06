/** Regressions for roads disappearing into the sphere, disconnected networks and bridge steps. */
import assert from "node:assert/strict";
import fs from "node:fs";
import * as T from "three";
import {
  Surface,
  roadElevation,
  roadCrossesRiver,
} from "../web/static/js/map3d/models/urban/streets.js";
import {
  roadNetwork,
  nearestRoad,
} from "../web/static/js/map3d/models/urban/traffic.js";
import { enableCityRiver } from "../web/static/js/map3d/models/urban/geography.js";
const surface = new Surface((x, y, h) => new T.Vector3(x, h, y));
surface.quad(
  [
    [0, 0, 0.2],
    [60, 0, 0.2],
    [0, 80, 0.2],
    [60, 80, 0.2],
  ],
  0x555555,
);
assert.equal(
  surface.p.length / 9,
  15 * 20 * 2,
  "Large parking lots are subdivided in both axes, not one huge chord",
);
for (let i = 0; i < surface.p.length; i += 9) {
  for (const [a, b] of [
    [0, 3],
    [3, 6],
    [6, 0],
  ]) {
    assert(
      Math.hypot(
        surface.p[i + a] - surface.p[i + b],
        surface.p[i + a + 2] - surface.p[i + b + 2],
      ) <=
        Math.sqrt(32) + 1e-8,
    );
  }
}
const fixture = JSON.parse(
  fs.readFileSync(
    new URL("../test-results/visual-fixture.json", import.meta.url),
  ),
);
enableCityRiver(12000);
let bridgeCount = 0;
for (const city of fixture.geometry.cities) {
  const graph = roadNetwork(city),
    seen = new Set(),
    queue = [graph.edges[0].a];
  while (queue.length) {
    const n = queue.pop();
    if (seen.has(n)) continue;
    seen.add(n);
    for (const edge of n.edges) queue.push(edge.a, edge.b);
  }
  assert.equal(
    seen.size,
    graph.nodes.size,
    `${city.id}: every service yard and street must connect`,
  );
  assert(graph.junctions.length > 0);
  for (const road of city.roads) {
    if (!roadCrossesRiver(city, road)) continue;
    bridgeCount++;
    for (const p of [road.points[0], road.points.at(-1)])
      assert(
        roadElevation(city, road, ...p) < 0.001,
        `${road.id}: bridge ramp meets the road at grade`,
      );
    assert(
      Math.max(...road.points.map((p) => roadElevation(city, road, ...p))) >
        23.9,
      "Bridge spans the channel at full deck clearance",
    );
  }
  for (let i = 0; i < city.houses; i += 29) {
    const p = nearestRoad(graph, city.access_x[i], city.access_y[i]);
    assert(
      Math.hypot(p.x - city.access_x[i], p.y - city.access_y[i]) < 1,
      "House frontage belongs to its actual road",
    );
  }
}
assert(bridgeCount >= 3);
console.log(
  `Streets: ${fixture.geometry.cities.length} connected city graphs, ${bridgeCount} continuous bridge ramps and <=4m surface tessellation passed.`,
);
