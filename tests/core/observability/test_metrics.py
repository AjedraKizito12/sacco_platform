"""Tests for app.core.observability.metrics.compute_business_gauges.

compute_business_gauges is a pure read-only aggregation over an already-open
AsyncSession (platform schema) — it never touches Logfire.

NOTE on fixture choice: the brief's illustrative test uses `platform_session`,
but that fixture (tests/conftest.py:133, `conn.begin()` + `AsyncSession(bind=conn)`)
is broken in this environment for ANY query — even a bare `SELECT 1` — with
`asyncpg` raising "attached to a different loop" (same underlying issue noted
in the project's IAM test-pattern memory for flush()/commit(), but here it
reproduces on reads too). No test in the repo currently exercises
`platform_session`/`tenant_session` directly; every DB-touching test instead
uses the proven `async_sessionmaker(test_engine) + commit()` pattern (see
tests/platform_/billing/test_models.py, tests/modules/iam/keys/test_key_service.py).
This file follows that proven pattern — `compute_business_gauges` itself still
takes a plain `AsyncSession` per the design contract; only the *construction*
of that session in tests differs from the brief's illustrative snippet.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.observability.metrics import compute_business_gauges
from app.platform_.billing.models import Invoice, Subscription, SubscriptionPlan
from app.platform_.models import Tenant

EXPECTED_KEYS = {
    "sacco_tenants_total",
    "sacco_subscriptions_total",
    "sacco_subscriptions_mrr",
    "sacco_invoices_outstanding",
    "sacco_backup_age_seconds",
    "sacco_outbox_queue_depth",
}


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _platform(session: AsyncSession) -> None:
    await session.execute(text("SET search_path TO platform"))
    session.sync_session.info["is_platform"] = True


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s:
        await _platform(s)
        await s.execute(delete(Invoice))
        await s.execute(delete(Subscription))
        await s.execute(delete(SubscriptionPlan))
        await s.execute(text("DELETE FROM platform.tenants WHERE slug LIKE 'obs-%'"))
        await s.execute(
            text(
                "DELETE FROM platform.audit_log WHERE table_name IN "
                "('subscription_plans', 'subscriptions', 'tenants')"
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_compute_business_gauges_shapes(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    async with factory() as session:
        await _platform(session)
        result = await compute_business_gauges(session)

    assert EXPECTED_KEYS.issubset(result.keys())

    # MRR only counts active + trialing (contract) — every entry is numeric.
    assert all(isinstance(v, int | float) for _, v in result["sacco_subscriptions_mrr"])

    # Every metric's readings are (labels_dict, numeric_value) pairs.
    for readings in result.values():
        for labels, value in readings:
            assert isinstance(labels, dict)
            assert isinstance(value, int | float)


@pytest.mark.asyncio
async def test_compute_business_gauges_backup_age_sentinel_when_no_succeeded_run(
    test_engine: AsyncEngine,
):
    factory = _factory(test_engine)
    async with factory() as session:
        await _platform(session)
        result = await compute_business_gauges(session)

    # No succeeded backup_runs rows: sentinel 0, single reading, no labels.
    assert result["sacco_backup_age_seconds"] == [({}, 0.0)]


@pytest.mark.asyncio
async def test_compute_business_gauges_outbox_depth_present(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    async with factory() as session:
        await _platform(session)
        result = await compute_business_gauges(session)

    readings = result["sacco_outbox_queue_depth"]
    assert len(readings) == 1
    labels, value = readings[0]
    assert labels == {"schema": "platform"}
    assert isinstance(value, int)
    assert value >= 0


@pytest.mark.asyncio
async def test_compute_business_gauges_reflects_seeded_data(test_engine: AsyncEngine):
    """Seeded-data assertion: async_sessionmaker + commit (not platform_session,
    not flush()) per the project's known-working DB test pattern."""
    factory = _factory(test_engine)
    now = datetime.now(UTC)
    today = date.today()

    try:
        async with factory() as s:
            await _platform(s)
            tenant = Tenant(
                slug=f"obs-{uuid.uuid4().hex[:8]}",
                schema_name=f"tenant_obs_{uuid.uuid4().hex[:8]}",
                name="Obs Test Tenant",
                status="active",
                is_active=True,
                subscription_status="active",
                created_at=now,
                updated_at=now,
            )
            s.add(tenant)
            await s.flush()

            plan = SubscriptionPlan(
                code=f"obs-plan-{uuid.uuid4().hex[:8]}",
                name="Obs Plan",
                currency="UGX",
                base_price=Decimal("75000.0000"),
                billing_period="monthly",
            )
            s.add(plan)
            await s.flush()

            subscription = Subscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="active",
                current_period_start=today,
                current_period_end=today,
            )
            s.add(subscription)
            await s.flush()

            invoice = Invoice(
                invoice_number=f"OBS-{uuid.uuid4().hex[:10]}",
                subscription_id=subscription.id,
                tenant_id=tenant.id,
                billing_period_start=today,
                billing_period_end=today,
                amount_subtotal=Decimal("75000.0000"),
                amount_total=Decimal("75000.0000"),
                currency="UGX",
                status="issued",
                due_at=today,
            )
            s.add(invoice)
            await s.commit()

        async with factory() as session:
            await _platform(session)
            result = await compute_business_gauges(session)

        tenant_counts = dict(
            (status, count) for status, count in result["sacco_tenants_total"]
            for status in [status["status"]]
        )
        assert tenant_counts.get("active", 0) >= 1

        mrr_by_currency = {
            labels["currency"]: value for labels, value in result["sacco_subscriptions_mrr"]
        }
        assert mrr_by_currency.get("UGX", 0) >= 75000.0

        invoice_statuses = {
            labels["status"] for labels, _ in result["sacco_invoices_outstanding"]
        }
        assert "issued" in invoice_statuses
    finally:
        await _cleanup(factory)
