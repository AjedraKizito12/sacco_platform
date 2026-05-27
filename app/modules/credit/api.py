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
    LoanProductCreateIn,
    LoanProductOut,
    LoanProductPatchIn,
)
from app.modules.credit.services.product import LoanProductService

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
