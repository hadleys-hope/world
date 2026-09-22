"""world: colony simulation components."""

from __future__ import annotations
from hadleys.enums import TransportKind
from typing import Optional

from collections import deque
import math
import numpy as np
import random
import threading
from hadleys.config import CFG, COSTS
from hadleys.domains.hydraulics import UtilityNetwork
from hadleys.domains.transport import make_traffic
from hadleys.models import Issue, Rover
from hadleys.numerics import polar


class World:
    SCHEMA = 4  # bump when array layouts change; new plain attributes are filled in by Store.migrate on load

    def __init__(self, cfg=CFG):
        self.schema = self.SCHEMA
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
        self.packets = []
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
        self.h_angle = self.h_sector * 60.0 + 7.5 + self.h_slot * 5.2
        self.h_radius = cfg["house_radius_min"] + self.h_ring * cfg["house_ring_step"]
        self.h_x = self.h_radius * np.cos(np.radians(self.h_angle))
        self.h_y = self.h_radius * np.sin(np.radians(self.h_angle))
        types = np.concatenate(
            [np.full(c, i) for i, c in enumerate(cfg["type_counts"])]
        )
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
        self.h_limit_w = np.zeros(N)
        self.h_power_ok = np.ones(N, dtype=bool)
        self.h_on_ups = np.zeros(N, dtype=bool)
        self.h_meter_kwh = np.zeros(N)
        self.h_meter_month = np.zeros(N)
        self.h_meter_day = np.zeros(N)
        self.h_water_day = np.zeros(N)
        self.h_water_month = np.zeros(N)
        self.h_water_m3 = np.zeros(N)
        self.h_pipes_ok = np.ones(N, dtype=bool)
        self.h_frozen = np.zeros(N, dtype=int)
        self.h_burst = np.zeros(N, dtype=bool)
        self.h_water_ok = np.ones(N, dtype=bool)
        self.h_wiring_ok = np.ones(N, dtype=bool)
        self.h_terminal_ok = np.ones(N, dtype=bool)
        self.h_aeration_ok = np.ones(N, dtype=bool)
        self.h_sludge = self.rng.uniform(0.0, 0.6, N)
        self.h_net_online = np.ones(N, dtype=bool)
        self.h_valve_open = np.ones(N, dtype=bool)
        self.h_appliances_on = np.ones(N, dtype=bool)
        self.h_repairs_month = np.zeros(N)
        # external house controllers (runtime over MQTT); fallback thermostat when stale
        self.h_ctrl_t = np.full(N, -10_000)
        self.h_ctrl_heater = np.zeros(N, dtype=bool)
        self.h_ctrl_target = np.full(N, cfg["comfort_c"])
        self.h_ctrl_valve = np.ones(N, dtype=bool)
        self.h_ctrl_appl = np.ones(N, dtype=bool)
        self.h_program = [""] * N
        self.h_reason = [""] * N
        self.prog_stats = (
            {}
        )  # program name -> {"kwh", "house_ticks", "cold_ticks", "t_sum"} accumulated this month
        self.h_log = [
            deque(maxlen=40) for _ in range(N)
        ]  # per-house event log: transitions and decisions
        self.h_hist = np.full(
            (N, 144), 20.0
        )  # indoor temperature every 10 minutes, last 24 h
        self.h_hist_draw = np.zeros((N, 144))
        self.h_hist_i = 0
        self.h_prev = None

        # ---- poles: a tree per sector. Spine along the boundary street (angle s*60),
        #      branches along each row street; every pole carries a lamp, a power span
        #      and an internet cable back to its parent ----
        spine_r = cfg["spine_radii"]
        arc_a = cfg["arc_pole_angles"]
        px, py, ps, pk, parent, kind, prad, pang = [], [], [], [], [], [], [], []
        self.spine_index = {}  # (sector, radius) -> pole index
        for s in range(S):
            first = len(px)
            for j, r in enumerate(spine_r):
                # Reserve a verge at both the radial street and the intersecting ring.
                verge_r = (
                    r + 24
                    if r == cfg["ring_road_radius"]
                    else r + 14 if r >= cfg["house_radius_min"] - 30 else r - 6
                )
                theta = math.radians(s * 60)
                x = verge_r * math.cos(theta) - 12 * math.sin(theta)
                y = verge_r * math.sin(theta) + 12 * math.cos(theta)
                base_angle = math.degrees(math.atan2(y, x)) % 360
                px.append(x)
                py.append(y)
                ps.append(s)
                pk.append(j)
                parent.append(first + j - 1 if j > 0 else -1)
                kind.append(0)
                prad.append(r)
                pang.append(base_angle)
                self.spine_index[(s, r)] = first + j
            for k in range(cfg["house_rows"] + 1):
                r = (
                    cfg["house_radius_min"] - 30 + k * cfg["house_ring_step"]
                )  # row street below row k
                prev = self.spine_index[(s, r)]
                for m, a in enumerate(arc_a):
                    ang = s * 60.0 + a
                    x, y = polar(ang, r - 6)
                    px.append(x)
                    py.append(y)
                    ps.append(s)
                    pk.append(k)
                    parent.append(prev)
                    kind.append(1)
                    prad.append(r)
                    pang.append(ang)
                    prev = len(px) - 1
        self.layout_version = 4
        self.P = P = len(px)
        self.p_x = np.array(px)
        self.p_y = np.array(py)
        self.p_sector = np.array(ps)
        self.p_k = np.array(pk)
        self.p_parent = np.array(parent)
        self.p_kind = np.array(kind)
        self.p_radius = np.array(prad)
        self.p_angle = np.array(pang)
        self.p_state = np.zeros(P, dtype=int)  # 0 standing, 1 tilted, 2 fallen
        self.p_lamp_ok = np.ones(P, dtype=bool)
        self.p_lamp_on = np.ones(P, dtype=bool)
        self.s_health = np.ones(P)  # span from parent to pole i
        self.s_ice = np.zeros(P)
        self.s_online = np.ones(P, dtype=bool)
        self.n_span_ok = np.ones(P, dtype=bool)
        self.net_chain = np.ones(P, dtype=bool)
        # house -> nearest arc pole of its row street
        hp = np.zeros(N, dtype=int)
        for i in range(N):
            s, k = int(self.h_sector[i]), int(self.h_ring[i])
            cands = np.flatnonzero(
                (self.p_sector == s) & (self.p_kind == 1) & (self.p_k == k)
            )
            hp[i] = int(cands[np.argmin(np.abs(self.p_angle[cands] - self.h_angle[i]))])
        self.h_pole = hp

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
        self.r_power_mw = 4.5
        self.r_setpoint_mw = 4.5
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
        self.r_flow = 1.0
        self.r_coolant_temp = 300.0

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
        self.water_plant_m3_h = 0.0
        self.intake_ok = True
        self.raw_intake_m3_h = self.brine_m3_h = 0.0
        self.water_heat_available_kw = self.water_heat_used_kw = 0.0
        self.ocean_withdrawn_m3 = self.brine_returned_m3 = 0.0
        self.pump_station_ok = True
        self.water_main_ok = np.ones(S, dtype=bool)
        self.sector_water_m3 = np.zeros(S)
        self.water_flow_m3_h = 0.0
        self.utilities = UtilityNetwork(self)

        # ---- internet ----
        self.comms_ok = True
        self.tower_ok = True
        self.cabinet_ok = np.ones(S, dtype=bool)
        self.cabinet_ups_h = np.full(S, 2.0)
        self.cabinet_online = np.ones(S, dtype=bool)
        self.net_sector_online = np.ones(S, dtype=bool)
        self.uplink_ok = True
        self.packets_per_min = 0

        # ---- roads, walls, gates, waste, sewage ----
        self.road_integrity = np.full(S, 100.0)  # ring road segment per sector
        self.road_icy = False
        self.gate_state = ["OPEN"] * S  # gate g sits in the wall at boundary angle g*60
        self.gate_ok = np.ones(S, dtype=bool)
        self.gate_open_frac = np.ones(S)  # 1 open, 0 closed, animated
        self.lockdown_ticks = np.zeros(S, dtype=int)
        self.waste_level = self.rng.uniform(0.2, 0.6, S)
        self.sludge_store = self.rng.uniform(0.1, 0.4, S)
        self.sanitary = np.full(S, 100.0)
        self.sector_dark = np.zeros(S, dtype=bool)
        R = cfg["ring_road_radius"]
        self.rovers = [
            Rover(
                TransportKind.GARBAGE,
                TransportKind.GARBAGE,
                *polar(15.0, R),
                speed=cfg["rover_speed"],
            ),
            Rover(
                TransportKind.SLUDGE,
                TransportKind.SLUDGE,
                *polar(195.0, R),
                speed=cfg["rover_speed"],
            ),
            Rover(
                "engineer",
                TransportKind.REPAIR,
                *polar(105.0, R),
                speed=cfg["rover_speed"] * 1.3,
            ),
            Rover(
                "engineer-2",
                TransportKind.REPAIR,
                *polar(345.0, R),
                speed=cfg["rover_speed"] * 1.3,
            ),
            Rover(
                TransportKind.PLUMBER,
                TransportKind.PLUMBER,
                *polar(285.0, R),
                speed=cfg["rover_speed"] * 1.3,
            ),
        ]
        self.traffic = make_traffic(self.cfg)
        self.cargo = {
            "phase": "WAIT",
            "progress": 0.0,
            "loaded": 0,
            "completed": 0,
            "truck": 0,
        }
        self.dish_ok = True
        self.mobile_online = True
        self.waste_station_level = 0.0

        # ---- people / threats ----
        self.xeno_markers: list[dict] = (
            []
        )  # agents: approach -> breach -> hunt -> attack -> retreat
        self.marines_active = 0
        self.nest_alert = 0
        self.wall_breach = [
            None
        ] * S  # angle of the broken wall panel per sector, or None
        self.squad = {
            "state": "BASE",
            "x": 0.0,
            "y": 60.0,
            "route": [],
            "sector": -1,
            "timer": 0,
        }
        W = cfg["walkers"]
        self.w_home = self.rng.integers(0, N, W)
        self.w_state = np.zeros(W, dtype=int)  # 0 home, 1 to hub, 2 at hub, 3 to home
        self.w_prog = np.zeros(W)
        self.w_timer = self.rng.integers(30, 600, W)
        self.w_x = self.h_x[self.w_home].copy()
        self.w_y = self.h_y[self.w_home].copy()

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

        # ---- attractor page: colony trajectory samples ----
        self.attr_fast = []  # every 10 ticks, last 5 days
        self.attr_slow = []  # every 6 hours, last 60 days
        self.last_levy = 0.0
        self.levy_total = 0.0
        self.last_sector_transfer = 0.0

    # ---- pickling: drop the lock, recreate it on load ----
    def __getstate__(self):
        d = self.__dict__.copy()
        d.pop("lock", None)
        d.pop("bridge", None)
        return d

    def __setstate__(self, d):
        self.__dict__.update(d)
        self.lock = threading.Lock()

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

    def open_issue(
        self, kind, target, sector, cause, cost_key, pos, severity="warning"
    ):
        for i in self.issues:
            if i.target == target and i.kind == kind and i.status != "resolved":
                return i
        cost, payer, dur = COSTS[cost_key]
        iss = Issue(
            self.next_issue_id,
            kind,
            target,
            sector,
            cause,
            float(cost),
            payer,
            dur,
            pos,
            self.t,
            severity=severity,
        )
        self.next_issue_id += 1
        self.issues.append(iss)
        self.log(
            "ALARM" if severity == "critical" else "WARN",
            f"{kind} at {target} ({cause})",
        )
        return iss

    def open_issues(self):
        return [i for i in self.issues if i.status != "resolved"]
