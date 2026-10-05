/** models/life: plants, rocks, ice crystals and hot springs, all instanced: one draw call per kind of thing,
 * whatever the count. Wind is done in the vertex shader, so a swaying forest costs no CPU per frame. */
import * as THREE from "three";

// ---- geometries (vertex colours in aCol; all built small, scaled per instance) ----
function merge(parts) {
  const pos = [], nor = [], col = [];
  for (const [g, color, tip] of parts) {
    const geo = g.toNonIndexed();
    geo.computeVertexNormals();
    const p = geo.attributes.position, n = geo.attributes.normal;
    const box = new THREE.Box3().setFromBufferAttribute(p);
    for (let i = 0; i < p.count; i++) {
      pos.push(p.getX(i), p.getY(i), p.getZ(i));
      nor.push(n.getX(i), n.getY(i), n.getZ(i));
      const k = tip ? (p.getY(i) - box.min.y) / Math.max(1e-6, box.max.y - box.min.y) : 0;
      const c = new THREE.Color(color).lerp(new THREE.Color(tip || color), k);
      col.push(c.r, c.g, c.b);
    }
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  out.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  out.setAttribute("aCol", new THREE.Float32BufferAttribute(col, 3));
  return out;
}

export function treeGeometry(style) {
  if (style === "frost") {        // LV-426: a squat alien conifer, blue-black needles with frosted tips
    const trunk = new THREE.CylinderGeometry(0.12, 0.22, 2.2, 5).translate(0, 1.1, 0);
    const c1 = new THREE.ConeGeometry(1.5, 2.4, 6).translate(0, 2.6, 0);
    const c2 = new THREE.ConeGeometry(1.15, 2.0, 6).translate(0, 3.8, 0);
    const c3 = new THREE.ConeGeometry(0.7, 1.6, 6).translate(0, 4.9, 0);
    return merge([[trunk, 0x3a2c22], [c1, 0x14303a, 0x5b8d9a], [c2, 0x16363f, 0x7fb1bb], [c3, 0x1a3d46, 0xd9eef2]]);
  }
  if (style === "broad") {        // Klyaksa: a round broadleaf
    const trunk = new THREE.CylinderGeometry(0.15, 0.3, 3, 5).translate(0, 1.5, 0);
    const crown = new THREE.IcosahedronGeometry(1.9, 0).scale(1, 0.85, 1).translate(0, 4.2, 0);
    return merge([[trunk, 0x4a3524], [crown, 0x2f6b2c, 0x6aa84a]]);
  }
  const trunk = new THREE.CylinderGeometry(0.12, 0.25, 2.5, 5).translate(0, 1.25, 0);    // Klyaksa pine
  const c1 = new THREE.ConeGeometry(1.6, 3.2, 6).translate(0, 3.4, 0);
  const c2 = new THREE.ConeGeometry(1.0, 2.4, 6).translate(0, 5.0, 0);
  return merge([[trunk, 0x4a3524], [c1, 0x1d4a2a, 0x3f7a3c], [c2, 0x235533, 0x5a9a4c]]);
}

export function tuftGeometry(base, tip) {   // three crossed blades; height 1
  const parts = [];
  for (let k = 0; k < 3; k++) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute([-0.09, 0, 0, 0.09, 0, 0, 0.02, 1, 0.03], 3));
    g.rotateY((k * Math.PI) / 3 + 0.3).translate(Math.cos(k * 2.1) * 0.12, 0, Math.sin(k * 2.1) * 0.12);
    parts.push([g, base, tip]);
  }
  return merge(parts);
}

export function rockGeometry() {
  const g = new THREE.IcosahedronGeometry(1, 0);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) p.setY(i, p.getY(i) * 0.55 + 0.25);
  return merge([[g, 0x4a4e52, 0x8a8f93]]);
}

export function crystalGeometry() {
  const parts = [];
  for (let k = 0; k < 3; k++) {
    const g = new THREE.OctahedronGeometry(0.4, 0).scale(1, 4 + k, 1).rotateZ((k - 1) * 0.35).translate((k - 1) * 0.5, 1.5 + k * 0.4, 0);
    parts.push([g, 0x6fa8c8, 0xe6f6ff]);
  }
  return merge(parts);
}

// ---- one material for everything that grows or lies on the ground ----
export function lifeMaterial(uniforms, { sway = 0, glow = 0, indoor = 0 } = {}) {
  return new THREE.ShaderMaterial({
    uniforms: { ...uniforms, uSway: { value: sway }, uGlow: { value: glow }, uIndoor: { value: indoor } },
    vertexShader: `attribute vec3 aCol; attribute vec3 aTint; uniform float uTime, uSway; varying vec3 vC, vN, vW, vUp;
      void main(){
        vec3 p=position; vec3 o=instanceMatrix[3].xyz;
        float ph=dot(o, vec3(0.031,0.027,0.019));
        float w=uSway*p.y*p.y*(sin(uTime*1.6+ph)*0.6+sin(uTime*3.1+ph*1.7)*0.25);
        p.x+=w; p.z+=w*0.5;
        vec4 wp=modelMatrix*instanceMatrix*vec4(p,1.0);
        vN=normalize(mat3(modelMatrix)*mat3(instanceMatrix)*normal);
        vUp=normalize(mat3(modelMatrix)*instanceMatrix[1].xyz);
        vC=aCol*aTint; vW=wp.xyz; gl_Position=projectionMatrix*viewMatrix*wp; }`,
    fragmentShader: `uniform vec3 uSun; uniform float uGlow, uIndoor; varying vec3 vC, vN, vW, vUp;
      void main(){ vec3 s=normalize(uSun); vec3 n=normalize(vN);
        float day=smoothstep(-0.12,0.25,dot(normalize(vUp),s));
        float diff=max(dot(n,s),0.0)*0.75+0.25*max(dot(-n,s),0.0);
        vec3 c=vC*(0.10+0.95*diff*day+0.05) + vC*uGlow*(0.35+0.65*(1.0-day));
        // under the dome the city's lamps light the garden at night
        c+=uIndoor*(1.0-day)*vC*vec3(1.0,0.86,0.66)*(0.38+0.25*max(dot(n,normalize(vUp)),0.0));
        float rim=pow(1.0-max(dot(n,normalize(cameraPosition-vW)),0.0),3.0);
        gl_FragColor=vec4(c+rim*0.08*vC,1.0); }`,
  });
}

/** Instances on a sphere: items = [{ n: [nx,ny,nz], h (m above radius), s (scale), tint: [r,g,b] }]. */
export function instances(geometry, material, items, radius) {
  const mesh = new THREE.InstancedMesh(geometry, material, items.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), yaw = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
  const n = new THREE.Vector3(), p = new THREE.Vector3(), sc = new THREE.Vector3();
  const tint = new Float32Array(items.length * 3);
  items.forEach((it, i) => {
    n.set(...it.n).normalize();
    q.setFromUnitVectors(up, n).multiply(yaw.setFromAxisAngle(up, it.yaw ?? (i * 2.399) % (Math.PI * 2)));
    p.copy(n).multiplyScalar(radius + it.h);
    sc.setScalar(it.s);
    if (it.sy) sc.y *= it.sy;
    mesh.setMatrixAt(i, m.compose(p, q, sc));
    tint.set(it.tint || [1, 1, 1], i * 3);
  });
  geometry.setAttribute("aTint", new THREE.InstancedBufferAttribute(tint, 3));
  mesh.instanceMatrix.needsUpdate = true;
  mesh.computeBoundingSphere();
  mesh.matrixAutoUpdate = false;
  mesh.frustumCulled = true;
  return mesh;
}

/** Hot springs: glowing mineral pools, plus steam that rises and fades entirely in the vertex shader. */
export function hotSprings(vents, radius, uniforms) {
  const disc = new THREE.CircleGeometry(1, 28).rotateX(-Math.PI / 2);
  const pool = new THREE.InstancedMesh(disc, new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, uniforms,
    vertexShader: `varying vec2 vP; varying vec3 vW; void main(){ vP=position.xz; vec4 w=modelMatrix*instanceMatrix*vec4(position,1.0); vW=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `uniform float uTime; varying vec2 vP; varying vec3 vW;
      void main(){ float r=length(vP); float ring=sin(r*22.0-uTime*2.2)*0.5+0.5;
        vec3 core=vec3(0.18,0.85,0.88), rim=vec3(0.95,0.52,0.18);
        vec3 c=mix(core, rim, smoothstep(0.55,0.95,r)) + ring*0.08*(1.0-r);
        gl_FragColor=vec4(c*1.2, smoothstep(1.0,0.82,r)*0.92); }`,
  }), vents.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
  const steamPos = [], steamSeed = [], steamUp = [];
  vents.forEach((v, i) => {
    const n = new THREE.Vector3(...v.n).normalize();
    const p = n.clone().multiplyScalar(radius + v.h + 0.6);
    pool.setMatrixAt(i, m.compose(p, q.setFromUnitVectors(up, n), new THREE.Vector3(v.r, 1, v.r)));
    for (let k = 0; k < 90; k++) {
      const a = k * 2.399, d = Math.sqrt((k % 30) / 30) * v.r * 0.8;
      const t1 = new THREE.Vector3(1, 0, 0).cross(n).normalize(), t2 = n.clone().cross(t1);
      const s = p.clone().addScaledVector(t1, Math.cos(a) * d).addScaledVector(t2, Math.sin(a) * d);
      steamPos.push(s.x, s.y, s.z); steamSeed.push(k / 90 + i * 0.37); steamUp.push(n.x, n.y, n.z);
    }
  });
  pool.instanceMatrix.needsUpdate = true;
  pool.computeBoundingSphere();
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(steamPos, 3));
  g.setAttribute("aSeed", new THREE.Float32BufferAttribute(steamSeed, 1));
  g.setAttribute("aUp", new THREE.Float32BufferAttribute(steamUp, 3));
  const steam = new THREE.Points(g, new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, uniforms,
    vertexShader: `attribute float aSeed; attribute vec3 aUp; uniform float uTime; varying float vA;
      void main(){ float t=fract(uTime*0.045+aSeed); vec3 p=position+aUp*(t*70.0)+vec3(sin(aSeed*40.0+uTime*0.3),0.0,cos(aSeed*33.0))*t*14.0;
        vec4 mv=modelViewMatrix*vec4(p,1.0); vA=(1.0-t)*smoothstep(0.0,0.08,t); gl_PointSize=clamp((18.0+70.0*t)*(260.0/-mv.z),1.0,220.0);
        gl_Position=projectionMatrix*mv; }`,
    fragmentShader: `varying float vA; void main(){ float d=length(gl_PointCoord-0.5); gl_FragColor=vec4(vec3(0.92,0.95,0.98), vA*0.28*smoothstep(0.5,0.0,d)); }`,
  }));
  steam.frustumCulled = false;
  return [pool, steam];
}
