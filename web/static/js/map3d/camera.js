/** camera: procedural colony viewer. */
import { state } from './state.js';
import * as THREE from 'three';
export function updateCameraMotion(now) {
  const dt = Math.min(.05, (now - state.cameraLast) / 1000);
  state.cameraLast = now;
  if (!state.cameraKeys.size) return;
  const distance = state.camera.position.distanceTo(state.controls.target),
    speed = Math.max(2.5, distance * .85) * (state.cameraKeys.has('shift') ? 4 : 1) * dt;
  const right = new THREE.Vector3().setFromMatrixColumn(state.camera.matrixWorld, 0),
    up = new THREE.Vector3().setFromMatrixColumn(state.camera.matrixWorld, 1),
    vertical = state.camera.position.clone().normalize(),
    move = new THREE.Vector3();
  if (state.cameraKeys.has('a') || state.cameraKeys.has('arrowleft')) move.addScaledVector(right, -1);
  if (state.cameraKeys.has('d') || state.cameraKeys.has('arrowright')) move.add(right);
  if (state.cameraKeys.has('w') || state.cameraKeys.has('arrowup')) move.add(up);
  if (state.cameraKeys.has('s') || state.cameraKeys.has('arrowdown')) move.addScaledVector(up, -1);
  if (state.cameraKeys.has('q')) move.addScaledVector(vertical, -1);
  if (state.cameraKeys.has('e')) move.add(vertical);
  if (move.lengthSq()) {
    move.normalize().multiplyScalar(speed);
    state.camera.position.add(move);
    state.controls.target.add(move);
    state.flyAnim = null;
  }
}
export function focusPoint(point, distance = 12, normal = null) {
  const direction = normal ? normal.clone().normalize() : state.camera.position.clone().sub(state.controls.target).normalize();
  state.flyAnim = {
    from: state.camera.position.clone(),
    to: point.clone().addScaledVector(direction, distance),
    tfrom: state.controls.target.clone(),
    tto: point.clone(),
    t0: performance.now()
  };
}
export function focusSelection() {
  if (!state.selected) return;
  if (state.selected.kind === 'pole') {
    const meter = state.cabinetMeters[state.selected.id];
    focusPoint(meter.position, 3, new THREE.Vector3(0, .15, 1).applyQuaternion(meter.quaternion));
    return;
  }
  if (state.selected.kind === 'house') {
    const h = state.houseShells[state.selected.id],
      dim = state.DIM[state.G.houses.type[state.selected.id]];
    focusPoint(h.base.clone().addScaledVector(h.base.clone().normalize(), dim[1] / 2), Math.max(dim[0], dim[2]) * 1.5);
    return;
  }
  const obj = state.clickables.find(o => o.userData.click?.id === state.selected.id);
  if (obj) {
    const bounds = new THREE.Box3().setFromObject(obj),
      center = bounds.getCenter(new THREE.Vector3());
    focusPoint(center, Math.max(8, bounds.getSize(new THREE.Vector3()).length() * 1.2));
  }
}
export function initialize() {
  state.cameraKeys = new Set();
  state.cameraLast = performance.now();
  window.addEventListener('keydown', e => {
    if (e.target.matches('input,textarea,select') || e.ctrlKey || e.metaKey) return;
    const key = e.key.toLowerCase();
    if (['w', 'a', 's', 'd', 'q', 'e', 'shift', 'arrowleft', 'arrowright', 'arrowup', 'arrowdown'].includes(key)) {
      e.preventDefault();
      state.cameraKeys.add(key);
    }
    if (key === 'f') focusSelection();
  });
  window.addEventListener('keyup', e => state.cameraKeys.delete(e.key.toLowerCase()));
  window.addEventListener('blur', () => state.cameraKeys.clear());
  state.renderer.domElement.addEventListener('wheel', e => {
    e.preventDefault();
    e.stopImmediatePropagation();
    state.flyAnim = null;
    const rect = state.renderer.domElement.getBoundingClientRect(),
      cursor = new THREE.Vector2((e.clientX - rect.left) / rect.width * 2 - 1, -(e.clientY - rect.top) / rect.height * 2 + 1),
      r = new THREE.Raycaster();
    r.setFromCamera(cursor, state.camera);
    const direction = state.camera.getWorldDirection(new THREE.Vector3()),
      plane = new THREE.Plane().setFromNormalAndCoplanarPoint(direction, state.controls.target),
      anchor = r.ray.intersectPlane(plane, new THREE.Vector3()) || state.controls.target.clone();
    const delta = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? rect.height : 1),
      distance = state.camera.position.distanceTo(state.controls.target),
      next = THREE.MathUtils.clamp(distance * Math.exp(THREE.MathUtils.clamp(delta, -180, 180) * .0018), .7, state.RP * 4),
      ratio = next / Math.max(distance, .001);
    state.camera.position.sub(anchor).multiplyScalar(ratio).add(anchor);
    state.controls.target.sub(anchor).multiplyScalar(ratio).add(anchor);
    state.controls.update();
  }, {
    passive: false,
    capture: true
  });
}
