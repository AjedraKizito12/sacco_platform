"""PaymentService tests."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Payment,
    Subscription,
    SubscriptionPlan,
)
from app.platform_.billing.services import (
    InvoiceService,
    PaymentService,
    SubscriptionService,
)
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(factory) -> Tenant:
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Test Tenant",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t


async def _make_plan(factory) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p


async def _make_platform_user(factory) -> PlatformUser:
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        u = PlatformUser(
            email=f"u-{uuid.uuid4().hex[:8]}@test.example",
            full_name="Test Operator",
            is_active=True,
            is_superuser=True,
            created_at=now,
            updated_at=now,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


async def _cleanup(factory) -> None:
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL, "
                "subscription_status = 'pending'"
            )
        )
        await s.execute(delete(Payment))
        await s.execute(delete(InvoiceLineItem))
        await s.execute(delete(Invoice))
        await s.execute(delete(Subscription))
        await s.execute(delete(SubscriptionPlan))
        await s.execute(delete(Tenant))
        await s.execute(delete(PlatformUser))
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.commit()


@pytest.fixture
async def factory(test_engine: AsyncEngine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def _make_invoice(factory, plan, tenant) -> uuid.UUID:
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(
            tenant_id=tenant.id, plan_id=plan.id
        )
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        inv = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        return inv.id


@pytest.mark.anyio
async def test_record_creates_pending_payment(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    user = await _make_platform_user(factory)
    invoice_id = await _make_invoice(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            pmt = await svc.record(
                invoice_id=invoice_id,
                amount=Decimal("50000"),
                currency="UGX",
                payment_method="bank_transfer",
                recorded_by=user.id,
                idempotency_key="key-aaaaa-001",
                external_reference="BANK-TXN-1",
            )
            await s.commit()
            assert pmt.status == "pending"
            assert pmt.amount == Decimal("50000")
            assert pmt.idempotency_key == "key-aaaaa-001"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_record_is_idempotent_on_same_key(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    user = await _make_platform_user(factory)
    invoice_id = await _make_invoice(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            a = await svc.record(
                invoice_id=invoice_id,
                amount=Decimal("50000"),
                currency="UGX",
                payment_method="cash",
                recorded_by=user.id,
                idempotency_key="key-bbbbb-001",
            )
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            b = await svc.record(
                invoice_id=invoice_id,
                amount=Decimal("50000"),
                currency="UGX",
                payment_method="cash",
                recorded_by=user.id,
                idempotency_key="key-bbbbb-001",
            )
            await s.commit()
        assert a.id == b.id
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_record_rejects_unknown_invoice(factory) -> None:
    user = await _make_platform_user(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            with pytest.raises(ValueError, match="Invoice"):
                await svc.record(
                    invoice_id=uuid.uuid4(),
                    amount=Decimal("100"),
                    currency="UGX",
                    payment_method="cash",
                    recorded_by=user.id,
                    idempotency_key="key-no-inv",
                )
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_record_rejects_currency_mismatch(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    user = await _make_platform_user(factory)
    invoice_id = await _make_invoice(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            with pytest.raises(ValueError, match="Currency mismatch"):
                await svc.record(
                    invoice_id=invoice_id,
                    amount=Decimal("50000"),
                    currency="USD",
                    payment_method="cash",
                    recorded_by=user.id,
                    idempotency_key="key-curr-001",
                )
    finally:
        await _cleanup(factory)
