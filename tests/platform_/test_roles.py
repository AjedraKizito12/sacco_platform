"""Role hierarchy + dep factory tests.

The factory returns a dep that requires the authenticated platform user
to have role rank >= the specified role's rank.

    superuser=4 > admin=3 > finance=2 > support=1
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform_.auth import (
    _ROLE_RANK,
    get_current_platform_user_with_role,
)
from app.platform_.models import PlatformUser


async def _make_user(
    factory: async_sessionmaker[AsyncSession],
    *,
    role: str,
    is_superuser: bool = False,
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"u-{uuid.uuid4().hex[:6]}@test.example",
            full_name="U",
            role=role,
            is_superuser=is_superuser,
            is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


def test_rank_constants() -> None:
    assert _ROLE_RANK == {"superuser": 4, "admin": 3, "finance": 2, "support": 1}


async def test_factory_allows_equal_or_higher_rank(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    super_u = await _make_user(factory, role="superuser", is_superuser=True)
    admin = await _make_user(factory, role="admin")
    finance = await _make_user(factory, role="finance")
    support = await _make_user(factory, role="support")
    try:
        gate = get_current_platform_user_with_role("finance")
        # superuser, admin, finance — all pass; support — rejected
        assert (await gate(super_u)).id == super_u.id
        assert (await gate(admin)).id == admin.id
        assert (await gate(finance)).id == finance.id
        with pytest.raises(HTTPException) as exc:
            await gate(support)
        assert exc.value.status_code == 403
    finally:
        await _cleanup(factory)


async def test_factory_admin_excludes_finance(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    admin = await _make_user(factory, role="admin")
    finance = await _make_user(factory, role="finance")
    try:
        gate = get_current_platform_user_with_role("admin")
        assert (await gate(admin)).id == admin.id
        with pytest.raises(HTTPException):
            await gate(finance)
    finally:
        await _cleanup(factory)


async def test_factory_rejects_unknown_role(test_engine: AsyncEngine) -> None:
    with pytest.raises(ValueError, match="unknown role"):
        get_current_platform_user_with_role("operator")


async def test_factory_rejects_user_with_unknown_role_value(
    test_engine: AsyncEngine,
) -> None:
    """A user whose role somehow ended up outside the enum is denied access
    regardless of rank. Defense in depth against a corrupt row.
    """
    # Bypass the model validation and check constraint by constructing the
    # user object in-memory only — never persisted.
    gate = get_current_platform_user_with_role("support")
    fake = PlatformUser(
        email="bad@example.com", full_name="bad", is_active=True,
        is_superuser=False, role="operator",  # not in the enum
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    with pytest.raises(HTTPException) as exc:
        await gate(fake)
    assert exc.value.status_code == 403
