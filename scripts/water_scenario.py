"""Sewage lift pump off -> sewage builds up -> the sump overflows -> pump on -> recovery.

    python3 scripts/water_scenario.py                # full 200 m3 sump, about 3 minutes
    python3 scripts/water_scenario.py --sump 20      # a small sump, quick

Runs the full simulation (seed from hadleys/config.py). Prints an hourly table of the tank, the sanitary sump,
what was pumped and what spilled, then the volume balance of every part of the water system: each part's
inflow minus outflow must equal its stock change, so no water appears or vanishes without a recorded cause.
Exits non-zero if the story does not happen or any balance is off.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from hadleys.config import CFG  # noqa: E402
from hadleys.domains.hydraulics import water_balance  # noqa: E402
from hadleys.simulation import inject, world_tick  # noqa: E402
from hadleys.world import World  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sump", type=float, default=CFG["drain_storage_m3"], help="sanitary sump volume, m3")
    ap.add_argument("--spill-hours", type=int, default=6, help="how long to let it overflow before the pump restarts")
    args = ap.parse_args()
    w = World({**CFG, "drain_storage_m3": args.sump})
    u, a = w.utilities, w.water_acc
    rows = []

    def row(note=""):
        if note and rows and rows[-1][0] == w.time_str():
            rows.pop()  # the marker replaces the hourly row of the same minute
        rows.append(
            (w.time_str(), w.water_tank_m3, a["delivered"], a["to_sewer"], u.sewer_storage, a["sewer_pumped"], a["sewer_overflow"], note)
        )

    def hours(n, note=""):
        for h in range(n):
            for _ in range(60):
                world_tick(w)
            row(note if h == 0 else "")

    hours(6, "normal")
    inject(w, "sewer_pump")
    row("PUMP OFF")
    spill_started = None
    for h in range(24 * 30):
        for _ in range(60):
            world_tick(w)
        if spill_started is None and a["sewer_overflow"] > 0:
            spill_started = h
            row("OVERFLOW starts")
        else:
            row("")
        if spill_started is not None and h - spill_started >= args.spill_hours:
            break
    else:
        sys.exit("the sump never overflowed")
    spilled = a["sewer_overflow"]
    inject(w, "sewer_pump")
    row("PUMP ON")
    for h in range(48):
        for _ in range(60):
            world_tick(w)
        row("recovered" if u.sewer_storage == 0 and rows[-1][4] > 0 else "")
        if u.sewer_storage == 0 and h >= 2:
            break
    print(f"sanitary sump {args.sump:g} m3; lift pump {CFG['sewer_lift_m3_s'] * 3600:g} m3/h\n")
    print("| time | tank m3 | delivered m3 | to sewer m3 | sump m3 | pumped m3 | spilled m3 | |")
    print("|---|---:|---:|---:|---:|---:|---:|---|")
    shown = [r for k, r in enumerate(rows) if r[7] or k % 6 == 0 or k == len(rows) - 1]
    for r in shown:
        print(f"| {r[0]} | {r[1]:.2f} | {r[2]:.3f} | {r[3]:.3f} | {r[4]:.3f} | {r[5]:.3f} | {r[6]:.3f} | {r[7]} |")
    print("\nbalance, m3 (inflow - outflow - stock change = residual):")
    worst = 0.0
    for part, b in water_balance(w).items():
        worst = max(worst, abs(b["residual"]))
        print(f"  {part:15s} in {b['in']:12.6f}  out {b['out']:12.6f}  stock change {b['stock_change']:12.6f}  residual {b['residual']:.2e}")
    print(
        f"\nsanitary sewer: drained {a['to_sewer']:.3f} = pumped {a['sewer_pumped']:.3f} + spilled {a['sewer_overflow']:.3f}"
        f" + in the sump {u.sewer_storage - a['sewer0']:.3f}"
    )
    print(
        f"houses: delivered {a['delivered']:.3f} = drained {a['to_sewer']:.3f} + used up {a['consumed']:.3f}"
        f" ({(1 - CFG['sewer_return_frac']) * 100:.0f}% drunk, cooked, evaporated)"
    )
    ok = spilled > 0 and u.sewer_storage == 0 and a["sewer_overflow"] == spilled and worst < 1e-6
    print("\n" + ("SCENARIO OK" if ok else "SCENARIO FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
