"""integrations / mqtt: colony simulation components."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

from collections import deque
import json
import numpy as np
import time


class MqttBridge:
    """World side of the bus.

    Per house (default): hh/house/{id}/sensors out, hh/house/{id}/actuators in, one message per house.
    Batched (batch=True, for thousands of houses): one hh/batch/sensors message per tick with the readings as
    columns, answers in hh/batch/actuators as rows. paho and json cost ~60 us per message, which at 5000 houses
    was 40 ms per tick; a batch costs about as much as a single message.
    Actuators are accepted on both topics in either mode.
    """

    def __init__(self, w: World, url: str, batch: bool = False):
        import paho.mqtt.client as mqtt

        host, _, port = url.partition(":")
        self.w = w
        self.batch = batch
        self.host, self.port = host or "localhost", int(port or 1883)
        self.cli = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="hh-world", clean_session=True
        )
        self.cli.on_connect = self._on_connect
        self.cli.on_disconnect = lambda *a: setattr(self, "connected", False)
        self.cli.on_message = self._on_message
        self.connected = False
        self.inbox = deque()
        self.last_t_in = np.full(w.N, -999.0)
        self.last_flags = np.full((w.N, 6), -1, dtype=int)
        self.last_pub_t = np.full(w.N, -999)
        self.sent = 0
        self.received = 0
        self.tail = deque(maxlen=150)  # recent messages for the /bus page
        self.rate_in = deque(
            maxlen=600
        )  # (wall time) of received actuators, for messages per second
        self.rate_out = deque(maxlen=600)
        # Paho owns connection retries in its network thread, never under w.lock.
        self.cli.reconnect_delay_set(min_delay=1, max_delay=30)
        self.cli.connect_async(self.host, self.port, keepalive=30)
        self.cli.loop_start()

    def _on_connect(self, client, userdata, flags, reason, properties=None):
        self.connected = True
        client.subscribe("hh/house/+/actuators")
        client.subscribe("hh/batch/actuators")
        self.last_pub_t[:] = -999  # resend everything after a reconnect

    def _on_message(self, client, userdata, msg):
        if msg.topic == "hh/batch/actuators":
            self._on_batch(msg)
            return
        try:
            hid = int(msg.topic.split("/")[2])
            body = msg.payload.decode("utf-8")
            self.inbox.append((hid, json.loads(body)))
            self.rate_in.append(time.time())
            if hid % 7 == 0:
                self.tail.append(
                    {
                        "dir": "in",
                        "topic": msg.topic,
                        "body": body[:160],
                        "at": time.time(),
                    }
                )
        except Exception:
            pass

    def _on_batch(self, msg):
        try:
            body = msg.payload.decode("utf-8")
            rows = [r for r in json.loads(body)["rows"] if 0 <= int(r["id"]) < self.w.N]   # Klyaksa's are not ours
            if not rows:
                return
            self.inbox.extend((int(r["id"]), r) for r in rows)
            now = time.time()
            self.rate_in.extend(now for _ in range(min(len(rows), 600)))
            self.tail.append({"dir": "in", "topic": msg.topic, "body": f"{len(rows)} houses: " + body[:140], "at": now})
        except Exception:
            pass

    def apply(self):
        """Called at the start of a tick under the world lock: move received actuators into the arrays."""
        w = self.w
        while self.inbox:
            hid, a = self.inbox.popleft()
            if not (0 <= hid < w.N):
                continue
            self.received += 1
            w.h_ctrl_t[hid] = w.t
            w.h_ctrl_heater[hid] = bool(a.get("heater_on", w.h_ctrl_heater[hid]))
            w.h_ctrl_target[hid] = float(a.get("target_c", w.h_ctrl_target[hid]))
            w.h_ctrl_valve[hid] = bool(a.get("valve_open", True))
            w.h_ctrl_appl[hid] = bool(a.get("appliances_on", True))
            w.h_program[hid] = str(a.get("program", ""))[:24]
            w.h_reason[hid] = str(a.get("reason", ""))[:60]

    def publish(self):
        """Called at the end of a tick: env every tick, houses on change or every 10 ticks."""
        w = self.w
        if not self.connected:
            return
        c = self.cli
        hour = w.t // 60 % 24 + (w.t % 60) / 60.0
        c.publish("hh/tick", json.dumps({"t": w.t, "time": w.time_str()}), qos=0)
        c.publish(
            "hh/env/weather",
            json.dumps(
                {
                    "t": w.t,
                    "t_out": round(w.t_out, 1),
                    "wind": round(w.wind, 1),
                    "storm": w.storm_ticks > 0,
                    "precip": w.precip,
                    "hour": round(hour, 2),
                    "night": w.is_night(),
                    "daylight": round(w.daylight, 3),
                }
            ),
            qos=0,
            retain=True,
        )
        c.publish(
            "hh/env/power",
            json.dumps(
                {
                    "t": w.t,
                    "available_kw": round(w.available_kw),
                    "demand_kw": round(w.demand_kw),
                    "shedding": w.shedding,
                    "reactor_mode": w.r_mode,
                    "tariff_kwh": w.cfg["tariff_kwh"],
                }
            ),
            qos=0,
            retain=True,
        )
        flags = np.stack(
            [
                w.h_power_ok,
                w.h_on_ups,
                w.h_water_ok,
                w.h_pipes_ok,
                w.h_net_online,
                w.h_limit_w > 0,
            ],
            axis=1,
        ).astype(int)
        changed = (
            (np.abs(w.h_t_in - self.last_t_in) >= 0.2)
            | (flags != self.last_flags).any(axis=1)
            | (self.last_pub_t < 0)  # never sent since (re)connect: everything at once
            # periodic refresh in each house's own phase: every house still every 10 ticks, but 30 per tick
            # instead of all 300 on the same tick (a synchronized burst held the world lock for ~15 ms)
            | (np.arange(w.N) % 10 == w.t % 10)
        )
        if self.batch:
            self._publish_batch(np.flatnonzero(changed), flags)
            return
        for i in np.flatnonzero(changed):
            payload = {
                "t": w.t,
                "id": int(i),
                "sector": int(w.h_sector[i]) + 1,
                "t_in": round(float(w.h_t_in[i]), 1),
                "power_ok": bool(w.h_power_ok[i]),
                "on_ups": bool(w.h_on_ups[i]),
                "limit_w": int(w.h_limit_w[i]),
                "water_ok": bool(w.h_water_ok[i]),
                "pipes_ok": bool(w.h_pipes_ok[i]),
                "burst": bool(w.h_burst[i]),
                "net_online": bool(w.h_net_online[i]),
                "sludge": round(float(w.h_sludge[i]), 2),
                "draw_w": int(w.h_draw_w[i]),
                "heater_on": bool(w.h_heater_on[i]),
                "residents": int(w.h_residents[i]),
                "pressure_kpa": round(float(w.utilities.pressure[i]), 2),
                "water_l_min": round(
                    float(w.utilities.delivered[i]) * 60000 / w.cfg["tick_seconds"], 4
                ),
                "leak_l_min": round(
                    float(w.utilities.leaks[i]) * 60000 / w.cfg["tick_seconds"], 4
                ),
            }
            body = json.dumps(payload)
            c.publish(f"hh/house/{int(i)}/sensors", body, qos=0, retain=True)
            self.rate_out.append(time.time())
            if i % 7 == 0:
                self.tail.append(
                    {
                        "dir": "out",
                        "topic": f"hh/house/{int(i)}/sensors",
                        "body": body[:160],
                        "at": time.time(),
                    }
                )
            self.last_t_in[i] = w.h_t_in[i]
            self.last_flags[i] = flags[i]
            self.last_pub_t[i] = w.t
            self.sent += 1

    def _publish_batch(self, ids, flags):
        """All houses due this tick in one message, as columns (a row per house costs paho and json the same as
        a message per house)."""
        w = self.w
        if ids.size == 0:
            return
        u = w.utilities
        per_min = 60000 / w.cfg["tick_seconds"]
        body = json.dumps(
            {
                "t": w.t,
                "id": ids.tolist(),
                "sector": (w.h_sector[ids] + 1).tolist(),
                "t_in": np.round(w.h_t_in[ids], 1).tolist(),
                "power_ok": w.h_power_ok[ids].tolist(),
                "on_ups": w.h_on_ups[ids].tolist(),
                "limit_w": w.h_limit_w[ids].astype(int).tolist(),
                "water_ok": w.h_water_ok[ids].tolist(),
                "pipes_ok": w.h_pipes_ok[ids].tolist(),
                "burst": w.h_burst[ids].tolist(),
                "net_online": w.h_net_online[ids].tolist(),
                "sludge": np.round(w.h_sludge[ids], 2).tolist(),
                "draw_w": w.h_draw_w[ids].astype(int).tolist(),
                "heater_on": w.h_heater_on[ids].tolist(),
                "residents": w.h_residents[ids].astype(int).tolist(),
                "pressure_kpa": np.round(u.pressure[ids], 2).tolist(),
                "water_l_min": np.round(u.delivered[ids] * per_min, 4).tolist(),
                "leak_l_min": np.round(u.leaks[ids] * per_min, 4).tolist(),
            }
        )
        self.cli.publish("hh/batch/sensors", body, qos=0)
        now = time.time()
        self.rate_out.extend(now for _ in range(min(int(ids.size), 600)))
        self.tail.append({"dir": "out", "topic": "hh/batch/sensors", "body": f"{ids.size} houses: " + body[:140], "at": now})
        self.last_t_in[ids] = w.h_t_in[ids]
        self.last_flags[ids] = flags[ids]
        self.last_pub_t[ids] = w.t
        self.sent += int(ids.size)

    def status(self):
        w = self.w
        fresh = int(((w.t - w.h_ctrl_t) < 15).sum())
        now = time.time()
        return {
            "enabled": True,
            "connected": self.connected,
            "broker": f"{self.host}:{self.port}",
            "controlled": fresh,
            "sent": self.sent,
            "received": self.received,
            "out_per_s": sum(1 for t in self.rate_out if now - t < 5) / 5.0,
            "in_per_s": sum(1 for t in self.rate_in if now - t < 5) / 5.0,
        }

    def tail_list(self):
        now = time.time()
        return [
            {
                "dir": m["dir"],
                "topic": m["topic"],
                "body": m["body"],
                "age": round(now - m["at"], 1),
            }
            for m in list(self.tail)[-60:]
        ]
