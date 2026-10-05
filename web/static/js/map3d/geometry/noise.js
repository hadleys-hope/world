/** geometry/noise: deterministic 3D value noise for terrain heights, shared by meshes and placement.
 * Heights are computed once on the CPU (so trees and rocks can stand on them); the shaders only add detail. */

// Integer hash: cheaper than the sin() hash and stable across browsers.
function hash3(x, y, z) {
  let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(z, 1440662683);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

export function noise3(x, y, z) {
  const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
  const fx = x - ix, fy = y - iy, fz = z - iz;
  const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy), w = fz * fz * (3 - 2 * fz);
  const a = hash3(ix, iy, iz), b = hash3(ix + 1, iy, iz), c = hash3(ix, iy + 1, iz), d = hash3(ix + 1, iy + 1, iz);
  const e = hash3(ix, iy, iz + 1), f = hash3(ix + 1, iy, iz + 1), g = hash3(ix, iy + 1, iz + 1), h = hash3(ix + 1, iy + 1, iz + 1);
  const x1 = a + (b - a) * u, x2 = c + (d - c) * u, x3 = e + (f - e) * u, x4 = g + (h - g) * u;
  const y1 = x1 + (x2 - x1) * v, y2 = x3 + (x4 - x3) * v;
  return (y1 + (y2 - y1) * w) * 2 - 1;
}

export function fbm3(x, y, z, octaves = 4) {
  let s = 0, amp = 0.5, f = 1;
  for (let o = 0; o < octaves; o++) {
    s += amp * noise3(x * f + o * 17.3, y * f + o * 5.1, z * f + o * 11.7);
    f *= 2.02;
    amp *= 0.5;
  }
  return s;
}

// Ridged noise: sharp crests where the noise crosses zero, i.e. mountain chains.
export function ridged3(x, y, z, octaves = 4) {
  let s = 0, amp = 0.55, f = 1, prev = 1;
  for (let o = 0; o < octaves; o++) {
    let r = 1 - Math.abs(noise3(x * f + o * 3.3, y * f + o * 9.9, z * f + o * 1.7));
    r *= r;
    s += r * amp * prev;
    prev = r;
    f *= 2.1;
    amp *= 0.5;
  }
  return s;
}

const smooth = (e0, e1, t) => {
  t = Math.min(1, Math.max(0, (t - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
};

/** LV-426 outside the colony: ice ranges, lowland valleys, lake basins and river channels (metres above the
 * datum, for a unit direction n). river: 0..1, how much of a river channel this point is. */
export const WATER_LEVEL = -10;   // the old sea sphere sat at RP - 10; the near-colony ice and intake are built for it
export function wild(nx, ny, nz) {
  const wx = nx + 0.18 * noise3(nx * 3 + 7, ny * 3, nz * 3),
    wy = ny + 0.18 * noise3(nx * 3, ny * 3 + 7, nz * 3),
    wz = nz + 0.18 * noise3(nx * 3, ny * 3, nz * 3 + 7);
  const cont = fbm3(wx * 2.4, wy * 2.4, wz * 2.4, 3);
  const ridge = ridged3(wx * 8, wy * 8, wz * 8, 3);
  const mountains = smooth(-0.02, 0.32, cont);
  let h = 14 + 30 * cont + 300 * mountains * ridge * ridge + 14 * noise3(nx * 40, ny * 40, nz * 40);
  h += (-34 - h) * smooth(-0.18, -0.42, cont);                     // lake basins in the lowest ground
  const rv = Math.abs(noise3(wx * 6.5 + 2, wy * 6.5, wz * 6.5 - 3));
  const river = (1 - smooth(0.012, 0.045, rv)) * (1 - smooth(25, 120, h));   // rivers only in the lowlands
  h += (-15 - h) * river;
  return { h, river };
}

/** Other worlds: a height in units of the body radius (about ±0.03) and a material id the shader reads. */
export function bodyHeight(kind, nx, ny, nz) {
  if (kind === 0) {           // Hephaestus: volcanoes, lava plains, cracked crust
    const v = ridged3(nx * 5, ny * 5, nz * 5, 3);
    const cones = Math.pow(Math.max(0, noise3(nx * 3.2, ny * 3.2, nz * 3.2)), 3) * 3;
    const crater = Math.max(0, 0.18 - Math.abs(noise3(nx * 9, ny * 9, nz * 9))) * -1.2;
    return 0.012 * v + 0.03 * cones + 0.01 * crater + 0.004 * fbm3(nx * 30, ny * 30, nz * 30, 2);
  }
  if (kind === 1) {           // Russet: dune seas, mesas, craters
    const warp = noise3(nx * 4, ny * 4, nz * 4);
    const dunes = Math.pow(Math.abs(Math.sin((nx * 70 + nz * 40 + warp * 6) )), 1.6) * smooth(-0.2, 0.2, fbm3(nx * 2, ny * 2, nz * 2, 2));
    const mesa = smooth(0.18, 0.24, fbm3(nx * 3 + 5, ny * 3, nz * 3, 3)) * 0.02;
    const crater = -Math.max(0, 0.12 - Math.abs(noise3(nx * 11, ny * 11, nz * 11))) * 0.15;
    return 0.004 * dunes + mesa + crater + 0.006 * fbm3(nx * 6, ny * 6, nz * 6, 3);
  }
  // Klyaksa: continents and islands in a warm ocean, mountains inland
  const cont = fbm3(nx * 2.2, ny * 2.2, nz * 2.2, 5) + 0.04;
  const ridge = ridged3(nx * 7, ny * 7, nz * 7, 3) * smooth(0.08, 0.3, cont);
  return 0.02 * cont + 0.028 * ridge * ridge;
}

// The same kind of noise for shaders (visual detail only, not heights).
export const GLSL_NOISE = `
float h3(vec3 p){ p=fract(p*0.3183099+.1); p*=17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
float n3(vec3 x){ vec3 i=floor(x), f=fract(x); f=f*f*(3.0-2.0*f);
  return mix(mix(mix(h3(i),h3(i+vec3(1,0,0)),f.x),mix(h3(i+vec3(0,1,0)),h3(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(h3(i+vec3(0,0,1)),h3(i+vec3(1,0,1)),f.x),mix(h3(i+vec3(0,1,1)),h3(i+vec3(1,1,1)),f.x),f.y),f.z); }
float fbm(vec3 p){ float s=0.0, a=0.5; for(int i=0;i<4;i++){ s+=a*n3(p); p=p*2.03+vec3(1.7,9.2,3.1); a*=0.5; } return s; }
`;
