/** Finite river surface, carved channel, masonry embankments and actual bridge structures. */
import * as T from "three";
import { state } from "../../state.js";
import { dirAt } from "../klyaksa.js";
import { bodyHeight, PLATEAU } from "../../geometry/noise.js";
import { Batches, Model, palette, bench, bin, pole } from "./kit.js";
import { Surface, roadElevation } from "./streets.js";
import { RiverFlow } from "./river-flow.js";
import {
  riverBounds,
  riverCentre,
  riverWidth,
  riverLevel,
  riverDepth,
  riverContains,
} from "./geography.js";
function bridgeGeometry(width = 18, span = 112, tower = 47, drop = 42) {
  const m = new Model(),
    half = span / 2;
  // The rigid box girder is recessed below the spherical road surface.
  // A 210m flat slab otherwise rises ~0.46m into its curved asphalt at the ends.
  m.box(0, -1.75, 0, width, 2, span, 0x819497);
  for (const side of [-1, 1]) {
    const x = side * (width / 2 - 0.6);
    m.box(x, 0.14, 0, 1.2, 0.28, span, 0xb8b8ad);
    m.beam([x, 1.25, -half], [x, 1.25, half], 0.07, palette.metal);
    for (let z = -half; z <= half; z += 5)
      m.beam([x, 0, z], [x, 1.25, z], 0.04, palette.metal);
    for (const z of [-half * 0.72, half * 0.72]) {
      m.box(x, (tower - drop) / 2, z, 1.8, tower + drop, 2.4, palette.concrete);
      for (let v = 8; v < half * 0.8; v += 8) {
        m.beam([x, tower, z], [x, 0.35, z - v], 0.085, 0xc4d2cf);
        m.beam([x, tower, z], [x, 0.35, z + v], 0.085, 0xc4d2cf);
      }
    }
  }
  for (const z of [-half * 0.72, half * 0.72])
    m.beam(
      [-width / 2 + 0.6, tower - 4, z],
      [width / 2 - 0.6, tower - 4, z],
      0.75,
      palette.concrete,
    );
  return m.finish();
}
export function riverCrossings(city) {
  if (city.id !== "k1") return [];
  const result = [];
  for (const road of city.roads || [])
    for (let i = 1; i < road.points.length; i++) {
      const a = road.points[i - 1],
        b = road.points[i],
        da = a[1] - riverCentre(a[0]),
        db = b[1] - riverCentre(b[0]);
      if (da * db > 0 || Math.abs(da - db) < 1e-6) continue;
      const t = da / (da - db),
        x = a[0] + (b[0] - a[0]) * t,
        y = riverCentre(x);
      if (
        !riverContains(x, y) ||
        Math.abs(x) > city.wall + 80 ||
        result.some((p) => Math.hypot(p.x - x, p.y - y) < 30)
      )
        continue;
      result.push({
        x,
        y,
        heading: Math.atan2(b[1] - a[1], b[0] - a[0]),
        width: road.width || 14,
        road: road.id,
      });
    }
  return result;
}
export function* buildRiverSceneSteps(body, R, plan, env) {
  const { source, mouth } = riverBounds(),
    sea = (x, y, h = 0) => dirAt(x, y, R).multiplyScalar(R + h);
  const flow = new RiverFlow({
    count: 160,
    length: mouth - source,
    bed: (s) => riverLevel(source + s) - riverDepth(source + s),
    depth: (s) => riverDepth(source + s),
  });
  const tex = new T.DataTexture(
    flow.encoded,
    flow.count,
    1,
    T.RGBAFormat,
    T.UnsignedByteType,
  );
  tex.minFilter = tex.magFilter = T.LinearFilter;
  tex.needsUpdate = true;
  state.klyaksaRiverFlow = { flow, texture: tex, source, mouth };
  const points = [],
    uv = [],
    norm = [],
    depth = [];
  const bed = new Surface(sea),
    banks = new Surface(sea),
    b = new Batches(body, R, sea, env);
  const vertex = (x, t) => {
    const y = riverCentre(x) + riverWidth(x) * t,
      n = dirAt(x, y, R);
    points.push(
      ...n
        .clone()
        .multiplyScalar(R + riverLevel(x) + 0.08)
        .toArray(),
    );
    norm.push(...n.toArray());
    uv.push((x - source) / (mouth - source), (t + 1) / 2);
    depth.push(riverDepth(x));
  };
  const n = Math.ceil((mouth - source) / 8);
  for (let i = 0; i < n; i++) {
    if (i % 80 === 0) yield;
    const a = source + ((mouth - source) * i) / n,
      c = source + ((mouth - source) * (i + 1)) / n;
    for (let j = 0; j < 8; j++) {
      const l = -1 + j / 4,
        h = l + 0.25;
      for (const [x, t] of [
        [a, l],
        [a, h],
        [c, l],
        [c, l],
        [a, h],
        [c, h],
      ])
        vertex(x, t);
    }
    for (let j = 0; j < 8; j++) {
      const l = -1 + j / 4,
        h = l + 0.25,
        at = (x, t) => [
          x,
          riverCentre(x) + riverWidth(x) * t,
          riverLevel(x) - riverDepth(x, t),
        ];
      bed.quad([at(a, l), at(a, h), at(c, l), at(c, h)], 0x596e62);
    }
    for (const side of [-1, 1]) {
      const urban = Math.abs(a) < 1100,
        innerX = a,
        // Inset the vertical wall inside the channel: finite terrain facets at the
        // transition otherwise protrude through the lower masonry courses.
        inset = urban ? 4 : 0,
        innerY = riverCentre(a) + side * (riverWidth(a) - inset),
        nextY = riverCentre(c) + side * (riverWidth(c) - inset);
      const bankTop = (x) =>
        urban
          ? R * PLATEAU
          : Math.max(
              riverLevel(x) + 3,
              bodyHeight(
                3,
                ...dirAt(
                  x,
                  riverCentre(x) + side * (riverWidth(x) + 32),
                  R,
                ).toArray(),
                true,
              ) * R,
            );
      if (urban) {
        // Prepared city plots use grade+.25; promenade slabs must clear that grade.
        const top = R * PLATEAU + 0.5;
        // Independent face/coping and mortar courses make the quay a wall, not a flat ribbon.
        banks.quad(
          [
            [a, innerY, riverLevel(a) - 6],
            [a, innerY, top],
            [c, nextY, riverLevel(c) - 6],
            [c, nextY, top],
          ],
          0x7c8586,
        );
        banks.quad(
          [
            [a, innerY, top + 0.15],
            [a, innerY + side * 8, top + 0.15],
            [c, nextY, top + 0.15],
            [c, nextY + side * 8, top + 0.15],
          ],
          0xb0aaa0,
        );
        if (i % 2 === 0)
          for (let k = 0; k < 5; k++)
            b.add(
              "quay-stone",
              () => {
                const m = new Model();
                for (let q = 0; q < 4; q++)
                  m.box(-6 + q * 4, 0, 0, 3.94, 1.38, 0.18, 0x909793);
                return m.finish();
              },
              a + 4,
              riverCentre(a + 4) +
                side * (riverWidth(a + 4) - inset) -
                side * 0.24,
              top - 0.72 - k * 1.48,
              1,
              Math.atan2(riverCentre(a + 5) - riverCentre(a + 3), 2),
              1,
              [0.9 + (i % 3) * 0.05, 1, 1],
            );
        if (i % 5 === 0) {
          b.add(
            "quay-bench",
            bench,
            a,
            innerY + side * 5.8,
            top + 0.2,
            1,
            side > 0 ? 0 : Math.PI,
          );
          b.add("quay-bin", bin, a + 3, innerY + side * 5.8, top + 0.2);
          b.add("quay-lamp", pole, a, innerY + side * 7, top + 0.2);
        }
        // Cycle path lies behind the stone coping; the continuous riverfront is pedestrian space.
        banks.quad(
          [
            [a, innerY + side * 8, top + 0.17],
            [a, innerY + side * 11, top + 0.17],
            [c, nextY + side * 8, top + 0.17],
            [c, nextY + side * 11, top + 0.17],
          ],
          0x617f78,
        );
      } else {
        banks.quad(
          [
            [a, innerY, riverLevel(a) - 1],
            [a, innerY + side * 34, bankTop(a)],
            [c, nextY, riverLevel(c) - 1],
            [c, nextY + side * 34, bankTop(c)],
          ],
          0x71876a,
        );
        if (i % 7 === 0 && a < -1150)
          b.add(
            "river-rock",
            () => {
              const m = new Model();
              m.parts.push([new T.IcosahedronGeometry(1, 1), 0x8c9082]);
              return m.finish();
            },
            a,
            innerY - side * 3,
            riverLevel(a) - 0.25,
            1.6 + (i % 3),
          );
      }
    }
  }
  // Passenger landings sit inside the retaining wall and leave the central freight fairway open.
  state.klyaksaRiverPiers = [];
  const crossingPositions = riverCrossings(
    plan.cities.find((c) => c.id === "k1"),
  );
  for (let x = -760; x < 800; x += 220) {
    if (crossingPositions.some((q) => Math.abs(q.x - x) < 85)) continue;
    const side = x < 0 ? 1 : -1,
      y = riverCentre(x) + side * (riverWidth(x) - 9),
      level = riverLevel(x) + 1.5;
    banks.quad(
      [
        [x - 22, y - 3, level],
        [x - 22, y + 3, level],
        [x + 22, y - 3, level],
        [x + 22, y + 3, level],
      ],
      0xa9a08b,
    );
    banks.quad(
      [
        [x - 3, y, level],
        [x + 3, y, level],
        [x - 3, y + side * 5, R * PLATEAU + 0.65],
        [x + 3, y + side * 5, R * PLATEAU + 0.65],
      ],
      0xa19b8d,
    );
    banks.quad(
      [
        [x - 3, y + side * 5, R * PLATEAU + 0.65],
        [x + 3, y + side * 5, R * PLATEAU + 0.65],
        [x - 3, y + side * 18, R * PLATEAU + 0.65],
        [x + 3, y + side * 18, R * PLATEAU + 0.65],
      ],
      0xa19b8d,
    );
    for (const dx of [-18, -6, 6, 18]) {
      b.add(
        "landing-pile",
        () => new Model().cyl(0, -4, 0, 0.4, 8, palette.metal).finish(),
        x + dx,
        y,
        level,
      );
      b.add(
        "landing-bollard",
        () => new Model().cyl(0, 0.3, 0, 0.2, 0.6, palette.dark).finish(),
        x + dx,
        y - side * 2.6,
        level,
      );
    }
    state.klyaksaRiverPiers.push({ x, y, width: 44, depth: 6 });
  }
  yield;
  const geometry = new T.BufferGeometry();
  geometry.setAttribute("position", new T.Float32BufferAttribute(points, 3));
  geometry.setAttribute("normal", new T.Float32BufferAttribute(norm, 3));
  geometry.setAttribute("uv", new T.Float32BufferAttribute(uv, 2));
  geometry.setAttribute("aDepth", new T.Float32BufferAttribute(depth, 1));
  const material = new T.ShaderMaterial({
    uniforms: {
      ...env,
      uFlow: { value: tex },
      uLength: { value: mouth - source },
    },
    side: T.DoubleSide,
    transparent: true,
    depthWrite: false,
    vertexShader: `uniform sampler2D uFlow;uniform float uTime,uLength;attribute float aDepth;varying vec2 vUV;varying vec3 vW,vN;void main(){vUV=uv;vec2 f=texture2D(uFlow,vec2(uv.x,.5)).rg;float s=uv.x*uLength-uTime*(f.r*32.-8.);float wave=sin(s*.65+uv.y*15.)*.07+sin(s*.21-uv.y*56.)*.04;float rise=clamp((f.g*20.-aDepth)*.3,-.4,.4);vec3 p=position+normal*(wave+rise)*(1.-smoothstep(.96,1.,uv.x));vN=normalize(mat3(modelMatrix)*normal);vec4 w=modelMatrix*vec4(p,1.);vW=w.xyz;gl_Position=projectionMatrix*viewMatrix*w;}`,
    fragmentShader: `uniform sampler2D uFlow;uniform float uTime,uLength;uniform vec3 uSun;varying vec2 vUV;varying vec3 vW,vN;void main(){vec3 f=texture2D(uFlow,vec2(vUV.x,.5)).rgb;float speed=f.r*32.-8.;float s=vUV.x*uLength-uTime*speed;float lateral=vUV.y*80.;float wave=sin(s*.65+lateral*.19)*.034+sin(s*.21-lateral*.72)*.026;vec3 n=normalize(vN+vec3(wave,cos(s*.49)*.032,sin(s*.34)*.026));vec3 view=normalize(cameraPosition-vW);float fres=pow(1.-abs(dot(n,view)),3.);float spec=pow(max(dot(reflect(-normalize(uSun),n),view),0.),90.);float bank=pow(abs(vUV.y*2.-1.),16.);float streak=pow(max(0.,sin(s*.48+sin(lateral*1.7))),14.);float shoal=exp(-pow((vUV.x*uLength-350.)/75.,2.));float foam=clamp((bank*.42+f.b*1.6+shoal*.85)*streak,0.,.8);vec3 col=mix(vec3(.032,.14,.13),vec3(.18,.40,.43),fres);col=mix(col,vec3(.85,.91,.85),foam)+spec*.9;float mouth=1.-smoothstep(.975,1.,vUV.x);gl_FragColor=vec4(col,mouth);}`,
  });
  const riverMesh = new T.Mesh(geometry, material);
  riverMesh.name = "Meridian finite river · solved flow";
  riverMesh.renderOrder = 3;
  body.add(riverMesh, bed.mesh(), banks.mesh({ paving: true }), b.finish());
  state.klyaksaBridges = [];
  yield;
  const city = plan.cities.find((c) => c.id === "k1"),
    bridgeBatch = new Batches(
      body,
      R,
      (x, y, h = 0) => sea(x, y, R * PLATEAU + h),
      env,
    );
  for (const crossing of riverCrossings(city)) {
    yield;
    bridgeBatch.add(
      `bridge-${crossing.width}`,
      () => bridgeGeometry(crossing.width + 5),
      crossing.x,
      crossing.y,
      24.4,
      1,
      Math.PI / 2 + crossing.heading,
    );
    state.klyaksaBridges.push({
      ...crossing,
      deckHeight: R * PLATEAU + 24.4,
      kind: "cable-stayed",
    });
  }
  yield;
  const girders = new Surface(sea);
  let approachSegments = 0;
  for (const road of city.roads.filter((r) => r.bridge))
    for (let i = 1; i < road.points.length; i++) {
      if (++approachSegments % 160 === 0) yield;
      const A = road.points[i - 1],
        B = road.points[i],
        L = Math.hypot(B[0] - A[0], B[1] - A[1]),
        nx = -(B[1] - A[1]) / L,
        ny = (B[0] - A[0]) / L,
        half = (road.width || 14) / 2 + 2.5;
      const count = Math.max(1, Math.ceil(L / 8));
      for (let j = 0; j < count; j++) {
        const at = (t) => [A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t],
          a = at(j / count),
          b = at((j + 1) / count),
          ha = R * PLATEAU + roadElevation(city, road, ...a) + 0.4,
          hb = R * PLATEAU + roadElevation(city, road, ...b) + 0.4;
        if (Math.max(ha, hb) < R * PLATEAU + 1) continue;
        for (const side of [-1, 1])
          girders.quad(
            [
              [a[0] + nx * half * side, a[1] + ny * half * side, ha],
              [a[0] + nx * half * side, a[1] + ny * half * side, ha - 1.6],
              [b[0] + nx * half * side, b[1] + ny * half * side, hb],
              [b[0] + nx * half * side, b[1] + ny * half * side, hb - 1.6],
            ],
            0x859392,
          );
        girders.quad(
          [
            [a[0] - nx * half, a[1] - ny * half, ha - 1.6],
            [a[0] + nx * half, a[1] + ny * half, ha - 1.6],
            [b[0] - nx * half, b[1] - ny * half, hb - 1.6],
            [b[0] + nx * half, b[1] + ny * half, hb - 1.6],
          ],
          0x677879,
        );
        if (j % 4 === 0 && !riverContains(...a, 8)) {
          const h = ha - R * PLATEAU;
          bridgeBatch.add(
            "approach-column",
            () =>
              new Model()
                .box(0, -0.5, 0, 2.2, 1, 2.2, palette.concrete)
                .finish(),
            ...a,
            h,
            1,
            0,
            h,
          );
        }
      }
    }
  yield;
  body.add(bridgeBatch.finish(), girders.mesh());
  yield;
  // A separate landmark bridge outside the dome: navigable span, deep box girder and graded approaches.
  const x = 1530,
    y = riverCentre(x),
    span = 210,
    deck = riverLevel(x) + 34,
    outside = new Batches(body, R, sea, env);
  outside.add(
    "estuary-landmark",
    () => bridgeGeometry(23, span, 72, 50),
    x,
    y,
    deck,
    1,
    Math.PI,
  );
  const access = new Surface(sea);
  for (let z = -span / 2; z < span / 2; z += 8) {
    const next = Math.min(span / 2, z + 8);
    access.quad(
      [
        [x - 10, y + z, deck + 0.03],
        [x + 10, y + z, deck + 0.03],
        [x - 10, y + next, deck + 0.03],
        [x + 10, y + next, deck + 0.03],
      ],
      0x38484f,
    );
  }
  for (let z = -span / 2; z < span / 2; z += 12)
    access.strip(
      [x, y + z],
      [x, y + Math.min(span / 2, z + 6)],
      0.22,
      deck + 0.05,
      0xe8dcac,
    );
  const eastgate = plan.cities.find((c) => c.id === "k2"),
    corridorY = (eastgate.at[1] * x) / eastgate.at[0],
    northRun = Math.max(360, corridorY - y);
  for (const side of [-1, 1])
    for (let d = span / 2; d < (side > 0 ? northRun : 500); d += 8) {
      const at = (s) => {
          const yy = y + side * s,
            n = dirAt(x, yy, R),
            ground = bodyHeight(3, n.x, n.y, n.z) * R;
          return [x, yy, Math.max(ground + 0.3, deck - (s - span / 2) * 0.065)];
        },
        a = at(d),
        c = at(Math.min(side > 0 ? northRun : 500, d + 8));
      // Width subdivision follows the spherical surface, while the approach profile is shared at every seam.
      access.quad(
        [
          [a[0] - 11, a[1], a[2]],
          [a[0] + 11, a[1], a[2]],
          [c[0] - 11, c[1], c[2]],
          [c[0] + 11, c[1], c[2]],
        ],
        0x39494f,
      );
      if (d % 32 < 8)
        outside.add(
          "bridge-approach-pier",
          () => new Model().box(0, -15, 0, 2, 30, 2, palette.concrete).finish(),
          x,
          a[1],
          a[2],
        );
    }
  // South approach terminates in a bridge maintenance depot, not an unexplained road stub.
  const ty = y - 520,
    tn = dirAt(x, ty, R),
    th =
      Math.max(
        bodyHeight(3, tn.x, tn.y, tn.z) * R,
        deck - (500 - span / 2) * 0.065,
      ) + 0.3;
  access.quad(
    [
      [x - 50, ty - 65, th],
      [x + 90, ty - 65, th],
      [x - 50, ty + 30, th],
      [x + 90, ty + 30, th],
    ],
    0x7f8983,
  );
  outside.add(
    "bridge-depot",
    () => {
      const m = new Model()
        .box(0, 6, 0, 42, 12, 23, palette.concrete)
        .box(0, 12.2, 0, 45, 0.5, 26, palette.metal);
      for (const v of [-13, 0, 13]) m.box(v, 4, 11.6, 9, 8, 0.15, palette.dark);
      return m.finish();
    },
    x + 58,
    ty - 37,
    th,
  );
  for (let k = 0; k < 8; k++) {
    outside.add(
      "maintenance-parked",
      () =>
        new Model()
          .box(0, 0.7, 0, 2.2, 1.4, 4.5, palette.white)
          .box(0, 1.8, -0.7, 1.9, 0.8, 2, palette.glass)
          .finish(),
      x - 35 + k * 4,
      ty - 42,
      th,
    );
    access.strip(
      [x - 37 + k * 4, ty - 47],
      [x - 37 + k * 4, ty - 36],
      0.15,
      th + 0.03,
      0xe5dcc1,
    );
  }
  for (const X of [x - 43, x + 83])
    for (const Y of [ty - 55, ty + 20])
      outside.add("maintenance-lamp", pole, X, Y, th);
  yield;
  body.add(outside.finish(), access.mesh());
  state.klyaksaBridges.push({
    x,
    y,
    deckHeight: deck,
    kind: "landmark-cable-stayed",
  });
}
/** Synchronous export used by scene regression fixtures. */
export function buildRiverScene(...args) {
  for (const _ of buildRiverSceneSteps(...args)) void _;
}
export function updateRiverFlow(dt) {
  const water = state.klyaksaRiverFlow;
  if (!water) return;
  water.flow.step(dt);
  water.texture.needsUpdate = true;
}
