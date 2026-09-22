/** render/packets: procedural colony viewer. */
import { state } from '../state.js';
import { polar, sph } from '../geometry/planet.js';
import { sample } from './flows.js';
export function packetPath(pk) {
  const c = state.G.cfg,
    HR = c.hub_radius,
    WR = c.wall_radius;
  const path = [];
  if (pk.from === 'house') {
    let i = pk.id,
      p = state.G.houses.pole[i];
    path.push(...(state.houseNetDrops[i] || []).slice().reverse());
    let guard = 0;
    while (p >= 0 && guard++ < 40) {
      path.push(...state.netSpanPaths[p].slice().reverse());
      p = state.G.poles.parent[p];
    }
    const s = state.G.houses.sector[i];
    const [cx, cy] = polar(s * 60 + 4.5, HR + 20);
    path.push(sph(cx, cy, 10));
    path.push(sph(80, 33, 18));
  } else path.push(sph(80, 33, 18));
  if (pk.kind === 'reactor' || pk.kind === 'lost') {
    path.push(sph(-HR + 10, 8, 21));
    path.push(sph(-WR - 40, 8, 25));
    path.push(sph(c.reactor_pos[0] + 70, 8, 25));
    path.push(sph(c.reactor_pos[0], c.reactor_pos[1], 30));
  } else if (pk.uplink) {
    path.push(...state.spaceFiberPath);
    path.push(sph(c.dish_pos[0] + 44, c.dish_pos[1], 12));
  }
  return path;
}
export function updatePackets() {
  const now = performance.now();
  const good = [],
    bad = [];
  for (const [key, v] of state.packetsSeen) {
    const u = (now - v.t0) / 2200;
    if (u >= 1) {
      state.packetsSeen.delete(key);
      continue;
    }
    if (!v.path) {
      const pts = packetPath(v.p),
        cum = [0];
      for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + pts[i].distanceTo(pts[i - 1]));
      v.path = {
        pts,
        cum,
        len: cum.at(-1)
      };
    }
    const q = sample(v.path, u);
    (v.p.uplink || v.p.kind === 'reactor' ? good : bad).push(q);
  }
  const put = (layer, arr) => {
    const a = layer.geometry.attributes.position;
    for (let i = 0; i < a.count; i++) {
      if (i < arr.length) a.setXYZ(i, arr[i].x, arr[i].y, arr[i].z);else a.setXYZ(i, 0, -99999, 0);
    }
    a.needsUpdate = true;
  };
  put(state.packetsPts, good);
  put(state.markers.packetsRed, bad);
}
