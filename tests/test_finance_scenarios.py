"""The three acceptance stories: the simulation's finance code against the independent reference model,
day by day, plus the milestones documented in docs/FINANCE_RU.md."""

import math
import unittest

from hadleys import finance_reference as ref
from hadleys.config import CFG
from hadleys.domains import households as hh
from hadleys.scenarios import LEDGER_SCENARIOS, ledger_inputs, run_ledger_scenario

TPD = CFG["ticks_per_day"]


class Scenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {}
        for name, spec in LEDGER_SCENARIOS.items():
            w, i, rows = run_ledger_scenario(name)
            events, wage = ledger_inputs(spec)
            expected, model = ref.run(CFG, spec["cash"], wage, events)
            cls.runs[name] = (w, i, rows, expected, model)

    def test_simulation_matches_reference_every_day(self):
        for name, (w, i, rows, expected, _) in self.runs.items():
            with self.subTest(scenario=name):
                self.assertEqual(len(rows), LEDGER_SCENARIOS[name]["days"])
                for d, (a, b) in enumerate(zip(rows, expected), start=1):
                    self.assertEqual(a, b, f"day {d}")

    def test_money_is_conserved(self):
        for name, (w, *_rest) in self.runs.items():
            with self.subTest(scenario=name):
                self.assertAlmostEqual(hh.internal_total(w) - w.fin_baseline - sum(w.fin_ext.values()), 0.0, places=5)

    def test_A_solvent(self):
        w, i, rows, _, model = self.runs["A-solvent"]
        self.assertTrue(all(r["status"] == "normal" and r["loans"] == 0 and r["cash"] > 0 for r in rows))
        # wage 2 x 40 = 80, bill 18: +62 a day until the reserve (600), then 20% of the excess is spent
        self.assertEqual(rows[0]["cash"], 200 + 80 - 18)
        self.assertEqual(rows[5]["cash"], 200 + 6 * 62)  # 572, still below the reserve
        # fixed point of c' = c + 62 - 0.2 (c + 62 - 600): c* = 600 + 62 / 0.2 - 62 = 848
        self.assertAlmostEqual(rows[28]["cash"], 848, delta=5)
        self.assertGreater(float(w.hh_prev_month[i, hh.PAID]), 30 * 18 + 35)  # bought at the commissary too

    def test_B_credit_then_recovery(self):
        w, i, rows, _, model = self.runs["B-credit-recovery"]
        # day 3: cash 200.40 + standby wage 14.40 - bill 18 = 196.80 against a 600 cr repair: short by 403.20
        self.assertEqual(model.log[0], (3 * TPD, "loan 450"))
        r = CFG["loan_rate_month"] * CFG["loan_period_days"] / CFG["days_per_month"]
        n = CFG["loan_term_periods"]
        self.assertEqual(math.ceil(450 * r / (1 - (1 + r) ** -n) * 100) / 100, 39.23)
        self.assertIn("12 x 39.23 cr every 7 days", " ".join(t for _, t in w.hh_notes[i]))
        self.assertEqual(rows[2]["principal"], 450.0)
        self.assertEqual(rows[2]["cash"], round(196.80 + 450 - 600, 2))
        self.assertEqual(rows[3]["interest"], 0.45)  # 450 x 3% / 30 per day
        repaid = next(d for d, row in enumerate(rows, start=1) if row["repaid"])
        self.assertEqual(repaid, 19)
        self.assertTrue(all(row["status"] == "normal" for row in rows))
        self.assertEqual(rows[-1]["principal"] + rows[-1]["interest"] + rows[-1]["arrears"], 0)

    def test_C_bankruptcy(self):
        w, i, rows, _, model = self.runs["C-bankruptcy"]
        status = {d: row["status"] for d, row in enumerate(rows, start=1)}
        # credit limit max(600, 2 x 36 x 30) = 2160: the loan is 2150, the rest of the 2700 repair stays unpaid
        self.assertEqual(model.log[0], (3 * TPD, "loan 2150"))
        self.assertGreater(rows[2]["arrears"], 500)
        self.assertEqual(min(d for d, s in status.items() if s == "overdue"), 8)  # the repair bill, 5 days late
        first_bankrupt = min(d for d, s in status.items() if s == "bankrupt")
        self.assertEqual(first_bankrupt, 8 + CFG["bankruptcy_overdue_days"])
        after = rows[first_bankrupt - 1:]
        self.assertTrue(all(row["status"] == "bankrupt" for row in after))
        self.assertTrue(all(row["cash"] == 0 for row in after), "every credit goes to the creditors")
        self.assertTrue(all(row["interest"] == 0 for row in after[1:]), "no interest after bankruptcy")
        self.assertEqual(max(row["loans"] for row in after), after[0]["loans"], "no new loans")
        self.assertGreater(after[-1]["principal"] + after[-1]["arrears"], 1500, "the debt does not vanish")
        self.assertIn("BANKRUPT after 14 days overdue", " ".join(t for _, t in w.hh_notes[i]))


if __name__ == "__main__":
    unittest.main()
