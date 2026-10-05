"""api / server: colony simulation components."""

from __future__ import annotations
from typing import Optional

import gzip
import hashlib
import json
import os
from http.server import ThreadingHTTPServer
from hadleys.api.snapshots import bus_snapshot, house_snapshot, snapshot, water_json
from hadleys.domains.attractors import attractor_snapshot
from hadleys.domains.households import finance_snapshot
from hadleys.domains.energy import reactor_scram
from hadleys.domains.driving import driver_command
from hadleys.numerics import clamp
from hadleys.simulation import inject, new_colony
from hadleys.web import HTMLATTR, HTMLBUS, HTMLFINANCE, HTMLGRAPH, HTMLHOUSE

from hadleys.web import STATIC_ROOT
from hadleys.api.static import accepts_gzip, serve_asset


class HttpServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a listen backlog that fits the 3D view.

    Behind Caddy the browser's ~60 module requests arrive as ~60 simultaneous upstream connections. The default
    backlog of 5 overflowed, the kernel dropped the rest and they came back after 1 s, 3 s, 7 s.
    """

    request_queue_size = 128


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

    geom_body = geom_json.encode("utf-8")
    geom = {
        "body": geom_body,
        "gzip": gzip.compress(geom_body, compresslevel=6, mtime=0),
        "etag": '"' + hashlib.sha256(geom_body).hexdigest()[:32] + '"',
    }
    # /state is built at most once per (world, tick, change): every viewer polls it every 300 ms, and building it
    # holds the world lock. Operator commands bump "changes", so their effect shows before the next tick.
    state_cache = {"key": None, "body": b""}
    changes = [0]

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

        def _send_geometry(self):
            """The colony geometry never changes while the server runs: compressed once, revalidated by ETag."""
            if self.headers.get("If-None-Match", "") == geom["etag"]:
                self.send_response(304)
                self.send_header("ETag", geom["etag"])
                self.send_header("Cache-Control", "public, no-cache")
                self.end_headers()
                return
            zipped = accepts_gzip(self.headers.get("Accept-Encoding", ""))
            body = geom["gzip"] if zipped else geom["body"]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("ETag", geom["etag"])
            self.send_header("Cache-Control", "public, no-cache")
            self.send_header("Vary", "Accept-Encoding")
            if zipped:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
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
                self._send_geometry()
            elif self.path.startswith("/state"):
                w = w_holder["w"]
                with w.lock:
                    key = (id(w), w.t, changes[0])
                    if state_cache["key"] != key:
                        state_cache["body"] = json.dumps(snapshot(w)).encode("utf-8")
                        state_cache["key"] = key
                    body = state_cache["body"]
                self._send(200, "application/json", body)
            elif self.path.startswith("/clock.json"):
                # the shared top bar on every 2D page: a few bytes instead of the whole /state
                w = w_holder["w"]
                with w.lock:
                    clock = {"t": w.t, "time": w.time_str(), "speed": w.speed, "paused": w.paused}
                self._send(200, "application/json", json.dumps(clock).encode("utf-8"))
            elif self.path.startswith("/water.json"):
                w = w_holder["w"]
                with w.lock:
                    body = json.dumps(water_json(w)).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path.startswith("/finance.json"):
                w = w_holder["w"]
                with w.lock:
                    body = json.dumps(finance_snapshot(w)).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path.startswith("/finance"):
                self._send(200, "text/html; charset=utf-8", HTMLFINANCE.encode("utf-8"))
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
            changes[0] += 1  # an operator or driver command may change what /state shows before the next tick
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
                if cmd in ("drive_claim", "drive_pose", "drive_release"):
                    result = driver_command(w, req)
                    self._send(
                        200 if result["ok"] else 409,
                        "application/json",
                        json.dumps(result).encode(),
                    )
                    return
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
