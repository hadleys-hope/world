"""Household finance rules and the fixed accounting defects (docs/FINANCE_RU.md)."""

import json
import math
import unittest

import numpy as np

from hadleys.api.snapshots import house_snapshot, snapshot
from hadleys.domains import households as hh
from hadleys.domains.finance import (
    finance_commit,
    finance_day_close,
    finance_month_close,
    finance_pay,
    finance_record,
    finance_reserve,
)
from hadleys.domains.incidents import _pipes_blocked, damage_target, resolve_issue
from hadleys.simulation import inject
from hadleys.world import World


def unexplained(w):
    return hh.internal_total(w) - w.fin_baseline - sum(w.fin_ext.values())


def rebase(w):
    """After a test sets a balance by hand, the money check starts from there."""
    w.fin_baseline = hh.internal_total(w) - sum(w.fin_ext.values())


def ordinary_house(w, residents=1, employer="mine"):
    crew = set(w.crew_house.values())
    for i in range(w.N):
        if w.h_residents[i] == residents and w.h_type[i] != 3 and i not in crew:
            w.hh_employer[i] = hh.EMPLOYERS.index(employer)
            return i
    raise AssertionError("no house")


def close_day(w, day, bills=None, mine=1.0):
    """A day close at the end of `day` with the given utility bill per house (default nothing)."""
    tpd = w.cfg["ticks_per_day"]
    w.t = day * tpd
    w.h_meter_day[:] = 0.0
    w.h_water_day[:] = 0.0
    for i, amount in (bills or {}).items():
        w.h_meter_day[i] = amount / w.cfg["tariff_kwh"]
    w.fin_act = [mine * tpd, float(tpd), tpd]
    finance_day_close(w)


class Accounting(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def test_house_payer_repairs_bill_the_right_household(self):
        """aeration:i and terminal:i were never billed: the house index came from parsing 'house:' in a note."""
        w = self.w
        i = ordinary_house(w)
        s = int(w.h_sector[i])
        for target, cost in ((f"house:{i}", 600.0), (f"aeration:{i}", 900.0), (f"terminal:{i}", 80.0)):
            damage_target(w, target, "test", 1.0)
            iss = next(x for x in w.issues if x.target == target and x.status == "open")
            self.assertTrue(finance_reserve(w, iss))
            self.assertTrue(finance_commit(w, iss))
            self.assertEqual(iss.funded_by, f"sector:{s}")
            before = float(w.sector_budget[s])
            resolve_issue(w, iss)
            self.assertAlmostEqual(before - float(w.sector_budget[s]), cost)
        self.assertEqual([b[2] for b in w.hh_bills[i]], [600.0, 900.0, 80.0])
        self.assertTrue(all(b[4] == f"sector:{s}" for b in w.hh_bills[i]))
        self.assertAlmostEqual(float(w.h_repairs_month[i]), 1580.0)
        self.assertAlmostEqual(float(w.sector_reserved[s]), 0.0)
        self.assertAlmostEqual(unexplained(w), 0.0, places=6)

    def test_reservation_prevents_funding_twice(self):
        """finance_reserve used to check the balance without holding it: two repairs, one set of credits.
        Now the money is set aside when a crew takes the job and nobody else can spend it."""
        w = self.w
        w.colony_budget = 0.0
        damage_target(w, "pole:130", "test", 1.0)  # 600 cr
        p = int(w.p_sector[130])
        w.sector_budget[p] = 1000.0
        damage_target(w, "lamp:131", "test", 1.0)  # 300 cr
        damage_target(w, "span:132", "test", 1.0)  # 200 cr
        jobs = [x for x in w.issues if x.sector == p]
        self.assertTrue(all(finance_reserve(w, x) for x in jobs), "each alone is affordable")
        taken = [finance_commit(w, x) for x in jobs]
        self.assertEqual(taken, [True, True, False], "600 + 300 fit into 1000, the 200 on top does not")
        self.assertAlmostEqual(float(w.sector_reserved[p]), 900.0)
        self.assertFalse(finance_pay(w, "sludge_trip", p, "normal_operation", "test"), "120 > the 100 not set aside")

    def test_a_queue_of_house_jobs_does_not_starve_an_urgent_repair(self):
        """Reserving at funding time let 150 burst-pipe jobs, done one at a time, lock up the colony's money."""
        w = self.w
        for i in range(150):
            w.h_burst[i] = True
            w.open_issue("pipes_burst", f"house:{i}", int(w.h_sector[i]), "freeze", "pipes", (0, 0), "critical")
        damage_target(w, "reactor:heat_exchanger", "marines", 0.8)
        for iss in w.issues:
            iss.status = "funded" if finance_reserve(w, iss) else "unfunded"
        hx = w.issues[-1]
        self.assertEqual(hx.status, "funded")
        self.assertTrue(finance_commit(w, hx))
        self.assertEqual(hx.funded_by, "colony")

    def test_a_driver_taking_a_repair_rover_returns_the_job(self):
        from hadleys.domains.driving import driver_command

        w = self.w
        damage_target(w, "span:40", "test", 1.0)
        iss = w.issues[-1]
        rover = next(r for r in w.rovers if r.name == "engineer")
        finance_commit(w, iss)
        iss.status = "in_progress"
        rover.job = iss
        s = iss.sector
        self.assertTrue(driver_command(w, {"cmd": "drive_claim", "name": "engineer", "owner": "x" * 20})["ok"])
        self.assertEqual(iss.status, "funded")
        self.assertIsNone(rover.job)
        self.assertAlmostEqual(float(w.sector_reserved[s]), 0.0)

    def test_sludge_driver_is_paid_by_the_full_load(self):
        w = self.w
        crew = w.crew_house["sludge"]
        cash = float(w.hh_cash[crew])
        finance_pay(w, "sludge_trip", 0, "normal_operation", "test", crew_house=crew, load=0.25)
        self.assertAlmostEqual(float(w.hh_cash[crew]) - cash, w.cfg["crew_pay_per_trip"] * 0.25)

    def test_ore_income_is_journaled(self):
        w = self.w
        w.fin_ext["ore"] += 4320.0
        w.colony_budget += 4320.0
        close_day(w, 1)
        self.assertAlmostEqual(w.fin_flows[("ext:ore", "colony", "ore sales")], 4320.0)
        self.assertAlmostEqual(unexplained(w), 0.0, places=6)

    def test_colony_fronted_house_repair_is_repaid_to_the_colony(self):
        """House repairs were reimbursed to the sector at month close even when the colony paid."""
        w = self.w
        i = ordinary_house(w)
        s = int(w.h_sector[i])
        w.sector_budget[s] = 0.0
        damage_target(w, f"house:{i}", "test", 1.0)
        iss = w.issues[-1]
        self.assertTrue(finance_commit(w, iss))
        self.assertEqual(iss.funded_by, "colony")
        resolve_issue(w, iss)
        colony = w.colony_budget
        close_day(w, 1)
        self.assertEqual(w.hh_bills[i], [])
        self.assertAlmostEqual(w.colony_budget - colony, 600.0 - w.cfg["colony_payroll_day"])
        self.assertAlmostEqual(float(w.sector_budget[s]), 0.0)

    def test_repair_nobody_could_pay_is_not_billed(self):
        w = self.w
        i = ordinary_house(w)
        w.sector_budget[:] = 0.0
        w.colony_budget = 0.0
        rebase(w)
        finance_record(w, 600.0, "house", int(w.h_sector[i]), "test", "repair", house=i)
        self.assertEqual(w.hh_bills[i], [])
        self.assertEqual(w.unfunded_total, 600.0)
        self.assertEqual(w.cost_records[-1]["source"], "unpaid")
        self.assertAlmostEqual(unexplained(w), 0.0, places=6)

    def test_crew_is_paid_for_the_repair(self):
        w = self.w
        crew = w.crew_house["engineer"]
        rover = next(r for r in w.rovers if r.name == "engineer")
        damage_target(w, "span:40", "test", 1.0)
        iss = w.issues[-1]
        finance_commit(w, iss)
        cash = float(w.hh_cash[crew])
        resolve_issue(w, iss, rover)
        pay = w.cfg["crew_pay_per_repair_tick"] * iss.duration
        self.assertAlmostEqual(float(w.hh_cash[crew]) - cash, pay)
        self.assertAlmostEqual(w.fin_flows[(f"sector:{iss.sector}", "ext:suppliers", "repair materials")], iss.cost - pay)
        self.assertAlmostEqual(unexplained(w), 0.0, places=6)

    def test_waste_collection_is_charged_by_the_share_taken(self):
        w = self.w
        before = float(w.sector_budget[0])
        self.assertTrue(finance_pay(w, "waste_trip", 0, "normal_operation", "test", frac=0.1))
        self.assertAlmostEqual(before - float(w.sector_budget[0]), 10.0)

    def test_failed_service_payment_is_recorded(self):
        w = self.w
        w.sector_budget[:] = 0.0
        w.colony_budget = 0.0
        self.assertFalse(finance_pay(w, "sludge_trip", 1, "normal_operation", "test"))
        self.assertEqual(w.cost_records[-1]["source"], "unpaid")
        self.assertEqual(w.unfunded_total, 120.0)

    def test_new_pole_closes_the_lamp_job_without_a_second_charge(self):
        w = self.w
        damage_target(w, "lamp:50", "test", 1.0)
        damage_target(w, "pole:50", "test", 1.0)
        lamp, pole = w.issues[-2], w.issues[-1]
        finance_commit(w, lamp)
        finance_commit(w, pole)
        s = pole.sector
        before = float(w.sector_budget[s])
        resolve_issue(w, pole)
        self.assertEqual(lamp.status, "resolved")
        self.assertAlmostEqual(before - float(w.sector_budget[s]), pole.cost)
        self.assertAlmostEqual(float(w.sector_reserved[s]), 0.0)

    def test_pipes_wait_until_the_house_can_hold_heat(self):
        w = self.w
        i = 5
        w.h_burst[i] = True
        iss = w.open_issue("pipes_burst", f"house:{i}", 0, "freeze", "pipes", (0, 0), "critical")
        w.h_t_in[i] = -5.0
        self.assertTrue(_pipes_blocked(w, iss))
        w.h_t_in[i] = 15.0
        w.h_power_ok[i] = False
        self.assertTrue(_pipes_blocked(w, iss))
        w.h_power_ok[i] = True
        self.assertFalse(_pipes_blocked(w, iss))

    def test_operator_grant_is_booked(self):
        w = self.w
        inject(w, "money")
        self.assertEqual(w.colony_month_income, 50000)
        self.assertAlmostEqual(unexplained(w), 0.0, places=6)


class Households(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def test_vacant_houses_are_company_housing(self):
        w = self.w
        v = int(np.flatnonzero(~w.hh_active)[0])
        s = int(w.h_sector[v])
        before = float(w.sector_budget[s])
        close_day(w, 1, {v: 20.0})
        self.assertAlmostEqual(float(w.sector_budget[s]) - before, 20.0)
        self.assertAlmostEqual(w.fin_flows[("ext:company", f"sector:{s}", "bills of company housing")], 20.0)
        self.assertEqual(w.hh_bills[v], [])
        self.assertEqual(float(w.hh_cash[v]), 0.0)

    def test_wages_follow_the_mine(self):
        """The mine stops: its households get standby pay; services are paid out of the colony payroll."""
        w = self.w
        miner = ordinary_house(w, 1, "mine")
        clerk = ordinary_house(w, 2, "services")
        colony = w.colony_budget
        close_day(w, 1, mine=0.0)
        rate = w.cfg["wage_day"]["mine"] * w.cfg["idle_pay_frac"]
        self.assertAlmostEqual(float(w.hh_month[miner, hh.EARNED]), rate)
        self.assertAlmostEqual(float(w.hh_month[clerk, hh.EARNED]), 2 * w.cfg["wage_day"]["services"])
        self.assertAlmostEqual(colony - w.colony_budget, w.cfg["colony_payroll_day"])
        close_day(w, 2, mine=0.5)
        self.assertAlmostEqual(float(w.hh_month[miner, hh.EARNED]) - rate, 36 * (0.2 + 0.8 * 0.5))
        self.assertAlmostEqual(unexplained(w), 0.0, places=6)

    def test_mine_flood_command_stops_the_mine(self):
        w = self.w
        info = inject(w, "mine")
        self.assertIn("Mine flooded", info["text"])
        self.assertEqual(w.mine_closed_until, w.cfg["mine_flood_days"] * w.cfg["ticks_per_day"])

    def test_bill_short_payment_creates_arrears_not_negative_cash(self):
        w = self.w
        i = ordinary_house(w)
        w.hh_cash[i] = 0.0
        w.hh_employer[i] = -1  # no income at all
        w.cfg = {**w.cfg, "loan_max_active": 0}  # and no credit
        close_day(w, 1, {i: 25.0})
        self.assertEqual(float(w.hh_cash[i]), 0.0)
        self.assertAlmostEqual(float(w.hh_arrears[i]), 25.0)
        self.assertEqual(hh.STATUS[int(w.hh_status[i])], "normal")
        for d in range(2, 7):
            close_day(w, d)
        self.assertEqual(hh.STATUS[int(w.hh_status[i])], "overdue", "unpaid 5 days after issue")

    def test_loan_terms(self):
        """Annuity instalment, daily interest on the principal, credit and debt kept apart."""
        w = self.w
        c = w.cfg
        i = ordinary_house(w, 1, "mine")
        w.hh_cash[i] = 0.0
        rebase(w)
        s = int(w.h_sector[i])
        finance_record(w, 1000.0, "house", s, "test", "repair", house=i)
        close_day(w, 1, {i: 18.0})
        loan = w.hh_loans[i][0]
        wage = c["wage_day"]["mine"]
        self.assertEqual(loan["amount"], math.ceil((1000 + 18 - wage) / 50) * 50)
        r = c["loan_rate_month"] * c["loan_period_days"] / c["days_per_month"]
        n = c["loan_term_periods"]
        self.assertAlmostEqual(loan["payment"], math.ceil(loan["amount"] * r / (1 - (1 + r) ** -n) * 100) / 100)
        self.assertAlmostEqual(float(w.hh_principal[i]), loan["amount"])
        self.assertEqual(float(w.hh_arrears[i]), 0.0)
        cash = float(w.hh_cash[i])
        close_day(w, 2, {i: 18.0})
        daily = round(loan["amount"] * c["loan_rate_month"] / c["days_per_month"], 2)
        self.assertAlmostEqual(float(w.hh_interest[i]), daily)
        self.assertAlmostEqual(float(w.hh_cash[i]) - cash, wage - 18.0)
        self.assertAlmostEqual(unexplained(w), 0.0, places=6)

    def test_bankrupt_household_cannot_borrow_or_buy_and_keeps_its_debt(self):
        w = self.w
        i = ordinary_house(w, 1, "mine")
        w.hh_cash[i] = 0.0
        rebase(w)
        finance_record(w, 5000.0, "house", int(w.h_sector[i]), "test", "repair", house=i)
        for d in range(1, 30):
            close_day(w, d, {i: 18.0}, mine=0.0)
        self.assertEqual(hh.STATUS[int(w.hh_status[i])], "bankrupt")
        loans = len(w.hh_loans[i])
        debt = hh._debt(w, i)
        self.assertGreater(debt, 0)
        interest = float(w.hh_interest[i])
        w.hh_cash[i] = 0.0
        rebase(w)
        close_day(w, 30, {i: 18.0}, mine=1.0)
        self.assertEqual(len(w.hh_loans[i]), loans, "no new loan while bankrupt")
        self.assertLessEqual(float(w.hh_interest[i]), interest, "interest stops")
        self.assertEqual(float(w.hh_cash[i]), 0.0, "every credit goes to the creditors, nothing is bought")
        rows = w.hh_led[i, : min(int(w.hh_led_n[i]), hh.LEDGER_LEN)]
        self.assertNotIn(hh.K_BUY, set(rows["k"].tolist()))
        self.assertEqual(hh.STATUS[int(w.hh_status[i])], "bankrupt")
        # the debt is repaid in full (say, a relative pays it): bankruptcy is discharged at the next close
        w.hh_cash[i] = hh._debt(w, i) + 100.0
        rebase(w)
        close_day(w, 31, mine=1.0)
        self.assertEqual(hh._debt(w, i), 0.0)
        close_day(w, 32, mine=1.0)
        self.assertEqual(hh.STATUS[int(w.hh_status[i])], "normal")
        self.assertEqual(int(w.hh_bankruptcies[i]), 1)
        self.assertAlmostEqual(unexplained(w), 0.0, places=6)

    def test_bankrupt_household_heats_to_eco(self):
        from hadleys.domains.houses import houses_decide

        w = self.w
        w.hh_status[7] = hh.BANKRUPT
        houses_decide(w)
        self.assertEqual(float(w.h_target[7]), w.cfg["eco_c"])
        self.assertEqual(float(w.h_target[8]), w.cfg["comfort_c"])

    def test_month_close_bills_fees_and_reports_the_households(self):
        w = self.w
        close_day(w, 30)
        finance_month_close(w)
        rep = w.last_report
        self.assertAlmostEqual(sum(rep["sector_income"]), 300 * 35.0, places=1)
        self.assertEqual(rep["households"]["households"], 208)
        self.assertEqual(rep["households"]["debtors"], 0)
        self.assertGreater(float(w.hh_prev_month[:, hh.PAID].sum()), 0.0)
        self.assertAlmostEqual(unexplained(w), 0.0, places=6)

    def test_finance_never_touches_the_world_rng(self):
        w = self.w
        state = json.dumps(w.rng.bit_generator.state, sort_keys=True)
        i = ordinary_house(w)
        finance_record(w, 600.0, "house", int(w.h_sector[i]), "test", "repair", house=i)
        for d in range(1, 12):
            close_day(w, d, {i: 18.0})
        finance_month_close(w)
        self.assertEqual(json.dumps(w.rng.bit_generator.state, sort_keys=True), state)

    def test_snapshots_are_json_and_read_only(self):
        from hadleys.domains.households import finance_snapshot

        w = self.w
        i = ordinary_house(w)
        finance_record(w, 600.0, "house", int(w.h_sector[i]), "test", "repair", house=i)
        close_day(w, 1, {i: 18.0})
        before = (w.hh_cash.tobytes(), w.hh_led.tobytes(), sorted(w.fin_flows.items()))
        for _ in range(2):
            json.dumps(snapshot(w), allow_nan=False)
            house = json.loads(json.dumps(house_snapshot(w, i), allow_nan=False))
            json.dumps(finance_snapshot(w), allow_nan=False)
        self.assertEqual((w.hh_cash.tobytes(), w.hh_led.tobytes(), sorted(w.fin_flows.items())), before)
        fin = house["finance"]
        self.assertEqual(fin["loans"][0]["principal"], fin["principal"])
        self.assertIsNotNone(fin["next_payment"])
        self.assertIn("loan received", {r["kind"] for r in fin["ledger"]})
        self.assertIn("repair bill", " ".join(n["text"] for n in fin["notes"]))


if __name__ == "__main__":
    unittest.main()
