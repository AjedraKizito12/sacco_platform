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
from app.platform_.auth import CurrentPlatformUser
from app.platform_.billing.schemas import (
    SubscriptionPlanIn,
    SubscriptionPlanOut,
    SubscriptionPlanPatch,
)
from app.platform_.billing.services import PlanCodeConflict, PlanService

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
