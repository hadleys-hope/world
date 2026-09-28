"""Finance and simulated time: pause stops accruals, speed does not change the result for the same simulated
time, save and load neither lose debts nor repeat payments."""

import json
import tempfile
import unittest
from unittest import mock

import numpy as np

import hadleys.simulation as simulation
from hadleys.domains import households as hh
from hadleys.domains.finance import finance_day_close, finance_month_close, finance_record
from hadleys.persistence import Store
from hadleys.world import World


class Stop(Exception):
    pass


def light_tick(w):
    """world_tick without the physics: meters run, the mine is down, the closes fire on w.t like the real tick."""
    c = w.cfg
    if w.finished:
        return
    w.t += 1
    w.h_meter_day += 0.05  # 72 kWh a day: 18 cr
    w.h_meter_month += 0.05
    w.mine_frac = 0.0
    hh.finance_tick(w)
    if w.t % c["ticks_per_day"] == 0:
        finance_day_close(w)
    if w.t % (c["ticks_per_day"] * c["days_per_month"]) == 0:
        finance_month_close(w)


def stressed_world():
    """Miners on standby pay and repair bills above the credit limit at a few houses: loans for many,
    overdue and bankruptcy for those within twenty days."""
    w = World()
    w.hh_cash[:] = np.where(w.hh_active, 40.0, 0.0)
    w.fin_baseline = hh.internal_total(w) - sum(w.fin_ext.values())
    for i in (3, 17, 44, 120, 251):
        if w.hh_active[i]:
            finance_record(w, 3000.0, "house", int(w.h_sector[i]), "test", "repair", house=i)
    return w


def state(w):
    """Everything finance keeps, by value."""
    return json.dumps(
        (
            w.t,
            w.hh_cash.tobytes().hex(),
            w.hh_status.tolist(),
            w.hh_led.tobytes().hex(),
            w.hh_led_n.tolist(),
            w.hh_bills,
            w.hh_loans,
            sorted(w.fin_ext.items()),
            sorted((list(k), v) for k, v in w.fin_flows_total.items()),
            w.sector_budget.tobytes().hex(),
            float(w.colony_budget),
            w.fin_series,
        ),
        sort_keys=True,
    )


class FakeClock:
    """time.time() and time.sleep() for sim_loop: every sleep advances the clock by `step` seconds."""

    def __init__(self, step, hook=None):
        self.now = 1000.0
        self.step = step
        self.hook = hook
        self.sleeps = 0

    def time(self):
        return self.now

    def sleep(self, dt):
        self.now += self.step
        self.sleeps += 1
        if self.hook:
            self.hook(self)


def run_loop(w, until_t, speed, step, tick=light_tick):
    """sim_loop with a fake clock; stops right after the tick that reaches until_t."""
    w.speed = speed

    def counted(world):
        tick(world)
        if world.t >= until_t:
            raise Stop

    clock = FakeClock(step)
    with mock.patch.object(simulation, "time", clock), mock.patch.object(simulation, "world_tick", counted):
        with np.errstate(all="ignore"):
            try:
                simulation.sim_loop({"w": w}, None)
            except Stop:
                pass
    return w


class FinanceTime(unittest.TestCase):
    T = 20 * 1440 + 17  # twenty simulated days and a bit

    @classmethod
    def setUpClass(cls):
        w = stressed_world()
        for _ in range(cls.T):
            light_tick(w)
        cls.reference = state(w)
        cls.summary = hh.summary(w)

    def test_the_stress_world_exercises_credit_and_bankruptcy(self):
        self.assertGreater(self.summary["borrowers"], 50)
        self.assertGreater(self.summary["bankrupt"], 0)

    def test_speed_does_not_change_the_result(self):
        for speed, step in ((1, 0.5), (20, 0.5), (600, 0.5), (600, 7.0)):  # the last is capped at 200 ticks a batch
            with self.subTest(speed=speed, step=step):
                w = run_loop(stressed_world(), self.T, speed, step)
                self.assertEqual(w.t, self.T)
                self.assertEqual(state(w), self.reference)

    def test_pause_stops_accruals(self):
        w = stressed_world()
        run_loop(w, 5 * 1440 + 3, 600, 0.5)
        before = state(w)
        w.paused = True

        def stop_after_a_week(clock):
            if clock.now > 1000.0 + 7 * 86400:
                raise Stop

        clock = FakeClock(3600.0, stop_after_a_week)  # an hour of wall time per loop, paused for a week
        with mock.patch.object(simulation, "time", clock), mock.patch.object(simulation, "world_tick", light_tick):
            with self.assertRaises(Stop):
                simulation.sim_loop({"w": w}, None)
        self.assertEqual(state(w), before)
        # resumed, it continues exactly like a world that was never paused
        w.paused = False
        run_loop(w, self.T, 20, 0.5)
        self.assertEqual(state(w), self.reference)

    def test_pause_with_the_real_tick(self):
        w = World()
        w.paused = True
        cash = w.hh_cash.copy()

        def stop(clock):
            if clock.sleeps > 50:
                raise Stop

        clock = FakeClock(86400.0, stop)
        with mock.patch.object(simulation, "time", clock):
            with self.assertRaises(Stop):
                simulation.sim_loop({"w": w}, None)
        self.assertEqual(w.t, 0)
        self.assertTrue(np.array_equal(w.hh_cash, cash))

    def test_speed_with_the_real_tick_across_a_day_close(self):
        results = []
        for speed in (1, 600):
            w = World()
            w.t = 1400  # the day closes at 1440
            run_loop(w, 1460, speed, 0.5, tick=simulation.world_tick)
            results.append(state(w))
        self.assertEqual(results[0], results[1])

    def test_save_and_load_neither_lose_debts_nor_repeat_payments(self):
        for cut in (7 * 1440 - 1, 7 * 1440, 7 * 1440 + 1, 12 * 1440 + 700):
            with self.subTest(saved_at=cut), tempfile.TemporaryDirectory() as directory:
                w = stressed_world()
                for _ in range(cut):
                    light_tick(w)
                store = Store(directory)
                store.save_world(w)
                resumed = store.load_world()
                self.assertEqual(state(resumed), state(w))
                for _ in range(self.T - cut):
                    light_tick(resumed)
                self.assertEqual(state(resumed), self.reference)

    def test_a_close_runs_once_per_day(self):
        w = stressed_world()
        for _ in range(1440):
            light_tick(w)
        rows = int(w.hh_led_n.sum())
        finance_day_close(w)  # the same day again: ignored
        self.assertEqual(int(w.hh_led_n.sum()), rows)


if __name__ == "__main__":
    unittest.main()
