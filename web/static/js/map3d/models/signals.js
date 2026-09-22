/** models/signals: procedural colony viewer. */
import { state } from '../state.js';
import { quatAt, sph } from '../geometry/planet.js';
import { Kit } from './kit.js';
import * as THREE from 'three';
export function streetSignals() {
  // Geometry and vehicle logic consume the same junction list and phase offset.
  for (const old of state.roadSignals) for (const s of old.signals) {
    if (s.group) state.world.remove(s.group);
  }
  state.roadSignals = [];
  const batch = new Kit(state.world),
    lampData = [];
  for (const j of state.G.junctions) {
    if (j.mode === 'roundabout') continue;
    const a = j.angle * Math.PI / 180,
      q = quatAt(j.x, j.y, -a),
      base = sph(j.x, j.y, 1.1),
      signals = [];
    for (let branch = 0; branch < j.arms.length; branch++) {
      const angle = j.arms[branch] - a,
        approach = Math.abs(Math.cos(angle)) > .7 ? 0 : 1,
        sg = new THREE.Group(),
        k = new Kit(sg),
        normal = new THREE.Vector3(Math.cos(angle), 0, Math.sin(angle)),
        side = new THREE.Vector3(-Math.sin(angle), 0, Math.cos(angle));
      sg.position.copy(base.clone().add(normal.clone().multiplyScalar(13.7).addScaledVector(side, -j.width / 2 - 1).applyQuaternion(q)));
      sg.quaternion.copy(q).multiply(new THREE.Quaternion().setFromAxisAngle(state.UP, Math.PI / 2 - angle));
      sg.updateMatrixWorld(true);
      k.pipe(state.M.steel, [0, 0, 0], [0, 5.3, 0], .075);
      k.box(state.M.dark, 0, 4.6, 0, .55, 1.55, .4);
      k.box(state.M.white, 0, 4.6, -.22, .66, 1.68, .045);
      for (let i = 0; i < 3; i++) {
        k.box(state.M.dark, 0, 5.12 - i * .46, .2, .56, .055, .55);
      }
      const lights = [];
      for (let i = 0; i < 3; i++) {
        const m = new THREE.Matrix4().makeTranslation(0, 5.04 - i * .46, .23).premultiply(sg.matrixWorld),
          record = {
            m,
            color: 0x19221c,
            index: lampData.length
          };
        lampData.push(record);
        lights.push({
          material: {
            color: {
              setHex: value => {
                record.color = value;
                if (record.mesh) {
                  record.mesh.setColorAt(record.index, new THREE.Color(value));
                  record.mesh.instanceColor.needsUpdate = true;
                }
              }
            }
          }
        });
      }
      for (const [key, bucket] of k.buckets) {
        if (!batch.buckets.has(key)) batch.buckets.set(key, {
          shape: bucket.shape,
          mat: bucket.mat,
          items: []
        });
        for (const item of bucket.items) {
          item.matrix.premultiply(sg.matrixWorld);
          batch.buckets.get(key).items.push(item);
        }
      }
      signals.push({
        lights,
        approach
      });
    }
    state.roadSignals.push({
      ...j,
      signals
    });
  }
  batch.finish();
  const lamps = new THREE.InstancedMesh(new THREE.CircleGeometry(.18, 12), new THREE.MeshBasicMaterial({
    color: 0xffffff,
    side: THREE.DoubleSide
  }), lampData.length);
  lampData.forEach(r => {
    r.mesh = lamps;
    lamps.setMatrixAt(r.index, r.m);
    lamps.setColorAt(r.index, new THREE.Color(r.color));
  });
  lamps.instanceMatrix.needsUpdate = true;
  state.world.add(lamps);
}
