from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine

_VALID_ACCOUNT_TYPES = frozenset({"asset", "liability", "equity", "income", "expense"})
_DEBIT_NORMAL = frozenset({"asset", "expense"})

_log = structlog.get_logger(__name__)


class LedgerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Chart of Accounts ─────────────────────────────────────────────────────

    async def create_account(
        self,
        *,
        code: str,
        name: str,
        account_type: str,
        created_by: uuid.UUID,
        parent_id: uuid.UUID | None = None,
        description: str | None = None,
    ) -> ChartOfAccount:
        if account_type not in _VALID_ACCOUNT_TYPES:
            raise ValueError(
                f"Invalid account_type '{account_type}'. "
                f"Must be one of: {sorted(_VALID_ACCOUNT_TYPES)}"
            )

        existing = await self._session.scalar(
            select(ChartOfAccount).where(ChartOfAccount.code == code)
        )
        if existing is not None:
            raise ValueError(f"Account with code '{code}' already exists")

        account = ChartOfAccount(
            code=code,
            name=name,
            account_type=account_type,
            parent_id=parent_id,
            description=description,
        )
        self._session.add(account)
        await self._session.flush()
        _log.info("account.created", code=code, account_type=account_type)
        return account

    async def list_accounts(
        self, *, include_inactive: bool = False
    ) -> list[ChartOfAccount]:
        q = select(ChartOfAccount).order_by(ChartOfAccount.code)
        if not include_inactive:
            q = q.where(ChartOfAccount.is_active.is_(True))
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_account(self, account_id: uuid.UUID) -> ChartOfAccount:
        account = await self._session.get(ChartOfAccount, account_id)
        if account is None:
            raise ValueError(f"Account '{account_id}' not found")
        return account

    # ── Journal Entries ───────────────────────────────────────────────────────

    async def post_journal_entry(
        self,
        *,
        reference: str,
        description: str,
        posted_by: uuid.UUID,
        idempotency_key: str,
        lines: list[dict],
    ) -> JournalEntry:
        """Post a balanced double-entry journal.

        lines: list of dicts with keys:
            account_id: uuid.UUID
            debit_amount: Decimal  (>= 0; exactly one of debit/credit must be > 0)
            credit_amount: Decimal (>= 0)
            description: str | None  (optional)

        Raises ValueError if debits != credits or fewer than 2 lines.
        Returns existing entry if idempotency_key already used.
        """
        existing = await self._session.scalar(
            select(JournalEntry).where(JournalEntry.idempotency_key == idempotency_key)
        )
        if existing is not None:
            _log.info("journal.idempotent_hit", idempotency_key=idempotency_key)
            return existing

        if len(lines) < 2:
            raise ValueError("Journal entry must have at least 2 lines")

        total_debit = sum(Decimal(str(ln["debit_amount"])) for ln in lines)
        total_credit = sum(Decimal(str(ln["credit_amount"])) for ln in lines)
        if total_debit != total_credit:
            raise ValueError(
                f"Journal entry is not balanced: "
                f"debits={total_debit}, credits={total_credit}"
            )

        entry = JournalEntry(
            reference=reference,
            description=description,
            posted_by=posted_by,
            idempotency_key=idempotency_key,
        )
        self._session.add(entry)
        await self._session.flush()  # populate entry.id

        for ln in lines:
            self._session.add(
                JournalLine(
                    journal_entry_id=entry.id,
                    account_id=uuid.UUID(str(ln["account_id"])),
                    debit_amount=Decimal(str(ln["debit_amount"])),
                    credit_amount=Decimal(str(ln["credit_amount"])),
                    description=ln.get("description"),
                )
            )

        await self._session.flush()
        await self._session.refresh(entry, attribute_names=["lines"])
        _log.info(
            "journal.posted",
            reference=reference,
            idempotency_key=idempotency_key,
            total=str(total_debit),
        )
        return entry

    async def list_journal_entries(self) -> list[JournalEntry]:
        result = await self._session.execute(
            select(JournalEntry).order_by(JournalEntry.posted_at.desc())
        )
        return list(result.scalars().all())

    async def get_journal_entry(self, entry_id: uuid.UUID) -> JournalEntry:
        entry = await self._session.get(JournalEntry, entry_id)
        if entry is None:
            raise ValueError(f"Journal entry '{entry_id}' not found")
        return entry

    # ── Balance Derivation ────────────────────────────────────────────────────

    # ── Maker-Checker ─────────────────────────────────────────────────────────

    async def submit_manual_entry(
        self,
        *,
        reference: str,
        description: str,
        submitted_by: uuid.UUID,
        idempotency_key: str,
        lines: list[dict],
    ) -> uuid.UUID:
        """Submit a manual GL entry for maker-checker approval.

        Returns the approval_request.id. The journal entry is NOT posted until
        the request is approved via ApprovalService.approve().
        """
        from app.modules.maker_checker.service import ApprovalService

        # Validate balance before submitting (fail fast before creating an approval row)
        total_debit = sum(Decimal(str(ln["debit_amount"])) for ln in lines)
        total_credit = sum(Decimal(str(ln["credit_amount"])) for ln in lines)
        if total_debit != total_credit:
            raise ValueError(
                f"Journal entry is not balanced: debits={total_debit}, credits={total_credit}"
            )
        if len(lines) < 2:
            raise ValueError("Journal entry must have at least 2 lines")

        payload = {
            "reference": reference,
            "description": description,
            "posted_by": str(submitted_by),
            "idempotency_key": idempotency_key,
            "lines": [
                {
                    "account_id": str(ln["account_id"]),
                    "debit_amount": str(ln["debit_amount"]),
                    "credit_amount": str(ln["credit_amount"]),
                    "description": ln.get("description"),
                }
                for ln in lines
            ],
        }

        approval_svc = ApprovalService(self._session)
        request = await approval_svc.submit(
            operation_type="ledger.post_journal_entry",
            payload=payload,
            requested_by=submitted_by,
        )
        return request.id

    async def get_account_balance(self, account_id: uuid.UUID) -> Decimal:
        """Derive balance from journal_lines. Never stored — computed on demand.

        Normal balance convention:
          ASSET / EXPENSE   → debit-normal  → balance = SUM(debit) - SUM(credit)
          LIABILITY / EQUITY / INCOME → credit-normal → balance = SUM(credit) - SUM(debit)
        """
        account = await self.get_account(account_id)

        row = await self._session.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit_amount), Decimal("0")).label("total_debit"),
                func.coalesce(func.sum(JournalLine.credit_amount), Decimal("0")).label("total_credit"),
            ).where(JournalLine.account_id == account_id)
        )
        r = row.one()
        total_debit: Decimal = r.total_debit
        total_credit: Decimal = r.total_credit

        if account.account_type in _DEBIT_NORMAL:
            return total_debit - total_credit
        return total_credit - total_debit
