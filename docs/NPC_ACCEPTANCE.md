# NPC acceptance and performance

Checked on 2026-10-04. Production scope: 300 persistent profiles, with only the 50 Sector 1 residents commuting.

The Chrome scenario verifies selection and profile cards, three profession outfits on outdoor residents, route highlighting and selection markers, blocked entrances and resuming, the full `HOME → WALK_TO_WORK → AT_WORK → WALK_HOME → HOME` cycle, and a storm triggered through **Operations → Scenario events → Storm**. It saves during the return trip, loads a new server world, reloads the page, checks identical profiles/routes/progress/position and pause state, then completes the trip. Storm expiry uses a controlled test clock; the test does not wait six real hours. No browser errors were recorded.

## Performance

Chrome 154, Windows 11, 1440×900, bloom and shadows enabled, ANGLE SwiftShader software rendering. Same camera and world for each capacity case; 3 warm-up frames and 12 measured frames, with GPU completion awaited. The 100/300 cases duplicate Sector 1 profiles in an isolated benchmark only. Server values use 240 steps per case. These are a short reproducible capacity check, not a guarantee of FPS on another computer.

| NPC models | Mean full frame | Derived FPS | Draw calls | Median full server step | Median NPC step |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 15.38 ms | 65.0 | 2,679 | 4.251 ms | 0.000 ms |
| 50 | 24.28 ms | 41.2 | 3,006 | 4.411 ms | 0.051 ms |
| 100 | 20.87 ms | 47.9 | 3,445 | 4.513 ms | 0.106 ms |
| 300 | 25.95 ms | 38.5 | 4,173 | 4.717 ms | 0.308 ms |

The short frame samples include timing noise and should not be assumed to scale monotonically. The full scene already submits about 13 million triangles; NPCs are only part of its cost.

Rigid body and equipment pieces are now merged into shared geometry with vertex colors: one body mesh and four articulated limbs per profession. For 300 NPCs, total draw calls fell from **5,949 to 4,173** (30%), and mean frame time from **36.27 to 25.95 ms** in these runs. Arms and legs remain animated. Reload now initializes the model from its exact saved route progress instead of rounded snapshot coordinates; card equipment descriptions wrap, and selection-marker size updates after camera movement.

Raw data: [before](validation/npc-performance-before.json), [after](validation/npc-performance-after.json), [acceptance](validation/npc-acceptance.json).

## Reproduce

From `world`, with Playwright available and Chrome installed:

```powershell
$env:BROWSER_EXECUTABLE='C:/Program Files/Google/Chrome/Application/chrome.exe'
py tests/browser-pedestrians.py
py tests/benchmark-npc.py
```

Reports and screenshots are written to `test-results`. Set `$env:NPC_BENCH_HARDWARE='1'` before benchmarking to request the browser's default GPU; the reported renderer identifies what was actually used. Both scripts run their own temporary HTTP server and never modify `./data`.

For a manual demonstration: pause at 07:30, select a Sector 1 resident and choose **Resume · 1 min/s**. Watch the shift times in the card; pause just before the shift ends to observe the return. While a resident is outdoors, trigger **M → Operations → Scenario events → Storm** and watch **Heading to shelter**, then **Sheltering from storm**. To verify persistence, stop the server with Ctrl+C during a trip, start again with the same `--data ./data`, refresh and select the same resident ID.
