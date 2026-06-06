"""HTTP API for /platform/impersonations/*.

Endpoints:
    POST   /platform/impersonations                        — submit (maker-checker)
    GET    /platform/impersonations/active                 — list mine
    GET    /platform/impersonations/all                    — list all (admin)
    GET    /platform/impersonations/{id}                   — detail
    DELETE /platform/impersonations/{id}                   — end (owner only)
    POST   /platform/impersonations/{id}/revoke            — revoke (admin)
    POST   /platform/impersonations/{id}/mint-tenant-token — mint a tenant JWT pair

Role gating (admin / superuser) currently delegates to the existing
get_current_superuser dep. When P1.7-05 ships 4-tier roles, swap the
`get_all` and `revoke` deps to require role>=admin without changing
call sites.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.platform_.auth import (
    CurrentAdmin,
    CurrentPlatformUser,
)
from app.platform_.impersonations.exceptions import (
    ImpersonationGone,
    ImpersonationNotActive,
)
from app.platform_.impersonations.schemas import (
    ImpersonationOut,
    ImpersonationStartIn,
    MintTenantTokenOut,
)
from app.platform_.impersonations.service import ImpersonationService

router = APIRouter(prefix="/platform/impersonations", tags=["platform-impersonations"])

Session = Annotated[AsyncSession, Depends(get_platform_session)]


class _SubmitOut(BaseModel):
    approval_request_id: uuid.UUID
    status: str


class _RevokeIn(BaseModel):
    reason: str = ""


@router.post("", response_model=_SubmitOut, status_code=202)
async def submit_impersonation(
    body: ImpersonationStartIn,
    session: Session,
    user: CurrentPlatformUser,
) -> _SubmitOut:
    try:
        approval = await ImpersonationService(session).request(
            platform_user_id=user.id,
            tenant_id=body.tenant_id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return _SubmitOut(
        approval_request_id=approval.id, status="pending_approval"
    )


@router.get("/active", response_model=list[ImpersonationOut])
async def list_active_mine(
    session: Session, user: CurrentPlatformUser,
) -> list[ImpersonationOut]:
    rows = await ImpersonationService(session).get_active_for_user(
        platform_user_id=user.id
    )
    return [ImpersonationOut.model_validate(r) for r in rows]


@router.get("/all", response_model=list[ImpersonationOut])
async def list_all_active(
    session: Session, _user: CurrentAdmin,
) -> list[ImpersonationOut]:
    rows = await ImpersonationService(session).get_all_active()
    return [ImpersonationOut.model_validate(r) for r in rows]


@router.get("/{impersonation_id}", response_model=ImpersonationOut)
async def get_impersonation(
    impersonation_id: uuid.UUID,
    session: Session,
    _user: CurrentPlatformUser,
) -> ImpersonationOut:
    row = await ImpersonationService(session).get_by_id(impersonation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Impersonation not found")
    return ImpersonationOut.model_validate(row)


@router.delete("/{impersonation_id}", status_code=204)
async def end_impersonation(
    impersonation_id: uuid.UUID,
    session: Session,
    user: CurrentPlatformUser,
) -> Response:
    svc = ImpersonationService(session)
    row = await svc.get_by_id(impersonation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Impersonation not found")
    if row.platform_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the impersonator can end this session (use /revoke instead)",
        )
    await svc.end(impersonation_id=impersonation_id, ended_by=user.id)
    await session.commit()
    return Response(status_code=204)


@router.post("/{impersonation_id}/revoke", status_code=204)
async def revoke_impersonation(
    impersonation_id: uuid.UUID,
    body: _RevokeIn,
    session: Session,
    user: CurrentAdmin,
) -> Response:
    svc = ImpersonationService(session)
    row = await svc.get_by_id(impersonation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Impersonation not found")
    await svc.revoke(impersonation_id=impersonation_id, revoked_by=user.id)
    await session.commit()
    return Response(status_code=204)


@router.post(
    "/{impersonation_id}/mint-tenant-token", response_model=MintTenantTokenOut
)
async def mint_tenant_token(
    impersonation_id: uuid.UUID,
    request: Request,
    session: Session,
    user: CurrentPlatformUser,
) -> MintTenantTokenOut:
    svc = ImpersonationService(session)
    row = await svc.get_by_id(impersonation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Impersonation not found")
    if row.platform_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the impersonator can mint a token for this session",
        )
    redis = getattr(request.app.state, "redis", None)
    try:
        return await svc.mint_tenant_token(
            impersonation_id=impersonation_id,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
            redis=redis,
        )
    except ImpersonationGone as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ImpersonationNotActive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
