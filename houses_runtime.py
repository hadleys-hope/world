"""Hadley's Hope house controllers over MQTT.

Stand-in for the real runtime (libhopevm running .hbc programs): every house gets a small
Python "program" that reads the house sensors and the colony feeds from the bus and publishes
actuators. The world applies them to its physics. Swap this file for the runtime later; the
topics and payloads stay the same.

Run next to a broker:   python3 houses_runtime.py --mqtt localhost:1883
Programs are assigned by house id (id % 5) unless --manifest points to a JSON {"17": "eco", ...}.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("pip install paho-mqtt")
    sys.exit(1)


# ------------------------------------------------------------------------------------
# Programs. Each is a function (house_state) -> actuators dict. The state carries the
# last sensors, the last colony feeds the house was able to receive, and per-house memory.
# ------------------------------------------------------------------------------------

def thermostat(mem, t_in, target, band=0.5):
    on = mem.get("heater_on", True)
    if t_in < target - band:
        on = True
    elif t_in > target + band:
        on = False
    mem["heater_on"] = on
    return on


def prog_comfort(st):
    s, env, pw, mem = st["sensors"], st["weather"], st["power"], st["mem"]
    target, why = 21.0, "comfort 21"
    if s["limit_w"] and s["limit_w"] <= 1800:
        target, why = 6.0, "grid limit, antifreeze"
    elif s["limit_w"] or s["on_ups"]:
        target, why = 16.0, "limited power, eco"
    return {"target_c": target, "heater_on": thermostat(mem, s["t_in"], target), "reason": why,
            "appliances_on": not (s["on_ups"] or (s["limit_w"] and s["limit_w"] <= 1800)), "valve_open": s["pipes_ok"]}


def prog_eco(st):
    s, env, pw, mem = st["sensors"], st["weather"], st["power"], st["mem"]
    night = env.get("night", False)
    target, why = (15.0, "eco night 15") if night else (18.0, "eco day 18")
    if pw.get("shedding", 0) >= 3:
        target, why = target - 2, f"shedding L{pw['shedding']}, minus 2"
    if s["limit_w"] and s["limit_w"] <= 1800:
        target, why = 6.0, "grid limit, antifreeze"
    return {"target_c": target, "heater_on": thermostat(mem, s["t_in"], target, 0.7), "reason": why,
            "appliances_on": not s["on_ups"], "valve_open": s["pipes_ok"]}


def prog_night_setback(st):
    s, env, pw, mem = st["sensors"], st["weather"], st["power"], st["mem"]
    hour = env.get("hour", 12.0)
    if 5.0 <= hour < 6.0:
        target, why = 21.0, "warm-up before morning"
    elif hour >= 22.0 or hour < 6.0:
        target, why = 16.0, "night setback 16"
    else:
        target, why = 21.0, "day 21"
    if s["on_ups"]:
        target, why = 14.0, "on ups, stretch the battery"
    if s["limit_w"] and s["limit_w"] <= 1800:
        target, why = 6.0, "grid limit, antifreeze"
    return {"target_c": target, "heater_on": thermostat(mem, s["t_in"], target), "reason": why,
            "appliances_on": not s["on_ups"], "valve_open": s["pipes_ok"]}


def prog_storm_ready(st):
    s, env, pw, mem = st["sensors"], st["weather"], st["power"], st["mem"]
    target, why = 21.0, "comfort 21"
    if env.get("storm") or env.get("wind", 0) > 20:
        target, why = 23.5, "storm, banking heat"
    if not s["net_online"]:
        why = why + " (offline, last forecast)"
    if s["on_ups"]:
        target, why = 12.0, "on ups, minimum"
    if s["limit_w"] and s["limit_w"] <= 1800:
        target, why = 6.0, "grid limit, antifreeze"
    return {"target_c": target, "heater_on": thermostat(mem, s["t_in"], target), "reason": why,
            "appliances_on": not (s["on_ups"] or bool(s["limit_w"])), "valve_open": s["pipes_ok"]}


def prog_dumb(st):
    s, mem = st["sensors"], st["mem"]
    return {"target_c": 26.0, "heater_on": thermostat(mem, s["t_in"], 26.0, 1.0), "reason": "always warm, never saves",
            "appliances_on": True, "valve_open": True}


PROGRAMS = {"comfort": prog_comfort, "eco": prog_eco, "night-setback": prog_night_setback,
            "storm-ready": prog_storm_ready, "dumb": prog_dumb}


# ------------------------------------------------------------------------------------
# Runtime: one MQTT client, a state per house, decide on every sensor update
# ------------------------------------------------------------------------------------

class Runtime:
    def __init__(self, url: str, manifest: dict, n_houses: int, verbose: bool):
        host, _, port = url.partition(":")
        self.host, self.port = host or "localhost", int(port or 1883)
        self.names = list(PROGRAMS.keys())
        self.manifest = manifest
        self.n = n_houses
        self.verbose = verbose
        self.houses = {}          # id -> state
        self.weather = {}
        self.power = {}
        self.decisions = 0
        self.lock = threading.Lock()
        self.cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="hh-houses-runtime")
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
        client.subscribe([("hh/house/+/sensors", 0), ("hh/env/weather", 0), ("hh/env/power", 0)])

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
        st = self.houses.setdefault(hid, {"mem": {}, "weather": {}, "power": {}, "sensors": None})
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
            print(f"{self.decisions} decisions, last: house {hid} {name}: {act['reason']}, target {act['target_c']}")

    def run(self):
        self.cli.connect_async(self.host, self.port, keepalive=30)
        self.cli.loop_start()
        try:
            while True:
                time.sleep(5)
                if not self.connected:
                    try:
                        self.cli.reconnect()
                    except Exception as e:
                        print(f"broker {self.host}:{self.port} not reachable ({e}), retrying")
                        continue
                print(f"houses seen {len(self.houses)}, decisions {self.decisions}, weather at t={self.weather.get('t')}")
        except KeyboardInterrupt:
            print("stopped")
        finally:
            self.cli.loop_stop()


def main():
    ap = argparse.ArgumentParser(description="Hadley's Hope house controllers over MQTT")
    ap.add_argument("--mqtt", default=os.environ.get("MQTT_URL", "localhost:1883"))
    ap.add_argument("--manifest", default="", help="JSON file mapping house id to program name")
    ap.add_argument("--houses", type=int, default=300)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    manifest = {}
    if args.manifest:
        with open(args.manifest, encoding="utf-8") as f:
            manifest = json.load(f)
    print("programs:", ", ".join(PROGRAMS.keys()))
    Runtime(args.mqtt, manifest, args.houses, args.verbose).run()


if __name__ == "__main__":
    main()
