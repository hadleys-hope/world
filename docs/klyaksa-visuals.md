# Klyaksa: cities, waterfronts and local exploration

This patch is based on the supplied October archive. It changes the 3D renderer and adds read-only fields to the Klyaksa presentation API. Existing domain calculations, MQTT controllers, the authored HUD layout, Docker, Compose and deployment workflows are preserved.

## What to inspect

- All 5010 simulated homes retain their global IDs and original positions. Their procedural envelopes have 1–10 floors, filtered facade patterns, windows, night lighting and service risers. Nearby roofs add HVAC fans, ducts, parapets and cable attachments; balconies and entrances use separate distance-limited batches. The main envelope remains visible at city and planetary distances.
- Six city layouts retain their ring roads. They now have road markings, raised sidewalks, curb faces, textured materials, signals, catenaries and three-conductor house connections. Branch corridors connect outer rings.
- Civic plots include bank towers, rooftop antennas, communications buildings, hospitals, libraries, sports/coworking buildings, cafes, garages, fire stations and churches. Reserved public plots include benches, bins, trees and small ponds. Utility compounds have reactors, treatment equipment, transformers, solar arrays and service roads.
- Tank fill heights and service vehicle poses come from existing simulation values. Vehicle poses interpolate in two instanced batches; no additional autonomous transport simulation is introduced.
- A navigable river crosses Meridian. Cable-stayed crossings and a separate opening pedestrian/service bridge provide different bridge silhouettes. The opening bridge is outside the existing server vehicle graph; it opens when a vessel approaches.
- Harbour and Eastgate have maritime quays, access roads, berths, warehouses, cranes, yachts, motorboats and small cargo vessels. The whole berth envelope is checked against water depth.
- Acheron retains its buildings and infrastructure. Vegetation gets branch/leaf geometry with analytic cutouts and wind; 22 reserved public spaces add seating, bins, tables/stages and exercise-path segments where space is available.

## Controls

1. Select **Klyaksa** using the existing planet selector or `4`.
2. `[` / `]`: visit the previous/next city. `P`: cycle the two ports. These shortcuts do not add another HUD panel.
3. Click a house for its existing temperature/power/controller telemetry. `F` or double-click focuses the selected object.
4. Click a vessel, then press `Enter` or its inspector button. `WASD` / arrows control throttle, reverse and rudder; existing camera drag/zoom controls remain available. `Esc` exits.

Vessels are **local exploration objects in the current browser tab**. Their motion is not persisted or synchronized over MQTT. Existing cars continue to use their existing server ownership/physics path. This separation is intentional: this change does not alter the server simulation's transport rules.

## Implementation and resource limits

Models are procedural source in `web/static/js/map3d/models/urban/`, not downloaded STL assets. No model CDN, new runtime package, ray tracer, per-window lights or per-leaf scene objects are required. Window reflections are shader approximations. Two 128×128 material tiles are generated locally and shared.

All home envelopes use one instanced draw. Roof hardware, entrances, balconies and vegetation have spatial/distance culling. Far forests use simpler geometry. City construction yields in groups of roads; gardens build per city and wilderness in eight sections. Roads to ports and facilities sample the actual terrain triangles, including spherical chord height.

Deterministic frustum checks at two fixed cameras, for Klyaksa geometry alone:

| View | Archive batches / triangles | Updated batches / triangles |
| --- | ---: | ---: |
| City overview | 72 / 609,167 | 128 / 1,025,877 |
| Street | 104 / 725,958 | 201 / 1,591,594 |

These are geometry/submission counts, **not FPS measurements**. They exclude the browser's postprocessing and other planets. The richer scene costs more than the old boxes; instancing and distance detail limit that increase. The regression ceilings are 350 visible submissions and 3.5 million triangles for these cameras.

## Checks

With the repository's existing Python requirements and Node 20+:

```bash
python3 -m unittest tests.test_klyaksa tests.test_klyaksa_visual_payload -q
node scripts/check-web.mjs
python3 tests/export_visual_fixture.py
node --experimental-loader ./tests/three-loader.mjs tests/klyaksa-visuals.mjs
```

The visual checks cover all home IDs/counts, 18 house ray picks across six cities, finite geometry, two water-based ports, 14 vessels, berth clearance, actual throttle movement, timestep sensitivity, river/bank heights, vehicle batching, Acheron public spaces and 38 comparisons against actual terrain-ray intersections.

Models and custom shaders were also inspected using a local Mesa/OpenGL renderer. Chromium cannot start in the execution sandbox, so a complete browser interaction pass and laptop GPU/FPS measurement remain unverified. After applying, inspect city/street/port views in the normal browser before deploying.

## Apply the delivered commit

Run from a clean checkout of the same `world` revision supplied in the archive:

```bash
cd ~/dev/hadleys-hope/world
git apply --check ~/Downloads/0001-feat-render-klyaksa-cities-and-acheron-gardens.patch
git am ~/Downloads/0001-feat-render-klyaksa-cities-and-acheron-gardens.patch
```

No `infra` patch is required. The existing image already copies the Python package and `web/` tree. Rebuild/restart through the existing local workflow; publishing remains a separate action.
