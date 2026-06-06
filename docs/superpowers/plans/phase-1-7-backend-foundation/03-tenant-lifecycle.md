# Phase 1.7 Sub-Plan 03: Tenant Lifecycle Endpoints

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/phase-1-7/03-tenant-lifecycle` from `main` before starting.

**Goal:** Add the four tenant-lifecycle endpoints Portal v1 needs but the existing API does not expose: edit name (immediate), suspend (maker-checker), reactivate (direct), assign-plan (delegates to billing). After this sub-plan merges, the platform admin portal can manage tenant lifecycle beyond create + retry-provisioning.

**Architecture:** Extend the existing `app/platform_/tenants/` module (`api.py`, `service.py`, `schemas.py`) in place. Add a new `executors.py` for the suspend maker-checker executor. No schema changes — the existing `platform.tenants` columns (`name`, `status`, `is_active`, `subscription_status`, `current_subscription_id`) already cover everything the new endpoints need. Optional contact fields (`contact_email`, `contact_phone`, `billing_address`) are intentionally NOT added in v1; they can ship later if the portal UX requires them.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2.

**Roadmap reference:** `docs/superpowers/plans/phase-1-7-backend-foundation/00-index.md` §P1.7-03.

**Prerequisite:** **P1.7-01 must be merged.** The suspend executor depends on the platform approvals HTTP path so a checker can approve via `POST /platform/approvals/{id}/approve`.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/platform_/tenants/schemas.py` | Modify | Add `TenantPatchIn`, `TenantSuspendIn`, `AssignPlanIn` request models |
| `app/platform_/tenants/service.py` | Modify | Add `update_name`, `suspend`, `reactivate` methods |
| `app/platform_/tenants/executors.py` | Create | `@approval_executor("tenant.suspend")` |
| `app/platform_/tenants/api.py` | Modify | Add `PATCH`, `POST /suspend`, `POST /reactivate`, `POST /assign-plan` routes |
| `app/main.py` | Modify | Import the new executors module at startup |
| `tests/platform_/tenants/test_lifecycle.py` | Create | Integration tests for the four new endpoints + suspend e2e via approvals |
| `CLAUDE.md` | Modify | Append the tenant lifecycle contract bullet to the `Platform_ module contracts` section |

---

## Task 1: Schema additions

**Files:**
- Modify: `app/platform_/tenants/schemas.py`

- [ ] **Step 1: Append three request models**

In `app/platform_/tenants/schemas.py`, append:

```python
class TenantPatchIn(BaseModel):
    """Body of PATCH /platform/tenants/{id}. Currently only name is editable."""

    name: str = Field(min_length=1, max_length=200)


class TenantSuspendIn(BaseModel):
    """Body of POST /platform/tenants/{id}/suspend."""

    reason: str = Field(min_length=10, max_length=500)


class AssignPlanIn(BaseModel):
    """Body of POST /platform/tenants/{id}/assign-plan."""

    plan_id: uuid.UUID
    start_date: datetime | None = None
```

You may also need to add the `from datetime import datetime` import at the top if it isn't already present (it is — `TenantOut` references it).

- [ ] **Step 2: Commit**

```bash
git add app/platform_/tenants/schemas.py
git commit -m "feat(tenants): TenantPatchIn / TenantSuspendIn / AssignPlanIn request models"
```

---

## Task 2: Failing endpoint tests

**Files:**
- Create: `tests/platform_/tenants/test_lifecycle.py`

- [ ] **Step 1: Write the test file**

```python
# tests/platform_/tenants/test_lifecycle.py
"""Integration tests for the new tenant lifecycle endpoints:
PATCH, POST /suspend (maker-checker), POST /reactivate, POST /assign-plan.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.platform_.tenants.executors  # noqa: F401 — register executor
from app.core.db import get_platform_session
from app.main import app, lifespan
from app.modules.maker_checker.service import ApprovalService
from app.platform_.billing.models import SubscriptionPlan
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


async def _create_superuser(
    factory: async_sessionmaker[AsyncSession], prefix: str = "u",
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"{prefix}-{uuid.uuid4().hex[:6]}@test.example",
            full_name=prefix.title(),
            is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _create_tenant(
    factory: async_sessionmaker[AsyncSession],
) -> Tenant:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Original Name",
            status="active",
            is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(t)
    return t


async def _create_plan(
    factory: async_sessionmaker[AsyncSession],
) -> SubscriptionPlan:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:6]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            is_active=True,
        )
        s.add(p)
    return p


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL, "
                "subscription_status = 'pending'"
            )
        )
        await s.execute(text("DELETE FROM platform.subscriptions"))
        await s.execute(text("DELETE FROM platform.subscription_plans"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
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


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


# ── PATCH ────────────────────────────────────────────────────────────────────


async def test_patch_updates_name(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    try:
        r = await client.patch(
            f"/platform/tenants/{tenant.id}",
            json={"name": "Renamed Tenant"},
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Renamed Tenant"
    finally:
        await _cleanup(factory)


async def test_patch_404_for_unknown_tenant(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        r = await client.patch(
            f"/platform/tenants/{uuid.uuid4()}",
            json={"name": "X"},
            headers=_hdr(actor.id),
        )
        assert r.status_code == 404
    finally:
        await _cleanup(factory)


# ── POST /suspend (maker-checker) ────────────────────────────────────────────


async def test_suspend_creates_approval_request(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_superuser(factory, "maker")
    tenant = await _create_tenant(factory)
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/suspend",
            json={"reason": "Suspected fraudulent activity reported"},
            headers=_hdr(maker.id),
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "pending_approval"
        assert "approval_request_id" in body
    finally:
        await _cleanup(factory)


async def test_suspend_end_to_end_via_approval(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    """Maker submits suspend → checker approves via /platform/approvals
    → executor flips status + is_active + subscription_status.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_superuser(factory, "maker")
    checker = await _create_superuser(factory, "checker")
    tenant = await _create_tenant(factory)
    try:
        # Submit
        sub = await client.post(
            f"/platform/tenants/{tenant.id}/suspend",
            json={"reason": "Suspected fraudulent activity reported"},
            headers=_hdr(maker.id),
        )
        approval_id = sub.json()["approval_request_id"]

        # Approve
        apr = await client.post(
            f"/platform/approvals/{approval_id}/approve",
            json={"comment": "verified"},
            headers=_hdr(checker.id),
        )
        assert apr.status_code == 200, apr.text
        assert apr.json()["status"] == "executed"

        # Verify tenant state
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.is_active is False
            assert t.status == "suspended"
            assert t.subscription_status == "suspended"
    finally:
        await _cleanup(factory)


# ── POST /reactivate ─────────────────────────────────────────────────────────


async def test_reactivate_restores_state(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    # Force-suspend
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = await s.get(Tenant, tenant.id)
        assert t is not None
        t.is_active = False
        t.status = "suspended"
        t.subscription_status = "suspended"
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/reactivate",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_active"] is True
        assert body["status"] == "active"
        # No live subscription seeded → subscription_status returns to pending
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            t2 = await s.get(Tenant, tenant.id)
            assert t2 is not None
            assert t2.subscription_status == "pending"
    finally:
        await _cleanup(factory)


async def test_reactivate_rejects_unsuspended(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)  # status='active', is_active=True
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/reactivate",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 409, r.text
    finally:
        await _cleanup(factory)


# ── POST /assign-plan ────────────────────────────────────────────────────────


async def test_assign_plan_creates_subscription(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory)
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/assign-plan",
            json={"plan_id": str(plan.id)},
            headers=_hdr(actor.id),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["tenant_id"] == str(tenant.id)
        assert body["plan_id"] == str(plan.id)
        assert body["status"] in {"active", "trialing"}
    finally:
        await _cleanup(factory)


async def test_assign_plan_rejects_duplicate(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory)
    try:
        r1 = await client.post(
            f"/platform/tenants/{tenant.id}/assign-plan",
            json={"plan_id": str(plan.id)},
            headers=_hdr(actor.id),
        )
        assert r1.status_code == 201
        r2 = await client.post(
            f"/platform/tenants/{tenant.id}/assign-plan",
            json={"plan_id": str(plan.id)},
            headers=_hdr(actor.id),
        )
        assert r2.status_code == 409, r2.text
    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Run — every test should fail with 404 (no routes yet)**

```bash
make test-fast T=tests/platform_/tenants/test_lifecycle.py
```
Expected: every endpoint test returns 405/404 because the new routes are not yet added.

- [ ] **Step 3: Commit**

```bash
git add tests/platform_/tenants/test_lifecycle.py
git commit -m "test(tenants): lifecycle endpoint tests (red)"
```

---

## Task 3: Service methods

**Files:**
- Modify: `app/platform_/tenants/service.py`

- [ ] **Step 1: Add three methods to `TenantService`**

Open `app/platform_/tenants/service.py`. After the existing `mark_retry` method, append:

```python
    async def update_name(
        self, *, tenant_id: uuid.UUID, name: str
    ) -> Tenant:
        """Edit the tenant's display name. Slug and schema are immutable."""
        tenant = await self.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found")
        tenant.name = name
        tenant.updated_at = datetime.now(UTC)
        return tenant

    async def suspend(
        self, *, tenant_id: uuid.UUID
    ) -> Tenant:
        """Flip the tenant into the suspended state.

        Called from the `tenant.suspend` maker-checker executor only. Sets:
        - is_active = false (subscription gate denies all tenant requests)
        - status = 'suspended' (lifecycle state)
        - subscription_status = 'suspended' (denormalised gate signal)

        Idempotent — if already suspended, no fields change.
        """
        tenant = await self.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found")
        if tenant.status == "suspended":
            return tenant  # idempotent
        tenant.is_active = False
        tenant.status = "suspended"
        tenant.subscription_status = "suspended"
        tenant.updated_at = datetime.now(UTC)
        return tenant

    async def reactivate(
        self, *, tenant_id: uuid.UUID
    ) -> Tenant:
        """Restore a suspended tenant.

        Sets:
        - is_active = true
        - status = 'active'
        - subscription_status: re-derived from any live subscription. If a
          live subscription exists, use its status; otherwise 'pending'.

        Raises:
            ValueError: tenant unknown, or current status is not 'suspended'.
        """
        # Lazy import to avoid a circular dep at module load time.
        from app.platform_.billing.models import Subscription

        tenant = await self.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found")
        if tenant.status != "suspended":
            raise ValueError(
                f"Tenant {tenant_id} is in status '{tenant.status}', "
                "not 'suspended' — reactivate is only valid from suspended state"
            )

        live = await self._s.scalar(
            select(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.status.in_(("trialing", "active", "past_due")),
            )
            .order_by(Subscription.started_at.desc())
            .limit(1)
        )

        tenant.is_active = True
        tenant.status = "active"
        tenant.subscription_status = live.status if live is not None else "pending"
        if live is not None:
            tenant.current_subscription_id = live.id
        tenant.updated_at = datetime.now(UTC)
        return tenant
```

- [ ] **Step 2: Commit**

```bash
git add app/platform_/tenants/service.py
git commit -m "feat(tenants): TenantService update_name / suspend / reactivate"
```

---

## Task 4: Suspend executor

**Files:**
- Create: `app/platform_/tenants/executors.py`

- [ ] **Step 1: Write the executor**

```python
# app/platform_/tenants/executors.py
"""Maker-checker executors for tenant operations.

Imported at app startup via app/main.py so the @approval_executor
decorator registers in approval_registry at boot.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.modules.maker_checker.registry import approval_executor
from app.platform_.tenants.service import TenantService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("tenant.suspend")  # type: ignore[misc]
async def execute_tenant_suspend(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: runs when a tenant.suspend approval reaches quorum.

    The maker/checker check is enforced by ApprovalService.approve()
    before this executor runs.

    payload keys:
        tenant_id: str (UUID)
        reason:    str
    """
    tenant_id = uuid.UUID(payload["tenant_id"])
    svc = TenantService(session)
    tenant = await svc.suspend(tenant_id=tenant_id)
    return {
        "tenant_id": str(tenant.id),
        "status": tenant.status,
        "is_active": tenant.is_active,
        "subscription_status": tenant.subscription_status,
    }
```

- [ ] **Step 2: Wire into main.py**

In `app/main.py`, add the import alongside the other executor imports:

```python
from app.platform_.tenants import executors as _tenants_executors  # noqa: F401
```

- [ ] **Step 3: Commit**

```bash
git add app/platform_/tenants/executors.py app/main.py
git commit -m "feat(tenants): tenant.suspend maker-checker executor"
```

---

## Task 5: API endpoints

**Files:**
- Modify: `app/platform_/tenants/api.py`

- [ ] **Step 1: Add the four new endpoints**

Open `app/platform_/tenants/api.py`. Add these imports if not already present:

```python
from app.platform_.billing.exceptions import (
    PlanInactive,
    SubscriptionConflict,
)
from app.platform_.billing.schemas import SubscriptionOut
from app.platform_.billing.services import SubscriptionService
from app.platform_.tenants.schemas import (
    AssignPlanIn,
    TenantPatchIn,
    TenantSuspendIn,
)
```

Append the four routes after the existing `retry_provisioning` handler:

```python
@router.patch("/{tenant_id}", response_model=TenantOut)
async def patch_tenant(
    tenant_id: uuid.UUID,
    body: TenantPatchIn,
    session: Session,
    actor: AnyPlatformUser,
) -> TenantOut:
    """Edit the tenant's name. Immediate, no maker-checker.

    Slug and schema_name are immutable — they're never updatable via this API.
    """
    svc = TenantService(session)
    try:
        tenant = await svc.update_name(tenant_id=tenant_id, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return TenantOut.model_validate(tenant)


@router.post("/{tenant_id}/suspend", status_code=202)
async def suspend_tenant(
    tenant_id: uuid.UUID,
    body: TenantSuspendIn,
    session: Session,
    actor: Superuser,
) -> dict[str, str]:
    """Submit a tenant-suspend approval request.

    Maker-checker required. The executor at @approval_executor("tenant.suspend")
    runs on approval and flips status + is_active + subscription_status.
    """
    from app.modules.maker_checker.service import ApprovalService

    tenant = await TenantService(session).get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status == "suspended":
        raise HTTPException(
            status_code=409,
            detail="Tenant is already suspended",
        )

    approval = await ApprovalService(session).submit(
        operation_type="tenant.suspend",
        payload={"tenant_id": str(tenant_id), "reason": body.reason},
        requested_by=actor.id,
    )
    await session.commit()
    return {
        "status": "pending_approval",
        "approval_request_id": str(approval.id),
    }


@router.post("/{tenant_id}/reactivate", response_model=TenantOut)
async def reactivate_tenant(
    tenant_id: uuid.UUID,
    session: Session,
    actor: Superuser,
) -> TenantOut:
    """Restore a suspended tenant. Direct (no maker-checker).

    Returns 409 if the tenant is not currently suspended.
    """
    svc = TenantService(session)
    try:
        tenant = await svc.reactivate(tenant_id=tenant_id)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=409, detail=msg) from exc
    await session.commit()
    return TenantOut.model_validate(tenant)


@router.post(
    "/{tenant_id}/assign-plan",
    response_model=SubscriptionOut,
    status_code=201,
)
async def assign_plan(
    tenant_id: uuid.UUID,
    body: AssignPlanIn,
    session: Session,
    actor: Superuser,
) -> SubscriptionOut:
    """Assign a billing plan to a tenant. Delegates to SubscriptionService.assign.

    Returns 409 if a live subscription already exists or the plan is inactive.
    """
    start_date = body.start_date.date() if body.start_date is not None else None
    try:
        sub = await SubscriptionService(session).assign(
            tenant_id=tenant_id,
            plan_id=body.plan_id,
            start_date=start_date,
        )
    except PlanInactive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SubscriptionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return SubscriptionOut.model_validate(sub)
```

- [ ] **Step 2: Run the failing tests — they should pass now**

```bash
make test-fast T=tests/platform_/tenants/test_lifecycle.py
```
Expected: 8 tests pass.

Also re-run the existing tenants tests to make sure nothing regressed:

```bash
make test-fast T=tests/platform_/test_tenants_api.py
```
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add app/platform_/tenants/api.py
git commit -m "feat(tenants): PATCH + suspend + reactivate + assign-plan endpoints"
```

---

## Task 6: CLAUDE.md contract

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append a bullet under `## Platform_ module contracts (do not violate)`**

Find the existing `## Platform_ module contracts (do not violate)` subsection in CLAUDE.md. Append this bullet to the end of the list:

```markdown
- Tenant lifecycle endpoints (`PATCH /platform/tenants/{id}`,
  `POST .../suspend`, `POST .../reactivate`, `POST .../assign-plan`) are the
  ONLY HTTP paths to mutate `tenants.name`, `tenants.is_active`,
  `tenants.status`, `tenants.subscription_status`, or
  `tenants.current_subscription_id`. Direct UPDATE from anywhere outside
  `TenantService` (for name/status/is_active/subscription_status) or
  `SubscriptionService` (for current_subscription_id, set automatically by
  `assign`) is forbidden. The `tenant.suspend` maker-checker executor is the
  only path that calls `TenantService.suspend()`. `reactivate` is direct —
  no maker-checker — because re-enabling a tenant is a less destructive
  operation and the operator's intent is the authorising signal. Slug and
  schema_name remain immutable.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): tenant lifecycle contract"
```

---

## Task 7: Final verification

- [ ] **Step 1: Full lint + type-check + test suite**

```bash
make lint
make mypy
make test
```
Expected: all clean.

- [ ] **Step 2: Manual smoke check**

```bash
make up
make migrate
make api &
sleep 3
TOKEN=$(make -s platform-token)
TENANT_ID=$(curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8001/platform/tenants | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

# PATCH
curl -s -X PATCH "http://127.0.0.1:8001/platform/tenants/$TENANT_ID" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Renamed Tenant"}' | python -m json.tool

# suspend
curl -s -X POST "http://127.0.0.1:8001/platform/tenants/$TENANT_ID/suspend" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"reason": "Smoke test reason long enough to pass validator"}' \
  | python -m json.tool

pkill -f "uvicorn app.main:app" || true
```
Expected: PATCH returns the updated tenant; suspend returns `{status: "pending_approval", approval_request_id: ...}`.

- [ ] **Step 3: PR**

```bash
git push -u origin feat/phase-1-7/03-tenant-lifecycle
gh pr create --title "feat(tenants): edit / suspend / reactivate / assign-plan endpoints" --body "$(cat <<'EOF'
## Summary
- `PATCH /platform/tenants/{id}` — edit name (immediate). Slug and schema immutable.
- `POST /platform/tenants/{id}/suspend` — maker-checker. Executor flips is_active, status, subscription_status.
- `POST /platform/tenants/{id}/reactivate` — direct (no maker-checker). Restores from suspended; re-derives subscription_status from live subscription.
- `POST /platform/tenants/{id}/assign-plan` — direct. Delegates to existing `SubscriptionService.assign`. Returns 409 on duplicate live subscription or inactive plan.
- New `tenant.suspend` maker-checker executor registered at app startup via `_tenants_executors` import in `app/main.py`.
- CLAUDE.md contract: these endpoints are the only paths to mutate tenant lifecycle columns.

## Out of scope
- No new schema columns. Optional contact fields (contact_email, contact_phone, billing_address) deferred — can ship later when portal UX requires them.
- No tenant deletion / archival. Lifecycle ends at suspended; archival is roadmap §Phase 7 (Tenant Offboarding & Retention).

## Test plan
- [ ] `make test-fast T=tests/platform_/tenants/test_lifecycle.py` — 8 integration tests
- [ ] `make test-fast T=tests/platform_/test_tenants_api.py` — existing tests still pass
- [ ] `make ci` (ruff + mypy + full pytest)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `TenantService` has `update_name`, `suspend`, `reactivate` methods
- [ ] `tenant.suspend` executor registered at startup
- [ ] Four new endpoints respond with the documented status codes
- [ ] `test_lifecycle.py` — all 8 tests pass
- [ ] No regression in `test_tenants_api.py`
- [ ] CLAUDE.md updated with the tenant lifecycle contract
- [ ] `make ci` clean
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** add contact_email / contact_phone / billing_address columns or any other schema change. The portal's edit screen ships with only name editable; the rest is documented as v1.1.
- **Do not** make reactivate gated by maker-checker. The contract trade-off is intentional: suspending hurts; reactivating restores.
- **Do not** auto-suspend tenants based on subscription state from here. That belongs to the existing `assess_subscription_state` Celery beat job (Phase 1 billing). The endpoints here are operator-driven.
- The `assign-plan` endpoint returns 201 with the full `SubscriptionOut`. The portal uses this to navigate immediately to the subscription detail.
- If `reactivate` is called against a tenant that was never suspended (e.g., `status='pending'` from a failed provisioning), the response is 409 with a clear message. Reactivate is not a generic "make this tenant active" — it specifically reverses suspension.
- If `make mypy` flags the `Subscription` import inside `reactivate`, that's the lazy-import pattern to avoid circular module loading. Keep it inside the method.
- The existing `retry_provisioning` route uses the maker-checker pattern with a separate executor in `app/platform_/tenants/api.py` (not in a dedicated `executors.py`). Leave that route alone — it ships from an earlier phase. The new `tenant.suspend` executor lives in the new dedicated `executors.py`, which is the pattern other modules use (e.g., `app/platform_/billing/executors.py`).
