/** models/materials: procedural colony viewer. */
import { state } from '../state.js';
import * as THREE from 'three';
export function material(name, color, opts = {}) {
  if (!state.MAT[name]) state.MAT[name] = new THREE.MeshStandardMaterial({
    color,
    roughness: .78,
    ...opts
  });
  return state.MAT[name];
}
export function initialize() {
  state.DIM = [[20, 7.25, 18], [16, 10.65, 18], [17, 7.25, 18], [20, 10.65, 20]];
  state.houseDetails = new Map();
  state.houseShells = [];
  state.roofProxies = [];
  state.utilityGroup = new THREE.Group();
  state.utilityBatches = [];
  state.utilityDrops = null;
  state.utilityPaths = [];
  state.utilityTime = 0;
  state.utilityLastTime = 0;
  state.streetDetail = new THREE.Group();
  state.cityPlate = null;
  state.detailFrame = 0;
  state.world.add(state.utilityGroup, state.streetDetail);
  state.UNIT = {
    tankcyl: new THREE.CylinderGeometry(1, 1, 1, 64),
    cone: new THREE.ConeGeometry(1, 1, 24),
    box: new THREE.BoxGeometry(1, 1, 1),
    cyl: new THREE.CylinderGeometry(1, 1, 1, 10),
    ball: new THREE.SphereGeometry(1, 8, 6),
    ring: new THREE.TorusGeometry(1, .13, 5, 12)
  };
  state.MAT = {};
  state.M = {
    roof: material('roof-slab', 0x6e7775, {
      transparent: true,
      opacity: .84,
      depthWrite: false,
      side: THREE.DoubleSide,
      metalness: .5,
      roughness: .48
    }),
    steel: material('steel', 0x465052, {
      metalness: .72,
      roughness: .48
    }),
    trim: material('trim', 0x929c98, {
      metalness: .65,
      roughness: .38
    }),
    panel: material('panel', 0x918e7c, {
      metalness: .35
    }),
    dark: material('dark', 0x1d2528),
    concrete: material('concrete', 0x696a60),
    brick: material('brick', 0x716050),
    grout: material('grout', 0x363a36),
    wood: material('wood', 0x896a46),
    fabric: material('fabric', 0x656e5a),
    white: material('white', 0xc1c6ba),
    amber: material('amber', 0xc99742),
    rubber: material('rubber', 0x171d20),
    blue: material('blue', 0x2e7083),
    glow: material('glow', 0xffcf85, {
      emissive: 0xffa849,
      emissiveIntensity: .7
    }),
    glass: new THREE.MeshPhysicalMaterial({
      color: 0x9abcc1,
      metalness: .08,
      roughness: .12,
      transparent: true,
      opacity: .28,
      depthWrite: false,
      side: THREE.DoubleSide,
      envMapIntensity: 1.5,
      clearcoat: 1
    }),
    screen: material('screen', 0x263e47, {
      emissive: 0x386575,
      emissiveIntensity: .6
    })
  };
  {
    const sky = new THREE.Scene();
    sky.background = new THREE.Color(0x46535b);
    const a = new THREE.Mesh(new THREE.SphereGeometry(40, 16, 12), new THREE.MeshBasicMaterial({
      color: 0x121b21,
      side: THREE.BackSide
    }));
    sky.add(a);
    for (let i = 0; i < 8; i++) {
      const p = new THREE.Mesh(new THREE.PlaneGeometry(7, 18), new THREE.MeshBasicMaterial({
        color: i % 2 ? 0xa7b7b5 : 0xddd0ab,
        side: THREE.DoubleSide
      }));
      p.position.set(Math.sin(i) * 25, 8, Math.cos(i) * 25);
      p.lookAt(0, 0, 0);
      sky.add(p);
    }
    const pmrem = new THREE.PMREMGenerator(state.renderer);
    const env = pmrem.fromScene(sky, .06);
    state.scene.environment = env.texture;
    sky.traverse(o => {
      if (o.isMesh) {
        o.geometry.dispose();
        o.material.dispose();
      }
    });
    pmrem.dispose();
  }
}
