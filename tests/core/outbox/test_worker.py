"""
Outbox worker integration tests.
These tests call _relay_outbox() directly with a mocked RabbitMQ exchange.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.outbox.models import TenantOutboxEvent
from app.core.outbox.worker import _MAX_ATTEMPTS, _next_attempt_delta, _relay_outbox

_SEARCH_PATH = "tenant_test, platform"


def _make_event(**overrides):
    """Helper: create a TenantOutboxEvent (not yet added to session)."""
    defaults = dict(
        aggregate_type="loan",
        aggregate_id=uuid.uuid4(),
        event_type="LoanDisbursed",
        payload={"amount": 100},
        occurred_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return TenantOutboxEvent(**defaults)


@pytest.fixture
def mock_exchange():
    exchange = AsyncMock()
    exchange.publish = AsyncMock()
    return exchange


@pytest.fixture
def mock_aio_pika(mock_exchange):
    """Patch aio_pika.connect_robust so _relay_outbox never hits real RabbitMQ."""
    channel = AsyncMock()
    channel.declare_exchange = AsyncMock(return_value=mock_exchange)
    conn = AsyncMock()
    conn.channel = AsyncMock(return_value=channel)
    conn.close = AsyncMock()
    with patch("app.core.outbox.worker.aio_pika") as mock:
        mock.connect_robust = AsyncMock(return_value=conn)
        mock.ExchangeType.TOPIC = "topic"
        mock.Message = MagicMock(side_effect=lambda **kw: MagicMock())
        mock.DeliveryMode.PERSISTENT = 2
        yield mock, mock_exchange


async def _insert_committed(engine, *events):
    """Insert events in a committed transaction and return their IDs."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {_SEARCH_PATH}"))
        for ev in events:
            s.add(ev)
    return [ev.id for ev in events]


async def _fetch_row(engine, event_id):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET LOCAL search_path TO {_SEARCH_PATH}"))
        return (
            await s.execute(
                select(TenantOutboxEvent).where(TenantOutboxEvent.id == event_id)
            )
        ).scalar_one()


async def test_happy_path_marks_published(test_engine, mock_aio_pika):
    """Published events have published_at set and exchange.publish is called."""
    _, exchange = mock_aio_pika
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    event = _make_event()
    await _insert_committed(test_engine, event)

    async with factory() as s:
        await _relay_outbox(
            s, TenantOutboxEvent, "test-tenant", "amqp://",
            search_path=_SEARCH_PATH,
        )

    row = await _fetch_row(test_engine, event.id)
    assert row.published_at is not None
    assert exchange.publish.called


async def test_skip_locked_prevents_double_publish(test_engine, mock_aio_pika):
    """Two concurrent relay calls must each publish a row exactly once."""
    _, exchange = mock_aio_pika
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    ev_a = _make_event(event_type="EventA")
    ev_b = _make_event(event_type="EventB")
    ids = await _insert_committed(test_engine, ev_a, ev_b)

    async def relay():
        async with factory() as s:
            await _relay_outbox(
                s, TenantOutboxEvent, "test-tenant", "amqp://",
                search_path=_SEARCH_PATH,
            )

    await asyncio.gather(relay(), relay())

    async with factory() as s:
        await s.execute(text(f"SET LOCAL search_path TO {_SEARCH_PATH}"))
        rows = (
            await s.execute(
                select(TenantOutboxEvent).where(TenantOutboxEvent.id.in_(ids))
            )
        ).scalars().all()

    published = [r for r in rows if r.published_at is not None]
    assert len(published) == 2
    assert exchange.publish.call_count == 2


async def test_publish_failure_sets_backoff(test_engine, mock_aio_pika):
    """A publish failure increments attempts, sets next_attempt_at, no dead-lettering yet."""
    _, exchange = mock_aio_pika
    exchange.publish.side_effect = Exception("connection refused")
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    event = _make_event()
    await _insert_committed(test_engine, event)

    async with factory() as s:
        await _relay_outbox(
            s, TenantOutboxEvent, "test-tenant", "amqp://",
            search_path=_SEARCH_PATH,
        )

    row = await _fetch_row(test_engine, event.id)
    assert row.published_at is None
    assert row.attempts == 1
    assert row.next_attempt_at is not None
    assert row.next_attempt_at > datetime.now(UTC)
    assert row.is_dead_lettered is False


async def test_dead_lettering_after_max_attempts(test_engine, mock_aio_pika):
    """After reaching _MAX_ATTEMPTS failures the row is marked is_dead_lettered."""
    _, exchange = mock_aio_pika
    exchange.publish.side_effect = Exception("always fails")
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    event = _make_event(attempts=_MAX_ATTEMPTS - 1)
    await _insert_committed(test_engine, event)

    async with factory() as s:
        await _relay_outbox(
            s, TenantOutboxEvent, "test-tenant", "amqp://",
            search_path=_SEARCH_PATH,
        )

    row = await _fetch_row(test_engine, event.id)
    assert row.is_dead_lettered is True


def test_backoff_formula():
    assert _next_attempt_delta(0).total_seconds() == 30
    assert _next_attempt_delta(1).total_seconds() == 60
    assert _next_attempt_delta(7).total_seconds() == 3600  # capped at 1 hour
    assert _next_attempt_delta(20).total_seconds() == 3600  # still capped
