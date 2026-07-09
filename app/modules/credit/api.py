# app/modules/credit/api.py
"""Credit module FastAPI router.

Product endpoints are implemented here (sub-plan 02).
Remaining endpoints are added in sub-plans 03, 04, 07, 10, 12.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.credit.models import Loan, LoanApplication, LoanInstallment
from app.modules.credit.schemas import (
    DisburseIn,
    GuarantorConsentIn,
    GuarantorNominateIn,
    GuarantorOut,
    LoanApplicationApproveIn,
    LoanApplicationCreateIn,
    LoanApplicationOut,
    LoanApplicationRejectIn,
    LoanInstallmentOut,
    LoanOut,
    LoanProductCreateIn,
    LoanProductOut,
    LoanProductPatchIn,
    LoanRecoveryIn,
    LoanRecoveryOut,
    LoanRepaymentCreateIn,
    LoanRepaymentOut,
    LoanStatementOut,
    MemberLoanProductOut,
    PayrollBatchJsonIn,
    PayrollBatchOut,
    RestructureIn,
    RestructuringOut,
    StatementLineOut,
    WriteOffIn,
    WriteOffOut,
)
from app.modules.credit.services.application import LoanApplicationService
from app.modules.credit.services.disbursement import LoanDisbursementService
from app.modules.credit.services.product import LoanProductService
from app.modules.credit.services.repayment import LoanRepaymentService
from app.modules.credit.services.restructuring import LoanRestructuringService
from app.modules.credit.services.write_off import LoanWriteOffService
from app.modules.iam.dependencies import CurrentMember, CurrentTenantUser
from app.modules.maker_checker.service import ApprovalService

router = APIRouter(prefix="/credit", tags=["credit"])
# Member self-service loans (read-only; scoped to the current member).
member_router = APIRouter(prefix="/member/loans", tags=["member-loans"])
# Member self-service loan applications (read-only; scoped to the current member).
member_app_router = APIRouter(prefix="/member/loan-applications", tags=["member-loans"])
# Member self-service loan products (read-only; active products, slim shape).
member_products_router = APIRouter(prefix="/member/loan-products", tags=["member-loans"])
Session = Annotated[AsyncSession, Depends(get_tenant_session)]


async def _member_loan_or_404(
    session: AsyncSession, loan_id: uuid.UUID, member_id: uuid.UUID
) -> Loan:
    """Fetch a loan and verify it belongs to *member_id*, else 404 (no leak)."""
    loan = await session.get(Loan, loan_id)
    if loan is None or loan.member_id != member_id:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


@member_router.get("", response_model=list[LoanOut])
async def member_loans(session: Session, member: CurrentMember) -> list[LoanOut]:
    """List the current member's own loans."""
    loans = list(
        (await session.execute(_select(Loan).where(Loan.member_id == member.id)))
        .scalars()
        .all()
    )
    return [LoanOut.model_validate(loan) for loan in loans]


@member_router.get("/{loan_id}", response_model=LoanOut)
async def member_loan_detail(
    loan_id: uuid.UUID, session: Session, member: CurrentMember
) -> LoanOut:
    """Return one of the current member's own loans (404 if not theirs)."""
    loan = await _member_loan_or_404(session, loan_id, member.id)
    return LoanOut.model_validate(loan)


@member_router.get("/{loan_id}/schedule", response_model=list[LoanInstallmentOut])
async def member_loan_schedule(
    loan_id: uuid.UUID, session: Session, member: CurrentMember
) -> list[LoanInstallmentOut]:
    """Return the repayment schedule for the member's own loan (404 if not theirs)."""
    await _member_loan_or_404(session, loan_id, member.id)
    installments = list(
        (
            await session.execute(
                _select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan_id)
                .order_by(LoanInstallment.period_number)
            )
        )
        .scalars()
        .all()
    )
    return [LoanInstallmentOut.model_validate(i) for i in installments]


@member_router.get("/{loan_id}/statement", response_model=LoanStatementOut)
async def member_loan_statement(
    loan_id: uuid.UUID, session: Session, member: CurrentMember
) -> LoanStatementOut:
    """Return a JSON statement for the member's own loan (404 if not theirs)."""
    await _member_loan_or_404(session, loan_id, member.id)
    from app.modules.credit.services.statement import LoanStatementService  # noqa: PLC0415

    svc = LoanStatementService(session)
    lines = await svc.get_statement(loan_id=loan_id, from_date=None, to_date=None)
    return LoanStatementOut(
        loan_id=loan_id,
        from_date=None,
        to_date=None,
        lines=[
            StatementLineOut(
                date=line.date,
                line_type=line.line_type,
                description=line.description,
                debit=line.debit,
                credit=line.credit,
                running_balance=line.running_balance,
            )
            for line in lines
        ],
    )


async def _member_application_or_404(
    session: AsyncSession, application_id: uuid.UUID, member_id: uuid.UUID
) -> LoanApplication:
    """Fetch an application and verify it belongs to *member_id*, else 404."""
    svc = LoanApplicationService(session)
    try:
        application = await svc.get(application_id=application_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Application not found") from exc
    if application.member_id != member_id:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@member_app_router.get("", response_model=list[LoanApplicationOut])
async def member_loan_applications(
    session: Session, member: CurrentMember
) -> list[LoanApplicationOut]:
    """List the current member's own loan applications."""
    svc = LoanApplicationService(session)
    applications = await svc.list(member_id=member.id, status=None)
    return [LoanApplicationOut.model_validate(a) for a in applications]


@member_app_router.get("/{application_id}", response_model=LoanApplicationOut)
async def member_loan_application_detail(
    application_id: uuid.UUID, session: Session, member: CurrentMember
) -> LoanApplicationOut:
    """Return one of the current member's own applications (404 if not theirs)."""
    application = await _member_application_or_404(session, application_id, member.id)
    return LoanApplicationOut.model_validate(application)


@member_products_router.get("", response_model=list[MemberLoanProductOut])
async def member_loan_products(
    session: Session, member: CurrentMember
) -> list[MemberLoanProductOut]:
    """List active loan products a member can apply for (slim view)."""
    svc = LoanProductService(session)
    products = await svc.list(include_inactive=False)
    return [MemberLoanProductOut.model_validate(p) for p in products]


# ── Loan Products ─────────────────────────────────────────────────────────────


@router.post("/products", response_model=LoanProductOut, status_code=201)
async def create_loan_product(
    body: LoanProductCreateIn, session: Session, user: CurrentTenantUser
) -> LoanProductOut:
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
            created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LoanProductOut.model_validate(product)


@router.get("/products", response_model=list[LoanProductOut])
async def list_loan_products(
    session: Session,
    user: CurrentTenantUser,
    include_inactive: bool = Query(default=False),
) -> list[LoanProductOut]:
    svc = LoanProductService(session)
    products = await svc.list(include_inactive=include_inactive)
    return [LoanProductOut.model_validate(p) for p in products]


@router.get("/products/{product_id}", response_model=LoanProductOut)
async def get_loan_product(
    product_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> LoanProductOut:
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
    user: CurrentTenantUser,
) -> LoanProductOut:
    try:
        svc = LoanProductService(session)
        product = await svc.update(
            product_id,
            name=body.name,
            description=body.description,
            penalty_fee_type_code=body.penalty_fee_type_code,
            write_off_threshold=body.write_off_threshold,
            updated_by=user.id,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanProductOut.model_validate(product)


# ── Loan Applications ─────────────────────────────────────────────────────────


@router.post("/applications", response_model=LoanApplicationOut, status_code=201)
async def submit_loan_application(
    body: LoanApplicationCreateIn, session: Session, user: CurrentTenantUser
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
            submitted_by=user.id,
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.get("/applications", response_model=list[LoanApplicationOut])
async def list_loan_applications(
    session: Session,
    user: CurrentTenantUser,
    member_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> list[LoanApplicationOut]:
    svc = LoanApplicationService(session)
    applications = await svc.list(member_id=member_id, status=status)
    return [LoanApplicationOut.model_validate(a) for a in applications]


@router.get("/applications/{application_id}", response_model=LoanApplicationOut)
async def get_loan_application(
    application_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.get(application_id=application_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.post("/applications/{application_id}/withdraw", response_model=LoanApplicationOut)
async def withdraw_loan_application(
    application_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        # Withdraw by the original submitter (resolved via the approval request)
        # so the maker-checker cancel check passes; fall back to the current user
        # if there is no linked approval request (shouldn't happen in practice).
        application = await svc.get(application_id=application_id)
        actor_id = user.id
        if application.approval_request_id is not None:
            from app.modules.maker_checker.models.tenant import TenantApprovalRequest

            req = await session.get(TenantApprovalRequest, application.approval_request_id)
            if req is not None:
                actor_id = req.requested_by
        application = await svc.withdraw(
            application_id=application_id,
            withdrawn_by=actor_id,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.post("/applications/{application_id}/approve", response_model=LoanApplicationOut)
async def approve_loan_application(
    application_id: uuid.UUID,
    body: LoanApplicationApproveIn,
    session: Session,
    user: CurrentTenantUser,
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.get(application_id=application_id)
        if application.approval_request_id is None:
            raise ValueError("Application has no pending approval request")
        approval_svc = ApprovalService(session)
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=user.id,
            comment=body.comment,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.post("/applications/{application_id}/reject", response_model=LoanApplicationOut)
async def reject_loan_application(
    application_id: uuid.UUID,
    body: LoanApplicationRejectIn,
    session: Session,
    user: CurrentTenantUser,
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.reject(
            application_id=application_id,
            rejected_by=user.id,
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
    user: CurrentTenantUser,
) -> LoanOut:
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application_id,
            actor_id=user.id,
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
    user: CurrentTenantUser,
    member_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> list[LoanOut]:
    stmt = _select(Loan)
    if member_id is not None:
        stmt = stmt.where(Loan.member_id == member_id)
    if status is not None:
        stmt = stmt.where(Loan.status == status)
    loans = list((await session.execute(stmt)).scalars().all())
    return [LoanOut.model_validate(loan) for loan in loans]


@router.get("/loans/{loan_id}", response_model=LoanOut)
async def get_loan(
    loan_id: uuid.UUID,
    session: Session,
    user: CurrentTenantUser,
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
    user: CurrentTenantUser,
) -> LoanRepaymentOut:
    try:
        svc = LoanRepaymentService(session)
        repayment = await svc.apply_repayment(
            loan_id=loan_id,
            amount=body.amount,
            payment_account_id=body.payment_account_id,
            posted_by=user.id,
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
    user: CurrentTenantUser,
) -> list[LoanRepaymentOut]:
    svc = LoanRepaymentService(session)
    repayments = await svc.list_repayments(loan_id)
    return [LoanRepaymentOut.model_validate(r) for r in repayments]


# ── Schedule endpoint ─────────────────────────────────────────────────────────


@router.get("/loans/{loan_id}/schedule", response_model=list[LoanInstallmentOut])
async def get_schedule(
    loan_id: uuid.UUID,
    session: Session,
    user: CurrentTenantUser,
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
    user: CurrentTenantUser,
) -> WriteOffOut:
    try:
        svc = LoanWriteOffService(session)
        result = await svc.write_off(
            loan_id=loan_id,
            amount=body.amount,
            reason=body.reason,
            actor_id=user.id,
            idempotency_key=body.idempotency_key,
            loan_loss_account_code=body.loan_loss_account_code,
        )
        await session.commit()
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return WriteOffOut(**result)


@router.post("/loans/{loan_id}/recover", response_model=LoanRecoveryOut, status_code=201)
async def recover_written_off_loan(
    loan_id: uuid.UUID,
    body: LoanRecoveryIn,
    session: Session,
    user: CurrentTenantUser,
) -> LoanRecoveryOut:
    try:
        svc = LoanWriteOffService(session)
        result = await svc.recover(
            loan_id=loan_id,
            amount=body.amount,
            reason=body.reason,
            actor_id=user.id,
            idempotency_key=body.idempotency_key,
        )
        await session.commit()
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanRecoveryOut(**result)


# ── Query endpoints ───────────────────────────────────────────────────────────


@router.get("/query/loans-eligible-for-fee", response_model=list[dict[str, Any]])
async def loans_eligible_for_fee(
    session: Session,
    user: CurrentTenantUser,
    min_days_past_due: int = 0,
) -> list[dict[str, Any]]:
    from app.modules.credit.services.query import CreditQueryService
    svc = CreditQueryService(session)
    return await svc.find_loans_eligible_for_fee(
        as_of_date=date.today(),
        min_days_past_due=min_days_past_due,
    )


# ── Guarantor endpoints ───────────────────────────────────────────────────────


@router.post("/applications/{application_id}/guarantors", status_code=201)
async def nominate_guarantors(
    application_id: uuid.UUID,
    body: GuarantorNominateIn,
    session: Session,
    user: CurrentTenantUser,
) -> list[GuarantorOut]:
    try:
        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application_id,
            guarantor_member_ids=body.guarantor_member_ids,
            actor_id=user.id,
        )
        await session.commit()
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return [GuarantorOut.model_validate(g) for g in guarantors]


@router.get("/applications/{application_id}/guarantors")
async def list_guarantors(
    application_id: uuid.UUID,
    session: Session,
    user: CurrentTenantUser,
) -> list[GuarantorOut]:
    from app.modules.credit.models import LoanGuarantor
    result = await session.execute(
        _select(LoanGuarantor).where(LoanGuarantor.loan_application_id == application_id)
    )
    return [GuarantorOut.model_validate(g) for g in result.scalars().all()]


@router.post("/guarantors/{guarantor_id}/accept")
async def accept_guarantor(
    guarantor_id: uuid.UUID,
    body: GuarantorConsentIn,
    session: Session,
    user: CurrentTenantUser,
) -> GuarantorOut:
    try:
        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        g = await svc.accept(
            loan_guarantor_id=guarantor_id,
            guarantor_member_id=body.guarantor_member_id,
        )
        await session.commit()
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return GuarantorOut.model_validate(g)


@router.post("/guarantors/{guarantor_id}/decline")
async def decline_guarantor(
    guarantor_id: uuid.UUID,
    body: GuarantorConsentIn,
    session: Session,
    user: CurrentTenantUser,
) -> GuarantorOut:
    try:
        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        g = await svc.decline(
            loan_guarantor_id=guarantor_id,
            guarantor_member_id=body.guarantor_member_id,
        )
        await session.commit()
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return GuarantorOut.model_validate(g)


# ── Restructuring endpoints ───────────────────────────────────────────────────


@router.post("/loans/{loan_id}/restructure", status_code=202)
async def restructure_loan(
    loan_id: uuid.UUID,
    body: RestructureIn,
    session: Session,
    user: CurrentTenantUser,
) -> dict[str, str]:
    """Submit a loan restructuring for maker-checker approval (quorum=2)."""
    try:
        svc = LoanRestructuringService(session)
        result = await svc.restructure(
            loan_id=loan_id,
            restructuring_type=body.restructuring_type,
            periods_added=body.periods_added,
            reason=body.reason,
            actor_id=user.id,
            idempotency_key=body.idempotency_key,
        )
        await session.commit()
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return {"approval_request_id": str(result["approval_request_id"])}


@router.get("/loans/{loan_id}/restructurings")
async def list_restructurings(
    loan_id: uuid.UUID,
    session: Session,
    user: CurrentTenantUser,
) -> list[RestructuringOut]:
    """List all executed restructurings for a loan."""
    from app.modules.credit.models import LoanRestructuring  # noqa: PLC0415
    result = await session.execute(
        _select(LoanRestructuring)
        .where(LoanRestructuring.loan_id == loan_id)
        .order_by(LoanRestructuring.executed_at)
    )
    return [RestructuringOut.model_validate(r) for r in result.scalars().all()]


# ── Payroll batch endpoints ───────────────────────────────────────────────────


@router.post("/payroll-batches", status_code=201)
async def submit_payroll_batch_json(
    body: PayrollBatchJsonIn,
    session: Session,
    user: CurrentTenantUser,
) -> PayrollBatchOut:
    from app.modules.credit.services.payroll import PayrollBatchService  # noqa: PLC0415
    svc = PayrollBatchService(session)
    rows = [{"member_id": r.member_id, "amount": str(r.amount)} for r in body.rows]
    try:
        batch = await svc.submit_batch(
            rows=rows,
            source_format="json",
            actor_id=user.id,
            idempotency_key=body.idempotency_key,
            clearing_account_id=body.clearing_account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PayrollBatchOut.model_validate(batch)


@router.post("/payroll-batches/csv", status_code=201)
async def submit_payroll_batch_csv(
    file: UploadFile,
    clearing_account_id: uuid.UUID,
    idempotency_key: str,
    session: Session,
    user: CurrentTenantUser,
) -> PayrollBatchOut:
    from app.modules.credit.services.payroll import PayrollBatchService  # noqa: PLC0415
    svc = PayrollBatchService(session)
    contents = await file.read()
    try:
        batch = await svc.submit_batch_csv(
            csv_bytes=contents,
            actor_id=user.id,
            idempotency_key=idempotency_key,
            clearing_account_id=clearing_account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PayrollBatchOut.model_validate(batch)


@router.get("/payroll-batches/{batch_id}")
async def get_payroll_batch(
    batch_id: uuid.UUID,
    session: Session,
    user: CurrentTenantUser,
) -> PayrollBatchOut:
    from app.modules.credit.models import PayrollBatch  # noqa: PLC0415
    batch = await session.get(PayrollBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Payroll batch not found")
    return PayrollBatchOut.model_validate(batch)


@router.post("/payroll-batches/{batch_id}/reject")
async def reject_payroll_batch(
    batch_id: uuid.UUID,
    session: Session,
    user: CurrentTenantUser,
) -> PayrollBatchOut:
    from app.modules.credit.models import PayrollBatch  # noqa: PLC0415
    batch = await session.scalar(
        _select(PayrollBatch).where(PayrollBatch.id == batch_id).with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Payroll batch not found")
    if batch.status != "pending_review":
        raise HTTPException(status_code=409, detail=f"Batch status is '{batch.status}'")
    batch.status = "rejected"
    batch.approved_by = user.id
    return PayrollBatchOut.model_validate(batch)


# ── Loan Statements ───────────────────────────────────────────────────────────


@router.get("/loans/{loan_id}/statement", response_model=LoanStatementOut)
async def get_loan_statement(
    loan_id: uuid.UUID,
    session: Session,
    user: CurrentTenantUser,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
) -> LoanStatementOut:
    """Return JSON loan statement with running balance."""
    from app.modules.credit.services.statement import LoanStatementService  # noqa: PLC0415
    svc = LoanStatementService(session)
    lines = await svc.get_statement(loan_id=loan_id, from_date=from_date, to_date=to_date)
    return LoanStatementOut(
        loan_id=loan_id,
        from_date=from_date,
        to_date=to_date,
        lines=[
            StatementLineOut(
                date=line.date,
                line_type=line.line_type,
                description=line.description,
                debit=line.debit,
                credit=line.credit,
                running_balance=line.running_balance,
            )
            for line in lines
        ],
    )


@router.get("/loans/{loan_id}/statement.pdf")
async def get_loan_statement_pdf(
    loan_id: uuid.UUID,
    session: Session,
    user: CurrentTenantUser,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
) -> Response:
    """Return PDF loan statement."""
    from fastapi.responses import Response as FastAPIResponse  # noqa: PLC0415

    from app.modules.credit.services.statement import LoanStatementService  # noqa: PLC0415
    svc = LoanStatementService(session)
    pdf_bytes = await svc.render_pdf(loan_id=loan_id, from_date=from_date, to_date=to_date)
    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="statement-{loan_id}.pdf"'},
    )
