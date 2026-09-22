"""domains / security: colony simulation components."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import math
import numpy as np
from hadleys.geometry.roads import arc_waypoints
from hadleys.numerics import polar


def move_toward(m, tx, ty, speed):
    dx, dy = tx - m["x"], ty - m["y"]
    d = math.hypot(dx, dy)
    if d <= speed:
        m["x"], m["y"] = tx, ty
        return True
    m["x"] += dx / d * speed
    m["y"] += dy / d * speed
    m["heading"] = math.atan2(dy, dx)
    return False


def street_path(w: World, sector, house):
    """Waypoints from the hub end of the sector's boundary street to a house along the streets."""
    ba = sector * 60.0 + math.degrees(6.0 / 300)
    r_street = float(w.h_radius[house]) - 30.0 + 5.0
    pts = [polar(ba, w.cfg["hub_radius"] + 12), polar(ba, r_street)]
    pts += arc_waypoints(ba, float(w.h_angle[house]), r_street, 4.0)
    return pts


def xeno_step(w: World):
    from hadleys.domains.incidents import damage_target

    c = w.cfg
    WR = c["wall_radius"]
    alive = []
    for m in w.xeno_markers:
        st = m.get("state", "hunt")
        s = m["sector"]
        if st == "approach":
            if move_toward(m, *polar(m["angle"], WR + 4), 3.0):
                m["state"], m["timer"] = "breach", 25
        elif st == "breach":
            m["timer"] -= 1
            if m["timer"] <= 0:
                if w.wall_breach[s] is None:
                    w.wall_breach[s] = m["angle"]
                    w.open_issue(
                        "wall_breach",
                        f"wall:{s}",
                        s,
                        "xenomorph",
                        "wall",
                        polar(m["angle"], WR),
                        "critical",
                    )
                    w.log("ALARM", f"Xenomorphs breached the wall of sector {s + 1}")
                m["state"] = "hunt"
                hs = np.flatnonzero(w.h_sector == s)
                m["target"] = int(w.rng.choice(hs))
                m["kills"] = 0
        elif st == "hunt":
            j = m["target"]
            if move_toward(m, float(w.h_x[j]), float(w.h_y[j]), 2.6):
                m["state"], m["timer"] = "attack", 40
                if w.h_wiring_ok[j]:
                    damage_target(w, f"house:{j}", "xenomorph", 1.0)
        elif st == "attack":
            m["timer"] -= 1
            if m["timer"] <= 0:
                m["kills"] = m.get("kills", 0) + 1
                if m["kills"] < 2:
                    hs = np.flatnonzero(w.h_sector == s)
                    m["target"] = int(w.rng.choice(hs))
                    m["state"] = "hunt"
                else:
                    m["state"] = "retreat"
        elif st == "retreat":
            ang = w.wall_breach[s] if w.wall_breach[s] is not None else m["angle"]
            if move_toward(m, *polar(ang, WR + 160), 3.5):
                continue  # gone
        elif st == "dying":
            m["timer"] -= 1
            if m["timer"] <= 0:
                continue
        if w.t > m["until"] and st in ("hunt", "attack"):
            m["state"] = "retreat"
        if m["state"] in ("breach", "hunt", "attack"):
            w.lockdown_ticks[s] = max(
                w.lockdown_ticks[s], 30
            )  # lockdown holds while they are inside
        alive.append(m)
    w.xeno_markers = alive


def squad_step(w: World):
    """Four marines from the operations center: go to the locked sector, kill what they reach, come back."""
    from hadleys.domains.incidents import damage_target

    q = w.squad
    c = w.cfg
    if q["state"] == "BASE":
        threats = [
            m for m in w.xeno_markers if m.get("state") in ("hunt", "attack", "breach")
        ]
        if threats:
            m = threats[0]
            q["sector"] = m["sector"]
            q["route"] = street_path(
                w,
                m["sector"],
                m.get("target", int(np.flatnonzero(w.h_sector == m["sector"])[0])),
            )
            q["state"] = "DEPLOY"
            w.log("WARN", f"Marine squad deployed to sector {m['sector'] + 1}")
    elif q["state"] == "DEPLOY":
        if q["route"]:
            tx, ty = q["route"][0]
            if move_toward(q, tx, ty, 7.0):
                q["route"].pop(0)
        else:
            q["state"], q["timer"] = "FIGHT", 240
    elif q["state"] == "FIGHT":
        q["timer"] -= 1
        threats = [
            m
            for m in w.xeno_markers
            if m.get("state") in ("hunt", "attack", "breach", "approach")
            and m["sector"] == q["sector"]
        ]
        if threats:
            m = min(threats, key=lambda m: math.hypot(m["x"] - q["x"], m["y"] - q["y"]))
            if (
                move_toward(q, m["x"], m["y"], 3.5)
                or math.hypot(m["x"] - q["x"], m["y"] - q["y"]) < 25
            ):
                m["state"], m["timer"] = "dying", 12
                w.log("INFO", f"Marines killed a xenomorph in sector {q['sector'] + 1}")
                if w.rng.random() < 0.25:
                    hs = np.flatnonzero(w.h_sector == q["sector"])
                    j = int(
                        hs[
                            np.argmin(
                                (w.h_x[hs] - q["x"]) ** 2 + (w.h_y[hs] - q["y"]) ** 2
                            )
                        ]
                    )
                    if w.h_terminal_ok[j]:
                        damage_target(w, f"terminal:{j}", "marines", 1.0)
        elif q["timer"] <= 0 or not [
            m for m in w.xeno_markers if m["sector"] == q["sector"]
        ]:
            q["route"] = list(
                reversed(
                    street_path(
                        w,
                        q["sector"],
                        int(np.flatnonzero(w.h_sector == q["sector"])[0]),
                    )
                )
            )[:2] + [(0.0, 60.0)]
            q["state"] = "RETURN"
    elif q["state"] == "RETURN":
        if q["route"]:
            tx, ty = q["route"][0]
            if move_toward(q, tx, ty, 4.0):
                q["route"].pop(0)
        else:
            q["state"] = "BASE"


def spawn_xeno(w: World, s, n=None):
    """A pack appears outside the wall of the sector and heads for it."""
    n = n or int(w.rng.integers(2, 5))
    ang = s * 60 + w.rng.uniform(8, 52)
    for k in range(n):
        x, y = polar(
            ang + w.rng.uniform(-3, 3),
            w.cfg["wall_radius"] + 120 + w.rng.uniform(0, 60),
        )
        w.xeno_markers.append(
            {
                "x": x,
                "y": y,
                "until": w.t + 400,
                "sector": s,
                "state": "approach",
                "angle": ang,
                "timer": 0,
                "target": -1,
                "heading": 0.0,
                "id": int(w.rng.integers(1, 10**6)),
            }
        )
