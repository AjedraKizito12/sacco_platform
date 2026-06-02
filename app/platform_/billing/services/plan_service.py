"""PlanService — CRUD for subscription_plans.

No state machine, no maker-checker. Plans are operator-managed.
Audit log captures changes via AuditableMixin on SubscriptionPlan.
"""
from __future__ import annotations

import uuid
from typing import Any, cast

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.billing.exceptions import BillingError
from app.platform_.billing.models import SubscriptionPlan

_log = structlog.get_logger(__name__)


class PlanCodeConflict(BillingError):
    """Raised when create() is called with a code that already exists."""


class PlanService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, plan_id: uuid.UUID) -> SubscriptionPlan | None:
        return cast(
            SubscriptionPlan | None,
            await self._s.scalar(
                select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
            ),
        )

    async def get_by_code(self, code: str) -> SubscriptionPlan | None:
        return cast(
            SubscriptionPlan | None,
            await self._s.scalar(
                select(SubscriptionPlan).where(SubscriptionPlan.code == code)
            ),
        )

    async def list_plans(self, *, only_active: bool = False) -> list[SubscriptionPlan]:
        q = select(SubscriptionPlan).order_by(SubscriptionPlan.code)
        if only_active:
            q = q.where(SubscriptionPlan.is_active.is_(True))
        result = await self._s.execute(q)
        return list(result.scalars().all())

    async def create(self, **fields: Any) -> SubscriptionPlan:
        """Create a plan.

        Raises:
            PlanCodeConflict: plan with same `code` already exists.
        """
        plan = SubscriptionPlan(**fields)
        self._s.add(plan)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            await self._s.rollback()
            raise PlanCodeConflict(
                f"Plan code {fields.get('code')!r} already in use"
            ) from exc
        _log.info("plan.created", plan_id=str(plan.id), code=plan.code)
        return plan

    async def update(
        self, *, plan_id: uuid.UUID, **changes: Any
    ) -> SubscriptionPlan:
        """Patch fields on a plan. Returns the updated plan.

        Raises:
            ValueError: plan not found.
            PlanCodeConflict: trying to change `code` to one that already exists.
        """
        plan = await self.get(plan_id)
        if plan is None:
            raise ValueError(f"Plan {plan_id} not found")
        for key, value in changes.items():
            if value is None:
                continue
            setattr(plan, key, value)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            await self._s.rollback()
            raise PlanCodeConflict(
                f"Cannot rename to code {changes.get('code')!r} — already in use"
            ) from exc
        _log.info("plan.updated", plan_id=str(plan.id), changed=list(changes.keys()))
        return plan
