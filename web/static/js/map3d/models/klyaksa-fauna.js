/** models/klyaksa-fauna: Klyaksa's flying crocodiles over the domed cities, from /klyaksa/state.json.
 * Same figures as LV-426 had (models/flying-crocs.js: shared geometry, wings, jaw and tail), placed in the
 * body's frame so they ride along with the planet. A hit on a dome makes it flash; its health crazes the glass. */
import { state } from "../state.js";
import { PLATEAU } from "../geometry/noise.js";
import { crocPose, crocShapes } from "./flying-crocs.js";
import { material } from "./materials.js";
import { dirAt } from "./klyaksa.js";
import * as THREE from "three";

const MAX = 160;
const pool = [];
let wingTime = 0, lastNow = 0;
const _up = new THREE.Vector3(), _e = new THREE.Vector3(), _n = new THREE.Vector3(), _f = new THREE.Vector3(), _x = new THREE.Vector3();

function figure(body) {
  const s = crocShapes();
  const tame = [material("croc-hide", 0x4c6a3a, { roughness: 0.9 }), material("croc-wing", 0x6f8647, { roughness: 0.95, side: THREE.DoubleSide })];
  const wild = [material("croc-wild", 0x5a3a2a, { roughness: 0.85 }), material("croc-wild-wing", 0x7a4a34, { roughness: 0.9, side: THREE.DoubleSide })];
  const g = new THREE.Group(), rig = new THREE.Group();
  g.add(rig);
  rig.add(new THREE.Mesh(s.body, tame[0]));
  const part = (geometry, mat, x, y, z) => {
    const pivot = new THREE.Group();
    pivot.position.set(x, y, z);
    pivot.add(new THREE.Mesh(geometry, mat));
    rig.add(pivot);
    return pivot;
  };
  const jaw = part(s.jaw, tame[0], 0, -0.25, 6.6), tail = part(s.tail, tame[0], 0, 0, -3.6);
  const wingR = part(s.wingR, tame[1], 1.5, 0.9, 0.8), wingL = part(s.wingL, tame[1], -1.5, 0.9, 0.8);
  const meshes = [];
  g.traverse((o) => o.isMesh && meshes.push(o));
  // Klyaksa's crocodiles are big: an elephant's size, about three times LV-426's sketch
  g.scale.setScalar(3);
  g.visible = false;
  body.add(g);
  const paint = (isWild) => meshes.forEach((o) => (o.material = (isWild ? wild : tame)[o.material.side === THREE.DoubleSide ? 1 : 0]));
  return { g, rig, jaw, tail, wingR, wingL, paint, wild: false, from: new THREE.Vector3(), to: new THREE.Vector3(), q: new THREE.Quaternion(), t0: 0, state: "roost", live: false };
}

/** Where a city-plan point is in the body's frame, and the turn that faces `heading` there. */
function place(c, x, y, z, heading, R, outPos, outQ) {
  const X = c.at[0] + x, Y = c.at[1] + y, ground = R + R * PLATEAU + 0.25;
  _up.copy(dirAt(X, Y, R));
  outPos.copy(_up).multiplyScalar(ground + z);
  _e.copy(dirAt(X + 1, Y, R)).sub(_up).normalize();
  _n.copy(dirAt(X, Y + 1, R)).sub(_up).normalize();
  _f.copy(_e).multiplyScalar(Math.cos(heading)).addScaledVector(_n, Math.sin(heading)).normalize();
  _x.crossVectors(_up, _f).normalize();
  _f.crossVectors(_x, _up);
  outQ.setFromRotationMatrix(new THREE.Matrix4().makeBasis(_x, _up, _f));
}

/** Per poll: every crocodile of every city gets a figure and its next position; domes flash on new hits. */
export function syncKlyaksaFauna(s, body, R, now) {
  const plan = state.klyaksaPlanData;
  if (!plan) return;
  const byId = Object.fromEntries(plan.cities.map((c) => [c.id, c]));
  let k = 0;
  for (const city of s.cities) {
    const c = byId[city.id];
    if (!c) continue;
    const dome = state.klyaksaDomes?.[city.id];
    if (dome) {
      const u = dome.material.uniforms, hits = city.raid?.dome_hits ?? 0, seen = dome.userData.hits ?? hits;
      if (hits > seen) u.uFlash.value = 1;
      dome.userData.hits = hits;
      u.uDamage.value = 1 - (city.dome_hp ?? 100) / 100;
    }
    for (const m of city.crocs || []) {
      if (k >= MAX) break;
      const p = pool[k] || (pool[k] = figure(body));
      k++;
      const q = new THREE.Quaternion();
      place(c, m.x, m.y, m.z, m.heading, R, p.to, q);
      if (!p.live) p.g.position.copy(p.to);
      p.from.copy(p.g.position);
      p.q.copy(q);
      p.t0 = now;
      p.state = m.state;
      p.live = true;
      p.g.visible = state.layers.fauna !== false;
      if (!!m.wild !== p.wild) { p.wild = !!m.wild; p.paint(p.wild); }
    }
  }
  for (; k < pool.length; k++) { pool[k].g.visible = false; pool[k].live = false; }
}

/** Per frame: glide between polls, move wings, jaw and tail; dome flashes fade. */
export function updateKlyaksaFauna(now) {
  const dt = Math.min(0.1, Math.max(0, (now - (lastNow || now)) / 1000));
  lastNow = now;
  wingTime += dt;
  const ease = 1 - Math.exp(-dt * 6);
  pool.forEach((p, k) => {
    if (!p.live) return;
    const u = Math.min(1, (now - p.t0) / 2000);
    p.g.position.lerpVectors(p.from, p.to, u);
    p.g.quaternion.slerp(p.q, ease);
    const pose = crocPose(p.state, wingTime, k);
    const toward = (o, axis, v) => { o.rotation[axis] += (v - o.rotation[axis]) * ease; };
    toward(p.wingR, "z", pose.flap); toward(p.wingL, "z", -pose.flap);
    toward(p.wingR, "y", pose.sweep); toward(p.wingL, "y", -pose.sweep);
    toward(p.jaw, "x", pose.jaw); toward(p.tail, "y", pose.tail);
    toward(p.rig, "x", pose.pitch); toward(p.rig, "z", pose.bank);
  });
  for (const dome of Object.values(state.klyaksaDomes || {})) {
    const f = dome.material.uniforms.uFlash;
    if (f.value > 0.001) f.value *= Math.exp(-dt * 5);
  }
}
