"""Integration tests: MemberAuthService login/refresh/logout/me.

Uses the mock_key_service fixture (conftest) — a KeyService stub returning a
real RSA keypair so tokens are genuinely signed/verified. redis=None, so lockout
is a no-op and the jti check falls back to the DB.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.iam.member_auth.service import MemberAuthService
from app.modules.iam.passwords.service import hash_password
from app.modules.members.models import Member

TEST_TENANT_SCHEMA = "tenant_test"
TEST_SLUG = "test-tenant"

_PASSWORD = "S3cret-pass!ok"
_HASHED = hash_password(_PASSWORD)  # computed once at import (~300ms)


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


async def _create_member(
    engine: AsyncEngine, *, email: str, portal_enabled: bool = True, status: str = "active"
) -> uuid.UUID:
    session = await _new_session(engine)
    try:
        member = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}",
            full_name="Eli M",
            date_of_birth=date(1991, 2, 2),
            gender="male",
            status=status,
            email=email,
            portal_enabled=portal_enabled,
            hashed_password=_HASHED,
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


async def test_login_success_issues_tokens(test_engine: AsyncEngine, mock_key_service) -> None:
    email = f"eli-{uuid.uuid4().hex[:6]}@example.com"
    member_id = await _create_member(test_engine, email=email)
    try:
        session = await _new_session(test_engine)
        try:
            svc = MemberAuthService(
                db=session, key_service=mock_key_service, redis=None, tenant_slug=TEST_SLUG
            )
            resp = await svc.login(
                email=email, password=_PASSWORD, user_agent="pytest", ip_address="127.0.0.1"
            )
            await session.commit()
            assert resp.access_token
            assert resp.refresh_token
            assert resp.expires_in > 0

            who = await svc.me(resp.access_token)
            assert who.id == member_id
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine, member_id)


async def test_login_access_token_has_member_audience(
    test_engine: AsyncEngine, mock_key_service, rsa_keypair: tuple[bytes, bytes]
) -> None:
    import jwt as pyjwt

    _, public_pem = rsa_keypair
    email = f"eli-{uuid.uuid4().hex[:6]}@example.com"
    member_id = await _create_member(test_engine, email=email)
    try:
        session = await _new_session(test_engine)
        try:
            svc = MemberAuthService(
                db=session, key_service=mock_key_service, redis=None, tenant_slug=TEST_SLUG
            )
            resp = await svc.login(
                email=email, password=_PASSWORD, user_agent=None, ip_address=None
            )
            await session.commit()
        finally:
            await session.close()

        claims = pyjwt.decode(
            resp.access_token, public_pem, algorithms=["RS256"], audience=f"member:{TEST_SLUG}"
        )
        assert claims["aud"] == f"member:{TEST_SLUG}"
        assert claims["actor_type"] == "member"
        assert claims["sub"] == str(member_id)
    finally:
        await _cleanup(test_engine, member_id)


async def test_login_rejects_disabled_portal(test_engine: AsyncEngine, mock_key_service) -> None:
    email = f"eli-{uuid.uuid4().hex[:6]}@example.com"
    member_id = await _create_member(test_engine, email=email, portal_enabled=False)
    try:
        session = await _new_session(test_engine)
        try:
            svc = MemberAuthService(
                db=session, key_service=mock_key_service, redis=None, tenant_slug=TEST_SLUG
            )
            with pytest.raises(HTTPException) as exc:
                await svc.login(email=email, password=_PASSWORD, user_agent=None, ip_address=None)
            assert exc.value.status_code == 401  # generic, anti-enumeration
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine, member_id)


async def test_login_rejects_wrong_password(test_engine: AsyncEngine, mock_key_service) -> None:
    email = f"eli-{uuid.uuid4().hex[:6]}@example.com"
    member_id = await _create_member(test_engine, email=email)
    try:
        session = await _new_session(test_engine)
        try:
            svc = MemberAuthService(
                db=session, key_service=mock_key_service, redis=None, tenant_slug=TEST_SLUG
            )
            with pytest.raises(HTTPException) as exc:
                await svc.login(
                    email=email, password="wrong-password-x", user_agent=None, ip_address=None
                )
            assert exc.value.status_code == 401
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine, member_id)
