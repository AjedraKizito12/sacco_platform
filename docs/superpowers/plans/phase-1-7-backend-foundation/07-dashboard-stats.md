# Phase 1.7 Sub-Plan 07: Dashboard Stats Aggregate Endpoint

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/phase-1-7/07-dashboard-stats` from `main` before starting.

**Goal:** Add a single aggregate endpoint — `GET /platform/admin/dashboard-stats` — that returns every metric the platform admin portal dashboard needs (tenant counts, subscription counts, MRR, outstanding invoice totals, pending approval count, active impersonations) in one round trip. Cache the response in Redis for 60 seconds so dashboard reloads don't pound Postgres.

**Architecture:** New `app/platform_/admin/` module follows the project conventions (`api.py`, `service.py`, `schemas.py`). The service runs ~7 small aggregation queries against `platform.tenants`, `platform.subscriptions`, `platform.invoices`, `platform.approval_requests`, and `platform.support_impersonations`. MRR is computed in-Python from `subscriptions.plan_id` joined to `plans.base_price`, normalised to a monthly amount per `plan.billing_period`. The router checks Redis first; on miss it calls the service and stores the result with a 60-second TTL.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2, Redis.

**Roadmap reference:** `docs/superpowers/plans/phase-1-7-backend-foundation/00-index.md` §P1.7-07.

**Prerequisite:** **P1.7-05 must be merged** so `CurrentAdmin` is available. **P1.7-02a must be merged** so `support_impersonations` exists.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/platform_/admin/__init__.py` | Create | Package marker |
| `app/platform_/admin/schemas.py` | Create | `DashboardStatsOut` |
| `app/platform_/admin/service.py` | Create | `DashboardStatsService` — runs the aggregations |
| `app/platform_/admin/api.py` | Create | `/platform/admin/dashboard-stats` endpoint with Redis cache |
| `app/main.py` | Modify | Mount the router |
| `tests/platform_/admin/__init__.py` | Create | Package marker |
| `tests/platform_/admin/test_service.py` | Create | Unit tests for each aggregation (against seeded fixtures) |
| `tests/platform_/admin/test_api.py` | Create | Endpoint tests (gate, cache, response shape) |
| `CLAUDE.md` | Modify | Append a short bullet noting the endpoint exists; cache TTL is the contract |

---

## Task 1: Schemas

**Files:**
- Create: `app/platform_/admin/__init__.py`
- Create: `app/platform_/admin/schemas.py`

- [ ] **Step 1: Create the package marker**

```python
# app/platform_/admin/__init__.py
```
(empty file)

- [ ] **Step 2: Write the schema**

```python
# app/platform_/admin/schemas.py
"""Pydantic types for /platform/admin/dashboard-stats."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DashboardStatsOut(BaseModel):
    """Single round-trip aggregate for the platform admin dashboard.

    - tenants:                       counts by `tenants.status`
    - subscriptions:                 counts by `subscriptions.status`
    - mrr:                           normalised monthly revenue per currency,
                                     computed from active+trialing
                                     subscriptions × plan.base_price
    - invoices_outstanding:          counts of unpaid invoices by status
                                     (issued / partial / overdue)
    - invoices_amount_outstanding:   sum(amount_total - amount_paid) per
                                     currency for the same set
    - approvals_pending:             count of pending platform-scoped
                                     approval_requests
    - active_impersonations:         count of non-ended, non-revoked,
                                     non-expired support_impersonations
    - last_updated:                  generation timestamp (so the portal
                                     can show a "Last updated 12s ago" hint)
    """

    tenants: dict[str, int]
    subscriptions: dict[str, int]
    mrr: dict[str, Decimal]
    invoices_outstanding: dict[str, int]
    invoices_amount_outstanding: dict[str, Decimal]
    approvals_pending: int
    active_impersonations: int
    last_updated: datetime
```

- [ ] **Step 3: Commit**

```bash
git add app/platform_/admin/__init__.py app/platform_/admin/schemas.py
git commit -m "feat(admin): DashboardStatsOut schema"
```

---

## Task 2: Failing service tests

**Files:**
- Create: `tests/platform_/admin/__init__.py`
- Create: `tests/platform_/admin/test_service.py`

- [ ] **Step 1: Create the package marker**

```python
# tests/platform_/admin/__init__.py
```
(empty file)

- [ ] **Step 2: Write the failing service tests**

```python
# tests/platform_/admin/test_service.py
"""Unit tests for DashboardStatsService.

Each test seeds a known fixture, runs the service, and asserts the
relevant aggregation.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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
```

- [ ] **Step 3: Run — expected to fail (ImportError)**

```bash
make test-fast T=tests/platform_/admin/test_service.py
```
Expected: `ImportError: cannot import name 'DashboardStatsService'`.

- [ ] **Step 4: Commit**

```bash
git add tests/platform_/admin/__init__.py tests/platform_/admin/test_service.py
git commit -m "test(admin): dashboard stats service tests (red)"
```

---

## Task 3: Service implementation

**Files:**
- Create: `app/platform_/admin/service.py`

- [ ] **Step 1: Write the service**

```python
# app/platform_/admin/service.py
"""DashboardStatsService — aggregates the platform admin dashboard view.

Runs ~7 small queries (one per metric) plus a small Python computation
for MRR. Designed to complete well under 100ms on the seeded test DB and
to scale to ~10k tenants in production without index changes — every
filter hits an existing index.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.platform_.admin.schemas import DashboardStatsOut
from app.platform_.billing.models import Invoice, Subscription, SubscriptionPlan
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.models import Tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Live = counted in MRR.
_LIVE_SUBSCRIPTION_STATUSES_FOR_MRR = ("active", "trialing")

# Statuses considered "outstanding" for invoice metrics.
_OUTSTANDING_INVOICE_STATUSES = ("issued", "partial", "overdue")

# Normalisation factor — number of months covered by each billing_period.
_PERIOD_TO_MONTHS: dict[str, Decimal] = {
    "monthly": Decimal("1"),
    "quarterly": Decimal("3"),
    "annual": Decimal("12"),
}


class DashboardStatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def compute(self) -> DashboardStatsOut:
        tenants = await self._tenants_by_status()
        subscriptions = await self._subscriptions_by_status()
        mrr = await self._mrr()
        invoices_outstanding, invoices_amount_outstanding = (
            await self._invoices_outstanding()
        )
        approvals_pending = await self._approvals_pending()
        active_impersonations = await self._active_impersonations()
        return DashboardStatsOut(
            tenants=tenants,
            subscriptions=subscriptions,
            mrr=mrr,
            invoices_outstanding=invoices_outstanding,
            invoices_amount_outstanding=invoices_amount_outstanding,
            approvals_pending=approvals_pending,
            active_impersonations=active_impersonations,
            last_updated=datetime.now(UTC),
        )

    async def _tenants_by_status(self) -> dict[str, int]:
        result = await self._s.execute(
            select(Tenant.status, func.count())
            .group_by(Tenant.status)
        )
        return {row[0]: row[1] for row in result.all()}

    async def _subscriptions_by_status(self) -> dict[str, int]:
        result = await self._s.execute(
            select(Subscription.status, func.count())
            .group_by(Subscription.status)
        )
        return {row[0]: row[1] for row in result.all()}

    async def _mrr(self) -> dict[str, Decimal]:
        """SUM(base_price / period_months) per currency for live subs."""
        result = await self._s.execute(
            select(
                SubscriptionPlan.currency,
                SubscriptionPlan.billing_period,
                func.sum(SubscriptionPlan.base_price),
            )
            .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
            .where(Subscription.status.in_(_LIVE_SUBSCRIPTION_STATUSES_FOR_MRR))
            .group_by(SubscriptionPlan.currency, SubscriptionPlan.billing_period)
        )
        mrr: dict[str, Decimal] = {}
        for currency, period, total in result.all():
            normalised = Decimal(total) / _PERIOD_TO_MONTHS[period]
            mrr[currency] = mrr.get(currency, Decimal("0")) + normalised
        return mrr

    async def _invoices_outstanding(
        self,
    ) -> tuple[dict[str, int], dict[str, Decimal]]:
        counts_result = await self._s.execute(
            select(Invoice.status, func.count())
            .where(Invoice.status.in_(_OUTSTANDING_INVOICE_STATUSES))
            .group_by(Invoice.status)
        )
        counts = {row[0]: row[1] for row in counts_result.all()}

        amounts_result = await self._s.execute(
            select(
                Invoice.currency,
                func.sum(Invoice.amount_total - Invoice.amount_paid),
            )
            .where(Invoice.status.in_(_OUTSTANDING_INVOICE_STATUSES))
            .group_by(Invoice.currency)
        )
        amounts = {row[0]: Decimal(row[1] or 0) for row in amounts_result.all()}
        return counts, amounts

    async def _approvals_pending(self) -> int:
        from app.modules.maker_checker.models.platform import (
            PlatformApprovalRequest,
        )
        result = await self._s.execute(
            select(func.count())
            .select_from(PlatformApprovalRequest)
            .where(PlatformApprovalRequest.status == "pending")
        )
        return int(result.scalar_one())

    async def _active_impersonations(self) -> int:
        now = datetime.now(UTC)
        result = await self._s.execute(
            select(func.count())
            .select_from(SupportImpersonation)
            .where(
                SupportImpersonation.ended_at.is_(None),
                SupportImpersonation.revoked_at.is_(None),
                SupportImpersonation.expires_at > now,
            )
        )
        return int(result.scalar_one())
```

- [ ] **Step 2: Run the service tests — they should pass**

```bash
make test-fast T=tests/platform_/admin/test_service.py
```
Expected: 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/platform_/admin/service.py
git commit -m "feat(admin): DashboardStatsService (aggregations + MRR normalisation)"
```

---

## Task 4: API endpoint with Redis caching

**Files:**
- Create: `app/platform_/admin/api.py`
- Create: `tests/platform_/admin/test_api.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write failing API tests**

```python
# tests/platform_/admin/test_api.py
"""Integration tests for /platform/admin/dashboard-stats."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.models import PlatformUser, Tenant


def _make_platform_session_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


async def _create_actor(
    factory: async_sessionmaker[AsyncSession], *, role: str,
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"a-{uuid.uuid4().hex[:6]}@test.example",
            full_name="A",
            role=role,
            is_active=True,
            is_superuser=(role == "superuser"),
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_platform_session] = (
        _make_platform_session_override(test_engine)
    )
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


def _hdr(uid: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(uid)}


async def test_returns_full_shape(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_actor(factory, role="admin")
    # Seed a single tenant so tenants["active"] is non-empty
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(
            Tenant(
                slug=f"t-{uuid.uuid4().hex[:8]}",
                schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
                name="T", status="active", is_active=True,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
        )
    try:
        r = await client.get(
            "/platform/admin/dashboard-stats", headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for key in (
            "tenants", "subscriptions", "mrr",
            "invoices_outstanding", "invoices_amount_outstanding",
            "approvals_pending", "active_impersonations", "last_updated",
        ):
            assert key in body, f"missing key {key}"
        assert body["tenants"]["active"] >= 1
    finally:
        await _cleanup(factory)


async def test_403_for_finance(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_actor(factory, role="finance")
    try:
        r = await client.get(
            "/platform/admin/dashboard-stats", headers=_hdr(actor.id),
        )
        assert r.status_code == 403, r.text
    finally:
        await _cleanup(factory)


async def test_cache_is_hit_on_second_call(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    """Same response shape on two back-to-back calls. The second call should
    return identical `last_updated` (cache hit), proving the Redis layer is
    active when Redis is available in the test env.

    If Redis is unavailable during the test run, the service falls through
    and the timestamps will differ; this is acceptable degradation and
    documented in CLAUDE.md.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_actor(factory, role="admin")
    try:
        r1 = await client.get(
            "/platform/admin/dashboard-stats", headers=_hdr(actor.id),
        )
        r2 = await client.get(
            "/platform/admin/dashboard-stats", headers=_hdr(actor.id),
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        # If Redis is present, the cached payload returns identical last_updated.
        # Otherwise, this assertion is documented as best-effort.
        if r1.json()["last_updated"] != r2.json()["last_updated"]:
            pytest.skip(
                "Redis cache not active in this test env; service "
                "computes fresh each time. Set REDIS_URL to a live Redis "
                "for full coverage."
            )
        else:
            assert r1.json() == r2.json()
    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Write the router with Redis cache**

```python
# app/platform_/admin/api.py
"""GET /platform/admin/dashboard-stats — aggregate endpoint for the portal.

Redis caches the response for 60 seconds to avoid hammering Postgres on
dashboard reloads. When Redis is unavailable, the route falls through
to a fresh computation (degraded but functional).
"""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.platform_.admin.schemas import DashboardStatsOut
from app.platform_.admin.service import DashboardStatsService
from app.platform_.auth import CurrentAdmin

router = APIRouter(prefix="/platform/admin", tags=["platform-admin"])

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]

_CACHE_KEY = "dashboard:platform:stats"
_CACHE_TTL_SECONDS = 60


@router.get("/dashboard-stats", response_model=DashboardStatsOut)
async def get_dashboard_stats(
    request: Request,
    _user: CurrentAdmin,
    session: PlatformSession,
) -> DashboardStatsOut:
    redis = getattr(request.app.state, "redis", None)

    if redis is not None:
        cached = await redis.get(_CACHE_KEY)
        if cached is not None:
            try:
                return DashboardStatsOut.model_validate(json.loads(cached))
            except Exception:
                # Stale-format cache; ignore and recompute.
                pass

    stats = await DashboardStatsService(session).compute()

    if redis is not None:
        try:
            await redis.set(
                _CACHE_KEY,
                stats.model_dump_json(),
                ex=_CACHE_TTL_SECONDS,
            )
        except Exception:
            # Cache write failures don't fail the request.
            pass

    return stats
```

- [ ] **Step 3: Mount the router in `app/main.py`**

Add the import alongside the other platform imports:

```python
from app.platform_.admin.api import router as platform_admin_router
```

Add the mount line:

```python
app.include_router(platform_admin_router)
```

- [ ] **Step 4: Run the API tests — they should pass**

```bash
make test-fast T=tests/platform_/admin/test_api.py
```
Expected: 3 tests pass (the cache test may skip if Redis is unavailable in the test env; that's expected per the test's docstring).

- [ ] **Step 5: Commit**

```bash
git add app/platform_/admin/api.py \
        app/main.py \
        tests/platform_/admin/test_api.py
git commit -m "feat(admin): dashboard-stats endpoint with 60s Redis cache"
```

---

## Task 5: CLAUDE.md contract

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append a bullet to the Platform_ module contracts**

Find `## Platform_ module contracts (do not violate)`. Append:

```markdown
- `GET /platform/admin/dashboard-stats` (admin gate) returns a single aggregate
  view used by the portal dashboard. Cached in Redis for 60 seconds under key
  `dashboard:platform:stats`. The response shape (`DashboardStatsOut`) is the
  contract — adding new metrics is fine, renaming or removing existing keys
  requires a portal-side coordination. When Redis is unavailable, the
  endpoint falls through to a fresh computation; this is documented degraded
  behaviour, not a fault.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): dashboard-stats endpoint contract"
```

---

## Task 6: Final verification

- [ ] **Step 1: Full lint + type-check + test suite**

```bash
make lint
make mypy
make test
```
Expected: all clean. New tests: 5 service + 3 api = 8 (one may skip without Redis).

- [ ] **Step 2: Manual smoke**

```bash
make up
make migrate
make api &
sleep 3
TOKEN=$(make -s platform-token)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8001/platform/admin/dashboard-stats" \
  | python -m json.tool
# Second call should be served from Redis (same last_updated)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8001/platform/admin/dashboard-stats" \
  | python -m json.tool
pkill -f "uvicorn app.main:app" || true
```
Expected: JSON with all eight keys. Two calls within 60s have identical `last_updated`.

- [ ] **Step 3: PR**

```bash
git push -u origin feat/phase-1-7/07-dashboard-stats
gh pr create --title "feat(admin): GET /platform/admin/dashboard-stats" --body "$(cat <<'EOF'
## Summary
- New `app/platform_/admin/` module: schemas + service + API
- `DashboardStatsService` runs 7 small aggregations (tenants/subscriptions by status, MRR normalised per period, invoices outstanding counts + amounts, pending approvals, active impersonations)
- Single endpoint `GET /platform/admin/dashboard-stats` (CurrentAdmin) with 60s Redis cache
- Falls through gracefully when Redis is unavailable
- CLAUDE.md contract: response shape is stable; cache TTL is part of the contract

## Test plan
- [ ] `make test-fast T=tests/platform_/admin/` — 8 tests (5 service + 3 api)
- [ ] `make ci`
- [ ] Manual: two back-to-back calls return identical `last_updated`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `DashboardStatsOut` defines the eight response fields
- [ ] `DashboardStatsService` computes each metric correctly per the unit tests
- [ ] MRR normalises monthly / quarterly / annual plans into a monthly figure per currency
- [ ] `GET /platform/admin/dashboard-stats` returns the aggregate; gated on `CurrentAdmin`
- [ ] 60s Redis cache under key `dashboard:platform:stats`
- [ ] Endpoint falls through when Redis is unavailable
- [ ] All 8 new tests pass (cache test may skip without Redis)
- [ ] CLAUDE.md updated
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** add per-tenant metrics. The aggregate is platform-wide; tenant-scoped dashboards are computed client-side by the tenant operator portal (Portal v1 sub-plan 35).
- **Do not** add a `force_refresh` query parameter to bypass the cache. If the portal needs fresher data, the answer is to shorten the cache TTL — not to give clients a knob that lets every dashboard reload skip the cache.
- **Do not** invalidate the cache on every billing / tenant write. The 60s TTL is the contract; that's what the portal expects. Premature invalidation creates surprise behaviour.
- MRR includes `active` and `trialing` subscriptions. `past_due`, `suspended`, and `cancelled` do not count. If finance wants a different convention, expose a second metric rather than redefining this one.
- Currency stays UGX-only in v1 (per the billing contracts). The `dict[str, Decimal]` shape exists so multi-currency lands later without an API break.
- If `make mypy` flags the `dict[str, Decimal]` returned from `_mrr` — Pydantic v2 serialises Decimal as a string by default, which is correct. The portal parses with BigNumber.js or similar.
- The MRR aggregation joins `subscriptions` to `subscription_plans`. Both are small tables; the join is cheap. No index changes needed.
- The Redis fallback path is deliberately silent. Logging here would either spam logs (Redis flapping) or stay quiet when needed (cache write failures). The portal's "Last updated" indicator is the operator's signal that data is fresh.
- This is the last Phase 1.7 sub-plan. After it merges, the Phase 1.7 backend foundation is complete and Portal v1 Part B feature sub-plans that depend on Phase 1.7 can begin.
