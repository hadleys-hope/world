/** build: procedural colony viewer. */
import { state } from './state.js';
import { box, cyl, localGroup, pointsLayer, setPoints } from './geometry/objects.js';
import { arcPts, polar, quatAt, sph } from './geometry/planet.js';
import { cap, ribbon } from './geometry/primitives.js';
import { buildRoadNetwork, buildRoadWalks, junctionMarkings, onRoad } from './geometry/roads.js';
import { buildCampus, equipmentCabinet, facility } from './models/campus.js';
import { buildCargoDepot } from './models/cargo.js';
import { buildUtilities } from './models/drainage.js';
import { buildExternalGrid } from './models/external-grid.js';
import { buildLandscape } from './models/habitat.js';
import { industrialDetails } from './models/industry.js';
import { Kit } from './models/kit.js';
import { material } from './models/materials.js';
import { buildNeighborhood } from './models/neighborhood.js';
import { buildOcean } from './models/ocean.js';
import { detailedPower } from './models/power.js';
import { reactorIndustry } from './models/reactor.js';
import { buildServiceHangar, buildSolarFarm, rebuildHydroponics, storageVessel } from './models/service-sites.js';
import { streetSignals } from './models/signals.js';
import { buildSpaceDish, secureCompound } from './models/space-uplink.js';
import { buildStreetLife } from './models/street-life.js';
import { detailedVehicle } from './models/vehicles.js';
import { buildWaterTower } from './models/water-tower.js';
import { FlowLayer, LineLayer, catenary } from './render/flows.js';
import { applyLayers } from './render/state-sync.js';
import { textSprite } from './render/textures.js';
import { addLabel, clickable } from './render/world.js';
import * as THREE from 'three';
export function build() {
  const c = state.G.cfg,
    R = c.ring_road_radius,
    WR = c.wall_radius,
    ns = c.sectors,
    HR = c.hub_radius,
    rx = c.reactor_pos[0],
    ry = c.reactor_pos[1];
  // ground plate of the city, lighter than the terrain
  buildLandscape();
  state.cityPlate = cap(WR + 6, 0.25, 0x827f73, 110, 256, 0.06);
  buildRoadNetwork();
  // hub plaza
  {
    const plaza = cap(HR, .9, 0x8a8d7e, 26, 128),
      v = plaza.geometry.attributes.position,
      uv = [];
    for (let i = 0; i < v.count; i++) uv.push(v.getX(i) / 7, v.getZ(i) / 7);
    plaza.geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    plaza.material.map = state.pavingTexture;
  }
  for (let s = 0; s < ns; s++) for (let k = 1; k <= c.house_rows; k++) {
    const r = c.house_radius_min - 30 + k * c.house_ring_step - 6;
    ribbon(arcPts(s * 60 + 2.5, s * 60 + 57.5, r, 20), 1.2, -0.4, 0x6f6a62);
  } // terrace edges
  // ---- wall: panels between posts, top rail, footing; gates: towers, floodlights, striped arm, booth ----
  {
    const segs = [];
    const gap = Math.atan2(21, WR) * 180 / Math.PI;
    for (let s = 0; s < ns; s++) {
      const a0 = s * 60 + gap,
        a1 = (s + 1) * 60 - gap,
        n = 22;
      for (let i = 0; i < n; i++) {
        segs.push([a0 + (a1 - a0) * (i + 0.5) / n, a0 + (a1 - a0) * i / n]);
      }
    }
    const segLen = WR * 2 * Math.PI * (60 - 2 * gap) / 360 / 22;
    const m4 = new THREE.Matrix4();
    const panels = new THREE.InstancedMesh(new THREE.BoxGeometry(segLen + 0.6, 13, 2.2), new THREE.MeshStandardMaterial({
      color: 0x8d877b,
      roughness: .85
    }), segs.length);
    const posts = new THREE.InstancedMesh(new THREE.BoxGeometry(3.6, 16, 3.6), new THREE.MeshStandardMaterial({
      color: 0x5f5a52,
      roughness: .8
    }), segs.length + ns);
    const rails = new THREE.InstancedMesh(new THREE.BoxGeometry(segLen + 0.6, 0.9, 3.6), new THREE.MeshStandardMaterial({
      color: 0x6a655c
    }), segs.length);
    const foot = new THREE.InstancedMesh(new THREE.BoxGeometry(segLen + 0.6, 1.4, 5), new THREE.MeshStandardMaterial({
      color: 0x4d4942
    }), segs.length);
    segs.forEach(([a, ap], i) => {
      const [x, y] = polar(a, WR);
      const q = quatAt(x, y, -a * Math.PI / 180 - Math.PI / 2);
      m4.compose(sph(x, y, 6.5), q, new THREE.Vector3(1, 1, 1));
      panels.setMatrixAt(i, m4);
      m4.compose(sph(x, y, 13.4), q, new THREE.Vector3(1, 1, 1));
      rails.setMatrixAt(i, m4);
      m4.compose(sph(x, y, 0.7), q, new THREE.Vector3(1, 1, 1));
      foot.setMatrixAt(i, m4);
      const [px, py] = polar(ap, WR);
      m4.compose(sph(px, py, 8), quatAt(px, py, -ap * Math.PI / 180 - Math.PI / 2), new THREE.Vector3(1, 1, 1));
      posts.setMatrixAt(i, m4);
    });
    for (let s = 0; s < ns; s++) {
      const ap = (s + 1) * 60 - gap;
      const [px, py] = polar(ap, WR);
      m4.compose(sph(px, py, 8), quatAt(px, py, -ap * Math.PI / 180 - Math.PI / 2), new THREE.Vector3(1, 1, 1));
      posts.setMatrixAt(segs.length + s, m4);
    }
    for (const m of [panels, posts, rails, foot]) {
      m.castShadow = true;
      m.receiveShadow = true;
      state.world.add(m);
    }
    state.wallMesh = panels;
    state.wallPanels = panels;
    state.wallSegs = segs;
    for (let g = 0; g < ns; g++) {
      const a = g * 60;
      const [gx, gy] = polar(a, WR);
      const grp = localGroup(gx, gy, 0, -a * Math.PI / 180);
      const tw = new THREE.MeshStandardMaterial({
        color: 0x7c766e,
        roughness: .8
      });
      const win = new THREE.MeshBasicMaterial({
        color: 0xffd27a
      });
      for (const z of [-16, 16]) {
        const t = new THREE.Mesh(new THREE.BoxGeometry(11, 28, 11), tw);
        t.position.set(0, 14, z);
        t.castShadow = true;
        grp.add(t);
        const w1 = new THREE.Mesh(new THREE.BoxGeometry(6, 3, 0.6), win);
        w1.position.set(0, 22, z + (z < 0 ? 5.6 : -5.6));
        grp.add(w1);
        const cap2 = new THREE.Mesh(new THREE.BoxGeometry(13, 1.2, 13), new THREE.MeshStandardMaterial({
          color: 0x4d4942
        }));
        cap2.position.set(0, 28.6, z);
        grp.add(cap2);
        const fl = new THREE.Sprite(new THREE.SpriteMaterial({
          map: state.TEX.glow,
          transparent: true,
          depthWrite: false,
          blending: THREE.AdditiveBlending
        }));
        fl.scale.set(40, 40, 1);
        fl.position.set(-6, 27, z * 0.55);
        grp.add(fl);
      }
      const booth = new THREE.Mesh(new THREE.BoxGeometry(7, 8, 7), new THREE.MeshStandardMaterial({
        color: 0x8a8478
      }));
      booth.position.set(9, 4, -10);
      booth.castShadow = true;
      grp.add(booth);
      const bw = new THREE.Mesh(new THREE.BoxGeometry(0.4, 3, 5), win);
      bw.position.set(5.4, 5, -10);
      grp.add(bw);
      const armG = new THREE.Group();
      armG.position.set(0, 7, -10);
      for (let k = 0; k < 6; k++) {
        const seg = new THREE.Mesh(new THREE.BoxGeometry(1.8, 1.8, 3.4), new THREE.MeshStandardMaterial({
          color: k % 2 ? 0xffffff : 0xe2574d
        }));
        seg.position.set(0, 0, 1.7 + k * 3.4);
        armG.add(seg);
      }
      grp.add(armG);
      const lamp = new THREE.Mesh(new THREE.SphereGeometry(1.4, 8, 8), new THREE.MeshBasicMaterial({
        color: 0x5ec07a
      }));
      lamp.position.set(0, 10, -10);
      grp.add(lamp);
      const beacons = [-16, 16].map(z => {
        const b = new THREE.Sprite(new THREE.SpriteMaterial({
          map: state.TEX.red,
          transparent: true,
          depthTest: false,
          blending: THREE.AdditiveBlending
        }));
        b.scale.set(26, 26, 1);
        b.position.set(0, 31, z);
        b.visible = false;
        grp.add(b);
        return b;
      });
      clickable(grp, 'gate' + g, 'gate', g);
      state.gates.push({
        g: grp,
        arm: armG,
        lamp,
        beacons
      });
      addLabel(g === 3 ? "HADLEY'S HOPE  pop. 158  Weyland-Yutani" : `gate ${g + 1}`, gx, gy, 40, g === 3 ? '#f2c14e' : '#c9cfdb', g === 3 ? 'mid' : 'near');
    }
  }
  // ---- lockdown overlays: a translucent wedge over each sector, shown while it is locked ----
  state.lockWedges = [];
  for (let s = 0; s < ns; s++) {
    const pos = [],
      idx = [];
    const n = 24;
    for (let k = 0; k <= n; k++) {
      const a = s * 60 + k * 60 / n;
      const p0 = sph(...polar(a, HR + 30), 2.5),
        p1 = sph(...polar(a, WR - 6), 2.5);
      pos.push(p0.x, p0.y, p0.z, p1.x, p1.y, p1.z);
      if (k < n) {
        const b = k * 2;
        idx.push(b, b + 1, b + 2, b + 1, b + 3, b + 2);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
      color: 0xe2574d,
      transparent: true,
      opacity: 0.0,
      depthWrite: false,
      side: THREE.DoubleSide
    }));
    m.visible = false;
    state.world.add(m);
    state.lockWedges.push(m);
  }
  buildNeighborhood();
  buildStreetLife();
  buildUtilities();
  const m4 = new THREE.Matrix4();
  // ---- poles, arms, lamps, cables ----
  const P = state.G.poles.x.length;
  state.polesMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(.19, .27, 11, 10), new THREE.MeshStandardMaterial({
    color: 0x9a9a9a
  }), P);
  state.armsMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(3.5, .18, .18), new THREE.MeshStandardMaterial({
    color: 0x777
  }), P);
  state.lampsMesh = new THREE.InstancedMesh(new THREE.SphereGeometry(.22, 8, 8), new THREE.MeshBasicMaterial({
    color: 0xffe9a8
  }), P);
  state.markers.lampGlow = pointsLayer(P, state.TEX.glow, 0xffe08a, 3, true);
  for (let i = 0; i < P; i++) {
    const x = state.G.poles.x[i],
      y = state.G.poles.y[i];
    const yaw = state.G.poles.kind[i] === 0 ? -state.G.poles.angle[i] * Math.PI / 180 + Math.PI / 2 : -state.G.poles.angle[i] * Math.PI / 180;
    m4.compose(sph(x, y, 5.5), quatAt(x, y, yaw), new THREE.Vector3(1, 1, 1));
    state.polesMesh.setMatrixAt(i, m4);
    m4.compose(sph(x, y, 10.3), quatAt(x, y, yaw), new THREE.Vector3(1, 1, 1));
    state.armsMesh.setMatrixAt(i, m4);
    m4.compose(sph(x, y, 9), quatAt(x, y, yaw), new THREE.Vector3(1, 1, 1));
    state.lampsMesh.setMatrixAt(i, m4);
  }
  state.world.add(state.polesMesh);
  state.world.add(state.armsMesh);
  state.world.add(state.lampsMesh);
  state.spanCurves = [];
  const netCurves = [];
  for (let i = 0; i < P; i++) {
    const p = state.G.poles.parent[i];
    const b = sph(state.G.poles.x[i], state.G.poles.y[i], 10.7);
    let a;
    if (p < 0) {
      const s = state.G.poles.sector[i];
      const [qx, qy] = state.G.layout.distribution[s].pole;
      a = sph(qx, qy, 10.7);
    } else a = sph(state.G.poles.x[p], state.G.poles.y[p], 10.7);
    const L = a.distanceTo(b);
    state.spanCurves.push(catenary(a, b, Math.min(1.5, L * .025)));
    const a2 = a.clone().addScaledVector(a.clone().normalize(), -2),
      b2 = b.clone().addScaledVector(b.clone().normalize(), -2);
    netCurves.push(catenary(a2, b2, Math.min(1.5, L * .025)));
  }
  state.netSpanPaths = netCurves;
  state.spanLines = new LineLayer(state.spanCurves, 0xf2c14e);
  state.netLines = new LineLayer(netCurves, 0x4fd1c5);
  detailedPower();
  // rp cabinets and internet cabinets at the start of each boundary street
  for (let s = 0; s < ns; s++) {
    const [qx, qy] = state.G.layout.distribution[s].rp;
    const rp = equipmentCabinet(qx, qy, 6, 4, 6, 0x899382, -(s * 60) * Math.PI / 180);
    clickable(rp, 'rp' + s, 'rp', s);
    state.rpBoxes.push(rp);
    const [cx, cy] = state.G.layout.distribution[s].cab;
    const cab = equipmentCabinet(cx, cy, 3, 3.2, 2.8, 0x708c88, -(s * 60) * Math.PI / 180);
    clickable(cab, 'cab' + s, 'cabinet', s);
    state.cabBoxes.push(cab);
    const [ux, uy] = state.G.layout.distribution[s].ups;
    const ups = equipmentCabinet(ux, uy, 12, 4, 8, 0x708c88, -(s * 60) * Math.PI / 180);
    clickable(ups, 'ups' + s, 'ups', s);
    state.hub['ups' + s] = ups;
    addLabel(`S${s + 1} distribution, UPS, cabinet`, qx, qy, 24, '#9aa3b5', 'near');
  }
  buildExternalGrid();
  // Pipe rendering comes exclusively from /geometry utilities.
  state.waterMainPts = [];
  state.waterSectorPts = [];
  // ---- hub: substation with transformers and a fenced yard, ups, comms, ops, pump station and tank ----
  {
    const yard = localGroup(0, -70, 0, 0);
    const fence = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(70, 6, 44)), new THREE.LineBasicMaterial({
      color: 0x9aa3b5
    }));
    fence.position.y = 3;
    yard.add(fence);
    for (let i = 0; i < 3; i++) {
      const tr = new THREE.Mesh(new THREE.BoxGeometry(12, 10, 9), new THREE.MeshStandardMaterial({
        color: 0x6a6d78
      }));
      tr.position.set(-22 + i * 22, 5, 0);
      yard.add(tr);
      for (let j = 0; j < 3; j++) {
        const b = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.6, 6, 6), new THREE.MeshStandardMaterial({
          color: 0xdddddd
        }));
        b.position.set(-22 + i * 22 - 3 + j * 3, 13, 0);
        yard.add(b);
      }
    }
    const bus = new THREE.Mesh(new THREE.BoxGeometry(60, 0.6, 0.6), new THREE.MeshStandardMaterial({
      color: 0xf2c14e
    }));
    bus.position.set(0, 16.5, 0);
    yard.add(bus);
    state.hub.yard = yard;
    clickable(yard, 'substation', 'substation');
    addLabel('substation 6 kV', 0, -70, 26, '#f2c14e', 'near', true).userData.role = 'sub';
    state.hub.ups = clickable(facility('UPS / BATTERY HALL', -80, 33, 26, 12, 20, {
      type: 'power',
      color: 0x829087
    }), 'upsc', 'upsc');
    addLabel('UPS center', -88, 10, 24, '#4fd1c5', 'near', true).userData.role = 'ups';
    state.hub.comms = clickable(facility('NETWORK / DATA CENTRE', 80, 33, 26, 16, 22, {
      type: 'network',
      color: 0x7d9293
    }), 'comms', 'comms');
    addLabel('network / data centre', 80, 33, 28, '#4fd1c5', 'near', true).userData.role = 'comms';
    state.hub.ops = clickable(facility('COLONY OPERATIONS', 0, 80, 36, 16, 24, {
      color: 0x93988b
    }), 'ops', 'ops');
    addLabel('operations center', 0, 80, 26, '#c9cfdb', 'near');
    state.hub.pump = clickable(facility('PUMP / PRESSURE CONTROL', -35, -40, 18, 9, 14, {
      type: 'power',
      color: 0x7b9694
    }), 'pump', 'pump');
    buildWaterTower();
    addLabel('pump station', -40, -40, 20, '#5aa9ff', 'near', true).userData.role = 'pump';
    addLabel('water tank', -70, -45, 38, '#5aa9ff', 'near', true).userData.role = 'tank';

    // water level inside the tank
  }
  // ---- reactor complex ----
  state.complex.contain = clickable(cyl(rx, ry, 46, 50, 0x555a66), 'reactor', 'reactor');
  state.complex.dome = new THREE.Mesh(new THREE.SphereGeometry(46, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.MeshStandardMaterial({
    color: 0x6a6f7a,
    roughness: .6
  }));
  state.complex.dome.position.copy(sph(rx, ry, 50));
  state.complex.dome.quaternion.copy(quatAt(rx, ry));
  state.world.add(state.complex.dome);
  clickable(state.complex.dome, 'reactor', 'reactor');
  state.complex.turbine = clickable(box(rx + 10, ry + 80, 70, 22, 34, 0x5c6070, 0x9aa3b5), 'reactor', 'reactor');
  addLabel('turbine hall', rx + 10, ry + 80, 34, '#9aa3b5', 'near');
  state.complex.tw1 = cyl(rx - 90, ry - 60, 22, 90, 0x8a8f9a);
  state.complex.tw2 = cyl(rx - 90, ry + 60, 22, 90, 0x8a8f9a);
  state.complex.steam = pointsLayer(24, state.TEX.steam, 0xffffff, 60, false);
  clickable(state.complex.tw1, 'reactor', 'reactor');
  clickable(state.complex.tw2, 'reactor', 'reactor');
  state.complex.core = new THREE.Mesh(new THREE.SphereGeometry(8, 12, 12), new THREE.MeshBasicMaterial({
    color: 0x5ec07a
  }));
  state.complex.core.position.copy(sph(rx, ry, 98));
  state.world.add(state.complex.core);
  addLabel('REACTOR, atmosphere processor', rx, ry, 120, '#5ec07a', 'mid', true).userData.role = 'reactor';
  buildSolarFarm();
  addLabel('solar field', c.solar_pos[0], c.solar_pos[1], 26, '#e0b04a', 'mid', true).userData.role = 'solar';
  state.complex.water = clickable(facility('OCEAN WATER / MELT · FILTER · DESALINATE', c.water_plant_pos[0], c.water_plant_pos[1], 60, 24, 40, {
    type: 'power',
    color: 0x809698
  }), 'wplant', 'wplant');
  state.complex.waterTank = clickable(storageVessel('W-02 / TREATED WATER', c.water_plant_pos[0] - 42, c.water_plant_pos[1] + 65, 11, 23, 0xa0b4b1), 'wplant', 'wplant');
  addLabel('ocean water treatment', ...c.water_plant_pos, 38, '#5aa9ff', 'mid', true).userData.role = 'wplant';
  state.complex.rad = clickable(facility('SHIELDED WASTE / TRANSFER', c.radwaste_pos[0], c.radwaste_pos[1], 70, 12, 50, {
    type: 'workshop',
    color: 0x989276
  }), 'rad', 'rad');
  {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({
      map: state.TEX.rad,
      transparent: true
    }));
    s.scale.set(16, 16, 1);
    s.position.copy(sph(c.radwaste_pos[0], c.radwaste_pos[1], 20));
    state.world.add(s);
    const f = localGroup(c.radwaste_pos[0], c.radwaste_pos[1], 0, 0);
    const fence = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(100, 5, 80)), new THREE.LineBasicMaterial({
      color: 0xe8d34a
    }));
    fence.position.y = 2.5;
    f.add(fence);
  }
  addLabel('radioactive waste storage', c.radwaste_pos[0], c.radwaste_pos[1], 30, '#e8d34a', 'mid');
  state.complex.mine = clickable(facility('MINING / ORE PROCESSING', c.mine_pos[0], c.mine_pos[1], 60, 20, 44, {
    type: 'workshop',
    color: 0x8d8978
  }), 'mine', 'mine');
  {
    const hf = localGroup(c.mine_pos[0] + 50, c.mine_pos[1] + 34, 0, 0);
    state.layoutFootprints.push({
      name: 'mine-headframe',
      x: c.mine_pos[0] + 50,
      y: c.mine_pos[1] + 34,
      w: 23,
      d: 5,
      yaw: 0
    });
    const legs = new THREE.Mesh(new THREE.BoxGeometry(3, 60, 3), new THREE.MeshStandardMaterial({
      color: 0x8a7a5a
    }));
    legs.position.set(-8, 30, 0);
    hf.add(legs);
    const legs2 = legs.clone();
    legs2.position.set(8, 30, 0);
    hf.add(legs2);
    const wheel = new THREE.Mesh(new THREE.TorusGeometry(8, 1.2, 8, 24), new THREE.MeshStandardMaterial({
      color: 0xaaaaaa
    }));
    wheel.position.set(0, 62, 0);
    hf.add(wheel);
    state.complex.wheel = wheel;
  }
  addLabel('mine', c.mine_pos[0], c.mine_pos[1], 34, '#a08a2a', 'mid', true).userData.role = 'mine';
  state.complex.waste = clickable(facility('RESOURCE RECOVERY', c.waste_station_pos[0], c.waste_station_pos[1], 40, 14, 30, {
    type: 'workshop',
    color: 0x879078
  }), 'wproc', 'wproc');
  addLabel('waste processing', c.waste_station_pos[0], c.waste_station_pos[1], 24, '#9bd36a', 'near', true).userData.role = 'wproc';
  // ---- radio tower: converging lattice mast with an omni antenna and a beacon; next to it a deep-space dish on a pedestal ----
  {
    const tx = c.tower_pos[0],
      ty = c.tower_pos[1];
    const g = localGroup(tx, ty, 0, 0);
    const H = 130;
    const legMat = new THREE.MeshStandardMaterial({
      color: 0xc44a3a
    });
    const whiteMat = new THREE.MeshStandardMaterial({
      color: 0xe8e8e8
    });
    const wAt = l => 10 - 8.5 * (l / 12);
    const brace = [];
    for (let l = 0; l < 12; l++) {
      const y0 = l * H / 12,
        y1 = (l + 1) * H / 12,
        w0 = wAt(l),
        w1 = wAt(l + 1);
      for (let k = 0; k < 4; k++) {
        const a1 = k * Math.PI / 2 + Math.PI / 4,
          a2 = (k + 1) * Math.PI / 2 + Math.PI / 4;
        const p0 = new THREE.Vector3(Math.cos(a1) * w0 / 2, y0, Math.sin(a1) * w0 / 2),
          p1 = new THREE.Vector3(Math.cos(a1) * w1 / 2, y1, Math.sin(a1) * w1 / 2);
        const seg = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.5, p0.distanceTo(p1), 6), l % 2 ? whiteMat : legMat);
        seg.position.copy(p0).lerp(p1, 0.5);
        seg.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), p1.clone().sub(p0).normalize());
        g.add(seg);
        brace.push(Math.cos(a1) * w0 / 2, y0, Math.sin(a1) * w0 / 2, Math.cos(a2) * w0 / 2, y0, Math.sin(a2) * w0 / 2);
        brace.push(Math.cos(a1) * w0 / 2, y0, Math.sin(a1) * w0 / 2, Math.cos(a2) * w1 / 2, y1, Math.sin(a2) * w1 / 2);
      }
    }
    const bg = new THREE.BufferGeometry();
    bg.setAttribute('position', new THREE.Float32BufferAttribute(brace, 3));
    g.add(new THREE.LineSegments(bg, new THREE.LineBasicMaterial({
      color: 0xd8d8d8
    })));
    for (let k = 0; k < 3; k++) {
      const a = k * Math.PI * 2 / 3 + 1.2,
        ax = tx + Math.cos(a) * 64,
        ay = ty + Math.sin(a) * 64,
        foot = sph(ax, ay, 1.15),
        top = sph(tx, ty, H * .7);
      state.world.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([top, foot]), new THREE.LineBasicMaterial({
        color: 0x9ba3a0
      })));
      const ak = new Kit(state.world);
      ak.add('box', state.M.concrete, foot.toArray(), [3.5, 1, 3.5], quatAt(ax, ay));
      ak.add('box', state.M.steel, sph(ax, ay, 1.75).toArray(), [.5, .35, .8], quatAt(ax, ay));
      ak.finish();
      state.layoutFootprints.push({
        name: 'mast-anchor',
        x: ax,
        y: ay,
        w: 3.5,
        d: 3.5,
        yaw: 0
      });
    }
    const omni = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 16, 6), whiteMat);
    omni.position.set(0, H + 8, 0);
    g.add(omni);
    state.complex.towerLight = new THREE.Sprite(new THREE.SpriteMaterial({
      map: state.TEX.red,
      transparent: true,
      depthTest: false
    }));
    state.complex.towerLight.scale.set(14, 14, 1);
    state.complex.towerLight.position.set(0, H + 17, 0);
    g.add(state.complex.towerLight);
    state.complex.rings = [];
    for (let k = 0; k < 3; k++) {
      const r = new THREE.Mesh(new THREE.TorusGeometry(8 + k * 7, 0.5, 6, 32), new THREE.MeshBasicMaterial({
        color: 0x4fd1c5,
        transparent: true,
        opacity: 0.5
      }));
      r.position.set(0, H + 8, 0);
      r.rotation.x = Math.PI / 2;
      g.add(r);
      state.complex.rings.push(r);
    }
    clickable(g, 'tower', 'tower');
    state.complex.towerGroup = g;
    addLabel('CELLULAR / 5G COLONY COVERAGE', tx, ty, H + 28, '#4fd1c5', 'mid');
    const ant = new Kit(g);
    for (let level = 0; level < 2; level++) for (let n = 0; n < 3; n++) {
      const a = n * Math.PI * 2 / 3,
        xx = Math.cos(a) * 3,
        zz = Math.sin(a) * 3;
      ant.box(state.M.white, xx, H - 7 - level * 6, zz, .75, 3.8, .3, [0, -a, 0]);
      ant.pipe(state.M.dark, [xx, H - 9 - level * 6, zz], [xx, 0, zz], .055);
    }
    ant.finish();
    secureCompound(tx, ty, 158, 158);
    facility('CELLULAR / 5G BASEBAND', tx + 25, ty - 28, 18, 8, 12, {
      type: 'network'
    });
  }
  buildSpaceDish();
  // ---- flows, markers, rovers, sector labels ----
  state.flowPower = new FlowLayer([...state.spanCurves, ...state.feederCurves, ...state.trunkCurves, ...state.towerCurves, ...state.solarCurves], 0xfff2b0, 2, 3, 30);
  state.flowWater = new FlowLayer([], 0x9ad0ff, 7, 4, 30);
  state.packetsPts = pointsLayer(80, state.TEX.dot, 0x4fd1c5, 2, false);
  state.markers.packetsRed = pointsLayer(20, state.TEX.dot, 0xe2574d, 9, false);
  state.markers.issues = pointsLayer(60, state.TEX.bang, 0xffffff, 22, false);
  state.markers.nonet = pointsLayer(300, state.TEX.nonet, 0xffffff, 12, false);
  state.markers.heater = pointsLayer(300, state.TEX.flame, 0xffffff, 8, false);
  state.markers.people = pointsLayer(80, state.TEX.person, 0xffffff, 9, false);
  state.markers.xenos = pointsLayer(20, state.TEX.diamond, 0xffffff, 20, false);
  state.markers.marines = pointsLayer(8, state.TEX.marine, 0xffffff, 11, false);
  state.markers.ups = pointsLayer(8, state.TEX.bolt, 0xffffff, 20, false);
  const rc = {
    garbage: [0x9bd36a, 'garbage rover'],
    sludge: [0xb48ead, 'sludge hauler'],
    engineer: [0xf2c14e, 'engineering crew 1'],
    'engineer-2': [0xf2c14e, 'engineering crew 2'],
    plumber: [0x5aa9ff, 'plumber']
  };
  for (const [name, [col, l]] of Object.entries(rc)) {
    const g = detailedVehicle(col, name);
    const lab = textSprite(l, '#fff', 22);
    lab.position.y = 5;
    lab.scale.multiplyScalar(0.22);
    g.add(lab);
    state.world.add(g);
    clickable(g, 'rover:' + name, 'rover', name);
    state.rovers[name] = {
      g,
      lab,
      from: null,
      to: null,
      q: null,
      t0: 0
    };
  }
  for (let s = 0; s < ns; s++) {
    const [x, y] = polar(s * 60 + 30, R + 70);
    addLabel(`Sector ${s + 1}`, x, y, 8, '#9aa3b5', 'mid');
  }
  // ---- inner ring props: vehicle bay, med lab, school, containers, greenhouses, tanks ----
  buildServiceHangar();
  {
    const [ma, mr] = c.medlab,
      [mx, my] = polar(ma, mr);
    clickable(facility('MEDICAL / RESEARCH', mx, my, 36, 12, 24, {
      yaw: -ma * Math.PI / 180 - Math.PI / 2,
      color: 0x929c90
    }), 'medlab', 'medlab');
    const [sa, sr] = c.school,
      [sx, sy] = polar(sa, sr);
    clickable(facility('SCHOOL / COMMUNITY', sx, sy, 40, 10, 24, {
      yaw: -sa * Math.PI / 180 - Math.PI / 2,
      color: 0x9c9b84
    }), 'school', 'school');
  }
  buildCargoDepot();
  rebuildHydroponics();
  for (let n = 0; n < 4; n++) {
    const [x, y] = polar(12 + n * 12, 244);
    storageVessel(n < 2 ? 'O2 / LIQUID OXYGEN' : 'DIESEL / ROVER FUEL', x, y, 5.2, 14, n < 2 ? 0xb5c3bc : 0x989f8c);
  }
  // ---- landing pad east of the city ----
  {
    const [lx, ly] = c.landing_pad_pos;
    cap(90, 0.9, 0x4a4f5a, 6, 48, 0, lx, ly);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(88, 1.2, 6, 64), new THREE.MeshBasicMaterial({
      color: 0xf2c14e
    }));
    ring.position.copy(sph(lx, ly, 1.6));
    ring.quaternion.copy(quatAt(lx, ly));
    ring.rotateX(Math.PI / 2);
    state.world.add(ring);
    state.complex.padLights = pointsLayer(12, state.TEX.glow, 0xffb060, 30, true);
    setPoints(state.complex.padLights, Array.from({
      length: 12
    }, (_, k) => {
      const [px, py] = polar(k * 30, 86);
      return [lx + px, ly + py];
    }), 2);
    const beacon = cyl(lx + 95, ly - 95, 1.5, 50, 0xc9cfdb);
    state.complex.beacon = new THREE.Sprite(new THREE.SpriteMaterial({
      map: state.TEX.red,
      transparent: true,
      depthTest: false
    }));
    state.complex.beacon.scale.set(16, 16, 1);
    state.complex.beacon.position.copy(sph(lx + 95, ly - 95, 52));
    state.world.add(state.complex.beacon);
    clickable(cap(90, 1.0, 0x4a4f5a, 6, 48, 0, lx, ly), 'pad', 'pad');
    addLabel('landing field', lx, ly, 30, '#f2c14e', 'mid');
  }
  // ---- xenomorphs: a pool of articulated figures; marines: a squad of four ----
  const xenoMat = new THREE.MeshStandardMaterial({
    color: 0x101216,
    roughness: .35,
    metalness: .6
  });
  for (let k = 0; k < 12; k++) {
    const g = new THREE.Group();
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(2.2, 7, 4, 8), xenoMat);
    body.rotation.x = Math.PI / 2;
    body.position.y = 4;
    g.add(body);
    const head = new THREE.Mesh(new THREE.CapsuleGeometry(1.4, 6, 4, 8), xenoMat);
    head.rotation.x = Math.PI / 2;
    head.position.set(0, 6, 5.5);
    g.add(head);
    const tail = new THREE.Mesh(new THREE.ConeGeometry(0.9, 12, 6), xenoMat);
    tail.rotation.x = -Math.PI / 2 - 0.3;
    tail.position.set(0, 4.5, -9);
    g.add(tail);
    for (const [sx, sz] of [[-2.4, 2], [2.4, 2], [-2.4, -2], [2.4, -2]]) {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.3, 5, 5), xenoMat);
      leg.position.set(sx, 2.2, sz);
      leg.rotation.z = sx > 0 ? -0.5 : 0.5;
      g.add(leg);
    }
    for (const sx of [-1.5, 1.5]) {
      const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.3, 5, 5), xenoMat);
      arm.position.set(sx, 5, 4);
      arm.rotation.z = sx > 0 ? -0.9 : 0.9;
      arm.rotation.x = -0.6;
      g.add(arm);
    }
    const lab = textSprite('xenomorph', '#e2574d', 22);
    lab.position.y = 14;
    lab.scale.multiplyScalar(0.5);
    g.add(lab);
    g.visible = false;
    state.world.add(g);
    clickable(g, 'xeno:' + k, 'xeno', k);
    state.xenoPool.push({
      g,
      lab,
      from: null,
      to: null,
      q: null,
      t0: 0,
      id: null
    });
  }
  state.squadGroup = new THREE.Group();
  const mMat = new THREE.MeshStandardMaterial({
    color: 0x5a6a3a,
    roughness: .8
  });
  for (let k = 0; k < 4; k++) {
    const m = new THREE.Group();
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(1.2, 3, 4, 8), mMat);
    body.position.y = 3.6;
    m.add(body);
    const helm = new THREE.Mesh(new THREE.SphereGeometry(1.3, 8, 8), new THREE.MeshStandardMaterial({
      color: 0x3a4a2a
    }));
    helm.position.y = 6.6;
    m.add(helm);
    const rifle = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.6, 4), new THREE.MeshStandardMaterial({
      color: 0x222
    }));
    rifle.position.set(1.4, 4, 1);
    m.add(rifle);
    m.position.set(k % 2 * 5 - 2.5, 0, Math.floor(k / 2) * 5 - 2.5);
    state.squadGroup.add(m);
  }
  {
    const lab = textSprite('marine squad', '#8be05a', 22);
    lab.position.y = 12;
    lab.scale.multiplyScalar(0.5);
    state.squadGroup.add(lab);
    state.squadGroup.userData.lab = lab;
  }
  state.squadGroup.visible = false;
  state.world.add(state.squadGroup);
  clickable(state.squadGroup, 'squad', 'squad');
  state.markers.ctrl = (() => {
    const n = 300;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(n * 3).fill(-99999), 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(n * 3), 3));
    const m = new THREE.Points(g, new THREE.PointsMaterial({
      map: state.TEX.dot,
      vertexColors: true,
      size: 9,
      transparent: true,
      depthWrite: false,
      sizeAttenuation: true
    }));
    m.frustumCulled = false;
    state.world.add(m);
    return m;
  })();
  industrialDetails();
  buildCampus();
  reactorIndustry();
  buildOcean();
  buildRoadWalks();
  streetSignals();
  junctionMarkings();
  scatterTerrainDebris();
  applyLayers();
}
export function scatterTerrainDebris() {
  const c = state.G.cfg,
    mesh = new THREE.InstancedMesh(new THREE.DodecahedronGeometry(1, 0), material('basalt', 0x5a544c, {
      roughness: 1
    }), 500),
    m = new THREE.Matrix4();
  let seed = 7,
    count = 0;
  const rnd = () => {
    seed = seed * 16807 % 2147483647;
    return seed / 2147483647;
  };
  for (let i = 0; i < 500; i++) {
    const a = rnd() * 360,
      r = c.wall_radius + 40 + rnd() * 900,
      [x, y] = polar(a, r),
      size = 2 + rnd() * 9;
    if (onRoad(x, y, size + 3) || state.layoutFootprints.some(f => {
      const dx = x - f.x,
        dy = y - f.y,
        co = Math.cos(f.yaw),
        si = Math.sin(f.yaw);
      return Math.abs(dx * co - dy * si) < f.w / 2 + size + 4 && Math.abs(dx * si + dy * co) < f.d / 2 + size + 4;
    }) || Math.hypot(x - c.reactor_pos[0], y - c.reactor_pos[1]) < 175 || Math.hypot(x - c.water_plant_pos[0], y - c.water_plant_pos[1]) < 100 || Math.hypot(x - c.solar_pos[0], y - c.solar_pos[1]) < 145 || Math.hypot(x - c.tower_pos[0], y - c.tower_pos[1]) < 120 || Math.hypot(x - c.dish_pos[0], y - c.dish_pos[1]) < 120) continue;
    m.compose(sph(x, y, size * .4), quatAt(x, y, rnd() * 6.3), new THREE.Vector3(size, size * .6, size));
    mesh.setMatrixAt(count++, m);
  }
  mesh.count = count;
  mesh.instanceMatrix.needsUpdate = true;
  mesh.castShadow = true;
  state.world.add(mesh);
}
