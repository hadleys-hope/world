"""domains / transport: colony simulation components."""

from __future__ import annotations
from hadleys.enums import TransportKind, TransportState
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import math
import numpy as np
from hadleys.domains.finance import finance_pay
from hadleys.geometry.roads import (
    angle_diff,
    arc_waypoints,
    colony_layout,
    plan_route,
    roundabout_route,
    signal_phase,
    traffic_junctions,
)
from hadleys.geometry.terrain import site_elevation
from hadleys.models import Rover
from hadleys.numerics import clamp, polar


def make_traffic(c):
    fleet = []
    for i in range(c.get("traffic_vehicles", 18)):
        radius = (
            c["ring_road_radius"]
            if i % 3 == 0
            else c["house_radius_min"]
            - 30
            + (i % c["house_rows"]) * c["house_ring_step"]
        )
        r = Rover(
            "transit-" + str(i + 1),
            TransportKind.TRANSIT,
            *polar((i * 137.508 + 7) % 360, radius),
            state=TransportState.CIRCULATING,
            speed=16 + i % 4 * 2,
        )
        r.job = {"radius": radius, "direction": 1 if i % 2 else -1, "cargo": False}
        r.heading = math.radians((i * 137.508 + 7) % 360) + (
            math.pi / 2 if i % 2 else -math.pi / 2
        )
        fleet.append(r)
    for i in range(2):
        a, rr = c["cargo_depot"]
        r = Rover(
            "freight-" + str(i + 1),
            TransportKind.FREIGHT,
            *polar(a - 11 + i * 9, rr),
            state=TransportState.TO_DEPOT,
            speed=13,
        )
        r.job = {"cargo": True, "radius": rr, "direction": 1}
        fleet.append(r)
    return fleet


def traffic_step(w):
    for r in w.traffic:
        if r.kind == TransportKind.TRANSIT:
            if not r.route:
                a = math.degrees(math.atan2(r.y, r.x))
                r.route = arc_waypoints(
                    a, a + r.job["direction"] * 60, r.job["radius"], 2
                )
            if math.hypot(r.x, r.y) > w.cfg["ring_road_radius"] - 5:
                a = math.degrees(math.atan2(r.y, r.x)) % 360
                nearest = int(round(a / 60)) % 6
                if (
                    abs(angle_diff(a, nearest * 60)) < 2
                    and w.gate_state[nearest] == "LOCKDOWN"
                ):
                    r.velocity = 0
                    continue
            rover_move(w, r)
            if r.fuel_l < 15 and not r.route:
                r.fuel_l = 120  # fuel service at a route endpoint
        elif r.state in (TransportState.TO_DEPOT, TransportState.RETURN):
            if not r.route:
                aa, rr = w.cfg["cargo_depot"]
                a = math.degrees(math.atan2(r.y, r.x))
                r.route = arc_waypoints(a, aa, rr, 2)
            if rover_move(w, r):
                r.state = TransportState.WAITING
                r.velocity = 0
        elif r.state == TransportState.DELIVER:
            if rover_move(w, r):
                r.state = TransportState.UNLOADING
                r.timer = 8
        elif r.state == TransportState.UNLOADING:
            r.timer -= 1
            if r.timer <= 0:
                r.load = 0
                r.state = TransportState.RETURN
                w.cargo["completed"] += 1
    # One rail-mounted crane serves one truck; no container teleport between vehicles.
    if w.cargo["phase"] == "WAIT":
        ready = [
            i
            for i, r in enumerate(w.traffic)
            if r.kind == TransportKind.FREIGHT and r.state == TransportState.WAITING
        ]
        if ready and w.cargo["loaded"] < 24:
            w.cargo.update(phase="LIFT", progress=0.0, truck=ready[0])
            w.traffic[ready[0]].state = TransportState.LOADING
    else:
        w.cargo["progress"] += 1 / 24
        if w.cargo["progress"] >= 1:
            r = w.traffic[w.cargo["truck"]]
            r.load = 1
            r.state = TransportState.DELIVER
            a, rr = w.cfg["cargo_depot"]
            r.route = arc_waypoints(a, 420, rr, 2)
            w.cargo["loaded"] += 1
            w.cargo["phase"] = "WAIT"
            w.cargo["progress"] = 0


def rover_move(w: World, r: Rover):
    """Advance along the planned route. Returns True when the route is finished."""
    if r.wait > 0:
        r.wait -= 1
        r.velocity = 0.0
        return False
    if not r.route:
        r.velocity = 0.0
        gx, gy = polar(*w.cfg["garage"])
        if math.hypot(r.x - gx, r.y - gy) < 40:
            r.fuel_l = min(120, getattr(r, "fuel_l", 120) + 20)
        return True
    if getattr(r, "_roundabout_route", None) is not r.route:
        r.route = roundabout_route((r.x, r.y), r.route, w.cfg)
        r._roundabout_route = r.route
    tx, ty = r.route[0]
    dx, dy = tx - r.x, ty - r.y
    d = math.hypot(dx, dy)
    grade = abs(site_elevation(tx, ty, w.cfg) - site_elevation(r.x, r.y, w.cfg)) / max(
        d, 1
    )
    target_speed = (
        r.speed * (0.5 if w.road_icy and not w.road_heating_on else 1) / (1 + grade * 5)
    )
    # Brake for the next bend and give moving vehicles a following gap.
    if len(r.route) > 1 and d < 18:
        nx, ny = r.route[1][0] - tx, r.route[1][1] - ty
        turn = abs(
            math.atan2(
                math.sin(math.atan2(ny, nx) - math.atan2(dy, dx)),
                math.cos(math.atan2(ny, nx) - math.atan2(dy, dx)),
            )
        )
        target_speed *= max(0.3, 1 - turn / math.pi)
    for other in w.rovers + getattr(w, "traffic", []):
        if other is r or (other.state == TransportState.IDLE and not other.route):
            continue
        ox, oy = other.x - r.x, other.y - r.y
        ahead = (ox * dx + oy * dy) / max(d, 1e-6)
        side = abs(ox * dy - oy * dx) / max(d, 1e-6)
        gap = (
            18
            if r.kind == TransportKind.FREIGHT or other.kind == TransportKind.FREIGHT
            else 6
        )
        if (
            0 < ahead < gap + 5
            and side < 3
            and math.cos(other.heading - math.atan2(dy, dx)) > 0.7
        ):
            target_speed = min(target_speed, max(0, ahead - gap))
    r.velocity = min(target_speed, getattr(r, "velocity", 0) + 2.5)
    r.fuel_l = getattr(r, "fuel_l", 120.0)
    if r.fuel_l <= 0:
        r.velocity = 0
    budget = r.velocity
    # Stop the vehicle nose before the painted bar; yield to circulating traffic.
    for junction in traffic_junctions(w.cfg):
        if junction["mode"] == "roundabout":
            continue
        ox, oy = junction["x"] - r.x, junction["y"] - r.y
        ahead = (ox * dx + oy * dy) / max(d, 1e-6)
        lateral = abs(ox * dy - oy * dx) / max(d, 1e-6)
        angle = math.radians(junction["angle"])
        phase = signal_phase(w.t, junction)
        radial = abs((dx * math.cos(angle) + dy * math.sin(angle)) / max(d, 1e-6)) > 0.7
        green = phase < 5 if radial else 6 <= phase < 11
        if not green and junction["stop"] - 0.1 <= ahead < 40 and lateral < 5:
            budget = min(budget, max(0, ahead - junction["stop"]))
            r.velocity = budget
    for q in colony_layout(w.cfg)["roundabouts"]:
        dist = math.hypot(r.x - q["x"], r.y - q["y"])
        if 18 < dist < 30 and (dx * (q["x"] - r.x) + dy * (q["y"] - r.y)) > 0:
            for other in w.rovers + getattr(w, "traffic", []):
                if other is r:
                    continue
                if (
                    9 < math.hypot(other.x - q["x"], other.y - q["y"]) < 17
                    and math.hypot(other.x - r.x, other.y - r.y) < 25
                ):
                    budget = min(budget, max(0, dist - 22))
                    r.velocity = budget
                    break
    travelled = 0.0
    while budget > 1e-9 and r.route:
        tx, ty = r.route[0]
        dx, dy = tx - r.x, ty - r.y
        d = math.hypot(dx, dy)
        if d > 1e-8:
            r.heading = math.atan2(dy, dx)
        step = min(d, budget)
        if d <= budget:
            r.x, r.y = tx, ty
            r.route.pop(0)
        else:
            r.x += dx / d * step
            r.y += dy / d * step
        budget -= step
        travelled += step
    r.odometer_m = getattr(r, "odometer_m", 0) + travelled
    r.fuel_l = max(0, r.fuel_l - travelled * 0.00045 * (1 + grade * 6))
    if not r.route:
        r.velocity = 0
        gx, gy = polar(*w.cfg["garage"])
        if math.hypot(r.x - gx, r.y - gy) < 40:
            r.fuel_l = 120.0
    return not r.route


def roads_step(w: World):
    from hadleys.domains.incidents import _repair_rover

    c = w.cfg
    S = w.S
    wear = 0.0004 + (0.001 if w.road_icy and not w.road_heating_on else 0.0)
    w.road_integrity = np.maximum(0.0, w.road_integrity - wear)
    for s in range(S):
        if w.road_integrity[s] < 20:
            w.open_issue(
                "road_blocked",
                f"road:{s}",
                s,
                "wear",
                "road",
                polar(s * 60 + 30, c["ring_road_radius"]),
            )
    # gates: gate g sits at boundary g*60; sector s locks gates s and s+1
    for s in range(S):
        if w.lockdown_ticks[s] > 0:
            w.lockdown_ticks[s] -= 1
            if w.lockdown_ticks[s] == 0:
                w.log("INFO", f"Sector {s + 1} lockdown lifted")
    for g in range(S):
        locked = w.lockdown_ticks[g] > 0 or w.lockdown_ticks[(g - 1) % S] > 0
        if locked:
            w.gate_state[g] = "LOCKDOWN"
        elif not w.gate_ok[g]:
            w.gate_state[g] = "CLOSED"
        elif not (w.sector_online[g] or w.ups_state[g] not in ("DEPLETED", "FAULT")):
            pass  # unpowered: keeps its last state
        else:
            w.gate_state[g] = "OPEN"
        want = 1.0 if w.gate_state[g] == "OPEN" else 0.0
        w.gate_open_frac[g] += clamp(want - w.gate_open_frac[g], -0.25, 0.25)
    residents = np.bincount(w.h_sector, weights=w.h_residents, minlength=S)
    w.waste_level = np.minimum(
        1.2, w.waste_level + residents * c["waste_per_resident_per_tick"]
    )
    overflow = w.waste_level >= 1.0
    sewage_bad = (~w.h_aeration_ok) | (w.h_sludge >= 1.0)
    sew_bad_frac = (
        np.bincount(w.h_sector, weights=sewage_bad.astype(float), minlength=S)
        / c["houses_per_sector"]
    )
    w.sanitary = np.clip(
        w.sanitary - overflow * 0.05 - sew_bad_frac * 0.1 + (~overflow) * 0.02, 0, 100
    )
    garbage, sludge = w.rovers[0], w.rovers[1]
    _garbage_rover(w, garbage)
    _sludge_rover(w, sludge)
    for r in w.rovers[2:]:
        _repair_rover(w, r)
    traffic_step(w)


def _go_home(w: World, r: Rover):
    """Idle rovers park at the vehicle bay instead of standing in the street."""
    ga, gr = w.cfg["garage"]
    gx, gy = polar(ga, gr)
    if math.hypot(r.x - gx, r.y - gy) > 40 and r.wait <= 0:
        if plan_route(w, r, {"kind": "garage"}):
            r.state = TransportState.TO_GARAGE
        else:
            r.wait = 30


def _garbage_rover(w: World, r: Rover):
    c = w.cfg
    if r.state == TransportState.TO_GARAGE:
        if rover_move(w, r):
            r.state = TransportState.IDLE
        return
    if r.state == TransportState.IDLE:
        need = np.flatnonzero(w.waste_level >= 0.9)
        if not len(need):
            _go_home(w, r)
        if len(need):
            s = int(need[np.argmax(w.waste_level[need])])
            if plan_route(w, r, {"kind": "bin", "s": s}):
                r.job = s
                r.state = TransportState.TO_BIN
            else:
                r.wait = 20
    elif r.state == TransportState.TO_BIN:
        if rover_move(w, r):
            r.state = TransportState.LOADING
            r.timer = 10
    elif r.state == TransportState.LOADING:
        r.timer -= 1
        if r.timer <= 0:
            s = r.job
            take = min(1.0 - r.load, float(w.waste_level[s]))
            w.waste_level[s] -= take
            r.load += take
            if finance_pay(
                w,
                "waste_trip",
                s,
                "normal_operation",
                f"waste collection sector {s + 1}",
            ):
                w.log("INFO", f"Garbage rover emptied sector {s + 1} bin")
            else:
                w.log("WARN", f"Sector {s + 1} could not pay for waste collection")
            if r.load >= 0.99 or not np.any(w.waste_level >= 0.9):
                if plan_route(
                    w,
                    r,
                    {"kind": "outside", "x": c["waste_station_pos"][0] + 40, "y": 20.0},
                ):
                    r.state = TransportState.TO_STATION
                else:
                    r.state = TransportState.WAIT_GATE
                    r.wait = 30
            else:
                r.state = TransportState.IDLE
    elif r.state == TransportState.WAIT_GATE:
        if plan_route(
            w, r, {"kind": "outside", "x": c["waste_station_pos"][0] + 40, "y": 20.0}
        ):
            r.state = TransportState.TO_STATION
        else:
            r.wait = 30
    elif r.state == TransportState.TO_STATION:
        if rover_move(w, r):
            r.state = TransportState.UNLOADING
            r.timer = 15
    elif r.state == TransportState.UNLOADING:
        r.timer -= 1
        if r.timer <= 0:
            w.waste_station_level += r.load
            r.load = 0.0
            if plan_route(w, r, {"kind": "ring", "a": 195.0}):
                r.state = TransportState.RETURN
            else:
                r.wait = 30
    elif r.state == TransportState.RETURN:
        if rover_move(w, r):
            r.state = TransportState.IDLE


def _sludge_rover(w: World, r: Rover):
    c = w.cfg
    if r.state == TransportState.TO_GARAGE:
        if rover_move(w, r):
            r.state = TransportState.IDLE
        return
    if r.state == TransportState.IDLE:
        full = np.flatnonzero(w.h_sludge >= 0.95)
        if not len(full) and r.load <= 0.5:
            _go_home(w, r)
        if len(full) and r.load < 0.99:
            i = int(full[0])
            if plan_route(w, r, {"kind": "house", "i": i}):
                r.job = i
                r.state = TransportState.TO_HOUSE
            else:
                r.wait = 20
        elif r.load > 0.5:
            s = int(np.argmin(w.sludge_store))
            if plan_route(w, r, {"kind": "bin", "s": s}):
                r.job = s
                r.state = TransportState.TO_STORE
            else:
                r.wait = 20
    elif r.state == TransportState.TO_HOUSE:
        if rover_move(w, r):
            r.state = TransportState.PUMPING
            r.timer = 8
    elif r.state == TransportState.PUMPING:
        r.timer -= 1
        if r.timer <= 0:
            i = r.job
            r.load = min(1.0, r.load + float(w.h_sludge[i]) * 0.25)
            w.h_sludge[i] = 0.05
            finance_pay(
                w,
                "sludge_trip",
                int(w.h_sector[i]),
                "normal_operation",
                f"sludge collection house {i + 1}",
            )
            r.state = TransportState.IDLE
    elif r.state == TransportState.TO_STORE:
        if rover_move(w, r):
            s = r.job
            w.sludge_store[s] = min(1.0, w.sludge_store[s] + r.load * 0.2)
            r.load = 0.0
            r.state = TransportState.IDLE
    w.sludge_store = np.maximum(0.0, w.sludge_store - 0.00005)
