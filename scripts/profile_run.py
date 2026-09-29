"""Reproducible profile of the simulation back end.

    python3 scripts/profile_run.py --days 2 --out profile.json

Fixed seed (CFG), fresh world, no MQTT, no HTTP server, one process. Measures:
- the wall time of every world_tick: mean, p50, p95, p99, max, per simulated day;
- the time of every domain step inside the tick (world_tick's own order, wrapped one by one);
- memory: peak RSS of the process, tracemalloc peak over 120 further ticks and five /state builds (never while
  timing: tracemalloc slows allocation), pickled world size;
- the cost of the JSON answers the browser polls: build time of snapshot() and json.dumps separately,
  and the size of /state, /house.json, /finance.json, /water.json, /attractors.json?hist=1, /bus.json;
- the top functions by cumulative time under cProfile for a separate shorter run.
All numbers go to --out as JSON; a short table is printed.
"""

import argparse
import cProfile
import gc
import io
import json
import os
import pickle
import pstats
import resource
import statistics
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import hadleys.simulation as sim  # noqa: E402
from hadleys.api import snapshots  # noqa: E402
from hadleys.domains.attractors import attractor_snapshot  # noqa: E402
from hadleys.world import World  # noqa: E402

STEPS = [
    "env_step",
    "reactor_step",
    "power_step",
    "houses_step",
    "water_step",
    "internet_step",
    "incidents_step",
    "roads_step",
    "people_step",
    "house_events",
    "pipes_audit",
    "finance_tick",
    "finance_day_close",
    "finance_month_close",
    "attractor_sample",
]


def pct(values, p):
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def summary(ms):
    return {
        "n": len(ms),
        "mean_ms": round(statistics.fmean(ms), 3),
        "p50_ms": round(pct(ms, 50), 3),
        "p95_ms": round(pct(ms, 95), 3),
        "p99_ms": round(pct(ms, 99), 3),
        "max_ms": round(max(ms), 3),
        "total_s": round(sum(ms) / 1000, 3),
    }


def timed_steps():
    """Wrap every domain step called by world_tick so its time is recorded."""
    spent = {name: [] for name in STEPS}
    originals = {}
    for name in STEPS:
        fn = getattr(sim, name, None)
        if fn is None:
            continue
        originals[name] = fn

        def wrapper(*a, _fn=fn, _name=name, **k):
            t0 = time.perf_counter()
            try:
                return _fn(*a, **k)
            finally:
                spent[_name].append((time.perf_counter() - t0) * 1000)

        setattr(sim, name, wrapper)
    return spent, originals


def json_costs(w, repeat=20):
    from hadleys.domains.households import finance_snapshot

    out = {}
    probes = {
        "/state": lambda: snapshots.snapshot(w),
        "/house.json": lambda: snapshots.house_snapshot(w, 17),
        "/finance.json": lambda: finance_snapshot(w),
        "/water.json": lambda: snapshots.water_json(w) if hasattr(snapshots, "water_json") else {},
        "/attractors.json?hist=1": lambda: attractor_snapshot(w, True),
        "/bus.json": lambda: snapshots.bus_snapshot(w),
    }
    for path, build in probes.items():
        b, d = [], []
        body = b""
        for _ in range(repeat):
            t0 = time.perf_counter()
            obj = build()
            t1 = time.perf_counter()
            body = json.dumps(obj).encode("utf-8")
            t2 = time.perf_counter()
            b.append((t1 - t0) * 1000)
            d.append((t2 - t1) * 1000)
        out[path] = {
            "build_p50_ms": round(pct(b, 50), 3),
            "dumps_p50_ms": round(pct(d, 50), 3),
            "total_p50_ms": round(pct([x + y for x, y in zip(b, d)], 50), 3),
            "bytes": len(body),
        }
    if "/state" in out:
        state = snapshots.snapshot(w)
        out["/state"]["top_keys_bytes"] = dict(
            sorted(((k, len(json.dumps(v))) for k, v in state.items()), key=lambda kv: -kv[1])[:8]
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=2.0)
    ap.add_argument("--profile-ticks", type=int, default=1440)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    ticks = int(args.days * 1440)
    gc.collect()
    w = World()
    spent, originals = timed_steps()
    per_tick = []
    per_day = []
    open_issues = []
    t_day = time.perf_counter()
    for k in range(ticks):
        t0 = time.perf_counter()
        sim.world_tick(w)
        per_tick.append((time.perf_counter() - t0) * 1000)
        if w.t % 1440 == 0:
            per_day.append(round(time.perf_counter() - t_day, 3))
            open_issues.append(len(w.issues))
            t_day = time.perf_counter()
    for name, fn in originals.items():
        setattr(sim, name, fn)
    # memory separately: tracemalloc slows every allocation down, so it never runs while timing
    tracemalloc.start()
    for _ in range(120):
        sim.world_tick(w)
    for _ in range(5):
        json.dumps(snapshots.snapshot(w))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    result = {
        "seed": w.cfg["seed"],
        "ticks": ticks,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "tick": summary(per_tick),
        "seconds_per_sim_day": per_day,
        "issues_list_length_at_day_end": open_issues,
        "steps": {k: summary(v) for k, v in spent.items() if v},
        "memory": {
            "max_rss_mb": round(rss_mb, 1),
            "tracemalloc_peak_mb_120_ticks_and_5_state": round(peak / 1e6, 1),
            "world_pickle_mb": round(len(pickle.dumps(w, protocol=pickle.HIGHEST_PROTOCOL)) / 1e6, 2),
        },
        "json": json_costs(w),
    }
    # cProfile of a further stretch of ticks, on the same world
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(args.profile_ticks):
        sim.world_tick(w)
    pr.disable()
    buf = io.StringIO()
    pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(25)
    result["cprofile_top"] = buf.getvalue()
    pr2 = pstats.Stats(pr)
    tott = sorted(pr2.stats.items(), key=lambda kv: -kv[1][2])[:15]
    result["cprofile_tottime"] = [
        {"function": f"{k[0].split('/')[-1]}:{k[1]} {k[2]}", "tottime_s": round(v[2], 3), "calls": v[1]} for k, v in tott
    ]
    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=1)
    t = result["tick"]
    print(f"seed {result['seed']}, {ticks} ticks: tick mean {t['mean_ms']} ms, p50 {t['p50_ms']}, p95 {t['p95_ms']}, p99 {t['p99_ms']}, max {t['max_ms']}")
    print("seconds per simulated day:", per_day, " issues in w.issues:", open_issues)
    print("\n| step | p50 ms | p95 ms | mean ms | share of tick |")
    print("|---|---:|---:|---:|---:|")
    total = sum(v["total_s"] for v in result["steps"].values())
    for k, v in sorted(result["steps"].items(), key=lambda kv: -kv[1]["total_s"]):
        print(f"| {k} | {v['p50_ms']} | {v['p95_ms']} | {v['mean_ms']} | {100 * v['total_s'] / max(total, 1e-9):.1f}% |")
    print("\nmemory:", result["memory"])
    print("\n| endpoint | build p50 ms | json p50 ms | bytes |")
    print("|---|---:|---:|---:|")
    for k, v in result["json"].items():
        print(f"| {k} | {v['build_p50_ms']} | {v['dumps_p50_ms']} | {v['bytes']} |")
    print("\n/state biggest parts (bytes):", result["json"]["/state"]["top_keys_bytes"])
    print("\ncProfile tottime top:")
    for r in result["cprofile_tottime"]:
        print(f"  {r['tottime_s']:7.3f} s  {r['calls']:8d}  {r['function']}")


if __name__ == "__main__":
    main()
