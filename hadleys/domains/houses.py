"""domains / houses: colony simulation components."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import numpy as np
from hadleys.numerics import euler_step
from hadleys.domains.hydraulics import hydraulic_step


def houses_decide(w: World):
    """House brains. Houses with a fresh external controller (runtime over MQTT) use its decisions;
    the rest run the built-in thermostat. This is where libhopevm plugs in."""
    c = w.cfg
    ext = (w.t - w.h_ctrl_t) < 15
    target = np.full(w.N, c["comfort_c"])
    target[w.h_on_ups | (w.h_limit_w > 0)] = c["eco_c"]
    target[(w.h_limit_w > 0) & (w.h_limit_w <= c["limit_level5_w"])] = c["antifreeze_c"]
    on = w.h_heater_on.copy()
    on[w.h_t_in < target - 0.5] = True
    on[w.h_t_in > target + 0.5] = False
    valve = ~w.h_burst
    appl = np.ones(w.N, dtype=bool)
    # external decisions override
    target = np.where(ext, w.h_ctrl_target, target)
    on = np.where(ext, w.h_ctrl_heater, on)
    valve = np.where(ext, w.h_ctrl_valve & ~w.h_burst, valve)
    appl = np.where(ext, w.h_ctrl_appl, appl)
    # hard limits the grid enforces regardless of the program: heater cannot exceed the limit budget
    w.h_target = target
    w.h_heater_on = on
    w.h_valve_open = valve
    w.h_appliances_on = appl
    w.h_ext = ext


def houses_demand(w: World):
    c = w.cfg
    night = w.is_night()
    base = w.h_base_w * (0.6 if night else 1.0) + w.rng.uniform(-50, 50, w.N)
    base = np.maximum(base, 80.0)
    base = np.where(
        w.h_appliances_on, base, 100.0
    )  # program switched appliances off: fridge only
    heater = np.where(w.h_heater_on, w.h_heater_w, 0.0)
    aeration = np.where(w.h_aeration_ok, c["aeration_w"], 0.0)
    want = base + heater + aeration
    limit = w.h_limit_w
    lim = np.where(limit > 0, limit, 1e9)
    essential = aeration + 100.0
    heat_alloc = np.minimum(heater, np.maximum(0.0, lim - essential))
    rest = np.minimum(base - 100.0, np.maximum(0.0, lim - essential - heat_alloc))
    draw = np.minimum(essential + heat_alloc + rest, want)
    return draw, heat_alloc


def houses_step(w: World):
    c = w.cfg
    dt = c["tick_seconds"]
    ua_eff = w.h_ua * (1.0 + 0.006 * w.wind)
    q_loss = ua_eff * (w.h_t_in - w.t_out)
    q_int = (w.h_draw_w - w.h_heat_w) * 0.8 + w.h_residents * 80.0
    w.h_t_in[:] = euler_step(w.h_t_in, w.h_heat_w + q_int - q_loss, dt, w.h_cap)
    cold = w.h_t_in < 0.0
    w.h_frozen = np.where(cold, w.h_frozen + 1, 0)
    w.h_pipes_ok[(w.h_t_in > 3.0) & ~w.h_burst] = True
    newly_frozen = (w.h_frozen == c["freeze_ticks_to_frozen"]) & w.h_pipes_ok
    for i in np.flatnonzero(newly_frozen):
        w.h_pipes_ok[i] = False
        w.log("WARN", f"House {i + 1}: pipes frozen")
    burst_now = (
        w.h_frozen == c["freeze_ticks_to_frozen"] + c["frozen_ticks_to_burst"]
    ) & ~w.h_burst
    for i in np.flatnonzero(burst_now):
        w.h_burst[i] = True
        cost_mul = 0.5 if not w.h_valve_open[i] else 1.0
        iss = w.open_issue(
            "pipes_burst",
            f"house:{i}",
            int(w.h_sector[i]),
            "freeze",
            "pipes",
            (float(w.h_x[i]), float(w.h_y[i])),
            "critical",
        )
        iss.cost *= cost_mul
    hydraulic_step(w)


def house_events(w: World):
    """Log state transitions per house in plain words; sample temperature history every 10 minutes."""
    cur = {
        "power": w.h_power_ok.copy(),
        "ups": w.h_on_ups.copy(),
        "water": w.h_water_ok.copy(),
        "net": w.h_net_online.copy(),
        "pipes": w.h_pipes_ok.copy(),
        "burst": w.h_burst.copy(),
        "limit": (w.h_limit_w > 0).copy(),
        "heater": w.h_heater_on.copy(),
        "target": w.h_target.copy(),
        "prog": list(w.h_program),
        "reason": list(w.h_reason),
    }
    prev = w.h_prev
    if prev is not None:
        texts = {
            "power": ("power restored", "power lost"),
            "ups": ("back on the grid", "running on the sector UPS"),
            "water": ("water supply restored", "no water"),
            "net": ("network link up", "network link lost"),
            "pipes": ("pipes thawed or repaired", "pipes frozen"),
            "burst": ("pipes repaired", "pipes burst"),
            "limit": ("power limit lifted", "power limit imposed by the grid"),
        }
        for key, (up, down) in texts.items():
            changed = np.flatnonzero(cur[key] != prev[key])
            for i in changed:
                w.h_log[i].appendleft((w.t, up if cur[key][i] else down))
        ext = getattr(w, "h_ext", np.zeros(w.N, dtype=bool))
        for i in range(w.N):
            if ext[i] and (
                cur["reason"][i] != prev["reason"][i]
                or abs(cur["target"][i] - prev["target"][i]) > 0.1
            ):
                text = f"{cur['prog'][i]}: {cur['reason'][i]} (target {cur['target'][i]:.1f} C)"
                if not w.h_log[i] or w.h_log[i][0][1] != text:
                    w.h_log[i].appendleft((w.t, text))
    w.h_prev = cur
    if w.t % 10 == 0:
        w.h_hist[:, w.h_hist_i] = w.h_t_in
        w.h_hist_draw[:, w.h_hist_i] = w.h_draw_w
        w.h_hist_i = (w.h_hist_i + 1) % w.h_hist.shape[1]
