/** Shared articulated body; professions are reusable equipment recipes. */
import * as THREE from 'three';
import { state } from '../state.js';
import { sph, quatAt } from '../geometry/planet.js';

export const PROFESSIONS = ['engineer', 'electrician', 'scientist'];
const box = new THREE.BoxGeometry(1, 1, 1);
const sphere = new THREE.SphereGeometry(1, 10, 8);
const materials = new Map();
function material(color) {
  if (!materials.has(color)) materials.set(color, new THREE.MeshStandardMaterial({ color, roughness: .8 }));
  return materials.get(color);
}
function part(parent, color, position, scale, geometry = box) {
  const mesh = new THREE.Mesh(geometry, material(color));
  mesh.position.set(...position);
  mesh.scale.set(...scale);
  parent.add(mesh);
  return mesh;
}
const equipment = {
  engineer(body) {
    part(body, 0xeebc3c, [0, 1.79, 0], [.23, .13, .22], sphere);
    part(body, 0xeebc3c, [0, 1.74, .035], [.49, .045, .49]);
    part(body, 0x493c30, [0, 1.02, 0], [.53, .11, .34]);
    part(body, 0x929ea4, [.3, 1.06, .05], [.07, .28, .07]);
    part(body, 0x929ea4, [.3, 1.21, .05], [.16, .06, .07]);
  },
  electrician(body) {
    part(body, 0xf0782c, [0, 1.79, 0], [.24, .14, .23], sphere);
    part(body, 0x426477, [0, 1.65, .19], [.4, .23, .05]);
    part(body, 0xeddb65, [0, 1.23, .17], [.46, .07, .025]);
    part(body, 0x41382e, [.34, .94, 0], [.24, .32, .3]);
    part(body, 0x222b32, [.28, 1.19, 0], [.05, .27, .07]);
  },
  scientist(body) {
    part(body, 0xe2e9e8, [0, 1.02, 0], [.54, .28, .35]);
    part(body, 0x59bfc6, [.13, 1.35, .18], [.12, .12, .025]);
    part(body, 0x34414d, [-.36, 1.04, .2], [.25, .34, .055]);
    part(body, 0x6ed1dd, [-.36, 1.04, .233], [.2, .27, .01]);
  },
};

export function createColonist(profession = 'engineer') {
  if (!equipment[profession]) throw new Error(`Unknown profession: ${profession}`);
  const root = new THREE.Group(), body = new THREE.Group();
  root.add(body);
  const suit = { engineer: 0x52758a, electrician: 0xbb733c, scientist: 0xd7e3e1 }[profession];
  part(body, suit, [0, 1.25, 0], [.48, .51, .3]);
  part(body, 0xc99876, [0, 1.65, 0], [.18, .22, .17], sphere);
  // Face points along local +Z, the same axis as the travel heading.
  part(body, 0x28323a, [0, 1.69, .155], [.23, .045, .035]);
  const legs = [], arms = [];
  for (const side of [-1, 1]) {
    const leg = new THREE.Group(); leg.position.set(side * .135, .88, 0); body.add(leg);
    part(leg, 0x303d49, [0, -.36, 0], [.19, .72, .22]);
    part(leg, 0x20282e, [0, -.8, .045], [.22, .16, .34]);
    legs.push(leg);
    const arm = new THREE.Group(); arm.position.set(side * .32, 1.45, 0); body.add(arm);
    part(arm, suit, [0, -.23, 0], [.16, .46, .19]);
    part(arm, 0x434e53, [0, -.5, 0], [.15, .14, .17]);
    arms.push(arm);
  }
  equipment[profession](body);
  root.userData.profession = profession;
  return { root, body, legs, arms, phase: 0, blend: 0 };
}

export function animateColonist(model, dt, walking) {
  if (dt <= 0) return;
  model.phase += dt * (walking ? 7 : 1.8);
  model.blend = THREE.MathUtils.damp(model.blend, walking ? 1 : 0, 10, dt);
  const swing = Math.sin(model.phase) * .48 * model.blend;
  model.legs[0].rotation.x = swing;
  model.legs[1].rotation.x = -swing;
  model.arms[0].rotation.x = -swing * .7;
  model.arms[1].rotation.x = swing * .7;
  // Account for the rotated boot sole so the support foot stays on the surface.
  model.body.scale.y = 1 + Math.sin(model.phase) * .003 * (1 - model.blend);
  model.body.position.y = (.88 * (Math.cos(swing) - 1) + .215 * Math.abs(Math.sin(swing))) * model.body.scale.y;
}

export function sampleRoute(route, progress, lengths = null) {
  lengths ||= route.slice(1).map((point, i) => Math.hypot(point[0] - route[i][0], point[1] - route[i][1]));
  let distance = lengths.reduce((sum, length) => sum + length, 0) * progress;
  for (let i = 0; i < lengths.length; i++) {
    if (distance <= lengths[i] || i === lengths.length - 1) {
      const u = lengths[i] ? Math.min(1, distance / lengths[i]) : 0;
      return route[i].map((value, axis) => value + (route[i + 1][axis] - value) * u);
    }
    distance -= lengths[i];
  }
  return route[0];
}

export function syncColonists(people) {
  if (!state.colonists) {
    state.colonists = new Map();
    state.colonistGroup = new THREE.Group();
    state.world.add(state.colonistGroup);
  }
  const active = new Set();
  for (const per of people) {
    const id = per[4];
    if (id == null) continue;
    active.add(id);
    let model = state.colonists.get(id);
    const fresh = !model;
    if (!model) {
      model = createColonist(per[5] || PROFESSIONS[id % PROFESSIONS.length]);
      Object.assign(model, { x: per[0], y: per[1], height: per[7] ?? .1, heading: 0, progress: per[9] ?? 0 });
      model.phase = id * 2.4;
      model.root.position.copy(sph(model.x, model.y, model.height));
      model.root.quaternion.copy(quatAt(model.x, model.y));
      model.root.traverse(o => { o.userData.click = { kind: 'person', id }; });
      state.colonistGroup.add(model.root);
      state.clickables.push(model.root);
      state.colonists.set(id, model);
    }
    model.targetX = per[0]; model.targetY = per[1]; model.walking = !per[6] && (per[2] === 1 || per[2] === 3);
    model.targetProgress = per[9];
    if (per[8]) {
      const key = JSON.stringify(per[8]);
      if (model.routeKey !== key) {
        model.route = per[8];
        model.routeLengths = model.route.slice(1).map((point, i) => Math.hypot(point[0] - model.route[i][0], point[1] - model.route[i][1]));
        model.routeKey = key;
        // A replanned path starts at the saved position; progress resets with it.
        model.progress = fresh ? per[9] : per[2] === 3 ? 1 : 0;
      }
    }
  }
  for (const [id, model] of state.colonists) if (!active.has(id)) {
    state.colonistGroup.remove(model.root);
    const index = state.clickables.indexOf(model.root);
    if (index >= 0) state.clickables.splice(index, 1);
    state.colonists.delete(id);
  }
  state.colonistGroup.visible = !!state.layers.people;
}

export function updateColonists(now) {
  const dt = Math.min(.1, Math.max(0, (now - (state.colonistLastFrame ?? now)) / 1000));
  state.colonistLastFrame = now;
  if (!state.colonists || state.S?.paused || !state.clock.speed) return;
  for (const model of state.colonists.values()) {
    let x, y, height;
    if (model.route) {
      model.progress = THREE.MathUtils.damp(model.progress, model.targetProgress, 8, dt);
      [x, y, height] = sampleRoute(model.route, model.progress, model.routeLengths);
    } else {
      x = THREE.MathUtils.damp(model.x, model.targetX, 8, dt);
      y = THREE.MathUtils.damp(model.y, model.targetY, 8, dt);
      height = model.height;
    }
    const dx = x - model.x, dy = y - model.y;
    if (Math.hypot(dx, dy) > .001) model.heading = Math.atan2(dx, dy);
    model.x = x; model.y = y; model.height = height;
    model.root.position.copy(sph(model.x, model.y, height));
    model.root.quaternion.slerp(quatAt(model.x, model.y, model.heading), 1 - Math.exp(-10 * dt));
    animateColonist(model, dt, model.walking);
  }
}
