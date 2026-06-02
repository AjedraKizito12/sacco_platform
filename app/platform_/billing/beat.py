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
