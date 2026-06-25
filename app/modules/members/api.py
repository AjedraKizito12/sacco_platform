from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_platform_session, get_tenant_session
from app.modules.iam.dependencies import CurrentMember, CurrentTenantUser
from app.modules.iam.keys.service import KeyService
from app.modules.iam.member_auth.schemas import EnablePortalAccessOut
from app.modules.iam.member_auth.schemas import MemberOut as MemberSelfOut
from app.modules.members.schemas import MemberIn, MemberOut, StatusChangeIn, StatusChangeOut
from app.modules.members.service import MemberService

router = APIRouter(prefix="/members", tags=["members"])
# Member self-service routes live under /member/* (distinct from operator /members/*).
member_router = APIRouter(prefix="/member", tags=["member-self"])

Session = Annotated[AsyncSession, Depends(get_tenant_session)]
PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]


@member_router.get("/me", response_model=MemberSelfOut)
async def member_self(member: CurrentMember) -> MemberSelfOut:
    """Return the authenticated member's own profile."""
    return MemberSelfOut.model_validate(member)


@router.post("", response_model=MemberOut, status_code=201)
async def register_member(
    body: MemberIn, session: Session, user: CurrentTenantUser
) -> MemberOut:
    svc = MemberService(session)
    try:
        member = await svc.register_member(
            full_name=body.full_name,
            date_of_birth=body.date_of_birth,
            gender=body.gender,
            created_by=user.id,
            phone=body.phone,
            email=body.email,
            physical_address=body.physical_address,
            national_id_number=body.national_id_number,
            id_document_type=body.id_document_type,
            id_document_number=body.id_document_number,
            id_issued_date=body.id_issued_date,
            id_expiry_date=body.id_expiry_date,
        )
    except ValueError as exc:
        if "already exists" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MemberOut.model_validate(member)


@router.get("", response_model=list[MemberOut])
async def list_members(
    session: Session, user: CurrentTenantUser, status: str | None = None
) -> list[MemberOut]:
    svc = MemberService(session)
    members = await svc.list_members(status=status)
    return [MemberOut.model_validate(m) for m in members]


@router.get("/{member_id}", response_model=MemberOut)
async def get_member(
    member_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> MemberOut:
    svc = MemberService(session)
    try:
        member = await svc.get_member(member_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MemberOut.model_validate(member)


@router.post("/{member_id}/enable-portal-access", response_model=EnablePortalAccessOut)
async def enable_portal_access(
    member_id: uuid.UUID,
    request: Request,
    session: Session,
    user: CurrentTenantUser,
    platform_db: PlatformSession,
) -> EnablePortalAccessOut:
    """Enable member portal login and mint a one-time set-password token.

    The token is returned once in the response body; the operator delivers it
    out of band (until Phase 3 email). The member redeems it via
    POST /member/auth/password-reset/confirm.
    """
    settings = get_settings()
    tenant_slug = request.headers.get(settings.tenant_header, "")
    redis = getattr(request.app.state, "redis", None)
    svc = MemberService(session)
    # enable_portal_access raises HTTPException (404 unknown / 400 no-email) which
    # FastAPI surfaces directly.
    token, ttl = await svc.enable_portal_access(
        member_id,
        key_service=KeyService(session=platform_db),
        redis=redis,
        tenant_slug=tenant_slug,
    )
    return EnablePortalAccessOut(
        member_id=member_id, portal_enabled=True, set_password_token=token, expires_in=ttl
    )


@router.post("/{member_id}/status-change", response_model=StatusChangeOut, status_code=202)
async def submit_status_change(
    member_id: uuid.UUID,
    body: StatusChangeIn,
    session: Session,
    user: CurrentTenantUser,
) -> StatusChangeOut:
    svc = MemberService(session)
    try:
        approval_id = await svc.submit_status_change(
            member_id=member_id,
            new_status=body.new_status,
            submitted_by=user.id,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StatusChangeOut(approval_request_id=approval_id, status="pending")
