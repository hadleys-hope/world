"""Tick timing for before/after comparisons under the same conditions.

    python3 scripts/bench_ticks.py [path/to/data-dir-with-a-late-world]

Times one simulated day on a fresh world (seed from CFG) and, if a saved world is given, 600 ticks from it
(the finance acceptance run saves a 30-day world: scripts/finance_acceptance.py --out DIR). Also the /state
build + JSON cost. Prints one JSON line. Run it on both versions alternately, e.g. with the old commit in a
git worktree, and compare.
"""

import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from hadleys.api.snapshots import snapshot  # noqa: E402
from hadleys.persistence import Store  # noqa: E402
from hadleys.simulation import world_tick  # noqa: E402
from hadleys.world import World  # noqa: E402


def run(w, n):
    ms = []
    for _ in range(n):
        t0 = time.perf_counter()
        world_tick(w)
        ms.append((time.perf_counter() - t0) * 1000)
    ms.sort()
    return {
        "mean": round(statistics.fmean(ms), 3),
        "p50": round(ms[len(ms) // 2], 3),
        "p95": round(ms[int(len(ms) * 0.95)], 3),
        "p99": round(ms[int(len(ms) * 0.99)], 3),
    }


def state_cost(w, n=30):
    ms = []
    for _ in range(n):
        t0 = time.perf_counter()
        json.dumps(snapshot(w))
        ms.append((time.perf_counter() - t0) * 1000)
    ms.sort()
    return round(ms[n // 2], 3)


def main():
    fresh = World()
    result = {"fresh_1day": run(fresh, 1440), "state_fresh_ms": state_cost(fresh)}
    if len(sys.argv) > 1:
        late = Store(sys.argv[1]).load_world()
        result["late_600"] = run(late, 600)
        result["state_late_ms"] = state_cost(late)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
