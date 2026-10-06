import assert from "node:assert/strict";
import {
  RiverFlow,
  flowDiagnostics,
} from "../web/static/js/map3d/models/urban/river-flow.js";
// Lake at rest on non-flat bathymetry: hydrostatic reconstruction must balance pressure and gravity.
const bed = (s) => 1.2 * Math.exp(-(((s - 500) / 90) ** 2));
const lake = new RiverFlow({
  length: 1000,
  count: 100,
  bed,
  depth: (s) => 8 - bed(s),
  inletSpeed: 0,
});
for (let i = 0; i < 600; i++) lake.step(1 / 60);
assert(
  Math.max(...lake.q.map(Math.abs)) < 1e-10,
  "still water must not develop numerical currents",
);
assert(
  Math.abs(lake.volumeError()) < 1e-7,
  "closed still reach conserves water",
);
// Sustained moving flow over shoals: finite depths and mass balance including open-boundary flux.
const moving = new RiverFlow({
  length: 2500,
  count: 160,
  bed: (s) => 8 - s * 0.008 + bed(s),
  depth: (s) => 7 - bed(s),
  inletSpeed: 1.6,
});
for (let i = 0; i < 18000; i++) moving.step(1 / 60);
assert(moving.h.every((h) => Number.isFinite(h) && h > 0.05));
assert(moving.q.every(Number.isFinite));
assert(
  Math.abs(moving.volumeError()) < 1e-6,
  "finite volume budget includes measured inlet/outlet fluxes",
);
const diag = flowDiagnostics(moving, 1200, 20);
assert(Object.values(diag).every(Number.isFinite));
assert(diag.vorticity > 0, "bank shear has nonzero rotational diagnostic");
console.log(
  "River SWE: hydrostatic equilibrium, 5-minute open-boundary conservation, positivity and flow diagnostics passed.",
);

const {
  configureCityRiver,
  riverBounds,
  riverLevel,
  riverContains,
  riverCentre,
} = await import("../web/static/js/map3d/models/urban/geography.js");
configureCityRiver(12000, (x) => (x >= 2400 ? -8 : 42));
const limits = riverBounds();
assert(
  limits.mouth >= 2400 && limits.mouth < 2440,
  "mouth stops at first coastal cross-section",
);
assert.equal(
  riverLevel(limits.mouth),
  0,
  "river stage meets the ocean exactly",
);
assert(
  !riverContains(limits.mouth + 1, riverCentre(limits.mouth + 1)),
  "no river ribbon beyond mouth",
);
assert(
  !riverContains(limits.source - 1, riverCentre(limits.source - 1)),
  "finite source boundary",
);
assert(
  !riverContains(2900, 400, 200),
  "Eastgate is outside the river corridor",
);
let previous = Infinity;
for (let x = limits.source; x <= limits.mouth; x += 10) {
  const level = riverLevel(x);
  assert(level <= previous + 1e-9, "river does not flow uphill");
  previous = level;
}
console.log(
  "River geography: finite source/mouth, sea-level junction, downstream grade and Eastgate exclusion passed.",
);
