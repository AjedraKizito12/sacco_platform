"""Pydantic types for GET /dashboard/stats (tenant scope)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class MonthPoint(BaseModel):
    """One point in a dashboard month-series. ``month`` is ``YYYY-MM``; the
    Decimal ``value`` serialises to a JSON string (the shape charts read)."""

    month: str
    value: Decimal


class TenantDashboardStatsOut(BaseModel):
    """Single round-trip aggregate for the tenant operator dashboard.

    - members:                       counts by `members.status`
                                     (pending/active/suspended/exited)
    - total_members:                 sum of `members` (convenience for the KPI)
    - total_savings:                 net savings balance across all accounts,
                                     in the tenant's single currency (UGX).
                                     SUM(deposit+SYSTEM_CREDIT) -
                                     SUM(withdrawal+SYSTEM_DEBIT), matching the
                                     per-account balance shown elsewhere.
    - loans_outstanding_principal:   SUM(outstanding_principal) over loans in an
                                     active status (disbursing/disbursed/
                                     in_arrears). The snapshot column is
                                     authoritative for operational queries.
    - loans_by_status:               counts by `loans.status`
    - members_in_arrears:            distinct members with an in_arrears loan
    - approvals_pending:             count of pending tenant-scoped
                                     approval_requests (the operator's queue)
    - applications_pending:          count of loan applications awaiting an
                                     operator decision (submitted/under_review)
    - savings_trend:                 month-end cumulative savings balance, last
                                     6 months (oldest first) — area chart
    - disbursement_trend:            principal disbursed per month, last 6
                                     months (oldest first) — bar/area chart
    - members_new_this_month:        members registered in the current month
    - last_updated:                  generation timestamp (portal freshness hint)

    Money is single-currency per tenant (UGX); amounts are rendered by the
    portal's <TenantCurrencyProvider>. Decimal serialises to a JSON string.
    """

    members: dict[str, int]
    total_members: int
    total_savings: Decimal
    loans_outstanding_principal: Decimal
    loans_by_status: dict[str, int]
    members_in_arrears: int
    approvals_pending: int
    applications_pending: int
    savings_trend: list[MonthPoint]
    disbursement_trend: list[MonthPoint]
    members_new_this_month: int
    last_updated: datetime
