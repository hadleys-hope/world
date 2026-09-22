/** geometry/remote-terrain: procedural colony viewer. */
import { state } from "../state.js";
import {
  normalXY,
  xyNormal,
  quatAt,
  surfaceHeight,
} from "../geometry/planet.js";

import * as THREE from "three";

export function updateRemoteTerrain(d) {
  if (Math.hypot(d.x, d.y) < 4250) {
    if (state.remoteTerrain) state.remoteTerrain.visible = false;
    return;
  }
  if (
    state.remoteTerrainAt &&
    Math.hypot(d.x - state.remoteTerrainAt[0], d.y - state.remoteTerrainAt[1]) <
      35
  ) {
    state.remoteTerrain.visible = true;
    return;
  }
  if (!state.remoteTerrain) {
    state.remoteTerrain = new THREE.Mesh(
      new THREE.BufferGeometry(),
      new THREE.MeshStandardMaterial({
        color: 0x899080,
        roughness: 0.94,
        side: THREE.DoubleSide,
      }),
    );
    state.world.add(state.remoteTerrain);
  }
  const q = quatAt(d.x, d.y),
    n = xyNormal(d.x, d.y),
    pos = [],
    idx = [],
    N = 64,
    step = 7;
  for (let z = 0; z <= N; z++)
    for (let x = 0; x <= N; x++) {
      const normal = n
          .clone()
          .multiplyScalar(state.RP)
          .add(
            new THREE.Vector3(
              (x - N / 2) * step,
              0,
              (z - N / 2) * step,
            ).applyQuaternion(q),
          )
          .normalize(),
        xy = normalXY(normal),
        p = normal.multiplyScalar(
          state.RP + Math.max(-10, surfaceHeight(...xy)) + 0.01,
        );
      pos.push(p.x, p.y, p.z);
      if (x < N && z < N) {
        const a = z * (N + 1) + x;
        idx.push(a, a + N + 1, a + 1, a + 1, a + N + 1, a + N + 2);
      }
    }
  state.remoteTerrain.geometry.dispose();
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geom.setIndex(idx);
  geom.computeVertexNormals();
  state.remoteTerrain.geometry = geom;
  state.remoteTerrain.visible = true;
  state.remoteTerrainAt = [d.x, d.y];
}

export function initialize() {
  state.remoteTerrain = null;
  state.remoteTerrainAt = null;
}
