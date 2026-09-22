import unittest, math, time, json, sys

sys.path.insert(0, ".")
import hadleys_hope as h


class DrivingTests(unittest.TestCase):
    def setUp(self):
        self.w = h.World()
        self.r = self.w.traffic[0]
        self.owner = "test-owner-0123456789"

    def cmd(self, cmd, **kwargs):
        return h.driver_command(
            self.w, dict(cmd=cmd, name=self.r.name, owner=self.owner, **kwargs)
        )

    def claim(self):
        self.assertTrue(self.cmd("drive_claim")["ok"])

    def test_claim_pauses_autopilot(self):
        self.claim()
        p = self.r.x, self.r.y
        for _ in range(40):
            h.traffic_step(self.w)
        self.assertEqual(p, (self.r.x, self.r.y))
        self.assertEqual(self.r.state, "DRIVING")

    def test_drive_while_paused_and_without_fuel(self):
        self.w.paused = True
        self.r.fuel_l = 0
        self.claim()
        x = self.r.x
        self.r.driver_pose_at -= 1
        out = self.cmd(
            "drive_pose",
            seq=0,
            x=x + 4,
            y=self.r.y,
            heading=0.2,
            velocity=4,
            chassis={"rpm": 2000, "gear": 2, "height": 1.1},
        )
        self.assertTrue(out["ok"])
        self.assertEqual(self.r.x, x + 4)
        self.assertEqual(self.r.fuel_l, 0)
        self.assertGreater(self.r.odometer_m, 3.5)

    def test_lease_exclusive_and_releases(self):
        self.claim()
        self.assertFalse(
            h.driver_command(
                self.w,
                dict(cmd="drive_claim", name=self.r.name, owner="another-owner-012345"),
            )["ok"]
        )
        self.assertTrue(self.cmd("drive_release")["ok"])
        self.assertTrue(self.r.driver_parked)
        self.assertEqual(self.r.velocity, 0)
        self.assertEqual(self.r.state, "PARKED")

    def test_invalid_pose_does_not_corrupt_world(self):
        self.claim()
        p = (self.r.x, self.r.y)
        for x in [float("nan"), float("inf"), 15000, self.r.x + 500]:
            self.assertFalse(
                self.cmd("drive_pose", seq=0, x=x, y=self.r.y, heading=0, velocity=1)[
                    "ok"
                ]
            )
            self.assertEqual((self.r.x, self.r.y), p)
        json.dumps(h.snapshot(self.w), allow_nan=False)

    def test_stale_pose_rejected(self):
        self.claim()
        args = dict(x=self.r.x, y=self.r.y, heading=0, velocity=0, seq=1)
        self.assertTrue(self.cmd("drive_pose", **args)["ok"])
        self.assertFalse(self.cmd("drive_pose", **args)["ok"])

    def test_disconnection_parks_car(self):
        self.claim()
        self.r.driver_until = time.monotonic() - 1
        self.assertTrue(h.driver_holds(self.r))
        self.assertIsNone(self.r.driver_owner)
        self.assertEqual(self.r.state, "PARKED")

    def test_old_ocean_config_migration(self):
        w = self.w
        w.cfg = dict(w.cfg)
        w.cfg.update(ocean_center=(-2350, 550), ocean_radii=(900, 1150))
        h.Store.migrate(w)
        self.assertEqual(w.cfg["ocean_radii"], (1080, 1380))
        self.assertEqual(w.cfg["planet_radius"], 4000)


if __name__ == "__main__":
    unittest.main()
