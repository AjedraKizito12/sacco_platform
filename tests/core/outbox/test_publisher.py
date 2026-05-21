"""
Integration tests for EventPublisher.

Each test manages its own session with explicit commit + cleanup, matching the
pattern used by maker_checker tests. This avoids the asyncpg protocol-state
error that occurs when flush() is called inside a session-scoped async fixture
in pytest-asyncio ≥0.21 with a session-scoped event loop (see CLAUDE.md note
on test fixture design).
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.outbox.models import PlatformOutboxEvent, TenantOutboxEvent
from app.core.outbox.publisher import EventPublisher

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_publish_writes_to_platform_outbox(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    agg_id = uuid.uuid4()

    # Write
    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        session.sync_session.info["is_platform"] = True
        await EventPublisher.publish(
            session,
            aggregate_type="tenant",
            aggregate_id=agg_id,
            event_type="TenantCreated",
            payload={"slug": "acme"},
        )
        await session.commit()

    # Assert
    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        rows = (await session.execute(select(PlatformOutboxEvent))).scalars().all()
        assert len(rows) == 1
        assert rows[0].event_type == "TenantCreated"
        assert rows[0].published_at is None
        assert rows[0].is_dead_lettered is False
        assert rows[0].attempts == 0

    # Cleanup
    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await session.execute(delete(PlatformOutboxEvent))
        await session.commit()


async def test_publish_writes_to_tenant_outbox(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    agg_id = uuid.uuid4()

    # Write
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await EventPublisher.publish(
            session,
            aggregate_type="loan",
            aggregate_id=agg_id,
            event_type="LoanDisbursed",
            payload={"amount": 500000},
        )
        await session.commit()

    # Assert
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        rows = (await session.execute(select(TenantOutboxEvent))).scalars().all()
        assert len(rows) == 1
        assert rows[0].aggregate_type == "loan"
        assert rows[0].payload == {"amount": 500000}

    # Cleanup
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantOutboxEvent))
        await session.commit()


async def test_rollback_removes_outbox_row(test_engine: AsyncEngine) -> None:
    """Row written inside a rolled-back transaction must not persist."""
    factory = _factory(test_engine)
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
