/** models/industry: procedural colony viewer. */
import { state } from '../state.js';
import { localGroup } from '../geometry/objects.js';
import { Kit } from './kit.js';
import * as THREE from 'three';
export function industrialDetails() {
  const k = new Kit(state.world),
    c = state.G.cfg;
  // Substation: cooling fins, conservators, porcelain discs, bus bars and secure yard.
  const g = localGroup(0, -70, .95, 0),
    yard = new Kit(g);
  yard.box(state.M.concrete, 0, -.12, 0, 72, .24, 46);
  for (let i = 0; i < 3; i++) {
    const x = -22 + i * 22;
    for (const z of [-5.2, 5.2]) for (let j = 0; j < 14; j++) yard.box(state.M.trim, x - 5.4 + j * .8, 4.5, z, .12, 6, 1.8);
    yard.add('cyl', state.M.trim, [x, 11.1, -2], [1.05, 7.5, 1.05], [0, 0, Math.PI / 2]);
    for (let phase = -1; phase <= 1; phase++) {
      for (let ring = 0; ring < 7; ring++) yard.add('cyl', state.M.white, [x + phase * 3, 11.7 + ring * .47, 0], [.72, .16, .72]);
      yard.pipe(state.M.trim, [x + phase * 3, 15, 0], [x + phase * 3, 17, phase * 2], .09);
    }
  }
  for (const z of [-23, 23]) for (let x = -36; x <= 36; x += 3) {
    yard.pipe(state.M.steel, [x, 0, z], [x, 3.2, z], .055);
    for (let h = .4; h < 3; h += .4) yard.pipe(state.M.trim, [x, h, z], [Math.min(x + 3, 36), h, z], .018);
  }
  for (const x of [-36, 36]) for (let z = -23; z < 23; z += 3) {
    yard.pipe(state.M.steel, [x, 0, z], [x, 3.3, z], .055);
    for (let h = .4; h < 3; h += .4) yard.pipe(state.M.trim, [x, h, z], [x, h, Math.min(23, z + 3)], .018);
  }
  for (const z of [-23, 23]) for (let x = -36; x < 36; x += .9) {
    yard.add('ring', state.M.steel, [x, 3.4, z], [.32, .32, .32], [0, Math.PI / 2, 0]);
  }
  yard.finish();
  k.finish();
}
export function updatePhysicalState(s) {
  const loads = new Float32Array(state.G.poles.x.length);
  for (let i = 0; i < state.G.houses.x.length; i++) {
    loads[state.G.houses.pole[i]] += s.houses.draw[i];
    if (state.phaseDropFlow) state.phaseDropFlow.active[i] = !!s.houses.power[i];
  }
  for (let i = loads.length - 1; i >= 0; i--) {
    const p = state.G.poles.parent[i];
    if (p >= 0) loads[p] += loads[i];
  }
  for (const m of state.mediumBatches) {
    if (m.material !== state.M.glow) continue;
    const original = m.userData.original;
    m.userData.tags.forEach((id, j) => {
      if (!s.houses.power[id] || state.houseDetails.has(id)) m.instanceMatrix.array.fill(0, j * 16, j * 16 + 16);else m.instanceMatrix.array.set(original.subarray(j * 16, j * 16 + 16), j * 16);
    });
    m.instanceMatrix.needsUpdate = true;
  }
  state.poleDisplays.forEach((v, i) => {
    const value = s.poles.span[i] ? (loads[i] / 1000).toFixed(1) : 'OFF';
    if (v.last === value) return;
    v.last = value;
    const x = v.canvas.getContext('2d');
    x.fillStyle = '#12231f';
    x.fillRect(0, 0, 192, 96);
    x.fillStyle = '#b7e6ba';
    x.font = 'bold 18px monospace';
    x.fillText('L1 L2 L3 / ' + String(i + 1).padStart(3, '0'), 7, 22);
    x.font = 'bold 35px monospace';
    x.fillText(value + ' kW', 7, 65);
    x.font = '13px monospace';
    x.fillText('WY / COLONY METER', 7, 88);
    v.texture.needsUpdate = true;
  });
  state.poleLoads = loads;
  state.cabinetMeters.forEach((m, i) => {
    const on = s.poles.span[i];
    m.material.emissiveIntensity = on ? .3 + Math.min(1.5, loads[i] / 12000) : 0;
    m.material.color.setHex(on ? loads[i] > 18000 ? 0xff834a : 0x9bce84 : 0x30393a);
  });
  for (const mesh of state.potableBatches) {
    if (mesh.material !== state.MAT['water-core'] && mesh.material !== state.MAT['pipe-sightglass'] && mesh.material !== state.MAT['pipe-ice']) continue;
    mesh.userData.tags.forEach((tag, j) => {
      const e = tag?.id >= 0 ? state.G.utilities.links[tag.id] : null,
        house = e ? state.G.utilities.nodes[e.b].house : -1;
      const frozen = house >= 0 && !s.houses.pipes[house],
        burst = house >= 0 && s.houses.burst[house];
      if (mesh.material === state.MAT['pipe-ice']) {
        if (frozen) mesh.instanceMatrix.array.set(mesh.userData.iceOriginal.subarray(j * 16, j * 16 + 16), j * 16);else mesh.instanceMatrix.array.fill(0, j * 16, j * 16 + 16);
        mesh.instanceMatrix.needsUpdate = true;
      }
      mesh.setColorAt(j, new THREE.Color(frozen ? 0xb6dfff : burst ? 0x817c6c : 0xffffff));
    });
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }
  for (const {
    offset,
    signals
  } of state.roadSignals) {
    const phase = (s.t + offset) % 12;
    signals.forEach(({
      lights,
      approach
    }) => {
      const green = approach % 2 === 0 ? phase < 5 : phase >= 6 && phase < 11,
        amber = approach % 2 === 0 ? phase === 5 : phase === 11;
      lights[0].material.color.setHex(!green && !amber ? 0xff392b : 0x241e1b);
      lights[1].material.color.setHex(amber ? 0xffbc43 : 0x242119);
      lights[2].material.color.setHex(green ? 0x9be2b2 : 0x17251e);
    });
  }
}
