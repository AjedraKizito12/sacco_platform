from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class FeeTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    applicable_to: str
    amount_kind: str
    amount: Decimal
    currency: str
    trigger_kind: str
    event_name: str | None
    schedule_config: dict[str, Any] | None
    gl_income_account_code: str
    gl_receivable_account_code: str
    is_active: bool
    requires_collection: bool


class FeeTypeCreateIn(BaseModel):
    code: str
    name: str
    description: str | None = None
    applicable_to: str
    amount_kind: str = "fixed"
    amount: Decimal
    currency: str
    trigger_kind: str
    event_name: str | None = None
    schedule_config: dict[str, Any] | None = None
    gl_income_account_code: str
    gl_receivable_account_code: str
    requires_collection: bool = False


class FeeTypePatchIn(BaseModel):
    name: str | None = None
    description: str | None = None
    amount: Decimal | None = None
    is_active: bool | None = None
    requires_collection: bool | None = None


class FeeAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fee_type_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    period_start: date
    period_end: date | None
    amount: Decimal
    currency: str
    status: str
    assessed_at: datetime
    due_at: datetime | None
    paid_at: datetime | None
    journal_entry_id: uuid.UUID


class FeeAssessmentCreateIn(BaseModel):
    fee_type_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    period_start: date
    period_end: date | None = None


class FeeCollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fee_assessment_id: uuid.UUID
    amount: Decimal
    collected_at: datetime
    method: str
    collected_by: uuid.UUID
    journal_entry_id: uuid.UUID
    idempotency_key: str


class FeeCollectionCreateIn(BaseModel):
    fee_assessment_id: uuid.UUID
    amount: Decimal
    method: str  # cash | journal_voucher  (savings_deduction is auto only)
    contra_account_id: uuid.UUID  # required for cash/journal_voucher
    idempotency_key: str


class FeeAssessmentDetailOut(FeeAssessmentOut):
    collections: list[FeeCollectionOut] = []
