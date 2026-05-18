import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.outbox.models import PlatformOutboxEvent
from app.core.outbox.retention import _purge


async def test_purge_deletes_old_published_rows(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    cutoff = datetime.now(UTC) - timedelta(days=90)
    old_date = cutoff - timedelta(days=1)
    # Use a future date so the recent row is clearly after the cutoff
    recent_date = datetime.now(UTC) + timedelta(days=1)
    old_id = uuid.uuid4()
    recent_id = uuid.uuid4()

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(PlatformOutboxEvent(
            id=old_id,
            aggregate_type="t",
            aggregate_id=uuid.uuid4(),
            event_type="Old",
            payload={},
            occurred_at=old_date,
            published_at=old_date,
        ))
        s.add(PlatformOutboxEvent(
            id=recent_id,
            aggregate_type="t",
            aggregate_id=uuid.uuid4(),
            event_type="Recent",
            payload={},
            occurred_at=recent_date,
            published_at=recent_date,
        ))

    deleted = await _purge("platform", PlatformOutboxEvent, cutoff, test_engine)
    assert deleted >= 1  # at least our old row was deleted

    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        old_row = (
            await s.execute(
                select(PlatformOutboxEvent).where(PlatformOutboxEvent.id == old_id)
            )
        ).scalar_one_or_none()
        recent_row = (
            await s.execute(
                select(PlatformOutboxEvent).where(PlatformOutboxEvent.id == recent_id)
            )
        ).scalar_one_or_none()

    assert old_row is None
    assert recent_row is not None


async def test_purge_ignores_unpublished_rows(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    # Use a past cutoff so unpublished rows would be caught IF the filter is wrong
    cutoff = datetime.now(UTC) - timedelta(days=1)
    old_date = cutoff - timedelta(days=100)
    unpublished_id = uuid.uuid4()

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(PlatformOutboxEvent(
            id=unpublished_id,
            aggregate_type="t",
            aggregate_id=uuid.uuid4(),
            event_type="Unpublished",
            payload={},
            occurred_at=old_date,
            published_at=None,
        ))

    deleted = await _purge("platform", PlatformOutboxEvent, cutoff, test_engine)
    assert deleted == 0

    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        row = (
            await s.execute(
                select(PlatformOutboxEvent).where(PlatformOutboxEvent.id == unpublished_id)
            )
        ).scalar_one_or_none()
    assert row is not None
