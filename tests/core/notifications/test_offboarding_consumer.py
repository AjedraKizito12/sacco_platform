"""Offboarding notifications consumer: platform outbox -> tenant-admin feeds."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.notifications.models import TenantNotificationEvent
from app.core.notifications.offboarding_consumer import _consume_batch
from app.core.notifications.seed_templates import seed_default_templates
from app.core.outbox.models import PlatformOutboxEvent
from app.modules.iam.tenant_users.models import TenantUser
from app.platform_.models import Tenant

SCHEMA = "tenant_test"
_CONSUMER = "notifications.offboarding_consumer"


def _factory(engine: AsyncEngine) -> async_sessionmaker:  # type: ignore[type-arg]
    return async_sessionmaker(engine, expire_on_commit=False)


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture(autouse=True)
async def _clean(test_engine: AsyncEngine):  # noqa: ANN201
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        await seed_default_templates(s)
        await s.execute(
            text(
                "DELETE FROM platform.outbox_events "
                "WHERE event_type LIKE 'TenantOffboarding%'"
            )
        )
        await s.commit()
    yield
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text(f"DELETE FROM {SCHEMA}.notification_events"))  # noqa: S608
        await s.execute(
            text(
                "DELETE FROM platform.processed_events "
                "WHERE consumer_name = 'notifications.offboarding_consumer'"
            )
        )
        await s.execute(
            text(
                "DELETE FROM platform.outbox_events "
                "WHERE event_type LIKE 'TenantOffboarding%'"
            )
        )
        await s.execute(text("DELETE FROM tenant_users WHERE email LIKE 'onc-%'"))
        await s.execute(text("DELETE FROM platform.tenants WHERE slug = 'onc-tenant'"))
        await s.commit()


async def _seed(
    test_engine: AsyncEngine,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (tenant_id, admin_user_id, teller_user_id, outbox_event_id)."""
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        now = datetime.now(UTC)
        tenant = Tenant(
            slug="onc-tenant",
            schema_name=SCHEMA,
            name="Offboard Notify Co",
            is_active=True,
            lifecycle_state="cancelled",
            created_at=now,
            updated_at=now,
        )
        admin = TenantUser(
            email=f"onc-admin-{uuid.uuid4().hex[:6]}@t.test", full_name="Admin",
            hashed_password=None, is_active=True, is_admin=True,
            created_at=now, updated_at=now,
        )
        teller = TenantUser(
            email=f"onc-teller-{uuid.uuid4().hex[:6]}@t.test", full_name="Teller",
            hashed_password=None, is_active=True, is_admin=False,
            created_at=now, updated_at=now,
        )
        s.add_all([tenant, admin, teller])
        await s.flush()
        event = PlatformOutboxEvent(
            aggregate_type="tenant",
            aggregate_id=tenant.id,
            event_type="TenantOffboardingCancelled",
            payload={
                "tenant_id": str(tenant.id),
                "tenant_name": "Offboard Notify Co",
                "to_state": "cancelled",
                "occurred_at": now.isoformat(),
            },
            occurred_at=now,
        )
        s.add(event)
        await s.flush()
        ids = (tenant.id, admin.id, teller.id, event.id)
        await s.commit()
        return ids


async def test_consumer_notifies_tenant_admins_only(test_engine: AsyncEngine) -> None:
    _, admin_id, teller_id, event_id = await _seed(test_engine)
    processed = await _consume_batch(test_engine)
    assert processed >= 1

    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        rows = list(
            (
                await s.execute(
                    select(TenantNotificationEvent).where(
                        TenantNotificationEvent.dedupe_key.like(
                            f"TenantOffboardingCancelled:{event_id}:%"
                        )
                    )
                )
            ).scalars()
        )
        marked = await s.scalar(
            text(
                "SELECT 1 FROM platform.processed_events "
                "WHERE event_id = :eid AND consumer_name = 'notifications.offboarding_consumer'"
            ),
            {"eid": event_id},
        )
    assert marked == 1
    recipients = {r.recipient_user_id for r in rows}
    assert admin_id in recipients
    assert teller_id not in recipients
    mine = next(r for r in rows if r.recipient_user_id == admin_id)
    assert mine.event_code == "tenant_offboarding_cancelled"
    assert mine.context["to_state"] == "cancelled"
    assert mine.context["tenant_name"] == "Offboard Notify Co"


async def test_consumer_is_idempotent(test_engine: AsyncEngine) -> None:
    _, admin_id, _teller_id, event_id = await _seed(test_engine)
    await _consume_batch(test_engine)
    assert await _consume_batch(test_engine) == 0

    factory = _factory(test_engine)
    async with factory() as s:
        await s.execute(
            text(
                "DELETE FROM platform.processed_events "
                "WHERE event_id = :eid AND consumer_name = 'notifications.offboarding_consumer'"
            ),
            {"eid": event_id},
        )
        await s.commit()
    await _consume_batch(test_engine)
    async with factory() as s:
        await _set_path(s)
        rows = list(
            (
                await s.execute(
                    select(TenantNotificationEvent).where(
                        TenantNotificationEvent.dedupe_key
                        == f"TenantOffboardingCancelled:{event_id}:{admin_id}"
                    )
                )
            ).scalars()
        )
    assert len(rows) == 1
