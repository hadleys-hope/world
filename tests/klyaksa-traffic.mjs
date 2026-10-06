/** Deterministic street-space traffic regression: topology, lanes, signal obedience, bounded integration. */
import assert from "node:assert/strict";
import {
  roadNetwork,
  nearestRoad,
  routeBetween,
  createVehicle,
  retargetVehicle,
  advanceVehicle,
  sampleRoad,
  signalPhase,
  trafficStopOffset,
} from "../web/static/js/map3d/models/urban/traffic.js";
const roads = [
  {
    id: "west",
    points: [
      [-100, 0],
      [-50, 0],
      [0, 0],
    ],
    width: 12,
  },
  {
    id: "east",
    points: [
      [0, 0],
      [50, 0],
      [100, 0],
    ],
    width: 12,
  },
  {
    id: "north",
    points: [
      [0, 0],
      [0, 50],
      [0, 100],
    ],
    width: 12,
  },
  {
    id: "south",
    points: [
      [0, -100],
      [0, -50],
      [0, 0],
    ],
    width: 12,
  },
  {
    id: "island",
    points: [
      [500, 500],
      [600, 500],
    ],
    width: 8,
  },
];
const graph = roadNetwork({ roads }),
  node = graph.junctions[0];
assert.equal(graph.junctions.length, 1);
const a = nearestRoad(graph, -80, 0),
  b = nearestRoad(graph, 80, 0),
  path = routeBetween(graph, a, b);
assert.equal(path.length, 2);
assert.deepEqual(
  path.map((p) => p.edge.road.id),
  ["west", "east"],
);
assert.equal(
  routeBetween(graph, a, nearestRoad(graph, 550, 500)).length,
  0,
  "Disconnected roads must never become a Cartesian teleport",
);
assert(
  sampleRoad(a.edge, 30, false).y < 0,
  "Eastbound right lane lies south of centreline",
);
assert(
  sampleRoad(a.edge, 30, true).y > 0,
  "Westbound right lane lies north of centreline",
);
const v = createVehicle(graph, { x: -80, y: 0 });
retargetVehicle(v, { x: 80, y: 0 });
assert.equal(signalPhase(node, 0, 30), "red");
let maxStep = 0,
  last = { ...v.pose };
for (let i = 0; i < 1200; i++) {
  advanceVehicle(v, 1 / 60, 30, true);
  maxStep = Math.max(maxStep, Math.hypot(v.pose.x - last.x, v.pose.y - last.y));
  last = { ...v.pose };
}
assert(
  v.pose.x <= -trafficStopOffset(node),
  "Front of vehicle remains behind the red stop line",
);
assert(v.speed < 0.02);
assert(maxStep < 0.3);
const stopped = v.pose.x;
let highestGear = 1;
for (let i = 0; i < 600; i++) {
  advanceVehicle(v, 1 / 60, 0, true);
  highestGear = Math.max(highestGear, v.gear);
}
assert(v.pose.x > stopped + 20, "Green releases the vehicle");
assert(highestGear >= 2);
assert(Number.isFinite(v.rpm));
const before = { ...v.pose };
advanceVehicle(v, 1000, 0, true);
assert(
  Math.hypot(v.pose.x - before.x, v.pose.y - before.y) < 3,
  "Tab suspension cannot produce a huge positional jump",
);
const run = (dt) => {
  const z = createVehicle(graph, { x: -80, y: 0 });
  retargetVehicle(z, { x: 80, y: 0 });
  for (let t = 0; t < 4 - 1e-8; t += dt) advanceVehicle(z, dt, 0, true);
  return z.pose.x;
};
assert(
  Math.abs(run(1 / 30) - run(1 / 120)) < 0.2,
  "Engine motion stable across frame rates",
);
console.log(
  "Traffic: graph routes, disconnected components, right lanes, red/green obedience, transmission and bounded integration passed.",
);
const turning = createVehicle(graph, { x: -80, y: 0 });
retargetVehicle(turning, { x: 0, y: 80 });
let previous = { ...turning.pose },
  turnStep = 0,
  roundCorner = false;
for (let i = 0; i < 1000; i++) {
  advanceVehicle(turning, 1 / 60, 0, true);
  turnStep = Math.max(
    turnStep,
    Math.hypot(turning.pose.x - previous.x, turning.pose.y - previous.y),
  );
  roundCorner ||=
    turning.pose.x > -8 &&
    turning.pose.x < -1 &&
    turning.pose.y > 1 &&
    turning.pose.y < 8;
  previous = { ...turning.pose };
}
assert(turnStep < 0.35, "Rounded lane connectors must not jump at the node");
assert(
  roundCorner,
  "A turn follows an arc through the junction instead of a sharp pivot at its centre",
);
