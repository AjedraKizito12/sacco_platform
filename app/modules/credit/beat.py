# app/modules/credit/beat.py
"""Celery beat tasks for the credit module.

Tasks:
    accrue_reducing_balance_interest  — daily
    mark_loans_in_arrears             — daily (added in sub-plan 09)
    reconcile_loan_snapshots          — daily (added in sub-plan 11)
"""
from __future__ import annotations

import asyncio
import re
import uuid
from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
_SYSTEM_ACTOR = uuid.UUID("00000000-0000-0000-0000-000000000000")


async def _accrue_for_tenant(schema_name: str, engine: AsyncEngine) -> int:
    """Accrue reducing-balance interest for all eligible loans in one tenant.

    Eligible: status IN ('disbursed', 'in_arrears'), interest_method='reducing_balance',
    with at least one installment where due_date <= today AND interest has not yet been
    accrued for that period (idempotency via LedgerService idempotency_key check).

    Returns count of accruals posted.
    """
    from app.modules.credit.models import Loan, LoanInstallment
    from app.modules.ledger.service import LedgerService

    factory = async_sessionmaker(engine, expire_on_commit=False)
    today = date.today()
    accrued_count = 0

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )

        loans = list(
            (
                await session.execute(
                    select(Loan).where(
                        Loan.interest_method == "reducing_balance",
                        Loan.status.in_(["disbursed", "in_arrears"]),
                    )
                )
            ).scalars().all()
        )

        for loan in loans:
            installments = list(
                (
                    await session.execute(
                        select(LoanInstallment).where(
                            LoanInstallment.loan_id == loan.id,
                            LoanInstallment.due_date <= today,
                            LoanInstallment.status.in_(["pending", "partial", "overdue"]),
                        ).order_by(LoanInstallment.due_date)
                    )
                ).scalars().all()
            )

            for installment in installments:
                idem_key = f"loan-accrue-{loan.id}-{installment.due_date.isoformat()}"

                from app.modules.ledger.models import JournalEntry as _JE

                existing = await session.scalar(
                    select(_JE).where(_JE.idempotency_key == idem_key)
                )
                if existing is not None:
                    continue

                period_interest = installment.interest_due
                if period_interest <= Decimal("0"):
                    continue

                try:
                    async with session.begin_nested():
                        ledger_svc = LedgerService(session)
                        await ledger_svc.post_journal_entry(
                            reference=f"LOAN-ACCRUE-{loan.id}-P{installment.period_number}",
                            description=(
                                f"Interest accrual: {loan.loan_reference}"
                                f" period {installment.period_number}"
                            ),
                            posted_by=_SYSTEM_ACTOR,
                            idempotency_key=idem_key,
                            lines=[
                                {
                                    "account_id": loan.gl_interest_receivable_id,
                                    "debit_amount": period_interest,
                                    "credit_amount": Decimal("0"),
                                    "sub_ledger_type": "loan",
                                    "sub_ledger_id": loan.id,
                                },
                                {
                                    "account_id": loan.gl_interest_income_id,
                                    "debit_amount": Decimal("0"),
                                    "credit_amount": period_interest,
                                    "sub_ledger_type": "loan",
                                    "sub_ledger_id": loan.id,
                                },
                            ],
                        )
                        loan.accrued_interest = loan.accrued_interest + period_interest
                        accrued_count += 1
                except Exception as exc:
                    _log.error(
                        "credit.beat.accrue_error",
                        schema=schema_name,
                        loan_id=str(loan.id),
                        period=installment.period_number,
                        error=str(exc),
                    )

        await session.commit()

    return accrued_count


async def _run_accrue_interest() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    totals: dict[str, int] = {}
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            schemas = [row[0] for row in result.fetchall()]
        for schema_name in schemas:
            if not _SCHEMA_RE.match(schema_name):
                continue
            try:
                count = await _accrue_for_tenant(schema_name, engine)
                if count:
                    totals[schema_name] = count
            except Exception as exc:
                _log.error(
                    "credit.beat.accrue_tenant_error",
                    schema=schema_name,
                    error=str(exc),
                )
    finally:
        await engine.dispose()
    _log.info("credit.beat.accrue_interest_complete", **totals)
    return totals


@celery_app.task(name="app.modules.credit.beat.accrue_reducing_balance_interest")  # type: ignore[misc]
def accrue_reducing_balance_interest() -> dict[str, int]:
    """Daily: accrue interest for reducing-balance loans with installments due today."""
    return asyncio.run(_run_accrue_interest())


# ── Arrears marking ───────────────────────────────────────────────────────────


async def _mark_arrears_for_tenant(schema_name: str, engine: AsyncEngine) -> int:
    """Set/clear in_arrears status for all active loans in one tenant.

    Returns count of loans whose status changed.
    """
    from app.modules.credit.models import Loan, LoanInstallment

    factory = async_sessionmaker(engine, expire_on_commit=False)
    today = date.today()
    changed_count = 0

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )

        loans = list(
            (
                await session.execute(
                    select(Loan).where(Loan.status.in_(["disbursed", "in_arrears"]))
                )
            ).scalars().all()
        )

        for loan in loans:
            try:
                async with session.begin_nested():
                    overdue_count = await session.scalar(
                        select(func.count()).select_from(LoanInstallment).where(
                            LoanInstallment.loan_id == loan.id,
                            LoanInstallment.due_date < today,
                            LoanInstallment.status.in_(["pending", "partial", "overdue"]),
                        )
                    )
                    has_overdue = (overdue_count or 0) > 0

                    if has_overdue and loan.status == "disbursed":
                        overdue_insts = list(
                            (
                                await session.execute(
                                    select(LoanInstallment).where(
                                        LoanInstallment.loan_id == loan.id,
                                        LoanInstallment.due_date < today,
                                        LoanInstallment.status.in_(["pending", "partial"]),
                                    )
                                )
                            ).scalars().all()
                        )
                        for inst in overdue_insts:
                            inst.status = "overdue"
                        loan.status = "in_arrears"
                        changed_count += 1

                    elif not has_overdue and loan.status == "in_arrears":
                        loan.status = "disbursed"
                        changed_count += 1

            except Exception as exc:
                _log.error(
                    "credit.beat.arrears_error",
                    schema=schema_name,
                    loan_id=str(loan.id),
                    error=str(exc),
                )

        await session.commit()

    return changed_count


async def _run_mark_arrears() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    totals: dict[str, int] = {}
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            schemas = [row[0] for row in result.fetchall()]
        for schema_name in schemas:
            if not _SCHEMA_RE.match(schema_name):
                continue
            try:
                count = await _mark_arrears_for_tenant(schema_name, engine)
                if count:
                    totals[schema_name] = count
            except Exception as exc:
                _log.error(
                    "credit.beat.arrears_tenant_error",
                    schema=schema_name,
                    error=str(exc),
                )
    finally:
        await engine.dispose()
    _log.info("credit.beat.mark_arrears_complete", **totals)
    return totals


@celery_app.task(name="app.modules.credit.beat.mark_loans_in_arrears")  # type: ignore[misc]
def mark_loans_in_arrears() -> dict[str, int]:
    """Daily: transition disbursed ↔ in_arrears based on overdue installments."""
    return asyncio.run(_run_mark_arrears())


# ── Snapshot reconciliation ───────────────────────────────────────────────────


async def _reconcile_for_tenant(schema_name: str, engine: AsyncEngine) -> int:
    """Compare loan snapshot outstanding_principal against GL net for one tenant.

    Checks disbursed, in_arrears, and written_off loans only.
    Returns count of drifted loans (read-only — never modifies loan rows).
    """
    from app.modules.credit.models import Loan
    from app.modules.ledger.models import JournalLine

    factory = async_sessionmaker(engine, expire_on_commit=False)
    drift_count = 0

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )

        loans = list(
            (
                await session.execute(
                    select(Loan).where(
                        Loan.status.in_(["disbursed", "in_arrears", "written_off"])
                    )
                )
            ).scalars().all()
        )

        for loan in loans:
            gl_net = await session.scalar(
                select(
                    func.coalesce(func.sum(JournalLine.debit_amount), Decimal("0"))
                    - func.coalesce(func.sum(JournalLine.credit_amount), Decimal("0"))
                ).where(
                    JournalLine.sub_ledger_type == "loan",
                    JournalLine.sub_ledger_id == loan.id,
                    JournalLine.account_id == loan.gl_principal_receivable_id,
                )
            ) or Decimal("0")

            snapshot = loan.outstanding_principal

            if abs(gl_net - snapshot) > Decimal("0.01"):
                drift_count += 1
                _log.error(
                    "loan_snapshot_drift",
                    schema=schema_name,
                    loan_id=str(loan.id),
                    loan_reference=loan.loan_reference,
                    snapshot_outstanding_principal=str(snapshot),
                    gl_net_principal=str(gl_net),
                    diff=str(gl_net - snapshot),
                )
                try:
                    from app.core.audit.service import TenantAuditService
                    audit_svc = TenantAuditService(session)
                    await audit_svc.record(
                        table_name="loans",
                        record_id=loan.id,
                        operation="loan_snapshot_drift_detected",
                        actor_type="system",
                        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
                        before_state={"outstanding_principal": str(snapshot)},
                        after_state={"gl_net_principal": str(gl_net)},
                    )
                except Exception as audit_exc:
                    _log.error(
                        "credit.beat.reconcile_audit_error",
                        loan_id=str(loan.id),
                        error=str(audit_exc),
                    )

        await session.commit()

    return drift_count


async def _run_reconcile_snapshots() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    totals: dict[str, int] = {}
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            schemas = [row[0] for row in result.fetchall()]
        for schema_name in schemas:
            if not _SCHEMA_RE.match(schema_name):
                continue
            try:
                count = await _reconcile_for_tenant(schema_name, engine)
                if count:
                    totals[schema_name] = count
            except Exception as exc:
                _log.error(
                    "credit.beat.reconcile_tenant_error",
                    schema=schema_name,
                    error=str(exc),
                )
    finally:
        await engine.dispose()
    _log.info("credit.beat.reconcile_complete", **totals)
    return totals


@celery_app.task(name="app.modules.credit.beat.reconcile_loan_snapshots")  # type: ignore[misc]
def reconcile_loan_snapshots() -> dict[str, int]:
    """Daily: compare loan snapshot fields to GL sums; alert on mismatch."""
    return asyncio.run(_run_reconcile_snapshots())
