from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select

from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_ALLOW_NEGATIVE_MODULES: frozenset[str] = frozenset()  # extended by credit module


@dataclass
class SystemDebitResult:
    transaction_id: uuid.UUID | None
    journal_entry_id: uuid.UUID | None
    debited_amount: Decimal
    requested_amount: Decimal
    shortfall_amount: Decimal
    status: str  # 'full' | 'partial' | 'zero'

_log = structlog.get_logger(__name__)


class SavingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Savings Products ──────────────────────────────────────────────────────

    async def create_product(
        self,
        *,
        name: str,
        interest_rate: Decimal,
        liability_account_id: uuid.UUID,
        minimum_balance: Decimal = Decimal("0"),
    ) -> SavingsProduct:
        if interest_rate < 0:
            raise ValueError("interest_rate must be >= 0")
        if minimum_balance < 0:
            raise ValueError("minimum_balance must be >= 0")

        product = SavingsProduct(
            name=name,
            interest_rate=interest_rate,
            liability_account_id=liability_account_id,
            minimum_balance=minimum_balance,
        )
        self._session.add(product)
        await self._session.flush()
        _log.info("savings_product.created", name=name, interest_rate=str(interest_rate))
        return product

    async def list_products(
        self, *, include_inactive: bool = False
    ) -> list[SavingsProduct]:
        q = select(SavingsProduct).order_by(SavingsProduct.name)
        if not include_inactive:
            q = q.where(SavingsProduct.is_active.is_(True))
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_product(self, product_id: uuid.UUID) -> SavingsProduct:
        product = await self._session.get(SavingsProduct, product_id)
        if product is None:
            raise ValueError(f"Savings product '{product_id}' not found")
        return product

    # ── Savings Accounts ──────────────────────────────────────────────────────

    async def open_account(
        self,
        *,
        member_id: uuid.UUID,
        savings_product_id: uuid.UUID,
    ) -> SavingsAccount:
        product = await self._session.get(SavingsProduct, savings_product_id)
        if product is None or not product.is_active:
            raise ValueError(
                f"Savings product '{savings_product_id}' not found or inactive"
            )

        existing = await self._session.scalar(
            select(SavingsAccount).where(
                SavingsAccount.member_id == member_id,
                SavingsAccount.savings_product_id == savings_product_id,
            )
        )
        if existing is not None:
            raise ValueError(
                f"Savings account already exists for member '{member_id}' "
                f"and product '{savings_product_id}'"
            )

        account = SavingsAccount(
            member_id=member_id,
            savings_product_id=savings_product_id,
            product_name=product.name,
            interest_rate=product.interest_rate,
            minimum_balance=product.minimum_balance,
            liability_account_id=product.liability_account_id,
        )
        self._session.add(account)
        await self._session.flush()
        _log.info(
            "savings_account.opened",
            member_id=str(member_id),
            savings_product_id=str(savings_product_id),
        )
        return account

    async def get_account(self, savings_account_id: uuid.UUID) -> SavingsAccount:
        account = await self._session.get(SavingsAccount, savings_account_id)
        if account is None:
            raise ValueError(f"Savings account '{savings_account_id}' not found")
        return account

    async def list_accounts(
        self, *, member_id: uuid.UUID | None = None
    ) -> list[SavingsAccount]:
        q = select(SavingsAccount).order_by(
            SavingsAccount.product_name, SavingsAccount.id
        )
        if member_id is not None:
            q = q.where(SavingsAccount.member_id == member_id)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    # ── Balance ───────────────────────────────────────────────────────────────

    async def get_balance(self, savings_account_id: uuid.UUID) -> Decimal:
        """Derive balance from savings_transactions. Never stored.

        balance = SUM(deposit amounts) - SUM(withdrawal amounts)
        """
        await self.get_account(savings_account_id)

        from sqlalchemy import or_

        deposits = await self._session.scalar(
            select(func.coalesce(func.sum(SavingsTransaction.amount), Decimal("0"))).where(
                SavingsTransaction.savings_account_id == savings_account_id,
                or_(
                    SavingsTransaction.transaction_type == "deposit",
                    SavingsTransaction.transaction_type == "SYSTEM_CREDIT",
                ),
            )
        ) or Decimal("0")

        withdrawals = await self._session.scalar(
            select(func.coalesce(func.sum(SavingsTransaction.amount), Decimal("0"))).where(
                SavingsTransaction.savings_account_id == savings_account_id,
                or_(
                    SavingsTransaction.transaction_type == "withdrawal",
                    SavingsTransaction.transaction_type == "SYSTEM_DEBIT",
                ),
            )
        ) or Decimal("0")

        return Decimal(str(deposits)) - Decimal(str(withdrawals))

    async def get_available_balance(self, savings_account_id: uuid.UUID) -> Decimal:
        """Raw balance minus any active guarantor liens on this account."""
        raw = await self.get_balance(savings_account_id)

        # Local import avoids circular dependency (credit imports savings).
        from sqlalchemy import func as sa_func  # noqa: PLC0415

        from app.modules.credit.models import LoanGuarantorLien

        result = await self._session.execute(
            select(sa_func.coalesce(sa_func.sum(LoanGuarantorLien.current_lien), Decimal("0")))
            .where(LoanGuarantorLien.savings_account_id == savings_account_id)
            .where(LoanGuarantorLien.is_active.is_(True))
        )
        total_lien: Decimal = result.scalar_one()
        return raw - total_lien

    # ── Transactions ──────────────────────────────────────────────────────────

    async def list_transactions(
        self, savings_account_id: uuid.UUID
    ) -> list[SavingsTransaction]:
        await self.get_account(savings_account_id)
        result = await self._session.execute(
            select(SavingsTransaction)
            .where(SavingsTransaction.savings_account_id == savings_account_id)
            .order_by(SavingsTransaction.posted_at)
        )
        return list(result.scalars().all())

    # ── Deposit ───────────────────────────────────────────────────────────────

    async def deposit(
        self,
        *,
        savings_account_id: uuid.UUID,
        amount: Decimal,
        payment_account_id: uuid.UUID,
        posted_by: uuid.UUID,
        idempotency_key: str,
        narration: str | None = None,
    ) -> SavingsTransaction:
        """Deposit funds directly (no maker-checker). Posts a balanced GL entry.

        GL: DEBIT payment_account (cash/bank), CREDIT account.liability_account_id.
        Idempotent: returns existing transaction if idempotency_key already used.
        """
        existing = await self._session.scalar(
            select(SavingsTransaction).where(
                SavingsTransaction.idempotency_key == idempotency_key,
                SavingsTransaction.savings_account_id == savings_account_id,
            )
        )
        if existing is not None:
            _log.info("savings.deposit.idempotent_hit", idempotency_key=idempotency_key)
            return existing

        account = await self.get_account(savings_account_id)

        from app.modules.ledger.service import LedgerService

        ledger_svc = LedgerService(self._session)
        entry = await ledger_svc.post_journal_entry(
            reference=f"SAV-DEP-{savings_account_id}",
            description=f"Savings deposit: {amount}",
            posted_by=posted_by,
            idempotency_key=f"savings-deposit-{idempotency_key}",
            lines=[
                {
                    "account_id": payment_account_id,
                    "debit_amount": amount,
                    "credit_amount": Decimal("0"),
                },
                {
                    "account_id": account.liability_account_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": amount,
                },
            ],
        )

        txn = SavingsTransaction(
            savings_account_id=savings_account_id,
            transaction_type="deposit",
            amount=amount,
            narration=narration,
            journal_entry_id=entry.id,
            posted_by=posted_by,
            idempotency_key=idempotency_key,
        )
        self._session.add(txn)
        await self._session.flush()
        _log.info(
            "savings.deposited",
            savings_account_id=str(savings_account_id),
            amount=str(amount),
        )
        return txn

    # ── Withdrawal (Maker-Checker) ────────────────────────────────────────────

    async def submit_withdrawal(
        self,
        *,
        savings_account_id: uuid.UUID,
        amount: Decimal,
        payment_account_id: uuid.UUID,
        submitted_by: uuid.UUID,
        idempotency_key: str,
        narration: str | None = None,
    ) -> uuid.UUID:
        """Submit a savings withdrawal for maker-checker approval.

        Validates that (current_balance - amount) >= account.minimum_balance.
        Returns the approval_request.id.
        Idempotent: returns existing request.id if idempotency_key already used.
        """
        account = await self.get_account(savings_account_id)

        from sqlalchemy import select as sa_select

        from app.modules.maker_checker.models.tenant import TenantApprovalRequest

        existing_req = await self._session.scalar(
            sa_select(TenantApprovalRequest).where(
                TenantApprovalRequest.operation_type == "savings.withdraw",
                TenantApprovalRequest.payload["idempotency_key"].astext == idempotency_key,
            )
        )
        if existing_req is not None:
            _log.info(
                "savings.withdrawal.idempotent_hit", idempotency_key=idempotency_key
            )
            return existing_req.id

        balance = await self.get_balance(savings_account_id)

        if amount > balance:
            raise ValueError(
                f"Insufficient balance: requested {amount}, available {balance}"
            )

        remaining = balance - amount
        if remaining < account.minimum_balance:
            raise ValueError(
                f"Withdrawal would breach minimum balance: "
                f"balance after withdrawal {remaining} < minimum {account.minimum_balance}"
            )

        from app.modules.maker_checker.service import ApprovalService

        payload = {
            "savings_account_id": str(savings_account_id),
            "amount": str(amount),
            "payment_account_id": str(payment_account_id),
            "liability_account_id": str(account.liability_account_id),
            "posted_by": str(submitted_by),
            "narration": narration,
            "idempotency_key": idempotency_key,
        }

        approval_svc = ApprovalService(self._session)
        request = await approval_svc.submit(
            operation_type="savings.withdraw",
            payload=payload,
            requested_by=submitted_by,
        )
        _log.info(
            "savings.withdrawal_submitted",
            savings_account_id=str(savings_account_id),
            amount=str(amount),
            approval_id=str(request.id),
        )
        return request.id

    # ── System-initiated debits/credits ───────────────────────────────────────

    async def get_primary_account_for_member(
        self, member_id: uuid.UUID
    ) -> SavingsAccount | None:
        """Return the member's oldest savings account, or None."""
        result = await self._session.scalar(
            select(SavingsAccount)
            .where(SavingsAccount.member_id == member_id)
            .order_by(SavingsAccount.created_at)
            .limit(1)
        )
        return result

    async def system_debit(
        self,
        *,
        savings_account_id: uuid.UUID,
        amount: Decimal,
        reason: str,
        source_module: str,
        source_id: uuid.UUID,
        actor: uuid.UUID,
        idempotency_key: str,
        contra_account_id: uuid.UUID,
        narration: str | None = None,
        on_insufficient_funds: str = "fail",
    ) -> SystemDebitResult:
        """System-initiated debit. NOT callable from API routes.

        on_insufficient_funds:
          'fail'    — raise ValueError if balance < amount (default)
          'partial' — debit min(balance, amount); return shortfall
          'allow_negative' — restricted to modules in _ALLOW_NEGATIVE_MODULES

        Note on idempotency replay: if idempotency_key was already processed, returns
        a SystemDebitResult reconstructed from the existing transaction. On replay,
        requested_amount == debited_amount and shortfall_amount == 0 regardless of
        the original shortfall (the SavingsTransaction row does not store requested_amount).
        Callers must not rely on shortfall_amount/status fields of a replayed result.
        """
        if (
            on_insufficient_funds == "allow_negative"
            and source_module not in _ALLOW_NEGATIVE_MODULES
        ):
            raise ValueError(
                f"'allow_negative' is not permitted for source_module='{source_module}'"
            )

        # Idempotency guard.
        existing = await self._session.scalar(
            select(SavingsTransaction).where(
                SavingsTransaction.idempotency_key == idempotency_key,
                SavingsTransaction.savings_account_id == savings_account_id,
            )
        )
        if existing is not None:
            _log.info("savings.system_debit.idempotent_hit", idempotency_key=idempotency_key)
            return SystemDebitResult(
                transaction_id=existing.id,
                journal_entry_id=existing.journal_entry_id,
                debited_amount=existing.amount,
                requested_amount=existing.amount,
                shortfall_amount=Decimal("0"),
                status="full",
            )

        account = await self.get_account(savings_account_id)
        balance = await self.get_balance(savings_account_id)

        if on_insufficient_funds == "fail" and balance < amount:
            raise ValueError(
                f"Insufficient balance for system_debit: "
                f"requested {amount}, available {balance}"
            )

        if on_insufficient_funds == "partial" and balance <= Decimal("0"):
            return SystemDebitResult(
                transaction_id=None,
                journal_entry_id=None,
                debited_amount=Decimal("0"),
                requested_amount=amount,
                shortfall_amount=amount,
                status="zero",
            )

        # NOTE: partial mode intentionally ignores minimum_balance.
        # System-initiated fee collection must be able to drain savings below the
        # product minimum — the minimum_balance constraint applies to user withdrawals only.
        actual_amount = amount if on_insufficient_funds != "partial" else min(balance, amount)

        from app.modules.ledger.service import LedgerService

        ledger_svc = LedgerService(self._session)
        entry = await ledger_svc.post_journal_entry(
            reference=f"SYS-DEB-{savings_account_id}",
            description=narration or f"System debit: {reason}",
            posted_by=actor,
            idempotency_key=f"sys-debit-{idempotency_key}",
            lines=[
                {
                    "account_id": account.liability_account_id,
                    "debit_amount": actual_amount,
                    "credit_amount": Decimal("0"),
                },
                {
                    "account_id": contra_account_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": actual_amount,
                },
            ],
        )

        txn = SavingsTransaction(
            savings_account_id=savings_account_id,
            transaction_type="SYSTEM_DEBIT",
            amount=actual_amount,
            narration=narration,
            journal_entry_id=entry.id,
            posted_by=actor,
            idempotency_key=idempotency_key,
            source_module=source_module,
            source_id=source_id,
            reason=reason,
        )
        self._session.add(txn)
        await self._session.flush()

        shortfall = amount - actual_amount
        _log.info(
            "savings.system_debit",
            savings_account_id=str(savings_account_id),
            amount=str(actual_amount),
            reason=reason,
            source_module=source_module,
        )
        return SystemDebitResult(
            transaction_id=txn.id,
            journal_entry_id=entry.id,
            debited_amount=actual_amount,
            requested_amount=amount,
            shortfall_amount=shortfall,
            status="full" if shortfall == Decimal("0") else "partial",
        )

    async def system_credit(
        self,
        *,
        savings_account_id: uuid.UUID,
        amount: Decimal,
        reason: str,
        source_module: str,
        source_id: uuid.UUID,
        actor: uuid.UUID,
        idempotency_key: str,
        contra_account_id: uuid.UUID,
        narration: str | None = None,
    ) -> SavingsTransaction:
        """System-initiated credit. NOT callable from API routes."""
        # Idempotency guard.
        existing = await self._session.scalar(
            select(SavingsTransaction).where(
                SavingsTransaction.idempotency_key == idempotency_key,
                SavingsTransaction.savings_account_id == savings_account_id,
            )
        )
        if existing is not None:
            _log.info("savings.system_credit.idempotent_hit", idempotency_key=idempotency_key)
            return existing

        account = await self.get_account(savings_account_id)

        from app.modules.ledger.service import LedgerService

        ledger_svc = LedgerService(self._session)
        entry = await ledger_svc.post_journal_entry(
            reference=f"SYS-CRD-{savings_account_id}",
            description=narration or f"System credit: {reason}",
            posted_by=actor,
            idempotency_key=f"sys-credit-{idempotency_key}",
            lines=[
                {
                    "account_id": contra_account_id,
                    "debit_amount": amount,
                    "credit_amount": Decimal("0"),
                },
                {
                    "account_id": account.liability_account_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": amount,
                },
            ],
        )

        txn = SavingsTransaction(
            savings_account_id=savings_account_id,
            transaction_type="SYSTEM_CREDIT",
            amount=amount,
            narration=narration,
            journal_entry_id=entry.id,
            posted_by=actor,
            idempotency_key=idempotency_key,
            source_module=source_module,
            source_id=source_id,
            reason=reason,
        )
        self._session.add(txn)
        await self._session.flush()
        _log.info(
            "savings.system_credit",
            savings_account_id=str(savings_account_id),
            amount=str(amount),
            reason=reason,
        )
        return txn

    async def record_external_credit(
        self,
        *,
        savings_account_id: uuid.UUID,
        amount: Decimal,
        journal_entry_id: uuid.UUID,
        source_module: str,
        source_id: uuid.UUID,
        narration: str | None = None,
        idempotency_key: str,
    ) -> SavingsTransaction:
        """Record a credit to a savings account made by an external module.

        The GL entry has ALREADY been posted by the calling module (e.g. credit).
        This method only writes the savings_transactions statement row.
        NOT callable from API routes.
        """
        existing = await self._session.scalar(
            select(SavingsTransaction).where(
                SavingsTransaction.idempotency_key == idempotency_key,
                SavingsTransaction.savings_account_id == savings_account_id,
            )
        )
        if existing is not None:
            _log.info(
                "savings.record_external_credit.idempotent_hit",
                idempotency_key=idempotency_key,
            )
            return existing

        await self.get_account(savings_account_id)  # existence check

        txn = SavingsTransaction(
            savings_account_id=savings_account_id,
            transaction_type="EXTERNAL_CREDIT",
            amount=amount,
            narration=narration,
            journal_entry_id=journal_entry_id,
            posted_by=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            idempotency_key=idempotency_key,
            source_module=source_module,
            source_id=source_id,
        )
        self._session.add(txn)
        await self._session.flush()
        _log.info(
            "savings.external_credit_recorded",
            savings_account_id=str(savings_account_id),
            amount=str(amount),
            source_module=source_module,
        )
        return txn

    async def record_external_debit(
        self,
        *,
        savings_account_id: uuid.UUID,
        amount: Decimal,
        journal_entry_id: uuid.UUID,
        source_module: str,
        source_id: uuid.UUID,
        narration: str | None = None,
        idempotency_key: str,
    ) -> SavingsTransaction:
        """Record a debit from a savings account made by an external module.

        The GL entry has ALREADY been posted by the calling module (e.g. credit).
        This method only writes the savings_transactions statement row.
        NOT callable from API routes.
        """
        existing = await self._session.scalar(
            select(SavingsTransaction).where(
                SavingsTransaction.idempotency_key == idempotency_key,
                SavingsTransaction.savings_account_id == savings_account_id,
            )
        )
        if existing is not None:
            _log.info(
                "savings.record_external_debit.idempotent_hit",
                idempotency_key=idempotency_key,
            )
            return existing

        await self.get_account(savings_account_id)  # existence check

        txn = SavingsTransaction(
            savings_account_id=savings_account_id,
            transaction_type="EXTERNAL_DEBIT",
            amount=amount,
            narration=narration,
            journal_entry_id=journal_entry_id,
            posted_by=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            idempotency_key=idempotency_key,
            source_module=source_module,
            source_id=source_id,
        )
        self._session.add(txn)
        await self._session.flush()
        _log.info(
            "savings.external_debit_recorded",
            savings_account_id=str(savings_account_id),
            amount=str(amount),
            source_module=source_module,
        )
        return txn
