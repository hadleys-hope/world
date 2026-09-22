/** render/sky: procedural colony viewer. */
import { state } from '../state.js';
import { terrainH } from '../geometry/planet.js';
import * as THREE from 'three';
export function makePlanet() {
  const hash = (x, y, z) => {
    const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453;
    return s - Math.floor(s);
  };
  const lerp = (a, b, t) => a + (b - a) * t;
  const noise = (x, y, z) => {
    const i = Math.floor(x),
      j = Math.floor(y),
      k = Math.floor(z);
    const fx = x - i,
      fy = y - j,
      fz = z - k;
    const u = fx * fx * (3 - 2 * fx),
      v = fy * fy * (3 - 2 * fy),
      w = fz * fz * (3 - 2 * fz);
    const c = (a, b, c2) => hash(i + a, j + b, k + c2);
    return lerp(lerp(lerp(c(0, 0, 0), c(1, 0, 0), u), lerp(c(0, 1, 0), c(1, 1, 0), u), v), lerp(lerp(c(0, 0, 1), c(1, 0, 1), u), lerp(c(0, 1, 1), c(1, 1, 1), u), v), w) * 2 - 1;
  };
  const fbm = (x, y, z, o = 6) => {
    let val = 0,
      amp = 0.5,
      f = 1;
    for (let q = 0; q < o; q++) {
      val += amp * noise(x * f + 1.7 * q, y * f + 9.2 * q, z * f + 3.1 * q);
      f *= 2.03;
      amp *= 0.5;
    }
    return val;
  };
  const craters = (x, y, z) => {
    let c = 0;
    for (let q = 0; q < 2; q++) {
      const s = 2 + q * 3;
      const qx = x * s,
        qy = y * s,
        qz = z * s;
      const cx = Math.floor(qx),
        cy = Math.floor(qy),
        cz = Math.floor(qz);
      const h1 = hash(cx, cy, cz),
        h2 = hash(cx + 7, cy + 3, cz + 1),
        h3 = hash(cx + 2, cy + 9, cz + 5);
      const fx = qx - cx - 0.5 + (h2 - 0.5) * 0.4,
        fy = qy - cy - 0.5 + (h3 - 0.5) * 0.4,
        fz = qz - cz - 0.5;
      const r = 0.18 + 0.22 * h1;
      const d = Math.sqrt(fx * fx + fy * fy + fz * fz);
      const sm = (e0, e1, t) => {
        t = Math.min(1, Math.max(0, (t - e0) / (e1 - e0)));
        return t * t * (3 - 2 * t);
      };
      const rim = sm(r, r * 0.75, d) * (1 - sm(r * 0.75, r * 0.35, d)) * 0.5;
      const bowl = sm(r * 0.75, 0, d);
      c += (rim - bowl * 0.8) * (0.5 + 0.5 * h1) / (1 + q);
    }
    return c;
  };
  const colonyAngle = 1500 / state.RP;
  const geo = new THREE.SphereGeometry(state.RP, 256, 192);
  const pos = geo.attributes.position;
  const hArr = new Float32Array(pos.count);
  const AMP = 90;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i),
      y = pos.getY(i),
      z = pos.getZ(i);
    const L = Math.hypot(x, y, z);
    const nx = x / L,
      ny = y / L,
      nz = z / L;
    const ang = Math.acos(Math.max(-1, Math.min(1, ny)));
    const mask = 1 - Math.min(1, Math.max(0, (ang - colonyAngle) / (colonyAngle * 0.6)));
    const m = mask * mask * (3 - 2 * mask);
    const h = (fbm(nx * 3, ny * 3, nz * 3) * 1.0 + (1 - Math.abs(noise(nx * 7, ny * 7, nz * 7))) * 0.35 + craters(nx, ny, nz) * 0.5 + fbm(nx * 22, ny * 22, nz * 22, 3) * 0.08) * (1 - m);
    const dist = ang * state.RP,
      az = Math.atan2(nz, nx),
      local = terrainH(dist * Math.cos(az), dist * Math.sin(az)),
      height = dist < 3750 ? local - 45 : THREE.MathUtils.lerp(local - 45, h * AMP, state.sstep(3750, 4100, dist));
    hArr[i] = height / AMP;
    const r = state.RP + height;
    pos.setXYZ(i, nx * r, ny * r, nz * r);
  }
  geo.setAttribute('aH', new THREE.BufferAttribute(hArr, 1));
  geo.computeVertexNormals();
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uSun: {
        value: new THREE.Vector3(1, 0.3, 0)
      },
      uColony: {
        value: new THREE.Vector3(0, 1, 0)
      },
      uCold: {
        value: 0.6
      },
      uStorm: {
        value: 0.0
      },
      uTime: {
        value: 0
      },
      uColonyAngle: {
        value: colonyAngle
      }
    },
    vertexShader: `attribute float aH; varying vec3 vN; varying vec3 vP; varying float vH; void main(){ vN=normalize(normalMatrix*normal); vP=(modelMatrix*vec4(position,1.0)).xyz; vH=aH; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
    fragmentShader: `uniform vec3 uSun; uniform vec3 uColony; uniform float uCold; uniform float uStorm; uniform float uTime; uniform float uColonyAngle;
      varying vec3 vN; varying vec3 vP; varying float vH;
      float hash(vec3 p){ return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453); }
      float vnoise(vec3 p){ vec3 i=floor(p), f=fract(p); vec3 u=f*f*(3.0-2.0*f); return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),u.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),u.x),u.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),u.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),u.x),u.y),u.z); }
      void main(){ vec3 n=normalize(vN); vec3 sn=normalize(vP); vec3 sd=normalize(uSun); float sun=max(dot(n,sd),0.0); float day=smoothstep(-0.15,0.25,dot(sn,sd));
        float grain=vnoise(sn*140.0)*0.6+vnoise(sn*900.0)*0.4;
        vec3 rock=mix(vec3(0.15,0.13,0.11), vec3(0.36,0.31,0.26), grain); rock=mix(rock, vec3(0.44,0.38,0.31), smoothstep(0.2,0.6,vH));
        float snow=smoothstep(0.30-0.35*uCold, 0.60-0.35*uCold, vH+0.25*(grain-0.5)) + 0.35*uStorm; float slope=1.0-max(dot(n,sn),0.0); snow*=1.0-smoothstep(0.25,0.6,slope*3.0); snow=clamp(snow,0.0,1.0);
        vec3 col=mix(rock, vec3(0.86,0.89,0.94), snow);
        float ang=acos(clamp(dot(sn,uColony),-1.0,1.0)); float glow=(1.0-smoothstep(uColonyAngle*0.8, uColonyAngle*2.2, ang))*(1.0-day);
        vec3 lit=col*(0.10+0.95*sun*day+0.07*(1.0-day)) + vec3(1.0,0.75,0.45)*glow*0.35;
        float rim=pow(1.0-max(dot(n,normalize(cameraPosition-vP)),0.0),3.0); lit+=vec3(0.25,0.35,0.55)*rim*0.5*(0.4+0.6*day);
        gl_FragColor=vec4(lit,1.0); }`
  });
  return new THREE.Mesh(geo, mat);
}
export function initialize() {
  state.scene.add(new THREE.AmbientLight(0xa8b0c4, 1.35));
  state.scene.add(new THREE.HemisphereLight(0x778ab0, 0x2a2118, 1.2));
  state.sun = new THREE.DirectionalLight(0xffe0b0, 1.3);
  state.scene.add(state.sun);
  state.sun.castShadow = true;
  state.sun.shadow.mapSize.set(2048, 2048);
  state.sun.shadow.camera.near = 100;
  state.sun.shadow.camera.far = 30000;
  state.sun.shadow.bias = -0.0008;
  state.sun.shadow.normalBias = .12;
  state.sunTarget = new THREE.Object3D();
  state.scene.add(state.sunTarget);
  state.sun.target = state.sunTarget;
  state.sunSprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: state.TEX.glow,
    transparent: true,
    depthTest: false
  }));
  state.sunSprite.scale.set(1800, 1800, 1);
  state.scene.add(state.sunSprite);
  {
    const n = 3000,
      p = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const v = new THREE.Vector3().randomDirection().multiplyScalar(60000);
      p.set([v.x, v.y, v.z], i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(p, 3));
    state.scene.add(new THREE.Points(g, new THREE.PointsMaterial({
      color: 0xbfc8dc,
      size: 2.2,
      sizeAttenuation: false
    })));
  }
  state.planetMesh = makePlanet();
  state.planetMat = state.planetMesh.material;
  state.scene.add(state.planetMesh);
  state.scene.add(new THREE.Mesh(new THREE.SphereGeometry(state.RP - 10, 256, 192), new THREE.MeshStandardMaterial({
    color: 0x749da8,
    roughness: .42,
    metalness: .18
  })));
  state.scene.add(new THREE.Mesh(new THREE.SphereGeometry(state.RP * 1.035, 64, 48), new THREE.MeshBasicMaterial({
    color: 0x4a6a9a,
    transparent: true,
    opacity: 0.10,
    side: THREE.BackSide,
    depthWrite: false
  })));
  state.weather = {
    snow: null,
    snowVel: null,
    tornado: null,
    wind: 8,
    precip: 'none',
    storm: false,
    tornadoOn: false
  };
  {
    const n = 6000,
      p = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      p[i * 3] = (Math.random() - 0.5) * 1600;
      p[i * 3 + 1] = Math.random() * 500;
      p[i * 3 + 2] = (Math.random() - 0.5) * 1600;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(p, 3));
    state.weather.snow = new THREE.Points(g, new THREE.PointsMaterial({
      color: 0xe8eef8,
      size: 6,
      map: state.TEX.dot,
      transparent: true,
      opacity: 0.0,
      depthWrite: false,
      sizeAttenuation: true
    }));
    state.weather.snow.frustumCulled = false;
    state.scene.add(state.weather.snow);
    state.weather.tornado = new THREE.Mesh(new THREE.CylinderGeometry(14, 70, 260, 24, 8, true), new THREE.MeshBasicMaterial({
      color: 0x9aa3b5,
      transparent: true,
      opacity: 0.0,
      side: THREE.DoubleSide,
      depthWrite: false
    }));
    state.weather.tornado.visible = false;
    state.scene.add(state.weather.tornado);
  }
  state.scene.fog = new THREE.FogExp2(0x2a2e38, 0.0);
}
