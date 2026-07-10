"""Notifications: renderer, providers, dispatcher, beat."""
from __future__ import annotations

import pytest

from app.core.notifications.renderer import render

SCHEMA = "tenant_test"


def test_render_text_and_html_escaping() -> None:
    assert render("Hi {{ name }}", {"name": "Ada"}, html=False) == "Hi Ada"
    assert render("<b>{{ v }}</b>", {"v": "<x>"}, html=True) == "<b>&lt;x&gt;</b>"
    assert render("{{ v }}", {"v": "<x>"}, html=False) == "<x>"


def test_render_is_sandboxed() -> None:
    with pytest.raises(Exception):  # noqa: B017 — SecurityError from the sandbox
        render("{{ ''.__class__.__mro__ }}", {}, html=False)


async def test_null_and_log_providers() -> None:
    from app.core.notifications.providers.log import LogEmailProvider, LogSMSProvider
    from app.core.notifications.providers.null import NullEmailProvider, NullSMSProvider

    assert NullEmailProvider.name == "null"
    assert LogEmailProvider.name == "log"
    assert await NullEmailProvider().send(to="a@b.c", subject="s", text="t", html=None) is None
    assert await NullSMSProvider().send(to="+256", body="b") is None
    assert await LogEmailProvider().send(to="a@b.c", subject="s", text="t", html=None)
    assert await LogSMSProvider().send(to="+256", body="b")


def test_provider_factory_defaults_to_null() -> None:
    from app.core.notifications import providers
    from app.core.notifications.providers.null import NullEmailProvider

    assert isinstance(providers.get_email_provider(), NullEmailProvider)


# ── Dispatcher ────────────────────────────────────────────────────────────────

import uuid  # noqa: E402

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.core.notifications.dispatcher import dispatch_event  # noqa: E402
from app.core.notifications.models import (  # noqa: E402
    TenantNotificationDelivery,
    TenantNotificationPreference,
)
from app.core.notifications.seed_templates import seed_default_templates  # noqa: E402
from app.core.notifications.service import NotificationService  # noqa: E402


@pytest.fixture
async def factory(test_engine: AsyncEngine):  # noqa: ANN201
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    yield maker
    async with maker() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        for tbl in (
            f"{SCHEMA}.notification_deliveries",
            f"{SCHEMA}.notification_preferences",
            f"{SCHEMA}.notification_events",
            "platform.notification_deliveries",
            "platform.notification_preferences",
            "platform.notification_events",
        ):
            await s.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        await s.commit()


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture
async def seeded(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        await seed_default_templates(s)
        await s.commit()


async def _publish(s: AsyncSession, **overrides):  # noqa: ANN003, ANN202
    kwargs: dict = {
        "event_code": "system_announcement",
        "recipient_kind": "tenant_user",
        "recipient_user_id": uuid.uuid4(),
        "recipient_email": "op@example.com",
        "context": {"title": "T", "body": "B"},
    }
    kwargs.update(overrides)
    return await NotificationService(s).publish(**kwargs)


async def test_dispatch_in_app_plus_null_email(factory, seeded) -> None:  # noqa: ANN001
    async with factory() as s:
        await _set_path(s)
        event = await _publish(s)
        status = await dispatch_event(s, event)
        await s.commit()
    assert status == "sent"
    async with factory() as s:
        await _set_path(s)
        deliveries = list(
            (await s.execute(select(TenantNotificationDelivery))).scalars()
        )
    # in_app writes NO delivery row; null email writes one 'sent' row.
    assert [d.channel for d in deliveries] == ["email"]
    assert deliveries[0].provider == "null"
    assert deliveries[0].status == "sent"


async def test_dispatch_preference_disabled_email(factory, seeded) -> None:  # noqa: ANN001
    user_id = uuid.uuid4()
    async with factory() as s:
        await _set_path(s)
        s.add(
            TenantNotificationPreference(
                recipient_kind="tenant_user", user_id=user_id,
                event_code="system_announcement", channel="email", enabled=False,
            )
        )
        event = await _publish(s, recipient_user_id=user_id)
        status = await dispatch_event(s, event)
        await s.commit()
    assert status == "sent"  # in_app remains; email skipped, no delivery row
    async with factory() as s:
        await _set_path(s)
        assert (
            await s.execute(select(TenantNotificationDelivery))
        ).scalars().first() is None


async def test_dispatch_missing_email_address_fails_channel(factory, seeded) -> None:  # noqa: ANN001
    async with factory() as s:
        await _set_path(s)
        event = await _publish(s, recipient_email=None, channels=["email"])
        status = await dispatch_event(s, event)
        await s.commit()
    assert status == "failed"
    async with factory() as s:
        await _set_path(s)
        d = (await s.execute(select(TenantNotificationDelivery))).scalars().one()
    assert d.status == "failed"
    assert "recipient" in (d.error_message or "")


async def test_dispatch_skips_already_sent_channel(factory, seeded) -> None:  # noqa: ANN001
    async with factory() as s:
        await _set_path(s)
        event = await _publish(s, channels=["email"])
        assert await dispatch_event(s, event) == "sent"
        # Second dispatch must not double-send: no new delivery row.
        assert await dispatch_event(s, event) == "sent"
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        rows = list((await s.execute(select(TenantNotificationDelivery))).scalars())
    assert len(rows) == 1


# ── Beat jobs ─────────────────────────────────────────────────────────────────

from app.core.notifications.beat import (  # noqa: E402
    _dispatch_for_schema,
    _purge_for_schema,
    _retry_for_schema,
)
from app.core.notifications.models import TenantNotificationEvent  # noqa: E402


async def test_beat_dispatches_due_queued_events(
    test_engine: AsyncEngine, factory, seeded  # noqa: ANN001
) -> None:
    async with factory() as s:
        await _set_path(s)
        event = await _publish(s)
        await s.commit()
    count = await _dispatch_for_schema(test_engine, SCHEMA)
    assert count == 1
    async with factory() as s:
        await _set_path(s)
        row = await s.get(TenantNotificationEvent, event.id)
    assert row is not None and row.status == "sent"
    # Second run: nothing queued.
    assert await _dispatch_for_schema(test_engine, SCHEMA) == 0


async def test_retry_requeues_failed_under_attempt_cap(
    test_engine: AsyncEngine, factory, seeded  # noqa: ANN001
) -> None:
    async with factory() as s:
        await _set_path(s)
        event = await _publish(s, recipient_email=None, channels=["email"])
        await s.commit()
    await _dispatch_for_schema(test_engine, SCHEMA)  # -> failed (no email addr)
    async with factory() as s:
        await _set_path(s)
        # Age the delivery so backoff allows a retry.
        await s.execute(
            text(
                "UPDATE notification_deliveries "
                "SET sent_at = now() - interval '10 minutes'"
            )
        )
        await s.commit()
    requeued = await _retry_for_schema(test_engine, SCHEMA, max_attempts=3)
    assert requeued == 1
    async with factory() as s:
        await _set_path(s)
        row = await s.get(TenantNotificationEvent, event.id)
    assert row is not None and row.status == "queued"


async def test_purge_deletes_only_old_terminal_events(
    test_engine: AsyncEngine, factory, seeded  # noqa: ANN001
) -> None:
    async with factory() as s:
        await _set_path(s)
        old = await _publish(s)
        fresh = await _publish(s)
        await dispatch_event(s, old)
        await dispatch_event(s, fresh)
        await s.flush()
        await s.execute(
            text(
                "UPDATE notification_events "
                "SET created_at = now() - interval '200 days' WHERE id = :i"
            ),
            {"i": str(old.id)},
        )
        await s.commit()
    deleted = await _purge_for_schema(test_engine, SCHEMA, days=180)
    assert deleted == 1
    async with factory() as s:
        await _set_path(s)
        assert await s.get(TenantNotificationEvent, old.id) is None
        assert await s.get(TenantNotificationEvent, fresh.id) is not None
