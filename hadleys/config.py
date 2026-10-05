"""config: colony simulation components."""

from __future__ import annotations


CFG = {
    "seed": 12345,
    "sectors": 6,
    "houses_per_sector": 50,
    "tick_seconds": 60,
    "ticks_per_day": 1440,
    "days_per_month": 30,
    # geometry (map units, roughly metres). The city is a ring of six sectors inside a wall.
    "hub_radius": 140,
    "house_radius_min": 300,  # first row of houses
    "house_ring_step": 60,  # distance between rows; streets run between rows
    "house_rows": 5,
    "ring_road_radius": 640,
    "wall_radius": 690,
    "spine_radii": [
        200,
        270,
        330,
        390,
        450,
        510,
        570,
        640,
    ],  # poles along each boundary street
    "arc_pole_angles": [
        10.0,
        20.5,
        31.0,
        41.5,
        52.0,
    ],  # poles along each row street, degrees inside the sector
    "reactor_pos": (-1280, 0),
    "solar_pos": (-1480, -300),
    "water_plant_pos": (-1280, 220),
    "radwaste_pos": (-1280, 420),
    "mine_pos": (-1280, 620),
    "waste_station_pos": (-1000, 140),
    "tower_junction": (-1000, 0),
    "tower_pos": (-1000, -540),
    "dish_pos": (-1680, -930),
    "ocean_intake_pos": (-1710, 220),
    "ocean_level_m": -8.0,
    "ocean_center": (-2450, 600),
    "ocean_radii": (1080, 1380),
    "planet_radius": 4000.0,
    "water_heat_kw": 1900.0,
    "water_recovery": 0.85,
    "traffic_vehicles": 18,
    "cargo_depot": (136.0, 210.0),
    "landing_pad_pos": (960, 0),
    "garage": (82.0, 244.0),  # polar: angle, radius; vehicle bay in sector 1
    "medlab": (195.0, 244.0),
    "school": (315.0, 244.0),
    "walkers": 60,
    # environment (LV-426: minus 40..60, permanent dusk, storms)
    "t_mean": -45.0,
    "t_daily_amp": 8.0,
    "storm_prob_per_tick": 0.0004,
    "storm_len_ticks": (180, 600),
    "storm_wind": (22.0, 34.0),
    "calm_wind": (4.0, 14.0),
    "daylight_max": 0.3,
    # houses
    "heater_kw": [
        3.5,
        3.0,
        3.0,
        4.5,
    ],  # by type: barracks, standard, insulated, manager
    "ua_w_per_k": [38.0, 32.0, 22.0, 45.0],
    "heat_cap_j_per_k": [0.8e7, 1.0e7, 1.3e7, 1.8e7],
    "base_load_w": [200, 300, 300, 600],
    "type_counts": [120, 120, 45, 15],
    "comfort_c": 21.0,
    "eco_c": 16.0,
    "antifreeze_c": 5.0,
    "freeze_ticks_to_frozen": 60,
    "frozen_ticks_to_burst": 30,
    "water_per_house_m3_day": 0.2,
    # reactor
    "reactor_gross_mw": 6.0,
    "reactor_self_mw": 0.6,
    "heat_export_mw": 3.0,
    "ramp_frac_per_min": 0.05,
    "core_temp_nominal": 780.0,
    "core_temp_limit": 1200.0,
    "pump_battery_h": 8.0,
    "reserve_mw": 0.5,
    # grid
    "solar_peak_kw": 200.0,
    "mine_kw": 2000.0,
    "water_plant_kw": 300.0,
    "waste_storage_kw": 20.0,
    "ops_center_kw": 40.0,
    "comms_kw": 20.0,
    "cabinet_kw": 1.0,
    "gate_kw": 2.0,
    "lamp_kw": 0.25,
    "road_heating_kw": 300.0,
    "aeration_w": 150.0,
    "pump_station_kw": 50.0,
    "ups_center_kw": 150.0,
    "ups_center_kwh": 800.0,
    "ups_sector_kw": 100.0,
    "ups_sector_kwh": 400.0,
    "ups_charge_kw": 100.0,
    "limit_level3_w": 2500.0,
    "limit_level5_w": 1800.0,
    # water
    "water_tank_m3": 500.0,
    "water_plant_m3_h": 12.0,
    "sewer_return_frac": 0.9,  # delivered water that goes down the drain; the rest is drunk, cooked, evaporates
    "drain_storage_m3": 200.0,  # sump of each gravity network (sanitary, storm) before it overflows
    "sewer_lift_m3_s": 0.012,  # sanitary lift pump at the western works
    "storm_lift_m3_s": 0.08,  # storm lift pump
    # finance
    "sector_budget": 10000.0,
    "colony_budget": 100000.0,
    "tariff_kwh": 0.25,
    "tariff_water_m3": 3.0,
    "sewage_fee": 20.0,
    "internet_fee": 15.0,
    "mine_income_per_tick": 3.0,
    # economy feedback: without these the colony budget only grows and has no attractor
    "colony_payroll_day": 2500.0,  # staff wages and supply shipments, paid every day even with the mine down
    "company_reserve_target": 100000.0,  # reserve the company leaves in the colony
    "company_levy_frac": 0.5,  # share of the surplus above the target the company takes at month close
    "sector_budget_cap": 30000.0,  # sector money above this goes to the colony at month close
    "reactor_upkeep_month": 3000.0,
    # households: one occupied house is one household with its own cash (docs/FINANCE_RU.md)
    "hh_start_cash": 200.0,  # opening balance of every occupied house
    "wage_day": {"mine": 36.0, "reactor": 40.0, "water plant": 34.0, "services": 30.0},  # cr per worker per day
    "wage_manager_mult": 1.6,  # manager houses earn this multiple of the wage
    "idle_pay_frac": 0.2,  # share of the wage paid while the employer stands still (mine stopped, plant down)
    "employer_houses": {"reactor": 18, "water plant": 14},  # occupied houses per employer; services up to the payroll, the rest mine
    "services_payroll_share": 0.9,  # services wages may take at most this share of colony_payroll_day
    "crew_pay_per_repair_tick": 0.15,  # paid to the crew household out of the repair cost, the rest buys materials
    "crew_pay_per_trip": 6.0,  # paid to the driver household for a full waste or sludge load
    "hh_cash_reserve": 600.0,  # above this a household in good standing spends on discretionary purchases
    "hh_discretionary_frac": 0.2,  # share of the cash above the reserve spent per day at the commissary
    "bill_grace_days": 5,  # an unpaid bill becomes overdue this many days after it was issued
    "loan_rate_month": 0.03,  # interest per 30 days on the outstanding principal, accrued daily
    "loan_period_days": 7,  # one instalment per period
    "loan_term_periods": 12,
    "loan_min": 100.0,
    "loan_step": 50.0,  # loans are rounded up to this step
    "credit_limit_months": 2.0,  # credit limit = this many months of the nominal wage ...
    "credit_limit_min": 600.0,  # ... but not below this
    "loan_max_active": 2,
    "loan_prepay_keep": 150.0,  # a household in good standing prepays loans with the cash above this
    "instalment_grace_days": 0,  # an instalment not paid in full at its due day close is overdue at once
    "bankruptcy_overdue_days": 14,  # continuously overdue this long: bankrupt
    "bankrupt_interest": False,  # interest stops accruing on the loans of a bankrupt household
    "bankrupt_eco_heating": True,  # a bankrupt household heats to eco_c to save money
    "mine_flood_days": 3,  # operator event "mine flooded": the mine stands still this long
    # incidents: probability per tick
    "p_xeno": 0.00004,
    "p_vandal": 0.00025,
    "p_animal": 0.0002,
    "p_rover_hit": 0.0003,
    "p_nest_fire": 0.02,  # per tick while a xeno attack near the processor is open
    "p_pump_wear": 0.00002,
    # sewage and waste
    "sludge_per_resident_per_tick": 1.0 / (1440 * 60),
    "waste_per_resident_per_tick": 1.0 / (1440 * 6 * 50),
    "rover_speed": 14.0,  # map units per tick on a good road
    # ui
    "http_port": 8000,
    "default_speed": 20,
}


COSTS = {
    "span": (200, "sector", 120),
    "pole": (600, "sector", 180),
    "feeder": (800, "sector", 240),
    "rp": (1500, "sector", 240),
    "ups": (1000, "sector", 120),
    "tower_line": (500, "colony", 240),
    "trunk": (3000, "colony", 480),
    "substation": (5000, "colony", 480),
    "pump": (4000, "colony", 360),
    "heat_exchanger": (15000, "colony", 720),
    "solar": (800, "colony", 120),
    "wiring": (600, "house", 120),
    "pipes": (1200, "house", 180),
    "aeration": (900, "house", 120),
    "cabinet": (400, "sector", 240),
    "net_span": (150, "sector", 120),
    "terminal": (80, "house", 60),
    "lamp": (300, "sector", 60),
    "road": (500, "sector", 3),
    "gate": (1200, "sector", 120),
    "waste_trip": (100, "sector", 0),
    "sludge_trip": (120, "sector", 0),
    "wall": (800, "sector", 200),
}


TYPE_NAMES = ["barracks", "standard", "insulated", "manager"]


FACILITY_KEYS = (
    "reactor_pos", "solar_pos", "water_plant_pos", "radwaste_pos", "mine_pos", "waste_station_pos",
    "tower_pos", "dish_pos", "ocean_intake_pos", "landing_pad_pos",
)


def colony_layout_cfg(cfg):
    """The layout derived from the colony size, so any number of houses is consistent.

    houses_per_sector = houses_per_row * house_rows. The rows, the streets between them, the ring road, the wall,
    the spine poles and the house type mix follow from that; facilities outside the wall move out with it. The
    default colony (6 x 50 houses, 10 per row) comes out exactly as configured, so cfg is returned unchanged.
    """
    per_row = cfg.get("houses_per_row", 10)
    H = cfg["houses_per_sector"]
    if H % per_row:
        raise ValueError(f"houses_per_sector {H} is not a multiple of houses_per_row {per_row}")
    rows = H // per_row
    N = cfg["sectors"] * H
    step = cfg["house_ring_step"]
    street0 = cfg["house_radius_min"] - 30  # the street below the first row
    ring = street0 + rows * step + 70
    wall = ring + 50
    spine = [200] + [street0 + k * step for k in range(rows + 1)] + [ring]
    counts = list(cfg["type_counts"])
    if sum(counts) != N:
        total = sum(counts)
        counts = [round(n * N / total) for n in counts]
        counts[0] += N - sum(counts)
    derived = {
        "house_rows": rows,
        "ring_road_radius": ring,
        "wall_radius": wall,
        "spine_radii": spine,
        "type_counts": counts,
    }
    if all(cfg.get(k) == v for k, v in derived.items()):
        return cfg
    out = {**cfg, **derived}
    grow = wall - cfg["wall_radius"]  # facilities keep their distance from the wall
    for key in FACILITY_KEYS:
        x, y = cfg[key]
        d = (x * x + y * y) ** 0.5
        out[key] = (x * (d + grow) / d, y * (d + grow) / d)
    return out
