"""geometry / roads: colony simulation components."""

from __future__ import annotations
from hadleys.enums import TransportKind
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import math
from hadleys.numerics import clamp, polar

_LAYOUT_CACHE = {}


def angle_diff(a, b):
    return (b - a + 180.0) % 360.0 - 180.0


def arc_waypoints(a0, a1, r, step=6.0):
    """Points along an arc from a0 to a1 (shortest way, unless |a1-a0| given explicitly > 180)."""
    d = a1 - a0
    n = max(1, int(abs(d) / step))
    return [polar(a0 + d * k / n, r) for k in range(1, n + 1)]


def ring_blocked(w: World, a0, a1, rover: Rover):
    """True if the ring road between a0 and a1 (in the direction of a1 - a0) crosses a broken segment."""
    if rover.kind == TransportKind.REPAIR:
        return False
    d = a1 - a0
    n = max(1, int(abs(d) / 5.0))
    for k in range(n):
        a = a0 + d * (k + 0.5) / n
        if w.road_integrity[int((a % 360.0) // 60.0)] < 20:
            return True
    return False


def ring_route(w: World, a0, a1, rover: Rover):
    """Arc along the ring road from a0 to a1, picking a direction that is not blocked. None if both are."""
    d = angle_diff(a0, a1)
    for dd in (d, d - 360.0 if d > 0 else d + 360.0):
        if not ring_blocked(w, a0, a0 + dd, rover):
            return arc_waypoints(a0, a0 + dd, w.cfg["ring_road_radius"])
    return None


def rover_polar(r: Rover):
    return math.degrees(math.atan2(r.y, r.x)) % 360.0, math.hypot(r.x, r.y)


def colony_layout(c):
    """One road/parcel plan shared by geometry, intersections and vehicle routes."""
    key = tuple(
        c[k] if not isinstance(c[k], (list, tuple)) else tuple(c[k])
        for k in (
            "wall_radius",
            "ring_road_radius",
            "house_radius_min",
            "house_ring_step",
            "reactor_pos",
            "water_plant_pos",
            "tower_pos",
            "dish_pos",
            "garage",
            "medlab",
            "school",
            "house_rows",
            "sectors",
            "solar_pos",
            "mine_pos",
            "radwaste_pos",
            "landing_pad_pos",
            "tower_junction",
            "waste_station_pos",
        )
    )
    if key in _LAYOUT_CACHE:
        return _LAYOUT_CACHE[key]
    roads = []
    rx, ry = c["reactor_pos"]
    wx, wy = c["water_plant_pos"]
    spine = rx + 220

    def road(name, points, width=10, walk=True):
        roads.append(
            dict(id=name, points=[list(p) for p in points], width=width, walk=walk)
        )

    def arc(a, b, r, step=2):
        return [
            polar(a + (b - a) * i / max(1, math.ceil(abs(b - a) / step)), r)
            for i in range(max(1, math.ceil(abs(b - a) / step)) + 1)
        ]

    for radius in (
        [118, 210]
        + [
            c["house_radius_min"] - 30 + k * c["house_ring_step"]
            for k in range(c["house_rows"] + 1)
        ]
        + [c["ring_road_radius"]]
    ):
        for sector in range(c["sectors"]):
            road(
                f"ring-{radius}-{sector}",
                arc(sector * 60, (sector + 1) * 60, radius),
                14 if radius == c["ring_road_radius"] else 12 if radius == 118 else 10,
            )
    for sector in range(c["sectors"]):
        road(
            "spoke-" + str(sector),
            [polar(sector * 60, 118), polar(sector * 60, c["wall_radius"] + 70)],
        )
    road("civic-cross", [(-118, 0), (118, 0)], 12)
    road("civic-north", [(0, 0), (0, 55)])
    for x in [-53, 53]:
        road("civic-south" + str(x), [(x, 0), (x, -math.sqrt(118**2 - x * x))], 9)
    for x in [-80, 80]:
        road("civic-parking" + str(x), [(x, 0), (x, -13)], 6, False)
    for name in ["garage", "medlab", "school"]:
        a, r = c[name]
        road(
            name + "-access",
            [polar(a, 210), polar(a, 224 if name != "garage" else 226)],
            8,
            False,
        )
    road("west-arterial", [(-c["wall_radius"] - 70, 0), (spine, 0)], 14)
    a, _ = c["garage"]
    road("garage-parking-access", [polar(a + 9.5, 210), polar(a + 9.5, 237)], 7, False)
    road(
        "east-arterial",
        [(c["wall_radius"] + 70, 0), (c["landing_pad_pos"][0] - 80, 0)],
        12,
    )
    road("industrial-spine", [(spine, -460), (spine, c["mine_pos"][1] + 100)], 16)
    road("reactor-east", [(rx + 90, -200), (rx + 90, 180)], 12)
    road("reactor-west", [(rx - 158, -200), (rx - 158, 180)], 10)
    road("reactor-north", [(rx - 158, -200), (spine, -200)], 12)
    road("reactor-south", [(rx - 158, 180), (spine, 180)], 12)
    road("reactor-gate", [(rx + 58, 0), (spine, 0)], 12)
    road("reactor-workshop-access", [(rx + 90, 84), (rx + 145, 84)], 8, False)
    road("reactor-parking-access", [(rx + 175, 52), (spine, 52)], 7, False)
    road("water-gate", [(wx + 38, wy), (spine, wy)], 12)
    road("water-east", [(wx + 80, wy - 40), (wx + 80, wy + 100)], 10)
    road("water-west", [(wx - 68, wy - 40), (wx - 68, wy + 100)], 10)
    # The north edge shares reactor-south; do not draw a second overlapping road.
    road("water-south", [(wx - 68, wy + 100), (wx + 80, wy + 100)], 10)
    road("water-parking-access", [(wx + 40, wy + 68), (wx + 80, wy + 68)], 6, False)
    for name in ["mine_pos", "radwaste_pos"]:
        x, y = c[name]
        road(name + "-access", [(spine, y), (x + 48, y)], 10)
    sx, sy = c["solar_pos"]
    road(
        "solar-access",
        [
            (spine, sy - 110),
            (sx + 136, sy - 110),
            (sx + 136, sy + 30),
            (sx + 108, sy + 30),
        ],
        10,
    )
    tx, ty = c["tower_pos"]
    dx, dy = c["dish_pos"]
    road(
        "mobile-link",
        [
            (c["tower_junction"][0], 0),
            (c["tower_junction"][0], ty + 40),
            (tx + 79, ty + 40),
            (tx + 79, ty),
            (tx + 72, ty),
        ],
        10,
    )
    road(
        "mobile-parking-access",
        [(tx + 72, ty), (tx + 58, ty), (tx + 58, ty - 11.5)],
        6,
        False,
    )
    road(
        "space-parking-access",
        [(dx + 72, dy), (dx + 58, dy), (dx + 58, dy - 11.5)],
        6,
        False,
    )
    road(
        "space-link",
        [
            (tx, ty + 92),
            (tx - 120, ty + 92),
            (tx - 120, dy + 105),
            (dx + 88, dy + 105),
            (dx + 88, dy),
            (dx + 72, dy),
        ],
        12,
    )
    x, y = c["waste_station_pos"]
    road("waste-access", [(x + 50, 0), (x + 50, y), (x + 29, y)], 9)
    roundabouts = [
        dict(
            x=polar(a, c["ring_road_radius"])[0],
            y=polar(a, c["ring_road_radius"])[1],
            radius=13,
            outer=17,
        )
        for a in [0, 180]
    ]
    # Locate every centreline crossing, including T junctions and driveway mouths.
    segments = [(r, a, b) for r in roads for a, b in zip(r["points"], r["points"][1:])]
    nodes = []

    def intersect(a, b, c, d):
        ux, uy = b[0] - a[0], b[1] - a[1]
        vx, vy = d[0] - c[0], d[1] - c[1]
        den = ux * vy - uy * vx
        if abs(den) < 1e-9:
            return None
        t = ((c[0] - a[0]) * vy - (c[1] - a[1]) * vx) / den
        u = ((c[0] - a[0]) * uy - (c[1] - a[1]) * ux) / den
        if -1e-7 <= t <= 1 + 1e-7 and -1e-7 <= u <= 1 + 1e-7:
            return (a[0] + ux * t, a[1] + uy * t)

    for i, (r, a, b) in enumerate(segments):
        for rr, aa, bb in segments[i + 1 :]:
            if r["id"] == rr["id"]:
                continue
            if (
                max(a[0], b[0]) < min(aa[0], bb[0]) - 0.01
                or max(aa[0], bb[0]) < min(a[0], b[0]) - 0.01
                or max(a[1], b[1]) < min(aa[1], bb[1]) - 0.01
                or max(aa[1], bb[1]) < min(a[1], b[1]) - 0.01
            ):
                continue
            p = intersect(a, b, aa, bb)
            if p is None:
                continue
            item = next((n for n in nodes if math.dist(p, (n["x"], n["y"])) < 2), None)
            if item is None:
                item = dict(x=p[0], y=p[1], arms=[], roads=set(), width=0)
                nodes.append(item)
            for path in [r, rr]:
                item["width"] = max(item["width"], path["width"])
                item["roads"].add(path["id"])
            for v in [a, b, aa, bb]:
                if math.dist(v, p) < 0.05:
                    continue
                angle = math.atan2(v[1] - p[1], v[0] - p[0])
                if not any(
                    abs(math.atan2(math.sin(angle - q), math.cos(angle - q))) < 0.12
                    for q in item["arms"]
                ):
                    item["arms"].append(angle)
    junctions = []
    for n in nodes:
        if len(n["arms"]) < 3:
            continue
        n["roads"] = sorted(n["roads"])
        n["arms"].sort()
        n["angle"] = math.degrees(n["arms"][0])
        n["sector"] = -1
        n["row"] = len(junctions)
        n["offset"] = len(junctions) * 3 % 12
        for name in n["roads"]:
            if name.startswith("spoke-"):
                n["sector"] = int(name.split("-")[-1])
                n["angle"] = n["sector"] * 60
                break
        n["mode"] = (
            "roundabout"
            if any(
                math.hypot(n["x"] - q["x"], n["y"] - q["y"]) < 3 for q in roundabouts
            )
            else "signals"
        )
        n["stop"] = 18.0
        junctions.append(n)
    distribution = []
    for sec in range(c["sectors"]):
        distribution.append(
            {
                key: polar(sec * 60 + angle, r)
                for key, angle, r in [
                    ("pole", 10, 169),
                    ("rp", 12, 174),
                    ("cab", 19, 174),
                    ("ups", 26, 174),
                ]
            }
        )
    out = dict(
        roads=roads,
        junctions=junctions,
        roundabouts=roundabouts,
        distribution=distribution,
        industrial_spine=spine,
    )
    _LAYOUT_CACHE[key] = out
    return out


def traffic_junctions(c):
    return colony_layout(c)["junctions"]


def signal_phase(t, j):
    phase = (t + j["offset"]) % 12
    return phase


def exterior_route(c, x, y):
    """Routes follow the same paved service roads exported to the renderer."""
    gate = (-c["wall_radius"] - 30, 0.0)
    spine = colony_layout(c)["industrial_spine"]
    rx, ry = c["reactor_pos"]
    wx, wy = c["water_plant_pos"]
    sx, sy = c["solar_pos"]
    tx, ty = c["tower_pos"]
    dx, dy = c["dish_pos"]
    junction = (c["tower_junction"][0], 0.0)
    if min(math.hypot(x - rx, y - ry), math.hypot(x - rx - 58, y)) < 1:
        return [gate, (spine, 0), (rx + 58, 0)]
    if min(math.hypot(x - wx, y - wy), math.hypot(x - wx - 38, y - wy)) < 1:
        return [gate, (spine, 0), (spine, wy), (wx + 38, wy)]
    vx, vy = c["waste_station_pos"]
    if min(math.hypot(x - vx, y - vy), math.hypot(x - vx - 29, y - vy)) < 1:
        return [gate, (vx + 50, 0), (vx + 50, vy), (vx + 29, vy)]
    if min(math.hypot(x - sx, y - sy), math.hypot(x - sx - 108, y - sy - 30)) < 1:
        return [
            gate,
            (spine, 0),
            (spine, sy - 110),
            (sx + 136, sy - 110),
            (sx + 136, sy + 30),
            (sx + 108, sy + 30),
        ]
    for key in ["mine_pos", "radwaste_pos"]:
        px, py = c[key]
        if min(math.hypot(x - px, y - py), math.hypot(x - px - 48, y - py)) < 1:
            return [gate, (spine, 0), (spine, py), (px + 48, py)]
    if min(math.hypot(x - tx, y - ty), math.hypot(x - tx - 72, y - ty)) < 1:
        return [
            gate,
            junction,
            (junction[0], ty + 40),
            (tx + 79, ty + 40),
            (tx + 79, ty),
            (tx + 72, ty),
        ]
    if min(math.hypot(x - dx, y - dy), math.hypot(x - dx - 72, y - dy)) < 1:
        return [
            gate,
            junction,
            (tx, ty + 92),
            (tx - 120, ty + 92),
            (tx - 120, dy + 105),
            (dx + 88, dy + 105),
            (dx + 88, dy),
            (dx + 72, dy),
        ]
    if abs(y) < 20 and x >= spine:
        return [gate, (x, 0), (x, y)]
    if y < -100 and x > spine:
        return [gate, junction, (junction[0], y), (x, y)]
    if x > spine and y > 30:
        return [gate, (x, 0), (x, y)]
    return [gate, (spine, 0), (spine, y), (x, y)]


def roundabout_route(start, route, c):
    """Replace paths through traffic islands with a continuous CCW circulating arc."""
    points = [start] + list(route)
    for q in colony_layout(c)["roundabouts"]:
        cx, cy = q["x"], q["y"]
        radius = q["radius"]
        out = [points[0]]
        entry = None
        for a, b in zip(points, points[1:]):
            ux, uy = b[0] - a[0], b[1] - a[1]
            ax, ay = a[0] - cx, a[1] - cy
            A = ux * ux + uy * uy
            B = 2 * (ax * ux + ay * uy)
            C = ax * ax + ay * ay - radius * radius
            disc = B * B - 4 * A * C
            cuts = []
            if A > 1e-12 and disc >= 0:
                for t in [
                    (-B - math.sqrt(disc)) / (2 * A),
                    (-B + math.sqrt(disc)) / (2 * A),
                ]:
                    if 1e-8 < t < 1 - 1e-8:
                        cuts.append((a[0] + t * ux, a[1] + t * uy))
            vertices = [a] + cuts + [b]
            for u, v in zip(vertices, vertices[1:]):
                inside = (
                    math.hypot((u[0] + v[0]) / 2 - cx, (u[1] + v[1]) / 2 - cy)
                    < radius - 1e-5
                )
                if inside:
                    if entry is None:
                        entry = u
                else:
                    if entry is not None:
                        aa = math.atan2(entry[1] - cy, entry[0] - cx)
                        bb = math.atan2(u[1] - cy, u[0] - cx)
                        sweep = (bb - aa) % (2 * math.pi)
                        # Tiny chords of an existing circular route already clear the island.
                        if sweep < 0.08:
                            out.append(u)
                        else:
                            n = max(2, math.ceil(sweep / 0.07))
                            out.extend(
                                (
                                    cx + radius * math.cos(aa + sweep * j / n),
                                    cy + radius * math.sin(aa + sweep * j / n),
                                )
                                for j in range(n + 1)
                            )
                        entry = None
                    if math.dist(out[-1], v) > 1e-7:
                        out.append(v)
        if entry is not None:
            out.append(points[-1])
        points = out
    return points[1:]


def plan_route(w: World, r: Rover, target):
    """Build a road route from the rover to a target, expressed as a dict:
    {"kind": "house", "i": idx} | {"kind": "bin", "s": sector} | {"kind": "outside", "x":, "y":}
    | {"kind": "hub", "s": sector} | {"kind": "ring", "a": angle}. Returns False if blocked right now.
    """
    c = w.cfg
    R = c["ring_road_radius"]
    a, rr = rover_polar(r)
    route = []
    # 1. get to the ring road first, along the nearest boundary street or the outside road
    if rr > R + 10:  # outside the wall: come back along the west road
        route += list(reversed(exterior_route(c, r.x, r.y)))
        gate = 3
        if w.gate_state[gate] != "OPEN":
            return False
        route += [polar(180.0, R)]
        a = 180.0
    elif rr < R - 10:  # inside: along the row street to the boundary street, then out
        s = int(a // 60.0)
        ba = s * 60.0
        street_r = (
            c["house_radius_min"]
            - 30
            + round((rr - (c["house_radius_min"] - 30)) / c["house_ring_step"])
            * c["house_ring_step"]
        )
        street_r = clamp(street_r, c["hub_radius"] + 20, R)
        if abs(rr - street_r) > 5 or rr < c["hub_radius"] + 30:
            street_r = max(street_r, c["hub_radius"] + 30)
        route += arc_waypoints(a, ba, street_r, 4.0)
        route += [polar(ba, R)]
        a = ba
    kind = target["kind"]
    if kind == "ring":
        arc = ring_route(w, a, target["a"], r)
        if arc is None:
            return False
        route += arc
    elif kind == "bin":
        arc = ring_route(w, a, target["s"] * 60.0 + 30.0, r)
        if arc is None:
            return False
        route += arc + [polar(target["s"] * 60.0 + 30.0, R + 22)]
    elif kind == "house":
        i = target["i"]
        s = int(w.h_sector[i])
        ba = s * 60.0
        arc = ring_route(w, a, ba, r)
        if arc is None:
            return False
        street_r = float(w.h_radius[i]) - 30.0
        route += (
            arc
            + [polar(ba, street_r)]
            + arc_waypoints(ba, float(w.h_angle[i]), street_r, 4.0)
        )
    elif kind == "hub":
        ba = target["s"] * 60.0
        arc = ring_route(w, a, ba, r)
        if arc is None:
            return False
        route += arc + [polar(ba, c["hub_radius"] + 30)]
    elif kind == "garage":
        ga, gr = c["garage"]
        ba = 60.0
        arc = ring_route(w, a, ba, r)
        if arc is None:
            return False
        route += (
            arc + [polar(ba, 210)] + arc_waypoints(ba, ga, 210, 2.0) + [polar(ga, 224)]
        )
    elif kind == "outside":
        arc = ring_route(w, a, 180.0, r)
        if arc is None:
            return False
        if w.gate_state[3] != "OPEN":
            return False
        route += arc + exterior_route(c, target["x"], target["y"])
    r.route = roundabout_route((r.x, r.y), route, c)
    return True
