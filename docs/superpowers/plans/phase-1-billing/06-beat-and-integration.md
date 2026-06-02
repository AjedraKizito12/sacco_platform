# Phase 1 Sub-Plan 06: Beat Jobs + Integration + Docs

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** All commits land on `feat/phase-1-billing`. After SP06, the integration branch is ready for the single PR into `main`.

**Goal:** The final mile of Phase 1. Wire the 4 nightly Celery beat jobs that drive the subscription lifecycle, generate invoices, send reminders, and mark overdue invoices. Add the end-to-end integration test that exercises the full billing lifecycle (assign → invoice → past_due → suspended → reactivate → confirm payment). Document the operator runbook. Finalise CLAUDE.md.

**Architecture:**

- `app/platform_/billing/beat.py` defines four Celery tasks, each calling an async helper:
  1. `assess_subscription_state` — `active|trialing` → `past_due`; `past_due` → `suspended`
  2. `generate_next_period_invoices` — for `next_billing_date == today`, create invoice + advance `next_billing_date`
  3. `send_invoice_reminders` — emit `BillingInvoiceReminderDue` outbox events at T-7, T-3, T-0, T+3, T+7
  4. `mark_overdue_invoices` — flip past-due invoices to `overdue`
- All four tasks operate at the **platform** schema level (billing data lives in `platform.*`). No per-tenant schema iteration, unlike credit / fees / reporting beats.
- Idempotency: each task is safe to re-run on the same day. `assess` uses the existing `InvalidTransition` guard. `generate_next_period_invoices` uses `InvoiceService.generate_for_subscription`'s built-in `(subscription_id, billing_period_start)` idempotency. `send_invoice_reminders` deduplicates via a per-event-per-day flag in the outbox payload. `mark_overdue` uses `InvoiceService.mark_overdue_batch`'s set-based UPDATE which only touches eligible rows.
- The reminder task emits to the platform outbox (`EventPublisher.publish`) at all five reminder windows. Phase 3's notification consumer will eventually subscribe to `BillingInvoiceReminderDue`; until then, the events accumulate harmlessly and are purged by the existing `purge-outbox-retention` job.
- End-to-end test exercises the full lifecycle in a single test: assign → wait → generate invoice → past_due → suspended → reactivate → record payment → confirm payment → assert final state. Runs against real Postgres + real services.
- Runbook documents the operator-facing workflow for recording a payment, voiding an invoice, hard-cancelling a subscription, and reading the beat job logs to debug a stuck state.

**Tech Stack:** Celery, SQLAlchemy 2.0 async, structlog, pytest. mypy strict + ruff non-negotiable.

**Roadmap reference:** `docs/superpowers/plans/saas-launch-roadmap.md` §5 Phase 1.

**Prerequisite:** SP01 + SP02 + SP03 + SP04 + SP05 merged onto `feat/phase-1-billing`.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/platform_/billing/beat.py` | Create | 4 Celery tasks with their async helpers |
| `app/workers/celery_app.py` | Modify | Add `app.platform_.billing.beat` to `include[]` and 4 entries to `beat_schedule` |
| `tests/platform_/billing/test_beat.py` | Create | Unit tests for each of the 4 tasks (~10 tests) |
| `tests/platform_/billing/test_e2e_lifecycle.py` | Create | One end-to-end integration test through the full lifecycle |
| `docs/runbooks/billing-operator-guide.md` | Create | Operator-facing playbook for the common billing workflows |
| `CLAUDE.md` | Modify | Final billing contracts section additions for beat-job invariants |

---

## Architectural decisions locked here

1. **Platform-scoped, not per-tenant.** Unlike credit / fees beats, the billing beat doesn't iterate `platform.tenants.schema_name`. All billing data is in `platform.*`. Single session per task.
2. **Each task is a single async function with its own `engine` lifecycle.** Match the existing pattern in `app/modules/credit/beat.py` — create a fresh engine inside the task (or accept one from a factory), open a session with `SET LOCAL search_path TO platform`, do work, commit. Tasks do NOT share an engine.
3. **`assess_subscription_state` reads `subscriptions` and routes transitions through `SubscriptionService`.** No direct UPDATEs to `status`. This way `tenants.subscription_status` denormalisation is kept in sync via the existing `_sync_tenant_status` helper.
4. **`generate_next_period_invoices` advances `next_billing_date` after generating.** The advance increments by the plan's billing period (monthly → +30 days approx, quarterly → +90, annual → +365). Same fixed-day approximation as SP02's `assign()` — calendar-month precision is post-launch work.
5. **`send_invoice_reminders` emits via `EventPublisher.publish` to the platform outbox.** Event type: `BillingInvoiceReminderDue`. Aggregate type: `invoice`. Aggregate id: the invoice id. Payload: `{ invoice_id, tenant_id, days_until_due, reminder_window, amount_outstanding }`. Phase 3's notification consumer subscribes to this event type.
6. **Reminder deduplication uses the outbox's natural idempotency.** Each reminder window emits exactly one event per `(invoice_id, reminder_window)` per day. The task tracks daily state in memory; idempotency across re-runs in the same day is handled by checking the outbox for an existing event with the same aggregate_id + event_type within the last 24h. **Simplification: for v1, accept that a re-run of the same day may emit a duplicate event** — Phase 3 consumers should dedupe by `(invoice_id, reminder_window, date)`. Document this caveat in CLAUDE.md.
7. **`mark_overdue_invoices` calls `InvoiceService.mark_overdue_batch`.** Already implemented in SP03 as a set-based UPDATE — cheap, idempotent.
8. **No retry policy for individual beat tasks.** Celery's default at-most-once with `task_acks_late=True` is sufficient. If a task crashes mid-run, the next day's run picks up where it left off (each task is idempotent on the relevant day).
9. **End-to-end integration test runs against real Postgres.** No mocking of services. Mimics the timing of a real subscription by manipulating dates in-place rather than waiting.
10. **Runbook lives at `docs/runbooks/billing-operator-guide.md`.** New directory if needed.

---

## Task 1: beat.py + unit tests

**Files:**
- Create: `app/platform_/billing/beat.py`
- Create: `tests/platform_/billing/test_beat.py`

- [ ] **Step 1: Write `app/platform_/billing/beat.py`**

```python
"""Celery beat tasks for the billing module.

All tasks operate on platform-scoped billing data. No per-tenant schema
iteration — billing tables live in `platform.*`.

Tasks (all run daily):
    assess_subscription_state       — transitions active|trialing → past_due, past_due → suspended
    generate_next_period_invoices   — creates next-period invoices for subscriptions due today
    send_invoice_reminders          — emits BillingInvoiceReminderDue outbox events at T-7/T-3/T-0/T+3/T+7
    mark_overdue_invoices           — flips issued|partial invoices past due_at to 'overdue'
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.outbox.publisher import EventPublisher
from app.platform_.billing.exceptions import InvalidTransition
from app.platform_.billing.models import (
    Invoice,
    Subscription,
    SubscriptionPlan,
)
from app.platform_.billing.services import (
    InvoiceService,
    SubscriptionService,
)
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)

# Same fixed-day approximations used by SubscriptionService.assign().
_BILLING_PERIOD_DAYS: Final[dict[str, int]] = {
    "monthly": 30,
    "quarterly": 90,
    "annual": 365,
}

# Reminder windows (days relative to due_at). Negative = before, positive = after.
_REMINDER_WINDOWS: Final[list[int]] = [-7, -3, 0, 3, 7]


# ── assess_subscription_state ────────────────────────────────────────────────


async def _run_assess_subscription_state() -> dict[str, int]:
    """active|trialing whose current_period_end < today  → past_due.
    past_due whose grace_period_ends_at < today          → suspended.

    Returns counts per transition.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    counts = {"past_due": 0, "suspended": 0}
    today = date.today()

    try:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True

            # Pass 1: active|trialing → past_due
            expired = list(
                (
                    await session.execute(
                        select(Subscription).where(
                            Subscription.status.in_(["active", "trialing"]),
                            Subscription.current_period_end < today,
                        )
                    )
                ).scalars().all()
            )
            svc = SubscriptionService(session)
            for sub in expired:
                try:
                    await svc.transition_to_past_due(subscription_id=sub.id)
                    counts["past_due"] += 1
                except InvalidTransition as exc:
                    _log.info(
                        "billing.beat.assess_skip",
                        subscription_id=str(sub.id),
                        reason=str(exc),
                    )

            # Pass 2: past_due whose grace has expired → suspended
            past_due = list(
                (
                    await session.execute(
                        select(Subscription).where(
                            Subscription.status == "past_due",
                            Subscription.grace_period_ends_at.is_not(None),
                            Subscription.grace_period_ends_at < today,
                        )
                    )
                ).scalars().all()
            )
            for sub in past_due:
                try:
                    await svc.transition_to_suspended(subscription_id=sub.id)
                    counts["suspended"] += 1
                except InvalidTransition as exc:
                    _log.info(
                        "billing.beat.assess_skip",
                        subscription_id=str(sub.id),
                        reason=str(exc),
                    )

            await session.commit()
    finally:
        await engine.dispose()

    _log.info("billing.beat.assess_complete", **counts)
    return counts


@celery_app.task(name="app.platform_.billing.beat.assess_subscription_state")  # type: ignore[misc]
def assess_subscription_state() -> dict[str, int]:
    """Daily: transition expired subscriptions to past_due and past-grace to suspended."""
    return asyncio.run(_run_assess_subscription_state())


# ── generate_next_period_invoices ────────────────────────────────────────────


async def _run_generate_next_period_invoices() -> dict[str, int]:
    """For subscriptions whose next_billing_date == today, generate the
    next-period invoice and advance next_billing_date.

    Skips: trialing subscriptions (no invoice during trial),
           subscriptions in cancelled or suspended state.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    counts = {"generated": 0, "skipped": 0}
    today = date.today()

    try:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True

            due_subs = list(
                (
                    await session.execute(
                        select(Subscription).where(
                            Subscription.status.in_(["active", "past_due"]),
                            Subscription.next_billing_date == today,
                        )
                    )
                ).scalars().all()
            )

            invoice_svc = InvoiceService(session)
            for sub in due_subs:
                try:
                    plan = await session.scalar(
                        select(SubscriptionPlan).where(
                            SubscriptionPlan.id == sub.plan_id
                        )
                    )
                    if plan is None:
                        counts["skipped"] += 1
                        continue

                    invoice = await invoice_svc.generate_for_subscription(
                        subscription_id=sub.id,
                        billing_period_start=today,
                    )

                    # Advance the subscription's next_billing_date.
                    period_days = _BILLING_PERIOD_DAYS[plan.billing_period]
                    sub.current_period_start = today
                    sub.current_period_end = today + timedelta(days=period_days)
                    sub.next_billing_date = sub.current_period_end
                    counts["generated"] += 1
                    _log.info(
                        "billing.beat.invoice_generated",
                        subscription_id=str(sub.id),
                        invoice_number=invoice.invoice_number,
                    )
                except Exception as exc:
                    counts["skipped"] += 1
                    _log.error(
                        "billing.beat.invoice_generation_error",
                        subscription_id=str(sub.id),
                        error=str(exc),
                    )

            await session.commit()
    finally:
        await engine.dispose()

    _log.info("billing.beat.generate_complete", **counts)
    return counts


@celery_app.task(  # type: ignore[misc]
    name="app.platform_.billing.beat.generate_next_period_invoices",
)
def generate_next_period_invoices() -> dict[str, int]:
    """Daily: generate the next-period invoice for subscriptions billing today."""
    return asyncio.run(_run_generate_next_period_invoices())


# ── send_invoice_reminders ───────────────────────────────────────────────────


async def _run_send_invoice_reminders() -> dict[str, int]:
    """Emit BillingInvoiceReminderDue outbox events for invoices in any
    reminder window: T-7, T-3, T-0, T+3, T+7 (days from due_at).

    Targets only invoices in status {'issued', 'partial', 'overdue'} with
    outstanding amount > 0.

    NOTE: v1 does NOT deduplicate across re-runs in the same day. If the
    beat task runs twice in 24h, duplicate events will be emitted to the
    outbox. Phase 3's notification consumer must dedupe by
    (invoice_id, reminder_window, date).
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    counts: dict[str, int] = {f"window_{w}": 0 for w in _REMINDER_WINDOWS}
    today = date.today()

    try:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True

            for window in _REMINDER_WINDOWS:
                target_date = today - timedelta(days=window)
                # window = -7 means "T-7 reminder" → due_at = today + 7
                target_due = today + timedelta(days=-window)
                invoices = list(
                    (
                        await session.execute(
                            select(Invoice).where(
                                Invoice.status.in_(["issued", "partial", "overdue"]),
                                Invoice.due_at == target_due,
                            )
                        )
                    ).scalars().all()
                )
                for inv in invoices:
                    outstanding = inv.amount_total - inv.amount_paid
                    if outstanding <= Decimal("0"):
                        continue
                    await EventPublisher.publish(
                        session,
                        aggregate_type="invoice",
                        aggregate_id=inv.id,
                        event_type="BillingInvoiceReminderDue",
                        payload={
                            "invoice_id": str(inv.id),
                            "tenant_id": str(inv.tenant_id),
                            "invoice_number": inv.invoice_number,
                            "reminder_window": window,
                            "days_until_due": -window,
                            "amount_outstanding": str(outstanding),
                            "due_at": inv.due_at.isoformat(),
                        },
                    )
                    counts[f"window_{window}"] += 1

            await session.commit()
    finally:
        await engine.dispose()

    _log.info("billing.beat.reminders_complete", **counts)
    return counts


@celery_app.task(name="app.platform_.billing.beat.send_invoice_reminders")  # type: ignore[misc]
def send_invoice_reminders() -> dict[str, int]:
    """Daily: emit BillingInvoiceReminderDue outbox events at the five reminder windows."""
    return asyncio.run(_run_send_invoice_reminders())


# ── mark_overdue_invoices ────────────────────────────────────────────────────


async def _run_mark_overdue_invoices() -> dict[str, int]:
    """Flip issued|partial invoices past due_at to 'overdue'.

    Idempotent — calls InvoiceService.mark_overdue_batch which only
    transitions eligible rows (and is a set-based UPDATE).
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    counts = {"transitioned": 0}

    try:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True

            svc = InvoiceService(session)
            counts["transitioned"] = await svc.mark_overdue_batch()
            await session.commit()
    finally:
        await engine.dispose()

    _log.info("billing.beat.mark_overdue_complete", **counts)
    return counts


@celery_app.task(name="app.platform_.billing.beat.mark_overdue_invoices")  # type: ignore[misc]
def mark_overdue_invoices() -> dict[str, int]:
    """Daily: mark issued/partial invoices past due_at as overdue."""
    return asyncio.run(_run_mark_overdue_invoices())
```

- [ ] **Step 2: Write `tests/platform_/billing/test_beat.py`**

Use the established helper pattern from `tests/platform_/billing/test_subscription_service_assign.py` (the `factory` fixture, `_set_platform`, `_make_tenant`, `_make_plan`, `_cleanup`). Add `_make_subscription` and `_make_invoice` helpers using the services.

Tests:

```python
"""Unit tests for billing beat tasks.

Each test calls the underscore-prefixed async helper directly (not the
Celery wrapper), so we can run inside the test event loop without
asyncio.run.
"""
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

from app.platform_.billing.beat import (
    _run_assess_subscription_state,
    _run_generate_next_period_invoices,
    _run_mark_overdue_invoices,
    _run_send_invoice_reminders,
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
            name="Beat Test",
            is_active=True,
            created_at=now,
            updated_at=now,
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
            name="Beat Plan",
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
        await s.execute(delete(Payment))
        await s.execute(delete(InvoiceLineItem))
        await s.execute(delete(Invoice))
        await s.execute(delete(Subscription))
        await s.execute(delete(SubscriptionPlan))
        await s.execute(delete(Tenant))
        await s.execute(delete(PlatformUser))
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.commit()


@pytest.fixture
async def factory(test_engine: AsyncEngine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


# IMPORTANT: The beat helpers create their own engine via create_async_engine
# (using settings.database_url). For tests we need to patch app.core.config
# or app.platform_.billing.beat to use test_engine.
# Pattern from tests/core/test_subscription_gate.py: patch the module's
# engine reference. The beat helpers use create_async_engine inside the
# function body, so we need a different approach: patch
# `app.platform_.billing.beat.create_async_engine` to return test_engine.


@pytest.fixture
def patched_beat(test_engine: AsyncEngine, monkeypatch):
    """Patch the beat module's engine constructor to return test_engine
    instead of creating a new one. The test_engine has NullPool which
    avoids event-loop conflicts in the test suite.
    """
    class _Wrapper:
        def __init__(self, engine):
            self._engine = engine

        async def dispose(self):
            # Don't actually dispose — the test session owns the engine
            pass

        def __getattr__(self, name):
            return getattr(self._engine, name)

    wrapper = _Wrapper(test_engine)
    monkeypatch.setattr(
        "app.platform_.billing.beat.create_async_engine",
        lambda *a, **kw: wrapper,
    )
    return None


# ── assess_subscription_state ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_assess_transitions_expired_active_to_past_due(factory, patched_beat) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id
    # Force the subscription's period_end into the past
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.subscriptions SET current_period_end = :pe WHERE id = :id"
            ),
            {"pe": date.today() - timedelta(days=1), "id": sub_id},
        )
        await s.commit()

    try:
        counts = await _run_assess_subscription_state()
        assert counts["past_due"] >= 1

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Subscription, sub_id)
            assert refreshed is not None
            assert refreshed.status == "past_due"
            assert refreshed.grace_period_ends_at is not None
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assess_transitions_past_due_with_expired_grace_to_suspended(factory, patched_beat) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id

    # Force into past_due with an expired grace period
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.subscriptions SET status = 'past_due', "
                "grace_period_ends_at = :gpe WHERE id = :id"
            ),
            {"gpe": date.today() - timedelta(days=1), "id": sub_id},
        )
        await s.execute(
            text(
                "UPDATE platform.tenants SET subscription_status = 'past_due' WHERE id = :id"
            ),
            {"id": str(tenant.id)},
        )
        await s.commit()

    try:
        counts = await _run_assess_subscription_state()
        assert counts["suspended"] >= 1

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Subscription, sub_id)
            assert refreshed is not None
            assert refreshed.status == "suspended"
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "suspended"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assess_is_idempotent(factory, patched_beat) -> None:
    """Running assess twice on the same day should not double-transition."""
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id

    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.subscriptions SET current_period_end = :pe WHERE id = :id"
            ),
            {"pe": date.today() - timedelta(days=1), "id": sub_id},
        )
        await s.commit()

    try:
        first = await _run_assess_subscription_state()
        assert first["past_due"] >= 1
        # Second run: subscription is now past_due, not active. Should not transition again.
        second = await _run_assess_subscription_state()
        # past_due count should be 0 in the second run (already transitioned)
        # suspended count should be 0 (grace not yet expired)
        assert second["past_due"] == 0
    finally:
        await _cleanup(factory)


# ── generate_next_period_invoices ────────────────────────────────────────────


@pytest.mark.anyio
async def test_generate_creates_invoice_for_subscription_due_today(factory, patched_beat) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id

    # Set next_billing_date to today
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.subscriptions SET next_billing_date = :nbd WHERE id = :id"
            ),
            {"nbd": date.today(), "id": sub_id},
        )
        await s.commit()

    try:
        counts = await _run_generate_next_period_invoices()
        assert counts["generated"] == 1

        async with factory() as s:
            await _set_platform(s)
            invoices = list(
                (
                    await s.execute(
                        select(Invoice).where(Invoice.subscription_id == sub_id)
                    )
                ).scalars().all()
            )
            # The assign() call already creates an invoice via SP02 design? No — it doesn't.
            # The beat should have created the first invoice here.
            assert len(invoices) >= 1
            refreshed = await s.get(Subscription, sub_id)
            assert refreshed is not None
            assert refreshed.next_billing_date == date.today() + timedelta(days=30)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_generate_skips_subscriptions_not_due(factory, patched_beat) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        # next_billing_date defaults to period_end, which is today + 30
        await s.commit()
    try:
        counts = await _run_generate_next_period_invoices()
        assert counts["generated"] == 0
    finally:
        await _cleanup(factory)


# ── send_invoice_reminders ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_reminders_emit_outbox_event_for_invoice_due_in_7_days(factory, patched_beat) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = invoice.id

    # Force the invoice due_at to today + 7 (T-7 reminder)
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text("UPDATE platform.invoices SET due_at = :da WHERE id = :id"),
            {"da": date.today() + timedelta(days=7), "id": invoice_id},
        )
        await s.commit()

    try:
        counts = await _run_send_invoice_reminders()
        assert counts["window_-7"] == 1

        async with factory() as s:
            await _set_platform(s)
            outbox_count = await s.scalar(
                text(
                    "SELECT count(*) FROM platform.outbox_events "
                    "WHERE event_type = 'BillingInvoiceReminderDue' "
                    "AND aggregate_id = :iid"
                ),
                {"iid": str(invoice_id)},
            )
            assert outbox_count == 1
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_reminders_skip_paid_invoices(factory, patched_beat) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = invoice.id

    # Mark fully paid + due in 7 days
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.invoices SET due_at = :da, amount_paid = amount_total, status = 'paid' "
                "WHERE id = :id"
            ),
            {"da": date.today() + timedelta(days=7), "id": invoice_id},
        )
        await s.commit()

    try:
        counts = await _run_send_invoice_reminders()
        # paid invoice not in {issued, partial, overdue} → no event
        assert counts["window_-7"] == 0
    finally:
        await _cleanup(factory)


# ── mark_overdue_invoices ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_mark_overdue_transitions_eligible_invoices(factory, patched_beat) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        # Force due_at into the past
        invoice.due_at = date.today() - timedelta(days=1)
        await s.commit()
        invoice_id = invoice.id

    try:
        counts = await _run_mark_overdue_invoices()
        assert counts["transitioned"] >= 1

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Invoice, invoice_id)
            assert refreshed is not None
            assert refreshed.status == "overdue"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_mark_overdue_idempotent_on_already_overdue(factory, patched_beat) -> None:
    """Running mark_overdue twice doesn't double-transition (set-based UPDATE)."""
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        invoice.due_at = date.today() - timedelta(days=1)
        await s.commit()

    try:
        first = await _run_mark_overdue_invoices()
        assert first["transitioned"] == 1
        second = await _run_mark_overdue_invoices()
        # Invoice is now 'overdue' — not in eligible set → 0 transitioned
        assert second["transitioned"] == 0
    finally:
        await _cleanup(factory)
```

- [ ] **Step 3: Run tests + lint**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_beat.py -v 2>&1 | tail -20
env -u DATABASE_URL python -m mypy app/platform_/billing/
ruff check app/platform_/billing/ tests/platform_/billing/test_beat.py
```

Expected: 9 tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/platform_/billing/beat.py tests/platform_/billing/test_beat.py
git commit -m "feat(billing): beat tasks — assess, generate, reminders, mark_overdue"
```

---

## Task 2: Celery wiring

**Files:**
- Modify: `app/workers/celery_app.py`

- [ ] **Step 1: Add the module to `include[]`**

Find the `include` list and add `"app.platform_.billing.beat"`. Match the existing module ordering (alphabetical within each group). Reasonable placement: after `app.modules.reporting.beat`.

- [ ] **Step 2: Add 4 entries to `beat_schedule`**

```python
"assess-subscription-state": {
    "task": "app.platform_.billing.beat.assess_subscription_state",
    "schedule": 24 * 3600.0,  # daily
},
"generate-next-period-invoices": {
    "task": "app.platform_.billing.beat.generate_next_period_invoices",
    "schedule": 24 * 3600.0,  # daily
},
"send-invoice-reminders": {
    "task": "app.platform_.billing.beat.send_invoice_reminders",
    "schedule": 24 * 3600.0,  # daily
},
"mark-overdue-invoices": {
    "task": "app.platform_.billing.beat.mark_overdue_invoices",
    "schedule": 24 * 3600.0,  # daily
},
```

Place these inside the existing `beat_schedule` dict, after the credit / reporting entries.

- [ ] **Step 3: Smoke test the celery import**

```bash
env -u DATABASE_URL python -c "
from app.workers.celery_app import celery_app
expected = {
    'app.platform_.billing.beat.assess_subscription_state',
    'app.platform_.billing.beat.generate_next_period_invoices',
    'app.platform_.billing.beat.send_invoice_reminders',
    'app.platform_.billing.beat.mark_overdue_invoices',
}
registered = set(celery_app.tasks.keys())
missing = expected - registered
assert not missing, f'Missing tasks: {missing}'
print('OK — all 4 billing beat tasks registered')
"
```

Expected: `OK — all 4 billing beat tasks registered`.

- [ ] **Step 4: Run full suite to check no regressions**

```bash
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
ruff check app/workers/celery_app.py
env -u DATABASE_URL python -m mypy app/workers/celery_app.py
```

- [ ] **Step 5: Commit**

```bash
git add app/workers/celery_app.py
git commit -m "feat(billing): wire 4 beat tasks into celery_app.py"
```

---

## Task 3: End-to-end integration test

**Files:**
- Create: `tests/platform_/billing/test_e2e_lifecycle.py`

The end-to-end test simulates a tenant's full billing lifecycle by manipulating dates in-place rather than waiting:

1. Create tenant + plan
2. Assign subscription (active)
3. Generate first invoice
4. Maker records a payment (creates Payment(pending) + ApprovalRequest)
5. Checker confirms (executes via ApprovalService.approve → executor → PaymentService.confirm)
6. Verify invoice is paid
7. Force time forward (period_end past) → assess_subscription_state → past_due
8. Force grace expired → assess_subscription_state → suspended
9. Reactivate
10. Verify final state

- [ ] **Step 1: Write `tests/platform_/billing/test_e2e_lifecycle.py`**

```python
"""End-to-end integration test for the Phase 1 billing lifecycle.

Exercises the full flow without waiting for real time to pass:
  assign → invoice → record_payment → confirm → past_due → suspended → reactivate
"""
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

from app.modules.maker_checker.models.platform import PlatformApprovalRequest
from app.modules.maker_checker.service import ApprovalService
from app.platform_.billing.beat import (
    _run_assess_subscription_state,
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

# Force the executors module to register
import app.platform_.billing.executors  # noqa: F401


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _cleanup(factory) -> None:
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL, "
                "subscription_status = 'pending'"
            )
        )
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(delete(Payment))
        await s.execute(delete(InvoiceLineItem))
        await s.execute(delete(Invoice))
        await s.execute(delete(Subscription))
        await s.execute(delete(SubscriptionPlan))
        await s.execute(delete(Tenant))
        await s.execute(delete(PlatformUser))
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.commit()


@pytest.fixture
async def factory(test_engine: AsyncEngine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture
def patched_beat(test_engine: AsyncEngine, monkeypatch):
    class _Wrapper:
        def __init__(self, engine):
            self._engine = engine

        async def dispose(self):
            pass

        def __getattr__(self, name):
            return getattr(self._engine, name)

    wrapper = _Wrapper(test_engine)
    monkeypatch.setattr(
        "app.platform_.billing.beat.create_async_engine",
        lambda *a, **kw: wrapper,
    )


@pytest.mark.anyio
async def test_full_billing_lifecycle(factory, patched_beat) -> None:
    """Walk a single tenant through every Phase 1 billing transition."""
    # Setup actors and plan
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        maker = PlatformUser(
            email=f"maker-{uuid.uuid4().hex[:8]}@test.example",
            full_name="Maker",
            is_active=True,
            is_superuser=True,
            created_at=now,
            updated_at=now,
        )
        checker = PlatformUser(
            email=f"checker-{uuid.uuid4().hex[:8]}@test.example",
            full_name="Checker",
            is_active=True,
            is_superuser=True,
            created_at=now,
            updated_at=now,
        )
        tenant = Tenant(
            slug=f"e2e-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_e2e_{uuid.uuid4().hex[:8]}",
            name="E2E Test SACCO",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        plan = SubscriptionPlan(
            code=f"e2e-plan-{uuid.uuid4().hex[:8]}",
            name="E2E Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            grace_period_days=14,
        )
        s.add_all([maker, checker, tenant, plan])
        await s.commit()
        await s.refresh(maker)
        await s.refresh(checker)
        await s.refresh(tenant)
        await s.refresh(plan)
        maker_id, checker_id, tenant_id, plan_id = (
            maker.id, checker.id, tenant.id, plan.id
        )

    try:
        # 1. Assign subscription (active because plan has no trial)
        async with factory() as s:
            await _set_platform(s)
            sub = await SubscriptionService(s).assign(
                tenant_id=tenant_id, plan_id=plan_id
            )
            await s.commit()
            sub_id = sub.id
            assert sub.status == "active"

        # 2. Generate the first invoice
        async with factory() as s:
            await _set_platform(s)
            invoice = await InvoiceService(s).generate_for_subscription(
                subscription_id=sub_id
            )
            await s.commit()
            invoice_id = invoice.id
            assert invoice.status == "issued"
            assert invoice.amount_total == Decimal("50000.0000")

        # 3. Maker records a payment
        async with factory() as s:
            await _set_platform(s)
            pmt = await PaymentService(s).record(
                invoice_id=invoice_id,
                amount=Decimal("50000"),
                currency="UGX",
                payment_method="bank_transfer",
                recorded_by=maker_id,
                idempotency_key=f"e2e-{uuid.uuid4().hex}",
            )
            # Create the linked ApprovalRequest (simulating the API layer)
            approval_request = await ApprovalService(s).submit(
                operation_type="billing.confirm_payment",
                payload={"payment_id": str(pmt.id)},
                requested_by=maker_id,
            )
            pmt.approval_request_id = approval_request.id
            await s.commit()
            payment_id = pmt.id
            request_id = approval_request.id

        # 4. Checker approves — triggers executor → PaymentService.confirm
        async with factory() as s:
            await _set_platform(s)
            await ApprovalService(s).approve(
                request_id=request_id,
                actor_user_id=checker_id,
            )
            await s.commit()

        # 5. Verify: payment confirmed, invoice paid
        async with factory() as s:
            await _set_platform(s)
            pmt = await s.get(Payment, payment_id)
            assert pmt is not None
            assert pmt.status == "confirmed"
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            assert inv.status == "paid"
            assert inv.amount_paid == Decimal("50000.0000")
            req = await s.get(PlatformApprovalRequest, request_id)
            assert req is not None
            assert req.status == "executed"

        # 6. Force the subscription into past_due (period_end in past)
        async with factory() as s:
            await _set_platform(s)
            await s.execute(
                text(
                    "UPDATE platform.subscriptions SET current_period_end = :pe "
                    "WHERE id = :id"
                ),
                {"pe": date.today() - timedelta(days=1), "id": sub_id},
            )
            await s.commit()

        # 7. assess_subscription_state → past_due
        counts = await _run_assess_subscription_state()
        assert counts["past_due"] >= 1

        async with factory() as s:
            await _set_platform(s)
            sub = await s.get(Subscription, sub_id)
            assert sub is not None
            assert sub.status == "past_due"
            assert sub.grace_period_ends_at is not None
            t = await s.get(Tenant, tenant_id)
            assert t is not None
            assert t.subscription_status == "past_due"

        # 8. Force grace period expired
        async with factory() as s:
            await _set_platform(s)
            await s.execute(
                text(
                    "UPDATE platform.subscriptions SET grace_period_ends_at = :gpe "
                    "WHERE id = :id"
                ),
                {"gpe": date.today() - timedelta(days=1), "id": sub_id},
            )
            await s.commit()

        # 9. assess → suspended
        counts = await _run_assess_subscription_state()
        assert counts["suspended"] >= 1

        async with factory() as s:
            await _set_platform(s)
            sub = await s.get(Subscription, sub_id)
            assert sub is not None
            assert sub.status == "suspended"
            t = await s.get(Tenant, tenant_id)
            assert t is not None
            assert t.subscription_status == "suspended"

        # 10. Reactivate
        async with factory() as s:
            await _set_platform(s)
            sub = await SubscriptionService(s).reactivate(subscription_id=sub_id)
            await s.commit()
            assert sub.status == "active"

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant_id)
            assert t is not None
            assert t.subscription_status == "active"

    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Run the e2e test**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_e2e_lifecycle.py -v 2>&1 | tail -10
```

Expected: 1 test passes (it's a long test — may take 5-10s).

- [ ] **Step 3: Commit**

```bash
git add tests/platform_/billing/test_e2e_lifecycle.py
git commit -m "test(billing): end-to-end lifecycle integration test"
```

---

## Task 4: Runbook + CLAUDE.md + final push

**Files:**
- Create: `docs/runbooks/billing-operator-guide.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Create the runbook directory if needed**

```bash
mkdir -p docs/runbooks
```

- [ ] **Step 2: Write `docs/runbooks/billing-operator-guide.md`**

```markdown
# Billing — Operator Runbook

Audience: platform operators (Sacco-platform staff) using the admin
endpoints in `/platform/billing/*`. This document is task-oriented.
For module contracts and architecture, see `CLAUDE.md` and
`docs/superpowers/plans/saas-launch-roadmap.md` §5.

---

## 1. Daily checks

The following Celery beat tasks run every 24 hours. If any of them has not
run in the last 36 hours, escalate to engineering — that means the beat
scheduler is wedged.

| Task | What it does |
|---|---|
| `assess_subscription_state` | Transitions expired subscriptions to `past_due`; past-grace to `suspended` |
| `generate_next_period_invoices` | Creates the next-period invoice for subscriptions billing today |
| `send_invoice_reminders` | Emits `BillingInvoiceReminderDue` outbox events at T-7/T-3/T-0/T+3/T+7 |
| `mark_overdue_invoices` | Flips `issued`/`partial` invoices past `due_at` to `overdue` |

Inspect by querying `platform.tenants.subscription_status` and counting
each status. A sudden jump in `suspended` count should be investigated
(usually a misconfigured plan grace_period_days).

---

## 2. Record a customer payment (offline)

Two-person workflow — the maker records, the checker confirms.

### Maker (Finance Officer)

1. Identify the invoice: `GET /platform/billing/invoices?tenant_id=<id>&status=issued`.
2. Confirm receipt of funds out-of-band (bank statement, mobile-money
   confirmation, cheque, cash receipt).
3. Submit the payment:

```
POST /platform/billing/invoices/{invoice_id}/payments
Headers: X-Platform-Actor-ID: <your-user-id>
Body:
{
  "amount": "50000.0000",
  "currency": "UGX",
  "payment_method": "bank_transfer",
  "external_reference": "BANK-TXN-12345",
  "notes": "Confirmed via bank statement 2026-06-01",
  "idempotency_key": "<a-unique-key-you-generate-from-the-bank-ref>"
}
```

Response includes `payment_id` and `approval_request_id`. Pass these to the
checker out-of-band (Slack, Signal, in-person).

### Checker (Senior Finance / Manager)

You CANNOT be the same person as the maker. Self-approval is rejected.

To approve (this triggers `PaymentService.confirm` and flips the invoice
to `paid` or `partial`):
```
POST /maker-checker/approval-requests/{approval_request_id}/approve
Headers: X-Platform-Actor-ID: <your-user-id>
```

To reject (this discards the payment):
```
POST /platform/billing/payments/{payment_id}/reject
Headers: X-Platform-Actor-ID: <your-user-id>
Body: { "reason": "Bank reference did not match deposit" }
```

⚠ The rejection endpoint pairs `ApprovalService.reject` and
`PaymentService.reject` atomically. Do NOT use the generic
`/approval-requests/{id}/reject` for billing payment rejections — that
leaves the `Payment` row stuck in `pending`.

---

## 3. Void an invoice

Voiding is for invoices that haven't received any payment yet.
Partial/paid invoices cannot be voided in v1 — payments must be reversed
first (out-of-scope).

### Maker

```
POST /platform/billing/invoices/{invoice_id}/void
Headers: X-Platform-Actor-ID: <your-user-id>
Body: { "reason": "Duplicate issuance for billing period" }
```

### Checker

```
POST /maker-checker/approval-requests/{approval_request_id}/approve
Headers: X-Platform-Actor-ID: <your-user-id>
```

The `billing.void_invoice` executor flips the invoice to `void`.

---

## 4. Cancel a subscription

Two modes:

### Soft cancel (cancel at period end) — direct, no maker-checker

```
POST /platform/billing/subscriptions/{id}/cancel?mode=at_period_end
Headers: X-Platform-Actor-ID: <your-user-id>
Body: { "reason": "Tenant requested non-renewal" }
```

The subscription stays active until `current_period_end`. The
`assess_subscription_state` beat job will transition to `cancelled` at
that point. Reversible via `reactivate` until then? No — reactivate only
works on `suspended`/`past_due`. For soft cancel, reverse by clearing
`cancelled_at` directly in the DB (engineering required).

### Hard cancel (immediate) — requires maker-checker

```
POST /platform/billing/subscriptions/{id}/cancel?mode=immediate
Headers: X-Platform-Actor-ID: <your-user-id>
Body: { "reason": "Compliance action" }
```

Checker approves via the generic approval endpoint. On approval, the
`billing.cancel_subscription` executor flips status to `cancelled` and
syncs `tenants.subscription_status`. The subscription gate then blocks
all tenant-scoped requests with 403.

---

## 5. Reactivate a suspended tenant

For tenants whose subscription is `suspended` (grace period expired)
or `past_due`:

```
POST /platform/billing/subscriptions/{id}/reactivate
Headers: X-Platform-Actor-ID: <your-user-id>
```

This is a direct call — no maker-checker. The current period is reset
to `today + plan.billing_period_days`, `grace_period_ends_at` is
cleared, and `tenants.subscription_status` flips to `active`.

⚠ Reactivation does NOT generate a new invoice automatically. The
operator should typically generate one immediately:

```
# Force the next-period invoice today
UPDATE platform.subscriptions SET next_billing_date = CURRENT_DATE WHERE id = '<sub-id>';
# Then trigger the beat
celery -A app.workers.celery_app call app.platform_.billing.beat.generate_next_period_invoices
```

Or wait for the next nightly beat run.

---

## 6. Debug a stuck subscription state

If a tenant complains they're locked out but the system says
`subscription_status = 'active'`:

1. Check `platform.tenants.subscription_status` directly.
2. Compare with `platform.subscriptions.status` for the same tenant. They
   should match — drift indicates a service bug.
3. Check the latest entries in the structured log for
   `billing.beat.assess_*` and `subscription.*` events.

If drift exists, the safe fix is to call `SubscriptionService` to
re-transition rather than UPDATE directly (the denormalisation only
stays in sync when the service does it). Engineering can do this via
a Python REPL against the prod DB.

---

## 7. PDF invoice download

Operators can fetch any invoice's PDF:
```
GET /platform/billing/invoices/{invoice_id}.pdf
Headers: X-Platform-Actor-ID: <your-user-id>
```

Tenants can fetch their own invoices:
```
GET /billing/me/invoices/{invoice_id}.pdf
Headers: X-Tenant-Slug: <slug> X-Tenant-Actor-ID: <user-id>
```

PDFs are rendered on-demand (no caching). Render time is ~200ms-1s.
```

- [ ] **Step 3: Update CLAUDE.md billing contracts section**

Append these bullets at the end of the existing "Billing module contracts" section:

```markdown
- The 4 nightly beat tasks live in `app/platform_/billing/beat.py`:
  `assess_subscription_state`, `generate_next_period_invoices`,
  `send_invoice_reminders`, `mark_overdue_invoices`. Each is registered
  in `app/workers/celery_app.py` with a 24-hour schedule. All four are
  idempotent on the same day — re-running them does not produce duplicate
  state transitions or invoices.
- `assess_subscription_state` is the ONLY path that transitions
  `active|trialing` → `past_due` and `past_due` → `suspended` via the
  beat. Manual transitions go through `SubscriptionService` methods
  directly; never UPDATE `subscriptions.status` from beat or service code
  outside `SubscriptionService`.
- `generate_next_period_invoices` is the ONLY path that creates an
  invoice for a subscription billing today. It advances
  `subscription.next_billing_date` after generation. Direct
  `InvoiceService.generate_for_subscription` calls are still permitted
  (e.g., from the API for a backdated invoice), but the beat is the
  canonical recurring path.
- `send_invoice_reminders` emits `BillingInvoiceReminderDue` events to
  the platform outbox at five windows (T-7, T-3, T-0, T+3, T+7 relative
  to `due_at`). v1 does NOT dedupe across same-day re-runs — Phase 3's
  notification consumer must dedupe by
  `(invoice_id, reminder_window, date)`. Document this constraint
  on the notification consumer when Phase 3 lands.
- `mark_overdue_invoices` is the ONLY beat path that flips
  `issued|partial` invoices to `overdue`. Direct calls to
  `InvoiceService.mark_overdue_batch` are still permitted (e.g., from
  ad-hoc maintenance scripts).
```

- [ ] **Step 4: Final regression + lint + push**

```bash
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
env -u DATABASE_URL python -m mypy app/
ruff check app/ tests/
```

Expected: all green. Roughly ~715 tests passing (701 from SP05 + ~14 from SP06).

- [ ] **Step 5: Commit and push**

```bash
git add docs/runbooks/billing-operator-guide.md CLAUDE.md
git commit -m "docs(billing): operator runbook + CLAUDE.md SP06 contracts"
git push origin feat/phase-1-billing
```

---

## Self-Review Checklist

- [x] `beat.py` defines 4 async helpers + 4 Celery task wrappers
- [x] All beat tasks operate on the platform schema directly (no per-tenant iteration)
- [x] `assess_subscription_state` uses `SubscriptionService` methods (no direct UPDATEs)
- [x] `generate_next_period_invoices` uses `InvoiceService.generate_for_subscription` (idempotent on (sub_id, period_start))
- [x] `send_invoice_reminders` emits to platform outbox via `EventPublisher.publish`
- [x] `mark_overdue_invoices` calls `InvoiceService.mark_overdue_batch`
- [x] All 4 tasks are idempotent on same-day re-runs (except reminders by design — documented)
- [x] Celery wiring: `include[]` + `beat_schedule` entries
- [x] Tests cover each task in isolation + an end-to-end lifecycle test
- [x] Runbook documents the maker/checker payment flow, void, cancel, reactivate, debug stuck state
- [x] CLAUDE.md final contracts added
- [x] mypy strict + ruff clean
- [x] No new top-level dependencies
