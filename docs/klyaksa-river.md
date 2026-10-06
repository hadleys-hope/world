# Klyaksa river and ports

The Meridian channel has a finite upstream source and a coast-checked downstream mouth. The city reach follows `y = 12 sin(x / 300)` and is 80 m wide. Downstream it turns south, away from Eastgate, and ends where the unmodified terrain is below sea level across the complete estuary. The water surface fades into the existing ocean only over its last 2.5%. `riverContains` is shared by vegetation reservations, picking/motion and terrain carving. Housing and road placement use the same city-reach centreline.

The river has a 10 m central navigation channel, shallower banks, stone-block retaining walls, coping, promenades and cycle lanes. Road crossings come from the exported road polylines, rather than assumed ring radii. Each crossing receives a box-girder deck, full-depth foundation piers, paired pylons, stays and edge rails. A separate larger crossing stands downstream outside Meridian. Three coastal terminals serve Harbour, Eastgate and Ridge, each with a cargo apron, corrugated containers, warehouse/repair sheds, four loading cranes, marina fingers, quay bollards and fenders. The fleet has six approximately 90 m cargo ships plus eighteen small vessels. Port access roads start at existing dome gates, curve around the protected city footprint, and connect to the quay with supported phase wires and water supply. Vessel control remains local browser exploration, not a new server transport domain.

## Numerical model and its limits

`river-flow.js` implements a small one-dimensional, depth-averaged Saint-Venant model in 160 cells:

\[
\partial_t h + \partial_s(hu) = 0,
\qquad
\partial_t(hu) + \partial_s(hu^2+\tfrac12 gh^2)
= -gh\,\partial_s z_b - g n^2 u|u|/h^{1/3}.
\]

Here `h` is water depth, `u` is longitudinal velocity, `z_b` is bed elevation, and `n = 0.024` is the visual reach's Manning roughness. Hydrostatic reconstruction balances pressure with bed slope. A Rusanov numerical flux transports water/momentum; the CFL limit is 0.4. Manning drag is treated semi-implicitly. The inlet prescribes depth and velocity; the outlet prescribes stage with extrapolated velocity. Boundary fluxes are accumulated so numerical volume conservation per unit channel width can be checked independently.

The shader receives a 160-pixel texture containing speed, depth and longitudinal velocity-gradient magnitude. Surface streaks travel with the solved velocity; shallow reaches and velocity gradients influence foam. Fine ripples and reflection highlights are visual effects, not another fluid solver. The transverse reconstruction tapers speed near banks; `flowDiagnostics` exposes its divergence and vorticity (`∂u/∂s + ∂v/∂n`, `∂v/∂s − ∂u/∂n`).

This is **not full 2D/3D CFD**: it does not solve variable-width channel momentum, sediment transport, erosion, breaking waves, ship displacement or turbulent flow around individual boulders. It runs only in the active Klyaksa view and does not modify the colony's water balance, pumps, demand, money or clock. Fixed-size typed arrays and one tiny texture update bound CPU and GPU cost.

Primary references consulted:

- [Clawpack Riemann book: shallow water equations](https://www.clawpack.org/riemann_book/html/Shallow_water.html), for conservative depth/momentum variables and characteristic wave speeds.
- [USACE HEC-RAS: shallow water equations](https://www.hec.usace.army.mil/confluence/rasdocs/hecras/latest/technical-reference/hydraulic-equations/shallow-water-equations), for the depth-averaged continuity and momentum framework.

Run `node tests/river-flow.mjs` and `node --experimental-loader ./tests/three-loader.mjs tests/river-port-layout.mjs` (after exporting the visual fixture). The port test checks 24 approach directions for gate attachment, city-footprint clearance and dense surface samples. The flow test checks hydrostatic equilibrium over a non-flat bed, positivity/finite values during five simulated minutes, mass conservation including boundary fluxes, and finite divergence/vorticity diagnostics.
