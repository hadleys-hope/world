/** render/world: procedural colony viewer. */
import { state } from '../state.js';
import { sph } from '../geometry/planet.js';
import { textSprite } from './textures.js';
import * as THREE from 'three';
export function addLabel(text, x, y, h, color, tier = 'mid', live = false) {
  const s = textSprite(text, color);
  s.position.copy(sph(x, y, h));
  state.labelGroup.add(s);
  state.lod[tier].push(s);
  if (live) state.liveLabels.push(s);
  return s;
}
export function clickable(obj, id, kind, extra) {
  obj.traverse(o => {
    o.userData.click = {
      id,
      kind,
      extra
    };
  });
  obj.userData.click = {
    id,
    kind,
    extra
  };
  state.clickables.push(obj);
  return obj;
}
export function initialize() {
  state.world = new THREE.Group();
  state.scene.add(state.world);
  state.labelGroup = new THREE.Group();
  state.world.add(state.labelGroup);
  state.lod = {
    near: [],
    mid: []
  };
  state.liveLabels = [];
  state.clickables = [];
  state.windowSlots = [];
  state.lockWedges = [];
  state.xenoPool = [];
  state.squadGroup = null;
  state.wallPanels = null;
  state.wallSegs = [];
  state.markers = {};
  state.gates = [];
  state.rovers = {};
  state.hub = {};
  state.complex = {};
  state.roadMeshes = {
    ring: []
  };
  state.pipes = {};
  state.rpBoxes = [];
  state.cabBoxes = [];
  state.flatHouses = [];
  state.spanCurves = [];
  state.trunkCurves = [];
  state.towerCurves = [];
  state.solarCurves = [];
  state.feederCurves = [];
  state.waterMainPts = [];
  state.waterSectorPts = [];
  state.cableTowerCurves = [];
}
