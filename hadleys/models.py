"""models: colony simulation components."""

from __future__ import annotations
from hadleys.enums import TransportKind, TransportState
from typing import Optional

from dataclasses import dataclass, field


@dataclass
class Issue:
    id: int
    kind: str
    target: (
        str  # "span:12", "pole:3", "house:17", "reactor:pump_b", "road:2", "gate:4" ...
    )
    sector: int  # -1 for colony objects
    cause: str
    cost: float
    payer: str  # sector | colony | house
    duration: int  # repair ticks
    pos: tuple
    opened_t: int
    status: str = "open"  # open | funded | in_progress | resolved | unfunded
    severity: str = "warning"
    started_t: int = -1
    resolved_t: int = -1


@dataclass
class Rover:
    name: str
    kind: TransportKind | str  # garbage | sludge | repair | plumber
    x: float = 0.0
    y: float = 0.0
    state: TransportState | str = TransportState.IDLE
    route: list = field(default_factory=list)  # list of (x, y) waypoints
    job: Optional[object] = None  # sector index, house index or Issue
    timer: int = 0
    load: float = 0.0
    speed: float = 14.0
    wait: int = 0
    heading: float = 0.0
    velocity: float = 0.0  # map metres per simulation tick
    odometer_m: float = 0.0
    fuel_l: float = 120.0
