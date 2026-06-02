# Phase 1 Sub-Plan 05: API Endpoints + Invoice PDF

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** All commits land on `feat/phase-1-billing`.

**Goal:** Expose the billing module via HTTP — platform-admin CRUD for plans / subscriptions / invoices, maker-checker submission for sensitive ops, payment rejection endpoint, invoice PDF rendering on-demand, and read-only tenant-facing endpoints under `/billing/me/*`.

**Architecture:**

- All endpoints live in `app/platform_/billing/api.py` exposing two routers:
  - `platform_router` mounted at `/platform/billing` — requires `CurrentPlatformUser`, uses `get_platform_session`
  - `tenant_router` mounted at `/billing/me` — requires `CurrentTenantUser`, uses `get_platform_session` (read-only billing data lives in platform schema; tenant-scoping is by `tenant_id == CurrentTenantUser.tenant_id`)
- Maker-checker integration follows the SP04 contract: the API layer creates the `ApprovalRequest` via `ApprovalService.submit()`, and the registered executor runs on approval. The payment-recording endpoint creates `Payment(pending)` + `ApprovalRequest` in one transaction.
- Payment rejection has its own endpoint (`POST /payments/{id}/reject`) that pairs `ApprovalService.reject()` + `PaymentService.reject()` in the same transaction. No executor for the reject path.
- Invoice PDF rendering is **on-demand**: every GET `/invoices/{id}.pdf` re-renders from the Jinja2 template + invoice ORM. No storage. `Invoice.pdf_storage_key` stays NULL in v1.
- Plan management uses a thin `PlanService` (new), which lives at `app/platform_/billing/services/plan_service.py` alongside the existing services.
- `PaymentService.confirm()` gets a minor refactor: `confirmed_by: UUID | None = None`. When None, the maker/checker check is skipped because `ApprovalService.approve()` has already done it. Direct callers (tests, future direct-API paths) keep passing a real UUID.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.0 async, Jinja2, WeasyPrint, structlog. mypy strict + ruff non-negotiable.

**Roadmap reference:** `docs/superpowers/plans/saas-launch-roadmap.md` §5 Phase 1.

**Prerequisite:** SP01 + SP02 + SP03 + SP04 merged onto `feat/phase-1-billing`.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/platform_/billing/services/payment_service.py` | Modify | `confirmed_by: UUID \| None = None` — optional, skip check when None |
| `app/platform_/billing/executors.py` | Modify | Pass `confirmed_by=None` from executor (relies on ApprovalService for maker/checker enforcement) |
| `app/platform_/billing/services/plan_service.py` | Create | Plan CRUD methods |
| `app/platform_/billing/services/__init__.py` | Modify | Re-export `PlanService` |
| `app/platform_/billing/api.py` | Create | Both routers (platform + tenant), all endpoints |
| `app/platform_/billing/templates/invoice.html` | Create | Jinja2 template for invoice PDF |
| `app/platform_/billing/pdf.py` | Create | `render_invoice_pdf(invoice, line_items) -> bytes` |
| `app/main.py` | Modify | Mount the two new routers |
| `tests/platform_/billing/test_api_plans.py` | Create | Plan CRUD endpoint tests (~6) |
| `tests/platform_/billing/test_api_subscriptions.py` | Create | Subscription endpoint tests (~6) |
| `tests/platform_/billing/test_api_invoices.py` | Create | Invoice + tenant-me endpoint tests (~8) |
| `tests/platform_/billing/test_api_payments.py` | Create | Payment record + reject flow tests (~6) |
| `tests/platform_/billing/test_api_void_cancel.py` | Create | Void + hard-cancel maker-checker flow (~4) |
| `tests/platform_/billing/test_pdf.py` | Create | PDF render smoke test (~2) |
| `CLAUDE.md` | Modify | Final billing contracts (API + PDF) |

---

## Architectural decisions locked here

1. **Single `api.py` file with two router instances.** `platform_router` and `tenant_router`. Both imported and mounted from `app/main.py` at their respective prefixes. Keeps related handlers together.
2. **Tenant-me endpoints use `get_platform_session`.** Billing data lives in `platform.*` tables. The endpoint handler filters by `tenant_id == current_tenant_user.tenant_id`. No cross-schema query.
3. **`PaymentService.confirm(confirmed_by: UUID | None = None)`.** Optional. None skips the maker/checker enforcement check. This is the path the executor uses. Direct callers (tests, future scripts) still pass real UUIDs. SP04 tests still pass because they call with explicit UUIDs.
4. **Plan operations are NOT maker-checker.** Operators can create/edit plans directly. Audit-log records the changes (via `AuditableMixin` on the model). Plan changes don't move money.
5. **Subscription `reactivate` is direct.** Suspended → active is a forward state change. No maker-checker required.
6. **Subscription `assign` is direct.** Platform admins can directly assign plans to tenants. No maker-checker (operator-only, audited).
7. **Subscription `cancel` API has two modes via query param:**
   - `?mode=at_period_end` (default) → direct call to `SubscriptionService.cancel(cancel_at_period_end=True)`. No maker-checker (soft cancel — reversible until period end).
   - `?mode=immediate` → goes through `billing.cancel_subscription` executor. Hard cancel. Requires maker-checker.
8. **Void invoice always requires maker-checker.** No "direct void" path. Void is destructive to data quality even if reversible.
9. **Record payment always requires maker-checker.** Creates `Payment(pending)` + `ApprovalRequest` in one transaction.
10. **Payment rejection has its own billing endpoint, NOT the generic /approval-requests/{id}/reject.** The billing endpoint pairs both rejections atomically.
11. **PDF is rendered on-demand, no storage.** WeasyPrint renders the template, returns bytes. `Invoice.pdf_storage_key` stays NULL.
12. **The PDF template is server-side only.** No JavaScript, no external CSS fetches. WeasyPrint sandboxed.
13. **Tenant invoice access enforces ownership in the handler.** Every `/billing/me/invoices/{id}` query filters by `tenant_id`. Cross-tenant access returns 404 (not 403 — don't leak existence).
14. **Currency: UGX-only.** The schemas enforce this; multi-currency support is post-launch.
15. **PDF requests use `application/pdf` Content-Type.** Filename via `Content-Disposition: inline; filename="INV-2026-000001.pdf"`.

---

## Task 1: PaymentService.confirm + executor refactor

**Files:**
- Modify: `app/platform_/billing/services/payment_service.py`
- Modify: `app/platform_/billing/executors.py`
- Modify: `tests/platform_/billing/test_executors.py` (call the executor without `confirmed_by` in payload to verify the new path)

- [ ] **Step 1: Read `app/platform_/billing/services/payment_service.py`**

Find the `confirm` method.

- [ ] **Step 2: Change the signature to make `confirmed_by` optional**

Replace the function signature and the maker/checker check:

```python
    async def confirm(
        self,
        *,
        payment_id: uuid.UUID,
        confirmed_by: uuid.UUID | None = None,
    ) -> Payment:
        """Confirm a pending payment. Applies amount to the parent invoice.

        Args:
            payment_id: target payment.
            confirmed_by: the checker's user_id. When None, the maker/checker
                check is skipped — this is the path used by the
                `billing.confirm_payment` approval executor, since
                `ApprovalService.approve()` has already enforced maker != checker.

        Transitions:
            payment.status: pending → confirmed
            invoice.amount_paid: += payment.amount
            invoice.status:
                amount_paid == amount_total → 'paid' (paid_at set)
                0 < amount_paid < amount_total → 'partial'
                else → unchanged

        Raises:
            ValueError: payment not found.
            PaymentConflict: payment not pending, or self-approval attempt
                            (only when confirmed_by is provided).
            OverpaymentRejected: confirmation would push amount_paid past total.
        """
        pmt = await self.get(payment_id)
        if pmt is None:
            raise ValueError(f"Payment {payment_id} not found")
        if pmt.status != "pending":
            raise PaymentConflict(
                f"Cannot confirm payment in status {pmt.status!r}"
            )
        if confirmed_by is not None and pmt.recorded_by == confirmed_by:
            raise PaymentConflict(
                "Maker cannot be checker (payment.recorded_by == confirmed_by)"
            )
        # ... rest of method unchanged
```

Keep the rest of `confirm` unchanged.

- [ ] **Step 3: Update `app/platform_/billing/executors.py`**

In `execute_confirm_payment`, remove the `confirmed_by` payload parse and call `confirm` with `confirmed_by=None`:

```python
@approval_executor("billing.confirm_payment")  # type: ignore[misc]
async def execute_confirm_payment(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: runs when a payment-recording request reaches quorum.

    The maker/checker check is enforced by ApprovalService.approve()
    before this executor runs, so we don't need to re-check here.

    payload keys:
        payment_id: str (UUID) — the pending Payment row created by the maker
    """
    payment_id = uuid.UUID(payload["payment_id"])

    svc = PaymentService(session)
    existing = await svc.get(payment_id)
    if existing is not None and existing.status == "confirmed":
        return {
            "payment_id": str(payment_id),
            "status": "confirmed",
            "idempotent": True,
        }

    pmt = await svc.confirm(payment_id=payment_id, confirmed_by=None)
    return {
        "payment_id": str(pmt.id),
        "invoice_id": str(pmt.invoice_id),
        "status": pmt.status,
    }
```

- [ ] **Step 4: Update SP04 executor tests to match**

In `tests/platform_/billing/test_executors.py`, update `test_confirm_payment_executor_marks_invoice_paid` and `test_confirm_payment_executor_is_idempotent` to NOT pass `confirmed_by` in the payload (since the executor no longer reads it).

```python
async def test_confirm_payment_executor_marks_invoice_paid(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    maker = await _make_platform_user(factory)
    # Note: checker no longer needed for executor — direct call
    payment_id = await _setup_pending_payment(factory, plan, tenant, maker)
    try:
        async with factory() as s:
            await _set_platform(s)
            result = await execute_confirm_payment(
                s,
                {"payment_id": str(payment_id)},  # no confirmed_by
            )
            await s.commit()
            assert result["status"] == "confirmed"
        # ... rest unchanged
```

And similarly the idempotency test.

- [ ] **Step 5: Update existing PaymentService tests** in `tests/platform_/billing/test_payment_service.py`

The existing test `test_confirm_full_payment_marks_invoice_paid` passes `confirmed_by=checker.id` — that still works (real UUID, check still runs). No changes needed UNLESS the type annotations break mypy. Verify by running mypy.

Also keep `test_confirm_rejects_self_approval` exactly as-is — it tests the path where `confirmed_by` IS provided.

Add ONE new test that verifies the None bypass works:

```python
@pytest.mark.anyio
async def test_confirm_with_none_confirmed_by_skips_maker_check(factory) -> None:
    """When confirmed_by=None (executor path), maker/checker check is skipped."""
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    maker = await _make_platform_user(factory)
    invoice_id = await _make_invoice(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            pmt = await svc.record(
                invoice_id=invoice_id,
                amount=Decimal("50000"),
                currency="UGX",
                payment_method="cash",
                recorded_by=maker.id,
                idempotency_key="key-confirm-bypass-001",
            )
            await s.commit()
            pmt_id = pmt.id

        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            # Same maker would normally trigger PaymentConflict; None skips it
            confirmed = await svc.confirm(payment_id=pmt_id, confirmed_by=None)
            await s.commit()
            assert confirmed.status == "confirmed"
    finally:
        await _cleanup(factory)
```

- [ ] **Step 6: Run tests + mypy + ruff**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_payment_service.py tests/platform_/billing/test_executors.py -v 2>&1 | tail -20
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/
```

Expected: all existing payment + executor tests still pass, plus 1 new test = ~16 in those two files.

- [ ] **Step 7: Commit**

```bash
git add app/platform_/billing/services/payment_service.py \
        app/platform_/billing/executors.py \
        tests/platform_/billing/test_executors.py \
        tests/platform_/billing/test_payment_service.py
git commit -m "refactor(billing): PaymentService.confirm — confirmed_by optional, executor uses None path"
```

---

## Task 2: PlanService + Plan CRUD endpoints

**Files:**
- Create: `app/platform_/billing/services/plan_service.py`
- Modify: `app/platform_/billing/services/__init__.py`
- Create: `app/platform_/billing/api.py` (initial — plan endpoints only; subscription/invoice/etc added in later tasks)
- Modify: `app/main.py` (mount the platform router)
- Create: `tests/platform_/billing/test_api_plans.py`

- [ ] **Step 1: Write `app/platform_/billing/services/plan_service.py`**

```python
"""PlanService — CRUD for subscription_plans.

No state machine, no maker-checker. Plans are operator-managed.
Audit log captures changes via AuditableMixin on SubscriptionPlan.
"""
from __future__ import annotations

import uuid
from typing import Any, cast

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.billing.exceptions import BillingError
from app.platform_.billing.models import SubscriptionPlan

_log = structlog.get_logger(__name__)


class PlanCodeConflict(BillingError):
    """Raised when create() is called with a code that already exists."""


class PlanService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, plan_id: uuid.UUID) -> SubscriptionPlan | None:
        return cast(
            SubscriptionPlan | None,
            await self._s.scalar(
                select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
            ),
        )

    async def get_by_code(self, code: str) -> SubscriptionPlan | None:
        return cast(
            SubscriptionPlan | None,
            await self._s.scalar(
                select(SubscriptionPlan).where(SubscriptionPlan.code == code)
            ),
        )

    async def list_plans(self, *, only_active: bool = False) -> list[SubscriptionPlan]:
        q = select(SubscriptionPlan).order_by(SubscriptionPlan.code)
        if only_active:
            q = q.where(SubscriptionPlan.is_active.is_(True))
        result = await self._s.execute(q)
        return list(result.scalars().all())

    async def create(self, **fields: Any) -> SubscriptionPlan:
        """Create a plan.

        Raises:
            PlanCodeConflict: plan with same `code` already exists.
        """
        plan = SubscriptionPlan(**fields)
        self._s.add(plan)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            await self._s.rollback()
            raise PlanCodeConflict(
                f"Plan code {fields.get('code')!r} already in use"
            ) from exc
        _log.info("plan.created", plan_id=str(plan.id), code=plan.code)
        return plan

    async def update(
        self, *, plan_id: uuid.UUID, **changes: Any
    ) -> SubscriptionPlan:
        """Patch fields on a plan. Returns the updated plan.

        Raises:
            ValueError: plan not found.
            PlanCodeConflict: trying to change `code` to one that already exists.
        """
        plan = await self.get(plan_id)
        if plan is None:
            raise ValueError(f"Plan {plan_id} not found")
        for key, value in changes.items():
            if value is None:
                continue
            setattr(plan, key, value)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            await self._s.rollback()
            raise PlanCodeConflict(
                f"Cannot rename to code {changes.get('code')!r} — already in use"
            ) from exc
        _log.info("plan.updated", plan_id=str(plan.id), changed=list(changes.keys()))
        return plan
```

- [ ] **Step 2: Update `app/platform_/billing/services/__init__.py`**

```python
from app.platform_.billing.services.invoice_service import InvoiceService
from app.platform_.billing.services.payment_service import PaymentService
from app.platform_.billing.services.plan_service import PlanCodeConflict, PlanService
from app.platform_.billing.services.subscription_service import SubscriptionService

__all__ = [
    "InvoiceService",
    "PaymentService",
    "PlanCodeConflict",
    "PlanService",
    "SubscriptionService",
]
```

- [ ] **Step 3: Create `app/platform_/billing/api.py` (initial — plan endpoints only)**

```python
"""HTTP API for the billing module.

platform_router (mounted at /platform/billing): admin-only CRUD + maker-checker
tenant_router   (mounted at /billing/me):       read-only tenant-facing views

All endpoints log structured events; audit goes through ORM mixins where
applicable, and through ApprovalService for maker-checker operations.
"""
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.platform_.auth import CurrentPlatformUser
from app.platform_.billing.exceptions import PlanCodeConflict
from app.platform_.billing.schemas import (
    SubscriptionPlanIn,
    SubscriptionPlanOut,
    SubscriptionPlanPatch,
)
from app.platform_.billing.services import PlanService

_log = structlog.get_logger(__name__)

platform_router = APIRouter(prefix="/platform/billing", tags=["billing-platform"])
tenant_router = APIRouter(prefix="/billing/me", tags=["billing-tenant"])

# ── Plans ─────────────────────────────────────────────────────────────────────


@platform_router.get(
    "/plans",
    response_model=list[SubscriptionPlanOut],
)
async def list_plans(
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    only_active: bool = False,
) -> list[SubscriptionPlanOut]:
    plans = await PlanService(session).list_plans(only_active=only_active)
    return [SubscriptionPlanOut.model_validate(p) for p in plans]


@platform_router.post(
    "/plans",
    response_model=SubscriptionPlanOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    payload: SubscriptionPlanIn,
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionPlanOut:
    try:
        plan = await PlanService(session).create(**payload.model_dump())
    except PlanCodeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SubscriptionPlanOut.model_validate(plan)


@platform_router.get(
    "/plans/{plan_id}",
    response_model=SubscriptionPlanOut,
)
async def get_plan(
    plan_id: uuid.UUID,
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionPlanOut:
    plan = await PlanService(session).get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return SubscriptionPlanOut.model_validate(plan)


@platform_router.patch(
    "/plans/{plan_id}",
    response_model=SubscriptionPlanOut,
)
async def update_plan(
    plan_id: uuid.UUID,
    payload: SubscriptionPlanPatch,
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionPlanOut:
    try:
        plan = await PlanService(session).update(
            plan_id=plan_id,
            **payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanCodeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SubscriptionPlanOut.model_validate(plan)
```

Note about `PlanCodeConflict` import: it's exported from `app.platform_.billing.services` (the public re-export). Either import from services or from exceptions — pick services for the API layer to depend only on the public service surface. Update if `PlanCodeConflict` is defined in `plan_service.py` and re-exported.

If the imports don't work cleanly, prefer importing `PlanCodeConflict` from `app.platform_.billing.services` (the re-export).

- [ ] **Step 4: Mount the platform router in `app/main.py`**

Read the file. Find where other routers are registered (look for `app.include_router(...)`). Add:

```python
from app.platform_.billing.api import platform_router as billing_platform_router  # near the other router imports
# ...
app.include_router(billing_platform_router)
```

Don't add the tenant router yet — that comes in Task 5.

- [ ] **Step 5: Create `tests/platform_/billing/test_api_plans.py`**

Use the existing test pattern. The `factory` fixture isn't enough here — you need a FastAPI test client. Look at `tests/platform_/test_tenants.py` (or similar) to find the existing client fixture pattern.

If a `client` fixture already exists in `tests/conftest.py` or a shared location, use it. Otherwise create one in this test file using:

```python
from httpx import ASGITransport, AsyncClient

@pytest.fixture
async def client(test_engine):
    # Use existing app from app.main, patch the DB to point at test_engine
    from app.main import app
    import app.core.db as _db_module
    _db_module.engine = test_engine
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

Auth: most existing tests use a `stub` mode that bypasses real JWT. Check `tests/conftest.py` for the auth shortcut. If `PLATFORM_AUTH_MODE=stub` works, set the `X-Platform-Actor-ID` header on requests.

Tests (6):

```python
@pytest.mark.anyio
async def test_create_plan(client, platform_actor_header):
    r = await client.post(
        "/platform/billing/plans",
        headers=platform_actor_header,
        json={
            "code": "starter-test",
            "name": "Starter Test",
            "base_price": "50000.0000",
            "billing_period": "monthly",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["code"] == "starter-test"
    assert body["base_price"] == "50000.0000"


@pytest.mark.anyio
async def test_create_plan_rejects_duplicate_code(client, platform_actor_header):
    payload = {
        "code": "dup-test",
        "name": "x",
        "base_price": "1.0000",
        "billing_period": "monthly",
    }
    await client.post(
        "/platform/billing/plans", headers=platform_actor_header, json=payload
    )
    r = await client.post(
        "/platform/billing/plans", headers=platform_actor_header, json=payload
    )
    assert r.status_code == 409


@pytest.mark.anyio
async def test_get_plan(client, platform_actor_header):
    create = await client.post(
        "/platform/billing/plans",
        headers=platform_actor_header,
        json={
            "code": "get-test",
            "name": "Get Plan",
            "base_price": "1000.0000",
            "billing_period": "monthly",
        },
    )
    plan_id = create.json()["id"]
    r = await client.get(
        f"/platform/billing/plans/{plan_id}", headers=platform_actor_header
    )
    assert r.status_code == 200
    assert r.json()["code"] == "get-test"


@pytest.mark.anyio
async def test_get_plan_404_for_unknown(client, platform_actor_header):
    r = await client.get(
        f"/platform/billing/plans/{uuid.uuid4()}", headers=platform_actor_header
    )
    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_plans(client, platform_actor_header):
    r = await client.get(
        "/platform/billing/plans", headers=platform_actor_header
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.anyio
async def test_patch_plan(client, platform_actor_header):
    create = await client.post(
        "/platform/billing/plans",
        headers=platform_actor_header,
        json={
            "code": "patch-test",
            "name": "Original Name",
            "base_price": "1000.0000",
            "billing_period": "monthly",
        },
    )
    plan_id = create.json()["id"]
    r = await client.patch(
        f"/platform/billing/plans/{plan_id}",
        headers=platform_actor_header,
        json={"name": "Updated Name"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Name"
```

You'll need a `platform_actor_header` fixture. Check `tests/platform_/conftest.py` or `tests/conftest.py` for the existing one — there should be a fixture that creates a platform user and returns the correct auth header.

If no such fixture exists, create one in the test file:

```python
@pytest.fixture
async def platform_actor_header(factory):
    # Create a platform user in the DB and return the stub header
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        u = PlatformUser(
            email=f"actor-{uuid.uuid4().hex[:8]}@test.example",
            full_name="API Test Actor",
            is_active=True,
            is_superuser=True,
            created_at=now,
            updated_at=now,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
    return {"X-Platform-Actor-ID": str(u.id)}
```

Add cleanup for the user.

- [ ] **Step 6: Run tests + mypy + ruff**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_api_plans.py -v 2>&1 | tail -20
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/test_api_plans.py
```

Expected: 6 tests pass.

If tests fail because the auth header format is wrong, read `app/platform_/auth.py` to understand the stub-mode header expectation. Use it consistently.

- [ ] **Step 7: Commit**

```bash
git add app/platform_/billing/services/plan_service.py \
        app/platform_/billing/services/__init__.py \
        app/platform_/billing/api.py \
        app/main.py \
        tests/platform_/billing/test_api_plans.py
git commit -m "feat(billing): PlanService + plan CRUD HTTP endpoints"
```

---

## Task 3: Subscription endpoints

**Files:**
- Modify: `app/platform_/billing/api.py` (append subscription endpoints)
- Create: `tests/platform_/billing/test_api_subscriptions.py`

Endpoints:
- `GET /platform/billing/subscriptions` — list (filter by `tenant_id`, `status`)
- `POST /platform/billing/subscriptions` — assign plan to tenant (direct, no maker-checker)
- `GET /platform/billing/subscriptions/{id}` — detail
- `POST /platform/billing/subscriptions/{id}/cancel` — supports `mode=at_period_end|immediate`
- `POST /platform/billing/subscriptions/{id}/reactivate` — direct

For `mode=immediate`, the endpoint creates an `ApprovalRequest(operation_type="billing.cancel_subscription")` instead of calling SubscriptionService.cancel directly. The executor handles the actual cancellation when quorum is met.

- [ ] **Step 1: Append endpoints to `app/platform_/billing/api.py`**

Add new imports at the top (or extend existing imports):

```python
from app.platform_.billing.exceptions import (
    InvalidTransition,
    PlanCodeConflict,
    PlanInactive,
    SubscriptionConflict,
)
from app.platform_.billing.schemas import (
    SubscriptionCancelIn,
    SubscriptionCreateIn,
    SubscriptionOut,
    SubscriptionPlanIn,
    SubscriptionPlanOut,
    SubscriptionPlanPatch,
)
from app.platform_.billing.services import SubscriptionService
from app.modules.maker_checker.service import ApprovalService
```

Append endpoint handlers:

```python
# ── Subscriptions ─────────────────────────────────────────────────────────────


@platform_router.get(
    "/subscriptions",
    response_model=list[SubscriptionOut],
)
async def list_subscriptions(
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    tenant_id: uuid.UUID | None = None,
    status_filter: str | None = None,
) -> list[SubscriptionOut]:
    from app.platform_.billing.models import Subscription
    from sqlalchemy import select

    q = select(Subscription).order_by(Subscription.created_at.desc())
    if tenant_id is not None:
        q = q.where(Subscription.tenant_id == tenant_id)
    if status_filter is not None:
        q = q.where(Subscription.status == status_filter)
    result = await session.execute(q)
    return [SubscriptionOut.model_validate(s) for s in result.scalars().all()]


@platform_router.post(
    "/subscriptions",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
)
async def assign_subscription(
    payload: SubscriptionCreateIn,
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionOut:
    try:
        sub = await SubscriptionService(session).assign(
            tenant_id=payload.tenant_id,
            plan_id=payload.plan_id,
            start_date=payload.start_date,
        )
    except PlanInactive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SubscriptionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SubscriptionOut.model_validate(sub)


@platform_router.get(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionOut,
)
async def get_subscription(
    subscription_id: uuid.UUID,
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionOut:
    sub = await SubscriptionService(session).get(subscription_id)
    if sub is None:
        raise HTTPException(
            status_code=404, detail=f"Subscription {subscription_id} not found"
        )
    return SubscriptionOut.model_validate(sub)


@platform_router.post(
    "/subscriptions/{subscription_id}/cancel",
)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    payload: SubscriptionCancelIn,
    user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    mode: str = "at_period_end",
) -> dict[str, str]:
    """Cancel a subscription. Two modes:

    - `mode=at_period_end` (default): graceful — sets cancelled_at + reason,
      status changes at period end (beat job). No maker-checker.
    - `mode=immediate`: hard cancel — creates an ApprovalRequest. The checker
      must approve, then the `billing.cancel_subscription` executor flips the
      status to cancelled.
    """
    if mode not in {"at_period_end", "immediate"}:
        raise HTTPException(
            status_code=400, detail="mode must be 'at_period_end' or 'immediate'"
        )

    if mode == "at_period_end":
        try:
            sub = await SubscriptionService(session).cancel(
                subscription_id=subscription_id,
                reason=payload.reason,
                cancel_at_period_end=True,
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "status": "cancellation_scheduled",
            "subscription_id": str(sub.id),
        }

    # mode == "immediate" — go through maker-checker
    sub = await SubscriptionService(session).get(subscription_id)
    if sub is None:
        raise HTTPException(
            status_code=404, detail=f"Subscription {subscription_id} not found"
        )

    approval_request = await ApprovalService(session).submit(
        operation_type="billing.cancel_subscription",
        payload={
            "subscription_id": str(subscription_id),
            "reason": payload.reason,
        },
        requested_by=user.id,
    )
    return {
        "status": "pending_approval",
        "approval_request_id": str(approval_request.id),
    }


@platform_router.post(
    "/subscriptions/{subscription_id}/reactivate",
    response_model=SubscriptionOut,
)
async def reactivate_subscription(
    subscription_id: uuid.UUID,
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionOut:
    try:
        sub = await SubscriptionService(session).reactivate(
            subscription_id=subscription_id
        )
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SubscriptionOut.model_validate(sub)
```

- [ ] **Step 2: Write `tests/platform_/billing/test_api_subscriptions.py`**

Tests (6):
- `test_assign_subscription` — POST /subscriptions creates and returns it
- `test_assign_subscription_rejects_inactive_plan` — 409
- `test_list_subscriptions_filters_by_tenant`
- `test_cancel_subscription_at_period_end` — direct, returns 200 with `cancellation_scheduled`
- `test_cancel_subscription_immediate_creates_approval_request` — returns 200 with `pending_approval`
- `test_reactivate_subscription_from_suspended`

Copy the helper pattern from `test_api_plans.py`. You'll need a tenant fixture too (create via `_make_tenant`).

- [ ] **Step 3: Run tests + mypy + ruff**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_api_subscriptions.py -v 2>&1 | tail -15
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/test_api_subscriptions.py
```

Expected: 6 tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/platform_/billing/api.py tests/platform_/billing/test_api_subscriptions.py
git commit -m "feat(billing): subscription HTTP endpoints — assign, list, detail, cancel, reactivate"
```

---

## Task 4: Invoice + Payment endpoints (maker-checker flow)

**Files:**
- Modify: `app/platform_/billing/api.py` (append invoice list/detail + payment record/reject + invoice void endpoints)
- Create: `tests/platform_/billing/test_api_invoices.py`
- Create: `tests/platform_/billing/test_api_payments.py`
- Create: `tests/platform_/billing/test_api_void_cancel.py`

Endpoints to add:
- `GET /platform/billing/invoices` — list (filter by tenant_id, status)
- `GET /platform/billing/invoices/{id}` — detail with line items (use InvoiceDetailOut)
- `POST /platform/billing/invoices/{id}/void` — submits ApprovalRequest(billing.void_invoice)
- `POST /platform/billing/invoices/{id}/payments` — creates Payment(pending) + ApprovalRequest(billing.confirm_payment) in one transaction
- `POST /platform/billing/payments/{id}/reject` — pairs ApprovalService.reject + PaymentService.reject
- `GET /platform/billing/payments/pending-confirmation` — list payments where status='pending'

- [ ] **Step 1: Append endpoints to `app/platform_/billing/api.py`**

```python
# Add imports
from app.platform_.billing.schemas import (
    InvoiceDetailOut,
    InvoiceOut,
    InvoiceVoidIn,
    PaymentOut,
    PaymentRecordIn,
)
from app.platform_.billing.services import (
    InvoiceService,
    PaymentService,
)
from pydantic import BaseModel


class PaymentRejectIn(BaseModel):
    reason: str


# ── Invoices ──────────────────────────────────────────────────────────────────


@platform_router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    tenant_id: uuid.UUID | None = None,
    status_filter: str | None = None,
) -> list[InvoiceOut]:
    from app.platform_.billing.models import Invoice
    from sqlalchemy import select

    q = select(Invoice).order_by(Invoice.created_at.desc())
    if tenant_id is not None:
        q = q.where(Invoice.tenant_id == tenant_id)
    if status_filter is not None:
        q = q.where(Invoice.status == status_filter)
    result = await session.execute(q)
    return [InvoiceOut.model_validate(inv) for inv in result.scalars().all()]


@platform_router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
async def get_invoice(
    invoice_id: uuid.UUID,
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> InvoiceDetailOut:
    from app.platform_.billing.models import InvoiceLineItem
    from sqlalchemy import select

    invoice = await InvoiceService(session).get(invoice_id)
    if invoice is None:
        raise HTTPException(
            status_code=404, detail=f"Invoice {invoice_id} not found"
        )
    line_result = await session.execute(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_order)
    )
    lines = list(line_result.scalars().all())
    inv_dict = InvoiceOut.model_validate(invoice).model_dump()
    inv_dict["line_items"] = [
        {
            "id": line.id,
            "invoice_id": line.invoice_id,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "amount": line.amount,
            "line_order": line.line_order,
        }
        for line in lines
    ]
    return InvoiceDetailOut.model_validate(inv_dict)


@platform_router.post("/invoices/{invoice_id}/void")
async def void_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceVoidIn,
    user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> dict[str, str]:
    """Submit a void-invoice approval request. The actual void runs in
    the `billing.void_invoice` executor on approval.
    """
    invoice = await InvoiceService(session).get(invoice_id)
    if invoice is None:
        raise HTTPException(
            status_code=404, detail=f"Invoice {invoice_id} not found"
        )

    approval_request = await ApprovalService(session).submit(
        operation_type="billing.void_invoice",
        payload={"invoice_id": str(invoice_id), "reason": payload.reason},
        requested_by=user.id,
    )
    return {
        "status": "pending_approval",
        "approval_request_id": str(approval_request.id),
    }


# ── Payments ──────────────────────────────────────────────────────────────────


@platform_router.post("/invoices/{invoice_id}/payments")
async def record_payment(
    invoice_id: uuid.UUID,
    payload: PaymentRecordIn,
    user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> dict[str, str]:
    """Maker action: create Payment(pending) + ApprovalRequest in one tx.

    The checker approves via `/maker-checker/approval-requests/{id}/approve`
    (which triggers the `billing.confirm_payment` executor) OR rejects via
    `/platform/billing/payments/{id}/reject`.
    """
    invoice = await InvoiceService(session).get(invoice_id)
    if invoice is None:
        raise HTTPException(
            status_code=404, detail=f"Invoice {invoice_id} not found"
        )

    try:
        pmt = await PaymentService(session).record(
            invoice_id=invoice_id,
            amount=payload.amount,
            currency=payload.currency,
            payment_method=payload.payment_method,
            external_reference=payload.external_reference,
            notes=payload.notes,
            recorded_by=user.id,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # If the payment was idempotently returned (same key, existing row),
    # it might already have an approval_request_id. Don't create a duplicate.
    if pmt.approval_request_id is not None:
        return {
            "status": "pending_approval",
            "payment_id": str(pmt.id),
            "approval_request_id": str(pmt.approval_request_id),
            "idempotent": "true",
        }

    approval_request = await ApprovalService(session).submit(
        operation_type="billing.confirm_payment",
        payload={"payment_id": str(pmt.id)},
        requested_by=user.id,
    )
    # Link the Payment to the ApprovalRequest.
    pmt.approval_request_id = approval_request.id
    await session.flush()

    return {
        "status": "pending_approval",
        "payment_id": str(pmt.id),
        "approval_request_id": str(approval_request.id),
    }


@platform_router.post("/payments/{payment_id}/reject")
async def reject_payment(
    payment_id: uuid.UUID,
    payload: PaymentRejectIn,
    user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> dict[str, str]:
    """Checker action: reject a pending payment.

    Pairs ApprovalService.reject + PaymentService.reject in one transaction.
    Self-rejection (maker == rejector) is rejected.
    """
    pmt = await PaymentService(session).get(payment_id)
    if pmt is None:
        raise HTTPException(
            status_code=404, detail=f"Payment {payment_id} not found"
        )
    if pmt.approval_request_id is None:
        raise HTTPException(
            status_code=409,
            detail=f"Payment {payment_id} has no associated approval request",
        )

    try:
        await ApprovalService(session).reject(
            request_id=pmt.approval_request_id,
            actor_user_id=user.id,
            reason=payload.reason,
        )
        await PaymentService(session).reject(
            payment_id=payment_id,
            rejected_by=user.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {"status": "rejected", "payment_id": str(payment_id)}


@platform_router.get(
    "/payments/pending-confirmation",
    response_model=list[PaymentOut],
)
async def list_pending_payments(
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> list[PaymentOut]:
    from app.platform_.billing.models import Payment
    from sqlalchemy import select

    q = (
        select(Payment)
        .where(Payment.status == "pending")
        .order_by(Payment.recorded_at.desc())
    )
    result = await session.execute(q)
    return [PaymentOut.model_validate(p) for p in result.scalars().all()]
```

- [ ] **Step 2: Write `tests/platform_/billing/test_api_invoices.py`**

8 tests covering:
- list invoices (empty + populated)
- list invoices filtered by tenant
- get invoice detail with line items
- get invoice 404
- void invoice creates approval request
- void invoice 404 for unknown

(Skip the full void execution path — that's the executor's job, tested in SP04.)

- [ ] **Step 3: Write `tests/platform_/billing/test_api_payments.py`**

6 tests:
- `test_record_payment_creates_pending_payment_and_approval_request`
- `test_record_payment_is_idempotent` (same idempotency_key twice → returns same payment_id + approval_request_id with `idempotent: "true"`)
- `test_record_payment_404_for_unknown_invoice`
- `test_reject_payment_marks_both_rejected`
- `test_reject_payment_rejects_self_rejection`
- `test_pending_confirmation_list_returns_only_pending`

- [ ] **Step 4: Write `tests/platform_/billing/test_api_void_cancel.py`**

4 tests:
- `test_void_invoice_creates_approval_request`
- `test_cancel_subscription_immediate_creates_approval_request`
- `test_cancel_subscription_at_period_end_marks_directly`
- `test_void_invoice_404_for_unknown`

- [ ] **Step 5: Run tests + mypy + ruff**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_api_invoices.py tests/platform_/billing/test_api_payments.py tests/platform_/billing/test_api_void_cancel.py -v 2>&1 | tail -25
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/
```

Expected: 8 + 6 + 4 = 18 new tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/platform_/billing/api.py \
        tests/platform_/billing/test_api_invoices.py \
        tests/platform_/billing/test_api_payments.py \
        tests/platform_/billing/test_api_void_cancel.py
git commit -m "feat(billing): invoice + payment HTTP endpoints — record, void, reject, pending"
```

---

## Task 5: Invoice PDF rendering

**Files:**
- Create: `app/platform_/billing/templates/invoice.html`
- Create: `app/platform_/billing/pdf.py`
- Modify: `app/platform_/billing/api.py` (add PDF endpoint)
- Create: `tests/platform_/billing/test_pdf.py`

- [ ] **Step 1: Create `app/platform_/billing/templates/invoice.html`**

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Invoice {{ invoice.invoice_number }}</title>
<style>
  @page { size: A4; margin: 18mm 15mm; }
  body { font-family: "DejaVu Sans", Helvetica, sans-serif; font-size: 10pt; color: #1a1a1a; }
  h1 { margin: 0; font-size: 22pt; color: #0a3a6b; }
  .meta { margin: 12pt 0 24pt; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 6pt 8pt; }
  thead th { background: #0a3a6b; color: white; text-align: left; }
  tbody td { border-bottom: 1px solid #e0e0e0; }
  td.right, th.right { text-align: right; }
  .totals { margin-top: 18pt; }
  .totals td { font-weight: bold; }
  .footer { margin-top: 36pt; font-size: 9pt; color: #555; }
  .status-tag { display: inline-block; padding: 3pt 8pt; border-radius: 3pt;
                background: #f1f5f9; font-weight: bold; text-transform: uppercase; }
  .void { color: #c00; }
</style>
</head>
<body>
  <h1>Invoice</h1>
  <div class="meta">
    <div><strong>Number:</strong> {{ invoice.invoice_number }}</div>
    <div><strong>Issued:</strong> {{ invoice.issued_at.strftime("%Y-%m-%d") if invoice.issued_at else "—" }}</div>
    <div><strong>Due:</strong> {{ invoice.due_at.strftime("%Y-%m-%d") }}</div>
    <div><strong>Period:</strong> {{ invoice.billing_period_start.strftime("%Y-%m-%d") }} to {{ invoice.billing_period_end.strftime("%Y-%m-%d") }}</div>
    <div><strong>Tenant:</strong> {{ invoice.tenant_id }}</div>
    <div><strong>Status:</strong> <span class="status-tag {% if invoice.status == 'void' %}void{% endif %}">{{ invoice.status }}</span></div>
    {% if invoice.status == "void" and invoice.void_reason %}
    <div class="void"><strong>Void reason:</strong> {{ invoice.void_reason }}</div>
    {% endif %}
  </div>

  <table>
    <thead>
      <tr>
        <th>Description</th>
        <th class="right">Quantity</th>
        <th class="right">Unit price ({{ invoice.currency }})</th>
        <th class="right">Amount ({{ invoice.currency }})</th>
      </tr>
    </thead>
    <tbody>
      {% for line in line_items %}
      <tr>
        <td>{{ line.description }}</td>
        <td class="right">{{ line.quantity }}</td>
        <td class="right">{{ "{:,.2f}".format(line.unit_price) }}</td>
        <td class="right">{{ "{:,.2f}".format(line.amount) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <table class="totals">
    <tr><td>Subtotal</td><td class="right">{{ "{:,.2f}".format(invoice.amount_subtotal) }}</td></tr>
    <tr><td>Tax</td><td class="right">{{ "{:,.2f}".format(invoice.amount_tax) }}</td></tr>
    <tr><td>Total ({{ invoice.currency }})</td><td class="right">{{ "{:,.2f}".format(invoice.amount_total) }}</td></tr>
    <tr><td>Paid</td><td class="right">{{ "{:,.2f}".format(invoice.amount_paid) }}</td></tr>
    <tr><td><strong>Balance due</strong></td><td class="right"><strong>{{ "{:,.2f}".format(invoice.amount_total - invoice.amount_paid) }}</strong></td></tr>
  </table>

  <div class="footer">
    Generated {{ now_iso }} — SACCO Platform Billing
  </div>
</body>
</html>
```

- [ ] **Step 2: Create `app/platform_/billing/pdf.py`**

```python
"""WeasyPrint-backed invoice PDF rendering.

`render_invoice_pdf` is pure — takes ORM objects, returns bytes. No I/O
beyond reading the bundled template. Callers (the API endpoint) are
responsible for setting Content-Type, Content-Disposition, etc.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

if TYPE_CHECKING:
    from app.platform_.billing.models import Invoice, InvoiceLineItem

_log = structlog.get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_invoice_pdf(
    invoice: Invoice, line_items: list[InvoiceLineItem]
) -> bytes:
    """Render an invoice + its line items to a PDF byte string."""
    from weasyprint import HTML  # noqa: PLC0415  — heavy import, lazy load

    template = _env.get_template("invoice.html")
    html_str = template.render(
        invoice=invoice,
        line_items=line_items,
        now_iso=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )
    pdf_bytes: bytes = HTML(string=html_str).write_pdf()
    _log.info(
        "invoice.pdf_rendered",
        invoice_id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        size_bytes=len(pdf_bytes),
    )
    return pdf_bytes
```

- [ ] **Step 3: Add the PDF endpoint to `app/platform_/billing/api.py`**

```python
from fastapi.responses import Response


@platform_router.get(
    "/invoices/{invoice_id}.pdf",
    response_class=Response,
)
async def get_invoice_pdf(
    invoice_id: uuid.UUID,
    _user: Annotated[CurrentPlatformUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> Response:
    from app.platform_.billing.models import InvoiceLineItem
    from app.platform_.billing.pdf import render_invoice_pdf
    from sqlalchemy import select

    invoice = await InvoiceService(session).get(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    line_result = await session.execute(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_order)
    )
    lines = list(line_result.scalars().all())
    pdf_bytes = render_invoice_pdf(invoice, lines)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="{invoice.invoice_number}.pdf"'
            ),
        },
    )
```

- [ ] **Step 4: Write `tests/platform_/billing/test_pdf.py`**

```python
"""Smoke tests for invoice PDF rendering."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
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
    Subscription,
    SubscriptionPlan,
)
from app.platform_.billing.pdf import render_invoice_pdf
from app.platform_.billing.services import (
    InvoiceService,
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
            name="PDF Test",
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
            name="PDF Plan",
            base_price=Decimal("75000.0000"),
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


@pytest.mark.anyio
async def test_render_invoice_pdf_returns_pdf_bytes(factory) -> None:
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
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = invoice.id
    try:
        async with factory() as s:
            await _set_platform(s)
            from sqlalchemy import select
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            lines = list(
                (
                    await s.execute(
                        select(InvoiceLineItem).where(
                            InvoiceLineItem.invoice_id == invoice_id
                        )
                    )
                ).scalars().all()
            )
            pdf = render_invoice_pdf(inv, lines)
            assert pdf[:5] == b"%PDF-"
            assert len(pdf) > 1000  # smoke: not empty
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_render_voided_invoice_includes_void_status(factory) -> None:
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
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = invoice.id
    async with factory() as s:
        await _set_platform(s)
        await InvoiceService(s).void(
            invoice_id=invoice_id, reason="rendered void test"
        )
        await s.commit()
    try:
        async with factory() as s:
            await _set_platform(s)
            from sqlalchemy import select
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            lines = list(
                (
                    await s.execute(
                        select(InvoiceLineItem).where(
                            InvoiceLineItem.invoice_id == invoice_id
                        )
                    )
                ).scalars().all()
            )
            pdf = render_invoice_pdf(inv, lines)
            assert pdf[:5] == b"%PDF-"
    finally:
        await _cleanup(factory)
```

- [ ] **Step 5: Run tests + mypy + ruff**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_pdf.py -v 2>&1 | tail -10
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/test_pdf.py
```

Expected: 2 PDF tests pass. WeasyPrint is already a project dependency (used by credit module per the v1b contracts), so this should "just work."

If WeasyPrint complains about missing system libraries (Pango, cairo), document the install command in the commit but do not block on the system install if dev env already has it.

- [ ] **Step 6: Commit**

```bash
git add app/platform_/billing/templates/ \
        app/platform_/billing/pdf.py \
        app/platform_/billing/api.py \
        tests/platform_/billing/test_pdf.py
git commit -m "feat(billing): invoice PDF rendering (Jinja2 + WeasyPrint) on-demand"
```

---

## Task 6: Tenant-facing /billing/me endpoints + CLAUDE.md + push

**Files:**
- Modify: `app/platform_/billing/api.py` (add tenant_router endpoints)
- Modify: `app/main.py` (mount tenant_router)
- Create: `tests/platform_/billing/test_api_me.py`
- Modify: `CLAUDE.md`

Tenant endpoints:
- `GET /billing/me/subscription` — current live subscription for the requesting tenant
- `GET /billing/me/invoices` — list own invoices
- `GET /billing/me/invoices/{id}` — single invoice detail (404 if not own tenant)
- `GET /billing/me/invoices/{id}.pdf` — PDF of own invoice (404 if not own tenant)

Each handler resolves `current_tenant_user.tenant_id`, then filters/validates. **Cross-tenant access returns 404, not 403** — don't leak existence.

- [ ] **Step 1: Append tenant endpoints to `app/platform_/billing/api.py`**

```python
from app.modules.iam.dependencies import CurrentTenantUser


@tenant_router.get("/subscription", response_model=SubscriptionOut)
async def get_my_subscription(
    user: Annotated[CurrentTenantUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> SubscriptionOut:
    sub = await SubscriptionService(session).get_live_for_tenant(user.tenant_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="No active subscription")
    return SubscriptionOut.model_validate(sub)


@tenant_router.get("/invoices", response_model=list[InvoiceOut])
async def list_my_invoices(
    user: Annotated[CurrentTenantUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> list[InvoiceOut]:
    from app.platform_.billing.models import Invoice
    from sqlalchemy import select

    q = (
        select(Invoice)
        .where(Invoice.tenant_id == user.tenant_id)
        .order_by(Invoice.created_at.desc())
    )
    result = await session.execute(q)
    return [InvoiceOut.model_validate(inv) for inv in result.scalars().all()]


@tenant_router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
async def get_my_invoice(
    invoice_id: uuid.UUID,
    user: Annotated[CurrentTenantUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> InvoiceDetailOut:
    from app.platform_.billing.models import InvoiceLineItem
    from sqlalchemy import select

    invoice = await InvoiceService(session).get(invoice_id)
    # Cross-tenant access: 404 (not 403, to avoid leaking existence)
    if invoice is None or invoice.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    line_result = await session.execute(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_order)
    )
    lines = list(line_result.scalars().all())
    inv_dict = InvoiceOut.model_validate(invoice).model_dump()
    inv_dict["line_items"] = [
        {
            "id": line.id,
            "invoice_id": line.invoice_id,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "amount": line.amount,
            "line_order": line.line_order,
        }
        for line in lines
    ]
    return InvoiceDetailOut.model_validate(inv_dict)


@tenant_router.get(
    "/invoices/{invoice_id}.pdf",
    response_class=Response,
)
async def get_my_invoice_pdf(
    invoice_id: uuid.UUID,
    user: Annotated[CurrentTenantUser, Depends()],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> Response:
    from app.platform_.billing.models import InvoiceLineItem
    from app.platform_.billing.pdf import render_invoice_pdf
    from sqlalchemy import select

    invoice = await InvoiceService(session).get(invoice_id)
    if invoice is None or invoice.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    line_result = await session.execute(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_order)
    )
    lines = list(line_result.scalars().all())
    pdf_bytes = render_invoice_pdf(invoice, lines)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="{invoice.invoice_number}.pdf"'
            ),
        },
    )
```

- [ ] **Step 2: Mount tenant_router in `app/main.py`**

```python
from app.platform_.billing.api import (
    platform_router as billing_platform_router,
    tenant_router as billing_tenant_router,
)
# ...
app.include_router(billing_platform_router)
app.include_router(billing_tenant_router)
```

- [ ] **Step 3: Write `tests/platform_/billing/test_api_me.py`**

5 tests (using the tenant auth stub):
- `test_get_my_subscription_returns_active`
- `test_get_my_subscription_404_when_none`
- `test_list_my_invoices_returns_own`
- `test_get_my_invoice_404_for_other_tenant`
- `test_get_my_invoice_pdf_returns_pdf_bytes`

For auth, you'll need a tenant-user fixture that sets the `X-Tenant-Slug` + `X-Tenant-Actor-ID` (or whatever the IAM stub headers are). Look at `tests/modules/iam/` for the pattern.

- [ ] **Step 4: Extend the "Billing module contracts" section in `CLAUDE.md`**

Append at the end of the existing section:

```markdown
- HTTP API surface lives in `app/platform_/billing/api.py`, exposing two
  routers: `platform_router` at `/platform/billing/*` and `tenant_router`
  at `/billing/me/*`. Both are mounted from `app/main.py`. Do not add
  billing endpoints outside this file.
- `POST /platform/billing/invoices/{id}/payments` creates `Payment(pending)`
  and the matching `ApprovalRequest(operation_type='billing.confirm_payment')`
  in one DB transaction. The maker calls this; the checker approves via
  the generic `/maker-checker/approval-requests/{id}/approve` endpoint or
  rejects via `/platform/billing/payments/{id}/reject` (paired rejection).
- `POST /platform/billing/payments/{id}/reject` is the ONLY way to reject
  a pending payment. It pairs `ApprovalService.reject()` +
  `PaymentService.reject()` in one transaction. Using the generic approval
  reject endpoint alone leaves the Payment row stuck in 'pending'.
- `POST /platform/billing/subscriptions/{id}/cancel?mode=at_period_end`
  is a direct call (no maker-checker — soft cancel, reversible until period
  end). `?mode=immediate` goes through the maker-checker executor.
- `POST /platform/billing/invoices/{id}/void` always requires maker-checker.
  There is no direct void endpoint.
- Invoice PDFs are rendered on-demand at GET time via WeasyPrint. The
  template lives at `app/platform_/billing/templates/invoice.html`.
  `Invoice.pdf_storage_key` is reserved for a future caching layer and
  stays NULL in v1.
- Tenant-facing endpoints (`/billing/me/*`) read from the platform schema
  but enforce ownership in the handler via `tenant_id == current_user.tenant_id`.
  Cross-tenant access returns 404 (not 403) to avoid leaking row existence.
- `PaymentService.confirm()` accepts `confirmed_by: UUID | None`. The
  `billing.confirm_payment` executor calls it with `None` because
  `ApprovalService.approve()` has already enforced maker != checker.
  Direct callers (tests, scripts) should still pass the actual user UUID.
```

- [ ] **Step 5: Final regression + lint + push**

```bash
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
env -u DATABASE_URL python -m mypy app/
ruff check app/ tests/
```

Expected: all green. Roughly 700+ tests passing (664 from SP04 + ~45 new SP05 tests).

- [ ] **Step 6: Commit and push**

```bash
git add app/platform_/billing/api.py \
        app/main.py \
        tests/platform_/billing/test_api_me.py \
        CLAUDE.md
git commit -m "feat(billing): tenant-facing /billing/me endpoints + CLAUDE.md SP05 contracts"
git push origin feat/phase-1-billing
```

---

## Self-Review Checklist

- [x] `PaymentService.confirm()` accepts `confirmed_by: UUID | None`; executor uses None path
- [x] PlanService thin CRUD wrapper around SubscriptionPlan ORM
- [x] Single api.py with two FastAPI router instances
- [x] All platform endpoints require `CurrentPlatformUser`
- [x] All tenant-me endpoints require `CurrentTenantUser` and enforce `tenant_id` ownership
- [x] Cross-tenant access returns 404 (not 403)
- [x] Payment record creates Payment(pending) + ApprovalRequest in one transaction
- [x] Payment record is idempotent on `idempotency_key` (existing Payment + linked approval_request_id returned)
- [x] Payment rejection has its own endpoint that pairs ApprovalService.reject + PaymentService.reject
- [x] Subscription cancel supports both `at_period_end` (direct) and `immediate` (maker-checker)
- [x] Subscription assign + reactivate are direct (no maker-checker)
- [x] Void invoice always requires maker-checker
- [x] PDF rendering on-demand via WeasyPrint; no storage in v1
- [x] PDF template uses only server-side data, no external fetches
- [x] CLAUDE.md updated with SP05 API contracts
- [x] mypy strict + ruff clean across all new code
- [x] No new top-level dependencies (WeasyPrint + Jinja2 already in project)
