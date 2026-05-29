# app/modules/reporting/beat.py
"""Celery beat tasks for the reporting module.

Five nightly tasks, one per report type:
    materialize_trial_balance        — 01:00 UTC
    materialize_loan_portfolio       — 01:00 UTC  (added in sub-plan 03)
    materialize_income_statement     — 01:00 UTC  (added in sub-plan 04)
    materialize_savings_statement    — 01:00 UTC  (added in sub-plan 05)
    materialize_fee_collection       — 01:00 UTC  (added in sub-plan 06)

Each task:
1. Lists all active tenant schemas from platform.tenants.
2. For each schema: opens a session, sets search_path, runs materialize().
3. Failures per tenant are logged and skipped — other tenants continue.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


async def _materialize_trial_balance_for_tenant(schema_name: str, engine, as_of: date) -> None:
    from app.modules.reporting.services.trial_balance import TrialBalanceService  # noqa: PLC0415

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        svc = TrialBalanceService(session)
        await svc.materialize(as_of_date=as_of)
        await session.commit()


async def _run_materialize_trial_balance() -> dict[str, str]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    as_of = date.today()
    result: dict[str, str] = {}
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            schemas = [row[0] for row in rows.fetchall()]
        for schema_name in schemas:
            if not _SCHEMA_RE.match(schema_name):
                continue
            try:
                await _materialize_trial_balance_for_tenant(schema_name, engine, as_of)
                result[schema_name] = "done"
            except Exception as exc:
                _log.error(
                    "reporting.beat.trial_balance_error",
                    schema=schema_name,
                    error=str(exc),
                )
                result[schema_name] = f"error: {exc}"
    finally:
        await engine.dispose()
    _log.info("reporting.beat.trial_balance_complete", **result)
    return result


@celery_app.task(name="app.modules.reporting.beat.materialize_trial_balance")  # type: ignore[misc]
def materialize_trial_balance() -> dict[str, str]:
    """Nightly 01:00 UTC: materialize trial balance for all active tenants."""
    return asyncio.run(_run_materialize_trial_balance())


async def _materialize_loan_portfolio_for_tenant(schema_name: str, engine, as_of: date) -> None:
    from app.modules.reporting.services.loan_portfolio import LoanPortfolioService  # noqa: PLC0415

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        svc = LoanPortfolioService(session)
        await svc.materialize(as_of_date=as_of)
        await session.commit()


async def _run_materialize_loan_portfolio() -> dict[str, str]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    as_of = date.today()
    result: dict[str, str] = {}
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            schemas = [row[0] for row in rows.fetchall()]
        for schema_name in schemas:
            if not _SCHEMA_RE.match(schema_name):
                continue
            try:
                await _materialize_loan_portfolio_for_tenant(schema_name, engine, as_of)
                result[schema_name] = "done"
            except Exception as exc:
                _log.error(
                    "reporting.beat.loan_portfolio_error",
                    schema=schema_name,
                    error=str(exc),
                )
                result[schema_name] = f"error: {exc}"
    finally:
        await engine.dispose()
    _log.info("reporting.beat.loan_portfolio_complete", **result)
    return result


@celery_app.task(name="app.modules.reporting.beat.materialize_loan_portfolio")  # type: ignore[misc]
def materialize_loan_portfolio() -> dict[str, str]:
    """Nightly 01:00 UTC: materialize loan portfolio for all active tenants."""
    return asyncio.run(_run_materialize_loan_portfolio())
