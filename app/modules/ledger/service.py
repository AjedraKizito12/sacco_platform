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
