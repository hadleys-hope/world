"""Reproducible finance scenarios (docs/FINANCE_RU.md).

Three stories, each with fixed initial conditions:
  A  solvent         two earners at the reactor, pays every bill, keeps a positive balance
  B  credit, repaid  two miners; the mine floods, a repair lands while income is down, a loan covers it,
                     the mine reopens and the loan is repaid early
  C  bankruptcy      one miner, the same flood, repairs above the credit limit (burst pipes, wiring,
                     aeration): the loan leaves bills unpaid, one wage cannot catch up, bankruptcy; the debt stays

Two ways to run them:
* run_ledger_scenario(name): the production finance code (finance_day_close / finance_month_close) is driven
  on a real World with fixed daily inputs and no physics, so the result is exact and takes a second;
  finance_reference.run() recomputes the same story independently (tests/test_finance_scenarios.py).
* setup_demo(w): the same three stories in the running world (`--scenario finance-demo`): houses A, B, C get
  the initial conditions, the flood and the repairs are scheduled as world events, the physics decides
  everything else. scripts/finance_acceptance.py runs it and checks it against finance_reference.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

from hadleys.config import CFG
from hadleys.domains import households as hh

# ---------------------------------------------------------------- ledger scenarios

# per day: (activity of the employer 0..1, utility bill cr); repairs: {day: amount billed during that day}
LEDGER_SCENARIOS = {
    "A-solvent": {
        "title": "A: earns enough, pays every bill, keeps a positive balance",
        "workers": 2,
        "employer": "reactor",
        "cash": 200.0,
        "days": 60,
        "bill": 18.0,
        "idle": [],
        "repairs": {},
    },
    "B-credit-recovery": {
        "title": "B: the mine stops, a repair lands, a loan covers it; the mine reopens and the loan is repaid",
        "workers": 2,
        "employer": "mine",
        "cash": 150.0,
        "days": 60,
        "bill": 18.0,
        "idle": list(range(2, 9)),  # the mine stands on days 2..8
        "repairs": {3: 600.0},  # house wiring
    },
    "C-bankruptcy": {
        "title": "C: one earner, the same stop and a big repair: overdue instalments, bankruptcy, the debt stays",
        "workers": 1,
        "employer": "mine",
        "cash": 30.0,
        "days": 60,
        "bill": 18.0,
        "idle": list(range(2, 9)),
        "repairs": {3: 2700.0},  # burst pipes 1200 + wiring 600 + aeration 900: more than the credit limit
    },
}


def _pick_house(w: World, workers: int):
    """A deterministic ordinary (non-manager, non-crew) house with this many residents."""
    crew = set(w.crew_house.values())
    for i in range(w.N):
        if w.h_residents[i] == workers and w.h_type[i] != 3 and i not in crew:
            return i
    raise ValueError("no such house")


def ledger_inputs(spec, cfg=CFG):
    """The scenario as finance_reference events, and the household's nominal wage."""
    c = cfg
    tpd = c["ticks_per_day"]
    rate = c["wage_day"][spec["employer"]] * spec["workers"]
    idle = c["idle_pay_frac"]
    events = []
    for d in range(1, spec["days"] + 1):
        if d in spec["repairs"]:
            events.append(("repair", d * tpd - tpd // 2, spec["repairs"][d]))
        act = 0.0 if d in spec["idle"] and spec["employer"] == "mine" else 1.0
        wage = round(rate * (idle + (1 - idle) * act) if spec["employer"] in ("mine", "water plant") else rate, 2)
        events.append(("day", d * tpd, wage, spec["bill"]))
        if d % c["days_per_month"] == 0:
            events.append(("fees", d * tpd, float(c["sewage_fee"] + c["internet_fee"])))
    return events, rate


def run_ledger_scenario(name: str, cfg=None):
    """Drive the production finance code with the scenario's inputs. Returns (world, house, daily rows)."""
    from hadleys.domains.finance import finance_day_close, finance_month_close, finance_record
    from hadleys.world import World

    spec = LEDGER_SCENARIOS[name]
    w = World(cfg or CFG)
    c = w.cfg
    tpd = c["ticks_per_day"]
    i = _pick_house(w, spec["workers"])
    w.hh_employer[i] = hh.EMPLOYERS.index(spec["employer"])
    hh.set_opening_cash(w, i, spec["cash"])
    s = int(w.h_sector[i])
    rows = []
    for d in range(1, spec["days"] + 1):
        if d in spec["repairs"]:
            w.t = d * tpd - tpd // 2
            finance_record(w, spec["repairs"][d], "house", s, "scenario", f"repair house:{i}", house=i)
        w.t = d * tpd
        w.h_meter_day[:] = 0.0
        w.h_water_day[:] = 0.0
        w.h_meter_day[i] = spec["bill"] / c["tariff_kwh"]
        down = d in spec["idle"]
        w.fin_act = [0.0 if down else float(tpd), float(tpd), tpd]
        finance_day_close(w)
        if d % c["days_per_month"] == 0:
            finance_month_close(w)
        rows.append(_row(w, i))
    return w, i, rows


def _row(w: World, i: int):
    return {
        "t": w.t,
        "cash": round(float(w.hh_cash[i]), 2),
        "principal": round(float(w.hh_principal[i]), 2),
        "interest": round(float(w.hh_interest[i]), 2),
        "arrears": round(float(w.hh_arrears[i]), 2),
        "status": hh.STATUS[int(w.hh_status[i])],
        "loans": len(w.hh_loans[i]),
        "repaid": int(w.hh_loans_repaid[i]),
    }


# ---------------------------------------------------------------- the live demo

DEMO = {
    # house: (label, residents wanted, employer, opening cash)
    "A": ("A · solvent", 2, "reactor", 200.0),
    "B": ("B · credit, repaid", 2, "mine", 150.0),
    "C": ("C · bankruptcy", 1, "mine", 30.0),
}


def setup_demo(w: World):
    """Houses A, B, C with the scenario's initial conditions and the scheduled world events."""
    c = w.cfg
    tpd = c["ticks_per_day"]
    crew = set(w.crew_house.values())
    chosen = {}
    # sector 2 row 1: close to the hub, ordinary houses (not managers, not crews)
    for key, (label, residents, employer, cash) in DEMO.items():
        for i in range(w.N):
            if (
                w.h_residents[i] == residents
                and w.h_type[i] in (0, 1)
                and i not in crew
                and i not in chosen.values()
                and w.h_sector[i] == 1
            ):
                chosen[key] = i
                break
        i = chosen[key]
        w.hh_employer[i] = hh.EMPLOYERS.index(employer)
        hh.set_opening_cash(w, i, cash)
        w.fin_trace[i] = []
        hh.note(w, i, f"scenario {label}: {residents} earner(s) at the {employer}, opening cash {cash:.0f} cr")
    A, B, C = chosen["A"], chosen["B"], chosen["C"]
    events = [
        # day 2 06:00: the mine floods for 6 days, miners go on standby pay
        [1 * tpd + 360, "mine_flood", 6],
        # day 3 03:00: B's wiring burns out (600 cr); at C the pipes burst, the wiring and the aeration go
        # (1200 + 600 + 900 cr, more than C's credit limit of 2160 cr)
        [2 * tpd + 180, "damage", f"house:{B}"],
        [2 * tpd + 180, "damage", f"house:{C}"],
        [2 * tpd + 180, "damage", f"aeration:{C}"],
        [2 * tpd + 180, "burst", C],
    ]
    w.fin_scenario = {
        "name": "finance-demo",
        "houses": {k: int(v) for k, v in chosen.items()},
        "labels": {str(v): DEMO[k][0] for k, v in chosen.items()},
        "events": sorted(events, key=lambda e: e[0]),
        "next": 0,
    }
    w.log("INFO", f"Finance demo: A = house {A + 1}, B = house {B + 1}, C = house {C + 1}")
    return chosen


def scenario_step(w: World):
    """Fire the scheduled scenario events that are due (called every tick from finance_tick)."""
    from hadleys.domains.incidents import damage_target

    sc = w.fin_scenario
    ev = sc["events"]
    while sc["next"] < len(ev) and ev[sc["next"]][0] <= w.t:
        _, kind, arg = ev[sc["next"]]
        sc["next"] += 1
        if kind == "mine_flood":
            w.mine_closed_until = max(w.mine_closed_until, w.t) + int(arg) * w.cfg["ticks_per_day"]
            w.log("ALARM", f"[scenario] mine flooded: no ore for {arg} days, miners are on standby pay")
        elif kind == "damage":
            damage_target(w, arg, "scenario", 1.0)
        elif kind == "burst":
            i = int(arg)
            w.h_burst[i] = True
            w.h_pipes_ok[i] = False
            w.open_issue(
                "pipes_burst", f"house:{i}", int(w.h_sector[i]), "scenario", "pipes",
                (float(w.h_x[i]), float(w.h_y[i])), "critical",
            )


def trace_events(w: World, i: int):
    """The recorded inputs of a demo house as finance_reference events."""
    out = []
    for t, what, value in w.fin_trace.get(i, []):
        if what == "repair":
            out.append(("repair", t, value))
        elif what == "day":
            out.append(("day", t, value[0], value[1]))
        elif what == "fees":
            out.append(("fees", t, value))
    return out


SCENARIOS = {"finance-demo": setup_demo}
