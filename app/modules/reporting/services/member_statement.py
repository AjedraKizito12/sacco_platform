# app/modules/reporting/services/member_statement.py
"""MemberStatementService — on-demand consolidated member statement.

Unlike the other reporting services this does NOT materialize report runs:
the statement is rendered live at request time, scoped to one member.
Reporting is the sanctioned cross-module read surface, so importing sibling
modules' models here follows the established pattern.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.members.models import Member

from app.modules.credit.models import Loan, LoanInstallment
from app.modules.fees.models import FeeAssessment, FeeType
from app.modules.savings.models import SavingsAccount, SavingsTransaction
from app.modules.shares.models import (
    MemberShareAccount,
    ShareProduct,
    ShareTransaction,
)

# Same signing convention as SavingsStatementService.
_CREDIT_TYPES = frozenset({"deposit", "SYSTEM_CREDIT", "EXTERNAL_CREDIT"})


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def _day_end_exclusive(d: date) -> datetime:
    return _day_start(d) + timedelta(days=1)


class MemberStatementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def build_context(
        self, member: Member, *, from_date: date | None, to_date: date | None
    ) -> dict[str, Any]:
        """Gather savings/shares/loans/fees for one member into a template context.

        The range filters transaction-level rows; loans always show current
        snapshot state + the active schedule. Savings opening balance is the
        signed sum of transactions before from_date.
        """
        return {
            "member": member,
            "from_date": from_date,
            "to_date": to_date,
            "generated_at": datetime.now(tz=UTC),
            "savings": await self._savings(member.id, from_date, to_date),
            "shares": await self._shares(member.id, from_date, to_date),
            "loans": await self._loans(member.id),
            "fees": await self._fees(member.id, from_date, to_date),
        }

    @staticmethod
    def _signed(txn_type: str, amount: Decimal) -> Decimal:
        return amount if txn_type in _CREDIT_TYPES else -amount

    async def _savings(
        self, member_id: uuid.UUID, from_date: date | None, to_date: date | None
    ) -> list[dict[str, Any]]:
        accounts = list(
            (
                await self._session.execute(
                    select(SavingsAccount)
                    .where(SavingsAccount.member_id == member_id)
                    .order_by(SavingsAccount.created_at)
                )
            ).scalars()
        )
        out: list[dict[str, Any]] = []
        for account in accounts:
            txns = list(
                (
                    await self._session.execute(
                        select(SavingsTransaction)
                        .where(SavingsTransaction.savings_account_id == account.id)
                        .order_by(SavingsTransaction.posted_at)
                    )
                ).scalars()
            )
            opening = Decimal("0")
            lines: list[dict[str, Any]] = []
            running = Decimal("0")
            for txn in txns:
                signed = self._signed(txn.transaction_type, txn.amount)
                if from_date is not None and txn.posted_at < _day_start(from_date):
                    opening += signed
                    running += signed
                    continue
                if to_date is not None and txn.posted_at >= _day_end_exclusive(to_date):
                    continue
                running += signed
                lines.append({"txn": txn, "signed": signed, "running": running})
            closing = lines[-1]["running"] if lines else opening
            out.append(
                {
                    "account": account,
                    "opening_balance": opening,
                    "closing_balance": closing,
                    "lines": lines,
                }
            )
        return out

    async def _shares(
        self, member_id: uuid.UUID, from_date: date | None, to_date: date | None
    ) -> list[dict[str, Any]]:
        rows = (
            await self._session.execute(
                select(MemberShareAccount, ShareProduct)
                .join(
                    ShareProduct,
                    MemberShareAccount.share_product_id == ShareProduct.id,
                )
                .where(MemberShareAccount.member_id == member_id)
                .order_by(MemberShareAccount.created_at)
            )
        ).all()
        out: list[dict[str, Any]] = []
        for account, product in rows:
            txns = list(
                (
                    await self._session.execute(
                        select(ShareTransaction)
                        .where(ShareTransaction.share_account_id == account.id)
                        .order_by(ShareTransaction.posted_at)
                    )
                ).scalars()
            )
            total_quantity = 0
            total_value = Decimal("0")
            in_range: list[ShareTransaction] = []
            for txn in txns:
                sign = 1 if txn.transaction_type == "purchase" else -1
                total_quantity += sign * txn.quantity
                total_value += sign * txn.amount
                if from_date is not None and txn.posted_at < _day_start(from_date):
                    continue
                if to_date is not None and txn.posted_at >= _day_end_exclusive(to_date):
                    continue
                in_range.append(txn)
            out.append(
                {
                    "account": account,
                    "product_name": product.name,
                    "total_quantity": total_quantity,
                    "total_value": total_value,
                    "txns": in_range,
                }
            )
        return out

    async def _loans(self, member_id: uuid.UUID) -> list[dict[str, Any]]:
        loans = list(
            (
                await self._session.execute(
                    select(Loan)
                    .where(Loan.member_id == member_id)
                    .order_by(Loan.created_at)
                )
            ).scalars()
        )
        out: list[dict[str, Any]] = []
        for loan in loans:
            installments = list(
                (
                    await self._session.execute(
                        select(LoanInstallment)
                        .where(
                            LoanInstallment.loan_id == loan.id,
                            LoanInstallment.is_superseded.is_(False),
                        )
                        .order_by(LoanInstallment.period_number)
                    )
                ).scalars()
            )
            out.append({"loan": loan, "installments": installments})
        return out

    async def _fees(
        self, member_id: uuid.UUID, from_date: date | None, to_date: date | None
    ) -> list[dict[str, Any]]:
        q = (
            select(FeeAssessment, FeeType)
            .join(FeeType, FeeAssessment.fee_type_id == FeeType.id)
            .where(
                FeeAssessment.target_type == "member",
                FeeAssessment.target_id == member_id,
            )
            .order_by(FeeAssessment.assessed_at)
        )
        if from_date is not None:
            q = q.where(FeeAssessment.assessed_at >= _day_start(from_date))
        if to_date is not None:
            q = q.where(FeeAssessment.assessed_at < _day_end_exclusive(to_date))
        rows = (await self._session.execute(q)).all()
        return [{"assessment": a, "fee_name": ft.name} for a, ft in rows]
