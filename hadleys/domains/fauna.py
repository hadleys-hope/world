"""domains / fauna: flying crocodiles, the native fauna of LV-426.

A small flock roosts on the ocean shore. By day, when there is no storm and the west gate is open, they fly to
the colony along the industrial road, pass the gate low, climb and soar in circles over the houses under the
dome. They are cold-blooded: now and then one comes down to bask on the roof of a heated house. In the evening
they fly home. A lockdown that closes the west gate keeps the ones outside out and the ones inside in.

They are also the face of the existing "wildlife" incidents: when wildlife damages a house, the nearest
crocodile in the air dives to that roof (fauna_blame).

Raids. Every few days (by day, not in a storm) or on the operator's command a wild flock gathers on the sea
cliffs: half an hour of warning, then two dozen crocodiles fly in through the west gate and settle on whatever
they fancy: they foul the ventilation of houses, chew power spans and internet cables, smash street lamps and
rip house wiring. Every hit is an ordinary incident (damage_target), so the same engineers repair it at the
colony's cost. A west gate shut in time (lockdown) keeps them out of the dome: they turn on the solar field
(droppings, less power) and the comms tower line (the uplink drops). When their time is up they fly home.

The calm flock never draws from the physics rng (its own stream is stored on the world) and logs nothing by
itself; without raids (croc_raid_mean_days = 0) a world with crocodiles is bit-identical to one without.
Raids change the world on purpose. Positions are map units; `z` is the height above the ground, which the
viewer adds to the terrain.
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
RAID = 24.0  # a hungry wild flock flies in faster than the colony's own
CLIMB = 6.0  # largest change of height per tick
# where a crocodile sits on a house, by house type: the viewer's house heights (models/materials.js DIM:
# 7.25 m, and 10.65 m for the two-storey types) plus the height of its belly over its feet
ROOF = (9.4, 12.8, 9.4, 12.8)
GATE_Z = 8.0  # height of the pass through the gate: under the wall top, the only way in
DOME_FOOT = 16.0  # the glass starts at the top of the wall posts (models/build.js, models/oasis.js)
TRANSIT_Z = 45.0  # height over the open ground between the shore and the gate
DAWN, DUSK = 7, 19  # the flock leaves the roost after DAWN and turns home at DUSK (hours)
AIRBORNE = ("soar", "dive")
GATHER = 30  # ticks of warning: the wild flock gathers on the cliffs before it flies
POLE_Z = 9.0  # where a crocodile perches on a pole
CAUSE = "flying crocodiles"
# what the raiders go for inside the dome, with weights; damage_target kinds with their severities
INSIDE = (("aeration", 0.45, 1.0), ("span", 0.2, 0.45), ("net_span", 0.12, 1.0), ("lamp", 0.13, 1.0), ("house", 0.1, 1.0))
OUTSIDE = (("solar", 0.75, 0.06), ("tower_line", 0.25, 1.0))
# Klyaksa's armoured domes: a raid has to break the dome before it gets at the city
DOME_HIT = 0.6  # health points (of 100) a crocodile knocks off the armoured glass with one good hit
DOME_REGEN = 0.03  # points per tick the dome crews restore between raids (about a day from empty)
DOME_BREACH_UNTIL = 25.0  # a breached dome lets them in until it is repaired back to this


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
    R = c["wall_radius"]  # the dome stands on the wall, its footing at the top of the posts
    return DOME_FOOT + c["dome_height"] * math.sqrt(max(0.0, 1.0 - (r / R) ** 2)) if r < R else 0.0


def fauna_init(w: World):
    """Create the flock; called at the end of World.__init__ (Store.migrate copies it into old saves)."""
    c = w.cfg
    n = int(c.get("flying_crocs", 0))
    w.crocs = []
    w.croc_call = 0  # ticks the operator's call still overrides the hour
    w.fauna_rng = None
    w.croc_raid = None  # the current raid: phase gather | raid | retreat, counts; None between raids
    w.dome_hp = 100.0  # the armoured dome's health (Klyaksa); LV-426 keeps the number but nothing hits it
    w.dome_breached = False
    w.fauna_on_klyaksa = True  # saved after the flock moved to Klyaksa (Store.migrate strips older LV-426 flocks)
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
    _raid_clock(w, day, g)
    for m in list(crocs):
        if m.get("raider"):
            _raider_step(w, m, g, gate_open, outside, inside)
            continue
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


# ---------------- raids ----------------

def raid_start(w: World, size=None):
    """A wild flock gathers on the sea cliffs and will fly in after GATHER ticks. Returns its size (0 if a raid
    is already on or the world has no fauna)."""
    g, c = getattr(w, "fauna_rng", None), w.cfg
    if g is None or getattr(w, "croc_raid", None):
        return 0
    n = int(size or c.get("croc_raid_size", 24))
    first = max((m["id"] for m in w.crocs), default=0) + 1
    for k in range(n):
        hx, hy = roost_site(c, 300.0 + k * 14.0)  # further along the shore than the colony's own flock
        w.crocs.append(
            {
                "id": first + k, "x": hx, "y": hy, "z": 0.0, "heading": math.atan2(-hy, -hx),
                "state": "gather", "timer": GATHER + int(g.integers(0, 15)), "house": -1, "home": (hx, hy),
                "radius": 0.0, "alt": 70.0 + 4.0 * (k % 8), "turn": 1, "leg": 0, "blamed": False,
                "raider": True, "target": None,
            }
        )
    w.croc_raid = {"phase": "gather", "t0": w.t, "arrive": w.t + GATHER, "until": None, "size": n, "hits": 0, "blocked": False}
    w.log("ALARM", f"A wild flock of {n} flying crocodiles is gathering on the shore: raid in {GATHER} min. Shut the west gate!")
    return n


def _raid_clock(w, day, g):
    raid = getattr(w, "croc_raid", None)
    c = w.cfg
    if c.get("dome_armor") and raid is None:
        w.dome_hp = min(100.0, getattr(w, "dome_hp", 100.0) + DOME_REGEN)
        if w.dome_breached and w.dome_hp >= DOME_BREACH_UNTIL:
            w.dome_breached = False
            w.log("INFO", "The dome is sealed again")
    if raid is None:
        mean = float(c.get("croc_raid_mean_days", 0))
        # one raid every `mean` days on average, counted over the twelve daylight hours
        if mean > 0 and day and w.croc_call == 0 and g.random() < 1.0 / (mean * 12 * 60):
            raid_start(w)
        return
    if raid["phase"] == "gather" and w.t >= raid["arrive"]:
        raid["phase"], raid["until"] = "raid", w.t + int(c.get("croc_raid_ticks", 150))
    elif raid["phase"] == "raid" and w.t >= raid["until"]:
        raid["phase"] = "retreat"
        w.log("WARN", f"The crocodile raid is over: {raid['hits']} things wrecked, the flock flies back to the cliffs")
    elif raid["phase"] == "retreat" and not any(m.get("raider") for m in w.crocs):
        w.croc_raid = None


def _pick_target(w, m, g, can_enter):
    """Something to land on: inside the dome if the way in is open, otherwise the solar field or the tower line."""
    c = w.cfg
    table = INSIDE if can_enter else OUTSIDE
    if not can_enter and c.get("dome_armor"):
        table = (("dome", 0.8, DOME_HIT),) + tuple((k, p * 0.2, s) for k, p, s in OUTSIDE)
    weights = np.array([t[1] for t in table])
    kind, _, severity = table[int(g.choice(len(table), p=weights / weights.sum()))]
    if kind == "dome":
        # a spot on the glass on the side they come from, low enough to claw at
        a = math.atan2(m["y"], m["x"]) + float(g.uniform(-0.5, 0.5))
        r = c["wall_radius"] * float(g.uniform(0.82, 0.97))
        x, y, z, i = r * math.cos(a), r * math.sin(a), dome_ceiling(c, r) + 3.0, None
    elif kind in ("aeration", "house"):
        i = int(g.integers(0, w.N))
        x, y, z = float(w.h_x[i]), float(w.h_y[i]), ROOF[int(w.h_type[i])]
    elif kind in ("span", "net_span", "lamp"):
        inside = np.flatnonzero(np.hypot(w.p_x, w.p_y) < c["wall_radius"] - 20)
        i = int(inside[int(g.integers(0, len(inside)))])
        x, y, z = float(w.p_x[i]), float(w.p_y[i]), POLE_Z
    elif kind == "solar":
        sx, sy = c["solar_pos"]
        x, y, z, i = sx + float(g.uniform(-60, 60)), sy + float(g.uniform(-40, 40)), 2.0, None
    else:  # the comms tower outside the wall: perched on it, they tear its line
        x, y, z, i = c["tower_pos"][0], c["tower_pos"][1], POLE_Z * 3, None
    # one sitting on the glass leaves it outwards before going anywhere else, so it never flies through the dome
    m["leave_glass"] = bool(m.get("outside")) and math.hypot(m["x"], m["y"]) < c["wall_radius"]
    m["target"] = {"kind": kind, "arg": i, "severity": severity, "x": x, "y": y, "z": z, "inside": kind in ("aeration", "house", "span", "net_span", "lamp")}
    m["outside"] = kind == "dome"  # on the glass, not under it
    m["house"] = i if kind in ("aeration", "house") else -1
    m["leg"] = 0


def _raider_step(w, m, g, gate_open, outside, inside):
    raid = w.croc_raid
    c = w.cfg
    st = m["state"]
    if st == "gather":
        m["timer"] -= 1
        if m["timer"] <= 0:
            m["state"] = "raid"
            _pick_target(w, m, g, gate_open)
    elif st == "raid":
        if raid is None or raid["phase"] == "retreat":
            _go_home(m, c)
            return
        if m.get("leave_glass"):
            a = math.atan2(m["y"], m["x"])
            if _fly(m, (c["wall_radius"] + 60) * math.cos(a), (c["wall_radius"] + 60) * math.sin(a), m["z"], RAID):
                m["leave_glass"] = False
            return
        t = m["target"]
        r = math.hypot(m["x"], m["y"])
        armoured = c.get("dome_armor")
        way_in = w.dome_breached if armoured else gate_open
        if t["inside"] and r >= c["wall_radius"] and armoured and not way_in:
            _pick_target(w, m, g, False)  # the dome is whole again: back to clawing at it
            return
        if t["inside"] and r >= c["wall_radius"]:
            if not gate_open and not armoured:  # the west gate is shut in their faces: they turn on what is outside
                if not raid["blocked"]:
                    raid["blocked"] = True
                    w.log("WARN", "The west gate is shut: the crocodiles turn on the solar field and the comms line")
                _pick_target(w, m, g, False)
                return
            if m["leg"] == 0:
                if _around(m, outside[0], outside[1], GATE_Z, RAID, TRANSIT_Z, c):
                    m["leg"] = 1
                return
            if _fly(m, inside[0], inside[1], GATE_Z, LOW):
                m["leg"] = 2
            return
        if t["kind"] == "dome":
            # climb outside the wall to the height of the spot first, then close in on the glass: never through it
            a = math.atan2(t["y"], t["x"])
            if m["leg"] == 0:
                if _around(m, (c["wall_radius"] + 60) * math.cos(a), (c["wall_radius"] + 60) * math.sin(a), t["z"], RAID, max(TRANSIT_Z, t["z"]), c):
                    m["leg"] = 1
            elif _fly(m, t["x"], t["y"], t["z"], DIVE):
                m["state"], m["timer"] = "attack", int(g.integers(6, 14))
            return
        moved = _fly(m, t["x"], t["y"], t["z"], DIVE, hold=m["alt"]) if r < c["wall_radius"] else _around(m, t["x"], t["y"], t["z"], RAID, TRANSIT_Z, c)
        if moved:
            m["state"], m["timer"] = "attack", int(g.integers(8, 20))
    elif st == "attack":
        m["timer"] -= 1
        if m["timer"] > 0:
            return
        from hadleys.domains.incidents import damage_target  # incidents imports this module: import here

        t = m["target"]
        fouled = t["kind"] == "solar" and w.solar_health <= 0.35  # droppings dim the panels, they do not destroy them
        if t["kind"] == "dome":
            if g.random() < c.get("croc_raid_hit_p", 0.6):
                w.dome_hp = max(0.0, w.dome_hp - t["severity"])
                raid["dome_hits"] = raid.get("dome_hits", 0) + 1
                if w.dome_hp <= 0 and not w.dome_breached:
                    w.dome_breached = True
                    w.log("ALARM", "The armoured dome is breached: the crocodiles are getting in")
        elif not fouled and g.random() < c.get("croc_raid_hit_p", 0.6):
            damage_target(w, t["kind"] if t["arg"] is None else f"{t['kind']}:{t['arg']}", CAUSE, t["severity"])
            raid["hits"] += 1
            if t["kind"] in ("aeration", "house"):
                w.h_log[t["arg"]].appendleft((w.t, "flying crocodiles wrecked the " + ("ventilation" if t["kind"] == "aeration" else "wiring")))
        if raid["phase"] == "raid":
            m["state"] = "raid"
            inside = math.hypot(m["x"], m["y"]) < c["wall_radius"] and not m.get("outside")
            way_in = w.dome_breached if c.get("dome_armor") else gate_open
            _pick_target(w, m, g, way_in or inside)  # already inside: no gate to pass
        else:
            _go_home(m, c)
    elif st == "outbound" and m["leg"] == 3:
        # off the glass first: straight out past the wall at the height it is at, then home over open ground
        a = math.atan2(m["y"], m["x"])
        if _fly(m, (c["wall_radius"] + 60) * math.cos(a), (c["wall_radius"] + 60) * math.sin(a), m["z"], RAID):
            m["leg"] = 2
    elif st == "outbound":
        if m["leg"] == 0:
            if not gate_open:  # shut in under the dome: they wait for the gate, circling
                _soar(m)
            elif _fly(m, inside[0], inside[1], GATE_Z, CRUISE, hold=m["alt"]):
                m["leg"] = 1
        elif m["leg"] == 1:
            if _fly(m, outside[0], outside[1], GATE_Z, LOW):
                m["leg"] = 2
        else:
            hx, hy = m["home"]
            if _around(m, hx, hy, 0.0, CRUISE, TRANSIT_Z, c):
                w.crocs.remove(m)  # back on the cliffs: they leave the colony's books


def _around(m, tx, ty, tz, speed, hold, c):
    """_fly, but a leg that would cut across an armoured dome goes round it: first to a point beside the dome
    on the near side of the chord, then on. Only for flights over open ground (both ends outside the wall)."""
    R = c["wall_radius"] + 50
    if c.get("dome_armor") and math.hypot(m["x"], m["y"]) >= R - 10 and math.hypot(tx, ty) >= R - 10:
        dx, dy = tx - m["x"], ty - m["y"]
        L2 = dx * dx + dy * dy or 1.0
        u = max(0.0, min(1.0, -(m["x"] * dx + m["y"] * dy) / L2))
        px, py = m["x"] + dx * u, m["y"] + dy * u
        d = math.hypot(px, py)
        if d < R:
            if d < 1e-6:
                px, py, d = -dy, dx, math.hypot(dx, dy)
            k = (R + 40) / d
            _fly(m, px * k, py * k, max(tz, TRANSIT_Z), speed, hold=hold)
            return False
    return _fly(m, tx, ty, tz, speed, hold=hold)


def _go_home(m, c):
    """Leave by the way they came: off the glass, out through the gate from under it, or straight home."""
    r = math.hypot(m["x"], m["y"])
    m["state"] = "outbound"
    on_glass = m.get("outside") or m.get("leave_glass")
    m["leg"] = 3 if on_glass and r < c["wall_radius"] else 0 if r < c["wall_radius"] else 2


def raid_snapshot(w: World):
    raid = getattr(w, "croc_raid", None)
    if not raid:
        return None
    left = (raid["arrive"] - w.t) if raid["phase"] == "gather" else (raid["until"] - w.t if raid["phase"] == "raid" else 0)
    return {"phase": raid["phase"], "size": raid["size"], "hits": raid["hits"], "blocked": raid["blocked"], "left": max(0, left),
            "dome_hits": raid.get("dome_hits", 0)}


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
            **({"wild": True} if m.get("raider") else {}),
        }
        for m in getattr(w, "crocs", [])
    ]
