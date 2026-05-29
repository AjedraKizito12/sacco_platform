# app/modules/reporting/services/trial_balance.py
"""TrialBalanceService — materialize and retrieve trial balance reports."""
from __future__ import annotations

import traceback
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select, text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.reporting.models import ReportRun, ReportTrialBalanceLine

_log = structlog.get_logger(__name__)


class TrialBalanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(self, *, as_of_date: date) -> ReportRun:
        """Aggregate GL journal lines up to as_of_date and populate report_trial_balance_lines.

        Flow:
        1. Insert ReportRun(status='running').
        2. Delete any existing lines for this run_id (clean slate).
        3. Aggregate journal_lines grouped by account.
        4. Bulk-insert results.
        5. Set status='done'.
        On exception: set status='failed', store traceback, re-raise.
        """
        run = ReportRun(
            report_type="trial_balance",
            as_of_date=as_of_date,
            status="running",
            started_at=datetime.now(tz=UTC),
        )
        self._session.add(run)
        await self._session.flush()

        try:
            # Delete existing trial-balance lines for this as_of_date across
            # all prior runs (idempotency: re-materializing the same date
            # replaces the prior result rather than accumulating).
            await self._session.execute(
                delete(ReportTrialBalanceLine).where(
                    ReportTrialBalanceLine.as_of_date == as_of_date
                )
            )

            # Aggregate: SUM(debit_amount), SUM(credit_amount) per account,
            # filtered to journal_entries.posted_at <= as_of_date.
            rows = (
                await self._session.execute(
                    select(
                        ChartOfAccount.id,
                        ChartOfAccount.code,
                        ChartOfAccount.name,
                        ChartOfAccount.account_type,
                        func.coalesce(func.sum(JournalLine.debit_amount), Decimal("0")).label("debit_total"),
                        func.coalesce(func.sum(JournalLine.credit_amount), Decimal("0")).label("credit_total"),
                    )
                    .join(JournalLine, JournalLine.account_id == ChartOfAccount.id)
                    .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
                    .where(JournalEntry.posted_at <= datetime(as_of_date.year, as_of_date.month, as_of_date.day, 23, 59, 59, tzinfo=UTC))
                    .group_by(ChartOfAccount.id, ChartOfAccount.code, ChartOfAccount.name, ChartOfAccount.account_type)
                    .order_by(ChartOfAccount.code)
                )
            ).all()

            lines = [
                ReportTrialBalanceLine(
                    report_run_id=run.id,
                    as_of_date=as_of_date,
                    account_id=row.id,
                    account_code=row.code,
                    account_name=row.name,
                    account_type=row.account_type,
                    debit_total=row.debit_total,
                    credit_total=row.credit_total,
                    balance=row.debit_total - row.credit_total,
                )
                for row in rows
            ]
            self._session.add_all(lines)

            run.status = "done"
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()

            _log.info(
                "reporting.trial_balance.materialized",
                as_of_date=str(as_of_date),
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

    async def get_trial_balance(self, *, as_of_date: date | None = None) -> tuple[ReportRun, list[ReportTrialBalanceLine]]:
        """Return (run, lines) for the latest successful trial balance run.

        If as_of_date is provided, returns the run for that date.
        Returns (None, []) if no run exists.
        """
        q = (
            select(ReportRun)
            .where(ReportRun.report_type == "trial_balance", ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        if as_of_date is not None:
            q = q.where(ReportRun.as_of_date == as_of_date)
        run = await self._session.scalar(q)
        if run is None:
            return None, []

        lines = list(
            (
                await self._session.execute(
                    select(ReportTrialBalanceLine)
                    .where(ReportTrialBalanceLine.report_run_id == run.id)
                    .order_by(ReportTrialBalanceLine.account_code)
                )
            )
            .scalars()
            .all()
        )
        return run, lines
