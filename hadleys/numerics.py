"""numerics: colony simulation components."""

from __future__ import annotations

import math


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def polar(angle_deg, radius):
    a = math.radians(angle_deg)
    return radius * math.cos(a), radius * math.sin(a)


def euler_step(value, net_rate, dt, capacity=1.0):
    """One explicit Euler step; scalars or NumPy arrays, seconds and SI units.

    Thermal balance: temperature + (watts * seconds / joules-per-kelvin).
    No solver or time-step change is introduced by the module extraction.
    """
    return value + net_rate * dt / capacity
