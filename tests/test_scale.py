"""Colony size and the pipe-network solver: any size builds and runs; the tree sums match the level-by-level ones."""

import unittest

import numpy as np

from hadleys.config import CFG, colony_layout_cfg
from hadleys.simulation import world_tick
from hadleys.world import World


class ColonySize(unittest.TestCase):
    def test_default_colony_is_unchanged(self):
        self.assertIs(colony_layout_cfg(CFG), CFG)

    def test_bigger_colony_is_consistent(self):
        c = colony_layout_cfg({**CFG, "houses_per_sector": 120, "houses_per_row": 20})
        self.assertEqual(c["house_rows"], 6)
        self.assertEqual(sum(c["type_counts"]), 720)
        self.assertGreater(c["wall_radius"], c["ring_road_radius"])
        self.assertEqual(c["spine_radii"][-1], c["ring_road_radius"])
        rx, ry = c["reactor_pos"]
        self.assertGreater((rx * rx + ry * ry) ** 0.5, c["wall_radius"], "facilities stay outside the wall")
        with self.assertRaises(ValueError):
            colony_layout_cfg({**CFG, "houses_per_sector": 55})

    def test_bigger_colony_runs(self):
        w = World({**CFG, "houses_per_sector": 120, "houses_per_row": 20})
        self.assertEqual(w.N, 720)
        for _ in range(3):
            world_tick(w)
        self.assertTrue(w.utilities.converged)
        self.assertGreater(int(w.h_water_ok.sum()), 700)


class TreeSums(unittest.TestCase):
    def test_prefix_sums_match_level_by_level(self):
        u = World().utilities
        rng = np.random.default_rng(1)
        demand = rng.uniform(0, 1e-3, len(u.nodes))
        out = demand.copy()
        for a, b, _ in reversed(u._lvl):
            np.add.at(out, a, out[b])
        np.testing.assert_allclose(u.aggregate(demand), out[u.b], rtol=0, atol=1e-15)
        loss = rng.uniform(0, 0.5, len(u.links))
        head = np.full(len(u.nodes), 50.0)
        for k, (a, b, ids) in enumerate(u._lvl):
            head[b] = head[a] - loss[ids]
            if k == u._pump_level:
                head[1] += 7.0
        np.testing.assert_allclose(u.heads(50.0, loss, 7.0), head, rtol=0, atol=1e-11)


if __name__ == "__main__":
    unittest.main()
