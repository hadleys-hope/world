/** camera: procedural colony viewer. */
import { state } from "./state.js";
import { startDriving, stopDriving, updateDriving } from "./driving.js";
import { goHome, switchPlanet } from "./models/solar-system.js";
import * as THREE from "three";

export function activeCentre() {
  return state.systemView
    ? state.solarSystem?.star.position || new THREE.Vector3()
    : state.solarSystem?.bodies[state.activeBody].position ||
        new THREE.Vector3();
}

export function direction() {
  return state.camera.getWorldDirection(new THREE.Vector3());
}

export function syncTarget(distance = 20) {
  state.controls.target
    .copy(state.camera.position)
    .addScaledVector(direction(), distance);
}

export function surfaceClearance() {
  const c = activeCentre(),
    r = state.systemView
      ? 8500
      : state.solarSystem?.specs[state.activeBody].radius || state.RP;
  return Math.max(0.025, state.camera.position.distanceTo(c) - r);
}

export function nearClip() {
  const clearance = surfaceClearance();
  state.camera.near = Math.max(0.005, Math.min(15, clearance * 0.0006));
  state.camera.updateProjectionMatrix();
}

export function navigationHUD() {
  const b = state.solarSystem?.specs[state.activeBody];
  const activeIndex = state.systemView ? -1 : state.activeBody;
  document.querySelectorAll('[data-planet]').forEach(button => {
    button.setAttribute('aria-pressed', String(+button.dataset.planet === activeIndex));
  });
  document.getElementById("camera-mode").textContent =
    state.cameraMode === "drive"
      ? "DRIVING"
      : state.cameraMode === "flight"
        ? "FREE FLIGHT"
        : "PLANET ORBIT";
  document.getElementById("flight-speed").textContent =
    state.flightSpeed.toFixed(state.flightSpeed < 1 ? 2 : 0) + " m/s";
  document.getElementById("focus-world").textContent = state.systemView
    ? "SYSTEM / ORBITAL VIEW"
    : `${b?.name || "ACHERON"} · ${b?.climate || "−55 °C / FROZEN OCEAN"}`;
  document.getElementById("hint").textContent =
    state.cameraMode === "drive"
      ? "W/S or ↑/↓ throttle / brake / reverse · A/D steer · SPACE handbrake · drag look · wheel follow distance · ESC park & exit"
      : state.cameraMode === "flight"
        ? "SHIFT → orbit · WASD fly · Q/E altitude · drag to look · L lock mouse / ESC release · wheel approach · +/− flight speed · F inspect"
        : "Drag with any button → orbit planet · wheel / pinch → approach · SHIFT → free flight · 1–4 planets · 0 system · HOME colony · F inspect";
  document.getElementById("flight-controls").hidden =
    state.cameraMode !== "flight";
  document.getElementById("driving-hud").hidden = !state.drive;
  document.getElementById("camera-toggle").disabled = !!state.drive;
  document.getElementById("camera-shortcut").hidden = !!state.drive;
}

export function setCameraMode(mode) {
  if (state.drive && mode !== "drive") return;
  if (mode === "flight" && state.cameraMode === "orbit")
    state.flightSpeed = Math.max(2, Math.min(1800, surfaceClearance() * 0.65));
  state.cameraMode = mode;
  state.cameraKeys.clear();
  state.flightVelocity.set(0, 0, 0);
  state.inputDrag = null;
  state.flyAnim = null;
  if (document.pointerLockElement) document.exitPointerLock();
  navigationHUD();
}

export function rotateCamera(dx, dy) {
  if (state.cameraMode === "drive") {
    if (state.drive) {
      state.drive.camYaw -= dx * 0.004;
      state.drive.camPitch = THREE.MathUtils.clamp(
        state.drive.camPitch + dy * 0.003,
        0.08,
        1.1,
      );
    }
    return;
  }
  const center = activeCentre(),
    right = new THREE.Vector3(1, 0, 0).applyQuaternion(state.camera.quaternion),
    up =
      state.cameraMode === "orbit"
        ? new THREE.Vector3(0, 1, 0)
        : state.camera.position.clone().sub(center).normalize();
  const scale =
    state.cameraMode === "orbit"
      ? Math.max(
          0.000008,
          0.003 *
            Math.min(
              1,
              surfaceClearance() /
                Math.max(
                  1,
                  state.solarSystem?.specs[state.activeBody].radius || state.RP,
                ),
            ),
        )
      : 0.0025;
  const yaw = new THREE.Quaternion().setFromAxisAngle(up, -dx * scale),
    pitch = new THREE.Quaternion().setFromAxisAngle(right, -dy * scale),
    q = yaw.multiply(pitch);
  if (state.cameraMode === "orbit") {
    state.camera.position.sub(center).applyQuaternion(q).add(center);
    state.controls.target.sub(center).applyQuaternion(q).add(center);
  }
  state.camera.quaternion.premultiply(q).normalize();
  state.camera.up.applyQuaternion(q).normalize();
  if (state.cameraMode === "flight") syncTarget();
  state.flyAnim = null;
}

export function zoomCamera(delta) {
  if (state.drive) {
    state.drive.camDistance = THREE.MathUtils.clamp(
      state.drive.camDistance * Math.exp(delta * 0.0015),
      3,
      45,
    );
    return;
  }
  const forward = direction(),
    clear = surfaceClearance(),
    base = Math.max(
      0.04,
      Math.min(clear, state.camera.position.distanceTo(state.controls.target)),
    ),
    step = THREE.MathUtils.clamp(delta, -250, 250) * 0.0025 * base;
  state.camera.position.addScaledVector(forward, -step);
  state.controls.target.addScaledVector(forward, -step);
  state.flyAnim = null;
  nearClip();
}

export function updateCameraMotion(now) {
  const dt = Math.max(0, Math.min(0.05, (now - state.cameraLast) / 1000));
  state.cameraLast = now;
  if (state.cameraMode === "drive") {
    updateDriving(dt, now);
    return;
  }
  if (state.cameraMode === "flight") {
    const forward = direction(),
      right = new THREE.Vector3(1, 0, 0).applyQuaternion(
        state.camera.quaternion,
      ),
      up = state.camera.position.clone().sub(activeCentre()).normalize(),
      move = new THREE.Vector3();
    if (state.cameraKeys.has("w") || state.cameraKeys.has("arrowup"))
      move.add(forward);
    if (state.cameraKeys.has("s") || state.cameraKeys.has("arrowdown"))
      move.sub(forward);
    if (state.cameraKeys.has("a") || state.cameraKeys.has("arrowleft"))
      move.sub(right);
    if (state.cameraKeys.has("d") || state.cameraKeys.has("arrowright"))
      move.add(right);
    if (state.cameraKeys.has("q")) move.sub(up);
    if (state.cameraKeys.has("e")) move.add(up);
    if (move.lengthSq()) {
      move.normalize().multiplyScalar(state.flightSpeed);
      state.flyAnim = null;
    }
    state.flightVelocity.lerp(move, 1 - Math.exp(-18 * dt));
    const shift = state.flightVelocity.clone().multiplyScalar(dt);
    state.camera.position.add(shift);
    state.controls.target.add(shift);
  } else if (state.cameraKeys.size) {
    const x =
        (state.cameraKeys.has("d") || state.cameraKeys.has("arrowright")
          ? 1
          : 0) -
        (state.cameraKeys.has("a") || state.cameraKeys.has("arrowleft")
          ? 1
          : 0),
      y =
        (state.cameraKeys.has("s") || state.cameraKeys.has("arrowdown")
          ? 1
          : 0) -
        (state.cameraKeys.has("w") || state.cameraKeys.has("arrowup") ? 1 : 0);
    rotateCamera(x * dt * 500, y * dt * 500);
  }
  nearClip();
}

export function focusPoint(point, distance = 12, normal = null) {
  if (state.drive) return;
  state.cameraMode = "flight";
  state.flightVelocity.set(0, 0, 0);
  state.cameraKeys.clear();
  const dir = normal
    ? normal.clone().normalize()
    : state.camera.position.clone().sub(point).normalize();
  state.camera.up.copy(point.clone().sub(activeCentre()).normalize());
  state.flyAnim = {
    from: state.camera.position.clone(),
    to: point.clone().addScaledVector(dir, distance),
    tfrom: state.controls.target.clone(),
    tto: point.clone(),
    t0: performance.now(),
  };
  state.flightSpeed = Math.max(0.2, Math.min(20, distance));
  navigationHUD();
}

export function focusSelection() {
  if (!state.selected) return;
  if (state.selected.kind === "rover") {
    const rv = state.rovers[state.selected.extra || state.selected.id];
    if (rv) focusPoint(rv.g.position, 12);
    return;
  }
  if (state.selected.kind === "pole") {
    const meter = state.cabinetMeters[state.selected.id];
    focusPoint(
      meter.position,
      3,
      new THREE.Vector3(0, 0.15, 1).applyQuaternion(meter.quaternion),
    );
    return;
  }
  if (state.selected.kind === "house") {
    const h = state.houseShells[state.selected.id],
      dim = state.DIM[state.G.houses.type[state.selected.id]];
    focusPoint(
      h.base.clone().addScaledVector(h.base.clone().normalize(), dim[1] / 2),
      Math.max(dim[0], dim[2]) * 1.5,
    );
    return;
  }
  const obj = state.clickables.find(
    (o) => o.userData.click?.id === state.selected.id,
  );
  if (obj) {
    const bounds = new THREE.Box3().setFromObject(obj),
      center = bounds.getCenter(new THREE.Vector3());
    focusPoint(
      center,
      Math.max(8, bounds.getSize(new THREE.Vector3()).length() * 1.2),
    );
  }
}

export function initialize() {
  state.cameraKeys = new Set();
  state.cameraLast = performance.now();
  state.cameraMode = "orbit";
  state.flightSpeed = 12;
  state.flightVelocity = new THREE.Vector3();
  state.inputDrag = null;
  state.activeBody = 2;
  state.systemView = false;
  state.drive = null;
  state.orbitalCamera = { yaw: 0, pitch: 0 };
  state.typing = (e) =>
    e.target.closest("input,textarea,select,[contenteditable=true]");
  window.addEventListener("keydown", (e) => {
    if (state.typing(e) || e.ctrlKey || e.metaKey || e.altKey) return;
    const key = e.key.toLowerCase();
    if (key === "shift") {
      e.preventDefault();
      if (!e.repeat && !state.drive)
        setCameraMode(state.cameraMode === "flight" ? "orbit" : "flight");
      return;
    }
    if (
      [
        "w",
        "a",
        "s",
        "d",
        "q",
        "e",
        "arrowleft",
        "arrowright",
        "arrowup",
        "arrowdown",
        " ",
      ].includes(key)
    ) {
      e.preventDefault();
      state.cameraKeys.add(key);
    }
    if (!e.repeat && key === "l" && state.cameraMode === "flight" && !state.drive) {
      state.renderer.domElement.requestPointerLock?.()?.catch?.(() => {});
    }
    if (!e.repeat && key === "f" && !state.drive) focusSelection();
    if (
      !e.repeat &&
      key === "enter" &&
      state.selected?.kind === "rover" &&
      !state.drive
    )
      startDriving(state.selected.extra || state.selected.id);
    if (!e.repeat && key === "escape") {
      if (state.drive) stopDriving();
      else {
        state.cameraKeys.clear();
        state.inputDrag = null;
        if (document.pointerLockElement) document.exitPointerLock();
      }
    }
    if (!e.repeat && ["0", "1", "2", "3", "4"].includes(key) && !state.drive)
      switchPlanet(+key - 1);
    if (key === "home" && !state.drive) {
      e.preventDefault();
      goHome();
    }
    if (["+", "=", "-", "_"].includes(key)) {
      state.flightSpeed = THREE.MathUtils.clamp(
        state.flightSpeed * (key === "-" || key === "_" ? 1 / 1.5 : 1.5),
        0.05,
        6000,
      );
      navigationHUD();
    }
  });
  window.addEventListener("keyup", (e) =>
    state.cameraKeys.delete(e.key.toLowerCase()),
  );
  state.clearInput = () => {
    state.cameraKeys.clear();
    state.inputDrag = null;
    state.flightVelocity.set(0, 0, 0);
    if (state.drive) {
      state.drive.throttle = 0;
      state.drive.brake = 1;
    }
  };
  window.addEventListener("blur", state.clearInput);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) state.clearInput();
  });
  state.renderer.domElement.addEventListener("contextmenu", (e) =>
    e.preventDefault(),
  );
  state.renderer.domElement.addEventListener("pointerdown", (e) => {
    if (e.target !== state.renderer.domElement) return;
    e.preventDefault();
    state.inputDrag = { id: e.pointerId, x: e.clientX, y: e.clientY, total: 0 };
    state.renderer.domElement.setPointerCapture(e.pointerId);
  });
  state.renderer.domElement.addEventListener("pointermove", (e) => {
    if (document.pointerLockElement === state.renderer.domElement) {
      rotateCamera(e.movementX, e.movementY);
      return;
    }
    if (!state.inputDrag || e.pointerId !== state.inputDrag.id) return;
    const dx = e.clientX - state.inputDrag.x,
      dy = e.clientY - state.inputDrag.y;
    state.inputDrag.total += Math.hypot(dx, dy);
    state.inputDrag.x = e.clientX;
    state.inputDrag.y = e.clientY;
    rotateCamera(dx, dy);
  });
  // A selection click must remain a normal click, including the inspector buttons.
  state.renderer.domElement.addEventListener("pointerup", () => {
    state.inputDrag = null;
  });
  state.renderer.domElement.addEventListener("pointercancel", state.clearInput);
  document.addEventListener("pointerlockchange", () => {
    state.inputDrag = null;
    state.cameraKeys.clear();
  });
  state.renderer.domElement.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      e.stopImmediatePropagation();
      const delta =
        e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 600 : 1);
      zoomCamera(delta);
    },
    { passive: false, capture: true },
  );
  document.getElementById("camera-toggle").onclick = () => {
    if (!state.drive)
      setCameraMode(state.cameraMode === "flight" ? "orbit" : "flight");
  };
  document.getElementById("slower-flight").onclick = () => {
    state.flightSpeed = Math.max(0.05, state.flightSpeed / 1.5);
    navigationHUD();
  };
  document.getElementById("faster-flight").onclick = () => {
    state.flightSpeed = Math.min(6000, state.flightSpeed * 1.5);
    navigationHUD();
  };
}
