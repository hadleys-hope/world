"""domains / finance: colony, sector and household budgets.

Who pays whom is described in docs/FINANCE_RU.md; the household side lives in domains/households.py.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.models import Issue
    from hadleys.world import World

import numpy as np
from hadleys.config import COSTS
from hadleys.domains.households import (
    EARNED,
    K_JOB,
    book,
    households_bill_repair,
    households_day_close,
    households_month_close,
    households_month_roll,
    transfer,
)


def _free_account(w: World, payer, sector, amount):
    """The account that can pay `amount` now without touching money reserved for funded repairs:
    the sector for sector and house costs, the colony as the fallback and for colony costs."""
    if payer in ("sector", "house") and sector >= 0:
        if w.sector_budget[sector] - w.sector_reserved[sector] >= amount:
            return f"sector:{sector}"
    if w.colony_budget - w.colony_reserved >= amount:
        return "colony"
    return None


def _reserve(w: World, acct, amount):
    if acct == "colony":
        w.colony_reserved += amount
    else:
        w.sector_reserved[int(acct[7:])] += amount


def _release(w: World, acct, amount):
    if acct == "colony":
        w.colony_reserved = max(0.0, w.colony_reserved - amount)
    else:
        s = int(acct[7:])
        w.sector_reserved[s] = max(0.0, w.sector_reserved[s] - amount)


def finance_reserve(w: World, iss: Issue):
    """Funding check (every 30 ticks for open issues): the payer has the money free right now. Nothing is set
    aside yet, so a long queue of jobs no crew can take cannot starve an urgent repair of its money."""
    return iss.funded_by != "" or _free_account(w, iss.payer, iss.sector, iss.cost) is not None


def finance_commit(w: World, iss: Issue):
    """A crew takes the job: set the money aside until the repair is done, so no other job can spend it."""
    if iss.funded_by:
        return True
    acct = _free_account(w, iss.payer, iss.sector, iss.cost)
    if acct is None:
        return False
    _reserve(w, acct, iss.cost)
    iss.funded_by = acct
    return True


def finance_release(w: World, iss: Issue):
    """Return the reservation of an issue closed without a repair."""
    if getattr(iss, "funded_by", ""):
        _release(w, iss.funded_by, iss.cost)
        iss.funded_by = ""


def _spend(w: World, acct, amount, labour, crew_house, what):
    """Pay a job from `acct`: the crew household's labour, the rest to suppliers for materials."""
    labour = min(labour, amount) if crew_house >= 0 else 0.0
    if labour > 0:
        transfer(w, acct, f"house:{crew_house}", labour, "job pay", K_JOB)
        w.hh_month[crew_house, EARNED] += labour
    transfer(w, acct, "ext:suppliers", amount - labour, what)
    if acct == "colony":
        w.colony_month_expense += amount
        return "colony"
    s = int(acct[7:])
    w.month_expense[s] += amount
    return f"sector {s + 1}"


def finance_record(
    w: World, amount, payer, sector, cause, note, house=-1, crew_house=-1, funded_by="", labour=0.0
):
    """Pay for a finished repair. The account that funded it pays (its reservation is released); a house
    repair is then billed to the household. Nothing funded and no money left: the cost is 'unpaid'."""
    if funded_by:
        _release(w, funded_by, amount)
        acct = funded_by
    else:  # issues funded before reservations existed decide at completion, as they used to
        acct = _free_account(w, payer, sector, amount)
    if acct is None:
        w.unfunded_total += amount
        src = "unpaid"
    else:
        src = _spend(w, acct, amount, labour, crew_house, "repair materials")
    if payer == "house" and house >= 0:
        w.h_repairs_month[house] += amount
        if acct is not None:
            households_bill_repair(w, house, amount, acct, note)
    w.cost_records.append(
        {
            "t": w.t,
            "amount": amount,
            "payer": payer,
            "source": src,
            "cause": cause,
            "note": note,
            "house": house,
        }
    )
    if len(w.cost_records) > 2000:
        w.cost_records = w.cost_records[-2000:]
    return acct is not None


def finance_pay(w: World, cost_key, sector, cause, note, crew_house=-1, frac=1.0, load=None):
    """A service paid on the spot (waste and sludge trips). `frac` scales the price; the driver is paid
    crew_pay_per_trip per full load, `load` being the share of a load this stop added (default `frac`)."""
    cost, payer, _ = COSTS[cost_key]
    amount = cost * frac
    if amount <= 0:
        return True
    acct = _free_account(w, payer, sector, amount)
    if acct is None:
        w.unfunded_total += amount
        src = "unpaid"
    else:
        labour = w.cfg["crew_pay_per_trip"] * (frac if load is None else load)
        src = _spend(w, acct, amount, labour, crew_house, cost_key.replace("_", " "))
    w.cost_records.append(
        {"t": w.t, "amount": amount, "payer": payer, "source": src, "cause": cause, "note": note, "house": -1}
    )
    if len(w.cost_records) > 2000:
        w.cost_records = w.cost_records[-2000:]
    return acct is not None


def finance_day_close(w: World):
    c = w.cfg
    if w.t // c["ticks_per_day"] == w.hh_last_close_day:
        return  # this day is closed already
    bill = w.h_meter_day * c["tariff_kwh"] + w.h_water_day * c["tariff_water_m3"]
    # wages, bills, loans; the sectors receive what the households actually paid
    services = households_day_close(w, bill)
    ore = w.fin_ext["ore"] - w.fin_ore_booked  # ore income arrives every tick; it is journaled once a day
    book(w, "ext:ore", "colony", ore, "ore sales")
    w.fin_ore_booked = w.fin_ext["ore"]
    w.h_meter_day[:] = 0
    w.h_water_day[:] = 0
    payroll = c["colony_payroll_day"]
    w.colony_budget -= (
        payroll  # may go below zero: that is debt, and colony repairs stop being funded
    )
    w.colony_month_expense += payroll
    # the payroll pays the service staff living in the colony; the rest is off-world staff and shipments
    if services > payroll:
        w.colony_budget -= services - payroll
        w.colony_month_expense += services - payroll
    w.fin_ext["suppliers"] -= max(0.0, payroll - services)
    book(w, "colony", "ext:suppliers", max(0.0, payroll - services), "shipments and off-world staff")


def finance_month_close(w: World):
    c = w.cfg
    month = w.t // (c["ticks_per_day"] * c["days_per_month"])
    if month == w.fin_last_month_close:
        return  # this month is closed already
    w.fin_last_month_close = month
    energy = w.h_meter_month * c["tariff_kwh"]
    water = w.h_water_month * c["tariff_water_m3"]
    sewage = np.full(w.N, c["sewage_fee"])
    internet = np.full(w.N, c["internet_fee"])
    repairs = w.h_repairs_month.copy()
    house_total = energy + water + sewage + internet + repairs
    # fees are billed to the households; house repairs were billed when they were done
    households_month_close(w)
    upkeep = c["reactor_upkeep_month"]
    w.colony_budget -= upkeep
    w.colony_month_expense += upkeep
    w.fin_ext["suppliers"] -= upkeep
    book(w, "colony", "ext:suppliers", upkeep, "reactor upkeep")
    extra = np.maximum(0.0, w.sector_budget - np.maximum(c["sector_budget_cap"], w.sector_reserved))
    w.sector_budget -= extra
    w.last_sector_transfer = float(extra.sum())
    w.colony_budget += w.last_sector_transfer
    w.colony_month_income += w.last_sector_transfer
    for s in np.flatnonzero(extra > 0):
        book(w, f"sector:{s}", "colony", float(extra[s]), "sector surplus")
    w.last_levy = (
        max(0.0, w.colony_budget - c["company_reserve_target"]) * c["company_levy_frac"]
    )
    w.colony_budget -= w.last_levy
    w.levy_total += w.last_levy
    w.fin_ext["company"] -= w.last_levy
    book(w, "colony", "ext:company", w.last_levy, "company levy")
    if w.last_levy > 0:
        w.log(
            "INFO",
            f"Company took {w.last_levy:.0f} cr of the surplus, sectors passed {w.last_sector_transfer:.0f} cr up",
        )
    common_share = (w.colony_month_expense - w.colony_month_income) / w.N
    top = np.argsort(-house_total)[:5]
    households = households_month_roll(w)
    w.last_report = {
        "month": w.month,
        "houses_total": float(house_total.sum()),
        "energy_total": float(energy.sum()),
        "water_total": float(water.sum()),
        "repairs_total": float(repairs.sum()),
        "kwh_total": float(w.h_meter_month.sum()),
        # everything the sectors received this month: the daily utility bills, the fees, repaid repairs
        "sector_income": [round(float(x), 1) for x in w.month_income],
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
        "households": households,
    }
    w.log(
        "INFO",
        f"Month {w.month} closed: owners billed {house_total.sum():.0f} cr, colony spent {w.colony_month_expense:.0f} cr",
    )
    if households["arrears"] > 0.5 or households["bankrupt"]:
        w.log(
            "WARN",
            f"Households owe {households['debt']:.0f} cr ({households['arrears']:.0f} cr unpaid bills), "
            f"{households['overdue']} overdue, {households['bankrupt']} bankrupt",
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
    """Money actually spent on repairs and services this month, by cause (unpaid costs are not spent)."""
    out = {}
    for r in w.cost_records:
        if r["source"] == "unpaid":
            continue
        if r["t"] > w.t - w.cfg["ticks_per_day"] * w.cfg["days_per_month"]:
            out[r["cause"]] = round(out.get(r["cause"], 0.0) + r["amount"], 1)
    return out
