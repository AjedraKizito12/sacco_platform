# app/modules/reporting/services/savings_statement.py
"""SavingsStatementService — materialize and retrieve savings statement reports."""
from __future__ import annotations

import traceback
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reporting.models import ReportRun, ReportSavingsStatementLine
from app.modules.savings.models import SavingsAccount, SavingsTransaction

_log = structlog.get_logger(__name__)


_CREDIT_TYPES = frozenset({"deposit", "SYSTEM_CREDIT", "EXTERNAL_CREDIT"})


class SavingsStatementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(self, *, period_start: date, period_end: date) -> ReportRun:
        """Materialize all savings transactions into report_savings_statement_lines.

        Running balance is computed per savings account in Python (ordered by posted_at).
        Deposits/SYSTEM_CREDIT/EXTERNAL_CREDIT add to balance.
        Withdrawals/SYSTEM_DEBIT/EXTERNAL_DEBIT subtract.
        as_of_date on ReportRun = period_end.
        """
        run = ReportRun(
            report_type="savings_statement",
            as_of_date=period_end,
            status="running",
            started_at=datetime.now(tz=UTC),
        )
        self._session.add(run)
        await self._session.flush()

        try:
            # Delete existing rows for this (period_start, period_end) across all prior runs
            # (idempotency: re-materializing the same period replaces the prior result).
            await self._session.execute(
                delete(ReportSavingsStatementLine).where(
                    ReportSavingsStatementLine.period_start == period_start,
                    ReportSavingsStatementLine.period_end == period_end,
                )
            )

            # Half-open interval [period_start 00:00 UTC, period_end+1d 00:00 UTC) — microsecond-safe.
            period_start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=UTC)
            period_end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=UTC) + timedelta(days=1)

            # Load all transactions + account.member_id in period, ordered for running-balance computation.
            txn_rows = (
                await self._session.execute(
                    select(SavingsTransaction, SavingsAccount.member_id)
                    .join(SavingsAccount, SavingsTransaction.savings_account_id == SavingsAccount.id)
                    .where(
                        SavingsTransaction.posted_at >= period_start_dt,
                        SavingsTransaction.posted_at < period_end_dt,
                    )
                    .order_by(SavingsTransaction.savings_account_id, SavingsTransaction.posted_at)
                )
            ).all()

            lines = []
            running_balances: dict[uuid.UUID, Decimal] = {}
            for txn, member_id in txn_rows:
                acct_id = txn.savings_account_id
                balance = running_balances.get(acct_id, Decimal("0"))
                balance = (
                    balance + txn.amount
                    if txn.transaction_type in _CREDIT_TYPES
                    else balance - txn.amount
                )
                running_balances[acct_id] = balance

                lines.append(
                    ReportSavingsStatementLine(
                        report_run_id=run.id,
                        period_start=period_start,
                        period_end=period_end,
                        savings_account_id=acct_id,
                        member_id=member_id,
                        posted_at=txn.posted_at,
                        transaction_type=txn.transaction_type,
                        narration=txn.narration,
                        amount=txn.amount,
                        running_balance=balance,
                    )
                )

            self._session.add_all(lines)

            run.status = "done"
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()

            _log.info(
                "reporting.savings_statement.materialized",
                period_start=str(period_start),
                period_end=str(period_end),
                lines=len(lines),
                run_id=str(run.id),
            )
            return run

        except Exception:
            run.status = "failed"
            run.error_detail = traceback.format_exc()
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()
            raise

    async def get_savings_statement(
        self,
        *,
        member_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[ReportRun | None, list[ReportSavingsStatementLine]]:
        """Return (run, lines) for the latest savings statement run, filtered by member_id.

        Run selection: when *to_date* is provided, the *oldest* run whose
        as_of_date is at or after *to_date* is returned. Each materialization
        is window-scoped (period_start <= posted_at < period_end), so an
        older qualifying run lines up with the caller's range more precisely
        than a newer (and possibly later-windowed) run that may have
        materialized zero transactions in the requested period. When
        *to_date* is None, the absolute latest run wins.

        Line ordering: ``(savings_account_id, posted_at)`` so multi-account
        members get rows grouped per account rather than interleaved.
        """
        run_q = (
            select(ReportRun)
            .where(ReportRun.report_type == "savings_statement", ReportRun.status == "done")
        )
        if to_date is not None:
            run_q = (
                run_q.where(ReportRun.as_of_date >= to_date)
                .order_by(ReportRun.as_of_date.asc())
                .limit(1)
            )
        else:
            run_q = run_q.order_by(ReportRun.as_of_date.desc()).limit(1)
        run = await self._session.scalar(run_q)
        if run is None:
            return None, []

        q = (
            select(ReportSavingsStatementLine)
            .where(
                ReportSavingsStatementLine.report_run_id == run.id,
                ReportSavingsStatementLine.member_id == member_id,
            )
            .order_by(
                ReportSavingsStatementLine.savings_account_id,
                ReportSavingsStatementLine.posted_at,
            )
        )
        if from_date is not None:
            q = q.where(ReportSavingsStatementLine.period_start >= from_date)
        if to_date is not None:
            q = q.where(ReportSavingsStatementLine.period_end <= to_date)
        lines = list((await self._session.execute(q)).scalars().all())
        return run, lines
