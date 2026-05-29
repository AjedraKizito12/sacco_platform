# app/modules/reporting/schemas.py
"""Pydantic response schemas for the reporting module."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ── ReportRun ──────────────────────────────────────────────────────────────────

class ReportRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_type: str
    as_of_date: date
    status: str
    started_at: datetime
    completed_at: datetime | None
    error_detail: str | None


# ── Trial Balance ──────────────────────────────────────────────────────────────

class TrialBalanceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    debit_total: Decimal
    credit_total: Decimal
    balance: Decimal


class TrialBalanceOut(BaseModel):
    as_of_date: date
    generated_at: datetime
    lines: list[TrialBalanceLineOut]


# ── Loan Portfolio ─────────────────────────────────────────────────────────────

class LoanPortfolioRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    loan_id: uuid.UUID
    loan_reference: str
    member_id: uuid.UUID
    product_name: str
    disbursed_at: date
    maturity_date: date | None
    status: str
    outstanding_principal: Decimal
    accrued_interest: Decimal
    total_written_off: Decimal
    days_in_arrears: int
    aging_bucket: str


class LoanPortfolioOut(BaseModel):
    as_of_date: date
    generated_at: datetime
    rows: list[LoanPortfolioRowOut]


# ── Income Statement ───────────────────────────────────────────────────────────

class IncomeStatementLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    debit_total: Decimal
    credit_total: Decimal
    net_movement: Decimal


class IncomeStatementOut(BaseModel):
    period_start: date
    period_end: date
    generated_at: datetime
    lines: list[IncomeStatementLineOut]


# ── Savings Statement ──────────────────────────────────────────────────────────

class SavingsStatementLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    savings_account_id: uuid.UUID
    member_id: uuid.UUID
    posted_at: datetime
    transaction_type: str
    narration: str | None
    amount: Decimal
    running_balance: Decimal


class SavingsStatementOut(BaseModel):
    member_id: uuid.UUID
    period_start: date
    period_end: date
    generated_at: datetime
    lines: list[SavingsStatementLineOut]


# ── Fee Collection ─────────────────────────────────────────────────────────────

class FeeCollectionRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fee_type_id: uuid.UUID
    fee_type_name: str
    target_type: str
    assessed_total: Decimal
    collected_total: Decimal
    outstanding_total: Decimal
    waived_total: Decimal


class FeeCollectionOut(BaseModel):
    period_start: date
    period_end: date
    generated_at: datetime
    rows: list[FeeCollectionRowOut]
