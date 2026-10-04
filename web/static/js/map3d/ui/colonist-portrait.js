/** Render the same body and profession equipment used in the world. */
import * as THREE from 'three';
import { createColonist } from '../models/colonists.js';
const portraits = new Map();
let renderer;
export function colonistPortrait(profession) {
  if (portraits.has(profession)) return portraits.get(profession);
  renderer ||= new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(180, 190);
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x425466, 2.5));
  const light = new THREE.DirectionalLight(0xffffff, 3);
  light.position.set(-3, 5, 6); scene.add(light);
  const model = createColonist(profession);
  model.root.rotation.y = -.3; scene.add(model.root);
  const camera = new THREE.PerspectiveCamera(32, 180 / 190, .1, 20);
  camera.position.set(0, 1.1, 4.2); camera.lookAt(0, .95, 0);
  renderer.render(scene, camera);
  const result = renderer.domElement.toDataURL('image/png');
  portraits.set(profession, result);
  return result;
}
