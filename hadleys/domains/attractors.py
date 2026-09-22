"""domains / attractors: colony simulation components."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import numpy as np


def attractor_sample(w: World):
    c = w.cfg
    ups_cap = c["ups_sector_kwh"] * w.S + c["ups_center_kwh"]
    ups = (float(w.ups_kwh.sum()) + float(w.ups_center_kwh)) / ups_cap
    opened = sum(1 for i in w.issues if i.status != "resolved")
    frozen = int((~w.h_pipes_ok & ~w.h_burst).sum())
    w.attr_fast.append(
        (
            w.t,
            round(w.water_tank_m3, 1),
            round(w.water_plant_m3_h, 2),
            round(w.water_flow_m3_h, 2),
            round(w.available_kw),
            round(w.demand_kw),
            round(ups, 3),
            int(w.shedding),
            opened,
            int(w.h_burst.sum()),
            frozen,
            round(w.colony_budget),
            round(float(w.sector_budget.sum())),
            round(float(w.mine_frac), 2),
        )
    )
    if len(w.attr_fast) > 720:
        del w.attr_fast[: len(w.attr_fast) - 720]
    if w.t % 360 == 0:
        w.attr_slow.append(
            (
                w.t,
                round(w.colony_budget),
                round(float(w.sector_budget.sum())),
                round(w.colony_budget + w.levy_total),
            )
        )
        if len(w.attr_slow) > 240:
            del w.attr_slow[: len(w.attr_slow) - 240]


FAST_KEYS = [
    "t",
    "tank",
    "water_in",
    "water_use",
    "avail_kw",
    "demand_kw",
    "ups",
    "shedding",
    "open",
    "burst",
    "frozen",
    "colony",
    "sectors",
    "mine",
]


def _houses_attractors(w: World):
    ua = w.h_ua * (1.0 + 0.006 * w.wind)
    q_now = (w.h_draw_w - w.h_heat_w) * 0.8 + w.h_residents * 80.0
    rate = (
        (w.h_heat_w + q_now - ua * (w.h_t_in - w.t_out)) / w.h_cap * 3600.0
    )  # C per hour, same law as houses_step
    q_int = q_now
    nonheater = np.maximum(0.0, w.h_draw_w - w.h_heat_w)
    p_on = np.where(
        w.h_power_ok,
        np.where(
            w.h_limit_w > 0,
            np.clip(w.h_limit_w - nonheater, 0, w.h_heater_w),
            w.h_heater_w,
        ),
        0.0,
    )
    eq_on = (
        w.t_out + (p_on + q_int) / ua
    )  # where the house settles with the heater always on
    eq_off = w.t_out + q_int / ua  # ... and with it always off
    tau_h = w.h_cap / ua / 3600.0  # how fast it gets there, hours
    target = w.h_target
    att = np.clip(target, eq_off, eq_on)
    basin = np.where(
        w.h_burst,
        3,
        np.where(np.abs(att - target) <= 1.0, 0, np.where(att >= 0.0, 1, 2)),
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        ttf = np.where(
            (basin == 2) & (w.h_t_in > 0),
            tau_h * np.log((w.h_t_in - eq_on) / (0.0 - eq_on)),
            -1.0,
        )
    return {
        "t": np.round(w.h_t_in, 2).tolist(),
        "rate": np.round(rate, 3).tolist(),
        "eq_on": np.round(eq_on, 1).tolist(),
        "eq_off": np.round(eq_off, 1).tolist(),
        "tau": np.round(tau_h, 1).tolist(),
        "target": np.round(target, 1).tolist(),
        "att": np.round(att, 1).tolist(),
        "basin": basin.tolist(),
        "ttf": np.round(np.nan_to_num(ttf, nan=-1.0), 1).tolist(),
        "sector": w.h_sector.tolist(),
        "pressure_kpa": np.round(w.utilities.pressure, 2).tolist(),
        "water_l_min": np.round(
            w.utilities.delivered * 60000 / w.cfg["tick_seconds"], 4
        ).tolist(),
        "counts": [int((basin == k).sum()) for k in range(4)],
        "first_freeze_h": (
            round(float(ttf[ttf > 0].min()), 1) if (ttf > 0).any() else -1
        ),
    }


def attractor_snapshot(w: World, with_hist: bool):
    c = w.cfg
    fast = w.attr_fast
    day = [r for r in fast if r[0] > w.t - c["ticks_per_day"]] or fast[-1:]

    # water: plant throttles as the tank fills, so inflow = use has one solution
    use = sum(r[3] for r in day) / len(day) if day else w.water_flow_m3_h
    nominal, cap = c["water_plant_m3_h"], c["water_tank_m3"]
    ice = max(0, -w.t_out) if w.t_out < -2 else 0
    melt_kwh_m3 = (2.1 * ice + (334 if ice else 0) + 4.18 * 5) / 3.6
    vmax = min(
        nominal,
        w.water_heat_available_kw / max(melt_kwh_m3, 1e-9) * c["water_recovery"],
    )
    if not w.water_plant_ok:
        v_star = 0.0
    elif use <= 0.15 * nominal and use < vmax:
        v_star = cap
    elif use < vmax:
        v_star = cap - 60.0 * use / nominal
    else:
        v_star = 0.0
    runway_w = w.water_tank_m3 / use if use > 0 else -1
    if not w.water_plant_ok:
        wv = ("bad", f"plant down: tank drains to zero, {runway_w:.0f} h left")
    elif v_star < 0.3 * cap:
        wv = (
            "warn",
            f"use {use:.1f} m3/h is close to plant capacity, tank settles low",
        )
    else:
        wv = (
            "ok",
            f"settles at {v_star:.0f} m3 with a daily loop; {runway_w:.0f} h of water if the plant stops",
        )

    # power
    margin = w.available_kw - w.demand_kw
    ups_cap = c["ups_sector_kwh"] * w.S + c["ups_center_kwh"]
    ups_kwh = float(w.ups_kwh.sum()) + float(w.ups_center_kwh)
    if w.r_mode not in ("ONLINE",):
        pv = (
            "bad" if w.r_mode != "RUNBACK" else "warn",
            f"reactor {w.r_mode}: UPS {ups_kwh:.0f} kWh is the only buffer",
        )
    elif w.shedding > 0:
        pv = (
            "warn",
            f"shedding level {w.shedding}: the grid trades comfort for balance",
        )
    else:
        pv = ("ok", f"margin {margin:.0f} kW, UPS {100 * ups_kwh / ups_cap:.0f}% full")

    # repairs as a queue: arrivals vs what the crews can close
    t0 = w.t - c["ticks_per_day"]
    lam = sum(1 for i in w.issues if i.opened_t > t0)
    done = [i for i in w.issues if i.status == "resolved" and i.started_t >= 0][-30:]
    svc = (sum(i.resolved_t - i.started_t for i in done) / len(done)) if done else 180.0
    crews = sum(1 for r in w.rovers if r.kind in ("repair", "plumber"))
    mu = crews * c["ticks_per_day"] / (svc + 40.0)
    rho = lam / mu if mu > 0 else 9.9
    unfunded = sum(1 for i in w.issues if i.status == "unfunded")
    backlog = len(w.open_issues())
    if unfunded:
        rv = ("bad", f"{unfunded} repairs wait for money: failures pile up")
    elif rho >= 1:
        rv = ("bad", f"load {rho:.2f}: failures arrive faster than crews close them")
    elif rho > 0.7:
        rv = ("warn", f"load {rho:.2f}: queue grows as 1/(1-load)")
    else:
        rv = ("ok", f"load {rho:.2f}: backlog returns to about {rho / (1 - rho):.1f}")

    # money: the company levy pulls the budget toward a fixed point
    slow = w.attr_slow
    tgt, f = c["company_reserve_target"], c["company_levy_frac"]
    net_month = None
    if len(slow) >= 5:
        # the budget as if the company never took anything: the formula needs the flow before the levy
        old = slow[max(0, len(slow) - 121)]
        span_days = (w.t - old[0]) / c["ticks_per_day"]
        gross_old = old[3] if len(old) > 3 else old[1]
        net_month = (
            (w.colony_budget + w.levy_total - gross_old)
            / max(span_days, 0.25)
            * c["days_per_month"]
        )
    burn = c["colony_payroll_day"]
    runway_m = w.colony_budget / burn if w.colony_budget > 0 else 0.0
    b_star = None
    if w.colony_budget < 0:
        mv = ("bad", "in debt: colony repairs are not funded, the loop feeds itself")
    elif net_month is None:
        mv = ("ok", "collecting history")
    elif net_month <= 0:
        mv = (
            "warn",
            f"losing {-net_month:.0f} cr a month, {runway_m:.0f} days of payroll left",
        )
    elif f <= 0:
        mv = (
            "warn",
            "no company levy: positive income has no finite budget equilibrium",
        )
    else:
        b_star = tgt + net_month / f - net_month
        mv = (
            "ok",
            f"settles near {b_star / 1000:.0f}k cr; {runway_m:.0f} days of payroll if income stops",
        )

    out = {
        "time": w.time_str(),
        "t": w.t,
        "t_out": round(w.t_out, 1),
        "wind": round(w.wind, 1),
        "paused": bool(w.paused),
        "speed": w.speed,
        "houses": _houses_attractors(w),
        "water": {
            "tank": round(w.water_tank_m3, 1),
            "cap": cap,
            "in": round(w.water_plant_m3_h, 2),
            "use": round(use, 2),
            "v_star": round(v_star, 1),
            "runway_h": round(runway_w, 1),
            "verdict": wv,
            "max_m3_h": vmax,
            "plant_ok": bool(w.water_plant_ok),
            "leak_m3_h": round(
                float(w.utilities.leaks.sum()) * 3600 / c["tick_seconds"], 4
            ),
        },
        "power": {
            "margin": round(margin),
            "ups": round(ups_kwh / ups_cap, 3),
            "shedding": w.shedding,
            "mode": w.r_mode,
            "verdict": pv,
        },
        "repairs": {
            "lam": lam,
            "mu": round(mu, 1),
            "rho": round(rho, 2),
            "backlog": backlog,
            "unfunded": unfunded,
            "burst": int(w.h_burst.sum()),
            "verdict": rv,
        },
        "money": {
            "colony": round(w.colony_budget),
            "sectors": round(float(w.sector_budget.sum())),
            "target": tgt,
            "levy_frac": f,
            "net_month": None if net_month is None else round(net_month),
            "b_star": None if b_star is None else round(b_star),
            "runway_days": round(runway_m, 1),
            "last_levy": round(w.last_levy),
            "verdict": mv,
        },
    }
    if with_hist:
        out["fast_keys"] = FAST_KEYS
        out["fast"] = fast
        out["slow"] = slow
    return out
