"""Regression gates for shared visual parcels, streets, river and mission targets."""
import json
import math
import unittest

from hadleys.klyaksa import Colony
from hadleys.geometry.klyaksa_layout import _Grid, _segment_distance, river_centre


class PresentationPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.colony = Colony()
        cls.geometry = json.loads(cls.colony.geometry())

    def test_ids_and_saved_domain_geometry_are_unchanged(self):
        ids = []
        for c, p in zip(self.colony.cities, self.geometry['cities']):
            ids.extend(range(p['first_id'], p['first_id'] + p['houses']))
            self.assertEqual(len(p['x']), c.w.N)
            self.assertEqual(len(p['yaw']), c.w.N)
            self.assertEqual(p['sim_x'], c.w.h_x.round(3).tolist())
            self.assertEqual(p['sim_y'], c.w.h_y.round(3).tolist())
            self.assertEqual(c.w.t, 0)
        self.assertEqual(ids, list(range(300, 5310)))

    def test_every_city_has_reserved_services_and_connected_gates(self):
        for c in self.geometry['cities']:
            self.assertGreaterEqual(len(c['parks']), 10)
            self.assertEqual({p['sector'] for p in c['sector_services']}, set(range(6)))
            kinds = {p['kind'] for p in c['parcels']}
            self.assertTrue({'bank', 'bigtech', 'government', 'hospital', 'fire', 'library',
                             'water', 'network', 'transformer', 'church', 'sports'} <= kinds)
            nodes = {n['id']: n for n in c['nodes']}
            adjacency = {n: set() for n in nodes}
            for r in c['roads'] + c['service_roads']:
                a, b = r['from'], r['to']
                self.assertEqual(r['points'][0], [nodes[a]['x'], nodes[a]['y']])
                self.assertEqual(r['points'][-1], [nodes[b]['x'], nodes[b]['y']])
                adjacency[a].add(b)
                adjacency[b].add(a)
            visited, todo = set(), [next(iter(nodes))]
            while todo:
                n = todo.pop()
                if n not in visited:
                    visited.add(n)
                    todo.extend(adjacency[n] - visited)
            self.assertEqual(visited, set(nodes), c['id'])
            for p in c['parcels']:
                self.assertIn(p['access']['node'], visited)
            for gate in c['gates']:
                self.assertAlmostEqual(math.hypot(gate['x'], gate['y']), c['wall'] + 45, delta=.002)
                self.assertIn(gate['node'], visited)

    def test_houses_stay_off_roads_and_reserved_parcels(self):
        for c in self.geometry['cities']:
            segments, grid = [], _Grid()
            for r in c['roads'] + c['service_roads']:
                for a, b in zip(r['points'], r['points'][1:]):
                    grid.add(len(segments), min(a[0], b[0])-20, min(a[1], b[1])-20,
                             max(a[0], b[0])+20, max(a[1], b[1])+20)
                    segments.append((a, b, r['width']))
            for x, y in zip(c['x'], c['y']):
                for k in grid.near(x, y, 12):
                    a, b, width = segments[k]
                    self.assertGreaterEqual(_segment_distance(x, y, a, b)[0], width/2 + 8.99)
                for p in c['parcels']:
                    ca, sa = math.cos(p['yaw']), math.sin(p['yaw'])
                    dx, dy = x-p['x'], y-p['y']
                    X, Y = dx*ca + dy*sa, -dx*sa + dy*ca
                    self.assertTrue(abs(X) >= p['w']/2+11.99 or abs(Y) >= p['d']/2+11.99)

    def test_streets_never_cross_without_a_shared_graph_junction(self):
        for c in self.geometry['cities']:
            segments, grid = [], _Grid(30)
            for r in c['roads'] + c['service_roads']:
                for a, b in zip(r['points'], r['points'][1:]):
                    for k in grid.near((a[0]+b[0])/2, (a[1]+b[1])/2, 10):
                        A, B, other = segments[k]
                        if r['id'] == other['id'] or {r['from'], r['to']} & {other['from'], other['to']}:
                            continue
                        dx, dy, DX, DY = b[0]-a[0], b[1]-a[1], B[0]-A[0], B[1]-A[1]
                        den = dx*DY-dy*DX
                        if abs(den) < 1e-10:
                            continue
                        t = ((A[0]-a[0])*DY-(A[1]-a[1])*DX)/den
                        u = ((A[0]-a[0])*dy-(A[1]-a[1])*dx)/den
                        self.assertFalse(0 < t < 1 and 0 < u < 1, (c['id'], r['id'], other['id']))
                    grid.add(len(segments), min(a[0],b[0]), min(a[1],b[1]), max(a[0],b[0]), max(a[1],b[1]))
                    segments.append((a,b,r))

    def test_meridian_river_has_clear_banks_and_only_bridge_crossings(self):
        c = self.geometry['cities'][0]
        self.assertTrue(c['river']['enabled'])
        for x, y in zip(c['x'], c['y']):
            self.assertGreaterEqual(abs(y-river_centre(x)), 75.99)
        bridges = 0
        for r in c['roads'] + c['service_roads']:
            for a, b in zip(r['points'], r['points'][1:]):
                da, db = a[1]-river_centre(a[0]), b[1]-river_centre(b[0])
                if da*db <= 0:
                    self.assertTrue(r.get('bridge'), r['id'])
                    bridges += 1
        self.assertGreater(bridges, 3)
        for road in c['roads'] + c['service_roads']:
            if road.get('bridge'):
                for x, y in (road['points'][0], road['points'][-1]):
                    self.assertGreaterEqual(abs(y-river_centre(x)), 220, road['id'])
        self.assertTrue(all(not p['river']['enabled'] for p in self.geometry['cities'][1:]))

    def test_house_service_mission_maps_to_exact_house_frontage(self):
        c = self.colony.cities[0]
        rover = c.w.rovers[0]
        original = (rover.job, rover.state, rover.route)
        try:
            rover.job, rover.state = 37, 'TO_HOUSE'
            rover.route = [(float(c.w.h_x[37]), float(c.w.h_y[37]))]
            row = self.colony._visual_rover(c, rover)
            p = self.geometry['cities'][0]
            self.assertEqual(row['visual_target'], {'x': p['access_x'][37], 'y': p['access_y'][37], 'node': p['access_node'][37]})
            self.assertTrue(row['moving'])
            self.assertEqual(row['mission_state'], 'TO_HOUSE')
            self.assertEqual(c.w.t, 0)
        finally:
            rover.job, rover.state, rover.route = original
