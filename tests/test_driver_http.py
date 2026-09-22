import sys, unittest, json, threading, http.client

sys.path.insert(0, ".")
import hadleys_hope as h
from http.server import HTTPServer


class DriverHTTPTests(unittest.TestCase):
    def test_paused_http_control_and_authorization(self):
        w = h.World()
        w.paused = True
        r = w.traffic[0]
        server = HTTPServer(
            ("127.0.0.1", 0),
            h.make_handler(
                {"w": w}, "", json.dumps(h.house_geometry(w)), None, "local-test"
            ),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def post(cmd, **kwargs):
            conn = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=3
            )
            body = dict(cmd=cmd, name=r.name, owner="local-http-owner-123456", **kwargs)
            conn.request(
                "POST", "/cmd", json.dumps(body), {"Content-Type": "application/json"}
            )
            res = conn.getresponse()
            out = res.status, json.loads(res.read())
            conn.close()
            return out

        try:
            self.assertEqual(post("drive_claim")[0], 403)
            self.assertEqual(post("drive_claim", token="local-test")[0], 200)
            self.assertEqual(
                post(
                    "drive_pose",
                    token="local-test",
                    seq=0,
                    x=r.x + 1,
                    y=r.y,
                    heading=0,
                    velocity=1,
                    chassis={},
                )[0],
                200,
            )
            self.assertTrue(w.paused)
            self.assertEqual(post("drive_release", token="local-test")[0], 200)
            self.assertEqual(r.state, "PARKED")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_snapshot_expires_disconnected_driver_during_pause(self):
        import time

        w = h.World()
        w.paused = True
        r = w.traffic[0]
        h.driver_command(
            w, dict(cmd="drive_claim", name=r.name, owner="local-http-owner-123456")
        )
        r.driver_until = time.monotonic() - 1
        state = h.snapshot(w)
        self.assertEqual(r.state, "PARKED")
        self.assertIsNone(r.driver_owner)


if __name__ == "__main__":
    unittest.main()
