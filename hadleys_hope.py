"""Hadley's Hope colony simulation, LV-426.

One process, one file: environment, reactor and grid, 300 houses, water,
internet, roads and rovers, incidents, finance, a browser UI and persistence.
Run `python3 hadleys_hope.py` and open http://localhost:8000.
"""
from __future__ import annotations

import json
import math
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ------------------------------------------------------------------------------------
# Configuration. Every number the simulation uses lives here.
# ------------------------------------------------------------------------------------

CFG = {
    "seed": 12345,
    "sectors": 6,
    "houses_per_sector": 50,
    "tick_seconds": 60,
    "ticks_per_day": 1440,
    "days_per_month": 30,
    # geometry (map units, roughly metres)
    "hub_radius": 80,
    "house_radius_min": 150,
    "house_ring_step": 36,
    "ring_road_radius": 330,
    "pole_radius_min": 100,
    "pole_radius_step": 40,
    "poles_per_sector": 6,
    "reactor_pos": (-640, 0),
    "tower_pos": (-420, -360),
    "waste_station_pos": (-640, 200),
    # environment (LV-426: minus 40..60, permanent dusk, storms)
    "t_mean": -45.0,
    "t_daily_amp": 8.0,
    "storm_prob_per_tick": 0.0006,
    "storm_len_ticks": (180, 600),
    "storm_wind": (22.0, 34.0),
    "calm_wind": (4.0, 14.0),
    "daylight_max": 0.3,
    # houses
    "heater_kw": [2.5, 3.0, 3.0, 4.0],          # by type: barracks, standard, insulated, manager
    "ua_w_per_k": [55.0, 45.0, 32.0, 60.0],
    "heat_cap_j_per_k": [0.8e7, 1.0e7, 1.3e7, 1.8e7],
    "base_load_w": [200, 300, 300, 600],
    "type_counts": [120, 120, 45, 15],
    "comfort_c": 21.0, "eco_c": 16.0, "antifreeze_c": 5.0,
    "freeze_ticks_to_frozen": 60, "frozen_ticks_to_burst": 30,
    "water_per_house_m3_day": 0.2,
    # reactor
    "reactor_gross_mw": 6.0, "reactor_self_mw": 0.6, "heat_export_mw": 3.0,
    "ramp_frac_per_min": 0.05, "core_temp_nominal": 780.0, "core_temp_limit": 1200.0,
    "pump_battery_h": 8.0,
    # grid
    "solar_peak_kw": 200.0,
    "mine_kw": 2000.0, "water_plant_kw": 300.0, "waste_storage_kw": 20.0,
    "ops_center_kw": 40.0, "comms_kw": 20.0, "cabinet_kw": 1.0, "gate_kw": 2.0,
    "lamps_per_sector": 6, "lamp_kw": 0.8, "road_heating_kw": 300.0,
    "aeration_w": 150.0, "pump_station_kw": 50.0,
    "ups_center_kw": 150.0, "ups_center_kwh": 800.0,
    "ups_sector_kw": 100.0, "ups_sector_kwh": 400.0,
    "ups_charge_kw": 100.0,
    "limit_level3_w": 2000.0, "limit_level5_w": 1000.0,
    # water
    "water_tank_m3": 500.0, "water_plant_m3_h": 12.0,
    # finance
    "sector_budget": 10000.0, "colony_budget": 100000.0,
    "tariff_kwh": 0.25, "tariff_water_m3": 3.0, "sewage_fee": 20.0, "internet_fee": 15.0,
    "mine_income_per_tick": 25.0,
    "reactor_upkeep_month": 3000.0,
    # incidents: probability per tick
    "p_xeno": 0.00035, "p_vandal": 0.00025, "p_animal": 0.0002, "p_rover_hit": 0.0003,
    "p_nest_fire": 0.02,           # per tick while a xeno attack near the processor is open
    "p_pump_wear": 0.00002,
    # sewage and waste
    "sludge_per_resident_per_tick": 1.0 / (1440 * 20),   # tank full in ~20 days at 1 resident
    "waste_per_resident_per_tick": 1.0 / (1440 * 6),     # sector bin full in ~6 days
    "hauler_speed_deg": 6.0,
    # ui
    "http_port": 8000,
    "default_speed": 20,
}

COSTS = {
    "span": (200, "sector", 120), "pole": (600, "sector", 180), "feeder": (800, "sector", 240),
    "rp": (1500, "sector", 240), "ups": (1000, "sector", 120), "tower_line": (500, "colony", 240),
    "trunk": (3000, "colony", 480), "substation": (5000, "colony", 480),
    "pump": (4000, "colony", 360), "heat_exchanger": (15000, "colony", 720),
    "solar": (800, "colony", 120), "wiring": (600, "house", 120), "pipes": (1200, "house", 180),
    "aeration": (900, "house", 120), "cabinet": (400, "sector", 240), "net_span": (150, "sector", 120),
    "terminal": (80, "house", 60), "lamp": (300, "sector", 60), "road": (500, "sector", 3),
    "gate": (1200, "sector", 120), "waste_trip": (100, "sector", 0), "sludge_trip": (120, "sector", 0),
}

TYPE_NAMES = ["barracks", "standard", "insulated", "manager"]


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


# ------------------------------------------------------------------------------------
# World state
# ------------------------------------------------------------------------------------

@dataclass
class Issue:
    id: int
    kind: str
    target: str          # "span:12", "pole:3", "house:17", "reactor:pump_b", "road:2", ...
    sector: int          # -1 for colony objects
    cause: str
    cost: float
    payer: str           # sector | colony | house
    duration: int        # repair ticks
    pos: tuple
    opened_t: int
    status: str = "open" # open | funded | in_progress | resolved | unfunded
    severity: str = "warning"
    started_t: int = -1
    resolved_t: int = -1


@dataclass
class Rover:
    name: str
    kind: str                       # garbage | sludge | repair
    angle: float = 90.0             # position on ring road, degrees
    radius: float = 330.0
    state: str = "IDLE"
    target_angle: float = 90.0
    target_radius: float = 330.0
    job: Optional[object] = None    # sector index or Issue
    timer: int = 0
    load: float = 0.0
    speed: float = 6.0
    wait: int = 0


class World:
    def __init__(self, cfg=CFG):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg["seed"])
        self.pyrng = random.Random(cfg["seed"])
        self.t = 0
        self.speed = cfg["default_speed"]
        self.paused = False
        self.finished = False
        self.finish_reason = ""
        self.events = deque(maxlen=400)
        self.issues: list[Issue] = []
        self.next_issue_id = 1
        self.packets = []            # recent internet packets for the UI
        self.lock = threading.Lock()
        S = cfg["sectors"]
        H = cfg["houses_per_sector"]
        self.S = S
        self.N = N = S * H

        # ---- houses (numpy) ----
        idx = np.arange(N)
        self.h_sector = idx // H
        self.h_ring = (idx % H) // 10
        self.h_slot = idx % 10
        self.h_angle = self.h_sector * 60.0 + 6.0 + self.h_slot * 5.3
        self.h_radius = cfg["house_radius_min"] + self.h_ring * cfg["house_ring_step"]
        self.h_x = self.h_radius * np.cos(np.radians(self.h_angle))
        self.h_y = self.h_radius * np.sin(np.radians(self.h_angle))
        types = np.concatenate([np.full(c, i) for i, c in enumerate(cfg["type_counts"])])
        self.rng.shuffle(types)
        self.h_type = types
        self.h_ua = np.array(cfg["ua_w_per_k"])[types]
        self.h_cap = np.array(cfg["heat_cap_j_per_k"])[types]
        self.h_heater_w = np.array(cfg["heater_kw"])[types] * 1000.0
        self.h_base_w = np.array(cfg["base_load_w"])[types].astype(float)
        self.h_residents = self.rng.integers(0, 3, N)
        self.h_residents[self.h_type == 3] = 2
        self.h_t_in = np.full(N, 20.0)
        self.h_heater_on = np.ones(N, dtype=bool)
        self.h_target = np.full(N, cfg["comfort_c"])
        self.h_draw_w = np.zeros(N)
        self.h_heat_w = np.zeros(N)
        self.h_limit_w = np.zeros(N)         # 0 = no limit
        self.h_power_ok = np.ones(N, dtype=bool)
        self.h_on_ups = np.zeros(N, dtype=bool)
        self.h_meter_kwh = np.zeros(N)
        self.h_meter_month = np.zeros(N)
        self.h_meter_day = np.zeros(N)
        self.h_water_day = np.zeros(N)
        self.h_water_month = np.zeros(N)
        self.h_water_m3 = np.zeros(N)
        self.h_pipes_ok = np.ones(N, dtype=bool)
        self.h_frozen = np.zeros(N, dtype=int)   # ticks below zero
        self.h_burst = np.zeros(N, dtype=bool)
        self.h_water_ok = np.ones(N, dtype=bool)
        self.h_wiring_ok = np.ones(N, dtype=bool)
        self.h_terminal_ok = np.ones(N, dtype=bool)
        self.h_aeration_ok = np.ones(N, dtype=bool)
        self.h_sludge = self.rng.uniform(0.0, 0.6, N)
        self.h_net_online = np.ones(N, dtype=bool)
        self.h_valve_open = np.ones(N, dtype=bool)
        self.h_repairs_month = np.zeros(N)
        self.h_pole = self.h_sector * cfg["poles_per_sector"] + np.minimum(self.h_ring + 1, cfg["poles_per_sector"] - 1)

        # ---- poles and spans ----
        PPS = cfg["poles_per_sector"]
        self.P = S * PPS
        self.p_sector = np.arange(self.P) // PPS
        self.p_k = np.arange(self.P) % PPS
        self.p_angle = self.p_sector * 60.0 + 30.0
        self.p_radius = cfg["pole_radius_min"] + self.p_k * cfg["pole_radius_step"]
        self.p_x = self.p_radius * np.cos(np.radians(self.p_angle))
        self.p_y = self.p_radius * np.sin(np.radians(self.p_angle))
        self.p_state = np.zeros(self.P, dtype=int)   # 0 standing, 1 tilted, 2 fallen
        self.p_lamp_ok = np.ones(self.P, dtype=bool)
        self.p_lamp_on = np.ones(self.P, dtype=bool)
        # span k feeds pole k of the same sector (span 0 goes from the rp to pole 0)
        self.s_health = np.ones(self.P)
        self.s_ice = np.zeros(self.P)
        self.s_online = np.ones(self.P, dtype=bool)
        self.n_span_ok = np.ones(self.P, dtype=bool)    # internet cable on the same route

        # ---- grid nodes ----
        self.trunk_ok = True
        self.substation_ok = True
        self.tower_line_ok = True
        self.feeder_ok = np.ones(S, dtype=bool)
        self.rp_ok = np.ones(S, dtype=bool)
        self.feeder_online = np.ones(S, dtype=bool)
        self.solar_health = 1.0
        self.solar_kw = 0.0

        # ---- ups ----
        self.ups_center_kwh = cfg["ups_center_kwh"]
        self.ups_center_state = "STANDBY"
        self.ups_kwh = np.full(S, cfg["ups_sector_kwh"])
        self.ups_state = ["STANDBY"] * S
        self.ups_health = np.ones(S)

        # ---- reactor ----
        self.r_mode = "ONLINE"
        self.r_power_mw = cfg["reactor_gross_mw"] * 0.85
        self.r_setpoint_mw = cfg["reactor_gross_mw"] * 0.85
        self.r_core_temp = cfg["core_temp_nominal"]
        self.r_decay_mw = 0.0
        self.r_available_mw = 0.0
        self.r_pump_a = 1.0
        self.r_pump_b = 1.0
        self.r_hx = 1.0
        self.r_battery_h = cfg["pump_battery_h"]
        self.r_mode_ticks = 0
        self.r_emergency_ticks = 0
        self.r_shutdown_t = 0
        self.r_faults: list[str] = []
        self.r_link_ok = True

        # ---- balance ----
        self.available_kw = 0.0
        self.demand_kw = 0.0
        self.deficit_kw = 0.0
        self.shedding = 0
        self.surplus_ticks = 0
        self.max_shed_logged = 0
        self.shed_log_t = -1000
        self.comms_powered = True
        self.sector_demand_kw = np.zeros(S)
        self.sector_online = np.ones(S, dtype=bool)
        self.mine_powered = True
        self.mine_frac = 1.0
        self.road_heating_on = False
        self.storm_lighting = False
        self.infra_loads_kw = {}

        # ---- water ----
        self.water_tank_m3 = cfg["water_tank_m3"]
        self.water_plant_ok = True
        self.water_plant_heat = True
        self.pump_station_ok = True
        self.water_main_ok = np.ones(S, dtype=bool)
        self.sector_water_m3 = np.zeros(S)

        # ---- internet ----
        self.comms_ok = True
        self.tower_ok = True
        self.cabinet_ok = np.ones(S, dtype=bool)
        self.cabinet_ups_h = np.full(S, 2.0)
        self.cabinet_online = np.ones(S, dtype=bool)
        self.net_sector_online = np.ones(S, dtype=bool)
        self.uplink_ok = True

        # ---- roads, gates, waste, sewage ----
        self.road_integrity = np.full(S, 100.0)     # ring segment per sector
        self.spoke_integrity = 100.0                 # spoke to the reactor complex
        self.road_icy = False
        self.gate_state = ["OPEN"] * S              # OPEN | CLOSED | LOCKDOWN
        self.gate_ok = np.ones(S, dtype=bool)
        self.lockdown_ticks = np.zeros(S, dtype=int)
        self.waste_level = self.rng.uniform(0.2, 0.6, S)
        self.sludge_store = self.rng.uniform(0.1, 0.4, S)
        self.sanitary = np.full(S, 100.0)
        self.sector_dark = np.zeros(S, dtype=bool)
        self.rovers = [
            Rover("garbage", "garbage", angle=15.0),
            Rover("sludge", "sludge", angle=195.0),
            Rover("engineer", "repair", angle=105.0, speed=8.0),
        ]
        self.waste_station_level = 0.0

        # ---- people / threats ----
        self.xeno_markers: list[dict] = []          # visible xenomorphs on the map
        self.marines_active = 0
        self.nest_alert = 0

        # ---- finance ----
        self.sector_budget = np.full(S, cfg["sector_budget"])
        self.colony_budget = cfg["colony_budget"]
        self.cost_records: list[dict] = []
        self.month = 1
        self.month_income = np.zeros(S)
        self.month_expense = np.zeros(S)
        self.colony_month_expense = 0.0
        self.colony_month_income = 0.0
        self.last_report: Optional[dict] = None
        self.unfunded_total = 0.0

        # ---- environment ----
        self.t_out = cfg["t_mean"]
        self.wind = 8.0
        self.precip = "none"
        self.daylight = 0.0
        self.dust = 0.2
        self.storm_ticks = 0
        self.synoptic = 0.0
        self.visibility = 100.0

    # ---- helpers ----
    def log(self, level, text):
        self.events.appendleft({"t": self.t, "level": level, "text": text})

    def time_str(self):
        c = self.cfg
        day = self.t // c["ticks_per_day"] % c["days_per_month"] + 1
        hour = self.t // 60 % 24
        minute = self.t % 60
        return f"M{self.month} D{day:02d} {hour:02d}:{minute:02d}"

    def is_night(self):
        h = self.t // 60 % 24
        return h >= 22 or h < 6

    def open_issue(self, kind, target, sector, cause, cost_key, pos, severity="warning"):
        for i in self.issues:
            if i.target == target and i.status != "resolved":
                return i
        cost, payer, dur = COSTS[cost_key]
        iss = Issue(self.next_issue_id, kind, target, sector, cause, float(cost), payer, dur, pos, self.t,
                    severity=severity)
        self.next_issue_id += 1
        self.issues.append(iss)
        self.log("ALARM" if severity == "critical" else "WARN", f"{kind} at {target} ({cause})")
        return iss

    def open_issues(self):
        return [i for i in self.issues if i.status != "resolved"]


# ------------------------------------------------------------------------------------
# Environment
# ------------------------------------------------------------------------------------

def env_step(w: World):
    c = w.cfg
    hour = (w.t % c["ticks_per_day"]) / 60.0
    # synoptic random walk, mean reverting
    w.synoptic += w.rng.normal(0, 0.15) - 0.01 * w.synoptic
    w.synoptic = clamp(w.synoptic, -12, 12)
    base = c["t_mean"] - c["t_daily_amp"] * math.cos(2 * math.pi * (hour - 4) / 24)
    # storms
    if w.storm_ticks > 0:
        w.storm_ticks -= 1
        w.wind += (w.rng.uniform(*c["storm_wind"]) - w.wind) * 0.1
        w.precip = "snow"
        w.visibility = 4.0
        if w.storm_ticks == 0:
            w.log("INFO", "Storm is over")
            w.storm_lighting = False
    else:
        if w.rng.random() < c["storm_prob_per_tick"]:
            w.storm_ticks = int(w.rng.integers(*c["storm_len_ticks"]))
            w.log("WARN", f"Snowstorm begins, {w.storm_ticks // 60} h")
            w.storm_lighting = True
        w.wind += (w.rng.uniform(*c["calm_wind"]) - w.wind) * 0.05
        w.precip = "snow" if w.rng.random() < 0.002 else ("none" if w.precip == "none" or w.rng.random() < 0.01 else w.precip)
        w.visibility = 60.0 if w.precip == "snow" else 100.0
    storm_drop = 10.0 if w.storm_ticks > 0 else 0.0
    w.t_out = base + w.synoptic - storm_drop
    # daylight: Calpamos is dim, permanent dusk
    w.daylight = c["daylight_max"] * max(0.0, math.sin(math.pi * (hour - 6) / 12)) * (0.2 if w.storm_ticks > 0 else 1.0)
    w.dust = clamp(w.dust + (0.02 * w.wind / 10 - 0.02) * 0.05 + w.rng.normal(0, 0.01), 0.05, 0.95)
    w.road_icy = w.precip == "snow" or w.storm_ticks > 0
    # ice on spans
    if w.precip == "snow":
        w.s_ice = np.minimum(1.0, w.s_ice + 0.002)
    elif w.t_out > 0:
        w.s_ice = np.maximum(0.0, w.s_ice - 0.005)


# ------------------------------------------------------------------------------------
# Reactor
# ------------------------------------------------------------------------------------

def reactor_step(w: World):
    c = w.cfg
    nom = c["reactor_gross_mw"]
    ramp = c["ramp_frac_per_min"] * nom
    flow = (0.5 * (w.r_pump_a > 0.2) + 0.5 * (w.r_pump_b > 0.2)) * w.r_hx
    w.r_mode_ticks += 1

    # pump wear
    if w.r_mode in ("ONLINE", "RUNBACK"):
        if w.rng.random() < c["p_pump_wear"]:
            which = "pump_b" if w.r_pump_b > 0.2 else "pump_a"
            setattr(w, "r_" + which, 0.1)
            w.open_issue("pump_trip", f"reactor:{which}", -1, "wear", "pump", c["reactor_pos"], "critical")
            w.log("ALARM", f"Reactor {which.upper()} tripped")

    if w.r_mode == "ONLINE":
        if flow < 0.75:
            w.r_mode = "RUNBACK"
            w.r_mode_ticks = 0
            w.log("ALARM", "Reactor RUNBACK: coolant flow reduced")
    if w.r_mode == "RUNBACK" and flow >= 0.99:
        w.r_mode = "ONLINE"
        w.log("INFO", "Reactor back ONLINE")

    if w.r_mode in ("ONLINE", "RUNBACK"):
        cap = nom * (1.0 if w.r_mode == "ONLINE" else 0.5) * min(1.0, flow / 0.5 if w.r_mode == "RUNBACK" else 1.0)
        target = min(w.r_setpoint_mw, cap)
        w.r_power_mw += clamp(target - w.r_power_mw, -ramp, ramp)
        w.r_decay_mw = 0.0
        thermal = w.r_power_mw / 0.3
        t_eq = 300.0 + 480.0 * (thermal / 20.0) / max(flow, 0.05)
        w.r_core_temp += (t_eq - w.r_core_temp) * 0.05
        w.r_core_temp = clamp(w.r_core_temp, 300, 1400)
        w.r_available_mw = max(0.0, min(cap, w.r_power_mw + ramp) - c["reactor_self_mw"] - 0.15 * c["heat_export_mw"])
        w.water_plant_heat = True
        if flow < 0.3 or w.r_core_temp > c["core_temp_limit"]:
            reactor_scram(w, "protection: temperature/flow")
    elif w.r_mode in ("SCRAM", "COOLING", "EMERGENCY"):
        w.r_power_mw = 0.0
        w.r_available_mw = 0.0
        w.water_plant_heat = False
        t_since = max(1, (w.t - w.r_shutdown_t) * 60)
        w.r_decay_mw = 0.066 * 20.0 * (t_since ** -0.2 - (t_since + 3.0e7) ** -0.2)
        pumps_powered = w.trunk_ok and w.substation_ok
        if not pumps_powered:
            w.r_battery_h = max(0.0, w.r_battery_h - 1 / 60)
        else:
            w.r_battery_h = min(c["pump_battery_h"], w.r_battery_h + 1 / 240)
        flow_now = flow if (pumps_powered or w.r_battery_h > 0) else 0.02 * w.r_hx   # natural circulation only
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
            elif w.r_core_temp < 400 and w.r_hx > 0.7 and flow >= 0.5 and pumps_powered and w.r_mode_ticks > 360:
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
    w.r_faults = [f for f, ok in (("PUMP_A_TRIP", w.r_pump_a > 0.2), ("PUMP_B_TRIP", w.r_pump_b > 0.2),
                                  ("HEAT_EXCHANGER_DAMAGE", w.r_hx > 0.7)) if not ok]


def reactor_scram(w: World, reason):
    if w.r_mode in ("ONLINE", "RUNBACK", "STARTING"):
        w.r_mode = "SCRAM"
        w.r_mode_ticks = 0
        w.r_shutdown_t = w.t
        w.r_power_mw = 0.0
        w.log("ALARM", f"Reactor SCRAM ({reason})")


