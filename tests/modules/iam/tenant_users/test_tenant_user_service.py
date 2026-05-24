"""Tests for TenantUser model and TenantUserService.

Uses async_sessionmaker + commit + cleanup (not tenant_session fixture).
TenantUser carries AuditableMixin, which calls session.add(audit_row) during
flush — this is incompatible with the conn.begin()+AsyncSession(bind=conn)
fixture pattern (asyncpg "another operation is in progress" during rollback).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.modules.iam.tenant_users.models import TenantUser
from app.modules.iam.tenant_users.service import TenantUserService

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine) -> async_sessionmaker:  # type: ignore[type-arg]
    return async_sessionmaker(engine, expire_on_commit=False)


async def _cleanup(engine: AsyncEngine, *emails: str) -> None:
    """Delete tenant_user rows and their audit_log entries."""
    if not emails:
        return
    factory = _factory(engine)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(
            text("DELETE FROM audit_log WHERE table_name = 'tenant_users'")
        )
        await session.execute(
            text("DELETE FROM tenant_users WHERE email = ANY(:emails)"),
            {"emails": list(emails)},
        )
        await session.commit()


# ── Model persistence ─────────────────────────────────────────────────────────


async def test_tenant_user_model_persists(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            user = TenantUser(
                email="admin@example.com",
                full_name="Test Admin",
                is_active=True,
                is_admin=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(user)
            await session.commit()

        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            result = await session.execute(
                select(TenantUser).where(TenantUser.email == "admin@example.com")
            )
            fetched = result.scalar_one()
            assert isinstance(fetched.id, uuid.UUID)
            assert fetched.full_name == "Test Admin"
            assert fetched.hashed_password is None
            assert fetched.last_login_at is None
    finally:
        await _cleanup(test_engine, "admin@example.com")


# ── create ────────────────────────────────────────────────────────────────────


async def test_create_tenant_user_inserts_row(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            user = await svc.create(email="alice@example.com", full_name="Alice Smith")
            await session.commit()

        assert user.email == "alice@example.com"
        assert user.full_name == "Alice Smith"
        assert user.hashed_password is None
        assert user.is_active is True
        assert user.is_admin is False
    finally:
        await _cleanup(test_engine, "alice@example.com")


async def test_create_tenant_user_as_admin(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            user = await svc.create(
                email="bob@example.com", full_name="Bob Admin", is_admin=True
            )
            await session.commit()

        assert user.is_admin is True
    finally:
        await _cleanup(test_engine, "bob@example.com")


async def test_create_tenant_user_duplicate_email_raises(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            await svc.create(email="dup@example.com", full_name="First")
            await session.commit()

        with pytest.raises(ValueError, match="already registered"):
            async with factory() as session:
                await session.execute(
                    text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
                )
                svc = TenantUserService(session)
                await svc.create(email="dup@example.com", full_name="Second")
                await session.commit()
    finally:
        await _cleanup(test_engine, "dup@example.com")


# ── get_by_id ─────────────────────────────────────────────────────────────────


async def test_get_by_id_returns_user(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    try:
        user_id: uuid.UUID
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            created = await svc.create(email="carol@example.com", full_name="Carol")
            user_id = created.id
            await session.commit()

        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            fetched = await svc.get_by_id(user_id)
            assert fetched is not None
            assert fetched.email == "carol@example.com"
    finally:
        await _cleanup(test_engine, "carol@example.com")


async def test_get_by_id_returns_none_for_missing(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        svc = TenantUserService(session)
        assert await svc.get_by_id(uuid.uuid4()) is None


# ── get_by_email ──────────────────────────────────────────────────────────────


async def test_get_by_email_returns_user(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            await svc.create(email="dave@example.com", full_name="Dave")
            await session.commit()

        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            fetched = await svc.get_by_email("dave@example.com")
            assert fetched is not None
            assert fetched.full_name == "Dave"
    finally:
        await _cleanup(test_engine, "dave@example.com")


async def test_get_by_email_returns_none_for_missing(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        svc = TenantUserService(session)
        assert await svc.get_by_email("nobody@example.com") is None


# ── list ──────────────────────────────────────────────────────────────────────


async def test_list_returns_all_users(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    try:
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            await svc.create(email="e1@example.com", full_name="E1")
            await svc.create(email="e2@example.com", full_name="E2")
            await session.commit()

        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            users = await svc.list()
            emails = {u.email for u in users}
            assert "e1@example.com" in emails
            assert "e2@example.com" in emails
    finally:
        await _cleanup(test_engine, "e1@example.com", "e2@example.com")


async def test_list_filters_by_is_active(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    try:
        inactive_id: uuid.UUID
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            await svc.create(email="active@example.com", full_name="Active")
            inactive = await svc.create(email="inactive@example.com", full_name="Inactive")
            inactive_id = inactive.id
            await session.commit()

        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            await svc.update(inactive_id, is_active=False)
            await session.commit()

        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            active_users = await svc.list(is_active=True)
            emails = {u.email for u in active_users}
            assert "active@example.com" in emails
            assert "inactive@example.com" not in emails
    finally:
        await _cleanup(test_engine, "active@example.com", "inactive@example.com")


# ── update ────────────────────────────────────────────────────────────────────


async def test_update_full_name(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    try:
        user_id: uuid.UUID
        created_at: datetime
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            user = await svc.create(email="frank@example.com", full_name="Frank Old")
            user_id = user.id
            created_at = user.created_at
            await session.commit()

        async with factory() as session:
            await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
            svc = TenantUserService(session)
            updated = await svc.update(user_id, full_name="Frank New")
            await session.commit()
            assert updated is not None
            assert updated.full_name == "Frank New"
            assert updated.updated_at >= created_at
    finally:
        await _cleanup(test_engine, "frank@example.com")


async def test_update_returns_none_for_missing_user(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        svc = TenantUserService(session)
        result = await svc.update(uuid.uuid4(), full_name="Ghost")
        assert result is None
