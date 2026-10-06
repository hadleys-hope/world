import assert from "node:assert/strict";
import { drainBuildQueue } from "../web/static/js/map3d/render/build-queue.js";
let time = 0;
const completed = [],
  costs = [],
  queue = [];
for (let i = 0; i < 100; i++)
  queue.push(() => {
    completed.push(i);
    time += 0.5;
  });
const run = (deadline) =>
  drainBuildQueue(
    queue,
    (cost) => costs.push(cost),
    deadline,
    () => time,
  );
assert(run({ timeRemaining: () => 20 }));
assert.equal(completed.length, 12, "cheap tasks share a six-millisecond slice");
queue.unshift(() => {
  time += 30;
});
const before = queue.length;
assert(run({ timeRemaining: () => 20 }));
assert.equal(
  queue.length,
  before - 1,
  "expensive task must yield immediately afterwards",
);
while (run()) {}
assert.deepEqual(
  completed,
  Array.from({ length: 100 }, (_, i) => i),
  "task order survives slicing",
);
assert(costs.every(Number.isFinite));
const waiting = () => queue.push(waiting);
queue.push(waiting);
assert(
  run({ timeRemaining: () => 0 }),
  "timed-out idle slice must still make bounded progress",
);
assert.equal(queue.length, 1, "self-requeue cannot consume an unbounded turn");
console.log(
  "Build queue: bounded idle work, heavy-step yield, order and asynchronous wait passed.",
);
