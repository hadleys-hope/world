/** render/frame: procedural colony viewer. */
import { state } from "../state.js";
import { surfaceClearance, updateCameraMotion } from "../camera.js";
import { quatAt, sph } from "../geometry/planet.js";
import { updateUtilityFlow } from "../models/drainage.js";
import { updateSolarSystem } from "../models/solar-system.js";
import { updateDetail } from "./lod.js";
import { updatePackets } from "./packets.js";
import * as THREE from "three";

export function resize() {
  const w = state.mapEl.clientWidth,
    h = state.mapEl.clientHeight;
  state.renderer.setSize(w, h, false);
  state.composer.setSize(w, h);
  state.renderer.domElement.style.width = w + "px";
  state.renderer.domElement.style.height = h + "px";
  state.camera.aspect = w / h;
  state.camera.updateProjectionMatrix();
}

export function frame() {
  const now = performance.now();
  const t = (now - state.t0) / 1000;
  updateSolarSystem(now, Math.max(0, (now - state.cameraLast) / 1000));
  if (state.flyAnim) {
    const u = Math.min(1, (now - state.flyAnim.t0) / 1200);
    const k = u * u * (3 - 2 * u);
    state.camera.position.lerpVectors(state.flyAnim.from, state.flyAnim.to, k);
    state.controls.target.lerpVectors(
      state.flyAnim.tfrom,
      state.flyAnim.tto,
      k,
    );
    state.camera.lookAt(state.controls.target);
    if (u >= 1) state.flyAnim = null;
  }
  updateCameraMotion(now);
  updateDetail();
  updateUtilityFlow(t);
  {
    const hour =
      (state.clock.hour +
        (state.clock.speed * (now - state.clock.at)) / 1000 / 60) %
      24;
    const a = ((hour - 6) / 24) * Math.PI * 2;
    state.sunDir.copy(state.solarSystem.star.position).normalize();
    state.sun.position.copy(state.sunDir).multiplyScalar(12000);
    state.sunSprite.visible = false;
    const dl =
      Math.max(0, Math.sin((Math.PI * (hour - 6)) / 12)) *
      (state.weather.storm ? 0.2 : 1);
    state.sun.intensity = 0.8 + 1.6 * dl;
    state.sun.color.setHSL(0.08, 0.6, 0.55 + 0.25 * dl);
    state.planetMat.uniforms.uSun.value.copy(state.sun.position).normalize();
    state.planetMat.uniforms.uTime.value = t;
    const wantFog =
      state.activeBody !== 2 || state.systemView || surfaceClearance() > 2200
        ? 0
        : state.weather.storm
          ? 0.00055
          : state.weather.precip === "snow"
            ? 0.00018
            : 0.0;
    state.scene.fog.density += (wantFog - state.scene.fog.density) * 0.05;
    state.scene.fog.color.setHex(state.weather.storm ? 0x3a3e48 : 0x2a2e38);
    const snowOn =
      state.activeBody === 2 &&
      !state.systemView &&
      (state.weather.precip === "snow" || state.weather.storm);
    const mat = state.weather.snow.material;
    const dist = state.camera.position.distanceTo(state.controls.target);
    const near = 1 - Math.min(1, Math.max(0, (dist - 700) / 1400));
    mat.opacity +=
      ((snowOn ? (state.weather.storm ? 0.85 : 0.55) * near : 0) -
        mat.opacity) *
      0.05;
    mat.size = 3 + 3 * near;
    if (mat.opacity > 0.02) {
      const p = state.weather.snow.geometry.attributes.position;
      const c = state.controls.target;
      const n = c.clone().normalize();
      const side = new THREE.Vector3()
        .crossVectors(n, new THREE.Vector3(0, 0, 1))
        .normalize();
      const fwd = new THREE.Vector3().crossVectors(side, n);
      const w = state.weather.wind * (state.weather.storm ? 0.9 : 0.3);
      const dt = 1 / 60;
      for (let i = 0; i < p.count; i++) {
        let x = p.getX(i),
          y = p.getY(i),
          z = p.getZ(i);
        y -= (state.weather.storm ? 60 : 25) * dt * 4;
        x += w * dt * 4;
        z += Math.sin(t * 3 + i) * 0.5;
        if (y < 0) {
          y = 500;
          x = (Math.random() - 0.5) * 1600;
          z = (Math.random() - 0.5) * 1600;
        }
        if (x > 800) x = -800;
        p.setXYZ(i, x, y, z);
      }
      p.needsUpdate = true;
      state.weather.snow.position.copy(c);
      state.weather.snow.quaternion.copy(
        new THREE.Quaternion().setFromUnitVectors(
          new THREE.Vector3(0, 1, 0),
          n,
        ),
      );
    }
    if (
      state.weather.tornadoOn &&
      state.activeBody === 2 &&
      !state.systemView
    ) {
      const tor = state.weather.tornado;
      tor.visible = true;
      tor.material.opacity += (0.35 - tor.material.opacity) * 0.02;
      const ang = t * 0.05;
      const [tx, ty] = [Math.cos(ang) * 1100 + 300, Math.sin(ang) * 900];
      tor.position.copy(sph(tx, ty, 130));
      tor.quaternion.copy(quatAt(tx, ty));
      tor.rotateY(t * 6);
    } else if (state.weather.tornado.visible) {
      const tor = state.weather.tornado;
      tor.material.opacity *= 0.97;
      if (tor.material.opacity < 0.01) tor.visible = false;
    }
  }
  if (state.housesMesh) {
    state.flowPower.update(t);
    if (state.phaseDropFlow) state.phaseDropFlow.update(t);
    state.flowWater.update(t);
    if (state.oceanFlow) {
      state.oceanFlow.update(t);
      state.thermalFlow.update(t);
      state.complex.deliveryFlow.update(t);
    }
    updatePackets();
    for (const g of state.gates) {
      if (g.armTarget !== undefined)
        g.arm.rotation.x += (g.armTarget - g.arm.rotation.x) * 0.15;
      g.beacons.forEach((b, i) => {
        b.material.opacity =
          0.3 + 0.7 * Math.max(0, Math.sin(t * 8 + i * Math.PI));
      });
    }
    for (const w of state.lockWedges) {
      if (w.visible) w.material.opacity = 0.1 + 0.08 * Math.sin(t * 3);
    }
    for (const p of state.xenoPool) {
      if (p.to) {
        const u = Math.min(1, (now - p.t0) / Math.max(200, state.pollGap));
        p.g.position.lerpVectors(p.from, p.to, u);
        p.g.quaternion.slerp(p.q, 0.2);
        const moving =
          p.state === "hunt" || p.state === "approach" || p.state === "retreat";
        p.g.children[0].position.y =
          4 + (moving ? Math.abs(Math.sin(t * 14)) * 1.2 : 0);
        if (p.state === "attack")
          p.g.children[1].position.z = 5.5 + Math.sin(t * 20) * 1.5;
        if (p.state === "dying")
          p.g.rotation.z = Math.min(1.4, p.g.rotation.z + 0.1);
        else p.g.rotation.z = 0;
      }
    }
    if (state.squadGroup.userData.to) {
      const d = state.squadGroup.userData;
      const u = Math.min(1, (now - d.t0) / Math.max(200, state.pollGap));
      state.squadGroup.position.lerpVectors(d.from, d.to, u);
      state.squadGroup.quaternion.slerp(d.q, 0.2);
    }
    for (const [name, rv] of Object.entries(state.rovers)) {
      if (state.drive?.name === name) continue;
      if (rv.to) {
        const u = Math.min(1, (now - rv.t0) / Math.max(200, state.pollGap));
        rv.g.position.lerpVectors(rv.from, rv.to, u);
        rv.g.quaternion.slerp(rv.q, 0.2);
        rv.distance = rv.distanceFrom + (rv.distanceTo - rv.distanceFrom) * u;
        for (const wheel of rv.g.userData.wheels || [])
          wheel.rotation.z = -rv.distance / 0.66;
      }
    }
    const d = state.camera.position.distanceTo(state.controls.target);
    state.lod.near.forEach((s) => (s.visible = state.layers.labels && d < 900));
    state.lod.mid.forEach((s) => (s.visible = state.layers.labels && d < 5000));
    state.complex.rings.forEach((r, k) => {
      const u = (t * 0.8 + k / 3) % 1;
      r.scale.setScalar(0.5 + u * 1.5);
      r.material.opacity = 0.6 * (1 - u);
    });
    state.complex.towerLight.material.opacity = 0.5 + 0.5 * Math.sin(t * 4);
    if (state.complex.wheel)
      state.complex.wheel.rotation.z +=
        state.S && state.S.power.mine ? 0.05 : 0;
    if (state.complex.steamOn !== undefined) {
      const c = state.G.cfg;
      const pts = [];
      for (let k = 0; k < 12; k++) {
        const u = (t * 0.25 + k / 12) % 1;
        for (const [tx, ty] of [
          [c.reactor_pos[0] - 90, c.reactor_pos[1] - 60],
          [c.reactor_pos[0] - 90, c.reactor_pos[1] + 60],
        ])
          pts.push(
            sph(
              tx + Math.sin(k * 3 + t) * 6 * u,
              ty + Math.cos(k * 2) * 6 * u,
              95 + u * 60,
            ),
          );
      }
      const a = state.complex.steam.geometry.attributes.position;
      for (let i = 0; i < a.count; i++) {
        if (state.complex.steamOn && i < pts.length)
          a.setXYZ(i, pts[i].x, pts[i].y, pts[i].z);
        else a.setXYZ(i, 0, -99999, 0);
      }
      a.needsUpdate = true;
    }
  }
  if (state.housesMesh) {
    for (const m of state.pipeMats) {
      if (m.userData.rate > 0)
        m.userData.tex.offset.x -= m.userData.rate * 0.02;
    }
    if (state.complex.beacon)
      state.complex.beacon.material.opacity =
        0.4 + 0.6 * Math.abs(Math.sin(t * 2));
  }
  state.sunTarget.position.copy(state.controls.target);
  const sd = state.camera.position.distanceTo(state.controls.target);
  const desiredNear = Math.max(
    0.005,
    Math.min(15, surfaceClearance() * 0.0006),
  );
  if (Math.abs(state.camera.near - desiredNear) > 0.01) {
    state.camera.near = desiredNear;
    state.camera.updateProjectionMatrix();
  }
  const ext = Math.min(2600, Math.max(90, sd * 1.2));
  state.sun.shadow.camera.left = -ext;
  state.sun.shadow.camera.right = ext;
  state.sun.shadow.camera.top = ext;
  state.sun.shadow.camera.bottom = -ext;
  state.sun.shadow.camera.updateProjectionMatrix();
  state.sun.position
    .copy(state.controls.target)
    .add(state.sunDir.clone().multiplyScalar(8000));
  if (state.layers.bloom) state.composer.render();
  else state.renderer.render(state.scene, state.camera);
  requestAnimationFrame(frame);
}

export function initialize() {
  window.addEventListener("resize", resize);
  resize();
  state.t0 = performance.now();
}
