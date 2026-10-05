"""Contract-level MQTT round trip without a broker or network access."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest
from hadleys.world import World
from hadleys.integrations.mqtt import MqttBridge
from hadleys.controllers.runtime import Runtime
from hadleys.domains.houses import houses_decide


class MqttContractTests(unittest.TestCase):
    def test_sensors_controller_actuators_round_trip(self):
        world_client = MagicMock()
        house_client = MagicMock()
        with patch("paho.mqtt.client.Client", side_effect=[world_client, house_client]):
            w = World()
            bridge = MqttBridge(w, "localhost:1883")
            runtime = Runtime("localhost:1883", {"0": "eco"}, 300, False)
            bridge.connected = True
            bridge.publish()
            messages = world_client.publish.call_args_list
            self.assertTrue(
                any(
                    c.args[0] == "hh/house/0/sensors" and c.kwargs.get("retain")
                    for c in messages
                )
            )
            for call in messages:
                topic, data = call.args[:2]
                if topic in {"hh/env/weather", "hh/env/power", "hh/house/0/sensors"}:
                    runtime.on_message(
                        house_client,
                        None,
                        SimpleNamespace(topic=topic, payload=data.encode()),
                    )
            topic, data = house_client.publish.call_args.args[:2]
            self.assertEqual(topic, "hh/house/0/actuators")
            self.assertEqual(json.loads(data)["program"], "eco")
            bridge._on_message(
                world_client, None, SimpleNamespace(topic=topic, payload=data.encode())
            )
            bridge.apply()
            houses_decide(w)
            self.assertTrue(w.h_ext[0])
            self.assertEqual(w.h_program[0], "eco")
            self.assertEqual(w.h_target[0], json.loads(data)["target_c"])

    def test_periodic_refresh_is_spread_over_ticks(self):
        """Unchanged houses are resent every 10 ticks each, a tenth of them per tick, never all on one tick."""
        client = MagicMock()
        with patch("paho.mqtt.client.Client", return_value=client):
            w = World()
            bridge = MqttBridge(w, "localhost:1883")
        bridge.connected = True
        bridge.publish()  # after a connect everything goes out once
        self.assertEqual(bridge.sent, w.N)
        last = {}
        for _ in range(30):
            w.t += 1  # nothing in the houses changes
            before = bridge.sent
            client.publish.reset_mock()
            bridge.publish()
            self.assertEqual(bridge.sent - before, w.N // 10)
            for c in client.publish.call_args_list:
                if c.args[0].endswith("/sensors"):
                    hid = int(c.args[0].split("/")[2])
                    if hid in last:
                        self.assertEqual(w.t - last[hid], 10)
                    last[hid] = w.t
        self.assertEqual(len(last), w.N)


class BatchedBusTests(unittest.TestCase):
    def test_houses_due_in_a_tick_go_out_as_one_message_of_columns(self):
        client = MagicMock()
        with patch("paho.mqtt.client.Client", return_value=client):
            w = World()
            bridge = MqttBridge(w, "localhost:1883", batch=True)
        bridge.connected = True
        bridge.publish()  # after a connect every house is due
        batches = [c for c in client.publish.call_args_list if c.args[0] == "hh/batch/sensors"]
        self.assertEqual(len(batches), 1)
        self.assertFalse(any(c.args[0].startswith("hh/house/") for c in client.publish.call_args_list))
        cols = json.loads(batches[0].args[1])
        self.assertEqual(cols["id"], list(range(w.N)))
        self.assertEqual(cols["t_in"][7], round(float(w.h_t_in[7]), 1))
        self.assertEqual(cols["pipes_ok"][7], bool(w.h_pipes_ok[7]))
        self.assertEqual(bridge.sent, w.N)
        client.publish.reset_mock()
        w.t += 1
        bridge.publish()
        cols = json.loads(next(c for c in client.publish.call_args_list if c.args[0] == "hh/batch/sensors").args[1])
        self.assertEqual(len(cols["id"]), w.N // 10, "then a tenth of the houses per tick, as per house")

    def test_batched_actuators_are_applied_like_single_ones(self):
        with patch("paho.mqtt.client.Client", return_value=MagicMock()):
            w = World()
            bridge = MqttBridge(w, "localhost:1883", batch=True)
        rows = [
            {"id": 3, "t": 0, "heater_on": False, "target_c": 15.0, "valve_open": True, "appliances_on": True,
             "program": "eco", "reason": "eco night 15"},
            {"id": 9, "t": 0, "heater_on": True, "target_c": 21.0, "valve_open": True, "appliances_on": False,
             "program": "comfort", "reason": "comfort 21"},
        ]
        msg = SimpleNamespace(topic="hh/batch/actuators", payload=json.dumps({"rows": rows}).encode())
        bridge._on_message(None, None, msg)
        bridge.apply()
        houses_decide(w)
        self.assertEqual(bridge.received, 2)
        self.assertTrue(w.h_ext[3] and w.h_ext[9])
        self.assertEqual((w.h_program[3], w.h_target[3]), ("eco", 15.0))
        self.assertEqual((w.h_program[9], bool(w.h_ctrl_appl[9])), ("comfort", False))
