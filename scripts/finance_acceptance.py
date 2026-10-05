"""Acceptance run of the finance demo in the full simulation.

    python3 scripts/finance_acceptance.py --days 30 --out data/finance-demo

Builds a fresh world (seed from hadleys/config.py), sets up houses A, B, C (hadleys/scenarios.py),
simulates the given number of days with all the physics, then for every demo house feeds the independent
finance_reference model with the day's utility bills and repair bills recorded from the physics, and with
wages, fees and the credit limit worked out from the rules and the employer's recorded activity (not taken
from the finance code); the scheduled repairs are checked against COSTS. It compares the model's daily
balances with the simulation. Prints the day-by-day tables and the story checks, exits
non-zero on any difference. With --out the world is saved there, so

    python3 hadleys_hope.py --data data/finance-demo

opens it in the browser at the end of the run.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from hadleys import finance_reference as ref  # noqa: E402
from hadleys.domains import households as hh  # noqa: E402
from hadleys.persistence import Store  # noqa: E402
from hadleys.config import COSTS  # noqa: E402
from hadleys.scenarios import DEMO, DEMO_REPAIRS, _row, expected_wage, setup_demo  # noqa: E402
from hadleys.simulation import world_tick  # noqa: E402
from hadleys.world import World  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    w = World()
    houses = setup_demo(w)
    opening = {k: float(w.hh_cash[i]) for k, i in houses.items()}
    # the reference gets its inputs from the scenario and the rules, not from the finance code under test:
    # wages from workers, wage_day and the employer's recorded activity; the credit limit from the nominal
    # wage; the recorded utility bills (physics) as they are; the repair bills checked against COSTS
    cfg = w.cfg
    nominal = {k: cfg["wage_day"][DEMO[k][2]] * DEMO[k][1] for k in houses}
    tpd = w.cfg["ticks_per_day"]
    rows = {k: [] for k in houses}
    t0 = time.time()
    for _ in range(args.days * tpd):
        world_tick(w)
        if w.t % tpd == 0:
            for k, i in houses.items():
                rows[k].append(_row(w, i))
            s = hh.summary(w)
            print(
                f"{w.time_str()} {time.time() - t0:5.0f}s  "
                + "  ".join(f"{k}: {r[-1]['cash']:8.2f} cr, debt {r[-1]['principal'] + r[-1]['interest'] + r[-1]['arrears']:8.2f}, {r[-1]['status']}" for k, r in rows.items())
                + f"  | colony debtors {s['debtors']} overdue {s['overdue']} bankrupt {s['bankrupt']}",
                flush=True,
            )
    failures = []
    for k, i in houses.items():
        events = []
        for t, what, value in w.fin_trace[i]:
            if what == "day":
                wage, bill, activity = value
                want = expected_wage(cfg, DEMO[k][1], DEMO[k][2], bool(w.h_type[i] == 3), activity)
                if abs(want - wage) > 0.005:
                    failures.append(f"{k}: wage {wage} at {hh.time_label(w, t)}, the rules give {want}")
                events.append(("day", t, want, bill))
            elif what == "repair":
                events.append(("repair", t, value))
            elif what == "fees":
                events.append(("fees", t, float(cfg["sewage_fee"] + cfg["internet_fee"])))
        billed = sorted(v for _, what, v in w.fin_trace[i] if what == "repair")
        scheduled = sorted(float(COSTS[key][0]) for key in DEMO_REPAIRS.get(k, []))
        missing = list(scheduled)
        for amount in billed:
            if amount in missing:
                missing.remove(amount)
        if missing:
            failures.append(f"{k}: scheduled repairs {missing} cr were not billed (billed {billed})")
        if len(billed) > len(scheduled):
            print(f"{k}: {len(billed) - len(scheduled)} repair(s) on top of the scenario (random incidents): {billed}")
        expected, model = ref.run(cfg, opening[k], nominal[k], events)
        diff = [(d + 1, a, b) for d, (a, b) in enumerate(zip(rows[k], expected)) if a != b]
        print(f"\n## {w.fin_scenario['labels'][str(i)]} (house {i + 1}, {hh.employer_name(w, i)}, {int(w.hh_workers[i])} earner(s))")
        print("| day | cash | loan principal | interest | unpaid bills | status | reference agrees |")
        print("|---|---|---|---|---|---|---|")
        for d, (a, b) in enumerate(zip(rows[k], expected)):
            print(
                f"| {d + 1} | {a['cash']:.2f} | {a['principal']:.2f} | {a['interest']:.2f} | {a['arrears']:.2f} | "
                f"{a['status']} | {'yes' if a == b else 'NO: ' + str(b)} |"
            )
        print("milestones:")
        for t, text in reversed(list(w.hh_notes[i])):
            print(f"  {hh.time_label(w, t)}  {text}")
        if diff:
            failures.append(f"{k}: {len(diff)} days differ from the reference, first {diff[0]}")
        if len(rows[k]) != len(expected):
            failures.append(f"{k}: {len(rows[k])} simulated days, {len(expected)} reference days")
    a, b, c = (rows[k] for k in "ABC")
    if any(r["loans"] or r["status"] != "normal" or r["cash"] <= 0 for r in a):
        failures.append("A: took a loan, fell behind or ran out of cash")
    if not any(r["loans"] for r in b) or b[-1]["repaid"] < 1 or b[-1]["loans"] or b[-1]["status"] != "normal":
        failures.append("B: the loan was not taken and repaid")
    if any(r["status"] == "bankrupt" for r in b):
        failures.append("B: went bankrupt")
    if c[-1]["status"] != "bankrupt" or c[-1]["principal"] + c[-1]["arrears"] <= 0:
        failures.append("C: not bankrupt with debt at the end")
    check = hh.internal_total(w) - w.fin_baseline - sum(w.fin_ext.values())
    print(f"\nmoney check: internal {hh.internal_total(w):.2f} = baseline {w.fin_baseline:.2f} + external {sum(w.fin_ext.values()):.2f} (unexplained {check:.2e})")
    if abs(check) > 1e-4:
        failures.append(f"money appeared or vanished: {check}")
    if args.out:
        Store(args.out).save_world(w)
        print(f"saved to {args.out}/world.pkl; open with: python3 hadleys_hope.py --data {args.out}")
    print("\n" + ("ACCEPTED" if not failures else "FAILED:\n  " + "\n  ".join(failures)))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
