"""Tests for the audit-log query service + endpoints."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.db import (
    get_platform_session,
    get_session_for_tenant_schema,
    get_tenant_session,
)
from app.main import app, lifespan
from app.platform_.audit.service import AuditQueryService
from app.platform_.models import PlatformUser

TEST_TENANT_SCHEMA = "tenant_test"


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


def _make_tenant_schema_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


async def _create_platform_user(factory: async_sessionmaker[AsyncSession]) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"op-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Op",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup_platform(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.execute(text("DELETE FROM platform.platform_users"))


async def test_query_filters_by_record_and_paginates(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    rid = uuid.uuid4()
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            for i in range(3):
                s.add(
                    PlatformAuditLog(
                        table_name="tenants",
                        record_id=rid,
                        operation="update",
                        actor_type="platform_user",
                        actor_id=uuid.uuid4(),
                        actor_label="op@test",
                        before_state={"a": i},
                        after_state={"a": i + 1},
                        occurred_at=datetime.now(UTC),
                    )
                )
            s.add(
                PlatformAuditLog(
                    table_name="tenants",
                    record_id=uuid.uuid4(),
                    operation="insert",
                    actor_type="system",
                    occurred_at=datetime.now(UTC),
                )
            )
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = AuditQueryService(s, PlatformAuditLog)
            rows, total = await svc.query(record_id=rid, page=1, page_size=2)
            assert total == 3
            assert len(rows) == 2
            rows2, total2 = await svc.query(operation="insert", page=1, page_size=10)
            assert total2 == 1
            assert rows2[0].actor_type == "system"
    finally:
        await _cleanup_platform(factory)


async def test_platform_audit_endpoint_lists_and_filters(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    rid = uuid.uuid4()
    actor = await _create_platform_user(factory)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            for i in range(2):
                s.add(
                    PlatformAuditLog(
                        table_name="tenants",
                        record_id=rid,
                        operation="update",
                        actor_type="platform_user",
                        actor_id=actor.id,
                        actor_label="op@test",
                        before_state={"a": i},
                        after_state={"a": i + 1},
                        occurred_at=datetime.now(UTC),
                    )
                )
        app.dependency_overrides[get_platform_session] = _make_platform_session_override(
            test_engine
        )
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get(
                    f"/platform/audit-log?table_name=tenants&record_id={rid}&page_size=10",
                    headers={"X-Platform-Actor-ID": str(actor.id)},
                )
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["total"] == 2
                assert len(body["items"]) == 2
                assert body["items"][0]["table_name"] == "tenants"
                assert body["items"][0]["impersonation_id"] is None
    finally:
        app.dependency_overrides.clear()
        await _cleanup_platform(factory)


async def _seed_tenant_user(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        uid = uuid.uuid4()
        await s.execute(
            text(
                "INSERT INTO tenant_users "
                "(id, email, full_name, is_active, is_admin, created_at, updated_at) "
                "VALUES (:id, :email, 'Op', true, true, now(), now())"
            ),
            {"id": uid, "email": f"op-{uid.hex[:6]}@test.example"},
        )
    return uid


async def test_operator_audit_endpoint_lists_own_tenant(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    rid = uuid.uuid4()
    actor_id = await _seed_tenant_user(factory)
    try:
        async with factory() as s, s.begin():
            await s.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
            for op in ("insert", "update"):
                s.add(
                    TenantAuditLog(
                        table_name="members",
                        record_id=rid,
                        operation=op,
                        actor_type="tenant_user",
                        actor_id=actor_id,
                        actor_label="op@test",
                        before_state=None,
                        after_state={"status": "active"},
                        occurred_at=datetime.now(UTC),
                    )
                )
        app.dependency_overrides[get_tenant_session] = _make_tenant_schema_override(test_engine)
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get(
                    f"/audit-log?record_id={rid}&page_size=10",
                    headers={
                        "X-Tenant-Slug": "test-tenant",
                        "X-Tenant-Actor-ID": str(actor_id),
                    },
                )
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["total"] == 2
                assert {i["operation"] for i in body["items"]} == {"insert", "update"}
                r2 = await client.get(
                    f"/audit-log?record_id={rid}&operation=update",
                    headers={
                        "X-Tenant-Slug": "test-tenant",
                        "X-Tenant-Actor-ID": str(actor_id),
                    },
                )
                assert r2.json()["total"] == 1
    finally:
        app.dependency_overrides.clear()
        async with factory() as s, s.begin():
            await s.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
            await s.execute(text(f"DELETE FROM {TEST_TENANT_SCHEMA}.audit_log"))  # noqa: S608
            await s.execute(
                text(f"DELETE FROM {TEST_TENANT_SCHEMA}.tenant_users WHERE id = :id"),  # noqa: S608
                {"id": actor_id},
            )


async def test_tenant_audit_endpoint_surfaces_impersonation_id(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    rid = uuid.uuid4()
    imp = uuid.uuid4()
    actor = await _create_platform_user(factory)
    try:
        async with factory() as s, s.begin():
            await s.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
            s.add(
                TenantAuditLog(
                    table_name="members",
                    record_id=rid,
                    operation="update",
                    actor_type="tenant_user",
                    actor_id=uuid.uuid4(),
                    actor_label="shadow (impersonating)",
                    before_state={"status": "active"},
                    after_state={"status": "dormant"},
                    occurred_at=datetime.now(UTC),
                    impersonation_id=imp,
                )
            )
        app.dependency_overrides[get_session_for_tenant_schema] = _make_tenant_schema_override(
            test_engine
        )
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get(
                    f"/platform/tenants/{uuid.uuid4()}/audit-log?record_id={rid}",
                    headers={"X-Platform-Actor-ID": str(actor.id)},
                )
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["total"] == 1
                assert body["items"][0]["impersonation_id"] == str(imp)
    finally:
        app.dependency_overrides.clear()
        async with factory() as s, s.begin():
            await s.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
            await s.execute(text(f"DELETE FROM {TEST_TENANT_SCHEMA}.audit_log"))  # noqa: S608
        await _cleanup_platform(factory)
