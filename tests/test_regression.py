"""Golden behavior captured from the supplied, pre-refactor repository."""

import gzip
import json
from pathlib import Path
import unittest
from hadleys.world import World
from hadleys.simulation import world_tick
from hadleys.api.snapshots import snapshot, bus_snapshot, house_snapshot
from hadleys.domains.attractors import attractor_snapshot

FIXTURES = Path(__file__).parent / "fixtures"


class SimulationRegression(unittest.TestCase):
    maxDiff = 2000

    def legacy_snapshot(self, value):
        # Additive manual-control fields and finer headings are intentional API changes.
        for rover in value["rovers"]:
            self.assertFalse(rover.pop("manual"))
            self.assertIsNone(rover.pop("chassis"))
            rover["heading"] = round(rover["heading"], 2)
        return value

    def test_original_snapshots_and_domain_order(self):
        with gzip.open(FIXTURES / "simulation.json.gz", "rt") as f:
            expected = json.load(f)
        w = World()
        for tick in range(121):
            if str(tick) in expected:
                actual = dict(
                    snapshot=self.legacy_snapshot(snapshot(w)),
                    bus=bus_snapshot(w),
                    house=house_snapshot(w, 17),
                    attractors=attractor_snapshot(w, True),
                )
                # Normalize tuples and string enums exactly as the HTTP JSON boundary does.
                actual = json.loads(json.dumps(actual, allow_nan=False))
                with self.subTest(tick=tick):
                    self.assertEqual(actual, expected[str(tick)])
            if tick < 120:
                world_tick(w)
        w.t = 1439
        world_tick(w)
        self.assertEqual(json.loads(json.dumps(self.legacy_snapshot(snapshot(w)))), expected["day"])
        w.t = w.cfg["ticks_per_day"] * w.cfg["days_per_month"] - 1
        world_tick(w)
        self.assertEqual(json.loads(json.dumps(self.legacy_snapshot(snapshot(w)))), expected["month"])
