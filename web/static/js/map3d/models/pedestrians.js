/** The exact server graph is also the source of visible pavements and entrances. */
import * as THREE from 'three';
import { state } from '../state.js';
import { polar, quatAt, sph } from '../geometry/planet.js';
import { facility } from './campus.js';
import { Kit } from './kit.js';
import { material } from './materials.js';
import { clickable } from '../render/world.js';

function strip(kit, a, b, width, mat, paint = false) {
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const count = Math.max(1, Math.ceil(length / (paint ? .9 : 2)));
  const point = t => sph(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t);
  for (let i = 0; i < count; i++) {
    if (paint && i % 2) continue;
    const start = point(i / count), end = point((i + 1) / count);
    const centre = start.clone().add(end).multiplyScalar(.5);
    const forward = end.clone().sub(start).normalize();
    const right = centre.clone().normalize().cross(forward).normalize();
    const up = forward.clone().cross(right).normalize();
    const q = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(right, up, forward));
    const thickness = paint ? .025 : .14;
    centre.addScaledVector(up, paint ? .015 : -thickness / 2);
    kit.add('box', mat, centre.toArray(), [width, thickness, start.distanceTo(end) + .01], q);
  }
}

export function buildPedestrianSector() {
  const graph = state.G.pedestrians;
  if (!graph) return;
  const pavement = material('npc-pavement', 0x9dada1);
  const kit = new Kit(state.world);
  state.pedestrianBarriers = new Map();
  for (const [name, spec] of Object.entries(graph.workplaces)) {
    const [x, y] = polar(spec.angle, spec.radius);
    clickable(facility(spec.name.toUpperCase(), x, y, spec.width, 8, spec.depth, {
      yaw: -spec.angle * Math.PI / 180 - Math.PI / 2,
      front: -1, color: name === 'laboratory' ? 0xb3c4c1 : 0x7d969e,
    }), name, 'workplace');
  }
  for (const [id, edge] of Object.entries(graph.edges)) {
    const a = graph.nodes[edge.a], b = graph.nodes[edge.b];
    strip(kit, a, b, edge.kind === 'crossing' ? 3 : 2.3, pavement);
    if (edge.kind === 'crossing') strip(kit, a, b, 2.6, state.M.white, true);
    if (id === 'entrance:workshop' || id === 'crossing:row:0:sector:0') {
      const x = (a[0] + b[0]) / 2, y = (a[1] + b[1]) / 2;
      const barrier = new THREE.Mesh(new THREE.BoxGeometry(3, 1, .2), material('npc-barrier', 0xe6684b));
      barrier.position.copy(sph(x, y, (a[2] + b[2]) / 2 + .5));
      barrier.quaternion.copy(quatAt(x, y, Math.atan2(b[0] - a[0], b[1] - a[1])));
      barrier.visible = false;
      state.world.add(barrier);
      state.pedestrianBarriers.set(id, barrier);
    }
  }
  kit.finish();
  state.npcRouteLine = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: 0x5cffe2, depthTest: false, fog: false, transparent: true, opacity: .85 }));
  state.npcRouteLine.renderOrder = 5;
  state.npcRouteLine.visible = false;
  state.world.add(state.npcRouteLine);
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#17312d'; ctx.strokeStyle = '#5cffe2'; ctx.lineWidth = 4;
  ctx.beginPath(); ctx.moveTo(32, 56); ctx.lineTo(10, 19); ctx.lineTo(54, 19); ctx.closePath(); ctx.fill(); ctx.stroke();
  state.npcSelectionMarker = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false, depthWrite: false, fog: false }));
  state.npcSelectionMarker.renderOrder = 10;
  state.npcSelectionMarker.visible = false;
  state.world.add(state.npcSelectionMarker);
}

export function updatePedestrianState(snapshot) {
  const closed = new Set(snapshot.pedestrians?.closed || []);
  for (const [id, barrier] of state.pedestrianBarriers || []) barrier.visible = closed.has(id);
  document.querySelectorAll('[data-pedestrian-edge]').forEach(button => {
    const noun = button.dataset.pedestrianEdge.startsWith('entrance:') ? 'workshop entrance' : 'crossing';
    button.textContent = `${closed.has(button.dataset.pedestrianEdge) ? 'Open' : 'Close'} ${noun}`;
  });
  updateSelectedRoute();
}

export function updateSelectedRoute() {
  const line = state.npcRouteLine;
  if (!line) return;
  const model = state.selected?.kind === 'person' ? state.colonists?.get(state.selected.id) : null;
  const marker = state.npcSelectionMarker;
  if (marker) {
    marker.visible = !!model && !!state.layers.people;
    if (marker.visible) {
      const size = THREE.MathUtils.clamp(state.camera.position.distanceTo(model.root.position) * .003, .08, .7);
      marker.position.copy(sph(model.x, model.y, model.height + 2.05 + size / 2));
      marker.scale.set(size, size, 1);
    }
  }
  line.visible = !!model?.route && !!state.layers.people;
  if (!line.visible) return;
  const signature = `${state.selected.id}:${model.routeKey}`;
  if (line.userData.signature === signature) return;
  line.geometry.dispose();
  line.geometry = new THREE.BufferGeometry().setFromPoints(model.route.map(p => sph(p[0], p[1], p[2] + .08)));
  line.userData.signature = signature;
}
