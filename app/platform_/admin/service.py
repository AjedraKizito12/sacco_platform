"""DashboardStatsService — aggregates the platform admin dashboard view.

Runs ~7 small queries (one per metric) plus a small Python computation
for MRR. Designed to complete well under 100ms on the seeded test DB and
to scale to ~10k tenants in production without index changes — every
filter hits an existing index.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.platform_.admin.schemas import DashboardStatsOut
from app.platform_.billing.models import Invoice, Subscription, SubscriptionPlan
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.models import Tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Live = counted in MRR.
_LIVE_SUBSCRIPTION_STATUSES_FOR_MRR = ("active", "trialing")

# Statuses considered "outstanding" for invoice metrics.
_OUTSTANDING_INVOICE_STATUSES = ("issued", "partial", "overdue")

# Normalisation factor — number of months covered by each billing_period.
_PERIOD_TO_MONTHS: dict[str, Decimal] = {
    "monthly": Decimal("1"),
    "quarterly": Decimal("3"),
    "annual": Decimal("12"),
}


class DashboardStatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def compute(self) -> DashboardStatsOut:
        tenants = await self._tenants_by_status()
        subscriptions = await self._subscriptions_by_status()
        mrr = await self._mrr()
        invoices_outstanding, invoices_amount_outstanding = (
            await self._invoices_outstanding()
        )
        approvals_pending = await self._approvals_pending()
        active_impersonations = await self._active_impersonations()
        return DashboardStatsOut(
            tenants=tenants,
            subscriptions=subscriptions,
            mrr=mrr,
            invoices_outstanding=invoices_outstanding,
            invoices_amount_outstanding=invoices_amount_outstanding,
            approvals_pending=approvals_pending,
            active_impersonations=active_impersonations,
            last_updated=datetime.now(UTC),
        )

    async def _tenants_by_status(self) -> dict[str, int]:
        result = await self._s.execute(
            select(Tenant.status, func.count())
            .group_by(Tenant.status)
        )
        return {row[0]: row[1] for row in result.all()}

    async def _subscriptions_by_status(self) -> dict[str, int]:
        result = await self._s.execute(
            select(Subscription.status, func.count())
            .group_by(Subscription.status)
        )
        return {row[0]: row[1] for row in result.all()}

    async def _mrr(self) -> dict[str, Decimal]:
        """SUM(base_price / period_months) per currency for live subs."""
        result = await self._s.execute(
            select(
                SubscriptionPlan.currency,
                SubscriptionPlan.billing_period,
                func.sum(SubscriptionPlan.base_price),
            )
            .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
            .where(Subscription.status.in_(_LIVE_SUBSCRIPTION_STATUSES_FOR_MRR))
            .group_by(SubscriptionPlan.currency, SubscriptionPlan.billing_period)
        )
        mrr: dict[str, Decimal] = {}
        for currency, period, total in result.all():
            normalised = Decimal(total) / _PERIOD_TO_MONTHS[period]
            mrr[currency] = mrr.get(currency, Decimal("0")) + normalised
        return mrr

    async def _invoices_outstanding(
        self,
    ) -> tuple[dict[str, int], dict[str, Decimal]]:
        counts_result = await self._s.execute(
            select(Invoice.status, func.count())
            .where(Invoice.status.in_(_OUTSTANDING_INVOICE_STATUSES))
            .group_by(Invoice.status)
        )
        counts = {row[0]: row[1] for row in counts_result.all()}

        amounts_result = await self._s.execute(
            select(
                Invoice.currency,
                func.sum(Invoice.amount_total - Invoice.amount_paid),
            )
            .where(Invoice.status.in_(_OUTSTANDING_INVOICE_STATUSES))
            .group_by(Invoice.currency)
        )
        amounts = {row[0]: Decimal(row[1] or 0) for row in amounts_result.all()}
        return counts, amounts

    async def _approvals_pending(self) -> int:
        from app.modules.maker_checker.models.platform import (
            PlatformApprovalRequest,
        )
        result = await self._s.execute(
            select(func.count())
            .select_from(PlatformApprovalRequest)
            .where(PlatformApprovalRequest.status == "pending")
        )
        return int(result.scalar_one())

    async def _active_impersonations(self) -> int:
        now = datetime.now(UTC)
        result = await self._s.execute(
            select(func.count())
            .select_from(SupportImpersonation)
            .where(
                SupportImpersonation.ended_at.is_(None),
                SupportImpersonation.revoked_at.is_(None),
                SupportImpersonation.expires_at > now,
            )
        )
        return int(result.scalar_one())
