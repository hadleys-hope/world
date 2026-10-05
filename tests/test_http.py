import gzip
import http.client
import json
from pathlib import Path
import threading
import time
import unittest
from hadleys.world import World
from hadleys.api.server import HttpServer, make_handler
from hadleys.api.snapshots import house_geometry
from hadleys.web import ROOT, HTML, HTML3D


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        w = World()
        w.paused = True
        cls.world = w
        cls.server = HttpServer(
            ("127.0.0.1", 0),
            make_handler(
                {"w": w},
                HTML,
                json.dumps(house_geometry(w)),
                None,
                "test-token",
                HTML3D.replace("__THREE_BASE__", "/vendor/three/"),
                str(ROOT / "vendor"),
            ),
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, headers=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        c.request(
            "POST" if body else "GET",
            path,
            json.dumps(body) if body else None,
            headers or {},
        )
        r = c.getresponse()
        result = r.status, dict(r.getheaders()), r.read()
        c.close()
        return result

    def test_all_pages_and_json_endpoints(self):
        for path in ["/", "/flat", "/bus", "/house?id=1", "/graph", "/attractors", "/finance"]:
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn(b"/static/", body)
                self.assertNotIn(b"__THREE_BASE__", body)
                self.assertNotIn(b"NAVHTML", body)
        for path in [
            "/state",
            "/geometry",
            "/bus.json",
            "/house.json?id=1",
            "/attractors.json?hist=1",
            "/finance.json",
            "/water.json",
            "/history",
        ]:
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                json.loads(body)
                # live data is never cached; the geometry is fixed for the server's lifetime and revalidated
                expected = "public, no-cache" if path == "/geometry" else "no-store"
                self.assertEqual(headers["Cache-Control"], expected)

    def test_geometry_is_compressed_and_revalidated(self):
        status, h, body = self.request("/geometry")
        self.assertEqual(status, 200)
        code, gh, compressed = self.request("/geometry", {"Accept-Encoding": "gzip"})
        self.assertEqual(gh["Content-Encoding"], "gzip")
        self.assertEqual(gzip.decompress(compressed), body)
        self.assertLess(len(compressed), len(body) / 3)
        code, _, cached = self.request("/geometry", {"If-None-Match": h["ETag"]})
        self.assertEqual(code, 304)
        self.assertFalse(cached)

    def test_state_is_built_once_per_tick(self):
        from unittest import mock
        import hadleys.api.server as server

        with mock.patch.object(server, "snapshot", wraps=server.snapshot) as build:
            with self.world.lock:
                self.world.t += 1  # whatever an earlier test cached is stale now
            first = self.request("/state")[2]
            second = self.request("/state")[2]
            self.assertEqual(first, second)
            self.assertEqual(build.call_count, 1, "same tick, nothing changed: served from the cache")
            with self.world.lock:
                self.world.t += 1
            self.request("/state")
            self.assertEqual(build.call_count, 2, "a new tick builds a new snapshot")

    def test_burst_of_module_requests_is_not_delayed(self):
        # Behind Caddy the 3D view opens ~60 upstream connections at once; with the default backlog of 5 the
        # kernel dropped most of them and they came back after a 1 s retransmit.
        results, latencies = [], []

        def fetch():
            started = time.monotonic()
            c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
            c.request("GET", "/static/js/map3d/main.js")
            r = c.getresponse()
            r.read()
            results.append(r.status)
            latencies.append(time.monotonic() - started)

        threads = [threading.Thread(target=fetch) for _ in range(60)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results, [200] * 60)
        self.assertLess(max(latencies), 0.9)

    def test_static_gzip_conditional_cache_and_mime(self):
        for path, mime in [
            ("/static/js/map3d/main.js", "text/javascript"),
            ("/static/css/map3d.css", "text/css"),
            ("/vendor/three/build/three.module.js", "text/javascript"),
        ]:
            with self.subTest(path=path):
                status, h, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(h["Content-Type"], mime)
                code, gh, compressed = self.request(path, {"Accept-Encoding": "gzip"})
                self.assertEqual(gzip.decompress(compressed), body)
                self.assertLess(len(compressed), len(body))
                code, _, cached = self.request(path, {"If-None-Match": h["ETag"]})
                self.assertEqual(code, 304)
                self.assertFalse(cached)
                self.assertEqual(
                    self.request(path, {"Accept-Encoding": "gzip;q=0"})[2], body
                )

    def test_path_containment(self):
        for path in [
            "/static/../../hadleys_hope.py",
            "/static/%2e%2e/%2e%2e/hadleys_hope.py",
            "/static/%2fetc/passwd",
            "/vendor/../hadleys_hope.py",
        ]:
            self.assertEqual(self.request(path)[0], 404, path)

    def test_admin_authorization_is_preserved(self):
        self.assertEqual(self.request("/cmd", body={"cmd": "pause"})[0], 403)
        self.assertEqual(
            self.request("/cmd", body={"cmd": "pause", "token": "test-token"})[0], 200
        )
        self.assertFalse(self.world.paused)
