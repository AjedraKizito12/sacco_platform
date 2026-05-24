"""Integration tests for PlatformAuthService.

Uses async_sessionmaker + commit + cleanup (NOT platform_session fixture).
PlatformUser carries AuditableMixin — using the conn.begin()+AsyncSession(bind=conn)
fixture with flush() triggers asyncpg "another operation is in progress" on rollback.

RSA keypair generated once per module (scope="module"). argon2id hash computed
once at import. Each test sequence uses a pre-committed PlatformUser row and a
fresh service session.

Test speed: argon2id hash ~200–400 ms once at import. Each verify call ~200 ms.
Expect ~6–10 s total for this file.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives import serialization

if TYPE_CHECKING:
    import uuid
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.modules.iam.passwords.service import hash_password
from app.modules.iam.platform_auth.service import PlatformAuthService
from app.platform_.models import PlatformUser
from tests.modules.iam.test_lockout import FakeRedis

# ── Pre-computed test data ─────────────────────────────────────────────────────

_PASSWORD = "CorrectHorseBatteryStaple!"
# Computed once at module import time (~300 ms). All tests share this hash.
_HASHED_PASSWORD = hash_password(_PASSWORD)


# ── Module-scoped fixtures ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[bytes, bytes]:
    """Generate a 2048-bit RSA keypair. scope=module — generated once."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture(scope="module")
def mock_key_service(rsa_keypair: tuple[bytes, bytes]) -> MagicMock:
    """KeyService stub returning the test RSA keypair."""
    private_pem, public_pem = rsa_keypair
    ks = MagicMock()
    ks.get_active_signing_key = AsyncMock(
        return_value=("test-kid", private_pem, "RS256")
    )
    ks.get_verification_key = AsyncMock(
        return_value=(public_pem, "RS256", "platform")
    )
    return ks


# ── Helpers ────────────────────────────────────────────────────────────────────


def _factory(engine: AsyncEngine) -> async_sessionmaker:  # type: ignore[type-arg]
    return async_sessionmaker(engine, expire_on_commit=False)


async def _create_user(
    engine: AsyncEngine,
    email: str,
    *,
    is_active: bool = True,
) -> PlatformUser:
    """Insert a PlatformUser with _HASHED_PASSWORD. Returns the committed row."""
    factory = _factory(engine)
    now = datetime.now(UTC)
    async with factory() as session:
        user = PlatformUser(
            email=email,
            full_name="Platform Auth Test",
            hashed_password=_HASHED_PASSWORD,
            is_active=is_active,
            is_superuser=False,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.commit()
    return user


async def _cleanup(engine: AsyncEngine, *user_ids: uuid.UUID) -> None:
    """Delete platform_sessions, audit_log, and platform_users for given IDs."""
    if not user_ids:
        return
    ids = [str(uid) for uid in user_ids]
    factory = _factory(engine)
    async with factory() as session:
        await session.execute(
            text(
                "DELETE FROM platform.platform_sessions"
                " WHERE platform_user_id = ANY(:ids)"
            ),
            {"ids": ids},
        )
        # Clean audit rows by record_id (session/user events) and by table_name
        # (platform_users events use record_id=user.id, caught by first clause).
        await session.execute(
            text(
                "DELETE FROM platform.audit_log"
                " WHERE record_id = ANY(:ids)"
                " OR table_name = 'platform_users'"
            ),
            {"ids": ids},
        )
        await session.execute(
            text("DELETE FROM platform.platform_users WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        await session.commit()


def _make_service(
    session: object, key_service: object, redis: object = None
) -> PlatformAuthService:
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    return PlatformAuthService(db=session, key_service=key_service, redis=redis)


# ── login ─────────────────────────────────────────────────────────────────────


async def test_login_returns_token_response(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    user = await _create_user(test_engine, "platform-auth-test@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            response = await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent="pytest/1.0",
                ip_address="127.0.0.1",
            )
            await session.commit()

        assert response.access_token
        assert response.refresh_token
        assert response.token_type == "bearer"
        assert response.expires_in > 0
    finally:
        await _cleanup(test_engine, user.id)


async def test_login_access_token_contains_expected_claims(
    test_engine: AsyncEngine,
    mock_key_service: MagicMock,
    rsa_keypair: tuple[bytes, bytes],
) -> None:
    import jwt as pyjwt

    _, public_pem = rsa_keypair
    user = await _create_user(test_engine, "platform-claims-test@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            response = await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
            await session.commit()

        claims = pyjwt.decode(
            response.access_token,
            public_pem,
            algorithms=["RS256"],
            audience="platform",
        )
        assert claims["sub"] == str(user.id)
        assert claims["aud"] == "platform"
        assert claims["actor_type"] == "platform_user"
        assert "session_id" in claims
        assert "exp" in claims
    finally:
        await _cleanup(test_engine, user.id)


async def test_login_wrong_password_raises_401(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from fastapi import HTTPException

    user = await _create_user(test_engine, "platform-wrongpwd@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            with pytest.raises(HTTPException) as exc_info:
                await svc.login(
                    email=user.email,
                    password="WrongPassword!!!!",
                    user_agent=None,
                    ip_address=None,
                )
        assert exc_info.value.status_code == 401
    finally:
        await _cleanup(test_engine, user.id)


async def test_login_unknown_email_raises_401(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from fastapi import HTTPException

    factory = _factory(test_engine)
    async with factory() as session:
        svc = PlatformAuthService(db=session, key_service=mock_key_service)
        with pytest.raises(HTTPException) as exc_info:
            await svc.login(
                email="nobody@example.com",
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
    assert exc_info.value.status_code == 401


async def test_login_inactive_user_raises_401(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from fastapi import HTTPException

    user = await _create_user(
        test_engine, "platform-inactive@example.com", is_active=False
    )
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            with pytest.raises(HTTPException) as exc_info:
                await svc.login(
                    email=user.email,
                    password=_PASSWORD,
                    user_agent=None,
                    ip_address=None,
                )
        assert exc_info.value.status_code == 401
    finally:
        await _cleanup(test_engine, user.id)


# ── refresh ───────────────────────────────────────────────────────────────────


async def test_refresh_returns_new_access_token(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    user = await _create_user(test_engine, "platform-refresh@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            login_resp = await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
            # autoflush inserts PlatformSession when refresh() queries it
            refresh_resp = await svc.refresh(login_resp.refresh_token)
            await session.commit()

        assert refresh_resp.access_token
        assert refresh_resp.access_token != login_resp.access_token
        assert refresh_resp.refresh_token is None  # refresh does not rotate token
        assert refresh_resp.token_type == "bearer"
    finally:
        await _cleanup(test_engine, user.id)


async def test_refresh_with_garbage_token_raises_401(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from fastapi import HTTPException

    factory = _factory(test_engine)
    async with factory() as session:
        svc = PlatformAuthService(db=session, key_service=mock_key_service)
        with pytest.raises(HTTPException) as exc_info:
            await svc.refresh("not.a.valid.jwt")
    assert exc_info.value.status_code == 401


async def test_refresh_after_logout_raises_401(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    """After logout the session is revoked; refresh must reject the token."""
    from fastapi import HTTPException

    user = await _create_user(test_engine, "platform-logout-refresh@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            login_resp = await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
            # logout() queries PlatformSession → autoflush → INSERT, then revokes
            await svc.logout(login_resp.access_token)

            with pytest.raises(HTTPException) as exc_info:
                await svc.refresh(login_resp.refresh_token)
            await session.commit()

        assert exc_info.value.status_code == 401
    finally:
        await _cleanup(test_engine, user.id)


# ── logout ────────────────────────────────────────────────────────────────────


async def test_logout_revokes_session(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    """logout() must not raise — session revocation verified via refresh test above."""
    user = await _create_user(test_engine, "platform-logout@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            login_resp = await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
            await svc.logout(login_resp.access_token)
            await session.commit()
    finally:
        await _cleanup(test_engine, user.id)


async def test_logout_with_invalid_token_raises_401(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from fastapi import HTTPException

    factory = _factory(test_engine)
    async with factory() as session:
        svc = PlatformAuthService(db=session, key_service=mock_key_service)
        with pytest.raises(HTTPException) as exc_info:
            await svc.logout("not.a.valid.jwt")
    assert exc_info.value.status_code == 401


# ── me ────────────────────────────────────────────────────────────────────────


async def test_me_returns_current_user(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    user = await _create_user(test_engine, "platform-me@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            login_resp = await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
            me_user = await svc.me(login_resp.access_token)
            await session.commit()

        assert me_user.id == user.id
        assert me_user.email == user.email
    finally:
        await _cleanup(test_engine, user.id)


async def test_me_with_invalid_token_raises_401(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from fastapi import HTTPException

    factory = _factory(test_engine)
    async with factory() as session:
        svc = PlatformAuthService(db=session, key_service=mock_key_service)
        with pytest.raises(HTTPException) as exc_info:
            await svc.me("not.a.valid.jwt")
    assert exc_info.value.status_code == 401


async def test_me_after_logout_raises_401(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    """After logout the session is revoked; me() must reject the old access token."""
    from fastapi import HTTPException

    user = await _create_user(test_engine, "platform-me-logout@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            login_resp = await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
            await svc.logout(login_resp.access_token)

            with pytest.raises(HTTPException) as exc_info:
                await svc.me(login_resp.access_token)
            await session.commit()

        assert exc_info.value.status_code == 401
    finally:
        await _cleanup(test_engine, user.id)


# ── reset_request ─────────────────────────────────────────────────────────────


async def test_reset_request_returns_none_for_known_email(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    """reset_request() must not raise for a known email."""
    user = await _create_user(test_engine, "platform-resetreq@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            result = await svc.reset_request(email=user.email)
            await session.commit()
        assert result is None
    finally:
        await _cleanup(test_engine, user.id)


async def test_reset_request_returns_none_for_unknown_email(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    """reset_request() must not raise for unknown emails — prevents enumeration."""
    factory = _factory(test_engine)
    async with factory() as session:
        svc = PlatformAuthService(db=session, key_service=mock_key_service)
        result = await svc.reset_request(email="nobody@nowhere.com")
    assert result is None


# ── reset_confirm ─────────────────────────────────────────────────────────────


async def test_reset_confirm_changes_password(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from app.core.config import get_settings
    from app.modules.iam.passwords.service import verify_password
    from app.modules.iam.reset_tokens import make_reset_token

    user = await _create_user(test_engine, "platform-resetconfirm@example.com")
    try:
        token, _jti = make_reset_token(str(user.id), get_settings().app_secret_key)
        new_password = "NewSecurePassword123!"

        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            await svc.reset_confirm(token=token, new_password=new_password)
            await session.commit()

        # Verify in a fresh session
        async with factory() as session:
            from sqlalchemy import select as sa_select

            from app.platform_.models import PlatformUser as _PU
            result = await session.execute(
                sa_select(_PU).where(_PU.id == user.id)
            )
            refreshed = result.scalar_one()
            assert verify_password(new_password, refreshed.hashed_password) is True
    finally:
        await _cleanup(test_engine, user.id)


async def test_reset_confirm_revokes_existing_sessions(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from app.core.config import get_settings
    from app.modules.iam.reset_tokens import make_reset_token
    from app.modules.iam.sessions.models import PlatformSession

    user = await _create_user(test_engine, "platform-resetrevoke@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            await svc.login(
                email=user.email, password=_PASSWORD,
                user_agent=None, ip_address=None,
            )
            await session.commit()

        # Verify non-revoked session exists
        from sqlalchemy import select as sa_select
        async with factory() as session:
            result = await session.execute(
                sa_select(PlatformSession).where(
                    PlatformSession.platform_user_id == user.id,
                    PlatformSession.revoked_at.is_(None),
                )
            )
            assert result.scalar_one_or_none() is not None

        # Reset password
        token, _jti = make_reset_token(str(user.id), get_settings().app_secret_key)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            await svc.reset_confirm(token=token, new_password="BrandNewPassword456!")
            await session.commit()

        # All sessions should now be revoked
        async with factory() as session:
            result2 = await session.execute(
                sa_select(PlatformSession).where(
                    PlatformSession.platform_user_id == user.id,
                    PlatformSession.revoked_at.is_(None),
                )
            )
            assert result2.scalar_one_or_none() is None
    finally:
        await _cleanup(test_engine, user.id)


async def test_reset_confirm_invalid_token_raises_400(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from fastapi import HTTPException

    factory = _factory(test_engine)
    async with factory() as session:
        svc = PlatformAuthService(db=session, key_service=mock_key_service)
        with pytest.raises(HTTPException) as exc_info:
            await svc.reset_confirm(token="not.a.valid.token", new_password="NewPassword123!")
    assert exc_info.value.status_code == 400


async def test_reset_confirm_short_password_raises_400(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from fastapi import HTTPException

    from app.core.config import get_settings
    from app.modules.iam.reset_tokens import make_reset_token

    user = await _create_user(test_engine, "platform-resetshort@example.com")
    try:
        token, _jti = make_reset_token(str(user.id), get_settings().app_secret_key)
        factory = _factory(test_engine)
        async with factory() as session:
            svc = PlatformAuthService(db=session, key_service=mock_key_service)
            with pytest.raises(HTTPException) as exc_info:
                await svc.reset_confirm(token=token, new_password="tooshort")
        assert exc_info.value.status_code == 400
    finally:
        await _cleanup(test_engine, user.id)


# ── lockout ───────────────────────────────────────────────────────────────────


async def test_platform_login_returns_423_after_threshold_failures(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    """After auth_lockout_threshold wrong-password failures the account locks."""
    from fastapi import HTTPException

    from app.core.config import get_settings

    settings = get_settings()
    fake_redis = FakeRedis()
    user = await _create_user(test_engine, "platform-lockout-423@example.com")
    try:
        factory = _factory(test_engine)
        for _ in range(settings.auth_lockout_threshold):
            async with factory() as session:
                svc = _make_service(session, mock_key_service, redis=fake_redis)
                with pytest.raises(HTTPException) as exc_info:
                    await svc.login(
                        email=user.email,
                        password="WrongPasswordXXX!",
                        user_agent=None,
                        ip_address=None,
                    )
                assert exc_info.value.status_code == 401

        # The next attempt — even with correct password — must be 423.
        async with factory() as session:
            svc = _make_service(session, mock_key_service, redis=fake_redis)
            with pytest.raises(HTTPException) as exc_info:
                await svc.login(
                    email=user.email,
                    password=_PASSWORD,
                    user_agent=None,
                    ip_address=None,
                )
        assert exc_info.value.status_code == 423
    finally:
        await _cleanup(test_engine, user.id)


async def test_platform_login_423_includes_retry_after(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from fastapi import HTTPException

    from app.core.config import get_settings

    settings = get_settings()
    fake_redis = FakeRedis()
    user = await _create_user(test_engine, "platform-lockout-retry@example.com")
    try:
        factory = _factory(test_engine)
        for _ in range(settings.auth_lockout_threshold):
            async with factory() as session:
                svc = _make_service(session, mock_key_service, redis=fake_redis)
                with pytest.raises(HTTPException):
                    await svc.login(
                        email=user.email,
                        password="WrongPasswordXXX!",
                        user_agent=None,
                        ip_address=None,
                    )

        async with factory() as session:
            svc = _make_service(session, mock_key_service, redis=fake_redis)
            with pytest.raises(HTTPException) as exc_info:
                await svc.login(
                    email=user.email,
                    password=_PASSWORD,
                    user_agent=None,
                    ip_address=None,
                )
        assert exc_info.value.status_code == 423
        assert "Retry-After" in exc_info.value.headers
    finally:
        await _cleanup(test_engine, user.id)


async def test_platform_login_clears_lockout_on_success(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    """Successful login must reset the attempt counter so the next failure
    starts a fresh window."""
    from fastapi import HTTPException

    from app.modules.iam.lockout import is_locked

    fake_redis = FakeRedis()
    user = await _create_user(test_engine, "platform-lockout-clear@example.com")
    try:
        factory = _factory(test_engine)

        # Fail once to put a count in Redis.
        async with factory() as session:
            svc = _make_service(session, mock_key_service, redis=fake_redis)
            with pytest.raises(HTTPException):
                await svc.login(
                    email=user.email,
                    password="WrongPasswordXXX!",
                    user_agent=None,
                    ip_address=None,
                )

        # Successful login must clear the counter.
        async with factory() as session:
            svc = _make_service(session, mock_key_service, redis=fake_redis)
            await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
            await session.commit()

        # Lockout state must be cleared.
        locked, _ = await is_locked(user.email, redis=fake_redis)
        assert locked is False
    finally:
        await _cleanup(test_engine, user.id)


async def test_platform_login_without_redis_never_locks(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    """When redis=None lockout is disabled — login always gives 401, never 423."""
    from fastapi import HTTPException

    from app.core.config import get_settings

    settings = get_settings()
    user = await _create_user(test_engine, "platform-lockout-noredis@example.com")
    try:
        factory = _factory(test_engine)
        for _ in range(settings.auth_lockout_threshold + 1):
            async with factory() as session:
                svc = _make_service(session, mock_key_service, redis=None)
                with pytest.raises(HTTPException) as exc_info:
                    await svc.login(
                        email=user.email,
                        password="WrongPasswordXXX!",
                        user_agent=None,
                        ip_address=None,
                    )
                # Must always be 401, never 423.
                assert exc_info.value.status_code == 401
    finally:
        await _cleanup(test_engine, user.id)


# ── audit wiring ──────────────────────────────────────────────────────────────

_AUDIT_TARGET = "app.modules.iam.platform_auth.service.write_platform_auth_event"


async def test_login_unknown_user_writes_login_failed_anonymous(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from unittest.mock import patch

    from fastapi import HTTPException

    factory = _factory(test_engine)
    async with factory() as session:
        svc = _make_service(session, mock_key_service)
        with (
            patch(_AUDIT_TARGET, new_callable=AsyncMock) as mock_audit,
            pytest.raises(HTTPException),
        ):
            await svc.login(
                email="nobody-audit@example.com",
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
    mock_audit.assert_awaited_once()
    call_kwargs = mock_audit.await_args.kwargs
    assert call_kwargs["operation"] == "login_failed"
    assert call_kwargs["actor_id"] is None


async def test_login_bad_password_writes_login_failed(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from unittest.mock import patch

    from fastapi import HTTPException

    user = await _create_user(test_engine, "platform-audit-badpwd@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = _make_service(session, mock_key_service)
            with (
                patch(_AUDIT_TARGET, new_callable=AsyncMock) as mock_audit,
                pytest.raises(HTTPException),
            ):
                await svc.login(
                    email=user.email,
                    password="WrongPasswordXXX!",
                    user_agent=None,
                    ip_address=None,
                )
        mock_audit.assert_awaited_once()
        call_kwargs = mock_audit.await_args.kwargs
        assert call_kwargs["operation"] == "login_failed"
        assert call_kwargs["actor_id"] == user.id
        assert call_kwargs["after_state"]["reason"] == "bad_password"
    finally:
        await _cleanup(test_engine, user.id)


async def test_login_locked_writes_login_locked(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from unittest.mock import patch

    from fastapi import HTTPException

    settings_obj = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    fake_redis = FakeRedis()
    user = await _create_user(test_engine, "platform-audit-locked@example.com")
    try:
        factory = _factory(test_engine)
        for _ in range(settings_obj.auth_lockout_threshold):
            async with factory() as session:
                svc = _make_service(session, mock_key_service, redis=fake_redis)
                with pytest.raises(HTTPException):
                    await svc.login(
                        email=user.email,
                        password="WrongPasswordXXX!",
                        user_agent=None,
                        ip_address=None,
                    )

        async with factory() as session:
            svc = _make_service(session, mock_key_service, redis=fake_redis)
            with (
                patch(_AUDIT_TARGET, new_callable=AsyncMock) as mock_audit,
                pytest.raises(HTTPException) as exc_info,
            ):
                await svc.login(
                    email=user.email,
                    password=_PASSWORD,
                    user_agent=None,
                    ip_address=None,
                )
        assert exc_info.value.status_code == 423
        mock_audit.assert_awaited_once()
        assert mock_audit.await_args.kwargs["operation"] == "login_locked"
        assert mock_audit.await_args.kwargs["actor_id"] == user.id
    finally:
        await _cleanup(test_engine, user.id)


async def test_login_success_writes_login_success(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from unittest.mock import patch

    user = await _create_user(test_engine, "platform-audit-success@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = _make_service(session, mock_key_service)
            with patch(_AUDIT_TARGET, new_callable=AsyncMock) as mock_audit:
                await svc.login(
                    email=user.email,
                    password=_PASSWORD,
                    user_agent="pytest/1.0",
                    ip_address="127.0.0.1",
                )
            await session.commit()
        mock_audit.assert_awaited_once()
        call_kwargs = mock_audit.await_args.kwargs
        assert call_kwargs["operation"] == "login_success"
        assert call_kwargs["actor_id"] == user.id
        assert call_kwargs["actor_label"] == user.email
    finally:
        await _cleanup(test_engine, user.id)


async def test_refresh_writes_refresh_event(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from unittest.mock import patch

    user = await _create_user(test_engine, "platform-audit-refresh@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = _make_service(session, mock_key_service)
            login_resp = await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
            with patch(_AUDIT_TARGET, new_callable=AsyncMock) as mock_audit:
                await svc.refresh(login_resp.refresh_token)
            await session.commit()
        mock_audit.assert_awaited_once()
        assert mock_audit.await_args.kwargs["operation"] == "refresh"
    finally:
        await _cleanup(test_engine, user.id)


async def test_logout_writes_logout_event(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from unittest.mock import patch

    user = await _create_user(test_engine, "platform-audit-logout@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = _make_service(session, mock_key_service)
            login_resp = await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
            with patch(_AUDIT_TARGET, new_callable=AsyncMock) as mock_audit:
                await svc.logout(login_resp.access_token)
            await session.commit()
        mock_audit.assert_awaited_once()
        assert mock_audit.await_args.kwargs["operation"] == "logout"
    finally:
        await _cleanup(test_engine, user.id)


async def test_me_writes_me_event(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from unittest.mock import patch

    user = await _create_user(test_engine, "platform-audit-me@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = _make_service(session, mock_key_service)
            login_resp = await svc.login(
                email=user.email,
                password=_PASSWORD,
                user_agent=None,
                ip_address=None,
            )
            with patch(_AUDIT_TARGET, new_callable=AsyncMock) as mock_audit:
                await svc.me(login_resp.access_token)
            await session.commit()
        mock_audit.assert_awaited_once()
        call_kwargs = mock_audit.await_args.kwargs
        assert call_kwargs["operation"] == "me"
        assert call_kwargs["actor_id"] == user.id
    finally:
        await _cleanup(test_engine, user.id)


async def test_reset_request_writes_password_reset_requested(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from unittest.mock import patch

    user = await _create_user(test_engine, "platform-audit-resetreq@example.com")
    try:
        factory = _factory(test_engine)
        async with factory() as session:
            svc = _make_service(session, mock_key_service)
            with patch(_AUDIT_TARGET, new_callable=AsyncMock) as mock_audit:
                await svc.reset_request(email=user.email)
            await session.commit()
        mock_audit.assert_awaited_once()
        call_kwargs = mock_audit.await_args.kwargs
        assert call_kwargs["operation"] == "password_reset_requested"
        assert call_kwargs["table_name"] == "platform_users"
        assert call_kwargs["actor_id"] == user.id
    finally:
        await _cleanup(test_engine, user.id)


async def test_reset_confirm_writes_password_reset_confirmed(
    test_engine: AsyncEngine, mock_key_service: MagicMock
) -> None:
    from unittest.mock import patch

    from app.core.config import get_settings
    from app.modules.iam.reset_tokens import make_reset_token

    user = await _create_user(test_engine, "platform-audit-resetconfirm2@example.com")
    try:
        token, _jti = make_reset_token(str(user.id), get_settings().app_secret_key)
        factory = _factory(test_engine)
        async with factory() as session:
            svc = _make_service(session, mock_key_service)
            with patch(_AUDIT_TARGET, new_callable=AsyncMock) as mock_audit:
                await svc.reset_confirm(token=token, new_password="NewPassword999!")
            await session.commit()
        mock_audit.assert_awaited_once()
        call_kwargs = mock_audit.await_args.kwargs
        assert call_kwargs["operation"] == "password_reset_confirmed"
        assert call_kwargs["table_name"] == "platform_users"
    finally:
        await _cleanup(test_engine, user.id)
