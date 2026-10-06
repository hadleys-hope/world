"""The richer 3D view reads existing domain values; it does not advance the simulation."""
import json
import unittest
from hadleys.klyaksa import Colony
from hadleys.geometry.roads import colony_layout


class VisualPayloadTests(unittest.TestCase):
    def test_facilities_and_every_road_are_exported(self):
        colony = Colony([('test', 'Test', 50, 10, (0, 0))])
        world = colony.cities[0].w
        city = json.loads(colony.geometry())['cities'][0]
        self.assertEqual(city['facilities']['reactor_pos'], list(world.cfg['reactor_pos']))
        self.assertEqual(len(city['roads']) + len(city['service_roads']), len(colony_layout(world.cfg)['roads']))
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
