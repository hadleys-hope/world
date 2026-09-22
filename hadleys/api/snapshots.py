"""api / snapshots: colony simulation components."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import numpy as np
from hadleys.config import TYPE_NAMES
from hadleys.geometry.roads import colony_layout, traffic_junctions
from hadleys.geometry.terrain import RIVER_PROFILE
from hadleys.models import Issue


from hadleys.domains.driving import driver_holds


def snapshot(w: World):
    for rover in w.rovers + w.traffic:
        driver_holds(rover)
    S = w.S
    c = w.cfg
    sec = []
    for s in range(S):
        m = w.h_sector == s
        sec.append(
            {
                "id": s + 1,
                "online": bool(w.sector_online[s]),
                "demand_kw": round(float(w.sector_demand_kw[s]), 1),
                "avg_t": round(float(w.h_t_in[m].mean()), 1),
                "min_t": round(float(w.h_t_in[m].min()), 1),
                "water_ok": int(w.h_water_ok[m].sum()),
                "power_ok": int(w.h_power_ok[m].sum()),
                "net_ok": int(w.h_net_online[m].sum()),
                "water_m3_h": round(float(w.sector_water_m3[s]) * 60, 2),
                "ups": w.ups_state[s],
                "ups_kwh": round(float(w.ups_kwh[s]), 0),
                "budget": round(float(w.sector_budget[s]), 0),
                "waste": round(float(w.waste_level[s]), 2),
                "sludge": round(float(w.sludge_store[s]), 2),
                "sanitary": round(float(w.sanitary[s]), 0),
                "gate": w.gate_state[s],
                "gate_ok": bool(w.gate_ok[s]),
                "gate_open": round(float(w.gate_open_frac[s]), 2),
                "road": round(float(w.road_integrity[s]), 0),
                "cabinet": bool(w.cabinet_online[s]),
                "cabinet_ups_h": round(float(w.cabinet_ups_h[s]), 1),
                "rp_ok": bool(w.rp_ok[s]),
                "feeder_ok": bool(w.feeder_ok[s]),
                "dark": bool(w.sector_dark[s]),
                "lamps_on": int(w.p_lamp_on[w.p_sector == s].sum()),
                "lockdown": int(w.lockdown_ticks[s]),
            }
        )
    issues = [
        {
            "id": i.id,
            "kind": i.kind,
            "target": i.target,
            "sector": i.sector + 1,
            "cause": i.cause,
            "cost": i.cost,
            "payer": i.payer,
            "status": i.status,
            "sev": i.severity,
            "x": round(i.pos[0]),
            "y": round(i.pos[1]),
            "age": w.t - i.opened_t,
        }
        for i in w.open_issues()
    ][-40:]
    return {
        "t": w.t,
        "time": w.time_str(),
        "paused": w.paused,
        "speed": w.speed,
        "finished": w.finished,
        "finish_reason": w.finish_reason,
        "env": {
            "t_out": round(w.t_out, 1),
            "wind": round(w.wind, 1),
            "precip": w.precip,
            "daylight": round(w.daylight, 3),
            "dust": round(w.dust, 2),
            "storm": w.storm_ticks > 0,
            "night": w.is_night(),
            "icy": w.road_icy,
            "visibility": w.visibility,
        },
        "power": {
            "available_kw": round(w.available_kw),
            "demand_kw": round(w.demand_kw),
            "deficit_kw": round(w.deficit_kw),
            "shedding": w.shedding,
            "solar_kw": round(w.solar_kw, 1),
            "trunk": w.trunk_ok,
            "substation": w.substation_ok,
            "tower_line": w.tower_line_ok,
            "feeder": [bool(x) for x in w.feeder_online],
            "mine": w.mine_powered,
            "mine_frac": w.mine_frac,
            "ups_center": w.ups_center_state,
            "ups_center_kwh": round(w.ups_center_kwh),
            "infra": w.infra_loads_kw,
            "road_heating": w.road_heating_on,
            "storm_lighting": w.storm_lighting,
            "sector_kw": [round(float(x), 1) for x in w.sector_demand_kw],
        },
        "reactor": {
            "mode": w.r_mode,
            "power_mw": round(w.r_power_mw, 2),
            "setpoint_mw": round(w.r_setpoint_mw, 2),
            "available_mw": round(w.r_available_mw, 2),
            "core_temp": round(w.r_core_temp),
            "coolant_temp": round(w.r_coolant_temp),
            "flow": round(w.r_flow, 2),
            "decay_mw": round(w.r_decay_mw, 2),
            "pump_a": round(w.r_pump_a, 2),
            "pump_b": round(w.r_pump_b, 2),
            "hx": round(w.r_hx, 2),
            "battery_h": round(w.r_battery_h, 1),
            "faults": w.r_faults,
            "link": w.r_link_ok,
            "marines": w.marines_active > 0,
            "thermal_mw": round(w.r_power_mw / 0.3, 1),
        },
        "hydraulics": w.utilities.state(),
        "water": {
            "tank_m3": round(w.water_tank_m3, 1),
            "tank_cap": c["water_tank_m3"],
            "plant": w.water_plant_ok,
            "source": "ocean",
            "intake_ok": w.intake_ok,
            "raw_m3_h": round(w.raw_intake_m3_h, 3),
            "brine_m3_h": round(w.brine_m3_h, 3),
            "heat_kw": round(w.water_heat_used_kw, 2),
            "heat_available_kw": round(w.water_heat_available_kw, 2),
            "heat": w.water_plant_heat,
            "plant_m3_h": round(w.water_plant_m3_h, 2),
            "flow_m3_h": round(w.water_flow_m3_h, 2),
            "pump": w.pump_station_ok,
            "houses_ok": int(w.h_water_ok.sum()),
            "burst": int(w.h_burst.sum()),
            "frozen": int((~w.h_pipes_ok).sum()),
            "sector_m3_h": [round(float(x) * 60, 2) for x in w.sector_water_m3],
        },
        "net": {
            "mobile": w.mobile_online,
            "dish": w.dish_ok,
            "uplink": w.uplink_ok,
            "tower": w.tower_ok,
            "comms": w.comms_ok,
            "houses_online": int(w.h_net_online.sum()),
            "packets_per_min": w.packets_per_min,
            "reactor_link": w.r_link_ok,
            "packets": w.packets[-40:],
        },
        "finance": {
            "colony": round(w.colony_budget),
            "sectors": [round(float(x)) for x in w.sector_budget],
            "unpaid": round(w.unfunded_total),
            "month": w.month,
            "month_expense": round(w.colony_month_expense),
            "month_income": round(w.colony_month_income),
            "waste_station": round(w.waste_station_level, 2),
        },
        "sectors": sec,
        "houses": {
            "t": [round(float(x), 1) for x in w.h_t_in],
            "power": w.h_power_ok.astype(int).tolist(),
            "ups": w.h_on_ups.astype(int).tolist(),
            "water": w.h_water_ok.astype(int).tolist(),
            "net": w.h_net_online.astype(int).tolist(),
            "heater": w.h_heater_on.astype(int).tolist(),
            "pipes": w.h_pipes_ok.astype(int).tolist(),
            "burst": w.h_burst.astype(int).tolist(),
            "sludge": [round(float(x), 2) for x in w.h_sludge],
            "limit": [int(x) for x in w.h_limit_w],
            "draw": [int(x) for x in w.h_draw_w],
        },
        "poles": {
            "state": w.p_state.tolist(),
            "lamp": w.p_lamp_on.astype(int).tolist(),
            "span": w.s_online.astype(int).tolist(),
            "net": w.net_chain.astype(int).tolist(),
            "ice": [round(float(x), 2) for x in w.s_ice],
        },
        "rovers": [
            {
                "name": r.name,
                "kind": r.kind,
                "state": r.state,
                "x": round(r.x, 3),
                "y": round(r.y, 3),
                "fuel_l": round(r.fuel_l, 2),
                "distance_m": round(r.odometer_m, 3),
                "velocity": round(r.velocity, 3),
                "heading": round(r.heading, 5),
                "manual": bool(
                    getattr(r, "driver_parked", False)
                    or getattr(r, "driver_owner", None)
                ),
                "chassis": getattr(r, "driver_chassis", None),
                "load": round(r.load, 2),
                "job": (
                    r.job.kind
                    if isinstance(r.job, Issue)
                    else (r.job + 1 if isinstance(r.job, (int, np.integer)) else None)
                ),
            }
            for r in w.rovers + getattr(w, "traffic", [])
        ],
        "cargo": w.cargo,
        "xenos": [
            {
                "id": m.get("id", 0),
                "x": round(m["x"]),
                "y": round(m["y"]),
                "state": m.get("state", "hunt"),
                "sector": m["sector"] + 1,
                "heading": round(m.get("heading", 0.0), 2),
                "target": int(m.get("target", -1)) + 1,
            }
            for m in w.xeno_markers
        ],
        "squad": {
            "x": round(w.squad["x"]),
            "y": round(w.squad["y"]),
            "state": w.squad["state"],
            "sector": w.squad["sector"] + 1,
            "heading": round(w.squad.get("heading", 0.0), 2),
        },
        "wall_breach": [
            None if a is None else round(float(a), 1) for a in w.wall_breach
        ],
        "people": [
            [round(float(x)), round(float(y)), int(s), int(h)]
            for x, y, s, h in zip(w.w_x, w.w_y, w.w_state, w.w_home)
            if s != 0
        ],
        "marines": (
            [
                [
                    c["reactor_pos"][0] + 60 + 24 * k,
                    c["reactor_pos"][1] - 50 + 20 * (k % 2),
                ]
                for k in range(4)
            ]
            if w.marines_active > 0
            else []
        ),
        "issues": issues,
        "issues_total": len(w.open_issues()),
        "events": list(w.events)[:40],
        "report": w.last_report,
        "month_progress": {
            "day": w.t // c["ticks_per_day"] % c["days_per_month"] + 1,
            "days": c["days_per_month"],
            "sector_income": [round(float(x)) for x in w.month_income],
            "sector_expense": [round(float(x)) for x in w.month_expense],
            "colony_income": round(w.colony_month_income),
            "colony_expense": round(w.colony_month_expense),
            "kwh": round(float(w.h_meter_month.sum())),
            "water_m3": round(float(w.h_water_month.sum()), 1),
            "repairs": round(float(w.h_repairs_month.sum())),
        },
        "control": {
            "programs": w.h_program,
            "reasons": w.h_reason,
            "ext": getattr(w, "h_ext", np.zeros(w.N, dtype=bool)).astype(int).tolist(),
            "targets": [round(float(x), 1) for x in w.h_target],
            "mqtt": (
                w.bridge.status() if getattr(w, "bridge", None) else {"enabled": False}
            ),
        },
    }


def bus_snapshot(w: World):
    """Everything the /bus page shows: bus status, message tail, per-house control table, per-program comparison."""
    c = w.cfg
    ext = getattr(w, "h_ext", np.zeros(w.N, dtype=bool))
    bridge = getattr(w, "bridge", None)
    houses = []
    for i in range(w.N):
        houses.append(
            [
                i + 1,
                int(w.h_sector[i]) + 1,
                (w.h_program[i] if ext[i] else "thermostat"),
                w.h_reason[i] if ext[i] else "",
                round(float(w.h_target[i]), 1),
                round(float(w.h_t_in[i]), 1),
                int(w.h_heater_on[i]),
                int(w.h_draw_w[i]),
                int(w.h_power_ok[i]),
                int(w.h_on_ups[i]),
                int(w.h_limit_w[i]),
                int(w.h_water_ok[i]),
                int(w.h_net_online[i]),
                int(w.t - bridge.last_pub_t[i]) if bridge else -1,
                int(w.t - w.h_ctrl_t[i]) if ext[i] else -1,
                int(w.h_appliances_on[i]),
                int(w.h_valve_open[i]),
            ]
        )
    progs = []
    current = [
        (p if (p and ext[i]) else "thermostat") for i, p in enumerate(w.h_program)
    ]
    for name, st in sorted(w.prog_stats.items()):
        ht = max(1, st["house_ticks"])
        progs.append(
            {
                "program": name,
                "houses": current.count(name),
                "avg_t": round(st["t_sum"] / ht, 2),
                "kwh_per_house_day": round(st["kwh"] / ht * 1440, 2),
                "cold_share": round(st["cold_ticks"] / ht * 100, 2),
                "cost_per_house_day": round(st["cost"] / ht * 1440, 2),
            }
        )
    return {
        "t": w.t,
        "time": w.time_str(),
        "mqtt": bridge.status() if bridge else {"enabled": False},
        "tail": bridge.tail_list() if bridge else [],
        "houses": houses,
        "programs": progs,
        "env": {
            "t_out": round(w.t_out, 1),
            "storm": w.storm_ticks > 0,
            "shedding": w.shedding,
        },
    }


def house_snapshot(w: World, i: int):
    c = w.cfg
    ext = getattr(w, "h_ext", np.zeros(w.N, dtype=bool))
    heater = float(w.h_heat_w[i])
    aeration = c["aeration_w"] if w.h_aeration_ok[i] else 0.0
    draw = float(w.h_draw_w[i])
    fridge = 100.0 if w.h_power_ok[i] else 0.0
    rest = max(0.0, draw - heater - (aeration if w.h_power_ok[i] else 0.0) - fridge)
    order = [(w.h_hist_i + k) % w.h_hist.shape[1] for k in range(w.h_hist.shape[1])]
    events = [
        e
        for e in list(w.events)
        if f"House {i + 1}:" in e["text"]
        or f"house:{i}" in e["text"]
        or f"house {i + 1}" in e["text"].lower()
    ][:10]
    return {
        "id": i + 1,
        "sector": int(w.h_sector[i]) + 1,
        "type": TYPE_NAMES[int(w.h_type[i])],
        "residents": int(w.h_residents[i]),
        "t_in": round(float(w.h_t_in[i]), 1),
        "target": round(float(w.h_target[i]), 1),
        "t_out": round(w.t_out, 1),
        "heater_on": bool(w.h_heater_on[i]),
        "heater_w": int(w.h_heater_w[i]),
        "heat_w": int(heater),
        "draw_w": int(draw),
        "split": {
            "heater": int(heater),
            "appliances": int(rest),
            "aeration": int(aeration if w.h_power_ok[i] else 0),
            "fridge": int(fridge),
        },
        "power_ok": bool(w.h_power_ok[i]),
        "on_ups": bool(w.h_on_ups[i]),
        "limit_w": int(w.h_limit_w[i]),
        "ups_kwh": round(float(w.ups_kwh[w.h_sector[i]]), 0),
        "ups_cap": c["ups_sector_kwh"],
        "ups_state": w.ups_state[w.h_sector[i]],
        "water_ok": bool(w.h_water_ok[i]),
        "pipes_ok": bool(w.h_pipes_ok[i]),
        "burst": bool(w.h_burst[i]),
        "valve_open": bool(w.h_valve_open[i]),
        "pressure_kpa": round(float(w.utilities.pressure[i]), 2),
        "delivered_l": round(float(w.utilities.delivered[i]) * 1000, 4),
        "leak_l": round(float(w.utilities.leaks[i]) * 1000, 4),
        "water_month_m3": round(float(w.h_water_month[i]), 2),
        "tank_m3": round(w.water_tank_m3, 0),
        "tank_cap": c["water_tank_m3"],
        "net_online": bool(w.h_net_online[i]),
        "terminal_ok": bool(w.h_terminal_ok[i]),
        "cabinet": bool(w.cabinet_online[w.h_sector[i]]),
        "sludge": round(float(w.h_sludge[i]), 2),
        "aeration_ok": bool(w.h_aeration_ok[i]),
        "appliances_on": bool(w.h_appliances_on[i]),
        "kwh_month": round(float(w.h_meter_month[i]), 1),
        "kwh_total": round(float(w.h_meter_kwh[i]), 1),
        "bill_month": round(
            float(w.h_meter_month[i]) * c["tariff_kwh"]
            + float(w.h_water_month[i]) * c["tariff_water_m3"]
            + float(w.h_repairs_month[i]),
            1,
        ),
        "program": (w.h_program[i] if ext[i] else "thermostat"),
        "reason": w.h_reason[i] if ext[i] else "built-in thermostat",
        "ctrl_age": int(w.t - w.h_ctrl_t[i]) if ext[i] else -1,
        "pole": int(w.h_pole[i]),
        "pole_online": bool(w.s_online[w.h_pole[i]]),
        "hist_t": [round(float(w.h_hist[i, k]), 1) for k in order],
        "hist_w": [int(w.h_hist_draw[i, k]) for k in order],
        "log": [{"t": t, "text": x} for t, x in list(w.h_log[i])],
        "events": events,
        "issues": [
            {"kind": s.kind, "status": s.status, "cost": s.cost}
            for s in w.open_issues()
            if s.target in (f"house:{i}", f"aeration:{i}", f"terminal:{i}")
        ],
        "time": w.time_str(),
        "t": w.t,
        "shedding": w.shedding,
    }


def house_geometry(w: World):
    c = w.cfg
    return {
        "houses": {
            "x": [round(float(x), 5) for x in w.h_x],
            "y": [round(float(y), 5) for y in w.h_y],
            "angle": [round(float(a), 2) for a in w.h_angle],
            "radius": [round(float(r)) for r in w.h_radius],
            "sector": w.h_sector.tolist(),
            "type": w.h_type.tolist(),
            "pole": w.h_pole.tolist(),
            "residents": w.h_residents.tolist(),
        },
        "poles": {
            "x": [round(float(x), 1) for x in w.p_x],
            "y": [round(float(y), 1) for y in w.p_y],
            "sector": w.p_sector.tolist(),
            "k": w.p_k.tolist(),
            "parent": w.p_parent.tolist(),
            "kind": w.p_kind.tolist(),
            "radius": [round(float(r)) for r in w.p_radius],
            "angle": [round(float(a), 2) for a in w.p_angle],
        },
        "cfg": {
            k: c[k]
            for k in (
                "hub_radius",
                "house_radius_min",
                "house_ring_step",
                "house_rows",
                "ring_road_radius",
                "wall_radius",
                "spine_radii",
                "reactor_pos",
                "solar_pos",
                "water_plant_pos",
                "radwaste_pos",
                "mine_pos",
                "waste_station_pos",
                "tower_junction",
                "tower_pos",
                "landing_pad_pos",
                "garage",
                "medlab",
                "school",
                "sectors",
                "water_tank_m3",
                "planet_radius",
                "dish_pos",
                "ocean_intake_pos",
                "ocean_level_m",
                "ocean_center",
                "ocean_radii",
                "cargo_depot",
            )
        },
        "layout": colony_layout(c),
        "junctions": traffic_junctions(c),
        "river": RIVER_PROFILE,
        "utilities": w.utilities.geometry(w),
        "types": TYPE_NAMES,
    }
