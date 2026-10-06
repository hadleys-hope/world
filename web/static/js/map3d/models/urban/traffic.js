/** Road-space presentation. Domain positions are never interpolated through buildings.
 * Distances/speeds here are metres and real seconds; simulation jobs remain server-owned. */
import * as T from "three";
import { state } from "../../state.js";
const caches = new WeakMap();
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const length = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);
const key = (p) => `${Math.round(p[0] * 100)},${Math.round(p[1] * 100)}`;
export function roadNetwork(city) {
  if (caches.has(city)) return caches.get(city);
  const nodes = new Map(),
    edges = [],
    node = (p) => {
      const k = key(p);
      if (!nodes.has(k)) nodes.set(k, { id: k, point: p, edges: [] });
      return nodes.get(k);
    };
  for (const road of [...(city.roads || []), ...(city.service_roads || [])]) {
    if (road.points.length < 2) continue;
    const points = road.points,
      a = node(points[0]),
      b = node(points.at(-1)),
      distances = [0];
    for (let i = 1; i < points.length; i++)
      distances.push(distances.at(-1) + length(points[i - 1], points[i]));
    if (distances.at(-1) < 0.01) continue;
    const edge = {
      index: edges.length,
      road,
      a,
      b,
      points,
      distances,
      length: distances.at(-1),
    };
    edges.push(edge);
    a.edges.push(edge);
    b.edges.push(edge);
  }
  const network = {
    city,
    nodes,
    edges,
    junctions: [...nodes.values()].filter((n) => n.edges.length > 2),
  };
  caches.set(city, network);
  return network;
}
export function nearestRoad(network, x, y) {
  let best = null,
    bestDistance = Infinity;
  for (const edge of network.edges)
    for (let i = 1; i < edge.points.length; i++) {
      const a = edge.points[i - 1],
        b = edge.points[i],
        dx = b[0] - a[0],
        dy = b[1] - a[1],
        L2 = dx * dx + dy * dy;
      const t = clamp(((x - a[0]) * dx + (y - a[1]) * dy) / (L2 || 1), 0, 1),
        px = a[0] + dx * t,
        py = a[1] + dy * t;
      const d = (x - px) ** 2 + (y - py) ** 2;
      if (d < bestDistance) {
        bestDistance = d;
        best = {
          edge,
          distance: edge.distances[i - 1] + Math.sqrt(L2) * t,
          x: px,
          y: py,
        };
      }
    }
  return best;
}
function shortest(network, start, finish) {
  network.pathCache ||= new Map();
  const cacheKey = start.id + ":" + finish.id;
  if (network.pathCache.has(cacheKey)) return network.pathCache.get(cacheKey);
  const open = new Set([start]),
    costs = new Map([[start, 0]]),
    previous = new Map();
  while (open.size) {
    let current = null,
      min = Infinity;
    for (const n of open)
      if (costs.get(n) < min) {
        current = n;
        min = costs.get(n);
      }
    open.delete(current);
    if (current === finish) break;
    for (const edge of current.edges) {
      const other = edge.a === current ? edge.b : edge.a,
        cost = min + edge.length;
      if (cost < (costs.get(other) ?? Infinity)) {
        costs.set(other, cost);
        previous.set(other, { node: current, edge });
        open.add(other);
      }
    }
  }
  if (!costs.has(finish)) return null;
  const path = [];
  let n = finish;
  while (n !== start) {
    const p = previous.get(n);
    path.push({ edge: p.edge, reverse: p.edge.b === p.node });
    n = p.node;
  }
  const result = { path: path.reverse(), length: costs.get(finish) };
  if (network.pathCache.size >= 2048)
    network.pathCache.delete(network.pathCache.keys().next().value);
  network.pathCache.set(cacheKey, result);
  return result;
}
/** Ordered edge intervals, not a Cartesian chord. Handles same-edge and disconnected targets. */
export function routeBetween(network, from, to) {
  if (!from || !to) return [];
  let result =
    from.edge === to.edge
      ? [{ edge: from.edge, start: from.distance, end: to.distance }]
      : null;
  let best = result ? Math.abs(to.distance - from.distance) : Infinity;
  for (const start of [from.edge.a, from.edge.b])
    for (const end of [to.edge.a, to.edge.b]) {
      const middle = shortest(network, start, end);
      if (!middle) continue;
      const s = start === from.edge.a ? 0 : from.edge.length,
        e = end === to.edge.a ? 0 : to.edge.length;
      const total =
        Math.abs(s - from.distance) + middle.length + Math.abs(e - to.distance);
      if (total >= best) continue;
      best = total;
      result = [
        { edge: from.edge, start: from.distance, end: s },
        ...middle.path.map((p) => ({
          edge: p.edge,
          start: p.reverse ? p.edge.length : 0,
          end: p.reverse ? 0 : p.edge.length,
        })),
        { edge: to.edge, start: e, end: to.distance },
      ];
    }
  return (result || []).filter((p) => Math.abs(p.end - p.start) > 0.001);
}
export function sampleRoad(edge, distance, reverse = false, lane = true) {
  distance = clamp(distance, 0, edge.length);
  let i = 1;
  while (i < edge.distances.length - 1 && edge.distances[i] < distance) i++;
  const a = edge.points[i - 1],
    b = edge.points[i],
    L = edge.distances[i] - edge.distances[i - 1],
    t = (distance - edge.distances[i - 1]) / (L || 1),
    sign = reverse ? -1 : 1;
  const dx = ((b[0] - a[0]) / (L || 1)) * sign,
    dy = ((b[1] - a[1]) / (L || 1)) * sign;
  // Right lane in planar x/y; merge to centre inside junction for a continuous turn.
  const taper = clamp(Math.min(distance, edge.length - distance) / 13, 0, 1),
    offset = lane ? Math.min(2.1, edge.road.width * 0.23) * taper : 0;
  return {
    x: a[0] + (b[0] - a[0]) * t + dy * offset,
    y: a[1] + (b[1] - a[1]) * t - dx * offset,
    heading: Math.atan2(dy, dx),
    edge,
    distance,
  };
}
export function trafficStopOffset(node) {
  return Math.max(...node.edges.map((e) => e.road.width)) * 0.62 + 6.5;
}
export function signalPhase(node, heading, seconds) {
  // Opposing approaches share a green; both axes get an all-red clearance.
  const axis =
    Math.abs(Math.cos(heading)) >= Math.abs(Math.sin(heading)) ? 0 : 1;
  const offset =
    (((Math.round(node.point[0]) * 7 + Math.round(node.point[1]) * 13) % 19) +
      19) %
    19;
  const t = ((((seconds + offset) % 44) + 44) % 44) - axis * 22;
  return t >= 0 && t < 17 ? "green" : t >= 17 && t < 20 ? "amber" : "red";
}
export function createVehicle(network, target, seed = 0) {
  const anchor = nearestRoad(network, target.x, target.y);
  if (!anchor) return null;
  return {
    network,
    anchor,
    route: [],
    speed: 0,
    gear: 1,
    rpm: 850,
    throttle: 0,
    target: anchor,
    pose: sampleRoad(anchor.edge, anchor.distance),
    seed,
    wheelAngle: 0,
  };
}
export function retargetVehicle(vehicle, target) {
  const to = nearestRoad(vehicle.network, target.x, target.y);
  if (!to) return;
  if (
    vehicle.target &&
    to.edge === vehicle.target.edge &&
    Math.abs(to.distance - vehicle.target.distance) < 6 &&
    vehicle.route.length
  )
    return;
  const route = routeBetween(vehicle.network, vehicle.anchor, to);
  if (route.length) {
    vehicle.route = route;
    vehicle.target = to;
    vehicle.previousLeg = null;
  }
}
function junctionPose(v) {
  const current = v.route[0];
  if (!current) return v.pose;
  const reversed = current.end < current.start,
    left = Math.abs(current.end - v.anchor.distance),
    travel = Math.abs(v.anchor.distance - current.start),
    radius = 12;
  let before, after, t;
  if (left < radius && v.route[1]) {
    before = current;
    after = v.route[1];
    t = (radius - left) / (2 * radius);
  } else if (travel < radius && v.previousLeg) {
    before = v.previousLeg;
    after = current;
    t = 0.5 + travel / (2 * radius);
  } else return v.pose;
  const beforeSign = before.end >= before.start ? 1 : -1,
    afterSign = after.end >= after.start ? 1 : -1;
  // Only joins at a shared node can receive a turn arc, never an arbitrary mission retarget.
  const A = sampleRoad(
      before.edge,
      before.end - beforeSign * radius,
      beforeSign < 0,
    ),
    B = sampleRoad(before.edge, before.end, beforeSign < 0, false),
    C = sampleRoad(after.edge, after.start + afterSign * radius, afterSign < 0),
    D = sampleRoad(after.edge, after.start, afterSign < 0, false);
  if (Math.hypot(B.x - D.x, B.y - D.y) > 0.01) return v.pose;
  const u = 1 - t,
    dx = 2 * u * (B.x - A.x) + 2 * t * (C.x - B.x),
    dy = 2 * u * (B.y - A.y) + 2 * t * (C.y - B.y);
  return {
    ...v.pose,
    x: u * u * A.x + 2 * u * t * B.x + t * t * C.x,
    y: u * u * A.y + 2 * u * t * B.y + t * t * C.y,
    heading: Math.atan2(dy, dx),
  };
}
export function advanceVehicle(v, dt, seconds, moving = true) {
  // Integrate with bounded substeps: an unfocused tab cannot teleport a car across a block.
  let remaining = Math.min(0.15, Math.max(0, dt));
  while (remaining > 1e-6) {
    const h = Math.min(1 / 60, remaining);
    remaining -= h;
    const leg = v.route[0];
    let desired = moving && leg ? 10.5 + (v.seed % 4) : 0,
      stopBarrier = Infinity;
    desired = Math.min(desired, v.followSpeed ?? Infinity);
    if (leg) {
      const reverse = leg.end < leg.start,
        left = Math.abs(leg.end - v.anchor.distance),
        node = reverse ? leg.edge.a : leg.edge.b;
      const approachingNode =
        Math.abs(leg.end - (reverse ? 0 : leg.edge.length)) < 0.01;
      const red =
        approachingNode &&
        node.edges.length > 2 &&
        signalPhase(node, v.pose.heading, seconds) !== "green";
      const available = red
        ? Math.max(0, left - trafficStopOffset(node))
        : v.route.length === 1
          ? left
          : Infinity;
      if (red) stopBarrier = available;
      desired = Math.min(
        desired,
        Math.sqrt(2 * 4.5 * Math.max(0, available - 0.5)),
      );
      if (left < 15 && v.route.length > 1) desired = Math.min(desired, 5);
      if (red && available < 0.7) desired = 0;
    }
    const ratios = [0, 3.6, 2.1, 1.4, 1.05, 0.82],
      roadRpm = ((v.speed / 0.34) * 60) / (2 * Math.PI),
      ratio = ratios[v.gear] * 3.9;
    v.rpm = Math.max(850, roadRpm * ratio);
    if (v.rpm > 3300 && v.gear < 5) v.gear++;
    if (v.rpm < 1200 && v.gear > 1) v.gear--;
    v.throttle = clamp((desired - v.speed) / 2.8, 0, 1);
    const engineForce =
      ((190 * ratios[v.gear] * 3.9 * 0.86) / 0.34) * v.throttle;
    const drag = 0.5 * 1.225 * 0.34 * 2.5 * v.speed * v.speed,
      rolling = 1450 * 9.81 * 0.014;
    const acceleration =
      desired < v.speed
        ? Math.max(-4.5, (desired - v.speed) * 2.5)
        : Math.min(2.8, (engineForce - drag - rolling) / 1450);
    v.speed = Math.max(0, v.speed + acceleration * h);
    if (!leg) continue;
    let distance = Math.min(
      v.speed * h,
      Math.max(0, stopBarrier - 0.05),
      Math.max(0, v.followGap ?? Infinity),
    );
    if (distance < 0.001 && Number.isFinite(stopBarrier)) v.speed = 0;
    while (distance > 0 && v.route.length) {
      const p = v.route[0],
        sign = p.end >= p.start ? 1 : -1,
        left = Math.abs(p.end - v.anchor.distance),
        step = Math.min(left, distance);
      v.anchor = { edge: p.edge, distance: v.anchor.distance + sign * step };
      distance -= step;
      v.pose = sampleRoad(p.edge, v.anchor.distance, sign < 0);
      if (left - step < 0.001) {
        v.previousLeg = v.route.shift();
        if (v.route[0])
          v.anchor = { edge: v.route[0].edge, distance: v.route[0].start };
        else v.speed = 0;
      } else break;
    }
    v.wheelAngle += (v.speed * h) / 0.34;
  }
  v.pose = junctionPose(v);
  return v.pose;
}
export function registerTrafficSignals(body, specs) {
  if (!specs.length) return;
  const mesh = new T.InstancedMesh(
      new T.SphereGeometry(0.115, 7, 5),
      new T.MeshBasicMaterial({ color: 0xffffff }),
      specs.length * 3,
    ),
    matrix = new T.Matrix4();
  specs.forEach((s, i) =>
    s.positions.forEach((p, k) => {
      matrix.makeTranslation(...p.toArray());
      mesh.setMatrixAt(i * 3 + k, matrix);
    }),
  );
  mesh.instanceMatrix.needsUpdate = true;
  mesh.computeBoundingSphere();
  body.add(mesh);
  (state.klyaksaSignals ||= []).push({ mesh, specs, phase: -1 });
}
export function updateTrafficSignals(seconds) {
  for (const group of state.klyaksaSignals || []) {
    if (group.phase === Math.floor(seconds * 4)) continue;
    group.phase = Math.floor(seconds * 4);
    group.specs.forEach((s, i) => {
      const active = signalPhase(s.node, s.heading, seconds),
        colors = [0xff493d, 0xffb930, 0x50f79a];
      ["red", "amber", "green"].forEach((phase, k) =>
        group.mesh.setColorAt(
          i * 3 + k,
          new T.Color(phase === active ? colors[k] : 0x192327),
        ),
      );
    });
    if (group.mesh.instanceColor) group.mesh.instanceColor.needsUpdate = true;
  }
}
