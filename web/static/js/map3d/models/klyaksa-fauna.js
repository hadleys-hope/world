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
const _qFace = new THREE.Quaternion(), _mFace = new THREE.Matrix4();
const _up = new THREE.Vector3(), _e = new THREE.Vector3(), _n = new THREE.Vector3(), _f = new THREE.Vector3(), _x = new THREE.Vector3();

// Scales: a pattern in the figure's own space, so they stay put on the hide; pale belly, dark ridged back.
function scaled(mat) {
  if (mat.userData.scaled) return mat;
  mat.userData.scaled = true;
  mat.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vObj;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvObj = position;");
    shader.fragmentShader = shader.fragmentShader.replace("#include <common>", "#include <common>\nvarying vec3 vObj;")
      .replace("#include <color_fragment>", `#include <color_fragment>
        { vec2 q = vec2(vObj.z * 2.2, vObj.x * 2.2 + floor(vObj.z * 2.2) * 0.5);
          vec2 f = abs(fract(q) - 0.5);
          float plate = smoothstep(0.42, 0.5, max(f.x, f.y));            // the grooves between scales
          float belly = smoothstep(-0.2, -1.1, vObj.y);                   // pale underside
          float ridge = smoothstep(1.0, 1.5, vObj.y) * (0.6 + 0.4 * sin(vObj.z * 6.0));
          diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * 1.9 + vec3(0.12, 0.1, 0.04), belly * 0.7);
          diffuseColor.rgb *= 1.0 - plate * 0.45 - ridge * 0.25; }`);
  };
  mat.needsUpdate = true;
  return mat;
}

function figure(body) {
  const s = crocShapes();
  const tame = [scaled(material("croc-hide", 0x4c6a3a, { roughness: 0.9 })), material("croc-wing", 0x6f8647, { roughness: 0.95, side: THREE.DoubleSide })];
  const wild = [scaled(material("croc-wild", 0x5a3a2a, { roughness: 0.85 })), material("croc-wild-wing", 0x7a4a34, { roughness: 0.9, side: THREE.DoubleSide })];
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
  return { g, rig, jaw, tail, wingR, wingL, paint, wild: false, from: new THREE.Vector3(), to: new THREE.Vector3(), q: new THREE.Quaternion(), t0: 0, state: "roost", live: false,
    climb: 0, turn: 0, heading: 0, big: false, prev: new THREE.Vector3() };
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
      // what the physics of the next pose needs: how fast it climbs, how fast it turns
      const dh = Math.atan2(Math.sin(m.heading - p.heading), Math.cos(m.heading - p.heading));
      p.turn = p.live ? dh / 2 : 0;
      p.climb = p.live ? (m.z - (p.z ?? m.z)) / 2 : 0;
      p.heading = m.heading;
      p.z = m.z;
      p.from.copy(p.g.position);
      p.q.copy(q);
      p.t0 = now;
      p.state = m.state;
      p.live = true;
      p.g.visible = state.layers.fauna !== false;
      if (!!m.wild !== p.wild) { p.wild = !!m.wild; p.paint(p.wild); }
      if (p.big) { p.big = false; p.g.scale.setScalar(3); }
    }
    // the migrating herd: bigger still, high over the dome; the shot ones tumble down
    for (const m of city.hazards?.migrants || []) {
      if (k >= MAX) break;
      const p = pool[k] || (pool[k] = figure(body));
      k++;
      const q = new THREE.Quaternion();
      place(c, m.x, m.y, m.z, m.heading, R, p.to, q);
      if (!p.live || !p.big) p.g.position.copy(p.to);
      p.from.copy(p.g.position);
      p.q.copy(q);
      p.t0 = now;
      p.state = m.state === "falling" ? "falling" : "migrate";
      p.live = true;
      p.climb = m.state === "falling" ? -9 : 0;
      p.turn = 0;
      p.g.visible = state.layers.fauna !== false;
      if (!p.big) { p.big = true; p.g.scale.setScalar(4.5); }
      if (p.wild) { p.wild = false; p.paint(false); }
    }
    tracers(city, c, R, body, now);
  }
  if (!state.klyaksaLairs) buildLairs(body, R);
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
    // a flying crocodile faces where it is going: its nose follows its real path between polls, not a heading jump
    const flying = p.state !== "roost" && p.state !== "bask" && p.state !== "attack" && p.state !== "gather";
    _f.subVectors(p.to, p.from);
    if (flying && _f.lengthSq() > 4) {
      _up.copy(p.g.position).normalize();
      _f.addScaledVector(_up, -_f.dot(_up)).normalize();
      _x.crossVectors(_up, _f).normalize();
      _f.crossVectors(_x, _up);
      _qFace.setFromRotationMatrix(_mFace.makeBasis(_x, _up, _f));
      p.g.quaternion.slerp(_qFace, ease);
    } else p.g.quaternion.slerp(p.q, ease);
    const pose = crocPose(p.state === "migrate" ? "soar" : p.state === "falling" ? "dive" : p.state, wingTime * (p.climb > 1 ? 1.8 : 1), k);
    // physics of flight: nose follows the climb, the body banks into the turn, a glide folds the wings back
    const pitch = THREE.MathUtils.clamp(-p.climb * 0.05, -0.6, 0.5), bank = THREE.MathUtils.clamp(p.turn * 3, -0.7, 0.7);
    pose.pitch = p.state === "falling" ? Math.sin(wingTime * 3 + k) * 1.4 : pose.pitch + pitch;
    pose.bank = p.state === "falling" ? wingTime * 2 + k : pose.bank + bank;
    if (p.climb < -2 && p.state !== "falling") { pose.flap = 0.05; pose.sweep = 0.6; }
    const toward = (o, axis, v) => { o.rotation[axis] += (v - o.rotation[axis]) * ease; };
    toward(p.wingR, "z", pose.flap); toward(p.wingL, "z", -pose.flap);
    toward(p.wingR, "y", pose.sweep); toward(p.wingL, "y", -pose.sweep);
    toward(p.jaw, "x", pose.jaw); toward(p.tail, "y", pose.tail);
    toward(p.rig, "x", pose.pitch); p.rig.rotation.z += (pose.bank - p.rig.rotation.z) * ease;
  });
  updateShells(now, dt);
  for (const dome of Object.values(state.klyaksaDomes || {})) {
    const f = dome.material.uniforms.uFlash;
    if (f.value > 0.001) f.value *= Math.exp(-dt * 5);
  }
}

// Air defence: four turrets on the shoulders of every dome. Each sits in an armoured mount let into the glass (a
// collar ring and a drum), turns on its mount (yaw) and raises a rack of twelve launch rails (pitch), like a rocket
// launcher. Before each salvo its rails charge, glowing orange like a railgun; then bolts streak to the target.
const turrets = [];
const shells = [];
const lastShots = {};
let boltMesh = null;
const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _q2 = new THREE.Quaternion(), _m2 = new THREE.Matrix4();
function domeSpot(c, R, k) {
  const Rd = c.wall + 45, Hd = Rd * 0.42, rr = Rd * 0.62, a = k * Math.PI / 2 + Math.PI / 4;
  const p = new THREE.Vector3(), q = new THREE.Quaternion();
  place(c, Math.cos(a) * rr, Math.sin(a) * rr, Hd * Math.sqrt(1 - 0.62 * 0.62), a, R, p, q);
  return { p, q, a };
}
function buildTurret(body, c, R, k) {
  const { p, q } = domeSpot(c, R, k);
  const armour = material("aa-armour", 0x2e3338, { roughness: 0.45, metalness: 0.75 }), trim = material("aa-trim", 0xc8a23a, { roughness: 0.4, metalness: 0.6 });
  const mount = new THREE.Group();
  mount.position.copy(p); mount.quaternion.copy(q);
  // the mount let into the glass: a heavy collar ring flush with the dome, an armoured drum on it
  mount.add(Object.assign(new THREE.Mesh(new THREE.TorusGeometry(10, 1.6, 10, 32).rotateX(Math.PI / 2), armour), {}));
  mount.add(Object.assign(new THREE.Mesh(new THREE.CylinderGeometry(8.5, 9.5, 6, 24).translate(0, 2, 0), armour), {}));
  mount.add(Object.assign(new THREE.Mesh(new THREE.CylinderGeometry(9.6, 9.6, 0.6, 24).translate(0, 5.2, 0), trim), {}));
  const yaw = new THREE.Group();
  yaw.position.y = 5.5;
  mount.add(yaw);
  yaw.add(new THREE.Mesh(new THREE.BoxGeometry(10, 5, 9).translate(0, 2.5, -1), armour));            // the turret body
  for (const s of [-1, 1]) yaw.add(new THREE.Mesh(new THREE.BoxGeometry(1.2, 7, 4).translate(s * 5.6, 4.5, 0), armour)); // trunnion cheeks
  const pitch = new THREE.Group();
  pitch.position.set(0, 6.5, 0);
  yaw.add(pitch);
  const rails = [], glow = new THREE.MeshBasicMaterial({ color: 0xff8a1e, transparent: true, opacity: 0.0, blending: THREE.AdditiveBlending, depthWrite: false });
  for (let row = 0; row < 3; row++)
    for (let col = 0; col < 4; col++) {
      const x = (col - 1.5) * 2.2, y = (row - 1) * 2.0;
      pitch.add(new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.2, 16).translate(x, y, 6), armour));         // a launch rail
      const line = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.35, 15.5).translate(x, y + 0.7, 6), glow); // its charge strip
      pitch.add(line);
      rails.push(new THREE.Vector3(x, y, 14.5));
    }
  pitch.add(new THREE.Mesh(new THREE.BoxGeometry(10.2, 7, 1.2).translate(0, 0, -2), trim));               // the rack's back plate
  body.add(mount);
  return { city: c.id, mount, yaw, pitch, glow, rails, charge: 0, aimYaw: 0, aimPitch: 0.6, target: null };
}
function ensureTurrets(body, R) {
  if (turrets.length || !state.klyaksaPlanData) return;
  for (const c of state.klyaksaPlanData.cities) for (let k = 0; k < 4; k++) turrets.push(buildTurret(body, c, R, k));
  boltMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.5, 0.5, 26, 6).rotateX(Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: 0xffb04a, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false }), 240);
  boltMesh.frustumCulled = false;
  boltMesh.count = 0;
  body.add(boltMesh);
}
function tracers(city, c, R, body, now) {
  const h = city.hazards;
  if (!h) return;
  ensureTurrets(body, R);
  // what the turrets aim at: the herd overhead, or raiders at the dome
  const targets = [...(h.migrants || []).filter((m) => m.state === "migrate"), ...(city.crocs || []).filter((m) => m.wild && (m.state === "raid" || m.state === "attack"))];
  const mine = turrets.filter((t) => t.city === city.id);
  mine.forEach((t, i) => {
    const m = targets.length ? targets[i % targets.length] : null;
    t.target = m ? (() => { const v = new THREE.Vector3(), q = new THREE.Quaternion(); place(c, m.x, m.y, m.z, 0, R, v, q); return v; })() : null;
  });
  const fired = h.aa.shots - (lastShots[city.id] ?? h.aa.shots);
  lastShots[city.id] = h.aa.shots;
  if (fired <= 0 || !targets.length) return;
  mine.forEach((t, i) => {
    if (!t.target) return;
    t.charge = 1;                                             // rails glow, then the salvo leaves
    for (let k = 0; k < 3; k++) shells.push({ t, rail: (i * 3 + k) % 12, to: t.target.clone(), t0: now + 350 + k * 120, life: 600 });
  });
}
function updateShells(now, dt) {
  for (const t of turrets) {
    // turn and raise the rack towards the target, slowly like a heavy mount
    if (t.target) {
      t.mount.worldToLocal(_a.copy(t.target).applyMatrix4(t.mount.parent.matrixWorld));
      t.aimYaw = Math.atan2(_a.x, _a.z);
      t.aimPitch = Math.atan2(_a.y - 12, Math.hypot(_a.x, _a.z));
    }
    const k = 1 - Math.exp(-dt * 2.5);
    t.yaw.rotation.y += Math.atan2(Math.sin(t.aimYaw - t.yaw.rotation.y), Math.cos(t.aimYaw - t.yaw.rotation.y)) * k;
    t.pitch.rotation.x += (-THREE.MathUtils.clamp(t.aimPitch, 0.1, 1.35) - t.pitch.rotation.x) * k;
    t.glow.opacity = Math.max(t.glow.opacity * Math.exp(-dt * 1.6), t.charge * 0.95);
    t.charge = Math.max(0, t.charge - dt * 2);
  }
  if (!boltMesh) return;
  let n = 0;
  for (let i = shells.length - 1; i >= 0; i--) {
    const s = shells[i], u = (now - s.t0) / s.life;
    if (u > 1) { shells.splice(i, 1); continue; }
    if (u < 0 || n >= 240) continue;
    s.t.pitch.localToWorld(_a.copy(s.t.rails[s.rail]));
    s.t.mount.parent.worldToLocal(_a);
    _b.lerpVectors(_a, s.to, u);
    _q2.setFromUnitVectors(new THREE.Vector3(0, 0, 1), s.to.clone().sub(_a).normalize());
    boltMesh.setMatrixAt(n++, _m2.compose(_b, _q2, new THREE.Vector3(1, 1, u < 0.1 ? 0.4 : 1)));
  }
  boltMesh.count = n;
  boltMesh.instanceMatrix.needsUpdate = true;
}

// The lair: where each city's flock sleeps, a ring of boulders round a dark mound with nests and old bones.
function buildLairs(body, R) {
  state.klyaksaLairs = [];
  const plan = state.klyaksaPlanData;
  if (!plan) return;
  const rock = material("lair-rock", 0x4a4640, { roughness: 1 }), dark = material("lair-mound", 0x2a2622, { roughness: 1 });
  const nest = material("lair-nest", 0x5e4a2e, { roughness: 1 }), bone = material("lair-bone", 0xd8d0bc, { roughness: 0.7 });
  const rockGeo = new THREE.DodecahedronGeometry(1, 0), nestGeo = new THREE.TorusGeometry(5, 1.6, 6, 14).rotateX(Math.PI / 2);
  const boneGeo = new THREE.CylinderGeometry(0.35, 0.35, 9, 5).rotateZ(Math.PI / 2), mound = new THREE.SphereGeometry(1, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2);
  const pos = new THREE.Vector3(), q = new THREE.Quaternion(), m4 = new THREE.Matrix4();
  for (const c of plan.cities) {
    if (!c.lair) continue;
    const [lx, ly] = c.lair, g = new THREE.Group();
    const rocks = new THREE.InstancedMesh(rockGeo, rock, 46), nests = new THREE.InstancedMesh(nestGeo, nest, 7), bones = new THREE.InstancedMesh(boneGeo, bone, 18);
    for (let i = 0; i < 46; i++) {
      const a = (i / 46) * Math.PI * 2, r = 70 + 18 * Math.sin(i * 2.7), s = 7 + 9 * Math.abs(Math.sin(i * 1.9));
      place(c, lx + Math.cos(a) * r, ly + Math.sin(a) * r, s * 0.4, a, R, pos, q);
      rocks.setMatrixAt(i, m4.compose(pos, q, new THREE.Vector3(s, s * (1.2 + Math.abs(Math.sin(i))), s)));
    }
    place(c, lx, ly, -6, 0, R, pos, q);
    const m = new THREE.Mesh(mound, dark);
    m.position.copy(pos); m.quaternion.copy(q); m.scale.set(48, 26, 48);
    g.add(m);
    for (let i = 0; i < 7; i++) {
      const a = (i / 7) * Math.PI * 2;
      place(c, lx + Math.cos(a) * 34, ly + Math.sin(a) * 34, 1, a, R, pos, q);
      nests.setMatrixAt(i, m4.compose(pos, q, new THREE.Vector3(1, 1, 1)));
    }
    for (let i = 0; i < 18; i++) {
      const a = i * 2.4, r = 40 + (i % 5) * 9;
      place(c, lx + Math.cos(a) * r, ly + Math.sin(a) * r, 0.4, a * 1.7, R, pos, q);
      bones.setMatrixAt(i, m4.compose(pos, q, new THREE.Vector3(1, 1, 1)));
    }
    for (const x of [rocks, nests, bones]) { x.instanceMatrix.needsUpdate = true; x.computeBoundingSphere(); g.add(x); }
    g.name = `Lair ${c.id}`;
    body.add(g);
    state.klyaksaLairs.push(g);
  }
}
