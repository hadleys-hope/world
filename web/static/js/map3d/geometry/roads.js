/** geometry/roads: procedural colony viewer. */
import { state } from '../state.js';
import { Kit } from '../models/kit.js';
import { addLabel } from '../render/world.js';
import { arcPts, polar, quatAt, sph, subdiv } from './planet.js';
import { cap, ribbon } from './primitives.js';
import * as THREE from 'three';
export function indexRoads() {
  state.roadIndex.clear();
  state.roadSegments = [];
  for (const r of state.G.layout.roads) for (let i = 1; i < r.points.length; i++) {
    const a = r.points[i - 1],
      b = r.points[i],
      v = {
        a,
        b,
        w: r.width,
        id: r.id
      };
    state.roadSegments.push(v);
    const pad = r.width / 2 + 7;
    for (let x = Math.floor((Math.min(a[0], b[0]) - pad) / 32); x <= Math.floor((Math.max(a[0], b[0]) + pad) / 32); x++) for (let y = Math.floor((Math.min(a[1], b[1]) - pad) / 32); y <= Math.floor((Math.max(a[1], b[1]) + pad) / 32); y++) {
      const key = x + ',' + y;
      if (!state.roadIndex.has(key)) state.roadIndex.set(key, []);
      state.roadIndex.get(key).push(v);
    }
  }
}
export function segmentDistance(x, y, a, b) {
  const dx = b[0] - a[0],
    dy = b[1] - a[1],
    t = THREE.MathUtils.clamp(((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy || 1), 0, 1);
  return Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy);
}
export function onRoad(x, y, margin = 0, ignore = null) {
  for (const q of state.G.layout.roundabouts) {
    const d = Math.hypot(x - q.x, y - q.y);
    if (d < q.outer + margin) return d > 8.6 - margin;
  }
  return (state.roadIndex.get(Math.floor(x / 32) + ',' + Math.floor(y / 32)) || []).some(s => s.id !== ignore && segmentDistance(x, y, s.a, s.b) < s.w / 2 + margin);
}
export function raisedWalk(flat, width = 2.8) {
  const points = subdiv(flat, 1.7),
    kit = new Kit(state.streetDetail);
  let run = [];
  const flush = () => {
    if (run.length > 1) ribbon(run, width, 1.25, 0xa2a597, {
      map: state.pavingTexture,
      bumpMap: state.pavingTexture,
      bumpScale: .018
    });
    run = [];
  };
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1],
      b = points[i],
      dx = b[0] - a[0],
      dy = b[1] - a[1],
      L = Math.hypot(dx, dy);
    if (!L) continue;
    const x = (a[0] + b[0]) / 2,
      y = (a[1] + b[1]) / 2,
      nx = -dy / L,
      ny = dx / L;
    if (onRoad(x, y, width * .52 + .1) || state.G.layout.roundabouts.some(q => Math.hypot(x - q.x, y - q.y) < q.outer + width)) {
      flush();
      continue;
    }
    if (!run.length) run.push(a);
    run.push(b);
    for (const side of [-1, 1]) {
      const xx = x + nx * side * width / 2,
        yy = y + ny * side * width / 2;
      kit.add('box', state.M.concrete, sph(xx, yy, 1.12).toArray(), [L + .03, .26, .19], quatAt(xx, yy, -Math.atan2(dy, dx)));
    }
  }
  flush();
  kit.finish();
}
export function drawRoadSurface(flat, width, h) {
  const pts = subdiv(flat, 2),
    parts = [];
  let run = [];
  for (const p of pts) {
    if (state.G.layout.roundabouts.some(q => Math.hypot(p[0] - q.x, p[1] - q.y) < 14.8)) {
      if (run.length > 1) parts.push(run);
      run = [];
    } else run.push(p);
  }
  if (run.length > 1) parts.push(run);
  const meshes = [];
  for (const path of parts) {
    ribbon(path, width + 1.1, h - .12, 0x777970);
    const m = ribbon(path, width, h, 0x454b4d, {
      roughness: .95,
      bumpMap: state.asphaltTexture,
      bumpScale: .015,
      polygonOffset: false
    });
    m.userData.road = true;
    meshes.push(m);
  }
  return meshes[0] || new THREE.Mesh(state.UNIT.box, state.M.dark);
}
export function paintStroke(kit, mat, a, b, width = .18, height = 1.13) {
  const p = sph(...a, height),
    q = sph(...b, height),
    axis = q.clone().sub(p).normalize(),
    mid = p.clone().add(q).multiplyScalar(.5),
    up = mid.clone().normalize(),
    side = axis.clone().cross(up).normalize();
  up.copy(side).cross(axis).normalize();
  kit.add('box', mat, mid.toArray(), [p.distanceTo(q) + .02, .035, width], new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(axis, up, side)));
}
export function markedRoad(flat, width, h) {
  const road = drawRoadSurface(flat, width, 1.0),
    pts = subdiv(flat, 2),
    paint = new Kit(state.world);
  let distance = 0;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1],
      b = pts[i],
      dx = b[0] - a[0],
      dy = b[1] - a[1],
      L = Math.hypot(dx, dy);
    if (!L) continue;
    const x = (a[0] + b[0]) / 2,
      y = (a[1] + b[1]) / 2,
      q = quatAt(x, y, -Math.atan2(dy, dx));
    distance += L;
    if (state.G.junctions.some(j => Math.hypot(x - j.x, y - j.y) < (j.mode === 'roundabout' ? 18 : 9.3))) continue;
    const normal = [-dy / L, dx / L];
    for (const side of [-1, 1]) {
      const off = side * (width / 2 - .35);
      paintStroke(paint, state.M.white, [a[0] + normal[0] * off, a[1] + normal[1] * off], [b[0] + normal[0] * off, b[1] + normal[1] * off], .20);
    }
    if (Math.floor(distance / 2) % 5 < 3) paintStroke(paint, state.M.amber, a, b, .22);
  }
  paint.finish();
  return road;
}
export function buildRoadNetwork() {
  indexRoads();
  for (const r of state.G.layout.roads) {
    const m = markedRoad(r.points, r.width, 1);
    m.userData.roadId = r.id;
    if (r.id.startsWith('ring-' + state.G.cfg.ring_road_radius + '-')) state.roadMeshes.ring.push(m);
  }
  const k = new Kit(state.world);
  for (const q of state.G.layout.roundabouts) {
    const ring = arcPts(0, 360, q.radius, 96).map(p => [p[0] + q.x, p[1] + q.y]);
    ribbon(ring, 8, 1.015, 0x454b4d, {
      bumpMap: state.asphaltTexture
    });
    const island = cap(8.3, 1.25, 0x818a79, 4, 40, 0, q.x, q.y);
    for (let j = 0; j < 64; j++) {
      const a = j * Math.PI / 32,
        b = (j + 1) * Math.PI / 32;
      k.pipe(state.M.concrete, sph(q.x + Math.cos(a) * 8.5, q.y + Math.sin(a) * 8.5, 1.17).toArray(), sph(q.x + Math.cos(b) * 8.5, q.y + Math.sin(b) * 8.5, 1.17).toArray(), .15);
    }
    for (let a = 0; a < 360; a += 45) {
      const [dx, dy] = polar(a, 13);
      k.add('box', state.M.white, sph(q.x + dx, q.y + dy, 1.055).toArray(), [2, .025, .15], quatAt(q.x + dx, q.y + dy, -a * Math.PI / 180 - Math.PI / 2));
    }
    const label = addLabel('ROUNDABOUT / YIELD', q.x, q.y, 3, '#c5cec0', 'near');
  }
  k.finish();
}
export function buildRoadWalks() {
  for (const r of state.G.layout.roads) {
    if (!r.walk) continue;
    const pts = subdiv(r.points, 3);
    for (const side of [-1, 1]) {
      const path = pts.map((p, i) => {
        const a = pts[Math.max(0, i - 1)],
          b = pts[Math.min(pts.length - 1, i + 1)],
          dx = b[0] - a[0],
          dy = b[1] - a[1],
          L = Math.hypot(dx, dy) || 1,
          d = side * (r.width / 2 + 1.55);
        return [p[0] - dy / L * d, p[1] + dx / L * d];
      });
      raisedWalk(path, 2.7);
    }
  }
}
export function junctionMarkings() {
  const k = new Kit(state.world);
  for (const j of state.G.junctions) {
    for (const angle of j.arms) {
      const dx = Math.cos(angle),
        dy = Math.sin(angle),
        nx = -dy,
        ny = dx;
      const stop = j.mode === 'roundabout' ? 22 : 14.2,
        half = j.width / 2;
      // Stop line is on the incoming half of the carriageway, before the zebra.
      const x = j.x + dx * stop + nx * half * .48,
        y = j.y + dy * stop + ny * half * .48;
      k.add('box', state.M.white, sph(x, y, 1.14).toArray(), [.4, .04, half - .5], quatAt(x, y, -angle));
      for (let stripe = -Math.floor(half / .85); stripe <= Math.floor(half / .85); stripe++) {
        const d = j.mode === 'roundabout' ? 19.2 : 11.2,
          xx = j.x + dx * d + nx * stripe * .82,
          yy = j.y + dy * d + ny * stripe * .82;
        if (onRoad(xx, yy, -.12)) paintStroke(k, state.M.white, [xx - dx * 1.15, yy - dy * 1.15], [xx + dx * 1.15, yy + dy * 1.15], .42, 1.14);
      }
    }
    if (j.mode === 'roundabout') continue;
    for (let i = 0; i < j.arms.length; i++) for (let n = 0; n < j.arms.length; n++) {
      if (i === n) continue;
      const a = j.arms[i],
        b = j.arms[n],
        angle = Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));
      if (angle < .6 || angle > 2.6) continue;
      const r = 8.5,
        lane = 2.2,
        A = [j.x + Math.cos(a) * r - Math.sin(a) * lane, j.y + Math.sin(a) * r + Math.cos(a) * lane],
        B = [j.x + Math.cos(b) * r + Math.sin(b) * lane, j.y + Math.sin(b) * r - Math.cos(b) * lane];
      let last = A;
      for (let t = .05; t <= 1.001; t += .05) {
        const p = [(1 - t) ** 2 * A[0] + 2 * t * (1 - t) * j.x + t * t * B[0], (1 - t) ** 2 * A[1] + 2 * t * (1 - t) * j.y + t * t * B[1]],
          x = (p[0] + last[0]) / 2,
          y = (p[1] + last[1]) / 2;
        if (Math.round(t * 20) % 3 === 0 && onRoad(x, y, -.1)) k.pipe(state.M.white, sph(...last, 1.058).toArray(), sph(...p, 1.058).toArray(), .035);
        last = p;
      }
    }
  }
  k.finish();
}
export function initialize() {
  state.roadIndex = new Map();
  state.roadSegments = [];
  state.layoutFootprints = [];
  state.externalPoleSites = [];
}
