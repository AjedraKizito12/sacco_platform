from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


AccountType = Literal["asset", "liability", "equity", "income", "expense"]


# ── Request schemas ───────────────────────────────────────────────────────────

class AccountIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    account_type: AccountType
    parent_id: uuid.UUID | None = None
    description: str | None = None


class JournalLineIn(BaseModel):
    account_id: uuid.UUID
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")
    description: str | None = None


class ManualGLSubmitIn(BaseModel):
    reference: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1, max_length=200)
    lines: list[JournalLineIn] = Field(..., min_length=2)


# ── Response schemas ──────────────────────────────────────────────────────────

class AccountOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    account_type: str
    parent_id: uuid.UUID | None
    is_active: bool
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountWithBalanceOut(AccountOut):
    balance: Decimal


class JournalLineOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    debit_amount: Decimal
    credit_amount: Decimal
    description: str | None

    model_config = {"from_attributes": True}


class JournalEntryOut(BaseModel):
    id: uuid.UUID
    reference: str
    description: str
    posted_by: uuid.UUID
    posted_at: datetime
    idempotency_key: str
    lines: list[JournalLineOut] = []

    model_config = {"from_attributes": True}


class ManualGLSubmitOut(BaseModel):
    approval_request_id: uuid.UUID
    status: str
