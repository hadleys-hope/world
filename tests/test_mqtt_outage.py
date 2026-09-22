"""A broker outage must not block the world lock used by the HTTP state API."""

import http.client
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import MagicMock, patch
from hadleys.api.server import make_handler
from hadleys.integrations.mqtt import MqttBridge
from hadleys.simulation import world_tick
from hadleys.world import World


class MqttOutageTests(unittest.TestCase):
    def test_state_remains_available_during_slow_broker_connection(self):
        release = threading.Event()
        entered = threading.Event()
        completed = threading.Event()
        client = MagicMock()

        def slow_reconnect():
            entered.set()
            release.wait(5)
            raise OSError("simulated unavailable broker")

        client.reconnect.side_effect = slow_reconnect
        with patch("paho.mqtt.client.Client", return_value=client):
            w = World()
            w.bridge = MqttBridge(w, "unavailable.invalid:1883")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), make_handler({"w": w}, "", "{}", None, "")
            )
            serving = threading.Thread(target=server.serve_forever, daemon=True)
            serving.start()

            def tick():
                with w.lock:
                    world_tick(w)
                completed.set()

            ticking = threading.Thread(target=tick, daemon=True)
            ticking.start()
            conn = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=0.5
            )
            try:
                # Old code enters synchronous reconnect; fixed code finishes the tick.
                for _ in range(50):
                    if entered.is_set() or completed.wait(0.01):
                        break
                conn.request("GET", "/state")
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                state = json.loads(response.read())
                self.assertFalse(state["control"]["mqtt"]["connected"])
                client.reconnect.assert_not_called()
                client.loop_start.assert_called_once()
            finally:
                release.set()
                ticking.join(2)
                conn.close()
                server.shutdown()
                server.server_close()
                serving.join(2)
