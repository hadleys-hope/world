"""cli: colony simulation components."""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from hadleys.api.server import HttpServer, make_handler
from hadleys.api.snapshots import compact_floats, house_geometry, snapshot
from hadleys.config import CFG
from hadleys.integrations.mqtt import MqttBridge
from hadleys.persistence import Store
from hadleys.simulation import sim_loop, world_tick
from hadleys.web import HTML, HTML3D, ROOT
from hadleys.world import World


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Hadley's Hope colony simulation")
    ap.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT", CFG["http_port"]))
    )
    ap.add_argument(
        "--data",
        default=os.environ.get("DATA_DIR", ""),
        help="directory for autosave and history (empty = no persistence)",
    )
    ap.add_argument(
        "--fresh", action="store_true", help="ignore a saved world and start over"
    )
    ap.add_argument(
        "--speed",
        type=int,
        default=CFG["default_speed"],
        help="simulated minutes per real second",
    )
    ap.add_argument("--seed", type=int, default=CFG["seed"])
    ap.add_argument(
        "--headless",
        type=int,
        default=0,
        help="run N ticks without the server, print a summary and exit",
    )
    ap.add_argument(
        "--scenario",
        default="",
        help="set up a named scenario in a new world: finance-demo (houses A, B, C; docs/FINANCE_RU.md)",
    )
    ap.add_argument(
        "--warp-days",
        type=int,
        default=0,
        help="before serving, run this many simulated days as fast as possible (saved if --data is set)",
    )
    ap.add_argument(
        "--mqtt",
        default=os.environ.get("MQTT_URL", ""),
        help="broker host:port; enables the sensor/actuator bus for external house controllers",
    )
    ap.add_argument(
        "--mqtt-batch",
        action="store_true",
        default=os.environ.get("MQTT_BATCH", "") == "1",
        help="send all houses due in a tick as one message (hh/batch/sensors); hope-runtime answers in batches",
    )
    ap.add_argument(
        "--no-klyaksa",
        action="store_true",
        default=os.environ.get("KLYAKSA", "1") == "0",
        help="do not simulate Klyaksa's dome cities (about 5000 houses) next to LV-426",
    )
    ap.add_argument(
        "--houses-per-sector",
        type=int,
        default=CFG["houses_per_sector"],
        help="colony size for a new world: sectors x this many houses (6 x 840 = 5040)",
    )
    ap.add_argument(
        "--houses-per-row",
        type=int,
        default=CFG.get("houses_per_row", 10),
        help="houses in one row of a sector; houses-per-sector must be a multiple of it",
    )
    args = ap.parse_args()
    CFG["seed"] = args.seed
    CFG["houses_per_sector"] = args.houses_per_sector
    CFG["houses_per_row"] = args.houses_per_row
    store = Store(args.data) if args.data else None
    w = None if (args.fresh or not store) else store.load_world()
    if w is None:
        w = World(CFG)
        if args.scenario:
            from hadleys.scenarios import SCENARIOS

            chosen = SCENARIOS[args.scenario](w)
            print(
                f"scenario {args.scenario}: "
                + ", ".join(f"{k} = house {v + 1} (/house?id={v + 1})" for k, v in chosen.items())
            )
    elif args.scenario:
        print(f"resumed a saved world, scenario {args.scenario} not applied (use --fresh)")
    w.speed = args.speed
    if args.warp_days:
        t0 = time.time()
        end = w.t + args.warp_days * w.cfg["ticks_per_day"]
        while w.t < end:
            world_tick(w)
            if store and w.t % 60 == 0:
                store.record_hour(w)
            if w.t % w.cfg["ticks_per_day"] == 0:
                print(f"warp: {w.time_str()} ({time.time() - t0:.0f} s)", flush=True)
        if store:
            store.save_world(w)
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    w.bridge = None
    if args.mqtt:
        try:
            w.bridge = MqttBridge(w, args.mqtt, batch=args.mqtt_batch)
            print(f"mqtt bridge: {args.mqtt}" + (" (batched)" if args.mqtt_batch else ""))
        except ImportError:
            print(
                "paho-mqtt is not installed, run: pip install paho-mqtt ; continuing without the bus"
            )
    if not args.no_klyaksa and not args.headless:
        from hadleys.klyaksa import Colony, ColonyBus

        holder_colony = Colony()
        print(f"klyaksa: {len(holder_colony.cities)} dome cities, {holder_colony.houses} houses (ids from 300)")
        if args.mqtt:
            try:
                ColonyBus(holder_colony, args.mqtt)
            except ImportError:
                pass
    else:
        holder_colony = None
    if args.headless:
        t0 = time.time()
        for _ in range(args.headless):
            world_tick(w)
        dt = time.time() - t0
        snap = snapshot(w)
        print(
            f"{args.headless} ticks in {dt:.2f} s ({args.headless / max(dt, 1e-9):.0f} ticks/s)"
        )
        print(
            json.dumps(
                {
                    k: snap[k]
                    for k in ("time", "env", "power", "reactor", "water", "finance")
                },
                indent=1,
                ensure_ascii=False,
            )
        )
        print("open issues:", snap["issues_total"])
        for e in list(w.events)[:15]:
            print(f"  t={e['t']:6d} {e['level']:5s} {e['text']}")
        return
    holder = {"w": w, "colony": holder_colony}
    threading.Thread(target=sim_loop, args=(holder, store), daemon=True).start()
    vendor_dir = ""
    for cand in (str(ROOT / "vendor"), os.path.join(args.data or ".", "vendor")):
        if os.path.isfile(os.path.join(cand, "three", "build", "three.module.js")):
            vendor_dir = cand
            break
    three_base = (
        "/vendor/three/"
        if vendor_dir
        else "https://cdn.jsdelivr.net/npm/three@0.160.0/"
    )
    html3d = HTML3D.replace("__THREE_BASE__", three_base)
    handler = make_handler(
        holder,
        HTML,
        json.dumps(compact_floats(house_geometry(w))),
        store,
        admin_token,
        html3d,
        vendor_dir,
    )
    srv = None
    for attempt in range(30):
        try:
            srv = HttpServer(("0.0.0.0", args.port), handler)
            break
        except OSError as e:
            if attempt == 0:
                print(f"port {args.port} busy ({e}), retrying for 30 s")
            time.sleep(1)
    if srv is None:
        print(
            f"could not bind port {args.port}; is another instance running? check: ss -tlnp | grep :{args.port}"
        )
        raise SystemExit(1)
    print(
        f"Hadley's Hope simulation: open http://localhost:{args.port}  (speed {w.speed} min/s, seed {args.seed})"
    )
    print(
        f"persistence: {args.data or 'off'}; admin token: {'set' if admin_token else 'not set, everyone can inject'}"
    )
    print("Ctrl+C to stop")

    def shutdown(*_):
        if store:
            current = holder["w"]
            with current.lock:
                store.save_world(current)
            print("world saved at", current.time_str())
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        shutdown()
