from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    import uuid


class SavingsProductIn(BaseModel):
    name: str
    interest_rate: Decimal
    liability_account_id: uuid.UUID
    minimum_balance: Decimal = Decimal("0")


class SavingsProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    interest_rate: Decimal
    minimum_balance: Decimal
    liability_account_id: uuid.UUID
    is_active: bool


class OpenAccountIn(BaseModel):
    member_id: uuid.UUID
    savings_product_id: uuid.UUID


class SavingsAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    savings_product_id: uuid.UUID
    product_name: str
    interest_rate: Decimal
    minimum_balance: Decimal
    liability_account_id: uuid.UUID


class SavingsAccountWithBalanceOut(SavingsAccountOut):
    balance: Decimal


class DepositIn(BaseModel):
    amount: Decimal
    payment_account_id: uuid.UUID
    idempotency_key: str
    narration: str | None = None


class WithdrawIn(BaseModel):
    amount: Decimal
    payment_account_id: uuid.UUID
    idempotency_key: str
    narration: str | None = None


class SavingsTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    savings_account_id: uuid.UUID
    transaction_type: str
    amount: Decimal
    narration: str | None
    journal_entry_id: uuid.UUID
    posted_by: uuid.UUID


class WithdrawalOut(BaseModel):
    approval_request_id: uuid.UUID
    status: str
