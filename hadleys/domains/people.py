"""Resident workday and the existing security agents."""
import math
from hadleys.domains.citizens import citizens_step
from hadleys.domains.security import squad_step, xeno_step


def walker_path_point(w, i, p):
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


def people_step(w):
    citizens_step(w)
    xeno_step(w)
    squad_step(w)
