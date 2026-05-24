"""Integration tests for LedgerService.

Uses the async_sessionmaker + commit + cleanup pattern (not the rollback fixture)
to avoid asyncpg protocol-state errors with flush() in session-scoped event loops.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.ledger.service import LedgerService
from app.modules.maker_checker.models.tenant import TenantApprovalRequest, TenantApprovalAction
from app.modules.maker_checker.service import ApprovalService
import app.modules.ledger.executors  # noqa: F401 — registers ledger executor in approval_registry

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
    """Return a new AsyncSession with search_path set (no transaction started).

    With NullPool each commit closes the underlying connection.  We attach an
    ``after_begin`` listener to the *sync* session so that search_path is
    re-applied at the start of every new transaction (i.e. on every new
    connection acquired after a commit).
    """
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
        await session.execute(delete(JournalLine))
        await session.execute(delete(JournalEntry))
        await session.execute(delete(ChartOfAccount))
        await session.commit()


# ── Account CRUD ──────────────────────────────────────────────────────────────


async def test_create_account_returns_active_account(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        account = await svc.create_account(
            code="1000",
            name="Cash",
            account_type="asset",
            created_by=uuid.uuid4(),
        )
        await session.commit()

        assert account.id is not None
        assert account.code == "1000"
        assert account.name == "Cash"
        assert account.account_type == "asset"
        assert account.is_active is True
        assert account.parent_id is None
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_create_account_duplicate_code_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        await svc.create_account(
            code="1001",
            name="Bank",
            account_type="asset",
            created_by=uuid.uuid4(),
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LedgerService(session2)
        with pytest.raises(ValueError, match="already exists"):
            await svc2.create_account(
                code="1001",
                name="Duplicate",
                account_type="asset",
                created_by=uuid.uuid4(),
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_create_account_invalid_type_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        with pytest.raises(ValueError, match="account_type"):
            await svc.create_account(
                code="9999",
                name="Bad",
                account_type="invalid",
                created_by=uuid.uuid4(),
            )
    finally:
        await session.close()


async def test_list_accounts_returns_active_only_by_default(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        actor = uuid.uuid4()
        await svc.create_account(code="2000", name="Equity", account_type="equity", created_by=actor)
        acc = await svc.create_account(code="2001", name="Inactive", account_type="equity", created_by=actor)
        acc.is_active = False
        await session.commit()

        results = await svc.list_accounts()
        codes = [a.code for a in results]
        assert "2000" in codes
        assert "2001" not in codes
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_get_account_not_found_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_account(uuid.uuid4())
    finally:
        await session.close()


# ── Journal Posting ───────────────────────────────────────────────────────────


async def _create_accounts(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    """Helper: create asset + liability account, return (asset_id, liability_id)."""
    session = await _new_session(engine)
    try:
        svc = LedgerService(session)
        actor = uuid.uuid4()
        asset = await svc.create_account(code="1100", name="Cash", account_type="asset", created_by=actor)
        liab = await svc.create_account(code="3100", name="Equity Capital", account_type="liability", created_by=actor)
        await session.commit()
        return asset.id, liab.id
    finally:
        await session.close()


async def test_post_journal_entry_balanced(test_engine):
    asset_id, liab_id = await _create_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        entry = await svc.post_journal_entry(
            reference="TEST-001",
            description="Initial capital injection",
            posted_by=uuid.uuid4(),
            idempotency_key="idem-test-001",
            lines=[
                {"account_id": asset_id, "debit_amount": Decimal("1000.00"), "credit_amount": Decimal("0")},
                {"account_id": liab_id, "debit_amount": Decimal("0"), "credit_amount": Decimal("1000.00")},
            ],
        )
        await session.commit()

        assert entry.id is not None
        assert len(entry.lines) == 2
        total_debit = sum(ln.debit_amount for ln in entry.lines)
        total_credit = sum(ln.credit_amount for ln in entry.lines)
        assert total_debit == total_credit == Decimal("1000.00")
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_post_journal_entry_unbalanced_raises(test_engine):
    asset_id, liab_id = await _create_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        with pytest.raises(ValueError, match="balanced"):
            await svc.post_journal_entry(
                reference="TEST-UNBAL",
                description="Unbalanced entry",
                posted_by=uuid.uuid4(),
                idempotency_key="idem-unbal",
                lines=[
                    {"account_id": asset_id, "debit_amount": Decimal("1000.00"), "credit_amount": Decimal("0")},
                    {"account_id": liab_id, "debit_amount": Decimal("0"), "credit_amount": Decimal("500.00")},
                ],
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_post_journal_entry_idempotency(test_engine):
    asset_id, liab_id = await _create_accounts(test_engine)

    async def _post(idem_key: str):
        session = await _new_session(test_engine)
        try:
            svc = LedgerService(session)
            entry = await svc.post_journal_entry(
                reference="TEST-IDEM",
                description="Capital",
                posted_by=uuid.uuid4(),
                idempotency_key=idem_key,
                lines=[
                    {"account_id": asset_id, "debit_amount": Decimal("500.00"), "credit_amount": Decimal("0")},
                    {"account_id": liab_id, "debit_amount": Decimal("0"), "credit_amount": Decimal("500.00")},
                ],
            )
            await session.commit()
            return entry
        finally:
            await session.close()

    try:
        e1 = await _post("idem-duplicate")
        e2 = await _post("idem-duplicate")
        assert e1.id == e2.id  # Same entry returned, not duplicated
    finally:
        await _cleanup(test_engine)


# ── Balance Derivation ────────────────────────────────────────────────────────


async def test_get_account_balance_asset_debit_normal(test_engine):
    """Asset accounts: balance = SUM(debit) - SUM(credit) — positive when debited."""
    asset_id, liab_id = await _create_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        await svc.post_journal_entry(
            reference="BAL-001",
            description="Debit asset 1000",
            posted_by=uuid.uuid4(),
            idempotency_key="bal-idem-001",
            lines=[
                {"account_id": asset_id, "debit_amount": Decimal("1000.00"), "credit_amount": Decimal("0")},
                {"account_id": liab_id, "debit_amount": Decimal("0"), "credit_amount": Decimal("1000.00")},
            ],
        )
        await session.commit()

        balance = await svc.get_account_balance(asset_id)
        assert balance == Decimal("1000.00")
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_get_account_balance_liability_credit_normal(test_engine):
    """Liability accounts: balance = SUM(credit) - SUM(debit) — positive when credited."""
    asset_id, liab_id = await _create_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        await svc.post_journal_entry(
            reference="BAL-002",
            description="Credit liability 1000",
            posted_by=uuid.uuid4(),
            idempotency_key="bal-idem-002",
            lines=[
                {"account_id": asset_id, "debit_amount": Decimal("1000.00"), "credit_amount": Decimal("0")},
                {"account_id": liab_id, "debit_amount": Decimal("0"), "credit_amount": Decimal("1000.00")},
            ],
        )
        await session.commit()

        balance = await svc.get_account_balance(liab_id)
        assert balance == Decimal("1000.00")
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_get_account_balance_zero_when_no_lines(test_engine):
    asset_id, _ = await _create_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        balance = await svc.get_account_balance(asset_id)
        assert balance == Decimal("0")
    finally:
        await session.close()
        await _cleanup(test_engine)


# ── Maker-Checker for Manual GL Entries ──────────────────────────────────────


async def _cleanup_approvals(engine: AsyncEngine) -> None:
    async with _factory(engine)() as s:
        await s.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await s.execute(delete(TenantApprovalAction))
        await s.execute(delete(TenantApprovalRequest))
        await s.commit()


async def test_submit_manual_entry_creates_pending_approval(test_engine):
    asset_id, liab_id = await _create_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        approval_id = await svc.submit_manual_entry(
            reference="MANUAL-001",
            description="Manual adjustment",
            submitted_by=uuid.uuid4(),
            idempotency_key="manual-idem-001",
            lines=[
                {"account_id": str(asset_id), "debit_amount": "200.00", "credit_amount": "0"},
                {"account_id": str(liab_id), "debit_amount": "0", "credit_amount": "200.00"},
            ],
        )
        await session.commit()

        assert isinstance(approval_id, uuid.UUID)
    finally:
        await session.close()
        await _cleanup_approvals(test_engine)
        await _cleanup(test_engine)


async def test_executor_posts_journal_entry_on_approve(test_engine):
    """Full maker-checker flow: submit → approve → verify journal entry created."""
    asset_id, liab_id = await _create_accounts(test_engine)
    maker_id = uuid.uuid4()
    checker_id = uuid.uuid4()

    # Submit
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        approval_id = await svc.submit_manual_entry(
            reference="MANUAL-002",
            description="Board adjustment",
            submitted_by=maker_id,
            idempotency_key="manual-idem-002",
            lines=[
                {"account_id": str(asset_id), "debit_amount": "300.00", "credit_amount": "0"},
                {"account_id": str(liab_id), "debit_amount": "0", "credit_amount": "300.00"},
            ],
        )
        await session.commit()
    finally:
        await session.close()

    # Approve (triggers executor which posts the journal entry)
    session2 = await _new_session(test_engine)
    try:
        approval_svc = ApprovalService(session2)
        await approval_svc.approve(request_id=approval_id, actor_user_id=checker_id)
        await session2.commit()
    finally:
        await session2.close()

    # Verify: journal entry created — balance reflects the posting
    session3 = await _new_session(test_engine)
    try:
        svc3 = LedgerService(session3)
        balance = await svc3.get_account_balance(asset_id)
        assert balance == Decimal("300.00")
    finally:
        await session3.close()
        await _cleanup_approvals(test_engine)
        await _cleanup(test_engine)
