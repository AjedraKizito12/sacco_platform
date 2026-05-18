from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.outbox.models import PlatformOutboxEvent, TenantOutboxEvent
from app.core.outbox.publisher import EventPublisher


async def test_publish_writes_to_platform_outbox(platform_session):
    agg_id = uuid.uuid4()
    await EventPublisher.publish(
        platform_session,
        aggregate_type="tenant",
        aggregate_id=agg_id,
        event_type="TenantCreated",
        payload={"slug": "acme"},
    )
    await platform_session.flush()

    rows = (await platform_session.execute(select(PlatformOutboxEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == "TenantCreated"
    assert rows[0].published_at is None
    assert rows[0].is_dead_lettered is False
    assert rows[0].attempts == 0


async def test_publish_writes_to_tenant_outbox(tenant_session):
    agg_id = uuid.uuid4()
    await EventPublisher.publish(
        tenant_session,
        aggregate_type="loan",
        aggregate_id=agg_id,
        event_type="LoanDisbursed",
        payload={"amount": 500000},
    )
    await tenant_session.flush()

    rows = (await tenant_session.execute(select(TenantOutboxEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].aggregate_type == "loan"
    assert rows[0].payload == {"amount": 500000}


async def test_rollback_removes_outbox_row(test_engine):
    """Row written inside a rolled-back transaction must not persist."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(text("SET LOCAL search_path TO platform"))
        session.sync_session.info["is_platform"] = True
        await EventPublisher.publish(
            session,
            aggregate_type="tenant",
            aggregate_id=uuid.uuid4(),
            event_type="ShouldNotExist",
            payload={},
        )
        await session.rollback()

    async with factory() as session:
        await session.execute(text("SET LOCAL search_path TO platform"))
        rows = (
            await session.execute(
                select(PlatformOutboxEvent).where(
                    PlatformOutboxEvent.event_type == "ShouldNotExist"
                )
            )
        ).scalars().all()
        assert rows == []
