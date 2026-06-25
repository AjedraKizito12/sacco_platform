"""Integration tests: MemberAuthService.enable_access + password reset."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.modules.iam.member_auth.service import (
    OPERATOR_SET_PASSWORD_TTL,
    MemberAuthService,
)
from app.modules.iam.passwords.service import verify_password
from app.modules.iam.reset_tokens import verify_reset_token
from app.modules.members.models import Member

TEST_TENANT_SCHEMA = "tenant_test"
TEST_SLUG = "test-tenant"


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
    from sqlalchemy import event as sa_event

    session = _factory(engine)()

    @sa_event.listens_for(session.sync_session, "after_begin")
    def _reapply(sess, transaction, connection):  # type: ignore[misc]  # noqa: ANN001, ANN202
        connection.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))

    await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
    return session


async def _create_member(engine: AsyncEngine, *, email: str | None, portal_enabled: bool = False) -> uuid.UUID:
    session = await _new_session(engine)
    try:
        member = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}",
            full_name="Jane Doe",
            date_of_birth=date(1990, 1, 1),
            gender="female",
            status="active",
            email=email,
            portal_enabled=portal_enabled,
        )
        session.add(member)
        await session.commit()
        return member.id
    finally:
        await session.close()


async def _cleanup(engine: AsyncEngine, member_id: uuid.UUID) -> None:
    session = await _new_session(engine)
    try:
        await session.execute(
            text("DELETE FROM audit_log WHERE record_id = :mid OR table_name = 'members'"),
            {"mid": str(member_id)},
        )
        await session.execute(
            text("DELETE FROM member_sessions WHERE member_id = :mid"), {"mid": str(member_id)}
        )
        await session.execute(text("DELETE FROM members WHERE id = :mid"), {"mid": str(member_id)})
        await session.commit()
    finally:
        await session.close()


def _secret() -> str:
    return get_settings().app_secret_key


async def test_enable_access_sets_flag_and_returns_token(
    test_engine: AsyncEngine, mock_key_service
) -> None:
    member_id = await _create_member(test_engine, email="jane@example.com")
    try:
        session = await _new_session(test_engine)
        try:
            svc = MemberAuthService(
                db=session, key_service=mock_key_service, redis=None, tenant_slug=TEST_SLUG
            )
            token, ttl = await svc.enable_access(member_id)
            await session.commit()
            assert ttl == OPERATOR_SET_PASSWORD_TTL
            payload = verify_reset_token(token, _secret())
            assert payload["sub"] == str(member_id)
        finally:
            await session.close()

        verify = await _new_session(test_engine)
        try:
            enabled = (
                await verify.execute(
                    text("SELECT portal_enabled FROM members WHERE id = :mid"),
                    {"mid": str(member_id)},
                )
            ).scalar()
            assert enabled is True
        finally:
            await verify.close()
    finally:
        await _cleanup(test_engine, member_id)


async def test_enable_access_rejects_member_without_email(
    test_engine: AsyncEngine, mock_key_service
) -> None:
    member_id = await _create_member(test_engine, email=None)
    try:
        session = await _new_session(test_engine)
        try:
            svc = MemberAuthService(
                db=session, key_service=mock_key_service, redis=None, tenant_slug=TEST_SLUG
            )
            with pytest.raises(HTTPException) as exc:
                await svc.enable_access(member_id)
            assert exc.value.status_code == 400
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine, member_id)


async def test_reset_confirm_sets_password(test_engine: AsyncEngine, mock_key_service) -> None:
    member_id = await _create_member(test_engine, email="jane2@example.com", portal_enabled=True)
    try:
        session = await _new_session(test_engine)
        try:
            svc = MemberAuthService(
                db=session, key_service=mock_key_service, redis=None, tenant_slug=TEST_SLUG
            )
            token, _ = await svc.enable_access(member_id)
            await svc.reset_confirm(token=token, new_password="N3wPassw0rd!")
            await session.commit()
        finally:
            await session.close()

        verify = await _new_session(test_engine)
        try:
            hashed = (
                await verify.execute(
                    text("SELECT hashed_password FROM members WHERE id = :mid"),
                    {"mid": str(member_id)},
                )
            ).scalar()
            assert hashed is not None
            assert verify_password("N3wPassw0rd!", hashed)
        finally:
            await verify.close()
    finally:
        await _cleanup(test_engine, member_id)
