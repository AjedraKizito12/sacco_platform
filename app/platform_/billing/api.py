"""HTTP API for the billing module.

platform_router (mounted at /platform/billing): admin-only CRUD + maker-checker
tenant_router   (mounted at /billing/me):       read-only tenant-facing views
"""
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.modules.maker_checker.service import ApprovalService
from app.platform_.auth import CurrentPlatformUser, get_current_platform_user
from app.platform_.billing.exceptions import (
    InvalidTransition,
    PlanInactive,
    SubscriptionConflict,
)
from app.platform_.billing.schemas import (
    SubscriptionCancelIn,
    SubscriptionCreateIn,
    SubscriptionOut,
    SubscriptionPlanIn,
    SubscriptionPlanOut,
    SubscriptionPlanPatch,
)
from app.platform_.billing.services import PlanCodeConflict, PlanService, SubscriptionService
from app.platform_.models import PlatformUser

_log = structlog.get_logger(__name__)

platform_router = APIRouter(prefix="/platform/billing", tags=["billing-platform"])
tenant_router = APIRouter(prefix="/billing/me", tags=["billing-tenant"])


# ── Plans ─────────────────────────────────────────────────────────────────────


@platform_router.get(
    "/plans",
    response_model=list[SubscriptionPlanOut],
)
async def list_plans(
    _user: CurrentPlatformUser,
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    only_active: bool = False,
) -> list[SubscriptionPlanOut]:
    plans = await PlanService(session).list_plans(only_active=only_active)
    return [SubscriptionPlanOut.model_validate(p) for p in plans]


@platform_router.post(
    "/plans",
    response_model=SubscriptionPlanOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    payload: SubscriptionPlanIn,
    _user: CurrentPlatformUser,
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionPlanOut:
    try:
        plan = await PlanService(session).create(**payload.model_dump())
    except PlanCodeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SubscriptionPlanOut.model_validate(plan)


@platform_router.get(
    "/plans/{plan_id}",
    response_model=SubscriptionPlanOut,
)
async def get_plan(
    plan_id: uuid.UUID,
    _user: CurrentPlatformUser,
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionPlanOut:
    plan = await PlanService(session).get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return SubscriptionPlanOut.model_validate(plan)


@platform_router.patch(
    "/plans/{plan_id}",
    response_model=SubscriptionPlanOut,
)
async def update_plan(
    plan_id: uuid.UUID,
    payload: SubscriptionPlanPatch,
    _user: CurrentPlatformUser,
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionPlanOut:
    try:
        plan = await PlanService(session).update(
            plan_id=plan_id,
            **payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanCodeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SubscriptionPlanOut.model_validate(plan)


# ── Subscriptions ─────────────────────────────────────────────────────────────


@platform_router.get(
    "/subscriptions",
    response_model=list[SubscriptionOut],
)
async def list_subscriptions(
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    tenant_id: uuid.UUID | None = None,
    status_filter: str | None = None,
) -> list[SubscriptionOut]:
    from sqlalchemy import select

    from app.platform_.billing.models import Subscription

    q = select(Subscription).order_by(Subscription.created_at.desc())
    if tenant_id is not None:
        q = q.where(Subscription.tenant_id == tenant_id)
    if status_filter is not None:
        q = q.where(Subscription.status == status_filter)
    result = await session.execute(q)
    return [SubscriptionOut.model_validate(s) for s in result.scalars().all()]


@platform_router.post(
    "/subscriptions",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
)
async def assign_subscription(
    payload: SubscriptionCreateIn,
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionOut:
    try:
        sub = await SubscriptionService(session).assign(
            tenant_id=payload.tenant_id,
            plan_id=payload.plan_id,
            start_date=payload.start_date,
        )
    except PlanInactive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SubscriptionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SubscriptionOut.model_validate(sub)


@platform_router.get(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionOut,
)
async def get_subscription(
    subscription_id: uuid.UUID,
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionOut:
    sub = await SubscriptionService(session).get(subscription_id)
    if sub is None:
        raise HTTPException(
            status_code=404, detail=f"Subscription {subscription_id} not found"
        )
    return SubscriptionOut.model_validate(sub)


@platform_router.post("/subscriptions/{subscription_id}/cancel")
async def cancel_subscription(
    subscription_id: uuid.UUID,
    payload: SubscriptionCancelIn,
    user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    mode: str = "at_period_end",
) -> dict[str, str]:
    """Cancel a subscription. Two modes:

    - mode=at_period_end (default): graceful — sets cancelled_at + reason,
      status changes at period end (beat job). No maker-checker.
    - mode=immediate: hard cancel — creates an ApprovalRequest. The checker
      must approve, then the billing.cancel_subscription executor flips status.
    """
    if mode not in {"at_period_end", "immediate"}:
        raise HTTPException(
            status_code=400, detail="mode must be 'at_period_end' or 'immediate'"
        )

    if mode == "at_period_end":
        try:
            sub = await SubscriptionService(session).cancel(
                subscription_id=subscription_id,
                reason=payload.reason,
                cancel_at_period_end=True,
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "status": "cancellation_scheduled",
            "subscription_id": str(sub.id),
        }

    # mode == "immediate" — go through maker-checker
    existing = await SubscriptionService(session).get(subscription_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail=f"Subscription {subscription_id} not found"
        )

    approval_request = await ApprovalService(session).submit(
        operation_type="billing.cancel_subscription",
        payload={
            "subscription_id": str(subscription_id),
            "reason": payload.reason,
        },
        requested_by=user.id,
    )
    return {
        "status": "pending_approval",
        "approval_request_id": str(approval_request.id),
    }


@platform_router.post(
    "/subscriptions/{subscription_id}/reactivate",
    response_model=SubscriptionOut,
)
async def reactivate_subscription(
    subscription_id: uuid.UUID,
    _user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionOut:
    try:
        sub = await SubscriptionService(session).reactivate(
            subscription_id=subscription_id
        )
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SubscriptionOut.model_validate(sub)
