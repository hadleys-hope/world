/** Run: node --experimental-loader ./tests/three-loader.mjs tests/planet-rotation.mjs */
import assert from "node:assert/strict";
import * as THREE from "three";
import { state } from "../web/static/js/map3d/state.js";
import {
  bodyPointToWorld,
  worldPointToBody,
  bodyDirectionToWorld,
  worldDirectionToBody,
  carryCameraFrame,
} from "../web/static/js/map3d/geometry/body-frame.js";
// The existing controls module registers a help button at module load.
globalThis.document = { getElementById: () => ({}) };
const { buildSolarSystem, updateSolarSystem } = await import(
  "../web/static/js/map3d/models/solar-system.js"
);

const near = (a, b, label) =>
  assert.ok(
    a.distanceTo(b) < 1e-7,
    `${label}: ${a.toArray()} != ${b.toArray()}`,
  );
const axis = new THREE.Vector3(0.2, 1, 0.07).normalize();
const body = new THREE.Group();
body.position.set(44000, -2900, -18200);
body.quaternion.setFromAxisAngle(axis, 0.72);
state.solarSystem = { bodies: [body, body, body, body] };
const point = new THREE.Vector3(100, 12042, -600);
const direction = new THREE.Vector3(0.1, 0.7, -0.4).normalize();
for (let i = 0; i < 4; i++) {
  near(
    worldPointToBody(i, bodyPointToWorld(i, point)),
    point,
    `body ${i} point round trip`,
  );
  near(
    worldDirectionToBody(i, bodyDirectionToWorld(i, direction)),
    direction,
    `body ${i} direction round trip`,
  );
}

const camera = new THREE.PerspectiveCamera(50, 1, 0.01, 500000);
const controls = { target: bodyPointToWorld(3, point) };
camera.position.copy(
  bodyPointToWorld(3, point.clone().add(new THREE.Vector3(15, 10, 24))),
);
camera.up.copy(bodyDirectionToWorld(3, new THREE.Vector3(0, 1, 0)));
camera.lookAt(controls.target);
const localCamera = worldPointToBody(3, camera.position);
const originalDistance = camera.position.distanceTo(controls.target);
const localVelocity = new THREE.Vector3(4, 0, -6);
const viewer = {
  camera,
  controls,
  flightVelocity: bodyDirectionToWorld(3, localVelocity),
  flyAnim: {
    from: camera.position.clone(),
    to: camera.position.clone().add(new THREE.Vector3(40, 8, -9)),
    tfrom: controls.target.clone(),
    tto: controls.target.clone().add(new THREE.Vector3(2, 10, 30)),
  },
};
const localAnimation = Object.fromEntries(
  Object.entries(viewer.flyAnim).map(([k, p]) => [k, worldPointToBody(3, p)]),
);
const localLook = worldDirectionToBody(
  3,
  camera.getWorldDirection(new THREE.Vector3()),
);
for (let k = 1; k <= 600; k++) {
  const previousPosition = body.position.clone(),
    previousQuaternion = body.quaternion.clone();
  body.position.set(44000 + k * 3, -2900 + Math.sin(k / 100) * 400, -18200 - k);
  body.quaternion.setFromAxisAngle(axis, 0.72 + k * 0.004);
  carryCameraFrame(
    viewer,
    previousPosition,
    previousQuaternion,
    body.position,
    body.quaternion,
  );
}
near(
  worldPointToBody(3, camera.position),
  localCamera,
  "camera remains surface anchored over repeated rotation",
);
near(
  worldDirectionToBody(3, camera.getWorldDirection(new THREE.Vector3())),
  localLook,
  "look direction follows planet",
);
near(
  worldDirectionToBody(3, viewer.flightVelocity),
  localVelocity,
  "flight inertia follows planet",
);
assert.ok(
  Math.abs(camera.position.distanceTo(controls.target) - originalDistance) <
    1e-7,
  "zoom distance is stable",
);
for (const key of Object.keys(localAnimation))
  near(
    worldPointToBody(3, viewer.flyAnim[key]),
    localAnimation[key],
    `focus animation ${key}`,
  );

// Picking relies on the same parent matrix as the visible instance, not a
// translated-only approximation of the body's position.
const instances = new THREE.InstancedMesh(
  new THREE.BoxGeometry(8, 12, 8),
  new THREE.MeshBasicMaterial(),
  2,
);
instances.setMatrixAt(
  0,
  new THREE.Matrix4().makeTranslation(point.x, point.y, point.z),
);
instances.setMatrixAt(
  1,
  new THREE.Matrix4().makeTranslation(point.x + 100, point.y, point.z),
);
body.add(instances);
body.updateMatrixWorld(true);
camera.updateMatrixWorld(true);
const ray = new THREE.Raycaster();
ray.setFromCamera(new THREE.Vector2(0, 0), camera);
const hit = ray.intersectObject(instances)[0];
assert.equal(
  hit?.instanceId,
  0,
  "the same house is pickable after body rotation",
);
const hitLocal = worldPointToBody(3, hit.point);
assert.ok(
  Math.abs(hitLocal.x - point.x) <= 4.00001 &&
    Math.abs(hitLocal.z - point.z) <= 4.00001,
);

// The actual solar-system update spins each body, carries the active viewer,
// honours Pause, and keeps the star-centred system view inertial.
state.RP = 4200;
state.camera = new THREE.PerspectiveCamera(50, 1, 0.01, 500000);
state.controls = { target: new THREE.Vector3(0, 4200, 0) };
state.camera.position.set(10, 4220, 30);
state.camera.lookAt(state.controls.target);
state.world = new THREE.Group();
state.planetMat = {
  uniforms: {
    uDetail: { value: 0 },
    uColony: { value: new THREE.Vector3(0, 1, 0) },
  },
};
state.flightVelocity = new THREE.Vector3(1, 2, 3);
state.flyAnim = null;
state.S = { t: 0, speed: 1, paused: false };
state.lastPoll = 0;
state.solarSystem = {
  star: new THREE.Group(),
  orbitGroup: new THREE.Group(),
  labels: [],
  lastAt: 0,
  spinTime: 0,
  specs: Array.from({ length: 4 }, (_, i) => ({
    phase: 0.5 + i,
    period: 3000 + i * 1000,
    spinPeriod: 100 + i * 20,
    orbit: 27000 + i * 20000,
    radius: 4200,
  })),
  bodies: Array.from({ length: 4 }, () => {
    const b = new THREE.Group();
    b.userData.spinAxis = axis;
    return b;
  }),
};
state.solarSystem.star.userData.photosphere = {
  uniforms: { time: { value: 0 } },
};
state.systemView = false;
for (let i = 0; i < 4; i++) {
  state.activeBody = i;
  const localBefore = worldPointToBody(i, state.camera.position);
  const rotationBefore = state.solarSystem.bodies[i].quaternion.clone();
  updateSolarSystem((i + 1) * 100, 0.1);
  near(
    worldPointToBody(i, state.camera.position),
    localBefore,
    `update carries active planet ${i}`,
  );
  assert.ok(
    rotationBefore.angleTo(state.solarSystem.bodies[i].quaternion) > 0.001,
    `planet ${i} rotates`,
  );
}
state.S.paused = true;
const frozen = state.solarSystem.bodies.map((b) => b.quaternion.clone());
updateSolarSystem(500, 0.1);
state.solarSystem.bodies.forEach((b, i) =>
  assert.ok(b.quaternion.angleTo(frozen[i]) < 1e-7, "paused spin stays frozen"),
);
state.S.paused = false;
state.systemView = true;
const systemLook = state.camera.quaternion.clone();
const starOffset = state.camera.position
  .clone()
  .sub(state.solarSystem.star.position);
updateSolarSystem(600, 0.1);
near(
  state.camera.position.clone().sub(state.solarSystem.star.position),
  starOffset,
  "system view tracks star translation only",
);
assert.ok(
  state.camera.quaternion.angleTo(systemLook) < 1e-7,
  "system view does not inherit axial spin",
);
console.log(
  "Planet rotation: 4 frames, follow, free-flight inertia, focus animation, picking, pause and system view passed.",
);

// Exercise the real builder as well: Acheron's old scene roots must be parented
// exactly once, while camera-relative weather and the fixed stars stay inertial.
const context2d = {
  createRadialGradient: () => ({ addColorStop() {} }),
  fillRect() {},
  beginPath() {},
  roundRect() {},
  fill() {},
  fillText() {},
  measureText: (text) => ({ width: text.length * 7 }),
};
globalThis.document = {
  getElementById: () => ({}),
  querySelectorAll: () => [],
  createElement: () => ({ width: 0, height: 0, getContext: () => context2d }),
};
state.spriteCache = new Map();
state.scene = new THREE.Scene();
state.solarSystem = null;
state.cameraMode = "orbit";
state.flightSpeed = 12;
state.systemView = false;
state.activeBody = 2;
state.world = new THREE.Group();
state.planetMesh = new THREE.Mesh();
state.seaSphere = new THREE.Mesh();
const core = new THREE.Mesh(),
  atmosphere = new THREE.Mesh();
const stars = new THREE.Points(),
  sunlight = new THREE.DirectionalLight();
state.weather = { snow: new THREE.Points(), tornado: new THREE.Mesh() };
state.scene.add(
  state.world,
  state.planetMesh,
  state.seaSphere,
  core,
  atmosphere,
  stars,
  sunlight,
  state.weather.snow,
  state.weather.tornado,
);
buildSolarSystem();
const acheron = state.solarSystem.bodies[2];
assert.equal(acheron.parent, state.scene);
for (const root of [
  state.world,
  state.planetMesh,
  state.seaSphere,
  core,
  atmosphere,
])
  assert.equal(
    root.parent,
    acheron,
    "Acheron surface root is attached to its rotating body",
  );
for (const root of [stars, sunlight, state.weather.snow, state.weather.tornado])
  assert.equal(
    root.parent,
    state.scene,
    "inertial or explicitly transformed object is not double rotated",
  );
assert.equal(state.solarSystem.bodies.length, 4);
assert.ok(state.solarSystem.specs.every((spec) => spec.spinPeriod >= 1800));
console.log(
  "Actual solar-system builder: Acheron terrain/sea/core/atmosphere/city parentage and inertial sky passed.",
);
