import { buildPublicSpace } from "./urban/public-space.js";
/** models/oasis: Hadley's Hope under a glass dome, and a garden inside it. The dome is one transparent mesh
 * with a geodesic frame drawn in its shader (no geometry for the struts). The garden finds the free ground
 * between roads and houses on a 3 m grid and fills it: lawns, flowerbeds, shrubs, trees, giant trees hung
 * with vines, ponds and a gravel path. Every kind is one InstancedMesh: a few draw calls for the whole park. */
import { state } from "../state.js";
import { sph, surfaceHeight } from "../geometry/planet.js";
import { instances, lifeMaterial, treeGeometry, tuftGeometry } from "./life.js";
import { waterMaterial } from "./waters.js";
import * as THREE from "three";

const DOME_R = 735, DOME_H = 320;

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = Math.imul(s ^ (s >>> 15), 2246822507) + 0x9e3779b9) >>> 0) / 4294967296;
}
const dirOf = (x, y) => {
  const a = Math.hypot(x, y) / state.RP, p = Math.atan2(y, x), s = Math.sin(a);
  return [s * Math.cos(p), Math.cos(a), s * Math.sin(p)];
};

/** A glass dome: point(x, y, h) maps a local plan position and a height to the body's frame. */
export function makeDome(point, radius, height, uniforms, segments = 192, portals = []) {
  const AZ = segments, EL = 64;
  const pos = [], uv = [], idx = [];
  for (let j = 0; j <= EL; j++) {
    const t = j / EL, r = radius * Math.cos((t * Math.PI) / 2), up = height * Math.sin((t * Math.PI) / 2);
    for (let i = 0; i <= AZ; i++) {
      const a = (i / AZ) * Math.PI * 2, p = point(r * Math.cos(a), r * Math.sin(a), up);
      pos.push(p.x, p.y, p.z);
      uv.push(i / AZ, t);
    }
  }
  for (let j = 0; j < EL; j++)
    for (let i = 0; i < AZ; i++) {
      const angle = (i + 0.5) / AZ * Math.PI * 2;
      const bottom = height * Math.sin(j / EL * Math.PI / 2);
      if (portals.some(p => bottom < p.height &&
        Math.abs(Math.atan2(Math.sin(angle - p.angle), Math.cos(angle - p.angle))) * radius < p.width / 2)) continue;
      const a = j * (AZ + 1) + i, b = a + 1, c = a + AZ + 1, d = c + 1;
      idx.push(a, c, b, b, c, d);
    }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("aUV", new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  const dome = new THREE.Mesh(geo, glassMaterial(uniforms));
  dome.renderOrder = 3;
  dome.matrixAutoUpdate = false;
  return dome;
}

export function glassMaterial(uniforms) {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide, uniforms:{uStructure:{value:1},uGlare:{value:1},...uniforms},
    vertexShader: `attribute vec2 aUV; varying vec2 vUV; varying vec3 vN, vW, vC;
      void main(){ vUV=aUV; vN=normalize(mat3(modelMatrix)*normal); vec4 w=modelMatrix*vec4(position,1.0); vW=w.xyz;
        vC=(modelMatrix*vec4(0.,0.,0.,1.)).xyz; gl_Position=projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `uniform float uStructure,uGlare; uniform vec3 uSun; varying vec2 vUV; varying vec3 vN, vW, vC;
      void main(){ vec3 n=normalize(vN); vec3 v=normalize(cameraPosition-vW); if(dot(n,v)<0.0) n=-n;
        vec3 s=normalize(uSun); float day=smoothstep(-0.12,0.25,dot(normalize(vW-vC),s));
        float u=vUV.x*96.0, w=vUV.y*28.0;
        float l1=abs(fract(u+w*0.5)-0.5), l2=abs(fract(u-w*0.5)-0.5), l3=abs(fract(w)-0.5)*1.7;
        float frame=1.0-smoothstep(0.012,0.035,min(min(l1,l2),l3));
        frame*=uStructure;
        float base=smoothstep(0.035,0.0,vUV.y);
        float fres=pow(1.0-abs(dot(n,v)),3.0);
        float spec=pow(max(dot(reflect(-s,n),v),0.0),300.0)*day*2.5*uGlare;
        float glint=pow(max(dot(reflect(-s,n),v),0.0),18.0)*day*0.25;
        vec3 glass=mix(vec3(0.55,0.72,0.82), vec3(0.85,0.93,1.0), fres)*(0.25+0.75*day);
        vec3 steel=vec3(0.30,0.33,0.36)*(0.35+0.65*max(dot(n,s),0.0)*day+0.15);
        vec3 col=mix(glass, steel, max(frame,base))+vec3(1.0,0.97,0.9)*(spec+glint);
        float a=mix(0.05+0.42*fres+spec, 0.92, max(frame*0.85,base));
        col+=vec3(1.0,0.78,0.5)*0.08*(1.0-day)*(1.0-vUV.y);
        gl_FragColor=vec4(col, clamp(a,0.0,1.0)); }`,
  });
}

export function buildDome() {
  const rim = surfaceHeight(DOME_R, 0);
  const dome = makeDome((x, y, up) => sph(x, y, rim + up - surfaceHeight(x, y) - 0.5), DOME_R, DOME_H, state.envUniforms);
  state.world.add(dome);
  state.dome = dome;
}

// 3 m cells; 1 = taken by a road, a house or a building
function freeGround() {
  const G = state.G, c = G.cfg, size = 3, half = 760, n = Math.ceil((2 * half) / size);
  const taken = new Uint8Array(n * n);
  const mark = (x, y, r) => {
    const i0 = Math.max(0, Math.floor((x - r + half) / size)), i1 = Math.min(n - 1, Math.floor((x + r + half) / size));
    const j0 = Math.max(0, Math.floor((y - r + half) / size)), j1 = Math.min(n - 1, Math.floor((y + r + half) / size));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
      const cx = i * size - half + size / 2, cy = j * size - half + size / 2;
      if ((cx - x) ** 2 + (cy - y) ** 2 <= r * r) taken[j * n + i] = 1;
    }
  };
  for (const road of G.layout?.roads || []) {
    const w = (road.width || 10) / 2 + 2;
    for (let k = 1; k < road.points.length; k++) {
      const [x0, y0] = road.points[k - 1], [x1, y1] = road.points[k], L = Math.hypot(x1 - x0, y1 - y0);
      for (let d = 0; d <= L; d += size) mark(x0 + ((x1 - x0) * d) / L, y0 + ((y1 - y0) * d) / L, w);
    }
  }
  for (let i = 0; i < G.houses.x.length; i++) mark(G.houses.x[i], G.houses.y[i], 11);
  for (const name of ["garage", "medlab", "school"]) {
    if (!c[name]) continue;
    const [a, r] = c[name], t = (a * Math.PI) / 180;
    mark(r * Math.cos(t), r * Math.sin(t), 34);
  }
  const free = (x, y, r = 0) => {
    const d = Math.hypot(x, y);
    if (d < c.hub_radius + 12 || d > c.wall_radius - 14) return false;
    for (const [ox, oy] of r ? [[0, 0], [r, 0], [-r, 0], [0, r], [0, -r]] : [[0, 0]]) {
      const i = Math.floor((x + ox + half) / size), j = Math.floor((y + oy + half) / size);
      if (i < 0 || j < 0 || i >= n || j >= n || taken[j * n + i]) return false;
    }
    return true;
  };
  return { free, mark };
}

export function buildOasis(steps) {
  const u = state.envUniforms, rand = rng(1979);
  let ground;
  const spot = (r = 0, tries = 60) => {
    for (let k = 0; k < tries; k++) {
      const d = Math.sqrt(rand()) * 690, a = rand() * Math.PI * 2, x = d * Math.cos(a), y = d * Math.sin(a);
      if (ground.free(x, y, r)) return [x, y];
    }
    return null;
  };
  // ponds and the giant trees first: they need the most room
  steps.push(() => {
    ground = freeGround();
    const ponds = [], giants = [], vines = [];
    for (let k = 0; k < 34; k++) {
      const p = spot(16);
      if (!p) continue;
      const r = 8 + rand() * 12;
      ponds.push([...p, r]);
      ground.mark(p[0], p[1], r + 3);
    }
    for (let k = 0; k < 90; k++) {
      const p = spot(9);
      if (!p) continue;
      const s = 6 + rand() * 4, h = surfaceHeight(...p);
      giants.push({ n: dirOf(...p), h: h - 0.4, s, tint: [0.85 + rand() * 0.2, 0.95 + rand() * 0.1, 0.85] });
      ground.mark(p[0], p[1], 8);
      for (let v = 0; v < 14; v++) {                     // vines hang from the crown
        const a = rand() * Math.PI * 2, d = s * (0.6 + rand() * 1.2);
        const x = p[0] + Math.cos(a) * d, y = p[1] + Math.sin(a) * d;
        vines.push({ n: dirOf(x, y), h: h + s * (3.6 + rand() * 0.8), s: s * (0.9 + rand() * 0.8), sy: -1.6, tint: [0.7, 0.95, 0.6] });
      }
    }
    // ponds: a disc of water each, the bed sloping to two metres
    const pos = [], depth = [], idx = [];
    for (const [x, y, r] of ponds) {
      const base = pos.length / 3, h = surfaceHeight(x, y);
      for (let ring = 0; ring <= 6; ring++)
        for (let s = 0; s < 32; s++) {
          const a = (s / 32) * Math.PI * 2, rr = (r * ring) / 6 * (1 + 0.08 * Math.sin(a * 3 + x));
          const p = sph(x + rr * Math.cos(a), y + rr * Math.sin(a), h - 0.35 - surfaceHeight(x + rr * Math.cos(a), y + rr * Math.sin(a)));
          pos.push(p.x, p.y, p.z);
          depth.push(2.2 * (1 - (ring / 6) ** 2) - 0.05);
        }
      for (let ring = 0; ring < 6; ring++)
        for (let s = 0; s < 32; s++) {
          const a = base + ring * 32 + s, b = base + ring * 32 + ((s + 1) % 32);
          idx.push(a, a + 32, b, b, a + 32, b + 32);
        }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("aDepth", new THREE.Float32BufferAttribute(depth, 1));
    g.setAttribute("aLiquid", new THREE.Float32BufferAttribute(new Float32Array(depth.length).fill(1), 1));
    g.setAttribute("aWarm", new THREE.Float32BufferAttribute(new Float32Array(depth.length), 1));
    g.setIndex(idx);
    const pondMesh = new THREE.Mesh(g, waterMaterial(u, { tint: [0.06, 0.28, 0.22] }));
    pondMesh.renderOrder = 2;
    state.world.add(pondMesh);
    state.world.add(instances(treeGeometry("broad"), lifeMaterial(u, { indoor: 1, sway: 0.0015 }), giants, state.RP));
    state.world.add(instances(tuftGeometry(0x1f3d17, 0x6fa046), lifeMaterial(u, { indoor: 1, sway: 0.02 }), vines, state.RP));
  });
  // trees and shrubs along every free strip, then lawns and flowerbeds in what is left
  steps.push(()=>buildPublicSpace(ground));
  steps.push(() => {
    const trees = [], pines = [], shrubs = [];
    for (let k = 0; k < 9000 && trees.length + pines.length < 2400; k++) {
      const p = spot(2.5, 4);
      if (!p) continue;
      const item = { n: dirOf(...p), h: surfaceHeight(...p) - 0.2, s: 2.2 + rand() * 1.8, tint: [0.85 + rand() * 0.3, 0.9 + rand() * 0.2, 0.8 + rand() * 0.2] };
      (rand() < 0.65 ? trees : pines).push(item);
      ground.mark(p[0], p[1], 4);
    }
    for (let k = 0; k < 9000 && shrubs.length < 3200; k++) {
      const p = spot(0, 3);
      if (!p) continue;
      shrubs.push({ n: dirOf(...p), h: surfaceHeight(...p) - 0.6, s: 0.45 + rand() * 0.45, sy: 0.6, tint: [0.8 + rand() * 0.3, 0.95, 0.7] });
    }
    state.world.add(instances(treeGeometry("broad"), lifeMaterial(u, { indoor: 1, sway: 0.004 }), trees, state.RP));
    state.world.add(instances(treeGeometry("pine"), lifeMaterial(u, { indoor: 1, sway: 0.004 }), pines, state.RP));
    state.world.add(instances(treeGeometry("broad"), lifeMaterial(u, { indoor: 1, sway: 0.01 }), shrubs, state.RP));
  });
  steps.push(() => {
    const grass = [], flowers = [];
    const COLORS = [[1.6, 0.6, 1.1], [1.7, 1.5, 0.4], [1.2, 0.8, 1.7], [1.8, 1.8, 1.8], [1.8, 0.7, 0.5]];
    for (let k = 0; k < 140000 && grass.length < 48000; k++) {
      const p = spot(0, 1);
      if (!p) continue;
      const h = surfaceHeight(...p);
      grass.push({ n: dirOf(...p), h: h - 0.05, s: 0.5 + rand() * 0.8, tint: [0.85 + rand() * 0.3, 0.9 + rand() * 0.25, 0.8] });
      if (rand() < 0.22) {                                // flowerbeds come in clumps of one colour
        const col = COLORS[Math.floor(Math.abs(Math.sin(p[0] * 0.013 + p[1] * 0.017)) * COLORS.length) % COLORS.length];
        for (let f = 0; f < 3; f++) {
          const x = p[0] + (rand() - 0.5) * 2.5, y = p[1] + (rand() - 0.5) * 2.5;
          flowers.push({ n: dirOf(x, y), h: h - 0.03, s: 0.45 + rand() * 0.35, tint: col });
        }
      }
    }
    state.world.add(instances(tuftGeometry(0x2a4d1c, 0x8cc456), lifeMaterial(u, { indoor: 1, sway: 0.16 }), grass, state.RP));
    state.world.add(instances(tuftGeometry(0x2a4d1c, 0xffffff), lifeMaterial(u, { indoor: 1, sway: 0.16, glow: 0.05 }), flowers, state.RP));
    // a gravel path loops through the park around the hub
    const pts = [], pos = [], idx = [];
    for (let k = 0; k <= 720; k++) {
      const a = (k / 720) * Math.PI * 2, r = 205 + 14 * Math.sin(a * 5) + 6 * Math.sin(a * 13);
      pts.push([r * Math.cos(a), r * Math.sin(a)]);
    }
    pts.forEach(([x, y], k) => {
      const [nx, ny] = [x / Math.hypot(x, y), y / Math.hypot(x, y)];
      for (const side of [-1.6, 1.6]) {
        const p = sph(x + nx * side, y + ny * side, 0.06);
        pos.push(p.x, p.y, p.z);
      }
      if (k < pts.length - 1) idx.push(2 * k, 2 * k + 2, 2 * k + 1, 2 * k + 1, 2 * k + 2, 2 * k + 3);
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    g.computeVertexNormals();
    const path = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: 0x8b8274, roughness: 1, polygonOffset: true, polygonOffsetFactor: -2 }));
    path.receiveShadow = true;
    state.world.add(path);
  });
}
