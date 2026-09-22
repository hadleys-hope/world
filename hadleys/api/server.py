"""api / server: colony simulation components."""

from __future__ import annotations
from typing import Optional

import json
import os
from hadleys.api.snapshots import bus_snapshot, house_snapshot, snapshot
from hadleys.domains.attractors import attractor_snapshot
from hadleys.domains.energy import reactor_scram
from hadleys.numerics import clamp
from hadleys.simulation import inject, new_colony
from hadleys.web import HTMLATTR, HTMLBUS, HTMLGRAPH, HTMLHOUSE

from hadleys.web import STATIC_ROOT
from hadleys.api.static import serve_asset


def make_handler(
    w_holder: dict,
    html: str,
    geom_json: str,
    store: Optional[Store],
    admin_token: str,
    html3d: str = "",
    vendor_dir: str = "",
):
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, ctype, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if (
                self.path == "/"
                or self.path.startswith("/index")
                or self.path.startswith("/?")
            ):
                self._send(
                    200, "text/html; charset=utf-8", (html3d or html).encode("utf-8")
                )
            elif self.path.startswith("/flat"):
                self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
            elif self.path.startswith("/static/"):
                serve_asset(self, STATIC_ROOT, "/static/")
            elif self.path.startswith("/vendor/") and vendor_dir:
                serve_asset(self, vendor_dir, "/vendor/")
            elif self.path.startswith("/geometry"):
                self._send(200, "application/json", geom_json.encode("utf-8"))
            elif self.path.startswith("/state"):
                w = w_holder["w"]
                with w.lock:
                    body = json.dumps(snapshot(w)).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path.startswith("/house.json"):
                w = w_holder["w"]
                try:
                    hid = int(
                        clamp(
                            int(self.path.split("id=")[1].split("&")[0]) - 1, 0, w.N - 1
                        )
                    )
                except (IndexError, ValueError):
                    hid = 0
                with w.lock:
                    body = json.dumps(house_snapshot(w, hid)).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path.startswith("/house"):
                self._send(200, "text/html; charset=utf-8", HTMLHOUSE.encode("utf-8"))
            elif self.path.startswith("/attractors.json"):
                w = w_holder["w"]
                with w.lock:
                    body = json.dumps(
                        attractor_snapshot(w, "hist=1" in self.path)
                    ).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path.startswith("/attractors"):
                self._send(200, "text/html; charset=utf-8", HTMLATTR.encode("utf-8"))
            elif self.path.startswith("/graph"):
                self._send(200, "text/html; charset=utf-8", HTMLGRAPH.encode("utf-8"))
            elif self.path.startswith("/bus.json"):
                w = w_holder["w"]
                with w.lock:
                    body = json.dumps(bus_snapshot(w)).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path.startswith("/bus"):
                self._send(200, "text/html; charset=utf-8", HTMLBUS.encode("utf-8"))
            elif self.path.startswith("/history"):
                hours = 720
                if "hours=" in self.path:
                    try:
                        hours = int(
                            clamp(
                                int(self.path.split("hours=")[1].split("&")[0]),
                                1,
                                24 * 365,
                            )
                        )
                    except ValueError:
                        pass
                body = json.dumps(
                    store.history(hours) if store else {"hourly": [], "reports": []}
                ).encode("utf-8")
                self._send(200, "application/json", body)
            else:
                self._send(404, "text/plain", b"not found")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n) if n else b"{}"
            try:
                req = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                req = {}
            cmd = req.get("cmd", "")
            w = w_holder["w"]
            if cmd == "auth":
                ok = (not admin_token) or req.get("token", "") == admin_token
                self._send(
                    200,
                    "application/json",
                    json.dumps({"ok": ok, "protected": bool(admin_token)}).encode(),
                )
                return
            if admin_token and req.get("token", "") != admin_token:
                self._send(
                    403,
                    "application/json",
                    b'{"ok": false, "error": "admin token required"}',
                )
                return
            with w.lock:
                if cmd == "pause":
                    w.paused = not w.paused
                elif cmd == "speed":
                    w.speed = int(clamp(int(req.get("value", 20)), 0, 600))
                    if w.speed == 0:
                        w.paused = True
                    elif w.paused:
                        w.paused = False
                elif cmd == "inject":
                    info = inject(w, req.get("value", "")) or {}
                    self._send(
                        200,
                        "application/json",
                        json.dumps({"ok": True, **info}).encode(),
                    )
                    return
                elif cmd == "reset":
                    w = new_colony(w_holder, "operator")
                elif cmd == "reactor":
                    v = req.get("value", "")
                    if v == "scram":
                        reactor_scram(w, "operator")
            self._send(200, "application/json", b'{"ok": true}')

    return Handler
