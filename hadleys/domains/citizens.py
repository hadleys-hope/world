"""Persistent resident profiles and a simulation-clock workday.

Routes are provisional polylines along the existing street rings. Obstacle-aware
navigation and verified building entrances belong to the next implementation stage.
"""
from dataclasses import dataclass
import math

PROFESSIONS = ("engineer", "electrician", "scientist")
STATES = ("HOME", "WALK_TO_WORK", "AT_WORK", "WALK_HOME")
WORKPLACES = {"garage": "Maintenance workshop", "medlab": "Research laboratory"}


@dataclass
class Citizen:
    id: int
    home: int
    profession: str
    workplace: str
    shift_start: int
    shift_end: int
    route: list
    route_length: float
    state: str = "HOME"
    progress: float = 0.0
    x: float = 0.0
    y: float = 0.0
    wait_reason: str = ""
    last_transition: int = 0


def polar(angle, radius):
    angle = math.radians(angle)
    return radius * math.cos(angle), radius * math.sin(angle)


def provisional_route(w, home, workplace):
    angle = float(w.h_angle[home])
    radius = float(w.h_radius[home]) - 25
    boundary = int(w.h_sector[home]) * 60 + math.degrees(6 / radius)
    work_angle, work_radius = w.cfg[workplace]
    points = [(float(w.h_x[home]), float(w.h_y[home])), polar(angle, radius)]
    def arc(start, end, r):
        steps = max(1, math.ceil(abs(end - start) / 2))
        points.extend(polar(start + (end - start) * k / steps, r) for k in range(1, steps + 1))
    arc(angle, boundary, radius)
    points.append(polar(boundary, 219))
    delta = (work_angle - boundary + 180) % 360 - 180
    arc(boundary, boundary + delta, 219)
    points.append(polar(work_angle, work_radius - 14))
    length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
    return points, length


def route_position(citizen):
    remaining = citizen.progress * citizen.route_length
    for a, b in zip(citizen.route, citizen.route[1:]):
        length = math.dist(a, b)
        if remaining <= length and length > 0:
            p = remaining / length
            return a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p
        remaining -= length
    return citizen.route[-1]


def initialize_citizens(w, migrate=False):
    """No global RNG draws: profiles don't perturb energy/weather simulations."""
    count = int(w.cfg.get("citizen_count", 300))
    citizens = []
    for i in range(count):
        legacy = migrate and i < len(getattr(w, "w_home", []))
        home = int(w.w_home[i]) if legacy else i % w.N
        profession = PROFESSIONS[i % len(PROFESSIONS)]
        workplace = "medlab" if profession == "scientist" else "garage"
        route, length = provisional_route(w, home, workplace)
        start = 8 * 60 + (i % 6) * 5
        c = Citizen(i, home, profession, workplace, start, start + 8 * 60, route, length)
        if legacy:
            c.state = STATES[int(w.w_state[i])]
            c.progress = float(w.w_prog[i])
            # Preserve the exact saved location, then join the remaining new route.
            old_position = (float(w.w_x[i]), float(w.w_y[i]))
            if c.state in ("WALK_TO_WORK", "WALK_HOME"):
                # Rebase the route around the saved point without teleporting on load.
                home_point = route[0]
                work_point = route[-1]
                c.route = [home_point, old_position, work_point]
                left, right = math.dist(home_point, old_position), math.dist(old_position, work_point)
                c.route_length = left + right
                c.progress = left / max(c.route_length, 1e-9)
            else:
                c.route[0 if c.state == "HOME" else -1] = old_position
                c.route_length = sum(math.dist(a, b) for a, b in zip(c.route, c.route[1:]))
                c.progress = 0. if c.state == "HOME" else 1.
            c.x, c.y = old_position
        else:
            c.x, c.y = c.route[0]
        citizens.append(c)
    w.citizens = citizens
    w.citizens_version = 1


def citizens_step(w):
    if w.paused or w.finished:
        return
    minute = w.t % w.cfg["ticks_per_day"]
    metres_per_tick = w.cfg.get("citizen_walk_mps", 1.3) * w.cfg["tick_seconds"]
    for c in w.citizens:
        previous = c.state
        storm = w.storm_ticks > 0
        locked = bool(w.lockdown_ticks[int(w.h_sector[c.home])])
        commute = math.ceil(c.route_length / max(metres_per_tick, 1e-9))
        shift_due = max(0, c.shift_start - commute) <= minute < c.shift_end
        c.wait_reason = ""
        if storm or locked:
            reason = "storm" if storm else "sector_lockdown"
            if c.state in ("HOME", "AT_WORK"):
                c.wait_reason = reason
                continue
            if locked:
                c.wait_reason = reason
                continue
            # On a provisional route, return to the closer known indoor endpoint.
            c.state = "WALK_HOME" if c.progress < .5 else "WALK_TO_WORK"
            c.wait_reason = "seeking_shelter"
        elif c.state == "HOME":
            if shift_due:
                c.state = "WALK_TO_WORK"
            else:
                c.wait_reason = "outside_shift"
        elif c.state == "AT_WORK":
            if not shift_due:
                c.state = "WALK_HOME"
            elif minute < c.shift_start:
                c.wait_reason = "before_shift"
        elif c.state == "WALK_TO_WORK" and not shift_due:
            c.state = "WALK_HOME"
        if c.state in ("WALK_TO_WORK", "WALK_HOME"):
            direction = 1 if c.state == "WALK_TO_WORK" else -1
            c.progress = min(1., max(0., c.progress + direction * metres_per_tick / max(c.route_length, 1e-9)))
            c.x, c.y = route_position(c)
            if c.progress in (0., 1.):
                c.state = "HOME" if c.progress == 0 else "AT_WORK"
                c.wait_reason = "storm" if storm else ""
        if previous != c.state:
            c.last_transition = w.t


def citizen_snapshot(w):
    result = []
    for c in w.citizens:
        profile = {key: value for key, value in vars(c).items() if key != "route"}
        profile["workplace_name"] = WORKPLACES[c.workplace]
        profile["destination"] = c.home if c.state in ("HOME", "WALK_HOME") else c.workplace
        profile["indoors"] = c.state in ("HOME", "AT_WORK")
        result.append(profile)
    return result
