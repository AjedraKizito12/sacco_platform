"""Integration tests for SavingsService.

Uses async_sessionmaker + commit + cleanup pattern (not the rollback fixture)
to avoid asyncpg protocol-state errors with flush() in session-scoped event loops.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.modules.savings.executors  # noqa: F401 — registers savings executor
from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.ledger.service import LedgerService
from app.modules.maker_checker.models.tenant import TenantApprovalAction, TenantApprovalRequest
from app.modules.maker_checker.service import ApprovalService
from app.modules.members.models import Member
from app.modules.members.service import MemberService
from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction
from app.modules.savings.service import SavingsService

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
    from sqlalchemy import event as sa_event

    session = _factory(engine)()

    @sa_event.listens_for(session.sync_session, "after_begin")
    def _reapply_search_path(sess, transaction, connection):  # type: ignore[misc]
        connection.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )

    await session.execute(
        text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
    )
    return session


async def _cleanup(engine: AsyncEngine) -> None:
    async with _factory(engine)() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(SavingsTransaction))
        await session.execute(delete(SavingsAccount))
        await session.execute(delete(SavingsProduct))
        await session.execute(delete(JournalLine))
        await session.execute(delete(JournalEntry))
        await session.execute(delete(ChartOfAccount))
        await session.execute(delete(Member))
        await session.commit()


async def _setup_gl_accounts(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a cash account (asset) and a savings liability account.
    Returns (cash_account_id, liability_account_id).
    """
    session = await _new_session(engine)
    try:
        svc = LedgerService(session)
        actor = uuid.uuid4()
        cash = await svc.create_account(
            code="1020", name="Cash in Hand", account_type="asset", created_by=actor
        )
        liability = await svc.create_account(
            code="2010", name="Member Savings", account_type="liability", created_by=actor
        )
        await session.commit()
        return cash.id, liability.id
    finally:
        await session.close()


async def _setup_product(engine: AsyncEngine, liability_account_id: uuid.UUID) -> uuid.UUID:
    """Create a savings product and return its ID."""
    session = await _new_session(engine)
    try:
        svc = SavingsService(session)
        product = await svc.create_product(
            name="Regular Savings",
            interest_rate=Decimal("5.00"),
            liability_account_id=liability_account_id,
            minimum_balance=Decimal("500.00"),
        )
        await session.commit()
        return product.id
    finally:
        await session.close()


async def _setup_member(engine: AsyncEngine) -> uuid.UUID:
    """Create a member and return its ID."""
    session = await _new_session(engine)
    try:
        svc = MemberService(session)
        member = await svc.register_member(
            full_name="Alice Nakato",
            date_of_birth=date(1990, 5, 15),
            gender="female",
            created_by=uuid.uuid4(),
        )
        await session.commit()
        return member.id
    finally:
        await session.close()


async def _setup_account(
    engine: AsyncEngine, product_id: uuid.UUID
) -> uuid.UUID:
    """Create a member and open a savings account, returning the account ID."""
    member_id = await _setup_member(engine)
    session = await _new_session(engine)
    try:
        svc = SavingsService(session)
        account = await svc.open_account(
            member_id=member_id,
            savings_product_id=product_id,
        )
        await session.commit()
        return account.id
    finally:
        await session.close()


# ── Savings Products ──────────────────────────────────────────────────────────


async def test_create_product_returns_active_product(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        product = await svc.create_product(
            name="Regular Savings",
            interest_rate=Decimal("5.00"),
            liability_account_id=liability_id,
            minimum_balance=Decimal("500.00"),
        )
        await session.commit()

        assert product.id is not None
        assert product.name == "Regular Savings"
        assert product.interest_rate == Decimal("5.00")
        assert product.minimum_balance == Decimal("500.00")
        assert product.is_active is True
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_create_product_negative_interest_rate_raises(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        with pytest.raises(ValueError, match="interest_rate"):
            await svc.create_product(
                name="Bad",
                interest_rate=Decimal("-1"),
                liability_account_id=liability_id,
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


# ── Savings Accounts ──────────────────────────────────────────────────────────


async def test_open_account_returns_account_with_snapshots(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    member_id = await _setup_member(test_engine)

    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        account = await svc.open_account(
            member_id=member_id,
            savings_product_id=product_id,
        )
        await session.commit()

        assert account.id is not None
        assert account.member_id == member_id
        assert account.savings_product_id == product_id
        # Product terms are snapshotted
        assert account.product_name == "Regular Savings"
        assert account.interest_rate == Decimal("5.00")
        assert account.minimum_balance == Decimal("500.00")
        assert account.liability_account_id == liability_id
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_open_account_duplicate_raises(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    member_id = await _setup_member(test_engine)

    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        _ = await svc.open_account(member_id=member_id, savings_product_id=product_id)
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = SavingsService(session2)
        with pytest.raises(ValueError, match="already exists"):
            await svc2.open_account(member_id=member_id, savings_product_id=product_id)
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_open_account_inactive_product_raises(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    member_id = await _setup_member(test_engine)

    # Deactivate the product
    session = await _new_session(test_engine)
    try:
        from app.modules.savings.models import SavingsProduct as SP
        product = await session.get(SP, product_id)
        product.is_active = False
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = SavingsService(session2)
        with pytest.raises(ValueError, match="not found or inactive"):
            await svc2.open_account(member_id=member_id, savings_product_id=product_id)
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_get_account_not_found_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_account(uuid.uuid4())
    finally:
        await session.close()


# ── Deposit ───────────────────────────────────────────────────────────────────


async def test_deposit_returns_transaction(test_engine):
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    account_id = await _setup_account(test_engine, product_id)

    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        txn = await svc.deposit(
            savings_account_id=account_id,
            amount=Decimal("10000.00"),
            payment_account_id=cash_id,
            posted_by=uuid.uuid4(),
            idempotency_key="dep-001",
        )
        await session.commit()

        assert txn.id is not None
        assert txn.transaction_type == "deposit"
        assert txn.amount == Decimal("10000.00")
        assert txn.journal_entry_id is not None
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_deposit_posts_balanced_gl_entry(test_engine):
    """Verify the GL entry debits cash (asset) and credits savings liability."""
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    account_id = await _setup_account(test_engine, product_id)

    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        await svc.deposit(
            savings_account_id=account_id,
            amount=Decimal("5000.00"),
            payment_account_id=cash_id,
            posted_by=uuid.uuid4(),
            idempotency_key="dep-002",
        )
        await session.commit()

        # cash (asset, debit-normal): SUM(debits) - SUM(credits) = 5000
        # savings liability (credit-normal): SUM(credits) - SUM(debits) = 5000
        ledger_svc = LedgerService(session)
        cash_balance = await ledger_svc.get_account_balance(cash_id)
        liability_balance = await ledger_svc.get_account_balance(liability_id)
        assert cash_balance == Decimal("5000.00")
        assert liability_balance == Decimal("5000.00")
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_deposit_updates_balance(test_engine):
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    account_id = await _setup_account(test_engine, product_id)

    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        await svc.deposit(
            savings_account_id=account_id,
            amount=Decimal("2000.00"),
            payment_account_id=cash_id,
            posted_by=uuid.uuid4(),
            idempotency_key="dep-003",
        )
        await session.commit()

        balance = await svc.get_balance(account_id)
        assert balance == Decimal("2000.00")
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_deposit_idempotency(test_engine):
    """Calling deposit twice with the same key returns the same transaction."""
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    account_id = await _setup_account(test_engine, product_id)

    async def _deposit(idem_key: str) -> uuid.UUID:
        s = await _new_session(test_engine)
        try:
            svc = SavingsService(s)
            txn = await svc.deposit(
                savings_account_id=account_id,
                amount=Decimal("1000.00"),
                payment_account_id=cash_id,
                posted_by=uuid.uuid4(),
                idempotency_key=idem_key,
            )
            await s.commit()
            return txn.id
        finally:
            await s.close()

    try:
        id1 = await _deposit("idem-dep-004")
        id2 = await _deposit("idem-dep-004")
        assert id1 == id2

        # Balance should reflect only one deposit
        s = await _new_session(test_engine)
        try:
            balance = await SavingsService(s).get_balance(account_id)
            assert balance == Decimal("1000.00")
        finally:
            await s.close()
    finally:
        await _cleanup(test_engine)


async def _cleanup_approvals(engine: AsyncEngine) -> None:
    async with _factory(engine)() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantApprovalAction))
        await session.execute(delete(TenantApprovalRequest))
        await session.commit()


# ── Withdrawal (Maker-Checker) ────────────────────────────────────────────────


async def test_submit_withdrawal_below_minimum_balance_raises(test_engine):
    """Withdrawal that would drop balance below minimum_balance is rejected."""
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    # product minimum_balance = 500.00
    account_id = await _setup_account(test_engine, product_id)

    # Deposit 600 first
    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        await svc.deposit(
            savings_account_id=account_id,
            amount=Decimal("600.00"),
            payment_account_id=cash_id,
            posted_by=uuid.uuid4(),
            idempotency_key="dep-for-wdraw-001",
        )
        await session.commit()
    finally:
        await session.close()

    # Try to withdraw 200 — would leave 400 < minimum_balance 500
    session2 = await _new_session(test_engine)
    try:
        svc2 = SavingsService(session2)
        with pytest.raises(ValueError, match="minimum balance"):
            await svc2.submit_withdrawal(
                savings_account_id=account_id,
                amount=Decimal("200.00"),
                payment_account_id=cash_id,
                submitted_by=uuid.uuid4(),
                idempotency_key="wdraw-fail-001",
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_submit_withdrawal_insufficient_balance_raises(test_engine):
    """Withdrawal larger than current balance is rejected."""
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    account_id = await _setup_account(test_engine, product_id)

    # Account has zero balance — try to withdraw anything
    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        with pytest.raises(ValueError, match="Insufficient"):
            await svc.submit_withdrawal(
                savings_account_id=account_id,
                amount=Decimal("100.00"),
                payment_account_id=cash_id,
                submitted_by=uuid.uuid4(),
                idempotency_key="wdraw-fail-002",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_executor_withdraws_and_posts_gl(test_engine):
    """Full maker-checker flow: deposit → submit withdrawal → approve → verify balance + GL."""
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    # product minimum_balance = 500.00
    account_id = await _setup_account(test_engine, product_id)
    maker_id = uuid.uuid4()
    checker_id = uuid.uuid4()

    # Deposit 2000 first
    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        await svc.deposit(
            savings_account_id=account_id,
            amount=Decimal("2000.00"),
            payment_account_id=cash_id,
            posted_by=maker_id,
            idempotency_key="dep-for-wdraw-exec-001",
        )
        await session.commit()
    finally:
        await session.close()

    # Submit withdrawal of 1000 (leaves 1000 >= minimum_balance 500)
    session2 = await _new_session(test_engine)
    try:
        svc2 = SavingsService(session2)
        approval_id = await svc2.submit_withdrawal(
            savings_account_id=account_id,
            amount=Decimal("1000.00"),
            payment_account_id=cash_id,
            submitted_by=maker_id,
            idempotency_key="wdraw-exec-001",
        )
        await session2.commit()
    finally:
        await session2.close()

    # Approve — triggers executor
    session3 = await _new_session(test_engine)
    try:
        approval_svc = ApprovalService(session3)
        await approval_svc.approve(request_id=approval_id, actor_user_id=checker_id)
        await session3.commit()
    finally:
        await session3.close()

    # Verify balance = 2000 - 1000 = 1000
    session4 = await _new_session(test_engine)
    try:
        svc4 = SavingsService(session4)
        balance = await svc4.get_balance(account_id)
        assert balance == Decimal("1000.00")

        # GL: cash net (debit-normal) = 2000 dep - 1000 wdraw = 1000
        # liability net (credit-normal) = 2000 dep - 1000 wdraw = 1000
        ledger_svc = LedgerService(session4)
        cash_balance = await ledger_svc.get_account_balance(cash_id)
        liability_balance = await ledger_svc.get_account_balance(liability_id)
        assert cash_balance == Decimal("1000.00")
        assert liability_balance == Decimal("1000.00")
    finally:
        await session4.close()
        await _cleanup_approvals(test_engine)
        await _cleanup(test_engine)


# ── system_debit ──────────────────────────────────────────────────────────────

async def test_system_debit_full_deducts_balance(test_engine):
    """system_debit with sufficient balance: full amount debited, balance reduced."""
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    account_id = await _setup_account(test_engine, product_id)
    source_id = uuid.uuid4()

    # Deposit 5000
    session = await _new_session(test_engine)
    try:
        await SavingsService(session).deposit(
            savings_account_id=account_id,
            amount=Decimal("5000.00"),
            payment_account_id=cash_id,
            posted_by=uuid.uuid4(),
            idempotency_key="sys-dep-001",
        )
        await session.commit()
    finally:
        await session.close()

    # system_debit 2000 (contra = cash account for test)
    session2 = await _new_session(test_engine)
    try:
        svc = SavingsService(session2)
        result = await svc.system_debit(
            savings_account_id=account_id,
            amount=Decimal("2000.00"),
            reason="FEE_COLLECTION",
            source_module="fees",
            source_id=source_id,
            actor=uuid.uuid4(),
            idempotency_key="sysdeb-001",
            contra_account_id=cash_id,
        )
        await session2.commit()

        assert result.debited_amount == Decimal("2000.00")
        assert result.shortfall_amount == Decimal("0.00")
        assert result.status == "full"
        assert result.transaction_id is not None
        assert result.journal_entry_id is not None

        balance = await SavingsService(session2).get_balance(account_id)
        assert balance == Decimal("3000.00")
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_system_debit_fail_on_insufficient(test_engine):
    """system_debit on_insufficient_funds='fail' raises when balance < amount."""
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    account_id = await _setup_account(test_engine, product_id)

    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        with pytest.raises(ValueError, match="Insufficient"):
            await svc.system_debit(
                savings_account_id=account_id,
                amount=Decimal("100.00"),
                reason="FEE_COLLECTION",
                source_module="fees",
                source_id=uuid.uuid4(),
                actor=uuid.uuid4(),
                idempotency_key="sysdeb-002",
                contra_account_id=cash_id,
                on_insufficient_funds="fail",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_system_debit_partial(test_engine):
    """system_debit on_insufficient_funds='partial' debits available balance."""
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    account_id = await _setup_account(test_engine, product_id)

    # Deposit only 1000
    session = await _new_session(test_engine)
    try:
        await SavingsService(session).deposit(
            savings_account_id=account_id,
            amount=Decimal("1000.00"),
            payment_account_id=cash_id,
            posted_by=uuid.uuid4(),
            idempotency_key="sys-dep-003",
        )
        await session.commit()
    finally:
        await session.close()

    # Try to debit 3000 with partial
    session2 = await _new_session(test_engine)
    try:
        svc = SavingsService(session2)
        result = await svc.system_debit(
            savings_account_id=account_id,
            amount=Decimal("3000.00"),
            reason="FEE_COLLECTION",
            source_module="fees",
            source_id=uuid.uuid4(),
            actor=uuid.uuid4(),
            idempotency_key="sysdeb-003",
            contra_account_id=cash_id,
            on_insufficient_funds="partial",
        )
        await session2.commit()

        assert result.debited_amount == Decimal("1000.00")
        assert result.shortfall_amount == Decimal("2000.00")
        assert result.status == "partial"
        balance = await SavingsService(session2).get_balance(account_id)
        assert balance == Decimal("0.00")
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_system_debit_zero_balance_returns_zero_status(test_engine):
    """system_debit with zero balance and on_insufficient_funds='partial' returns status='zero'."""
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    account_id = await _setup_account(test_engine, product_id)

    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        result = await svc.system_debit(
            savings_account_id=account_id,
            amount=Decimal("500.00"),
            reason="FEE_COLLECTION",
            source_module="fees",
            source_id=uuid.uuid4(),
            actor=uuid.uuid4(),
            idempotency_key="sysdeb-004",
            contra_account_id=cash_id,
            on_insufficient_funds="partial",
        )
        # No commit needed — nothing written
        assert result.status == "zero"
        assert result.debited_amount == Decimal("0.00")
        assert result.transaction_id is None
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_system_debit_records_source_columns(test_engine):
    """system_debit rows have source_module, source_id, reason populated."""
    cash_id, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    account_id = await _setup_account(test_engine, product_id)
    source_id = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        await SavingsService(session).deposit(
            savings_account_id=account_id, amount=Decimal("1000.00"),
            payment_account_id=cash_id, posted_by=uuid.uuid4(),
            idempotency_key="sys-dep-005",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        result = await SavingsService(session2).system_debit(
            savings_account_id=account_id, amount=Decimal("200.00"),
            reason="FEE_COLLECTION", source_module="fees", source_id=source_id,
            actor=uuid.uuid4(), idempotency_key="sysdeb-005",
            contra_account_id=cash_id,
        )
        await session2.commit()

        row = await session2.get(SavingsTransaction, result.transaction_id)
        assert row.source_module == "fees"
        assert row.source_id == source_id
        assert row.reason == "FEE_COLLECTION"
        assert row.transaction_type == "SYSTEM_DEBIT"
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_savings_transaction_accepts_external_credit_type(test_engine):
    """EXTERNAL_CREDIT is a valid transaction_type — CHECK constraint allows it."""
    # Set up: GL account + savings product + savings account + a journal entry to reference.
    session = await _new_session(test_engine)
    try:
        actor = uuid.uuid4()
        ledger_svc = LedgerService(session)
        cash = await ledger_svc.create_account(
            code=f"1-EXT-{uuid.uuid4().hex[:4]}", name="Cash EXT",
            account_type="asset", created_by=actor,
        )
        liab = await ledger_svc.create_account(
            code=f"2-EXT-{uuid.uuid4().hex[:4]}", name="Savings EXT",
            account_type="liability", created_by=actor,
        )
        # Post a dummy journal entry (represents the external module's GL entry).
        entry = await ledger_svc.post_journal_entry(
            reference="EXT-CR-TEST",
            description="Dummy external entry",
            posted_by=actor,
            idempotency_key=f"ext-cr-test-{uuid.uuid4()}",
            lines=[
                {"account_id": cash.id, "debit_amount": Decimal("500"),
                 "credit_amount": Decimal("0")},
                {"account_id": liab.id, "debit_amount": Decimal("0"),
                 "credit_amount": Decimal("500")},
            ],
        )

        savings_svc = SavingsService(session)
        product = SavingsProduct(
            name="EXT Test Product",
            interest_rate=Decimal("5"),
            minimum_balance=Decimal("0"),
            liability_account_id=liab.id,
        )
        session.add(product)
        await session.flush()

        member_svc = MemberService(session)
        from datetime import date as _date
        member = await member_svc.register_member(
            full_name="EXT Test Member",
            date_of_birth=_date(1990, 1, 1),
            gender="female",
            created_by=actor,
        )
        account = await savings_svc.open_account(member_id=member.id, savings_product_id=product.id)

        # Insert EXTERNAL_CREDIT row directly (bypassing service — testing model/schema only).
        txn = SavingsTransaction(
            savings_account_id=account.id,
            transaction_type="EXTERNAL_CREDIT",
            amount=Decimal("500"),
            journal_entry_id=entry.id,
            posted_by=actor,
            idempotency_key=f"ext-cr-direct-{uuid.uuid4()}",
            source_module="credit",
            source_id=uuid.uuid4(),
            reason="LOAN_DISBURSEMENT",
        )
        session.add(txn)
        await session.flush()
        await session.commit()

        assert txn.id is not None
        assert txn.transaction_type == "EXTERNAL_CREDIT"
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_savings_transaction_accepts_external_debit_type(test_engine):
    """EXTERNAL_DEBIT is a valid transaction_type — CHECK constraint allows it."""
    # Set up: GL account + savings product + savings account + a journal entry to reference.
    session = await _new_session(test_engine)
    try:
        actor = uuid.uuid4()
        ledger_svc = LedgerService(session)
        cash = await ledger_svc.create_account(
            code=f"1-EXTD-{uuid.uuid4().hex[:4]}", name="Cash EXTD",
            account_type="asset", created_by=actor,
        )
        liab = await ledger_svc.create_account(
            code=f"2-EXTD-{uuid.uuid4().hex[:4]}", name="Savings EXTD",
            account_type="liability", created_by=actor,
        )
        # Post a dummy journal entry (represents the external module's GL entry).
        entry = await ledger_svc.post_journal_entry(
            reference="EXT-DR-TEST",
            description="Dummy external debit entry",
            posted_by=actor,
            idempotency_key=f"ext-dr-test-{uuid.uuid4()}",
            lines=[
                {"account_id": liab.id, "debit_amount": Decimal("500"),
                 "credit_amount": Decimal("0")},
                {"account_id": cash.id, "debit_amount": Decimal("0"),
                 "credit_amount": Decimal("500")},
            ],
        )

        savings_svc = SavingsService(session)
        product = SavingsProduct(
            name="EXTD Test Product",
            interest_rate=Decimal("5"),
            minimum_balance=Decimal("0"),
            liability_account_id=liab.id,
        )
        session.add(product)
        await session.flush()

        member_svc = MemberService(session)
        from datetime import date as _date
        member = await member_svc.register_member(
            full_name="EXTD Test Member",
            date_of_birth=_date(1990, 1, 1),
            gender="female",
            created_by=actor,
        )
        account = await savings_svc.open_account(member_id=member.id, savings_product_id=product.id)

        # Insert EXTERNAL_DEBIT row directly (bypassing service — testing model/schema only).
        txn = SavingsTransaction(
            savings_account_id=account.id,
            transaction_type="EXTERNAL_DEBIT",
            amount=Decimal("500"),
            journal_entry_id=entry.id,
            posted_by=actor,
            idempotency_key=f"ext-dr-direct-{uuid.uuid4()}",
            source_module="credit",
            source_id=uuid.uuid4(),
            reason="LOAN_REPAYMENT",
        )
        session.add(txn)
        await session.flush()
        await session.commit()

        assert txn.id is not None
        assert txn.transaction_type == "EXTERNAL_DEBIT"
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.anyio
async def test_get_available_balance_subtracts_active_liens(test_engine: AsyncEngine) -> None:
    """Available balance = raw balance - SUM(active current_lien)."""
    from app.modules.credit.models import (
        LoanApplication,
        LoanGuarantor,
        LoanGuarantorLien,
        LoanProduct,
    )

    # Set up GL accounts and a real member (savings_accounts FK requires both)
    _, liability_account_id = await _setup_gl_accounts(test_engine)
    member_id = await _setup_member(test_engine)
    product_id = await _setup_product(test_engine, liability_account_id)

    session = await _new_session(test_engine)
    try:
        sav_svc = SavingsService(session)
        savings_account = await sav_svc.open_account(
            member_id=member_id, savings_product_id=product_id
        )
        await session.flush()

        # Create loan product + application + guarantor rows (needed for FK chain)
        loan_product = LoanProduct(
            name=f"avail-bal-lp-{uuid.uuid4()}",
            interest_method="flat",
            annual_interest_rate=Decimal("12.0000"),
            repayment_frequency="monthly",
            max_term_periods=12,
            min_amount=Decimal("1000.0000"),
            max_amount=Decimal("100000.0000"),
            required_approvals=1,
            required_guarantors=1,
            disbursement_destinations=["member_savings"],
            gl_principal_receivable_code="1100",
            gl_interest_receivable_code="1110",
            gl_interest_income_code="4100",
        )
        session.add(loan_product)
        await session.flush()
        loan_app = LoanApplication(
            loan_product_id=loan_product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("10000.0000"),
            requested_term_periods=12,
            disbursement_destination="member_savings",
            status="submitted",
            idempotency_key=str(uuid.uuid4()),
        )
        session.add(loan_app)
        await session.flush()
        guarantor_row = LoanGuarantor(
            loan_application_id=loan_app.id,
            guarantor_member_id=member_id,
            guaranteed_amount=Decimal("5000.0000"),
            status="accepted",
            idempotency_key=str(uuid.uuid4()),
        )
        session.add(guarantor_row)
        await session.flush()

        # Add a lien linked to the real guarantor row
        lien = LoanGuarantorLien(
            loan_guarantor_id=guarantor_row.id,
            savings_account_id=savings_account.id,
            original_lien=Decimal("5000.0000"),
            current_lien=Decimal("3000.0000"),
            is_active=True,
        )
        session.add(lien)
        await session.commit()

        # Raw balance is 0 (no transactions); available should subtract the lien
        available = await sav_svc.get_available_balance(savings_account.id)
        # raw balance = 0, lien = 3000, available = 0 - 3000 = -3000
        assert available == Decimal("-3000.0000")
    finally:
        await session.close()
        await _cleanup(test_engine)
