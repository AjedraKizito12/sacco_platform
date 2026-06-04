# Phase 1.7 Sub-Plan 01: Platform Approvals API

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/phase-1-7/01-platform-approvals` from `main` before starting.

**Goal:** Expose the existing `PlatformApprovalRequest` model through a new HTTP router at `/platform/approvals/*`, mirroring the existing tenant `/approvals/*` router shape. This unlocks the billing maker-checker flow (payment confirmation, invoice voiding, hard subscription cancellation) and every other platform-scoped approvable operation already in the codebase.

**Architecture:** Single new router file at `app/modules/maker_checker/platform_api.py`. Uses `get_platform_session` (which sets `session.sync_session.info["is_platform"] = True`) and `CurrentPlatformUser`. `ApprovalService` is already schema-agnostic (`app/modules/maker_checker/service.py:31-42`); it auto-resolves `PlatformApprovalRequest`/`PlatformApprovalAction` from the session info flag. No service changes. No schema changes. No new Pydantic schemas — the existing `app/modules/maker_checker/schemas.py` (`SubmitApprovalRequest`, `ApprovalRequestOut`, `ApprovalActionRequest`, `RejectRequest`) is reused.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2.

**Roadmap reference:** `docs/superpowers/plans/phase-1-7-backend-foundation/00-index.md` §P1.7-01.

**Prerequisite:** None. `PlatformApprovalRequest`/`PlatformApprovalAction` already exist (`app/modules/maker_checker/models/platform.py:12-31`). The billing module already writes to `platform.approval_requests` via `ApprovalService.submit` from a platform session (`app/platform_/billing/api.py:447`).

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/modules/maker_checker/platform_api.py` | Create | New `/platform/approvals/*` router |
| `app/main.py` | Modify | Mount the new router |
| `app/platform_/billing/api.py` | Modify | Fix misleading docstring reference (`/maker-checker/approval-requests/...` → `/platform/approvals/...`) |
| `tests/modules/maker_checker/test_platform_api.py` | Create | Endpoint smoke + negative tests against a real Postgres |
| `tests/platform_/billing/test_payment_confirmation_e2e.py` | Create | End-to-end: maker records payment → checker approves via new endpoint → payment confirmed |
| `CLAUDE.md` | Modify | Update billing contracts subsection: the checker path is `/platform/approvals/{id}/approve` |

---

## Task 1: Failing endpoint tests

**Files:**
- Create: `tests/modules/maker_checker/test_platform_api.py`

- [ ] **Step 1: Create the test file with smoke tests for all six endpoints**

```python
# tests/modules/maker_checker/test_platform_api.py
"""Integration tests for the /platform/approvals/* router.

Mirrors tests/modules/maker_checker/test_api.py but in platform context.
Uses the test_engine session-scoped fixture from tests/conftest.py.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.modules.maker_checker.registry import approval_registry
from app.platform_.models import PlatformUser

# Register a no-op executor for the synthetic operation used by these tests.
# Other modules register their own executors via @approval_executor at import time.
approval_registry["platform.test.op"] = AsyncMock(return_value={"done": True})


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


async def _create_platform_user(
    factory: async_sessionmaker[AsyncSession],
    email_prefix: str,
    *,
    is_superuser: bool = True,
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"{email_prefix}-{uuid.uuid4().hex[:6]}@test.example",
            full_name=email_prefix.title(),
            is_active=True,
            is_superuser=is_superuser,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


async def test_submit_returns_201(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        r = await client.post(
            "/platform/approvals",
            json={
                "operation_type": "platform.test.op",
                "payload": {"hello": "world"},
                "required_approvals": 1,
            },
            headers=_hdr(maker.id),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert body["operation_type"] == "platform.test.op"
        assert body["requested_by"] == str(maker.id)
    finally:
        await _cleanup(factory)


async def test_submit_unknown_operation_returns_400(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        r = await client.post(
            "/platform/approvals",
            json={"operation_type": "no.such.op", "payload": {}},
            headers=_hdr(maker.id),
        )
        assert r.status_code == 400, r.text
    finally:
        await _cleanup(factory)


async def test_list_and_filter(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        # Two pending requests of the same op_type
        for _ in range(2):
            await client.post(
                "/platform/approvals",
                json={"operation_type": "platform.test.op", "payload": {}},
                headers=_hdr(maker.id),
            )
        r = await client.get("/platform/approvals", headers=_hdr(maker.id))
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 2
        assert all(item["operation_type"] == "platform.test.op" for item in body)

        # Filter by operation_type
        r2 = await client.get(
            "/platform/approvals?operation_type=platform.test.op",
            headers=_hdr(maker.id),
        )
        assert r2.status_code == 200
        assert len(r2.json()) == 2

        # Filter by non-matching operation_type
        r3 = await client.get(
            "/platform/approvals?operation_type=no.such.op",
            headers=_hdr(maker.id),
        )
        assert r3.status_code == 200
        assert r3.json() == []

        # Filter by requested_by
        r4 = await client.get(
            f"/platform/approvals?requested_by={maker.id}",
            headers=_hdr(maker.id),
        )
        assert r4.status_code == 200
        assert len(r4.json()) == 2
    finally:
        await _cleanup(factory)


async def test_get_detail_and_404(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        post = await client.post(
            "/platform/approvals",
            json={"operation_type": "platform.test.op", "payload": {}},
            headers=_hdr(maker.id),
        )
        rid = post.json()["id"]
        r = await client.get(f"/platform/approvals/{rid}", headers=_hdr(maker.id))
        assert r.status_code == 200
        assert r.json()["id"] == rid

        r404 = await client.get(
            f"/platform/approvals/{uuid.uuid4()}",
            headers=_hdr(maker.id),
        )
        assert r404.status_code == 404
    finally:
        await _cleanup(factory)


async def test_approve_executes_on_quorum(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    checker = await _create_platform_user(factory, "checker")
    try:
        post = await client.post(
            "/platform/approvals",
            json={
                "operation_type": "platform.test.op",
                "payload": {},
                "required_approvals": 1,
            },
            headers=_hdr(maker.id),
        )
        rid = post.json()["id"]
        r = await client.post(
            f"/platform/approvals/{rid}/approve",
            json={"comment": "looks good"},
            headers=_hdr(checker.id),
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "executed"
    finally:
        await _cleanup(factory)


async def test_self_approval_rejected(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        post = await client.post(
            "/platform/approvals",
            json={"operation_type": "platform.test.op", "payload": {}},
            headers=_hdr(maker.id),
        )
        rid = post.json()["id"]
        r = await client.post(
            f"/platform/approvals/{rid}/approve",
            json={},
            headers=_hdr(maker.id),
        )
        assert r.status_code == 400, r.text
        assert "self-approval" in r.text.lower()
    finally:
        await _cleanup(factory)


async def test_reject_and_self_reject_blocked(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    checker = await _create_platform_user(factory, "checker")
    try:
        post = await client.post(
            "/platform/approvals",
            json={"operation_type": "platform.test.op", "payload": {}},
            headers=_hdr(maker.id),
        )
        rid = post.json()["id"]
        # Maker cannot self-reject
        r_self = await client.post(
            f"/platform/approvals/{rid}/reject",
            json={"reason": "nope"},
            headers=_hdr(maker.id),
        )
        assert r_self.status_code == 400

        # Checker can reject
        r = await client.post(
            f"/platform/approvals/{rid}/reject",
            json={"reason": "duplicate request"},
            headers=_hdr(checker.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "rejected"
        assert body["rejection_reason"] == "duplicate request"
    finally:
        await _cleanup(factory)


async def test_cancel_maker_only(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    other = await _create_platform_user(factory, "other")
    try:
        post = await client.post(
            "/platform/approvals",
            json={
                "operation_type": "platform.test.op",
                "payload": {},
                "required_approvals": 2,
            },
            headers=_hdr(maker.id),
        )
        rid = post.json()["id"]

        # A different platform user cannot cancel
        r_other = await client.post(
            f"/platform/approvals/{rid}/cancel",
            json={},
            headers=_hdr(other.id),
        )
        assert r_other.status_code == 400

        # Maker can cancel
        r = await client.post(
            f"/platform/approvals/{rid}/cancel",
            json={},
            headers=_hdr(maker.id),
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"
    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Run the new tests and verify they fail with import error**

Run:
```bash
make test-fast T=tests/modules/maker_checker/test_platform_api.py
```
Expected: collection errors / `ModuleNotFoundError` (or 404 on every request) because `app/modules/maker_checker/platform_api.py` and its router are not yet mounted.

- [ ] **Step 3: Commit**

```bash
git add tests/modules/maker_checker/test_platform_api.py
git commit -m "test(maker-checker): add platform approvals API tests (red)"
```

---

## Task 2: Implement the platform router

**Files:**
- Create: `app/modules/maker_checker/platform_api.py`

- [ ] **Step 1: Write the router**

```python
# app/modules/maker_checker/platform_api.py
"""FastAPI router for /platform/approvals/* endpoints.

Mirrors the tenant router in app/modules/maker_checker/api.py but uses
get_platform_session and the PlatformApprovalRequest model.

ApprovalService (app/modules/maker_checker/service.py) is schema-agnostic
and resolves PlatformApprovalRequest / PlatformApprovalAction from
session.sync_session.info["is_platform"], which get_platform_session sets.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.modules.maker_checker.models.platform import PlatformApprovalRequest
from app.modules.maker_checker.schemas import (
    ApprovalActionRequest,
    ApprovalRequestOut,
    RejectRequest,
    SubmitApprovalRequest,
)
from app.modules.maker_checker.service import ApprovalService
from app.platform_.auth import CurrentPlatformUser

router = APIRouter(prefix="/platform/approvals", tags=["platform-maker-checker"])

Session = Annotated[AsyncSession, Depends(get_platform_session)]


@router.post("", response_model=ApprovalRequestOut, status_code=201)
async def submit_approval(
    body: SubmitApprovalRequest,
    session: Session,
    user: CurrentPlatformUser,
) -> ApprovalRequestOut:
    """Submit a new platform-scoped approval request.

    Most platform-scoped approvals are submitted by other services (billing,
    platform_users update, tenant suspend). This endpoint exists for the
    rare case of an operator-initiated approval.
    """
    svc = ApprovalService(session)
    try:
        request = await svc.submit(
            operation_type=body.operation_type,
            payload=body.payload,
            requested_by=user.id,
            required_approvals=body.required_approvals,
            expires_at=body.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApprovalRequestOut.model_validate(request)


@router.get("", response_model=list[ApprovalRequestOut])
async def list_approvals(
    session: Session,
    user: CurrentPlatformUser,
    status: str | None = Query(None),
    operation_type: str | None = Query(None),
    requested_by: uuid.UUID | None = Query(None),
) -> list[ApprovalRequestOut]:
    q = select(PlatformApprovalRequest).order_by(PlatformApprovalRequest.requested_at.desc())
    if status:
        q = q.where(PlatformApprovalRequest.status == status)
    if operation_type:
        q = q.where(PlatformApprovalRequest.operation_type == operation_type)
    if requested_by is not None:
        q = q.where(PlatformApprovalRequest.requested_by == requested_by)
    rows = (await session.execute(q)).scalars().all()
    return [ApprovalRequestOut.model_validate(r) for r in rows]


@router.get("/{request_id}", response_model=ApprovalRequestOut)
async def get_approval(
    request_id: uuid.UUID,
    session: Session,
    user: CurrentPlatformUser,
) -> ApprovalRequestOut:
    row = await session.scalar(
        select(PlatformApprovalRequest).where(PlatformApprovalRequest.id == request_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return ApprovalRequestOut.model_validate(row)


@router.post("/{request_id}/approve", response_model=ApprovalRequestOut)
async def approve(
    request_id: uuid.UUID,
    body: ApprovalActionRequest,
    session: Session,
    user: CurrentPlatformUser,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.approve(
            request_id=request_id,
            actor_user_id=user.id,
            comment=body.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApprovalRequestOut.model_validate(request)


@router.post("/{request_id}/reject", response_model=ApprovalRequestOut)
async def reject(
    request_id: uuid.UUID,
    body: RejectRequest,
    session: Session,
    user: CurrentPlatformUser,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.reject(
            request_id=request_id,
            actor_user_id=user.id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApprovalRequestOut.model_validate(request)


@router.post("/{request_id}/cancel", response_model=ApprovalRequestOut)
async def cancel(
    request_id: uuid.UUID,
    body: ApprovalActionRequest,
    session: Session,
    user: CurrentPlatformUser,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.cancel(request_id=request_id, requested_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApprovalRequestOut.model_validate(request)
```

- [ ] **Step 2: Run the tests — still failing because router isn't mounted**

Run:
```bash
make test-fast T=tests/modules/maker_checker/test_platform_api.py
```
Expected: all tests return 404 (router exists in module but not yet included in `app/main.py`).

- [ ] **Step 3: Commit**

```bash
git add app/modules/maker_checker/platform_api.py
git commit -m "feat(maker-checker): platform approvals API router (not yet mounted)"
```

---

## Task 3: Mount the router

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add the import and mount**

In `app/main.py`, add this import alongside the other router imports (alphabetised in the `from app.modules.maker_checker...` group):

```python
from app.modules.maker_checker.platform_api import router as platform_maker_checker_router
```

Add the mount line in the `app.include_router(...)` block, immediately after the existing `app.include_router(maker_checker_router)` line:

```python
app.include_router(maker_checker_router)
app.include_router(platform_maker_checker_router)
```

- [ ] **Step 2: Run the tests — they should now all pass**

Run:
```bash
make test-fast T=tests/modules/maker_checker/test_platform_api.py
```
Expected: 8 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat(maker-checker): mount /platform/approvals router"
```

---

## Task 4: End-to-end billing payment confirmation test

This validates the most important downstream consumer of P1.7-01: the billing payment maker-checker flow. A maker calls `POST /platform/billing/invoices/{id}/payments`, which creates a `Payment(pending)` and an `ApprovalRequest(operation_type='billing.confirm_payment')` in one transaction. The checker now approves via the new `/platform/approvals/{id}/approve` endpoint, the `billing.confirm_payment` executor runs, and the payment flips to `confirmed`.

**Files:**
- Create: `tests/platform_/billing/test_payment_confirmation_e2e.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/platform_/billing/test_payment_confirmation_e2e.py
"""End-to-end: maker records payment → checker approves via /platform/approvals
→ payment confirmed via billing.confirm_payment executor.

Validates that P1.7-01 (platform approvals API) correctly unblocks the
existing billing maker-checker flow. The executor is registered at import
time in app/platform_/billing/executors.py — imported by app/main.py.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.billing.models import Invoice, Payment, SubscriptionPlan
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


async def _seed_billing_invoice(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[PlatformUser, PlatformUser, uuid.UUID]:
    """Create maker, checker, tenant, plan, subscription, and invoice.

    Returns (maker, checker, invoice_id).
    """
    from app.platform_.billing.services import InvoiceService, SubscriptionService

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        maker = PlatformUser(
            email=f"maker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Maker",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        checker = PlatformUser(
            email=f"checker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Checker",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        tenant = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="E2E Pmt Test",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        plan = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:6]}",
            name="E2E Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            is_active=True,
        )
        s.add_all([maker, checker, tenant, plan])

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        sub_id = sub.id

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        invoice = await InvoiceService(s).generate_for_subscription(subscription_id=sub_id)
        invoice_id = invoice.id

    return maker, checker, invoice_id


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL, "
                "subscription_status = 'pending'"
            )
        )
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
        await s.execute(text("DELETE FROM platform.outbox_events"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


async def test_payment_confirmation_e2e(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, invoice_id = await _seed_billing_invoice(factory)
    try:
        # 1. Maker records a payment — creates Payment(pending) + ApprovalRequest.
        rec = await client.post(
            f"/platform/billing/invoices/{invoice_id}/payments",
            headers={"X-Platform-Actor-ID": str(maker.id)},
            json={
                "amount": "50000.0000",
                "currency": "UGX",
                "payment_method": "bank_transfer",
                "external_reference": "MTN-REF-12345",
                "idempotency_key": f"k-{uuid.uuid4().hex}",
            },
        )
        assert rec.status_code == 200, rec.text
        body = rec.json()
        assert body["status"] == "pending_approval"
        approval_id = body["approval_request_id"]
        payment_id = body["payment_id"]

        # 2. Checker approves via the new /platform/approvals/{id}/approve endpoint.
        appr = await client.post(
            f"/platform/approvals/{approval_id}/approve",
            headers={"X-Platform-Actor-ID": str(checker.id)},
            json={"comment": "verified receipt"},
        )
        assert appr.status_code == 200, appr.text
        assert appr.json()["status"] == "executed"

        # 3. Verify Payment.status == 'confirmed' via the DB.
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            pmt = await s.get(Payment, uuid.UUID(payment_id))
            assert pmt is not None
            assert pmt.status == "confirmed"
            assert pmt.confirmed_at is not None

        # 4. Verify Invoice.amount_paid is updated.
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            assert inv.amount_paid == Decimal("50000.0000")
            assert inv.status == "paid"
    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Run the integration test**

Run:
```bash
make test-fast T=tests/platform_/billing/test_payment_confirmation_e2e.py
```
Expected: PASS. If `billing.confirm_payment` executor isn't registered, the approve call would return 400 — the failure mode would point at `app/main.py` not importing `app.platform_.billing.executors`. (It does — line 33 — so this should pass.)

- [ ] **Step 3: Commit**

```bash
git add tests/platform_/billing/test_payment_confirmation_e2e.py
git commit -m "test(billing): end-to-end payment confirmation via platform approvals API"
```

---

## Task 5: Update the misleading docstring in billing api.py

**Files:**
- Modify: `app/platform_/billing/api.py`

- [ ] **Step 1: Fix the docstring**

Open `app/platform_/billing/api.py`. Find the docstring on `record_payment` (around line 411–416):

```python
async def record_payment(
    invoice_id: uuid.UUID,
    payload: PaymentRecordIn,
    user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> dict[str, str]:
    """Maker action: create Payment(pending) + ApprovalRequest in one tx.

    The checker approves via `/maker-checker/approval-requests/{id}/approve`
    (which triggers the `billing.confirm_payment` executor) OR rejects via
    `/platform/billing/payments/{id}/reject`.
    """
```

Replace with:

```python
async def record_payment(
    invoice_id: uuid.UUID,
    payload: PaymentRecordIn,
    user: Annotated[PlatformUser, Depends(get_current_platform_user)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> dict[str, str]:
    """Maker action: create Payment(pending) + ApprovalRequest in one tx.

    The checker approves via `POST /platform/approvals/{id}/approve`
    (which triggers the `billing.confirm_payment` executor) OR rejects via
    `POST /platform/billing/payments/{id}/reject`.
    """
```

- [ ] **Step 2: Run the billing api tests to confirm no breakage**

Run:
```bash
make test-fast T=tests/platform_/billing/
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add app/platform_/billing/api.py
git commit -m "docs(billing): correct approve-path reference in record_payment docstring"
```

---

## Task 6: Update CLAUDE.md billing contracts

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate the relevant contract bullet**

In `CLAUDE.md`, under `## Billing module contracts (do not violate)`, find this bullet:

```markdown
- The maker-checker executors live in `app/platform_/billing/executors.py`:
  `billing.confirm_payment`, `billing.void_invoice`, `billing.cancel_subscription`.
  These are imported at app startup via `app/main.py` so the
  `@approval_executor` decorators register on boot. Do not remove the
  startup import — the registry is empty without it.
```

- [ ] **Step 2: Append a new bullet immediately after, describing the platform approvals API**

Append this bullet immediately after the one above:

```markdown
- Platform-scoped approval requests (created by `billing.*`, `platform_user.update_sensitive`,
  `tenant.retry_provisioning`, and future platform-scoped operations) are approved,
  rejected, listed, and cancelled via the `/platform/approvals/*` router in
  `app/modules/maker_checker/platform_api.py`. The tenant-scoped `/approvals/*`
  router in `app/modules/maker_checker/api.py` handles tenant-scoped requests
  only and does NOT see platform.approval_requests rows. `ApprovalService` is
  schema-agnostic — it picks the right model based on
  `session.sync_session.info["is_platform"]`, set by `get_platform_session`.
  Both routers reuse the same `SubmitApprovalRequest` / `ApprovalRequestOut` /
  `ApprovalActionRequest` / `RejectRequest` Pydantic schemas.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): contract for /platform/approvals/* router"
```

---

## Task 7: Final verification

- [ ] **Step 1: Lint, type-check, and run the full suite**

Run each in turn:
```bash
make lint
make mypy
make test
```
Expected: all pass. Specifically the new test files (`tests/modules/maker_checker/test_platform_api.py` and `tests/platform_/billing/test_payment_confirmation_e2e.py`) appear in the pass count and no existing tests regress.

- [ ] **Step 2: Manual smoke check (optional but recommended)**

```bash
make up
make migrate
make api &
sleep 3
make platform-token > /tmp/token.txt
TOKEN=$(cat /tmp/token.txt)
# List should return [] initially:
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8001/platform/approvals
```
Expected: `[]` (empty list, 200 OK).

Kill the API server when done:
```bash
pkill -f "uvicorn app.main:app" || true
```

- [ ] **Step 3: PR**

```bash
git push -u origin feat/phase-1-7/01-platform-approvals
gh pr create --title "feat(maker-checker): platform approvals API" --body "$(cat <<'EOF'
## Summary
- Adds `/platform/approvals/*` router (submit, list, get, approve, reject, cancel) operating against `PlatformApprovalRequest`.
- Unlocks the existing billing maker-checker flow (`billing.confirm_payment`, `billing.void_invoice`, `billing.cancel_subscription`), platform user sensitive updates, and tenant retry-provisioning — all of which previously had no HTTP path to approve.
- Reuses the schema-agnostic `ApprovalService`. Zero schema changes. Zero new Pydantic schemas.
- Fixes a stale docstring in `app/platform_/billing/api.py` that referenced the non-existent `/maker-checker/approval-requests/...` path.
- Adds a CLAUDE.md contract distinguishing platform vs tenant approval routers.

## Test plan
- [ ] `make test-fast T=tests/modules/maker_checker/test_platform_api.py` — 8 endpoint tests
- [ ] `make test-fast T=tests/platform_/billing/test_payment_confirmation_e2e.py` — end-to-end billing flow
- [ ] `make ci` (ruff + mypy + full pytest)
- [ ] Manual: list endpoint returns `[]` against a fresh DB

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opens cleanly, CI green.

---

## Acceptance criteria (sub-plan exits here)

- [ ] All 8 endpoint tests in `tests/modules/maker_checker/test_platform_api.py` pass
- [ ] `tests/platform_/billing/test_payment_confirmation_e2e.py` passes (proves billing maker-checker flow is now operable end-to-end via HTTP)
- [ ] `make lint`, `make mypy`, `make test` all clean
- [ ] `app/platform_/billing/api.py` docstring updated
- [ ] CLAUDE.md billing contracts subsection updated with the new bullet
- [ ] PR opened, CI green, ready for review

## Notes for the executing subagent

- **Do not** modify `ApprovalService` in `app/modules/maker_checker/service.py`. It's already schema-agnostic and is consumed by both routers.
- **Do not** add new Pydantic schemas. The existing ones in `app/modules/maker_checker/schemas.py` are intentionally reused.
- **Do not** introduce a `requested_by` filter on the tenant router — that's out of scope here. Only the new platform router gets the filter (the tenant API can be aligned in a follow-up).
- **Do not** add audit log writes from the router — `ApprovalService` already writes audit on submit/approve/reject. Double-writing would inflate the audit log.
- If `make test` reveals an unrelated regression elsewhere, stop and surface to the user — do not "fix" it as part of this sub-plan.
- If you discover that `billing.confirm_payment` executor is NOT registered at import time (Task 4 test fails with 400 "no executor"), the diagnosis is `app/main.py:33` no longer importing `app.platform_.billing.executors as _billing_executors`. Stop and surface — that's a separate regression, not in scope here.
