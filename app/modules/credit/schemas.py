# app/modules/credit/schemas.py
"""Pydantic v2 schemas for the credit module.

Organised by sub-resource. Additional schemas are appended in subsequent
sub-plans: applications (03), disbursement (04), repayment (07), write-off (10).
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import uuid
    from datetime import date, datetime


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
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
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


class LoanApplicationApproveIn(BaseModel):
    comment: str | None = None


class LoanApplicationRejectIn(BaseModel):
    reason: str | None = None


# ── Disbursement schemas ──────────────────────────────────────────────────────


class LoanInstallmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_id: uuid.UUID
    period_number: int
    due_date: date
    principal_due: Decimal
    interest_due: Decimal
    total_due: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    status: str
    paid_at: datetime | None


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_reference: str
    loan_application_id: uuid.UUID
    loan_product_id: uuid.UUID
    member_id: uuid.UUID
    status: str
    principal_amount: Decimal
    outstanding_principal: Decimal
    accrued_interest: Decimal
    accrued_penalties: Decimal
    annual_interest_rate: Decimal
    interest_method: str
    repayment_frequency: str
    term_periods: int
    disbursement_destination: str
    first_repayment_due: date | None
    maturity_date: date | None
    disbursed_at: datetime | None
    created_at: datetime


class DisburseIn(BaseModel):
    idempotency_key: str


# ── Repayment schemas ─────────────────────────────────────────────────────────


class LoanRepaymentCreateIn(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    payment_account_id: uuid.UUID
    narration: str | None = None
    idempotency_key: str
    savings_account_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class LoanRepaymentOut(BaseModel):
    id: uuid.UUID
    loan_id: uuid.UUID
    amount: Decimal
    principal_applied: Decimal
    interest_applied: Decimal
    penalties_applied: Decimal
    overpayment: Decimal
    payment_account_id: uuid.UUID
    journal_entry_id: uuid.UUID
    posted_by: uuid.UUID
    narration: str | None
    idempotency_key: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Write-off schemas ─────────────────────────────────────────────────────────


class WriteOffIn(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    reason: str
    idempotency_key: str
    loan_loss_account_code: str = "5100"

    model_config = ConfigDict(from_attributes=True)


class WriteOffOut(BaseModel):
    direct: bool
    approval_request_id: uuid.UUID | None
    journal_entry_id: uuid.UUID | None

    model_config = ConfigDict(from_attributes=True)
