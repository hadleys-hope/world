"""domains / energy: colony simulation components."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import numpy as np
from hadleys.domains.houses import houses_decide, houses_demand
from hadleys.numerics import clamp


def reactor_step(w: World):
    c = w.cfg
    nom = c["reactor_gross_mw"]
    ramp = c["ramp_frac_per_min"] * nom
    flow = (0.5 * (w.r_pump_a > 0.2) + 0.5 * (w.r_pump_b > 0.2)) * w.r_hx
    w.r_mode_ticks += 1

    if w.r_mode in ("ONLINE", "RUNBACK"):
        if w.rng.random() < c["p_pump_wear"]:
            which = "pump_b" if w.r_pump_b > 0.2 else "pump_a"
            setattr(w, "r_" + which, 0.1)
            w.open_issue(
                "pump_trip",
                f"reactor:{which}",
                -1,
                "wear",
                "pump",
                c["reactor_pos"],
                "critical",
            )
            w.log("ALARM", f"Reactor {which.upper()} tripped")

    if w.r_mode == "ONLINE" and flow < 0.75:
        w.r_mode = "RUNBACK"
        w.r_mode_ticks = 0
        w.log("ALARM", "Reactor RUNBACK: coolant flow reduced")
    if w.r_mode == "RUNBACK" and flow >= 0.99:
        w.r_mode = "ONLINE"
        w.log("INFO", "Reactor back ONLINE")

    if w.r_mode in ("ONLINE", "RUNBACK"):
        # the operator follows the load: generation tracks demand plus a spinning reserve
        # during load shedding the operator asks for everything the plant can give
        wanted = (
            nom
            if w.shedding > 0
            else w.demand_kw / 1000.0
            + c["reactor_self_mw"]
            + 0.15 * c["heat_export_mw"]
            + c["reserve_mw"]
        )
        w.r_setpoint_mw = clamp(wanted, 0.2 * nom, nom)
        cap = nom * (1.0 if w.r_mode == "ONLINE" else min(1.0, flow / 0.5) * 0.5)
        target = min(w.r_setpoint_mw, cap)
        w.r_power_mw += clamp(target - w.r_power_mw, -ramp, ramp) + w.rng.normal(
            0, 0.004
        )
        w.r_power_mw = clamp(w.r_power_mw, 0.0, nom)
        w.r_decay_mw = 0.0
        thermal = w.r_power_mw / 0.3
        t_eq = 300.0 + 480.0 * (thermal / 20.0) / max(flow, 0.05)
        w.r_core_temp += (t_eq - w.r_core_temp) * 0.05 + w.rng.normal(0, 0.6)
        w.r_core_temp = clamp(w.r_core_temp, 300, 1400)
        w.r_available_mw = max(
            0.0,
            min(cap, w.r_power_mw + ramp)
            - c["reactor_self_mw"]
            - 0.15 * c["heat_export_mw"],
        )
        w.water_plant_heat = True
        if flow < 0.3 or w.r_core_temp > c["core_temp_limit"]:
            reactor_scram(w, "protection: temperature/flow")
    elif w.r_mode in ("SCRAM", "COOLING", "EMERGENCY"):
        w.r_power_mw = 0.0
        w.r_available_mw = 0.0
        w.water_plant_heat = False
        t_since = max(1, (w.t - w.r_shutdown_t) * 60)
        w.r_decay_mw = 0.066 * 20.0 * (t_since**-0.2 - (t_since + 3.0e7) ** -0.2)
        pumps_powered = w.trunk_ok and w.substation_ok
        if not pumps_powered:
            w.r_battery_h = max(0.0, w.r_battery_h - 1 / 60)
        else:
            w.r_battery_h = min(c["pump_battery_h"], w.r_battery_h + 1 / 240)
        flow_now = flow if (pumps_powered or w.r_battery_h > 0) else 0.02 * w.r_hx
        t_eq = 300.0 + 480.0 * (w.r_decay_mw / 20.0) / max(flow_now, 0.002)
        w.r_core_temp += (t_eq - w.r_core_temp) * 0.02
        w.r_core_temp = clamp(w.r_core_temp, 300, 1400)
        if w.r_mode == "SCRAM" and w.r_mode_ticks > 30:
            w.r_mode = "COOLING"
            w.r_mode_ticks = 0
        if w.r_mode == "COOLING":
            if flow_now < 0.05 or w.r_core_temp > c["core_temp_limit"]:
                w.r_mode = "EMERGENCY"
                w.r_mode_ticks = 0
                w.log("ALARM", "Reactor EMERGENCY: heat removal lost")
            elif (
                w.r_core_temp < 400
                and w.r_hx > 0.7
                and flow >= 0.5
                and pumps_powered
                and w.r_mode_ticks > 360
            ):
                w.r_mode = "STARTING"
                w.r_mode_ticks = 0
                w.log("INFO", "Reactor STARTING")
        if w.r_mode == "EMERGENCY":
            if w.r_core_temp > c["core_temp_limit"]:
                w.r_emergency_ticks += 1
                if w.r_emergency_ticks > 240:
                    w.r_mode = "CORE_DAMAGE"
                    w.log("ALARM", "CORE DAMAGE. Simulation over.")
                    w.finished = True
                    w.finish_reason = "Reactor core damage"
            else:
                w.r_emergency_ticks = 0
            if flow_now >= 0.4 and w.r_core_temp < 900:
                w.r_mode = "COOLING"
                w.r_mode_ticks = 0
                w.log("INFO", "Reactor heat removal restored, COOLING")
    elif w.r_mode == "STARTING":
        w.r_power_mw += ramp * 0.5
        w.r_available_mw = max(0.0, w.r_power_mw - c["reactor_self_mw"])
        w.water_plant_heat = w.r_power_mw > 2.0
        w.r_core_temp += (c["core_temp_nominal"] - w.r_core_temp) * 0.02
        if w.r_power_mw >= nom * 0.5:
            w.r_mode = "ONLINE"
            w.r_mode_ticks = 0
            w.log("INFO", "Reactor ONLINE")
    elif w.r_mode == "CORE_DAMAGE":
        w.r_available_mw = 0.0
    w.r_flow = flow
    w.r_coolant_temp = 300.0 + (w.r_core_temp - 300.0) * 0.35
    w.r_faults = [
        f
        for f, ok in (
            ("PUMP_A_TRIP", w.r_pump_a > 0.2),
            ("PUMP_B_TRIP", w.r_pump_b > 0.2),
            ("HEAT_EXCHANGER_DAMAGE", w.r_hx > 0.7),
        )
        if not ok
    ]


def reactor_scram(w: World, reason):
    if w.r_mode in ("ONLINE", "RUNBACK", "STARTING"):
        w.r_mode = "SCRAM"
        w.r_mode_ticks = 0
        w.r_shutdown_t = w.t
        w.r_power_mw = 0.0
        w.log("ALARM", f"Reactor SCRAM ({reason})")


def grid_rebuild(w: World):
    """Walk the pole tree: a pole is online when its parent is online and the span to it is intact."""
    fallen = w.p_state == 2
    parent = w.p_parent
    parent_fallen = np.where(parent >= 0, fallen[np.maximum(parent, 0)], False)
    span_ok = (w.s_health >= 0.2) & ~fallen & ~parent_fallen
    net_ok = w.n_span_ok & ~fallen & ~parent_fallen
    sector_feed = w.trunk_ok & w.substation_ok & w.feeder_ok & w.rp_ok
    w.feeder_online = sector_feed
    online = np.zeros(w.P, dtype=bool)
    net = np.zeros(w.P, dtype=bool)
    for i in range(w.P):  # parents always precede children in the arrays
        p = parent[i]
        up = sector_feed[w.p_sector[i]] if p < 0 else online[p]
        upn = True if p < 0 else net[p]
        online[i] = up and span_ok[i]
        net[i] = upn and net_ok[i]
    w.s_online = online
    w.net_chain = net


def power_step(w: World):
    c = w.cfg
    S = w.S
    grid_rebuild(w)
    w.solar_kw = (
        c["solar_peak_kw"]
        * w.daylight
        * (1 - w.dust)
        * w.solar_health
        * (1 + w.rng.normal(0, 0.03))
    )
    w.solar_kw = max(0.0, w.solar_kw)
    reactor_kw = w.r_available_mw * 1000.0 if (w.trunk_ok and w.substation_ok) else 0.0
    available = reactor_kw + (w.solar_kw if w.substation_ok else 0.0)

    houses_decide(w)
    house_pole_online = w.s_online[w.h_pole] & w.h_wiring_ok
    draw, heat_alloc = houses_demand(w)
    infra = {
        "mine": c["mine_kw"] * w.mine_frac,
        "water_plant": c["water_plant_kw"] if w.water_plant_ok else 0.0,
        "waste_storage": c["waste_storage_kw"],
        "ops_center": c["ops_center_kw"],
        "comms": c["comms_kw"] + (c["comms_kw"] * 0.5 if w.tower_line_ok else 0.0),
        "cabinets": c["cabinet_kw"] * S,
        "gates": c["gate_kw"] * S,
        "lamps": 0.0,
        "road_heating": (
            c["road_heating_kw"] if (w.road_icy and w.shedding < 2) else 0.0
        ),
        "pump_station": c["pump_station_kw"],
        "ups_charge": 0.0,
    }
    lamps_on = (
        w.p_lamp_ok
        & w.s_online
        & (w.shedding < 4)
        & (w.is_night() or w.storm_ticks > 0 or w.precip == "snow")
    )
    lamp_kw = c["lamp_kw"] * (1.2 if w.storm_lighting else 1.0)
    infra["lamps"] = float(lamps_on.sum()) * lamp_kw
    w.p_lamp_on = lamps_on
    w.road_heating_on = infra["road_heating"] > 0
    need = np.maximum(0.0, c["ups_sector_kwh"] - w.ups_kwh)
    charge_kw = np.where(
        (need > 0) & w.feeder_online & (w.shedding < 2), c["ups_charge_kw"], 0.0
    )
    center_need = c["ups_center_kwh"] - w.ups_center_kwh
    center_charge = (
        c["ups_charge_kw"]
        if (center_need > 0 and w.substation_ok and w.trunk_ok and w.shedding < 2)
        else 0.0
    )
    infra["ups_charge"] = float(charge_kw.sum()) + center_charge

    grid_house_draw = np.where(house_pole_online, draw, 0.0)
    sector_draw = np.bincount(w.h_sector, weights=grid_house_draw, minlength=S) / 1000.0
    demand = float(sector_draw.sum()) + sum(infra.values())
    w.sector_demand_kw = sector_draw

    deficit = max(0.0, demand - available)
    if deficit > 0 and available > 0:
        if w.shedding < 8:
            w.shedding += 1
            if w.shedding > w.max_shed_logged or w.t - w.shed_log_t > 240:
                w.log(
                    "WARN",
                    f"Load shedding level {w.shedding}, deficit {deficit:.0f} kW",
                )
                w.max_shed_logged = w.shedding
                w.shed_log_t = w.t
        w.surplus_ticks = 0
    elif available > 0 and demand < available * 0.9:
        w.surplus_ticks += 1
        if w.surplus_ticks > 30 and w.shedding > 0:
            w.shedding -= 1
            w.surplus_ticks = 0
            if w.shedding == 0:
                w.log("INFO", "Load shedding ended")
                w.max_shed_logged = 0
    if available <= 0.0:
        w.shedding = 8
    reactor_up = w.r_mode not in ("SCRAM", "COOLING", "EMERGENCY", "CORE_DAMAGE")
    w.mine_frac = (
        (1.0 if w.shedding < 6 else 0.5 if w.shedding < 7 else 0.0)
        if (available > 0 and reactor_up)
        else 0.0
    )
    w.mine_powered = w.mine_frac > 0

    limit = np.zeros(w.N)
    if w.shedding >= 3:
        limit[:] = c["limit_level3_w"]
    if w.shedding >= 5:
        limit[:] = c["limit_level5_w"]
    shed_sectors = np.zeros(S, dtype=bool)
    if w.shedding >= 8 and available > 0:
        excess = deficit
        for s in range(S - 1, -1, -1):
            if excess <= 0:
                break
            shed_sectors[s] = True
            excess -= float(sector_draw[s])
    sector_feed = w.feeder_online & ~shed_sectors
    w.sector_online = sector_feed

    house_feed_ok = house_pole_online & sector_feed[w.h_sector]
    on_ups = np.zeros(w.N, dtype=bool)
    powered = house_feed_ok.copy()
    for s in range(S):
        mask = w.h_sector == s
        if sector_feed[s]:
            w.ups_kwh[s] = min(c["ups_sector_kwh"], w.ups_kwh[s] + charge_kw[s] / 60.0)
            w.ups_state[s] = "CHARGING" if charge_kw[s] > 0 else "STANDBY"
        else:
            if w.ups_kwh[s] > 0 and w.ups_health[s] > 0.2:
                m = mask & house_pole_online & ~house_feed_ok
                limit[m] = np.minimum(
                    np.where(limit[m] > 0, limit[m], 1e9), c["limit_level3_w"]
                )
                sup = min(
                    c["ups_sector_kw"],
                    float(np.minimum(draw[m], c["limit_level3_w"]).sum()) / 1000.0,
                )
                w.ups_kwh[s] = max(0.0, w.ups_kwh[s] - sup / 60.0)
                powered[m] = True
                on_ups[m] = True
                w.ups_state[s] = "DISCHARGING"
                if w.ups_kwh[s] <= 0:
                    w.ups_state[s] = "DEPLETED"
                    w.log("ALARM", f"Sector {s + 1} UPS depleted")
            else:
                w.ups_state[s] = "DEPLETED" if w.ups_kwh[s] <= 0 else "FAULT"
    if w.substation_ok and w.trunk_ok and available > 0:
        w.ups_center_kwh = min(
            c["ups_center_kwh"], w.ups_center_kwh + center_charge / 60.0
        )
        w.ups_center_state = "CHARGING" if center_charge > 0 else "STANDBY"
        w.comms_powered = True
        w.pump_station_ok = True
    else:
        if w.ups_center_kwh > 0:
            w.ups_center_kwh = max(
                0.0,
                w.ups_center_kwh
                - (c["ops_center_kw"] + c["comms_kw"] + c["pump_station_kw"]) / 60.0,
            )
            w.ups_center_state = "DISCHARGING"
            w.comms_powered = True
            w.pump_station_ok = True
        else:
            w.ups_center_state = "DEPLETED"
            w.comms_powered = False
            w.pump_station_ok = False

    real_draw = np.where(powered, draw, 0.0)
    heat = np.where(powered, heat_alloc, 0.0)
    w.h_power_ok = powered
    w.h_on_ups = on_ups
    w.h_limit_w = limit
    w.h_draw_w = real_draw
    w.h_heat_w = heat
    kwh = real_draw / 1000.0 / 60.0
    w.h_meter_kwh += kwh
    w.h_meter_month += kwh
    w.h_meter_day += kwh
    w.available_kw = available
    w.demand_kw = demand
    w.deficit_kw = deficit
    # statistics by house program (external programs by name, the rest as "thermostat")
    names = [
        p if (p and ext_i) else "thermostat"
        for p, ext_i in zip(w.h_program, getattr(w, "h_ext", np.zeros(w.N, dtype=bool)))
    ]
    for name in set(names):
        idx = np.fromiter((k for k, n in enumerate(names) if n == name), dtype=int)
        st = w.prog_stats.setdefault(
            name,
            {"kwh": 0.0, "house_ticks": 0, "cold_ticks": 0, "t_sum": 0.0, "cost": 0.0},
        )
        st["kwh"] += float(kwh[idx].sum())
        st["house_ticks"] += int(len(idx))
        st["cold_ticks"] += int((w.h_t_in[idx] < 16.0).sum())
        st["t_sum"] += float(w.h_t_in[idx].sum())
        st["cost"] += float(kwh[idx].sum()) * c["tariff_kwh"]
    w.infra_loads_kw = {k: round(v, 1) for k, v in infra.items()}
    lamps_by_sector = np.bincount(
        w.p_sector, weights=w.p_lamp_on.astype(float), minlength=S
    )
    w.sector_dark = (lamps_by_sector < 6) & np.array([w.is_night()] * S)
    if w.mine_frac > 0:
        w.colony_budget += c["mine_income_per_tick"] * w.mine_frac
        w.colony_month_income += c["mine_income_per_tick"] * w.mine_frac
