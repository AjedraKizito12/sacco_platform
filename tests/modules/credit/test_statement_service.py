# tests/modules/credit/test_statement_service.py
"""Integration tests for LoanStatementService.

Uses test_engine + _new_session + _setup_disbursement_accounts + _make_disbursed_loan
helpers from tests/modules/credit/test_service.py.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.credit.services.statement import LoanStatementService
from app.modules.ledger.models import JournalEntry, JournalLine
from tests.modules.credit.test_service import (
    _cleanup,
    _make_disbursed_loan,
    _new_session,
    _setup_disbursement_accounts,
)

VALID_LINE_TYPES = frozenset(
    [
        "disbursement",
        "repayment",
        "interest_booked",
        "interest_accrual",
        "penalty_assessed",
        "write_off",
        "recovery",
        "other",
    ]
)


async def _add_journal_line(
    session,
    *,
    loan_id: uuid.UUID,
    account_id: uuid.UUID,
    reference: str,
    description: str,
    debit: Decimal,
    credit: Decimal,
    posted_at: datetime,
) -> JournalLine:
    """Insert a JournalEntry + one JournalLine tagged to a loan sub-ledger."""
    entry = JournalEntry(
        reference=reference,
        description=description,
        posted_by=uuid.uuid4(),
        posted_at=posted_at,
        idempotency_key=str(uuid.uuid4()),
    )
    session.add(entry)
    await session.flush()

    line = JournalLine(
        journal_entry_id=entry.id,
        account_id=account_id,
        debit_amount=debit,
        credit_amount=credit,
        sub_ledger_type="loan",
        sub_ledger_id=loan_id,
    )
    session.add(line)
    await session.flush()
    return line


@pytest.mark.asyncio
async def test_get_statement_returns_lines_in_order(test_engine: AsyncEngine):
    """Lines are returned in chronological order."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        t1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 2, 1, 0, 0, 0, tzinfo=UTC)

        await _add_journal_line(
            session,
            loan_id=loan.id,
            account_id=accounts["principal_recv_id"],
            reference="LOAN-DISB-001",
            description="Disbursement",
            debit=Decimal("120000"),
            credit=Decimal("0"),
            posted_at=t1,
        )
        await _add_journal_line(
            session,
            loan_id=loan.id,
            account_id=accounts["principal_recv_id"],
            reference="LOAN-REP-001",
            description="Repayment",
            debit=Decimal("0"),
            credit=Decimal("10000"),
            posted_at=t2,
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = LoanStatementService(session2)
        lines = await svc.get_statement(loan_id=loan.id)
        # Filter to only our test lines (disbursement created real GL lines too)
        # Order must be chronological
        dates = [ln.date for ln in lines]
        assert dates == sorted(dates)
        assert len(lines) >= 2
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_get_statement_running_balance_correct(test_engine: AsyncEngine):
    """running_balance accumulates: disbursement debit increases, repayment credit decreases."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    disb_amount = Decimal("120000")
    rep_amount = Decimal("10000")

    session = await _new_session(test_engine)
    try:
        t1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 2, 1, 0, 0, 0, tzinfo=UTC)

        await _add_journal_line(
            session,
            loan_id=loan.id,
            account_id=accounts["principal_recv_id"],
            reference="LOAN-DISB-BAL",
            description="Disbursement for balance test",
            debit=disb_amount,
            credit=Decimal("0"),
            posted_at=t1,
        )
        await _add_journal_line(
            session,
            loan_id=loan.id,
            account_id=accounts["principal_recv_id"],
            reference="LOAN-REP-BAL",
            description="Repayment for balance test",
            debit=Decimal("0"),
            credit=rep_amount,
            posted_at=t2,
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = LoanStatementService(session2)
        lines = await svc.get_statement(loan_id=loan.id)
        assert len(lines) >= 2
        # Final running balance should equal sum of all debits minus sum of all credits
        total_debits = sum(ln.debit for ln in lines)
        total_credits = sum(ln.credit for ln in lines)
        expected_final = total_debits - total_credits
        assert lines[-1].running_balance == expected_final
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_get_statement_date_filter(test_engine: AsyncEngine):
    """Date filter restricts lines to the specified range."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        t_jan = datetime(2026, 1, 15, 0, 0, 0, tzinfo=UTC)
        t_feb = datetime(2026, 2, 15, 0, 0, 0, tzinfo=UTC)
        t_mar = datetime(2026, 3, 15, 0, 0, 0, tzinfo=UTC)

        for ts, ref in [
            (t_jan, "LOAN-REP-JAN"),
            (t_feb, "LOAN-REP-FEB"),
            (t_mar, "LOAN-REP-MAR"),
        ]:
            await _add_journal_line(
                session,
                loan_id=loan.id,
                account_id=accounts["principal_recv_id"],
                reference=ref,
                description=f"Line {ref}",
                debit=Decimal("0"),
                credit=Decimal("1000"),
                posted_at=ts,
            )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = LoanStatementService(session2)
        lines = await svc.get_statement(
            loan_id=loan.id,
            from_date=date(2026, 2, 1),
            to_date=date(2026, 2, 28),
        )
        # Only the Feb line should be in the filtered result
        feb_lines = [ln for ln in lines if ln.date == date(2026, 2, 15)]
        assert len(feb_lines) >= 1
        # No lines outside Feb
        for ln in lines:
            assert date(2026, 2, 1) <= ln.date <= date(2026, 2, 28)
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_get_statement_empty_range(test_engine: AsyncEngine):
    """Date range with no matching transactions returns empty list."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        svc = LoanStatementService(session)
        lines = await svc.get_statement(
            loan_id=loan.id,
            from_date=date(2099, 1, 1),
            to_date=date(2099, 12, 31),
        )
        assert lines == []
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_get_statement_line_fields(test_engine: AsyncEngine):
    """Each line has all required fields with valid values."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        await _add_journal_line(
            session,
            loan_id=loan.id,
            account_id=accounts["principal_recv_id"],
            reference="LOAN-DISB-FIELD",
            description="Field test disbursement",
            debit=Decimal("50000"),
            credit=Decimal("0"),
            posted_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = LoanStatementService(session2)
        lines = await svc.get_statement(loan_id=loan.id)
        assert len(lines) >= 1
        for ln in lines:
            assert isinstance(ln.date, date)
            assert isinstance(ln.description, str)
            assert isinstance(ln.debit, Decimal)
            assert isinstance(ln.credit, Decimal)
            assert isinstance(ln.running_balance, Decimal)
            assert ln.line_type in VALID_LINE_TYPES
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_render_pdf_returns_bytes(test_engine: AsyncEngine):
    """render_pdf returns bytes starting with %PDF."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        await _add_journal_line(
            session,
            loan_id=loan.id,
            account_id=accounts["principal_recv_id"],
            reference="LOAN-DISB-PDF",
            description="PDF test disbursement",
            debit=Decimal("120000"),
            credit=Decimal("0"),
            posted_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = LoanStatementService(session2)
        pdf_bytes = await svc.render_pdf(loan_id=loan.id)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:4] == b"%PDF"
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_render_pdf_date_filtered(test_engine: AsyncEngine):
    """PDF with date range filter also starts with %PDF."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        await _add_journal_line(
            session,
            loan_id=loan.id,
            account_id=accounts["principal_recv_id"],
            reference="LOAN-REP-PDFRANGE",
            description="PDF range test repayment",
            debit=Decimal("0"),
            credit=Decimal("10000"),
            posted_at=datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC),
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = LoanStatementService(session2)
        pdf_bytes = await svc.render_pdf(
            loan_id=loan.id,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 12, 31),
        )
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:4] == b"%PDF"
    finally:
        await session2.close()
        await _cleanup(test_engine)
