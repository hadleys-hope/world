"""domains / hazards: what Klyaksa does to a city on its shore, next to the creatine mine (cfg "klyaksa_hazards").

Creatine. The mine digs creatine, which sells for a fortune (mine_income_per_tick is set ~25x LV-426's ore),
and every ton of it in the air mutates the fauna: `mutation` grows with the creatine mined, and crocodile raids
on the dome get bigger and hit harder with it (domains/fauna.py).

Migrations. Every day or so a herd of elephant-sized crocodiles migrates across the sky over the city. They
drop manure in industrial amounts: it lands on the dome (dims it, clogs the air intakes at the rim) and on the
roads round the city. Air defence (ПВО) on the dome shoots them down before they are overhead: it needs power
and shells, and every shot costs money. Without it the manure piles up, the intakes clog one after another
(aeration issues in the houses) and the roads round the dome jam (road damage): the city drowns in manure.
Cleaning crews wash the dome and clear the roads all the time, at a cost per ton.

Plankton tides. Now and then a tide of predatory plankton comes in from the sea. It eats everything, steel and
concrete included: poles, cables, lamps and the wall of the seaward sector, more the denser it gets. It has to
be burned off (flamethrower crews, expensive); the colony burns it on its own once it is dense, or the operator
does it earlier.

Sea vapours. The tide and the rotting plankton give off vapours; personnel who breathe them drink and do
stupid things: vandalism rises with `drunk` (domains/incidents.py).

The hazards draw from their own random stream, so a world without them is untouched.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from hadleys.domains.fauna import dome_ceiling

if TYPE_CHECKING:
    from hadleys.world import World

MIGRANT_Z = 380.0  # they fly over the dome (300 m) with room to spare
MIGRANT_SPEED = 16.0
AA_RANGE = 1600.0  # map units from the hub
AA_P = 0.05  # per tick, per migrant in range: a shell brings one down
SHELL_COST = 60.0
CLEAN_PER_TICK = 0.05  # tons of manure the crews clear per tick, per sector and from the dome
CLEAN_COST = 25.0  # cr per ton
BURN_COST = 6000.0
DOME_DIRT_PER_TON = 0.4  # % of the dome covered per ton that lands on it


def hazards_init(w: World):
    c = w.cfg
    w.hazards_on = bool(c.get("klyaksa_hazards"))
    w.hazard_rng = np.random.default_rng([int(c["seed"]), 0x4A2D]) if w.hazards_on else None
    S = c["sectors"]
    w.creatine_t = 0.0
    w.mutation = 0.0
    w.manure = np.zeros(S)  # tons on the roads round each sector
    w.dome_dirt = 0.0  # % of the dome covered
    w.migrants = []
    w.migration = None  # {"t0", "size", "kills", "dropped"} while a herd is crossing
    w.aa = {"on": True, "ammo": 600, "kills": 0, "shots": 0}
    w.plankton = {"level": 0.0, "tide_until": -1, "burns": 0}
    w.vapour = 0.0
    w.drunk = 0.0
    w.hazard_costs = 0.0


def _seaward_sector(w):
    cx, cy = w.cfg["ocean_center"]
    return int((math.degrees(math.atan2(cy, cx)) % 360) // (360 / w.cfg["sectors"]))


def migration_start(w: World, size=None):
    if not getattr(w, "hazards_on", False) or w.migration:
        return 0
    g, c = w.hazard_rng, w.cfg
    n = int(size or g.integers(10, 17))
    a = float(g.uniform(0, 2 * math.pi))
    start, R = (math.cos(a), math.sin(a)), c["wall_radius"] + 2600
    side = float(g.uniform(-0.3, 0.3)) * c["wall_radius"]
    # they fly well over the dome: Klyaksa's armoured dome stands 0.42 of its radius tall
    top = 0.42 * (c["wall_radius"] + 45.0) if c.get("dome_armor") else 300.0
    for k in range(n):
        off = (k - n / 2) * 22.0
        w.migrants.append({
            "x": start[0] * R - start[1] * (side + off) + float(g.uniform(-20, 20)),
            "y": start[1] * R + start[0] * (side + off) + float(g.uniform(-20, 20)),
            "z": top + 150.0 + float(g.uniform(-30, 30)), "heading": a + math.pi, "state": "migrate", "id": 1000 + k,
        })
    w.migration = {"t0": w.t, "size": n, "kills": 0, "dropped": 0.0}
    w.log("WARN", f"A migrating herd of {n} crocodiles is heading over the city: air defence {'ready' if w.aa['on'] else 'OFF'}")
    return n


def plankton_tide(w: World, ticks=360):
    if not getattr(w, "hazards_on", False):
        return False
    w.plankton["tide_until"] = w.t + ticks
    w.log("WARN", f"A tide of predatory plankton is coming in on sector {_seaward_sector(w) + 1}")
    return True


def plankton_burn(w: World):
    p = w.plankton
    if p["level"] < 1:
        return False
    p["level"] = max(0.0, p["level"] - 70.0)
    p["burns"] += 1
    w.colony_budget -= BURN_COST
    w.hazard_costs += BURN_COST
    w.colony_month_expense = getattr(w, "colony_month_expense", 0.0) + BURN_COST
    w.log("INFO", f"Flamethrower crews burned the plankton off the seaward sector ({BURN_COST:.0f} cr)")
    return True


def hazards_step(w: World):
    if not getattr(w, "hazards_on", False):
        return
    from hadleys.domains.incidents import damage_target  # incidents imports the fauna, keep imports one way

    g, c, S = w.hazard_rng, w.cfg, w.cfg["sectors"]
    day = 7 <= w.t // 60 % 24 < 19
    # ---- creatine: the money, and the mutation it brings
    mined = 0.05 * float(getattr(w, "mine_frac", 0.0))
    w.creatine_t += mined
    w.mutation = min(3.0, w.creatine_t / 400.0)
    # ---- migrations
    if not w.migration and g.random() < 1.0 / (c.get("migration_mean_days", 1.0) * 1440):
        migration_start(w)
    powered = w.available_kw > 0 and w.substation_ok
    wr = c["wall_radius"]
    for m in list(w.migrants):
        if m["state"] == "falling":
            m["z"] -= 9.0
            m["x"] += math.cos(m["heading"]) * 4
            m["y"] += math.sin(m["heading"]) * 4
            r = math.hypot(m["x"], m["y"])
            floor = dome_ceiling(c, r) if c.get("dome_armor") else 0.0
            if m["z"] < floor:   # it hits the dome and slides off the glass
                m["z"] = floor
                m["x"] += m["x"] / (r or 1) * 7.0
                m["y"] += m["y"] / (r or 1) * 7.0
            if m["z"] <= 0:
                w.migrants.remove(m)
            continue
        m["x"] += math.cos(m["heading"]) * MIGRANT_SPEED
        m["y"] += math.sin(m["heading"]) * MIGRANT_SPEED
        r = math.hypot(m["x"], m["y"])
        aa = w.aa
        if aa["on"] and powered and aa["ammo"] > 0 and r < AA_RANGE:
            aa["ammo"] -= 1
            aa["shots"] += 1
            w.colony_budget -= SHELL_COST
            w.hazard_costs += SHELL_COST
            if g.random() < AA_P * 4:  # four shells a tick at each one in range
                m["state"] = "falling"
                aa["kills"] += 1
                w.migration["kills"] += 1
                continue
        if r < wr + 250:  # overhead: what it drops lands on the dome or the roads round it
            tons = 0.06
            w.migration["dropped"] += tons
            if r < wr:
                w.dome_dirt = min(100.0, w.dome_dirt + tons * DOME_DIRT_PER_TON)
            s = int((math.degrees(math.atan2(m["y"], m["x"])) % 360) // (360 / S))
            w.manure[s] += tons * (0.5 if r < wr else 1.0)
        if r > wr + 2700 and math.cos(math.atan2(m["y"], m["x"]) - m["heading"]) > 0:
            w.migrants.remove(m)  # out of sight on the far side
    # the same guns turn on a raid: raiders in range over the dome are shot down
    raid = getattr(w, "croc_raid", None)
    if raid and raid["phase"] == "raid" and w.aa["on"] and powered:
        # four turrets: each tick they can engage four raiders, so a big raid still reaches the glass
        targets = [m for m in w.crocs if m.get("raider") and m["state"] in ("raid", "attack") and m["z"] > 15 and math.hypot(m["x"], m["y"]) < AA_RANGE]
        for m in targets[:4]:
            if w.aa["ammo"] > 0:
                w.aa["ammo"] -= 1
                w.aa["shots"] += 1
                w.colony_budget -= SHELL_COST
                w.hazard_costs += SHELL_COST
                if g.random() < AA_P * 0.6:
                    m["state"] = "shot"
                    w.aa["kills"] += 1
                    raid["shot"] = raid.get("shot", 0) + 1
    if w.migration and not w.migrants:
        mg = w.migration
        w.log("INFO", f"The herd has passed: {mg['kills']} shot down, {mg['dropped']:.1f} t of manure dropped")
        w.migration = None
    # ---- cleaning: crews wash the dome and clear the roads, at a cost
    cleared = np.minimum(w.manure, CLEAN_PER_TICK)
    w.manure -= cleared
    washed = min(w.dome_dirt, CLEAN_PER_TICK * DOME_DIRT_PER_TON * 2)
    w.dome_dirt -= washed
    cost = (float(cleared.sum()) + washed / DOME_DIRT_PER_TON) * CLEAN_COST
    w.colony_budget -= cost
    w.hazard_costs += cost
    # ---- what the manure does when the crews fall behind
    for s in range(S):
        if w.manure[s] > 3.0 and g.random() < 0.002 * w.manure[s]:
            damage_target(w, f"road:{s}", "manure", 0.5)
    if w.dome_dirt > 50 and g.random() < 0.0004 * w.dome_dirt:
        hs = np.flatnonzero(w.h_radius > wr * 0.85)  # the houses by the rim breathe through the clogged intakes
        if len(hs):
            damage_target(w, f"aeration:{int(hs[int(g.integers(0, len(hs)))])}", "manure", 1.0)
    # ---- plankton tides
    p = w.plankton
    if p["tide_until"] < w.t and g.random() < 1.0 / (c.get("plankton_mean_days", 2.0) * 1440):
        plankton_tide(w)
    if w.t < p["tide_until"]:
        p["level"] = min(100.0, p["level"] + 0.5)
    else:
        p["level"] = max(0.0, p["level"] - 0.05)
    if p["level"] > 5 and g.random() < p["level"] / 100 * 0.05:
        s = _seaward_sector(w)
        poles = np.flatnonzero(w.p_sector == s)
        what = g.random()
        if len(poles) and what < 0.7:
            i = int(poles[int(g.integers(0, len(poles)))])
            damage_target(w, ("span:%d" if what < 0.4 else "net_span:%d" if what < 0.55 else "lamp:%d") % i, "plankton", 0.5)
        else:
            damage_target(w, f"gate:{s}", "plankton", 1.0)
    if p["level"] > c.get("plankton_burn_at", 45.0):
        plankton_burn(w)
    # ---- vapours and the people who breathe them
    w.vapour = min(1.0, p["level"] / 60.0 + (0.15 if not day else 0.0))
    w.drunk += (w.vapour - w.drunk) * 0.01
    if w.drunk > 0.5 and not getattr(w, "drunk_logged", False):
        w.log("WARN", "Personnel are drunk on the sea vapours: expect vandalism")
        w.drunk_logged = True
    elif w.drunk < 0.3:
        w.drunk_logged = False


def hazards_snapshot(w: World):
    if not getattr(w, "hazards_on", False):
        return None
    return {
        "creatine_t": round(w.creatine_t, 1), "mutation": round(w.mutation, 2),
        "manure_t": round(float(w.manure.sum()), 1), "dome_dirt": round(w.dome_dirt, 1),
        "aa": dict(w.aa), "migration": dict(w.migration) if w.migration else None,
        "migrants": [{"x": round(m["x"], 1), "y": round(m["y"], 1), "z": round(m["z"], 1), "heading": round(m["heading"], 2), "state": m["state"], "id": m["id"]} for m in w.migrants],
        "plankton": round(w.plankton["level"], 1), "tide": w.t < w.plankton["tide_until"], "burns": w.plankton["burns"],
        "drunk": round(w.drunk, 2), "costs": round(w.hazard_costs),
    }
