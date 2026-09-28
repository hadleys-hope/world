import copy
import math
import tempfile
import unittest

from hadleys.world import World
from hadleys.simulation import world_tick
from hadleys.persistence import Store
from hadleys.api.snapshots import snapshot
from hadleys.domains.citizens import citizens_step, route_position, citizen_snapshot


class CitizenTests(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def step_at(self, minute):
        self.w.t = minute
        citizens_step(self.w)

    def test_profiles_are_complete_and_stable(self):
        profiles = citizen_snapshot(self.w)
        self.assertEqual(len(profiles), 300)
        self.assertEqual(len({c['id'] for c in profiles}), 300)
        self.assertEqual({c['profession'] for c in profiles}, {'engineer', 'electrician', 'scientist'})
        self.assertEqual({c['workplace'] for c in profiles}, {'garage', 'medlab'})
        self.assertTrue(all(0 <= c['home'] < self.w.N for c in profiles))
        self.assertEqual(profiles, citizen_snapshot(World()))
        self.assertEqual(len(snapshot(self.w)['citizens']), 300)

    def test_every_resident_completes_a_workday(self):
        history = {c.id: [c.state] for c in self.w.citizens}
        for minute in range(1, 1440):
            self.step_at(minute)
            for c in self.w.citizens:
                if history[c.id][-1] != c.state:
                    history[c.id].append(c.state)
        for c in self.w.citizens:
            self.assertEqual(history[c.id], ['HOME', 'WALK_TO_WORK', 'AT_WORK', 'WALK_HOME', 'HOME'])
            self.assertEqual(c.progress, 0)
            self.assertEqual((c.x, c.y), c.route[0])

    def test_arrive_by_shift_and_leave_at_end(self):
        for minute in range(430, 600):
            self.step_at(minute)
            for c in self.w.citizens:
                if minute == c.shift_start:
                    self.assertEqual(c.state, 'AT_WORK')
        c = self.w.citizens[0]
        self.step_at(c.shift_end - 1)
        self.assertEqual(c.state, 'AT_WORK')
        self.step_at(c.shift_end)
        self.assertEqual(c.state, 'WALK_HOME')

    def test_pause_freezes_clock_profiles_and_rng(self):
        self.step_at(470)
        before = copy.deepcopy(citizen_snapshot(self.w))
        tick = self.w.t
        rng = copy.deepcopy(self.w.rng.bit_generator.state)
        self.w.paused = True
        for _ in range(10):
            world_tick(self.w)
            citizens_step(self.w)
        self.assertEqual(self.w.t, tick)
        self.assertEqual(citizen_snapshot(self.w), before)
        self.assertEqual(self.w.rng.bit_generator.state, rng)
        self.w.paused = False
        world_tick(self.w)
        self.assertEqual(self.w.t, tick + 1)

    def test_storm_shelter_and_resume(self):
        c = self.w.citizens[0]
        c.state, c.progress = 'WALK_TO_WORK', .2
        c.x, c.y = route_position(c)
        self.w.storm_ticks = 100
        for minute in range(480, 500):
            self.step_at(minute)
        self.assertEqual(c.state, 'HOME')
        self.assertEqual(c.wait_reason, 'storm')
        self.w.storm_ticks = 0
        self.step_at(500)
        self.assertEqual(c.state, 'WALK_TO_WORK')
        c.state, c.progress = 'AT_WORK', 1
        self.w.storm_ticks = 100
        self.step_at(1000)
        self.assertEqual(c.state, 'AT_WORK')
        self.w.storm_ticks = 0
        self.step_at(1001)
        self.assertEqual(c.state, 'WALK_HOME')

    def test_lockdown_wait_has_reason_and_resumes(self):
        c = self.w.citizens[0]
        c.state, c.progress = 'WALK_TO_WORK', .2
        c.x, c.y = route_position(c)
        sector = int(self.w.h_sector[c.home])
        self.w.lockdown_ticks[sector] = 100
        self.step_at(480)
        self.assertEqual(c.progress, .2)
        self.assertEqual(c.wait_reason, 'sector_lockdown')
        visible = next(p for p in snapshot(self.w)['people'] if p[4] == c.id)
        self.assertTrue(visible[6])
        self.w.lockdown_ticks[sector] = 0
        self.step_at(481)
        self.assertGreater(c.progress, .2)

    def test_late_departure_does_not_start_after_shift(self):
        self.step_at(1100)
        self.assertTrue(all(c.state == 'HOME' for c in self.w.citizens))
        self.step_at(1440 + 480)
        self.assertEqual(self.w.citizens[0].state, 'WALK_TO_WORK')

    def test_save_load_continues_exactly(self):
        self.step_at(470)
        self.assertTrue(any(c.state == 'WALK_TO_WORK' for c in self.w.citizens))
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            self.w.paused = True
            store.save_world(self.w)
            resumed = store.load_world()
            self.assertIsNotNone(resumed)
            self.assertTrue(resumed.paused)
            self.assertEqual(citizen_snapshot(resumed), citizen_snapshot(self.w))
            self.assertEqual([c.route for c in resumed.citizens], [c.route for c in self.w.citizens])
            resumed.paused = self.w.paused = False
            for _ in range(50):
                resumed.t += 1
                self.w.t += 1
                citizens_step(resumed)
                citizens_step(self.w)
            self.assertEqual(citizen_snapshot(resumed), citizen_snapshot(self.w))

    def test_migration_preserves_legacy_identity_and_position(self):
        del self.w.citizens
        del self.w.citizens_version
        self.w.w_state[3] = 1
        self.w.w_prog[3] = .4
        self.w.w_x[3], self.w.w_y[3] = 220, 110
        Store.migrate(self.w)
        self.assertEqual(len(self.w.citizens), 300)
        c = self.w.citizens[3]
        self.assertEqual(c.home, int(self.w.w_home[3]))
        self.assertEqual(c.state, 'WALK_TO_WORK')
        self.assertEqual((c.x, c.y), (220, 110))
        self.assertLess(math.dist(route_position(c), (220, 110)), 1e-8)
        before = citizen_snapshot(self.w)
        Store.migrate(self.w)
        self.assertEqual(citizen_snapshot(self.w), before)


if __name__ == '__main__':
    unittest.main()
