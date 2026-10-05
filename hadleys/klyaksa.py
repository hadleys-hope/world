"""Klyaksa: the new colony, a branching chain of glass-domed cities, ~5000 houses in all.

Each dome is a whole city with the same structure as Hadley's Hope (sectors, rows of houses, roads, the hub
with its towers, power, water, money), simulated as its own World. They tick in the simulation thread after
LV-426. House ids are global: LV-426 has 0..299, Klyaksa's cities follow, so one bus and one hope-runtime
serve every house in the system.

The bus is batched (one message per city per tick each way), because a message per house is what does not
scale: 5000 houses reporting every 10 ticks at 20 ticks/s would be 10 000 messages/s each way, and each one
costs ~60 us in Python. Batched it is 6 cities x 20 ticks/s = 120 messages/s each way, carrying the same rows.
"""

from __future__ import annotations

import json
import threading
import time

import numpy as np

from hadleys.config import CFG
from hadleys.geometry.roads import colony_layout
from hadleys.simulation import world_tick
from hadleys.world import World

# name, houses per sector (6 sectors), houses per row, centre in metres from the colony centre on Klyaksa
CITIES = [
    ("k1", "Meridian", 250, 25, (0, 0)),
    ("k2", "Eastgate", 200, 20, (2900, 400)),
    ("k3", "Harbour", 150, 15, (-2500, -1500)),
    ("k4", "Northfield", 125, 25, (-200, 2900)),
    ("k5", "Far East", 75, 15, (5300, 1500)),
    ("k6", "Ridge", 35, 7, (-4300, -3700)),
]
BRANCHES = [("k1", "k2"), ("k2", "k5"), ("k1", "k3"), ("k3", "k6"), ("k1", "k4")]
# a temperate coast: houses still heat at night, but nothing freezes
CLIMATE = {"t_mean": 12.0, "t_daily_amp": 5.0}


class City:
    def __init__(self, key, name, hps, per_row, at, offset, seed):
        self.key, self.name, self.at, self.offset = key, name, at, offset
        self.w = World({**CFG, **CLIMATE, "seed": seed, "houses_per_sector": hps, "houses_per_row": per_row})
        self.w.speed = 20
        self.w.bridge = None


class Colony:
    def __init__(self, cities=CITIES, first_id=300, seed=4242):
        self.cities = []
        offset = first_id
        for i, (key, name, hps, per_row, at) in enumerate(cities):
            c = City(key, name, hps, per_row, at, offset, seed + i)
            self.cities.append(c)
            offset += c.w.N
        self.houses = offset - first_id
        self.bus = None
        self._state = (0, b"")
        self._geometry = None

    def tick(self, n):
        for c in self.cities:
            w = c.w
            if w.paused or w.finished:
                continue
            with w.lock:
                for _ in range(n):
                    if self.bus:
                        self.bus.apply(c)
                    world_tick(w)
                    if self.bus:
                        self.bus.publish(c)

    def geometry(self) -> bytes:
        """Built once: houses, roads and sizes of every city, for the 3D view."""
        if self._geometry is None:
            out = []
            for c in self.cities:
                w, cfg = c.w, c.w.cfg
                roads = [
                    {"points": [[round(x, 1), round(y, 1)] for x, y in r["points"]], "width": r.get("width", 10)}
                    for r in colony_layout(cfg)["roads"]
                    if all(abs(x) < cfg["wall_radius"] + 80 and abs(y) < cfg["wall_radius"] + 80 for x, y in r["points"])
                ]
                out.append({
                    "id": c.key, "name": c.name, "at": list(c.at), "first_id": c.offset, "houses": w.N,
                    "wall": cfg["wall_radius"], "hub": cfg["hub_radius"],
                    "x": np.round(w.h_x, 1).tolist(), "y": np.round(w.h_y, 1).tolist(), "type": w.h_type.tolist(),
                    "roads": roads,
                })
            self._geometry = json.dumps({"cities": out, "branches": BRANCHES}).encode()
        return self._geometry

    def state(self) -> bytes:
        """Small enough to poll: per house one temperature byte and a few flags; per city the money."""
        now = time.monotonic()
        if now - self._state[0] < 1.0:
            return self._state[1]
        cities = []
        for c in self.cities:
            w = c.w
            with w.lock:
                cities.append({
                    "id": c.key, "time": w.time_str(), "t_out": round(w.t_out, 1),
                    "budget": round(float(w.colony_budget)), "power_kw": round(w.available_kw), "demand_kw": round(w.demand_kw),
                    "t_in": np.round(w.h_t_in).astype(int).tolist(),
                    "flags": (w.h_power_ok.astype(int) + 2 * w.h_heater_on.astype(int) + 4 * w.h_ext.astype(int)).tolist(),
                })
        body = json.dumps({"houses": self.houses, "cities": cities}).encode()
        self._state = (now, body)
        return body


class ColonyBus:
    """One MQTT connection for every Klyaksa city. Sensors go out as one batch per city per tick (columns, with
    the city's own weather as scalars, so a house program sees its own climate); actuator batches come back
    as rows and are routed to the city by the house's global id."""

    FIELDS = ("t_in", "power_ok", "on_ups", "limit_w", "water_ok", "pipes_ok", "burst", "net_online", "heater_on", "residents")

    def __init__(self, colony: Colony, url: str):
        import paho.mqtt.client as mqtt

        host, _, port = url.partition(":")
        self.colony = colony
        self.inbox = {c.key: [] for c in colony.cities}
        self.lock = threading.Lock()
        self.sent = self.received = 0
        self.cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="hh-klyaksa", clean_session=True)
        self.cli.on_connect = lambda c, *a: c.subscribe("hh/batch/actuators")
        self.cli.on_message = self._on_message
        self.cli.reconnect_delay_set(min_delay=1, max_delay=30)
        self.cli.connect_async(host or "localhost", int(port or 1883), keepalive=30)
        self.cli.loop_start()
        colony.bus = self

    def _city(self, hid):
        for c in self.colony.cities:
            if c.offset <= hid < c.offset + c.w.N:
                return c
        return None

    def _on_message(self, client, userdata, msg):
        try:
            rows = json.loads(msg.payload)["rows"]
        except Exception:
            return
        with self.lock:
            for r in rows:
                c = self._city(int(r.get("id", -1)))
                if c:
                    self.inbox[c.key].append(r)

    def apply(self, c: City):
        with self.lock:
            rows, self.inbox[c.key] = self.inbox[c.key], []
        w = c.w
        for a in rows:
            i = int(a["id"]) - c.offset
            self.received += 1
            w.h_ctrl_t[i] = w.t
            w.h_ctrl_heater[i] = bool(a.get("heater_on", w.h_ctrl_heater[i]))
            w.h_ctrl_target[i] = float(a.get("target_c", w.h_ctrl_target[i]))
            w.h_ctrl_valve[i] = bool(a.get("valve_open", True))
            w.h_ctrl_appl[i] = bool(a.get("appliances_on", True))
            w.h_program[i] = str(a.get("program", ""))[:24]
            w.h_reason[i] = str(a.get("reason", ""))[:60]

    def publish(self, c: City):
        w = c.w
        ids = np.flatnonzero(np.arange(w.N) % 10 == w.t % 10)          # every house every 10 ticks, spread
        if ids.size == 0:
            return
        hour = w.t // 60 % 24 + (w.t % 60) / 60.0
        msg = {
            "t": w.t, "city": c.key, "t_out": round(w.t_out, 1), "wind": round(w.wind, 1), "hour": round(hour, 2),
            "night": int(w.is_night()), "shedding": int(w.shedding), "storm": int(w.storm_ticks > 0),
            "id": (ids + c.offset).tolist(),
            "sector": (w.h_sector[ids] + 1).tolist(),
        }
        for f in self.FIELDS:
            arr = getattr(w, "h_" + f)[ids]
            msg[f] = np.round(arr, 1).tolist() if arr.dtype.kind == "f" else arr.astype(int).tolist()
        self.cli.publish("hh/batch/sensors", json.dumps(msg), qos=0)
        self.sent += int(ids.size)
