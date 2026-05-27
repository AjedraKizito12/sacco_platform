# app/modules/credit/api.py
"""Credit module FastAPI router.

Product endpoints are implemented here (sub-plan 02).
Remaining endpoints are added in sub-plans 03, 04, 07, 10, 12.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.credit.schemas import (
    LoanApplicationApproveIn,
    LoanApplicationCreateIn,
    LoanApplicationOut,
    LoanApplicationRejectIn,
    LoanProductCreateIn,
    LoanProductOut,
    LoanProductPatchIn,
)
from app.modules.credit.services.application import LoanApplicationService
from app.modules.credit.services.product import LoanProductService
from app.modules.maker_checker.service import ApprovalService

router = APIRouter(prefix="/credit", tags=["credit"])
Session = Annotated[AsyncSession, Depends(get_tenant_session)]


# ── Loan Products ─────────────────────────────────────────────────────────────


@router.post("/products", response_model=LoanProductOut, status_code=201)
async def create_loan_product(body: LoanProductCreateIn, session: Session) -> LoanProductOut:
    try:
        svc = LoanProductService(session)
        product = await svc.create(
            name=body.name,
            description=body.description,
            interest_method=body.interest_method,
            annual_interest_rate=body.annual_interest_rate,
            repayment_frequency=body.repayment_frequency,
            max_term_periods=body.max_term_periods,
            min_amount=body.min_amount,
            max_amount=body.max_amount,
            required_approvals=body.required_approvals,
            disbursement_destinations=body.disbursement_destinations,
            repayment_allocation=body.repayment_allocation,
            gl_principal_receivable_code=body.gl_principal_receivable_code,
            gl_interest_receivable_code=body.gl_interest_receivable_code,
            gl_interest_income_code=body.gl_interest_income_code,
            gl_loan_loss_expense_code=body.gl_loan_loss_expense_code,
            penalty_fee_type_code=body.penalty_fee_type_code,
            write_off_threshold=body.write_off_threshold,
            created_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LoanProductOut.model_validate(product)


@router.get("/products", response_model=list[LoanProductOut])
async def list_loan_products(
    session: Session,
    include_inactive: bool = Query(default=False),
) -> list[LoanProductOut]:
    svc = LoanProductService(session)
    products = await svc.list(include_inactive=include_inactive)
    return [LoanProductOut.model_validate(p) for p in products]


@router.get("/products/{product_id}", response_model=LoanProductOut)
async def get_loan_product(product_id: uuid.UUID, session: Session) -> LoanProductOut:
    try:
        svc = LoanProductService(session)
        product = await svc.get(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LoanProductOut.model_validate(product)


@router.patch("/products/{product_id}", response_model=LoanProductOut)
async def patch_loan_product(
    product_id: uuid.UUID,
    body: LoanProductPatchIn,
    session: Session,
) -> LoanProductOut:
    try:
        svc = LoanProductService(session)
        product = await svc.update(
            product_id,
            name=body.name,
            description=body.description,
            penalty_fee_type_code=body.penalty_fee_type_code,
            write_off_threshold=body.write_off_threshold,
            updated_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanProductOut.model_validate(product)


# ── Loan Applications ─────────────────────────────────────────────────────────


@router.post("/applications", response_model=LoanApplicationOut, status_code=201)
async def submit_loan_application(
    body: LoanApplicationCreateIn, session: Session
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.submit(
            loan_product_id=body.loan_product_id,
            member_id=body.member_id,
            requested_amount=body.requested_amount,
            requested_term_periods=body.requested_term_periods,
            purpose=body.purpose,
            disbursement_destination=body.disbursement_destination,
            disbursement_account_id=body.disbursement_account_id,
            submitted_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.get("/applications", response_model=list[LoanApplicationOut])
async def list_loan_applications(
    session: Session,
    member_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> list[LoanApplicationOut]:
    svc = LoanApplicationService(session)
    applications = await svc.list(member_id=member_id, status=status)
    return [LoanApplicationOut.model_validate(a) for a in applications]


@router.get("/applications/{application_id}", response_model=LoanApplicationOut)
async def get_loan_application(
    application_id: uuid.UUID, session: Session
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.get(application_id=application_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.post("/applications/{application_id}/withdraw", response_model=LoanApplicationOut)
async def withdraw_loan_application(
    application_id: uuid.UUID, session: Session
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.withdraw(
            application_id=application_id,
            withdrawn_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.post("/applications/{application_id}/approve", response_model=LoanApplicationOut)
async def approve_loan_application(
    application_id: uuid.UUID, body: LoanApplicationApproveIn, session: Session
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.get(application_id=application_id)
        if application.approval_request_id is None:
            raise ValueError("Application has no pending approval request")
        approval_svc = ApprovalService(session)
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
            comment=body.comment,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.post("/applications/{application_id}/reject", response_model=LoanApplicationOut)
async def reject_loan_application(
    application_id: uuid.UUID, body: LoanApplicationRejectIn, session: Session
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.reject(
            application_id=application_id,
            rejected_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
            reason=body.reason,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)
