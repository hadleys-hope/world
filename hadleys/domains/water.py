"""domains / water: colony simulation components."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World


from hadleys.numerics import clamp


def water_step(w: World):
    c = w.cfg
    dt = float(c["tick_seconds"])
    electric = bool(
        w.trunk_ok and w.substation_ok and w.r_available_mw > 0 and w.shedding < 7
    )
    w.water_plant_ok = bool(w.water_plant_heat and electric and w.intake_ok)
    need = max(0, c["water_tank_m3"] - w.water_tank_m3)
    desired = c["water_plant_m3_h"] * clamp(need / 60, 0.15, 1.0) if need > 0 else 0.0
    # kWh per m3: warm ice to 0 C, latent heat, then temper water to 5 C.
    # Saline source is conservatively treated as frozen whenever ambient < -2 C.
    ice = max(0, -w.t_out) if w.t_out < -2 else 0
    melt_kwh_m3 = (2.1 * ice + (334 if ice else 0) + 4.18 * 5) / 3.6
    w.water_heat_available_kw = (
        min(c["water_heat_kw"], max(0, w.r_power_mw * (1 / 0.3 - 1) * 1000 * 0.18))
        if w.water_plant_ok
        else 0.0
    )
    raw_limit = w.water_heat_available_kw / max(melt_kwh_m3, 1e-9)
    clean_rate = (
        min(desired, raw_limit * c["water_recovery"]) if w.water_plant_ok else 0.0
    )
    produced = min(need, clean_rate * dt / 3600)
    raw = produced / c["water_recovery"]
    reject = raw - produced
    w.water_plant_m3_h = produced * 3600 / dt
    w.raw_intake_m3_h = raw * 3600 / dt
    w.brine_m3_h = reject * 3600 / dt
    w.water_heat_used_kw = w.raw_intake_m3_h * melt_kwh_m3
    w.water_tank_m3 += produced
    w.ocean_withdrawn_m3 += raw
    w.brine_returned_m3 += reject
    if w.water_tank_m3 <= 0 and w.t % 60 == 0:
        w.log("ALARM", "Water tank empty")
