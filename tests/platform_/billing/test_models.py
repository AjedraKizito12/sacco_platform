"""Model round-trip and constraint tests for the Phase 1 billing module.

SubscriptionPlan and Subscription use AuditableMixin, which fires SQLAlchemy
events during flush and writes audit rows. This conflicts with the
connection-bound `platform_session` fixture (asyncpg "another operation is in
progress"). All tests therefore use `async_sessionmaker` + `commit()` with
manual try/finally cleanup — the same pattern as
tests/modules/iam/keys/test_key_service.py.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Payment,
    Subscription,
    SubscriptionPlan,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _set_platform(session: AsyncSession) -> None:
    """Set search_path to platform for audit log writes (audit tables are in platform)."""
    await session.execute(text("SET search_path TO platform"))
    session.sync_session.info["is_platform"] = True


async def _make_plan(factory: async_sessionmaker[AsyncSession]) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        plan = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            per_user_price=Decimal("0"),
            per_member_price=Decimal("0"),
            billing_period="monthly",
        )
        s.add(plan)
        await s.commit()
    return plan


async def _make_tenant(factory: async_sessionmaker[AsyncSession]):
    from app.platform_.models import Tenant

    now = datetime.now(UTC)
    async with factory() as s:
        await _set_platform(s)
        tenant = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Test Tenant",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        s.add(tenant)
        await s.commit()
    return tenant


async def _make_platform_user(factory: async_sessionmaker[AsyncSession]):
    from app.platform_.models import PlatformUser

    now = datetime.now(UTC)
    async with factory() as s:
        await _set_platform(s)
        user = PlatformUser(
            email=f"u-{uuid.uuid4().hex[:8]}@test.example",
            full_name="Test Operator",
            is_active=True,
            is_superuser=True,
            created_at=now,
            updated_at=now,
        )
        s.add(user)
        await s.commit()
    return user


async def _cleanup_billing(factory: async_sessionmaker[AsyncSession]) -> None:
    """Delete all billing rows in dependency order."""

    async with factory() as s:
        await s.execute(text("SET search_path TO platform"))
        await s.execute(delete(Payment))
        await s.execute(delete(InvoiceLineItem))
        await s.execute(delete(Invoice))
        await s.execute(delete(Subscription))
        await s.execute(delete(SubscriptionPlan))
        # Clean up tenants created by these tests (slug starts with t- or sg-)
        await s.execute(
            text(
                "DELETE FROM platform.tenants WHERE slug LIKE 't-%' OR slug LIKE 'sg-%'"
            )
        )
        await s.execute(
            text(
                "DELETE FROM platform.platform_users WHERE email LIKE 'u-%@test.example'"
            )
        )
        # Remove audit logs that reference these rows (FK-free, just clean up)
        await s.execute(
            text("DELETE FROM platform.audit_log WHERE table_name IN "
                 "('subscription_plans', 'subscriptions', 'tenants', 'platform_users')")
        )
        await s.commit()


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_subscription_plan_roundtrip(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        plan = await _make_plan(factory)

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            fetched = await s.scalar(
                select(SubscriptionPlan).where(SubscriptionPlan.id == plan.id)
            )
        assert fetched is not None
        assert fetched.code == plan.code
        assert fetched.billing_period == "monthly"
        assert fetched.is_active is True
        assert fetched.currency == "UGX"
    finally:
        await _cleanup_billing(factory)


@pytest.mark.anyio
async def test_subscription_plan_invalid_period_rejected(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    with pytest.raises(IntegrityError):
        async with factory() as s:
            await _set_platform(s)
            plan = SubscriptionPlan(
                code=f"bad-{uuid.uuid4().hex[:8]}",
                name="Bad",
                base_price=Decimal("1000"),
                billing_period="bogus",
            )
            s.add(plan)
            await s.commit()


@pytest.mark.anyio
async def test_subscription_roundtrip(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        plan = await _make_plan(factory)
        tenant = await _make_tenant(factory)

        async with factory() as s:
            await _set_platform(s)
            sub = Subscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="active",
                current_period_start=date(2026, 6, 1),
                current_period_end=date(2026, 6, 30),
            )
            s.add(sub)
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            fetched = await s.scalar(
                select(Subscription).where(Subscription.id == sub.id)
            )
        assert fetched is not None
        assert fetched.status == "active"
        assert fetched.metadata_json == {}
    finally:
        await _cleanup_billing(factory)


@pytest.mark.anyio
async def test_subscription_invalid_status_rejected(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        plan = await _make_plan(factory)
        tenant = await _make_tenant(factory)

        with pytest.raises(IntegrityError):
            async with factory() as s:
                await _set_platform(s)
                sub = Subscription(
                    tenant_id=tenant.id,
                    plan_id=plan.id,
                    status="not-a-status",
                    current_period_start=date(2026, 6, 1),
                    current_period_end=date(2026, 6, 30),
                )
                s.add(sub)
                await s.commit()
    finally:
        await _cleanup_billing(factory)


@pytest.mark.anyio
async def test_subscription_one_live_per_tenant(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        plan = await _make_plan(factory)
        tenant = await _make_tenant(factory)

        async with factory() as s:
            await _set_platform(s)
            sub1 = Subscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="active",
                current_period_start=date(2026, 6, 1),
                current_period_end=date(2026, 6, 30),
            )
            s.add(sub1)
            await s.commit()

        with pytest.raises(IntegrityError):
            async with factory() as s:
                await _set_platform(s)
                sub2 = Subscription(
                    tenant_id=tenant.id,
                    plan_id=plan.id,
                    status="active",
                    current_period_start=date(2026, 7, 1),
                    current_period_end=date(2026, 7, 31),
                )
                s.add(sub2)
                await s.commit()
    finally:
        await _cleanup_billing(factory)


@pytest.mark.anyio
async def test_subscription_cancelled_then_new_active_allowed(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        plan = await _make_plan(factory)
        tenant = await _make_tenant(factory)

        async with factory() as s:
            await _set_platform(s)
            sub1 = Subscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="cancelled",
                current_period_start=date(2026, 6, 1),
                current_period_end=date(2026, 6, 30),
                cancelled_at=datetime.now(UTC),
            )
            s.add(sub1)
            await s.commit()

        # Adding a second active subscription after cancellation should succeed
        async with factory() as s:
            await _set_platform(s)
            sub2 = Subscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="active",
                current_period_start=date(2026, 7, 1),
                current_period_end=date(2026, 7, 31),
            )
            s.add(sub2)
            await s.commit()  # should not raise
    finally:
        await _cleanup_billing(factory)


@pytest.mark.anyio
async def test_invoice_with_line_items_cascade_delete(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        plan = await _make_plan(factory)
        tenant = await _make_tenant(factory)

        async with factory() as s:
            await _set_platform(s)
            sub = Subscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="active",
                current_period_start=date(2026, 6, 1),
                current_period_end=date(2026, 6, 30),
            )
            s.add(sub)
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            invoice = Invoice(
                invoice_number=f"INV-TEST-{uuid.uuid4().hex[:8]}",
                subscription_id=sub.id,
                tenant_id=tenant.id,
                billing_period_start=date(2026, 6, 1),
                billing_period_end=date(2026, 6, 30),
                amount_subtotal=Decimal("50000.0000"),
                amount_total=Decimal("50000.0000"),
                due_at=date(2026, 7, 7),
            )
            s.add(invoice)
            await s.flush()

            line = InvoiceLineItem(
                invoice_id=invoice.id,
                description="Base subscription",
                quantity=1,
                unit_price=Decimal("50000.0000"),
                amount=Decimal("50000.0000"),
                line_order=1,
            )
            s.add(line)
            await s.commit()
            line_id = line.id

        # Delete the invoice — line items should cascade
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            inv = await s.scalar(select(Invoice).where(Invoice.id == invoice.id))
            assert inv is not None
            await s.delete(inv)
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            remaining = await s.scalar(
                select(InvoiceLineItem).where(InvoiceLineItem.id == line_id)
            )
        assert remaining is None
    finally:
        await _cleanup_billing(factory)


@pytest.mark.anyio
async def test_payment_invalid_method_rejected(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        plan = await _make_plan(factory)
        tenant = await _make_tenant(factory)
        user = await _make_platform_user(factory)

        async with factory() as s:
            await _set_platform(s)
            sub = Subscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="active",
                current_period_start=date(2026, 6, 1),
                current_period_end=date(2026, 6, 30),
            )
            s.add(sub)
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            invoice = Invoice(
                invoice_number=f"INV-PMT-{uuid.uuid4().hex[:8]}",
                subscription_id=sub.id,
                tenant_id=tenant.id,
                billing_period_start=date(2026, 6, 1),
                billing_period_end=date(2026, 6, 30),
                amount_subtotal=Decimal("50000"),
                amount_total=Decimal("50000"),
                due_at=date(2026, 7, 7),
                status="issued",
            )
            s.add(invoice)
            await s.commit()

        with pytest.raises(IntegrityError):
            async with factory() as s:
                await s.execute(text("SET search_path TO platform"))
                pmt = Payment(
                    invoice_id=invoice.id,
                    amount=Decimal("50000"),
                    payment_method="paypal",  # not in CHECK constraint
                    recorded_by=user.id,
                )
                s.add(pmt)
                await s.commit()
    finally:
        await _cleanup_billing(factory)


@pytest.mark.anyio
async def test_tenant_subscription_status_check_constraint(test_engine: AsyncEngine):
    from app.platform_.models import Tenant

    factory = _factory(test_engine)
    now = datetime.now(UTC)

    async with factory() as s:
        await _set_platform(s)
        t = Tenant(
            slug=f"sg-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_sg_{uuid.uuid4().hex[:8]}",
            name="Status Gate Tenant",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        s.add(t)
        await s.commit()
        tenant_id = t.id

    try:
        with pytest.raises(IntegrityError):
            async with factory() as s:
                await s.execute(text("SET search_path TO platform"))
                await s.execute(
                    text(
                        "UPDATE platform.tenants "
                        "SET subscription_status = 'bogus' WHERE id = :id"
                    ),
                    {"id": str(tenant_id)},
                )
                await s.commit()
    finally:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            await s.execute(
                text("DELETE FROM platform.audit_log WHERE record_id = :id"),
                {"id": str(tenant_id)},
            )
            await s.execute(
                text("DELETE FROM platform.tenants WHERE id = :id"),
                {"id": str(tenant_id)},
            )
            await s.commit()
