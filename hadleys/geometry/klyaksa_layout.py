"""Deterministic, read-only 3-D presentation plan for Klyaksa.

The simulation's saved polar coordinates and route logic are deliberately untouched.
House index i in this plan always denotes the same domain house i.  Road nodes,
frontages and reserved parcels are shared by buildings, utility networks and traffic.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict


def river_centre(x):
    return 12.0 * math.sin(x / 300.0)


# ---------------- Meridian: a canal city on its river (London's river, Amsterdam's canal belt) ----------------
EMB = 62.0          # embankment roads run this far from the river's centre line
CANAL_R, CANAL_HW = 330.0, 9.0
BASIN = (-175.0, -305.0, 175.0, -38.0)   # the port basin cut into the south bank: x0, y0, x1, y1 (open to the river)
PORT = (-262.0, -432.0, 262.0)           # the port's ring road: west x, south y, east x
RIVER_BRIDGES = [  # id, kind, x on the north bank, x on the south bank: angled, never square to the river
    ("cable-west", "cable", -640.0, -695.0), ("cable-port", "cable", -470.0, -425.0),
    ("bascule-port", "bascule", 420.0, 395.0), ("bascule-mouth", "bascule", 610.0, 640.0),
]


def _ring_r(base, t, k, canal=None):
    return base + (18.0 * math.sin(3 * t) if canal else 9.0 * math.sin(2 * t + k))


def canal_line():
    """The canal (Fontanka): a half ring round the north bank's square, joined to the river at both ends."""
    arc = [(_ring_r(CANAL_R, math.pi * k / 72, 0, True) * math.cos(math.pi * k / 72),
            EMB + _ring_r(CANAL_R, math.pi * k / 72, 0, True) * math.sin(math.pi * k / 72)) for k in range(73)]
    return [(arc[0][0], river_centre(arc[0][0]))] + arc + [(arc[-1][0], river_centre(arc[-1][0]))]


def meridian_wet(x, y, margin=0.0):
    if abs(y - river_centre(x)) < 40 + margin:
        return True
    x0, y0, x1, y1 = BASIN
    if x0 - margin < x < x1 + margin and y0 - margin < y < y1 + margin:
        return True
    line = canal_line()
    return any(_segment_distance(x, y, a, b)[0] < CANAL_HW + margin for a, b in zip(line, line[1:]))


def meridian_network(R, add_road, nodes, node_by_id):
    """Nodes and roads of Meridian; returns the quads (block centres) and the waterways for the 3D view."""
    made = []

    def _road(*a, **k):
        r = add_road(*a, **k)
        made.append(r)
        return r

    def crosses(p, q):
        """Would a straight street from p to q cut through one already laid (other than at its ends)?"""
        for r in made:
            for a, b in zip(r['points'], r['points'][1:]):
                d1x, d1y, d2x, d2y = q[0] - p[0], q[1] - p[1], b[0] - a[0], b[1] - a[1]
                den = d1x * d2y - d1y * d2x
                if abs(den) < 1e-9:
                    continue
                t = ((a[0] - p[0]) * d2y - (a[1] - p[1]) * d2x) / den
                u = ((a[0] - p[0]) * d1y - (a[1] - p[1]) * d1x) / den
                if 0.02 < t < 0.98 and 0.0 < u < 1.0:
                    return True
        return False
    def node(ident, x, y):
        n = {'id': ident, 'x': round(x, 3), 'y': round(y, 3)}
        nodes.append(n)
        node_by_id[ident] = n
        return ident

    def arc(cx, cy, base, k, t0, t1, canal=False):
        steps = max(2, int(abs(t1 - t0) * base / 6))
        return [(cx + _ring_r(base, t0 + (t1 - t0) * i / steps, k, canal) * math.cos(t0 + (t1 - t0) * i / steps),
                 cy + _ring_r(base, t0 + (t1 - t0) * i / steps, k, canal) * math.sin(t0 + (t1 - t0) * i / steps)) for i in range(steps + 1)]

    def line(a, b):
        n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 6))
        return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]

    def bank(x0, x1, side):
        n = max(2, int(abs(x1 - x0) / 6))
        return [(x0 + (x1 - x0) * i / n, river_centre(x0 + (x1 - x0) * i / n) + side * EMB) for i in range(n + 1)]

    inside = lambda x, y: math.hypot(x, y) < R - 100   # inside the wall boulevard, so nothing crosses it
    x0, y0, x1, y1 = BASIN
    in_port = lambda x, y: PORT[0] - 18 < x < PORT[2] + 18 and PORT[1] - 18 < y < y1 + 8
    quads, embank = [], {1: {}, -1: {}}

    def bank_node(side, x):
        x = round(x, 1)
        if x not in embank[side]:
            embank[side][x] = node(f'emb{"n" if side > 0 else "s"}{x:+.0f}', x, river_centre(x) + side * EMB)
        return embank[side][x]

    for side, rings, cy in ((1, [100, 170, 240, CANAL_R - CANAL_HW - 12, CANAL_R + CANAL_HW + 12, 420, 490, 560, 630], EMB),
                            (-1, [130, 200, 270, 340, 410, 480, 550, 620], -EMB)):
        S = 18
        t_of = lambda j, k: (math.pi * (j + 0.5) / S + 0.05 * math.sin(j * 2.3) + 0.06 * math.sin(k * 1.3 + j)) * side
        canal_rings = (3, 4) if side > 0 else ()
        grid = {}
        for k, base in enumerate(rings):
            for j in range(S):
                t = t_of(j, k)
                r = _ring_r(base, abs(t), k, k in canal_rings)
                x, y = r * math.cos(t), cy + r * math.sin(t)
                if inside(x, y) and not (side < 0 and in_port(x, y)) and not meridian_wet(x, y, 6):
                    grid[k, j] = node(f'm{"n" if side > 0 else "s"}{k}_{j}', x, y)
        for (k, j), a in grid.items():
            b = grid.get((k, j + 1))
            if b:   # ring arc
                pts = arc(0, cy, rings[k], k, abs(t_of(j, k)), abs(t_of(j + 1, k)), k in canal_rings)
                pts = [(x, y * side if side < 0 else y) for x, y in pts] if side > 0 else [(x, cy - (y - cy)) for x, y in pts]
                if not any(in_port(x, y) for x, y in pts) and all(inside(x, y) for x, y in pts):
                    pts[0], pts[-1] = (node_by_id[a]['x'], node_by_id[a]['y']), (node_by_id[b]['x'], node_by_id[b]['y'])
                    _road(f'ring-{a}-{b}', a, b, pts, 15 if k in (2, 6) else 11, 'avenue' if k in (2, 6) else 'street')
            inner = k + 1 < (4 if side > 0 else 3)   # fewer radial streets near the square: bigger inner blocks
            c = grid.get((k + 1, j)) if not (inner and j % 2) else None
            if c:   # spoke
                road = _road(f'spoke-{a}-{c}', a, c, line((node_by_id[a]['x'], node_by_id[a]['y']), (node_by_id[c]['x'], node_by_id[c]['y'])),
                                15 if j % 4 == 1 else 11, 'avenue' if j % 4 == 1 else 'street')
                if k in canal_rings and k + 1 in canal_rings:
                    road['canal_bridge'] = True
            step = 2 if inner else 1
            if (not inner or j % 2 == 0) and all(q in grid for q in ((k + 1, j), (k, j + step), (k + 1, j + step))) and not (k in canal_rings and k + 1 in canal_rings):
                qs = [node_by_id[grid[q]] for q in ((k, j), (k + 1, j), (k, j + step), (k + 1, j + step))]
                quads.append((sum(q['x'] for q in qs) / 4, sum(q['y'] for q in qs) / 4))
        # ring ends come down to the embankment
        for k, base in enumerate(rings):
            for j, t_end in ((0, 0.0), (S - 1, math.pi)):
                a = grid.get((k, j))
                if not a:
                    continue
                r = _ring_r(base, t_end, k, k in canal_rings)
                x = r * math.cos(t_end)
                if side < 0 and PORT[0] - 10 < x < PORT[2] + 10:
                    continue
                e = bank_node(side, x)
                road = _road(f'end-{a}-{e}', a, e, line((node_by_id[a]['x'], node_by_id[a]['y']), (node_by_id[e]['x'], node_by_id[e]['y'])), 11, 'street')
    # the north bank's square, where the inner spokes meet the embankment
    plaza = bank_node(1, 0.0)
    for j in (8, 9):
        if f'mn0_{j}' in node_by_id:
            _road(f'plaza-{j}', plaza, f'mn0_{j}', line((0.0, river_centre(0) + EMB), (node_by_id[f'mn0_{j}']['x'], node_by_id[f'mn0_{j}']['y'])), 15, 'avenue')
    # river bridges: angled crossings between the embankments
    bridges = []
    for ident, kind, xn, xs in RIVER_BRIDGES:
        a, b = bank_node(1, xn), bank_node(-1, xs)
        road = _road(f'bridge-{ident}', a, b, line((node_by_id[a]['x'], node_by_id[a]['y']), (node_by_id[b]['x'], node_by_id[b]['y'])), 16, 'avenue')
        bridges.append({'id': ident, 'kind': kind, 'road': road['id'], 'n': [node_by_id[a]['x'], node_by_id[a]['y']], 's': [node_by_id[b]['x'], node_by_id[b]['y']]})
    # the embankments, split at every node on them; the north one crosses the canal's two mouths on bridges
    for side in (1, -1):
        xs = sorted(embank[side])
        lo, hi = -(R - 70), R - 70
        ends = [x for x in xs if lo <= x <= hi]
        if side < 0:
            ends = [x for x in ends if not (PORT[0] - 10 < x < PORT[2] + 10)]
            port_w, port_e = bank_node(-1, PORT[0]), bank_node(-1, PORT[2])
            ends = sorted(set(ends + [PORT[0], PORT[2]]))
        for xa, xb in zip(ends, ends[1:]):
            if side < 0 and xa == PORT[0] and xb == PORT[2]:
                continue  # the basin opens here: the embankment road goes round the port
            road = _road(f'bank-{side}-{xa:+.0f}', embank[side][xa], embank[side][xb], bank(xa, xb, side), 13, 'embankment')
            if side > 0 and any(abs(abs(x) - CANAL_R) < 30 for x in (xa, xb, (xa + xb) / 2)) and min(abs(xa), abs(xb)) < CANAL_R < max(abs(xa), abs(xb)):
                road['canal_bridge'] = True
    # the port: a ring road round the basin and its yards, joined to the south rings
    pw, pe = embank[-1][PORT[0]], embank[-1][PORT[2]]
    sw, se = node('port-sw', PORT[0], PORT[1]), node('port-se', PORT[2], PORT[1])
    _road('port-west', pw, sw, line((PORT[0], river_centre(PORT[0]) - EMB), (PORT[0], PORT[1])), 15, 'avenue')
    _road('port-south', sw, se, line((PORT[0], PORT[1]), (PORT[2], PORT[1])), 15, 'avenue')
    _road('port-east', se, pe, line((PORT[2], PORT[1]), (PORT[2], river_centre(PORT[2]) - EMB)), 15, 'avenue')
    for ident in [n['id'] for n in nodes if n['id'].startswith('ms')]:
        n = node_by_id[ident]
        for corner in (sw, se):
            c = node_by_id[corner]
            if 40 < math.hypot(n['x'] - c['x'], n['y'] - c['y']) < 150 and n['y'] < PORT[1] + 60 and not crosses((n['x'], n['y']), (c['x'], c['y'])):
                _road(f'portlink-{ident}-{corner}', ident, corner, line((n['x'], n['y']), (c['x'], c['y'])), 13, 'street')
                break
    piers = ([{'kind': 'river', 'x': x, 'y': river_centre(x) + 46, 'heading': 0.0} for x in (-250.0, 160.0, 520.0)] +
             [{'kind': 'river', 'x': x, 'y': river_centre(x) - 46, 'heading': math.pi} for x in (-560.0, 500.0)] +
             [{'kind': 'canal', 't': t} for t in (0.28, 0.5, 0.72)])
    # a boulevard along the inside of the wall, joined to the radial streets that reach it
    ring_r, ring_nodes = R - 82, []
    for k in range(60):
        a = k * math.tau / 60
        x, y = ring_r * math.cos(a), ring_r * math.sin(a)
        ring_nodes.append(None if meridian_wet(x, y, 30) or in_port(x, y) else node(f'wall{k}', x, y))
    for k in range(60):
        a, b = ring_nodes[k], ring_nodes[(k + 1) % 60]
        if a and b:
            t0, t1 = k * math.tau / 60, (k + 1) * math.tau / 60
            _road(f'boulevard-{k}', a, b, [(ring_r * math.cos(t0 + (t1 - t0) * i / 8), ring_r * math.sin(t0 + (t1 - t0) * i / 8)) for i in range(9)], 13, 'avenue')
    for ident in [n['id'] for n in nodes if n['id'][:2] in ('mn', 'ms')]:
        n = node_by_id[ident]
        best = min((b for b in ring_nodes if b), key=lambda b: math.hypot(node_by_id[b]['x'] - n['x'], node_by_id[b]['y'] - n['y']))
        d = math.hypot(node_by_id[best]['x'] - n['x'], node_by_id[best]['y'] - n['y'])
        if 25 < d < 75 and not crosses((n['x'], n['y']), (node_by_id[best]['x'], node_by_id[best]['y'])) and not any(meridian_wet(n['x'] + (node_by_id[best]['x'] - n['x']) * f, n['y'] + (node_by_id[best]['y'] - n['y']) * f, 10) for f in (0.25, 0.5, 0.75)):
            _road(f'tie-{ident}', ident, best, line((n['x'], n['y']), (node_by_id[best]['x'], node_by_id[best]['y'])), 11, 'street')
    # the port's own yards either side of the basin and behind it: room for sorting centres and warehouses
    quads += [(-218.0, -150.0), (-218.0, -290.0), (218.0, -150.0), (218.0, -290.0), (-110.0, -490.0), (110.0, -490.0)]
    return quads, {'canal': [[round(x, 2), round(y, 2)] for x, y in canal_line()], 'canal_half_width': CANAL_HW,
                   'basin': list(BASIN), 'port': list(PORT), 'bridges': bridges, 'piers': piers, 'embankment': EMB}


def _segment_distance(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0., min(1., ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy or 1)))
    px, py = a[0] + dx * t, a[1] + dy * t
    return math.hypot(x - px, y - py), px, py


class _Grid:
    def __init__(self, size=50):
        self.size, self.cells = size, defaultdict(list)

    def add(self, item, x0, y0, x1=None, y1=None):
        x1, y1 = (x0 if x1 is None else x1), (y0 if y1 is None else y1)
        for ix in range(math.floor(x0 / self.size), math.floor(x1 / self.size) + 1):
            for iy in range(math.floor(y0 / self.size), math.floor(y1 / self.size) + 1):
                self.cells[ix, iy].append(item)

    def near(self, x, y, r):
        seen = set()
        for ix in range(math.floor((x-r)/self.size), math.floor((x+r)/self.size)+1):
            for iy in range(math.floor((y-r)/self.size), math.floor((y+r)/self.size)+1):
                for item in self.cells.get((ix, iy), ()):
                    if item not in seen:
                        seen.add(item)
                        yield item


def city_plan(city, destinations=()):
    """Generate connected warped blocks, road-accessible parcels and every house."""
    w, key = city.w, city.key
    seed = sum((i + 3) * ord(c) for i, c in enumerate(key)) + 7163
    rng = random.Random(seed)
    R = float(max(w.cfg['wall_radius'], 740 if w.N >= 700 else 690))
    river = key == 'k1'
    angle = 0 if river else [-.18, .24, -.31, .13, -.12, .34][seed % 6]
    ca, sa = math.cos(angle), math.sin(angle)
    phase = (seed % 43) / 7

    def warp(x, y):
        # A diffeomorphic low-frequency warp keeps street topology while producing
        # broad curves and different block shapes instead of repeating circular rings.
        X = x + 17 * math.sin(y / 210 + phase) + 8 * math.sin(y / 83)
        Y = y + 15 * math.sin(x / 260 + phase * .7)
        return (X * ca - Y * sa, X * sa + Y * ca)

    xs = [i * 116 + 10 * math.sin(i * 1.7 + phase) + 54 for i in range(-12, 13)]
    ys = [i * 116 + 9 * math.sin(i * 1.4 + phase) + 56 for i in range(-12, 13)]
    if river:
        # Both embankments are free of carriageways.  Only north/south bridge
        # corridors cross the water; no centre road runs along the channel.
        ys = sorted([v for v in ys if abs(v) >= 345] + [-250., 250.])
    nodes, roads, service_roads = [], [], []
    lookup = {}
    for i, x in enumerate([] if river else xs):
        for j, y in enumerate(ys):
            X, Y = warp(x, y)
            if math.hypot(X, Y) < R - 56:
                ident = f'n{i}_{j}'
                lookup[i, j] = ident
                nodes.append({'id': ident, 'x': round(X, 3), 'y': round(Y, 3)})
    node_by_id = {n['id']: n for n in nodes}

    def add_road(ident, a, b, points, width=11, kind='street', service=False):
        road = {'id': ident, 'from': a, 'to': b, 'points': [[round(x, 3), round(y, 3)] for x, y in points], 'width': width, 'kind': kind}
        if river and any((p[1] - river_centre(p[0])) * (q[1] - river_centre(q[0])) <= 0 for p, q in zip(points, points[1:])):
            road['bridge'] = True
        (service_roads if service else roads).append(road)
        return road

    for (i, j), a in lookup.items():
        for di, dj in ((1, 0), (0, 1)):
            b = lookup.get((i+di, j+dj))
            if not b:
                continue
            x0, y0, x1, y1 = xs[i], ys[j], xs[i+di], ys[j+dj]
            count = max(2, math.ceil(math.hypot(x1-x0, y1-y0) / 6))
            points = [warp(x0+(x1-x0)*k/count, y0+(y1-y0)*k/count) for k in range(count+1)]
            major = (i % 3 == 0 if dj else j % 3 == 0)
            add_road(f'e-{a}-{b}', a, b, points, 15 if major else 11, 'avenue' if major else 'street')

    waterways, quads = None, None
    if river:
        node_by_id = {}
        quads, waterways = meridian_network(R, add_road, nodes, node_by_id)
        links = defaultdict(set)
        for r in roads + service_roads:
            links[r['from']].add(r['to']); links[r['to']].add(r['from'])
        seen, todo = set(), ['embn+0']
        while todo:
            n = todo.pop()
            if n not in seen:
                seen.add(n); todo.extend(links[n] - seen)
        roads[:] = [r for r in roads if r['from'] in seen]
        nodes[:] = [n for n in nodes if n['id'] in seen]

    def closest_node(x, y):
        return min(nodes, key=lambda n: (n['x']-x)**2 + (n['y']-y)**2)

    def extension(ident, xy, width=13, service=True, towards=None):
        x, y = xy
        start = closest_node(x, y)
        end = {'id': ident, 'x': round(x, 3), 'y': round(y, 3)}
        # A broad quadratic bend leads into the gate without a right-angle kink.
        dx, dy = x-start['x'], y-start['y']
        length = math.hypot(dx, dy)
        bend = min(14, length * .08)
        points = [(start['x']+dx*t + math.sin(math.pi*t)*(-dy/(length or 1))*bend,
                   start['y']+dy*t + math.sin(math.pi*t)*(dx/(length or 1))*bend)
                  for t in [k / max(2, math.ceil(length/6)) for k in range(max(2, math.ceil(length/6))+1)]]
        nodes.append(end)
        node_by_id[ident] = end
        add_road('access-'+ident, start['id'], ident, points, width, 'service' if service else 'gateway', service)
        return {'x': end['x'], 'y': end['y'], 'node': ident, 'towards': towards}

    gates = []
    for name, dx, dy in destinations:
        a = math.atan2(dy, dx)
        gate = extension('gate-'+name, ((R+45)*math.cos(a), (R+45)*math.sin(a)), 16, False, name)
        gate['angle'] = a
        gate['to'] = name
        gates.append(gate)

    facility_spec = [('reactor_pos', 2.53, 220), ('water_plant_pos', -2.47, 175),
                     ('waste_station_pos', 2.02, 130), ('tower_pos', -.82, 160), ('solar_pos', 2.93, 310)]
    facilities, facility_access = {}, {}
    for name, a, extra in facility_spec:
        x, y = (R+extra)*math.cos(a), (R+extra)*math.sin(a)
        facilities[name] = [round(x, 3), round(y, 3)]
        # Stop at the gate, never draw an access road through a plant's footprint.
        setback = 100 if name == 'reactor_pos' else 48
        gate = (x - setback*math.cos(a), y - setback*math.sin(a))
        facility_access[name] = extension('facility-'+name, gate, 15)

    segments, road_grid = [], _Grid()
    for r in roads + service_roads:
        for a, b in zip(r['points'], r['points'][1:]):
            idx = len(segments)
            segments.append((a, b, r['width'], r['from'], r['to']))
            road_grid.add(idx, min(a[0], b[0])-12, min(a[1], b[1])-12, max(a[0], b[0])+12, max(a[1], b[1])+12)

    def road_clear(x, y, radius):
        return all(_segment_distance(x, y, segments[k][0], segments[k][1])[0] >= radius + segments[k][2]/2
                   for k in road_grid.near(x, y, radius+20))

    def frontage(x, y):
        best = min((( _segment_distance(x, y, a, b), A, B) for a, b, _, A, B in segments), key=lambda row: row[0][0])
        (_, X, Y), A, B = best
        na, nb = node_by_id[A], node_by_id[B]
        node = A if math.hypot(X-na['x'], Y-na['y']) < math.hypot(X-nb['x'], Y-nb['y']) else B
        return {'x': round(X, 3), 'y': round(Y, 3), 'node': node}

    cells = []
    centres = quads if river else [warp((xs[i]+xs[i+1])/2, (ys[j]+ys[j+1])/2) for (i, j), _ in lookup.items()
                                   if all(p in lookup for p in ((i+1,j), (i,j+1), (i+1,j+1)))]
    for x, y in centres:
        if river and meridian_wet(x, y, 20):
            continue
        if math.hypot(x, y) > R - (75 if river else 130):
            continue
        # A conservative rectangle uses exact corners; plots never cover a road. Meridian's blocks follow
        # its rings (turned to face the square they ring), and smaller plots fit the tighter inner blocks.
        yaw = math.atan2(y - (EMB if y > river_centre(x) else -EMB), x) + math.pi / 2 if river else angle
        c2, s2 = math.cos(yaw), math.sin(yaw)
        for width, depth in (((76., 66.), (62., 54.), (50., 44.), (42., 38.)) if river else ((76., 66.),)):
            if all(road_clear(x+sx*c2-sy*s2, y+sx*s2+sy*c2, 5) and not (river and meridian_wet(x+sx*c2-sy*s2, y+sx*s2+sy*c2, 6))
                   for sx in (-width/2, 0, width/2) for sy in (-depth/2, 0, depth/2)):
                cells.append({'x': round(x, 3), 'y': round(y, 3), 'w': width, 'd': depth, 'yaw': yaw, 'access': frontage(x, y)})
                break
    available = list(cells)
    parcels = []

    def reserve(kind, score, sector=None):
        if not available:
            if river and kind not in ('sector_service',):
                return None   # Meridian's blocks are fewer: the civic ones come first, the rest as room allows
            raise ValueError(f'{key}: insufficient blocks for {kind}')
        p = min(available, key=score)
        available.remove(p)
        p = {**p, 'id': f'{kind}-{sum(v["kind"] == kind for v in parcels)}', 'kind': kind}
        if sector is not None:
            p['sector'] = sector
        parcels.append(p)
        return p

    # Public infrastructure gets the best connected central blocks before housing.
    for kind in ('bank', 'bigtech', 'government', 'water', 'network', 'transformer', 'hospital', 'fire', 'library', 'sports', 'church', 'cafe'):
        reserve(kind, lambda p: math.hypot(p['x'], p['y']))
    for sector in range(6):
        a = (sector+.5)*math.pi/3
        target = (math.cos(a)*R*.66, math.sin(a)*R*.66)
        reserve('sector_service', lambda p: math.hypot(p['x']-target[0], p['y']-target[1]), sector)
    if river:   # the port's sorting centres and warehouses, on the blocks nearest the basin
        for kind in ('logistics', 'logistics', 'warehouse', 'warehouse', 'warehouse'):
            reserve(kind, lambda p: math.hypot(p['x'], p['y'] - BASIN[1]))
    for i in range(10):
        a = i*math.pi/5 + phase
        radius = R*(.40 if i % 2 else .77)
        if river and not available:
            break   # Meridian's blocks are smaller and fewer; its green is along the water instead
        reserve('park', lambda p: math.hypot(p['x']-math.cos(a)*radius, p['y']-math.sin(a)*radius))

    parcel_grid = _Grid()
    for i, p in enumerate(parcels):
        radius = math.hypot(p['w'], p['d']) / 2 + 14
        parcel_grid.add(i, p['x']-radius, p['y']-radius, p['x']+radius, p['y']+radius)

    def free_parcel(x, y):
        for i in parcel_grid.near(x, y, 1):
            p = parcels[i]
            dx, dy = x-p['x'], y-p['y']
            cp, sp = math.cos(p['yaw']), math.sin(p['yaw'])   # each plot on its own heading
            X, Y = dx*cp+dy*sp, -dx*sp+dy*cp
            if abs(X) < p['w']/2+12 and abs(Y) < p['d']/2+12:
                return False
        return True

    candidates, home_grid = [], _Grid(24)
    # Frontages sampled along exactly the same polylines used by the renderer.
    # Offset keeps 14x12 m homes behind sidewalks and the utility verge.
    candidate_roads = list(roads)
    rng.shuffle(candidate_roads)
    for r in candidate_roads:
        if r['kind'] == 'gateway':
            continue
        points = r['points']
        lens = [math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(points, points[1:])]
        length = sum(lens)
        # Meridian's streets are short arcs between radial streets: start nearer the corner and sample closer
        first, step = (11, 16) if river else (20, 18)
        for s in [first+i*step for i in range(max(0, int((length-2*first+2)/step)+1))]:
            passed = 0
            for seg, L in enumerate(lens):
                if passed+L >= s:
                    a, b = points[seg], points[seg+1]
                    t = (s-passed)/(L or 1)
                    X, Y = a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t
                    dx, dy = (b[0]-a[0])/(L or 1), (b[1]-a[1])/(L or 1)
                    break
                passed += L
            else:
                continue
            for side in (-1, 1):
                offset = r['width']/2 + (14 if river else 17)   # Meridian is built close: terraces along the street
                x, y = X-dy*offset*side, Y+dx*offset*side
                if math.hypot(x, y) > R-62 or (river and abs(y-river_centre(x)) < 76):
                    continue
                if river and r.get('bridge') and abs(y-river_centre(x)) < 225:
                    continue
                if river and (meridian_wet(x, y, 16) or r.get('canal_bridge')):
                    continue
                if not free_parcel(x, y) or not road_clear(x, y, 9):
                    continue
                if any(math.hypot(x-candidates[k]['x'], y-candidates[k]['y']) < (13 if river else 17) for k in home_grid.near(x, y, 18)):
                    continue
                idx = len(candidates)
                candidates.append({'x': round(x, 3), 'y': round(y, 3), 'yaw': math.atan2(dy, dx),
                                   'access': {'x': round(X, 3), 'y': round(Y, 3), 'node': r['from'] if s < length/2 else r['to']}})
                home_grid.add(idx, x, y)
    if river and len(candidates) < w.N:
        # Meridian is dense: what the street frontages cannot hold goes into the blocks' courtyards
        for qx, qy in quads:
            for gx in (-16, 0, 16):
                for gy in (-16, 0, 16):
                    x, y = qx + gx, qy + gy
                    if len(candidates) >= w.N or math.hypot(x, y) > R - 62 or meridian_wet(x, y, 16):
                        continue
                    if not free_parcel(x, y) or not road_clear(x, y, 9):
                        continue
                    if any(math.hypot(x-candidates[k]['x'], y-candidates[k]['y']) < 13 for k in home_grid.near(x, y, 18)):
                        continue
                    acc = frontage(x, y)
                    candidates.append({'x': round(x, 3), 'y': round(y, 3), 'yaw': math.atan2(acc['y'] - y, acc['x'] - x) + math.pi / 2, 'access': acc})
                    home_grid.add(len(candidates) - 1, x, y)
    if len(candidates) < w.N:
        raise ValueError(f'{key}: {len(candidates)} safe frontages for {w.N} houses')
    # Spread density evenly, then keep each six-sector domain's house IDs near its
    # visual service depot.  Buildings may vary in height but identity never moves.
    rng.shuffle(candidates)
    selected = candidates[:w.N]
    selected.sort(key=lambda p: math.atan2(p['y'], p['x']) % math.tau)
    return {'presentation_version': 2, 'wall': R, 'x': [p['x'] for p in selected], 'y': [p['y'] for p in selected],
            'yaw': [round(p['yaw'], 6) for p in selected],
            'access_x': [p['access']['x'] for p in selected], 'access_y': [p['access']['y'] for p in selected],
            'access_node': [p['access']['node'] for p in selected],
            'roads': roads, 'service_roads': service_roads, 'nodes': nodes, 'gates': gates,
            'parcels': parcels, 'parks': [p for p in parcels if p['kind'] == 'park'],
            'sector_services': [p for p in parcels if p['kind'] == 'sector_service'],
            'civic_plots': [p for p in parcels if p['kind'] not in ('park', 'sector_service')],
            'facilities': facilities, 'facility_access': facility_access,
            'river': {'enabled': river, 'half_width': 40, 'bank_clearance': 36}, 'waterways': waterways}
