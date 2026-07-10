"""Notifications: catalog, template seeds, and NotificationService.publish."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.notifications.catalog import (
    CHANNELS,
    NOTIFICATION_CATALOG,
    RECIPIENT_KINDS,
    spec_for,
)
from app.core.notifications.models import (
    PlatformNotificationEvent,
    TenantNotificationEvent,
)

SCHEMA = "tenant_test"

EXPECTED_CODES = (
    "password_reset",
    "maker_checker_pending",
    "maker_checker_approved",
    "maker_checker_rejected",
    "invoice_issued",
    "invoice_overdue",
    "subscription_suspended",
    "system_announcement",
    "member_activated",
    "kyc_submission_approved",
    "kyc_submission_rejected",
    "loan_application_approved",
    "loan_application_rejected",
)


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


def test_catalog_has_all_13_codes_with_valid_shapes() -> None:
    assert tuple(s.code for s in NOTIFICATION_CATALOG) == EXPECTED_CODES
    for spec in NOTIFICATION_CATALOG:
        assert spec.default_channels
        assert set(spec.default_channels) <= set(CHANNELS)
        assert spec.recipient_kinds
        assert set(spec.recipient_kinds) <= set(RECIPIENT_KINDS)
    assert spec_for("password_reset").code == "password_reset"
    with pytest.raises(KeyError):
        spec_for("nope")


async def test_event_rows_in_both_schemas_and_dedupe_unique(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        s.add(
            TenantNotificationEvent(
                event_code="system_announcement",
                recipient_kind="tenant_user",
                recipient_user_id=uuid.uuid4(),
                channels=["in_app"],
                context={"title": "hi"},
                dedupe_key="k-1",
            )
        )
        s.add(
            PlatformNotificationEvent(
                event_code="system_announcement",
                recipient_kind="platform_user",
                recipient_user_id=uuid.uuid4(),
                channels=["in_app"],
                context={},
            )
        )
        await s.flush()
        s.add(
            TenantNotificationEvent(
                event_code="system_announcement",
                recipient_kind="tenant_user",
                recipient_user_id=uuid.uuid4(),
                channels=["in_app"],
                context={},
                dedupe_key="k-1",
            )
        )
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()


from app.core.notifications.seed_templates import (  # noqa: E402
    DEFAULT_TEMPLATES,
    seed_default_templates,
)


def test_default_templates_cover_every_catalog_default_channel() -> None:
    pairs = {(t["code"], t["channel"]) for t in DEFAULT_TEMPLATES}
    for spec in NOTIFICATION_CATALOG:
        for channel in spec.default_channels:
            assert (spec.code, channel) in pairs, (spec.code, channel)
    for t in DEFAULT_TEMPLATES:
        assert isinstance(t["variables"], dict)
        if t["channel"] == "email":
            assert t["subject_template"] and t["body_text"]
        if t["channel"] == "in_app":
            assert t["subject_template"] and t["body_text"]


async def test_seed_is_idempotent(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        first = await seed_default_templates(s)
        again = await seed_default_templates(s)
        await s.commit()
    assert first >= len(DEFAULT_TEMPLATES) or first == 0  # fresh DB: all; reruns: 0
    assert again == 0


from app.core.notifications.service import NotificationService  # noqa: E402


@pytest.fixture
async def seeded(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        await seed_default_templates(s)
        await s.commit()


async def test_publish_writes_queued_event_in_callers_txn(
    factory: async_sessionmaker, seeded: None
) -> None:
    user_id = uuid.uuid4()
    async with factory() as s:
        await _set_path(s)
        event = await NotificationService(s).publish(
            event_code="system_announcement",
            recipient_kind="tenant_user",
            recipient_user_id=user_id,
            recipient_email="op@example.com",
            context={"title": "Maintenance", "body": "Tonight 22:00"},
        )
        assert event.status == "queued"
        assert sorted(event.channels) == ["email", "in_app"]  # catalog defaults
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        row = await s.get(TenantNotificationEvent, event.id)
    assert row is not None
    assert row.recipient_email == "op@example.com"


async def test_publish_platform_session_uses_platform_table(
    factory: async_sessionmaker, seeded: None
) -> None:
    async with factory() as s:
        s.sync_session.info["is_platform"] = True
        await _set_path(s)
        event = await NotificationService(s).publish(
            event_code="system_announcement",
            recipient_kind="platform_user",
            recipient_user_id=uuid.uuid4(),
            context={"title": "t", "body": "b"},
        )
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        assert await s.get(PlatformNotificationEvent, event.id) is not None


async def test_publish_validation_errors(
    factory: async_sessionmaker, seeded: None
) -> None:
    async with factory() as s:
        await _set_path(s)
        svc = NotificationService(s)
        with pytest.raises(ValueError, match="Unknown"):
            await svc.publish(
                event_code="nope", recipient_kind="member",
                recipient_user_id=uuid.uuid4(), context={},
            )
        with pytest.raises(ValueError, match="recipient kind"):
            await svc.publish(
                event_code="invoice_issued", recipient_kind="member",
                recipient_user_id=uuid.uuid4(), context={},
            )
        with pytest.raises(ValueError, match="channel"):
            await svc.publish(
                event_code="system_announcement", recipient_kind="member",
                recipient_user_id=uuid.uuid4(), context={}, channels=["pigeon"],
            )
        with pytest.raises(ValueError, match="context key"):
            await svc.publish(
                event_code="system_announcement", recipient_kind="member",
                recipient_user_id=uuid.uuid4(),
                context={"title": "x", "body": "y", "national_id": "SECRET"},
            )
        await s.rollback()


async def test_publish_dedupe_key_is_idempotent(
    factory: async_sessionmaker, seeded: None
) -> None:
    key = f"test-{uuid.uuid4()}"
    async with factory() as s:
        await _set_path(s)
        svc = NotificationService(s)
        first = await svc.publish(
            event_code="system_announcement", recipient_kind="member",
            recipient_user_id=uuid.uuid4(), context={"title": "a", "body": "b"},
            dedupe_key=key,
        )
        second = await svc.publish(
            event_code="system_announcement", recipient_kind="member",
            recipient_user_id=uuid.uuid4(), context={"title": "a", "body": "b"},
            dedupe_key=key,
        )
        await s.commit()
    assert second.id == first.id
