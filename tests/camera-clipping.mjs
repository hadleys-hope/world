import assert from "node:assert/strict";
import { clippingNear } from "../web/static/js/map3d/geometry/view-precision.js";
import * as T from "three";
// Inspect centimetre-sized parts even on a tall roof; stay clear of nearby ground.
assert(clippingNear(200, 0.1) < 0.02);
assert(clippingNear(0.3, 500) < 0.03);
assert.equal(clippingNear(0.01, 0.01), 0.005);
const camera = new T.PerspectiveCamera(48, 1.5, clippingNear(205, 269), 50000);
const quantizedDepth = z => {
  const p = new T.Vector3(0, 0, -z).project(camera);
  return Math.round((p.z * .5 + .5) * (2 ** 24 - 1));
};
assert(Math.abs(quantizedDepth(500) - quantizedDepth(500.08)) > 8,
  "port markings eight centimetres above paving need distinct depth values at overview distance");
console.log("Camera clipping: centimetre inspection and distant overlay depth separation passed.");
