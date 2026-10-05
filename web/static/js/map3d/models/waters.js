/** models/waters: lakes, rivers, seas and ice as one partial sphere per world.
 * Only the cells that are actually under the water level get triangles, so the water costs nothing where
 * there is land. Each vertex knows its depth and whether it is open water, so the shader can make shallows
 * clear and the deep dark without a depth texture. */
import { GLSL_NOISE } from "../geometry/noise.js";
import * as THREE from "three";

/**
 * radius: the water surface; sample(nx, ny, nz) -> { depth (m, > 0 under water), liquid (0 ice .. 1 open),
 * warm (0..1, steam-heated) }; res: cells around the equator.
 */
export function buildWater({ radius, sample, res = 384, uniforms, tint = [0.05, 0.32, 0.38], iceTint = [0.78, 0.86, 0.93] }) {
  const cols = res, rows = Math.round(res * 0.66);
  const grid = new Array((rows + 1) * (cols + 1));
  for (let r = 0; r <= rows; r++) {
    const th = (r / rows) * Math.PI, st = Math.sin(th), ct = Math.cos(th);
    for (let c = 0; c <= cols; c++) {
      const ph = (c / cols) * Math.PI * 2;
      const nx = st * Math.cos(ph), ny = ct, nz = st * Math.sin(ph);
      grid[r * (cols + 1) + c] = { nx, ny, nz, ...sample(nx, ny, nz) };
    }
  }
  const pos = [], depth = [], liquid = [], warm = [], index = [], map = new Map();
  const vert = (k) => {
    if (map.has(k)) return map.get(k);
    const g = grid[k];
    pos.push(g.nx * radius, g.ny * radius, g.nz * radius);
    depth.push(Math.max(0, g.depth));
    liquid.push(g.liquid);
    warm.push(g.warm || 0);
    map.set(k, pos.length / 3 - 1);
    return pos.length / 3 - 1;
  };
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) {
      const a = r * (cols + 1) + c, b = a + 1, d = a + cols + 1, e = d + 1;
      if (Math.max(grid[a].depth, grid[b].depth, grid[d].depth, grid[e].depth) <= -0.5) continue;   // dry cell
      const A = vert(a), B = vert(b), D = vert(d), E = vert(e);
      index.push(A, D, B, B, D, E);
    }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("aDepth", new THREE.Float32BufferAttribute(depth, 1));
  geo.setAttribute("aLiquid", new THREE.Float32BufferAttribute(liquid, 1));
  geo.setAttribute("aWarm", new THREE.Float32BufferAttribute(warm, 1));
  geo.setIndex(index);
  geo.computeBoundingSphere();
  const mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,   // seen from above and, after a dive, from below
    uniforms: { ...uniforms, uTint: { value: new THREE.Vector3(...tint) }, uIce: { value: new THREE.Vector3(...iceTint) } },
    vertexShader: `attribute float aDepth, aLiquid, aWarm; varying float vDepth, vLiquid, vWarm; varying vec3 vW, vN;
      void main(){ vDepth=aDepth; vLiquid=aLiquid; vWarm=aWarm; vec4 w=modelMatrix*vec4(position,1.0); vW=w.xyz;
        vN=normalize(mat3(modelMatrix)*position); gl_Position=projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `uniform float uTime; uniform vec3 uSun, uTint, uIce; varying float vDepth, vLiquid, vWarm; varying vec3 vW, vN;
      ${GLSL_NOISE}
      void main(){
        vec3 n=normalize(vN); vec3 v=normalize(cameraPosition-vW); vec3 s=normalize(uSun);
        float day=smoothstep(-0.12,0.25,dot(n,s));
        // ripples: two drifting noise layers bend the normal of open water
        vec3 q=vW*0.06; float t=uTime;
        vec3 rip=vec3(n3(q+vec3(t*0.35,0.,t*0.2))-0.5, 0.0, n3(q*1.7+vec3(-t*0.25,t*0.1,0.))-0.5);
        vec3 nw=normalize(n+0.22*vLiquid*(rip - n*dot(rip,n)));
        float fres=pow(1.0-max(dot(nw,v),0.0),4.0);
        float spec=pow(max(dot(reflect(-s,nw),v),0.0),180.0)*day;
        // open water: clear in the shallows, deep teal further out
        float deep=smoothstep(0.5,22.0,vDepth);
        vec3 shallow=mix(vec3(0.55,0.78,0.80), uTint*1.6, deep);
        vec3 water=mix(shallow, uTint*0.45, deep*0.7);
        vec3 sky=mix(vec3(0.10,0.14,0.22), vec3(0.62,0.72,0.84), day);
        vec3 open=mix(water*(0.25+0.75*day), sky, fres*0.75) + vec3(1.0,0.96,0.88)*spec*1.6;
        float openA=mix(0.30, 0.86, deep) + fres*0.3;
        // ice: white-blue with dark cracks and a frosted grain
        float crack=1.0-smoothstep(0.0,0.04,abs(n3(vW*0.045)-0.5));
        float grain=n3(vW*0.6);
        vec3 ice=mix(uIce*0.82, uIce, grain)*(0.18+0.82*max(dot(n,s),0.0)*day+0.06) - crack*0.18;
        ice+=vec3(0.8,0.9,1.0)*pow(max(dot(reflect(-s,n),v),0.0),24.0)*0.25*day;
        // steam-heated water glows faintly at night
        vec3 col=mix(ice, open, vLiquid) + vWarm*vec3(0.95,0.55,0.25)*0.35*(1.0-day*0.7);
        float a=mix(0.93, openA, vLiquid);
        gl_FragColor=vec4(col, clamp(a,0.0,1.0)*smoothstep(-0.2,0.6,vDepth+0.6));
      }`,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.matrixAutoUpdate = false;
  mesh.renderOrder = 2;
  return mesh;
}
