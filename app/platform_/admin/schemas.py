# app/platform_/admin/schemas.py
"""Pydantic types for /platform/admin/dashboard-stats."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class MonthPoint(BaseModel):
    """One point in a dashboard month-series. ``month`` is ``YYYY-MM``; the
    Decimal ``value`` serialises to a JSON string (the shape charts read)."""

    month: str
    value: Decimal


class DashboardStatsOut(BaseModel):
    """Single round-trip aggregate for the platform admin dashboard.

    - tenants:                       counts by `tenants.status`
    - subscriptions:                 counts by `subscriptions.status`
    - mrr:                           normalised monthly revenue per currency,
                                     computed from active+trialing
                                     subscriptions × plan.base_price
    - invoices_outstanding:          counts of unpaid invoices by status
                                     (issued / partial / overdue)
    - invoices_amount_outstanding:   sum(amount_total - amount_paid) per
                                     currency for the same set
    - approvals_pending:             count of pending platform-scoped
                                     approval_requests
    - active_impersonations:         count of non-ended, non-revoked,
                                     non-expired support_impersonations
    - revenue_trend:                 confirmed-payment amount collected per
                                     month, last 6 months (oldest first)
    - tenants_trend:                 cumulative tenant count at each month-end,
                                     last 6 months (oldest first)
    - tenants_new_this_month:        tenants created in the current month
    - last_updated:                  generation timestamp (so the portal
                                     can show a "Last updated 12s ago" hint)
    """

    tenants: dict[str, int]
    subscriptions: dict[str, int]
    mrr: dict[str, Decimal]
    invoices_outstanding: dict[str, int]
    invoices_amount_outstanding: dict[str, Decimal]
    approvals_pending: int
    active_impersonations: int
    revenue_trend: list[MonthPoint]
    tenants_trend: list[MonthPoint]
    tenants_new_this_month: int
    last_updated: datetime
