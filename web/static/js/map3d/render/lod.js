/** render/lod: procedural colony viewer. */
import { state } from '../state.js';
import { syncMedium } from '../models/habitat.js';
import { makeHouse } from '../models/houses.js';
import * as THREE from 'three';
export function updateDetail() {
  if (!state.housesMesh || ++state.detailFrame % 10 !== 0) return;
  const near = state.houseShells.map((h, i) => [state.camera.position.distanceTo(h.base), i]).sort((a, b) => a[0] - b[0]);
  const wanted = new Set(near.filter(x => x[0] < 480).slice(0, 32).map(x => x[1]));
  if (state.selected?.kind === 'house' && state.camera.position.distanceTo(state.houseShells[state.selected.id].base) < 1000) wanted.add(state.selected.id);
  const zero = new THREE.Matrix4().makeScale(0, 0, 0);
  for (const [i, v] of state.houseDetails) {
    if (!wanted.has(i)) {
      state.world.remove(v.g);
      v.litMaterials.forEach(m => m.dispose());
      v.g.traverse(o => {
        if (o.isInstancedMesh) o.dispose();
        if (o.isSprite) {
          o.material.dispose();
        }
      });
      state.houseDetails.delete(i);
      state.housesMesh.setMatrixAt(i, state.houseShells[i].matrix);
      state.roofProxies[i].mesh.setMatrixAt(i, state.roofProxies[i].matrix);
    }
  }
  let built = 0;
  for (const i of wanted) {
    if (!state.houseDetails.has(i)) {
      if (built++ >= 2) continue;
      state.houseDetails.set(i, makeHouse(i));
      state.housesMesh.setMatrixAt(i, zero);
      state.roofProxies[i].mesh.setMatrixAt(i, zero);
    }
    const v = state.houseDetails.get(i);
    v.roof.visible = true;
    v.shell.visible = true;
    if (state.S) {
      v.litMaterials[0].emissiveIntensity = state.S.houses.power[i] ? .7 : 0;
      v.litMaterials[1].emissiveIntensity = state.S.houses.power[i] ? .6 : 0;
    }
    // The roof and complete upper storey contents share a removable group.
  }
  syncMedium(new Set(state.houseDetails.keys()));
  state.housesMesh.instanceMatrix.needsUpdate = true;
  state.roofProxies[0].mesh.instanceMatrix.needsUpdate = true;
}
