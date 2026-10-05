/** models/worlds: the other bodies get real relief and climate instead of a painted ball.
 * Hephaestus: volcanoes, glowing lava cracks, acid cyclones. Russet: dune seas, mesas, craters, a ring and
 * dust storms. Klyaksa, the new colony: continents in a clear ocean, beaches, meadows, forests, snow peaks,
 * clouds. Each body is upgraded after the first frame, one idle step at a time. */
import { state } from "../state.js";
import { bodyHeight, fbm3, GLSL_NOISE } from "../geometry/noise.js";
import { buildWater } from "./waters.js";
import { instances, lifeMaterial, treeGeometry, tuftGeometry } from "./life.js";
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

function surfaceMesh(spec, uniforms) {
  const R = spec.radius, geo = new THREE.SphereGeometry(R, 320, 240), pos = geo.attributes.position;
  const hs = new Float32Array(pos.count);
  let lo = 1e9, hi = -1e9;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i) / R, y = pos.getY(i) / R, z = pos.getZ(i) / R;
    const h = bodyHeight(spec.kind, x, y, z);
    hs[i] = h; lo = Math.min(lo, h); hi = Math.max(hi, h);
    pos.setXYZ(i, x * R * (1 + h), y * R * (1 + h), z * R * (1 + h));
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
      void main(){ vec3 p=normalize(vP); float d=fbm(p*40.0)*0.7+n3(vW*0.08)*0.3;
        ${SURFACE[spec.kind]}
        vec3 n=normalize(vN); float light=max(dot(n,normalize(uLight)),0.0);
        float rim=pow(1.0-max(dot(n,normalize(cameraPosition-vW)),0.0),3.0);
        gl_FragColor=vec4(col*(0.07+0.93*light)+glow+rim*0.12*col, 1.0); }`,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.matrixAutoUpdate = false;
  return mesh;
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
  [0, 1, 3].forEach((i) => {
    steps.push(() => {
      const ss = state.solarSystem;
      if (!ss) return;
      const body = ss.bodies[i], spec = ss.specs[i], old = body.userData.surface;
      const u = { uTime: old.uniforms.uTime, uKind: old.uniforms.uKind, uLight: old.uniforms.uLight };
      const mesh = surfaceMesh(spec, u);
      const flat = body.children.find((c) => c.material === old);
      if (flat) { body.remove(flat); flat.geometry.dispose(); }
      body.add(mesh);
      body.userData.surface = mesh.material;
      const R = spec.radius;
      body.add(cloudLayer(R * (i === 0 ? 1.06 : 1.03), { uTime: u.uTime, uLight: u.uLight }, spec.kind));
      if (i === 1) body.add(ring(R, { uTime: u.uTime }));
    });
  });
  // Klyaksa: the ocean, the forests and the meadows of the landing coast
  steps.push(() => {
    const ss = state.solarSystem;
    if (!ss) return;
    const body = ss.bodies[3], spec = ss.specs[3], R = spec.radius, u = body.userData.surface.uniforms;
    const env = { uTime: u.uTime, uSun: u.uLight };
    body.add(buildWater({
      radius: R, res: 320, uniforms: env, tint: [0.03, 0.30, 0.42],
      sample: (x, y, z) => ({ depth: -bodyHeight(3, x, y, z) * R, liquid: 1, warm: 0 }),
    }));
    const rand = rng(77), trees = [], tufts = [];
    for (let k = 0; k < 120000 && trees.length < 9000; k++) {
      const n = randomDir(rand), h = bodyHeight(3, ...n);
      if (h < 0.0012 || h > 0.016) continue;
      if (fbm3(n[0] * 5, n[1] * 5, n[2] * 5, 3) < 0.02) continue;                   // forests come in patches
      trees.push({ n, h: h * R - 0.3, s: 2.2 + rand() * 2.2, tint: [0.85 + rand() * 0.3, 0.9 + rand() * 0.2, 0.85] });
    }
    const site = [-0.66, 0.32, -0.68];                                               // the landing coast
    for (let k = 0; k < 80000 && tufts.length < 16000; k++) {
      const n = randomDir(rand);
      if (n[0] * site[0] + n[1] * site[1] + n[2] * site[2] < 0.9) continue;
      const h = bodyHeight(3, ...n);
      if (h < 0.0006 || h > 0.008) continue;
      tufts.push({ n, h: h * R - 0.05, s: 1.2 + rand() * 1.6, tint: [0.9 + rand() * 0.2, 1, 0.8] });
    }
    body.add(instances(treeGeometry("pine"), lifeMaterial(env, { sway: 0.004 }), trees.filter((_, j) => j % 2 === 0), R));
    body.add(instances(treeGeometry("broad"), lifeMaterial(env, { sway: 0.004 }), trees.filter((_, j) => j % 2 === 1), R));
    body.add(instances(tuftGeometry(0x2f5a1e, 0x9cc95a), lifeMaterial(env, { sway: 0.1 }), tufts, R));
  });
}
