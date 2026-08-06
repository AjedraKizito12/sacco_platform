"""Offboarding gate tests — verifies _check_offboarding_gate maps each
lifecycle_state (+ HTTP method) to allow or the right HTTPException.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.core.db as _db_module
from app.core.db import _check_offboarding_gate
from app.platform_.models import Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(
    factory: async_sessionmaker[AsyncSession], slug: str, lifecycle_state: str = "active"
) -> None:
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        s.add(
            Tenant(
                slug=slug,
                schema_name=f"tenant_{slug.replace('-', '_')}",
                name="Offboard Gate Test",
                is_active=True,
                lifecycle_state=lifecycle_state,
                created_at=now,
                updated_at=now,
            )
        )
        await s.commit()


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s:
        await _set_platform(s)
        await s.execute(delete(Tenant))
        await s.commit()


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    _db_module.engine = test_engine
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_active_allows_reads_and_writes(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    slug = f"og-active-{uuid.uuid4().hex[:6]}"
    await _make_tenant(factory, slug, "active")
    try:
        await _check_offboarding_gate(slug, "GET")
        await _check_offboarding_gate(slug, "POST")
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_read_only_allows_get_blocks_write(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    slug = f"og-ro-{uuid.uuid4().hex[:6]}"
    await _make_tenant(factory, slug, "read_only")
    try:
        await _check_offboarding_gate(slug, "GET")
        await _check_offboarding_gate(slug, "HEAD")
        with pytest.raises(HTTPException) as exc:
            await _check_offboarding_gate(slug, "POST")
        assert exc.value.status_code == 403
        assert "read-only" in str(exc.value.detail).lower()
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancelled_blocks_all(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    slug = f"og-cnx-{uuid.uuid4().hex[:6]}"
    await _make_tenant(factory, slug, "cancelled")
    try:
        with pytest.raises(HTTPException) as exc_get:
            await _check_offboarding_gate(slug, "GET")
        assert exc_get.value.status_code == 403
        with pytest.raises(HTTPException):
            await _check_offboarding_gate(slug, "POST")
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_archived_blocks_all(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    slug = f"og-arc-{uuid.uuid4().hex[:6]}"
    await _make_tenant(factory, slug, "archived")
    try:
        with pytest.raises(HTTPException) as exc:
            await _check_offboarding_gate(slug, "GET")
        assert exc.value.status_code == 403
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_missing_row_allows(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    # Defensive path — no tenant row → return (subscription gate 404s first).
    await _check_offboarding_gate(f"og-none-{uuid.uuid4().hex[:6]}", "POST")
