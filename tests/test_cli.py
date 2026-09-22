"""Actual subprocess entry point, arbitrary cwd, and reset followed by SIGTERM."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from hadleys.world import World
from hadleys.persistence import Store
from hadleys.web import ROOT


class CliTests(unittest.TestCase):
    def test_external_cwd_static_assets_and_current_world_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            old = World()
            old.t = 123
            store.save_world(old)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            env = dict(os.environ, MQTT_URL="", ADMIN_TOKEN="", DATA_DIR=directory)
            p = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "hadleys_hope.py"),
                    "--port",
                    str(port),
                    "--speed",
                    "0",
                ],
                cwd=directory,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                base = f"http://127.0.0.1:{port}"
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(
                            base + "/state", timeout=0.2
                        ) as response:
                            state = json.load(response)
                        break
                    except OSError:
                        if p.poll() is not None:
                            self.fail(p.stderr.read().decode())
                        time.sleep(0.05)
                else:
                    self.fail("Server startup timeout")
                self.assertEqual(state["t"], 123)
                for route in [
                    "/static/js/map3d/main.js",
                    "/vendor/three/build/three.module.js",
                ]:
                    with urllib.request.urlopen(base + route) as response:
                        self.assertEqual(response.status, 200)
                request = urllib.request.Request(
                    base + "/cmd",
                    data=json.dumps({"cmd": "reset"}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.status, 200)
                p.terminate()
                p.wait(timeout=5)
                current = store.load_world()
                self.assertEqual(
                    current.t, 0, "SIGTERM must save the new colony after reset"
                )
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait()
                p.stderr.close()
