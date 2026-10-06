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
import os
import pickle
import threading
import time
from collections import deque

import numpy as np

from hadleys.config import CFG
from hadleys.geometry.klyaksa_layout import city_plan
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


class CityBusView:
    """What the /bus page reads from a world's bridge, for one Klyaksa city on the shared batched bus.
    apply/publish are no-ops: the colony drives the bus itself, once per city per tick."""

    def __init__(self, city):
        self.city = city
        self.last_pub_t = np.full(city.w.N, -999)
        self.sent = self.received = 0
        self.connected = False
        self.tail = deque(maxlen=150)
        self.rate_out = deque(maxlen=200)
        self.rate_in = deque(maxlen=200)

    def apply(self):
        pass

    def publish(self):
        pass

    def status(self):
        w, now = self.city.w, time.time()
        rate = lambda q: sum(n for t, n in q if now - t < 5) / 5.0
        return {
            "enabled": True, "connected": self.connected, "broker": "batched, one message per tick",
            "controlled": int(((w.t - w.h_ctrl_t) < 15).sum()), "sent": self.sent, "received": self.received,
            "out_per_s": rate(self.rate_out), "in_per_s": rate(self.rate_in),
        }

    def tail_list(self):
        now = time.time()
        return [{"dir": m["dir"], "topic": m["topic"], "body": m["body"], "age": round(now - m["at"], 1), "at": m["at"]} for m in list(self.tail)[-60:]]


class City:
    def __init__(self, key, name, hps, per_row, at, offset, seed, saved=None):
        self.key, self.name, self.at, self.offset = key, name, at, offset
        self.w = saved or World({**CFG, **CLIMATE, "seed": seed, "houses_per_sector": hps, "houses_per_row": per_row})
        self.w.speed = 20
        self.w.bridge = CityBusView(self)


class Colony:
    def __init__(self, cities=CITIES, first_id=300, seed=4242, data_dir=None):
        self.cities = []
        self.data_dir = data_dir
        offset = first_id
        for i, (key, name, hps, per_row, at) in enumerate(cities):
            c = City(key, name, hps, per_row, at, offset, seed + i, self._load(key, 6 * hps))
            self.cities.append(c)
            offset += c.w.N
        self.houses = offset - first_id
        self.bus = None
        self._state = (0, b"")
        self._geometry = None
        self._geometry_lock = threading.Lock()
        self._visual_plans = {}
        self._visual_anchors = {}

    def _path(self, key):
        return os.path.join(self.data_dir, f"klyaksa-{key}.pkl") if self.data_dir else None

    def _load(self, key, houses):
        """A saved city, if there is one of the right size and schema; otherwise None (a new one is built)."""
        path = self._path(key)
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                w = pickle.load(f)
            if getattr(w, "schema", 1) == World.SCHEMA and w.N == houses:
                return w
        except Exception as e:
            print(f"klyaksa {key}: saved city unreadable ({e}), building a new one")
        return None

    def save(self):
        """Each city to its own file, written aside and renamed, so a crash never leaves half a file."""
        for c in self.cities:
            path = self._path(c.key)
            if not path:
                return
            bridge, c.w.bridge = c.w.bridge, None             # the bus view holds a lock and a client; not saved
            try:
                with c.w.lock:
                    with open(path + ".tmp", "wb") as f:
                        pickle.dump(c.w, f, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(path + ".tmp", path)
            finally:
                c.w.bridge = bridge

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
        """Built once: a shared read-only presentation plan for every 3D layer."""
        with self._geometry_lock:
            return self._build_geometry()

    def _build_geometry(self) -> bytes:
        """Keep parallel initial HTTP requests from generating the same plan twice."""
        if self._geometry is None:
            out = []
            for c in self.cities:
                w, cfg = c.w, c.w.cfg
                neighbours = []
                for left, right in BRANCHES:
                    other = right if left == c.key else left if right == c.key else None
                    target = next((v for v in self.cities if v.key == other), None)
                    if target:
                        neighbours.append((target.key, target.at[0] - c.at[0], target.at[1] - c.at[1]))
                plan = city_plan(c, neighbours)
                self._visual_plans[c.key] = plan
                out.append({
                    "id": c.key, "name": c.name, "at": list(c.at), "first_id": c.offset, "houses": w.N,
                    "hub": cfg["hub_radius"], "type": w.h_type.tolist(),
                    "sim_x": np.round(w.h_x, 3).tolist(), "sim_y": np.round(w.h_y, 3).tolist(),
                    "sim_facilities": {key: list(cfg[key]) for key in plan["facilities"]},
                    **plan,
                })
            self._geometry = json.dumps({"cities": out, "branches": BRANCHES}).encode()
        return self._geometry

    def _visual_rover(self, c, rover):
        """Mission metadata for road-following presentation, never a simulation write.

        The 3-D street plan differs from the persisted polar domain plan.  Expose
        both coordinates explicitly; the browser traverses the exported graph to
        these destinations instead of interpolating a polar position across blocks.
        """
        plan, w = self._visual_plans[c.key], c.w
        anchors = self._visual_anchors.get(c.key)
        if anchors is None:
            points = list(zip(w.h_x, w.h_y))
            mapped = [{'x': x, 'y': y, 'node': node} for x, y, node in
                      zip(plan['access_x'], plan['access_y'], plan['access_node'])]
            for name, access in plan['facility_access'].items():
                points.append(w.cfg[name])
                mapped.append(access)
            for name, index in (('garage', 0), ('cargo_depot', 4)):
                a, radius = w.cfg[name]
                a = np.deg2rad(a)
                points.append((radius * np.cos(a), radius * np.sin(a)))
                mapped.append(plan['sector_services'][index]['access'])
            anchors = (np.asarray(points), mapped)
            self._visual_anchors[c.key] = anchors

        def mapped_point(xy):
            index = int(np.argmin(np.sum((anchors[0] - xy) ** 2, axis=1)))
            return anchors[1][index]

        target = mapped_point(rover.route[-1] if rover.route else (rover.x, rover.y))
        job, mission = rover.job, str(rover.state)
        if mission == 'TO_GARAGE':
            target = plan['sector_services'][0]['access']
        elif mission == 'TO_STATION':
            target = plan['facility_access']['waste_station_pos']
        elif mission == 'TO_DEPOT':
            target = plan['sector_services'][4]['access']
        if isinstance(job, (int, np.integer)):
            if mission in ('TO_HOUSE', 'PUMPING') and 0 <= int(job) < w.N:
                target = anchors[1][int(job)]
            elif mission in ('TO_BIN', 'TO_STORE', 'LOADING') and 0 <= int(job) < 6:
                target = plan['sector_services'][int(job)]['access']
        if getattr(job, 'target', '').startswith('house:'):
            try:
                i = int(job.target.split(':', 1)[1])
                if 0 <= i < w.N:
                    target = anchors[1][i]
            except (ValueError, IndexError):
                pass
        return {
            'name': rover.name, 'kind': rover.kind, 'x': round(rover.x, 2), 'y': round(rover.y, 2),
            'heading': round(rover.heading, 4), 'load': round(rover.load, 2),
            'velocity': round(rover.velocity, 3), 'mission_state': mission,
            'moving': bool(rover.route) and not w.paused and not w.finished,
            'circulating': mission == 'CIRCULATING',
            'visual_origin': mapped_point((rover.x, rover.y)), 'visual_target': target,
        }

    def state(self) -> bytes:
        """Small enough to poll: per house one temperature byte and a few flags; per city the money."""
        now = time.monotonic()
        if now - self._state[0] < 1.0:
            return self._state[1]
        if not self._geometry:
            self.geometry()
        cities = []
        for c in self.cities:
            w = c.w
            with w.lock:
                cities.append({
                    "id": c.key, "time": w.time_str(), "sim_tick": w.t, "paused": w.paused, "t_out": round(w.t_out, 1),
                    "budget": round(float(w.colony_budget)), "power_kw": round(w.available_kw), "demand_kw": round(w.demand_kw),
                    "t_in": np.round(w.h_t_in).astype(int).tolist(),
                    "water": {"tank_m3": round(w.water_tank_m3, 2), "capacity_m3": w.cfg["water_tank_m3"]},
                    "rovers": [self._visual_rover(c, r) for r in w.rovers + getattr(w, "traffic", [])],
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
        def connected(c, *a):
            c.subscribe("hh/batch/actuators")
            for city in colony.cities:
                city.w.bridge.connected = True

        self.cli.on_connect = connected
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
        view = c.w.bridge
        if rows:
            view.received += len(rows)
            view.rate_in.append((time.time(), len(rows)))
            view.tail.append({"dir": "in", "topic": "hh/batch/actuators", "body": f"{len(rows)} houses: " + json.dumps(rows[0])[:140], "at": time.time()})
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
        body = json.dumps(msg)
        self.cli.publish("hh/batch/sensors", body, qos=0)
        self.sent += int(ids.size)
        view = c.w.bridge
        view.sent += int(ids.size)
        view.last_pub_t[ids] = w.t
        view.rate_out.append((time.time(), int(ids.size)))
        if w.t % 7 == 0:
            view.tail.append({"dir": "out", "topic": "hh/batch/sensors", "body": f"{ids.size} houses: " + body[:140], "at": time.time()})
