"""The richer 3D view reads existing domain values; it does not advance the simulation."""
import json
import unittest
from hadleys.klyaksa import Colony


class VisualPayloadTests(unittest.TestCase):
    def test_presentation_geometry_preserves_domain_coordinates(self):
        colony = Colony([('test', 'Test', 50, 10, (0, 0))])
        world = colony.cities[0].w
        city = json.loads(colony.geometry())['cities'][0]
        self.assertEqual(city['sim_facilities']['reactor_pos'], list(world.cfg['reactor_pos']))
        self.assertEqual(city['sim_x'], world.h_x.round(3).tolist())
        self.assertEqual(city['sim_y'], world.h_y.round(3).tolist())
        self.assertEqual(city['presentation_version'], 2)
        self.assertEqual(len(city['sector_services']), 6)
        self.assertGreaterEqual(len(city['parks']), 10)
        self.assertEqual(len(city['x']), world.N)

    def test_telemetry_matches_domains_without_advancing_them(self):
        colony = Colony([('test', 'Test', 50, 10, (0, 0))])
        colony.tick(1)
        w = colony.cities[0].w
        vehicles = w.rovers + getattr(w, 'traffic', [])
        before = (w.t, w.water_tank_m3, w.colony_budget, [(r.x, r.y, r.heading) for r in vehicles])
        city = json.loads(colony.state())['cities'][0]
        self.assertEqual(city['water']['tank_m3'], round(w.water_tank_m3, 2))
        self.assertEqual(city['water']['capacity_m3'], w.cfg['water_tank_m3'])
        self.assertEqual(len(city['rovers']), len(vehicles))
        for row, rover in zip(city['rovers'], vehicles):
            self.assertEqual(row['name'], rover.name)
            self.assertEqual(row['x'], round(rover.x, 2))
            self.assertEqual(row['y'], round(rover.y, 2))
            self.assertEqual(row['heading'], round(rover.heading, 4))
        self.assertEqual(before, (w.t, w.water_tank_m3, w.colony_budget, [(r.x, r.y, r.heading) for r in vehicles]))
