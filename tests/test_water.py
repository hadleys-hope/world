"""Water and sewage volumes: every failure mode keeps the balance closed (docs/WATER_RU.md)."""

import tempfile
import unittest

import numpy as np

from hadleys.config import CFG
from hadleys.domains.hydraulics import water_balance
from hadleys.domains.incidents import resolve_issue
from hadleys.persistence import Store
from hadleys.simulation import inject, world_tick
from hadleys.world import World


def ticks(w, n):
    for _ in range(n):
        world_tick(w)


class WaterBalance(unittest.TestCase):
    def assertClosed(self, w):
        for part, b in water_balance(w).items():
            self.assertAlmostEqual(b["residual"], 0.0, places=8, msg=part)
        self.assertEqual(w.water_acc["tank_clamp"], 0.0)

    def test_normal_day_part_accounts(self):
        w = World()
        ticks(w, 240)
        a = w.water_acc
        self.assertGreater(a["produced"], 0)
        self.assertAlmostEqual(a["to_sewer"], a["delivered"] * CFG["sewer_return_frac"], places=9)
        self.assertAlmostEqual(a["consumed"], a["delivered"] * (1 - CFG["sewer_return_frac"]), places=9)
        self.assertAlmostEqual(a["ocean_raw"], a["produced"] + a["brine"], places=9)
        self.assertClosed(w)

    def test_empty_tank(self):
        w = World()
        w.intake_ok = False  # the plant makes nothing
        w.water_tank_m3 = 2.0
        w.water_acc["tank0"] = 2.0
        ticks(w, 180)
        self.assertEqual(w.water_tank_m3, 0.0, "the tank runs dry and stays at zero, never below")
        self.assertEqual(int(w.h_water_ok.sum()), 0)
        self.assertEqual(w.water_acc["produced"], 0.0)
        self.assertAlmostEqual(w.water_acc["delivered"] + w.water_acc["leaked"], 2.0, places=9)
        self.assertClosed(w)

    def test_pump_station_without_power(self):
        w = World()
        ticks(w, 5)
        w.trunk_ok = False
        w.ups_center_kwh = 0.0  # no grid and no battery: the station stops
        before = dict(w.water_acc)
        ticks(w, 30)
        self.assertFalse(w.pump_station_ok)
        self.assertEqual(w.water_acc["delivered"], before["delivered"], "no supply without the pump")
        self.assertEqual(w.water_acc["sewer_pumped"], before["sewer_pumped"])
        self.assertClosed(w)

    def test_leak_with_a_stuck_valve_until_the_plumber_comes(self):
        w = World()
        ticks(w, 5)
        info = inject(w, "leak")
        i = int(np.flatnonzero(w.h_valve_stuck)[0])
        self.assertIn(str(i + 1), info["text"])
        before = w.water_acc["leaked"]
        ticks(w, 60)
        leaked = w.water_acc["leaked"] - before
        self.assertGreater(leaked, 0.05, "a stuck valve keeps leaking")
        self.assertGreaterEqual(w.water_acc["storm_pumped"] + w.utilities.storm_storage, leaked - 1e-9)
        self.assertClosed(w)
        resolve_issue(w, next(x for x in w.issues if x.target == f"house:{i}"))
        ticks(w, 2)
        after = w.water_acc["leaked"]
        ticks(w, 30)
        self.assertEqual(w.water_acc["leaked"], after, "repaired: no more leak")
        self.assertClosed(w)

    def test_burst_house_closes_its_valve(self):
        w = World()
        ticks(w, 5)
        w.h_burst[9] = True
        w.h_pipes_ok[9] = False
        ticks(w, 30)
        self.assertFalse(w.h_valve_open[9])
        self.assertEqual(float(w.utilities.leaks[9]), 0.0)
        self.assertClosed(w)

    def test_freeze_then_burst(self):
        w = World()
        i = 20
        w.h_heater_w[i] = 0.0  # a dead heater at minus forty
        w.h_t_in[i] = -2.0
        ticks(w, CFG["freeze_ticks_to_frozen"] + 1)
        self.assertFalse(w.h_pipes_ok[i])
        self.assertEqual(float(w.utilities.delivered[i]), 0.0, "frozen pipes deliver nothing")
        ticks(w, CFG["frozen_ticks_to_burst"] + 2)
        self.assertTrue(w.h_burst[i])
        self.assertTrue(any(x.kind == "pipes_burst" and x.target == f"house:{i}" for x in w.issues))
        self.assertClosed(w)

    def test_sewer_pump_off_overflow_then_recovery(self):
        w = World({**CFG, "drain_storage_m3": 2.0})
        ticks(w, 360)  # morning use
        inject(w, "sewer_pump")
        self.assertFalse(w.sewer_pump_on)
        ticks(w, 180)
        self.assertEqual(w.utilities.sewer_storage, 2.0, "the sump fills to the top")
        spilled = w.water_acc["sewer_overflow"]
        self.assertGreater(spilled, 0.0)
        self.assertTrue(any("overflowing" in e["text"] for e in w.events))
        inject(w, "sewer_pump")
        ticks(w, 30)
        self.assertEqual(w.utilities.sewer_storage, 0.0, "pumped out")
        self.assertEqual(w.water_acc["sewer_overflow"], spilled, "no more spill")
        self.assertTrue(any("no longer overflowing" in e["text"] for e in w.events))
        self.assertClosed(w)

    def test_accounts_survive_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            w = World()
            ticks(w, 50)
            inject(w, "sewer_pump")
            ticks(w, 20)
            store = Store(directory)
            store.save_world(w)
            resumed = store.load_world()
            self.assertEqual(resumed.water_acc, w.water_acc)
            ticks(w, 30)
            ticks(resumed, 30)
            self.assertEqual(resumed.water_acc, w.water_acc)
            self.assertClosed(resumed)


if __name__ == "__main__":
    unittest.main()
