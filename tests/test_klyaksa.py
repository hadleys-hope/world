"""Klyaksa: dome cities with global house ids, a batched bus that routes answers to the right city."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from hadleys.klyaksa import CITIES, Colony, ColonyBus

SMALL = [("a", "A", 50, 10, (0, 0)), ("b", "B", 20, 10, (2000, 0))]


class KlyaksaTests(unittest.TestCase):
    def test_full_colony_has_about_5000_houses(self):
        total = sum(6 * hps for _, _, hps, _, _ in CITIES)
        self.assertGreaterEqual(total, 5000)

    def test_ids_are_global_and_contiguous(self):
        c = Colony(SMALL, first_id=300)
        self.assertEqual([x.offset for x in c.cities], [300, 600])
        self.assertEqual(c.houses, 300 + 120)
        c.tick(2)
        self.assertTrue(all(x.w.t == 2 for x in c.cities))
        g = json.loads(c.geometry())
        self.assertEqual([len(x["x"]) for x in g["cities"]], [300, 120])
        s = json.loads(c.state())
        self.assertEqual(len(s["cities"][1]["t_in"]), 120)

    def test_batches_out_and_answers_routed_by_id(self):
        client = MagicMock()
        with patch("paho.mqtt.client.Client", return_value=client):
            c = Colony(SMALL, first_id=300)
            bus = ColonyBus(c, "localhost:1883")
        c.tick(1)
        sent = [json.loads(call.args[1]) for call in client.publish.call_args_list]
        self.assertEqual({m["city"] for m in sent}, {"a", "b"})
        self.assertTrue(all(i >= 300 for m in sent for i in m["id"]))
        rows = [{"id": 305, "target_c": 19.0, "heater_on": True, "program": "eco"}, {"id": 610, "target_c": 23.0, "program": "comfort"}, {"id": 5, "target_c": 1.0}]
        bus._on_message(None, None, SimpleNamespace(payload=json.dumps({"rows": rows}).encode()))
        c.tick(1)
        a, b = c.cities
        self.assertEqual((a.w.h_program[5], a.w.h_ctrl_target[5]), ("eco", 19.0))
        self.assertEqual((b.w.h_program[10], b.w.h_ctrl_target[10]), ("comfort", 23.0))
        self.assertEqual(bus.received, 2, "id 5 belongs to LV-426, not to Klyaksa")


if __name__ == "__main__":
    unittest.main()


class CityPagesTests(unittest.TestCase):
    def test_every_endpoint_serves_the_city_asked_for(self):
        import http.client
        import threading
        from hadleys.api.server import HttpServer, make_handler
        from hadleys.web import HTML
        from hadleys.world import World

        w = World()
        colony = Colony(SMALL, first_id=300)
        holder = {"w": w, "colony": colony}
        srv = HttpServer(("127.0.0.1", 0), make_handler(holder, HTML, "{}", None, "", HTML, None))
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        def get(path):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
            c.request("GET", path)
            r = c.getresponse()
            return r.status, r.read()

        try:
            cities = json.loads(get("/cities.json")[1])
            self.assertEqual([c["id"] for c in cities], ["", "a", "b"])
            self.assertEqual(len(json.loads(get("/state")[1])["houses"]["t"]), 300)
            self.assertEqual(len(json.loads(get("/state?city=b")[1])["houses"]["t"]), 120)
            self.assertEqual(len(json.loads(get("/geometry?city=a")[1])["houses"]["x"]), 300)
            bus = json.loads(get("/bus.json?city=b")[1])
            self.assertEqual(len(bus["houses"]), 120)
            self.assertTrue(bus["mqtt"]["enabled"])
            self.assertEqual(get("/finance.json?city=a")[0], 200)
            self.assertEqual(get("/programs")[0], 200)
            self.assertEqual(json.loads(get("/programs.json")[1])["programs"], [])
        finally:
            srv.shutdown()

    def test_cities_are_saved_and_restored(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            c = Colony(SMALL, first_id=300, data_dir=d)
            c.tick(3)
            c.save()
            again = Colony(SMALL, first_id=300, data_dir=d)
            self.assertEqual([x.w.t for x in again.cities], [3, 3])
            self.assertIsNotNone(again.cities[0].w.bridge, "a restored city gets its bus view back")
