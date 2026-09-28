import gzip
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest
from hadleys.world import World
from hadleys.api.server import make_handler
from hadleys.api.snapshots import house_geometry
from hadleys.web import ROOT, HTML, HTML3D


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        w = World()
        w.paused = True
        cls.world = w
        cls.server = ThreadingHTTPServer(
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
        for path in ["/", "/flat", "/bus", "/house?id=1", "/graph", "/attractors"]:
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
            "/history",
        ]:
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                json.loads(body)
                self.assertEqual(headers["Cache-Control"], "no-store")

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

    def test_resident_profiles_are_available_while_indoors(self):
        status, _, body = self.request('/state')
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(len(data['citizens']), 300)
        self.assertEqual(len({c['id'] for c in data['citizens']}), 300)
        self.assertEqual(data['people'], [])
        self.assertTrue(all(c['state'] == 'HOME' and c['indoors'] for c in data['citizens']))
        self.assertEqual({c['workplace'] for c in data['citizens']}, {'garage', 'medlab'})

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

    def test_scheduled_pause_command_requires_auth_and_validates_time(self):
        old = self.world.pause_at, self.world.paused, self.world.speed
        try:
            self.assertEqual(self.request('/cmd', body={'cmd': 'pause_at', 'value': '07:30'})[0], 403)
            self.assertIsNone(self.world.pause_at)
            self.assertEqual(self.request('/cmd', body={'cmd': 'pause_at', 'value': '07:30', 'token': 'test-token'})[0], 200)
            self.assertEqual(self.world.pause_at, 450)
            self.assertFalse(self.world.paused)
            self.assertEqual(json.loads(self.request('/state')[2])['pause_at'], 450)
            self.assertEqual(self.request('/cmd', body={'cmd': 'pause_at', 'value': '25:00', 'token': 'test-token'})[0], 400)
            self.assertEqual(self.world.pause_at, 450)
            self.assertEqual(self.request('/cmd', body={'cmd': 'pause_at', 'value': None, 'token': 'test-token'})[0], 200)
            self.assertIsNone(self.world.pause_at)
        finally:
            self.world.pause_at, self.world.paused, self.world.speed = old
