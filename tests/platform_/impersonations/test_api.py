"""HTTP integration tests for /platform/impersonations/*.

Uses stub auth + the platform session override pattern from
tests/platform_/billing/test_api_invoices.py.

Note: the mint-tenant-token endpoint requires a real signing key in the DB.
The dedicated end-to-end test in test_end_to_end.py exercises that path.
These tests focus on the lifecycle endpoints (submit/list/get/end/revoke).
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.platform_.impersonations.executors  # noqa: F401
from app.core.db import get_platform_session
from app.main import app, lifespan
from app.modules.maker_checker.service import ApprovalService
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.service import ImpersonationService
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


async def _seed(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[PlatformUser, PlatformUser, Tenant]:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        maker = PlatformUser(
            email=f"maker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Maker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        checker = PlatformUser(
            email=f"checker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Checker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        tenant = Tenant(
            slug=f"t-{uuid.uuid4().hex[:6]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:6]}",
            name="T", is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add_all([maker, checker, tenant])
    return maker, checker, tenant


async def _seed_extra_user(
    factory: async_sessionmaker[AsyncSession],
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"x-{uuid.uuid4().hex[:6]}@test.example",
            full_name="X", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _approve(
    factory: async_sessionmaker[AsyncSession],
    maker_id: uuid.UUID, checker_id: uuid.UUID, tenant_id: uuid.UUID,
) -> uuid.UUID:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        approval = await ImpersonationService(s).request(
            platform_user_id=maker_id, tenant_id=tenant_id,
            reason="Investigating reported issue with member balance",
        )
        approval_id = approval.id
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        executed = await ApprovalService(s).approve(
            request_id=approval_id, actor_user_id=checker_id,
        )
        return uuid.UUID(executed.execution_result["impersonation_id"])  # type: ignore[index]


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.support_impersonations"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


async def test_post_submit_returns_approval_request(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, _checker, tenant = await _seed(factory)
    try:
        r = await client.post(
            "/platform/impersonations",
            json={
                "tenant_id": str(tenant.id),
                "reason": "Investigating member balance reported by tenant admin",
            },
            headers=_hdr(maker.id),
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert "approval_request_id" in body
        assert body["status"] == "pending_approval"
    finally:
        await _cleanup(factory)


async def test_post_submit_rejects_short_reason(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, _, tenant = await _seed(factory)
    try:
        r = await client.post(
            "/platform/impersonations",
            json={"tenant_id": str(tenant.id), "reason": "short"},
            headers=_hdr(maker.id),
        )
        # Pydantic rejects at the validator layer
        assert r.status_code == 422, r.text
    finally:
        await _cleanup(factory)


async def test_get_active_returns_only_mine(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    other = await _seed_extra_user(factory)
    await _approve(factory, maker.id, checker.id, tenant.id)
    await _approve(factory, other.id, checker.id, tenant.id)
    try:
        r = await client.get("/platform/impersonations/active", headers=_hdr(maker.id))
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["platform_user_id"] == str(maker.id)
    finally:
        await _cleanup(factory)


async def test_get_all_returns_every_active(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    other = await _seed_extra_user(factory)
    await _approve(factory, maker.id, checker.id, tenant.id)
    await _approve(factory, other.id, checker.id, tenant.id)
    try:
        r = await client.get("/platform/impersonations/all", headers=_hdr(maker.id))
        assert r.status_code == 200
        assert len(r.json()) == 2
    finally:
        await _cleanup(factory)


async def test_delete_marks_ended_by_owner(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    imp_id = await _approve(factory, maker.id, checker.id, tenant.id)
    try:
        r = await client.delete(
            f"/platform/impersonations/{imp_id}", headers=_hdr(maker.id),
        )
        assert r.status_code == 204, r.text

        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, imp_id)
            assert row is not None
            assert row.ended_at is not None
            assert row.ended_by == maker.id
    finally:
        await _cleanup(factory)


async def test_delete_rejects_non_owner(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    other = await _seed_extra_user(factory)
    imp_id = await _approve(factory, maker.id, checker.id, tenant.id)
    try:
        r = await client.delete(
            f"/platform/impersonations/{imp_id}", headers=_hdr(other.id),
        )
        assert r.status_code == 403, r.text
    finally:
        await _cleanup(factory)


async def test_revoke_by_other_user(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    revoker = await _seed_extra_user(factory)
    imp_id = await _approve(factory, maker.id, checker.id, tenant.id)
    try:
        r = await client.post(
            f"/platform/impersonations/{imp_id}/revoke",
            json={"reason": "policy violation"},
            headers=_hdr(revoker.id),
        )
        assert r.status_code == 204, r.text
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, imp_id)
            assert row is not None
            assert row.revoked_at is not None
            assert row.revoked_by == revoker.id
    finally:
        await _cleanup(factory)
