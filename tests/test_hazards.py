"""Klyaksa's hazards (hadleys/domains/hazards.py): creatine, migrations and air defence, plankton, vapours."""

import unittest

from hadleys.config import CFG
from hadleys.domains.hazards import hazards_snapshot
from hadleys.simulation import inject, world_tick
from hadleys.world import World

KLYAKSA = {**CFG, "klyaksa_hazards": True, "migration_mean_days": 1e9, "plankton_mean_days": 1e9, "mine_income_per_tick": 75.0}


def city(**over):
    w = World({**KLYAKSA, **over})
    w.t = 10 * 60
    return w


def run(w, ticks):
    for _ in range(ticks):
        world_tick(w)


class Hazards(unittest.TestCase):
    def test_lv426_has_none(self):
        w = World()
        self.assertIsNone(hazards_snapshot(w))
        self.assertIn("No migration", inject(w, "migration")["text"])

    def test_without_air_defence_the_city_drowns_in_manure(self):
        w = city()
        inject(w, "aa_toggle")  # off
        inject(w, "migration")
        run(w, 400)
        h = hazards_snapshot(w)
        self.assertGreater(h["dome_dirt"] + h["manure_t"], 1.0)
        self.assertEqual(h["aa"]["kills"], 0)

    def test_air_defence_shoots_them_down(self):
        on, off = city(), city()
        inject(off, "aa_toggle")
        for w in (on, off):
            inject(w, "migration")
            run(w, 400)
        a, b = hazards_snapshot(on), hazards_snapshot(off)
        self.assertGreater(a["aa"]["kills"], 3)
        self.assertLess(a["dome_dirt"] + a["manure_t"], b["dome_dirt"] + b["manure_t"])
        self.assertGreater(a["costs"], 0, "shells cost money")

    def test_plankton_eats_the_seaward_sector_and_is_burned(self):
        w = city()
        inject(w, "plankton")
        run(w, 300)
        h = hazards_snapshot(w)
        self.assertGreater(h["burns"], 0, "the colony burns it once it is dense")
        self.assertTrue(any(i.cause == "plankton" for i in w.issues))

    def test_vapours_make_the_personnel_drunk(self):
        w = city()
        inject(w, "plankton")
        run(w, 300)
        self.assertGreater(w.drunk, 0.2)

    def test_creatine_pays_and_mutates_the_fauna(self):
        w = city(flying_crocs=7, dome_armor=True, croc_raid_mean_days=0)
        before = w.colony_budget
        run(w, 200)
        self.assertGreater(w.creatine_t, 0)
        self.assertGreater(w.colony_budget - before, 5000, "creatine is worth a fortune")
        w.creatine_t, w.mutation = 800.0, 2.0
        self.assertEqual(sum(1 for m in w.crocs if m.get("raider")), 0)
        inject(w, "croc_raid")
        self.assertEqual(sum(1 for m in w.crocs if m.get("raider")), int(CFG["croc_raid_size"] * 2))


if __name__ == "__main__":
    unittest.main()
