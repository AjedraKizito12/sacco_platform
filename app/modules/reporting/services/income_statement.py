# app/modules/reporting/services/income_statement.py
"""IncomeStatementService — materialize and retrieve income statement reports."""
from __future__ import annotations

import traceback
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.reporting.models import ReportIncomeStatementLine, ReportRun

_log = structlog.get_logger(__name__)


class IncomeStatementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(self, *, period_start: date, period_end: date) -> ReportRun:
        """Aggregate GL journal lines for income/expense accounts in the period.

        as_of_date on the ReportRun is set to period_end.
        net_movement = credit_total - debit_total (positive = net income).
        """
        run = ReportRun(
            report_type="income_statement",
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
                delete(ReportIncomeStatementLine).where(
                    ReportIncomeStatementLine.period_start == period_start,
                    ReportIncomeStatementLine.period_end == period_end,
                )
            )

            # Half-open interval [period_start 00:00 UTC, period_end+1d 00:00 UTC) — microsecond-safe.
            period_start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=UTC)
            period_end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=UTC) + timedelta(days=1)

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
                    .where(
                        ChartOfAccount.account_type.in_(["income", "expense"]),
                        JournalEntry.posted_at >= period_start_dt,
                        JournalEntry.posted_at < period_end_dt,
                    )
                    .group_by(ChartOfAccount.id, ChartOfAccount.code, ChartOfAccount.name, ChartOfAccount.account_type)
                    .order_by(ChartOfAccount.code)
                )
            ).all()

            lines = [
                ReportIncomeStatementLine(
                    report_run_id=run.id,
                    period_start=period_start,
                    period_end=period_end,
                    account_id=row.id,
                    account_code=row.code,
                    account_name=row.name,
                    account_type=row.account_type,
                    debit_total=row.debit_total,
                    credit_total=row.credit_total,
                    net_movement=row.credit_total - row.debit_total,
                )
                for row in rows
            ]
            self._session.add_all(lines)

            run.status = "done"
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()

            _log.info(
                "reporting.income_statement.materialized",
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

    async def get_income_statement(
        self, *, period_end: date
    ) -> tuple[ReportRun | None, list[ReportIncomeStatementLine]]:
        """Return (run, lines) for the income statement run where as_of_date == period_end."""
        run = await self._session.scalar(
            select(ReportRun)
            .where(
                ReportRun.report_type == "income_statement",
                ReportRun.status == "done",
                ReportRun.as_of_date == period_end,
            )
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        if run is None:
            return None, []

        lines = list(
            (
                await self._session.execute(
                    select(ReportIncomeStatementLine)
                    .where(ReportIncomeStatementLine.report_run_id == run.id)
                    .order_by(ReportIncomeStatementLine.account_code)
                )
            )
            .scalars()
            .all()
        )
        return run, lines
