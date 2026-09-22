/** models/neighborhood: procedural colony viewer. */
import { state } from '../state.js';
import { quatAt, sph } from '../geometry/planet.js';
import { mediumHomes } from './habitat.js';
import { Kit } from './kit.js';
import * as THREE from 'three';
export function patternTexture(kind) {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const x = c.getContext('2d');
  let seed = 814;
  const rnd = () => {
    seed = seed * 16807 % 2147483647;
    return seed / 2147483647;
  };
  x.fillStyle = kind === 'paving' ? '#494b46' : '#303637';
  x.fillRect(0, 0, 256, 256);
  if (kind === 'paving') {
    for (let row = 0; row < 16; row++) for (let col = -1; col < 8; col++) {
      const v = 155 + Math.floor(rnd() * 35);
      x.fillStyle = `rgb(${v},${v + 3},${v - 3})`;
      x.fillRect(col * 36 + row % 2 * 18 + 1, row * 16 + 1, 34, 14);
    }
  } else for (let k = 0; k < 19000; k++) {
    const v = 35 + rnd() * 45;
    x.fillStyle = `rgba(${v},${v + 3},${v + 4},.5)`;
    x.fillRect(rnd() * 256, rnd() * 256, 1, 1);
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = Math.min(8, state.renderer.capabilities.getMaxAnisotropy());
  return t;
}
export function buildNeighborhood() {
  const n = state.G.houses.x.length,
    m4 = new THREE.Matrix4();
  state.housesMesh = new THREE.InstancedMesh(state.UNIT.box, new THREE.MeshStandardMaterial({
    roughness: .8,
    transparent: true,
    opacity: 0,
    depthWrite: false
  }), n);
  state.housesMesh.castShadow = true;
  state.world.add(state.housesMesh);
  const roofs = new THREE.InstancedMesh(state.UNIT.box, state.M.steel, n);
  roofs.visible = false;
  state.world.add(roofs);
  state.windowsMesh = new THREE.InstancedMesh(state.UNIT.box, state.M.glow, 1);
  state.windowsMesh.count = 0;
  state.world.add(state.windowsMesh);
  state.windowSlots = [];
  const trim = new Kit(state.world);
  for (let i = 0; i < n; i++) {
    const x = state.G.houses.x[i],
      y = state.G.houses.y[i],
      a = state.G.houses.angle[i] * Math.PI / 180,
      [w, h, d] = state.DIM[state.G.houses.type[i]],
      yaw = -a - Math.PI / 2;
    state.flatHouses.push([x, y]);
    const q = quatAt(x, y, yaw),
      base = sph(x, y, 2.35);
    const matrix = new THREE.Matrix4().compose(base.clone().add(new THREE.Vector3(0, h / 2, 0).applyQuaternion(q)), q, new THREE.Vector3(w, h, d));
    state.housesMesh.setMatrixAt(i, matrix);
    state.housesMesh.setColorAt(i, new THREE.Color([0x898674, 0x999786, 0x7e8c85, 0xb0a48a][state.G.houses.type[i]]));
    const rm = new THREE.Matrix4().compose(base.clone().add(new THREE.Vector3(0, h + .18, 0).applyQuaternion(q)), q, new THREE.Vector3(w + .5, .36, d + .5));
    roofs.setMatrixAt(i, rm);
    state.roofProxies.push({
      mesh: roofs,
      matrix: rm
    });
    state.houseShells.push({
      matrix,
      base,
      q,
      yaw
    });
    // Silhouettes stay present at colony scale: rooftop HVAC, duct, parapet bands.
    for (const [p, scale, mat] of [[[w * .25, h + .85, -d * .15], [3.5, 1.4, 2.5], state.M.trim], [[-w * .28, h + .9, -d * .2], [.55, 1.8, .55], state.M.steel]]) {
      const pos = base.clone().add(new THREE.Vector3(...p).applyQuaternion(q));
      trim.add('box', mat, pos.toArray(), scale, q);
    }
  }
  mediumHomes();
  state.housesMesh.instanceMatrix.needsUpdate = true;
  roofs.instanceMatrix.needsUpdate = true;
}
export function initialize() {
  state.pavingTexture = patternTexture('paving');
  state.asphaltTexture = patternTexture('asphalt');
}
