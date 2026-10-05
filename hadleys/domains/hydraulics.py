"""domains / hydraulics: colony simulation components."""

from __future__ import annotations

import math
import numpy as np
from hadleys.geometry.terrain import site_elevation
from hadleys.numerics import polar


class UtilityNetwork:
    """Rooted, isolatable district mains. Every service has one traced supply path.

    A tree is intentional: sector isolation cannot secretly backfeed through a
    decorative ring. Nodes/links are also the authoritative drawing coordinates.
    Sanitary and storm gravity networks run in separate corridors and outfalls.
    """

    VERSION = 4

    def __init__(self, w):
        self.version = self.VERSION
        c = w.cfg
        self.nodes, self.links = [], []
        self.house_nodes = np.zeros(w.N, dtype=int)

        def node(xy, kind, sector=-1, house=-1, height=3.6):
            x, y = map(float, xy)
            n = len(self.nodes)
            self.nodes.append(
                dict(
                    id=n,
                    x=x,
                    y=y,
                    z=site_elevation(x, y, c) + height,
                    kind=kind,
                    sector=int(sector),
                    house=int(house),
                )
            )
            return n

        def link(a, b, diameter, kind, points=None):
            na, nb = self.nodes[a], self.nodes[b]
            pts = points or [[na["x"], na["y"]], [nb["x"], nb["y"]]]
            xyz = [[float(x), float(y), site_elevation(x, y, c) + 3.6] for x, y in pts]
            xyz[0] = [na["x"], na["y"], na["z"]]
            xyz[-1] = [nb["x"], nb["y"], nb["z"]]
            if kind in ("main", "district", "header"):
                # Keep this route above vehicle clearance; node endpoints are shared.
                for v in xyz[1:-1]:
                    v[2] = site_elevation(v[0], v[1], c) + 7.2
            length = sum(math.dist(p, q) for p, q in zip(xyz, xyz[1:]))
            self.links.append(
                dict(
                    id=len(self.links),
                    a=a,
                    b=b,
                    diameter_m=diameter,
                    length_m=length,
                    roughness_m=0.000007 if diameter < 0.1 else 0.000045,
                    material="PE100 SDR11" if diameter < 0.1 else "lined ductile iron",
                    insulation_mm=60,
                    minor_k=2.5 if kind == "service" else 1.2,
                    kind=kind,
                    sector=nb["sector"],
                    points=xyz,
                )
            )

        root = node((-70, -45), "tank", height=24)
        pump = node((-40, -40), "pump")
        link(root, pump, 0.25, "pump")
        # A common header goes round the outside of the civic campus. Branch
        # spines sit 12 m to the side of the road centre, beyond its sidewalk.
        headers = [None] * w.S
        rr = c["hub_radius"] + 48
        start_angle = math.degrees(math.atan2(12, c["hub_radius"] + 28))
        # Feed the west-side tee directly, then split clockwise/counterclockwise.
        # Open horseshoe: no perimeter loop, no rectangular detour across the core.
        for sector in [3, 4, 5, 0, 2, 1]:
            angle = sector * 60 + start_angle
            header = node(polar(angle, rr), "header", height=7.2)
            if sector == 3:
                na = self.nodes[pump]
                nb = self.nodes[header]
                link(
                    pump,
                    header,
                    0.22,
                    "header",
                    [(na["x"], na["y"]), (-40, -24), (-148, -24), (nb["x"], nb["y"])],
                )
            else:
                parent = {4: 3, 5: 4, 0: 5, 2: 3, 1: 2}[sector]
                a0 = parent * 60 + start_angle
                a1 = angle + (360 if sector == 0 else 0)
                link(
                    headers[parent],
                    header,
                    0.20,
                    "header",
                    [polar(v, rr) for v in np.linspace(a0, a1, 25)],
                )
            headers[sector] = header
        for sector in range(w.S):
            angle = sector * 60.0
            rad = math.radians(angle)

            def shoulder(r):
                return (
                    r * math.cos(rad) - 12 * math.sin(rad),
                    r * math.sin(rad) + 12 * math.cos(rad),
                )

            prev = node(shoulder(c["hub_radius"] + 56), "isolation", sector, height=7.2)
            link(headers[sector], prev, 0.15, "district")
            for row in range(c["house_rows"]):
                r = c["house_radius_min"] - 18 + row * c["house_ring_step"]
                junction = node(shoulder(r), "tee", sector, height=7.2)
                link(prev, junction, 0.125, "main")
                prev = junction
                last = junction
                previous_angle = angle + math.degrees(math.atan2(12, r))
                for i in np.flatnonzero((w.h_sector == sector) & (w.h_ring == row)):
                    end_angle = float(w.h_angle[i])
                    tap = node(polar(end_angle, r), "tee", sector)
                    pts = [
                        polar(v, r)
                        for v in np.linspace(
                            previous_angle,
                            end_angle,
                            max(3, int((end_angle - previous_angle) / 0.8) + 1),
                        )
                    ]
                    link(last, tap, 0.08, "row", pts)
                    # The last point is the exact common service inlet, under the wet core.
                    service = node(
                        polar(end_angle, float(w.h_radius[i]) - 6),
                        "meter",
                        sector,
                        int(i),
                        0.9,
                    )
                    link(tap, service, 0.025, "service")
                    self.house_nodes[i] = service
                    last, previous_angle = tap, end_angle
        self.a = np.array([e["a"] for e in self.links])
        self.b = np.array([e["b"] for e in self.links])
        self.length = np.array([e["length_m"] for e in self.links])
        self.diameter = np.array([e["diameter_m"] for e in self.links])
        self.roughness = np.array([e["roughness_m"] for e in self.links])
        self.minor = np.array([e["minor_k"] for e in self.links])
        self.z = np.array([n["z"] for n in self.nodes])
        self.parent_edge = np.full(len(self.nodes), -1, dtype=int)
        self.parent_edge[self.b] = np.arange(len(self.links))
        depth = np.zeros(len(self.nodes), dtype=int)
        for a, b in zip(self.a, self.b):
            depth[b] = depth[a] + 1
        self.levels = [
            np.flatnonzero(depth[self.b] == d) for d in range(1, int(depth.max()) + 1)
        ]
        self._prepare()
        self.head = self.z.copy()
        self.flow = np.zeros(len(self.links))
        self.velocity = self.flow.copy()
        self.loss = self.flow.copy()
        self.pressure = np.zeros(w.N)
        self.delivered = np.zeros(w.N)
        self.leaks = np.zeros(w.N)
        self.converged = True
        self.residual = 0.0
        self.iterations = 0
        self.pump_speed = 1.0
        self.sewer_storage = 0.0
        self.storm_storage = 0.0
        self.snow_m3 = 0.0
        self.sewer_out_m3 = self.storm_out_m3 = self.overflow_m3 = 0.0
        self.drainage = self._drainage(w)
        self.drain_rates = [np.zeros(len(self.links)), np.zeros(len(self.links))]

    def _drainage(self, w):
        """Separate foul/surface-water trees; inverts descend all the way to outfall.

        Deep collectors are required by the artificial terrace grades. Lift at the
        western treatment sump is explicit; no uphill gravity sewer is implied.
        """
        systems = []
        for name, offset, rough in [("sanitary", 2.3, 0.013), ("storm", -2.3, 0.015)]:
            nodes = []
            for n in self.nodes:
                a = math.atan2(n["y"], n["x"])
                nodes.append(
                    dict(
                        x=n["x"] - math.sin(a) * offset,
                        y=n["y"] + math.cos(a) * offset,
                        z=0.0,
                        kind=n["kind"],
                        house=n["house"],
                    )
                )
            # Accumulate rises first, then lower the whole network to maintain cover.
            distances = []
            for e in self.links:
                a, b = e["a"], e["b"]
                pa, pb = nodes[a], nodes[b]
                L = e["length_m"]
                slope = 0.02 if e["kind"] == "service" else 0.005
                nodes[b]["z"] = nodes[a]["z"] + L * slope
                distances.append((L, slope))
            datum = min(
                site_elevation(n["x"], n["y"], w.cfg) - 3.2 - n["z"] for n in nodes
            )
            for n in nodes:
                n["z"] += datum
            edges = []
            for e, (L, slope) in zip(self.links, distances):
                # A service is 110 mm; rows 250 mm; collectors 450/600 mm.
                d = (
                    0.11
                    if e["kind"] == "service"
                    else (
                        0.25
                        if e["kind"] == "row"
                        else (0.6 if name == "storm" else 0.45)
                    )
                )
                area = math.pi * d * d / 4
                capacity = area * (d / 4) ** (2 / 3) * math.sqrt(slope) / rough
                pts = []
                for k, p in enumerate(e["points"]):
                    f = k / (len(e["points"]) - 1)
                    a, b = nodes[e["a"]], nodes[e["b"]]
                    ang = math.atan2(p[1], p[0])
                    pts.append(
                        [
                            p[0] - math.sin(ang) * offset,
                            p[1] + math.cos(ang) * offset,
                            a["z"] + (b["z"] - a["z"]) * f,
                        ]
                    )
                pts[0] = [nodes[e["a"]][k] for k in ("x", "y", "z")]
                pts[-1] = [nodes[e["b"]][k] for k in ("x", "y", "z")]
                edges.append(
                    dict(
                        a=e["b"],
                        b=e["a"],
                        diameter_m=d,
                        slope=slope,
                        length_m=L,
                        material=(
                            "vitrified clay"
                            if name == "sanitary"
                            else "reinforced concrete"
                        ),
                        capacity_m3_s=capacity,
                        points=pts,
                    )
                )
            outlet = nodes[0]
            plant = w.cfg["water_plant_pos"]
            # These are pumped rising mains, shown separately from gravity links.
            rising = [
                [outlet[k] for k in ("x", "y", "z")],
                [plant[0] + 20, plant[1] - 12, site_elevation(*plant, w.cfg) - 2.5],
            ]
            systems.append(
                dict(
                    name=name,
                    nodes=nodes,
                    links=edges,
                    rising_main=rising,
                    outfall="western treatment / retention works",
                    manning_n=rough,
                )
            )
        return systems

    def _prepare(self):
        """Tree order and link constants used on every solver iteration (derived, not saved).

        Nodes are numbered in depth-first order from the root, so every subtree is one contiguous range
        [tin, tout) of that order. Then the flow of a link (the demand of its subtree) is a difference of two
        prefix sums, and the head of a node (the source minus the losses on its path) is a prefix sum of range
        updates: two numpy calls instead of one call per tree level, whatever the depth of the network.
        """
        self._lvl = [(self.a[ids], self.b[ids], ids) for ids in self.levels]
        self._pump_level = next(k for k, ids in enumerate(self.levels) if 0 in ids)
        self._area4 = math.pi * self.diameter**2
        self._rel_rough = self.roughness / (3.7 * self.diameter)
        n = len(self.nodes)
        children = [[] for _ in range(n)]
        has_parent = np.zeros(n, dtype=bool)
        for a, b in zip(self.a.tolist(), self.b.tolist()):
            children[a].append(b)
            has_parent[b] = True
        order, tin, tout = [], np.zeros(n, dtype=np.int64), np.zeros(n, dtype=np.int64)
        for root in np.flatnonzero(~has_parent).tolist():
            stack = [(root, False)]
            while stack:
                node, done = stack.pop()
                if done:
                    tout[node] = len(order)
                    continue
                tin[node] = len(order)
                order.append(node)
                stack.append((node, True))
                stack.extend((c, False) for c in reversed(children[node]))
        self._order = np.array(order, dtype=np.int64)
        self._tin_b = tin[self.b]
        self._tout_b = tout[self.b]
        self._pump_range = (int(tin[1]), int(tout[1]))

    def __setstate__(self, d):
        self.__dict__.update(d)
        self._prepare()

    def __getstate__(self):
        derived = ("_lvl", "_pump_level", "_area4", "_rel_rough", "_order", "_tin_b", "_tout_b", "_pump_range")
        return {k: v for k, v in self.__dict__.items() if k not in derived}

    def aggregate(self, demand):
        """Flow through every link: the total demand of the subtree below it."""
        prefix = np.concatenate(([0.0], np.cumsum(demand[self._order])))
        return prefix[self._tout_b] - prefix[self._tin_b]

    def heads(self, source, loss, pump_gain):
        """Head at every node: the source minus the losses on its path, plus the pump below node 1."""
        n = len(self.nodes)
        diff = np.zeros(n + 1)
        np.add.at(diff, self._tin_b, loss)
        np.subtract.at(diff, self._tout_b, loss)
        lo, hi = self._pump_range
        diff[lo] -= pump_gain
        diff[hi] += pump_gain
        head = np.empty(n)
        head[self._order] = source - np.cumsum(diff[:-1])
        return head

    def headloss(self, q):
        """Darcy-Weisbach; laminar f=64/Re; Swamee-Jain turbulent estimate."""
        v = 4 * np.abs(q) / self._area4
        re = v * self.diameter / 1.31e-6  # 10 C water
        safe = np.maximum(re, 1.0)
        f = 64 / safe
        # Swamee-Jain (a log10 and a power per link) only where the flow is past laminar: under 1 % of the links,
        # and for the others the blend is exactly 0, so the result is the same number.
        t = np.flatnonzero(re > 2300)
        if t.size:
            turbulent = 0.25 / np.log10(self._rel_rough[t] + 5.74 / safe[t] ** 0.9) ** 2
            blend = np.minimum((re[t] - 2300) / 1700, 1)
            f[t] = (1 - blend) * 64 / safe[t] + blend * turbulent
        return (f * self.length / self.diameter + self.minor) * v * v / (2 * 9.81)

    def solve(self, w, requested):
        dt = float(w.cfg["tick_seconds"])
        active = w.water_main_ok[w.h_sector] & w.h_valve_open
        intact = w.h_pipes_ok & ~w.h_burst
        active &= bool(w.pump_station_ok and w.water_tank_m3 > 0)
        requested = np.where(active & intact, requested, 0.0)
        leak_area = np.where(
            active & w.h_burst, math.pi * 0.0015**2, 0.0
        )  # 3 mm equivalent break
        node_load = np.zeros(len(self.nodes))
        # A house cut off from the supply has pressure 0 whatever happens; starting it there instead of at
        # 20 m saves the ~40 relaxation steps it needed to decay, which held every other house in the loop.
        p = np.where(active, np.maximum(self.pressure / 9.81, 20.0), 0.0)
        use = np.zeros(w.N)
        leak = use.copy()
        # Plain fixed-point steps converge in a handful of iterations (5-6 at 5040 houses, where the old damped
        # step needed 66). If an error ever grows, the rest of this solve falls back to the damped step.
        relax, last_error = 1.0, math.inf
        for iteration in range(200):
            use = requested * np.sqrt(np.clip(p / 15.0, 0, 1))
            leak = 0.62 * leak_area * np.sqrt(2 * 9.81 * np.maximum(p, 0))
            total = float((use + leak).sum())
            # Average partial-tick delivery when the tank runs dry, exact mass balance.
            factor = min(1.0, w.water_tank_m3 / max(total * dt, 1e-30))
            use *= factor
            leak *= factor
            node_load.fill(0)
            node_load[self.house_nodes] = use + leak
            q = self.aggregate(node_load)
            loss = self.headloss(q)
            source = self.z[0] + 6.12 * w.water_tank_m3 / w.cfg["water_tank_m3"]
            pump_gain = (
                max(0, 28 * self.pump_speed**2 - 20000 * q[0] ** 2)
                if w.pump_station_ok
                else 0.0
            )
            head = self.heads(source, loss, pump_gain)
            target = np.where(
                active,
                np.maximum(0, head[self.house_nodes] - self.z[self.house_nodes]),
                0,
            )
            error = float(np.max(np.abs(target - p)))
            if error < 1e-6:
                break
            if error > last_error:
                relax = 0.35
            last_error = error
            p = (1 - relax) * p + relax * target
        self.iterations = iteration + 1
        self.converged = error < 1e-5
        self.residual = error
        self.head = head
        self.flow = q
        self.loss = loss
        self.velocity = 4 * q / (math.pi * self.diameter**2)
        self.pressure = target * 9.81  # kPa, gauge
        self.delivered = use * dt
        self.leaks = leak * dt
        w.h_water_ok = (
            active
            & intact
            & (target >= 3.0)
            & (use >= requested * 0.95)
            & (factor > 0.95)
        )
        return self.delivered

    def geometry(self, w):
        c = w.cfg
        plant = c["water_plant_pos"]
        feed_xy = [
            [plant[0] + 30, plant[1] - 12],
            [plant[0] + 54, plant[1] - 12],
            [plant[0] + 54, 18],
            [-148, 18],
            [-148, -14],
            [-70, -14],
            [-70, -45],
        ]
        feed = []
        for a, b in zip(feed_xy, feed_xy[1:]):
            count = max(1, math.ceil(math.dist(a, b) / 12))
            for j in range(count):
                t = j / count
                x = a[0] + (b[0] - a[0]) * t
                y = a[1] + (b[1] - a[1]) * t
                feed.append([x, y, site_elevation(x, y, c) + 10.5])
        feed.append([-70, -45, site_elevation(-70, -45, c) + 10.5])
        feed.append([-70, -45, self.z[0] + 6.5])
        return dict(
            nodes=self.nodes,
            links=self.links,
            house_nodes=self.house_nodes.tolist(),
            drainage=self.drainage,
            plant_feed=feed,
            version=self.VERSION,
        )

    def state(self):
        return dict(
            pressure_kpa=np.round(self.pressure, 2).tolist(),
            flow_l_s=np.round(self.flow * 1000, 5).tolist(),
            velocity_m_s=np.round(self.velocity, 5).tolist(),
            headloss_m=np.round(self.loss, 6).tolist(),
            head_m=np.round(self.head, 4).tolist(),
            delivered_l=np.round(self.delivered * 1000, 4).tolist(),
            leak_l=np.round(self.leaks * 1000, 4).tolist(),
            converged=self.converged,
            residual_m=self.residual,
            iterations=self.iterations,
            sewer_storage_m3=round(self.sewer_storage, 5),
            storm_storage_m3=round(self.storm_storage, 5),
            snow_m3=round(self.snow_m3, 5),
            sewer_out_m3=round(self.sewer_out_m3, 5),
            storm_out_m3=round(self.storm_out_m3, 5),
            overflow_m3=round(self.overflow_m3, 5),
            drainage_l_s=[np.round(q * 1000, 5).tolist() for q in self.drain_rates],
        )


WATER_ACCOUNTS = (
    "ocean_raw",  # pumped from the ocean intake
    "brine",  # returned to the ocean by the plant
    "produced",  # clean water into the tank
    "delivered",  # through the house meters
    "leaked",  # out of burst house pipes, into the storm drains
    "tank_clamp",  # water the tank would have gone below zero by (must stay 0)
    "consumed",  # drunk, cooked, evaporated in the houses: does not reach the drains
    "to_sewer",  # down the house drains into the sanitary sewer
    "sewer_pumped",  # lifted from the sanitary sump to the western works
    "sewer_overflow",  # spilled from the sanitary sump when it is full
    "rain",  # liquid precipitation into the storm drains
    "snowfall",  # precipitation stored as snow
    "melt",  # snow melting into the storm drains
    "storm_pumped",
    "storm_overflow",
)


def water_accounts(w):
    """Cumulative volumes (m3) of every water flow, and the stocks they started from."""
    u = w.utilities
    acc = {k: 0.0 for k in WATER_ACCOUNTS}
    acc.update(
        tank0=float(w.water_tank_m3),
        sewer0=float(u.sewer_storage),
        storm0=float(u.storm_storage),
        snow0=float(u.snow_m3),
    )
    return acc


def water_balance(w):
    """Every stock change against its recorded inflows and outflows. Each residual must be 0 (to rounding):
    water neither appears nor vanishes without an accounted cause."""
    u, a = w.utilities, w.water_acc
    parts = {
        "plant": (a["ocean_raw"], a["produced"] + a["brine"], 0.0),
        "tank": (a["produced"] + a["tank_clamp"], a["delivered"] + a["leaked"], w.water_tank_m3 - a["tank0"]),
        "houses": (a["delivered"], a["consumed"] + a["to_sewer"], 0.0),
        "sanitary sewer": (a["to_sewer"], a["sewer_pumped"] + a["sewer_overflow"], u.sewer_storage - a["sewer0"]),
        "snow": (a["snowfall"], a["melt"], u.snow_m3 - a["snow0"]),
        "storm drains": (
            a["leaked"] + a["rain"] + a["melt"],
            a["storm_pumped"] + a["storm_overflow"],
            u.storm_storage - a["storm0"],
        ),
    }
    out = {}
    for name, (inflow, outflow, stock) in parts.items():
        out[name] = {
            "in": round(inflow, 6),
            "out": round(outflow, 6),
            "stock_change": round(stock, 6),
            "residual": inflow - outflow - stock,
        }
    return out


def hydraulic_step(w):
    if not hasattr(w, "utilities") or w.utilities.version != UtilityNetwork.VERSION:
        w.utilities = UtilityNetwork(w)
    u = w.utilities
    c = w.cfg
    acc = w.water_acc
    dt = float(c["tick_seconds"])
    hour = (w.t % 1440) / 60
    diurnal = 0.5 + 0.9 * max(0, math.sin(math.pi * (hour - 5) / 16))
    request = c["water_per_house_m3_day"] / 86400 * (1 + 0.5 * w.h_residents) * diurnal
    use = u.solve(w, request)
    w.h_water_m3 += use
    w.h_water_day += use
    w.h_water_month += use
    w.sector_water_m3 = np.bincount(w.h_sector, weights=use, minlength=w.S)
    w.water_flow_m3_h = float((use + u.leaks).sum()) / dt * 3600
    drawn = float((use + u.leaks).sum())
    if drawn > w.water_tank_m3:  # the solver scales delivery to the tank; any float excess is recorded
        acc["tank_clamp"] += drawn - w.water_tank_m3
    w.water_tank_m3 = max(0, w.water_tank_m3 - drawn)
    acc["delivered"] += float(use.sum())
    acc["leaked"] += float(u.leaks.sum())
    # Most of the delivered water returns to the separate foul sewer; the rest is consumed in the house.
    # Manning full-bore capacities bound each subtree. This is a lumped storage
    # approximation, not an unsteady free-surface/backwater solver.
    drained = use * c["sewer_return_frac"]
    acc["to_sewer"] += float(drained.sum())
    acc["consumed"] += float(use.sum()) - float(drained.sum())
    for system, attr, inflow in [
        (u.drainage[0], "sewer_storage", drained),
        (u.drainage[1], "storm_storage", u.leaks.copy()),
    ]:
        if attr == "storm_storage":
            # Water-equivalent precipitation accumulates as snow below freezing.
            rain = (
                (0.003 if w.storm_ticks > 0 else 0.0002) if w.precip != "none" else 0.0
            )
            volume = rain * (w.N * 350) * dt / 3600
            if w.t_out <= 0:
                u.snow_m3 += volume
                acc["snowfall"] += volume
                volume = 0.0
            melt = min(u.snow_m3, max(0, w.t_out) * 0.0001 * w.N * 350 * dt / 3600)
            u.snow_m3 -= melt
            acc["rain"] += volume
            acc["melt"] += melt
            inflow += (volume + melt) / w.N
        loads = np.zeros(len(u.nodes))
        loads[u.house_nodes] = inflow / dt
        rates = u.aggregate(loads)
        u.drain_rates[0 if attr == "sewer_storage" else 1] = rates
        ratios = [
            e["capacity_m3_s"] / q for e, q in zip(system["links"], rates) if q > 0
        ]
        ratio = min(1.0, min(ratios, default=1.0))
        amount = float(inflow.sum())
        queued = getattr(u, attr) + amount
        # Lift pumps run on the same protected supply as the potable station; the sanitary one can also
        # be switched off by the operator.
        sanitary = attr == "sewer_storage"
        running = w.pump_station_ok and (w.sewer_pump_on or not sanitary)
        capacity = (c["sewer_lift_m3_s"] if sanitary else c["storm_lift_m3_s"]) * dt if running else 0.0
        out = min(queued, capacity, max(0, amount * ratio) + max(0, capacity - amount))
        storage = queued - out
        cap = c["drain_storage_m3"]
        overflow = max(0, storage - cap)
        setattr(u, attr, min(storage, cap))
        u.overflow_m3 += overflow  # both networks together, as before
        if sanitary:
            u.sewer_out_m3 = out
            acc["sewer_pumped"] += out
            acc["sewer_overflow"] += overflow
            if (overflow > 0) != w.sewer_spilling:
                w.sewer_spilling = overflow > 0
                if overflow > 0:
                    w.log("ALARM", "Sanitary sewer sump full: sewage overflowing")
                else:
                    w.log("INFO", "Sanitary sewer no longer overflowing")
        else:
            u.storm_out_m3 = out
            acc["storm_pumped"] += out
            acc["storm_overflow"] += overflow
    w.h_sludge += np.where(
        w.h_water_ok, c["sludge_per_resident_per_tick"] * (1 + w.h_residents), 0
    )
    w.h_sludge = np.minimum(w.h_sludge, 1.0)
