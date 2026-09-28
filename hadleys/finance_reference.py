"""An independent, single-household re-implementation of the finance rules (docs/FINANCE_RU.md).

It shares no code with domains/households.py: plain Python, one household, one loop over days. The tests
and scripts/finance_acceptance.py feed it the same inputs as the simulation and compare the results day by
day, so a bug in either implementation shows up as a difference.

Inputs (`events`, in time order):
    ("repair", t, amount)      a repair bill issued at tick t (between day closes)
    ("day", t, wage, bill)     a day close at tick t: the day's wage and utility bill
    ("fees", t, amount)        the month close right after the day close at tick t
"""

import math

NORMAL, OVERDUE, BANKRUPT = "normal", "overdue", "bankrupt"


class Household:
    def __init__(self, cfg, cash, nominal_wage_day):
        self.c = cfg
        self.cash = float(cash)
        self.limit = max(cfg["credit_limit_min"], cfg["credit_limit_months"] * nominal_wage_day * cfg["days_per_month"])
        self.bills = []  # [remaining, issued_t]
        self.loans = []  # dicts
        self.status = NORMAL
        self.overdue_since = None
        self.repaid = 0
        self.log = []  # (t, text)

    # ---- helpers
    def debt(self):
        return self.principal() + self.interest() + self.arrears()

    def principal(self):
        return sum(ln["P"] for ln in self.loans)

    def interest(self):
        return sum(ln["I"] for ln in self.loans)

    def arrears(self):
        return sum(b[0] for b in self.bills)

    def pay_loan(self, ln, amount):
        to_i = min(amount, ln["I"])
        to_p = min(amount - to_i, ln["P"])
        amount = to_i + to_p
        if amount <= 1e-9:
            return
        ln["I"] -= to_i
        ln["P"] -= to_p
        if ln["P"] < 1e-9:
            ln["P"] = 0.0
        if ln["I"] < 1e-9:
            ln["I"] = 0.0
        ln["due"] = min(max(0.0, ln["due"] - amount), ln["P"] + ln["I"])
        if ln["due"] < 1e-9:
            ln["due"] = 0.0
            ln["since"] = None
        self.cash -= amount

    def drop_repaid(self, t):
        for ln in [ln for ln in self.loans if ln["P"] + ln["I"] <= 1e-9]:
            self.loans.remove(ln)
            self.repaid += 1
            self.log.append((t, "repaid"))

    def pay_bills(self):
        for b in self.bills:
            if self.cash <= 1e-9:
                break
            if b[0] > 1e-9:
                x = min(self.cash, b[0])
                b[0] -= x
                if b[0] < 1e-9:
                    b[0] = 0.0
                self.cash -= x
        self.bills = [b for b in self.bills if b[0] > 1e-9]

    # ---- the rules
    def day(self, t, wage, bill):
        c = self.c
        tpd = c["ticks_per_day"]
        if self.status != BANKRUPT or c["bankrupt_interest"]:
            for ln in self.loans:
                ln["I"] += round(ln["P"] * ln["rate"] / c["days_per_month"], 2)
        self.cash += wage
        if bill > 0:
            self.bills.append([float(bill), t])
        for ln in self.loans:
            owed = ln["P"] + ln["I"]
            if ln["n"] >= ln["term"]:
                ln["due"] = owed
            elif t >= ln["next"]:
                ln["n"] += 1
                ln["next"] += ln["period"] * tpd
                ln["due"] = owed if ln["n"] >= ln["term"] else min(owed, ln["due"] + ln["pay"])
            if ln["due"] > 1e-9 and ln["since"] is None:
                ln["since"] = t
        for ln in self.loans:
            if ln["due"] > 1e-9 and self.cash > 1e-9:
                self.pay_loan(ln, min(self.cash, ln["due"]))
        self.drop_repaid(t)
        self.pay_bills()
        self.borrow(t)
        self.update_status(t)
        self.spend(t)

    def borrow(self, t):
        c = self.c
        if self.status == BANKRUPT:
            return
        need = self.arrears() - self.cash
        if need <= 1e-9 or any(ln["due"] > 1e-9 for ln in self.loans) or len(self.loans) >= c["loan_max_active"]:
            return
        step = c["loan_step"]
        amount = max(c["loan_min"], math.ceil(need / step - 1e-9) * step)
        room = self.limit - self.principal()
        if amount > room:
            amount = math.floor(room / step + 1e-9) * step
        if amount < c["loan_min"]:
            return
        r = c["loan_rate_month"] * c["loan_period_days"] / c["days_per_month"]
        n = c["loan_term_periods"]
        pay = amount * r / (1 - (1 + r) ** -n) if r > 0 else amount / n
        self.loans.append(
            {
                "A": float(amount),
                "P": float(amount),
                "I": 0.0,
                "rate": c["loan_rate_month"],
                "period": c["loan_period_days"],
                "term": n,
                "pay": math.ceil(pay * 100 - 1e-6) / 100,
                "next": t + c["loan_period_days"] * c["ticks_per_day"],
                "n": 0,
                "due": 0.0,
                "since": None,
            }
        )
        self.cash += amount
        self.log.append((t, f"loan {amount:.0f}"))
        self.pay_bills()

    def update_status(self, t):
        c = self.c
        tpd = c["ticks_per_day"]
        late_bill = any(b[0] > 1e-9 and t - b[1] >= c["bill_grace_days"] * tpd for b in self.bills)
        late_loan = any(
            ln["due"] > 1e-9 and ln["since"] is not None and t - ln["since"] >= c["instalment_grace_days"] * tpd
            for ln in self.loans
        )
        if self.status == BANKRUPT:
            if self.debt() <= 0.005:
                self.status = NORMAL
                self.overdue_since = None
                self.log.append((t, "discharged"))
            return
        if self.status == OVERDUE:
            if not self.bills and not any(ln["due"] > 1e-9 for ln in self.loans):
                self.status = NORMAL
                self.overdue_since = None
                self.log.append((t, "normal"))
            elif t - self.overdue_since >= c["bankruptcy_overdue_days"] * tpd:
                self.status = BANKRUPT
                self.log.append((t, "bankrupt"))
        elif late_bill or late_loan:
            self.status = OVERDUE
            self.overdue_since = t
            self.log.append((t, "overdue"))

    def spend(self, t):
        c = self.c
        if self.status == BANKRUPT:
            keep = 0.0
        elif self.status == NORMAL and not self.bills:
            keep = c["loan_prepay_keep"] if self.loans else c["hh_cash_reserve"]
        else:
            return
        excess = self.cash - keep
        if excess <= 0.005:
            return
        if self.loans:
            for ln in self.loans:
                if excess <= 0.005:
                    break
                before = self.cash
                self.pay_loan(ln, min(excess, ln["P"] + ln["I"]))
                excess -= before - self.cash
            self.drop_repaid(t)
        elif self.status == NORMAL:
            self.cash -= round(excess * c["hh_discretionary_frac"], 2)

    def fees(self, t, amount):
        self.bills.append([float(amount), t])
        self.pay_bills()

    def repair(self, t, amount):
        self.bills.append([float(amount), t])

    def row(self, t):
        return {
            "t": t,
            "cash": round(self.cash, 2),
            "principal": round(self.principal(), 2),
            "interest": round(self.interest(), 2),
            "arrears": round(self.arrears(), 2),
            "status": self.status,
            "loans": len(self.loans),
            "repaid": self.repaid,
        }


def run(cfg, cash, nominal_wage_day, events):
    """Replay the inputs; returns one row per day close (after the month close on month ends)."""
    h = Household(cfg, cash, nominal_wage_day)
    rows = []
    for ev in events:
        if ev[0] == "repair":
            h.repair(ev[1], ev[2])
        elif ev[0] == "day":
            h.day(ev[1], ev[2], ev[3])
            rows.append(h.row(ev[1]))
        elif ev[0] == "fees":
            h.fees(ev[1], ev[2])
            rows[-1] = h.row(ev[1])
    return rows, h
