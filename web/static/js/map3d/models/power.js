/** models/power: procedural colony viewer. */
import { state } from '../state.js';
import { quatAt, sph } from '../geometry/planet.js';
import { FlowLayer, LineLayer, catenary } from '../render/flows.js';
import { Kit } from './kit.js';
import * as THREE from 'three';
export function serviceEntry(i) {
  const {
      base,
      q
    } = state.houseShells[i],
    [w, h, d] = state.DIM[state.G.houses.type[i]],
    pole = state.G.houses.pole[i];
  const direction = sph(state.G.poles.x[pole], state.G.poles.y[pole], 10.7).sub(base).applyQuaternion(q.clone().invert());
  const t = Math.min((w / 2 - .48) / Math.max(.001, Math.abs(direction.x)), (d / 2 - .48) / Math.max(.001, Math.abs(direction.z)));
  const x = direction.x * t,
    z = direction.z * t,
    side = Math.abs(x) / (w / 2) > Math.abs(z) / (d / 2) ? 'x' : 'z',
    height = h + 2.25 + i % 3 * .3;
  return {
    x,
    z,
    height,
    w,
    h,
    d,
    side,
    pole,
    base,
    q,
    world: new THREE.Vector3(x, height, z).applyQuaternion(q).add(base)
  };
}
export function makeServiceDrops(kit, physical, anchor) {
  for (let i = 0; i < state.G.houses.x.length; i++) {
    const e = serviceEntry(i);
    state.serviceEntries[i] = e;
    const {
      x,
      z,
      height,
      w,
      h,
      d,
      side,
      pole,
      base,
      q
    } = e;
    const point = p => new THREE.Vector3(...p).applyQuaternion(q).add(base),
      end = e.world;
    kit.pipe(state.M.steel, point([x, h, z]).toArray(), end.toArray(), .085);
    kit.add('box', state.M.trim, point([x, height - .3, z]).toArray(), [1.3, .12, .13], q);
    kit.add('box', state.M.dark, point([x, h + .15, z]).toArray(), [.65, .3, .65], q);
    for (let phase = -1; phase <= 1; phase++) {
      const to = point([x + phase * .38, height, z]),
        from = anchor(pole, phase),
        line = catenary(from, to, .55);
      // Every cable segment within the building footprint must clear the parapet.
      for (const p of line) {
        const v = p.clone().sub(base).applyQuaternion(q.clone().invert());
        if (Math.abs(v.x) < w / 2 + .1 && Math.abs(v.z) < d / 2 + .1 && v.y < h + .6) p.addScaledVector(p.clone().normalize(), h + .6 - v.y);
      }
      physical.push(line);
      state.serviceWirePaths.push({
        house: i,
        kind: 'phase',
        points: line
      });
      for (let j = 1; j < line.length; j++) kit.pipe(state.M.dark, line[j - 1].toArray(), line[j].toArray(), .025);
      for (let disc = 0; disc < 4; disc++) kit.add('cyl', state.M.white, point([x + phase * .38, height - .27 + disc * .075, z]).toArray(), [.09, .038, .09], q);
      if (phase === 0) state.phaseDrops.push(line);
    }
    const neutral = catenary(anchor(pole, 0, 9.9), point([x, height - .22, z]), .4);
    physical.push(neutral);
    state.serviceWirePaths.push({
      house: i,
      kind: 'neutral',
      points: neutral
    });
    for (let j = 1; j < neutral.length; j++) kit.pipe(state.M.dark, neutral[j - 1].toArray(), neutral[j].toArray(), .022);
    const net = catenary(anchor(pole, 0, 8.7), point([x, height - .46, z]), .32);
    physical.push(net);
    state.serviceWirePaths.push({
      house: i,
      kind: 'fiber',
      points: net
    });
    state.houseNetDrops[i] = net;
    const exterior = side === 'x' ? [Math.sign(x) * (w / 2 + .26), h + .3, z] : [x, h + .3, Math.sign(z) * (d / 2 + .26)];
    const meter = [exterior[0], 1.9, exterior[2]],
      bend = [x, h + .3, z];
    for (const [a, b] of [[[x, height - .2, z], bend], [bend, exterior], [exterior, meter]]) kit.pipe(state.M.rubber, point(a).toArray(), point(b).toArray(), .047);
    kit.add('box', state.M.trim, point(meter).toArray(), side === 'x' ? [.26, 1, .66] : [.66, 1, .26], q);
    const led = meter.slice();
    led[side === 'x' ? 0 : 2] += Math.sign(side === 'x' ? x : z) * .15;
    kit.add('box', state.M.screen, point([led[0], 2.1, led[2]]).toArray(), side === 'x' ? [.035, .22, .4] : [.4, .22, .035], q);
  }
}
export function buildPolePicking() {
  const count = state.G.poles.x.length;
  state.polePickMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1.2, 11, 1.2), new THREE.MeshBasicMaterial({
    transparent: true,
    opacity: 0,
    depthWrite: false,
    colorWrite: false
  }), count);
  const m = new THREE.Matrix4();
  for (let i = 0; i < count; i++) state.polePickMesh.setMatrixAt(i, m.compose(sph(state.G.poles.x[i], state.G.poles.y[i], 5.5), quatAt(state.G.poles.x[i], state.G.poles.y[i]), new THREE.Vector3(1, 1, 1)));
  state.world.add(state.polePickMesh);
  state.cabinetMeters.forEach((m, i) => {
    m.userData.pole = i;
  });
}
export function detailedPower() {
  const kit = new Kit(state.world),
    physical = [],
    P = state.G.poles.x.length,
    phaseColors = [0xc5bfa7, 0xbeb3a2, 0xa9b8bf];
  const anchor = (i, phase, height = 10.7) => {
    const x = state.G.poles.x[i],
      y = state.G.poles.y[i],
      yaw = state.G.poles.kind[i] === 0 ? -state.G.poles.angle[i] * Math.PI / 180 + Math.PI / 2 : -state.G.poles.angle[i] * Math.PI / 180;
    return sph(x, y, height).add(new THREE.Vector3(phase * 1.5, 0, 0).applyQuaternion(quatAt(x, y, yaw)));
  };
  for (let i = 0; i < P; i++) {
    const x = state.G.poles.x[i],
      y = state.G.poles.y[i],
      parent = state.G.poles.parent[i],
      q = quatAt(x, y, -state.G.poles.angle[i] * Math.PI / 180);
    for (let phase = -1; phase <= 1; phase++) {
      const b = anchor(i, phase),
        a = parent >= 0 ? anchor(parent, phase) : state.spanCurves[i][0].clone().add(new THREE.Vector3(phase * 1.4, 0, 0).applyQuaternion(quatAt(...state.G.layout.distribution[state.G.poles.sector[i]].pole)));
      const line = catenary(a, b, Math.min(1.5, a.distanceTo(b) * .025));
      physical.push(line);
      for (let j = 1; j < line.length; j++) kit.pipe(state.M.dark, line[j - 1].toArray(), line[j].toArray(), .026);
      for (let ring = 0; ring < 4; ring++) kit.add('cyl', state.M.white, b.clone().addScaledVector(b.clone().normalize(), -.32 + ring * .1).toArray(), [.13, .055, .13], quatAt(x, y));
    }
    const neutralEnd = anchor(i, 0, 9.9),
      neutralStart = parent >= 0 ? anchor(parent, 0, 9.9) : state.spanCurves[i][0].clone().addScaledVector(state.spanCurves[i][0].clone().normalize(), -.8),
      neutral = catenary(neutralStart, neutralEnd, Math.min(1.5, neutralStart.distanceTo(neutralEnd) * .025));
    physical.push(neutral);
    for (let j = 1; j < neutral.length; j++) kit.pipe(state.M.dark, neutral[j - 1].toArray(), neutral[j].toArray(), .03);
    kit.pipe(state.M.trim, sph(x + .25, y, .2).toArray(), sph(x + .25, y, 9.9).toArray(), .018);
    const base = sph(x, y, 1.2),
      put = (mat, p, sz) => kit.add('box', mat, base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(), sz, q);
    put(state.M.trim, [.42, 1.5, 0], [.65, 1.25, .33]);
    put(state.M.steel, [.42, 1.5, .19], [.57, 1.14, .05]);
    put(state.M.screen, [.42, 1.74, .225], [.38, .24, .025]);
    for (let j = 0; j < 3; j++) put(state.M.amber, [.28 + j * .14, 1.43, .24], [.065, .12, .045]);
    put(state.M.dark, [.65, 1.49, .25], [.045, .16, .05]);
    kit.pipe(state.M.dark, sph(x, y, 2.8).toArray(), sph(x, y, 8.7).toArray(), .044);
    const led = new THREE.Mesh(state.UNIT.box, state.M.glow.clone());
    led.scale.set(.38, .07, .035);
    led.position.copy(base.clone().add(new THREE.Vector3(.42, 1.14, .23).applyQuaternion(q)));
    led.quaternion.copy(q);
    state.world.add(led);
    state.cabinetMeters.push(led);
    const canvas = document.createElement('canvas');
    canvas.width = 192;
    canvas.height = 96;
    const texture = new THREE.CanvasTexture(canvas),
      display = new THREE.Mesh(new THREE.PlaneGeometry(.38, .24), new THREE.MeshBasicMaterial({
        map: texture
      }));
    display.position.copy(base.clone().add(new THREE.Vector3(.42, 1.74, .245).applyQuaternion(q)));
    display.quaternion.copy(q);
    state.world.add(display);
    state.poleDisplays.push({
      display,
      canvas,
      texture,
      last: ''
    });
  }
  makeServiceDrops(kit, physical, anchor);
  kit.finish();
  new LineLayer(physical, 0x8b9996);
  state.phaseDropFlow = new FlowLayer(state.phaseDrops, 0xffd777, 1.5, 3, 22);
  buildPolePicking();
}
export function initialize() {
  state.serviceWirePaths = [];
  state.serviceEntries = [];
  state.poleLoads = new Float32Array(0);
  state.polePickMesh = null;
  state.poleDisplays = [];
}
