/** models/external-grid: procedural colony viewer. */
import { state } from '../state.js';
import { polar, quatAt, sph } from '../geometry/planet.js';
import { onRoad, segmentDistance } from '../geometry/roads.js';
import { LineLayer, catenary } from '../render/flows.js';
import { Kit } from './kit.js';
import * as THREE from 'three';
export function buildExternalGrid() {
  const c = state.G.cfg,
    kit = new Kit(state.world),
    nodes = new Map(),
    physical = [];
  function node(x, y, h = 15.2, yaw = 0) {
    const key = [x.toFixed(4), y.toFixed(4), h.toFixed(3)].join('|');
    if (nodes.has(key)) return nodes.get(key);
    for (const n of nodes.values()) if (Math.hypot(n.x - x, n.y - y) < 7 && Math.abs(n.h - h) < 1) {
      nodes.set(key, n);
      return n;
    }
    if (onRoad(x, y, 1.2)) {
      const seg = (state.roadIndex.get(Math.floor(x / 32) + ',' + Math.floor(y / 32)) || []).sort((a, b) => segmentDistance(x, y, a.a, a.b) - segmentDistance(x, y, b.a, b.b))[0];
      if (seg) {
        const dx = seg.b[0] - seg.a[0],
          dy = seg.b[1] - seg.a[1],
          L = Math.hypot(dx, dy) || 1,
          side = Math.sign((x - seg.a[0]) * -dy + (y - seg.a[1]) * dx) || 1,
          move = seg.w / 2 + 4 - segmentDistance(x, y, seg.a, seg.b);
        x -= dy / L * side * move;
        y += dx / L * side * move;
      }
    }
    for (const n of nodes.values()) if (Math.hypot(n.x - x, n.y - y) < 7) {
      nodes.set(key, n);
      return n;
    }
    state.externalPoleSites.push({
      x,
      y,
      h
    });
    const q = quatAt(x, y, yaw),
      p = sph(x, y, h),
      n = {
        x,
        y,
        h,
        q,
        p
      };
    nodes.set(key, n);
    const base = sph(x, y, .2),
      local = (mat, pos, size) => kit.add('box', mat, base.clone().add(new THREE.Vector3(...pos).applyQuaternion(q)).toArray(), size, q);
    kit.pipe(state.M.steel, base.toArray(), p.toArray(), .22);
    local(state.M.concrete, [0, .12, 0], [.9, .24, .9]);
    local(state.M.trim, [0, h - .7, 0], [3.6, .2, .25]);
    local(state.M.steel, [.4, 2.1, 0], [.68, 1.25, .4]);
    local(state.M.screen, [.4, 2.36, .22], [.4, .22, .035]);
    local(state.M.amber, [.4, 1.85, .23], [.4, .07, .04]);
    for (let phase = -1; phase <= 1; phase++) for (let disc = 0; disc < 5; disc++) kit.add('cyl', state.M.white, p.clone().add(new THREE.Vector3(phase * 1.4, -.45 + disc * .09, 0).applyQuaternion(q)).toArray(), [.16, .055, .16], q);
    local(state.M.steel, [0, h - 2, 1], [.14, .14, 2.3]);
    local(state.M.glow, [0, h - 2.1, 2.1], [.8, .12, .4]);
    kit.pipe(state.M.trim, base.clone().add(new THREE.Vector3(.24, 0, 0).applyQuaternion(q)).toArray(), p.clone().add(new THREE.Vector3(.24, -1, 0).applyQuaternion(q)).toArray(), .018);
    return n;
  }
  const anchor = (n, phase, dh = 0) => n.p.clone().add(new THREE.Vector3(phase * 1.4, dh, 0).applyQuaternion(n.q));
  function circuit(flat) {
    const samples = [];
    for (let i = 1; i < flat.length; i++) {
      const a = flat[i - 1],
        b = flat[i],
        L = Math.hypot(b[0] - a[0], b[1] - a[1]),
        N = Math.max(1, Math.ceil(L / 42)),
        yaw = -Math.atan2(b[1] - a[1], b[0] - a[0]) + Math.PI / 2;
      for (let j = 0; j < N; j++) {
        const t = j / N;
        samples.push(node(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, (a[2] ?? 15.2) + ((b[2] ?? 15.2) - (a[2] ?? 15.2)) * t, yaw));
      }
    }
    const last = flat.at(-1);
    samples.push(node(last[0], last[1], last[2] ?? 15.2));
    const center = [],
      fiber = [];
    for (let i = 1; i < samples.length; i++) {
      const a = samples[i - 1],
        b = samples[i],
        sag = Math.min(1.8, a.p.distanceTo(b.p) * .035);
      for (let phase = -1; phase <= 1; phase++) {
        const curve = catenary(anchor(a, phase), anchor(b, phase), sag);
        physical.push(curve);
        for (let j = 1; j < curve.length; j++) kit.pipe(state.M.dark, curve[j - 1].toArray(), curve[j].toArray(), .045);
        if (!phase) center.push(curve);
      }
      const n = catenary(anchor(a, 0, -.8), anchor(b, 0, -.8), sag);
      physical.push(n);
      const f = catenary(anchor(a, 0, -2), anchor(b, 0, -2), sag);
      physical.push(f);
      fiber.push(f);
    }
    return {
      center,
      fiber
    };
  }
  const rx = c.reactor_pos[0];
  const main = circuit([[rx + 30, -88, 16.5], [rx + 76, -88, 15.2], [rx + 76, -18, 15.2], [-988, -18, 15.2], [-c.wall_radius - 40, -18, 15.2], [-164, -18, 15.2], [-110, -85, 15.2], [0, -70, 16.5]]);
  state.trunkCurves = main.center;
  state.hub.trunkLayer = new LineLayer(state.trunkCurves, 0xf2c14e);
  const mobile = circuit([[-988, -18, 15.2], [-988, c.tower_pos[1] + 105, 15.2], [-988, c.tower_pos[1] + 40, 15.2], [c.tower_pos[0] + 12, c.tower_pos[1], 12]]);
  const space = circuit([[-988, c.tower_pos[1] + 105, 15.2], [c.tower_pos[0] - 108, c.tower_pos[1] + 105, 15.2], [c.tower_pos[0] - 108, c.dish_pos[1] + 119, 15.2], [c.dish_pos[0] + 103, c.dish_pos[1] + 119, 15.2], [c.dish_pos[0] + 103, c.dish_pos[1], 15.2], [c.dish_pos[0] + 44, c.dish_pos[1], 12]]);
  state.towerCurves = [...mobile.center, ...space.center];
  state.hub.towerLayer = new LineLayer(state.towerCurves, 0xf2c14e);
  const solar = circuit([[c.solar_pos[0] + 112, c.solar_pos[1] + 10, 10], [c.solar_pos[0] + 122, c.solar_pos[1] + 10, 15.2], [c.solar_pos[0] + 122, -218, 15.2], [rx + 76, -218, 15.2], [rx + 76, -88, 15.2], [rx + 30, -88, 16.5]]);
  state.solarCurves = [solar.center.flat()];
  state.hub.solarLayer = new LineLayer(state.solarCurves, 0xf2c14e);
  // A single set of 24 regularly spaced poles supports the common cable corridor.
  const master = Array.from({
      length: 25
    }, (_, i) => [...polar(280 + i * 15, 152), 10.7]),
    backbone = circuit(master),
    entry = circuit([[0, -70, 16.5], [13, -100, 13.5], master[0]]);
  state.feederCurves = [];
  const districtFiber = [];
  for (let sector = 0; sector < c.sectors; sector++) {
    const [x, y] = state.G.layout.distribution[sector].pole,
      ring = polar(sector * 60 + 10, 152);
    node(x, y, 10.7, 0);
    const spur = circuit([[...ring, 10.7], [x, y, 10.7]]),
      arc = [];
    const end = (sector * 60 + 10 - 280 + 360) % 360,
      count = Math.round(end / 15);
    for (let j = 0; j < count; j++) arc.push(...backbone.center[j]);
    state.feederCurves.push([...entry.center.flat(), ...arc, ...spur.center.flat()]);
    districtFiber.push(...spur.fiber);
    const d = state.G.layout.distribution[sector],
      top = sph(...d.pole, 8.7),
      cabinet = sph(...d.cab, 3.9),
      link = catenary(top, sph(...d.cab, 10.7), .35);
    link.push(cabinet);
    new LineLayer([link], 0x4fd1c5);
    for (let j = 1; j < link.length; j++) kit.pipe(state.M.dark, link[j - 1].toArray(), link[j].toArray(), .026);
  }
  state.hub.feederLayer = new LineLayer(state.feederCurves, 0xf2c14e);
  const comms = circuit([[80, 33, 20], [132, 45, 15.2], [...polar(10, 152), 10.7]]);
  state.cableTowerCurves = [...main.fiber, ...mobile.fiber, ...space.fiber, ...backbone.fiber, ...entry.fiber, ...comms.fiber, ...districtFiber];
  state.hub.cableTowerLayer = new LineLayer(state.cableTowerCurves, 0x4fd1c5);
  state.externalFiber = state.cableTowerCurves;
  // Route packets over the actual connected cable graph; never jump between branches.
  const graph = new Map(),
    key = p => p.toArray().map(v => v.toFixed(3)).join(','),
    connect = (a, b, path) => {
      if (!graph.has(a)) graph.set(a, []);
      graph.get(a).push({
        to: b,
        path
      });
    };
  for (const curve of state.cableTowerCurves) {
    const a = key(curve[0]),
      b = key(curve.at(-1));
    connect(a, b, curve);
    connect(b, a, curve.slice().reverse());
  }
  const start = key(comms.fiber[0][0]),
    goal = key(space.fiber.at(-1).at(-1)),
    queue = [start],
    previous = new Map([[start, null]]);
  for (let i = 0; i < queue.length && !previous.has(goal); i++) for (const edge of graph.get(queue[i]) || []) if (!previous.has(edge.to)) {
    previous.set(edge.to, {
      from: queue[i],
      path: edge.path
    });
    queue.push(edge.to);
  }
  const paths = [];
  for (let at = goal; previous.get(at); at = previous.get(at).from) paths.unshift(previous.get(at).path);
  state.spaceFiberPath = paths.flat();
  kit.finish();
  new LineLayer(physical, 0x88958d);
}
