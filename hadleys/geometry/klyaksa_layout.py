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
    for i, x in enumerate(xs):
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
    for (i, j), _ in lookup.items():
        if not all(p in lookup for p in ((i+1,j), (i,j+1), (i+1,j+1))):
            continue
        x, y = warp((xs[i]+xs[i+1])/2, (ys[j]+ys[j+1])/2)
        if river and abs(y-river_centre(x)) < 118:
            continue
        if math.hypot(x, y) > R - 130:
            continue
        # A conservative rectangle uses exact corners; plots never cover a road.
        width, depth = 76., 66.
        if not all(road_clear(x+sx*ca-sy*sa, y+sx*sa+sy*ca, 5)
                   for sx in (-width/2, 0, width/2) for sy in (-depth/2, 0, depth/2)):
            continue
        cells.append({'x': round(x, 3), 'y': round(y, 3), 'w': width, 'd': depth, 'yaw': angle, 'access': frontage(x, y)})
    available = list(cells)
    parcels = []

    def reserve(kind, score, sector=None):
        if not available:
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
    for i in range(10):
        a = i*math.pi/5 + phase
        radius = R*(.40 if i % 2 else .77)
        reserve('park', lambda p: math.hypot(p['x']-math.cos(a)*radius, p['y']-math.sin(a)*radius))

    parcel_grid = _Grid()
    for i, p in enumerate(parcels):
        radius = math.hypot(p['w'], p['d']) / 2 + 14
        parcel_grid.add(i, p['x']-radius, p['y']-radius, p['x']+radius, p['y']+radius)

    def free_parcel(x, y):
        for i in parcel_grid.near(x, y, 1):
            p = parcels[i]
            dx, dy = x-p['x'], y-p['y']
            X, Y = dx*ca+dy*sa, -dx*sa+dy*ca
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
        for s in [20+i*18 for i in range(max(0, int((length-36)/18)+1))]:
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
                offset = r['width']/2 + 17
                x, y = X-dy*offset*side, Y+dx*offset*side
                if math.hypot(x, y) > R-62 or (river and abs(y-river_centre(x)) < 76):
                    continue
                if river and r.get('bridge') and abs(y-river_centre(x)) < 225:
                    continue
                if not free_parcel(x, y) or not road_clear(x, y, 9):
                    continue
                if any(math.hypot(x-candidates[k]['x'], y-candidates[k]['y']) < 17 for k in home_grid.near(x, y, 18)):
                    continue
                idx = len(candidates)
                candidates.append({'x': round(x, 3), 'y': round(y, 3), 'yaw': math.atan2(dy, dx),
                                   'access': {'x': round(X, 3), 'y': round(Y, 3), 'node': r['from'] if s < length/2 else r['to']}})
                home_grid.add(idx, x, y)
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
            'river': {'enabled': river, 'half_width': 40, 'bank_clearance': 36} }
