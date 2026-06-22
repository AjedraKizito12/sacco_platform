from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.iam.dependencies import CurrentTenantUser
from app.modules.maker_checker.models.tenant import TenantApprovalRequest
from app.modules.maker_checker.schemas import (
    ApprovalActionOut,
    ApprovalActionRequest,
    ApprovalRequestDetailOut,
    ApprovalRequestOut,
    RejectRequest,
    SubmitApprovalRequest,
)
from app.modules.maker_checker.service import ApprovalService

router = APIRouter(prefix="/approvals", tags=["maker-checker"])

Session = Annotated[AsyncSession, Depends(get_tenant_session)]


@router.post("", response_model=ApprovalRequestOut, status_code=201)
async def submit_approval(
    body: SubmitApprovalRequest,
    session: Session,
    user: CurrentTenantUser,
) -> ApprovalRequestOut:
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
    user: CurrentTenantUser,
    status: str | None = Query(None),
    operation_type: str | None = Query(None),
    requested_by: uuid.UUID | None = Query(None),
) -> list[ApprovalRequestOut]:
    q = select(TenantApprovalRequest).order_by(TenantApprovalRequest.requested_at.desc())
    if status:
        q = q.where(TenantApprovalRequest.status == status)
    if operation_type:
        q = q.where(TenantApprovalRequest.operation_type == operation_type)
    if requested_by is not None:
        q = q.where(TenantApprovalRequest.requested_by == requested_by)
    rows = (await session.execute(q)).scalars().all()
    svc = ApprovalService(session)
    out: list[ApprovalRequestOut] = []
    for r in rows:
        dto = ApprovalRequestOut.model_validate(r)
        dto.current_approvals = await svc.approval_count(r.id)
        out.append(dto)
    return out


@router.get("/{request_id}", response_model=ApprovalRequestDetailOut)
async def get_approval(
    request_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> ApprovalRequestDetailOut:
    row = (
        await session.execute(
            select(TenantApprovalRequest).where(TenantApprovalRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    svc = ApprovalService(session)
    dto = ApprovalRequestDetailOut.model_validate(row)
    dto.current_approvals = await svc.approval_count(row.id)
    dto.actions = [ApprovalActionOut.model_validate(a) for a in await svc.list_actions(row.id)]
    return dto


@router.post("/{request_id}/approve", response_model=ApprovalRequestOut)
async def approve(
    request_id: uuid.UUID,
    body: ApprovalActionRequest,
    session: Session,
    user: CurrentTenantUser,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.approve(
            request_id=request_id, actor_user_id=user.id, comment=body.comment
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
    user: CurrentTenantUser,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.reject(
            request_id=request_id, actor_user_id=user.id, reason=body.reason
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
    user: CurrentTenantUser,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.cancel(request_id=request_id, requested_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApprovalRequestOut.model_validate(request)
