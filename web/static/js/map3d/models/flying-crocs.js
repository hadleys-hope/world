/** models/flying-crocs: the flock of flying crocodiles from /state.crocs (hadleys/domains/fauna.py). */
import { state } from '../state.js';
import { quatAt, sph } from '../geometry/planet.js';
import { clickable } from '../render/world.js';
import { material } from './materials.js';
import * as THREE from 'three';

const MAX = 40; // pool cap: the colony's seven and a raid of two dozen
const AWAY = new THREE.Vector3(0, -99999, 0); // hidden figures are parked here: the ray picker ignores `visible`
const FLYING = { inbound: 1, soar: 1, dive: 1, outbound: 1, raid: 1, migrate: 1, falling: 1 };
let shapes = null;
let wingTime = 0, lastNow = 0;

/** One geometry out of several transformed primitives (no three/addons needed). */
export function merged(parts) {
  const pos = [], nor = [];
  for (const [geometry, place] of parts) {
    const g = (geometry.index ? geometry.toNonIndexed() : geometry.clone()).applyMatrix4(place);
    pos.push(...g.attributes.position.array);
    nor.push(...g.attributes.normal.array);
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  out.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  return out;
}

function at(x, y, z, rx = 0, ry = 0, rz = 0, sx = 1, sy = 1, sz = 1) {
  return new THREE.Matrix4().compose(
    new THREE.Vector3(x, y, z),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)),
    new THREE.Vector3(sx, sy, sz),
  );
}

/** A flat membrane from the shoulder out to the tip; `side` is +1 for the right wing, -1 for the left. */
function wingShape(side) {
  const p = [[0, 0, 1.6], [6.5, 0.5, 2.6], [11.5, 0.2, -0.5], [8.2, 0, -3.4], [4.6, 0, -2.6], [2.4, 0, -4.4], [0, 0, -3.2]];
  const v = [];
  for (let i = 1; i + 1 < p.length; i++) for (const q of [p[0], p[i], p[i + 1]]) v.push(q[0] * side, q[1], q[2]);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(v, 3));
  g.computeVertexNormals();
  return g;
}

/** Geometries shared by the whole flock. Forward is local +Z, up is +Y. */
export function crocShapes() {
  if (shapes) return shapes;
  const half = Math.PI / 2;
  const body = [
    [new THREE.CapsuleGeometry(1.5, 6.2, 4, 10), at(0, 0, 0, half, 0, 0, 1.15, 1, 0.8)], // trunk
    [new THREE.BoxGeometry(2.3, 1.5, 2.8), at(0, 0.15, 5.4)], // skull
    [new THREE.BoxGeometry(1.5, 0.55, 5), at(0, 0.25, 9)], // upper jaw: the long flat snout
    [new THREE.SphereGeometry(0.42, 8, 6), at(0.85, 1.0, 5.9)], // eye ridges
    [new THREE.SphereGeometry(0.42, 8, 6), at(-0.85, 1.0, 5.9)],
  ];
  for (let k = 0; k < 6; k++) body.push([new THREE.ConeGeometry(0.42, 0.9, 4), at(0, 1.45, 3.2 - k * 1.25)]); // back scutes
  for (const [sx, sz] of [[1.6, 2.6], [-1.6, 2.6], [1.6, -2.4], [-1.6, -2.4]])
    body.push([new THREE.CylinderGeometry(0.42, 0.3, 2.2, 6), at(sx, -1.1, sz, 0, 0, sx > 0 ? 0.55 : -0.55)]); // legs tucked under
  shapes = {
    body: merged(body),
    jaw: merged([[new THREE.BoxGeometry(1.3, 0.4, 4.7), at(0, -0.2, 2.5)]]), // hinge at the pivot origin
    tail: merged([
      [new THREE.ConeGeometry(1.25, 9.5, 8), at(0, 0, -4.75, -half, 0, 0, 1, 1, 0.75)],
      [new THREE.ConeGeometry(0.34, 0.8, 4), at(0, 0.75, -2.2)],
      [new THREE.ConeGeometry(0.28, 0.7, 4), at(0, 0.6, -3.8)],
    ]),
    wingR: wingShape(1),
    wingL: wingShape(-1),
  };
  return shapes;
}

/** Where every moving part should be for a state; `w` is wing-beat time in seconds, `k` the individual. */
export function crocPose(what, w, k = 0) {
  const ph = k * 1.7;
  if (what === 'attack') {
    // on its target: wings half open for balance, jaws snapping, tail thrashing
    return { flap: 0.6, sweep: 0.9, pitch: 0.25, bank: 0, jaw: 0.35 + 0.3 * Math.sin(w * 7 + ph), tail: 0.35 * Math.sin(w * 4 + ph) };
  }
  if (!FLYING[what]) {
    // on the ground or on a roof: wings folded back along the body, a slow yawn while basking
    return {
      flap: 0.4, sweep: 1.32, pitch: 0, bank: 0,
      jaw: what === 'bask' ? 0.3 + 0.22 * Math.sin(w * 0.8 + ph) : 0.04,
      tail: 0.1 * Math.sin(w * 0.9 + ph),
    };
  }
  const beat = what === 'soar' ? 2.2 : 5.2, reach = what === 'soar' ? 0.26 : what === 'dive' ? 0.12 : 0.5;
  return {
    flap: 0.1 + reach * Math.sin(w * beat + ph),
    sweep: what === 'dive' ? 0.75 : 0,
    pitch: what === 'dive' ? 0.45 : 0,
    bank: what === 'soar' ? 0.3 : 0,
    jaw: 0.05,
    tail: 0.24 * Math.sin(w * 2.1 + ph),
  };
}

function figure(k) {
  const s = crocShapes();
  const hide = material('croc-hide', 0x4c6a3a, { roughness: 0.9 });
  const skin = material('croc-wing', 0x6f8647, { roughness: 0.95, side: THREE.DoubleSide });
  const wild = material('croc-wild', 0x5a3a2a, { roughness: 0.85 }); // the raiders: rust-brown sea-cliff crocodiles
  const wildSkin = material('croc-wild-wing', 0x7a4a34, { roughness: 0.9, side: THREE.DoubleSide });
  const g = new THREE.Group(), rig = new THREE.Group();
  g.add(rig);
  rig.add(new THREE.Mesh(s.body, hide));
  const part = (geometry, mat, x, y, z) => {
    const pivot = new THREE.Group();
    pivot.position.set(x, y, z);
    pivot.add(new THREE.Mesh(geometry, mat));
    rig.add(pivot);
    return pivot;
  };
  const jaw = part(s.jaw, hide, 0, -0.25, 6.6), tail = part(s.tail, hide, 0, 0, -3.6);
  const wingR = part(s.wingR, skin, 1.5, 0.9, 0.8), wingL = part(s.wingL, skin, -1.5, 0.9, 0.8);
  g.position.copy(AWAY);
  g.visible = false;
  state.world.add(g);
  clickable(g, 'croc:' + k, 'croc', k);
  const meshes = [];
  g.traverse((o) => o.isMesh && meshes.push(o));
  const paint = (isWild) => meshes.forEach((o) => (o.material = o.material.side === THREE.DoubleSide ? (isWild ? wildSkin : skin) : isWild ? wild : hide));
  return { g, rig, jaw, tail, wingR, wingL, paint, wild: false, from: null, to: null, q: null, t0: 0, id: null, state: 'roost', turn: 1 };
}

/** Per /state poll: one pooled figure per crocodile, with the next interpolation target. */
export function syncFlyingCrocs(s, now, first) {
  const rows = s.crocs || [], pool = state.crocPool;
  if (!pool || !state.world) return;
  const show = state.layers.fauna !== false;
  rows.slice(0, MAX).forEach((c, k) => {
    const p = pool[k] || (pool[k] = figure(k));
    const to = sph(c.x, c.y, c.z);
    const q = quatAt(c.x, c.y, -c.heading + Math.PI / 2);
    if (first || p.id !== c.id || !p.to) {
      p.g.position.copy(to);
      p.g.quaternion.copy(q);
    }
    p.from = p.g.position.clone();
    // a soaring crocodile leans into its circle: the heading runs clockwise or anticlockwise round the hub
    p.turn = Math.sin(c.heading - Math.atan2(c.y, c.x)) >= 0 ? 1 : -1;
    Object.assign(p, { to, q, t0: now, id: c.id, state: c.state });
    if (!!c.wild !== p.wild) { p.wild = !!c.wild; p.paint(p.wild); p.g.scale.setScalar(p.wild ? 1.25 : 1); }
    p.g.visible = show;
  });
  for (let k = rows.length; k < pool.length; k++) {
    const p = pool[k];
    p.g.visible = false;
    p.g.position.copy(AWAY);
    p.id = p.to = null;
  }
}

/** Layer checkbox: takes effect at once, without waiting for the next poll. */
export function showFlyingCrocs(on) {
  for (const p of state.crocPool || []) p.g.visible = on && p.id !== null;
}

/** Per frame: glide between the polled positions and move wings, jaw and tail. */
export function updateFlyingCrocs(now) {
  const pool = state.crocPool;
  if (!pool || !pool.length) return;
  const dt = Math.min(0.1, Math.max(0, (now - (lastNow || now)) / 1000));
  lastNow = now;
  if (!(state.S && state.S.paused)) wingTime += dt; // a paused colony holds its crocodiles still in the air
  const ease = 1 - Math.exp(-dt * 8);
  pool.forEach((p, k) => {
    if (!p.to) return;
    const u = Math.min(1, (now - p.t0) / Math.max(200, state.pollGap || 300));
    p.g.position.lerpVectors(p.from, p.to, u);
    p.g.quaternion.slerp(p.q, ease);
    const pose = crocPose(p.state, wingTime, k);
    const toward = (object, axis, value) => { object.rotation[axis] += (value - object.rotation[axis]) * ease; };
    toward(p.wingR, 'z', pose.flap);
    toward(p.wingL, 'z', -pose.flap);
    toward(p.wingR, 'y', pose.sweep);
    toward(p.wingL, 'y', -pose.sweep);
    toward(p.jaw, 'x', pose.jaw);
    toward(p.tail, 'y', pose.tail);
    toward(p.rig, 'x', pose.pitch);
    toward(p.rig, 'z', pose.bank * p.turn);
  });
}
