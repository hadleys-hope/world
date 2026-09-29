"""Tick and MQTT bridge cost against a live broker with the house controllers answering.

    python3 scripts/bench_mqtt.py host:port [ticks]

Needs a broker and houses_runtime.py connected to it (see docs/PERF_RU.md). Fresh world, the bridge's apply()
and publish() are timed separately from world_tick, with a 20 ms pause per tick so the controllers answer as in
the real loop. Prints how many houses go out per tick and the timings; one JSON line at the end.
"""

import collections
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from hadleys.integrations.mqtt import MqttBridge  # noqa: E402
from hadleys.simulation import world_tick  # noqa: E402
from hadleys.world import World  # noqa: E402


def stats(ms):
    s = sorted(ms)
    return {"mean": round(statistics.fmean(s), 2), "p95": round(s[int(0.95 * (len(s) - 1))], 2), "max": round(s[-1], 2)}


def main():
    url = sys.argv[1]
    ticks = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    w = World()
    w.bridge = None  # the bridge calls are timed here, outside world_tick
    for _ in range(30):
        world_tick(w)
    b = MqttBridge(w, url)
    for _ in range(50):
        if b.connected:
            break
        time.sleep(0.1)
    if not b.connected:
        raise SystemExit(f"broker {url} not reachable")
    b.publish()  # the full send after a connect
    time.sleep(1)
    tick, apply, publish, per_tick = [], [], [], []
    sent0, received0 = b.sent, b.received
    for _ in range(ticks):
        t0 = time.perf_counter()
        world_tick(w)
        tick.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        b.apply()
        apply.append((time.perf_counter() - t0) * 1000)
        s0 = b.sent
        t0 = time.perf_counter()
        b.publish()
        publish.append((time.perf_counter() - t0) * 1000)
        per_tick.append(b.sent - s0)
        time.sleep(0.02)
    result = {
        "ticks": ticks,
        "houses_per_tick": dict(collections.Counter(per_tick).most_common(6)),
        "tick_ms": stats(tick),
        "apply_ms": stats(apply),
        "publish_ms": stats(publish),
        "sent": b.sent - sent0,
        "received": b.received - received0,
    }
    print("houses sent per tick -> number of ticks:", result["houses_per_tick"])
    for k in ("tick_ms", "apply_ms", "publish_ms"):
        print(f"{k}: {result[k]}")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
