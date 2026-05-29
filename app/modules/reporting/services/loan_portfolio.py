# app/modules/reporting/services/loan_portfolio.py
"""LoanPortfolioService — materialize and retrieve loan portfolio reports."""
from __future__ import annotations

import traceback
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanInstallment, LoanProduct
from app.modules.reporting.models import ReportLoanPortfolioRow, ReportRun

_log = structlog.get_logger(__name__)


def _aging_bucket(days: int) -> str:
    if days == 0:
        return "current"
    if days <= 30:
        return "1_30"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    return "90_plus"


class LoanPortfolioService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(self, *, as_of_date: date) -> ReportRun:
        """Populate report_loan_portfolio_rows from loans snapshot columns.

        Aging buckets computed from loan_installments. Never reads from GL.
        """
        run = ReportRun(
            report_type="loan_portfolio",
            as_of_date=as_of_date,
            status="running",
            started_at=datetime.now(tz=UTC),
        )
        self._session.add(run)
        await self._session.flush()

        try:
            # Delete existing rows for this as_of_date across all prior runs
            # (idempotency: re-materializing the same date replaces the prior result).
            await self._session.execute(
                delete(ReportLoanPortfolioRow).where(
                    ReportLoanPortfolioRow.as_of_date == as_of_date
                )
            )

            # Load all loans with their product name.
            loan_rows = (
                await self._session.execute(
                    select(Loan, LoanProduct.name.label("product_name"))
                    .join(LoanProduct, Loan.loan_product_id == LoanProduct.id)
                    .where(Loan.status.in_(["disbursed", "in_arrears", "written_off", "closed"]))
                    .order_by(Loan.loan_reference)
                )
            ).all()

            today = date.today()

            portfolio_rows = []
            for loan, product_name in loan_rows:
                # Compute days_in_arrears from earliest overdue installment.
                days_in_arrears = 0
                if loan.status == "in_arrears":
                    earliest_overdue = await self._session.scalar(
                        select(func.min(LoanInstallment.due_date))
                        .where(
                            LoanInstallment.loan_id == loan.id,
                            LoanInstallment.status == "overdue",
                            LoanInstallment.is_superseded.is_(False),
                        )
                    )
                    if earliest_overdue is not None:
                        days_in_arrears = (today - earliest_overdue).days

                bucket = _aging_bucket(days_in_arrears)
                disbursed_at_date = loan.disbursed_at.date() if loan.disbursed_at else as_of_date

                portfolio_rows.append(
                    ReportLoanPortfolioRow(
                        report_run_id=run.id,
                        as_of_date=as_of_date,
                        loan_id=loan.id,
                        loan_reference=loan.loan_reference,
                        member_id=loan.member_id,
                        product_name=product_name,
                        disbursed_at=disbursed_at_date,
                        maturity_date=loan.maturity_date,
                        status=loan.status,
                        outstanding_principal=loan.outstanding_principal,
                        accrued_interest=loan.accrued_interest,
                        total_written_off=loan.total_written_off,
                        days_in_arrears=days_in_arrears,
                        aging_bucket=bucket,
                    )
                )

            self._session.add_all(portfolio_rows)

            run.status = "done"
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()

            _log.info(
                "reporting.loan_portfolio.materialized",
                as_of_date=str(as_of_date),
                rows=len(portfolio_rows),
                run_id=str(run.id),
            )
            return run

        except Exception:
            run.status = "failed"
            run.error_detail = traceback.format_exc()
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()
            raise

    async def get_loan_portfolio(
        self, *, as_of_date: date | None = None, status: str | None = None
    ) -> tuple[ReportRun | None, list[ReportLoanPortfolioRow]]:
        """Return (run, rows) for the latest successful loan portfolio run."""
        q = (
            select(ReportRun)
            .where(ReportRun.report_type == "loan_portfolio", ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        if as_of_date is not None:
            q = q.where(ReportRun.as_of_date == as_of_date)
        run = await self._session.scalar(q)
        if run is None:
            return None, []

        rq = (
            select(ReportLoanPortfolioRow)
            .where(ReportLoanPortfolioRow.report_run_id == run.id)
            .order_by(ReportLoanPortfolioRow.loan_reference)
        )
        if status is not None and status != "all":
            rq = rq.where(ReportLoanPortfolioRow.status == status)
        rows = list((await self._session.execute(rq)).scalars().all())
        return run, rows
