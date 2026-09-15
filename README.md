# Hadley's Hope simulation

[![Русская версия](https://img.shields.io/badge/lang-RU-blue)](README_RU.md)

One-file simulation of the LV-426 mining colony: 300 smart houses in six sectors,
reactor and power grid, water, internet, sewage, waste, roads, gates, incidents,
repairs and money. Numpy for the house physics, a browser UI on plain canvas.

## Run locally

```
pip install numpy
python3 hadleys_hope.py
```

Open http://localhost:8000. The process stays in the foreground and logs to the terminal;
Ctrl+C stops it.

```
python3 hadleys_hope.py --port 8000 --speed 20 --seed 12345
python3 hadleys_hope.py --data ./data          # autosave and history in ./data, resumes on restart
python3 hadleys_hope.py --data ./data --fresh  # ignore the saved world
python3 hadleys_hope.py --headless 43200       # one simulated month without UI, summary to stdout
```

`--speed` is simulated minutes per real second (1 tick = 1 minute). Environment variables:
`PORT`, `DATA_DIR` (same as `--data`), `ADMIN_TOKEN` (when set, inject and speed controls
require opening the page as `/?admin=TOKEN`; everyone else is view only).

## Persistence

With `--data` or `DATA_DIR` the world is pickled every five minutes and on SIGTERM / Ctrl+C
and restored on the next start, so a hosted colony keeps living across deploys. Hourly
metrics, the event log and monthly reports go to `history.db` (sqlite) and are served at
`/history?hours=720`.

## Hosting

### Railway (fastest)

1. Push this folder to a GitHub repo.
2. railway.app: New Project, Deploy from GitHub repo. The Dockerfile is picked up automatically.
3. Service settings: Networking, Generate Domain (public https url). Variables: `ADMIN_TOKEN=your-secret`,
   `DATA_DIR=/data`. Volumes: add a volume mounted at `/data`.
4. Every push to `main` redeploys. The saved world on the volume survives the restart.

### Own VPS with GitHub Actions

1. On a fresh Ubuntu server as root: `git clone` this repository, `cd` into it and run `sh deploy/server-setup.sh`.
   It creates a user, a venv with numpy, a systemd service listening on port 80, a data directory and opens
   ports 22 and 80 in ufw. Put your token into `/opt/hadleys-hope/env`.
2. `systemctl start hadleys-hope`, watch it with `journalctl -u hadleys-hope -f`.
3. In the GitHub repo add secrets `SSH_HOST`, `SSH_USER`, `SSH_KEY` (a deploy user that can `sudo systemctl restart hadleys-hope`
   and write `/opt/hadleys-hope/`). `.github/workflows/deploy.yml` then smoke-tests, copies the file and restarts the service on every push.
4. Optional https: point a domain at the server, install Caddy and proxy the domain to port 80 (or set `PORT=8000` in the unit and proxy to it).

Vercel, Netlify and other serverless hosts do not fit: the simulation is a long-running process
with state in memory, and they end the process after each request.

## What you see

The page at `/` is a 3D view: the colony wrapped onto a small planet. Drag to rotate, right-drag,
shift-drag, WASD or arrows to move, wheel to zoom, double-click to centre on a point. Every building,
gate, rover and colonist is clickable and opens a panel with live numbers; hovering a house shows its
state. "Fly to" buttons and sector rows move the camera. Layer checkboxes toggle issues, houses
without internet, UPS charging icons, heaters, power and water flow, packets, people, xenomorphs and
labels. When the server has `ADMIN_TOKEN`, paste it into the token field once (it is remembered by the
browser) or open `/?admin=TOKEN`.

The city: six sectors of five house rows behind a wall with six gates at the sector boundaries. Streets
run between the rows and along the boundaries, every street has poles with hanging power and internet
cables and a street lamp, benches, and people walking to the hub. Water mains lie on the ground along
the boundary streets with branches along the rows. The hub holds the substation with a transformer yard,
the UPS center, the comms node, the operations center and the pump station with the tank. West of the
wall the trunk road with its own pole line leads to the reactor complex (containment, cooling towers,
turbine hall, switchyard, water plant, radioactive waste storage, mine, waste processing) and the lattice
radio tower. Rovers drive along the roads and wait at locked gates. three.js is loaded from jsdelivr; for an offline
setup put a copy of the `three` npm package into `vendor/three/` next to the script
(`npm pack three@0.160.0`, unpack, rename `package` to `three`) and it is served locally.
The flat 2D map stays at `/flat` and is lighter for phones.

Map, left:

- Reactor complex outside the city: reactor with its mode, solar plant, water plant (melts ground ice with reactor heat), waste storage, mine. The trunk line runs to the substation in the hub.
- Hub: substation, central UPS, comms node, ops center, water pump and tank.
- Six sectors, 50 houses each. House colour is indoor temperature, red frame = no power, blue frame = on the sector UPS, yellow frame = power limit, x = burst pipes. Hover a house for details.
- Poles with street lamps (glow when lit), power spans (moving dashes when energised), internet cable next to them, packets travelling from houses to the hub and the radio tower.
- Ring road with a gate at every sector boundary (green open, red lockdown), waste bins at the ring, rovers: G garbage, S sludge hauler, E engineers, P plumber.
- Red diamonds are xenomorphs, "!" markers are open issues.

Panel, right: time and speed, inject buttons, colony and sector budgets, power balance and
load shedding level, reactor telemetry, per-sector table, open issues, event log, last monthly report.

## Inject

`break span`, `fell pole`, `xenomorphs` (lockdown of a sector), `storm`, `cut trunk`
(whole colony on UPS), `pump trip` (reactor RUNBACK, load shedding), `marines fire`
(heat exchanger hit, SCRAM), `SCRAM`, `break road`, `+50k cr`.

## Model in short

- Time: 1 tick = 1 simulated minute, 30-day months. Weather: mean -45 C, daily swing, synoptic drift, storms.
- Houses: one thermal zone, `C dT/dt = Q_heat + Q_internal - UA (T_in - T_out)`, four house types, electric heating 3..4.5 kW, thermostat with comfort / eco / antifreeze targets chosen from the power situation. Pipes freeze after 60 minutes below zero and burst 30 minutes later.
- Reactor: 6 MW gross, 0.6 MW self use, power follows a setpoint at 5 %/min, core temperature with pumps and natural circulation, decay heat after shutdown, modes ONLINE / RUNBACK / SCRAM / COOLING / EMERGENCY / STARTING / CORE_DAMAGE. Core damage ends the run.
- Grid: trunk, substation, six feeders, distribution point per sector, six poles per sector with spans, house drops. A fallen pole cuts spans and the internet cable. Load shedding in eight steps: road heating, UPS charging, house limit 2 kW, street lights, house limit 1 kW, mine to 50 %, mine off, sectors dropped.
- UPS: central (800 kWh) and one per sector (400 kWh, 100 kW).
- Water: plant needs reactor heat and power, 500 m3 tank, per-house consumption.
- Internet: cabinet per sector with a 2 h UPS, cable on the poles, central node, radio tower uplink on its own line.
- Sewage: aeration station per house, sludge hauler rover, sector sludge stores. Waste: sector bins, garbage rover, processing station at the reactor complex. Sanitary index per sector.
- Incidents: weather (logistic in wind, ice and cold), xenomorphs, marines (stray fire on the cooling while a nest is active), vandals, wildlife, rovers hitting poles in dark sectors, pump wear.
- Repairs: issues are funded sector-first, then colony; rovers drive to the target by road (blocked roads and lockdowns delay them; crews in dark sectors get attacked). Nothing gets fixed without money.
- Finance: sector budgets 10 000, colony 100 000. Owners pay energy and water daily and fees plus repair reimbursements monthly; the mine earns for the colony while powered. Monthly report by cause.

All constants are in `CFG` and `COSTS` at the top of the file.

## Where the VM goes

House behaviour lives in `houses_decide()`. That function is the place where the compiled
`.hbc` programs and `libhopevm` plug in: it reads the sensors (`h_t_in`, `h_power_ok`,
`h_on_ups`, `h_limit_w`, ...) and sets the actuators (`h_heater_on`, `h_valve_open`).
