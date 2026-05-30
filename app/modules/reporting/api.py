# app/modules/reporting/api.py
"""FastAPI router for the reporting module.

All endpoints read from pre-materialized summary tables.
Materialization happens nightly via Celery beat tasks (beat.py).
"""
from __future__ import annotations

import uuid  # noqa: TC003 — FastAPI inspects uuid.UUID at runtime via get_type_hints
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.iam.dependencies import CurrentTenantUser
from app.modules.reporting.models import (
    ReportFeeCollectionRow,
    ReportIncomeStatementLine,
    ReportLoanPortfolioRow,
    ReportRun,
    ReportSavingsStatementLine,
    ReportTrialBalanceLine,
)
from app.modules.reporting.schemas import (
    FeeCollectionOut,
    FeeCollectionRowOut,
    IncomeStatementLineOut,
    IncomeStatementOut,
    LoanPortfolioOut,
    LoanPortfolioRowOut,
    ReportRunOut,
    SavingsStatementLineOut,
    SavingsStatementOut,
    TrialBalanceLineOut,
    TrialBalanceOut,
)

router = APIRouter(prefix="/reporting", tags=["reporting"])
Session = Annotated[AsyncSession, Depends(get_tenant_session)]


async def _latest_run(session: AsyncSession, report_type: str, as_of: date | None) -> ReportRun:
    """Fetch the most recent successful ReportRun for a report type.

    If as_of is provided, fetches the run for that specific date.
    Raises 404 with last_successful_run info if no run found.
    """
    q = (
        select(ReportRun)
        .where(ReportRun.report_type == report_type, ReportRun.status == "done")
        .order_by(ReportRun.as_of_date.desc())
        .limit(1)
    )
    if as_of is not None:
        q = q.where(ReportRun.as_of_date == as_of)
    run = await session.scalar(q)
    if run is None:
        # Find last successful run for error body.
        last = await session.scalar(
            select(ReportRun)
            .where(ReportRun.report_type == report_type, ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"No materialized {report_type} data for requested date",
                "last_successful_run": (
                    last.completed_at.isoformat()
                    if last and last.completed_at
                    else None
                ),
            },
        )
    return run


@router.get("/trial-balance", response_model=None)
async def get_trial_balance(
    session: Session,
    user: CurrentTenantUser,
    as_of: date | None = Query(default=None),
    format: str = Query(default="json", pattern="^(json|pdf|csv)$"),
) -> TrialBalanceOut | Response:
    """Trial balance as of a date. Defaults to latest successful run."""
    run = await _latest_run(session, "trial_balance", as_of)
    lines = list(
        (
            await session.execute(
                select(ReportTrialBalanceLine)
                .where(ReportTrialBalanceLine.report_run_id == run.id)
                .order_by(ReportTrialBalanceLine.account_code)
            )
        )
        .scalars()
        .all()
    )

    if format == "json":
        return TrialBalanceOut(
            as_of_date=run.as_of_date,
            generated_at=datetime.now(tz=UTC),
            lines=[TrialBalanceLineOut.model_validate(ln) for ln in lines],
        )
    if format == "pdf":
        from app.modules.reporting._base import render_pdf  # noqa: PLC0415
        pdf = render_pdf("trial_balance.html", {
            "run": run, "lines": lines, "generated_at": datetime.now(tz=UTC),
        })
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="trial-balance-{run.as_of_date}.pdf"'
                ),
            },
        )
    # csv
    from app.modules.reporting._base import render_csv  # noqa: PLC0415
    headers = [
        "Account Code", "Account Name", "Account Type",
        "Debit Total", "Credit Total", "Balance",
    ]
    rows = [
        [
            ln.account_code, ln.account_name, ln.account_type,
            ln.debit_total, ln.credit_total, ln.balance,
        ]
        for ln in lines
    ]
    return Response(
        content=render_csv(headers, rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="trial-balance-{run.as_of_date}.csv"'
            ),
        },
    )


@router.get("/loan-portfolio", response_model=None)
async def get_loan_portfolio(
    session: Session,
    user: CurrentTenantUser,
    as_of: date | None = Query(default=None),
    status: str = Query(default="all", pattern="^(all|disbursed|in_arrears|written_off)$"),
    format: str = Query(default="json", pattern="^(json|pdf|csv)$"),
) -> LoanPortfolioOut | Response:
    """Loan portfolio as of a date."""
    run = await _latest_run(session, "loan_portfolio", as_of)
    q = (
        select(ReportLoanPortfolioRow)
        .where(ReportLoanPortfolioRow.report_run_id == run.id)
        .order_by(ReportLoanPortfolioRow.loan_reference)
    )
    if status != "all":
        q = q.where(ReportLoanPortfolioRow.status == status)
    rows = list((await session.execute(q)).scalars().all())

    if format == "json":
        return LoanPortfolioOut(
            as_of_date=run.as_of_date,
            generated_at=datetime.now(tz=UTC),
            rows=[LoanPortfolioRowOut.model_validate(r) for r in rows],
        )
    if format == "pdf":
        from app.modules.reporting._base import render_pdf  # noqa: PLC0415
        pdf = render_pdf(
            "loan_portfolio.html",
            {"run": run, "rows": rows, "generated_at": datetime.now(tz=UTC)},
        )
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="loan-portfolio-{run.as_of_date}.pdf"'
                ),
            },
        )
    from app.modules.reporting._base import render_csv  # noqa: PLC0415
    headers = [
        "Loan Ref", "Member ID", "Product", "Disbursed At", "Maturity Date", "Status",
        "Outstanding Principal", "Accrued Interest", "Total Written Off",
        "Days in Arrears", "Aging Bucket",
    ]
    csv_rows = [
        [
            r.loan_reference, r.member_id, r.product_name, r.disbursed_at,
            r.maturity_date, r.status, r.outstanding_principal, r.accrued_interest,
            r.total_written_off, r.days_in_arrears, r.aging_bucket,
        ]
        for r in rows
    ]
    return Response(
        content=render_csv(headers, csv_rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="loan-portfolio-{run.as_of_date}.csv"'
            ),
        },
    )


@router.get("/income-statement", response_model=None)
async def get_income_statement(
    session: Session,
    user: CurrentTenantUser,
    from_date: date = Query(...),
    to_date: date = Query(...),
    format: str = Query(default="json", pattern="^(json|pdf|csv)$"),
) -> IncomeStatementOut | Response:
    """Income statement for a period. from_date and to_date are required."""
    # Find run whose period_start == from_date and period_end == to_date.
    run = await session.scalar(
        select(ReportRun)
        .where(
            ReportRun.report_type == "income_statement",
            ReportRun.status == "done",
            ReportRun.as_of_date == to_date,
        )
        .order_by(ReportRun.as_of_date.desc())
        .limit(1)
    )
    if run is None:
        last = await session.scalar(
            select(ReportRun)
            .where(ReportRun.report_type == "income_statement", ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No materialized income statement data for requested period",
                "last_successful_run": (
                    last.completed_at.isoformat()
                    if last and last.completed_at
                    else None
                ),
            },
        )
    lines_q = (
        select(ReportIncomeStatementLine)
        .where(
            ReportIncomeStatementLine.report_run_id == run.id,
            ReportIncomeStatementLine.period_start >= from_date,
            ReportIncomeStatementLine.period_end <= to_date,
        )
        .order_by(ReportIncomeStatementLine.account_code)
    )
    lines = list((await session.execute(lines_q)).scalars().all())

    if format == "json":
        return IncomeStatementOut(
            period_start=from_date, period_end=to_date,
            generated_at=datetime.now(tz=UTC),
            lines=[IncomeStatementLineOut.model_validate(ln) for ln in lines],
        )
    if format == "pdf":
        from app.modules.reporting._base import render_pdf  # noqa: PLC0415
        pdf = render_pdf(
            "income_statement.html",
            {
                "run": run, "lines": lines,
                "from_date": from_date, "to_date": to_date,
                "generated_at": datetime.now(tz=UTC),
            },
        )
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="income-statement-{from_date}-{to_date}.pdf"'
                ),
            },
        )
    from app.modules.reporting._base import render_csv  # noqa: PLC0415
    headers = [
        "Account Code", "Account Name", "Account Type",
        "Debit Total", "Credit Total", "Net Movement",
    ]
    csv_rows = [
        [
            ln.account_code, ln.account_name, ln.account_type,
            ln.debit_total, ln.credit_total, ln.net_movement,
        ]
        for ln in lines
    ]
    return Response(
        content=render_csv(headers, csv_rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="income-statement-{from_date}-{to_date}.csv"'
            ),
        },
    )


@router.get("/savings-statement", response_model=None)
async def get_savings_statement(
    session: Session,
    user: CurrentTenantUser,
    member_id: uuid.UUID = Query(...),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    format: str = Query(default="json", pattern="^(json|pdf|csv)$"),
) -> SavingsStatementOut | Response:
    """Savings statement for a member. member_id is required."""
    # Latest run that covers the period.
    run = await session.scalar(
        select(ReportRun)
        .where(ReportRun.report_type == "savings_statement", ReportRun.status == "done")
        .order_by(ReportRun.as_of_date.desc())
        .limit(1)
    )
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No materialized savings statement data",
                "last_successful_run": None,
            },
        )

    q = (
        select(ReportSavingsStatementLine)
        .where(
            ReportSavingsStatementLine.report_run_id == run.id,
            ReportSavingsStatementLine.member_id == member_id,
        )
        .order_by(ReportSavingsStatementLine.posted_at)
    )
    if from_date is not None:
        q = q.where(ReportSavingsStatementLine.period_start >= from_date)
    if to_date is not None:
        q = q.where(ReportSavingsStatementLine.period_end <= to_date)
    lines = list((await session.execute(q)).scalars().all())

    effective_from = from_date or run.as_of_date
    effective_to = to_date or run.as_of_date

    if format == "json":
        return SavingsStatementOut(
            member_id=member_id, period_start=effective_from, period_end=effective_to,
            generated_at=datetime.now(tz=UTC),
            lines=[SavingsStatementLineOut.model_validate(ln) for ln in lines],
        )
    if format == "pdf":
        from app.modules.reporting._base import render_pdf  # noqa: PLC0415
        pdf = render_pdf(
            "savings_statement.html",
            {
                "run": run, "lines": lines, "member_id": member_id,
                "from_date": effective_from, "to_date": effective_to,
                "generated_at": datetime.now(tz=UTC),
            },
        )
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="savings-statement-{member_id}-{effective_to}.pdf"'
                ),
            },
        )
    from app.modules.reporting._base import render_csv  # noqa: PLC0415
    headers = ["Posted At", "Transaction Type", "Narration", "Amount", "Running Balance"]
    csv_rows = [
        [
            ln.posted_at, ln.transaction_type, ln.narration,
            ln.amount, ln.running_balance,
        ]
        for ln in lines
    ]
    return Response(
        content=render_csv(headers, csv_rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="savings-statement-{member_id}-{effective_to}.csv"'
            ),
        },
    )


@router.get("/fee-collection", response_model=None)
async def get_fee_collection(
    session: Session,
    user: CurrentTenantUser,
    from_date: date = Query(...),
    to_date: date = Query(...),
    fee_type_id: uuid.UUID | None = Query(default=None),
    format: str = Query(default="json", pattern="^(json|pdf|csv)$"),
) -> FeeCollectionOut | Response:
    """Fee collection summary for a period. from_date and to_date are required."""
    run = await session.scalar(
        select(ReportRun)
        .where(
            ReportRun.report_type == "fee_collection",
            ReportRun.status == "done",
            ReportRun.as_of_date == to_date,
        )
        .order_by(ReportRun.as_of_date.desc())
        .limit(1)
    )
    if run is None:
        last = await session.scalar(
            select(ReportRun)
            .where(ReportRun.report_type == "fee_collection", ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No materialized fee collection data for requested period",
                "last_successful_run": (
                    last.completed_at.isoformat()
                    if last and last.completed_at
                    else None
                ),
            },
        )
    q = (
        select(ReportFeeCollectionRow)
        .where(ReportFeeCollectionRow.report_run_id == run.id)
        .order_by(ReportFeeCollectionRow.fee_type_name)
    )
    if fee_type_id is not None:
        q = q.where(ReportFeeCollectionRow.fee_type_id == fee_type_id)
    rows = list((await session.execute(q)).scalars().all())

    if format == "json":
        return FeeCollectionOut(
            period_start=from_date, period_end=to_date,
            generated_at=datetime.now(tz=UTC),
            rows=[FeeCollectionRowOut.model_validate(r) for r in rows],
        )
    if format == "pdf":
        from app.modules.reporting._base import render_pdf  # noqa: PLC0415
        pdf = render_pdf(
            "fee_collection.html",
            {
                "run": run, "rows": rows,
                "from_date": from_date, "to_date": to_date,
                "generated_at": datetime.now(tz=UTC),
            },
        )
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="fee-collection-{from_date}-{to_date}.pdf"'
                ),
            },
        )
    from app.modules.reporting._base import render_csv  # noqa: PLC0415
    headers = [
        "Fee Type", "Target Type", "Assessed Total",
        "Collected Total", "Outstanding Total", "Waived Total",
    ]
    csv_rows = [
        [
            r.fee_type_name, r.target_type, r.assessed_total,
            r.collected_total, r.outstanding_total, r.waived_total,
        ]
        for r in rows
    ]
    return Response(
        content=render_csv(headers, csv_rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="fee-collection-{from_date}-{to_date}.csv"'
            ),
        },
    )


@router.get("/runs", response_model=list[ReportRunOut])
async def list_report_runs(
    session: Session,
    user: CurrentTenantUser,
    report_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[ReportRunOut]:
    """List recent report runs. Optionally filter by report_type."""
    q = select(ReportRun).order_by(ReportRun.started_at.desc()).limit(limit)
    if report_type is not None:
        q = q.where(ReportRun.report_type == report_type)
    runs = list((await session.execute(q)).scalars().all())
    return [ReportRunOut.model_validate(r) for r in runs]
