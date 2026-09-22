/** driving: procedural colony viewer. */
import { state } from "./state.js";
import { navigationHUD, nearClip } from "./camera.js";
import { quatAt, surfaceHeight, xyNormal } from "./geometry/planet.js";
import { updateRemoteTerrain } from "./geometry/remote-terrain.js";
import { chassisState, stepChassis, groundAt } from "./physics/chassis.js";
import { toast } from "./ui/controls.js";
import { renderInfo } from "./ui/inspection.js";
import * as THREE from "three";

export function obstacleGrid() {
  const grid = new Map(),
    put = (f) => {
      const r = Math.hypot(f.w, f.d) / 2 + 4;
      for (
        let x = Math.floor((f.x - r) / 32);
        x <= Math.floor((f.x + r) / 32);
        x++
      )
        for (
          let y = Math.floor((f.y - r) / 32);
          y <= Math.floor((f.y + r) / 32);
          y++
        ) {
          const key = x + "," + y;
          if (!grid.has(key)) grid.set(key, []);
          grid.get(key).push(f);
        }
    };
  for (const f of state.layoutFootprints) if (!f.parking) put(f);
  for (let i = 0; i < state.G.houses.x.length; i++) {
    const d = state.DIM[state.G.houses.type[i]];
    put({
      x: state.G.houses.x[i],
      y: state.G.houses.y[i],
      w: d[0] + 0.8,
      d: d[2] + 0.8,
      yaw: (-state.G.houses.angle[i] * Math.PI) / 180 - Math.PI / 2,
    });
  }
  for (let i = 0; i < state.G.poles.x.length; i++)
    put({
      x: state.G.poles.x[i],
      y: state.G.poles.y[i],
      w: 0.7,
      d: 0.7,
      yaw: 0,
    });
  for (const f of state.externalPoleSites)
    put({ ...f, w: 0.7, d: 0.7, yaw: 0 });
  return grid;
}

export function blockedVehicle(x, y, name) {
  for (const f of state.collisionIndex?.get(
    Math.floor(x / 32) + "," + Math.floor(y / 32),
  ) || []) {
    const co = Math.cos(f.yaw),
      si = Math.sin(f.yaw),
      dx = x - f.x,
      dy = y - f.y;
    if (
      Math.abs(dx * co - dy * si) < f.w / 2 + 1.45 &&
      Math.abs(dx * si + dy * co) < f.d / 2 + 1.45
    )
      return true;
  }
  const radius = Math.hypot(x, y),
    a = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360,
    nearest = Math.round(a / 60) % 6,
    diff = Math.abs(((a - nearest * 60 + 540) % 360) - 180);
  if (
    Math.abs(radius - state.G.cfg.wall_radius) < 4 &&
    (diff > 1.45 || state.S?.sectors[nearest]?.gate !== "OPEN")
  )
    return true;
  return (state.S?.rovers || []).some(
    (r) => r.name !== name && Math.hypot(r.x - x, r.y - y) < 3.1,
  );
}

export async function driveCommand(cmd, extra = {}) {
  const response = await fetch("/cmd", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      cmd,
      token: state.ADMIN,
      owner: state.DRIVER_OWNER,
      ...extra,
    }),
  });
  const result = await response.json();
  if (!response.ok || !result.ok)
    throw new Error(
      result.error || "Driving unavailable: check control access",
    );
  return result;
}

export async function startDriving(name) {
  if (state.drive || state.driverRequest) return;
  state.driverRequest = true;
  try {
    const result = await driveCommand("drive_claim", { name });
    state.activeBody = 2;
    state.systemView = false;
    state.clearInput();
    if (document.pointerLockElement) document.exitPointerLock();
    state.flyAnim = null;
    state.collisionIndex = obstacleGrid();
    const d = chassisState(result.x, result.y, result.heading);
    Object.assign(d, {
      name,
      distance: result.distance,
      seq: 0,
      camYaw: 0,
      camPitch: 0.32,
      camDistance: 12,
      lastSend: 0,
      pending: false,
      camReady: false,
    });
    state.drive = d;
    state.selected = null;
    document.getElementById('tip').style.display = 'none';
    state.driverAccumulator = 0;
    state.cameraMode = "drive";
    navigationHUD();
    renderInfo();
  } catch (e) {
    toast(e.message);
  } finally {
    state.driverRequest = false;
  }
}

export async function stopDriving() {
  if (!state.drive) return;
  const d = state.drive;
  state.cameraKeys.clear();
  d.v = 0;
  try {
    if (d.pending) await d.pending;
    await sendDriverPose(true);
    await driveCommand("drive_release", { name: d.name });
  } catch (e) {
    toast(e.message);
  }
  state.drive = null;
  state.cameraMode = "flight";
  state.flightSpeed = 8;
  state.flightVelocity.set(0, 0, 0);
  navigationHUD();
  renderInfo();
}

export function sendDriverPose(force = false) {
  const d = state.drive;
  if (!d) return Promise.resolve();
  if (d.pending) return d.pending;
  d.pending = (async () => {
    try {
      await driveCommand("drive_pose", {
        name: d.name,
        seq: d.seq++,
        x: d.x,
        y: d.y,
        heading: d.heading,
        velocity: d.v,
        chassis: {
          height: d.alt - surfaceHeight(d.x, d.y),
          pitch: d.pitch,
          roll: d.roll,
          rpm: d.rpm,
          gear: d.gear,
          steer: d.steer,
        },
      });
    } catch (e) {
      toast(e.message);
      state.drive = null;
      state.cameraMode = "flight";
      state.cameraKeys.clear();
      navigationHUD();
    } finally {
      d.pending = null;
    }
  })();
  return d.pending;
}

export function updateDriving(dt, now) {
  const d = state.drive;
  if (!d) return;
  state.driverAccumulator = Math.min(0.12, state.driverAccumulator + dt);
  const input = {
    forward: state.cameraKeys.has("w") || state.cameraKeys.has("arrowup"),
    back: state.cameraKeys.has("s") || state.cameraKeys.has("arrowdown"),
    left: state.cameraKeys.has("a") || state.cameraKeys.has("arrowleft"),
    right: state.cameraKeys.has("d") || state.cameraKeys.has("arrowright"),
    handbrake: state.cameraKeys.has(" "),
  };
  while (state.driverAccumulator >= 1 / 120) {
    stepChassis(d, input, 1 / 120, groundAt, blockedVehicle);
    state.driverAccumulator -= 1 / 120;
  }
  const rv = state.rovers[d.name],
    normal = xyNormal(d.x, d.y),
    base = normal.clone().multiplyScalar(state.RP + d.alt),
    q = quatAt(d.x, d.y, -d.heading),
    forward = new THREE.Vector3(1, 0, 0).applyQuaternion(q);
  if (rv) {
    rv.g.position.copy(base);
    rv.g.quaternion
      .copy(q)
      .multiply(
        new THREE.Quaternion().setFromEuler(
          new THREE.Euler(d.roll, 0, d.pitch),
        ),
      );
    for (let i = 0; i < (rv.g.userData.wheels || []).length; i++) {
      const wheel = rv.g.userData.wheels[i];
      wheel.position.y = d.wheelY[i % 4];
      wheel.rotation.y = wheel.position.x > 0 ? -d.steer : 0;
      wheel.rotation.z = -d.distance / 0.66;
    }
  }
  const behind = forward
      .clone()
      .applyAxisAngle(normal, d.camYaw)
      .multiplyScalar(-Math.cos(d.camPitch) * d.camDistance),
    target = base.clone().addScaledVector(normal, 1.8),
    cam = target
      .clone()
      .add(behind)
      .addScaledVector(normal, Math.sin(d.camPitch) * d.camDistance + 1.4);
  state.camera.position.lerp(cam, d.camReady ? 1 - Math.exp(-7 * dt) : 1);
  state.camera.up.copy(normal);
  state.controls.target
    .copy(target)
    .addScaledVector(forward, Math.min(5, Math.abs(d.v) * 0.16));
  state.camera.lookAt(state.controls.target);
  d.camReady = true;
  nearClip();
  if (now - d.lastSend > 180) {
    d.lastSend = now;
    sendDriverPose();
  }
  document.getElementById("drive-speed").textContent = Math.round(
    Math.abs(d.v) * 3.6,
  );
  document.getElementById("drive-rpm").textContent = Math.round(d.rpm) + " RPM";
  document.getElementById("drive-gear").textContent = d.gear < 0 ? "R" : d.gear;
  document.getElementById("drive-surface").textContent =
    `${d.surface} · grip ${d.mu.toFixed(2)} · ${d.grounded ? "CONTACT" : "AIRBORNE"}`;
  document.getElementById("rpm-fill").style.width =
    Math.min(100, d.rpm / 60) + "%";
  updateRemoteTerrain(d);
}

export function initialize() {
  state.DRIVER_OWNER = crypto.randomUUID
    ? crypto.randomUUID()
    : "driver-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  state.driverAccumulator = 0;
  state.driverRequest = false;
  state.collisionIndex = null;
  document.getElementById("exit-drive").onclick = () => stopDriving();
  document.getElementById("infobody").addEventListener("click", (e) => {
    const b = e.target.closest("[data-drive]");
    if (b) startDriving(b.dataset.drive);
  });
  window.addEventListener("pagehide", () => {
    if (state.drive)
      navigator.sendBeacon(
        "/cmd",
        new Blob(
          [
            JSON.stringify({
              cmd: "drive_release",
              token: state.ADMIN,
              owner: state.DRIVER_OWNER,
              name: state.drive.name,
            }),
          ],
          { type: "application/json" },
        ),
      );
  });
}
