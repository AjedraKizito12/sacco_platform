# tests/modules/credit/test_schedule.py
"""Unit tests for _schedule.py — pure math, no database required."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.credit.services._schedule import compute_schedule

# ── Flat method ───────────────────────────────────────────────────────────────


def test_flat_monthly_12_principal_sum() -> None:
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


def test_flat_monthly_12_interest_sum() -> None:
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


def test_flat_monthly_equal_installments() -> None:
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
    assert len(set(interests)) == 1  # all equal


def test_flat_quarterly_4_periods() -> None:
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


def test_flat_single_period() -> None:
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


def test_reducing_monthly_12_principal_sum() -> None:
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


def test_reducing_monthly_interest_front_loaded() -> None:
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


def test_reducing_zero_rate() -> None:
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


def test_due_dates_monthly() -> None:
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


def test_due_dates_quarterly() -> None:
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


def test_due_dates_weekly() -> None:
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


def test_due_dates_biweekly() -> None:
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


def test_installment_fields_present() -> None:
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


def test_period_numbers_start_at_1() -> None:
    """Period numbers start at 1, not 0."""
    schedule = compute_schedule(
        principal=Decimal("60000"),
        annual_interest_rate=Decimal("12"),
        interest_method="flat",
        repayment_frequency="monthly",
        term_periods=6,
        disbursement_date=date(2026, 1, 15),
    )
    assert [i.period_number for i in schedule] == [1, 2, 3, 4, 5, 6]
