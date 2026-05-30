# Sub-plan 05 — Repayment Schedule Generation

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Implement `_schedule.py` — pure functions that compute an amortisation schedule
from loan terms. No database access. No side effects. These helpers are called by
`LoanDisbursementService` in sub-plan 04 and tested independently.

**Architecture:** A single public function `compute_schedule(...)` returns a list of
`ScheduledInstallment` dataclasses. Flat method uses equal principal+interest per period.
Reducing balance uses the standard annuity formula. Due dates are computed from
`disbursement_date` using calendar arithmetic (monthdate-add for monthly/quarterly,
7-day multiples for weekly/biweekly).

**Tech Stack:** Python `decimal.Decimal`, `datetime.date`, `dateutil.relativedelta`

---

## Required Reading

- Sub-plan 01 (completed — models must exist)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §5 (Interest Calculation)

---

## File Map

```
New
  app/modules/credit/services/_schedule.py    compute_schedule + ScheduledInstallment
  tests/modules/credit/test_schedule.py       unit tests (no DB)
```

No modifications to existing files.

---

## Task 1 — Schedule Helpers (TDD)

**Files:**
- Create: `tests/modules/credit/test_schedule.py`
- Create: `app/modules/credit/services/_schedule.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/credit/test_schedule.py`:

```python
# tests/modules/credit/test_schedule.py
"""Unit tests for _schedule.py — pure math, no database required."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.credit.services._schedule import ScheduledInstallment, compute_schedule

# ── Flat method ───────────────────────────────────────────────────────────────


def test_flat_monthly_12_principal_sum():
    """SUM(principal_due) == principal for flat monthly 12-period loan."""
    schedule = compute_schedule(
        principal=Decimal("120000"),
        annual_interest_rate=Decimal("12"),
        interest_method="flat",
        repayment_frequency="monthly",
        term_periods=12,
        disbursement_date=date(2026, 1, 15),
    )
    assert len(schedule) == 12
    total_principal = sum(i.principal_due for i in schedule)
    assert total_principal == Decimal("120000")


def test_flat_monthly_12_interest_sum():
    """SUM(interest_due) == principal × rate × 1 for flat method (1 year)."""
    schedule = compute_schedule(
        principal=Decimal("120000"),
        annual_interest_rate=Decimal("12"),
        interest_method="flat",
        repayment_frequency="monthly",
        term_periods=12,
        disbursement_date=date(2026, 1, 15),
    )
    # total_interest = 120000 × 0.12 × (12/12) = 14400
    total_interest = sum(i.interest_due for i in schedule)
    assert total_interest == Decimal("14400")


def test_flat_monthly_equal_installments():
    """All installments have the same principal_due and interest_due for flat."""
    schedule = compute_schedule(
        principal=Decimal("120000"),
        annual_interest_rate=Decimal("12"),
        interest_method="flat",
        repayment_frequency="monthly",
        term_periods=12,
        disbursement_date=date(2026, 1, 15),
    )
    principals = [i.principal_due for i in schedule]
    interests = [i.interest_due for i in schedule]
    assert len(set(principals)) == 1  # all equal
    assert len(set(interests)) == 1   # all equal


def test_flat_quarterly_4_periods():
    """Flat quarterly: interest = principal × rate × (4/4) = principal × rate × 1."""
    schedule = compute_schedule(
        principal=Decimal("100000"),
        annual_interest_rate=Decimal("20"),
        interest_method="flat",
        repayment_frequency="quarterly",
        term_periods=4,
        disbursement_date=date(2026, 1, 1),
    )
    assert len(schedule) == 4
    total_interest = sum(i.interest_due for i in schedule)
    # 100000 × 0.20 × (4/4) = 20000
    assert total_interest == Decimal("20000")


def test_flat_single_period():
    """Single installment (lump-sum style via term_periods=1, monthly frequency)."""
    schedule = compute_schedule(
        principal=Decimal("50000"),
        annual_interest_rate=Decimal("24"),
        interest_method="flat",
        repayment_frequency="monthly",
        term_periods=1,
        disbursement_date=date(2026, 3, 1),
    )
    assert len(schedule) == 1
    # interest = 50000 × 0.24 × (1/12) = 1000
    assert schedule[0].interest_due == Decimal("1000")
    assert schedule[0].principal_due == Decimal("50000")
    assert schedule[0].period_number == 1


# ── Reducing balance method ───────────────────────────────────────────────────


def test_reducing_monthly_12_principal_sum():
    """SUM(principal_due) == principal for reducing balance (within 1-unit rounding)."""
    schedule = compute_schedule(
        principal=Decimal("120000"),
        annual_interest_rate=Decimal("12"),
        interest_method="reducing_balance",
        repayment_frequency="monthly",
        term_periods=12,
        disbursement_date=date(2026, 1, 15),
    )
    assert len(schedule) == 12
    total_principal = sum(i.principal_due for i in schedule)
    # Allow ±1 minor unit rounding tolerance (last installment absorbs rounding)
    assert abs(total_principal - Decimal("120000")) <= Decimal("1")


def test_reducing_monthly_interest_front_loaded():
    """Reducing balance: earlier periods have higher interest than later ones."""
    schedule = compute_schedule(
        principal=Decimal("120000"),
        annual_interest_rate=Decimal("18"),
        interest_method="reducing_balance",
        repayment_frequency="monthly",
        term_periods=12,
        disbursement_date=date(2026, 1, 15),
    )
    assert schedule[0].interest_due > schedule[-1].interest_due


def test_reducing_zero_rate():
    """0% rate: all interest_due == 0, installments are pure principal splits."""
    schedule = compute_schedule(
        principal=Decimal("120000"),
        annual_interest_rate=Decimal("0"),
        interest_method="reducing_balance",
        repayment_frequency="monthly",
        term_periods=12,
        disbursement_date=date(2026, 1, 15),
    )
    for inst in schedule:
        assert inst.interest_due == Decimal("0")
    total_principal = sum(i.principal_due for i in schedule)
    assert abs(total_principal - Decimal("120000")) <= Decimal("1")


# ── Due dates ─────────────────────────────────────────────────────────────────


def test_due_dates_monthly():
    """Monthly schedule: each due date is one calendar month after previous."""
    schedule = compute_schedule(
        principal=Decimal("60000"),
        annual_interest_rate=Decimal("12"),
        interest_method="flat",
        repayment_frequency="monthly",
        term_periods=3,
        disbursement_date=date(2026, 1, 15),
    )
    assert schedule[0].due_date == date(2026, 2, 15)
    assert schedule[1].due_date == date(2026, 3, 15)
    assert schedule[2].due_date == date(2026, 4, 15)


def test_due_dates_quarterly():
    """Quarterly schedule: each due date is 3 calendar months after previous."""
    schedule = compute_schedule(
        principal=Decimal("60000"),
        annual_interest_rate=Decimal("12"),
        interest_method="flat",
        repayment_frequency="quarterly",
        term_periods=2,
        disbursement_date=date(2026, 1, 15),
    )
    assert schedule[0].due_date == date(2026, 4, 15)
    assert schedule[1].due_date == date(2026, 7, 15)


def test_due_dates_weekly():
    """Weekly schedule: each due date is 7 days after previous."""
    schedule = compute_schedule(
        principal=Decimal("14000"),
        annual_interest_rate=Decimal("0"),
        interest_method="flat",
        repayment_frequency="weekly",
        term_periods=4,
        disbursement_date=date(2026, 1, 5),
    )
    assert schedule[0].due_date == date(2026, 1, 12)
    assert schedule[1].due_date == date(2026, 1, 19)
    assert schedule[2].due_date == date(2026, 1, 26)
    assert schedule[3].due_date == date(2026, 2, 2)


def test_due_dates_biweekly():
    """Biweekly schedule: each due date is 14 days after previous."""
    schedule = compute_schedule(
        principal=Decimal("28000"),
        annual_interest_rate=Decimal("0"),
        interest_method="flat",
        repayment_frequency="biweekly",
        term_periods=2,
        disbursement_date=date(2026, 1, 1),
    )
    assert schedule[0].due_date == date(2026, 1, 15)
    assert schedule[1].due_date == date(2026, 1, 29)


# ── Data structure ────────────────────────────────────────────────────────────


def test_installment_fields_present():
    """Each ScheduledInstallment has required fields."""
    schedule = compute_schedule(
        principal=Decimal("60000"),
        annual_interest_rate=Decimal("12"),
        interest_method="flat",
        repayment_frequency="monthly",
        term_periods=3,
        disbursement_date=date(2026, 1, 15),
    )
    for i, inst in enumerate(schedule, 1):
        assert inst.period_number == i
        assert inst.due_date is not None
        assert inst.principal_due >= Decimal("0")
        assert inst.interest_due >= Decimal("0")
        assert inst.total_due == inst.principal_due + inst.interest_due


def test_period_numbers_start_at_1():
    schedule = compute_schedule(
        principal=Decimal("60000"),
        annual_interest_rate=Decimal("12"),
        interest_method="flat",
        repayment_frequency="monthly",
        term_periods=6,
        disbursement_date=date(2026, 1, 15),
    )
    assert [i.period_number for i in schedule] == [1, 2, 3, 4, 5, 6]
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_schedule.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.modules.credit.services._schedule'`

- [ ] **Step 3: Create `app/modules/credit/services/_schedule.py`**

```python
# app/modules/credit/services/_schedule.py
"""Pure amortisation schedule helpers. No database access, no side effects.

Public interface:
    compute_schedule(...) -> list[ScheduledInstallment]

Called by LoanDisbursementService at disbursement time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

_PERIODS_PER_YEAR: dict[str, int] = {
    "weekly": 52,
    "biweekly": 26,
    "monthly": 12,
    "quarterly": 4,
}

_PERIOD_DELTA: dict[str, relativedelta | timedelta] = {
    "weekly": timedelta(weeks=1),
    "biweekly": timedelta(weeks=2),
    "monthly": relativedelta(months=1),
    "quarterly": relativedelta(months=3),
}

_QUANTIZE = Decimal("0.0001")  # 4 decimal places — matches DECIMAL(19,4)


@dataclass(frozen=True)
class ScheduledInstallment:
    period_number: int
    due_date: date
    principal_due: Decimal
    interest_due: Decimal
    total_due: Decimal


def compute_schedule(
    *,
    principal: Decimal,
    annual_interest_rate: Decimal,
    interest_method: str,
    repayment_frequency: str,
    term_periods: int,
    disbursement_date: date,
) -> list[ScheduledInstallment]:
    """Compute a full amortisation schedule.

    Args:
        principal: Loan principal amount (positive).
        annual_interest_rate: Annual rate as percentage (e.g. 18.0 = 18%).
        interest_method: 'flat' or 'reducing_balance'.
        repayment_frequency: 'weekly' | 'biweekly' | 'monthly' | 'quarterly'.
        term_periods: Number of repayment periods (>= 1).
        disbursement_date: Date of disbursement; first due date is one period later.

    Returns:
        List of ScheduledInstallment, length == term_periods, period_number 1-based.
    """
    if interest_method == "flat":
        return _flat_schedule(
            principal=principal,
            annual_interest_rate=annual_interest_rate,
            repayment_frequency=repayment_frequency,
            term_periods=term_periods,
            disbursement_date=disbursement_date,
        )
    elif interest_method == "reducing_balance":
        return _reducing_schedule(
            principal=principal,
            annual_interest_rate=annual_interest_rate,
            repayment_frequency=repayment_frequency,
            term_periods=term_periods,
            disbursement_date=disbursement_date,
        )
    else:
        raise ValueError(f"Unknown interest_method: '{interest_method}'")


def _due_dates(
    disbursement_date: date, repayment_frequency: str, term_periods: int
) -> list[date]:
    delta = _PERIOD_DELTA[repayment_frequency]
    dates = []
    current = disbursement_date
    for _ in range(term_periods):
        current = current + delta
        dates.append(current)
    return dates


def _flat_schedule(
    *,
    principal: Decimal,
    annual_interest_rate: Decimal,
    repayment_frequency: str,
    term_periods: int,
    disbursement_date: date,
) -> list[ScheduledInstallment]:
    periods_per_year = Decimal(_PERIODS_PER_YEAR[repayment_frequency])
    rate_decimal = annual_interest_rate / Decimal("100")
    total_interest = (
        principal * rate_decimal * (Decimal(term_periods) / periods_per_year)
    ).quantize(_QUANTIZE, rounding=ROUND_HALF_UP)

    interest_per_period = (total_interest / Decimal(term_periods)).quantize(
        _QUANTIZE, rounding=ROUND_HALF_UP
    )
    principal_per_period = (principal / Decimal(term_periods)).quantize(
        _QUANTIZE, rounding=ROUND_HALF_UP
    )

    # Last-period adjustment to absorb rounding residual.
    interest_residual = total_interest - interest_per_period * Decimal(term_periods - 1)
    principal_residual = principal - principal_per_period * Decimal(term_periods - 1)

    dates = _due_dates(disbursement_date, repayment_frequency, term_periods)
    schedule = []
    for i in range(term_periods):
        p = principal_per_period if i < term_periods - 1 else principal_residual
        ir = interest_per_period if i < term_periods - 1 else interest_residual
        schedule.append(
            ScheduledInstallment(
                period_number=i + 1,
                due_date=dates[i],
                principal_due=p,
                interest_due=ir,
                total_due=p + ir,
            )
        )
    return schedule


def _reducing_schedule(
    *,
    principal: Decimal,
    annual_interest_rate: Decimal,
    repayment_frequency: str,
    term_periods: int,
    disbursement_date: date,
) -> list[ScheduledInstallment]:
    periods_per_year = Decimal(_PERIODS_PER_YEAR[repayment_frequency])
    period_rate = (annual_interest_rate / Decimal("100")) / periods_per_year

    if period_rate == Decimal("0"):
        # 0% rate: equal principal splits, zero interest.
        principal_per_period = (principal / Decimal(term_periods)).quantize(
            _QUANTIZE, rounding=ROUND_HALF_UP
        )
        principal_residual = principal - principal_per_period * Decimal(term_periods - 1)
        dates = _due_dates(disbursement_date, repayment_frequency, term_periods)
        return [
            ScheduledInstallment(
                period_number=i + 1,
                due_date=dates[i],
                principal_due=(principal_per_period if i < term_periods - 1 else principal_residual),
                interest_due=Decimal("0"),
                total_due=(principal_per_period if i < term_periods - 1 else principal_residual),
            )
            for i in range(term_periods)
        ]

    # Standard annuity formula: A = P × r / (1 - (1+r)^-n)
    n = term_periods
    r = period_rate
    annuity = (principal * r / (1 - (1 + r) ** (-n))).quantize(
        _QUANTIZE, rounding=ROUND_HALF_UP
    )

    dates = _due_dates(disbursement_date, repayment_frequency, term_periods)
    schedule = []
    outstanding = principal

    for i in range(term_periods):
        interest_i = (outstanding * r).quantize(_QUANTIZE, rounding=ROUND_HALF_UP)
        if i < term_periods - 1:
            principal_i = (annuity - interest_i).quantize(_QUANTIZE, rounding=ROUND_HALF_UP)
        else:
            # Last period: absorb accumulated rounding — pay remaining principal.
            principal_i = outstanding.quantize(_QUANTIZE, rounding=ROUND_HALF_UP)
        outstanding = outstanding - principal_i
        schedule.append(
            ScheduledInstallment(
                period_number=i + 1,
                due_date=dates[i],
                principal_due=principal_i,
                interest_due=interest_i,
                total_due=principal_i + interest_i,
            )
        )
    return schedule
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/modules/credit/test_schedule.py -v
```

Expected: all 14 tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/services/_schedule.py tests/modules/credit/test_schedule.py
git commit -m "feat(credit): compute_schedule — flat + reducing balance amortisation helpers"
```

---

## Verification Criteria

```bash
# 1. All schedule unit tests pass (no DB required)
pytest tests/modules/credit/test_schedule.py -v

# 2. Import clean
python -c "from app.modules.credit.services._schedule import compute_schedule, ScheduledInstallment; print('OK')"

# 3. No regressions
pytest -x -q
```

All commands must exit 0. Confirm specifically:
- Flat monthly 12-period: `SUM(principal_due) == 120000`, `SUM(interest_due) == 14400`
- Flat quarterly 4-period: `SUM(interest_due) == 20000`
- Reducing balance: `SUM(principal_due) within ±1` of principal
- Zero-rate reducing: all `interest_due == 0`
- Due dates: monthly = 1-month gap, quarterly = 3-month gap, weekly = 7-day gap
