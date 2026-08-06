"""Integration tests for the Phase 7 offboarding endpoints:
POST /cancel (maker-checker q=2), /restore, /extend-retention, GET /lifecycle.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.platform_.tenants.executors  # noqa: F401 — register executors
from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.models import PlatformUser, Tenant


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


async def _create_user(
    factory: async_sessionmaker[AsyncSession],
    *,
    prefix: str,
    role: str = "support",
    is_superuser: bool = False,
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"{prefix}-{uuid.uuid4().hex[:6]}@test.example",
            full_name=prefix.title(),
            role=role,
            is_active=True,
            is_superuser=is_superuser,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _create_tenant(
    factory: async_sessionmaker[AsyncSession], **overrides: object
) -> Tenant:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Offboard Co",
            status="active",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        for k, v in overrides.items():
            setattr(t, k, v)
        s.add(t)
    return t


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.tenant_lifecycle_events"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_platform_session] = (
        _make_platform_session_override(test_engine)
    )
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


async def test_cancel_submits_approval(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_user(factory, prefix="su", is_superuser=True)
    tenant = await _create_tenant(factory)
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/cancel",
            json={"reason": "Customer terminated the contract"},
            headers=_hdr(maker.id),
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "pending_approval"
        assert "approval_request_id" in body
    finally:
        await _cleanup(factory)


async def test_cancel_forbidden_for_non_superuser(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    admin = await _create_user(factory, prefix="admin", role="admin")
    tenant = await _create_tenant(factory)
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/cancel",
            json={"reason": "Customer terminated the contract"},
            headers=_hdr(admin.id),
        )
        assert r.status_code == 403, r.text
    finally:
        await _cleanup(factory)


async def test_cancel_rejects_non_active(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_user(factory, prefix="su", is_superuser=True)
    tenant = await _create_tenant(factory, lifecycle_state="cancelled")
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/cancel",
            json={"reason": "Customer terminated the contract"},
            headers=_hdr(maker.id),
        )
        assert r.status_code == 409, r.text
    finally:
        await _cleanup(factory)


async def test_cancel_end_to_end_two_approvals(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_user(factory, prefix="maker", is_superuser=True)
    checker1 = await _create_user(factory, prefix="chk1", is_superuser=True)
    checker2 = await _create_user(factory, prefix="chk2", is_superuser=True)
    tenant = await _create_tenant(factory)
    try:
        sub = await client.post(
            f"/platform/tenants/{tenant.id}/cancel",
            json={"reason": "Customer terminated the contract"},
            headers=_hdr(maker.id),
        )
        approval_id = sub.json()["approval_request_id"]

        a1 = await client.post(
            f"/platform/approvals/{approval_id}/approve",
            json={"comment": "ok"},
            headers=_hdr(checker1.id),
        )
        assert a1.status_code == 200, a1.text
        a2 = await client.post(
            f"/platform/approvals/{approval_id}/approve",
            json={"comment": "ok"},
            headers=_hdr(checker2.id),
        )
        assert a2.status_code == 200, a2.text
        assert a2.json()["status"] == "executed"

        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.lifecycle_state == "cancelled"
            assert t.cancelled_at is not None
    finally:
        await _cleanup(factory)


async def test_restore_flips_cancelled_to_active(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    su = await _create_user(factory, prefix="su", is_superuser=True)
    tenant = await _create_tenant(
        factory, lifecycle_state="cancelled", cancelled_at=datetime.now(UTC)
    )
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/restore", headers=_hdr(su.id)
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["lifecycle_state"] == "active"
        assert body["cancelled_at"] is None
    finally:
        await _cleanup(factory)


async def test_restore_on_archived_returns_409(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    su = await _create_user(factory, prefix="su", is_superuser=True)
    tenant = await _create_tenant(
        factory, lifecycle_state="archived", archive_checksum="sha256:abc"
    )
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/restore", headers=_hdr(su.id)
        )
        assert r.status_code == 409, r.text
    finally:
        await _cleanup(factory)


async def test_extend_retention_sets_hold(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    su = await _create_user(factory, prefix="su", is_superuser=True)
    tenant = await _create_tenant(factory, lifecycle_state="read_only")
    hold = datetime.now(UTC) + timedelta(days=45)
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/extend-retention",
            json={"hold_until": hold.isoformat()},
            headers=_hdr(su.id),
        )
        assert r.status_code == 200, r.text
        assert r.json()["retention_hold_until"] is not None
    finally:
        await _cleanup(factory)


async def test_lifecycle_returns_timeline(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    su = await _create_user(factory, prefix="su", is_superuser=True)
    tenant = await _create_tenant(
        factory, lifecycle_state="cancelled", cancelled_at=datetime.now(UTC)
    )
    try:
        # Produce one event via restore.
        await client.post(
            f"/platform/tenants/{tenant.id}/restore", headers=_hdr(su.id)
        )
        r = await client.get(
            f"/platform/tenants/{tenant.id}/lifecycle", headers=_hdr(su.id)
        )
        assert r.status_code == 200, r.text
        events = r.json()
        assert len(events) >= 1
        assert events[-1]["to_state"] == "active"
        assert "metadata" in events[-1]
    finally:
        await _cleanup(factory)
