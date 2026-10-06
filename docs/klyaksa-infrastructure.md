# Klyaksa infrastructure: second patch series

Apply the complete `0002`–`0007` series **after** `0001-feat-render-klyaksa-cities-and-acheron-gardens.patch`. This series is based on that patch's resulting tree, not on a different/newer checkout. Commit or stash unrelated local changes first.

```bash
cd ~/dev/hadleys-hope/world
git am ~/Downloads/000[2-7]-hh-*.patch
```

If the source differs and a patch conflicts, inspect the conflict; `git am --abort` returns to the pre-series state. Do not force patches onto another version. No `infra`, Compose, credentials, firewall or deployment changes are included. Use the existing local build workflow after applying; applying does not push or deploy.

## What changed

All planets rotate slowly around their own axes, in addition to their existing orbital motion. The followed planet carries the camera, focus, camera up direction and free-flight inertia with it. Local surface objects, Acheron controls, terrain sampling and ship controls use explicit local/world conversions. System overview remains inertial. Pausing the simulation pauses axial motion. The near clipping plane adapts to both surface clearance and focus distance, improving depth precision on distant paving while retaining the existing 5 mm minimum for close inspection.

The six Klyaksa cities keep all **5010 house identities**. A deterministic presentation layout replaces concentric residential rings with differently warped street grids, connected junctions, rounded turns and reserved plots. It is an original procedural layout, not a reconstruction of Amsterdam, London or Madrid. Cached presentation coordinates are separate from the simulation's saved coordinates; no saved house identity, controller or domain topology is migrated.

Every city has:

- Ten parks and six sector service yards with parking, workshop bays and fuel canopies.
- Ten civic plots: hospital, fire station, library, sports centre, coworking, cafe, network facility, government tower, bank and technology tower. The principal towers reach approximately 110, 142 and 182 m.
- Streets with raised sidewalks, curbs, driveway openings, crossings, stop lines, turn guides, signals, selected cycle lanes, benches and bins.
- A connected supported water distribution graph, three-phase suspended conductors and fibre links reaching every house; roof service entries, pole cabinets, flow/traffic indicators and bridge utility routes.
- A braced water tower whose fill follows actual tank telemetry, treatment equipment, substation and a reactor compound with cooling plant, turbine hall, pipe racks, access yard and switchgear.
- Ground 4G sites with road/power access, and rooftop 5G arrays/dishes. Lattice towers, monopoles and roof arrays have distinct geometry. Animated blue directional rings illustrate coverage; they do not simulate RF propagation.

Windows use a bounded interior-mapping shader with room/furniture silhouettes, approximate reflections and lit windows. They are not individually modelled furnished rooms or hardware ray tracing. Roofs and service details remain separate distance-limited geometry. Main house envelopes remain visible at overview distance.

Meridian has a finite winding river with a deeply carved channel, stone embankments, promenades, piers, full structural cable-stayed crossings and a larger downstream bridge. The downstream course avoids Eastgate's residential footprint and ends at the actual sea. Terrain refinement is limited to the river strip, and vegetation rejects the channel and access roads. See [the river model](klyaksa-river.md) for equations, numerical checks and limitations.

Harbour, Eastgate and Ridge have three coastal ports, twelve cranes in total and **24 controllable vessels**, including six cargo ships approximately 90 m long. Port roads leave through actual city gates, curve outside occupied blocks and reach the quays with water and overhead power. Intercity galleries terminate at the same graph gates; their dome portals are genuine openings.

## Movement and controls

- `4`: Klyaksa. `[` / `]`: previous/next city. `P`: next port.
- Click a house for existing telemetry; `F` or double-click focuses it.
- Click a vessel, then `Enter` (or the existing inspector's Sail button); `WASD`/arrows operate throttle and rudder, `Esc` exits.
- The existing HUD layout and camera shortcuts are retained.

Visible municipal vehicles now follow graph routes, lane offsets and traffic signals, using bounded acceleration, gear changes, braking and following distances. Snapshot changes retarget their destinations instead of snapping meshes between points. These are **visual vehicle dynamics**; server mission timing, economic effects, fuel accounting and transport decisions are unchanged. The visual vehicle can therefore take a different amount of time to reach a mission destination than the server's abstract mission.

Ships remain **local exploration in one browser tab**. They use water-depth and berth checks, drag, steering and the river's solved current. Their motion is not persisted or synchronized over MQTT, and they do not add an intercity freight economy. Existing server-controlled cars retain their ownership path.

## Performance and validation

The server changes add cached presentation geometry and read-only route metadata. Browser models are generated from source; no external asset/CDN dependency, new runtime package, per-window lights or per-leaf scene objects are required. Home envelopes remain one instanced draw; details use instancing, spatial batches and distance culling. Pipe geometry and wires have cheaper far representations. Road reservations use spatial indexes. Scene construction yields between bounded batches rather than assembling every utility/port/tree in one task. An idle callback drains up to 6 ms of cheap steps at once; expensive steps yield immediately afterwards, and asynchronous waits have a hard iteration cap. This avoids adding a timer delay for each of the thousand construction steps.

The fixed-camera geometry regression enforces fewer than 350 visible submissions and 3.5 million triangles in each tested city/street view. These counts concern Klyaksa scene objects: terrain, other planets and postprocessing have additional cost. They are **not laptop FPS measurements**. Measured in this sandbox:

| View            | Visible submissions | Triangles |
| --------------- | ------------------: | --------: |
| City overview   |                 206 | 3,362,409 |
| Street / bridge |                 276 | 3,132,461 |

The refined terrain adds 340,730 triangles. Construction used 1,080 yielded tasks; the longest measured task was 293 ms (initial intercity connections). This is still a startup pause, not a guarantee of a hitch-free load or any particular frame rate.

Run from the repository root with its existing Python requirements and Node 20+:

```bash
python3 -m unittest tests.test_klyaksa tests.test_klyaksa_layout tests.test_klyaksa_visual_payload tests.test_driving tests.test_driver_http -q
node scripts/check-web.mjs
node scripts/check-klyaksa.mjs
```

Checks cover connected road/utility graphs, house identity and picking, clear parcels, signal-controlled movement, real dome openings, berth/depth clearance, throttle response, camera transforms, rotated-body LOD, actual rendered riverbed intersections, hydraulic conservation and geometry budgets. The local Mesa/OpenGL preview compiles custom shaders and inspects city/street/port geometry. Chromium cannot start in the execution sandbox, so a complete browser interaction pass and the target laptop's GPU/FPS are still unverified.

This series replaces the layout, counts and movement descriptions in the historical [first visual-patch notes](klyaksa-visuals.md). Acheron's authored architecture and domain simulation remain intact; its objects and controls now follow axial rotation correctly.
