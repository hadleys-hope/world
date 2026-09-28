"""domains / households: the money of the households.

One occupied house is one household. It earns a wage from its employer and, if one of its residents drives a
service rover, pay for the work done; it pays utility bills, monthly fees and repairs of its house from its own
cash, borrows from an external bank when the cash runs out, can fall behind and go bankrupt. Vacant houses
(no residents) are company housing: the Company pays their bills.

Accounts. Internal: the colony budget, the six sector budgets and one cash account per household. External
counterparties: ext:company (employer of the mine, reactor and water plant staff, landlord of vacant houses,
takes the levy), ext:suppliers (materials, shipments, reactor upkeep), ext:ore (buys the mine output),
ext:bank (lends to households). transfer() moves money from exactly one account to exactly one other, so
every payment is one receipt, and w.fin_ext holds the net amount each counterparty has put into the colony:

    colony + sectors + household cash == w.fin_baseline + sum(w.fin_ext.values())

Obligations are kept apart: loan principal, accrued loan interest and unpaid bills (arrears); cash never
goes negative. Everything runs inside world_tick at the day and month closes, so a pause stops accruals,
the speed only changes how soon the closes arrive, and all state is pickled with the world.

Settlement at a day close, in this order (docs/FINANCE_RU.md):
 1. interest for the day on every loan (not for a bankrupt household unless bankrupt_interest),
 2. wages (services from the colony payroll, everybody else from the Company),
 3. the day's utility bill (energy + water) is issued,
 4. instalments that fall due are added to the loan's due amount,
 5. payments from cash: loan dues first, then bills oldest first,
 6. a loan if bills are still open and the household may borrow,
 7. status: normal -> overdue when a bill is unpaid bill_grace_days after issue or an instalment is not
    paid at its due close; overdue -> normal only when fully current (no open bill, no unpaid instalment);
    overdue bankruptcy_overdue_days in a row -> bankrupt; bankrupt -> normal once every debt is repaid,
 8. a household in good standing prepays its loans or, without loans, buys at the commissary;
    a bankrupt one hands every credit left to the bank.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hadleys.world import World

from collections import deque
import math
import numpy as np

EMPLOYERS = ("mine", "reactor", "water plant", "services")
SERVICES = 3
STATUS = ("normal", "overdue", "bankrupt")
NORMAL, OVERDUE, BANKRUPT = 0, 1, 2
EPS = 1e-9

# ledger rows: code -> (name, sign of the cash change, sign of the debt change)
K_OPEN, K_WAGE, K_JOB, K_BILL, K_PAY, K_LOAN, K_INTEREST, K_INST, K_BUY = range(1, 10)
LEDGER_KINDS = {
    K_OPEN: ("opening balance", 1, 0),
    K_WAGE: ("wage", 1, 0),
    K_JOB: ("job pay", 1, 0),
    K_BILL: ("bill", 0, 1),
    K_PAY: ("bill paid", -1, -1),
    K_LOAN: ("loan received", 1, 1),
    K_INTEREST: ("interest", 0, 1),
    K_INST: ("loan payment", -1, -1),
    K_BUY: ("purchase", -1, 0),
}
LEDGER_LEN = 256  # rows kept per house
HIST_DAYS = 120  # daily cash/debt samples kept per house
SERIES_DAYS = 400  # colony-wide daily samples
LEDGER_DTYPE = np.dtype(
    [("t", "i8"), ("k", "i2"), ("amt", "f8"), ("cash", "f8"), ("debt", "f8"), ("ref", "i8")]
)
EARNED, BILLED, PAID, BORROWED = range(4)  # columns of hh_month / hh_prev_month


# ---------------------------------------------------------------- set-up


def households_init(w: World):
    """Create the household state; called at the end of World.__init__ (and by Store.migrate for old saves)."""
    c = w.cfg
    N = w.N
    w.hh_active = w.h_residents > 0
    w.hh_workers = np.where(w.hh_active, w.h_residents, 0).astype(np.int64)
    w.hh_employer = np.full(N, -1, dtype=np.int64)
    w.crew_house = {}
    # a private stream: the world's rng drives the physics and must not be touched
    _assign_employers(w, np.random.default_rng([int(c["seed"]), 0xF1A7]))
    w.hh_cash = np.where(w.hh_active, float(c["hh_start_cash"]), 0.0)
    w.hh_status = np.zeros(N, dtype=np.int64)
    w.hh_overdue_since = np.full(N, -1, dtype=np.int64)
    w.hh_bankruptcies = np.zeros(N, dtype=np.int64)
    w.hh_bills = [[] for _ in range(N)]  # open bills: [id, kind, amount, remaining, creditor, issued_t]
    w.hh_loans = [[] for _ in range(N)]  # active loans: dicts, see _open_loan
    w.hh_loans_repaid = np.zeros(N, dtype=np.int64)
    w.hh_principal = np.zeros(N)
    w.hh_interest = np.zeros(N)
    w.hh_arrears = np.zeros(N)
    w.hh_month = np.zeros((N, 4))  # earned, billed, paid, borrowed in the current month
    w.hh_prev_month = np.zeros((N, 4))
    w.hh_led = np.zeros((N, LEDGER_LEN), dtype=LEDGER_DTYPE)
    w.hh_led_n = np.zeros(N, dtype=np.int64)
    w.hh_notes = [deque(maxlen=30) for _ in range(N)]
    w.hh_hist = np.zeros((N, HIST_DAYS, 2), dtype=np.float32)
    w.hh_hist_t = np.zeros(HIST_DAYS, dtype=np.int64)
    w.hh_hist_n = 0
    w.hh_last_close_day = -1
    w.fin_next_id = 1
    w.fin_ext = {"company": 0.0, "suppliers": 0.0, "ore": 0.0, "bank": 0.0}
    w.fin_flows = {}  # (from, to, what) -> cr this month
    w.fin_flows_prev = {}
    w.fin_flows_total = {}
    w.fin_counts = _zero_counts()
    w.fin_series = []
    w.fin_act = [0.0, 0.0, 0]  # mine activity, water plant activity, ticks since the last day close
    w.sector_reserved = np.zeros(w.S)
    w.colony_reserved = 0.0
    w.mine_closed_until = 0
    w.fin_scenario = None
    w.fin_trace = {}
    for i in np.flatnonzero(w.hh_active):
        _led(w, int(i), K_OPEN, float(w.hh_cash[i]), 0)
    w.fin_baseline = internal_total(w)


def _zero_counts():
    return {"loans": 0, "loaned": 0.0, "interest": 0.0, "repaid": 0, "bankrupt": 0, "overdue": 0}


def _assign_employers(w: World, g):
    """Crew households first (one per service rover), then the reactor and water plant quotas, then services
    as long as their wages fit in the colony payroll, the rest work at the mine."""
    c = w.cfg
    order = [int(i) for i in g.permutation(np.flatnonzero(w.hh_active))]
    nominal = _nominal_wage(w, np.full(w.N, SERVICES))
    cap = c["colony_payroll_day"] * c["services_payroll_share"]
    used = 0.0
    k = 0
    for r in w.rovers:
        i = order[k]
        k += 1
        w.hh_employer[i] = SERVICES
        w.crew_house[str(r.name)] = i
        used += nominal[i]
    for e, name in ((1, "reactor"), (2, "water plant")):
        for _ in range(int(c["employer_houses"].get(name, 0))):
            if k < len(order):
                w.hh_employer[order[k]] = e
                k += 1
    for i in order[k:]:
        if used + nominal[i] <= cap:
            w.hh_employer[i] = SERVICES
            used += nominal[i]
        else:
            w.hh_employer[i] = 0


def _nominal_wage(w: World, employer):
    c = w.cfg
    rate = np.array([c["wage_day"][e] for e in EMPLOYERS])[np.clip(employer, 0, 3)]
    mult = np.where(w.h_type == 3, c["wage_manager_mult"], 1.0)
    return np.where(w.hh_active & (employer >= 0), w.hh_workers * rate * mult, 0.0)


def credit_limit(w: World, i: int):
    c = w.cfg
    monthly = float(_nominal_wage(w, w.hh_employer)[i]) * c["days_per_month"]
    return max(c["credit_limit_min"], c["credit_limit_months"] * monthly)


def internal_total(w: World):
    return float(w.colony_budget) + float(w.sector_budget.sum()) + float(w.hh_cash.sum())


# ---------------------------------------------------------------- money movement


def _move(w: World, acct: str, delta: float):
    kind, _, arg = acct.partition(":")
    if kind == "house":
        w.hh_cash[int(arg)] += delta
    elif kind == "sector":
        w.sector_budget[int(arg)] += delta
    elif kind == "colony":
        w.colony_budget += delta
    else:  # ext: an external counterparty; fin_ext is what it has put into the colony
        w.fin_ext[arg] = w.fin_ext.get(arg, 0.0) - delta


def _group(acct: str):
    return "house" if acct.startswith("house:") else acct


def book(w: World, src: str, dst: str, amount: float, what: str):
    """Journal a movement without touching balances (the caller has moved them)."""
    key = (_group(src), _group(dst), what)
    w.fin_flows[key] = w.fin_flows.get(key, 0.0) + amount
    w.fin_flows_total[key] = w.fin_flows_total.get(key, 0.0) + amount


def transfer(
    w: World,
    src: str,
    dst: str,
    amount: float,
    what: str,
    kind: int = 0,
    ref: int = 0,
    move_src: bool = True,
    move_dst: bool = True,
):
    """Move `amount` from one account to another: one debit, one credit, one journal entry, and a ledger row
    for the household on either side. move_src/move_dst=False when the caller moves that side in bulk."""
    if amount <= 0:
        return
    if move_src:
        _move(w, src, -amount)
    if move_dst:
        _move(w, dst, amount)
    book(w, src, dst, amount, what)
    if kind:
        for acct in (src, dst):
            if acct.startswith("house:"):
                _led(w, int(acct[6:]), kind, amount, ref)


def _debt(w: World, i: int):
    return float(w.hh_principal[i] + w.hh_interest[i] + w.hh_arrears[i])


def _refresh(w: World, i: int):
    loans = w.hh_loans[i]
    w.hh_principal[i] = sum(ln["principal"] for ln in loans)
    w.hh_interest[i] = sum(ln["interest"] for ln in loans)
    w.hh_arrears[i] = sum(b[3] for b in w.hh_bills[i])


def _led(w: World, i: int, kind: int, amount: float, ref: int):
    _refresh(w, i)
    row = w.hh_led[i, w.hh_led_n[i] % LEDGER_LEN]
    row["t"] = w.t
    row["k"] = kind
    row["amt"] = amount
    row["cash"] = w.hh_cash[i]
    row["debt"] = _debt(w, i)
    row["ref"] = ref
    w.hh_led_n[i] += 1


def note(w: World, i: int, text: str):
    """A milestone in the household's finances, shown on the house page."""
    notes = w.hh_notes[i]
    if notes and notes[0][1] == text:
        return
    notes.appendleft((w.t, text))
    w.h_log[i].appendleft((w.t, text))


def _next_id(w: World):
    n = w.fin_next_id
    w.fin_next_id += 1
    return n


# ---------------------------------------------------------------- bills


def issue_bill(w: World, i: int, what: str, amount: float, creditor: str):
    if amount <= 0:
        return None
    bill = [_next_id(w), what, float(amount), float(amount), creditor, w.t]
    w.hh_bills[i].append(bill)
    w.hh_month[i, BILLED] += amount
    _led(w, i, K_BILL, amount, bill[0])
    return bill


def households_bill_repair(w: World, i: int, amount: float, creditor: str, text: str):
    """A repair of house i fronted by `creditor` (a sector or the colony) is billed to the household;
    the Company pays for its vacant houses at once."""
    if not w.hh_active[i]:
        transfer(w, "ext:company", creditor, amount, "repair of company housing")
        if creditor == "colony":
            w.colony_month_income += amount
        else:
            w.month_income[int(creditor[7:])] += amount
        return
    bill = issue_bill(w, i, "repair", amount, creditor)
    note(w, i, f"repair bill #{bill[0]}: {text}, {amount:.0f} cr")
    _trace(w, i, "repair", amount)


def _pay_bill(w: World, i: int, bill, amount: float, pend):
    creditor = bill[4]
    own = creditor == f"sector:{int(w.h_sector[i])}"
    transfer(w, f"house:{i}", creditor, amount, "bill " + bill[1], 0, bill[0], move_dst=not own)
    if own:
        pend[i] += amount  # credited to the sectors with one bincount, as before households had cash
    elif creditor == "colony":
        w.colony_month_income += amount
    elif creditor.startswith("sector:"):
        w.month_income[int(creditor[7:])] += amount
    bill[3] -= amount
    if bill[3] < 1e-9:
        bill[3] = 0.0
    w.hh_month[i, PAID] += amount
    _led(w, i, K_PAY, amount, bill[0])


def _bill_overdue(w: World, bill):
    return bill[3] > EPS and w.t - bill[5] >= w.cfg["bill_grace_days"] * w.cfg["ticks_per_day"]


# ---------------------------------------------------------------- loans


def _open_loan(w: World, i: int, amount: float):
    c = w.cfg
    tpd = c["ticks_per_day"]
    rate = float(c["loan_rate_month"])
    period = int(c["loan_period_days"])
    term = int(c["loan_term_periods"])
    r = rate * period / c["days_per_month"]
    payment = amount * r / (1.0 - (1.0 + r) ** -term) if r > 0 else amount / term
    loan = {
        "id": _next_id(w),
        "amount": amount,
        "principal": amount,
        "interest": 0.0,
        "rate_month": rate,
        "period_days": period,
        "term": term,
        "payment": math.ceil(payment * 100 - 1e-6) / 100,
        "opened_t": w.t,
        "next_due_t": w.t + period * tpd,
        "billed": 0,
        "due": 0.0,
        "due_since": -1,
        "paid": 0.0,
        "interest_total": 0.0,
    }
    w.hh_loans[i].append(loan)
    transfer(w, "ext:bank", f"house:{i}", amount, "loan", K_LOAN, loan["id"])
    w.hh_month[i, BORROWED] += amount
    w.fin_counts["loans"] += 1
    w.fin_counts["loaned"] += amount
    note(
        w,
        i,
        f"loan #{loan['id']}: {amount:.0f} cr at {rate * 100:.1f}% a month, "
        f"{term} x {loan['payment']:.2f} cr every {period} days",
    )
    return loan


def _pay_loan(w: World, i: int, loan, amount: float):
    """Interest first, then principal; any payment counts against the amount due first."""
    to_interest = min(amount, loan["interest"])
    to_principal = min(amount - to_interest, loan["principal"])
    amount = to_interest + to_principal
    if amount <= EPS:
        return
    loan["interest"] -= to_interest
    loan["principal"] -= to_principal
    if loan["principal"] < 1e-9:
        loan["principal"] = 0.0
    if loan["interest"] < 1e-9:
        loan["interest"] = 0.0
    owed = loan["principal"] + loan["interest"]
    loan["due"] = min(max(0.0, loan["due"] - amount), owed)
    if loan["due"] < 1e-9:
        loan["due"] = 0.0
        loan["due_since"] = -1
    loan["paid"] += amount
    transfer(w, f"house:{i}", "ext:bank", amount, "loan payment", K_INST, loan["id"])
    w.hh_month[i, PAID] += amount


def _close_repaid(w: World, i: int):
    loans = w.hh_loans[i]
    done = [ln for ln in loans if ln["principal"] + ln["interest"] <= EPS]
    for ln in done:
        loans.remove(ln)
        w.hh_loans_repaid[i] += 1
        w.fin_counts["repaid"] += 1
        note(
            w,
            i,
            f"loan #{ln['id']} repaid: {ln['amount']:.0f} cr borrowed, "
            f"{ln['interest_total']:.2f} cr interest, {ln['paid']:.2f} cr paid",
        )


def _accrue_interest(w: World, i: int):
    c = w.cfg
    if w.hh_status[i] == BANKRUPT and not c["bankrupt_interest"]:
        return
    for ln in w.hh_loans[i]:
        x = round(ln["principal"] * ln["rate_month"] / c["days_per_month"], 2)
        if x > 0:
            ln["interest"] += x
            ln["interest_total"] += x
            w.hh_month[i, BILLED] += x
            w.fin_counts["interest"] += x
            _led(w, i, K_INTEREST, x, ln["id"])


def _instalments_due(w: World, i: int):
    tpd = w.cfg["ticks_per_day"]
    for ln in w.hh_loans[i]:
        owed = ln["principal"] + ln["interest"]
        if ln["billed"] >= ln["term"]:
            ln["due"] = owed  # past the term everything left is due
        elif w.t >= ln["next_due_t"]:
            ln["billed"] += 1
            ln["next_due_t"] += ln["period_days"] * tpd
            last = ln["billed"] >= ln["term"]
            ln["due"] = owed if last else min(owed, ln["due"] + ln["payment"])
        if ln["due"] > EPS and ln["due_since"] < 0:
            ln["due_since"] = w.t


def _loan_overdue(w: World, ln):
    grace = w.cfg["instalment_grace_days"] * w.cfg["ticks_per_day"]
    return ln["due"] > EPS and ln["due_since"] >= 0 and w.t - ln["due_since"] >= grace


# ---------------------------------------------------------------- the household's day


def _settle(w: World, i: int, pend, loans_first=True):
    if loans_first:
        for ln in w.hh_loans[i]:
            if ln["due"] > EPS and w.hh_cash[i] > EPS:
                _pay_loan(w, i, ln, min(float(w.hh_cash[i]), ln["due"]))
        _close_repaid(w, i)
    bills = w.hh_bills[i]
    paid_any = False
    for b in bills:
        if w.hh_cash[i] <= EPS:
            break
        if b[3] > EPS:
            _pay_bill(w, i, b, min(float(w.hh_cash[i]), b[3]), pend)
            paid_any = True
    if paid_any:
        w.hh_bills[i] = [b for b in bills if b[3] > EPS]


def _borrow(w: World, i: int, pend):
    c = w.cfg
    if w.hh_status[i] == BANKRUPT:
        return
    need = sum(b[3] for b in w.hh_bills[i]) - float(w.hh_cash[i])
    if need <= EPS:
        return
    loans = w.hh_loans[i]
    if any(ln["due"] > EPS for ln in loans):
        return note(w, i, "no new credit: an instalment is unpaid")
    if len(loans) >= c["loan_max_active"]:
        return note(w, i, f"no new credit: already {len(loans)} loans")
    step = c["loan_step"]
    available = credit_limit(w, i) - sum(ln["principal"] for ln in loans)
    amount = max(c["loan_min"], math.ceil(need / step - 1e-9) * step)
    if amount > available:
        amount = math.floor(available / step + 1e-9) * step
    if amount < c["loan_min"]:
        return note(w, i, f"no new credit: limit {credit_limit(w, i):.0f} cr reached")
    _open_loan(w, i, float(amount))
    _settle(w, i, pend, loans_first=False)


def _update_status(w: World, i: int):
    c = w.cfg
    tpd = c["ticks_per_day"]
    _refresh(w, i)
    st = int(w.hh_status[i])
    overdue_bills = [b for b in w.hh_bills[i] if _bill_overdue(w, b)]
    overdue_loans = [ln for ln in w.hh_loans[i] if _loan_overdue(w, ln)]
    if st == BANKRUPT:
        if _debt(w, i) <= 0.005:
            w.hh_status[i] = NORMAL
            w.hh_overdue_since[i] = -1
            note(w, i, "all debts repaid: bankruptcy discharged")
        return
    if st == OVERDUE:
        # cured only when fully current: no unpaid instalment and no open bill at all
        if not w.hh_bills[i] and not any(ln["due"] > EPS for ln in w.hh_loans[i]):
            w.hh_status[i] = NORMAL
            w.hh_overdue_since[i] = -1
            note(w, i, "arrears paid: back to normal")
        elif w.t - w.hh_overdue_since[i] >= c["bankruptcy_overdue_days"] * tpd:
            w.hh_status[i] = BANKRUPT
            w.hh_bankruptcies[i] += 1
            w.fin_counts["bankrupt"] += 1
            days = (w.t - w.hh_overdue_since[i]) // tpd
            text = (
                f"BANKRUPT after {days} days overdue: loans {w.hh_principal[i]:.2f} cr, "
                f"interest {w.hh_interest[i]:.2f} cr, unpaid bills {w.hh_arrears[i]:.2f} cr"
            )
            note(w, i, text)
            w.log("WARN", f"House {i + 1}: household bankrupt ({text[9:]})")
    elif overdue_bills or overdue_loans:
        w.hh_status[i] = OVERDUE
        w.hh_overdue_since[i] = w.t
        w.fin_counts["overdue"] += 1
        what = [f"instalment of loan #{ln['id']} {ln['due']:.2f} cr" for ln in overdue_loans]
        what += [f"bill #{b[0]} ({b[1]}) {b[3]:.2f} cr" for b in overdue_bills[:3]]
        note(w, i, "payment overdue: " + ", ".join(what))


def _spend(w: World, i: int):
    c = w.cfg
    st = w.hh_status[i]
    loans = w.hh_loans[i]
    if st == BANKRUPT:
        keep = 0.0  # every credit left goes to the bank
    elif st == NORMAL and not w.hh_bills[i]:
        keep = c["loan_prepay_keep"] if loans else c["hh_cash_reserve"]
    else:
        return
    excess = float(w.hh_cash[i]) - keep
    if excess <= 0.005:
        return
    if loans:
        for ln in loans:
            if excess <= 0.005:
                break
            before = float(w.hh_cash[i])
            _pay_loan(w, i, ln, min(excess, ln["principal"] + ln["interest"]))
            excess -= before - float(w.hh_cash[i])
        _close_repaid(w, i)
    elif st == NORMAL:
        buy = round(excess * c["hh_discretionary_frac"], 2)
        if buy > 0:
            transfer(w, f"house:{i}", "colony", buy, "commissary purchases", K_BUY)
            w.colony_month_income += buy
            w.hh_month[i, PAID] += buy


def _wages(w: World):
    c = w.cfg
    mine, water, n = w.fin_act
    n = max(1, n)
    idle = c["idle_pay_frac"]
    act = np.array(
        [
            idle + (1 - idle) * min(1.0, mine / n),
            1.0,
            idle + (1 - idle) * min(1.0, water / n),
            1.0,
        ]
    )
    pay = _nominal_wage(w, w.hh_employer) * act[np.clip(w.hh_employer, 0, 3)]
    return np.round(pay, 2)


def households_day_close(w: World, bill):
    """The households' day: see the module docstring. `bill` is today's utility bill of every house.
    Credits the sectors with what reached them and returns the wages owed by the colony payroll."""
    c = w.cfg
    S = w.S
    day = w.t // c["ticks_per_day"]
    pend = np.zeros(w.N)
    services = 0.0
    if day == w.hh_last_close_day:  # a day is closed once, whatever happens to w.t
        return services
    w.hh_last_close_day = day
    wages = _wages(w)
    w.fin_act = [0.0, 0.0, 0]
    for i in range(w.N):
        amount = float(bill[i])
        if not w.hh_active[i]:
            if amount > 0:  # company housing
                transfer(w, "ext:company", f"sector:{int(w.h_sector[i])}", amount, "bills of company housing", move_dst=False)
                pend[i] += amount
            continue
        _accrue_interest(w, i)
        if wages[i] > 0:
            if w.hh_employer[i] == SERVICES:
                transfer(w, "colony", f"house:{i}", float(wages[i]), "wage", K_WAGE, SERVICES, move_src=False)
                services += float(wages[i])
            else:
                transfer(w, "ext:company", f"house:{i}", float(wages[i]), "wage", K_WAGE, int(w.hh_employer[i]))
            w.hh_month[i, EARNED] += float(wages[i])
        issue_bill(w, i, "utilities", amount, f"sector:{int(w.h_sector[i])}")
        _trace(w, i, "day", (float(wages[i]), amount))
        _instalments_due(w, i)
        _settle(w, i, pend)
        _borrow(w, i, pend)
        _update_status(w, i)
        _spend(w, i)
        _refresh(w, i)
    income = np.bincount(w.h_sector, weights=pend, minlength=S)
    w.sector_budget += income
    w.month_income += income
    _sample(w)
    return services


def households_month_close(w: World):
    """Monthly fees (sewage, internet) are billed and paid from cash; returns what reached each sector."""
    c = w.cfg
    fee = float(c["sewage_fee"] + c["internet_fee"])
    pend = np.zeros(w.N)
    for i in range(w.N):
        s = f"sector:{int(w.h_sector[i])}"
        if not w.hh_active[i]:
            transfer(w, "ext:company", s, fee, "fees of company housing", move_dst=False)
            pend[i] += fee
            continue
        issue_bill(w, i, "fees", fee, s)
        _trace(w, i, "fees", fee)
        _settle(w, i, pend, loans_first=False)
        _refresh(w, i)
    income = np.bincount(w.h_sector, weights=pend, minlength=w.S)
    w.sector_budget += income
    w.month_income += income
    return income


def households_month_roll(w: World):
    """Month report of the households, then start a new month."""
    a = w.hh_active
    m = w.hh_month
    out = {
        "earned": round(float(m[:, EARNED].sum()), 1),
        "billed": round(float(m[:, BILLED].sum()), 1),
        "paid": round(float(m[:, PAID].sum()), 1),
        "borrowed": round(float(m[:, BORROWED].sum()), 1),
        **summary(w),
        "new_loans": w.fin_counts["loans"],
        "loans_repaid": w.fin_counts["repaid"],
        "interest_accrued": round(w.fin_counts["interest"], 1),
        "fell_overdue": w.fin_counts["overdue"],
        "went_bankrupt": w.fin_counts["bankrupt"],
        "households": int(a.sum()),
    }
    w.hh_prev_month = w.hh_month.copy()
    w.hh_month[:] = 0.0
    w.fin_flows_prev = w.fin_flows
    w.fin_flows = {}
    w.fin_counts = _zero_counts()
    return out


def summary(w: World):
    a = w.hh_active
    debt = w.hh_principal + w.hh_interest + w.hh_arrears
    return {
        "cash": round(float(w.hh_cash[a].sum()), 1),
        "debt": round(float(debt.sum()), 1),
        "principal": round(float(w.hh_principal.sum()), 1),
        "interest": round(float(w.hh_interest.sum()), 1),
        "arrears": round(float(w.hh_arrears.sum()), 1),
        "debtors": int((debt > 0.005).sum()),
        "borrowers": int((w.hh_principal + w.hh_interest > 0.005).sum()),
        "overdue": int((w.hh_status == OVERDUE).sum()),
        "bankrupt": int((w.hh_status == BANKRUPT).sum()),
    }


def _sample(w: World):
    k = w.hh_hist_n % HIST_DAYS
    w.hh_hist[:, k, 0] = w.hh_cash
    w.hh_hist[:, k, 1] = w.hh_principal + w.hh_interest + w.hh_arrears
    w.hh_hist_t[k] = w.t
    w.hh_hist_n += 1
    s = summary(w)
    w.fin_series.append(
        (
            w.t,
            s["cash"],
            s["principal"],
            s["interest"],
            s["arrears"],
            s["debtors"],
            s["overdue"],
            s["bankrupt"],
            round(float(w.colony_budget), 1),
            round(float(w.sector_budget.sum()), 1),
        )
    )
    if len(w.fin_series) > SERIES_DAYS:
        del w.fin_series[: len(w.fin_series) - SERIES_DAYS]


SERIES_KEYS = ["t", "cash", "principal", "interest", "arrears", "debtors", "overdue", "bankrupt", "colony", "sectors"]


def _trace(w: World, i: int, what: str, value):
    """Inputs of the scenario houses, for the acceptance comparison with finance_reference."""
    if i in w.fin_trace:
        w.fin_trace[i].append((w.t, what, value))


def finance_tick(w: World):
    """Per tick: how much of the day the employers worked; scenario events; the mine reopening."""
    w.fin_act[0] += w.mine_frac
    w.fin_act[1] += 1.0 if w.water_plant_ok else 0.0
    w.fin_act[2] += 1
    if w.mine_closed_until and w.t == w.mine_closed_until:
        w.log("INFO", "Mine back in operation: miners return to full pay")
    if w.fin_scenario:
        from hadleys.scenarios import scenario_step

        scenario_step(w)


def employer_name(w: World, i: int):
    e = int(w.hh_employer[i])
    return EMPLOYERS[e] if e >= 0 else ""


def time_label(w: World, t: int):
    c = w.cfg
    tpd = c["ticks_per_day"]
    month = t // (tpd * c["days_per_month"]) + 1
    day = t // tpd % c["days_per_month"] + 1
    return f"M{month} D{day:02d} {t // 60 % 24:02d}:{t % 60:02d}"


def next_payment(w: World, i: int):
    """What the household has to pay next: an overdue amount now, else the next instalment."""
    due_now = sum(ln["due"] for ln in w.hh_loans[i]) + sum(b[3] for b in w.hh_bills[i])
    if due_now > 0.005:
        return {"t": w.t, "time": "now", "amount": round(due_now, 2), "what": "unpaid instalments and bills"}
    best = None
    for ln in w.hh_loans[i]:
        amount = min(ln["payment"], ln["principal"] + ln["interest"])
        if ln["billed"] + 1 >= ln["term"]:
            amount = ln["principal"] + ln["interest"]
        if best is None or ln["next_due_t"] < best["t"]:
            best = {
                "t": int(ln["next_due_t"]),
                "time": time_label(w, int(ln["next_due_t"])),
                "amount": round(amount, 2),
                "what": f"instalment {ln['billed'] + 1} of {ln['term']}, loan #{ln['id']}",
            }
    return best


def house_finance(w: World, i: int, rows: int = 60):
    """The finance block of /house.json."""
    c = w.cfg
    tpd = c["ticks_per_day"]
    n = int(w.hh_led_n[i])
    led = []
    for k in range(max(0, n - rows), n):
        r = w.hh_led[i, k % LEDGER_LEN]
        name, cash_sign, debt_sign = LEDGER_KINDS.get(int(r["k"]), ("?", 0, 0))
        led.append(
            {
                "t": int(r["t"]),
                "time": time_label(w, int(r["t"])),
                "kind": name,
                "amount": round(float(r["amt"]), 2),
                "cash_sign": cash_sign,
                "debt_sign": debt_sign,
                "cash": round(float(r["cash"]), 2),
                "debt": round(float(r["debt"]), 2),
                "ref": int(r["ref"]),
            }
        )
    led.reverse()
    h = min(w.hh_hist_n, HIST_DAYS)
    order = [(w.hh_hist_n - h + k) % HIST_DAYS for k in range(h)]
    st = int(w.hh_status[i])
    label = ""
    if w.fin_scenario:
        label = w.fin_scenario.get("labels", {}).get(str(i), "")
    return {
        "active": bool(w.hh_active[i]),
        "label": label,
        "employer": employer_name(w, i),
        "workers": int(w.hh_workers[i]),
        "wage_day": round(float(_nominal_wage(w, w.hh_employer)[i]), 2),
        "crew": next((k for k, v in w.crew_house.items() if v == i), ""),
        "cash": round(float(w.hh_cash[i]), 2),
        "status": STATUS[st],
        "overdue_days": (w.t - int(w.hh_overdue_since[i])) // tpd if w.hh_overdue_since[i] >= 0 else 0,
        "bankruptcies": int(w.hh_bankruptcies[i]),
        "month": [round(float(x), 2) for x in w.hh_month[i]],
        "prev_month": [round(float(x), 2) for x in w.hh_prev_month[i]],
        "arrears": round(float(w.hh_arrears[i]), 2),
        "principal": round(float(w.hh_principal[i]), 2),
        "interest": round(float(w.hh_interest[i]), 2),
        "debt": round(_debt(w, i), 2),
        "credit_limit": round(credit_limit(w, i), 2) if w.hh_active[i] else 0.0,
        "next_payment": next_payment(w, i),
        "bills": [
            {
                "id": b[0],
                "kind": b[1],
                "amount": round(b[2], 2),
                "remaining": round(b[3], 2),
                "creditor": b[4],
                "issued": time_label(w, b[5]),
                "overdue": _bill_overdue(w, b),
            }
            for b in w.hh_bills[i][:12]
        ],
        "bills_open": len(w.hh_bills[i]),
        "loans": [
            {
                "id": ln["id"],
                "amount": round(ln["amount"], 2),
                "principal": round(ln["principal"], 2),
                "interest": round(ln["interest"], 2),
                "rate_month": ln["rate_month"],
                "payment": ln["payment"],
                "instalment": f"{ln['billed']} of {ln['term']}",
                "next_due": time_label(w, int(ln["next_due_t"])),
                "due": round(ln["due"], 2),
                "overdue": _loan_overdue(w, ln),
                "opened": time_label(w, int(ln["opened_t"])),
            }
            for ln in w.hh_loans[i]
        ],
        "loans_repaid": int(w.hh_loans_repaid[i]),
        "hist_t": [int(w.hh_hist_t[k]) for k in order],
        "hist_cash": [round(float(w.hh_hist[i, k, 0]), 1) for k in order],
        "hist_debt": [round(float(w.hh_hist[i, k, 1]), 1) for k in order],
        "ledger": led,
        "notes": [{"t": t, "time": time_label(w, t), "text": x} for t, x in list(w.hh_notes[i])],
    }


RULES = [
    ("hh_start_cash", "opening cash of an occupied house, cr"),
    ("wage_day", "wage per worker per day by employer, cr"),
    ("wage_manager_mult", "manager houses earn this multiple"),
    ("idle_pay_frac", "share of the wage paid while the mine or the water plant stands"),
    ("crew_pay_per_repair_tick", "crew household's pay per minute of repair, cr (out of the repair cost)"),
    ("crew_pay_per_trip", "driver household's pay per full waste or sludge load, cr"),
    ("tariff_kwh", "energy, cr per kWh, billed daily"),
    ("tariff_water_m3", "water, cr per m3, billed daily"),
    ("sewage_fee", "sewage fee, cr per month"),
    ("internet_fee", "internet fee, cr per month"),
    ("hh_cash_reserve", "above this cash a household without debts buys at the commissary"),
    ("hh_discretionary_frac", "share of the cash above the reserve spent per day"),
    ("bill_grace_days", "an unpaid bill is overdue after, days"),
    ("loan_rate_month", "loan interest per 30 days, accrued daily on the principal"),
    ("loan_period_days", "days between instalments"),
    ("loan_term_periods", "number of instalments (annuity)"),
    ("loan_min", "smallest loan, cr"),
    ("loan_step", "loans are rounded up to, cr"),
    ("credit_limit_months", "credit limit in months of the nominal wage"),
    ("credit_limit_min", "credit limit at least, cr"),
    ("loan_max_active", "loans at the same time at most"),
    ("loan_prepay_keep", "a household with loans prepays with the cash above, cr"),
    ("instalment_grace_days", "an unpaid instalment is overdue after, days"),
    ("bankruptcy_overdue_days", "continuously overdue this long: bankrupt, days"),
    ("bankrupt_interest", "interest keeps accruing after bankruptcy"),
    ("bankrupt_eco_heating", "a bankrupt household heats only to eco_c"),
]


def finance_snapshot(w: World):
    """/finance.json: rules, colony-wide summary and series, households in trouble, money flows."""
    c = w.cfg
    debt = w.hh_principal + w.hh_interest + w.hh_arrears
    trouble = [int(i) for i in np.argsort(-debt, kind="stable") if debt[i] > 0.005][:40]
    labels = (w.fin_scenario or {}).get("labels", {})

    def flows(d):
        return [
            {"from": a, "to": b, "what": k, "amount": round(v, 2)}
            for (a, b, k), v in sorted(d.items(), key=lambda kv: -kv[1])
        ]

    total = internal_total(w)
    return {
        "t": w.t,
        "time": w.time_str(),
        "summary": {**summary(w), "households": int(w.hh_active.sum()), "vacant": int((~w.hh_active).sum())},
        "rules": [{"key": k, "value": c[k], "meaning": m} for k, m in RULES],
        "series_keys": SERIES_KEYS,
        "series": w.fin_series[-SERIES_DAYS:],
        "trouble": [
            {
                "house": i + 1,
                "sector": int(w.h_sector[i]) + 1,
                "employer": employer_name(w, i),
                "status": STATUS[int(w.hh_status[i])],
                "cash": round(float(w.hh_cash[i]), 2),
                "principal": round(float(w.hh_principal[i]), 2),
                "interest": round(float(w.hh_interest[i]), 2),
                "arrears": round(float(w.hh_arrears[i]), 2),
                "label": labels.get(str(i), ""),
            }
            for i in trouble
        ],
        "scenario": [
            {
                "house": int(i) + 1,
                "label": lab,
                "status": STATUS[int(w.hh_status[int(i)])],
                "cash": round(float(w.hh_cash[int(i)]), 2),
                "debt": round(float(debt[int(i)]), 2),
            }
            for i, lab in sorted(labels.items(), key=lambda kv: kv[1])
        ],
        "mine_closed_until": time_label(w, w.mine_closed_until) if w.mine_closed_until > w.t else "",
        "flows_month": flows(w.fin_flows),
        "flows_prev_month": flows(w.fin_flows_prev),
        "external": {k: round(v, 2) for k, v in w.fin_ext.items()},
        "check": {
            "internal_total": round(total, 2),
            "baseline": round(w.fin_baseline, 2),
            "external_net": round(sum(w.fin_ext.values()), 2),
            "unexplained": round(total - w.fin_baseline - sum(w.fin_ext.values()), 6),
        },
    }
