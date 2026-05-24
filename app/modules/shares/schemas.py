from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ── Request schemas ───────────────────────────────────────────────────────────

class ShareProductIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    par_value: Decimal = Field(..., gt=0)
    minimum_shares: int = Field(default=1, ge=1)
    maximum_shares: int | None = None
    share_capital_account_id: uuid.UUID


class OpenAccountIn(BaseModel):
    member_id: uuid.UUID
    share_product_id: uuid.UUID


class PurchaseSharesIn(BaseModel):
    quantity: int = Field(..., ge=1)
    payment_account_id: uuid.UUID  # cash/bank account to debit
    idempotency_key: str = Field(..., min_length=1, max_length=200)


class RedeemSharesIn(BaseModel):
    quantity: int = Field(..., ge=1)
    payment_account_id: uuid.UUID  # cash/bank account to credit
    reason: str | None = None
    idempotency_key: str = Field(..., min_length=1, max_length=200)


# ── Response schemas ──────────────────────────────────────────────────────────

class ShareProductOut(BaseModel):
    id: uuid.UUID
    name: str
    par_value: Decimal
    minimum_shares: int
    maximum_shares: int | None
    share_capital_account_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShareAccountOut(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    share_product_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShareAccountWithBalanceOut(ShareAccountOut):
    shares_held: int
    total_value: Decimal


class ShareTransactionOut(BaseModel):
    id: uuid.UUID
    share_account_id: uuid.UUID
    transaction_type: str
    quantity: int
    amount: Decimal
    journal_entry_id: uuid.UUID
    posted_by: uuid.UUID
    posted_at: datetime
    idempotency_key: str

    model_config = {"from_attributes": True}


class RedemptionOut(BaseModel):
    approval_request_id: uuid.UUID
    status: str
