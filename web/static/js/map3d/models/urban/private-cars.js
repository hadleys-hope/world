/** urban/private-cars: the colonists' own cars on every Klyaksa city's roads, driving in the right-hand lane,
 * turning onto connected roads at junctions. A dozen body styles (car-models.js); head- and tail-lights are
 * their own glowing instances, and after dark every car throws a beam of light ahead of it. */
import { state } from "../../state.js";
import { PLATEAU } from "../../geometry/noise.js";
import { dirAt } from "../klyaksa.js";
import { carStyle, PAINT, STYLES } from "./car-models.js";
import { roadElevation } from "./streets.js";
import * as T from "three";

const _n = new T.Vector3(), _e = new T.Vector3(), _no = new T.Vector3(), _f = new T.Vector3(), _r = new T.Vector3();
const _m = new T.Matrix4(), _q = new T.Quaternion(), _one = new T.Vector3(1, 1, 1);

function frame(R, x, y, heading, h) {
  _n.copy(dirAt(x, y, R));
  _e.copy(dirAt(x + 1, y, R)).sub(_n).normalize();
  _no.copy(dirAt(x, y + 1, R)).sub(_n).normalize();
  _f.copy(_e).multiplyScalar(Math.cos(heading)).addScaledVector(_no, Math.sin(heading)).normalize();
  _r.crossVectors(_n, _f).normalize();
  _f.crossVectors(_r, _n);
  _q.setFromRotationMatrix(_m.makeBasis(_r, _n, _f));
  return _n.multiplyScalar(R + R * PLATEAU + 0.25 + h);
}

export function buildPrivateCars(body, R, plan) {
  const roads = [], cars = [];
  let seed = 11;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (const c of plan.cities) {
    const mine = [];
    for (const road of c.roads || []) {
      const pts = road.points.map(([x, y]) => [c.at[0] + x, c.at[1] + y]);
      if (pts.length < 2) continue;
      const cum = [0];
      for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
      if (cum.at(-1) < 20) continue;
      const r = { pts, cum, len: cum.at(-1), width: road.width || 10, next: [[], []], city: c, plan: road };
      roads.push(r); mine.push(r);
    }
    // junctions: road ends within 6 m of each other connect
    const key = (p) => `${Math.round(p[0] / 6)},${Math.round(p[1] / 6)}`;
    const ends = new Map();
    for (const r of mine) for (const end of [0, 1]) {
      const k = key(end ? r.pts.at(-1) : r.pts[0]);
      if (!ends.has(k)) ends.set(k, []);
      ends.get(k).push([r, end]);
    }
    for (const r of mine) for (const end of [0, 1]) r.next[end] = (ends.get(key(end ? r.pts.at(-1) : r.pts[0])) || []).filter(([o]) => o !== r);
    const n = Math.min(260, Math.round(c.houses / 6));
    for (let k = 0; k < n && mine.length; k++) {
      const r = mine[Math.floor(rnd() * mine.length)];
      cars.push({ road: r, s: rnd() * r.len, dir: rnd() < 0.5 ? 1 : -1, speed: 9 + rnd() * 8, style: Math.floor(rnd() * STYLES.length), paint: Math.floor(rnd() * PAINT.length) });
    }
  }
  // one batch per body style, painted per car; one batch each for headlamps, tail-lamps and the beams
  const byStyle = STYLES.map(() => []);
  cars.forEach((car) => { car.slot = byStyle[car.style].length; byStyle[car.style].push(car); });
  const body3 = (geo, mat, n) => { const m = new T.InstancedMesh(geo, mat, Math.max(1, n)); m.frustumCulled = false; m.instanceMatrix.setUsage(T.DynamicDrawUsage); body.add(m); return m; };
  const batches = byStyle.map((list, k) => {
    const g = carStyle(k);
    g.setAttribute("color", g.getAttribute("aCol"));
    const m = body3(g, new T.MeshStandardMaterial({ vertexColors: true, roughness: 0.35, metalness: 0.55 }), list.length);
    list.forEach((car, i) => m.setColorAt(i, new T.Color(PAINT[car.paint])));
    return m;
  });
  const lamps = (z, w) => { const g = new T.BoxGeometry(0.42, 0.18, 0.06); return [g.clone().translate(-w, 0.75, z), g.clone().translate(w, 0.75, z)]; };
  const pair = (gs) => { const out = new T.BufferGeometry(); out.setAttribute("position", new T.Float32BufferAttribute(gs.flatMap((g) => [...g.toNonIndexed().attributes.position.array]), 3)); return out; };
  const head = body3(pair(lamps(2.48, 0.62)), new T.MeshBasicMaterial({ color: 0xfff4d6 }), cars.length);
  const tail = body3(pair(lamps(-2.48, 0.62)), new T.MeshBasicMaterial({ color: 0xff2a1a }), cars.length);
  // the beam: two cones from the lamps, brightest at the glass and fading with distance and towards the edge;
  // the pool: an ellipse of light on the road ahead, strongest a few metres out
  const beamShader = (pool) => new T.ShaderMaterial({
    transparent: true, depthWrite: false, blending: T.AdditiveBlending, side: T.DoubleSide,
    uniforms: { uNight: { value: 0 } },
    vertexShader: `varying vec3 vL; void main() { vL = position; vec4 p = vec4(position, 1.0);
      #ifdef USE_INSTANCING
      p = instanceMatrix * p;
      #endif
      gl_Position = projectionMatrix * modelViewMatrix * p; }`,
    fragmentShader: pool
      ? `uniform float uNight; varying vec3 vL; void main() { vec2 q = vec2(vL.x / 4.2, (vL.z - 10.0) / 9.0); float d = dot(q, q);
           float a = (1.0 - smoothstep(0.0, 1.0, d)) * smoothstep(2.0, 6.0, vL.z) * 0.55 * uNight; gl_FragColor = vec4(vec3(1.0, 0.93, 0.78) * a, a); }`
      : `uniform float uNight; varying vec3 vL; void main() { float along = clamp((vL.z - 2.4) / 22.0, 0.0, 1.0); float w = 0.35 + along * 3.2;
           float side = min(abs(vL.x - 0.62), abs(vL.x + 0.62)) / w; float a = pow(1.0 - along, 1.6) * (1.0 - smoothstep(0.2, 1.0, side)) * 0.22 * uNight;
           gl_FragColor = vec4(vec3(1.0, 0.95, 0.82) * a, a); }`,
  });
  const beamGeo = new T.BufferGeometry();
  {
    const pos = [];
    for (const sx of [-0.62, 0.62]) for (let k = 0; k < 12; k++) {          // a cone per lamp, as 12 thin wedges
      const a0 = (k / 12) * Math.PI * 2, a1 = ((k + 1) / 12) * Math.PI * 2, r0 = 0.25, r1 = 3.6, z0 = 2.4, z1 = 24;
      const P0 = [sx + Math.cos(a0) * r0, 0.72 + Math.sin(a0) * r0 * 0.6, z0], P1 = [sx + Math.cos(a1) * r0, 0.72 + Math.sin(a1) * r0 * 0.6, z0];
      const Q0 = [sx + Math.cos(a0) * r1, 0.72 + Math.sin(a0) * r1 * 0.35 - 0.5, z1], Q1 = [sx + Math.cos(a1) * r1, 0.72 + Math.sin(a1) * r1 * 0.35 - 0.5, z1];
      pos.push(...P0, ...Q0, ...P1, ...P1, ...Q0, ...Q1);
    }
    beamGeo.setAttribute("position", new T.Float32BufferAttribute(pos, 3));
  }
  const beams = body3(beamGeo, beamShader(false), cars.length);
  const pools = body3(new T.PlaneGeometry(9, 20, 1, 1).rotateX(-Math.PI / 2).translate(0, 0.08, 10), beamShader(true), cars.length);
  return { R, cars, batches, byStyle, head, tail, beams, pools };
}

function at(road, s) {
  let i = 1;
  while (i < road.cum.length - 1 && road.cum[i] < s) i++;
  const a = road.pts[i - 1], b = road.pts[i], u = (s - road.cum[i - 1]) / Math.max(1e-6, road.cum[i] - road.cum[i - 1]);
  return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, Math.atan2(b[1] - a[1], b[0] - a[0])];
}

export function updatePrivateCars(pc, dt) {
  if (!pc) return;
  const night = state.klyaksaNight ?? 0, R = pc.R;
  pc.beams.visible = pc.pools.visible = night > 0.05;
  pc.beams.material.uniforms.uNight.value = pc.pools.material.uniforms.uNight.value = night;
  pc.head.material.color.setScalar(0.55 + 0.45 * night).multiply(new T.Color(0xfff4d6));
  pc.cars.forEach((car, i) => {
    car.s += car.dir * car.speed * dt;
    if (car.s < 0 || car.s > car.road.len) {
      const end = car.s > car.road.len ? 1 : 0, options = car.road.next[end].filter(([r]) => !state.meridianStops?.has(r.plan.id));
      if (options.length) {
        const [r, e] = options[Math.floor(Math.random() * options.length)];
        car.road = r; car.dir = e === 0 ? 1 : -1; car.s = e === 0 ? 0 : r.len;
      } else { car.dir = -car.dir; car.s = Math.max(0, Math.min(car.road.len, car.s)); }
    }
    const [x0, y0, h0] = at(car.road, car.s), heading = car.dir > 0 ? h0 : h0 + Math.PI;
    const lane = Math.min(car.road.width / 4, 2.6);                      // keep right
    const x = x0 + Math.sin(heading) * lane, y = y0 - Math.cos(heading) * lane;
    const lift = roadElevation(car.road.city, car.road.plan, x - car.road.city.at[0], y - car.road.city.at[1]) || 0;   // up onto the bridges
    const pos = frame(R, x, y, heading, lift);
    _m.compose(pos, _q, _one);
    pc.batches[car.style].setMatrixAt(car.slot, _m);
    pc.head.setMatrixAt(i, _m); pc.tail.setMatrixAt(i, _m); pc.beams.setMatrixAt(i, _m); pc.pools.setMatrixAt(i, _m);
  });
  for (const m of [...pc.batches, pc.head, pc.tail, pc.beams, pc.pools]) m.instanceMatrix.needsUpdate = true;
}
