# app/modules/shares/service.py
from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.shares.models import MemberShareAccount, ShareProduct, ShareTransaction

_log = structlog.get_logger(__name__)


class ShareService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Share Products ────────────────────────────────────────────────────────

    async def create_product(
        self,
        *,
        name: str,
        par_value: Decimal,
        share_capital_account_id: uuid.UUID,
        minimum_shares: int = 1,
        maximum_shares: int | None = None,
    ) -> ShareProduct:
        if par_value <= 0:
            raise ValueError("par_value must be positive")
        if minimum_shares < 1:
            raise ValueError("minimum_shares must be at least 1")
        if maximum_shares is not None and maximum_shares < minimum_shares:
            raise ValueError("maximum_shares must be >= minimum_shares")

        product = ShareProduct(
            name=name,
            par_value=par_value,
            share_capital_account_id=share_capital_account_id,
            minimum_shares=minimum_shares,
            maximum_shares=maximum_shares,
        )
        self._session.add(product)
        await self._session.flush()
        _log.info("share_product.created", name=name, par_value=str(par_value))
        return product

    async def list_products(self, *, include_inactive: bool = False) -> list[ShareProduct]:
        q = select(ShareProduct).order_by(ShareProduct.name)
        if not include_inactive:
            q = q.where(ShareProduct.is_active.is_(True))
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_product(self, product_id: uuid.UUID) -> ShareProduct:
        product = await self._session.get(ShareProduct, product_id)
        if product is None:
            raise ValueError(f"Share product '{product_id}' not found")
        return product

    # ── Member Share Accounts ─────────────────────────────────────────────────

    async def open_account(
        self,
        *,
        member_id: uuid.UUID,
        share_product_id: uuid.UUID,
    ) -> MemberShareAccount:
        product = await self._session.get(ShareProduct, share_product_id)
        if product is None or not product.is_active:
            raise ValueError(f"Share product '{share_product_id}' not found or inactive")

        existing = await self._session.scalar(
            select(MemberShareAccount).where(
                MemberShareAccount.member_id == member_id,
                MemberShareAccount.share_product_id == share_product_id,
            )
        )
        if existing is not None:
            raise ValueError(
                f"Share account already exists for member '{member_id}' "
                f"and product '{share_product_id}'"
            )

        account = MemberShareAccount(
            member_id=member_id,
            share_product_id=share_product_id,
        )
        self._session.add(account)
        await self._session.flush()
        _log.info(
            "share_account.opened",
            member_id=str(member_id),
            share_product_id=str(share_product_id),
        )
        return account

    async def get_account(self, share_account_id: uuid.UUID) -> MemberShareAccount:
        account = await self._session.get(MemberShareAccount, share_account_id)
        if account is None:
            raise ValueError(f"Share account '{share_account_id}' not found")
        return account

    # ── Balance ───────────────────────────────────────────────────────────────

    async def get_balance(
        self, share_account_id: uuid.UUID
    ) -> tuple[int, Decimal]:
        """Return (shares_held, total_value) derived from share_transactions.

        shares_held = SUM(purchase qty) - SUM(redemption qty)
        total_value = shares_held × par_value
        """
        account = await self.get_account(share_account_id)
        product = await self._session.get(ShareProduct, account.share_product_id)
        if product is None:
            raise ValueError(f"Share product '{account.share_product_id}' not found")

        purchased = await self._session.scalar(
            select(func.coalesce(func.sum(ShareTransaction.quantity), 0)).where(
                ShareTransaction.share_account_id == share_account_id,
                ShareTransaction.transaction_type == "purchase",
            )
        ) or 0

        redeemed = await self._session.scalar(
            select(func.coalesce(func.sum(ShareTransaction.quantity), 0)).where(
                ShareTransaction.share_account_id == share_account_id,
                ShareTransaction.transaction_type == "redemption",
            )
        ) or 0

        shares_held = int(purchased) - int(redeemed)
        total_value = Decimal(shares_held) * product.par_value
        return shares_held, total_value

    # ── Transactions ──────────────────────────────────────────────────────────

    async def list_transactions(
        self, share_account_id: uuid.UUID
    ) -> list[ShareTransaction]:
        await self.get_account(share_account_id)
        result = await self._session.execute(
            select(ShareTransaction)
            .where(ShareTransaction.share_account_id == share_account_id)
            .order_by(ShareTransaction.posted_at)
        )
        return list(result.scalars().all())

    # ── Share Purchase ────────────────────────────────────────────────────────

    async def purchase_shares(
        self,
        *,
        share_account_id: uuid.UUID,
        quantity: int,
        payment_account_id: uuid.UUID,
        posted_by: uuid.UUID,
        idempotency_key: str,
    ) -> ShareTransaction:
        """Buy shares directly (no maker-checker). Posts a balanced GL entry.

        GL: DEBIT payment_account (cash/bank), CREDIT share_capital_account (equity).
        Idempotent: returns existing transaction if idempotency_key already used.
        """
        existing = await self._session.scalar(
            select(ShareTransaction).where(
                ShareTransaction.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            _log.info("shares.purchase.idempotent_hit", idempotency_key=idempotency_key)
            return existing

        account = await self.get_account(share_account_id)
        product = await self.get_product(account.share_product_id)
        if not product.is_active:
            raise ValueError("Share product is not active")

        if quantity < product.minimum_shares:
            raise ValueError(
                f"quantity must be >= minimum_shares ({product.minimum_shares})"
            )
        if product.maximum_shares is not None:
            shares_held, _ = await self.get_balance(share_account_id)
            if shares_held + quantity > product.maximum_shares:
                raise ValueError(
                    f"Purchase would exceed maximum_shares ({product.maximum_shares}); "
                    f"currently holding {shares_held}"
                )

        amount = Decimal(quantity) * product.par_value

        from app.modules.ledger.service import LedgerService

        ledger_svc = LedgerService(self._session)
        entry = await ledger_svc.post_journal_entry(
            reference=f"SHARES-{share_account_id}",
            description=f"Share purchase: {quantity} shares @ {product.par_value} each",
            posted_by=posted_by,
            idempotency_key=f"share-purchase-{idempotency_key}",
            lines=[
                {
                    "account_id": payment_account_id,
                    "debit_amount": amount,
                    "credit_amount": Decimal("0"),
                },
                {
                    "account_id": product.share_capital_account_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": amount,
                },
            ],
        )

        txn = ShareTransaction(
            share_account_id=share_account_id,
            transaction_type="purchase",
            quantity=quantity,
            amount=amount,
            journal_entry_id=entry.id,
            posted_by=posted_by,
            idempotency_key=idempotency_key,
        )
        self._session.add(txn)
        await self._session.flush()
        _log.info(
            "shares.purchased",
            share_account_id=str(share_account_id),
            quantity=quantity,
            amount=str(amount),
        )
        return txn

    # ── Share Redemption (Maker-Checker) ──────────────────────────────────────

    async def submit_redemption(
        self,
        *,
        share_account_id: uuid.UUID,
        quantity: int,
        payment_account_id: uuid.UUID,
        submitted_by: uuid.UUID,
        reason: str | None = None,
        idempotency_key: str,
    ) -> uuid.UUID:
        """Submit a share redemption for maker-checker approval.

        Validates the member has sufficient shares before submitting.
        Returns the approval_request.id.
        """
        account = await self.get_account(share_account_id)
        product = await self.get_product(account.share_product_id)

        from sqlalchemy import select as sa_select
        from app.modules.maker_checker.models.tenant import TenantApprovalRequest

        existing_req = await self._session.scalar(
            sa_select(TenantApprovalRequest).where(
                TenantApprovalRequest.operation_type == "shares.redeem_shares",
                TenantApprovalRequest.payload["idempotency_key"].astext == idempotency_key,
            )
        )
        if existing_req is not None:
            _log.info(
                "shares.redemption.idempotent_hit", idempotency_key=idempotency_key
            )
            return existing_req.id

        shares_held, _ = await self.get_balance(share_account_id)
        if quantity > shares_held:
            raise ValueError(
                f"Insufficient shares: requested {quantity}, held {shares_held}"
            )

        amount = Decimal(quantity) * product.par_value

        from app.modules.maker_checker.service import ApprovalService

        payload = {
            "share_account_id": str(share_account_id),
            "quantity": quantity,
            "amount": str(amount),
            "payment_account_id": str(payment_account_id),
            "share_capital_account_id": str(product.share_capital_account_id),
            "posted_by": str(submitted_by),
            "reason": reason,
            "idempotency_key": idempotency_key,
        }

        approval_svc = ApprovalService(self._session)
        request = await approval_svc.submit(
            operation_type="shares.redeem_shares",
            payload=payload,
            requested_by=submitted_by,
        )
        _log.info(
            "shares.redemption_submitted",
            share_account_id=str(share_account_id),
            quantity=quantity,
            approval_id=str(request.id),
        )
        return request.id
