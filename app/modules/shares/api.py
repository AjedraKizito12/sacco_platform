from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.iam.dependencies import CurrentTenantUser
from app.modules.shares.schemas import (
    OpenAccountIn,
    PurchaseSharesIn,
    RedeemSharesIn,
    RedemptionOut,
    ShareAccountListItemOut,
    ShareAccountOut,
    ShareAccountWithBalanceOut,
    ShareProductIn,
    ShareProductOut,
    ShareTransactionOut,
)
from app.modules.shares.service import ShareService

router = APIRouter(prefix="/shares", tags=["shares"])

Session = Annotated[AsyncSession, Depends(get_tenant_session)]


# ── Share Products ────────────────────────────────────────────────────────────


@router.post("/products", response_model=ShareProductOut, status_code=201)
async def create_product(
    body: ShareProductIn, session: Session, user: CurrentTenantUser
) -> ShareProductOut:
    svc = ShareService(session)
    try:
        product = await svc.create_product(
            name=body.name,
            par_value=body.par_value,
            share_capital_account_id=body.share_capital_account_id,
            minimum_shares=body.minimum_shares,
            maximum_shares=body.maximum_shares,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ShareProductOut.model_validate(product)


@router.get("/products", response_model=list[ShareProductOut])
async def list_products(
    session: Session, user: CurrentTenantUser, include_inactive: bool = False
) -> list[ShareProductOut]:
    svc = ShareService(session)
    products = await svc.list_products(include_inactive=include_inactive)
    return [ShareProductOut.model_validate(p) for p in products]


@router.get("/products/{product_id}", response_model=ShareProductOut)
async def get_product(
    product_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> ShareProductOut:
    svc = ShareService(session)
    try:
        product = await svc.get_product(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ShareProductOut.model_validate(product)


# ── Member Share Accounts ─────────────────────────────────────────────────────


@router.post("/accounts", response_model=ShareAccountOut, status_code=201)
async def open_account(
    body: OpenAccountIn, session: Session, user: CurrentTenantUser
) -> ShareAccountOut:
    svc = ShareService(session)
    try:
        account = await svc.open_account(
            member_id=body.member_id,
            share_product_id=body.share_product_id,
        )
    except ValueError as exc:
        if "already exists" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ShareAccountOut.model_validate(account)


@router.get("/accounts", response_model=list[ShareAccountListItemOut])
async def list_accounts(
    session: Session,
    user: CurrentTenantUser,
    member_id: uuid.UUID | None = None,
) -> list[ShareAccountListItemOut]:
    svc = ShareService(session)
    items = await svc.list_accounts(member_id=member_id)
    return [ShareAccountListItemOut.model_validate(i) for i in items]


@router.get("/accounts/{account_id}", response_model=ShareAccountWithBalanceOut)
async def get_account(
    account_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> ShareAccountWithBalanceOut:
    svc = ShareService(session)
    try:
        account = await svc.get_account(account_id)
        shares_held, total_value = await svc.get_balance(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    account_dict = ShareAccountOut.model_validate(account).model_dump()
    account_dict["shares_held"] = shares_held
    account_dict["total_value"] = total_value
    return ShareAccountWithBalanceOut.model_validate(account_dict)


@router.get("/accounts/{account_id}/transactions", response_model=list[ShareTransactionOut])
async def list_transactions(
    account_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> list[ShareTransactionOut]:
    svc = ShareService(session)
    try:
        txns = await svc.list_transactions(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [ShareTransactionOut.model_validate(t) for t in txns]


@router.post("/accounts/{account_id}/purchase", response_model=ShareTransactionOut, status_code=201)
async def purchase_shares(
    account_id: uuid.UUID,
    body: PurchaseSharesIn,
    session: Session,
    user: CurrentTenantUser,
) -> ShareTransactionOut:
    svc = ShareService(session)
    try:
        txn = await svc.purchase_shares(
            share_account_id=account_id,
            quantity=body.quantity,
            payment_account_id=body.payment_account_id,
            posted_by=user.id,
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ShareTransactionOut.model_validate(txn)


@router.post("/accounts/{account_id}/redeem", response_model=RedemptionOut, status_code=202)
async def submit_redemption(
    account_id: uuid.UUID,
    body: RedeemSharesIn,
    session: Session,
    user: CurrentTenantUser,
) -> RedemptionOut:
    svc = ShareService(session)
    try:
        approval_id = await svc.submit_redemption(
            share_account_id=account_id,
            quantity=body.quantity,
            payment_account_id=body.payment_account_id,
            submitted_by=user.id,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedemptionOut(approval_request_id=approval_id, status="pending")
