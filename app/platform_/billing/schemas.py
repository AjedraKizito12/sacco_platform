from __future__ import annotations

import uuid  # noqa: TC003
from datetime import date, datetime  # noqa: TC003
from decimal import Decimal  # noqa: TC003
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── SubscriptionPlan ───────────────────────────────────────────────────────────


class SubscriptionPlanIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str
    description: str | None = None
    currency: str = "UGX"
    base_price: Decimal = Field(..., ge=Decimal("0"))
    per_user_price: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    per_member_price: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    billing_period: str = Field(..., pattern="^(monthly|quarterly|annual)$")
    member_limit: int | None = Field(default=None, ge=0)
    user_limit: int | None = Field(default=None, ge=0)
    features: dict[str, Any] = Field(default_factory=dict)
    trial_period_days: int = Field(default=0, ge=0)
    grace_period_days: int = Field(default=30, ge=0)
    is_active: bool = True


class SubscriptionPlanPatch(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=64)
    name: str | None = None
    description: str | None = None
    currency: str | None = None
    base_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    per_user_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    per_member_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    billing_period: str | None = Field(default=None, pattern="^(monthly|quarterly|annual)$")
    member_limit: int | None = Field(default=None, ge=0)
    user_limit: int | None = Field(default=None, ge=0)
    features: dict[str, Any] | None = None
    trial_period_days: int | None = Field(default=None, ge=0)
    grace_period_days: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class SubscriptionPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    currency: str
    base_price: Decimal
    per_user_price: Decimal
    per_member_price: Decimal
    billing_period: str
    member_limit: int | None
    user_limit: int | None
    features: dict[str, Any]
    trial_period_days: int
    grace_period_days: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Subscription ───────────────────────────────────────────────────────────────


class SubscriptionCreateIn(BaseModel):
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    start_date: date | None = None


class SubscriptionCancelIn(BaseModel):
    reason: str = Field(..., min_length=2)
    cancel_at_period_end: bool = True


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    started_at: datetime
    current_period_start: date
    current_period_end: date
    grace_period_ends_at: date | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    next_billing_date: date | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ── Invoice ────────────────────────────────────────────────────────────────────


class InvoiceLineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    description: str
    quantity: int
    unit_price: Decimal
    amount: Decimal
    line_order: int


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    subscription_id: uuid.UUID
    tenant_id: uuid.UUID
    billing_period_start: date
    billing_period_end: date
    amount_subtotal: Decimal
    amount_tax: Decimal
    amount_total: Decimal
    amount_paid: Decimal
    currency: str
    status: str
    issued_at: datetime | None
    due_at: date
    paid_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    pdf_storage_key: str | None
    created_at: datetime
    updated_at: datetime


class InvoiceDetailOut(InvoiceOut):
    line_items: list[InvoiceLineItemOut]


class InvoiceVoidIn(BaseModel):
    reason: str = Field(..., min_length=2)


# ── Payment ────────────────────────────────────────────────────────────────────


class PaymentRecordIn(BaseModel):
    amount: Decimal = Field(..., gt=Decimal("0"))
    currency: str = "UGX"
    payment_method: str = Field(..., pattern="^(bank_transfer|mobile_money|cash|cheque)$")
    external_reference: str | None = None
    notes: str | None = None
    idempotency_key: str = Field(..., min_length=8)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    amount: Decimal
    currency: str
    payment_method: str
    external_reference: str | None
    notes: str | None
    recorded_by: uuid.UUID
    recorded_at: datetime
    approval_request_id: uuid.UUID | None
    status: str
    confirmed_at: datetime | None
