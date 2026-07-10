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
