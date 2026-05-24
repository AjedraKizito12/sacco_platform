from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.ledger.schemas import (
    AccountIn,
    AccountOut,
    AccountWithBalanceOut,
    JournalEntryOut,
    ManualGLSubmitIn,
    ManualGLSubmitOut,
)
from app.modules.ledger.service import LedgerService

router = APIRouter(prefix="/ledger", tags=["ledger"])

Session = Annotated[AsyncSession, Depends(get_tenant_session)]


# ── Chart of Accounts ─────────────────────────────────────────────────────────


@router.post("/accounts", response_model=AccountOut, status_code=201)
async def create_account(body: AccountIn, session: Session) -> AccountOut:
    svc = LedgerService(session)
    try:
        account = await svc.create_account(
            code=body.code,
            name=body.name,
            account_type=body.account_type,
            created_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser actor
            parent_id=body.parent_id,
            description=body.description,
        )
    except ValueError as exc:
        if "already exists" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AccountOut.model_validate(account)


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(session: Session, include_inactive: bool = False) -> list[AccountOut]:
    svc = LedgerService(session)
    accounts = await svc.list_accounts(include_inactive=include_inactive)
    return [AccountOut.model_validate(a) for a in accounts]


@router.get("/accounts/{account_id}", response_model=AccountWithBalanceOut)
async def get_account(account_id: uuid.UUID, session: Session) -> AccountWithBalanceOut:
    svc = LedgerService(session)
    try:
        account = await svc.get_account(account_id)
        balance = await svc.get_account_balance(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    account_dict = AccountOut.model_validate(account).model_dump()
    account_dict["balance"] = balance
    return AccountWithBalanceOut.model_validate(account_dict)


# ── Journal Entries ───────────────────────────────────────────────────────────


@router.post("/journal-entries/submit", response_model=ManualGLSubmitOut, status_code=202)
async def submit_manual_entry(body: ManualGLSubmitIn, session: Session) -> ManualGLSubmitOut:
    svc = LedgerService(session)
    lines = [
        {
            "account_id": str(ln.account_id),
            "debit_amount": str(ln.debit_amount),
            "credit_amount": str(ln.credit_amount),
            "description": ln.description,
        }
        for ln in body.lines
    ]
    try:
        approval_id = await svc.submit_manual_entry(
            reference=body.reference,
            description=body.description,
            submitted_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser actor
            idempotency_key=body.idempotency_key,
            lines=lines,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ManualGLSubmitOut(approval_request_id=approval_id, status="pending")


@router.get("/journal-entries", response_model=list[JournalEntryOut])
async def list_journal_entries(session: Session) -> list[JournalEntryOut]:
    svc = LedgerService(session)
    entries = await svc.list_journal_entries()
    return [JournalEntryOut.model_validate(e) for e in entries]


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryOut)
async def get_journal_entry(entry_id: uuid.UUID, session: Session) -> JournalEntryOut:
    svc = LedgerService(session)
    try:
        entry = await svc.get_journal_entry(entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JournalEntryOut.model_validate(entry)
