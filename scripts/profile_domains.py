"""Where a tick goes, per domain, for colonies of several sizes; and what a /state snapshot costs.

    python scripts/profile_domains.py                  # 300, 1500, 5040 and 10080 houses
    python scripts/profile_domains.py --houses 300 1500 --ticks 60 --json out.json
"""

import argparse
import json
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hadleys.simulation as sim
from hadleys.api.snapshots import snapshot
from hadleys.config import CFG
from hadleys.world import World

SPENT = defaultdict(float)


def instrument():
    """Wrap every domain function the tick calls, so each call adds its time to SPENT."""
    for name, fn in list(vars(sim).items()):
        if callable(fn) and getattr(fn, "__module__", "").startswith("hadleys.domains") and name != "world_tick":
            def timed(*a, _fn=fn, _name=name, **k):
                t = time.perf_counter()
                try:
                    return _fn(*a, **k)
                finally:
                    SPENT[_name] += time.perf_counter() - t
            setattr(sim, name, timed)


def profile(houses, ticks, warm):
    hps = houses // 6
    per_row = next(r for r in (25, 20, 15, 10) if hps % r == 0)
    w = World({**CFG, "houses_per_sector": hps, "houses_per_row": per_row, "croc_raid_mean_days": 0})
    built = time.perf_counter()
    for _ in range(warm):
        sim.world_tick(w)
    SPENT.clear()
    t = time.perf_counter()
    for _ in range(ticks):
        sim.world_tick(w)
    total = (time.perf_counter() - t) / ticks
    domains = {k: v / ticks for k, v in sorted(SPENT.items(), key=lambda kv: -kv[1])}
    t = time.perf_counter()
    for _ in range(5):
        body = json.dumps(snapshot(w))
    snap = (time.perf_counter() - t) / 5
    return {
        "houses": w.N, "tick_ms": total * 1e3, "us_per_house": total / w.N * 1e6,
        "snapshot_ms": snap * 1e3, "state_kb": len(body) / 1e3, "pickle_mb": len(pickle.dumps(w)) / 1e6,
        "domains_ms": {k: round(v * 1e3, 3) for k, v in domains.items()},
        "other_ms": round((total - sum(domains.values())) * 1e3, 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--houses", type=int, nargs="+", default=[300, 1500, 5040, 10080])
    ap.add_argument("--ticks", type=int, default=40)
    ap.add_argument("--warm", type=int, default=20)
    ap.add_argument("--json")
    a = ap.parse_args()
    instrument()
    rows = []
    for n in a.houses:
        r = profile(n, a.ticks, a.warm)
        rows.append(r)
        top = ", ".join(f"{k} {v:.2f}" for k, v in list(r["domains_ms"].items())[:6])
        print(f"{r['houses']:>6} houses: {r['tick_ms']:7.2f} ms/tick ({r['us_per_house']:.2f} us/house), "
              f"/state {r['snapshot_ms']:.1f} ms {r['state_kb']:.0f} KB, save {r['pickle_mb']:.1f} MB | {top}", flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
