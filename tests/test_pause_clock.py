import pickle
import unittest

from hadleys.world import World
from hadleys.simulation import schedule_pause, world_tick


class PauseClockTests(unittest.TestCase):
    def test_large_batch_stops_exactly_at_target(self):
        w = World()
        w.t = 448
        w.speed = 600
        schedule_pause(w, '07:30')
        for _ in range(200):
            world_tick(w)
        self.assertEqual(w.t, 450)
        self.assertTrue(w.paused)
        self.assertIsNone(w.pause_at)
        w.paused = False
        world_tick(w)
        self.assertEqual(w.t, 451)

    def test_past_time_wraps_and_equal_time_pauses_now(self):
        w = World()
        w.t = 500
        schedule_pause(w, '07:30')
        self.assertEqual(w.pause_at, 1440 + 450)
        schedule_pause(w, '08:20')
        self.assertTrue(w.paused)
        self.assertIsNone(w.pause_at)
        world_tick(w)
        self.assertEqual(w.t, 500)

    def test_midnight_stop_and_restore(self):
        w = World()
        w.t = 1439
        schedule_pause(w, '00:00')
        resumed = pickle.loads(pickle.dumps(w))
        self.assertEqual(resumed.pause_at, 1440)
        world_tick(resumed)
        self.assertEqual(resumed.t, 1440)
        self.assertTrue(resumed.paused)

    def test_cancel_keeps_pause_and_rearming_unfreezes_zero_speed(self):
        w = World()
        w.paused, w.speed = True, 0
        schedule_pause(w, '07:30')
        self.assertFalse(w.paused)
        self.assertGreater(w.speed, 0)
        w.paused = True
        schedule_pause(w, None)
        self.assertTrue(w.paused)
        self.assertIsNone(w.pause_at)

    def test_invalid_times_do_not_change_existing_target(self):
        w = World()
        schedule_pause(w, '07:30')
        for value in ('24:00', '07:60', '7:30', '', '07:30:00', 450, {}, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                schedule_pause(w, value)
            self.assertEqual(w.pause_at, 450)


if __name__ == '__main__':
    unittest.main()
