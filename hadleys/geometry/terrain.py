"""geometry / terrain: colony simulation components."""

from __future__ import annotations

import math
from hadleys.numerics import clamp

RIVER_PROFILE = [
    (500, 1550, 46),
    (50, 1490, 34),
    (-410, 1250, 23),
    (-900, 1060, 12),
    (-1450, 840, 1),
    (-2050, 740, -8),
]


def coast_height(x, y, height):
    """Shared coastal basin and graded frozen river profile; keep colony terraces intact."""
    if math.hypot(x, y) < 900:
        return height
    q = math.hypot((x + 2450) / 1080, (y - 600) / 1380)
    az = math.atan2((y - 600) / 1380, (x + 2450) / 1080)
    q /= (
        1
        + 0.08 * math.sin(3 * az)
        + 0.05 * math.sin(7 * az)
        + 0.025 * math.sin(11 * az)
    )
    t = clamp((1.10 - q) / 0.16, 0, 1)
    t = t * t * (3 - 2 * t)
    height = height * (1 - t) + (-26 - 22 * max(0, 1 - q * q)) * t
    for a, b in zip(RIVER_PROFILE, RIVER_PROFILE[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        u = clamp(((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy), 0, 1)
        distance = math.hypot(x - a[0] - u * dx, y - a[1] - u * dy)
        t = clamp((95 - distance) / 70, 0, 1)
        t = t * t * (3 - 2 * t)
        target = a[2] + (b[2] - a[2]) * u - 2
        height = height * (1 - t) + target * t
    return height


def site_elevation(x, y, c):
    """Same finished grades as terrainH in the viewer (metres above local datum)."""
    r = math.hypot(x, y)

    def smooth(a, b, v):
        t = clamp((v - a) / (b - a), 0.0, 1.0)
        return t * t * (3 - 2 * t)

    if r < c["hub_radius"]:
        h = 8.0
    elif r < c["house_radius_min"] - 30:
        h = 8 - 3 * smooth(c["hub_radius"], c["house_radius_min"] - 30, r)
    elif r < c["ring_road_radius"]:
        u = (r - (c["house_radius_min"] - 30)) / c["house_ring_step"]
        k = math.floor(u)
        h = 5 + 3.4 * min(c["house_rows"], k + smooth(0.62, 1, u - k))
    elif r < c["wall_radius"] + 20:
        h = 5 + c["house_rows"] * 3.4
    else:
        h = (5 + c["house_rows"] * 3.4) * (
            1 - smooth(c["wall_radius"] + 20, c["wall_radius"] + 260, r)
        )
    # Engineered terraces meet a continuous, rolling basalt landscape.
    natural = (
        22
        + 24 * math.sin(x * 0.0018) * math.cos(y * 0.0024)
        + 14 * math.sin(x * 0.004 + y * 0.001)
    )
    for px, py, height, width in [
        (1250, 850, 180, 280),
        (-450, -1350, 145, 360),
        (-1640, 980, 220, 310),
        (450, 1650, 190, 330),
    ]:
        natural += height * math.exp(-((x - px) ** 2 + (y - py) ** 2) / (width * width))
    blend = smooth(c["wall_radius"] + 20, c["wall_radius"] + 320, r)
    return coast_height(
        x, y, h + blend * natural + 0.5 * math.sin(x * 0.031) * math.cos(y * 0.027)
    )
