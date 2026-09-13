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
    "storm_prob_per_tick": 0.0004,
    "storm_len_ticks": (180, 600),
    "storm_wind": (22.0, 34.0),
    "calm_wind": (4.0, 14.0),
    "daylight_max": 0.3,
    # houses
    "heater_kw": [3.5, 3.0, 3.0, 4.5],          # by type: barracks, standard, insulated, manager
    "ua_w_per_k": [38.0, 32.0, 22.0, 45.0],
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
    "mine_income_per_tick": 3.0,
    "reactor_upkeep_month": 3000.0,
    # incidents: probability per tick
    "p_xeno": 0.00004, "p_vandal": 0.00025, "p_animal": 0.0002, "p_rover_hit": 0.0003,
    "p_nest_fire": 0.02,           # per tick while a xeno attack near the processor is open
    "p_pump_wear": 0.00002,
    # sewage and waste
    "sludge_per_resident_per_tick": 1.0 / (1440 * 60),   # station tank full in ~30 days for a family
    "waste_per_resident_per_tick": 1.0 / (1440 * 6 * 50),   # sector bin full in ~6 days
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
            Rover("engineer-2", "repair", angle=345.0, speed=8.0),
            Rover("plumber", "plumber", angle=285.0, speed=8.0),
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


# ------------------------------------------------------------------------------------
# Grid, balance, ups
# ------------------------------------------------------------------------------------

def grid_rebuild(w: World):
    """Recompute who is online down the tree. Spans are cut by fallen poles and low health."""
    PPS = w.cfg["poles_per_sector"]
    # fallen pole cuts the span feeding it and the next one
    fallen = w.p_state == 2
    cut = np.zeros(w.P, dtype=bool)
    cut |= fallen
    nxt = np.roll(fallen, 1)
    nxt[w.p_k == 0] = False
    cut |= nxt
    span_ok = (w.s_health >= 0.2) & ~cut
    # cumulative along each sector chain
    span_ok_m = span_ok.reshape(w.S, PPS)
    chain = np.cumprod(span_ok_m, axis=1).astype(bool)
    sector_feed = w.trunk_ok & w.substation_ok & w.feeder_ok & w.rp_ok
    w.feeder_online = sector_feed
    w.s_online = (chain & sector_feed[:, None]).reshape(-1)
    # internet cable on the same route
    net_span = w.n_span_ok & ~cut
    w.net_chain = np.cumprod(net_span.reshape(w.S, PPS), axis=1).astype(bool).reshape(-1)


def houses_decide(w: World):
    """House programs: thermostat with modes chosen from the power situation."""
    c = w.cfg
    target = np.full(w.N, c["comfort_c"])
    target[w.h_on_ups | (w.h_limit_w > 0)] = c["eco_c"]
    target[(w.h_limit_w > 0) & (w.h_limit_w <= c["limit_level5_w"])] = c["antifreeze_c"]
    w.h_target = target
    on = w.h_heater_on.copy()
    on[w.h_t_in < target - 0.5] = True
    on[w.h_t_in > target + 0.5] = False
    w.h_heater_on = on
    # valve closes when pipes burst (a good program does this)
    w.h_valve_open = ~w.h_burst


def houses_demand(w: World):
    """Desired draw per house given limit and priorities."""
    c = w.cfg
    night = w.is_night()
    base = w.h_base_w * (0.6 if night else 1.0) + w.rng.uniform(-50, 50, w.N)
    base = np.maximum(base, 80.0)
    heater = np.where(w.h_heater_on, w.h_heater_w, 0.0)
    aeration = np.where(w.h_aeration_ok, c["aeration_w"], 0.0)
    want = base + heater + aeration
    limit = w.h_limit_w
    lim = np.where(limit > 0, limit, 1e9)
    # priorities inside the limit: aeration and fridge (100 W) first, heater, then the rest
    essential = aeration + 100.0
    heat_alloc = np.minimum(heater, np.maximum(0.0, lim - essential))
    rest = np.minimum(base - 100.0, np.maximum(0.0, lim - essential - heat_alloc))
    draw = essential + heat_alloc + rest
    draw = np.minimum(draw, want)
    return draw, heat_alloc


def power_step(w: World):
    c = w.cfg
    S = w.S
    grid_rebuild(w)
    # sources
    w.solar_kw = c["solar_peak_kw"] * w.daylight * (1 - w.dust) * w.solar_health
    reactor_kw = w.r_available_mw * 1000.0 if (w.trunk_ok and w.substation_ok) else 0.0
    available = reactor_kw + (w.solar_kw if w.substation_ok else 0.0)

    # demand from houses with current limits
    houses_decide(w)
    house_pole_online = w.s_online[w.h_pole] & w.h_wiring_ok
    draw, heat_alloc = houses_demand(w)
    # infrastructure loads
    infra = {
        "mine": c["mine_kw"] * w.mine_frac,
        "water_plant": c["water_plant_kw"] if w.water_plant_ok else 0.0,
        "waste_storage": c["waste_storage_kw"],
        "ops_center": c["ops_center_kw"],
        "comms": c["comms_kw"] + (c["comms_kw"] * 0.5 if w.tower_line_ok else 0.0),
        "cabinets": c["cabinet_kw"] * S,
        "gates": c["gate_kw"] * S,
        "lamps": 0.0,
        "road_heating": c["road_heating_kw"] if (w.road_icy and w.shedding < 2) else 0.0,
        "pump_station": c["pump_station_kw"],
        "ups_charge": 0.0,
    }
    lamps_on = w.p_lamp_ok & (w.s_online) & (w.shedding < 4) & (w.is_night() or w.storm_ticks > 0 or w.precip == "snow")
    lamp_kw = c["lamp_kw"] * (1.2 if w.storm_lighting else 1.0)
    infra["lamps"] = float(lamps_on.sum()) * lamp_kw
    w.p_lamp_on = lamps_on
    w.road_heating_on = infra["road_heating"] > 0
    # ups charging demand
    need = np.maximum(0.0, c["ups_sector_kwh"] - w.ups_kwh)
    charge_kw = np.where((need > 0) & w.feeder_online & (w.shedding < 2), c["ups_charge_kw"], 0.0)
    center_need = c["ups_center_kwh"] - w.ups_center_kwh
    center_charge = c["ups_charge_kw"] if (center_need > 0 and w.substation_ok and w.trunk_ok and w.shedding < 2) else 0.0
    infra["ups_charge"] = float(charge_kw.sum()) + center_charge

    grid_house_draw = np.where(house_pole_online, draw, 0.0)
    sector_draw = np.bincount(w.h_sector, weights=grid_house_draw, minlength=S) / 1000.0
    demand = float(sector_draw.sum()) + sum(infra.values())
    w.sector_demand_kw = sector_draw

    # balance and shedding
    deficit = max(0.0, demand - available)
    if deficit > 0 and available > 0:
        if w.shedding < 8:
            w.shedding += 1
            if w.shedding > w.max_shed_logged or w.t - w.shed_log_t > 240:
                w.log("WARN", f"Load shedding level {w.shedding}, deficit {deficit:.0f} kW")
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
    w.mine_frac = (1.0 if w.shedding < 6 else 0.5 if w.shedding < 7 else 0.0) if (available > 0 and reactor_up) else 0.0
    w.mine_powered = w.mine_frac > 0

    # apply limits for next tick
    limit = np.zeros(w.N)
    if w.shedding >= 3:
        limit[:] = c["limit_level3_w"]
    if w.shedding >= 5:
        limit[:] = c["limit_level5_w"]
    # level 8: whole sectors dropped, from 6 down
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

    # UPS per sector when feed is lost
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
                # ups feeds houses whose local chain is intact, with a 2 kW limit each
                m = mask & house_pole_online & ~house_feed_ok
                limit[m] = np.minimum(np.where(limit[m] > 0, limit[m], 1e9), c["limit_level3_w"])
                sup = min(c["ups_sector_kw"], float(np.minimum(draw[m], c["limit_level3_w"]).sum()) / 1000.0)
                w.ups_kwh[s] = max(0.0, w.ups_kwh[s] - sup / 60.0)
                powered[m] = True
                on_ups[m] = True
                w.ups_state[s] = "DISCHARGING"
                if w.ups_kwh[s] <= 0:
                    w.ups_state[s] = "DEPLETED"
                    w.log("ALARM", f"Sector {s + 1} UPS depleted")
            else:
                w.ups_state[s] = "DEPLETED" if w.ups_kwh[s] <= 0 else "FAULT"
    # center ups
    if w.substation_ok and w.trunk_ok and available > 0:
        w.ups_center_kwh = min(c["ups_center_kwh"], w.ups_center_kwh + center_charge / 60.0)
        w.ups_center_state = "CHARGING" if center_charge > 0 else "STANDBY"
        w.comms_powered = True
        w.pump_station_ok = True
    else:
        if w.ups_center_kwh > 0:
            w.ups_center_kwh = max(0.0, w.ups_center_kwh - (c["ops_center_kw"] + c["comms_kw"] + c["pump_station_kw"]) / 60.0)
            w.ups_center_state = "DISCHARGING"
            w.comms_powered = True
            w.pump_station_ok = True
        else:
            w.ups_center_state = "DEPLETED"
            w.comms_powered = False
            w.pump_station_ok = False

    # final house feed
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
    w.infra_loads_kw = {k: round(v, 1) for k, v in infra.items()}
    # lamps: dark sectors
    lamps_by_sector = np.bincount(w.p_sector, weights=w.p_lamp_on.astype(float), minlength=S)
    w.sector_dark = (lamps_by_sector < 2) & np.array([w.is_night()] * S)
    # mine income
    if w.mine_frac > 0:
        w.colony_budget += c["mine_income_per_tick"] * w.mine_frac
        w.colony_month_income += c["mine_income_per_tick"] * w.mine_frac


# ------------------------------------------------------------------------------------
# Houses: thermal, pipes, water
# ------------------------------------------------------------------------------------

def houses_step(w: World):
    c = w.cfg
    dt = c["tick_seconds"]
    ua_eff = w.h_ua * (1.0 + 0.006 * w.wind)
    q_loss = ua_eff * (w.h_t_in - w.t_out)
    q_int = (w.h_draw_w - w.h_heat_w) * 0.8 + w.h_residents * 80.0   # appliances and people turn into heat
    w.h_t_in += (w.h_heat_w + q_int - q_loss) * dt / w.h_cap
    # pipes
    cold = w.h_t_in < 0.0
    w.h_frozen = np.where(cold, w.h_frozen + 1, 0)
    newly_frozen = (w.h_frozen == c["freeze_ticks_to_frozen"]) & w.h_pipes_ok
    for i in np.flatnonzero(newly_frozen):
        w.h_pipes_ok[i] = False
        w.log("WARN", f"House {i + 1}: pipes frozen")
    burst_now = (w.h_frozen == c["freeze_ticks_to_frozen"] + c["frozen_ticks_to_burst"]) & ~w.h_burst
    for i in np.flatnonzero(burst_now):
        w.h_burst[i] = True
        cost_mul = 0.5 if not w.h_valve_open[i] else 1.0
        iss = w.open_issue("pipes_burst", f"house:{i}", int(w.h_sector[i]), "freeze", "pipes",
                           (float(w.h_x[i]), float(w.h_y[i])), "critical")
        iss.cost *= cost_mul
    # water
    supply = w.water_tank_m3 > 0 and w.pump_station_ok
    w.h_water_ok = supply & w.water_main_ok[w.h_sector] & w.h_pipes_ok & ~w.h_burst
    use = np.where(w.h_water_ok, c["water_per_house_m3_day"] / 1440.0 * (1 + 0.5 * w.h_residents), 0.0)
    w.h_water_m3 += use
    w.h_water_day += use
    w.h_water_month += use
    w.sector_water_m3 = np.bincount(w.h_sector, weights=use, minlength=w.S)
    w.water_tank_m3 = max(0.0, w.water_tank_m3 - float(use.sum()))
    # sewage: aeration stations need power; sludge accumulates
    w.h_aeration_ok = w.h_aeration_ok & True
    w.h_sludge += np.where(w.h_water_ok, c["sludge_per_resident_per_tick"] * (1 + w.h_residents), 0.0)
    w.h_sludge = np.minimum(w.h_sludge, 1.0)


def water_step(w: World):
    c = w.cfg
    w.water_plant_ok = w.water_plant_heat and w.trunk_ok
    if w.water_plant_ok:
        w.water_tank_m3 = min(c["water_tank_m3"], w.water_tank_m3 + c["water_plant_m3_h"] / 60.0)
    if w.water_tank_m3 <= 0 and w.t % 60 == 0:
        w.log("ALARM", "Water tank empty")
# ------------------------------------------------------------------------------------
# Internet
# ------------------------------------------------------------------------------------

def internet_step(w: World):
    c = w.cfg
    S = w.S
    center_ok = w.comms_ok and getattr(w, "comms_powered", True)
    w.uplink_ok = center_ok and w.tower_ok and w.tower_line_ok and w.trunk_ok and w.substation_ok
    for s in range(S):
        if w.sector_online[s] and w.rp_ok[s]:
            w.cabinet_ups_h[s] = min(2.0, w.cabinet_ups_h[s] + 1 / 240)
            powered = True
        else:
            w.cabinet_ups_h[s] = max(0.0, w.cabinet_ups_h[s] - 1 / 60)
            powered = w.cabinet_ups_h[s] > 0
        w.cabinet_online[s] = bool(w.cabinet_ok[s] and powered and center_ok)
    w.net_sector_online = w.cabinet_online
    house_net = w.net_chain[w.h_pole] & w.h_terminal_ok & w.cabinet_online[w.h_sector] & w.h_power_ok
    w.h_net_online = house_net
    # packets for the ui: telemetry from a few random houses, a control packet to the reactor
    if w.t % 2 == 0:
        online = np.flatnonzero(house_net)
        if len(online):
            pick = w.rng.choice(online, size=min(4, len(online)), replace=False)
            for i in pick:
                w.packets.append({"t": w.t, "from": "house", "id": int(i), "sector": int(w.h_sector[i]),
                                  "uplink": bool(w.uplink_ok), "kind": "telemetry"})
    if w.t % 5 == 0 and center_ok:
        w.packets.append({"t": w.t, "from": "hub", "id": -1, "sector": -1, "uplink": bool(w.uplink_ok and w.r_link_ok),
                          "kind": "reactor" if w.r_link_ok else "lost"})
    w.r_link_ok = center_ok and w.trunk_ok
    w.packets = [p for p in w.packets if w.t - p["t"] < 6]


# ------------------------------------------------------------------------------------
# Roads, gates, rovers, waste, sewage
# ------------------------------------------------------------------------------------

def angle_diff(a, b):
    """Signed shortest difference b - a in degrees."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return d


def road_segment_of(angle):
    return int((angle % 360.0) // 60.0)


def path_blocked(w: World, a0, a1, direction, rover: Rover):
    """Walk from a0 to a1 in the given direction (+1 ccw / -1 cw); return True if a broken road or a locked gate is in the way."""
    a = a0
    steps = 0
    while abs(angle_diff(a, a1)) > 1.0 and steps < 400:
        seg = road_segment_of(a + direction * 0.5)
        if w.road_integrity[seg] < 20 and rover.kind != "repair":
            return True
        # gate at multiples of 60
        nxt = a + direction * 1.0
        if int(a // 60) != int(nxt // 60):
            g = int((nxt if direction > 0 else a) // 60) % 6
            if w.gate_state[g] == "LOCKDOWN":
                return True
        a = nxt
        steps += 1
    return False


def rover_move(w: World, r: Rover):
    """Move rover toward its target: along the ring first, then radially."""
    R = w.cfg["ring_road_radius"]
    if r.wait > 0:
        r.wait -= 1
        return False
    # radial move back to the ring if we are off it and the angle differs
    if abs(angle_diff(r.angle, r.target_angle)) > 1.0:
        if abs(r.radius - R) > 2:
            r.radius += clamp(R - r.radius, -25, 25)
            return False
        d = angle_diff(r.angle, r.target_angle)
        direction = 1 if d > 0 else -1
        if path_blocked(w, r.angle, r.target_angle, direction, r):
            if not path_blocked(w, r.angle, r.target_angle, -direction, r):
                direction = -direction
            else:
                r.wait = 5
                return False
        step = min(abs(d), r.speed * (0.5 if w.road_icy and not w.road_heating_on else 1.0))
        new_angle = r.angle + direction * step
        # gate crossing costs a couple of ticks
        if int(r.angle // 60) != int(new_angle // 60):
            r.wait = 2
        r.angle = new_angle % 360.0
        return False
    r.angle = r.target_angle
    if abs(r.radius - r.target_radius) > 2:
        r.radius += clamp(r.target_radius - r.radius, -25, 25)
        return False
    r.radius = r.target_radius
    return True


def rover_xy(w: World, r: Rover):
    a = math.radians(r.angle)
    return r.radius * math.cos(a), r.radius * math.sin(a)


def sector_storage_angle(s):
    return s * 60.0 + 30.0


def roads_step(w: World):
    c = w.cfg
    S = w.S
    # degradation: freeze-thaw-ish wear and traffic
    wear = 0.0004 + (0.001 if w.road_icy and not w.road_heating_on else 0.0)
    w.road_integrity = np.maximum(0.0, w.road_integrity - wear)
    for s in range(S):
        if w.road_integrity[s] < 20:
            w.open_issue("road_blocked", f"road:{s}", s, "wear", "road",
                         (c["ring_road_radius"] * math.cos(math.radians(s * 60 + 30)),
                          c["ring_road_radius"] * math.sin(math.radians(s * 60 + 30))))
    # gates
    for s in range(S):
        if w.lockdown_ticks[s] > 0:
            w.lockdown_ticks[s] -= 1
            w.gate_state[s] = "LOCKDOWN"
            if w.lockdown_ticks[s] == 0:
                w.gate_state[s] = "OPEN"
                w.log("INFO", f"Sector {s + 1} lockdown lifted")
        elif not w.gate_ok[s]:
            w.gate_state[s] = "CLOSED"
        elif not w.sector_online[s] and w.ups_state[s] in ("DEPLETED", "FAULT"):
            pass  # unpowered: keep last state
        else:
            w.gate_state[s] = "OPEN"
    # waste accumulation and sanitary index
    residents = np.bincount(w.h_sector, weights=w.h_residents, minlength=S)
    w.waste_level = np.minimum(1.2, w.waste_level + residents * c["waste_per_resident_per_tick"])
    sludge_req = np.bincount(w.h_sector, weights=(w.h_sludge >= 0.95).astype(float), minlength=S)
    overflow = w.waste_level >= 1.0
    sewage_bad = (~w.h_aeration_ok) | (w.h_sludge >= 1.0)
    sew_bad_frac = np.bincount(w.h_sector, weights=sewage_bad.astype(float), minlength=S) / c["houses_per_sector"]
    w.sanitary = np.clip(w.sanitary - overflow * 0.05 - sew_bad_frac * 0.1 + (~overflow) * 0.02, 0, 100)
    # rovers
    garbage, sludge = w.rovers[0], w.rovers[1]
    _garbage_rover(w, garbage)
    _sludge_rover(w, sludge, sludge_req)
    for r in w.rovers[2:]:
        _repair_rover(w, r)


def _garbage_rover(w: World, r: Rover):
    c = w.cfg
    R = c["ring_road_radius"]
    if r.state == "IDLE":
        need = np.flatnonzero(w.waste_level >= 0.9)
        if len(need):
            s = int(need[np.argmax(w.waste_level[need])])
            r.job = s
            r.state = "TO_BIN"
            r.target_angle = sector_storage_angle(s)
            r.target_radius = R + 20
    elif r.state == "TO_BIN":
        if rover_move(w, r):
            r.state = "LOADING"
            r.timer = 10
    elif r.state == "LOADING":
        r.timer -= 1
        if r.timer <= 0:
            s = r.job
            take = min(1.0 - r.load, float(w.waste_level[s]))
            w.waste_level[s] -= take
            r.load += take
            if finance_pay(w, "waste_trip", s, "normal_operation", f"waste collection sector {s + 1}"):
                w.log("INFO", f"Garbage rover emptied sector {s + 1} bin")
            else:
                w.log("WARN", f"Sector {s + 1} could not pay for waste collection")
            if r.load >= 0.99 or not np.any(w.waste_level >= 0.9):
                r.state = "TO_STATION"
                r.target_angle = 180.0
                r.target_radius = 520.0
            else:
                r.state = "IDLE"
    elif r.state == "TO_STATION":
        if rover_move(w, r):
            r.state = "UNLOADING"
            r.timer = 15
    elif r.state == "UNLOADING":
        r.timer -= 1
        if r.timer <= 0:
            w.waste_station_level += r.load
            r.load = 0.0
            r.state = "IDLE"
            r.target_angle = 195.0
            r.target_radius = R


def _sludge_rover(w: World, r: Rover, sludge_req):
    c = w.cfg
    R = c["ring_road_radius"]
    if r.state == "IDLE":
        full = np.flatnonzero(w.h_sludge >= 0.95)
        if len(full):
            i = int(full[0])
            r.job = i
            r.state = "TO_HOUSE"
            r.target_angle = float(w.h_angle[i])
            r.target_radius = float(w.h_radius[i]) + 12
        elif r.load > 0.5:
            r.state = "TO_STORE"
            s = int(np.argmin(w.sludge_store))
            r.job = s
            r.target_angle = sector_storage_angle(s) + 8
            r.target_radius = R + 20
    elif r.state == "TO_HOUSE":
        if rover_move(w, r):
            r.state = "PUMPING"
            r.timer = 8
    elif r.state == "PUMPING":
        r.timer -= 1
        if r.timer <= 0:
            i = r.job
            r.load = min(1.0, r.load + float(w.h_sludge[i]) * 0.25)
            w.h_sludge[i] = 0.05
            finance_pay(w, "sludge_trip", int(w.h_sector[i]), "normal_operation", f"sludge collection house {i + 1}")
            r.state = "IDLE"
            if r.load >= 0.99:
                r.state = "TO_STORE"
                s = int(np.argmin(w.sludge_store))
                r.job = s
                r.target_angle = sector_storage_angle(s) + 8
                r.target_radius = R + 20
    elif r.state == "TO_STORE":
        if rover_move(w, r):
            s = r.job
            w.sludge_store[s] = min(1.0, w.sludge_store[s] + r.load * 0.2)
            r.load = 0.0
            r.state = "IDLE"
            r.target_radius = R
    # sector storage slowly processed
    w.sludge_store = np.maximum(0.0, w.sludge_store - 0.00005)


HOUSE_TARGETS = ("house", "aeration", "terminal")
REPAIR_PRIORITY = {"reactor": 0, "trunk": 1, "substation": 1, "feeder": 2, "rp": 2, "ups": 3, "pole": 3, "span": 4,
                   "cabinet": 4, "tower_line": 5, "net_span": 5, "gate": 5, "road": 5, "lamp": 6, "solar": 6}


def _repair_rover(w: World, r: Rover):
    c = w.cfg
    R = c["ring_road_radius"]
    if r.state == "IDLE":
        # engineer takes infrastructure, plumber takes house-level issues
        cands = [i for i in w.issues if i.status == "funded"
                 and ((i.target.split(":")[0] in HOUSE_TARGETS) == (r.kind == "plumber"))]
        if cands:
            cands.sort(key=lambda i: (REPAIR_PRIORITY.get(i.target.split(":")[0], 9), i.severity != "critical", i.opened_t))
            iss = cands[0]
            r.job = iss
            iss.status = "in_progress"
            iss.started_t = w.t
            r.state = "TO_TARGET"
            x, y = iss.pos
            r.target_angle = math.degrees(math.atan2(y, x)) % 360.0
            r.target_radius = max(90.0, min(560.0, math.hypot(x, y) + 15))
            if iss.target.startswith("reactor") or iss.target.startswith("trunk") or iss.target.startswith("solar") \
                    or iss.target.startswith("water_plant"):
                r.target_angle = 180.0
                r.target_radius = 560.0
            if iss.target.startswith("tower"):
                r.target_angle = 220.0
                r.target_radius = 480.0
            if iss.target.startswith("substation") or iss.target.startswith("feeder") or iss.target.startswith("hub"):
                r.target_radius = 95.0
    elif r.state == "TO_TARGET":
        if rover_move(w, r):
            r.state = "REPAIRING"
            r.timer = r.job.duration
            # xenomorph attack on a crew in a dark sector
            s = r.job.sector
            if s >= 0 and w.sector_dark[s] and w.rng.random() < 0.15:
                w.log("ALARM", f"Repair crew attacked by xenomorphs in dark sector {s + 1}, repair aborted")
                r.job.status = "funded"
                r.job = None
                r.state = "IDLE"
                r.wait = 60
                spawn_xeno(w, s)
    elif r.state == "REPAIRING":
        r.timer -= 1
        if r.timer <= 0:
            resolve_issue(w, r.job)
            r.job = None
            r.state = "IDLE"
            r.target_radius = R


# ------------------------------------------------------------------------------------
# Incidents, damage, repair resolution
# ------------------------------------------------------------------------------------

def damage_target(w: World, target: str, cause: str, severity: float):
    c = w.cfg
    kind, _, arg = target.partition(":")
    if kind == "span":
        i = int(arg)
        w.s_health[i] = max(0.0, w.s_health[i] - severity)
        if w.s_health[i] < 0.2:
            w.open_issue("span_broken", target, int(w.p_sector[i]), cause, "span", (float(w.p_x[i]), float(w.p_y[i])))
    elif kind == "net_span":
        i = int(arg)
        w.n_span_ok[i] = False
        w.open_issue("cable_broken", target, int(w.p_sector[i]), cause, "net_span", (float(w.p_x[i]), float(w.p_y[i])))
    elif kind == "pole":
        i = int(arg)
        if severity > 0.7:
            w.p_state[i] = 2
            w.p_lamp_ok[i] = False
            w.open_issue("pole_fallen", target, int(w.p_sector[i]), cause, "pole", (float(w.p_x[i]), float(w.p_y[i])), "critical")
        elif severity > 0.3:
            w.p_state[i] = max(w.p_state[i], 1)
            w.open_issue("pole_tilted", target, int(w.p_sector[i]), cause, "pole", (float(w.p_x[i]), float(w.p_y[i])))
    elif kind == "lamp":
        i = int(arg)
        w.p_lamp_ok[i] = False
        w.open_issue("lamp_broken", target, int(w.p_sector[i]), cause, "lamp", (float(w.p_x[i]), float(w.p_y[i])), "info")
    elif kind == "house":
        i = int(arg)
        w.h_wiring_ok[i] = False
        w.open_issue("house_wiring", target, int(w.h_sector[i]), cause, "wiring", (float(w.h_x[i]), float(w.h_y[i])))
    elif kind == "aeration":
        i = int(arg)
        w.h_aeration_ok[i] = False
        w.open_issue("aeration_failure", target, int(w.h_sector[i]), cause, "aeration", (float(w.h_x[i]), float(w.h_y[i])))
    elif kind == "terminal":
        i = int(arg)
        w.h_terminal_ok[i] = False
        w.open_issue("terminal_broken", target, int(w.h_sector[i]), cause, "terminal", (float(w.h_x[i]), float(w.h_y[i])), "info")
    elif kind == "cabinet":
        s = int(arg)
        w.cabinet_ok[s] = False
        a = math.radians(s * 60 + 30)
        w.open_issue("cabinet_damaged", target, s, cause, "cabinet", (95 * math.cos(a), 95 * math.sin(a)))
    elif kind == "gate":
        s = int(arg)
        w.gate_ok[s] = False
        a = math.radians(s * 60)
        R = c["ring_road_radius"]
        w.open_issue("gate_damaged", target, s, cause, "gate", (R * math.cos(a), R * math.sin(a)))
    elif kind == "road":
        s = int(arg)
        w.road_integrity[s] = max(0.0, w.road_integrity[s] - severity * 100)
    elif kind == "feeder":
        s = int(arg)
        w.feeder_ok[s] = False
        a = math.radians(s * 60 + 30)
        w.open_issue("feeder_broken", target, s, cause, "feeder", (60 * math.cos(a), 60 * math.sin(a)), "critical")
    elif kind == "rp":
        s = int(arg)
        w.rp_ok[s] = False
        a = math.radians(s * 60 + 30)
        w.open_issue("rp_damaged", target, s, cause, "rp", (85 * math.cos(a), 85 * math.sin(a)), "critical")
    elif kind == "trunk":
        w.trunk_ok = False
        w.open_issue("trunk_broken", "trunk", -1, cause, "trunk", (-360, 0), "critical")
    elif kind == "substation":
        w.substation_ok = False
        w.open_issue("substation_damaged", "substation", -1, cause, "substation", (0, 0), "critical")
    elif kind == "tower_line":
        w.tower_line_ok = False
        w.open_issue("tower_line_broken", "tower_line", -1, cause, "tower_line", (-220, -190), "warning")
    elif kind == "solar":
        w.solar_health = max(0.0, w.solar_health - severity)
        w.open_issue("solar_damaged", "solar", -1, cause, "solar", (-640, -110), "info")
    elif kind == "reactor":
        comp = arg
        if comp == "heat_exchanger":
            w.r_hx = max(0.0, w.r_hx - severity)
            w.open_issue("heat_exchanger_damage", target, -1, cause, "heat_exchanger", c["reactor_pos"], "critical")
        elif comp in ("pump_a", "pump_b"):
            setattr(w, "r_" + comp, 0.1)
            w.open_issue("pump_trip", target, -1, cause, "pump", c["reactor_pos"], "critical")
    elif kind == "ups":
        s = int(arg)
        w.ups_health[s] = 0.1
        a = math.radians(s * 60 + 30)
        w.open_issue("ups_damaged", target, s, cause, "ups", (100 * math.cos(a), 100 * math.sin(a)))


def resolve_issue(w: World, iss: Issue):
    kind, _, arg = iss.target.partition(":")
    if kind == "span":
        w.s_health[int(arg)] = 1.0
    elif kind == "net_span":
        w.n_span_ok[int(arg)] = True
    elif kind == "pole":
        i = int(arg)
        w.p_state[i] = 0
        w.p_lamp_ok[i] = True
        # a fallen pole also cut the spans and the cable: they are fixed with it
        w.s_health[i] = max(w.s_health[i], 1.0)
        if w.p_k[i] + 1 < w.cfg["poles_per_sector"]:
            w.s_health[i + 1] = 1.0
            w.n_span_ok[i + 1] = True
        w.n_span_ok[i] = True
    elif kind == "lamp":
        w.p_lamp_ok[int(arg)] = True
    elif kind == "house":
        i = int(arg)
        if iss.kind == "pipes_burst":
            w.h_burst[i] = False
            w.h_pipes_ok[i] = True
            w.h_frozen[i] = 0
        else:
            w.h_wiring_ok[i] = True
    elif kind == "aeration":
        w.h_aeration_ok[int(arg)] = True
    elif kind == "terminal":
        w.h_terminal_ok[int(arg)] = True
    elif kind == "cabinet":
        w.cabinet_ok[int(arg)] = True
    elif kind == "gate":
        w.gate_ok[int(arg)] = True
    elif kind == "road":
        w.road_integrity[int(arg)] = 100.0
    elif kind == "feeder":
        w.feeder_ok[int(arg)] = True
    elif kind == "rp":
        w.rp_ok[int(arg)] = True
    elif kind == "trunk":
        w.trunk_ok = True
    elif kind == "substation":
        w.substation_ok = True
    elif kind == "tower_line":
        w.tower_line_ok = True
    elif kind == "solar":
        w.solar_health = 1.0
    elif kind == "reactor":
        comp = arg
        if comp == "heat_exchanger":
            w.r_hx = 1.0
        else:
            setattr(w, "r_" + comp, 1.0)
    elif kind == "ups":
        w.ups_health[int(arg)] = 1.0
    iss.status = "resolved"
    iss.resolved_t = w.t
    finance_record(w, iss.cost, iss.payer, iss.sector, iss.cause, f"repair {iss.kind} {iss.target}")
    w.log("INFO", f"Repaired {iss.kind} at {iss.target}, {iss.cost:.0f} cr")


def spawn_xeno(w: World, s):
    a = math.radians(s * 60 + w.rng.uniform(5, 55))
    r = w.rng.uniform(140, 330)
    w.xeno_markers.append({"x": r * math.cos(a), "y": r * math.sin(a), "until": w.t + 90, "sector": s})


def incidents_step(w: World):
    c = w.cfg
    S = w.S
    rng = w.rng
    night = w.is_night()
    # weather on spans: logistic in wind, ice, cold
    v = w.wind
    z = 0.35 * (v - 22.0) + 3.0 * w.s_ice + 0.03 * (-w.t_out - 40) - 10.0
    p = 1.0 / (1.0 + np.exp(-z)) * 0.02
    p = p * np.where(w.p_state == 1, 2.0, 1.0)
    hit = rng.random(w.P) < p
    for i in np.flatnonzero(hit & (w.s_health >= 0.2)):
        damage_target(w, f"span:{i}", "weather", 1.0)
        if rng.random() < 0.5:
            damage_target(w, f"net_span:{i}", "weather", 1.0)
    # xenomorphs
    pxeno = c["p_xeno"] * (3.0 if night else 1.0)
    for s in range(S):
        if rng.random() < pxeno * (2.0 if w.sector_dark[s] else 1.0):
            spawn_xeno(w, s)
            w.lockdown_ticks[s] = 120
            w.gate_state[s] = "LOCKDOWN"
            w.log("ALARM", f"Xenomorphs in sector {s + 1}: LOCKDOWN")
            roll = rng.random()
            base = s * c["poles_per_sector"]
            if roll < 0.4:
                damage_target(w, f"cabinet:{s}", "xenomorph", 1.0)
            elif roll < 0.7:
                damage_target(w, f"pole:{base + int(rng.integers(1, c['poles_per_sector']))}", "xenomorph", 0.9)
            else:
                hs = np.flatnonzero(w.h_sector == s)
                damage_target(w, f"house:{int(rng.choice(hs))}", "xenomorph", 1.0)
    # nest near the processor: marines show up and shoot the cooling
    if rng.random() < c["p_xeno"] * 0.5:
        w.nest_alert = 300
        w.marines_active = 300
        w.log("ALARM", "Xenomorph nest activity under the atmosphere processor. Marines deployed.")
    if w.nest_alert > 0:
        w.nest_alert -= 1
        w.marines_active = max(0, w.marines_active - 1)
        if rng.random() < c["p_nest_fire"] / 10:
            comp = "heat_exchanger" if rng.random() < 0.6 else ("pump_a" if rng.random() < 0.5 else "pump_b")
            damage_target(w, f"reactor:{comp}", "marines", 0.6)
            w.log("ALARM", f"Stray marine fire damaged reactor {comp}")
    # vandals
    if rng.random() < c["p_vandal"] * (2.0 if night else 1.0):
        s = int(rng.integers(0, S))
        roll = rng.random()
        base = s * c["poles_per_sector"]
        if roll < 0.4:
            damage_target(w, f"lamp:{base + int(rng.integers(0, c['poles_per_sector']))}", "vandal", 1.0)
        elif roll < 0.6:
            damage_target(w, f"gate:{s}", "vandal", 1.0)
        elif roll < 0.8:
            hs = np.flatnonzero(w.h_sector == s)
            damage_target(w, f"terminal:{int(rng.choice(hs))}", "vandal", 1.0)
        else:
            hs = np.flatnonzero(w.h_sector == s)
            damage_target(w, f"aeration:{int(rng.choice(hs))}", "vandal", 1.0)
    # animals
    if rng.random() < c["p_animal"]:
        i = int(rng.integers(0, w.N))
        if rng.random() < 0.5:
            damage_target(w, f"house:{i}", "wildlife", 1.0)
        else:
            damage_target(w, f"aeration:{i}", "wildlife", 1.0)
    # rover collisions with poles in the dark
    for s in range(S):
        if w.sector_dark[s] and rng.random() < c["p_rover_hit"]:
            base = s * c["poles_per_sector"]
            damage_target(w, f"pole:{base + int(rng.integers(0, c['poles_per_sector']))}", "impact", 0.9)
            w.log("WARN", f"Rover hit a pole in dark sector {s + 1}")
    # xeno marker expiry
    w.xeno_markers = [m for m in w.xeno_markers if m["until"] > w.t]
    # funding of open issues
    for iss in w.issues:
        if iss.status in ("open", "unfunded") and (w.t - iss.opened_t) % 30 == 0:
            if finance_reserve(w, iss):
                iss.status = "funded"
            else:
                if iss.status == "open":
                    w.log("WARN", f"No funds for {iss.kind} at {iss.target} ({iss.cost:.0f} cr)")
                iss.status = "unfunded"


# ------------------------------------------------------------------------------------
# Finance
# ------------------------------------------------------------------------------------

def finance_reserve(w: World, iss: Issue):
    """Sector-first funding rule. Returns True if the money is available (charged on completion)."""
    if iss.payer == "colony":
        return w.colony_budget >= iss.cost
    s = iss.sector if iss.sector >= 0 else 0
    return w.sector_budget[s] >= iss.cost or w.colony_budget >= iss.cost


def finance_record(w: World, amount, payer, sector, cause, note):
    s = sector if sector >= 0 else 0
    src = "colony"
    if payer in ("sector", "house") and w.sector_budget[s] >= amount:
        w.sector_budget[s] -= amount
        w.month_expense[s] += amount
        src = f"sector {s + 1}"
    elif w.colony_budget >= amount:
        w.colony_budget -= amount
        w.colony_month_expense += amount
    else:
        w.unfunded_total += amount
        src = "unpaid"
    if payer == "house":
        # owner reimburses the sector at month end
        i = int(note.split("house:")[-1]) if "house:" in note else -1
        if 0 <= i < w.N:
            w.h_repairs_month[i] += amount
    w.cost_records.append({"t": w.t, "amount": amount, "payer": payer, "source": src, "cause": cause, "note": note})
    if len(w.cost_records) > 2000:
        w.cost_records = w.cost_records[-2000:]


def finance_pay(w: World, cost_key, sector, cause, note):
    cost, payer, _ = COSTS[cost_key]
    if w.sector_budget[sector] >= cost:
        finance_record(w, cost, "sector", sector, cause, note)
        return True
    if w.colony_budget >= cost:
        finance_record(w, cost, "colony", -1, cause, note)
        return True
    return False


def finance_day_close(w: World):
    """Owners pay energy and water daily, so sectors have cash flow during the month."""
    c = w.cfg
    bill = w.h_meter_day * c["tariff_kwh"] + w.h_water_day * c["tariff_water_m3"]
    income = np.bincount(w.h_sector, weights=bill, minlength=w.S)
    w.sector_budget += income
    w.month_income += income
    w.h_meter_day[:] = 0
    w.h_water_day[:] = 0


def finance_month_close(w: World):
    c = w.cfg
    S = w.S
    energy = w.h_meter_month * c["tariff_kwh"]
    water = w.h_water_month * c["tariff_water_m3"]
    sewage = np.full(w.N, c["sewage_fee"])
    internet = np.full(w.N, c["internet_fee"])
    repairs = w.h_repairs_month.copy()
    house_total = energy + water + sewage + internet + repairs
    # energy and water were paid daily; fees and repair reimbursements are paid now
    income = np.bincount(w.h_sector, weights=sewage + internet + repairs, minlength=S)
    w.sector_budget += income
    w.month_income += income
    # colony upkeep
    upkeep = c["reactor_upkeep_month"]
    w.colony_budget -= upkeep
    w.colony_month_expense += upkeep
    common_share = (w.colony_month_expense - w.colony_month_income) / w.N
    top = np.argsort(-house_total)[:5]
    w.last_report = {
        "month": w.month,
        "houses_total": float(house_total.sum()),
        "energy_total": float(energy.sum()), "water_total": float(water.sum()),
        "repairs_total": float(repairs.sum()),
        "kwh_total": float(w.h_meter_month.sum()),
        "sector_income": [round(float(x), 1) for x in income],
        "sector_expense": [round(float(x), 1) for x in w.month_expense],
        "sector_budget": [round(float(x), 1) for x in w.sector_budget],
        "colony_expense": round(w.colony_month_expense, 1),
        "colony_income": round(w.colony_month_income, 1),
        "colony_budget": round(w.colony_budget, 1),
        "common_share_per_house": round(float(common_share), 2),
        "unpaid": round(w.unfunded_total, 1),
        "top_houses": [{"house": int(i) + 1, "sector": int(w.h_sector[i]) + 1, "energy": round(float(energy[i]), 1),
                        "water": round(float(water[i]), 1), "repairs": round(float(repairs[i]), 1),
                        "total": round(float(house_total[i]), 1)} for i in top],
        "by_cause": _expense_by_cause(w),
    }
    w.log("INFO", f"Month {w.month} closed: owners paid {house_total.sum():.0f} cr, colony spent {w.colony_month_expense:.0f} cr")
    w.month += 1
    w.h_meter_month[:] = 0
    w.h_water_month[:] = 0
    w.h_water_m3[:] = 0
    w.h_repairs_month[:] = 0
    w.month_income[:] = 0
    w.month_expense[:] = 0
    w.colony_month_expense = 0.0
    w.colony_month_income = 0.0


def _expense_by_cause(w: World):
    out = {}
    for r in w.cost_records:
        if r["t"] > w.t - w.cfg["ticks_per_day"] * w.cfg["days_per_month"]:
            out[r["cause"]] = round(out.get(r["cause"], 0.0) + r["amount"], 1)
    return out


# ------------------------------------------------------------------------------------
# Tick
# ------------------------------------------------------------------------------------

def world_tick(w: World):
    if w.finished:
        return
    w.t += 1
    env_step(w)
    reactor_step(w)
    power_step(w)
    houses_step(w)
    water_step(w)
    internet_step(w)
    incidents_step(w)
    roads_step(w)
    if w.t % w.cfg["ticks_per_day"] == 0:
        finance_day_close(w)
    if w.t % (w.cfg["ticks_per_day"] * w.cfg["days_per_month"]) == 0:
        finance_month_close(w)


def inject(w: World, cmd: str):
    rng = w.rng
    if cmd == "span":
        i = int(rng.integers(0, w.P))
        damage_target(w, f"span:{i}", "vandal", 1.0)
        w.log("WARN", f"[manual] span {i} broken")
    elif cmd == "pole":
        i = int(rng.integers(0, w.P))
        damage_target(w, f"pole:{i}", "impact", 1.0)
        w.log("WARN", f"[manual] pole {i} fallen")
    elif cmd == "xeno":
        s = int(rng.integers(0, w.S))
        spawn_xeno(w, s)
        w.lockdown_ticks[s] = 120
        damage_target(w, f"cabinet:{s}", "xenomorph", 1.0)
        w.log("ALARM", f"[manual] xenomorph attack in sector {s + 1}")
    elif cmd == "storm":
        w.storm_ticks = 400
        w.storm_lighting = True
        w.log("WARN", "[manual] snowstorm")
    elif cmd == "trunk":
        damage_target(w, "trunk", "xenomorph", 1.0)
    elif cmd == "pump":
        damage_target(w, "reactor:pump_b", "wear", 1.0)
    elif cmd == "marines":
        w.nest_alert = 300
        w.marines_active = 300
        damage_target(w, "reactor:heat_exchanger", "marines", 0.8)
        w.log("ALARM", "[manual] marines hit the heat exchanger")
    elif cmd == "scram":
        reactor_scram(w, "operator")
    elif cmd == "money":
        w.colony_budget += 50000
        w.log("INFO", "[manual] corporation transferred 50 000 cr to the colony")
    elif cmd == "road":
        s = int(rng.integers(0, w.S))
        damage_target(w, f"road:{s}", "impact", 1.0)
        w.log("WARN", f"[manual] road segment {s + 1} collapsed")


# ------------------------------------------------------------------------------------
# Snapshot for the UI
# ------------------------------------------------------------------------------------

def snapshot(w: World):
    S = w.S
    sec = []
    for s in range(S):
        m = w.h_sector == s
        sec.append({
            "id": s + 1,
            "online": bool(w.sector_online[s]),
            "demand_kw": round(float(w.sector_demand_kw[s]), 1),
            "avg_t": round(float(w.h_t_in[m].mean()), 1),
            "min_t": round(float(w.h_t_in[m].min()), 1),
            "water_ok": int(w.h_water_ok[m].sum()),
            "power_ok": int(w.h_power_ok[m].sum()),
            "net_ok": int(w.h_net_online[m].sum()),
            "water_m3_h": round(float(w.sector_water_m3[s]) * 60, 2),
            "ups": w.ups_state[s], "ups_kwh": round(float(w.ups_kwh[s]), 0),
            "budget": round(float(w.sector_budget[s]), 0),
            "waste": round(float(w.waste_level[s]), 2),
            "sludge": round(float(w.sludge_store[s]), 2),
            "sanitary": round(float(w.sanitary[s]), 0),
            "gate": w.gate_state[s], "gate_ok": bool(w.gate_ok[s]),
            "road": round(float(w.road_integrity[s]), 0),
            "cabinet": bool(w.cabinet_online[s]),
            "dark": bool(w.sector_dark[s]),
            "lamps_on": int(w.p_lamp_on[w.p_sector == s].sum()),
        })
    issues = [{"id": i.id, "kind": i.kind, "target": i.target, "sector": i.sector + 1, "cause": i.cause,
               "cost": i.cost, "payer": i.payer, "status": i.status, "sev": i.severity,
               "x": round(i.pos[0]), "y": round(i.pos[1]), "age": w.t - i.opened_t}
              for i in w.open_issues()][-40:]
    return {
        "t": w.t, "time": w.time_str(), "paused": w.paused, "speed": w.speed,
        "finished": w.finished, "finish_reason": w.finish_reason,
        "env": {"t_out": round(w.t_out, 1), "wind": round(w.wind, 1), "precip": w.precip,
                "daylight": round(w.daylight, 2), "dust": round(w.dust, 2), "storm": w.storm_ticks > 0,
                "night": w.is_night(), "icy": w.road_icy, "visibility": w.visibility},
        "power": {"available_kw": round(w.available_kw), "demand_kw": round(w.demand_kw),
                  "deficit_kw": round(w.deficit_kw), "shedding": w.shedding, "solar_kw": round(w.solar_kw, 1),
                  "trunk": w.trunk_ok, "substation": w.substation_ok, "tower_line": w.tower_line_ok,
                  "feeder": [bool(x) for x in w.feeder_online], "mine": w.mine_powered,
                  "ups_center": w.ups_center_state, "ups_center_kwh": round(w.ups_center_kwh),
                  "infra": w.infra_loads_kw, "road_heating": w.road_heating_on, "storm_lighting": w.storm_lighting},
        "reactor": {"mode": w.r_mode, "power_mw": round(w.r_power_mw, 2), "available_mw": round(w.r_available_mw, 2),
                    "core_temp": round(w.r_core_temp), "decay_mw": round(w.r_decay_mw, 2),
                    "pump_a": round(w.r_pump_a, 2), "pump_b": round(w.r_pump_b, 2), "hx": round(w.r_hx, 2),
                    "battery_h": round(w.r_battery_h, 1), "faults": w.r_faults, "link": w.r_link_ok,
                    "marines": w.marines_active > 0},
        "water": {"tank_m3": round(w.water_tank_m3, 1), "plant": w.water_plant_ok, "heat": w.water_plant_heat,
                  "pump": w.pump_station_ok, "houses_ok": int(w.h_water_ok.sum()),
                  "burst": int(w.h_burst.sum()), "frozen": int((~w.h_pipes_ok).sum())},
        "net": {"uplink": w.uplink_ok, "tower": w.tower_ok, "comms": w.comms_ok, "houses_online": int(w.h_net_online.sum()),
                "packets": w.packets[-40:]},
        "finance": {"colony": round(w.colony_budget), "sectors": [round(float(x)) for x in w.sector_budget],
                    "unpaid": round(w.unfunded_total), "month": w.month,
                    "month_expense": round(w.colony_month_expense), "month_income": round(w.colony_month_income),
                    "waste_station": round(w.waste_station_level, 2)},
        "sectors": sec,
        "houses": {"t": [round(float(x), 1) for x in w.h_t_in], "power": w.h_power_ok.astype(int).tolist(),
                   "ups": w.h_on_ups.astype(int).tolist(), "water": w.h_water_ok.astype(int).tolist(),
                   "net": w.h_net_online.astype(int).tolist(), "heater": w.h_heater_on.astype(int).tolist(),
                   "burst": w.h_burst.astype(int).tolist(), "sludge": [round(float(x), 2) for x in w.h_sludge],
                   "limit": [int(x) for x in w.h_limit_w]},
        "poles": {"state": w.p_state.tolist(), "lamp": w.p_lamp_on.astype(int).tolist(),
                  "span": w.s_online.astype(int).tolist(), "net": w.net_chain.astype(int).tolist(),
                  "ice": [round(float(x), 2) for x in w.s_ice]},
        "rovers": [{"name": r.name, "state": r.state, "x": round(rover_xy(w, r)[0]), "y": round(rover_xy(w, r)[1]),
                    "load": round(r.load, 2)} for r in w.rovers],
        "xenos": [{"x": round(m["x"]), "y": round(m["y"])} for m in w.xeno_markers],
        "issues": issues, "issues_total": len(w.open_issues()),
        "events": list(w.events)[:40],
        "report": w.last_report,
    }


def house_geometry(w: World):
    return {
        "houses": {"x": [round(float(x)) for x in w.h_x], "y": [round(float(y)) for y in w.h_y],
                   "sector": w.h_sector.tolist(), "type": w.h_type.tolist(), "pole": w.h_pole.tolist()},
        "poles": {"x": [round(float(x)) for x in w.p_x], "y": [round(float(y)) for y in w.p_y],
                  "sector": w.p_sector.tolist(), "k": w.p_k.tolist()},
        "cfg": {"hub_radius": w.cfg["hub_radius"], "ring_road_radius": w.cfg["ring_road_radius"],
                "reactor": w.cfg["reactor_pos"], "tower": w.cfg["tower_pos"], "waste_station": w.cfg["waste_station_pos"],
                "sectors": w.S, "poles_per_sector": w.cfg["poles_per_sector"]},
        "types": TYPE_NAMES,
    }



# ------------------------------------------------------------------------------------
# Browser UI (served at /). Plain canvas, polls /state four times per second.
# ------------------------------------------------------------------------------------

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Hadley's Hope</title>
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --text:#d9dde6; --dim:#8a93a6; --ok:#5ec07a; --warn:#e0b04a; --bad:#e2574d; --blue:#5aa9ff; --cyan:#4fd1c5; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:13px/1.35 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display:flex; height:100vh; overflow:hidden; }
  #map { flex:1 1 auto; position:relative; }
  canvas { display:block; width:100%; height:100%; }
  #side { width:490px; flex:0 0 490px; background:var(--panel); border-left:1px solid var(--line); overflow-y:auto; padding:10px 12px; }
  h1 { font-size:15px; margin:0 0 6px; } h2 { font-size:12px; color:var(--dim); text-transform:uppercase; letter-spacing:.06em; margin:14px 0 6px; }
  .row { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
  button { background:#232835; color:var(--text); border:1px solid var(--line); border-radius:6px; padding:4px 8px; cursor:pointer; font-size:12px; }
  button:hover { background:#2d3444; } button.on { border-color:var(--blue); color:var(--blue); }
  .kpi { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
  .card { background:#1f2430; border:1px solid var(--line); border-radius:8px; padding:6px 8px; }
  .card .v { font-size:17px; font-weight:600; } .card .l { color:var(--dim); font-size:11px; }
  table { width:100%; border-collapse:collapse; font-size:11.5px; } th,td { padding:2px 3px; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap; } th { color:var(--dim); font-weight:500; } td:first-child, th:first-child { text-align:left; }
  .ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); } .dim { color:var(--dim); }
  #log { font-family: ui-monospace, Menlo, Consolas, monospace; font-size:11px; max-height:230px; overflow-y:auto; background:#0f1115; border:1px solid var(--line); border-radius:6px; padding:6px; }
  #log div { padding:1px 0; } .ALARM { color:var(--bad); } .WARN { color:var(--warn); } .INFO { color:var(--dim); }
  #legend { position:absolute; left:10px; bottom:10px; background:rgba(23,26,33,.9); border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:11px; color:var(--dim); line-height:1.5; }
  #legend b { color:var(--text); }
  #banner { position:absolute; left:10px; top:10px; background:rgba(23,26,33,.9); border:1px solid var(--line); border-radius:8px; padding:6px 10px; font-size:13px; }
  #finished { position:absolute; inset:0; display:none; align-items:center; justify-content:center; background:rgba(0,0,0,.6); font-size:28px; color:var(--bad); }
  pre { white-space:pre-wrap; font-size:11px; background:#0f1115; padding:6px; border-radius:6px; border:1px solid var(--line); }
</style></head>
<body>
<div id="map"><canvas id="c"></canvas>
  <div id="banner">connecting...</div>
  <div id="legend"><b>Map</b>: house colour = indoor temperature (blue cold, orange warm), red frame = no power, blue frame = on sector UPS, x = burst pipes.<br>
  Yellow lines = power (moving dashes = energised), blue = water, cyan = internet cable, cyan dots = packets, red dot = packet with no uplink.<br>
  Poles: dot; orange = tilted, red x = fallen; glow = street lamp on. Gates on the ring road: green open, grey closed, red lockdown.<br>
  Rovers: G garbage, S sludge hauler, E engineers, P plumber. Red diamonds = xenomorphs. ! = open issue.</div>
  <div id="finished"></div>
  <div id="tip" style="position:absolute;display:none;background:rgba(23,26,33,.95);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:11px;pointer-events:none"></div>
</div>
<div id="side">
  <h1>Hadley's Hope, LV-426</h1>
  <div class="row"><span id="time" style="font-weight:600;min-width:120px"></span>
    <button id="pause">Pause</button>
    <span class="dim">speed</span><button data-s="1">1x</button><button data-s="20">20x</button><button data-s="120">120x</button><button data-s="600">600x</button></div>
  <h2>Inject</h2>
  <div class="row">
    <button data-i="span">break span</button><button data-i="pole">fell pole</button><button data-i="xeno">xenomorphs</button>
    <button data-i="storm">storm</button><button data-i="trunk">cut trunk</button><button data-i="pump">pump trip</button>
    <button data-i="marines">marines fire</button><button data-i="scram">SCRAM</button><button data-i="road">break road</button><button data-i="money">+50k cr</button>
  </div>
  <h2>Colony</h2>
  <div class="kpi" id="kpi"></div>
  <h2>Reactor and power</h2>
  <div id="reactor" class="card"></div>
  <h2>Sectors</h2>
  <table id="sectors"><thead><tr><th>#</th><th>cr</th><th>kW</th><th>avg C</th><th>min C</th><th>pwr</th><th>water</th><th>net</th><th>UPS</th><th>waste</th><th>san</th><th>gate</th><th>road</th></tr></thead><tbody></tbody></table>
  <h2>Open issues <span id="nissues" class="dim"></span></h2>
  <div id="issues" class="dim" style="font-size:11px;max-height:120px;overflow-y:auto"></div>
  <h2>Events</h2>
  <div id="log"></div>
  <h2>Last monthly report</h2>
  <pre id="report">no month closed yet</pre>
</div>
<script>
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
let G = null, S = null, packetsSeen = new Map(), lastFetch = 0, animT = 0;
const post = (o) => fetch('/cmd', {method:'POST', body: JSON.stringify(o)});
document.getElementById('pause').onclick = () => post({cmd:'pause'});
document.querySelectorAll('button[data-s]').forEach(b => b.onclick = () => post({cmd:'speed', value:+b.dataset.s}));
document.querySelectorAll('button[data-i]').forEach(b => b.onclick = () => post({cmd:'inject', value:b.dataset.i}));

async function loadGeom(){ G = await (await fetch('/geometry')).json(); }
async function poll(){
  try { const s = await (await fetch('/state')).json(); S = s; lastFetch = performance.now(); renderSide(s); }
  catch(e) { document.getElementById('banner').textContent = 'no connection'; }
  setTimeout(poll, 250);
}

// ---------- coordinate transform ----------
let sc = 1, ox = 0, oy = 0;
function fit(){
  const W = cv.clientWidth, H = cv.clientHeight; cv.width = W * devicePixelRatio; cv.height = H * devicePixelRatio;
  const x0=-780, x1=440, y0=-440, y1=440;
  sc = Math.min(W/(x1-x0), H/(y1-y0)); ox = W/2 - sc*(x0+x1)/2; oy = H/2 - sc*(y0+y1)/2;
}
const X = x => ox + sc*x, Y = y => oy + sc*y;
function polar(a, r){ const t = a*Math.PI/180; return [r*Math.cos(t), r*Math.sin(t)]; }

// ---------- colours ----------
function tempColor(t){ // -60..25 -> blue..white..orange
  const u = Math.max(0, Math.min(1, (t + 40) / 65));
  if (u < 0.6) { const k = u/0.6; return `rgb(${Math.round(60+150*k)},${Math.round(110+120*k)},${Math.round(230-20*k)})`; }
  const k = (u-0.6)/0.4; return `rgb(${Math.round(210+45*k)},${Math.round(230-90*k)},${Math.round(210-150*k)})`;
}
const modeColor = {ONLINE:'#5ec07a', RUNBACK:'#e0b04a', SCRAM:'#e2574d', COOLING:'#e2574d', EMERGENCY:'#ff2a2a', CORE_DAMAGE:'#ff0000', STARTING:'#5aa9ff'};

// ---------- drawing helpers ----------
function line(x0,y0,x1,y1,color,w,dash,off){ ctx.beginPath(); ctx.strokeStyle=color; ctx.lineWidth=w; ctx.setLineDash(dash||[]); ctx.lineDashOffset=off||0; ctx.moveTo(X(x0),Y(y0)); ctx.lineTo(X(x1),Y(y1)); ctx.stroke(); ctx.setLineDash([]); }
function flow(x0,y0,x1,y1,color,w,on,speed){ line(x0,y0,x1,y1,on?color:'#3a3f4a',w); if(on) line(x0,y0,x1,y1,'#ffffff',Math.max(1,w-1),[3,9],-animT*speed); }
function dot(x,y,r,color){ ctx.beginPath(); ctx.fillStyle=color; ctx.arc(X(x),Y(y),r,0,Math.PI*2); ctx.fill(); }
function text(x,y,s,color,size,align){ ctx.fillStyle=color||'#d9dde6'; ctx.font=`${size||11}px sans-serif`; ctx.textAlign=align||'center'; ctx.fillText(s,X(x),Y(y)); }
function box(x,y,w,h,fill,stroke,label,sub){ ctx.fillStyle=fill; ctx.strokeStyle=stroke; ctx.lineWidth=1.2; ctx.beginPath(); if(ctx.roundRect) ctx.roundRect(X(x)-w/2,Y(y)-h/2,w,h,6); else ctx.rect(X(x)-w/2,Y(y)-h/2,w,h); ctx.fill(); ctx.stroke(); if(label) text(x,y-3,label,'#e8ecf3',11); if(sub) text(x,y+10,sub,'#9aa3b5',10); }

function draw(){
  fit(); ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  ctx.clearRect(0,0,cv.clientWidth,cv.clientHeight);
  animT = performance.now()/40;
  if(!G || !S) { requestAnimationFrame(draw); return; }
  const c = G.cfg, R = c.ring_road_radius, ns = c.sectors;
  const night = S.env.night;
  // sectors
  for(let s=0;s<ns;s++){
    const a0=(s*60)*Math.PI/180, a1=((s+1)*60)*Math.PI/180;
    ctx.beginPath(); ctx.arc(X(0),Y(0),sc*(R+40),a0,a1); ctx.arc(X(0),Y(0),sc*(c.hub_radius+10),a1,a0,true); ctx.closePath();
    const sec=S.sectors[s];
    ctx.fillStyle = sec.gate==='LOCKDOWN' ? 'rgba(226,87,77,.10)' : (!sec.online ? 'rgba(226,87,77,.05)' : (sec.dark ? 'rgba(0,0,0,.35)' : 'rgba(255,255,255,.025)'));
    ctx.fill(); ctx.strokeStyle='#262b36'; ctx.lineWidth=1; ctx.stroke();
    const [lx,ly]=polar(s*60+30, R+58); text(lx,ly,`S${s+1}`,'#6d7689',12);
  }
  // roads: ring segments and spokes
  for(let s=0;s<ns;s++){
    const integ=S.sectors[s].road; const col = integ<20?'#e2574d':(integ<50?'#8a6a2a':'#3d4350');
    ctx.beginPath(); ctx.strokeStyle=col; ctx.lineWidth=S.power.road_heating?5:4; ctx.arc(X(0),Y(0),sc*R,(s*60)*Math.PI/180,((s+1)*60)*Math.PI/180); ctx.stroke();
    const [sx,sy]=polar(s*60,c.hub_radius), [ex,ey]=polar(s*60,R); line(sx,sy,ex,ey,'#2e3440',2);
  }
  line(-R,0,c.reactor[0]+60,0,'#3d4350',4); // spoke to the reactor complex (under the trunk)
  // gates
  for(let s=0;s<ns;s++){ const [gx,gy]=polar(s*60,R); const st=S.sectors[s].gate; const col = st==='LOCKDOWN'?'#e2574d':(st==='OPEN'?'#5ec07a':'#8a93a6');
    ctx.save(); ctx.translate(X(gx),Y(gy)); ctx.rotate(s*60*Math.PI/180); ctx.fillStyle=col; ctx.fillRect(-3,-9,6,18); ctx.restore(); if(!S.sectors[s].gate_ok) text(gx,gy-12,'!','#e2574d',12); }
  // water pipes: plant -> hub, hub -> sector mains
  const waterOn = S.water.tank_m3>0 && S.water.pump;
  flow(c.reactor[0], 100, -c.hub_radius-4, 8, '#5aa9ff', 2, S.water.plant, 1.2);
  for(let s=0;s<ns;s++){ const [x0,y0]=polar(s*60+36,c.hub_radius), [x1,y1]=polar(s*60+36,R-30); flow(x0,y0,x1,y1,'#5aa9ff',1.5, waterOn && S.sectors[s].water_ok>0, 1.0); }
  // power: trunk, feeders, spans
  const reactorUp = S.reactor.available_mw>0;
  flow(c.reactor[0]+40, -4, -c.hub_radius, -4, '#f2c14e', 3, S.power.trunk && reactorUp, 2.5);
  flow(c.reactor[0]+40, -60, c.tower[0]+20, c.tower[1]+30, '#f2c14e', 1.2, S.power.tower_line && S.power.trunk && reactorUp, 2);
  for(let s=0;s<ns;s++){ const [x1,y1]=polar(s*60+30,c.hub_radius+18); const [x0,y0]=polar(s*60+30,c.hub_radius-30); flow(x0,y0,x1,y1,'#f2c14e',2,S.power.feeder[s]&&S.sectors[s].online,2); }
  const PPS=c.poles_per_sector;
  for(let i=0;i<G.poles.x.length;i++){
    const k=G.poles.k[i], s=G.poles.sector[i];
    let px0,py0; if(k===0){ [px0,py0]=polar(s*60+30,c.hub_radius+18); } else { px0=G.poles.x[i-1]; py0=G.poles.y[i-1]; }
    const px1=G.poles.x[i], py1=G.poles.y[i];
    flow(px0,py0,px1,py1,'#f2c14e',1.6,S.poles.span[i]===1,2);
    // internet cable, offset perpendicular
    const dx=px1-px0, dy=py1-py0, L=Math.hypot(dx,dy)||1, nx=-dy/L*6, ny=dx/L*6;
    line(px0+nx,py0+ny,px1+nx,py1+ny,S.poles.net[i]===1?'#4fd1c5':'#4a3030',1);
  }
  // house drops to poles (faint)
  for(let i=0;i<G.houses.x.length;i++){ const p=G.houses.pole[i]; line(G.houses.x[i],G.houses.y[i],G.poles.x[p],G.poles.y[p],'rgba(242,193,78,.12)',1); }
  // hub
  dot(0,0,sc*c.hub_radius,'#1c2028'); ctx.beginPath(); ctx.strokeStyle=S.power.substation?'#f2c14e':'#e2574d'; ctx.lineWidth=2; ctx.arc(X(0),Y(0),sc*c.hub_radius,0,Math.PI*2); ctx.stroke();
  text(0,-30,'substation',S.power.substation?'#f2c14e':'#e2574d',11); text(0,-16,`UPS center ${S.power.ups_center_kwh} kWh`,'#9aa3b5',10);
  text(0,0,S.net.comms?'comms node':'comms DOWN',S.net.comms&&S.net.uplink?'#4fd1c5':'#e2574d',11); text(0,16,'ops center, water pump','#9aa3b5',10);
  text(0,32,`tank ${S.water.tank_m3} m3`,waterOn?'#5aa9ff':'#e2574d',10);
  // reactor complex
  const rc=modeColor[S.reactor.mode]||'#888';
  box(c.reactor[0],-110,110,34,'#20242e','#7a6a2a','solar',`${S.power.solar_kw} kW`);
  box(c.reactor[0],0,120,54,'#20242e',rc,`REACTOR ${S.reactor.mode}`,`${S.reactor.power_mw} MW  core ${S.reactor.core_temp} C`);
  if(S.reactor.marines) text(c.reactor[0],-38,'MARINES IN THE SUBLEVELS','#e2574d',10);
  box(c.reactor[0],100,110,34,'#20242e',S.water.plant?'#5aa9ff':'#e2574d','water plant',S.water.plant?'melting ice':'no heat');
  box(c.reactor[0],200,110,34,'#20242e','#6a7a2a','waste storage',`+${S.finance.waste_station}`);
  box(c.reactor[0],300,110,34,'#20242e',S.power.mine?'#a08a2a':'#5a5a5a','mine',S.power.mine?`${S.power.infra.mine} kW`:'stopped');
  // tower
  const [tx,ty]=[c.tower[0],c.tower[1]];
  ctx.beginPath(); ctx.strokeStyle=S.net.uplink?'#4fd1c5':'#e2574d'; ctx.lineWidth=2; ctx.moveTo(X(tx)-10,Y(ty)+18); ctx.lineTo(X(tx),Y(ty)-18); ctx.lineTo(X(tx)+10,Y(ty)+18); ctx.stroke();
  text(tx,ty+32,S.net.uplink?'uplink OK':'uplink LOST',S.net.uplink?'#4fd1c5':'#e2574d',10);
  line(-c.hub_radius+8,-8,tx+6,ty+14,S.net.uplink?'#4fd1c5':'#4a3030',1.2);
  if(S.net.uplink){ for(let k=0;k<3;k++){ ctx.beginPath(); ctx.strokeStyle=`rgba(79,209,197,${0.5-0.15*k})`; ctx.arc(X(tx),Y(ty)-14,8+6*k+((animT*2)%6),-2.2,-0.9); ctx.stroke(); } }
  // poles and lamps
  for(let i=0;i<G.poles.x.length;i++){ const x=G.poles.x[i],y=G.poles.y[i],st=S.poles.state[i];
    if(S.poles.lamp[i]===1){ const g=ctx.createRadialGradient(X(x),Y(y),0,X(x),Y(y),sc*28); g.addColorStop(0,'rgba(255,230,140,.35)'); g.addColorStop(1,'rgba(255,230,140,0)'); ctx.fillStyle=g; ctx.beginPath(); ctx.arc(X(x),Y(y),sc*28,0,Math.PI*2); ctx.fill(); }
    if(st===2){ text(x,y+4,'x','#e2574d',13); } else dot(x,y,3,st===1?'#e0b04a':'#c9cfdb'); }
  // houses
  const hs=S.houses; const sz=Math.max(4,sc*9);
  for(let i=0;i<G.houses.x.length;i++){ const x=X(G.houses.x[i]),y=Y(G.houses.y[i]);
    ctx.fillStyle=tempColor(hs.t[i]); ctx.fillRect(x-sz/2,y-sz/2,sz,sz);
    if(!hs.power[i]){ ctx.strokeStyle='#e2574d'; ctx.lineWidth=1.5; ctx.strokeRect(x-sz/2,y-sz/2,sz,sz); }
    else if(hs.ups[i]){ ctx.strokeStyle='#5aa9ff'; ctx.lineWidth=1.5; ctx.strokeRect(x-sz/2,y-sz/2,sz,sz); }
    else if(hs.limit[i]>0){ ctx.strokeStyle='#e0b04a'; ctx.lineWidth=1; ctx.strokeRect(x-sz/2,y-sz/2,sz,sz); }
    if(hs.heater[i]&&hs.power[i]){ ctx.fillStyle='#ff7a30'; ctx.fillRect(x-1.5,y-1.5,3,3); }
    if(hs.burst[i]){ ctx.strokeStyle='#5aa9ff'; ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(x-sz/2,y-sz/2); ctx.lineTo(x+sz/2,y+sz/2); ctx.moveTo(x+sz/2,y-sz/2); ctx.lineTo(x-sz/2,y+sz/2); ctx.stroke(); }
  }
  // internet packets
  const now=performance.now();
  for(const p of S.net.packets){ const key=p.t+':'+p.from+':'+p.id; if(!packetsSeen.has(key)) packetsSeen.set(key, now); }
  for(const [key,t0] of packetsSeen){ if(now-t0>1800){ packetsSeen.delete(key); continue; }
    const [t,from,id]=key.split(':'); const pk=S.net.packets.find(q=>q.t+':'+q.from+':'+q.id===key); if(!pk) continue;
    let path=[];
    if(from==='house'){ const i=+id, p=G.houses.pole[i], s=G.houses.sector[i]; path.push([G.houses.x[i],G.houses.y[i]]);
      for(let k=G.poles.k[p];k>=0;k--){ const j=s*PPS+k; path.push([G.poles.x[j],G.poles.y[j]]); } const [hx,hy]=polar(s*60+30,c.hub_radius+18); path.push([hx,hy]); path.push([0,0]); }
    else { path.push([0,0]); }
    if(pk.uplink) path.push([tx+6,ty+14]);
    const u=(now-t0)/1800; let seg=Math.floor(u*(path.length-1)), f=u*(path.length-1)-seg; if(seg>=path.length-1){seg=path.length-2;f=1;}
    const [ax,ay]=path[seg],[bx,by]=path[seg+1]; dot(ax+(bx-ax)*f,ay+(by-ay)*f,2.5,pk.uplink?(pk.kind==='reactor'?'#f2c14e':'#4fd1c5'):'#e2574d'); }
  // waste bins and sludge stores at the ring
  for(let s=0;s<ns;s++){ const [bx,by]=polar(s*60+30,R+22); const w=S.sectors[s].waste; ctx.fillStyle=w>=1?'#e2574d':(w>=0.9?'#e0b04a':'#3d4350'); ctx.fillRect(X(bx)-5,Y(by)-5,10,10); ctx.fillStyle='#8a93a6'; ctx.fillRect(X(bx)-4,Y(by)+4-8*Math.min(1,w),8,8*Math.min(1,w)); }
  // rovers
  const rc2={garbage:['G','#9bd36a'],sludge:['S','#b48ead'],repair:['E','#f2c14e'],plumber:['P','#5aa9ff']};
  for(const r of S.rovers){ const [l,col]=rc2[r.name==='engineer-2'?'repair':(r.name==='engineer'?'repair':r.name)]||['?','#fff']; dot(r.x,r.y,7,col); text(r.x,r.y+4,l,'#111',10); text(r.x,r.y+16,r.state.toLowerCase().replace('_',' '),'#9aa3b5',9); }
  // xenomorphs
  for(const x of S.xenos){ ctx.save(); ctx.translate(X(x.x),Y(x.y)); ctx.rotate(Math.PI/4); ctx.fillStyle='#e2574d'; ctx.fillRect(-5,-5,10,10); ctx.restore(); }
  // issues
  for(const i of S.issues){ const col=i.sev==='critical'?'#e2574d':(i.sev==='warning'?'#e0b04a':'#8a93a6'); dot(i.x+8,i.y-8,6,col); text(i.x+8,i.y-4,'!','#111',10); }
  // banner
  const e=S.env; document.getElementById('banner').innerHTML = `<b>${S.time}</b> &nbsp; ${e.t_out} C, wind ${e.wind} m/s${e.storm?' <span class="bad">STORM</span>':''}${e.precip==='snow'?' snow':''}${e.night?' night':' day'}${S.paused?' <span class="warn">PAUSED</span>':''} &nbsp; ${S.speed} min/s`;
  const fin=document.getElementById('finished'); if(S.finished){ fin.style.display='flex'; fin.textContent='SIMULATION OVER: '+S.finish_reason; }
  requestAnimationFrame(draw);
}

function cls(ok, warn){ return ok?'ok':(warn?'warn':'bad'); }
function renderSide(s){
  document.getElementById('time').textContent = s.time;
  document.getElementById('pause').textContent = s.paused?'Resume':'Pause';
  document.querySelectorAll('button[data-s]').forEach(b=>b.classList.toggle('on', +b.dataset.s===s.speed));
  const p=s.power, r=s.reactor, w=s.water, f=s.finance;
  const kp=[
    ['Colony budget', f.colony.toLocaleString()+' cr', f.colony>20000?'ok':(f.colony>0?'warn':'bad')],
    ['Sector budgets', f.sectors.map(x=>Math.round(x/1000)+'k').join(' '), Math.min(...f.sectors)>2000?'ok':'warn'],
    ['Power available', p.available_kw+' kW', p.available_kw>p.demand_kw?'ok':'bad'],
    ['Power demand', p.demand_kw+' kW'+(p.shedding?` / shedding L${p.shedding}`:''), p.shedding?'warn':'ok'],
    ['Water tank', w.tank_m3+' m3, '+w.houses_ok+'/300 houses', w.tank_m3>100&&w.houses_ok>280?'ok':'warn'],
    ['Pipes', `${w.frozen} frozen, ${w.burst} burst`, w.burst===0?'ok':'bad'],
    ['Internet', `${s.net.houses_online}/300 online, uplink ${s.net.uplink?'OK':'LOST'}`, s.net.uplink&&s.net.houses_online>280?'ok':'warn'],
    ['Open issues', s.issues_total+(f.unpaid?` (unpaid ${f.unpaid} cr)`:''), s.issues_total<5?'ok':'warn'],
    ['Month income (colony)', f.month_income.toLocaleString()+' cr', 'dim'],
    ['Month expense (colony)', f.month_expense.toLocaleString()+' cr', 'dim'],
  ];
  document.getElementById('kpi').innerHTML = kp.map(([l,v,c])=>`<div class="card"><div class="v ${c}">${v}</div><div class="l">${l}</div></div>`).join('');
  const inf=p.infra;
  document.getElementById('reactor').innerHTML = `<div><b class="${r.mode==='ONLINE'?'ok':(r.mode==='RUNBACK'||r.mode==='STARTING'?'warn':'bad')}">${r.mode}</b> &nbsp; ${r.power_mw} MW gross, ${r.available_mw} MW to grid, core ${r.core_temp} C${r.decay_mw?`, decay ${r.decay_mw} MW`:''}</div>
    <div class="dim">pumps A ${r.pump_a} B ${r.pump_b}, heat exchanger ${r.hx}, batteries ${r.battery_h} h, link ${r.link?'ok':'<span class="bad">lost</span>'}${r.faults.length?', faults: '+r.faults.join(', '):''}</div>
    <div class="dim">solar ${p.solar_kw} kW; loads: mine ${inf.mine}, houses ${Math.round(p.demand_kw-Object.values(inf).reduce((a,b)=>a+b,0))}, water plant ${inf.water_plant}, road heating ${inf.road_heating}, lamps ${inf.lamps}, comms ${inf.comms}, ups charge ${inf.ups_charge} kW</div>
    <div class="dim">trunk ${p.trunk?'ok':'<span class="bad">CUT</span>'}, substation ${p.substation?'ok':'<span class="bad">DOWN</span>'}, UPS center ${p.ups_center} ${p.ups_center_kwh} kWh</div>`;
  document.querySelector('#sectors tbody').innerHTML = s.sectors.map(x=>`<tr><td>${x.id}${x.dark?' <span class="warn">dark</span>':''}</td><td>${x.budget}</td><td>${x.demand_kw}</td><td class="${x.avg_t>15?'ok':(x.avg_t>4?'warn':'bad')}">${x.avg_t}</td><td class="${x.min_t>4?'ok':'bad'}">${x.min_t}</td><td class="${cls(x.power_ok===50,x.power_ok>30)}">${x.power_ok}</td><td class="${cls(x.water_ok===50,x.water_ok>30)}">${x.water_ok}</td><td class="${cls(x.net_ok===50,x.net_ok>30)}">${x.net_ok}</td><td class="${x.ups==='DISCHARGING'?'warn':(x.ups==='DEPLETED'?'bad':'dim')}">${x.ups.slice(0,4)} ${x.ups_kwh}</td><td class="${x.waste>=1?'bad':(x.waste>=0.9?'warn':'dim')}">${Math.round(x.waste*100)}%</td><td class="${x.sanitary>70?'ok':'bad'}">${x.sanitary}</td><td class="${x.gate==='OPEN'?'ok':(x.gate==='LOCKDOWN'?'bad':'warn')}">${x.gate.slice(0,4)}</td><td class="${x.road>20?'dim':'bad'}">${x.road}%</td></tr>`).join('');
  document.getElementById('nissues').textContent = `(${s.issues_total})`;
  document.getElementById('issues').innerHTML = s.issues.slice().reverse().map(i=>`<div><span class="${i.sev==='critical'?'bad':(i.sev==='warning'?'warn':'dim')}">${i.kind}</span> ${i.target} ${i.sector>0?'S'+i.sector:''} ${i.cause}, ${i.cost} cr (${i.payer}) <span class="dim">${i.status}, ${Math.round(i.age/60)} h</span></div>`).join('') || '<div>none</div>';
  document.getElementById('log').innerHTML = s.events.map(e=>`<div class="${e.level}">${String(e.t).padStart(6)} ${e.text}</div>`).join('');
  const rp=s.report; if(rp){ document.getElementById('report').textContent =
    `Month ${rp.month}: owners paid ${Math.round(rp.houses_total)} cr (energy ${Math.round(rp.energy_total)}, water ${Math.round(rp.water_total)}, repairs ${Math.round(rp.repairs_total)}), ${Math.round(rp.kwh_total)} kWh\n`+
    `colony: income ${rp.colony_income}, expense ${rp.colony_expense}, budget ${rp.colony_budget}, unpaid ${rp.unpaid}\n`+
    `sector income ${rp.sector_income.join(' | ')}\nsector expense ${rp.sector_expense.join(' | ')}\n`+
    `expense by cause: ${Object.entries(rp.by_cause).map(([k,v])=>k+' '+v).join(', ')}\n`+
    `top houses: ${rp.top_houses.map(h=>`#${h.house} (S${h.sector}) ${h.total}`).join(', ')}`; }
}
cv.addEventListener('mousemove', ev => {
  const tip=document.getElementById('tip'); if(!G||!S){ tip.style.display='none'; return; }
  const r=cv.getBoundingClientRect(), mx=ev.clientX-r.left, my=ev.clientY-r.top; let best=-1, bd=10;
  for(let i=0;i<G.houses.x.length;i++){ const d=Math.hypot(X(G.houses.x[i])-mx, Y(G.houses.y[i])-my); if(d<bd){bd=d;best=i;} }
  if(best<0){ tip.style.display='none'; return; }
  const h=S.houses, i=best;
  tip.innerHTML=`<b>House ${i+1}</b> (S${G.houses.sector[i]+1}, ${G.types[G.houses.type[i]]})<br>indoor ${h.t[i]} C, heater ${h.heater[i]?'on':'off'}<br>power ${h.power[i]?(h.ups[i]?'UPS':'grid'):'<span class="bad">none</span>'}${h.limit[i]?', limit '+h.limit[i]+' W':''}<br>water ${h.water[i]?'ok':'<span class="bad">no</span>'}${h.burst[i]?', <span class="bad">pipes burst</span>':''}<br>internet ${h.net[i]?'online':'offline'}, sludge ${Math.round(h.sludge[i]*100)}%`;
  tip.style.display='block'; tip.style.left=(mx+14)+'px'; tip.style.top=(my+14)+'px';
});
loadGeom().then(()=>{ poll(); draw(); });
window.addEventListener('resize', fit);
</script></body></html>
"""
# ------------------------------------------------------------------------------------
# Simulation thread and HTTP server
# ------------------------------------------------------------------------------------

def sim_loop(w: World):
    last = time.time()
    acc = 0.0
    while True:
        now = time.time()
        acc += (now - last) * w.speed
        last = now
        n = int(acc)
        acc -= n
        if w.paused or w.finished:
            time.sleep(0.05)
            acc = 0.0
            continue
        with w.lock:
            for _ in range(min(n, 200)):
                world_tick(w)
        time.sleep(0.01)


def make_handler(w: World, html: str, geom_json: str):
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, ctype, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/index"):
                self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
            elif self.path.startswith("/geometry"):
                self._send(200, "application/json", geom_json.encode("utf-8"))
            elif self.path.startswith("/state"):
                with w.lock:
                    body = json.dumps(snapshot(w)).encode("utf-8")
                self._send(200, "application/json", body)
            else:
                self._send(404, "text/plain", b"not found")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n) if n else b"{}"
            try:
                req = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                req = {}
            cmd = req.get("cmd", "")
            with w.lock:
                if cmd == "pause":
                    w.paused = not w.paused
                elif cmd == "speed":
                    w.speed = int(clamp(int(req.get("value", 20)), 0, 600))
                elif cmd == "inject":
                    inject(w, req.get("value", ""))
                elif cmd == "reactor":
                    v = req.get("value", "")
                    if v == "scram":
                        reactor_scram(w, "operator")
                    elif v == "setpoint":
                        w.r_setpoint_mw = float(clamp(float(req.get("mw", 5.0)), 1.2, 6.0))
            self._send(200, "application/json", b'{"ok": true}')

    return Handler


def main():
    import argparse
    from http.server import ThreadingHTTPServer

    ap = argparse.ArgumentParser(description="Hadley's Hope colony simulation")
    ap.add_argument("--port", type=int, default=CFG["http_port"])
    ap.add_argument("--speed", type=int, default=CFG["default_speed"], help="simulated minutes per real second")
    ap.add_argument("--seed", type=int, default=CFG["seed"])
    ap.add_argument("--headless", type=int, default=0, help="run N ticks without the server, print a summary and exit")
    args = ap.parse_args()
    CFG["seed"] = args.seed
    w = World(CFG)
    w.speed = args.speed
    if args.headless:
        t0 = time.time()
        for _ in range(args.headless):
            world_tick(w)
        dt = time.time() - t0
        snap = snapshot(w)
        print(f"{args.headless} ticks in {dt:.2f} s ({args.headless / max(dt, 1e-9):.0f} ticks/s)")
        print(json.dumps({k: snap[k] for k in ("time", "env", "power", "reactor", "water", "finance")}, indent=1, ensure_ascii=False))
        print("open issues:", snap["issues_total"])
        for e in list(w.events)[:15]:
            print(f"  t={e['t']:6d} {e['level']:5s} {e['text']}")
        return
    threading.Thread(target=sim_loop, args=(w,), daemon=True).start()
    handler = make_handler(w, HTML, json.dumps(house_geometry(w)))
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    print(f"Hadley's Hope simulation: open http://localhost:{args.port}  (speed {w.speed} min/s, seed {args.seed})")
    print("Ctrl+C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped at", w.time_str())


if __name__ == "__main__":
    main()
