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
