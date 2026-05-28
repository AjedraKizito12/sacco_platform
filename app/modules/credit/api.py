# app/modules/credit/api.py
"""Credit module FastAPI router.

Product endpoints are implemented here (sub-plan 02).
Remaining endpoints are added in sub-plans 03, 04, 07, 10, 12.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.credit.models import Loan, LoanInstallment
from app.modules.credit.schemas import (
    DisburseIn,
    LoanApplicationApproveIn,
    LoanApplicationCreateIn,
    LoanApplicationOut,
    LoanApplicationRejectIn,
    LoanInstallmentOut,
    LoanOut,
    LoanProductCreateIn,
    LoanProductOut,
    LoanProductPatchIn,
    LoanRepaymentCreateIn,
    LoanRepaymentOut,
    WriteOffIn,
    WriteOffOut,
)
from app.modules.credit.services.application import LoanApplicationService
from app.modules.credit.services.disbursement import LoanDisbursementService
from app.modules.credit.services.product import LoanProductService
from app.modules.credit.services.repayment import LoanRepaymentService
from app.modules.credit.services.write_off import LoanWriteOffService
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


# ── Disbursement ──────────────────────────────────────────────────────────────


@router.post(
    "/loans/{application_id}/disburse",
    response_model=LoanOut,
    status_code=201,
)
async def disburse_loan(
    application_id: uuid.UUID,
    body: DisburseIn,
    session: Session,
) -> LoanOut:
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application_id,
            actor_id=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
            idempotency_key=body.idempotency_key,
        )
        await session.commit()
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanOut.model_validate(loan)


@router.get("/loans", response_model=list[LoanOut])
async def list_loans(
    session: Session,
    member_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> list[LoanOut]:
    stmt = _select(Loan)
    if member_id is not None:
        stmt = stmt.where(Loan.member_id == member_id)
    if status is not None:
        stmt = stmt.where(Loan.status == status)
    loans = list((await session.execute(stmt)).scalars().all())
    return [LoanOut.model_validate(l) for l in loans]


@router.get("/loans/{loan_id}", response_model=LoanOut)
async def get_loan(
    loan_id: uuid.UUID,
    session: Session,
) -> LoanOut:
    loan = await session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    return LoanOut.model_validate(loan)


# ── Repayment endpoints ───────────────────────────────────────────────────────


@router.post("/loans/{loan_id}/repayments", response_model=LoanRepaymentOut, status_code=201)
async def post_repayment(
    loan_id: uuid.UUID,
    body: LoanRepaymentCreateIn,
    session: Session,
) -> LoanRepaymentOut:
    try:
        svc = LoanRepaymentService(session)
        repayment = await svc.apply_repayment(
            loan_id=loan_id,
            amount=body.amount,
            payment_account_id=body.payment_account_id,
            posted_by=uuid.uuid4(),  # TODO SP12: replace with current_user.user_id
            narration=body.narration,
            idempotency_key=body.idempotency_key,
            savings_account_id=body.savings_account_id,
        )
        await session.commit()
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanRepaymentOut.model_validate(repayment)


@router.get("/loans/{loan_id}/repayments", response_model=list[LoanRepaymentOut])
async def list_repayments(
    loan_id: uuid.UUID,
    session: Session,
) -> list[LoanRepaymentOut]:
    svc = LoanRepaymentService(session)
    repayments = await svc.list_repayments(loan_id)
    return [LoanRepaymentOut.model_validate(r) for r in repayments]


# ── Schedule endpoint ─────────────────────────────────────────────────────────


@router.get("/loans/{loan_id}/schedule", response_model=list[LoanInstallmentOut])
async def get_schedule(
    loan_id: uuid.UUID,
    session: Session,
) -> list[LoanInstallmentOut]:
    installments = list(
        (
            await session.execute(
                _select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan_id)
                .order_by(LoanInstallment.period_number)
            )
        ).scalars().all()
    )
    return [LoanInstallmentOut.model_validate(i) for i in installments]


# ── Write-off endpoint ────────────────────────────────────────────────────────


@router.post("/loans/{loan_id}/write-off", response_model=WriteOffOut, status_code=201)
async def write_off_loan(
    loan_id: uuid.UUID,
    body: WriteOffIn,
    session: Session,
) -> WriteOffOut:
    try:
        svc = LoanWriteOffService(session)
        result = await svc.write_off(
            loan_id=loan_id,
            amount=body.amount,
            reason=body.reason,
            actor_id=uuid.uuid4(),  # TODO SP12: replace with current_user.user_id
            idempotency_key=body.idempotency_key,
            loan_loss_account_code=body.loan_loss_account_code,
        )
        await session.commit()
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return WriteOffOut(**result)


# ── Query endpoints ───────────────────────────────────────────────────────────


@router.get("/query/loans-eligible-for-fee", response_model=list[dict])
async def loans_eligible_for_fee(
    session: Session,
    min_days_past_due: int = 0,
) -> list[dict]:
    from app.modules.credit.services.query import CreditQueryService
    svc = CreditQueryService(session)
    return await svc.find_loans_eligible_for_fee(
        as_of_date=date.today(),
        min_days_past_due=min_days_past_due,
    )
