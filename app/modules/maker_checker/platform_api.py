"""FastAPI router for /platform/approvals/* endpoints.

Mirrors the tenant router in app/modules/maker_checker/api.py but uses
get_platform_session and the PlatformApprovalRequest model.

ApprovalService (app/modules/maker_checker/service.py) is schema-agnostic
and resolves PlatformApprovalRequest / PlatformApprovalAction from
session.sync_session.info["is_platform"], which get_platform_session sets.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.modules.maker_checker.models.platform import PlatformApprovalRequest
from app.modules.maker_checker.schemas import (
    ApprovalActionRequest,
    ApprovalRequestOut,
    RejectRequest,
    SubmitApprovalRequest,
)
from app.modules.maker_checker.service import ApprovalService
from app.platform_.auth import CurrentAdmin, CurrentSupport

router = APIRouter(prefix="/platform/approvals", tags=["platform-maker-checker"])

Session = Annotated[AsyncSession, Depends(get_platform_session)]


@router.post("", response_model=ApprovalRequestOut, status_code=201)
async def submit_approval(
    body: SubmitApprovalRequest,
    session: Session,
    user: CurrentAdmin,
) -> ApprovalRequestOut:
    """Submit a new platform-scoped approval request.

    Most platform-scoped approvals are submitted by other services (billing,
    platform_users update, tenant suspend). This endpoint exists for the
    rare case of an operator-initiated approval.
    """
    svc = ApprovalService(session)
    try:
        request = await svc.submit(
            operation_type=body.operation_type,
            payload=body.payload,
            requested_by=user.id,
            required_approvals=body.required_approvals,
            expires_at=body.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApprovalRequestOut.model_validate(request)


@router.get("", response_model=list[ApprovalRequestOut])
async def list_approvals(
    session: Session,
    user: CurrentSupport,
    status: str | None = Query(None),
    operation_type: str | None = Query(None),
    requested_by: uuid.UUID | None = Query(None),
) -> list[ApprovalRequestOut]:
    q = select(PlatformApprovalRequest).order_by(PlatformApprovalRequest.requested_at.desc())
    if status:
        q = q.where(PlatformApprovalRequest.status == status)
    if operation_type:
        q = q.where(PlatformApprovalRequest.operation_type == operation_type)
    if requested_by is not None:
        q = q.where(PlatformApprovalRequest.requested_by == requested_by)
    rows = (await session.execute(q)).scalars().all()
    return [ApprovalRequestOut.model_validate(r) for r in rows]


@router.get("/{request_id}", response_model=ApprovalRequestOut)
async def get_approval(
    request_id: uuid.UUID,
    session: Session,
    user: CurrentSupport,
) -> ApprovalRequestOut:
    row = await session.scalar(
        select(PlatformApprovalRequest).where(PlatformApprovalRequest.id == request_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return ApprovalRequestOut.model_validate(row)


@router.post("/{request_id}/approve", response_model=ApprovalRequestOut)
async def approve(
    request_id: uuid.UUID,
    body: ApprovalActionRequest,
    session: Session,
    user: CurrentAdmin,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.approve(
            request_id=request_id,
            actor_user_id=user.id,
            comment=body.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApprovalRequestOut.model_validate(request)


@router.post("/{request_id}/reject", response_model=ApprovalRequestOut)
async def reject(
    request_id: uuid.UUID,
    body: RejectRequest,
    session: Session,
    user: CurrentAdmin,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.reject(
            request_id=request_id,
            actor_user_id=user.id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApprovalRequestOut.model_validate(request)


@router.post("/{request_id}/cancel", response_model=ApprovalRequestOut)
async def cancel(
    request_id: uuid.UUID,
    body: ApprovalActionRequest,
    session: Session,
    user: CurrentAdmin,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.cancel(request_id=request_id, requested_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApprovalRequestOut.model_validate(request)
