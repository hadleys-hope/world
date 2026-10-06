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
  const mat = waterMaterial(uniforms, { tint, iceTint });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.matrixAutoUpdate = false;
  mesh.renderOrder = 2;
  return mesh;
}

/** The one water look, for seas, lakes, rivers and ponds. Geometry attributes: aDepth (metres of water under
 * the vertex; < 0 where the ground is higher), aLiquid (0 ice .. 1 open), aWarm (0..1). Options: floes (0..1
 * drifting ice on open water), flow ([x, y, z] planet-local direction the surface runs, for rivers). */
export function waterMaterial(uniforms, { tint = [0.05, 0.32, 0.38], iceTint = [0.78, 0.86, 0.93], floes = 0, flow = null } = {}) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,   // seen from above and, after a dive, from below
    uniforms: {
      ...uniforms,
      uTint: { value: new THREE.Vector3(...tint) },
      uIce: { value: new THREE.Vector3(...iceTint) },
      uFloes: { value: floes },
      uFlow: { value: new THREE.Vector3(...(flow || [0, 0, 0])) },
    },
    vertexShader: `attribute float aDepth, aLiquid, aWarm; varying float vDepth, vLiquid, vWarm; varying vec3 vW, vN, vLocal, vAxisX, vAxisZ;
      void main(){ vDepth=aDepth; vLiquid=aLiquid; vWarm=aWarm; vLocal=position; vAxisX=normalize(mat3(modelMatrix)*vec3(1.,0.,0.)); vAxisZ=normalize(mat3(modelMatrix)*vec3(0.,0.,1.)); vec4 w=modelMatrix*vec4(position,1.0); vW=w.xyz;
        vN=normalize(w.xyz - (modelMatrix*vec4(0.,0.,0.,1.)).xyz); gl_Position=projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `uniform float uTime, uFloes; uniform vec3 uSun, uTint, uIce, uFlow;
      varying float vDepth, vLiquid, vWarm; varying vec3 vW, vN, vLocal, vAxisX, vAxisZ;
      ${GLSL_NOISE}
      void main(){
        vec3 n=normalize(vN); vec3 v=normalize(cameraPosition-vW); vec3 s=normalize(uSun);
        float day=smoothstep(-0.12,0.25,dot(n,s));
        float dist=length(cameraPosition-vW);
        // waves: three noise layers drift with the wind (or downstream on a river) and bend the normal
        vec3 drift=uFlow*uTime*1.8;
        vec3 q=vLocal*0.09-drift*0.09;
        float e=0.35;
        float h0=fbm(q+vec3(uTime*0.12,0.,uTime*0.07));
        float hx=fbm(q+vec3(e,0.,0.)+vec3(uTime*0.12,0.,uTime*0.07));
        float hz=fbm(q+vec3(0.,0.,e)+vec3(uTime*0.12,0.,uTime*0.07));
        vec3 g=(vAxisX*(hx-h0)+vAxisZ*(hz-h0))/e;
        float fine=n3(vLocal*0.8+vec3(uTime*0.9,0.,-uTime*0.6))-0.5;
        vec3 wave=0.55*g+0.06*fine*(vAxisX+vAxisZ);
        vec3 nw=normalize(n+vLiquid*(wave-n*dot(wave,n))*(1.0-smoothstep(300.,2500.,dist)));
        float fres=0.02+0.98*pow(1.0-max(dot(nw,v),0.0),5.0);
        float spec=pow(max(dot(reflect(-s,nw),v),0.0),220.0)*day*3.0 + pow(max(dot(reflect(-s,nw),v),0.0),24.0)*day*0.12;
        // what you see through the water: the bed fades into depth colour; shallows show light patterns
        float clarity=exp(-max(vDepth,0.0)/5.5);
        vec3 bed=vec3(0.42,0.46,0.42)*(0.6+0.4*n3(vLocal*0.25));
        float caustic=pow(1.0-abs(n3(vLocal*0.35+vec3(uTime*0.4,0.,uTime*0.3))-n3(vLocal*0.35-vec3(uTime*0.3,0.,-uTime*0.2))),8.0);
        vec3 through=mix(uTint*0.55, bed+caustic*0.35*day, clarity);
        vec3 sky=mix(vec3(0.05,0.07,0.12), vec3(0.58,0.68,0.82), day);
        vec3 open=mix(through*(0.18+0.82*day), sky, fres)+vec3(1.0,0.96,0.88)*spec;
        // foam where the water thins out at the shore
        float foamBand=1.0-smoothstep(0.0,0.9,vDepth);
        float foam=foamBand*smoothstep(0.35,0.7,n3(vLocal*0.6+vec3(uTime*0.5,0.,0.))+foamBand*0.4);
        open=mix(open, vec3(0.9,0.94,0.96)*(0.25+0.75*day), foam*vLiquid);
        float openA=mix(0.25,0.92,1.0-clarity)+fres*0.4+foam*0.6;
        // drifting ice floes on open water, and solid ice where it is frozen
        float floe=uFloes*smoothstep(0.6,0.64,n3(vLocal*0.012+vec3(uTime*0.004,0.,0.)))*smoothstep(1.5,4.0,vDepth);
        float crack=1.0-smoothstep(0.0,0.035,abs(n3(vLocal*0.045)-0.5));
        vec3 ice=mix(uIce*0.8,uIce,n3(vLocal*0.6))*(0.16+0.84*max(dot(n,s),0.0)*day+0.06)-crack*0.16;
        ice+=vec3(0.8,0.9,1.0)*pow(max(dot(reflect(-s,n),v),0.0),24.0)*0.25*day;
        float frozen=max(1.0-vLiquid, floe);
        vec3 col=mix(open, ice, frozen)+vWarm*vec3(0.95,0.55,0.25)*0.3*(1.0-day*0.7);
        float a=mix(openA, 0.95, frozen);
        gl_FragColor=vec4(col, clamp(a,0.0,1.0)*smoothstep(-0.3,0.05,vDepth));
      }`,
  });
}
