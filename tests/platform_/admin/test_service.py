"""Unit tests for DashboardStatsService.

Each test seeds a known fixture, runs the service, and asserts the
relevant aggregation.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.platform_.admin.service import DashboardStatsService
from app.platform_.billing.models import Invoice, Subscription, SubscriptionPlan
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.models import PlatformUser, Tenant


async def _seed_tenants(
    factory: async_sessionmaker, *, by_status: dict[str, int],
) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        for status, count in by_status.items():
            for _ in range(count):
                t = Tenant(
                    slug=f"t-{uuid.uuid4().hex[:8]}",
                    schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
                    name="T",
                    status=status,
                    is_active=True,
                    created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
                )
                s.add(t)


async def _seed_plan(
    factory: async_sessionmaker,
    *,
    base_price: str,
    period: str,
    currency: str = "UGX",
) -> SubscriptionPlan:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        p = SubscriptionPlan(
            code=f"p-{uuid.uuid4().hex[:6]}",
            name="P",
            currency=currency,
            base_price=Decimal(base_price),
            billing_period=period,
            is_active=True,
        )
        s.add(p)
    return p


async def _seed_subscription(
    factory: async_sessionmaker,
    *,
    plan_id: uuid.UUID,
    status: str = "active",
) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="T", status="active", is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(t)
        await s.flush()
        sub = Subscription(
            tenant_id=t.id, plan_id=plan_id, status=status,
            started_at=datetime.now(UTC),
            current_period_start=date.today(),
            current_period_end=date.today() + timedelta(days=30),
        )
        s.add(sub)


async def _seed_invoice(
    factory: async_sessionmaker,
    *,
    status: str,
    amount_total: str,
    amount_paid: str = "0",
    currency: str = "UGX",
) -> None:
    """Quick-and-dirty seed; relies on a tenant + subscription existing.
    Caller seeds those first.
    """
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        tenant_id = (
            await s.execute(text("SELECT id FROM platform.tenants LIMIT 1"))
        ).scalar()
        sub_id = (
            await s.execute(text("SELECT id FROM platform.subscriptions LIMIT 1"))
        ).scalar()
        inv = Invoice(
            invoice_number=f"INV-{uuid.uuid4().hex[:10]}",
            subscription_id=sub_id,
            tenant_id=tenant_id,
            billing_period_start=date.today(),
            billing_period_end=date.today() + timedelta(days=30),
            amount_subtotal=Decimal(amount_total),
            amount_total=Decimal(amount_total),
            amount_paid=Decimal(amount_paid),
            currency=currency,
            status=status,
            due_at=date.today(),
        )
        s.add(inv)


async def _seed_impersonation(
    factory: async_sessionmaker,
    *,
    active: bool,
) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"i-{uuid.uuid4().hex[:6]}@test.example",
            full_name="I",
            role="admin",
            is_active=True, is_superuser=False,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="T", status="active", is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add_all([u, t])
        await s.flush()
        now = datetime.now(UTC)
        imp = SupportImpersonation(
            platform_user_id=u.id, tenant_id=t.id,
            reason="r" * 10,
            started_at=now,
            expires_at=now + timedelta(minutes=30) if active else now - timedelta(minutes=1),
            ended_at=None if active else now,
            ended_by=None if active else u.id,
            created_at=now, updated_at=now,
        )
        s.add(imp)


async def _create_actor_for_followup(
    factory: async_sessionmaker,
) -> PlatformUser:
    """Minimal platform-user seed for tests that need a requested_by FK."""
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"f-{uuid.uuid4().hex[:6]}@test.example",
            full_name="F",
            role="admin",
            is_active=True, is_superuser=False,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup(factory: async_sessionmaker) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL, "
                "subscription_status = 'pending'"
            )
        )
        await s.execute(text("DELETE FROM platform.support_impersonations"))
        await s.execute(text("DELETE FROM platform.payments"))
        await s.execute(text("DELETE FROM platform.invoice_line_items"))
        await s.execute(text("DELETE FROM platform.invoices"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.subscriptions"))
        await s.execute(text("DELETE FROM platform.subscription_plans"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


async def test_tenant_counts_by_status(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_tenants(factory, by_status={"active": 3, "suspended": 1, "pending": 2})
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            stats = await DashboardStatsService(s).compute()
            assert stats.tenants == {"active": 3, "suspended": 1, "pending": 2}
    finally:
        await _cleanup(factory)


async def test_mrr_normalises_per_period(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monthly = await _seed_plan(factory, base_price="100", period="monthly")
    quarterly = await _seed_plan(factory, base_price="900", period="quarterly")  # 300/mo
    annual = await _seed_plan(factory, base_price="1200", period="annual")  # 100/mo
    await _seed_subscription(factory, plan_id=monthly.id)
    await _seed_subscription(factory, plan_id=quarterly.id)
    await _seed_subscription(factory, plan_id=annual.id)
    # cancelled subscription doesn't count
    await _seed_subscription(factory, plan_id=monthly.id, status="cancelled")
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            stats = await DashboardStatsService(s).compute()
            # 100 + 300 + 100 = 500 UGX/month
            assert stats.mrr == {"UGX": Decimal("500")}
    finally:
        await _cleanup(factory)


async def test_invoices_outstanding(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    plan = await _seed_plan(factory, base_price="100", period="monthly")
    await _seed_subscription(factory, plan_id=plan.id)
    await _seed_invoice(factory, status="issued", amount_total="100")
    await _seed_invoice(factory, status="partial", amount_total="200", amount_paid="50")
    await _seed_invoice(factory, status="overdue", amount_total="300")
    await _seed_invoice(factory, status="paid", amount_total="100", amount_paid="100")
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            stats = await DashboardStatsService(s).compute()
            assert stats.invoices_outstanding == {
                "issued": 1, "partial": 1, "overdue": 1,
            }
            # 100 + (200-50) + 300 = 550 UGX outstanding
            assert stats.invoices_amount_outstanding == {"UGX": Decimal("550")}
    finally:
        await _cleanup(factory)


async def test_active_impersonations_count(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_impersonation(factory, active=True)
    await _seed_impersonation(factory, active=True)
    await _seed_impersonation(factory, active=False)
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            stats = await DashboardStatsService(s).compute()
            assert stats.active_impersonations == 2
    finally:
        await _cleanup(factory)


async def test_subscriptions_by_status(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    plan = await _seed_plan(factory, base_price="100", period="monthly")
    await _seed_subscription(factory, plan_id=plan.id, status="active")
    await _seed_subscription(factory, plan_id=plan.id, status="active")
    await _seed_subscription(factory, plan_id=plan.id, status="trialing")
    await _seed_subscription(factory, plan_id=plan.id, status="cancelled")
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            stats = await DashboardStatsService(s).compute()
            assert stats.subscriptions == {
                "active": 2, "trialing": 1, "cancelled": 1,
            }
    finally:
        await _cleanup(factory)


async def test_approvals_pending_count(test_engine: AsyncEngine) -> None:
    """Seed a pending platform approval request and confirm the count > 0."""
    from app.modules.maker_checker.models.platform import PlatformApprovalRequest
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_actor_for_followup(factory)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add_all([
            PlatformApprovalRequest(
                operation_type="billing.confirm_payment",
                payload={"payment_id": str(uuid.uuid4())},
                status="pending",
                required_approvals=1,
                requested_by=actor.id,
                requested_at=datetime.now(UTC),
            ),
            PlatformApprovalRequest(
                operation_type="billing.confirm_payment",
                payload={"payment_id": str(uuid.uuid4())},
                status="executed",
                required_approvals=1,
                requested_by=actor.id,
                requested_at=datetime.now(UTC),
            ),
        ])
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            stats = await DashboardStatsService(s).compute()
            assert stats.approvals_pending == 1
    finally:
        await _cleanup(factory)


async def test_active_impersonations_excludes_revoked(test_engine: AsyncEngine) -> None:
    """A revoked impersonation is inactive even if ended_at is NULL."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"r-{uuid.uuid4().hex[:6]}@test.example",
            full_name="R",
            role="admin",
            is_active=True, is_superuser=False,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="T", status="active", is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add_all([u, t])
        await s.flush()
        now = datetime.now(UTC)
        s.add(SupportImpersonation(
            platform_user_id=u.id, tenant_id=t.id,
            reason="r" * 10,
            started_at=now,
            expires_at=now + timedelta(minutes=30),
            ended_at=None,
            revoked_at=now,
            revoked_by=u.id,
            created_at=now, updated_at=now,
        ))
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            stats = await DashboardStatsService(s).compute()
            assert stats.active_impersonations == 0
    finally:
        await _cleanup(factory)


async def test_zero_state(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            stats = await DashboardStatsService(s).compute()
            assert stats.tenants == {}
            assert stats.subscriptions == {}
            assert stats.mrr == {}
            assert stats.invoices_outstanding == {}
            assert stats.invoices_amount_outstanding == {}
            assert stats.approvals_pending == 0
            assert stats.active_impersonations == 0
    finally:
        await _cleanup(factory)
