"""domains / fauna: flying crocodiles, the native fauna of LV-426.

A small flock roosts on the ocean shore. By day, when there is no storm and the west gate is open, they fly to
the colony along the industrial road, pass the gate low, climb and soar in circles over the houses under the
dome. They are cold-blooded: now and then one comes down to bask on the roof of a heated house. In the evening
they fly home. A lockdown that closes the west gate keeps the ones outside out and the ones inside in.

They are also the face of the existing "wildlife" incidents: when wildlife damages a house, the nearest
crocodile in the air dives to that roof (fauna_blame). They add no damage of their own.

The flock never draws from the physics rng (its own stream is stored on the world) and logs nothing by itself,
so a world without crocodiles is bit-identical to one with them. Positions are map units; `z` is the height
above the ground, which the viewer adds to the terrain.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import math
import numpy as np
from hadleys.geometry.terrain import site_elevation
from hadleys.numerics import clamp, polar

WEST_GATE = 3  # gate g sits in the wall at g * 60 degrees; the industrial road leaves through this one
CRUISE, LOW, DIVE = 14.0, 10.0, 16.0  # map units per tick: open flight, the low pass through the gate, a dive
CLIMB = 6.0  # largest change of height per tick
# where a crocodile sits on a house, by house type: the viewer's house heights (models/materials.js DIM:
# 7.25 m, and 10.65 m for the two-storey types) plus the height of its belly over its feet
ROOF = (9.4, 12.8, 9.4, 12.8)
GATE_Z = 8.0  # height of the pass through the gate
TRANSIT_Z = 45.0  # height over the open ground between the shore and the gate
DAWN, DUSK = 7, 19  # the flock leaves the roost after DAWN and turns home at DUSK (hours)
AIRBORNE = ("soar", "dive")


def roost_site(c, shift=0.0):
    """The first dry spot on the ray from the ocean centre to the colony, `shift` units along the shore."""
    cx, cy = c["ocean_center"]
    d = math.hypot(cx, cy)
    ux, uy = -cx / d, -cy / d
    ox, oy = cx - uy * shift, cy + ux * shift
    dry = c["ocean_level_m"] + 4.0
    t = 0.0
    while t < d and site_elevation(ox + ux * t, oy + uy * t, c) < dry:
        t += 5.0
    return ox + ux * t, oy + uy * t


def dome_ceiling(c, r):
    """Height of the glass above the ground at distance r from the hub (the viewer's dome, models/oasis.js)."""
    R = c["dome_radius"]
    return c["dome_height"] * math.sqrt(max(0.0, 1.0 - (r / R) ** 2)) if r < R else 0.0


def fauna_init(w: World):
    """Create the flock; called at the end of World.__init__ (Store.migrate copies it into old saves)."""
    c = w.cfg
    n = int(c.get("flying_crocs", 0))
    w.crocs = []
    w.croc_call = 0  # ticks the operator's call still overrides the hour
    w.fauna_rng = None
    if n <= 0:
        return
    # a private stream: the world's rng drives the physics and must not be touched
    g = w.fauna_rng = np.random.default_rng([int(c["seed"]), 0xC70C])
    r_in, r_out = float(w.h_radius.min()), float(w.h_radius.max())
    for k in range(n):
        hx, hy = roost_site(c, (k - (n - 1) / 2) * 34.0)
        radius = r_in + (r_out - r_in) * (k + 0.5) / n
        w.crocs.append(
            {
                "id": k + 1,
                "x": hx,
                "y": hy,
                "z": 0.0,
                "heading": math.atan2(-hy, -hx),
                "state": "roost",
                "timer": int(g.integers(0, 90)),  # how long after dawn this one sleeps in
                "house": -1,
                "home": (hx, hy),
                "radius": radius,
                # well under the glass at its orbit, higher for the wide circles
                "alt": min(60.0 + 8.0 * k, dome_ceiling(c, radius) - 50.0),
                "turn": 1 if k % 2 == 0 else -1,
                "leg": 0,  # which stretch of the way in or out it is on
                "blamed": False,
            }
        )


def _gate_points(c):
    """Outside and inside ends of the low pass through the west gate."""
    wr = c["wall_radius"]
    return polar(WEST_GATE * 60.0, wr + 110.0), polar(WEST_GATE * 60.0, wr - 90.0)


def _fly(m, tx, ty, tz, speed, hold=None):
    """One tick towards (tx, ty), ending at height tz. With `hold` it keeps that height on the way and comes
    down (or climbs) only over the last stretch, so it never skims the roofs across the colony. True on arrival."""
    dx, dy = tx - m["x"], ty - m["y"]
    d = math.hypot(dx, dy)
    if hold is not None and d > (abs(hold - tz) / CLIMB + 1.0) * speed:
        tz = hold
    m["z"] += clamp(tz - m["z"], -CLIMB, CLIMB)
    if d <= speed:
        m["x"], m["y"] = tx, ty
        return abs(tz - m["z"]) < 0.01
    m["x"] += dx / d * speed
    m["y"] += dy / d * speed
    m["heading"] = math.atan2(dy, dx)
    return False


def _soar(m):
    """One tick along the circle around the hub, easing onto the crocodile's own radius and height."""
    r = math.hypot(m["x"], m["y"])
    a = math.atan2(m["y"], m["x"]) + m["turn"] * CRUISE / max(r, 60.0)
    r += clamp(m["radius"] - r, -CRUISE * 0.4, CRUISE * 0.4)
    m["x"], m["y"] = r * math.cos(a), r * math.sin(a)
    m["z"] += clamp(m["alt"] - m["z"], -CLIMB, CLIMB)
    m["heading"] = a + m["turn"] * math.pi / 2


def fauna_step(w: World):
    crocs = getattr(w, "crocs", None)  # worlds saved before the flock existed (Klyaksa cities) have none
    if not crocs:
        return
    c = w.cfg
    hour = w.t // 60 % 24
    gate_open = w.gate_state[WEST_GATE] == "OPEN"
    if w.croc_call > 0:
        w.croc_call -= 1
    day = (DAWN <= hour < DUSK and w.storm_ticks <= 0) or w.croc_call > 0
    outside, inside = _gate_points(c)
    g = w.fauna_rng
    for m in crocs:
        st = m["state"]
        if st == "roost":
            if day and gate_open:
                m["timer"] -= 1
                if m["timer"] <= 0 or w.croc_call > 0:
                    m["state"], m["leg"] = "inbound", 0
        elif st == "inbound":
            if m["leg"] == 0:  # over the open ground, coming down for the gate
                if not (day and gate_open):
                    m["state"], m["leg"] = "outbound", 2  # night, storm or a shut gate: back to the shore
                    continue
                if _fly(m, outside[0], outside[1], GATE_Z, CRUISE, hold=TRANSIT_Z):
                    m["leg"] = 1
            elif _fly(m, inside[0], inside[1], GATE_Z, LOW):  # the low pass through the gate
                m["state"], m["leg"] = "soar", 0
        elif st == "soar":
            if not day and gate_open:
                m["state"], m["leg"] = "outbound", 0
                continue
            _soar(m)
            if day and g.random() < c["croc_bask_p"]:
                warm = np.flatnonzero(w.h_heater_on & w.h_power_ok)
                if len(warm):
                    m["house"] = int(warm[int(g.integers(0, len(warm)))])
                    m["state"] = "dive"
        elif st == "dive":
            i = m["house"]
            if _fly(m, float(w.h_x[i]), float(w.h_y[i]), ROOF[int(w.h_type[i])], DIVE, hold=m["alt"]):
                m["state"] = "bask"
                m["timer"] = 25 if m["blamed"] else int(g.integers(30, 120))
        elif st == "bask":
            m["timer"] -= 1
            if m["timer"] <= 0 or (not day and gate_open):
                m["state"], m["house"], m["blamed"] = "soar", -1, False
        elif st == "outbound":
            if m["leg"] == 0:  # under the dome, heading for the gate
                if day or not gate_open:
                    m["state"] = "soar"  # the day is back, or the gate shut them in: keep circling
                elif _fly(m, inside[0], inside[1], GATE_Z, CRUISE, hold=m["alt"]):
                    m["leg"] = 1
            elif m["leg"] == 1:
                if _fly(m, outside[0], outside[1], GATE_Z, LOW):
                    m["leg"] = 2
            else:
                hx, hy = m["home"]
                if _fly(m, hx, hy, 0.0, CRUISE, hold=TRANSIT_Z):
                    m["state"], m["leg"] = "roost", 0
                    m["timer"] = int(g.integers(0, 90))
                    m["heading"] = math.atan2(-hy, -hx)


def fauna_blame(w: World, house: int):
    """Wildlife has just damaged this house: the nearest crocodile in the air comes down on its roof."""
    crocs = getattr(w, "crocs", None)
    if not crocs:
        return None
    hx, hy = float(w.h_x[house]), float(w.h_y[house])
    near = [m for m in crocs if m["state"] in AIRBORNE]
    if not near:
        return None
    m = min(near, key=lambda m: math.hypot(m["x"] - hx, m["y"] - hy))
    m["state"], m["house"], m["blamed"] = "dive", int(house), True
    w.h_log[house].appendleft((w.t, "a flying crocodile came down on the roof"))
    return m


def fauna_call(w: World, ticks=240):
    """The operator stirs the flock: every roosting crocodile leaves for the colony now, whatever the hour."""
    w.croc_call = ticks
    return sum(1 for m in getattr(w, "crocs", []) if m["state"] == "roost")


def fauna_snapshot(w: World):
    """The flock for /state: compact rows the viewer interpolates between polls."""
    return [
        {
            "id": m["id"],
            "x": round(m["x"], 1),
            "y": round(m["y"], 1),
            "z": round(m["z"], 1),
            "heading": round(m["heading"], 2),
            "state": m["state"],
            "house": m["house"] + 1,
        }
        for m in getattr(w, "crocs", [])
    ]
