"""Real-time vehicle control leases and validated poses, independent of simulation speed.

The browser integrates chassis dynamics. The server arbitrates ownership,
validates travel and keeps manually parked vehicles out of the autopilot.
"""

from __future__ import annotations
import math
import time
from hadleys.numerics import clamp
from hadleys.enums import TransportState


def driver_holds(r):
    """Manual driving uses a real-time lease; paused colonies still accept controls."""
    if getattr(r, "driver_owner", None) and time.monotonic() > getattr(
        r, "driver_until", 0
    ):
        r.driver_owner = None
        r.driver_parked = True
        r.velocity = 0
        r.state = TransportState.PARKED
    return bool(getattr(r, "driver_owner", None) or getattr(r, "driver_parked", False))


def driver_command(w, req):
    name = req.get("name")
    r = next((r for r in w.rovers + getattr(w, "traffic", []) if r.name == name), None)
    if r is None:
        return {"ok": False, "error": "Vehicle not found"}
    owner = req.get("owner", "")
    if not isinstance(owner, str) or not 16 <= len(owner) <= 80:
        return {"ok": False, "error": "Invalid driving session"}
    driver_holds(r)
    now = time.monotonic()
    cmd = req["cmd"]
    if cmd == "drive_claim":
        if getattr(r, "driver_owner", None) not in (None, owner):
            return {"ok": False, "error": "Vehicle is controlled by another driver"}
        if r.state == TransportState.LOADING:
            return {"ok": False, "error": "Wait until the crane finishes loading"}
        if not driver_holds(r):
            lane = 8.5 if r.state == TransportState.IDLE else 2.2
            r.x -= math.sin(r.heading) * lane
            r.y += math.cos(r.heading) * lane
        r.driver_owner = owner
        r.driver_until = now + 6
        r.driver_pose_at = now
        r.driver_seq = -1
        r.driver_parked = False
        r.velocity = 0
        r.state = TransportState.DRIVING
        r.route = []
        return {
            "ok": True,
            "x": r.x,
            "y": r.y,
            "heading": r.heading,
            "distance": r.odometer_m,
        }
    if getattr(r, "driver_owner", None) != owner:
        return {"ok": False, "error": "Driving session expired"}
    if cmd == "drive_release":
        r.driver_owner = None
        r.driver_parked = True
        r.velocity = 0
        r.state = TransportState.PARKED
        return {"ok": True}
    if cmd != "drive_pose":
        return {"ok": False, "error": "Unknown driving command"}
    try:
        x, y, heading, velocity = [
            float(req[k]) for k in ("x", "y", "heading", "velocity")
        ]
        seq = int(req["seq"])
        if not all(math.isfinite(v) for v in [x, y, heading, velocity]):
            raise ValueError()
        radius = w.cfg.get("planet_radius", 4000)
        distance = math.hypot(x, y)
        if (
            distance > math.pi * radius + 0.1
            or abs(velocity) > 60
            or seq <= r.driver_seq
        ):
            raise ValueError()

        def normal(x, y):
            d = math.hypot(x, y)
            a = d / radius
            p = math.atan2(y, x)
            return (math.sin(a) * math.cos(p), math.cos(a), math.sin(a) * math.sin(p))

        a, b = normal(r.x, r.y), normal(x, y)
        travel = radius * math.acos(clamp(sum(p * q for p, q in zip(a, b)), -1, 1))
        if travel > 65 * min(6, max(0.05, now - r.driver_pose_at)) + 3:
            raise ValueError()
        chassis = {}
        for k, low, high in [
            ("height", -0.2, 150),
            ("pitch", -1.5, 1.5),
            ("roll", -1.5, 1.5),
            ("rpm", 0, 8500),
            ("gear", -1, 6),
            ("steer", -0.7, 0.7),
        ]:
            v = float(req.get("chassis", {}).get(k, 0))
            if not math.isfinite(v):
                raise ValueError()
            chassis[k] = clamp(v, low, high)
    except (KeyError, ValueError, TypeError, OverflowError):
        return {"ok": False, "error": "Invalid vehicle pose"}
    r.x = x
    r.y = y
    r.heading = heading % (math.pi * 2)
    r.velocity = velocity
    r.odometer_m += travel
    r.driver_chassis = chassis
    r.driver_seq = seq
    r.driver_pose_at = now
    r.driver_until = now + 6
    return {"ok": True, "seq": seq}
