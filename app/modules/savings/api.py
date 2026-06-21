from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.iam.dependencies import CurrentTenantUser
from app.modules.savings.schemas import (
    DepositIn,
    OpenAccountIn,
    SavingsAccountOut,
    SavingsAccountWithBalanceOut,
    SavingsProductIn,
    SavingsProductOut,
    SavingsTransactionOut,
    WithdrawalOut,
    WithdrawIn,
)
from app.modules.savings.service import SavingsService

router = APIRouter(prefix="/savings", tags=["savings"])

Session = Annotated[AsyncSession, Depends(get_tenant_session)]


# ── Savings Products ──────────────────────────────────────────────────────────


@router.post("/products", response_model=SavingsProductOut, status_code=201)
async def create_product(
    body: SavingsProductIn, session: Session, user: CurrentTenantUser
) -> SavingsProductOut:
    svc = SavingsService(session)
    try:
        product = await svc.create_product(
            name=body.name,
            interest_rate=body.interest_rate,
            liability_account_id=body.liability_account_id,
            minimum_balance=body.minimum_balance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SavingsProductOut.model_validate(product)


@router.get("/products", response_model=list[SavingsProductOut])
async def list_products(
    session: Session, user: CurrentTenantUser, include_inactive: bool = False
) -> list[SavingsProductOut]:
    svc = SavingsService(session)
    products = await svc.list_products(include_inactive=include_inactive)
    return [SavingsProductOut.model_validate(p) for p in products]


@router.get("/products/{product_id}", response_model=SavingsProductOut)
async def get_product(
    product_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> SavingsProductOut:
    svc = SavingsService(session)
    try:
        product = await svc.get_product(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SavingsProductOut.model_validate(product)


# ── Savings Accounts ──────────────────────────────────────────────────────────


@router.post("/accounts", response_model=SavingsAccountOut, status_code=201)
async def open_account(
    body: OpenAccountIn, session: Session, user: CurrentTenantUser
) -> SavingsAccountOut:
    svc = SavingsService(session)
    try:
        account = await svc.open_account(
            member_id=body.member_id,
            savings_product_id=body.savings_product_id,
        )
    except ValueError as exc:
        if "already exists" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SavingsAccountOut.model_validate(account)


@router.get("/accounts", response_model=list[SavingsAccountOut])
async def list_accounts(
    session: Session,
    user: CurrentTenantUser,
    member_id: uuid.UUID | None = None,
) -> list[SavingsAccountOut]:
    svc = SavingsService(session)
    accounts = await svc.list_accounts(member_id=member_id)
    return [SavingsAccountOut.model_validate(a) for a in accounts]


@router.get("/accounts/{account_id}", response_model=SavingsAccountWithBalanceOut)
async def get_account(
    account_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> SavingsAccountWithBalanceOut:
    svc = SavingsService(session)
    try:
        account = await svc.get_account(account_id)
        balance = await svc.get_balance(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    account_dict = SavingsAccountOut.model_validate(account).model_dump()
    account_dict["balance"] = balance
    return SavingsAccountWithBalanceOut.model_validate(account_dict)


@router.get(
    "/accounts/{account_id}/transactions",
    response_model=list[SavingsTransactionOut],
)
async def list_transactions(
    account_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> list[SavingsTransactionOut]:
    svc = SavingsService(session)
    try:
        txns = await svc.list_transactions(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [SavingsTransactionOut.model_validate(t) for t in txns]


@router.post(
    "/accounts/{account_id}/deposit",
    response_model=SavingsTransactionOut,
    status_code=201,
)
async def deposit(
    account_id: uuid.UUID,
    body: DepositIn,
    session: Session,
    user: CurrentTenantUser,
) -> SavingsTransactionOut:
    svc = SavingsService(session)
    try:
        txn = await svc.deposit(
            savings_account_id=account_id,
            amount=body.amount,
            payment_account_id=body.payment_account_id,
            posted_by=user.id,
            idempotency_key=body.idempotency_key,
            narration=body.narration,
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SavingsTransactionOut.model_validate(txn)


@router.post(
    "/accounts/{account_id}/withdraw",
    response_model=WithdrawalOut,
    status_code=202,
)
async def submit_withdrawal(
    account_id: uuid.UUID,
    body: WithdrawIn,
    session: Session,
    user: CurrentTenantUser,
) -> WithdrawalOut:
    svc = SavingsService(session)
    try:
        approval_id = await svc.submit_withdrawal(
            savings_account_id=account_id,
            amount=body.amount,
            payment_account_id=body.payment_account_id,
            submitted_by=user.id,
            idempotency_key=body.idempotency_key,
            narration=body.narration,
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WithdrawalOut(approval_request_id=approval_id, status="pending")
