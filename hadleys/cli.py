"""cli: colony simulation components."""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from hadleys.api.server import make_handler
from hadleys.api.snapshots import house_geometry, snapshot
from hadleys.config import CFG
from hadleys.integrations.mqtt import MqttBridge
from hadleys.persistence import Store
from hadleys.simulation import sim_loop, world_tick
from hadleys.web import HTML, HTML3D, ROOT
from hadleys.world import World


def main():
    import argparse
    from http.server import ThreadingHTTPServer

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
        "--mqtt",
        default=os.environ.get("MQTT_URL", ""),
        help="broker host:port; enables the sensor/actuator bus for external house controllers",
    )
    args = ap.parse_args()
    CFG["seed"] = args.seed
    store = Store(args.data) if args.data else None
    w = None if (args.fresh or not store) else store.load_world()
    if w is None:
        w = World(CFG)
    w.speed = args.speed
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    w.bridge = None
    if args.mqtt:
        try:
            w.bridge = MqttBridge(w, args.mqtt)
            print(f"mqtt bridge: {args.mqtt}")
        except ImportError:
            print(
                "paho-mqtt is not installed, run: pip install paho-mqtt ; continuing without the bus"
            )
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
    holder = {"w": w}
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
        json.dumps(house_geometry(w)),
        store,
        admin_token,
        html3d,
        vendor_dir,
    )
    srv = None
    for attempt in range(30):
        try:
            srv = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
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
