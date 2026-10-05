"""Guards for the tick optimisations: they must not change results, only the work done."""

import unittest

import numpy as np

from hadleys.simulation import world_tick
from hadleys.world import World


class SolverStart(unittest.TestCase):
    def test_houses_cut_off_do_not_hold_the_pressure_loop(self):
        """A house without supply has pressure 0; it used to start at 20 m and take ~40 relaxation steps."""
        w = World()
        for _ in range(3):
            world_tick(w)
        cut = np.arange(0, 300, 2)
        w.h_burst[cut] = True  # valves close on a burst: half the colony is cut off
        w.h_pipes_ok[cut] = False
        its = []
        for _ in range(20):
            world_tick(w)
            its.append(w.utilities.iterations)
        self.assertTrue(w.utilities.converged)
        self.assertLessEqual(max(its[2:]), 20)
        self.assertEqual(float(np.abs(w.utilities.pressure[cut]).max()), 0.0)


if __name__ == "__main__":
    unittest.main()
