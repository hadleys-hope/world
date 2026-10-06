/** Open dome portals and continuous intercity road galleries. */
import * as T from "three";
import { makeDome, glassMaterial } from "../oasis.js";
import { dirAt } from "../klyaksa.js";
import { Surface } from "./streets.js";
import { Model } from "./kit.js";
import { PLATEAU } from "../../geometry/noise.js";
import { state } from "../../state.js";

export function buildConnections(plan, body, R, env) {
  const grade = R * PLATEAU + 0.25;
  const point = (x, y, h = 0) => dirAt(x, y, R).multiplyScalar(R + grade + h);
  const frames = new Model(),
    portals = [];
  for (const c of plan.cities) {
    const gates = c.gates || [];
    const dome = makeDome(
      (x, y, h) => point(c.at[0] + x, c.at[1] + y, h),
      c.wall + 45,
      (c.wall + 45) * 0.42,
      { ...env, uStructure: { value: 0.18 }, uGlare: { value: 0.1 } },
      320,
      gates.map((g) => ({ angle: g.angle, width: 108, height: 35 })),
    );
    dome.name = `Dome ${c.id}`;
    body.add(dome);
    for (const g of gates) {
      const a = g.angle,
        forward = [Math.cos(a), Math.sin(a)],
        side = [-forward[1], forward[0]];
      const at = (s, h, d = 0) =>
        point(
          c.at[0] + g.x + side[0] * s + forward[0] * d,
          c.at[1] + g.y + side[1] * s + forward[1] * d,
          h,
        ).toArray();
      for (const depth of [-7, 7]) {
        for (let i = 0; i < 18; i++) {
          const a = (i / 18) * Math.PI,
            b = ((i + 1) / 18) * Math.PI;
          frames.beam(
            at(Math.cos(a) * 48, 4 + Math.sin(a) * 29, depth),
            at(Math.cos(b) * 48, 4 + Math.sin(b) * 29, depth),
            0.65,
            0x637e89,
          );
        }
        for (const s of [-48, 48])
          frames.beam(at(s, 0, depth), at(s, 4, depth), 0.8, 0x637e89);
      }
      for (let i = 0; i <= 6; i++) {
        const a = (i / 6) * Math.PI;
        frames.beam(
          at(Math.cos(a) * 48, 4 + Math.sin(a) * 29, -7),
          at(Math.cos(a) * 48, 4 + Math.sin(a) * 29, 7),
          0.22,
          0xacc7ce,
        );
      }
      portals.push({
        city: c.id,
        to: g.to,
        x: c.at[0] + g.x,
        y: c.at[1] + g.y,
        width: 96,
        clearance: 33,
      });
    }
  }
  const byId = new Map(plan.cities.map((c) => [c.id, c]));
  const streets = new Surface(point),
    glassP = [],
    glassUV = [],
    glassI = [],
    links = [];
  for (const [a, b] of plan.branches) {
    const A = byId.get(a),
      B = byId.get(b),
      ga = A.gates?.find((g) => g.to === b),
      gb = B.gates?.find((g) => g.to === a);
    if (!ga || !gb) continue;
    const start = [A.at[0] + ga.x, A.at[1] + ga.y],
      end = [B.at[0] + gb.x, B.at[1] + gb.y];
    const dx = end[0] - start[0],
      dy = end[1] - start[1],
      L = Math.hypot(dx, dy);
    const normal = [-dy / L, dx / L],
      N = Math.max(1, Math.ceil(L / 4));
    const at = (t) => [start[0] + dx * t, start[1] + dy * t];
    for (let i = 0; i < N; i++) {
      const p = at(i / N),
        q = at((i + 1) / N);
      streets.strip(p, q, 16, 0.24, 0x39454a);
      for (const side of [-7.5, 7.5])
        streets.strip(p, q, 0.18, 0.27, 0xede6cc, side);
      if (i % 3 < 2) streets.strip(p, q, 0.18, 0.27, 0xf6dfae);
      for (const side of [-10, 10])
        streets.strip(p, q, 3, 0.41, 0x84928d, side);
      if (i % 8 === 0)
        for (const side of [-12.5, 12.5]) {
          const x = p[0] + normal[0] * side,
            y = p[1] + normal[1] * side;
          frames.beam(
            point(x, y, 0).toArray(),
            point(x, y, 7).toArray(),
            0.13,
            0x7b8b91,
          );
          frames.beam(
            point(x, y, 7).toArray(),
            point(
              x - normal[0] * Math.sign(side) * 2,
              y - normal[1] * Math.sign(side) * 2,
              7,
            ).toArray(),
            0.12,
            0xfee2ae,
          );
        }
    }
    const base = glassP.length / 3,
      sections = Math.ceil(L / 12);
    for (let k = 0; k <= sections; k++) {
      const p = at(k / sections);
      for (let j = 0; j <= 20; j++) {
        const t = (j / 20) * Math.PI;
        const v = point(
          p[0] + normal[0] * Math.cos(t) * 45,
          p[1] + normal[1] * Math.cos(t) * 45,
          Math.sin(t) * 29 + 3,
        );
        glassP.push(v.x, v.y, v.z);
        glassUV.push(j / 20 / 3, (k * L) / sections / 400);
        if (k < sections && j < 20) {
          const n = base + k * 21 + j;
          glassI.push(n, n + 21, n + 1, n + 1, n + 21, n + 22);
        }
      }
    }
    links.push({ from: a, to: b, start, end, width: 16 });
  }
  const g = new T.BufferGeometry();
  g.setAttribute("position", new T.Float32BufferAttribute(glassP, 3));
  g.setAttribute("aUV", new T.Float32BufferAttribute(glassUV, 2));
  g.setIndex(glassI);
  g.computeVertexNormals();
  const gallery = new T.Mesh(
    g,
    glassMaterial({
      ...env,
      uStructure: { value: 0.35 },
      uGlare: { value: 0.12 },
    }),
  );
  gallery.renderOrder = 3;
  const steel = frames.finish();
  steel.setAttribute("color", steel.getAttribute("aCol"));
  body.add(
    gallery,
    streets.mesh(),
    new T.Mesh(
      steel,
      new T.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.65,
        metalness: 0.5,
      }),
    ),
  );
  state.klyaksaConnections = { portals, links };
}
