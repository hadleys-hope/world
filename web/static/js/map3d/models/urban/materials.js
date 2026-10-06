/** Two tiny deterministic material tiles, shared by every road and sidewalk. No network assets. */
import * as T from "three";
const cache = new Map();
export function streetTexture(paving = false) {
  if (cache.has(paving)) return cache.get(paving);
  const size = 128,
    data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const hash = Math.imul(x + 1, 374761393) ^ Math.imul(y + 1, 668265263),
        grain = (hash >>> 8) & 31;
      const row = Math.floor(y / 32),
        joint = paving && ((x + (row % 2) * 32) % 64 < 2 || y % 32 < 2);
      const v = joint ? 153 : 224 + grain;
      const i = (y * size + x) * 4;
      data[i] = data[i + 1] = data[i + 2] = v;
      data[i + 3] = 255;
    }
  const texture = new T.DataTexture(data, size, size, T.RGBAFormat);
  texture.colorSpace = T.SRGBColorSpace;
  texture.wrapS = texture.wrapT = T.RepeatWrapping;
  texture.magFilter = T.LinearFilter;
  texture.minFilter = T.LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  texture.anisotropy = 4;
  texture.needsUpdate = true;
  cache.set(paving, texture);
  return texture;
}
