"""MQTT process hosting the house controllers. Wire protocol is unchanged."""

from __future__ import annotations
import argparse
import json
import os
import threading
import time
import paho.mqtt.client as mqtt
from .programs import PROGRAMS


class Runtime:
    def __init__(self, url: str, manifest: dict, n_houses: int, verbose: bool):
        host, _, port = url.partition(":")
        self.host, self.port = host or "localhost", int(port or 1883)
        self.names = list(PROGRAMS.keys())
        self.manifest = manifest
        self.n = n_houses
        self.verbose = verbose
        self.houses = {}  # id -> state
        self.weather = {}
        self.power = {}
        self.decisions = 0
        self.lock = threading.Lock()
        self.cli = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="hh-houses-runtime"
        )
        self.cli.on_connect = self.on_connect
        self.cli.on_message = self.on_message
        self.cli.on_disconnect = lambda *a: setattr(self, "connected", False)
        self.connected = False

    def program_for(self, hid):
        name = self.manifest.get(str(hid)) or self.names[hid % len(self.names)]
        return name, PROGRAMS[name]

    def on_connect(self, client, userdata, flags, reason, properties=None):
        self.connected = True
        print(f"connected to {self.host}:{self.port}, subscribing")
        client.subscribe(
            [("hh/house/+/sensors", 0), ("hh/env/weather", 0), ("hh/env/power", 0)]
        )

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        if msg.topic == "hh/env/weather":
            self.weather = payload
            return
        if msg.topic == "hh/env/power":
            self.power = payload
            return
        hid = int(msg.topic.split("/")[2])
        if hid >= self.n:
            return
        st = self.houses.setdefault(
            hid, {"mem": {}, "weather": {}, "power": {}, "sensors": None}
        )
        st["sensors"] = payload
        # the house controller only receives colony feeds while its own link is up; otherwise it keeps the last copy
        if payload.get("net_online", True):
            st["weather"] = dict(self.weather)
            st["power"] = dict(self.power)
        name, prog = self.program_for(hid)
        act = prog(st)
        act["program"] = name
        act["t"] = payload.get("t")
        client.publish(f"hh/house/{hid}/actuators", json.dumps(act), qos=0)
        self.decisions += 1
        if self.verbose and self.decisions % 500 == 0:
            print(
                f"{self.decisions} decisions, last: house {hid} {name}: {act['reason']}, target {act['target_c']}"
            )

    def run(self):
        self.cli.reconnect_delay_set(min_delay=1, max_delay=30)
        self.cli.connect_async(self.host, self.port, keepalive=30)
        self.cli.loop_start()
        try:
            while True:
                time.sleep(5)
                if not self.connected:
                    print(
                        f"broker {self.host}:{self.port} not connected; background retry active"
                    )
                    continue
                print(
                    f"houses seen {len(self.houses)}, decisions {self.decisions}, weather at t={self.weather.get('t')}"
                )
        except KeyboardInterrupt:
            print("stopped")
        finally:
            self.cli.loop_stop()


def main():
    ap = argparse.ArgumentParser(
        description="Hadley's Hope house controllers over MQTT"
    )
    ap.add_argument("--mqtt", default=os.environ.get("MQTT_URL", "localhost:1883"))
    ap.add_argument(
        "--manifest", default="", help="JSON file mapping house id to program name"
    )
    ap.add_argument("--houses", type=int, default=300)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    manifest = {}
    if args.manifest:
        with open(args.manifest, encoding="utf-8") as f:
            manifest = json.load(f)
    print("programs:", ", ".join(PROGRAMS.keys()))
    Runtime(args.mqtt, manifest, args.houses, args.verbose).run()
