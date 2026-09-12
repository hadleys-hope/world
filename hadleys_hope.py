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
    lamps_on = w.p_lamp_ok & (w.s_online) & (w.shedding < 4)
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
    ua_eff = w.h_ua * (1.0 + 0.015 * w.wind)
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
    z = 0.35 * (v - 22.0) + 3.0 * w.s_ice + 0.03 * (-w.t_out - 40) - 6.5
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


