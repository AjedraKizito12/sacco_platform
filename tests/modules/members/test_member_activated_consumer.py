"""member_activated consumer: MemberActivated outbox event -> notification."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.notifications.models import TenantNotificationEvent
from app.core.notifications.seed_templates import seed_default_templates
from app.core.outbox.models import TenantOutboxEvent
from app.modules.members.consumer import _consume_for_tenant
from app.modules.members.models import Member

SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture(autouse=True)
async def _clean(test_engine: AsyncEngine):  # noqa: ANN201
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        await seed_default_templates(s)
        await s.commit()
    yield
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text(f"DELETE FROM {SCHEMA}.notification_events"))  # noqa: S608
        await s.execute(
            text(
                "DELETE FROM processed_events "
                "WHERE consumer_name = 'notifications.member_consumer'"
            )
        )
        await s.execute(
            text("DELETE FROM outbox_events WHERE event_type = 'MemberActivated'")
        )
        await s.execute(text("DELETE FROM audit_log WHERE table_name = 'members'"))
        await s.execute(text("DELETE FROM members WHERE email LIKE 'mac-%'"))
        await s.commit()


async def _seed(test_engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (member_id, outbox_event_id)."""
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        member = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}",
            full_name="Activated Member",
            date_of_birth=date(1990, 1, 1),
            gender="female",
            status="active",
            email=f"mac-{uuid.uuid4().hex[:6]}@m.test",
        )
        s.add(member)
        await s.flush()
        event = TenantOutboxEvent(
            aggregate_type="member",
            aggregate_id=member.id,
            event_type="MemberActivated",
            payload={
                "member_id": str(member.id),
                "member_number": member.member_number,
                "activated_at": date.today().isoformat(),
            },
            occurred_at=datetime.now(UTC),
        )
        s.add(event)
        await s.flush()
        ids = (member.id, event.id)
        await s.commit()
        return ids


async def test_consumer_publishes_member_activated(test_engine: AsyncEngine) -> None:
    member_id, event_id = await _seed(test_engine)
    processed = await _consume_for_tenant(test_engine, SCHEMA)
    assert processed >= 1

    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.dedupe_key == f"member_activated:{event_id}"
                )
            )
        ).scalars().one()
        marked = await s.scalar(
            text(
                "SELECT 1 FROM processed_events "
                "WHERE event_id = :eid AND consumer_name = 'notifications.member_consumer'"
            ),
            {"eid": event_id},
        )
    assert marked == 1
    assert row.event_code == "member_activated"
    assert row.recipient_kind == "member"
    assert row.recipient_user_id == member_id
    assert row.context["full_name"] == "Activated Member"


async def test_consumer_is_idempotent(test_engine: AsyncEngine) -> None:
    _, event_id = await _seed(test_engine)
    await _consume_for_tenant(test_engine, SCHEMA)
    assert await _consume_for_tenant(test_engine, SCHEMA) == 0

    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        rows = list(
            (
                await s.execute(
                    select(TenantNotificationEvent).where(
                        TenantNotificationEvent.dedupe_key
                        == f"member_activated:{event_id}"
                    )
                )
            ).scalars()
        )
    assert len(rows) == 1
