"""Tests for LoanWriteOffService.recover()."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.credit.models import Loan

# Import helpers from existing test_service
from tests.modules.credit.test_service import (
    _new_session,
    _setup_disbursement_accounts,
    _make_disbursed_loan,
    _cleanup,
)


async def _make_written_off_loan(test_engine: AsyncEngine, accounts: dict) -> Loan:
    """Set up a loan in written_off status with total_written_off populated."""
    from app.modules.credit.services.write_off import LoanWriteOffService
    from app.modules.credit.models import LoanProduct

    # First create a disbursed loan
    loan = await _make_disbursed_loan(test_engine, accounts)

    # Set write_off_threshold high so write-off is direct (no maker-checker)
    session = await _new_session(test_engine)
    try:
        product = await session.get(LoanProduct, loan.loan_product_id)
        product.write_off_threshold = Decimal("999999.00")
        await session.commit()
    finally:
        await session.close()

    # Write off the full outstanding principal
    session = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session)
        await svc.write_off(
            loan_id=loan.id,
            amount=loan.outstanding_principal,
            reason="Setup for recovery test",
            actor_id=accounts["actor"],
            idempotency_key=f"setup-wo-{loan.id}",
        )
        await session.commit()
    finally:
        await session.close()

    # Reload to get updated state
    session = await _new_session(test_engine)
    try:
        loan_updated = await session.get(Loan, loan.id)
        return loan_updated
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_recover_restores_principal(test_engine: AsyncEngine) -> None:
    """Recovery posts GL entry and restores outstanding_principal."""
    from app.modules.credit.services.write_off import LoanWriteOffService

    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_written_off_loan(test_engine, accounts)
    recovery_amount = loan.total_written_off  # recover all of it

    session = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session)
        result = await svc.recover(
            loan_id=loan.id,
            amount=recovery_amount,
            reason="Partial recovery from debtor",
            actor_id=accounts["actor"],
            idempotency_key="test-rec-001",
        )
        await session.commit()
    finally:
        await session.close()

    session = await _new_session(test_engine)
    try:
        refreshed = await session.get(Loan, loan.id)
        assert refreshed.outstanding_principal == recovery_amount
        assert refreshed.total_written_off == Decimal("0")
        assert refreshed.status == "in_arrears"
        assert result["journal_entry_id"] is not None
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_recover_on_non_written_off_loan_raises(test_engine: AsyncEngine) -> None:
    """recover() on a non-written_off loan raises ValueError."""
    from app.modules.credit.services.write_off import LoanWriteOffService

    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts)

    session = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session)
        with pytest.raises(ValueError, match="written_off"):
            await svc.recover(
                loan_id=loan.id,
                amount=Decimal("50000"),
                reason="test",
                actor_id=accounts["actor"],
                idempotency_key="test-rec-002",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_recover_exceeds_written_off_raises(test_engine: AsyncEngine) -> None:
    """recover() with amount > total_written_off raises ValueError."""
    from app.modules.credit.services.write_off import LoanWriteOffService

    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_written_off_loan(test_engine, accounts)

    session = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session)
        with pytest.raises(ValueError, match="exceeds"):
            await svc.recover(
                loan_id=loan.id,
                amount=loan.total_written_off + Decimal("1"),
                reason="test",
                actor_id=accounts["actor"],
                idempotency_key="test-rec-003",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_recover_gl_balanced(test_engine: AsyncEngine) -> None:
    """Recovery GL: Dr principal_receivable / Cr loan_loss_expense — balanced."""
    from app.modules.credit.services.write_off import LoanWriteOffService
    from app.modules.ledger.models import JournalLine

    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_written_off_loan(test_engine, accounts)

    session = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session)
        result = await svc.recover(
            loan_id=loan.id,
            amount=Decimal("50000"),
            reason="test gl balance",
            actor_id=accounts["actor"],
            idempotency_key="test-rec-004",
        )
        await session.commit()
    finally:
        await session.close()

    session = await _new_session(test_engine)
    try:
        lines = (
            await session.scalars(
                select(JournalLine).where(
                    JournalLine.journal_entry_id == result["journal_entry_id"]
                )
            )
        ).all()
        total_debit = sum(ln.debit_amount for ln in lines)
        total_credit = sum(ln.credit_amount for ln in lines)
        assert total_debit == total_credit
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_recover_idempotent(test_engine: AsyncEngine) -> None:
    """Same idempotency_key twice → no duplicate GL entry."""
    from app.modules.credit.services.write_off import LoanWriteOffService
    from app.modules.ledger.models import JournalEntry

    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_written_off_loan(test_engine, accounts)

    idem_key = "test-rec-idem"

    session = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session)
        r1 = await svc.recover(
            loan_id=loan.id,
            amount=Decimal("50000"),
            reason="first",
            actor_id=accounts["actor"],
            idempotency_key=idem_key,
        )
        await session.commit()
    finally:
        await session.close()

    session = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session)
        r2 = await svc.recover(
            loan_id=loan.id,
            amount=Decimal("50000"),
            reason="second",
            actor_id=accounts["actor"],
            idempotency_key=idem_key,
        )
        await session.commit()
    finally:
        await session.close()

    assert r1["journal_entry_id"] == r2["journal_entry_id"]

    session = await _new_session(test_engine)
    try:
        entries = (
            await session.scalars(
                select(JournalEntry).where(
                    JournalEntry.idempotency_key == f"loan-wor-{idem_key}"
                )
            )
        ).all()
        assert len(entries) == 1
    finally:
        await session.close()
        await _cleanup(test_engine)
