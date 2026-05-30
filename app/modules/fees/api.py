from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.fees.models import FeeType
from app.modules.fees.schemas import (
    FeeAssessmentCreateIn,
    FeeAssessmentDetailOut,
    FeeAssessmentOut,
    FeeCollectionCreateIn,
    FeeCollectionOut,
    FeeTypeCreateIn,
    FeeTypeOut,
    FeeTypePatchIn,
)
from app.modules.fees.service import FeeAssessmentService, FeeCollectionService
from app.modules.iam.dependencies import CurrentTenantUser

router = APIRouter(prefix="/fees", tags=["fees"])
Session = Annotated[AsyncSession, Depends(get_tenant_session)]


# ── Fee Types ─────────────────────────────────────────────────────────────────


@router.get("/types", response_model=list[FeeTypeOut])
async def list_fee_types(
    session: Session,
    user: CurrentTenantUser,
    include_inactive: bool = False,
) -> list[FeeTypeOut]:
    q = select(FeeType).order_by(FeeType.name)
    if not include_inactive:
        q = q.where(FeeType.is_active.is_(True))
    result = await session.execute(q)
    return [FeeTypeOut.model_validate(ft) for ft in result.scalars().all()]


@router.get("/types/{fee_type_id}", response_model=FeeTypeOut)
async def get_fee_type(
    fee_type_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> FeeTypeOut:
    ft = await session.get(FeeType, fee_type_id)
    if ft is None:
        raise HTTPException(status_code=404, detail=f"FeeType '{fee_type_id}' not found")
    return FeeTypeOut.model_validate(ft)


@router.post("/types", response_model=FeeTypeOut, status_code=201)
async def create_fee_type(
    body: FeeTypeCreateIn, session: Session, user: CurrentTenantUser
) -> FeeTypeOut:
    existing = await session.scalar(select(FeeType).where(FeeType.code == body.code))
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"FeeType with code '{body.code}' already exists")

    ft = FeeType(
        code=body.code,
        name=body.name,
        description=body.description,
        applicable_to=body.applicable_to,
        amount_kind=body.amount_kind,
        amount=body.amount,
        currency=body.currency,
        trigger_kind=body.trigger_kind,
        event_name=body.event_name,
        schedule_config=body.schedule_config,
        gl_income_account_code=body.gl_income_account_code,
        gl_receivable_account_code=body.gl_receivable_account_code,
        requires_collection=body.requires_collection,
    )
    session.add(ft)
    await session.flush()
    return FeeTypeOut.model_validate(ft)


@router.patch("/types/{fee_type_id}", response_model=FeeTypeOut)
async def patch_fee_type(
    fee_type_id: uuid.UUID,
    body: FeeTypePatchIn,
    session: Session,
    user: CurrentTenantUser,
) -> FeeTypeOut:
    ft = await session.get(FeeType, fee_type_id)
    if ft is None:
        raise HTTPException(status_code=404, detail=f"FeeType '{fee_type_id}' not found")
    if body.name is not None:
        ft.name = body.name
    if body.description is not None:
        ft.description = body.description
    if body.amount is not None:
        ft.amount = body.amount
    if body.is_active is not None:
        ft.is_active = body.is_active
    if body.requires_collection is not None:
        ft.requires_collection = body.requires_collection
    await session.flush()
    return FeeTypeOut.model_validate(ft)


# ── Fee Assessments ───────────────────────────────────────────────────────────


@router.get("/assessments", response_model=list[FeeAssessmentOut])
async def list_assessments(
    session: Session,
    user: CurrentTenantUser,
    status: str | None = Query(default=None),
    member_id: uuid.UUID | None = Query(default=None),
    fee_type_code: str | None = Query(default=None),
) -> list[FeeAssessmentOut]:
    svc = FeeAssessmentService(session)
    assessments = await svc.list_assessments(
        status=status,
        target_type="member" if member_id else None,
        target_id=member_id,
        fee_type_code=fee_type_code,
    )
    return [FeeAssessmentOut.model_validate(a) for a in assessments]


@router.get("/assessments/{assessment_id}", response_model=FeeAssessmentDetailOut)
async def get_assessment(
    assessment_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> FeeAssessmentDetailOut:
    try:
        svc = FeeAssessmentService(session)
        assessment = await svc.get_assessment(assessment_id)
        collections = await FeeCollectionService(session).list_collections(assessment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    data = FeeAssessmentOut.model_validate(assessment).model_dump()
    data["collections"] = [FeeCollectionOut.model_validate(c) for c in collections]
    return FeeAssessmentDetailOut.model_validate(data)


@router.post("/assessments", response_model=FeeAssessmentOut, status_code=201)
async def create_assessment(
    body: FeeAssessmentCreateIn, session: Session, user: CurrentTenantUser
) -> FeeAssessmentOut:
    ft = await session.get(FeeType, body.fee_type_id)
    if ft is None:
        raise HTTPException(status_code=404, detail=f"FeeType '{body.fee_type_id}' not found")
    try:
        svc = FeeAssessmentService(session)
        assessment = await svc.assess(
            fee_type=ft,
            target_type=body.target_type,
            target_id=body.target_id,
            period_start=body.period_start,
            period_end=body.period_end,
            triggered_by_event_id=None,
            actor=user.id,
            idempotency_key=f"manual-{body.fee_type_id}-{body.target_id}-{body.period_start}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FeeAssessmentOut.model_validate(assessment)


# ── Fee Collections ───────────────────────────────────────────────────────────


@router.post("/collections", response_model=FeeCollectionOut, status_code=201)
async def create_collection(
    body: FeeCollectionCreateIn, session: Session, user: CurrentTenantUser
) -> FeeCollectionOut:
    if body.method not in ("cash", "journal_voucher"):
        raise HTTPException(
            status_code=400,
            detail="API collections must use 'cash' or 'journal_voucher'. 'savings_deduction' is automatic only.",
        )
    try:
        svc = FeeCollectionService(session)
        collection = await svc.collect(
            assessment_id=body.fee_assessment_id,
            amount=body.amount,
            method=body.method,
            collected_by=user.id,
            idempotency_key=body.idempotency_key,
            contra_account_id=body.contra_account_id,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return FeeCollectionOut.model_validate(collection)
