/** models/kit: procedural colony viewer. */
import { state } from '../state.js';
import * as THREE from 'three';
export class Kit {
  constructor(parent) {
    this.parent = parent;
    this.buckets = new Map();
  }
  add(shape, mat, p, s = [1, 1, 1], rotation = null, color = null, tag = null) {
    const key = shape + '|' + mat.uuid;
    if (!this.buckets.has(key)) this.buckets.set(key, {
      shape,
      mat,
      items: []
    });
    const q = rotation instanceof THREE.Quaternion ? rotation : new THREE.Quaternion().setFromEuler(new THREE.Euler(...(rotation || [0, 0, 0])));
    const matrix = new THREE.Matrix4().compose(new THREE.Vector3(...p), q, new THREE.Vector3(...s));
    this.buckets.get(key).items.push({
      matrix,
      color,
      tag
    });
  }
  box(mat, x, y, z, w, h, d, rot = null, col = null) {
    this.add('box', mat, [x, y, z], [w, h, d], rot, col);
  }
  pipe(mat, a, b, r, tag = null) {
    const p = new THREE.Vector3(...a),
      q = new THREE.Vector3(...b),
      delta = q.clone().sub(p);
    if (delta.length() < 1e-5) return;
    this.add('cyl', mat, p.add(q).multiplyScalar(.5).toArray(), [r, delta.length(), r], new THREE.Quaternion().setFromUnitVectors(state.UP, delta.normalize()), null, tag);
  }
  finish() {
    const meshes = [];
    for (const {
      shape,
      mat,
      items
    } of this.buckets.values()) {
      const mesh = new THREE.InstancedMesh(state.UNIT[shape], mat, items.length);
      items.forEach((v, i) => {
        mesh.setMatrixAt(i, v.matrix);
        if (v.color !== null) mesh.setColorAt(i, new THREE.Color(v.color));
      });
      mesh.instanceMatrix.needsUpdate = true;
      mesh.castShadow = !mat.transparent;
      mesh.receiveShadow = true;
      mesh.userData.tags = items.map(v => v.tag);
      mesh.computeBoundingSphere();
      this.parent.add(mesh);
      meshes.push(mesh);
    }
    return meshes;
  }
}
