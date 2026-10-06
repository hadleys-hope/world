/** Branch skeleton plus foliage cards. Analytic leaf cutouts avoid texture downloads and chunky crowns. */
import * as T from "three";
export function botanicalTree(style, far = false) {
  const broad = style === "broad",
    frost = style === "frost",
    parts = [];
  const add = (g, c, leaf = false) =>
    parts.push({ g, c: new T.Color(c), leaf });
  add(
    new T.CylinderGeometry(0.1, 0.23, 4.5, 5, 1, true).translate(0, 2.25, 0),
    0x66503b,
  );
  for (let k = 0; k < (far ? 3 : 6); k++) {
    const a = k * 2.39996,
      y = broad ? 2.5 + (k % 3) * 0.6 : 1.8 + k * 0.43,
      r = broad ? 1.45 : 1.65 - k * 0.14;
    const from = new T.Vector3(0, y, 0),
      to = new T.Vector3(Math.cos(a) * r, y + 0.55, Math.sin(a) * r),
      delta = to.clone().sub(from);
    const branch = new T.CylinderGeometry(
      0.035,
      0.08,
      delta.length(),
      4,
      1,
      true,
    );
    branch.applyQuaternion(
      new T.Quaternion().setFromUnitVectors(
        new T.Vector3(0, 1, 0),
        delta.normalize(),
      ),
    );
    branch.translate(...from.add(to).multiplyScalar(0.5).toArray());
    if (!far) add(branch, 0x66503b);
    else branch.dispose();
    const size = far ? 3.4 : broad ? 2.2 : 2.1 - k * 0.14;
    const card = new T.PlaneGeometry(size, size * (broad ? 0.9 : 0.75), 1, 1)
      .rotateY(a)
      .rotateX(broad ? -0.25 : -0.5)
      .translate(Math.cos(a) * r * 0.65, y + 0.8, Math.sin(a) * r * 0.65);
    add(
      card.clone().rotateY(0.9).translate(0.1, 0.2, 0),
      frost ? 0x7da49e : broad ? 0x648d47 : 0x548454,
      true,
    );
    add(
      card,
      frost
        ? 0x91babc
        : broad
          ? [0x739958, 0x4e803f, 0x91ac64][k % 3]
          : 0x4d8054,
      true,
    );
  }
  const p = [],
    n = [],
    c = [],
    leaf = [];
  for (const { g, color, leaf: isLeaf, c: col } of parts) {
    const geo = g.toNonIndexed(),
      pos = geo.attributes.position,
      nor = geo.attributes.normal,
      uv = geo.attributes.uv;
    for (let i = 0; i < pos.count; i++) {
      p.push(pos.getX(i), pos.getY(i), pos.getZ(i));
      n.push(nor.getX(i), nor.getY(i), nor.getZ(i));
      c.push(col.r, col.g, col.b);
      leaf.push(
        isLeaf ? uv.getX(i) : 0,
        isLeaf ? uv.getY(i) : 0,
        isLeaf ? 1 : 0,
      );
    }
    geo.dispose();
    g.dispose();
  }
  const g = new T.BufferGeometry();
  for (const [name, data] of Object.entries({
    position: p,
    normal: n,
    aCol: c,
    aLeaf: leaf,
  }))
    g.setAttribute(name, new T.Float32BufferAttribute(data, 3));
  return g;
}
