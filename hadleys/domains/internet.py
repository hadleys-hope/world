"""domains / internet: colony simulation components."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import numpy as np


def internet_step(w: World):
    c = w.cfg
    S = w.S
    center_ok = w.comms_ok and w.comms_powered
    w.mobile_online = bool(center_ok and w.tower_ok and w.tower_line_ok)
    w.uplink_ok = bool(
        center_ok and w.dish_ok and w.tower_line_ok and w.trunk_ok and w.substation_ok
    )
    for s in range(S):
        if w.sector_online[s] and w.rp_ok[s]:
            w.cabinet_ups_h[s] = min(2.0, w.cabinet_ups_h[s] + 1 / 240)
            powered = True
        else:
            w.cabinet_ups_h[s] = max(0.0, w.cabinet_ups_h[s] - 1 / 60)
            powered = w.cabinet_ups_h[s] > 0
        w.cabinet_online[s] = bool(w.cabinet_ok[s] and powered and center_ok)
    w.net_sector_online = w.cabinet_online
    house_net = (
        w.net_chain[w.h_pole]
        & w.h_terminal_ok
        & w.cabinet_online[w.h_sector]
        & w.h_power_ok
    )
    w.h_net_online = house_net
    w.packets_per_min = int(house_net.sum()) * 2 + (12 if center_ok else 0)
    if w.t % 2 == 0:
        online = np.flatnonzero(house_net)
        if len(online):
            pick = w.rng.choice(online, size=min(4, len(online)), replace=False)
            for i in pick:
                w.packets.append(
                    {
                        "t": w.t,
                        "from": "house",
                        "id": int(i),
                        "sector": int(w.h_sector[i]),
                        "uplink": bool(w.uplink_ok),
                        "kind": "telemetry",
                    }
                )
    if w.t % 5 == 0 and center_ok:
        w.packets.append(
            {
                "t": w.t,
                "from": "hub",
                "id": -1,
                "sector": -1,
                "uplink": bool(w.uplink_ok and w.r_link_ok),
                "kind": "reactor" if w.r_link_ok else "lost",
            }
        )
    w.r_link_ok = center_ok and w.trunk_ok
    w.packets = [p for p in w.packets if w.t - p["t"] < 6]
