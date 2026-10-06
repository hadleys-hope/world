/** Render-space transforms. Simulation coordinates always remain planet-local. */
import * as THREE from "three";
import { state } from "../state.js";

function bodyFrame(index) {
  return state.solarSystem?.bodies[index];
}

export function bodyPointToWorld(index, point, out = new THREE.Vector3()) {
  const body = bodyFrame(index);
  out.copy(point);
  if (body) out.applyQuaternion(body.quaternion).add(body.position);
  return out;
}

export function worldPointToBody(index, point, out = new THREE.Vector3()) {
  const body = bodyFrame(index);
  out.copy(point);
  if (body)
    out.sub(body.position).applyQuaternion(body.quaternion.clone().invert());
  return out;
}

export function bodyDirectionToWorld(
  index,
  direction,
  out = new THREE.Vector3(),
) {
  out.copy(direction);
  const body = bodyFrame(index);
  if (body) out.applyQuaternion(body.quaternion);
  return out;
}

export function worldDirectionToBody(
  index,
  direction,
  out = new THREE.Vector3(),
) {
  out.copy(direction);
  const body = bodyFrame(index);
  if (body) out.applyQuaternion(body.quaternion.clone().invert());
  return out;
}

/** Carry a viewer with a rigid planet frame, preserving its local view exactly.
 * Free-flight velocity and in-flight focus destinations must rotate too: otherwise
 * changing input mode or focusing a moving body introduces a lateral jump.
 */
export function carryCameraFrame(
  viewer,
  previousPosition,
  previousQuaternion,
  position,
  quaternion,
) {
  const delta = quaternion
    .clone()
    .multiply(previousQuaternion.clone().invert())
    .normalize();
  const carry = (point) =>
    point.sub(previousPosition).applyQuaternion(delta).add(position);
  carry(viewer.camera.position);
  carry(viewer.controls.target);
  viewer.camera.quaternion.premultiply(delta).normalize();
  viewer.camera.up.applyQuaternion(delta).normalize();
  viewer.flightVelocity?.applyQuaternion(delta);
  if (viewer.flyAnim) {
    for (const key of ["from", "to", "tfrom", "tto"])
      carry(viewer.flyAnim[key]);
  }
}
