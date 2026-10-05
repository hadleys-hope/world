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
# The pipe-network solver sums the flows of a subtree as a difference of prefix sums (one numpy call instead of one
# per tree level). The order of the additions differs from the fixture's level-by-level sums, so a drainage flow
# rounded to 5 decimals can land one unit in the last place away, and the solver residual (~1e-15 m) differs in
# its last bits. Nothing else changes: pressures, supply flows, temperatures and money are exact.
SUMMATION_TOLERANCE = {"drainage_l_s": 1.0001e-5, "residual_m": 1e-12}


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
        # Water accounts are additive; in the golden run the balance closes and the sewer pump runs.
        self.assertTrue(value["water"].pop("sewer_pump"))
        self.assertLess(value["water"].pop("accounts")["residual"], 1e-6)
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

    def snap_summation_order(self, actual, expected):
        """Replace hydraulic leaves that differ from the fixture only by summation order (see SUMMATION_TOLERANCE)."""
        mine, theirs = actual["hydraulics"], expected["hydraulics"]
        tol = SUMMATION_TOLERANCE["drainage_l_s"]
        for row_m, row_t in zip(mine["drainage_l_s"], theirs["drainage_l_s"]):
            for k, (a, b) in enumerate(zip(row_m, row_t)):
                if abs(a - b) <= tol:
                    row_m[k] = b
        if abs(mine["residual_m"] - theirs["residual_m"]) <= SUMMATION_TOLERANCE["residual_m"]:
            mine["residual_m"] = theirs["residual_m"]
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
                self.snap_summation_order(actual["snapshot"], expected[str(tick)]["snapshot"])
                with self.subTest(tick=tick):
                    self.assertEqual(actual, expected[str(tick)])
            if tick < 120:
                world_tick(w)
        w.t = 1439
        world_tick(w)
        with self.subTest(tick="day"):
            actual = json.loads(json.dumps(self.legacy_snapshot(snapshot(w))))
            self.snap_summation_order(self.snap_kinematics(actual, expected["day"]), expected["day"])
            self.assertEqual(actual, expected["day"])
        w.t = w.cfg["ticks_per_day"] * w.cfg["days_per_month"] - 1
        world_tick(w)
        with self.subTest(tick="month"):
            actual = json.loads(json.dumps(self.legacy_snapshot(snapshot(w))))
            self.snap_summation_order(self.snap_kinematics(actual, expected["month"]), expected["month"])
            self.assertEqual(actual, expected["month"])
