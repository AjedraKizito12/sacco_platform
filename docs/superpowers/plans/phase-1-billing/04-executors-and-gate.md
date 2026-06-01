# Phase 1 Sub-Plan 04: Maker-Checker Executors + Subscription Gate

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** All commits land on `feat/phase-1-billing`.

**Goal:** Wire the billing services from SP02/SP03 into the platform's maker-checker framework, and add the subscription-state gate to `get_tenant_session`. After this sub-plan, sensitive billing operations require a second approver and the platform refuses to serve tenants whose subscription has lapsed.

**Architecture:**

- `app/platform_/billing/executors.py` registers three approval executors that run when `ApprovalService.approve()` reaches quorum:
  - `billing.confirm_payment` → `PaymentService.confirm()`
  - `billing.void_invoice` → `InvoiceService.void()`
  - `billing.cancel_subscription` → `SubscriptionService.cancel(cancel_at_period_end=False)`
- Note: `record_payment` is **not** an executor. The maker action creates `Payment(status=pending)` + `ApprovalRequest(op=billing.confirm_payment)` in one transaction (SP05 wires this in the API). The checker's approval triggers the `confirm_payment` executor. Payment **rejection** is handled at the API layer in SP05 — `ApprovalService.reject()` + `PaymentService.reject()` paired in the same transaction.
- The subscription gate lives inside `get_tenant_session` (just before yielding the session). On every tenant-scoped request, the gate runs a single JOIN query to read `tenants.subscription_status` and (if past_due) `subscriptions.grace_period_ends_at`, then either allows the request or raises 402/403. The schema_name cache in Redis is untouched — subscription state is fetched fresh per request because it changes too often to cache safely.
- Gate semantics (locked):
  - `pending` / `trialing` / `active` → allow
  - `past_due` with `grace_period_ends_at IS NULL OR grace_period_ends_at >= today` → allow
  - `past_due` with `grace_period_ends_at < today` → **402 Payment Required**
  - `suspended` → **403 Forbidden**
  - `cancelled` → **403 Forbidden**
- The gate applies to **all** tenant-scoped requests (reads + writes). It does NOT apply to `get_platform_session` — operators must still be able to manage suspended tenants.

**Tech Stack:** SQLAlchemy 2.0 async, FastAPI dependencies, structlog, pytest + httpx for HTTP testing.

**Roadmap reference:** `docs/superpowers/plans/saas-launch-roadmap.md` §5 Phase 1.

**Prerequisite:** SP01 + SP02 + SP03 merged onto `feat/phase-1-billing`.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/platform_/billing/executors.py` | Create | 3 approval executors registered via `@approval_executor` |
| `app/main.py` | Modify | Import `app.platform_.billing.executors` at startup so decorators register |
| `app/core/db.py` | Modify | Add subscription gate to `get_tenant_session` (new helper `_check_subscription_gate`) |
| `tests/platform_/billing/test_executors.py` | Create | 6 tests — each executor end-to-end + idempotency on re-execution |
| `tests/core/test_subscription_gate.py` | Create | 7 tests covering each status path through the middleware |
| `CLAUDE.md` | Modify | Append SP04 contracts to the existing Billing module section |

---

## Architectural decisions locked here

1. **The executor for confirmed payments is named `billing.confirm_payment`.** The maker flow (`record_payment` API endpoint, SP05) creates the `Payment(pending)` and the matching `ApprovalRequest(operation_type='billing.confirm_payment')` in one transaction. There is no `billing.record_payment` executor — the maker action is direct row creation, not an approval-deferred operation.
2. **Payment rejection is NOT an executor.** The `ApprovalService.reject()` method doesn't invoke executors. SP05's API will pair `ApprovalService.reject(...)` with `PaymentService.reject(...)` in the same transaction at the rejection endpoint. SP04 only defines the approve path.
3. **Executors take `(session: AsyncSession, payload: dict[str, Any])` and return `dict[str, Any]`.** Matches the existing `@approval_executor` signature in `app/modules/maker_checker/registry.py`. Payload values are JSON-roundtripped — store UUIDs as strings, convert in the executor.
4. **Executors are idempotent.** Each one checks the target row's current state first; if already in the post-execution state, return the success result without re-applying. This protects against duplicate `ApprovalService.approve()` invocations from retries.
5. **The subscription gate query is one JOIN.** `LEFT JOIN platform.subscriptions ON t.current_subscription_id = s.id`. The LEFT JOIN is necessary because pending tenants have `current_subscription_id IS NULL`. The query runs on every tenant-scoped request — it's a PK lookup, sub-millisecond.
6. **The gate's HTTP status codes are fixed contracts.** 402 for past_due-outside-grace, 403 for suspended/cancelled. Do not change these without coordinating with frontend / Phase 2 portal.
7. **The gate runs INSIDE `get_tenant_session`, not as separate FastAPI middleware.** This is deliberate — `get_tenant_session` already does the schema resolution that we'd need to repeat in middleware. Keeping it co-located avoids a second slug lookup.
8. **`get_platform_session` is NOT gated.** Operators must be able to operate on tenants in any state (suspend, reactivate, view billing history).
9. **The 5-minute Redis cache for `schema_name` is untouched.** Subscription state is fetched per-request from Postgres. A separate cache for subscription state would add invalidation complexity for ~1ms of saved latency — not worth it.
10. **No new top-level dependencies.** All work uses existing SQLAlchemy / FastAPI / Redis / structlog.

---

## Task 1: Billing executors module

**Files:**
- Create: `app/platform_/billing/executors.py`
- Create: `tests/platform_/billing/test_executors.py`

- [ ] **Step 1: Write `app/platform_/billing/executors.py`**

```python
"""Maker-checker executors for billing operations.

Import this module at app startup so the decorators register their executors
in `app.modules.maker_checker.registry.approval_registry`.

Each executor is the second leg of a maker-checker flow:
    maker action (SP05 API)  →  creates ApprovalRequest with the op_type below
    checker approval         →  ApprovalService.approve() invokes the executor

Executor signature: (session: AsyncSession, payload: dict[str, Any]) -> dict.
Payload keys are JSON-roundtripped strings; UUIDs must be parsed.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.modules.maker_checker.registry import approval_executor
from app.platform_.billing.services import (
    InvoiceService,
    PaymentService,
    SubscriptionService,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("billing.confirm_payment")  # type: ignore[misc]
async def execute_confirm_payment(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: runs when a payment-recording request reaches quorum.

    payload keys:
        payment_id: str (UUID) — the pending Payment row created by the maker
        confirmed_by: str (UUID) — the checker (this must NOT be the maker)
    """
    payment_id = uuid.UUID(payload["payment_id"])
    confirmed_by = uuid.UUID(payload["confirmed_by"])

    svc = PaymentService(session)
    # Idempotency: if the payment is already confirmed, return success.
    existing = await svc.get(payment_id)
    if existing is not None and existing.status == "confirmed":
        return {
            "payment_id": str(payment_id),
            "status": "confirmed",
            "idempotent": True,
        }

    pmt = await svc.confirm(payment_id=payment_id, confirmed_by=confirmed_by)
    return {
        "payment_id": str(pmt.id),
        "invoice_id": str(pmt.invoice_id),
        "status": pmt.status,
    }


@approval_executor("billing.void_invoice")  # type: ignore[misc]
async def execute_void_invoice(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: runs when a void-invoice request reaches quorum.

    payload keys:
        invoice_id: str (UUID)
        reason: str
    """
    invoice_id = uuid.UUID(payload["invoice_id"])
    reason = str(payload["reason"])

    svc = InvoiceService(session)
    existing = await svc.get(invoice_id)
    if existing is not None and existing.status == "void":
        return {
            "invoice_id": str(invoice_id),
            "status": "void",
            "idempotent": True,
        }

    inv = await svc.void(invoice_id=invoice_id, reason=reason)
    return {
        "invoice_id": str(inv.id),
        "invoice_number": inv.invoice_number,
        "status": inv.status,
    }


@approval_executor("billing.cancel_subscription")  # type: ignore[misc]
async def execute_cancel_subscription(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: runs when a hard-cancel subscription request reaches quorum.

    Hard cancel only (cancel_at_period_end=False). The soft path (graceful
    end-of-period cancellation) does not need maker-checker — operators can
    call SubscriptionService.cancel(cancel_at_period_end=True) directly.

    payload keys:
        subscription_id: str (UUID)
        reason: str
    """
    subscription_id = uuid.UUID(payload["subscription_id"])
    reason = str(payload["reason"])

    svc = SubscriptionService(session)
    existing = await svc.get(subscription_id)
    if existing is not None and existing.status == "cancelled":
        return {
            "subscription_id": str(subscription_id),
            "status": "cancelled",
            "idempotent": True,
        }

    sub = await svc.cancel(
        subscription_id=subscription_id,
        reason=reason,
        cancel_at_period_end=False,
    )
    return {
        "subscription_id": str(sub.id),
        "status": sub.status,
    }
```

- [ ] **Step 2: Write `tests/platform_/billing/test_executors.py`**

Use the now-standard helper pattern. Copy `_set_platform`, `_make_tenant`, `_make_plan`, `_make_platform_user`, `_cleanup`, `factory` fixture from `test_payment_service.py`.

```python
"""Tests for billing maker-checker executors.

Verifies each executor reads its payload, calls the right service, and is
idempotent on re-execution.
"""
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

from app.platform_.billing.executors import (
    execute_cancel_subscription,
    execute_confirm_payment,
    execute_void_invoice,
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


async def _setup_pending_payment(factory, plan, tenant, maker) -> uuid.UUID:
    """Create a subscription, invoice, and pending payment. Return payment_id."""
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
        invoice_id = inv.id
    async with factory() as s:
        await _set_platform(s)
        pmt = await PaymentService(s).record(
            invoice_id=invoice_id,
            amount=Decimal("50000"),
            currency="UGX",
            payment_method="bank_transfer",
            recorded_by=maker.id,
            idempotency_key=f"exec-test-{uuid.uuid4().hex[:8]}",
        )
        await s.commit()
        return pmt.id


@pytest.mark.anyio
async def test_confirm_payment_executor_marks_invoice_paid(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    maker = await _make_platform_user(factory)
    checker = await _make_platform_user(factory)
    payment_id = await _setup_pending_payment(factory, plan, tenant, maker)
    try:
        async with factory() as s:
            await _set_platform(s)
            result = await execute_confirm_payment(
                s,
                {
                    "payment_id": str(payment_id),
                    "confirmed_by": str(checker.id),
                },
            )
            await s.commit()
            assert result["status"] == "confirmed"
            assert result["payment_id"] == str(payment_id)

        async with factory() as s:
            await _set_platform(s)
            pmt = await s.get(Payment, payment_id)
            assert pmt is not None
            assert pmt.status == "confirmed"
            inv = await s.get(Invoice, pmt.invoice_id)
            assert inv is not None
            assert inv.status == "paid"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_confirm_payment_executor_is_idempotent(factory) -> None:
    """Calling the executor twice with the same payload returns success
    the second time without re-applying."""
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    maker = await _make_platform_user(factory)
    checker = await _make_platform_user(factory)
    payment_id = await _setup_pending_payment(factory, plan, tenant, maker)
    try:
        payload = {
            "payment_id": str(payment_id),
            "confirmed_by": str(checker.id),
        }
        async with factory() as s:
            await _set_platform(s)
            await execute_confirm_payment(s, payload)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            second = await execute_confirm_payment(s, payload)
            await s.commit()
            assert second["status"] == "confirmed"
            assert second.get("idempotent") is True
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_void_invoice_executor_voids_invoice(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
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
        invoice_id = inv.id
    try:
        async with factory() as s:
            await _set_platform(s)
            result = await execute_void_invoice(
                s,
                {
                    "invoice_id": str(invoice_id),
                    "reason": "duplicate issuance",
                },
            )
            await s.commit()
            assert result["status"] == "void"

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Invoice, invoice_id)
            assert refreshed is not None
            assert refreshed.status == "void"
            assert refreshed.void_reason == "duplicate issuance"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_void_invoice_executor_is_idempotent(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
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
        invoice_id = inv.id
    try:
        payload = {"invoice_id": str(invoice_id), "reason": "x"}
        async with factory() as s:
            await _set_platform(s)
            await execute_void_invoice(s, payload)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            result = await execute_void_invoice(s, payload)
            await s.commit()
            assert result["status"] == "void"
            assert result.get("idempotent") is True
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancel_subscription_executor_hard_cancels(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(
            tenant_id=tenant.id, plan_id=plan.id
        )
        await s.commit()
        sub_id = sub.id
    try:
        async with factory() as s:
            await _set_platform(s)
            result = await execute_cancel_subscription(
                s,
                {
                    "subscription_id": str(sub_id),
                    "reason": "tenant requested",
                },
            )
            await s.commit()
            assert result["status"] == "cancelled"

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Subscription, sub_id)
            assert refreshed is not None
            assert refreshed.status == "cancelled"
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "cancelled"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancel_subscription_executor_is_idempotent(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(
            tenant_id=tenant.id, plan_id=plan.id
        )
        await s.commit()
        sub_id = sub.id
    try:
        payload = {"subscription_id": str(sub_id), "reason": "x"}
        async with factory() as s:
            await _set_platform(s)
            await execute_cancel_subscription(s, payload)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            result = await execute_cancel_subscription(s, payload)
            await s.commit()
            assert result["status"] == "cancelled"
            assert result.get("idempotent") is True
    finally:
        await _cleanup(factory)
```

- [ ] **Step 3: Run tests, mypy, ruff**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_executors.py -v 2>&1 | tail -15
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/test_executors.py
```

Expected: 6 tests pass. mypy/ruff clean.

- [ ] **Step 4: Commit**

```bash
git add app/platform_/billing/executors.py tests/platform_/billing/test_executors.py
git commit -m "feat(billing): maker-checker executors — confirm_payment, void_invoice, cancel_subscription"
```

---

## Task 2: App startup registration

**Files:**
- Modify: `app/main.py`

The `@approval_executor` decorators only register their functions when the module is imported. SP01 created the empty `processors/__init__.py` and `services/__init__.py` but `executors.py` is in `app/platform_/billing/` directly. It must be explicitly imported at app boot so the registry knows about the operation_types.

- [ ] **Step 1: Read `app/main.py` to find where other executors are imported**

Look for a comment block or section that imports `app.modules.credit.executors` (the existing pattern). If the credit executors are imported via a similar line, add the billing import next to it.

If `app.modules.credit.executors` is not explicitly imported anywhere, check how it gets registered today (it might be via a model import side-effect, or via `app/main.py` startup). Match that pattern.

- [ ] **Step 2: Add the import**

Append a line in `app/main.py` (after other module imports, before app construction or in the startup hook depending on existing pattern):

```python
# Register maker-checker executors by importing the modules.
import app.platform_.billing.executors  # noqa: F401  # registers @approval_executor side-effects
```

If credit already has an equivalent line, put the billing one next to it. If not (i.e., credit relies on being imported elsewhere), make sure billing follows the same path — read the surrounding code to verify the import chain reaches `app.platform_.billing.executors`.

- [ ] **Step 3: Verify the registration happens at import time**

```bash
env -u DATABASE_URL python -c "
import app.main  # noqa
from app.modules.maker_checker.registry import approval_registry
assert 'billing.confirm_payment' in approval_registry
assert 'billing.void_invoice' in approval_registry
assert 'billing.cancel_subscription' in approval_registry
print('OK — all 3 executors registered')
"
```

Expected: `OK — all 3 executors registered`.

- [ ] **Step 4: Run full suite as a regression check**

```bash
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
env -u DATABASE_URL python -m mypy app/
ruff check app/ tests/
```

Expected: 657 tests pass (651 prior + 6 from Task 1). mypy/ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/main.py
git commit -m "feat(billing): register maker-checker executors at app startup"
```

---

## Task 3: Subscription gate middleware

**Files:**
- Modify: `app/core/db.py`

- [ ] **Step 1: Read the current `app/core/db.py`**

You're going to add a private helper `_check_subscription_gate(slug)` that runs after `_resolve_tenant_schema()` succeeds and before the session is yielded.

- [ ] **Step 2: Add the gate helper above `get_tenant_session`**

```python
from datetime import date  # add to imports at top if not present


async def _check_subscription_gate(slug: str) -> None:
    """Reject requests for tenants whose subscription has lapsed.

    Reads platform.tenants.subscription_status and (for past_due) the
    grace_period_ends_at on the current subscription, then maps to:
        pending / trialing / active → allow
        past_due within grace        → allow
        past_due past grace          → 402 Payment Required
        suspended                    → 403 Forbidden
        cancelled                    → 403 Forbidden

    Raises:
        HTTPException(402): past_due, grace_period_ends_at < today
        HTTPException(403): suspended or cancelled
    """
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT t.subscription_status, s.grace_period_ends_at "
                "FROM platform.tenants t "
                "LEFT JOIN platform.subscriptions s "
                "  ON t.current_subscription_id = s.id "
                "WHERE t.slug = :slug AND t.is_active = true"
            ),
            {"slug": slug},
        )
        row = result.fetchone()
    if row is None:
        # Defensive — should be unreachable because _resolve_tenant_schema
        # already raised 404 for missing tenants.
        return

    status: str = row[0]
    grace_end: date | None = row[1]

    if status in {"pending", "trialing", "active"}:
        return
    if status == "past_due":
        if grace_end is None or grace_end >= date.today():
            return
        raise HTTPException(
            status_code=402,
            detail=(
                "Subscription past due and grace period has expired. "
                "Please settle the outstanding invoice to restore access."
            ),
        )
    if status in {"suspended", "cancelled"}:
        raise HTTPException(
            status_code=403,
            detail=f"Subscription status is '{status}'; access denied.",
        )
    # Defensive — any unexpected status is treated as a fail-closed error.
    _log.error("subscription_gate.unknown_status", slug=slug, status=status)
    raise HTTPException(status_code=403, detail="Subscription state invalid")
```

- [ ] **Step 3: Wire the gate into `get_tenant_session`**

In `get_tenant_session`, between `schema_name = await _resolve_tenant_schema(...)` and the schema regex check, add the gate call:

```python
    redis_client: Redis = request.app.state.redis
    schema_name = await _resolve_tenant_schema(slug, redis_client)

    # Subscription gate — runs on every tenant-scoped request.
    await _check_subscription_gate(slug)

    # Defense in depth: validate the schema_name we got from our own DB.
    if not _SCHEMA_RE.match(schema_name):
        ...
```

- [ ] **Step 4: Verify the file parses + lint**

```bash
python -c "import ast; ast.parse(open('app/core/db.py').read()); print('OK')"
env -u DATABASE_URL python -m mypy app/core/db.py
ruff check app/core/db.py
```

All three clean.

- [ ] **Step 5: Commit**

```bash
git add app/core/db.py
git commit -m "feat(billing): subscription gate in get_tenant_session — 402/403 on lapsed tenants"
```

---

## Task 4: Subscription gate tests

**Files:**
- Create: `tests/core/test_subscription_gate.py`

The gate runs as part of a FastAPI dependency, so tests need to hit the dependency. The cleanest approach: instantiate `_check_subscription_gate` directly and verify each status path. (End-to-end HTTP tests through TestClient are also valuable but more involved; we'll add one of those plus 6 unit tests on the helper.)

- [ ] **Step 1: Write `tests/core/test_subscription_gate.py`**

```python
"""Subscription gate tests — verifies _check_subscription_gate maps each
subscription status to the correct HTTPException (or allow).
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.core.db import _check_subscription_gate
from app.platform_.billing.models import Subscription, SubscriptionPlan
from app.platform_.billing.services import SubscriptionService
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(factory, slug: str) -> Tenant:
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        t = Tenant(
            slug=slug,
            schema_name=f"tenant_{slug.replace('-', '_')}",
            name="Gate Test",
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


async def _cleanup(factory) -> None:
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL, "
                "subscription_status = 'pending'"
            )
        )
        await s.execute(delete(Subscription))
        await s.execute(delete(SubscriptionPlan))
        await s.execute(delete(Tenant))
        await s.execute(delete(PlatformUser))
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.commit()


@pytest.fixture
async def factory(test_engine: AsyncEngine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_gate_allows_pending_tenant(factory) -> None:
    slug = f"sg-pending-{uuid.uuid4().hex[:6]}"
    await _make_tenant(factory, slug)
    try:
        # No assertion needed — allow path returns None
        await _check_subscription_gate(slug)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_allows_active_tenant(factory) -> None:
    slug = f"sg-active-{uuid.uuid4().hex[:6]}"
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    try:
        await _check_subscription_gate(slug)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_allows_trialing_tenant(factory) -> None:
    slug = f"sg-trial-{uuid.uuid4().hex[:6]}"
    # Trialing requires a plan with trial_period_days > 0
    async with factory() as s:
        await _set_platform(s)
        plan = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Trial Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            trial_period_days=14,
        )
        s.add(plan)
        await s.commit()
        await s.refresh(plan)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    try:
        await _check_subscription_gate(slug)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_allows_past_due_within_grace(factory) -> None:
    slug = f"sg-pd-grace-{uuid.uuid4().hex[:6]}"
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).transition_to_past_due(
            subscription_id=(
                await s.execute(
                    text("SELECT id FROM platform.subscriptions LIMIT 1")
                )
            ).scalar_one()
        )
        await s.commit()
    try:
        # grace_period_ends_at defaults to today+30 — well within grace
        await _check_subscription_gate(slug)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_blocks_past_due_past_grace_with_402(factory) -> None:
    slug = f"sg-pd-exp-{uuid.uuid4().hex[:6]}"
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        sub_id = (
            await s.execute(text("SELECT id FROM platform.subscriptions LIMIT 1"))
        ).scalar_one()
        await SubscriptionService(s).transition_to_past_due(subscription_id=sub_id)
        # Force the grace period into the past
        await s.execute(
            text(
                "UPDATE platform.subscriptions SET grace_period_ends_at = :gpe "
                "WHERE id = :id"
            ),
            {"gpe": date.today() - timedelta(days=1), "id": sub_id},
        )
        await s.commit()
    try:
        with pytest.raises(HTTPException) as exc:
            await _check_subscription_gate(slug)
        assert exc.value.status_code == 402
        assert "grace" in str(exc.value.detail).lower()
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_blocks_suspended_with_403(factory) -> None:
    slug = f"sg-susp-{uuid.uuid4().hex[:6]}"
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        sub_id = (
            await s.execute(text("SELECT id FROM platform.subscriptions LIMIT 1"))
        ).scalar_one()
        svc = SubscriptionService(s)
        await svc.transition_to_past_due(subscription_id=sub_id)
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        sub_id = (
            await s.execute(text("SELECT id FROM platform.subscriptions LIMIT 1"))
        ).scalar_one()
        await SubscriptionService(s).transition_to_suspended(subscription_id=sub_id)
        await s.commit()
    try:
        with pytest.raises(HTTPException) as exc:
            await _check_subscription_gate(slug)
        assert exc.value.status_code == 403
        assert "suspended" in str(exc.value.detail).lower()
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_blocks_cancelled_with_403(factory) -> None:
    slug = f"sg-cnx-{uuid.uuid4().hex[:6]}"
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        sub_id = (
            await s.execute(text("SELECT id FROM platform.subscriptions LIMIT 1"))
        ).scalar_one()
        await SubscriptionService(s).cancel(
            subscription_id=sub_id,
            reason="test",
            cancel_at_period_end=False,
        )
        await s.commit()
    try:
        with pytest.raises(HTTPException) as exc:
            await _check_subscription_gate(slug)
        assert exc.value.status_code == 403
        assert "cancelled" in str(exc.value.detail).lower()
    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Create `tests/core/__init__.py` if it doesn't exist**

```bash
touch tests/core/__init__.py
```

- [ ] **Step 3: Run tests + full suite + lint**

```bash
env -u DATABASE_URL pytest tests/core/test_subscription_gate.py -v 2>&1 | tail -15
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
env -u DATABASE_URL python -m mypy app/ tests/
ruff check app/ tests/
```

Expected: 7 gate tests pass. Full suite ~664 (657 + 7).

- [ ] **Step 4: Commit**

```bash
git add tests/core/__init__.py tests/core/test_subscription_gate.py
git commit -m "test(billing): subscription gate — 7 tests covering each status path"
```

---

## Task 5: CLAUDE.md update + push

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Extend the existing "Billing module contracts" section**

Read the current Billing contracts section in CLAUDE.md (it has the entries from SP02 and SP03). Append these bullets at the end of that section:

```markdown
- The maker-checker executors live in `app/platform_/billing/executors.py`:
  `billing.confirm_payment`, `billing.void_invoice`, `billing.cancel_subscription`.
  These are imported at app startup via `app/main.py` so the
  `@approval_executor` decorators register on boot. Do not remove the
  startup import — the registry is empty without it.
- There is no `billing.record_payment` executor. The maker action creates
  `Payment(status=pending)` + `ApprovalRequest(operation_type='billing.confirm_payment')`
  in one transaction (SP05 API). The checker's approval triggers the
  `billing.confirm_payment` executor, which calls `PaymentService.confirm()`.
- Payment rejection is paired at the API layer (SP05): the rejection endpoint
  calls `ApprovalService.reject(...)` and `PaymentService.reject(...)` in the
  same DB transaction. There is no rejection executor — `ApprovalService.reject()`
  alone would leave the `Payment` row stuck in `pending`.
- All billing executors are idempotent. They check the target row's status
  first and return success if already in the post-execution state. This
  protects against duplicate `ApprovalService.approve()` invocations from
  retries or beat-job interactions.
- The subscription gate runs inside `get_tenant_session` (in `app/core/db.py`)
  after schema resolution. It runs a single LEFT JOIN query
  (`platform.tenants` ⋈ `platform.subscriptions`) per request — fresh from
  Postgres, not cached. Schema_name continues to use the 5-minute Redis cache.
- Gate HTTP semantics are fixed contracts:
  `pending | trialing | active` → allow.
  `past_due` within `grace_period_ends_at` → allow.
  `past_due` past grace → **402 Payment Required**.
  `suspended | cancelled` → **403 Forbidden**.
  Changing any of these requires coordination with the Phase 2 admin portal.
- The gate applies to ALL tenant-scoped requests including GETs.
  `get_platform_session` is NOT gated — operators must be able to manage
  tenants in any state.
- Hard cancellation (`SubscriptionService.cancel(cancel_at_period_end=False)`)
  is only callable from the `billing.cancel_subscription` executor.
  Direct calls from HTTP handlers are forbidden. Soft cancellation
  (`cancel_at_period_end=True`) does not require maker-checker.
```

- [ ] **Step 2: Final regression + lint**

```bash
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
ruff check app/ tests/
env -u DATABASE_URL python -m mypy app/
```

All clean.

- [ ] **Step 3: Commit and push**

```bash
git add CLAUDE.md
git commit -m "docs(claude-md): billing module contracts — executors + subscription gate (SP04)"
git push origin feat/phase-1-billing
```

---

## Self-Review Checklist

- [x] 3 executors registered via `@approval_executor`: confirm_payment, void_invoice, cancel_subscription
- [x] Each executor is idempotent (checks target status before applying)
- [x] No `billing.record_payment` executor — the maker action creates the pending row directly
- [x] No rejection executor — paired at API layer in SP05
- [x] App startup imports `app.platform_.billing.executors` so decorators register
- [x] Subscription gate runs inside `get_tenant_session`, NOT in `get_platform_session`
- [x] Gate uses a single LEFT JOIN query for tenants + subscriptions
- [x] Gate fetches fresh per-request; schema_name cache untouched
- [x] HTTP contracts: pending/trialing/active → allow; past_due within grace → allow; past_due past grace → 402; suspended/cancelled → 403
- [x] Gate applies to ALL tenant-scoped requests (reads + writes)
- [x] Tests cover each status path end-to-end
- [x] CLAUDE.md updated with SP04 contracts
- [x] No new top-level dependencies
- [x] mypy strict + ruff clean across all new code
