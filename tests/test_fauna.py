"""The flock of flying crocodiles (hadleys/domains/fauna.py)."""

import json
import math
import tempfile
import unittest
from collections import Counter

import numpy as np

from hadleys.api.snapshots import snapshot
from hadleys.config import CFG
from hadleys.domains.fauna import ROOF, WEST_GATE, dome_ceiling, fauna_blame, fauna_step
from hadleys.domains.incidents import incidents_step
from hadleys.geometry.terrain import site_elevation
from hadleys.persistence import Store
from hadleys.simulation import inject, world_tick
from hadleys.world import World


def flock_only(w, ticks):
    """Advance the clock and the flock without the physics: fast, and enough for flight tests."""
    for _ in range(ticks):
        w.t += 1
        fauna_step(w)


def states(w):
    return Counter(m["state"] for m in w.crocs)


class Flock(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def test_the_flock_roosts_on_dry_shore_at_night(self):
        w = self.w
        self.assertEqual(len(w.crocs), CFG["flying_crocs"])
        self.assertEqual(states(w), {"roost": 7})
        for m in w.crocs:
            self.assertGreater(site_elevation(m["x"], m["y"], w.cfg), w.cfg["ocean_level_m"])
            self.assertGreater(math.hypot(m["x"], m["y"]), w.cfg["wall_radius"] + 300)
        flock_only(w, 5 * 60)  # 05:00: still night
        self.assertEqual(states(w), {"roost": 7})

    def test_a_day_out_and_back(self):
        w = self.w
        c = w.cfg
        seen = set()
        for _ in range(1440):
            w.t += 1
            fauna_step(w)
            for m in w.crocs:
                seen.add(m["state"])
                r = math.hypot(m["x"], m["y"])
                self.assertTrue(all(math.isfinite(m[k]) for k in ("x", "y", "z", "heading")))
                self.assertGreaterEqual(m["z"], 0.0)
                if r < c["wall_radius"]:
                    self.assertLess(m["z"], dome_ceiling(c, r) - 40.0, "kept well under the glass")
            if w.t == 13 * 60:
                midday = states(w)
        self.assertEqual(seen, {"roost", "inbound", "soar", "dive", "bask", "outbound"})
        self.assertEqual(midday["roost"] + midday["inbound"] + midday["outbound"], 0, "all over the colony at 13:00")
        self.assertEqual(states(w), {"roost": 7}, "home by midnight")
        for m in w.crocs:
            self.assertEqual((m["x"], m["y"], m["z"]), (*m["home"], 0.0))

    def test_they_enter_low_through_the_west_gate(self):
        w = self.w
        wr = w.cfg["wall_radius"]
        crossings = []
        for _ in range(11 * 60):
            before = [math.hypot(m["x"], m["y"]) for m in w.crocs]
            w.t += 1
            fauna_step(w)
            for m, r0 in zip(w.crocs, before):
                if r0 >= wr > math.hypot(m["x"], m["y"]):
                    crossings.append((math.degrees(math.atan2(m["y"], m["x"])) % 360, m["z"]))
        self.assertEqual(len(crossings), 7)
        for angle, z in crossings:
            self.assertAlmostEqual(angle, WEST_GATE * 60.0, delta=2.0)
            self.assertLess(z, 12.0)

    def test_basking_is_on_a_heated_roof(self):
        w = self.w
        w.h_heater_on[:] = False
        w.h_heater_on[[40, 41, 42]] = True
        landed = set()
        for _ in range(18 * 60):
            w.t += 1
            fauna_step(w)
            for m in w.crocs:
                if m["state"] == "bask":
                    landed.add(m["house"])
                    self.assertEqual((m["x"], m["y"]), (float(w.h_x[m["house"]]), float(w.h_y[m["house"]])))
                    self.assertEqual(m["z"], ROOF[int(w.h_type[m["house"]])], "above the roof of its house type")
        self.assertTrue(landed)
        self.assertLessEqual(landed, {40, 41, 42})

    def test_a_storm_or_a_shut_gate_keeps_them_on_the_shore(self):
        for name in ("storm", "lockdown"):
            with self.subTest(name):
                w = World()
                if name == "storm":
                    w.storm_ticks = 10**6
                else:
                    w.gate_state[WEST_GATE] = "LOCKDOWN"
                flock_only(w, 14 * 60)
                self.assertEqual(states(w), {"roost": 7})

    def test_a_gate_shut_behind_them_keeps_them_circling(self):
        w = self.w
        flock_only(w, 13 * 60)
        w.gate_state[WEST_GATE] = "LOCKDOWN"
        flock_only(w, 9 * 60)  # 22:00, long after dusk
        self.assertEqual(states(w)["roost"], 0)
        for m in w.crocs:
            self.assertLess(math.hypot(m["x"], m["y"]), w.cfg["wall_radius"])
        w.gate_state[WEST_GATE] = "OPEN"
        flock_only(w, 4 * 60)
        self.assertEqual(states(w), {"roost": 7})

    def test_wildlife_damage_brings_the_nearest_one_down(self):
        w = self.w
        flock_only(w, 11 * 60)
        for m in w.crocs:
            if m["state"] != "soar":
                m["state"], m["house"] = "soar", -1
        house = 123
        hx, hy = float(w.h_x[house]), float(w.h_y[house])
        nearest = min(w.crocs, key=lambda m: math.hypot(m["x"] - hx, m["y"] - hy))
        self.assertIs(fauna_blame(w, house), nearest)
        self.assertEqual((nearest["state"], nearest["house"]), ("dive", house))
        self.assertIn("flying crocodile", w.h_log[house][0][1])
        for _ in range(90):
            flock_only(w, 1)
            if nearest["state"] == "bask":
                break
        roof = ROOF[int(w.h_type[house])]
        self.assertEqual((nearest["state"], nearest["x"], nearest["y"], nearest["z"]), ("bask", hx, hy, roof))
        self.assertTrue(nearest["blamed"])
        flock_only(w, 26)
        self.assertEqual((nearest["state"], nearest["blamed"]), ("soar", False), "it sat a while and left")

    def test_the_incident_roll_calls_the_flock_without_extra_draws(self):
        """The wildlife incident is the existing roll; blaming a crocodile must not change the physics stream."""
        a, b = World({**CFG, "p_animal": 1.0}), World({**CFG, "p_animal": 1.0, "flying_crocs": 0})
        for w in (a, b):
            w.t = 11 * 60
        for m in a.crocs:
            m["state"], m["x"], m["y"], m["z"] = "soar", 300.0, 0.0, 60.0
        incidents_step(a)
        incidents_step(b)
        self.assertEqual(a.rng.bit_generator.state, b.rng.bit_generator.state)
        self.assertEqual([i.target for i in a.issues], [i.target for i in b.issues])
        self.assertEqual(states(a)["dive"], 1)

    def test_no_crocodile_in_the_air_no_blame(self):
        self.assertIsNone(fauna_blame(self.w, 5))
        self.assertEqual(len(self.w.h_log[5]), 0)

    def test_operator_call_at_night(self):
        w = self.w
        w.t = 22 * 60
        info = inject(w, "croc")
        self.assertIn("west gate", info["text"])
        self.assertAlmostEqual(info["x"], -w.cfg["wall_radius"])
        flock_only(w, 90)
        self.assertEqual(states(w)["roost"], 0)
        flock_only(w, 6 * 60)  # 05:30: the call wore off at 02:00, the way home takes up to three hours
        self.assertEqual(states(w), {"roost": 7}, "the call wears off and they go home in the dark")

    def test_the_physics_does_not_notice_the_flock(self):
        a, b = World(), World({**CFG, "flying_crocs": 0})
        self.assertEqual(b.crocs, [])
        for w in (a, b):
            w.t = 8 * 60  # the flock is on its way in
            for _ in range(240):
                world_tick(w)
        self.assertGreater(states(a)["soar"] + states(a)["bask"] + states(a)["dive"], 0)
        self.assertEqual(a.rng.bit_generator.state, b.rng.bit_generator.state)
        sa, sb = snapshot(a), snapshot(b)
        self.assertEqual(len(sa.pop("crocs")), 7)
        self.assertEqual(sb.pop("crocs"), [])
        self.assertEqual(json.dumps(sa, sort_keys=True, default=str), json.dumps(sb, sort_keys=True, default=str))

    def test_snapshot_rows_are_json_and_small(self):
        w = self.w
        flock_only(w, 12 * 60)
        rows = json.loads(json.dumps(snapshot(w)["crocs"], allow_nan=False))
        self.assertEqual([r["id"] for r in rows], list(range(1, 8)))
        self.assertEqual(set(rows[0]), {"id", "x", "y", "z", "heading", "state", "house"})
        self.assertLess(len(json.dumps(rows)), 900)

    def test_save_and_load_mid_flight(self):
        with tempfile.TemporaryDirectory() as directory:
            w = self.w
            w.t = 9 * 60
            for _ in range(120):
                world_tick(w)
            store = Store(directory)
            store.save_world(w)
            resumed = store.load_world()
            self.assertEqual(snapshot(resumed)["crocs"], snapshot(w)["crocs"])
            for _ in range(240):  # the flock's own random stream is saved too: both pick the same roofs
                world_tick(w)
                world_tick(resumed)
            self.assertEqual(snapshot(resumed)["crocs"], snapshot(w)["crocs"])

    def test_a_world_saved_before_the_flock_existed_still_ticks(self):
        """Klyaksa city saves are unpickled without Store.migrate: no crocs attribute, no cfg key."""
        w = World({**CFG, "flying_crocs": 0})
        for name in ("crocs", "croc_call", "fauna_rng"):
            delattr(w, name)
        del w.cfg["flying_crocs"]
        world_tick(w)
        self.assertEqual(snapshot(w)["crocs"], [])
        self.assertIsNone(fauna_blame(w, 3))

    def test_klyaksa_cities_have_no_crocodiles(self):
        from hadleys.klyaksa import City

        city = City("k6", "Ridge", 35, 7, (-4300, -3700), 0, 7)
        self.assertEqual(city.w.crocs, [])

    def test_other_colony_sizes(self):
        w = World({**CFG, "houses_per_sector": 120, "houses_per_row": 20})
        flock_only(w, 13 * 60)
        self.assertEqual(states(w)["roost"], 0)
        for m in w.crocs:
            self.assertLess(math.hypot(m["x"], m["y"]), w.cfg["wall_radius"])
            self.assertGreater(m["alt"], 20.0)


if __name__ == "__main__":
    unittest.main()
