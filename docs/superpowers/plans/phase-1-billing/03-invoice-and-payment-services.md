# Phase 1 Sub-Plan 03: InvoiceService + PaymentService

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** All commits land on `feat/phase-1-billing`.

**Goal:** Land the two transactional billing services on top of the data layer (SP01) and `SubscriptionService` (SP02): invoice generation, voiding, overdue marking, and the maker-checker-friendly payment flow (record → confirm | reject). Plus migration 007 to add `payments.idempotency_key` (the carryover gap from SP01).

**Architecture:**

- `InvoiceService` owns invoice lifecycle: `generate_for_subscription`, `void`, `mark_overdue`, `mark_overdue_batch` (for SP06 beat). Invoice numbers are issued via per-year Postgres SEQUENCE (`platform.invoice_seq_YYYY`), formatted as `INV-YYYY-NNNNNN`.
- `PaymentService` owns the maker-checker-friendly flow: `record` creates a pending `Payment` row (maker), `confirm` flips it to confirmed and applies the amount to the invoice (checker), `reject` discards it. Idempotency is enforced by the new UNIQUE column.
- v1 invoice line generation: **base subscription line only** (`line_order=1`, description "Base subscription (<billing_period>)", amount = `plan.base_price`). Per-user / per-member lines are deferred — the v1 plans default both prices to 0 so the line would be a zero-amount row anyway. Documented in CLAUDE.md as out-of-scope.
- All amounts: `Numeric(19, 4)`. UGX-only. Same `_set_platform()` test pattern as SP01/SP02.
- **No HTTP, no maker-checker executor wrapping, no beat scheduling here.** SP04 wraps `record_payment` / `void_invoice` / `cancel_subscription` with `@approval_executor` and writes the executors. SP05 adds API. SP06 wires beat jobs to call `mark_overdue_batch` etc.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, structlog, pytest. mypy strict + ruff non-negotiable.

**Roadmap reference:** `docs/superpowers/plans/saas-launch-roadmap.md` §5 Phase 1.

**Prerequisite:** SP01 + SP02 merged onto `feat/phase-1-billing`.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `alembic/platform/versions/007_payments_idempotency_key.py` | Create | Adds `payments.idempotency_key TEXT NOT NULL UNIQUE` + invoice_seq_2026 sequence |
| `app/platform_/billing/models.py` | Modify | Add `idempotency_key: Mapped[str]` to `Payment` + unique constraint in `__table_args__` |
| `app/platform_/billing/services/invoice_service.py` | Create | InvoiceService (numbering + generate + void + mark_overdue + queries) |
| `app/platform_/billing/services/payment_service.py` | Create | PaymentService (record + confirm + reject) |
| `app/platform_/billing/services/__init__.py` | Modify | Re-export `InvoiceService`, `PaymentService` |
| `app/platform_/billing/exceptions.py` | Modify | Add `InvoiceConflict`, `PaymentConflict`, `OverpaymentRejected` |
| `tests/platform_/billing/test_invoice_service.py` | Create | 8 tests for generate / void / mark_overdue / numbering |
| `tests/platform_/billing/test_payment_service.py` | Create | 9 tests for record / confirm / reject / idempotency / partial-paid handling |
| `tests/platform_/billing/test_invoice_numbering.py` | Create | 3 tests for the per-year sequence behaviour |
| `CLAUDE.md` | Modify | Extend billing contracts section with invoice/payment rules |

---

## Architectural decisions locked here

1. **`payments.idempotency_key` is `TEXT NOT NULL UNIQUE` at the DB level.** The Pydantic schema's `PaymentRecordIn.idempotency_key` (min_length=8) is now backed by a real column. Migration 007 is its own revision (not 006a) — clean revision graph.
2. **Idempotency replays return the existing payment row, not raise.** A caller submitting the same idempotency_key gets HTTP-equivalent of 200/already-recorded instead of 409. The `record()` method does a pre-check by key; if found, returns the existing Payment. If two callers race past the pre-check, the UNIQUE constraint raises `IntegrityError` which is translated to a fetch-by-key + return.
3. **Invoice numbering: per-year Postgres SEQUENCE, format `INV-{YYYY}-{N:06d}`.** Numbers start at 1 each year. The sequence is created lazily via `CREATE SEQUENCE IF NOT EXISTS` inside the InvoiceService — no startup hook, no migration churn at year boundary. Migration 007 pre-creates the 2026 sequence so tests have something to read.
4. **`generate_for_subscription()` is allowed only for `trialing`, `active`, `past_due` subscriptions.** Cancelled / suspended subscriptions never get new invoices. The function is idempotent on `(subscription_id, billing_period_start)` — if an invoice already exists for that period, return it instead of creating a duplicate.
5. **v1 line items: one row per invoice — `description = "Base subscription (<billing_period>)"`, `quantity=1`, `unit_price = plan.base_price`, `amount = plan.base_price`, `line_order=1`.** No per-user / per-member math. Documented in CLAUDE.md.
6. **`void()` is only allowed for invoices with `amount_paid == 0`.** Voiding a partially-paid invoice would require reversing payments — out of scope for v1, raises `InvoiceConflict`. Voided invoices are not deleted; status=`void`, `voided_at`, `void_reason` set.
7. **`mark_overdue(invoice_id)` is callable on a single invoice; `mark_overdue_batch(as_of=today)` is the beat-facing helper.** Both only transition `issued` or `partial` invoices whose `due_at < as_of`. `draft`, `paid`, `void` invoices are silently skipped.
8. **`confirm()` applies the payment amount to `invoice.amount_paid` and transitions the invoice status:**
   - `amount_paid + new_amount > amount_total` → raise `OverpaymentRejected`
   - `amount_paid + new_amount == amount_total` → invoice.status='paid', invoice.paid_at=now
   - `0 < amount_paid + new_amount < amount_total` → invoice.status='partial'
9. **`reject()` is the inverse of confirm.** Payment.status='rejected', no invoice mutation. Audit log captures rejecter id + reason.
10. **Audit logging:** `Payment`, `Invoice`, `InvoiceLineItem` are intentionally NOT `AuditableMixin` (per SP01 design). Their state transitions are written to `audit_log` explicitly by the service methods via a small helper. The helper uses the same `connection.execute()` pattern that core/audit uses.

---

## Task 1: Alembic migration 007 + Payment model update

**Files:**
- Create: `alembic/platform/versions/007_payments_idempotency_key.py`
- Modify: `app/platform_/billing/models.py`

- [ ] **Step 1: Write the migration**

```python
"""Phase 1 Billing — payments.idempotency_key + invoice_seq_2026.

Revision: 007
Depends on: 006
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotency key for the payments table (SP01 carryover).
    # The table has no production rows yet, so NOT NULL is safe.
    op.add_column(
        "payments",
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        schema="platform",
    )
    op.create_unique_constraint(
        "uq_payments_idempotency_key",
        "payments",
        ["idempotency_key"],
        schema="platform",
    )

    # Invoice numbering sequence for the current year.
    # InvoiceService creates additional yearly sequences lazily.
    op.execute("CREATE SEQUENCE IF NOT EXISTS platform.invoice_seq_2026")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS platform.invoice_seq_2026")
    op.drop_constraint(
        "uq_payments_idempotency_key",
        "payments",
        type_="unique",
        schema="platform",
    )
    op.drop_column("payments", "idempotency_key", schema="platform")
```

- [ ] **Step 2: Smoke-check the migration parses**

```bash
python -c "import ast; ast.parse(open('alembic/platform/versions/007_payments_idempotency_key.py').read()); print('parsed OK')"
```

Expected: `parsed OK`.

- [ ] **Step 3: Update `app/platform_/billing/models.py` — the `Payment` class**

Find the `Payment` class. In its `__table_args__`, add a UniqueConstraint after the existing CheckConstraints:

```python
    __table_args__ = (
        CheckConstraint(
            "payment_method IN ('bank_transfer', 'mobile_money', 'cash', 'cheque')",
            name="ck_payments_payment_method",
        ),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')",
            name="ck_payments_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        Index("ix_payments_invoice", "invoice_id"),
        {"schema": "platform"},
    )
```

And add the column. Place it directly after the `notes` field:

```python
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        ...
```

- [ ] **Step 4: Run the migration smoke + model collection check**

```bash
env -u DATABASE_URL pytest tests/test_main.py tests/platform_/billing/test_models.py -q 2>&1 | tail -10
env -u DATABASE_URL python -m mypy app/platform_/billing/models.py
ruff check app/platform_/billing/models.py
```

Expected: all tests still pass, mypy/ruff clean.

If `test_payment_invalid_method_rejected` from SP01 now fails because the test fixture doesn't set `idempotency_key`, edit the test to add a unique idempotency_key:

```python
pmt = Payment(
    invoice_id=invoice.id,
    amount=Decimal("50000"),
    payment_method="paypal",
    recorded_by=seeded_platform_user.id,
    idempotency_key=f"idem-{uuid.uuid4().hex}",
)
```

(The CHECK violation should fire first; the idempotency_key just makes the row insertable up to that point.)

- [ ] **Step 5: Commit**

```bash
git add alembic/platform/versions/007_payments_idempotency_key.py app/platform_/billing/models.py tests/platform_/billing/test_models.py
git commit -m "feat(billing): migration 007 — payments.idempotency_key + invoice_seq_2026"
```

---

## Task 2: InvoiceService — numbering + generate_for_subscription

**Files:**
- Modify: `app/platform_/billing/exceptions.py`
- Create: `app/platform_/billing/services/invoice_service.py`
- Modify: `app/platform_/billing/services/__init__.py`
- Create: `tests/platform_/billing/test_invoice_numbering.py`

- [ ] **Step 1: Add new exception types to `app/platform_/billing/exceptions.py`**

Append after the existing exceptions:

```python
class InvoiceConflict(BillingError):
    """Raised when an invoice operation conflicts with current state
    (e.g., voiding a partially-paid invoice, or generating an invoice for
    a billing period that already has one).
    """


class PaymentConflict(BillingError):
    """Raised when a payment operation conflicts with current state
    (e.g., confirming an already-confirmed payment).
    """


class OverpaymentRejected(BillingError):
    """Raised when a payment confirmation would push amount_paid past
    amount_total. Use partial-then-final flow instead.
    """
```

- [ ] **Step 2: Write `app/platform_/billing/services/invoice_service.py` (numbering + generate only — void/mark_overdue come in Task 3)**

```python
"""InvoiceService — invoice lifecycle.

Invoice numbering: per-year Postgres SEQUENCE named `invoice_seq_YYYY` in
the `platform` schema. Format: INV-YYYY-NNNNNN. Sequences are created
lazily via `CREATE SEQUENCE IF NOT EXISTS`.

v1 line items: one base-price line per invoice. Per-user/per-member
billing lines are out of scope.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final, cast

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.billing.exceptions import InvoiceConflict
from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Subscription,
    SubscriptionPlan,
)

_log = structlog.get_logger(__name__)

_GENERATABLE_STATUSES: Final[frozenset[str]] = frozenset(
    {"trialing", "active", "past_due"}
)

_BILLING_PERIOD_DAYS: Final[dict[str, int]] = {
    "monthly": 30,
    "quarterly": 90,
    "annual": 365,
}


class InvoiceService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── Numbering ──────────────────────────────────────────────────────────

    async def _next_invoice_number(self, *, today: date | None = None) -> str:
        """Allocate the next invoice number from this year's sequence.

        Creates the sequence lazily if it doesn't exist (e.g., first invoice
        of a new year). Two callers across a year boundary may both try to
        create — that's fine, CREATE SEQUENCE IF NOT EXISTS is idempotent.
        """
        d = today or date.today()
        seq_name = f"platform.invoice_seq_{d.year}"
        await self._s.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))
        n = await self._s.scalar(text(f"SELECT nextval('{seq_name}')"))
        if n is None:  # pragma: no cover — nextval cannot return null
            raise RuntimeError("nextval returned None")
        return f"INV-{d.year}-{int(n):06d}"

    # ── Queries ────────────────────────────────────────────────────────────

    async def get(self, invoice_id: uuid.UUID) -> Invoice | None:
        return cast(
            Invoice | None,
            await self._s.scalar(select(Invoice).where(Invoice.id == invoice_id)),
        )

    async def get_for_subscription_period(
        self,
        *,
        subscription_id: uuid.UUID,
        billing_period_start: date,
    ) -> Invoice | None:
        """Return the (one and only) invoice for this subscription/period,
        if it exists. Used by `generate_for_subscription` for idempotency.
        """
        return cast(
            Invoice | None,
            await self._s.scalar(
                select(Invoice).where(
                    Invoice.subscription_id == subscription_id,
                    Invoice.billing_period_start == billing_period_start,
                )
            ),
        )

    # ── Commands ───────────────────────────────────────────────────────────

    async def generate_for_subscription(
        self,
        *,
        subscription_id: uuid.UUID,
        billing_period_start: date | None = None,
    ) -> Invoice:
        """Generate the issued invoice for the subscription's current period.

        If `billing_period_start` is omitted, defaults to
        `subscription.current_period_start`. If an invoice already exists for
        that subscription+period_start, return it (idempotent).

        Raises:
            ValueError: subscription or plan not found.
            InvoiceConflict: subscription is not in a generatable state
                            (cancelled, suspended).
        """
        sub = cast(
            Subscription | None,
            await self._s.scalar(
                select(Subscription).where(Subscription.id == subscription_id)
            ),
        )
        if sub is None:
            raise ValueError(f"Subscription {subscription_id} not found")
        if sub.status not in _GENERATABLE_STATUSES:
            raise InvoiceConflict(
                f"Cannot generate invoice for subscription in status {sub.status!r}"
            )

        plan = cast(
            SubscriptionPlan | None,
            await self._s.scalar(
                select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
            ),
        )
        if plan is None:
            raise ValueError(f"SubscriptionPlan {sub.plan_id} not found")

        period_start = billing_period_start or sub.current_period_start
        existing = await self.get_for_subscription_period(
            subscription_id=subscription_id,
            billing_period_start=period_start,
        )
        if existing is not None:
            return existing

        period_end = period_start + timedelta(
            days=_BILLING_PERIOD_DAYS[plan.billing_period]
        )
        # Standard net-7 due: due_at = period_start + 7 days.
        due_at = period_start + timedelta(days=7)
        now = datetime.now(UTC)

        invoice_number = await self._next_invoice_number()

        invoice = Invoice(
            invoice_number=invoice_number,
            subscription_id=subscription_id,
            tenant_id=sub.tenant_id,
            billing_period_start=period_start,
            billing_period_end=period_end,
            amount_subtotal=plan.base_price,
            amount_tax=Decimal("0"),
            amount_total=plan.base_price,
            amount_paid=Decimal("0"),
            currency=plan.currency,
            status="issued",
            issued_at=now,
            due_at=due_at,
        )
        self._s.add(invoice)
        await self._s.flush()

        line = InvoiceLineItem(
            invoice_id=invoice.id,
            description=f"Base subscription ({plan.billing_period})",
            quantity=1,
            unit_price=plan.base_price,
            amount=plan.base_price,
            line_order=1,
        )
        self._s.add(line)
        await self._s.flush()

        _log.info(
            "invoice.generated",
            invoice_id=str(invoice.id),
            invoice_number=invoice_number,
            subscription_id=str(sub.id),
            tenant_id=str(sub.tenant_id),
            amount_total=str(plan.base_price),
        )
        return invoice
```

- [ ] **Step 3: Update `app/platform_/billing/services/__init__.py`**

```python
from app.platform_.billing.services.invoice_service import InvoiceService
from app.platform_.billing.services.subscription_service import SubscriptionService

__all__ = ["InvoiceService", "SubscriptionService"]
```

- [ ] **Step 4: Write `tests/platform_/billing/test_invoice_numbering.py`**

Test the per-year sequence logic in isolation (without needing subscriptions/plans):

```python
"""InvoiceService numbering tests — the per-year sequence."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.services.invoice_service import InvoiceService


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_invoice_number_format(factory) -> None:
    """Format is INV-YYYY-NNNNNN with zero-padded 6-digit counter."""
    async with factory() as s:
        await _set_platform(s)
        svc = InvoiceService(s)
        n = await svc._next_invoice_number(today=date(2026, 6, 1))
        assert n.startswith("INV-2026-")
        suffix = n.split("-")[-1]
        assert len(suffix) == 6
        assert suffix.isdigit()
        await s.commit()


@pytest.mark.anyio
async def test_invoice_number_is_monotonic_within_year(factory) -> None:
    async with factory() as s:
        await _set_platform(s)
        svc = InvoiceService(s)
        a = await svc._next_invoice_number(today=date(2026, 6, 1))
        b = await svc._next_invoice_number(today=date(2026, 6, 1))
        c = await svc._next_invoice_number(today=date(2026, 12, 31))
        await s.commit()
        assert int(a.split("-")[-1]) < int(b.split("-")[-1])
        assert int(b.split("-")[-1]) < int(c.split("-")[-1])


@pytest.mark.anyio
async def test_invoice_number_creates_sequence_for_new_year(factory) -> None:
    """The first invoice of a new year creates its sequence on demand."""
    async with factory() as s:
        await _set_platform(s)
        # Drop any stray 2099 sequence from a prior test run
        await s.execute(text("DROP SEQUENCE IF EXISTS platform.invoice_seq_2099"))
        svc = InvoiceService(s)
        n = await svc._next_invoice_number(today=date(2099, 1, 1))
        assert n == "INV-2099-000001"
        # Cleanup
        await s.execute(text("DROP SEQUENCE platform.invoice_seq_2099"))
        await s.commit()
```

- [ ] **Step 5: Run the numbering tests**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_invoice_numbering.py -v 2>&1 | tail -15
```

Expected: 3 tests pass.

- [ ] **Step 6: Write `tests/platform_/billing/test_invoice_service.py` (generate cases only — void/mark_overdue come in Task 3)**

Use the same helper pattern as `test_subscription_service_assign.py`. Copy the helpers (`_set_platform`, `_make_tenant`, `_make_plan`, `_cleanup`, `factory`, `_assign`). Add a new helper `_assigned_subscription` that calls SubscriptionService.assign and returns the subscription id.

```python
"""InvoiceService.generate_for_subscription() tests."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.exceptions import InvoiceConflict
from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Payment,
    Subscription,
    SubscriptionPlan,
)
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
            name="Test Tenant",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t


async def _make_plan(factory, *, base_price: Decimal = Decimal("50000.0000")) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=base_price,
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


async def _assigned_subscription(factory, plan, tenant) -> uuid.UUID:
    async with factory() as s:
        await _set_platform(s)
        svc = SubscriptionService(s)
        sub = await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        return sub.id


@pytest.mark.anyio
async def test_generate_creates_issued_invoice_with_base_line(factory) -> None:
    plan = await _make_plan(factory, base_price=Decimal("60000"))
    tenant = await _make_tenant(factory)
    sub_id = await _assigned_subscription(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            inv = await svc.generate_for_subscription(subscription_id=sub_id)
            await s.commit()

            assert inv.status == "issued"
            assert inv.amount_subtotal == Decimal("60000")
            assert inv.amount_total == Decimal("60000")
            assert inv.amount_paid == Decimal("0")
            assert inv.due_at == inv.billing_period_start + timedelta(days=7)
            assert inv.invoice_number.startswith("INV-")

        async with factory() as s:
            await _set_platform(s)
            lines = list(
                (
                    await s.execute(
                        select(InvoiceLineItem).where(
                            InvoiceLineItem.invoice_id == inv.id
                        )
                    )
                ).scalars().all()
            )
            assert len(lines) == 1
            assert lines[0].description == "Base subscription (monthly)"
            assert lines[0].quantity == 1
            assert lines[0].unit_price == Decimal("60000")
            assert lines[0].line_order == 1
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_generate_is_idempotent_per_period(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assigned_subscription(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            a = await svc.generate_for_subscription(subscription_id=sub_id)
            await s.commit()
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            b = await svc.generate_for_subscription(subscription_id=sub_id)
            await s.commit()
        assert a.id == b.id  # idempotent
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_generate_rejects_cancelled_subscription(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assigned_subscription(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            sub = await s.get(Subscription, sub_id)
            assert sub is not None
            sub.status = "cancelled"
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            with pytest.raises(InvoiceConflict, match="cancelled"):
                await svc.generate_for_subscription(subscription_id=sub_id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_generate_rejects_unknown_subscription(factory) -> None:
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            with pytest.raises(ValueError, match="Subscription"):
                await svc.generate_for_subscription(subscription_id=uuid.uuid4())
    finally:
        await _cleanup(factory)
```

- [ ] **Step 7: Run all new tests**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_invoice_service.py tests/platform_/billing/test_invoice_numbering.py -v 2>&1 | tail -20
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/test_invoice_service.py tests/platform_/billing/test_invoice_numbering.py
```

Expected: 4 invoice tests + 3 numbering tests = 7 pass. mypy/ruff clean.

- [ ] **Step 8: Commit**

```bash
git add app/platform_/billing/exceptions.py app/platform_/billing/services/ \
        tests/platform_/billing/test_invoice_service.py \
        tests/platform_/billing/test_invoice_numbering.py
git commit -m "feat(billing): InvoiceService.generate_for_subscription() + per-year numbering"
```

---

## Task 3: InvoiceService — void + mark_overdue

**Files:**
- Modify: `app/platform_/billing/services/invoice_service.py`
- Modify: `tests/platform_/billing/test_invoice_service.py`

- [ ] **Step 1: Append methods to `InvoiceService`**

```python
    async def void(
        self,
        *,
        invoice_id: uuid.UUID,
        reason: str,
    ) -> Invoice:
        """Void an invoice that has not received any payment.

        Only invoices with amount_paid == 0 are voidable. Voiding a partial
        or paid invoice raises InvoiceConflict; the caller must reverse
        payments first (out of scope for v1).

        Raises:
            ValueError: invoice not found.
            InvoiceConflict: invoice already void, or has nonzero amount_paid.
        """
        invoice = await self.get(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        if invoice.status == "void":
            raise InvoiceConflict(f"Invoice {invoice_id} is already void")
        if invoice.amount_paid > Decimal("0"):
            raise InvoiceConflict(
                f"Invoice {invoice_id} has amount_paid={invoice.amount_paid}; "
                "reverse payments before voiding"
            )

        invoice.status = "void"
        invoice.voided_at = datetime.now(UTC)
        invoice.void_reason = reason
        await self._s.flush()

        _log.info(
            "invoice.voided",
            invoice_id=str(invoice.id),
            invoice_number=invoice.invoice_number,
            tenant_id=str(invoice.tenant_id),
            reason=reason,
        )
        return invoice

    async def mark_overdue(self, *, invoice_id: uuid.UUID) -> Invoice:
        """Mark a single invoice overdue. Silent no-op if invoice is not
        in {'issued', 'partial'} or if due_at has not passed.
        """
        invoice = await self.get(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        if invoice.status not in {"issued", "partial"}:
            return invoice
        if invoice.due_at >= date.today():
            return invoice

        invoice.status = "overdue"
        await self._s.flush()

        _log.info(
            "invoice.overdue",
            invoice_id=str(invoice.id),
            invoice_number=invoice.invoice_number,
            tenant_id=str(invoice.tenant_id),
            due_at=invoice.due_at.isoformat(),
        )
        return invoice

    async def mark_overdue_batch(self, *, as_of: date | None = None) -> int:
        """Mark all overdue invoices in one pass. Returns count transitioned.

        This is the beat-job-friendly bulk version. Uses a single UPDATE
        statement to keep the lock window small.
        """
        cutoff = as_of or date.today()
        result = await self._s.execute(
            text(
                "UPDATE platform.invoices "
                "SET status = 'overdue', updated_at = now() "
                "WHERE status IN ('issued', 'partial') "
                "AND due_at < :cutoff"
            ),
            {"cutoff": cutoff},
        )
        affected = result.rowcount or 0
        _log.info(
            "invoice.mark_overdue_batch",
            cutoff=cutoff.isoformat(),
            invoices_transitioned=affected,
        )
        return affected
```

- [ ] **Step 2: Append tests to `tests/platform_/billing/test_invoice_service.py`**

```python
@pytest.mark.anyio
async def test_void_unpaid_invoice_succeeds(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assigned_subscription(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            inv = await svc.generate_for_subscription(subscription_id=sub_id)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            voided = await svc.void(invoice_id=inv.id, reason="duplicate")
            await s.commit()
            assert voided.status == "void"
            assert voided.voided_at is not None
            assert voided.void_reason == "duplicate"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_void_rejects_partially_paid_invoice(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assigned_subscription(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            inv = await svc.generate_for_subscription(subscription_id=sub_id)
            inv.amount_paid = Decimal("100")
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            with pytest.raises(InvoiceConflict, match="amount_paid"):
                await svc.void(invoice_id=inv.id, reason="x")
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_mark_overdue_skips_recent_invoice(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assigned_subscription(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            inv = await svc.generate_for_subscription(subscription_id=sub_id)
            # due_at is today+7 by default
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            result = await svc.mark_overdue(invoice_id=inv.id)
            assert result.status == "issued"  # unchanged
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_mark_overdue_batch_transitions_only_eligible(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assigned_subscription(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            inv = await svc.generate_for_subscription(subscription_id=sub_id)
            # Force due_at into the past
            inv.due_at = date.today() - timedelta(days=1)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            n = await svc.mark_overdue_batch()
            await s.commit()
            assert n == 1

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Invoice, inv.id)
            assert refreshed is not None
            assert refreshed.status == "overdue"
    finally:
        await _cleanup(factory)
```

- [ ] **Step 3: Run tests, mypy, ruff**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_invoice_service.py -v 2>&1 | tail -15
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/
```

Expected: 8 tests pass (4 from Task 2 + 4 new). mypy/ruff clean.

- [ ] **Step 4: Commit**

```bash
git add app/platform_/billing/services/invoice_service.py tests/platform_/billing/test_invoice_service.py
git commit -m "feat(billing): InvoiceService.void() + mark_overdue() + mark_overdue_batch()"
```

---

## Task 4: PaymentService — record()

**Files:**
- Create: `app/platform_/billing/services/payment_service.py`
- Modify: `app/platform_/billing/services/__init__.py`
- Create: `tests/platform_/billing/test_payment_service.py`

- [ ] **Step 1: Write `app/platform_/billing/services/payment_service.py` (record only — confirm/reject in Task 5)**

```python
"""PaymentService — payment lifecycle.

State machine:
    record  → pending (maker action)
    confirm → confirmed (checker action; applies amount to invoice)
    reject  → rejected (checker action; no invoice change)

Idempotency: every record() takes an idempotency_key. Replays return
the existing payment row instead of raising. The DB has a UNIQUE
constraint on payments.idempotency_key as the ultimate guard.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.billing.models import Invoice, Payment

_log = structlog.get_logger(__name__)


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── Queries ────────────────────────────────────────────────────────────

    async def get(self, payment_id: uuid.UUID) -> Payment | None:
        return cast(
            Payment | None,
            await self._s.scalar(select(Payment).where(Payment.id == payment_id)),
        )

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        return cast(
            Payment | None,
            await self._s.scalar(
                select(Payment).where(Payment.idempotency_key == key)
            ),
        )

    # ── Commands ───────────────────────────────────────────────────────────

    async def record(
        self,
        *,
        invoice_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        payment_method: str,
        recorded_by: uuid.UUID,
        idempotency_key: str,
        external_reference: str | None = None,
        notes: str | None = None,
    ) -> Payment:
        """Create a pending payment record. Idempotent on idempotency_key.

        Raises:
            ValueError: invoice not found, or amount/currency mismatch.
        """
        # Idempotency: check before insert.
        existing = await self.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        invoice = cast(
            Invoice | None,
            await self._s.scalar(select(Invoice).where(Invoice.id == invoice_id)),
        )
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        if currency != invoice.currency:
            raise ValueError(
                f"Currency mismatch: payment {currency!r} vs invoice {invoice.currency!r}"
            )

        pmt = Payment(
            invoice_id=invoice_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            external_reference=external_reference,
            notes=notes,
            recorded_by=recorded_by,
            idempotency_key=idempotency_key,
            status="pending",
            recorded_at=datetime.now(UTC),
        )
        self._s.add(pmt)
        try:
            await self._s.flush()
        except IntegrityError:
            # Race: another caller inserted with the same idempotency_key
            # between our check and our flush. Return the existing row.
            await self._s.rollback()
            existing = await self.get_by_idempotency_key(idempotency_key)
            if existing is None:  # pragma: no cover — defensive
                raise
            return existing

        _log.info(
            "payment.recorded",
            payment_id=str(pmt.id),
            invoice_id=str(invoice_id),
            tenant_id=str(invoice.tenant_id),
            amount=str(amount),
            payment_method=payment_method,
            recorded_by=str(recorded_by),
        )
        return pmt
```

- [ ] **Step 2: Update `app/platform_/billing/services/__init__.py`**

```python
from app.platform_.billing.services.invoice_service import InvoiceService
from app.platform_.billing.services.payment_service import PaymentService
from app.platform_.billing.services.subscription_service import SubscriptionService

__all__ = ["InvoiceService", "PaymentService", "SubscriptionService"]
```

- [ ] **Step 3: Write `tests/platform_/billing/test_payment_service.py` (record cases only — confirm/reject in Task 5)**

Use the same helper pattern. Add `_make_platform_user` (from the SP01 test_models.py) and `_make_invoice` helpers.

```python
"""PaymentService tests."""
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
        u = PlatformUser(
            email=f"u-{uuid.uuid4().hex[:8]}@test.example",
            full_name="Test Operator",
            is_active=True,
            is_superuser=True,
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
                    currency="USD",  # invoice is UGX
                    payment_method="cash",
                    recorded_by=user.id,
                    idempotency_key="key-curr-001",
                )
    finally:
        await _cleanup(factory)
```

- [ ] **Step 4: Run tests, mypy, ruff**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_payment_service.py -v 2>&1 | tail -10
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/
```

Expected: 4 tests pass. mypy/ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/platform_/billing/services/payment_service.py app/platform_/billing/services/__init__.py \
        tests/platform_/billing/test_payment_service.py
git commit -m "feat(billing): PaymentService.record() with idempotency"
```

---

## Task 5: PaymentService — confirm() + reject()

**Files:**
- Modify: `app/platform_/billing/services/payment_service.py`
- Modify: `tests/platform_/billing/test_payment_service.py`

- [ ] **Step 1: Append methods to `PaymentService`**

```python
    async def confirm(
        self,
        *,
        payment_id: uuid.UUID,
        confirmed_by: uuid.UUID,
    ) -> Payment:
        """Confirm a pending payment. Applies amount to the parent invoice.

        Transitions:
            payment.status: pending → confirmed
            invoice.amount_paid: += payment.amount
            invoice.status:
                amount_paid == amount_total → 'paid' (paid_at set)
                0 < amount_paid < amount_total → 'partial'
                else → unchanged

        Raises:
            ValueError: payment not found.
            PaymentConflict: payment not pending, or self-approval attempt.
            OverpaymentRejected: confirmation would push amount_paid past total.
        """
        pmt = await self.get(payment_id)
        if pmt is None:
            raise ValueError(f"Payment {payment_id} not found")
        if pmt.status != "pending":
            raise PaymentConflict(
                f"Cannot confirm payment in status {pmt.status!r}"
            )
        if pmt.recorded_by == confirmed_by:
            raise PaymentConflict(
                "Maker cannot be checker (payment.recorded_by == confirmed_by)"
            )

        invoice = cast(
            Invoice | None,
            await self._s.scalar(
                select(Invoice).where(Invoice.id == pmt.invoice_id)
            ),
        )
        if invoice is None:  # pragma: no cover — FK guarantees existence
            raise ValueError(f"Invoice {pmt.invoice_id} not found")

        new_paid = invoice.amount_paid + pmt.amount
        if new_paid > invoice.amount_total:
            raise OverpaymentRejected(
                f"Confirming would make amount_paid={new_paid} > "
                f"amount_total={invoice.amount_total}"
            )

        now = datetime.now(UTC)
        pmt.status = "confirmed"
        pmt.confirmed_at = now
        invoice.amount_paid = new_paid
        if new_paid == invoice.amount_total:
            invoice.status = "paid"
            invoice.paid_at = now
        elif new_paid > Decimal("0"):
            invoice.status = "partial"
        await self._s.flush()

        _log.info(
            "payment.confirmed",
            payment_id=str(pmt.id),
            invoice_id=str(invoice.id),
            tenant_id=str(invoice.tenant_id),
            amount=str(pmt.amount),
            new_invoice_status=invoice.status,
            confirmed_by=str(confirmed_by),
        )
        return pmt

    async def reject(
        self,
        *,
        payment_id: uuid.UUID,
        rejected_by: uuid.UUID,
        reason: str,
    ) -> Payment:
        """Reject a pending payment. Invoice is not touched.

        Raises:
            ValueError: payment not found.
            PaymentConflict: payment not pending, or self-rejection attempt.
        """
        pmt = await self.get(payment_id)
        if pmt is None:
            raise ValueError(f"Payment {payment_id} not found")
        if pmt.status != "pending":
            raise PaymentConflict(
                f"Cannot reject payment in status {pmt.status!r}"
            )
        if pmt.recorded_by == rejected_by:
            raise PaymentConflict(
                "Maker cannot be checker (payment.recorded_by == rejected_by)"
            )

        pmt.status = "rejected"
        # Reason is captured in audit log, not in the Payment row.
        await self._s.flush()

        _log.info(
            "payment.rejected",
            payment_id=str(pmt.id),
            invoice_id=str(pmt.invoice_id),
            rejected_by=str(rejected_by),
            reason=reason,
        )
        return pmt
```

Add the new imports at the top:

```python
from app.platform_.billing.exceptions import (
    OverpaymentRejected,
    PaymentConflict,
)
```

- [ ] **Step 2: Append tests to `tests/platform_/billing/test_payment_service.py`**

Add `from app.platform_.billing.exceptions import OverpaymentRejected, PaymentConflict` at top.

```python
async def _make_two_users(factory) -> tuple[PlatformUser, PlatformUser]:
    return (
        await _make_platform_user(factory),
        await _make_platform_user(factory),
    )


@pytest.mark.anyio
async def test_confirm_full_payment_marks_invoice_paid(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    maker, checker = await _make_two_users(factory)
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
                recorded_by=maker.id,
                idempotency_key="key-cccc-001",
            )
            await s.commit()
            pmt_id = pmt.id

        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            confirmed = await svc.confirm(payment_id=pmt_id, confirmed_by=checker.id)
            await s.commit()
            assert confirmed.status == "confirmed"
            assert confirmed.confirmed_at is not None

        async with factory() as s:
            await _set_platform(s)
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            assert inv.status == "paid"
            assert inv.amount_paid == Decimal("50000")
            assert inv.paid_at is not None
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_confirm_partial_payment_marks_invoice_partial(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    maker, checker = await _make_two_users(factory)
    invoice_id = await _make_invoice(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            pmt = await svc.record(
                invoice_id=invoice_id,
                amount=Decimal("20000"),
                currency="UGX",
                payment_method="cash",
                recorded_by=maker.id,
                idempotency_key="key-dddd-001",
            )
            await s.commit()
            pmt_id = pmt.id

        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            await svc.confirm(payment_id=pmt_id, confirmed_by=checker.id)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            assert inv.status == "partial"
            assert inv.amount_paid == Decimal("20000")
            assert inv.paid_at is None
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_confirm_rejects_overpayment(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    maker, checker = await _make_two_users(factory)
    invoice_id = await _make_invoice(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            pmt = await svc.record(
                invoice_id=invoice_id,
                amount=Decimal("999999"),
                currency="UGX",
                payment_method="bank_transfer",
                recorded_by=maker.id,
                idempotency_key="key-eeee-001",
            )
            await s.commit()
            pmt_id = pmt.id

        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            with pytest.raises(OverpaymentRejected):
                await svc.confirm(payment_id=pmt_id, confirmed_by=checker.id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_confirm_rejects_self_approval(factory) -> None:
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
                idempotency_key="key-ffff-001",
            )
            await s.commit()
            pmt_id = pmt.id

        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            with pytest.raises(PaymentConflict, match="Maker cannot be checker"):
                await svc.confirm(payment_id=pmt_id, confirmed_by=maker.id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_reject_moves_to_rejected_without_touching_invoice(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    maker, checker = await _make_two_users(factory)
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
                idempotency_key="key-gggg-001",
            )
            await s.commit()
            pmt_id = pmt.id

        async with factory() as s:
            await _set_platform(s)
            svc = PaymentService(s)
            rejected = await svc.reject(
                payment_id=pmt_id, rejected_by=checker.id, reason="fake reference"
            )
            await s.commit()
            assert rejected.status == "rejected"

        async with factory() as s:
            await _set_platform(s)
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            assert inv.status == "issued"
            assert inv.amount_paid == Decimal("0")
    finally:
        await _cleanup(factory)
```

- [ ] **Step 3: Run all new tests + full suite regression**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_payment_service.py -v 2>&1 | tail -15
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/
```

Expected: 9 PaymentService tests pass total (4 record + 5 confirm/reject). Full suite ~654 (631 + 23 new from SP03).

- [ ] **Step 4: Commit**

```bash
git add app/platform_/billing/services/payment_service.py tests/platform_/billing/test_payment_service.py
git commit -m "feat(billing): PaymentService.confirm() + reject() with invoice state machine"
```

---

## Task 6: CLAUDE.md update + push

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Extend the existing "Billing module contracts" section**

Read the current "Billing module contracts" section in CLAUDE.md. Append these bullets (at the end of that section, before the next `##` heading):

```markdown
- Invoice numbers are issued via per-year Postgres SEQUENCE named
  `platform.invoice_seq_YYYY`. Format: `INV-YYYY-NNNNNN` (6-digit
  zero-padded). The InvoiceService creates new yearly sequences lazily
  via `CREATE SEQUENCE IF NOT EXISTS`; do not hand-roll numbers.
- `InvoiceService.generate_for_subscription()` is the only path to
  creating an Invoice row. Direct `Invoice(...)` instantiation outside
  the service is forbidden. The function is idempotent on
  `(subscription_id, billing_period_start)`.
- v1 invoice line generation is **base price only** — one
  `InvoiceLineItem` per invoice with `quantity=1`, `unit_price =
  plan.base_price`. Per-user and per-member billing lines are
  intentionally out of scope; they would be zero-amount rows anyway
  because all v1 plans default both prices to 0. Implementations may
  add multi-line generation when a real-world plan requires it.
- `InvoiceService.void()` only voids invoices with `amount_paid = 0`.
  Voiding a partial/paid invoice is forbidden in v1; the caller must
  reverse payments first (payment reversal is post-launch work).
- `PaymentService.record()` is the only path to creating a Payment row.
  The function is idempotent on `idempotency_key` (DB-enforced via
  `uq_payments_idempotency_key`). Callers must supply a key ≥ 8 chars
  long (validated by `PaymentRecordIn`).
- `PaymentService.confirm()` is the only path to flipping a pending
  Payment to `confirmed` and applying the amount to the parent invoice.
  Self-approval (maker == checker) is rejected at the service level.
- `PaymentService.reject()` is the only path to flipping pending →
  rejected. Rejection reason is captured in the audit log (SP04
  executors write the entry), not on the Payment row.
- Overpayment is rejected: `confirm()` raises `OverpaymentRejected`
  if `amount_paid + new_amount > amount_total`. Partial payments are
  supported; the invoice transitions to `partial` until cumulative
  payments equal the total.
```

- [ ] **Step 2: Final regression + lint**

```bash
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
ruff check app/ tests/
env -u DATABASE_URL python -m mypy app/
```

All three must be clean.

- [ ] **Step 3: Commit and push**

```bash
git add CLAUDE.md
git commit -m "docs(claude-md): billing module contracts — invoice + payment rules (SP03)"
git push origin feat/phase-1-billing
```

---

## Self-Review Checklist

- [x] Migration 007 adds idempotency_key with UNIQUE constraint + 2026 sequence; downgrade reverses both
- [x] Payment model gets idempotency_key column + unique constraint matching the DDL
- [x] InvoiceService.generate_for_subscription() is idempotent on (subscription_id, billing_period_start)
- [x] Generate rejects cancelled/suspended subscriptions
- [x] One base-price line per invoice — no per-user/per-member lines
- [x] Invoice number format INV-YYYY-NNNNNN via per-year sequence
- [x] void() rejects amount_paid > 0
- [x] mark_overdue() is a no-op for non-issued/partial invoices
- [x] mark_overdue_batch() returns transitioned count
- [x] PaymentService.record() is idempotent on idempotency_key with race-safe IntegrityError fallback
- [x] PaymentService.confirm() rejects self-approval (maker != checker)
- [x] PaymentService.confirm() applies full→paid, partial→partial state transitions on invoice
- [x] PaymentService.confirm() rejects overpayment with OverpaymentRejected
- [x] PaymentService.reject() does not touch invoice
- [x] All currency mismatches surface as ValueError, not silent acceptance
- [x] CLAUDE.md updated with invoice + payment contracts
- [x] No HTTP / executor / beat / audit-log code added (those are SP04/SP05/SP06)
- [x] No new top-level dependencies
- [x] mypy strict + ruff clean across all new code
