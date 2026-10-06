/** Connected, above-ground utility easements. This is presentation geometry, never a domain solver. */
import * as T from "three";
import { state } from "../../state.js";
import { bodyHeight } from "../../geometry/noise.js";
import { dirAt } from "../klyaksa.js";
import { createPlacement } from "./placement.js";
import { roadDeckHeight, roadCrossesRiver, roadElevation } from "./streets.js";
import { Model, Batches, palette, pole } from "./kit.js";
import { instances, chunkedInstances, lifeMaterial } from "../life.js";

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const segmentDistance = (p, a, b) => {
  const dx = b[0] - a[0],
    dy = b[1] - a[1],
    t = Math.max(
      0,
      Math.min(
        1,
        ((p.x - a[0]) * dx + (p.y - a[1]) * dy) / (dx * dx + dy * dy || 1),
      ),
    );
  return Math.hypot(p.x - a[0] - dx * t, p.y - a[1] - dy * t);
};
function samplePath(points, spacing = 28) {
  const out = [];
  let remain = 0;
  for (let j = 1; j < points.length; j++) {
    const a = points[j - 1],
      b = points[j],
      L = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (!L) continue;
    for (let d = remain; d < L; d += spacing)
      out.push({
        x: a[0] + ((b[0] - a[0]) * d) / L,
        y: a[1] + ((b[1] - a[1]) * d) / L,
        nx: -(b[1] - a[1]) / L,
        ny: (b[0] - a[0]) / L,
      });
    remain = (remain - L) % spacing;
    if (remain < 0) remain += spacing;
  }
  const a = points.at(-2),
    b = points.at(-1),
    L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
  out.push({ x: b[0], y: b[1], nx: -(b[1] - a[1]) / L, ny: (b[0] - a[0]) / L });
  return out;
}
/** Pure plan, shared by rendering and connectivity tests. Every service belongs to one explicit graph. */
export function utilityPlan(c) {
  const roads = [...(c.roads || []), ...(c.service_roads || [])].filter(
      (r) => r.points?.length > 1,
    ),
    nodes = [],
    edges = [],
    byId = new Map(),
    roadNodes = [];
  const add = (id, x, y, kind, extra = {}) => {
    if (byId.has(id)) return byId.get(id);
    const n = { id, x, y, kind, ...extra };
    byId.set(id, n);
    nodes.push(n);
    return n;
  };
  const join = (a, b, kind = "trunk", crossing = false) => {
    if (a !== b && dist(a, b) > 0.01)
      edges.push({ a: a.id, b: b.id, kind, crossing });
  };
  const segments = roads.flatMap((r) =>
      r.points.slice(1).map((b, i) => ({ a: r.points[i], b, w: r.width / 2 })),
    ),
    grid = new Map();
  for (const s of segments)
    for (
      let x = Math.floor((Math.min(s.a[0], s.b[0]) - 36) / 48);
      x <= Math.floor((Math.max(s.a[0], s.b[0]) + 36) / 48);
      x++
    )
      for (
        let y = Math.floor((Math.min(s.a[1], s.b[1]) - 36) / 48);
        y <= Math.floor((Math.max(s.a[1], s.b[1]) + 36) / 48);
        y++
      ) {
        const k = x + "," + y;
        if (!grid.has(k)) grid.set(k, []);
        grid.get(k).push(s);
      }
  const nearby = (p) =>
    grid.get(Math.floor(p.x / 48) + "," + Math.floor(p.y / 48)) || [];
  const clearance = (p) =>
    Math.min(100, ...nearby(p).map((s) => segmentDistance(p, s.a, s.b) - s.w));
  const junction = (id, p) => {
    id = "j/" + id;
    if (byId.has(id)) return byId.get(id);
    let best = { x: p[0] + 17, y: p[1] + 17 },
      score = -Infinity;
    for (const r of [18, 24, 30])
      for (let k = 0; k < 16; k++) {
        const a = (k * Math.PI) / 8,
          q = { x: p[0] + Math.cos(a) * r, y: p[1] + Math.sin(a) * r },
          v = Math.min(8, clearance(q)) - r * 0.025;
        if (v > score) {
          best = q;
          score = v;
        }
      }
    return add(id, best.x, best.y, "junction", { clearance: clearance(best) });
  };
  roads.forEach((r, ri) => {
    const A = r.points[0],
      B = r.points.at(-1),
      a = junction(r.from ?? A.join(","), A),
      b = junction(r.to ?? B.join(","), B),
      samples = samplePath(r.points),
      off = (r.width || 10) / 2 + 6;
    let previous = a;
    for (let i = 0; i < samples.length; i++) {
      const p = samples[i];
      if (
        Math.hypot(p.x - A[0], p.y - A[1]) < 15 ||
        Math.hypot(p.x - B[0], p.y - B[1]) < 15
      )
        continue;
      const n = add(
        `r/${ri}/${i}`,
        p.x + p.nx * off,
        p.y + p.ny * off,
        "road",
        {
          road: r.id ?? ri,
          nx: p.nx,
          ny: p.ny,
          clearance: off - (r.width || 10) / 2,
        },
      );
      roadNodes.push(n);
      join(previous, n, "trunk", previous === a);
      previous = n;
    }
    join(previous, b, "trunk", true);
  });
  const nearest = (p) => {
    let result = roadNodes[0] || nodes[0],
      d = Infinity;
    for (const n of roadNodes.length ? roadNodes : nodes) {
      const v = dist(p, n);
      if (v < d) {
        result = n;
        d = v;
      }
    }
    return result;
  };
  const waterParcel = (c.parcels || c.civic_plots || []).find(
      (p) => p.kind === "water",
    ),
    tank = add("tank", waterParcel?.x ?? 25, waterParcel?.y ?? -60, "tank"),
    water = c.facilities?.water_plant_pos || [tank.x + 40, tank.y],
    reactor = c.facilities?.reactor_pos || [-c.wall - 110, 0],
    network = c.facilities?.tower_pos || [c.wall + 110, 0];
  const sources = {
    water: add("source/water", water[0] + 28, water[1] - 29, "source"),
    power: add("source/power", reactor[0] + 40, reactor[1] + 10, "source"),
    telecom: add("source/telecom", network[0] - 5, network[1] - 3, "source"),
  };
  const transformer = (c.parcels || []).find((p) => p.kind === "transformer");
  if (transformer) {
    const n = add("substation", transformer.x + 22, transformer.y, "source");
    join(n, nearest(n), "feed", true);
  }
  join(tank, nearest(tank), "feed", true);
  for (const n of Object.values(sources)) join(n, nearest(n), "feed", true);
  const homes = [];
  for (let i = 0; i < c.houses; i++) {
    const p = { x: c.x[i], y: c.y[i] },
      access = { x: c.access_x?.[i] ?? p.x, y: c.access_y?.[i] ?? p.y },
      target = nearest(access),
      L = dist(p, target) || 1,
      nx = (target.x - p.x) / L,
      ny = (target.y - p.y) / L,
      yaw = c.yaw?.[i] ?? Math.atan2(p.y, p.x) + Math.PI / 2,
      co = Math.cos(yaw),
      si = Math.sin(yaw),
      lx = nx * co + ny * si,
      lz = nx * si - ny * co,
      t = 1 / Math.max(Math.abs(lx) / 4.3, Math.abs(lz) / 5.25),
      n = add(
        "house/" + (c.first_id + i),
        p.x + nx * (t + 0.18),
        p.y + ny * (t + 0.18),
        "house",
        {
          houseId: c.first_id + i,
          index: i,
          yaw,
          roofX: p.x + co * Math.sign(lx) * 4.48 + si * Math.sign(lz) * 5.43,
          roofY: p.y + si * Math.sign(lx) * 4.48 - co * Math.sign(lz) * 5.43,
        },
      );
    // A service on the opposite verge crosses the carriageway on a labelled steel gantry.
    const mid = { x: (target.x + n.x) / 2, y: (target.y + n.y) / 2 },
      crossing = nearby(mid).some((s) => {
        const dx = n.x - target.x,
          dy = n.y - target.y,
          ex = s.b[0] - s.a[0],
          ey = s.b[1] - s.a[1],
          d = dx * ey - dy * ex;
        if (Math.abs(d) < 1e-6) return false;
        const ax = s.a[0] - target.x,
          ay = s.a[1] - target.y,
          u = (ax * ey - ay * ex) / d,
          v = (ax * dy - ay * dx) / d;
        return u > 0 && u < 1 && v >= 0 && v <= 1;
      });
    join(target, n, "service", crossing);
    homes.push(n);
  }
  return {
    cityId: c.id,
    nodes,
    edges,
    homes,
    sources: Object.fromEntries(
      Object.entries(sources).map(([k, n]) => [k, n.id]),
    ),
    tank: tank.id,
  };
}
function instanceSegments(geometry, material, segments, name) {
  const mesh = new T.InstancedMesh(geometry, material, segments.length),
    m = new T.Matrix4(),
    q = new T.Quaternion(),
    scale = new T.Vector3(),
    p = new T.Vector3();
  segments.forEach((s, i) => {
    const axis = s.b.clone().sub(s.a),
      L = axis.length(),
      Y = axis.normalize(),
      Z = s.a
        .clone()
        .add(s.b)
        .normalize()
        .addScaledVector(Y, -s.a.clone().add(s.b).normalize().dot(Y))
        .normalize(),
      X = new T.Vector3().crossVectors(Y, Z).normalize();
    q.setFromRotationMatrix(m.makeBasis(X, Y, Z));
    p.copy(s.a).add(s.b).multiplyScalar(0.5);
    mesh.setMatrixAt(i, m.compose(p, q, scale.set(s.r, L, s.r)));
  });
  mesh.name = name;
  mesh.computeBoundingSphere();
  return mesh;
}
const placements = new WeakMap(),
  bridgeSegments = new WeakMap();
export function utilityPoint(c, R, x, y, h = 0) {
  let placement = placements.get(c);
  if (!placement) {
    placement = createPlacement(R);
    placements.set(c, placement);
  }
  let bridges = bridgeSegments.get(c);
  if (!bridges) {
    bridges = new Map();
    const all = [...(c.roads || []), ...(c.service_roads || [])]
      .filter((r) => roadCrossesRiver(c, r))
      .flatMap((r) =>
        r.points.slice(1).map((b, i) => ({ r, a: r.points[i], b })),
      );
    for (const s of all) {
      const margin = s.r.width / 2 + 9;
      for (
        let gx = Math.floor((Math.min(s.a[0], s.b[0]) - margin) / 48);
        gx <= Math.floor((Math.max(s.a[0], s.b[0]) + margin) / 48);
        gx++
      )
        for (
          let gy = Math.floor((Math.min(s.a[1], s.b[1]) - margin) / 48);
          gy <= Math.floor((Math.max(s.a[1], s.b[1]) + margin) / 48);
          gy++
        ) {
          const key = gx + "," + gy;
          if (!bridges.has(key)) bridges.set(key, []);
          bridges.get(key).push(s);
        }
    }
    bridgeSegments.set(c, bridges);
  }
  let lift = 0;
  for (const s of bridges.get(Math.floor(x / 48) + "," + Math.floor(y / 48)) ||
    [])
    if (segmentDistance({ x, y }, s.a, s.b) < s.r.width / 2 + 9) {
      lift = Math.max(lift, roadElevation(c, s.r, x, y));
    }
  return placement(c.at[0] + x, c.at[1] + y, h + lift);
}
export function buildUtilities(c, body, R, env) {
  const build = buildUtilitiesSteps(c, body, R, env);
  let next;
  do {
    next = build.next();
  } while (!next.done);
  return next.value;
}
export function* buildUtilitiesSteps(c, body, R, env) {
  const graph = utilityPlan(c),
    byId = new Map(graph.nodes.map((n) => [n.id, n])),
    point = (x, y, h = 0) => utilityPoint(c, R, x, y, h),
    root = new T.Group(),
    batch = new Batches(root, R, point, env),
    pipe = [],
    flow = [],
    wire = [],
    joints = [],
    supportHeights = new Map(),
    jointKeys = new Set();
  root.name = `${c.name} · connected above-ground utilities`;
  const metaById = new Map(
    (state.klyaksaHouseMeta || []).map((m) => [m.id, m]),
  );
  const nodeHeight = (n) => (n.kind === "house" ? 1.15 : 2.8);
  const segment = (a, b, r) => {
    if (a.distanceTo(b) > 0.015) {
      pipe.push({ a, b, r });
      flow.push({ a, b, r: r * 0.72 });
    }
  };
  const addSupport = (n, h = 2.8) =>
    batch.add(
      "pipe-saddle",
      () =>
        new Model()
          .box(0, 0.12, 0, 1.4, 0.24, 1.2, palette.concrete)
          .beam([-0.4, 0.2, 0], [-0.4, 1, 0], 0.08)
          .beam([0.4, 0.2, 0], [0.4, 1, 0], 0.08)
          .box(0, 1.03, 0, 1.1, 0.14, 0.6, palette.metal)
          .finish(),
      n.x,
      n.y,
      0,
      1,
      0,
      h / 1.1,
    );
  const support = (n, h = 2.8) => {
    const old = supportHeights.get(n.id);
    if (!old || h > old.h) supportHeights.set(n.id, { n, h });
  };
  const addJoint = (p) => {
    const key = p
      .toArray()
      .map((v) => v.toFixed(2))
      .join();
    if (jointKeys.has(key)) return;
    jointKeys.add(key);
    joints.push({
      a: p.clone().addScaledVector(p.clone().normalize(), -0.055),
      b: p.clone().addScaledVector(p.clone().normalize(), 0.055),
      r: 0.38,
    });
  };
  yield;
  let edgeCount = 0;
  for (const e of graph.edges) {
    const a = byId.get(e.a),
      b = byId.get(e.b),
      r = e.kind === "service" ? 0.13 : 0.3,
      ha = nodeHeight(a),
      hb = nodeHeight(b),
      A = point(a.x, a.y, ha),
      B = point(b.x, b.y, hb);
    if (e.crossing) {
      const h = 7.8,
        U = point(a.x, a.y, h),
        V = point(b.x, b.y, h);
      segment(A, U, r);
      segment(U, V, r);
      segment(V, B, r);
      addJoint(U);
      addJoint(V);
      if (a.kind !== "house") support(a, h);
      if (b.kind !== "house") support(b, h);
    } else segment(A, B, r);
    // Three uninterrupted catenaries terminate on actual insulators, including every roof entry mast.
    const roof = (n) =>
      metaById.get(n.houseId)?.height ??
      (1 + ((Math.imul(n.index + 31, 2654435761) >>> 0) % 10)) * 3.15 + 0.7;
    const anchor = (n) =>
      n.kind === "house"
        ? { x: n.roofX, y: n.roofY, h: roof(n) + 1.05 }
        : { x: n.x, y: n.y, h: 10.49 };
    const wa = anchor(a),
      wb = anchor(b),
      length = Math.hypot(wa.x - wb.x, wa.y - wb.y),
      sag = Math.min(2.1, length * 0.035);
    for (let phase = -1; phase <= 2; phase++) {
      let prior;
      const steps = Math.max(3, Math.ceil(length / 10));
      for (let j = 0; j <= steps; j++) {
        const t = j / steps,
          P = point(
            wa.x +
              (wb.x - wa.x) * t +
              (phase === 2 ? 0 : phase) *
                ((a.kind === "house" ? 0.55 : 1.1) * (1 - t) +
                  (b.kind === "house" ? 0.55 : 1.1) * t),
            wa.y + (wb.y - wa.y) * t,
            wa.h +
              (wb.h - wa.h) * t -
              sag * 4 * t * (1 - t) -
              (phase === 2
                ? (a.kind === "house" ? 0.55 : 1.69) * (1 - t) +
                  (b.kind === "house" ? 0.55 : 1.69) * t
                : 0),
          );
        if (prior)
          wire.push({
            a: prior,
            b: P,
            channel: phase === 2 ? 1 : 0,
            d0: (length * (j - 1)) / steps,
            d1: (length * j) / steps,
            r: e.kind === "service" ? 0.026 : 0.042,
          });
        prior = P;
      }
    }
    if (++edgeCount % 80 === 0) yield;
  }
  let nodeCount = 0;
  for (const n of graph.nodes) {
    if (++nodeCount % 120 === 0) yield;
    if (n.kind === "house") {
      const meta = metaById.get(n.houseId),
        height = meta?.height ?? 8;
      batch.add(
        "roof-service-mast",
        () => {
          const m = new Model()
            .cyl(0, 0.45, 0, 0.06, 0.9)
            .box(0, 0.8, 0, 1.4, 0.09, 0.09);
          for (let k = -1; k <= 1; k++)
            m.cyl(k * 0.55, 0.98, 0, 0.09, 0.26, palette.white, undefined, 6);
          return m.finish();
        },
        n.roofX,
        n.roofY,
        height + 0.05,
      );
      continue;
    }
    support(n);
    batch.add(
      "three-phase-pole",
      () => {
        const m = new Model();
        m.parts.push([pole().scale(1, 1.3, 1), null]);
        m.box(0, 8.8, 0, 0.3, 0.14, 0.3, palette.dark);
        return m.finish();
      },
      n.x,
      n.y,
    );
    addJoint(point(n.x, n.y, nodeHeight(n)));
  }
  for (const { n, h } of supportHeights.values()) addSupport(n, h);
  yield;
  const opaque = new T.MeshStandardMaterial({
      color: 0x547f83,
      metalness: 0.58,
      roughness: 0.4,
      side: T.DoubleSide,
    }),
    glass = new T.MeshStandardMaterial({
      color: 0xaddfe6,
      transparent: true,
      opacity: 0.2,
      roughness: 0.22,
      metalness: 0.35,
      depthWrite: false,
      side: T.DoubleSide,
    }),
    flowMaterial = new T.ShaderMaterial({
      uniforms: { uTime: env.uTime, uFlow: { value: 1 } },
      vertexShader: `varying float vY;varying vec3 vN;void main(){vY=position.y*length(instanceMatrix[1].xyz)+dot(instanceMatrix[3].xyz,vec3(.3,.2,.1));vN=normalize(mat3(modelMatrix)*mat3(instanceMatrix)*normal);gl_Position=projectionMatrix*modelViewMatrix*instanceMatrix*vec4(position,1.);}`,
      fragmentShader: `uniform float uTime,uFlow;varying float vY;varying vec3 vN;void main(){float wave=smoothstep(.65,.95,sin(vY*2.-uTime*2.2*uFlow));gl_FragColor=vec4(mix(vec3(.035,.31,.4),vec3(.33,.85,.93),wave*.6),1.);}`,
    });
  root.add(
    instanceSegments(
      new T.CylinderGeometry(1, 1, 1, 6, 1, true, Math.PI / 2, Math.PI),
      opaque,
      pipe,
      "insulated lower pipe shells",
    ),
    instanceSegments(
      new T.CylinderGeometry(1, 1, 1, 6, 1, true, -Math.PI / 2, Math.PI),
      glass,
      pipe,
      "inspection glass upper pipe shells",
    ),
    instanceSegments(
      new T.CylinderGeometry(1, 1, 1, 5, 1, true),
      flowMaterial,
      flow,
      "visible flowing water",
    ),
    instanceSegments(
      new T.CylinderGeometry(1, 1, 1, 4, 1, true),
      opaque,
      joints,
      "flanged pipe junctions",
    ),
  );
  yield;
  const wirePositions = Float32Array.from(
      wire.flatMap((s) => [...s.a.toArray(), ...s.b.toArray()]),
    ),
    wireGeometry = new T.BufferGeometry();
  wireGeometry.setAttribute(
    "position",
    new T.BufferAttribute(wirePositions, 3),
  );
  wireGeometry.setAttribute(
    "aDistance",
    new T.Float32BufferAttribute(
      wire.flatMap((s) => [s.d0, s.d1]),
      1,
    ),
  );
  wireGeometry.setAttribute(
    "aChannel",
    new T.Float32BufferAttribute(
      wire.flatMap((s) => [s.channel, s.channel]),
      1,
    ),
  );
  const cables = new T.LineSegments(
    wireGeometry,
    new T.ShaderMaterial({
      uniforms: { uTime: env.uTime },
      vertexShader: `attribute float aDistance,aChannel;varying float vDistance,vChannel;void main(){vDistance=aDistance;vChannel=aChannel;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
      fragmentShader: `uniform float uTime;varying float vDistance,vChannel;void main(){float pulse=pow(max(0.,sin(vDistance*.34-uTime*3.)),18.);vec3 signalColor=mix(vec3(.86,.56,.18),vec3(.12,.7,1.),vChannel);gl_FragColor=vec4(mix(vec3(.07,.09,.1),signalColor,pulse*.8),1.);}`,
    }),
  );
  cables.name = "continuous three phase and fibre catenaries";
  root.add(cables);
  // One cheap far batch stays visible for every object. Fine fittings are submitted only near the camera.
  const farPrototypes = {
    "three-phase-pole": () =>
      new Model()
        .box(0, 5.59, 0, 0.22, 11.18, 0.22, palette.metal)
        .box(0, 10.01, 0, 3, 0.18, 0.18, palette.metal)
        .box(0, 10.48, 2.2, 0.55, 0.15, 1.1, 0xffdf9d)
        .finish(),
    "roof-service-mast": () =>
      new Model()
        .box(0, 0.5, 0, 0.09, 1, 0.09, palette.metal)
        .box(0, 0.8, 0, 1.4, 0.09, 0.09, palette.metal)
        .finish(),
    "pipe-saddle": () =>
      new Model().box(0, 0.5, 0, 0.8, 1, 0.25, palette.metal).finish(),
  };
  yield;
  for (const [key, g] of batch.groups) {
    const far = lifeMaterial(env, { indoor: 1 }),
      near = lifeMaterial(env, { indoor: 1 });
    far.vertexShader = far.vertexShader.replace(
      "float ph=",
      "if(distance((modelMatrix*vec4(o,1.)).xyz,cameraPosition)<160.){gl_Position=vec4(2.,2.,2.,1.);return;} float ph=",
    );
    near.vertexShader = near.vertexShader.replace(
      "float ph=",
      "if(distance((modelMatrix*vec4(o,1.)).xyz,cameraPosition)>=160.){gl_Position=vec4(2.,2.,2.,1.);return;} float ph=",
    );
    const cheap = instances(
      farPrototypes[key]?.() || g.geometry,
      far,
      g.items,
      R,
    );
    cheap.name = key + " · distant silhouette";
    root.add(cheap);
    const detail = chunkedInstances(() => g.geometry, near, g.items, R, {
      cell: 0.015,
      maxDist: 165,
    });
    detail.name = key + " · nearby fittings";
    root.add(detail);
    (state.klyaksaLod ||= []).push(detail);
    yield;
  }
  (state.klyaksaWaterMaterials ||= new Map()).set(c.id, flowMaterial);
  body.add(root);
  (state.klyaksaUtilityGraphs ||= new Map()).set(c.id, graph);
  return graph;
}

/** Port utilities share the city supply graph and the exact same raised access-road grade. */
export function buildPortWaterExtension(c, points, body, R, env, point) {
  if (points.length < 2) return;
  const graph = state.klyaksaUtilityGraphs?.get(c.id);
  if (!graph) return;
  const samples = samplePath(points, 18),
    offset = samples.map((p) => ({ x: p.x - p.nx * 8, y: p.y - p.ny * 8 })),
    start = offset[0];
  let from = null,
    d = Infinity;
  for (const n of graph.nodes) {
    if (!["road", "junction"].includes(n.kind)) continue;
    const length = Math.hypot(c.at[0] + n.x - start.x, c.at[1] + n.y - start.y);
    if (length < d) {
      d = length;
      from = n;
    }
  }
  if (!from) return;
  const segments = [],
    root = new T.Group(),
    b = new Batches(root, R, point, env),
    pipeRadius = 0.22,
    at = (p, h = 2.6) => point(p.x, p.y, h),
    startPoint = utilityPoint(c, R, from.x, from.y, 2.8),
    raised = startPoint
      .clone()
      .addScaledVector(startPoint.clone().normalize(), 5);
  segments.push(
    { a: startPoint, b: raised, r: pipeRadius },
    { a: raised, b: at(start, 7.8), r: pipeRadius },
    { a: at(start, 7.8), b: at(start), r: pipeRadius },
  );
  const key = "port/" + Math.round(start.x) + "/" + Math.round(start.y);
  let prior = from.id;
  for (let i = 0; i < offset.length; i++) {
    const p = offset[i],
      id = key + "/" + i;
    graph.nodes.push({ id, x: p.x - c.at[0], y: p.y - c.at[1], kind: "port" });
    graph.edges.push({ a: prior, b: id, kind: "port-feed" });
    prior = id;
    if (i) segments.push({ a: at(offset[i - 1]), b: at(p), r: pipeRadius });
    b.add(
      "harbour-water-pipe-support",
      () =>
        new Model()
          .box(0, 0.13, 0, 1.1, 0.26, 1.1, palette.concrete)
          .box(0, 1.4, 0, 0.15, 2.6, 0.25, palette.metal)
          .box(0, 2.56, 0, 0.75, 0.12, 0.4, palette.metal)
          .finish(),
      p.x,
      p.y,
    );
  }
  const terminal = offset.at(-1);
  b.add(
    "harbour-water-meter-and-valve",
    () =>
      new Model()
        .box(0, 0.7, 0, 1.6, 1.4, 1, palette.metal)
        .cyl(0, 1.7, 0, 0.18, 1.8, 0x588f99)
        .box(0.9, 1.1, 0, 0.55, 0.9, 0.5, palette.white)
        .box(0.9, 1.25, 0.27, 0.36, 0.25, 0.02, palette.dark)
        .finish(),
    terminal.x,
    terminal.y,
  );
  const shell = new T.MeshStandardMaterial({
      color: 0x547f83,
      metalness: 0.55,
      roughness: 0.45,
      side: T.DoubleSide,
    }),
    glass = new T.MeshStandardMaterial({
      color: 0xb8e8ed,
      transparent: true,
      opacity: 0.22,
      roughness: 0.25,
      depthWrite: false,
      side: T.DoubleSide,
    });
  root.add(
    instanceSegments(
      new T.CylinderGeometry(1, 1, 1, 5, 1, true, Math.PI / 2, Math.PI),
      shell,
      segments,
      "harbour supply insulated lower shell",
    ),
    instanceSegments(
      new T.CylinderGeometry(1, 1, 1, 5, 1, true, -Math.PI / 2, Math.PI),
      glass,
      segments,
      "harbour supply inspection glass",
    ),
    instanceSegments(
      new T.CylinderGeometry(1, 1, 1, 5, 1, true),
      state.klyaksaWaterMaterials?.get(c.id) || shell,
      segments.map((s) => ({ ...s, r: s.r * 0.72 })),
      "harbour supply visible flow",
    ),
  );
  b.finish();
  root.name = c.name + " · harbour water supply";
  body.add(root);
}
