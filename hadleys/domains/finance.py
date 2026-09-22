"""domains / finance: colony simulation components."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

import numpy as np
from hadleys.config import COSTS


def finance_reserve(w: World, iss: Issue):
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
        i = int(note.split("house:")[-1]) if "house:" in note else -1
        if 0 <= i < w.N:
            w.h_repairs_month[i] += amount
    w.cost_records.append(
        {
            "t": w.t,
            "amount": amount,
            "payer": payer,
            "source": src,
            "cause": cause,
            "note": note,
        }
    )
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
    c = w.cfg
    bill = w.h_meter_day * c["tariff_kwh"] + w.h_water_day * c["tariff_water_m3"]
    income = np.bincount(w.h_sector, weights=bill, minlength=w.S)
    w.sector_budget += income
    w.month_income += income
    w.h_meter_day[:] = 0
    w.h_water_day[:] = 0
    payroll = c["colony_payroll_day"]
    w.colony_budget -= (
        payroll  # may go below zero: that is debt, and colony repairs stop being funded
    )
    w.colony_month_expense += payroll


def finance_month_close(w: World):
    c = w.cfg
    S = w.S
    energy = w.h_meter_month * c["tariff_kwh"]
    water = w.h_water_month * c["tariff_water_m3"]
    sewage = np.full(w.N, c["sewage_fee"])
    internet = np.full(w.N, c["internet_fee"])
    repairs = w.h_repairs_month.copy()
    house_total = energy + water + sewage + internet + repairs
    income = np.bincount(w.h_sector, weights=sewage + internet + repairs, minlength=S)
    w.sector_budget += income
    w.month_income += income
    upkeep = c["reactor_upkeep_month"]
    w.colony_budget -= upkeep
    w.colony_month_expense += upkeep
    extra = np.maximum(0.0, w.sector_budget - c["sector_budget_cap"])
    w.sector_budget -= extra
    w.last_sector_transfer = float(extra.sum())
    w.colony_budget += w.last_sector_transfer
    w.colony_month_income += w.last_sector_transfer
    w.last_levy = (
        max(0.0, w.colony_budget - c["company_reserve_target"]) * c["company_levy_frac"]
    )
    w.colony_budget -= w.last_levy
    w.levy_total += w.last_levy
    if w.last_levy > 0:
        w.log(
            "INFO",
            f"Company took {w.last_levy:.0f} cr of the surplus, sectors passed {w.last_sector_transfer:.0f} cr up",
        )
    common_share = (w.colony_month_expense - w.colony_month_income) / w.N
    top = np.argsort(-house_total)[:5]
    w.last_report = {
        "month": w.month,
        "houses_total": float(house_total.sum()),
        "energy_total": float(energy.sum()),
        "water_total": float(water.sum()),
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
        "levy": round(w.last_levy, 1),
        "sector_transfer": round(w.last_sector_transfer, 1),
        "top_houses": [
            {
                "house": int(i) + 1,
                "sector": int(w.h_sector[i]) + 1,
                "energy": round(float(energy[i]), 1),
                "water": round(float(water[i]), 1),
                "repairs": round(float(repairs[i]), 1),
                "total": round(float(house_total[i]), 1),
            }
            for i in top
        ],
        "by_cause": _expense_by_cause(w),
    }
    w.log(
        "INFO",
        f"Month {w.month} closed: owners paid {house_total.sum():.0f} cr, colony spent {w.colony_month_expense:.0f} cr",
    )
    w.month += 1
    w.h_meter_month[:] = 0
    w.h_water_month[:] = 0
    w.h_water_m3[:] = 0
    w.h_repairs_month[:] = 0
    w.month_income[:] = 0
    w.month_expense[:] = 0
    w.colony_month_expense = 0.0
    w.colony_month_income = 0.0
    w.prog_stats = {}


def _expense_by_cause(w: World):
    out = {}
    for r in w.cost_records:
        if r["t"] > w.t - w.cfg["ticks_per_day"] * w.cfg["days_per_month"]:
            out[r["cause"]] = round(out.get(r["cause"], 0.0) + r["amount"], 1)
    return out
