/** models/worlds: the other bodies get real relief and climate instead of a painted ball.
 * Hephaestus: volcanoes, glowing lava cracks, acid cyclones. Russet: dune seas, mesas, craters, a ring and
 * dust storms. Klyaksa, the new colony: continents in a clear ocean, beaches, meadows, forests, snow peaks,
 * clouds. Each body is upgraded after the first frame, one idle step at a time. */
import { state } from "../state.js";
import { bodyHeight, GLSL_NOISE } from "../geometry/noise.js";
import { buildWater } from "./waters.js";
import { waterMaterial } from "./waters.js";
import { buildKlyaksa, dirAt, klyaksaSites, loadKlyaksa } from "./klyaksa.js";
import * as THREE from "three";

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = Math.imul(s ^ (s >>> 15), 2246822507) + 0x9e3779b9) >>> 0) / 4294967296;
}
const randomDir = (rand) => {
  const z = rand() * 2 - 1, a = rand() * Math.PI * 2, r = Math.sqrt(1 - z * z);
  return [r * Math.cos(a), z, r * Math.sin(a)];
};

const SURFACE = {
  0: `vec3 basalt=mix(vec3(0.07,0.05,0.05), vec3(0.22,0.17,0.14), d); vec3 ash=vec3(0.36,0.33,0.30);
      vec3 col=mix(basalt, ash, smoothstep(0.35,0.75,vH+0.2*d));
      col=mix(col, vec3(0.62,0.55,0.18), smoothstep(0.62,0.7,n3(p*6.0))*0.5);                       // sulfur fields
      float crack=1.0-smoothstep(0.0,0.045,abs(n3(p*16.0+vec3(0.,uTime*0.002,0.))-0.5));
      vec3 glow=vec3(1.0,0.42,0.08)*(crack*(1.0-smoothstep(0.15,0.45,vH)) + smoothstep(0.86,0.97,vH)*1.5);`,
  1: `vec3 sand=mix(vec3(0.46,0.22,0.10), vec3(0.78,0.48,0.26), d);
      vec3 col=mix(sand, vec3(0.30,0.15,0.09), smoothstep(0.55,0.75,vH));                             // mesas
      col=mix(col, vec3(0.20,0.10,0.07), smoothstep(0.2,0.0,vH));                                       // crater floors
      vec3 glow=vec3(0.0);`,
  3: `float sea=step(vH,0.0);
      vec3 sand=vec3(0.80,0.74,0.55), grass=mix(vec3(0.20,0.45,0.17), vec3(0.42,0.58,0.22), d), forest=vec3(0.09,0.26,0.10);
      vec3 rock=mix(vec3(0.35,0.33,0.30), vec3(0.52,0.50,0.47), d), snow=vec3(0.92,0.95,0.98);
      vec3 col=mix(sand, grass, smoothstep(0.02,0.06,vH));
      col=mix(col, forest, smoothstep(0.45,0.6,n3(p*5.0))*smoothstep(0.06,0.12,vH)*(1.0-smoothstep(0.45,0.6,vH)));
      col=mix(col, rock, smoothstep(0.5,0.7,vH)); col=mix(col, snow, smoothstep(0.78,0.86,vH+0.1*d));
      col=mix(col, mix(vec3(0.55,0.5,0.36), vec3(0.08,0.16,0.2), smoothstep(0.0,-0.4,vH)), sea);    // sea floor
      vec3 glow=vec3(0.0);`,
};

const PATCH = 11500;   // metres: the fine-grained land around Klyaksa's colony

function surfaceMesh(spec, uniforms) {
  const R = spec.radius, geo = new THREE.SphereGeometry(R, 320, 240), pos = geo.attributes.position;
  const centre = spec.kind === 3 ? dirAt(0, 0, R) : null;
  const hs = new Float32Array(pos.count);
  let lo = 1e9, hi = -1e9;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i) / R, y = pos.getY(i) / R, z = pos.getZ(i) / R;
    const h = bodyHeight(spec.kind, x, y, z);
    hs[i] = h; lo = Math.min(lo, h); hi = Math.max(hi, h);
    const sink = centre && centre.angleTo(new THREE.Vector3(x, y, z)) < (PATCH * 0.98) / R ? 25 / R : 0;
    pos.setXYZ(i, x * R * (1 + h - sink), y * R * (1 + h - sink), z * R * (1 + h - sink));
  }
  // aH: 0..1 across the body's height range; on Klyaksa 0 is the sea level, below it negative
  const aH = new Float32Array(pos.count);
  for (let i = 0; i < pos.count; i++) aH[i] = spec.kind === 3 ? hs[i] / Math.max(1e-6, hi) : (hs[i] - lo) / (hi - lo);
  geo.setAttribute("aH", new THREE.BufferAttribute(aH, 1));
  geo.computeVertexNormals();
  const mat = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: `attribute float aH; varying vec3 vN, vP, vW; varying float vH;
      void main(){ vN=normalize(mat3(modelMatrix)*normal); vP=position; vH=aH; vec4 w=modelMatrix*vec4(position,1.0); vW=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `uniform float uTime, uKind; uniform vec3 uLight; varying vec3 vN, vP, vW; varying float vH;
      ${GLSL_NOISE}
      void main(){ vec3 p=normalize(vP); float d=fbm(p*40.0)*0.5+n3(vW*0.08)*0.25+n3(vW*0.7)*0.15+n3(vW*4.0)*0.1;
        ${SURFACE[spec.kind]}
        vec3 n=normalize(vN); float light=max(dot(n,normalize(uLight)),0.0);
        float rim=pow(1.0-max(dot(n,normalize(cameraPosition-vW)),0.0),3.0);
        gl_FragColor=vec4(col*(0.07+0.93*light)+glow+rim*0.12*col, 1.0); }`,
  });
  mat.userData.hi = hi;
  const mesh = new THREE.Mesh(geo, mat);
  mesh.matrixAutoUpdate = false;
  return mesh;
}

/** Klyaksa around the colony: a fine cap (about 20 m between vertices) with the same material, and its water. */
function klyaksaPatch(spec, material, uniforms) {
  const R = spec.radius, rings = 240, segs = 480, hi = material.userData.hi;
  const pos = [], aH = [], depth = [], idx = [];
  for (let r = 0; r <= rings; r++)
    for (let k = 0; k < segs; k++) {
      const d = (PATCH * r) / rings, a = (k / segs) * Math.PI * 2;
      const v = dirAt(Math.cos(a) * d, Math.sin(a) * d, R), h = bodyHeight(3, v.x, v.y, v.z);
      pos.push(...v.clone().multiplyScalar(R * (1 + h)).toArray());
      aH.push(h / hi);
      depth.push(-h * R);
    }
  for (let r = 0; r < rings; r++)
    for (let k = 0; k < segs; k++) {
      const a = r * segs + k, b = r * segs + ((k + 1) % segs), c = a + segs, d = b + segs;
      idx.push(a, c, b, b, c, d);
    }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("aH", new THREE.Float32BufferAttribute(aH, 1));
  g.setIndex(idx);
  g.computeVertexNormals();
  const land = new THREE.Mesh(g, material);
  state.klyaksaGroundAt = groundSampler(g, R, rings, segs, PATCH);
  // water on the same grid, only the cells that are wet
  const widx = [];
  for (let t = 0; t < idx.length; t += 3)
    if (Math.max(depth[idx[t]], depth[idx[t + 1]], depth[idx[t + 2]]) > -0.5) widx.push(idx[t], idx[t + 1], idx[t + 2]);
  const wg = new THREE.BufferGeometry();
  const wpos = pos.map((v, i) => v);                                     // water lies on the sphere of radius R
  for (let i = 0; i < wpos.length; i += 3) {
    const L = Math.hypot(wpos[i], wpos[i + 1], wpos[i + 2]);
    wpos[i] *= R / L; wpos[i + 1] *= R / L; wpos[i + 2] *= R / L;
  }
  wg.setAttribute("position", new THREE.Float32BufferAttribute(wpos, 3));
  wg.setAttribute("aDepth", new THREE.Float32BufferAttribute(depth, 1));
  wg.setAttribute("aLiquid", new THREE.Float32BufferAttribute(new Float32Array(depth.length).fill(1), 1));
  wg.setAttribute("aWarm", new THREE.Float32BufferAttribute(new Float32Array(depth.length), 1));
  wg.setIndex(widx);
  const water = new THREE.Mesh(wg, waterMaterial(uniforms, { tint: [0.03, 0.30, 0.42] }));
  water.renderOrder = 2;
  return [land, water];
}

function cloudLayer(R, uniforms, kind) {
  const look = {
    0: `vec3 c=vec3(0.85,0.72,0.32); float sw=atan(p.z,p.x)*3.0+length(p.xz)*8.0; float a=smoothstep(0.52,0.75,fbm(p*4.0+vec3(sin(sw+uTime*0.02),0.,0.)*0.6+uTime*0.003))*0.75;`,
    1: `vec3 c=vec3(0.78,0.52,0.30); float a=smoothstep(0.58,0.8,fbm(p*3.0+vec3(uTime*0.006,0.,0.)))*0.55;`,
    3: `vec3 c=vec3(1.0); float a=smoothstep(0.55,0.78,fbm(p*3.4+vec3(uTime*0.004,0.,uTime*0.002)))*0.85;`,
  }[kind];
  return new THREE.Mesh(
    new THREE.SphereGeometry(R, 128, 96),
    new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, uniforms,
      vertexShader: `varying vec3 vP, vN; void main(){ vP=position; vN=normalize(mat3(modelMatrix)*normal); gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
      fragmentShader: `uniform float uTime; uniform vec3 uLight; varying vec3 vP, vN; ${GLSL_NOISE}
        void main(){ vec3 p=normalize(vP); ${look} float l=max(dot(normalize(vN),normalize(uLight)),0.0);
          gl_FragColor=vec4(c*(0.12+0.88*l), a); }`,
    }),
  );
}

function ring(R, uniforms) {
  const mesh = new THREE.Mesh(
    new THREE.RingGeometry(R * 1.45, R * 2.5, 192, 1),
    new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, side: THREE.DoubleSide, uniforms: { ...uniforms, uR: { value: R } },
      vertexShader: `varying vec3 vP; void main(){ vP=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
      fragmentShader: `uniform float uR; varying vec3 vP; ${GLSL_NOISE}
        void main(){ float r=length(vP.xy)/uR; float bands=n3(vec3(r*60.0,0.,0.))*0.6+n3(vec3(r*230.0,1.,0.))*0.4;
          float gap=smoothstep(0.02,0.0,abs(r-1.95))+smoothstep(0.015,0.0,abs(r-2.2));
          float a=smoothstep(1.45,1.55,r)*smoothstep(2.5,2.3,r)*(0.25+0.6*bands)*(1.0-gap*0.9);
          gl_FragColor=vec4(mix(vec3(0.62,0.45,0.32),vec3(0.86,0.76,0.62),bands), a); }`,
    }),
  );
  mesh.rotation.x = Math.PI / 2 - 0.42;
  mesh.rotation.y = 0.3;
  return mesh;
}

export function upgradeWorlds(steps) {
  loadKlyaksa();
  [0, 1, 3].forEach((i) => {
    const step = () => {
      const ss = state.solarSystem;
      if (!ss) return;
      const body = ss.bodies[i], spec = ss.specs[i], old = body.userData.surface;
      if (i === 3 && state.klyaksaPlanData === undefined) {
        // not here yet: ask once, and come back to this step when the plan has arrived
        if (!state.klyaksaWaiting) state.klyaksaWaiting = klyaksaSites(spec.radius).then((p) => (state.klyaksaPlanData = p || null));
        steps.push(step);
        return;
      }
      const u = { uTime: old.uniforms.uTime, uKind: old.uniforms.uKind, uLight: old.uniforms.uLight };
      const mesh = surfaceMesh(spec, u);
      const flat = body.children.find((c) => c.material === old);
      if (flat) { body.remove(flat); flat.geometry.dispose(); }
      body.add(mesh);
      body.userData.surface = mesh.material;
      const R = spec.radius;
      body.add(cloudLayer(R * (i === 0 ? 1.06 : 1.03), { uTime: u.uTime, uLight: u.uLight }, spec.kind));
      if (i === 1) body.add(ring(R, { uTime: u.uTime }));
      if (i === 3) klyaksaLife(steps, body, spec, mesh.material);
    };
    steps.push(step);
  });
}

// Klyaksa: the ocean, the fine land around the colony, then its cities and valleys
function klyaksaLife(steps, body, spec, material) {
  const R = spec.radius, u = material.uniforms, env = { uTime: u.uTime, uSun: u.uLight };
  const centre = dirAt(0, 0, R);
  steps.push(() => {
    body.add(buildWater({
      radius: R, res: 448, uniforms: env, tint: [0.03, 0.30, 0.42],
      sample: (x, y, z) => (centre.angleTo(new THREE.Vector3(x, y, z)) < (PATCH * 0.97) / R ? { depth: -5 } : { depth: -bodyHeight(3, x, y, z) * R, liquid: 1, warm: 0 }),
    }));
  });
  steps.push(() => { for (const m of klyaksaPatch(spec, material, env)) body.add(m); });
  if (state.klyaksaPlanData) {
    state.klyaksaLod = [];
    buildKlyaksa(steps, body, R, u);
  }
}

/** Height on the rendered triangle, including the sphere chord between terrain vertices. */
export function groundSampler(geometry, R, rings, segs, reach) {
  const ray = new THREE.Ray(new THREE.Vector3(), new THREE.Vector3());
  const A = new THREE.Vector3(), B = new THREE.Vector3();
  const C = new THREE.Vector3(), D = new THREE.Vector3(), hit = new THREE.Vector3();
  const positions = geometry.attributes.position;
  return (X, Y) => {
    const d = Math.hypot(X, Y), n = dirAt(X, Y, R);
    if (d >= reach) return bodyHeight(3, n.x, n.y, n.z) * R;
    const row = Math.min(rings - 1, Math.floor(d / reach * rings));
    const angle = (Math.atan2(Y, X) + Math.PI * 2) % (Math.PI * 2);
    const col = Math.floor(angle / (Math.PI * 2) * segs);
    ray.direction.copy(n);
    // Straight triangle edges deviate slightly from polar ring boundaries.
    // Probe adjacent rows at seams, rather than falling back to the noise height.
    for (const offset of [0, 1, -1]) {
      const r = row + offset;
      if (r < 0 || r >= rings) continue;
      const a = r * segs + col, b = r * segs + (col + 1) % segs;
      A.fromBufferAttribute(positions, a); B.fromBufferAttribute(positions, b);
      C.fromBufferAttribute(positions, a + segs); D.fromBufferAttribute(positions, b + segs);
      if (ray.intersectTriangle(A, C, B, false, hit) || ray.intersectTriangle(B, C, D, false, hit))
        return hit.length() - R;
    }
    return bodyHeight(3, n.x, n.y, n.z) * R;
  };
}
