"""Golden behavior captured from the supplied, pre-refactor repository."""

import gzip
import json
import sys
from pathlib import Path
import unittest
from hadleys.world import World
from hadleys.simulation import world_tick
from hadleys.api.snapshots import snapshot, bus_snapshot, house_snapshot
from hadleys.domains.attractors import attractor_snapshot

FIXTURES = Path(__file__).parent / "fixtures"
# Transit vehicles re-route along arcs whose step count is int(abs(d) / step) with d a hair from 60 degrees;
# a libm whose sin() is 1 ULP off (macOS) flips 30 steps to 29 and one car ends a few millimetres elsewhere.
# The fixture was made with a correctly rounding libm (glibc). Only these kinematic leaves get a tolerance.
KINEMATIC_TOLERANCE = {"x": 0.05, "y": 0.05, "distance_m": 0.05, "heading": 0.02}
LIBM_DRIFT = sys.platform == "darwin"


class SimulationRegression(unittest.TestCase):
    maxDiff = 2000

    def legacy_snapshot(self, value):
        # Additive manual-control fields and finer headings are intentional API changes.
        for rover in value["rovers"]:
            self.assertFalse(rover.pop("manual"))
            self.assertIsNone(rover.pop("chassis"))
            rover["heading"] = round(rover["heading"], 2)
        # Household finance is additive too; in the golden run every household stays solvent.
        households = value["finance"].pop("households")
        self.assertEqual(households["debt"], 0.0)
        self.assertEqual(households["bankrupt"], 0)
        self.assertEqual(households["households"], 208)
        self.assertEqual(set(value["houses"].pop("fin")), {-1, 0})
        self.assertEqual(len(value["houses"].pop("cash")), 300)
        if value["report"]:
            self.assertEqual(value["report"].pop("households")["debtors"], 0)
        return value

    def snap_kinematics(self, actual, expected):
        """Replace transit kinematics that differ from the fixture by less than the tolerance (macOS only)."""
        if not LIBM_DRIFT:
            return actual
        for mine, theirs in zip(actual["rovers"], expected["rovers"]):
            if theirs["kind"] != "transit":
                continue
            for key, tol in KINEMATIC_TOLERANCE.items():
                if abs(mine[key] - theirs[key]) <= tol:
                    mine[key] = theirs[key]
        return actual

    def legacy_house(self, value):
        finance = value.pop("finance")
        self.assertEqual(finance["status"], "normal")
        self.assertEqual(finance["debt"], 0.0)
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
                    house=self.legacy_house(house_snapshot(w, 17)),
                    attractors=attractor_snapshot(w, True),
                )
                # Normalize tuples and string enums exactly as the HTTP JSON boundary does.
                actual = json.loads(json.dumps(actual, allow_nan=False))
                self.snap_kinematics(actual["snapshot"], expected[str(tick)]["snapshot"])
                with self.subTest(tick=tick):
                    self.assertEqual(actual, expected[str(tick)])
            if tick < 120:
                world_tick(w)
        w.t = 1439
        world_tick(w)
        with self.subTest(tick="day"):
            actual = json.loads(json.dumps(self.legacy_snapshot(snapshot(w))))
            self.assertEqual(self.snap_kinematics(actual, expected["day"]), expected["day"])
        w.t = w.cfg["ticks_per_day"] * w.cfg["days_per_month"] - 1
        world_tick(w)
        with self.subTest(tick="month"):
            actual = json.loads(json.dumps(self.legacy_snapshot(snapshot(w))))
            self.assertEqual(self.snap_kinematics(actual, expected["month"]), expected["month"])
