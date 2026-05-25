from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction

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

    # ── Balance ───────────────────────────────────────────────────────────────

    async def get_balance(self, savings_account_id: uuid.UUID) -> Decimal:
        """Derive balance from savings_transactions. Never stored.

        balance = SUM(deposit amounts) - SUM(withdrawal amounts)
        """
        await self.get_account(savings_account_id)

        deposits = await self._session.scalar(
            select(func.coalesce(func.sum(SavingsTransaction.amount), Decimal("0"))).where(
                SavingsTransaction.savings_account_id == savings_account_id,
                SavingsTransaction.transaction_type == "deposit",
            )
        ) or Decimal("0")

        withdrawals = await self._session.scalar(
            select(func.coalesce(func.sum(SavingsTransaction.amount), Decimal("0"))).where(
                SavingsTransaction.savings_account_id == savings_account_id,
                SavingsTransaction.transaction_type == "withdrawal",
            )
        ) or Decimal("0")

        return Decimal(str(deposits)) - Decimal(str(withdrawals))

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
                SavingsTransaction.idempotency_key == idempotency_key
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
