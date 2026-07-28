"""Integration tests for /platform/ops/backups (superuser-only).

Stub platform auth (X-Platform-Actor-ID) + a get_platform_session override
bound to the test engine, mirroring tenant_users_admin/test_api.py.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.models import PlatformUser
from app.platform_.ops.models import BackupRun, BackupVerification


def _make_platform_session_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


async def _create_platform_user(
    factory: async_sessionmaker[AsyncSession], *, superuser: bool
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"{'super' if superuser else 'support'}-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Ops Tester",
            is_active=True,
            is_superuser=superuser,
            role="superuser" if superuser else "support",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.backup_verifications"))
        await s.execute(text("DELETE FROM platform.backup_runs"))
        await s.execute(text("DELETE FROM platform.platform_users"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_platform_session] = (
        _make_platform_session_override(test_engine)
    )
    try:
        async with lifespan(app), AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
    except Exception:  # noqa: BLE001, S110
        pass
    finally:
        app.dependency_overrides.pop(get_platform_session, None)


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


async def test_get_backups_returns_runs_and_latest_verification(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_user(factory, superuser=True)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(
            BackupRun(
                backup_type="full",
                status="succeeded",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                repo_size_bytes=1234,
            )
        )
        s.add(
            BackupVerification(
                status="passed",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
    try:
        r = await client.get("/platform/ops/backups", headers=_hdr(actor.id))
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["recent_runs"]) == 1
        assert body["recent_runs"][0]["backup_type"] == "full"
        assert body["recent_runs"][0]["repo_size_bytes"] == 1234
        assert body["latest_verification"]["status"] == "passed"
    finally:
        await _cleanup(factory)


async def test_last_verified_at_returns_passed_finished_at(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_user(factory, superuser=True)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(
            BackupVerification(
                status="passed",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
    try:
        r = await client.get(
            "/platform/ops/backups/last-verified-at", headers=_hdr(actor.id)
        )
        assert r.status_code == 200, r.text
        assert r.json()["last_verified_at"] is not None
    finally:
        await _cleanup(factory)


async def test_last_verified_at_null_when_none_passed(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_user(factory, superuser=True)
    try:
        r = await client.get(
            "/platform/ops/backups/last-verified-at", headers=_hdr(actor.id)
        )
        assert r.status_code == 200, r.text
        assert r.json()["last_verified_at"] is None
    finally:
        await _cleanup(factory)


async def test_trigger_then_conflict(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_user(factory, superuser=True)
    try:
        r1 = await client.post(
            "/platform/ops/backups/trigger-verification", headers=_hdr(actor.id)
        )
        assert r1.status_code == 201, r1.text
        assert r1.json()["status"] == "requested"
        r2 = await client.post(
            "/platform/ops/backups/trigger-verification", headers=_hdr(actor.id)
        )
        assert r2.status_code == 409
    finally:
        await _cleanup(factory)


async def test_backups_requires_superuser(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    support = await _create_platform_user(factory, superuser=False)
    try:
        r = await client.get("/platform/ops/backups", headers=_hdr(support.id))
        assert r.status_code == 403
    finally:
        await _cleanup(factory)
