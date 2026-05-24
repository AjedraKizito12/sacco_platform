"""Tests for PlatformSession / TenantSession models and SessionService.

These tests use ``async_sessionmaker`` + ``commit()`` + manual cleanup rather
than the ``platform_session`` / ``tenant_session`` fixtures.  The connection-
bound session in those fixtures conflicts with asyncpg when ``flush()`` is
called inside an explicitly-begun transaction — the same asyncpg pipelining
issue documented in test_key_service.py.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.iam.sessions.models import PlatformSession, TenantSession
from app.modules.iam.sessions.service import SessionService


# ── Factory helpers ─────────────────────────────────────────────────────────

def _platform_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    f = async_sessionmaker(engine, expire_on_commit=False)
    return f


def _tenant_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _cleanup_platform(engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await s.execute(text("SET search_path TO platform"))
        await s.execute(delete(PlatformSession))
        await s.commit()


async def _cleanup_tenant(engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await s.execute(text("SET search_path TO tenant_test, platform"))
        await s.execute(delete(TenantSession))
        await s.commit()


def _platform_svc(session: AsyncSession, redis: object | None = None) -> SessionService:
    return SessionService(db=session, model_cls=PlatformSession, redis=redis)


def _tenant_svc(session: AsyncSession, redis: object | None = None) -> SessionService:
    return SessionService(db=session, model_cls=TenantSession, redis=redis)


# ── model persistence ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_platform_session_model_persists(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            row = PlatformSession(
                platform_user_id=uuid.uuid4(),
                jti="test-jti-001",
                user_agent="pytest/1.0",
                ip_address="127.0.0.1",
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            session.add(row)
            await session.commit()

            result = await session.execute(
                select(PlatformSession).where(PlatformSession.jti == "test-jti-001")
            )
            fetched = result.scalar_one()
            assert isinstance(fetched.id, uuid.UUID)
            assert fetched.revoked_at is None
            assert fetched.last_used_at is None
    finally:
        await _cleanup_platform(test_engine)


@pytest.mark.anyio
async def test_tenant_session_model_persists(test_engine: AsyncEngine):
    factory = _tenant_factory(test_engine)
    try:
        async with factory() as session:
            # Use SET LOCAL so the path stays for the whole transaction.
            # Do not commit mid-test — flush is enough to make the row visible.
            await session.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            row = TenantSession(
                tenant_user_id=uuid.uuid4(),
                jti="test-jti-002",
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(hours=8),
            )
            session.add(row)
            await session.flush()  # visible within the same transaction

            result = await session.execute(
                select(TenantSession).where(TenantSession.jti == "test-jti-002")
            )
            fetched = result.scalar_one()
            assert isinstance(fetched.id, uuid.UUID)
            assert fetched.tenant_user_id is not None
    finally:
        await _cleanup_tenant(test_engine)


# ── create ──────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_create_platform_session_inserts_row(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            user_id = uuid.uuid4()
            svc = _platform_svc(session)

            row = await svc.create(
                user_id=user_id,
                jti="jti-platform-001",
                user_agent="Mozilla/5.0",
                ip_address="10.0.0.1",
                refresh_ttl_seconds=3600,
            )
            await session.commit()

            assert isinstance(row.id, uuid.UUID)
            assert row.platform_user_id == user_id
            assert row.jti == "jti-platform-001"
            assert row.revoked_at is None
            assert row.expires_at > row.created_at
    finally:
        await _cleanup_platform(test_engine)


@pytest.mark.anyio
async def test_create_tenant_session_inserts_row(test_engine: AsyncEngine):
    factory = _tenant_factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO tenant_test, platform"))
            user_id = uuid.uuid4()
            svc = _tenant_svc(session)

            row = await svc.create(
                user_id=user_id,
                jti="jti-tenant-001",
                user_agent=None,
                ip_address=None,
                refresh_ttl_seconds=28800,
            )
            await session.commit()

            assert row.tenant_user_id == user_id
            assert row.jti == "jti-tenant-001"
    finally:
        await _cleanup_tenant(test_engine)


@pytest.mark.anyio
async def test_create_calls_redis_set_with_ttl(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session, redis=mock_redis)

            await svc.create(
                user_id=uuid.uuid4(),
                jti="jti-redis-test",
                user_agent=None,
                ip_address=None,
                refresh_ttl_seconds=3600,
            )
            await session.commit()

        mock_redis.set.assert_called_once_with(
            "iam:jti:jti-redis-test", "1", ex=3600
        )
    finally:
        await _cleanup_platform(test_engine)


@pytest.mark.anyio
async def test_create_without_redis_does_not_raise(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session, redis=None)
            row = await svc.create(
                user_id=uuid.uuid4(),
                jti="jti-no-redis",
                user_agent=None,
                ip_address=None,
                refresh_ttl_seconds=3600,
            )
            await session.commit()
            assert row.jti == "jti-no-redis"
    finally:
        await _cleanup_platform(test_engine)


# ── get_by_session_id ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_by_session_id_returns_existing_row(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session)
            row = await svc.create(
                user_id=uuid.uuid4(), jti="jti-get-001",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()

            fetched = await svc.get_by_session_id(row.id)
            assert fetched is not None
            assert fetched.id == row.id
    finally:
        await _cleanup_platform(test_engine)


@pytest.mark.anyio
async def test_get_by_session_id_returns_none_for_missing(test_engine: AsyncEngine):
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as session:
        await session.execute(text("SET search_path TO platform"))
        svc = _platform_svc(session)
        result = await svc.get_by_session_id(uuid.uuid4())
        assert result is None


# ── revoke ───────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_revoke_sets_revoked_at(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session)
            row = await svc.create(
                user_id=uuid.uuid4(), jti="jti-revoke-001",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()

            await svc.revoke(row.id)
            await session.commit()

            await session.refresh(row)
            assert row.revoked_at is not None
    finally:
        await _cleanup_platform(test_engine)


@pytest.mark.anyio
async def test_revoke_deletes_redis_jti(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.delete = AsyncMock()
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session, redis=mock_redis)

            row = await svc.create(
                user_id=uuid.uuid4(), jti="jti-revoke-redis",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()

            await svc.revoke(row.id)
            await session.commit()

        mock_redis.delete.assert_called_once_with("iam:jti:jti-revoke-redis")
    finally:
        await _cleanup_platform(test_engine)


@pytest.mark.anyio
async def test_revoke_is_idempotent(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session)
            row = await svc.create(
                user_id=uuid.uuid4(), jti="jti-revoke-idem",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()

            await svc.revoke(row.id)
            await session.commit()
            await svc.revoke(row.id)  # second call must not raise or change revoked_at
            await session.commit()

            await session.refresh(row)
            assert row.revoked_at is not None
    finally:
        await _cleanup_platform(test_engine)


# ── revoke_all_for_user ──────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_revoke_all_for_user_revokes_all_active_sessions(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        user_id = uuid.uuid4()
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session)

            s1 = await svc.create(
                user_id=user_id, jti="jti-bulk-001",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            s2 = await svc.create(
                user_id=user_id, jti="jti-bulk-002",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()

            count = await svc.revoke_all_for_user(user_id)
            await session.commit()

            assert count == 2
            await session.refresh(s1)
            await session.refresh(s2)
            assert s1.revoked_at is not None
            assert s2.revoked_at is not None
    finally:
        await _cleanup_platform(test_engine)


@pytest.mark.anyio
async def test_revoke_all_for_user_skips_already_revoked_sessions(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        user_id = uuid.uuid4()
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session)

            s1 = await svc.create(
                user_id=user_id, jti="jti-bulk-skip-001",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()
            await svc.revoke(s1.id)
            await session.commit()

            s2 = await svc.create(
                user_id=user_id, jti="jti-bulk-skip-002",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()

            count = await svc.revoke_all_for_user(user_id)
            assert count == 1  # only the non-revoked session
    finally:
        await _cleanup_platform(test_engine)


# ── cleanup_expired ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_cleanup_expired_deletes_rows_past_retention(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        user_id = uuid.uuid4()
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session)

            # Session that expired 8 days ago — should be deleted.
            old = await svc.create(
                user_id=user_id, jti="jti-expired-old",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()
            old.expires_at = datetime.now(UTC) - timedelta(days=8)
            await session.commit()

            # Session that expired 1 day ago — still within 7-day retention window.
            recent = await svc.create(
                user_id=user_id, jti="jti-expired-recent",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()
            recent.expires_at = datetime.now(UTC) - timedelta(days=1)
            await session.commit()

            deleted = await svc.cleanup_expired()
            await session.commit()

            assert deleted == 1

            result = await session.execute(
                select(PlatformSession).where(PlatformSession.jti == "jti-expired-old")
            )
            assert result.scalar_one_or_none() is None

            result = await session.execute(
                select(PlatformSession).where(PlatformSession.jti == "jti-expired-recent")
            )
            assert result.scalar_one_or_none() is not None
    finally:
        await _cleanup_platform(test_engine)


# ── is_jti_valid ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_is_jti_valid_returns_true_when_redis_has_key(test_engine: AsyncEngine):
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as session:
        await session.execute(text("SET search_path TO platform"))
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)
        svc = _platform_svc(session, redis=mock_redis)

        assert await svc.is_jti_valid("jti-exists") is True
        mock_redis.exists.assert_called_once_with("iam:jti:jti-exists")


@pytest.mark.anyio
async def test_is_jti_valid_returns_false_when_redis_missing_key(test_engine: AsyncEngine):
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as session:
        await session.execute(text("SET search_path TO platform"))
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)
        svc = _platform_svc(session, redis=mock_redis)

        assert await svc.is_jti_valid("jti-missing") is False


@pytest.mark.anyio
async def test_is_jti_valid_falls_back_to_db_when_redis_is_none(test_engine: AsyncEngine):
    """When Redis is unavailable, fall back to DB lookup.

    A session row that exists and is not revoked and not expired is valid.
    """
    factory = _platform_factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session, redis=None)
            await svc.create(
                user_id=uuid.uuid4(), jti="jti-db-fallback",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()

            assert await svc.is_jti_valid("jti-db-fallback") is True
    finally:
        await _cleanup_platform(test_engine)


@pytest.mark.anyio
async def test_is_jti_valid_db_fallback_returns_false_for_revoked(test_engine: AsyncEngine):
    factory = _platform_factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            svc = _platform_svc(session, redis=None)
            row = await svc.create(
                user_id=uuid.uuid4(), jti="jti-db-revoked",
                user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
            )
            await session.commit()
            await svc.revoke(row.id)
            await session.commit()

            assert await svc.is_jti_valid("jti-db-revoked") is False
    finally:
        await _cleanup_platform(test_engine)
