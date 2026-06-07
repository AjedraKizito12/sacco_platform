"""get_session_for_tenant_schema looks up the tenant by UUID, validates the
schema_name, and yields a session with search_path set. NOT subscription-gated
— platform admins must be able to manage users in any tenant state.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_session_for_tenant_schema
from app.platform_.models import Tenant


async def _seed_tenant(
    factory: async_sessionmaker[AsyncSession], schema: str, *, is_active: bool = True,
) -> Tenant:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=schema,
            name="T",
            is_active=is_active,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(t)
    return t


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.tenants"))


async def test_yields_session_with_search_path_set(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    tenant = await _seed_tenant(factory, "tenant_test")
    try:
        gen = get_session_for_tenant_schema(tenant.id)
        session = await gen.__anext__()
        try:
            row = await session.execute(text("SHOW search_path"))
            sp = row.scalar()
            assert "tenant_test" in str(sp)
        finally:
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
    finally:
        await _cleanup(factory)


async def test_404_when_tenant_unknown(test_engine: AsyncEngine) -> None:
    gen = get_session_for_tenant_schema(uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        await gen.__anext__()
    assert exc.value.status_code == 404


async def test_404_when_tenant_inactive(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    tenant = await _seed_tenant(factory, "tenant_test", is_active=False)
    try:
        gen = get_session_for_tenant_schema(tenant.id)
        with pytest.raises(HTTPException) as exc:
            await gen.__anext__()
        assert exc.value.status_code == 404
    finally:
        await _cleanup(factory)


async def test_500_when_schema_name_malformed(test_engine: AsyncEngine) -> None:
    """Defense in depth: even if the DB returns a malformed schema_name
    (data corruption), the dep refuses to SET search_path.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    # Bypass the model's validation by inserting directly via SQL.
    bad_id = uuid.uuid4()
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(
            text(
                "INSERT INTO platform.tenants "
                "(id, slug, schema_name, name, status, is_active, "
                "subscription_status, seed_version, created_at, updated_at) "
                "VALUES (:id, :slug, 'evil; DROP SCHEMA tenant_test CASCADE; --', "
                "'evil', 'active', true, 'pending', 1, now(), now())"
            ),
            {"id": bad_id, "slug": f"evil-{bad_id.hex[:6]}"},
        )
    try:
        gen = get_session_for_tenant_schema(bad_id)
        with pytest.raises(HTTPException) as exc:
            await gen.__anext__()
        assert exc.value.status_code == 500
    finally:
        await _cleanup(factory)
