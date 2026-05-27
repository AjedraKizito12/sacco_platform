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

_PERIODS_PER_YEAR: dict[str, int] = {
    "weekly": 52,
    "biweekly": 26,
    "monthly": 12,
    "quarterly": 4,
}

_QUANTIZE = Decimal("0.0001")  # 4 decimal places — matches DECIMAL(19,4)


@dataclass(frozen=True)
class ScheduledInstallment:
    period_number: int
    due_date: date
    principal_due: Decimal
    interest_due: Decimal
    total_due: Decimal


def _add_months(d: date, months: int) -> date:
    """Add months to a date, preserving day-of-month where possible."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in a given month."""
    if month == 2:
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            return 29
        return 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


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
    """Generate due dates for each period."""
    dates = []
    current = disbursement_date

    for _ in range(term_periods):
        if repayment_frequency == "weekly":
            current = current + timedelta(weeks=1)
        elif repayment_frequency == "biweekly":
            current = current + timedelta(weeks=2)
        elif repayment_frequency == "monthly":
            current = _add_months(current, 1)
        elif repayment_frequency == "quarterly":
            current = _add_months(current, 3)
        else:
            raise ValueError(f"Unknown repayment_frequency: '{repayment_frequency}'")
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
    """Compute flat-rate amortisation schedule."""
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
    """Compute reducing-balance amortisation schedule."""
    periods_per_year = Decimal(_PERIODS_PER_YEAR[repayment_frequency])
    period_rate = (annual_interest_rate / Decimal("100")) / periods_per_year

    if period_rate == Decimal("0"):
        # 0% rate: equal principal splits, zero interest.
        principal_per_period = (principal / Decimal(term_periods)).quantize(
            _QUANTIZE, rounding=ROUND_HALF_UP
        )
        principal_residual = principal - principal_per_period * Decimal(
            term_periods - 1
        )
        dates = _due_dates(disbursement_date, repayment_frequency, term_periods)
        return [
            ScheduledInstallment(
                period_number=i + 1,
                due_date=dates[i],
                principal_due=(
                    principal_per_period if i < term_periods - 1 else principal_residual
                ),
                interest_due=Decimal("0"),
                total_due=(
                    principal_per_period if i < term_periods - 1 else principal_residual
                ),
            )
            for i in range(term_periods)
        ]

    # Standard annuity formula: A = P × r / (1 - (1+r)^-n)
    n = Decimal(term_periods)
    r = period_rate
    one_plus_r = 1 + r
    # (1+r)^-n = 1 / (1+r)^n
    one_plus_r_power_n = one_plus_r ** n
    annuity = (principal * r / (1 - 1 / one_plus_r_power_n)).quantize(
        _QUANTIZE, rounding=ROUND_HALF_UP
    )

    dates = _due_dates(disbursement_date, repayment_frequency, term_periods)
    schedule = []
    outstanding = principal

    for i in range(term_periods):
        interest_i = (outstanding * r).quantize(_QUANTIZE, rounding=ROUND_HALF_UP)
        if i < term_periods - 1:
            principal_i = (annuity - interest_i).quantize(
                _QUANTIZE, rounding=ROUND_HALF_UP
            )
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
