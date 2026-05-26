"""Celery beat tasks for fee assessment scheduling and partial-collection retry.

assess_scheduled_fees       — daily: assess fees due for all schedule-triggered fee types
retry_partial_fee_collections — daily: retry savings deduction for partially-paid assessments
"""
from __future__ import annotations

import asyncio
import re
from datetime import UTC, date, datetime

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


def _is_annual_sub_due(fee_type, member_id, today: date, last_assessment_period_end: date | None) -> bool:
    """Return True if member is due for annual subscription fee."""
    if last_assessment_period_end is None:
        return True
    return last_assessment_period_end < today


async def _assess_scheduled_for_tenant(schema_name: str, engine) -> int:
    """Assess all due schedule-triggered fees for one tenant. Returns count."""
    import uuid as _uuid
    from app.modules.fees.models import FeeAssessment, FeeType
    from app.modules.fees.service import FeeAssessmentService
    from app.modules.members.models import Member

    factory = async_sessionmaker(engine, expire_on_commit=False)
    assessed = 0
    today = date.today()
    _SYSTEM_ACTOR = _uuid.UUID("00000000-0000-0000-0000-000000000000")

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )

        fee_types = list(
            (
                await session.execute(
                    select(FeeType).where(
                        FeeType.trigger_kind == "schedule",
                        FeeType.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )

        for ft in fee_types:
            if ft.applicable_to != "member":
                continue  # Other target types deferred to future modules.

            config = ft.schedule_config or {}
            recurrence = config.get("recurrence", "yearly")
            month = int(config.get("month", 1))
            day = int(config.get("day", 1))

            # Get all active members.
            members = list(
                (
                    await session.execute(
                        select(Member).where(Member.status == "active")
                    )
                ).scalars().all()
            )

            svc = FeeAssessmentService(session)

            for member in members:
                # Find latest assessment period_end for this fee_type + member.
                latest = await session.scalar(
                    select(FeeAssessment.period_end)
                    .where(
                        FeeAssessment.fee_type_id == ft.id,
                        FeeAssessment.target_type == "member",
                        FeeAssessment.target_id == member.id,
                        FeeAssessment.status.in_(["assessed", "partially_paid", "paid"]),
                    )
                    .order_by(FeeAssessment.period_start.desc())
                    .limit(1)
                )

                if not _is_annual_sub_due(ft, member.id, today, latest):
                    continue

                # Compute the period for the current cycle.
                period_start = date(today.year, month, day)
                if period_start > today:
                    period_start = date(today.year - 1, month, day)
                period_end = date(period_start.year + 1, month, day)

                try:
                    async with session.begin_nested():
                        await svc.assess(
                            fee_type=ft,
                            target_type="member",
                            target_id=member.id,
                            period_start=period_start,
                            period_end=period_end,
                            triggered_by_event_id=None,
                            actor=_SYSTEM_ACTOR,
                            idempotency_key=f"sched-{ft.id}-{member.id}-{period_start.isoformat()}",
                        )
                        assessed += 1
                except Exception as exc:
                    _log.error(
                        "fees.beat.assess_error",
                        schema=schema_name,
                        fee_type=ft.code,
                        member_id=str(member.id),
                        error=str(exc),
                    )

        await session.commit()

    return assessed


async def _retry_partial_for_tenant(schema_name: str, engine) -> dict[str, int]:
    """Retry collection for assessed/partially_paid assessments. Returns stats."""
    import uuid as _uuid
    from app.modules.fees.models import FeeAssessment, FeeType
    from app.modules.fees.service import FeeCollectionService
    from app.modules.ledger.models import ChartOfAccount

    factory = async_sessionmaker(engine, expire_on_commit=False)
    stats = {"retried": 0, "fully_collected": 0, "still_partial": 0}
    _SYSTEM_ACTOR = _uuid.UUID("00000000-0000-0000-0000-000000000000")
    today = date.today()

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )

        assessments = list(
            (
                await session.execute(
                    select(FeeAssessment)
                    .join(FeeType)
                    .where(
                        FeeAssessment.status.in_(["assessed", "partially_paid"]),
                        FeeType.requires_collection.is_(True),
                    )
                )
            ).scalars().all()
        )

        coll_svc = FeeCollectionService(session)

        for assessment in assessments:
            ft = await session.get(FeeType, assessment.fee_type_id)
            if ft is None:
                continue

            receivable_account = await session.scalar(
                select(ChartOfAccount).where(ChartOfAccount.code == ft.gl_receivable_account_code)
            )
            if receivable_account is None:
                continue

            try:
                async with session.begin_nested():
                    await coll_svc.auto_collect(
                        assessment=assessment,
                        fee_type=ft,
                        receivable_account_id=receivable_account.id,
                        idempotency_key=f"retry-{assessment.id}-{today.isoformat()}",
                    )
                    stats["retried"] += 1
                    if assessment.status == "paid":
                        stats["fully_collected"] += 1
                    else:
                        stats["still_partial"] += 1
            except Exception as exc:
                _log.error(
                    "fees.beat.retry_error",
                    schema=schema_name,
                    assessment_id=str(assessment.id),
                    error=str(exc),
                )

        await session.commit()

    return stats


async def _run_assess_scheduled() -> dict[str, int]:
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
                count = await _assess_scheduled_for_tenant(schema_name, engine)
                if count:
                    totals[schema_name] = count
            except Exception as exc:
                _log.error("fees.beat.assess_tenant_error", schema=schema_name, error=str(exc))
    finally:
        await engine.dispose()
    _log.info("fees.beat.assess_scheduled_complete", **totals)
    return totals


async def _run_retry_partial() -> dict[str, object]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    result: dict[str, object] = {}
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
                stats = await _retry_partial_for_tenant(schema_name, engine)
                if any(stats.values()):
                    result[schema_name] = stats
            except Exception as exc:
                _log.error("fees.beat.retry_tenant_error", schema=schema_name, error=str(exc))
    finally:
        await engine.dispose()
    _log.info("fees.beat.retry_partial_complete", **{k: str(v) for k, v in result.items()})
    return result


@celery_app.task(name="app.modules.fees.beat.assess_scheduled_fees")  # type: ignore[misc]
def assess_scheduled_fees() -> dict[str, int]:
    """Daily: assess schedule-triggered fees due for all active tenants."""
    return asyncio.run(_run_assess_scheduled())


@celery_app.task(name="app.modules.fees.beat.retry_partial_fee_collections")  # type: ignore[misc]
def retry_partial_fee_collections() -> dict[str, object]:
    """Daily: retry savings deduction for assessed/partially_paid fee assessments."""
    return asyncio.run(_run_retry_partial())
