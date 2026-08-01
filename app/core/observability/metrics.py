"""Business-metric OTel gauges for the platform + tenant schemas.

`compute_business_gauges` is a pure, read-only aggregation over an already
open `AsyncSession` (platform schema). It never touches Logfire — this keeps
it trivially testable with the `platform_session` fixture, offline.

`record_business_gauges` is the beat entrypoint: it opens its own engine,
computes the platform gauges via `compute_business_gauges`, computes the
per-tenant-schema gauges directly (loans by status, outbox queue depth), and
pushes every reading onto the module-level gauge handles below. Per-schema
failures are isolated (logged, skipped) so one broken tenant schema never
blocks the others — same pattern as `app/core/notifications/beat.py`.
"""
from __future__ import annotations

import re
from typing import Any

import logfire
import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.outbox.models import PlatformOutboxEvent, TenantOutboxEvent
from app.platform_.billing.models import Invoice, Subscription, SubscriptionPlan
from app.platform_.models import Tenant
from app.platform_.ops.models import BackupRun

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")

GaugeLabels = dict[str, str]
GaugeReading = tuple[GaugeLabels, float | int]
BusinessGauges = dict[str, list[GaugeReading]]

INVOICE_OUTSTANDING_STATUSES = ("issued", "partial", "overdue")
MRR_STATUSES = ("active", "trialing")

# ── Gauge handles ────────────────────────────────────────────────────────────
# Only used by record_business_gauges — never by compute_business_gauges, so
# importing/calling compute_business_gauges never touches Logfire egress.
tenants_total_gauge = logfire.metric_gauge(
    "sacco_tenants_total", unit="1", description="Count of platform tenants by status"
)
subscriptions_total_gauge = logfire.metric_gauge(
    "sacco_subscriptions_total", unit="1", description="Count of subscriptions by status"
)
subscriptions_mrr_gauge = logfire.metric_gauge(
    "sacco_subscriptions_mrr",
    unit="1",
    description="MRR: sum of active/trialing subscriptions' plan base_price, by currency",
)
invoices_outstanding_gauge = logfire.metric_gauge(
    "sacco_invoices_outstanding",
    unit="1",
    description="Count of outstanding (issued/partial/overdue) invoices by status",
)
backup_age_gauge = logfire.metric_gauge(
    "sacco_backup_age_seconds",
    unit="s",
    description="Seconds since the last succeeded backup run finished",
)
outbox_queue_depth_gauge = logfire.metric_gauge(
    "sacco_outbox_queue_depth",
    unit="1",
    description="Count of unpublished, non-dead-lettered outbox events, per schema",
)
loans_total_gauge = logfire.metric_gauge(
    "sacco_loans_total", unit="1", description="Count of tenant loans by status"
)


async def compute_business_gauges(session: AsyncSession) -> BusinessGauges:
    """Read-only aggregation of platform-schema business gauges.

    Returns `{metric_name: [(labels, value), ...]}`. All sums/counts COALESCE
    to 0 so an empty database still returns present keys with numeric values.
    Never touches Logfire — pure SQL reads on the passed session.
    """
    result: BusinessGauges = {}

    tenants_rows = (
        await session.execute(select(Tenant.status, func.count()).group_by(Tenant.status))
    ).all()
    result["sacco_tenants_total"] = [
        ({"status": status}, int(count)) for status, count in tenants_rows
    ]

    subs_rows = (
        await session.execute(
            select(Subscription.status, func.count()).group_by(Subscription.status)
        )
    ).all()
    result["sacco_subscriptions_total"] = [
        ({"status": status}, int(count)) for status, count in subs_rows
    ]

    mrr_rows = (
        await session.execute(
            select(
                SubscriptionPlan.currency,
                func.coalesce(func.sum(SubscriptionPlan.base_price), 0),
            )
            .select_from(Subscription)
            .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
            .where(Subscription.status.in_(MRR_STATUSES))
            .group_by(SubscriptionPlan.currency)
        )
    ).all()
    result["sacco_subscriptions_mrr"] = [
        ({"currency": currency}, float(total)) for currency, total in mrr_rows
    ]

    invoice_rows = (
        await session.execute(
            select(Invoice.status, func.count())
            .where(Invoice.status.in_(INVOICE_OUTSTANDING_STATUSES))
            .group_by(Invoice.status)
        )
    ).all()
    result["sacco_invoices_outstanding"] = [
        ({"status": status}, int(count)) for status, count in invoice_rows
    ]

    backup_age = (
        await session.execute(
            select(
                func.extract("epoch", func.now() - func.max(BackupRun.finished_at))
            ).where(BackupRun.status == "succeeded")
        )
    ).scalar()
    # No succeeded backup run yet: sentinel 0 rather than null/negative.
    result["sacco_backup_age_seconds"] = [
        ({}, float(backup_age) if backup_age is not None else 0.0)
    ]

    outbox_count = (
        await session.execute(
            select(func.count())
            .select_from(PlatformOutboxEvent)
            .where(
                PlatformOutboxEvent.published_at.is_(None),
                PlatformOutboxEvent.is_dead_lettered.is_(False),
            )
        )
    ).scalar_one()
    result["sacco_outbox_queue_depth"] = [({"schema": "platform"}, int(outbox_count))]

    return result


async def _schemas(engine: AsyncEngine) -> list[str]:
    """All scopes: the platform schema + active tenant schemas."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
        )
        tenant_schemas = [row[0] for row in rows.fetchall() if _SCHEMA_RE.match(row[0])]
    return ["platform", *tenant_schemas]


def _apply(gauge: Any, readings: list[GaugeReading]) -> None:
    for labels, value in readings:
        gauge.set(value, labels)


async def _record_tenant_gauges(engine: AsyncEngine, schema: str) -> None:
    """Compute + push sacco_loans_total and sacco_outbox_queue_depth for one tenant schema."""
    from app.modules.credit.models import Loan

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))  # noqa: S608
        loan_rows = (
            await session.execute(select(Loan.status, func.count()).group_by(Loan.status))
        ).all()
        outbox_count = (
            await session.execute(
                select(func.count())
                .select_from(TenantOutboxEvent)
                .where(
                    TenantOutboxEvent.published_at.is_(None),
                    TenantOutboxEvent.is_dead_lettered.is_(False),
                )
            )
        ).scalar_one()

    for status, count in loan_rows:
        loans_total_gauge.set(int(count), {"status": status})
    outbox_queue_depth_gauge.set(int(outbox_count), {"schema": schema})


async def record_business_gauges() -> None:
    """Beat entrypoint: compute every business gauge and push it to Logfire."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.sync_session.info["is_platform"] = True
            await session.execute(text("SET LOCAL search_path TO platform"))
            platform_gauges = await compute_business_gauges(session)

        _apply(tenants_total_gauge, platform_gauges["sacco_tenants_total"])
        _apply(subscriptions_total_gauge, platform_gauges["sacco_subscriptions_total"])
        _apply(subscriptions_mrr_gauge, platform_gauges["sacco_subscriptions_mrr"])
        _apply(invoices_outstanding_gauge, platform_gauges["sacco_invoices_outstanding"])
        _apply(backup_age_gauge, platform_gauges["sacco_backup_age_seconds"])
        _apply(outbox_queue_depth_gauge, platform_gauges["sacco_outbox_queue_depth"])

        for schema in await _schemas(engine):
            if schema == "platform":
                continue
            try:
                await _record_tenant_gauges(engine, schema)
            except Exception as exc:  # keep other schemas running
                _log.warning(
                    "observability.beat_schema_failed", schema=schema, error=str(exc)
                )
    finally:
        await engine.dispose()
