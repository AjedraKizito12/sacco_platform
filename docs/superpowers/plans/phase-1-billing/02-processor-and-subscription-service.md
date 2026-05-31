# Phase 1 Sub-Plan 02: Processor Interface + SubscriptionService

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** All commits land on `feat/phase-1-billing` (the integration branch). Sub-branches are optional — SP01 worked directly on the integration branch and that pattern is fine for solo work.

**Goal:** Land the `PaymentProcessor` abstraction (ABC + `OfflineProcessor` default + 3 stub future processors) and the `SubscriptionService` with assign / cancel / reactivate / past-due / suspended transitions. Every transition updates both `platform.subscriptions.status` and the denormalized `platform.tenants.subscription_status` atomically.

**Architecture:**

- `PaymentProcessor` is a tiny ABC in `processors/base.py`. v1 only exercises `OfflineProcessor`; `flutterwave.py`, `stripe.py`, `momo.py` are import-only stubs that raise `NotImplementedError` when instantiated. This pins the module graph so SP03/SP05 don't need to invent new shape later.
- `SubscriptionService` lives in `services/subscription_service.py`. It is plain async, takes an `AsyncSession` in its constructor (mirroring `TenantService`, `UserService` patterns already in `app/platform_/`).
- All state transitions are atomic writes to **two rows** in the same session flush: the `Subscription` row and the owning `Tenant.subscription_status` denormalisation. No transition method is allowed to skip the tenant update — the middleware in SP04 keys off `tenants.subscription_status`, so drift breaks access control.
- No HTTP, no maker-checker wrapping, no beat-job scheduling in this sub-plan. Those land in SP04 (executors + middleware), SP05 (API), SP06 (beat).

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0 async, structlog, pytest + pytest-asyncio. mypy strict + ruff non-negotiable.

**Roadmap reference:** `docs/superpowers/plans/saas-launch-roadmap.md` §5 Phase 1.

**Prerequisite:** SP01 merged onto `feat/phase-1-billing` (DB tables + ORM models + Pydantic schemas exist).

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/platform_/billing/processors/base.py` | Create | `PaymentProcessor` ABC + `ProcessorResult` dataclass |
| `app/platform_/billing/processors/offline.py` | Create | `OfflineProcessor` — the v1 default; returns pending result for human-driven flow |
| `app/platform_/billing/processors/flutterwave.py` | Create | Stub — class raises `NotImplementedError` |
| `app/platform_/billing/processors/stripe.py` | Create | Stub — class raises `NotImplementedError` |
| `app/platform_/billing/processors/momo.py` | Create | Stub — class raises `NotImplementedError` |
| `app/platform_/billing/processors/__init__.py` | Modify | Re-export `PaymentProcessor`, `OfflineProcessor`, `ProcessorResult`; keep stubs internal |
| `app/platform_/billing/services/subscription_service.py` | Create | `SubscriptionService` (assign, cancel, reactivate, transition helpers) |
| `app/platform_/billing/services/__init__.py` | Modify | Re-export `SubscriptionService` |
| `app/platform_/billing/exceptions.py` | Create | Module-local exception types (`SubscriptionConflict`, `InvalidTransition`, `PlanInactive`) |
| `tests/platform_/billing/test_processors.py` | Create | ABC contract test + OfflineProcessor behaviour + stubs raise |
| `tests/platform_/billing/test_subscription_service_assign.py` | Create | All assign() paths and edge cases |
| `tests/platform_/billing/test_subscription_service_cancel.py` | Create | cancel() and reactivate() paths |
| `tests/platform_/billing/test_subscription_service_transitions.py` | Create | past_due / suspended transitions, tenant denormalisation parity |
| `CLAUDE.md` | Modify | Append billing-module contracts section |

---

## Architectural decisions locked here

1. **PaymentProcessor interface is minimal.** Just `code: str` property and `async initiate(...)` method. `verify_payment`, `handle_webhook`, `refund` etc. will be added when a real processor (Flutterwave) lands — YAGNI.
2. **`OfflineProcessor.initiate()` is a pure function — it does NOT touch the DB.** It returns a `ProcessorResult(status="pending", external_id=None, message="awaiting confirmation")`. DB writes (creating the `Payment` row, status changes) happen in `PaymentService` (SP03), invoked by the API/executor layer.
3. **`SubscriptionService.assign()` raises `SubscriptionConflict` on duplicate live subscription.** The `uq_subscriptions_live_tenant` partial unique index would raise an `IntegrityError` anyway; we translate to a domain exception so callers don't depend on DB error strings.
4. **`assign()` does not create the first invoice.** Invoice generation is SP03 (`InvoiceService.generate_for_subscription`). The first nightly run of the `generate_next_period_invoices` beat job (SP06) handles ongoing periods. For trial subscriptions, no invoice is generated until trial end.
5. **Initial status from `assign()`:** if `plan.trial_period_days > 0` → status=`trialing`, `current_period_end = start_date + trial_period_days`. Otherwise status=`active`, `current_period_end = start_date + billing_period_length`. The `billing_period_length` mapping is `{monthly: 30 days, quarterly: 90 days, annual: 365 days}`. Calendar-month accuracy is a SP06 concern (beat job uses `relativedelta`); for `assign()`, fixed-day approximation is acceptable because the next billing job will reconcile.
6. **`cancel(cancel_at_period_end=True)` (default)** sets `cancelled_at = now()` and `cancellation_reason = reason` but leaves `status` as-is until the next beat job picks it up. `cancel(cancel_at_period_end=False)` immediately transitions to `cancelled` and updates `tenants.subscription_status`.
7. **`reactivate()`** is the inverse of suspension: moves `suspended` → `active`, recomputes `current_period_end` from `now()` + plan period, clears `grace_period_ends_at`. Only callable from `suspended` or `past_due`; raises `InvalidTransition` otherwise.
8. **`transition_to_past_due()` and `transition_to_suspended()`** are the beat-callable transition methods. Each performs both writes (Subscription + Tenant) in the caller's session. The caller (SP06 beat) is responsible for the `commit()` boundary so the two writes are atomic.
9. **No maker-checker in SP02.** `cancel()` is a direct method here. SP04 wraps it via `@approval_executor`. The service does not know about ApprovalRequests.
10. **Plan term snapshotting is deliberately not implemented in v1.** CLAUDE.md rule 10 applies to loans/savings products; billing plans use live FK lookup. This is documented in the CLAUDE.md update at the end. A future migration can add snapshot columns to `subscriptions` if pricing audit becomes a requirement.

---

## Task 1: PaymentProcessor ABC + ProcessorResult

**Files:**
- Create: `app/platform_/billing/processors/base.py`
- Test: `tests/platform_/billing/test_processors.py` (set up shell only; offline test added in Task 2)

- [ ] **Step 1: Write `app/platform_/billing/processors/base.py`**

```python
"""PaymentProcessor abstraction.

A `PaymentProcessor` is an external (or no-op) integration that handles
the payment-initiation half of the billing flow. The default in v1 is
`OfflineProcessor`, which is a no-op — invoices are paid via bank transfer
or mobile money outside the platform and the resulting `Payment` row is
created by a human operator through the maker-checker flow.

`flutterwave.py`, `stripe.py`, `momo.py` are import-only stubs in v1.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal  # noqa: TC003
from uuid import UUID  # noqa: TC003


@dataclass(frozen=True)
class ProcessorResult:
    """Outcome of `PaymentProcessor.initiate()`.

    status:
        - "pending"   — call accepted; payment outcome will be determined later
                        (e.g., human confirmation, async webhook).
        - "succeeded" — synchronous success (rare; reserved for direct-debit-style
                        processors that confirm in one round trip).
        - "failed"    — processor rejected the request synchronously.
    external_id:
        Provider-side identifier, if any. None for offline.
    message:
        Human-readable detail (logged, surfaced in UI).
    """

    status: str
    external_id: str | None
    message: str

    def __post_init__(self) -> None:
        if self.status not in {"pending", "succeeded", "failed"}:
            raise ValueError(f"invalid ProcessorResult.status: {self.status!r}")


class PaymentProcessor(ABC):
    """Minimal v1 interface.

    Real processors will add `verify_payment`, `handle_webhook`, `refund` as
    they are needed. YAGNI applies — do not add methods speculatively.
    """

    @property
    @abstractmethod
    def code(self) -> str:
        """Short stable identifier: 'offline', 'flutterwave', 'stripe', 'momo'."""

    @abstractmethod
    async def initiate(
        self,
        *,
        invoice_id: UUID,
        amount: Decimal,
        payment_method: str,
        external_reference: str | None,
    ) -> ProcessorResult:
        """Begin a payment for `invoice_id`. Does NOT write to the DB.

        Args:
            invoice_id: the invoice being paid (already exists).
            amount: payment amount (must be > 0; processor implementations
                    may further restrict).
            payment_method: matches `payments.payment_method` CHECK
                            ('bank_transfer'|'mobile_money'|'cash'|'cheque').
            external_reference: optional caller-supplied reference (bank txn id,
                                MoMo reference, cheque number).
        """
```

- [ ] **Step 2: Write the contract test in `tests/platform_/billing/test_processors.py`**

```python
"""Tests for the PaymentProcessor abstraction and concrete implementations."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.platform_.billing.processors.base import PaymentProcessor, ProcessorResult


def test_processor_is_abstract() -> None:
    with pytest.raises(TypeError):
        PaymentProcessor()  # type: ignore[abstract]


def test_processor_result_validates_status() -> None:
    ProcessorResult(status="pending", external_id=None, message="ok")
    ProcessorResult(status="succeeded", external_id="x", message="ok")
    ProcessorResult(status="failed", external_id=None, message="declined")
    with pytest.raises(ValueError, match="invalid ProcessorResult.status"):
        ProcessorResult(status="bogus", external_id=None, message="")


def test_processor_result_is_frozen() -> None:
    r = ProcessorResult(status="pending", external_id=None, message="x")
    with pytest.raises(Exception):
        r.status = "succeeded"  # type: ignore[misc]
```

- [ ] **Step 3: Run the tests**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_processors.py -v 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 4: mypy + ruff**

```bash
env -u DATABASE_URL python -m mypy app/platform_/billing/processors/base.py
ruff check app/platform_/billing/processors/ tests/platform_/billing/test_processors.py
```

Both must be clean.

- [ ] **Step 5: Commit**

```bash
git add app/platform_/billing/processors/base.py tests/platform_/billing/test_processors.py
git commit -m "feat(billing): PaymentProcessor ABC + ProcessorResult"
```

---

## Task 2: OfflineProcessor + stub processors

**Files:**
- Create: `app/platform_/billing/processors/offline.py`
- Create: `app/platform_/billing/processors/flutterwave.py`
- Create: `app/platform_/billing/processors/stripe.py`
- Create: `app/platform_/billing/processors/momo.py`
- Modify: `app/platform_/billing/processors/__init__.py`
- Modify: `tests/platform_/billing/test_processors.py`

- [ ] **Step 1: Write `app/platform_/billing/processors/offline.py`**

```python
"""OfflineProcessor — the v1 default.

Payments are recorded by a human operator after confirming receipt via
bank statement, mobile-money dashboard, etc. `initiate()` is a no-op
that immediately returns a pending result; the actual `Payment` row is
created by the maker via `PaymentService.record()` (SP03) and confirmed
by the checker via the maker-checker flow (SP04).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.platform_.billing.processors.base import PaymentProcessor, ProcessorResult


class OfflineProcessor(PaymentProcessor):
    @property
    def code(self) -> str:
        return "offline"

    async def initiate(
        self,
        *,
        invoice_id: UUID,
        amount: Decimal,
        payment_method: str,
        external_reference: str | None,
    ) -> ProcessorResult:
        if amount <= Decimal("0"):
            return ProcessorResult(
                status="failed",
                external_id=None,
                message="amount must be greater than 0",
            )
        return ProcessorResult(
            status="pending",
            external_id=None,
            message="awaiting human confirmation",
        )
```

- [ ] **Step 2: Write stub processors**

Create `app/platform_/billing/processors/flutterwave.py`:

```python
"""Flutterwave processor — stub.

Not implemented in v1. The class exists so the import graph and the
`PaymentProcessor` registry shape are pinned for future work.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.platform_.billing.processors.base import PaymentProcessor, ProcessorResult


class FlutterwaveProcessor(PaymentProcessor):
    def __init__(self) -> None:
        raise NotImplementedError(
            "FlutterwaveProcessor is a v1 stub; integration is post-launch"
        )

    @property
    def code(self) -> str:
        return "flutterwave"

    async def initiate(
        self,
        *,
        invoice_id: UUID,
        amount: Decimal,
        payment_method: str,
        external_reference: str | None,
    ) -> ProcessorResult:
        raise NotImplementedError
```

Create `app/platform_/billing/processors/stripe.py` (identical structure, class name `StripeProcessor`, code `"stripe"`, error message says "StripeProcessor").

Create `app/platform_/billing/processors/momo.py` (identical structure, class name `MobileMoneyProcessor`, code `"momo"`, error message says "MobileMoneyProcessor").

- [ ] **Step 3: Update `app/platform_/billing/processors/__init__.py`**

```python
"""Billing payment-processor package.

Re-exports the public surface. Stubs (Flutterwave/Stripe/MoMo) are
intentionally NOT re-exported — code paths that need them import them
directly from their module so the import error surface is small.
"""
from app.platform_.billing.processors.base import PaymentProcessor, ProcessorResult
from app.platform_.billing.processors.offline import OfflineProcessor

__all__ = ["OfflineProcessor", "PaymentProcessor", "ProcessorResult"]
```

- [ ] **Step 4: Extend `tests/platform_/billing/test_processors.py` with these tests**

```python
import pytest

from app.platform_.billing.processors.flutterwave import FlutterwaveProcessor
from app.platform_.billing.processors.momo import MobileMoneyProcessor
from app.platform_.billing.processors.offline import OfflineProcessor
from app.platform_.billing.processors.stripe import StripeProcessor


def test_offline_processor_code() -> None:
    assert OfflineProcessor().code == "offline"


@pytest.mark.anyio
async def test_offline_initiate_returns_pending() -> None:
    p = OfflineProcessor()
    result = await p.initiate(
        invoice_id=uuid.uuid4(),
        amount=Decimal("50000"),
        payment_method="bank_transfer",
        external_reference="TXN-001",
    )
    assert result.status == "pending"
    assert result.external_id is None
    assert "awaiting" in result.message.lower()


@pytest.mark.anyio
async def test_offline_initiate_rejects_zero_amount() -> None:
    p = OfflineProcessor()
    result = await p.initiate(
        invoice_id=uuid.uuid4(),
        amount=Decimal("0"),
        payment_method="cash",
        external_reference=None,
    )
    assert result.status == "failed"
    assert "amount" in result.message.lower()


@pytest.mark.anyio
async def test_offline_initiate_rejects_negative_amount() -> None:
    p = OfflineProcessor()
    result = await p.initiate(
        invoice_id=uuid.uuid4(),
        amount=Decimal("-1"),
        payment_method="cash",
        external_reference=None,
    )
    assert result.status == "failed"


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        (FlutterwaveProcessor, "flutterwave"),
        (StripeProcessor, "stripe"),
        (MobileMoneyProcessor, "momo"),
    ],
)
def test_stub_processors_raise_on_instantiation(cls, code) -> None:
    with pytest.raises(NotImplementedError, match=cls.__name__):
        cls()
```

(Make sure `uuid` and `Decimal` are imported at the top of the file if they aren't already from Task 1's tests.)

- [ ] **Step 5: Run tests, mypy, ruff**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_processors.py -v 2>&1 | tail -20
env -u DATABASE_URL python -m mypy app/platform_/billing/processors/
ruff check app/platform_/billing/processors/ tests/platform_/billing/test_processors.py
```

Expected: all tests pass; mypy/ruff clean.

- [ ] **Step 6: Commit**

```bash
git add app/platform_/billing/processors/ tests/platform_/billing/test_processors.py
git commit -m "feat(billing): OfflineProcessor (default) + stubs for Flutterwave/Stripe/MoMo"
```

---

## Task 3: SubscriptionService.assign()

**Files:**
- Create: `app/platform_/billing/exceptions.py`
- Create: `app/platform_/billing/services/subscription_service.py`
- Modify: `app/platform_/billing/services/__init__.py`
- Create: `tests/platform_/billing/test_subscription_service_assign.py`

- [ ] **Step 1: Write `app/platform_/billing/exceptions.py`**

```python
"""Domain exceptions for the billing module.

Service callers catch these instead of relying on DB error strings.
"""
from __future__ import annotations


class BillingError(Exception):
    """Base class for all billing-module domain errors."""


class SubscriptionConflict(BillingError):
    """Raised when a tenant already has a live subscription and we tried
    to create another one."""


class PlanInactive(BillingError):
    """Raised when the requested plan is_active=False at assign() time."""


class InvalidTransition(BillingError):
    """Raised when a state transition is requested from a status it isn't
    allowed from."""

    def __init__(self, *, from_status: str, to_status: str) -> None:
        super().__init__(f"cannot transition from {from_status!r} to {to_status!r}")
        self.from_status = from_status
        self.to_status = to_status
```

- [ ] **Step 2: Write `app/platform_/billing/services/subscription_service.py` (skeleton + assign)**

```python
"""SubscriptionService — owns the subscription state machine.

State machine:
    pending (tenant default) ──assign──> trialing OR active
    trialing ──(period ends)──> active (via beat or explicit transition)
    active ──transition_to_past_due──> past_due
    past_due ──transition_to_suspended──> suspended
    past_due ──reactivate──> active
    suspended ──reactivate──> active
    any ──cancel──> cancelled

Every transition writes BOTH platform.subscriptions.status AND the
denormalised platform.tenants.subscription_status in the same flush.
The middleware in SP04 reads tenants.subscription_status on every
request, so drift breaks access control.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Final

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.billing.exceptions import (
    PlanInactive,
    SubscriptionConflict,
)
from app.platform_.billing.models import Subscription, SubscriptionPlan
from app.platform_.models import Tenant

_log = structlog.get_logger(__name__)

# Fixed-day approximations used by `assign()` for the initial period end.
# The nightly invoice-generation job (SP06) uses `relativedelta` for
# calendar-month accuracy and reconciles via current_period_start/end.
_BILLING_PERIOD_DAYS: Final[dict[str, int]] = {
    "monthly": 30,
    "quarterly": 90,
    "annual": 365,
}

# Set of statuses that count as "live" — must match the SQL partial unique
# index `uq_subscriptions_live_tenant`.
_LIVE_STATUSES: Final[frozenset[str]] = frozenset(
    {"trialing", "active", "past_due"}
)


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── Queries ────────────────────────────────────────────────────────────

    async def get(self, subscription_id: uuid.UUID) -> Subscription | None:
        return await self._s.scalar(
            select(Subscription).where(Subscription.id == subscription_id)
        )

    async def get_live_for_tenant(self, tenant_id: uuid.UUID) -> Subscription | None:
        """Return the tenant's current live subscription, if any."""
        return await self._s.scalar(
            select(Subscription).where(
                Subscription.tenant_id == tenant_id,
                Subscription.status.in_(_LIVE_STATUSES),
            )
        )

    # ── Commands ───────────────────────────────────────────────────────────

    async def assign(
        self,
        *,
        tenant_id: uuid.UUID,
        plan_id: uuid.UUID,
        start_date: date | None = None,
    ) -> Subscription:
        """Assign `plan_id` to `tenant_id`.

        Raises:
            ValueError: tenant or plan does not exist.
            PlanInactive: plan.is_active is False.
            SubscriptionConflict: tenant already has a live subscription.
        """
        tenant = await self._s.scalar(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found")

        plan = await self._s.scalar(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        )
        if plan is None:
            raise ValueError(f"SubscriptionPlan {plan_id} not found")
        if not plan.is_active:
            raise PlanInactive(f"Plan {plan.code!r} is not active")

        existing = await self.get_live_for_tenant(tenant_id)
        if existing is not None:
            raise SubscriptionConflict(
                f"Tenant {tenant_id} already has a live subscription "
                f"({existing.id}, status={existing.status!r})"
            )

        period_start = start_date or date.today()
        if plan.trial_period_days > 0:
            initial_status = "trialing"
            period_end = period_start + timedelta(days=plan.trial_period_days)
        else:
            initial_status = "active"
            period_end = period_start + timedelta(
                days=_BILLING_PERIOD_DAYS[plan.billing_period]
            )

        sub = Subscription(
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=initial_status,
            started_at=datetime.now(UTC),
            current_period_start=period_start,
            current_period_end=period_end,
            next_billing_date=period_end,
        )
        self._s.add(sub)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            # Race: another caller inserted a live subscription between
            # the get_live_for_tenant() check and this flush. Translate
            # to the domain exception.
            await self._s.rollback()
            raise SubscriptionConflict(
                f"Tenant {tenant_id} already has a live subscription (race)"
            ) from exc

        tenant.subscription_status = initial_status
        tenant.current_subscription_id = sub.id
        await self._s.flush()

        _log.info(
            "subscription.assigned",
            subscription_id=str(sub.id),
            tenant_id=str(tenant_id),
            plan_id=str(plan_id),
            initial_status=initial_status,
        )
        return sub
```

- [ ] **Step 3: Update `app/platform_/billing/services/__init__.py`**

```python
from app.platform_.billing.services.subscription_service import SubscriptionService

__all__ = ["SubscriptionService"]
```

- [ ] **Step 4: Write `tests/platform_/billing/test_subscription_service_assign.py`**

```python
"""SubscriptionService.assign() tests.

Uses the async_sessionmaker + commit pattern (not the platform_session
fixture) because AuditableMixin's after_insert hook conflicts with the
connection-bound rollback fixture. See SP01 test docstring for context.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.exceptions import (
    PlanInactive,
    SubscriptionConflict,
)
from app.platform_.billing.models import Subscription, SubscriptionPlan
from app.platform_.billing.services import SubscriptionService
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(factory: async_sessionmaker[AsyncSession]) -> Tenant:
    async with factory() as s:
        await _set_platform(s)
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Test Tenant",
            is_active=True,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t


async def _make_plan(
    factory: async_sessionmaker[AsyncSession],
    *,
    trial_period_days: int = 0,
    billing_period: str = "monthly",
    is_active: bool = True,
) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            billing_period=billing_period,
            trial_period_days=trial_period_days,
            is_active=is_active,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s:
        await _set_platform(s)
        # Null the tenant FK first so we can delete subscriptions
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
async def factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_assign_active_for_no_trial_plan(factory) -> None:
    plan = await _make_plan(factory, trial_period_days=0, billing_period="monthly")
    tenant = await _make_tenant(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
            await s.commit()

            assert sub.status == "active"
            assert sub.current_period_end == sub.current_period_start + timedelta(days=30)

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Tenant, tenant.id)
            assert refreshed is not None
            assert refreshed.subscription_status == "active"
            assert refreshed.current_subscription_id == sub.id
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_trialing_when_plan_has_trial(factory) -> None:
    plan = await _make_plan(factory, trial_period_days=14)
    tenant = await _make_tenant(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
            await s.commit()
            assert sub.status == "trialing"
            assert sub.current_period_end == sub.current_period_start + timedelta(days=14)

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "trialing"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_uses_start_date_override(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    custom_start = date(2027, 1, 15)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.assign(
                tenant_id=tenant.id, plan_id=plan.id, start_date=custom_start
            )
            await s.commit()
            assert sub.current_period_start == custom_start
            assert sub.current_period_end == custom_start + timedelta(days=30)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_rejects_unknown_tenant(factory) -> None:
    plan = await _make_plan(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(ValueError, match="Tenant"):
                await svc.assign(tenant_id=uuid.uuid4(), plan_id=plan.id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_rejects_unknown_plan(factory) -> None:
    tenant = await _make_tenant(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(ValueError, match="SubscriptionPlan"):
                await svc.assign(tenant_id=tenant.id, plan_id=uuid.uuid4())
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_rejects_inactive_plan(factory) -> None:
    plan = await _make_plan(factory, is_active=False)
    tenant = await _make_tenant(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(PlanInactive, match="not active"):
                await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_raises_conflict_on_existing_live_sub(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(SubscriptionConflict):
                await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
    finally:
        await _cleanup(factory)
```

- [ ] **Step 5: Run the tests**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_subscription_service_assign.py -v 2>&1 | tail -20
```

Expected: 7 passed.

- [ ] **Step 6: mypy + ruff**

```bash
env -u DATABASE_URL python -m mypy app/platform_/billing/exceptions.py app/platform_/billing/services/subscription_service.py
ruff check app/platform_/billing/ tests/platform_/billing/test_subscription_service_assign.py
```

Both must be clean.

- [ ] **Step 7: Commit**

```bash
git add app/platform_/billing/exceptions.py app/platform_/billing/services/ \
        tests/platform_/billing/test_subscription_service_assign.py
git commit -m "feat(billing): SubscriptionService.assign() — initial state + tenant denormalisation"
```

---

## Task 4: SubscriptionService.cancel() and reactivate()

**Files:**
- Modify: `app/platform_/billing/services/subscription_service.py`
- Create: `tests/platform_/billing/test_subscription_service_cancel.py`

- [ ] **Step 1: Add `cancel()` and `reactivate()` methods**

Append to `app/platform_/billing/services/subscription_service.py` (inside the `SubscriptionService` class, after `assign`):

```python
    async def cancel(
        self,
        *,
        subscription_id: uuid.UUID,
        reason: str,
        cancel_at_period_end: bool = True,
    ) -> Subscription:
        """Cancel a subscription.

        cancel_at_period_end=True (default):
            Sets cancelled_at + cancellation_reason but leaves status as-is.
            The beat job at period end transitions to 'cancelled'.
            tenant.subscription_status is NOT changed.

        cancel_at_period_end=False:
            Immediately transitions to 'cancelled' and updates
            tenants.subscription_status. Hard cancel.

        Raises:
            ValueError: subscription not found.
            InvalidTransition: subscription is already cancelled.
        """
        sub = await self.get(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription {subscription_id} not found")
        if sub.status == "cancelled":
            raise InvalidTransition(from_status=sub.status, to_status="cancelled")

        now = datetime.now(UTC)
        sub.cancelled_at = now
        sub.cancellation_reason = reason

        if not cancel_at_period_end:
            old_status = sub.status
            sub.status = "cancelled"
            await self._sync_tenant_status(sub.tenant_id, "cancelled", sub.id)
            _log.info(
                "subscription.cancelled_immediately",
                subscription_id=str(sub.id),
                tenant_id=str(sub.tenant_id),
                from_status=old_status,
                reason=reason,
            )
        else:
            _log.info(
                "subscription.cancel_scheduled",
                subscription_id=str(sub.id),
                tenant_id=str(sub.tenant_id),
                current_status=sub.status,
                effective_at=sub.current_period_end.isoformat(),
                reason=reason,
            )

        await self._s.flush()
        return sub

    async def reactivate(self, *, subscription_id: uuid.UUID) -> Subscription:
        """Move past_due or suspended → active.

        Recomputes current_period_end from now() + plan period and clears
        grace_period_ends_at. Also updates tenant.subscription_status.

        Raises:
            ValueError: subscription or plan not found.
            InvalidTransition: subscription is not in {'past_due', 'suspended'}.
        """
        sub = await self.get(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription {subscription_id} not found")
        if sub.status not in {"past_due", "suspended"}:
            raise InvalidTransition(from_status=sub.status, to_status="active")

        plan = await self._s.scalar(
            select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
        )
        if plan is None:
            raise ValueError(f"SubscriptionPlan {sub.plan_id} not found")

        today = date.today()
        sub.status = "active"
        sub.current_period_start = today
        sub.current_period_end = today + timedelta(
            days=_BILLING_PERIOD_DAYS[plan.billing_period]
        )
        sub.next_billing_date = sub.current_period_end
        sub.grace_period_ends_at = None

        await self._sync_tenant_status(sub.tenant_id, "active", sub.id)
        await self._s.flush()

        _log.info(
            "subscription.reactivated",
            subscription_id=str(sub.id),
            tenant_id=str(sub.tenant_id),
        )
        return sub

    # ── Internals ──────────────────────────────────────────────────────────

    async def _sync_tenant_status(
        self,
        tenant_id: uuid.UUID,
        new_status: str,
        current_subscription_id: uuid.UUID,
    ) -> None:
        """Write the denormalised status onto the tenant row."""
        tenant = await self._s.scalar(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        if tenant is None:  # pragma: no cover — FK guarantees existence
            raise ValueError(f"Tenant {tenant_id} not found")
        tenant.subscription_status = new_status
        tenant.current_subscription_id = current_subscription_id
```

Add `InvalidTransition` to the existing import line:

```python
from app.platform_.billing.exceptions import (
    InvalidTransition,
    PlanInactive,
    SubscriptionConflict,
)
```

- [ ] **Step 2: Write the tests in `tests/platform_/billing/test_subscription_service_cancel.py`**

Reuse the same helper pattern from Task 3 (`_set_platform`, `_make_tenant`, `_make_plan`, `_cleanup`, `factory` fixture). Copy them — DRY across test modules is not worth the indirection.

```python
"""SubscriptionService.cancel() + reactivate() tests."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.exceptions import InvalidTransition
from app.platform_.billing.models import Subscription, SubscriptionPlan
from app.platform_.billing.services import SubscriptionService
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(factory) -> Tenant:
    async with factory() as s:
        await _set_platform(s)
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Test Tenant",
            is_active=True,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t


async def _make_plan(factory, *, trial_period_days: int = 0) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            trial_period_days=trial_period_days,
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


async def _assign(factory, plan, tenant) -> uuid.UUID:
    async with factory() as s:
        await _set_platform(s)
        svc = SubscriptionService(s)
        sub = await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        return sub.id


@pytest.mark.anyio
async def test_cancel_at_period_end_marks_but_keeps_status(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.cancel(
                subscription_id=sub_id,
                reason="not needed",
                cancel_at_period_end=True,
            )
            await s.commit()
            assert sub.status == "active"  # unchanged
            assert sub.cancelled_at is not None
            assert sub.cancellation_reason == "not needed"

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "active"  # unchanged
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancel_immediate_transitions_and_syncs_tenant(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.cancel(
                subscription_id=sub_id,
                reason="hard cancel",
                cancel_at_period_end=False,
            )
            await s.commit()
            assert sub.status == "cancelled"
            assert sub.cancelled_at is not None

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "cancelled"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancel_rejects_already_cancelled(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            await svc.cancel(
                subscription_id=sub_id, reason="x", cancel_at_period_end=False
            )
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(InvalidTransition):
                await svc.cancel(
                    subscription_id=sub_id,
                    reason="again",
                    cancel_at_period_end=False,
                )
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancel_rejects_unknown_subscription(factory) -> None:
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(ValueError, match="Subscription"):
                await svc.cancel(
                    subscription_id=uuid.uuid4(),
                    reason="x",
                )
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_reactivate_from_suspended_resets_period(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        # Force the subscription into 'suspended'
        async with factory() as s:
            await _set_platform(s)
            sub = await s.get(Subscription, sub_id)
            assert sub is not None
            sub.status = "suspended"
            sub.grace_period_ends_at = date.today() - timedelta(days=1)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            t.subscription_status = "suspended"
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.reactivate(subscription_id=sub_id)
            await s.commit()
            assert sub.status == "active"
            assert sub.grace_period_ends_at is None
            assert sub.current_period_end == date.today() + timedelta(days=30)

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "active"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_reactivate_rejects_from_active(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(InvalidTransition):
                await svc.reactivate(subscription_id=sub_id)
    finally:
        await _cleanup(factory)
```

- [ ] **Step 3: Run tests**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_subscription_service_cancel.py -v 2>&1 | tail -20
```

Expected: 6 passed.

- [ ] **Step 4: mypy + ruff**

```bash
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/
```

Both must be clean.

- [ ] **Step 5: Commit**

```bash
git add app/platform_/billing/services/subscription_service.py \
        tests/platform_/billing/test_subscription_service_cancel.py
git commit -m "feat(billing): SubscriptionService.cancel() + reactivate() with tenant sync"
```

---

## Task 5: Beat-callable transitions — past_due + suspended

**Files:**
- Modify: `app/platform_/billing/services/subscription_service.py`
- Create: `tests/platform_/billing/test_subscription_service_transitions.py`

- [ ] **Step 1: Add transition methods**

Append to `SubscriptionService`:

```python
    async def transition_to_past_due(
        self, *, subscription_id: uuid.UUID
    ) -> Subscription:
        """active|trialing → past_due. Called by the nightly beat job
        when current_period_end has passed without payment.

        Sets grace_period_ends_at = today + plan.grace_period_days. Also
        updates tenants.subscription_status.

        Raises:
            ValueError: subscription or plan not found.
            InvalidTransition: subscription not in {'active', 'trialing'}.
        """
        sub = await self.get(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription {subscription_id} not found")
        if sub.status not in {"active", "trialing"}:
            raise InvalidTransition(from_status=sub.status, to_status="past_due")

        plan = await self._s.scalar(
            select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
        )
        if plan is None:
            raise ValueError(f"SubscriptionPlan {sub.plan_id} not found")

        sub.status = "past_due"
        sub.grace_period_ends_at = date.today() + timedelta(days=plan.grace_period_days)
        await self._sync_tenant_status(sub.tenant_id, "past_due", sub.id)
        await self._s.flush()

        _log.info(
            "subscription.past_due",
            subscription_id=str(sub.id),
            tenant_id=str(sub.tenant_id),
            grace_period_ends_at=sub.grace_period_ends_at.isoformat(),
        )
        return sub

    async def transition_to_suspended(
        self, *, subscription_id: uuid.UUID
    ) -> Subscription:
        """past_due → suspended. Called by the nightly beat job when
        grace_period_ends_at has passed.

        Raises:
            ValueError: subscription not found.
            InvalidTransition: subscription is not 'past_due'.
        """
        sub = await self.get(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription {subscription_id} not found")
        if sub.status != "past_due":
            raise InvalidTransition(from_status=sub.status, to_status="suspended")

        sub.status = "suspended"
        await self._sync_tenant_status(sub.tenant_id, "suspended", sub.id)
        await self._s.flush()

        _log.info(
            "subscription.suspended",
            subscription_id=str(sub.id),
            tenant_id=str(sub.tenant_id),
        )
        return sub
```

- [ ] **Step 2: Write `tests/platform_/billing/test_subscription_service_transitions.py`**

Reuse the same helper pattern. Test coverage:
- `test_past_due_from_active_succeeds`
- `test_past_due_sets_grace_period_end_from_plan`
- `test_past_due_rejects_from_past_due` (idempotency)
- `test_past_due_syncs_tenant`
- `test_suspended_from_past_due_succeeds`
- `test_suspended_rejects_from_active`
- `test_suspended_syncs_tenant`

```python
"""SubscriptionService transition tests — past_due and suspended."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.exceptions import InvalidTransition
from app.platform_.billing.models import Subscription, SubscriptionPlan
from app.platform_.billing.services import SubscriptionService
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(factory) -> Tenant:
    async with factory() as s:
        await _set_platform(s)
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Test Tenant",
            is_active=True,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t


async def _make_plan(factory, *, grace_period_days: int = 30) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            grace_period_days=grace_period_days,
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


async def _assign(factory, plan, tenant) -> uuid.UUID:
    async with factory() as s:
        await _set_platform(s)
        svc = SubscriptionService(s)
        sub = await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        return sub.id


@pytest.mark.anyio
async def test_past_due_from_active_succeeds_and_sets_grace(factory) -> None:
    plan = await _make_plan(factory, grace_period_days=14)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.transition_to_past_due(subscription_id=sub_id)
            await s.commit()
            assert sub.status == "past_due"
            assert sub.grace_period_ends_at == date.today() + timedelta(days=14)

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "past_due"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_past_due_rejects_when_already_past_due(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            await svc.transition_to_past_due(subscription_id=sub_id)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(InvalidTransition):
                await svc.transition_to_past_due(subscription_id=sub_id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_suspended_from_past_due_succeeds(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            await svc.transition_to_past_due(subscription_id=sub_id)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.transition_to_suspended(subscription_id=sub_id)
            await s.commit()
            assert sub.status == "suspended"

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "suspended"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_suspended_rejects_from_active(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(InvalidTransition):
                await svc.transition_to_suspended(subscription_id=sub_id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_past_due_from_trialing_succeeds(factory) -> None:
    """Trialing subscriptions whose trial ends without conversion go past_due."""
    # Build a plan with a trial period
    async with factory() as s:
        await _set_platform(s)
        plan = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Trial Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            trial_period_days=7,
        )
        s.add(plan)
        await s.commit()
        await s.refresh(plan)

    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.transition_to_past_due(subscription_id=sub_id)
            await s.commit()
            assert sub.status == "past_due"
    finally:
        await _cleanup(factory)
```

- [ ] **Step 3: Run tests**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_subscription_service_transitions.py -v 2>&1 | tail -20
```

Expected: 5 passed.

- [ ] **Step 4: Full suite regression check**

```bash
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
```

Expected: 603 (from end of SP01) + 21 new (3 from Task 1, 7 from Task 2, 7 from Task 3 assign, 6 from Task 4 cancel, 5 from Task 5 transitions = 28 new). Adjust if numbers differ.

Actually: Task 1 added 3 tests, Task 2 added 7, Task 3 added 7, Task 4 added 6, Task 5 added 5 = **28 new tests, expected total ~631**.

- [ ] **Step 5: mypy + ruff**

```bash
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/
```

Both must be clean.

- [ ] **Step 6: Commit**

```bash
git add app/platform_/billing/services/subscription_service.py \
        tests/platform_/billing/test_subscription_service_transitions.py
git commit -m "feat(billing): SubscriptionService transitions — past_due + suspended for beat jobs"
```

---

## Task 6: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md` (append new section)

- [ ] **Step 1: Open `CLAUDE.md` and append this section after the Credit v1b contracts**

```markdown

## Billing module contracts (do not violate)

- All billing tables live in the `platform` schema. The tenant schema never
  sees billing state. The only tenant-schema impact is *behaviour* (the
  subscription gate middleware in `get_tenant_session` — SP04 — rejects
  requests against suspended/cancelled tenants).
- `platform.subscriptions.status` is the authoritative subscription state.
  `platform.tenants.subscription_status` is a **denormalised** copy read by
  the request-time middleware. Every `SubscriptionService` transition writes
  BOTH rows in the same DB transaction. No other code path may update either
  column directly. CI should enforce that no service or executor outside
  `app/platform_/billing/services/` mutates `subscriptions.status` or
  `tenants.subscription_status`.
- `SubscriptionService.assign()`, `cancel()`, `reactivate()`,
  `transition_to_past_due()`, `transition_to_suspended()` are the only
  permitted state-transition methods. Direct `UPDATE platform.subscriptions
  SET status = ...` is forbidden.
- Money is `Numeric(19, 4)`. UGX-only in v1; the `currency` columns exist
  for forward compatibility but no code may key off them yet.
- `PaymentProcessor` interface lives in `app/platform_/billing/processors/base.py`.
  `OfflineProcessor` is the only concrete implementation in v1.
  `FlutterwaveProcessor`, `StripeProcessor`, `MobileMoneyProcessor` are
  intentional stubs — instantiating them raises `NotImplementedError`. Do not
  remove them; the module graph is part of the contract.
- `OfflineProcessor.initiate()` is a pure function — it never writes to the
  database. All DB writes for a payment happen in `PaymentService` (SP03),
  invoked via the maker-checker executor in SP04.
- Plan term snapshotting is intentionally NOT implemented in v1. Subscriptions
  reference plans by FK. If plan pricing changes, historical subscriptions
  reflect the new pricing on read. CLAUDE.md rule 10 (snapshotting product
  terms) applies to loans/savings; billing plans are explicitly out of scope.
  Add snapshot columns to `subscriptions` if regulatory audit later requires it.
- Maker-checker for `billing.record_payment`, `billing.void_invoice`,
  `billing.cancel_subscription` is wired in SP04 via `@approval_executor`.
  Direct calls to `PaymentService.confirm` / `InvoiceService.void` /
  `SubscriptionService.cancel(cancel_at_period_end=False)` are only allowed
  from the maker-checker executor module, never from HTTP route handlers.
```

- [ ] **Step 2: Final regression check**

```bash
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
ruff check app/ tests/
env -u DATABASE_URL python -m mypy app/
```

All three must be clean.

- [ ] **Step 3: Commit and push**

```bash
git add CLAUDE.md
git commit -m "docs(claude-md): billing module contracts (SP02)"
git push origin feat/phase-1-billing
```

---

## Self-Review Checklist

- [x] No HTTP routes added (SP05's job)
- [x] No maker-checker executors added (SP04's job)
- [x] No invoice or payment service code added (SP03's job)
- [x] No beat jobs added (SP06's job)
- [x] Every state transition writes both `subscriptions.status` and `tenants.subscription_status` (via `_sync_tenant_status`)
- [x] `PaymentProcessor` ABC is minimal — only `code` property and `initiate` method
- [x] Stub processors raise `NotImplementedError` at instantiation, not at method call (caller gets the failure early)
- [x] `OfflineProcessor.initiate()` does not touch the DB
- [x] Domain exceptions (`SubscriptionConflict`, `PlanInactive`, `InvalidTransition`) defined in `exceptions.py`; callers don't depend on DB error strings
- [x] Tests use `async_sessionmaker + commit + _cleanup` pattern (consistent with SP01)
- [x] `_set_platform(s)` sets both `search_path` and `info["is_platform"]` (required for audit-log routing through AuditableMixin)
- [x] mypy strict + ruff clean across the new code
- [x] CLAUDE.md updated with module contracts
- [x] No new top-level dependencies introduced
