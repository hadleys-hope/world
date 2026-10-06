import assert from "node:assert/strict";
import fs from "node:fs";
import * as T from "three";
import { dirAt } from "../web/static/js/map3d/models/klyaksa.js";
import {
  harbourAccess,
  quayMeshes,
} from "../web/static/js/map3d/models/urban/marine.js";
const plan = JSON.parse(
  fs.readFileSync(
    new URL("../test-results/visual-fixture.json", import.meta.url),
  ),
).geometry;
for (const city of plan.cities)
  for (const a of [-2.7, -1.1, 0.4, 1.8]) {
    const score = city.wall + 1800,
      coast = {
        x: city.at[0] + Math.cos(a) * score,
        y: city.at[1] + Math.sin(a) * score,
        a,
        score,
      },
      points = harbourAccess(city, coast);
    assert(points.length > 20);
    assert(
      city.gates.some(
        (g) =>
          Math.hypot(
            city.at[0] + g.x - points[0][0],
            city.at[1] + g.y - points[0][1],
          ) < 1e-6,
      ),
      "harbour road starts at an actual city gate",
    );
    assert(
      points.every(
        ([x, y]) => Math.hypot(x - city.at[0], y - city.at[1]) > city.wall + 34,
      ),
      "access route must not cut city parcels or dome wall",
    );
    for (let i = 1; i < points.length; i++)
      assert(
        Math.hypot(
          points[i][0] - points[i - 1][0],
          points[i][1] - points[i - 1][1],
        ) < 4.5,
        "spherical road surface samples must stay dense",
      );
  }
console.log(
  "Harbour access: 24 route directions use real gates, clear every city footprint, and keep surface samples under4.5m.",
);

// Actual ray intersections, including the long quay ends where the old flat foundation emerged.
const R = 12000,
  point = (u, v, h = 0) => dirAt(-3100 + u, -2400 + v, R).multiplyScalar(R + h),
  quay = quayMeshes(point),
  ray = new T.Raycaster();
quay.deck.updateMatrixWorld(true);
quay.foundation.updateMatrixWorld(true);
for (const u of [-75, -40, -5])
  for (const v of [-195, -100, 0, 100, 195]) {
    const normal = point(u, v).normalize();
    ray.set(normal.clone().multiplyScalar(R + 20), normal.clone().negate());
    const deck = ray.intersectObject(quay.deck)[0],
      base = ray.intersectObject(quay.foundation)[0];
    assert(
      deck && base,
      "every quay sample has both a deck and supporting caisson",
    );
    assert(
      base.distance - deck.distance > 0.5,
      "caisson stays below curved paving across the whole400m quay",
    );
    assert(
      Math.abs(deck.point.length() - R - 4) < 0.015,
      "curved deck stays at intended radial grade",
    );
  }
console.log(
  "Quay geometry: 15 ray samples verify radial grade and foundation clearance, including both ends.",
);
