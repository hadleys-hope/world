"""domains / people: colony simulation components."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import math
from hadleys.domains.security import squad_step, xeno_step


def walker_path_point(w: World, i, p):
    """House -> along its row street to the boundary street of the sector -> down the boundary street to the hub."""
    c = w.cfg
    h = w.w_home[i]
    a0 = float(w.h_angle[h])
    r_street = float(w.h_radius[h]) - 30.0 + 5.0  # sidewalk side of the row street
    ba = float(w.h_sector[h]) * 60.0 + math.degrees(6.0 / r_street)
    arc = abs(a0 - ba) * math.pi / 180.0 * r_street
    rad = r_street - (c["hub_radius"] + 10)
    L = arc + rad
    d = p * L
    if d <= arc:
        a = a0 + (ba - a0) * (d / arc if arc > 0 else 1.0)
        rr = r_street
    else:
        a = ba
        rr = r_street - (d - arc)
    return rr * math.cos(math.radians(a)), rr * math.sin(math.radians(a))


def people_step(w: World):
    W = len(w.w_home)
    night = w.is_night()
    storm = w.storm_ticks > 0
    speed = 1.0 / 400.0
    for i in range(W):
        st = w.w_state[i]
        h = w.w_home[i]
        if st == 0:
            w.w_timer[i] -= 1
            if (
                w.w_timer[i] <= 0
                and not storm
                and not (night and w.rng.random() < 0.9)
                and not w.lockdown_ticks[w.h_sector[h]]
                and w.h_power_ok[h]
            ):
                w.w_state[i] = 1
                w.w_prog[i] = 0.0
            else:
                continue
        if st == 1:
            w.w_prog[i] = min(1.0, w.w_prog[i] + speed)
            if w.w_prog[i] >= 1.0:
                w.w_state[i] = 2
                w.w_timer[i] = int(w.rng.integers(30, 240))
        elif st == 2:
            w.w_timer[i] -= 1
            if w.w_timer[i] <= 0 or storm:
                w.w_state[i] = 3
        elif st == 3:
            w.w_prog[i] = max(0.0, w.w_prog[i] - speed * 1.3)
            if w.w_prog[i] <= 0.0:
                w.w_state[i] = 0
                w.w_timer[i] = int(w.rng.integers(120, 900))
        x, y = walker_path_point(w, i, float(w.w_prog[i]))
        w.w_x[i], w.w_y[i] = x, y
    xeno_step(w)
    squad_step(w)
