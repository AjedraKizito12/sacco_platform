"""SubscriptionService — owns the subscription state machine.

State machine:
    pending (tenant default) ──assign──> trialing OR active
    trialing ──(period ends)──> active (via beat or explicit transition)
    active ──transition_to_past_due──> past_due
    past_due ──transition_to_suspended──> suspended
    past_due ──reactivate──> active
    suspended ──reactivate──> active
    any ──cancel──> cancelled

Every transition writes BOTH platform.subscriptions.status AND the
denormalised platform.tenants.subscription_status in the same flush.
The middleware in SP04 reads tenants.subscription_status on every
request, so drift breaks access control.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Final, cast

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.billing.exceptions import (
    PlanInactive,
    SubscriptionConflict,
)
from app.platform_.billing.models import Subscription, SubscriptionPlan
from app.platform_.models import Tenant

_log = structlog.get_logger(__name__)

# Fixed-day approximations used by `assign()` for the initial period end.
# The nightly invoice-generation job (SP06) uses `relativedelta` for
# calendar-month accuracy and reconciles via current_period_start/end.
_BILLING_PERIOD_DAYS: Final[dict[str, int]] = {
    "monthly": 30,
    "quarterly": 90,
    "annual": 365,
}

# Set of statuses that count as "live" — must match the SQL partial unique
# index `uq_subscriptions_live_tenant`.
_LIVE_STATUSES: Final[frozenset[str]] = frozenset(
    {"trialing", "active", "past_due"}
)


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── Queries ────────────────────────────────────────────────────────────

    async def get(self, subscription_id: uuid.UUID) -> Subscription | None:
        return cast(
            Subscription | None,
            await self._s.scalar(
                select(Subscription).where(Subscription.id == subscription_id)
            ),
        )

    async def get_live_for_tenant(self, tenant_id: uuid.UUID) -> Subscription | None:
        """Return the tenant's current live subscription, if any."""
        return cast(
            Subscription | None,
            await self._s.scalar(
                select(Subscription).where(
                    Subscription.tenant_id == tenant_id,
                    Subscription.status.in_(_LIVE_STATUSES),
                )
            ),
        )

    # ── Commands ───────────────────────────────────────────────────────────

    async def assign(
        self,
        *,
        tenant_id: uuid.UUID,
        plan_id: uuid.UUID,
        start_date: date | None = None,
    ) -> Subscription:
        """Assign `plan_id` to `tenant_id`.

        Raises:
            ValueError: tenant or plan does not exist.
            PlanInactive: plan.is_active is False.
            SubscriptionConflict: tenant already has a live subscription.
        """
        tenant = await self._s.scalar(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found")

        plan = await self._s.scalar(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        )
        if plan is None:
            raise ValueError(f"SubscriptionPlan {plan_id} not found")
        if not plan.is_active:
            raise PlanInactive(f"Plan {plan.code!r} is not active")

        existing = await self.get_live_for_tenant(tenant_id)
        if existing is not None:
            raise SubscriptionConflict(
                f"Tenant {tenant_id} already has a live subscription "
                f"({existing.id}, status={existing.status!r})"
            )

        period_start = start_date or date.today()
        if plan.trial_period_days > 0:
            initial_status = "trialing"
            period_end = period_start + timedelta(days=plan.trial_period_days)
        else:
            initial_status = "active"
            period_end = period_start + timedelta(
                days=_BILLING_PERIOD_DAYS[plan.billing_period]
            )

        sub = Subscription(
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=initial_status,
            started_at=datetime.now(UTC),
            current_period_start=period_start,
            current_period_end=period_end,
            next_billing_date=period_end,
        )
        self._s.add(sub)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            # Race: another caller inserted a live subscription between
            # the get_live_for_tenant() check and this flush. Translate
            # to the domain exception.
            await self._s.rollback()
            raise SubscriptionConflict(
                f"Tenant {tenant_id} already has a live subscription (race)"
            ) from exc

        tenant.subscription_status = initial_status
        tenant.current_subscription_id = sub.id
        await self._s.flush()

        _log.info(
            "subscription.assigned",
            subscription_id=str(sub.id),
            tenant_id=str(tenant_id),
            plan_id=str(plan_id),
            initial_status=initial_status,
        )
        return sub
