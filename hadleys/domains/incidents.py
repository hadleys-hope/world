"""domains / incidents: colony simulation components."""

from __future__ import annotations
from hadleys.enums import TransportKind, TransportState
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import math
import numpy as np
from hadleys.domains.finance import finance_record, finance_reserve
from hadleys.geometry.roads import plan_route
from hadleys.numerics import polar

HOUSE_TARGETS = ("house", "aeration", "terminal")


REPAIR_PRIORITY = {
    "reactor": 0,
    "trunk": 1,
    "substation": 1,
    "wall": 2,
    "feeder": 2,
    "rp": 2,
    "ups": 3,
    "pole": 3,
    "span": 4,
    "cabinet": 4,
    "tower_line": 5,
    "net_span": 5,
    "gate": 5,
    "road": 5,
    "lamp": 6,
    "solar": 6,
}


OUTSIDE_TARGETS = ("reactor", "trunk", "solar", "water_plant", "tower", "tower_line")


def issue_target_spec(w: World, iss: Issue):
    kind, _, arg = iss.target.partition(":")
    x, y = iss.pos
    if kind in OUTSIDE_TARGETS:
        return {"kind": "outside", "x": x + 40, "y": y + 30}
    if kind in ("house", "aeration", "terminal"):
        return {"kind": "house", "i": int(arg)}
    if kind in ("pole", "span", "net_span", "lamp"):
        i = int(arg)
        # nearest house of that pole's row street, or the hub end for spine poles
        if w.p_kind[i] == 1:
            hs = np.flatnonzero(w.h_pole == i)
            j = (
                int(hs[0])
                if len(hs)
                else int(np.argmin((w.h_x - x) ** 2 + (w.h_y - y) ** 2))
            )
            return {"kind": "house", "i": j}
        return {"kind": "hub", "s": int(w.p_sector[i])}
    if kind in ("cabinet", "rp", "feeder", "ups", "substation"):
        return {"kind": "hub", "s": int(iss.sector if iss.sector >= 0 else 0)}
    if kind == "gate":
        g = int(arg)
        return {"kind": "ring", "a": g * 60.0 + 1.0}
    if kind == "wall":
        s = int(arg)
        return {
            "kind": "ring",
            "a": (
                w.wall_breach[s] if w.wall_breach[s] is not None else s * 60.0 + 30.0
            ),
        }
    if kind == "road":
        return {"kind": "ring", "a": int(arg) * 60.0 + 30.0}
    return {"kind": "ring", "a": math.degrees(math.atan2(y, x)) % 360.0}


def _crew_fits(r: Rover, iss: Issue):
    """Plumber takes house jobs; engineers take the colony network and, when free, house wiring (it is electrical,
    and a house without wiring has no heat: leaving it to the one plumber let whole rows freeze).
    """
    house = iss.target.split(":")[0] in HOUSE_TARGETS
    if r.kind == TransportKind.PLUMBER:
        return house
    return (not house) or iss.kind == "house_wiring"


def _pipes_blocked(w: World, iss: Issue):
    """Fixing pipes in a house that still has no wiring is wasted: it freezes and bursts again."""
    if iss.kind != "pipes_burst":
        return 0
    return 0 if w.h_wiring_ok[int(iss.target.split(":")[1])] else 1


def _repair_rover(w: World, r: Rover):
    from hadleys.domains.security import spawn_xeno
    from hadleys.domains.transport import _go_home, rover_move

    if r.state == TransportState.TO_GARAGE:
        if rover_move(w, r):
            r.state = TransportState.IDLE
        return
    if r.state == TransportState.IDLE:
        cands = [i for i in w.issues if i.status == "funded" and _crew_fits(r, i)]
        if not cands:
            _go_home(w, r)
        if cands:
            cands.sort(
                key=lambda i: (
                    _pipes_blocked(w, i),
                    REPAIR_PRIORITY.get(i.target.split(":")[0], 9),
                    i.severity != "critical",
                    i.opened_t,
                )
            )
            iss = cands[0]
            if plan_route(w, r, issue_target_spec(w, iss)):
                r.job = iss
                iss.status = "in_progress"
                iss.started_t = w.t
                r.state = TransportState.TO_TARGET
            else:
                r.wait = 20
    elif r.state == TransportState.TO_TARGET:
        if rover_move(w, r):
            r.state = TransportState.REPAIRING
            r.timer = r.job.duration
            s = r.job.sector
            if s >= 0 and w.sector_dark[s] and w.rng.random() < 0.15:
                w.log(
                    "ALARM",
                    f"Repair crew attacked by xenomorphs in dark sector {s + 1}, repair aborted",
                )
                r.job.status = "funded"
                r.job = None
                r.state = TransportState.IDLE
                r.wait = 60
                spawn_xeno(w, s)
    elif r.state == TransportState.REPAIRING:
        r.timer -= 1
        if r.timer <= 0:
            resolve_issue(w, r.job)
            r.job = None
            r.state = TransportState.IDLE


def damage_target(w: World, target: str, cause: str, severity: float):
    c = w.cfg
    kind, _, arg = target.partition(":")
    if kind == "span":
        i = int(arg)
        w.s_health[i] = max(0.0, w.s_health[i] - severity)
        if w.s_health[i] < 0.2:
            w.open_issue(
                "span_broken",
                target,
                int(w.p_sector[i]),
                cause,
                "span",
                (float(w.p_x[i]), float(w.p_y[i])),
            )
    elif kind == "net_span":
        i = int(arg)
        w.n_span_ok[i] = False
        w.open_issue(
            "cable_broken",
            target,
            int(w.p_sector[i]),
            cause,
            "net_span",
            (float(w.p_x[i]), float(w.p_y[i])),
        )
    elif kind == "pole":
        i = int(arg)
        if severity > 0.7:
            w.p_state[i] = 2
            w.p_lamp_ok[i] = False
            w.open_issue(
                "pole_fallen",
                target,
                int(w.p_sector[i]),
                cause,
                "pole",
                (float(w.p_x[i]), float(w.p_y[i])),
                "critical",
            )
        elif severity > 0.3:
            w.p_state[i] = max(w.p_state[i], 1)
            w.open_issue(
                "pole_tilted",
                target,
                int(w.p_sector[i]),
                cause,
                "pole",
                (float(w.p_x[i]), float(w.p_y[i])),
            )
    elif kind == "lamp":
        i = int(arg)
        w.p_lamp_ok[i] = False
        w.open_issue(
            "lamp_broken",
            target,
            int(w.p_sector[i]),
            cause,
            "lamp",
            (float(w.p_x[i]), float(w.p_y[i])),
            "info",
        )
    elif kind == "house":
        i = int(arg)
        w.h_wiring_ok[i] = False
        w.open_issue(
            "house_wiring",
            target,
            int(w.h_sector[i]),
            cause,
            "wiring",
            (float(w.h_x[i]), float(w.h_y[i])),
        )
    elif kind == "aeration":
        i = int(arg)
        w.h_aeration_ok[i] = False
        w.open_issue(
            "aeration_failure",
            target,
            int(w.h_sector[i]),
            cause,
            "aeration",
            (float(w.h_x[i]), float(w.h_y[i])),
        )
    elif kind == "terminal":
        i = int(arg)
        w.h_terminal_ok[i] = False
        w.open_issue(
            "terminal_broken",
            target,
            int(w.h_sector[i]),
            cause,
            "terminal",
            (float(w.h_x[i]), float(w.h_y[i])),
            "info",
        )
    elif kind == "cabinet":
        s = int(arg)
        w.cabinet_ok[s] = False
        w.open_issue(
            "cabinet_damaged",
            target,
            s,
            cause,
            "cabinet",
            polar(s * 60 + 3, c["hub_radius"] + 40),
        )
    elif kind == "gate":
        g = int(arg)
        w.gate_ok[g] = False
        w.open_issue(
            "gate_damaged", target, g, cause, "gate", polar(g * 60, c["wall_radius"])
        )
    elif kind == "road":
        s = int(arg)
        w.road_integrity[s] = max(0.0, w.road_integrity[s] - severity * 100)
    elif kind == "feeder":
        s = int(arg)
        w.feeder_ok[s] = False
        w.open_issue(
            "feeder_broken",
            target,
            s,
            cause,
            "feeder",
            polar(s * 60 + 3, c["hub_radius"] - 20),
            "critical",
        )
    elif kind == "rp":
        s = int(arg)
        w.rp_ok[s] = False
        w.open_issue(
            "rp_damaged",
            target,
            s,
            cause,
            "rp",
            polar(s * 60 + 3, c["hub_radius"] + 30),
            "critical",
        )
    elif kind == "trunk":
        w.trunk_ok = False
        w.open_issue(
            "trunk_broken",
            "trunk",
            -1,
            cause,
            "trunk",
            (-c["wall_radius"] - 200, 0),
            "critical",
        )
    elif kind == "substation":
        w.substation_ok = False
        w.open_issue(
            "substation_damaged",
            "substation",
            -1,
            cause,
            "substation",
            (0, -60),
            "critical",
        )
    elif kind == "tower_line":
        w.tower_line_ok = False
        w.open_issue(
            "tower_line_broken",
            "tower_line",
            -1,
            cause,
            "tower_line",
            (c["tower_junction"][0], c["tower_pos"][1] / 2),
            "warning",
        )
    elif kind == "solar":
        w.solar_health = max(0.0, w.solar_health - severity)
        w.open_issue(
            "solar_damaged", "solar", -1, cause, "solar", c["solar_pos"], "info"
        )
    elif kind == "reactor":
        comp = arg
        if comp == "heat_exchanger":
            w.r_hx = max(0.0, w.r_hx - severity)
            w.open_issue(
                "heat_exchanger_damage",
                target,
                -1,
                cause,
                "heat_exchanger",
                c["reactor_pos"],
                "critical",
            )
        elif comp in ("pump_a", "pump_b"):
            setattr(w, "r_" + comp, 0.1)
            w.open_issue(
                "pump_trip", target, -1, cause, "pump", c["reactor_pos"], "critical"
            )
    elif kind == "ups":
        s = int(arg)
        w.ups_health[s] = 0.1
        w.open_issue(
            "ups_damaged",
            target,
            s,
            cause,
            "ups",
            polar(s * 60 + 3, c["hub_radius"] + 50),
        )


def resolve_issue(w: World, iss: Issue):
    kind, _, arg = iss.target.partition(":")
    if kind == "span":
        w.s_health[int(arg)] = 1.0
    elif kind == "net_span":
        w.n_span_ok[int(arg)] = True
    elif kind == "pole":
        i = int(arg)
        w.p_state[i] = 0
        w.p_lamp_ok[i] = True
    elif kind == "lamp":
        w.p_lamp_ok[int(arg)] = True
    elif kind == "house":
        i = int(arg)
        if iss.kind == "pipes_burst":
            w.h_burst[i] = False
            w.h_pipes_ok[i] = True
            w.h_frozen[i] = 0
        else:
            w.h_wiring_ok[i] = True
    elif kind == "aeration":
        w.h_aeration_ok[int(arg)] = True
    elif kind == "terminal":
        w.h_terminal_ok[int(arg)] = True
    elif kind == "cabinet":
        w.cabinet_ok[int(arg)] = True
    elif kind == "gate":
        w.gate_ok[int(arg)] = True
    elif kind == "wall":
        w.wall_breach[int(arg)] = None
    elif kind == "road":
        w.road_integrity[int(arg)] = 100.0
    elif kind == "feeder":
        w.feeder_ok[int(arg)] = True
    elif kind == "rp":
        w.rp_ok[int(arg)] = True
    elif kind == "trunk":
        w.trunk_ok = True
    elif kind == "substation":
        w.substation_ok = True
    elif kind == "tower_line":
        w.tower_line_ok = True
    elif kind == "solar":
        w.solar_health = 1.0
    elif kind == "reactor":
        if arg == "heat_exchanger":
            w.r_hx = 1.0
        else:
            setattr(w, "r_" + arg, 1.0)
    elif kind == "ups":
        w.ups_health[int(arg)] = 1.0
    iss.status = "resolved"
    iss.resolved_t = w.t
    finance_record(
        w, iss.cost, iss.payer, iss.sector, iss.cause, f"repair {iss.kind} {iss.target}"
    )
    w.log("INFO", f"Repaired {iss.kind} at {iss.target}, {iss.cost:.0f} cr")


def incidents_step(w: World):
    from hadleys.domains.security import spawn_xeno

    c = w.cfg
    S = w.S
    rng = w.rng
    night = w.is_night()
    v = w.wind
    z = 0.35 * (v - 22.0) + 3.0 * w.s_ice + 0.03 * (-w.t_out - 40) - 10.0
    p = (
        1.0 / (1.0 + np.exp(-z)) * 0.02 * (36.0 / w.P)
    )  # same colony-wide rate as with 36 spans
    p = p * np.where(w.p_state == 1, 2.0, 1.0)
    hit = rng.random(w.P) < p
    for i in np.flatnonzero(hit & (w.s_health >= 0.2)):
        damage_target(w, f"span:{i}", "weather", 1.0)
        if rng.random() < 0.5:
            damage_target(w, f"net_span:{i}", "weather", 1.0)
    pxeno = c["p_xeno"] * (3.0 if night else 1.0)
    for s in range(S):
        if rng.random() < pxeno * (2.0 if w.sector_dark[s] else 1.0):
            spawn_xeno(w, s)
            w.lockdown_ticks[s] = 240
            w.log("ALARM", f"Xenomorphs sighted outside sector {s + 1}: LOCKDOWN")
    if rng.random() < c["p_xeno"] * 0.5:
        w.nest_alert = 300
        w.marines_active = 300
        w.log(
            "ALARM",
            "Xenomorph nest activity under the atmosphere processor. Marines deployed.",
        )
    if w.nest_alert > 0:
        w.nest_alert -= 1
        w.marines_active = max(0, w.marines_active - 1)
        if rng.random() < c["p_nest_fire"] / 10:
            comp = (
                "heat_exchanger"
                if rng.random() < 0.6
                else ("pump_a" if rng.random() < 0.5 else "pump_b")
            )
            damage_target(w, f"reactor:{comp}", "marines", 0.6)
            w.log("ALARM", f"Stray marine fire damaged reactor {comp}")
    if rng.random() < c["p_vandal"] * (2.0 if night else 1.0):
        s = int(rng.integers(0, S))
        roll = rng.random()
        ps = np.flatnonzero(w.p_sector == s)
        if roll < 0.4:
            damage_target(w, f"lamp:{int(rng.choice(ps))}", "vandal", 1.0)
        elif roll < 0.6:
            damage_target(w, f"gate:{s}", "vandal", 1.0)
        elif roll < 0.8:
            hs = np.flatnonzero(w.h_sector == s)
            damage_target(w, f"terminal:{int(rng.choice(hs))}", "vandal", 1.0)
        else:
            hs = np.flatnonzero(w.h_sector == s)
            damage_target(w, f"aeration:{int(rng.choice(hs))}", "vandal", 1.0)
    if rng.random() < c["p_animal"]:
        i = int(rng.integers(0, w.N))
        damage_target(
            w, f"house:{i}" if rng.random() < 0.5 else f"aeration:{i}", "wildlife", 1.0
        )
    for s in range(S):
        if w.sector_dark[s] and rng.random() < c["p_rover_hit"]:
            ps = np.flatnonzero(w.p_sector == s)
            damage_target(w, f"pole:{int(rng.choice(ps))}", "impact", 0.9)
            w.log("WARN", f"Rover hit a pole in dark sector {s + 1}")
    w.xeno_markers = [m for m in w.xeno_markers if m["until"] > w.t]
    for iss in w.issues:
        if iss.status in ("open", "unfunded") and (w.t - iss.opened_t) % 30 == 0:
            if finance_reserve(w, iss):
                iss.status = "funded"
            else:
                if iss.status == "open":
                    w.log(
                        "WARN",
                        f"No funds for {iss.kind} at {iss.target} ({iss.cost:.0f} cr)",
                    )
                iss.status = "unfunded"


def pipes_audit(w: World):
    """Reconcile: every burst house must have an open pipes_burst issue, or nobody will ever fix it."""
    for i in np.flatnonzero(w.h_burst):
        w.open_issue(
            "pipes_burst",
            f"house:{i}",
            int(w.h_sector[i]),
            "freeze",
            "pipes",
            (float(w.h_x[i]), float(w.h_y[i])),
            "critical",
        )
