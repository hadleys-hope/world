/** render/scene: procedural colony viewer. */
import { state } from '../state.js';
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
export function initialize() {
  state.mapEl = document.getElementById('map');
  state.renderer = new THREE.WebGLRenderer({
    antialias: true
  });
  state.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  state.renderer.shadowMap.enabled = true;
  state.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  state.renderer.toneMapping = THREE.ACESFilmicToneMapping;
  state.renderer.toneMappingExposure = 1.05;
  state.mapEl.appendChild(state.renderer.domElement);
  state.scene = new THREE.Scene();
  state.scene.background = new THREE.Color(0x05070b);
  state.camera = new THREE.PerspectiveCamera(50, 1, .15, 80000);
  state.camera.position.set(360, state.RP + 1050, 1180);
  state.controls = new OrbitControls(state.camera, state.renderer.domElement);
  state.controls.target.set(0, state.RP, 0);
  state.controls.minDistance = .7;
  state.controls.maxDistance = state.RP * 4;
  state.controls.enablePan = true;
  state.controls.screenSpacePanning = true;
  state.controls.panSpeed = 1.35;
  state.controls.zoomSpeed = .65;
  state.controls.enableDamping = true;
  state.controls.dampingFactor = 0.1;
  state.controls.keyPanSpeed = 40;
  state.controls.mouseButtons = {
    LEFT: THREE.MOUSE.PAN,
    MIDDLE: THREE.MOUSE.PAN,
    RIGHT: THREE.MOUSE.ROTATE
  };
  state.controls.touches = {
    ONE: THREE.TOUCH.PAN,
    TWO: THREE.TOUCH.DOLLY_ROTATE
  };
  state.composer = new EffectComposer(state.renderer);
  state.composer.addPass(new RenderPass(state.scene, state.camera));
  state.bloomPass = new UnrealBloomPass(new THREE.Vector2(800, 600), 0.45, 0.5, 0.86);
  state.composer.addPass(state.bloomPass);
}
