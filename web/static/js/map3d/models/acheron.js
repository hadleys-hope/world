/** models/acheron: LV-426 outside the wall comes alive. Frozen seas and lakes, open rivers, hot springs in the
 * valleys with steam, moss and frost pines around them, boulders on the slopes, ice crystals on the ranges.
 * Built after the first frame, in small steps, so the colony shows up first. */
import { state } from "../state.js";
import { WATER_LEVEL } from "../geometry/noise.js";
import { normalXY, surfaceHeight, wildXY } from "../geometry/planet.js";
import { buildWater } from "./waters.js";
import { crystalGeometry, hotSprings, instances, lifeMaterial, rockGeometry, treeGeometry, tuftGeometry } from "./life.js";
import * as THREE from "three";

// A small deterministic generator, so the forest is the same on every load.
function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = Math.imul(s ^ (s >>> 15), 2246822507) + 0x9e3779b9) >>> 0) / 4294967296;
}
const dirOf = (x, y) => {
  const a = Math.hypot(x, y) / state.RP, p = Math.atan2(y, x), s = Math.sin(a);
  return [s * Math.cos(p), Math.cos(a), s * Math.sin(p)];
};
const ground = (x, y) => surfaceHeight(x, y);

function findVents(rand) {
  const vents = [];
  for (let tries = 0; tries < 4000 && vents.length < 9; tries++) {
    const d = 3600 + rand() * 6200, a = rand() * Math.PI * 2;
    const x = d * Math.cos(a), y = d * Math.sin(a), h = ground(x, y);
    if (h < 2 || h > 70) continue;                                        // valley floors, above the ice
    const slope = Math.abs(ground(x + 20, y) - h) + Math.abs(ground(x, y + 20) - h);
    if (slope > 6) continue;
    if (vents.some((v) => Math.hypot(v.x - x, v.y - y) < 1300)) continue;
    vents.push({ x, y, h, r: 10 + rand() * 12 });
  }
  return vents;
}

export function buildAcheronLife(steps) {
  const u = state.envUniforms;
  const rand = rng(426);
  const vents = findVents(rand);
  state.vents = vents;
  // 1. water: frozen seas and lakes, open where rivers run or springs warm it
  steps.push(() => {
    const water = buildWater({
      radius: state.RP + WATER_LEVEL, res: 448, uniforms: u, tint: [0.04, 0.28, 0.34],
      sample(nx, ny, nz) {
        const [x, y] = normalXY(new THREE.Vector3(nx, ny, nz));
        const h = ground(x, y), depth = WATER_LEVEL - h;
        if (depth < -2) return { depth };
        const far = Math.hypot(x, y) > 3000 ? wildXY(x, y).river : 0;
        let warm = 0;
        for (const v of vents) warm = Math.max(warm, 1 - Math.min(1, Math.hypot(v.x - x, v.y - y) / 420));
        return { depth, liquid: Math.min(1, far * 1.6 + warm * 1.4), warm };
      },
    });
    if (state.seaSphere) state.seaSphere.visible = false;
    state.scene.add(water);
    state.acheronWater = water;
  });
  // 2. hot springs and their steam
  steps.push(() => {
    const items = vents.map((v) => ({ n: dirOf(v.x, v.y), h: v.h, r: v.r }));
    for (const o of hotSprings(items, state.RP, u)) state.world.add(o);
  });
  // 3. moss around the springs, thinning out with distance
  steps.push(() => {
    const tufts = [];
    for (const v of vents)
      for (let k = 0; k < 3200; k++) {
        const d = v.r + 4 + Math.pow(rand(), 1.7) * 230, a = rand() * Math.PI * 2;
        const x = v.x + d * Math.cos(a), y = v.y + d * Math.sin(a), h = ground(x, y);
        if (h < WATER_LEVEL + 0.5) continue;
        const heat = 1 - d / 240;
        tufts.push({ n: dirOf(x, y), h: h - 0.05, s: 0.6 + heat * 1.4 + rand() * 0.5, tint: [0.8 + heat * 0.4, 0.9 + heat * 0.2, 0.7 + rand() * 0.2] });
      }
    state.world.add(instances(tuftGeometry(0x2d3f1c, 0xc9d36a), lifeMaterial(u, { sway: 0.12, glow: 0.12 }), tufts, state.RP));
  });
  // 4. frost pines around the springs and along the rivers
  steps.push(() => {
    const trees = [];
    for (const v of vents)
      for (let k = 0; k < 340; k++) {
        const d = v.r + 25 + Math.pow(rand(), 1.2) * 420, a = rand() * Math.PI * 2;
        const x = v.x + d * Math.cos(a), y = v.y + d * Math.sin(a), h = ground(x, y);
        if (h < WATER_LEVEL + 1 || h > 140) continue;
        trees.push({ n: dirOf(x, y), h: h - 0.2, s: 1.4 + rand() * 1.6 * (1 - d / 520), tint: [0.9 + rand() * 0.2, 1, 1] });
      }
    for (let k = 0; trees.length < 4200 && k < 40000; k++) {
      const d = 3400 + rand() * 7000, a = rand() * Math.PI * 2;
      const x = d * Math.cos(a), y = d * Math.sin(a), w = wildXY(x, y), h = ground(x, y);
      if (w.river < 0.05 || w.river > 0.7 || h < WATER_LEVEL + 1 || h > 90) continue;   // river banks
      trees.push({ n: dirOf(x, y), h: h - 0.2, s: 1.2 + rand() * 1.4, tint: [1, 1, 1] });
    }
    state.world.add(instances(treeGeometry("frost"), lifeMaterial(u, { sway: 0.006 }), trees, state.RP));
  });
  // 5. boulders on every slope outside the wall, ice crystals on the high ranges
  steps.push(() => {
    const rocks = [], crystals = [];
    for (let k = 0; k < 60000 && (rocks.length < 3500 || crystals.length < 1600); k++) {
      const d = 1100 + rand() * 11000, a = rand() * Math.PI * 2;
      const x = d * Math.cos(a), y = d * Math.sin(a), h = ground(x, y);
      if (h < WATER_LEVEL + 0.5) continue;
      if (h > 170 && crystals.length < 1600) crystals.push({ n: dirOf(x, y), h: h - 0.4, s: 2 + rand() * 5, tint: [0.9, 0.95 + rand() * 0.1, 1] });
      else if (rocks.length < 3500 && (d > 1500 || rand() < 0.2)) {
        const g = 0.75 + rand() * 0.4;
        rocks.push({ n: dirOf(x, y), h: h - 0.3, s: 0.8 + Math.pow(rand(), 3) * 9, sy: 0.7 + rand() * 0.6, tint: [g, g, g * 1.04] });
      }
    }
    state.world.add(instances(rockGeometry(), lifeMaterial(u), rocks, state.RP));
    state.world.add(instances(crystalGeometry(), lifeMaterial(u, { glow: 0.35 }), crystals, state.RP));
  });
}

/** Below the crust: a molten core, so a camera that slips under the ground never looks into an empty shell. */
export function makeCore(radius, uniforms) {
  return new THREE.Mesh(
    new THREE.SphereGeometry(radius, 64, 48),
    new THREE.ShaderMaterial({
      side: THREE.DoubleSide, uniforms,
      vertexShader: `varying vec3 vP; void main(){ vP=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
      fragmentShader: `uniform float uTime; varying vec3 vP;
        float h(vec3 p){ return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453); }
        void main(){ vec3 p=normalize(vP)*9.0; float n=fract(sin(dot(floor(p),vec3(12.9,78.2,37.7)))*43758.5);
          float veins=smoothstep(0.92,1.0,sin(p.x*3.1+uTime*0.2)*sin(p.y*2.7)*sin(p.z*3.3)+0.25*n);
          vec3 rock=vec3(0.08,0.05,0.04)*(0.6+0.8*h(floor(vP*0.05)));
          gl_FragColor=vec4(rock+vec3(1.0,0.38,0.08)*veins*1.4,1.0); }`,
    }),
  );
}
