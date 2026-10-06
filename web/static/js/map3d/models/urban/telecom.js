/** Three real antenna silhouettes; directional rings describe coverage, not an RF propagation solver. */
import * as T from "three";
import { state } from "../../state.js";
import { Batches, Model, palette, antenna, planYaw } from "./kit.js";
import { createPlacement } from "./placement.js";
import { Surface } from "./streets.js";

function sectorPanels(m, h, r = 1.1) {
  for (let k = 0; k < 3; k++) {
    const a = (k * Math.PI * 2) / 3,
      co = Math.cos(a),
      si = Math.sin(a);
    m.beam([0, h, 0], [co * r, h, si * r], 0.06);
    for (const offset of [-0.32, 0.32]) {
      const x = co * r - si * offset,
        z = si * r + co * offset,
        g = new T.BoxGeometry(0.3, 2.6, 0.22)
          .rotateY(-a + Math.PI / 2)
          .translate(x, h, z);
      m.parts.push([g, palette.white]);
      m.beam(
        [x, h - 1.3, z],
        [co * 0.16, h - 4, si * 0.16],
        0.025,
        palette.dark,
      );
    }
  }
}
export function satelliteDish() {
  const m = new Model().cyl(0, 0.6, 0, 0.07, 1.2).box(0, 0.04, 0, 1, 0.08, 1),
    points = [];
  for (let i = 0; i <= 10; i++) {
    const r = i * 0.11;
    points.push(new T.Vector2(r, r * r * 0.26));
  }
  const g = new T.LatheGeometry(points, 18).rotateZ(-0.72).translate(0, 1.4, 0);
  m.parts.push([g, palette.white]);
  m.beam([0, 1.3, 0], [0.9, 2.15, 0], 0.04).cyl(
    0.9,
    2.16,
    0,
    0.11,
    0.2,
    palette.dark,
  );
  return m.finish();
}
export function towerGeometry(style = "lattice") {
  const m = new Model(),
    height = style === "monopole" ? 34 : 42;
  if (style === "lattice") {
    for (let i = 0; i < 3; i++) {
      const a = (i * Math.PI * 2) / 3,
        b = ((i + 1) * Math.PI * 2) / 3;
      for (let h = 0; h < height; h += 4) {
        const r = 2.6 - h * 0.045,
          r2 = 2.6 - (h + 4) * 0.045,
          A = [Math.cos(a) * r, h, Math.sin(a) * r],
          B = [Math.cos(b) * r, h, Math.sin(b) * r],
          U = [Math.cos(a) * r2, h + 4, Math.sin(a) * r2],
          V = [Math.cos(b) * r2, h + 4, Math.sin(b) * r2];
        m.beam(A, U, 0.085, h % 8 === 0 ? palette.white : 0xc36b50)
          .beam(A, V, 0.045)
          .beam(B, U, 0.045)
          .beam(A, B, 0.05);
      }
    }
    for (const h of [18, 32, 39]) m.cyl(0, h, 0, 2, 0.16, palette.metal, 2, 12);
  } else {
    m.cyl(0, height / 2, 0, 0.66, height, palette.white, 0.3, 12);
    for (const h of [22, 30]) m.cyl(0, h, 0, 1.3, 0.16, palette.metal, 1.3, 12);
  }
  for (let h = 1; h < height - 2; h += 0.6)
    m.box(0.5, h, 0.3, 0.4, 0.05, 0.05, palette.metal);
  sectorPanels(m, height - 2, 1.35);
  sectorPanels(m, height - 9, 1.2);
  m.cyl(0, height + 0.5, 0, 0.035, 2, palette.metal).cyl(
    0,
    height - 0.1,
    0,
    0.14,
    0.12,
    0xf85947,
  );
  m.box(3, 1.1, 1, 1.8, 2.2, 1.2, palette.white).box(
    3,
    1.15,
    1.64,
    1.3,
    1.8,
    0.08,
    palette.dark,
  );
  m.parts.push([
    satelliteDish().scale(1.7, 1.7, 1.7).translate(-1.1, 24, 0),
    null,
  ]);
  return m.finish();
}
export function roofArray() {
  const m = new Model()
    .cyl(0, 2.5, 0, 0.12, 5)
    .box(0, 0.1, 0, 2.6, 0.2, 2.6, palette.metal);
  sectorPanels(m, 3.7, 0.85);
  for (let k = 0; k < 3; k++) {
    const a = (k * Math.PI * 2) / 3;
    m.beam([0, 2, 0], [Math.cos(a) * 1.5, 0.15, Math.sin(a) * 1.5], 0.055);
  }
  m.box(1.7, 0.65, 0, 0.65, 1.3, 0.65, palette.white);
  m.parts.push([satelliteDish().translate(-2.1, 0, 0), null]);
  return m.finish();
}
function coverageGeometry() {
  const p = [],
    phase = [];
  for (let sector = 0; sector < 3; sector++)
    for (let ring = 0; ring < 3; ring++)
      for (let k = 0; k < 36; k++) {
        const az = (sector * Math.PI * 2) / 3,
          a = (k * Math.PI) / 18,
          b = ((k + 1) * Math.PI) / 18;
        const at = (angle, thick) => {
          const along = 1,
            vertical = Math.cos(angle) * (0.15 + thick),
            side = Math.sin(angle) * (0.22 + thick);
          return [
            Math.cos(az) * along - Math.sin(az) * side,
            vertical,
            Math.sin(az) * along + Math.cos(az) * side,
          ];
        };
        const q = [at(a, 0), at(a, 0.011), at(b, 0), at(b, 0.011)];
        for (const j of [0, 1, 2, 2, 1, 3]) {
          p.push(...q[j]);
          phase.push(ring / 3);
        }
      }
  const g = new T.BufferGeometry();
  g.setAttribute("position", new T.Float32BufferAttribute(p, 3));
  g.setAttribute("aPhase", new T.Float32BufferAttribute(phase, 1));
  return g;
}
export function buildTelecom(c, body, R, env) {
  const point = createPlacement(R),
    local = (x, y, h = 0) => point(c.at[0] + x, c.at[1] + y, h),
    b = new Batches(body, R, local, env),
    anchors = [];
  for (const roof of state.klyaksaTelecomRoofs || []) {
    if (roof.cityId !== c.id) continue;
    const x = roof.x - c.at[0],
      y = roof.y - c.at[1];
    b.add("roof-5G-three-sector-array", roofArray, x, y, roof.h);
    anchors.push({ x, y, h: roof.h + 3.7, type: "5G" });
  }
  const ground = c.facilities?.tower_pos || [c.wall + 110, 0],
    style = Number(c.id.replace(/\D/g, "")) % 2 ? "lattice" : "monopole";
  b.add("ground-4G-" + style, () => towerGeometry(style), ...ground, 0.2);
  b.add(
    "communications-control-shelter",
    () => {
      const m = new Model()
        .box(0, 2, 0, 9, 4, 6, palette.concrete)
        .box(0, 4.08, 0, 9.3, 0.18, 6.3, palette.metal)
        .box(0, 1.25, 3.04, 1.3, 2.5, 0.12, palette.dark);
      for (const x of [-3, 3]) {
        m.box(x, 2, 3.1, 1.4, 1.6, 0.12, palette.glass);
        for (let y = 0; y < 5; y++)
          m.box(x, 1.4 + y * 0.25, 3.18, 1.4, 0.04, 0.04, palette.metal);
      }
      return m.finish();
    },
    ground[0] + 13,
    ground[1] + 9,
  );
  anchors.push({
    x: ground[0],
    y: ground[1],
    h: (style === "lattice" ? 42 : 34) - 2,
    type: "4G",
  });
  // Service apron, gate cabinets and lightning earth connections stay on the utility parcel.
  b.add(
    "telecom-compound-apron",
    () => new Model().box(0, -0.1, 0, 42, 0.2, 42, 0x87928c).finish(),
    ground[0] + 3,
    ground[1],
  );
  b.add(
    "tower-concrete-plinth",
    () => new Model().box(0, -0.08, 0, 8, 0.28, 8, palette.concrete).finish(),
    ...ground,
    0.05,
  );
  b.add(
    "tower-feeder-cabinet",
    () =>
      new Model()
        .box(0, 0.85, 0, 1.2, 1.7, 0.6, palette.metal)
        .box(0, 0.9, 0.31, 0.9, 1.3, 0.025, palette.dark)
        .box(0.3, 1.2, 0.34, 0.08, 0.06, 0.025, 0x58d594)
        .finish(),
    ground[0] - 4,
    ground[1] - 3,
  );
  const access = c.facility_access?.tower_pos;
  if (access) {
    const road = new Surface(local),
      sx = ground[0] + (access.x < ground[0] ? -29 : 29),
      path = [
        [access.x, access.y],
        [sx, access.y],
        [sx, ground[1] + 29],
        [ground[0], ground[1] + 29],
        [ground[0], ground[1] + 15],
      ];
    for (let i = 1; i < path.length; i++) {
      road.strip(path[i - 1], path[i], 6, 0.18, 0x39464b);
      road.strip(path[i - 1], path[i], 0.12, 0.2, 0xd9d4ae);
    }
    body.add(road.mesh());
    b.add(
      "telecom-entry-barrier",
      () =>
        new Model()
          .box(-3.8, 0.9, 0, 0.45, 1.8, 0.45, palette.metal)
          .box(-3.8, 3.2, 0, 0.12, 4.4, 0.12, palette.white)
          .finish(),
      ground[0],
      ground[1] + 21,
    );
  }
  b.add(
    "mast-power-and-fibre-conduit",
    () =>
      new Model()
        .beam([-5, 8.8, -3], [-5, 0.45, -3], 0.055, palette.dark)
        .beam([-5, 0.45, -3], [-4, 0.45, -3], 0.055, palette.dark)
        .beam([-4, 0.45, -3], [0, 0.45, 0], 0.07, palette.dark)
        .finish(),
    ...ground,
  );
  b.finish();
  const material = new T.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      depthTest: true,
      side: T.DoubleSide,
      blending: T.AdditiveBlending,
      uniforms: { uTime: env.uTime },
      vertexShader: `attribute float aPhase;uniform float uTime;varying float vAlpha;void main(){float age=fract(uTime*.16+aPhase);float d=5.+age*58.;vAlpha=pow(1.-age,1.7)*.25;gl_Position=projectionMatrix*modelViewMatrix*instanceMatrix*vec4(position*d,1.);}`,
      fragmentShader: `varying float vAlpha;void main(){gl_FragColor=vec4(.17,.63,1.,vAlpha);}`,
    }),
    mesh = new T.InstancedMesh(coverageGeometry(), material, anchors.length),
    matrix = new T.Matrix4(),
    scale = new T.Vector3(1, 1, 1);
  anchors.forEach((a, i) => {
    const p = local(a.x, a.y, a.h),
      q = new T.Quaternion()
        .setFromUnitVectors(new T.Vector3(0, 1, 0), p.clone().normalize())
        .multiply(
          new T.Quaternion().setFromAxisAngle(
            new T.Vector3(0, 1, 0),
            planYaw(local, a.x, a.y),
          ),
        );
    mesh.setMatrixAt(i, matrix.compose(p, q, scale));
  });
  mesh.name = `${c.name} · directional 4G / 5G coverage`;
  mesh.frustumCulled = false;
  body.add(mesh);
  (state.klyaksaTelecomSites ||= new Map()).set(c.id, anchors);
  return anchors;
}
