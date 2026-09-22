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
