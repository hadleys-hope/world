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


FLOCK = {**CFG, "flying_crocs": 7}  # LV-426 has no crocodiles (they are Klyaksa's); the tests give it a flock
CALM = {**FLOCK, "croc_raid_mean_days": 0}  # the calm flock alone; raids have their own tests below


class Flock(unittest.TestCase):
    def setUp(self):
        self.w = World(CALM)

    def test_the_flock_roosts_on_dry_shore_at_night(self):
        w = self.w
        self.assertEqual(len(w.crocs), FLOCK["flying_crocs"])
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
                w = World(CALM)
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
        a, b = World({**CALM, "p_animal": 1.0}), World({**CALM, "p_animal": 1.0, "flying_crocs": 0})
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
        a, b = World(CALM), World({**CALM, "flying_crocs": 0})
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

    def test_lv426_has_no_crocodiles_and_klyaksa_has_the_flock(self):
        from hadleys.klyaksa import City

        self.assertEqual(World().crocs, [])
        city = City("k6", "Ridge", 35, 7, (-4300, -3700), 0, 7)
        self.assertEqual(len(city.w.crocs), 7)
        self.assertEqual(city.w.dome_hp, 100.0)

    def test_an_old_lv426_save_loses_its_flock(self):
        with tempfile.TemporaryDirectory() as directory:
            w = World(dict(FLOCK))
            self.assertEqual(len(w.crocs), 7)
            del w.fauna_on_klyaksa  # saved before the flock moved to Klyaksa
            Store(directory).save_world(w)
            resumed = Store(directory).load_world()
            self.assertEqual((resumed.crocs, resumed.cfg["flying_crocs"]), ([], 0))

    def test_other_colony_sizes(self):
        w = World({**CALM, "houses_per_sector": 120, "houses_per_row": 20})
        flock_only(w, 13 * 60)
        self.assertEqual(states(w)["roost"], 0)
        for m in w.crocs:
            self.assertLess(math.hypot(m["x"], m["y"]), w.cfg["wall_radius"])
            self.assertGreater(m["alt"], 20.0)


class Raid(unittest.TestCase):
    """A wild flock flies in, wrecks things through the ordinary incident system, and flies home."""

    def raid_world(self):
        w = World(CALM)
        w.t = 10 * 60
        return w

    def run_raid(self, w, ticks=640):   # gathering 30, raid 300, the flight home
        wr, crossings, inside = w.cfg["wall_radius"], [], 0
        for _ in range(ticks):
            before = {m["id"]: math.hypot(m["x"], m["y"]) for m in w.crocs if m.get("raider")}
            world_tick(w)
            for m in w.crocs:
                if m.get("raider"):
                    r = math.hypot(m["x"], m["y"])
                    inside = max(inside, sum(1 for k in w.crocs if k.get("raider") and math.hypot(k["x"], k["y"]) < wr))
                    if before.get(m["id"], 0) >= wr > r:
                        crossings.append((math.degrees(math.atan2(m["y"], m["x"])) % 360, m["z"]))
        return crossings, inside

    def croc_issues(self, w):
        return Counter(i.kind for i in w.issues if i.cause == "flying crocodiles")

    def test_a_raid_through_the_open_gate_wrecks_the_colony(self):
        w = self.raid_world()
        info = inject(w, "croc_raid")
        self.assertIn("gathering", info["text"])
        self.assertEqual(snapshot(w)["croc_raid"]["phase"], "gather")
        crossings, inside = self.run_raid(w)
        self.assertGreater(inside, 10, "they get in under the dome")
        for angle, z in crossings:
            self.assertAlmostEqual(angle, WEST_GATE * 60.0, delta=2.0, msg="only through the west gate")
            self.assertLess(z, 12.0)
        hits = self.croc_issues(w)
        self.assertGreaterEqual(sum(hits.values()), 8)
        self.assertGreater(hits["aeration_failure"], 0, "they foul the ventilation of houses")
        self.assertTrue(any("flying crocodiles wrecked" in e[1] for log in w.h_log for e in log))
        self.assertIsNone(w.croc_raid, "the raid is over")
        self.assertEqual([m for m in w.crocs if m.get("raider")], [], "the wild flock went home")
        self.assertEqual(len(w.crocs), 7)

    def test_a_gate_shut_in_time_keeps_them_out_of_the_dome(self):
        w = self.raid_world()
        inject(w, "croc_raid")
        inject(w, "croc_lock")
        crossings, inside = self.run_raid(w)
        self.assertEqual((crossings, inside), ([], 0))
        hits = self.croc_issues(w)
        self.assertTrue(hits, "they turn on what is outside")
        self.assertLessEqual(set(hits), {"solar_damaged", "tower_line_broken"})
        self.assertGreaterEqual(w.solar_health, 0.3 - 0.06, "droppings dim the panels, they do not destroy them")

    def test_one_raid_at_a_time(self):
        w = self.raid_world()
        inject(w, "croc_raid")
        self.assertIn("already", inject(w, "croc_raid")["text"])
        self.assertEqual(sum(1 for m in w.crocs if m.get("raider")), FLOCK["croc_raid_size"])

    def test_raids_come_by_themselves_only_by_day(self):
        w = World({**FLOCK, "croc_raid_mean_days": 0.02})
        starts = []
        for _ in range(3 * 1440):
            had = w.croc_raid is not None
            w.t += 1
            fauna_step(w)
            if not had and w.croc_raid is not None:
                starts.append(w.t // 60 % 24)
        self.assertGreater(len(starts), 2)
        self.assertTrue(all(7 <= h < 19 for h in starts), starts)

    def test_the_bus_tells_the_houses(self):
        """hh/env/weather carries croc_raid, so a house program can sense("croc_raid") and shut its vents."""
        from unittest.mock import MagicMock, patch

        from hadleys.integrations.mqtt import MqttBridge

        def weather(w):
            client = MagicMock()
            with patch("paho.mqtt.client.Client", return_value=client):
                bridge = MqttBridge(w, "localhost:1883")
                client.is_connected.return_value = True
                bridge.connected = True
                bridge.publish()
            sent = {call.args[0]: json.loads(call.args[1]) for call in client.publish.call_args_list}
            return sent["hh/env/weather"]["croc_raid"]

        w = self.raid_world()
        self.assertEqual(weather(w), 0)
        inject(w, "croc_raid")
        self.assertEqual(weather(w), 1)

    def test_save_and_load_mid_raid(self):
        with tempfile.TemporaryDirectory() as directory:
            w = self.raid_world()
            inject(w, "croc_raid")
            for _ in range(80):
                world_tick(w)
            store = Store(directory)
            store.save_world(w)
            resumed = store.load_world()
            for _ in range(150):
                world_tick(w)
                world_tick(resumed)
            self.assertEqual(snapshot(resumed)["crocs"], snapshot(w)["crocs"])
            self.assertEqual(snapshot(resumed)["croc_raid"], snapshot(w)["croc_raid"])
            self.assertEqual(self.croc_issues(resumed), self.croc_issues(w))



class KlyaksaFlock(unittest.TestCase):
    def test_the_flock_lives_round_the_dome_never_under_it(self):
        from hadleys.klyaksa import City

        w = City("k4", "Northfield", 125, 25, (-200, 2900), 3900, 11).w
        w.cfg["croc_raid_mean_days"] = 0
        w.t, seen, under = 6 * 60, set(), 0
        for _ in range(16 * 60):
            w.t += 1
            fauna_step(w)
            for m in w.crocs:
                seen.add(m["state"])
                under += m["z"] < dome_ceiling(w.cfg, math.hypot(m["x"], m["y"])) - 1.0
        self.assertEqual(under, 0)
        self.assertTrue({"inbound", "soar", "bask"} <= seen, seen)

    def test_air_defence_shoots_raiders(self):
        from hadleys.klyaksa import City

        w = City("k4", "Northfield", 125, 25, (-200, 2900), 3900, 11).w
        w.t = 10 * 60
        inject(w, "croc_raid")
        for _ in range(400):
            world_tick(w)
        self.assertGreater(w.aa["kills"], 0)


class AfterARaid(unittest.TestCase):
    """A raid that breaks the dome: the crocodiles leave, the dome is repaired and paid for, the damage is fixed."""

    def test_the_city_recovers(self):
        from hadleys.klyaksa import City

        w = City("k4", "Northfield", 125, 25, (-200, 2900), 3900, 11).w
        w.cfg["croc_raid_mean_days"] = 0
        w.t, w.dome_hp = 600, 3.0
        inject(w, "croc_raid")
        for _ in range(500):
            world_tick(w)
        self.assertTrue(w.dome_breached)
        budget = w.colony_budget
        for _ in range(1500):
            world_tick(w)
        self.assertIsNone(w.croc_raid, "the raid ends: nobody is left stuck in the air")
        self.assertEqual([m for m in w.crocs if m.get("raider")], [])
        self.assertGreater(w.dome_hp, 50.0, "the dome crews repair it")
        self.assertFalse(w.dome_breached)
        self.assertGreater(w.dome_repair_spent, 10000, "and the colony pays for it")
        left = [i for i in w.issues if i.cause == "flying crocodiles" and i.status != "resolved"]
        self.assertLessEqual(len(left), 2, "contract crews fix the damage")

    def test_found_klyaksa_anew(self):
        import tempfile

        from hadleys.klyaksa import CITIES, Colony

        with tempfile.TemporaryDirectory() as d:
            colony = Colony(CITIES[4:6], first_id=4650, data_dir=d)
            colony.cities[0].w.dome_hp = 5.0
            colony.save()
            old = [c.w for c in colony.cities]
            colony.reset(CITIES[4:6], first_id=4650)
            self.assertTrue(all(c.w is not o for c, o in zip(colony.cities, old)))
            self.assertEqual(colony.cities[0].w.dome_hp, 100.0)
            self.assertEqual([c.w.N for c in colony.cities], [o.N for o in old])


class ArmouredDome(unittest.TestCase):
    """Klyaksa: a raid has to break the city's armoured dome before it gets at the houses."""

    def city(self):
        from hadleys.klyaksa import City

        c = City("k4", "Northfield", 125, 25, (-200, 2900), 3900, 11)
        c.w.t = 10 * 60
        return c.w

    def test_the_raid_claws_at_the_dome_and_stays_outside(self):
        w = self.city()
        inject(w, "croc_raid")
        wr, low, inside = w.cfg["wall_radius"], 100.0, 0
        for _ in range(420):
            world_tick(w)
            low = min(low, w.dome_hp)
            inside = max(inside, sum(1 for m in w.crocs if m.get("raider") and m["z"] < dome_ceiling(w.cfg, math.hypot(m["x"], m["y"])) - 1.0))
        self.assertLess(low, 95.0, "the dome takes damage")
        self.assertGreater(low, 0.0, "and holds: it is armoured")
        self.assertEqual(inside, 0, "no crocodile gets under an unbroken dome")
        self.assertFalse(any(i.cause == "flying crocodiles" and i.kind in ("aeration_failure", "house_wiring") for i in w.issues))

    def test_a_breach_lets_them_in(self):
        w = self.city()
        w.dome_hp = 0.5
        inject(w, "croc_raid")
        for _ in range(420):
            world_tick(w)
        self.assertTrue(any(i.cause == "flying crocodiles" and i.kind in ("aeration_failure", "house_wiring", "cable_broken", "lamp_broken") for i in w.issues))

    def test_the_dome_heals_between_raids(self):
        w = self.city()
        w.cfg["croc_raid_mean_days"] = 0
        w.dome_hp, w.dome_breached = 10.0, True
        for _ in range(600):
            world_tick(w)
        self.assertGreater(w.dome_hp, 25.0)
        self.assertFalse(w.dome_breached)


if __name__ == "__main__":
    unittest.main()
