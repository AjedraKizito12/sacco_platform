# app/modules/credit/schemas.py
"""Pydantic v2 schemas for the credit module.

Organised by sub-resource. Additional schemas are appended in subsequent
sub-plans: applications (03), disbursement (04), repayment (07), write-off (10).
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    import uuid
    from datetime import datetime


# ── Loan Products ─────────────────────────────────────────────────────────────


class LoanProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    interest_method: str
    annual_interest_rate: Decimal
    repayment_frequency: str
    max_term_periods: int
    min_amount: Decimal
    max_amount: Decimal
    required_approvals: int
    disbursement_destinations: list[str]
    repayment_allocation: str
    gl_principal_receivable_code: str
    gl_interest_receivable_code: str
    gl_interest_income_code: str
    gl_loan_loss_expense_code: str | None
    penalty_fee_type_code: str | None
    write_off_threshold: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoanProductCreateIn(BaseModel):
    name: str
    description: str | None = None
    interest_method: str
    annual_interest_rate: Decimal
    repayment_frequency: str
    max_term_periods: int
    min_amount: Decimal
    max_amount: Decimal
    required_approvals: int = 1
    disbursement_destinations: list[str]
    repayment_allocation: str = "INTEREST_PRINCIPAL"
    gl_principal_receivable_code: str
    gl_interest_receivable_code: str
    gl_interest_income_code: str
    gl_loan_loss_expense_code: str | None = None
    penalty_fee_type_code: str | None = None
    write_off_threshold: Decimal = Decimal("0")


class LoanProductPatchIn(BaseModel):
    name: str | None = None
    description: str | None = None
    penalty_fee_type_code: str | None = None
    write_off_threshold: Decimal | None = None


# ── Application schemas ───────────────────────────────────────────────────────


class LoanApplicationCreateIn(BaseModel):
    loan_product_id: uuid.UUID
    member_id: uuid.UUID
    requested_amount: Decimal
    requested_term_periods: int
    purpose: str | None = None
    disbursement_destination: str
    disbursement_account_id: uuid.UUID | None = None
    idempotency_key: str


class LoanApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_product_id: uuid.UUID
    member_id: uuid.UUID
    requested_amount: Decimal
    requested_term_periods: int
    approved_amount: Decimal | None
    approved_term_periods: int | None
    purpose: str | None
    disbursement_destination: str
    disbursement_account_id: uuid.UUID | None
    status: str
    rejection_reason: str | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    approval_request_id: uuid.UUID | None
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
