from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.members.schemas import MemberIn, MemberOut, StatusChangeIn, StatusChangeOut
from app.modules.members.service import MemberService

router = APIRouter(prefix="/members", tags=["members"])

Session = Annotated[AsyncSession, Depends(get_tenant_session)]


@router.post("", response_model=MemberOut, status_code=201)
async def register_member(body: MemberIn, session: Session) -> MemberOut:
    svc = MemberService(session)
    try:
        member = await svc.register_member(
            full_name=body.full_name,
            date_of_birth=body.date_of_birth,
            gender=body.gender,
            created_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser actor
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
async def list_members(session: Session, status: str | None = None) -> list[MemberOut]:
    svc = MemberService(session)
    members = await svc.list_members(status=status)
    return [MemberOut.model_validate(m) for m in members]


@router.get("/{member_id}", response_model=MemberOut)
async def get_member(member_id: uuid.UUID, session: Session) -> MemberOut:
    svc = MemberService(session)
    try:
        member = await svc.get_member(member_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MemberOut.model_validate(member)


@router.post("/{member_id}/status-change", response_model=StatusChangeOut, status_code=202)
async def submit_status_change(
    member_id: uuid.UUID, body: StatusChangeIn, session: Session
) -> StatusChangeOut:
    svc = MemberService(session)
    try:
        approval_id = await svc.submit_status_change(
            member_id=member_id,
            new_status=body.new_status,
            submitted_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser actor
            reason=body.reason,
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StatusChangeOut(approval_request_id=approval_id, status="pending")
