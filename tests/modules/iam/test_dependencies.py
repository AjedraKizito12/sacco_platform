"""Unit tests for the real JWT-validating dependency functions.

Calls get_current_platform_user_jwt and get_current_tenant_user_jwt directly
with manually-constructed inputs. FastAPI's Depends() resolution is bypassed —
we test the function logic, not the DI wiring.

The rsa_keypair fixture generates a 2048-bit key pair once per module.
Tokens are encoded with the test private key; KeyService is mocked to return
the test public key on get_verification_key().
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.security import HTTPAuthorizationCredentials

from app.modules.iam.dependencies import (
    get_current_platform_user_jwt,
    get_current_tenant_user_jwt,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[bytes, bytes]:
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


def _make_platform_token(
    private_pem: bytes,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    expired: bool = False,
) -> str:
    from app.modules.iam.tokens.service import encode_access_token

    ttl_seconds = -60 if expired else 900
    return encode_access_token(
        sub=str(user_id),
        audience="platform",
        session_id=str(session_id),
        actor_type="platform_user",
        kid="test-kid",
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=ttl_seconds,
    )


def _make_tenant_token(
    private_pem: bytes,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    slug: str = "test-sacco",
    *,
    expired: bool = False,
) -> str:
    from app.modules.iam.tokens.service import encode_access_token

    ttl_seconds = -60 if expired else 900
    return encode_access_token(
        sub=str(user_id),
        audience=f"tenant:{slug}",
        session_id=str(session_id),
        actor_type="tenant_user",
        kid="test-tenant-kid",
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=ttl_seconds,
    )


def _make_mock_key_service(public_pem: bytes, audience: str = "platform") -> MagicMock:
    ks = MagicMock()
    ks.get_verification_key = AsyncMock(
        return_value=(public_pem, "RS256", audience)
    )
    return ks


def _make_mock_session_row(*, revoked: bool = False) -> MagicMock:
    row = MagicMock()
    row.revoked_at = datetime.now(UTC) if revoked else None
    return row


def _make_mock_platform_user(*, active: bool = True) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "admin@example.com"
    user.is_active = active
    return user


def _make_mock_tenant_user(*, active: bool = True) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "member@sacco.org"
    user.is_active = active
    return user


def _mock_request(slug: str = "test-sacco") -> MagicMock:
    req = MagicMock()
    req.app.state.redis = None
    req.headers.get = MagicMock(return_value=slug)
    return req


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="bearer", credentials=token)


# ── get_current_platform_user_jwt ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_platform_jwt_dep_returns_user_for_valid_token(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = _make_platform_token(private_pem, user_id, session_id)

    mock_user = _make_mock_platform_user()
    mock_session_row = _make_mock_session_row()
    mock_db_session = AsyncMock()
    mock_db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
    )
    mock_key_service = _make_mock_key_service(public_pem, "platform")

    with patch("app.modules.iam.dependencies.KeyService", return_value=mock_key_service), \
         patch("app.modules.iam.dependencies.SessionService") as MockSvc:
        mock_svc_instance = AsyncMock()
        mock_svc_instance.get_by_session_id = AsyncMock(return_value=mock_session_row)
        MockSvc.return_value = mock_svc_instance

        result = await get_current_platform_user_jwt(
            credentials=_credentials(token),
            session=mock_db_session,
            request=_mock_request(),
        )

    assert result is mock_user


@pytest.mark.anyio
async def test_platform_jwt_dep_raises_401_for_garbage_token(rsa_keypair):
    from fastapi import HTTPException

    _, public_pem = rsa_keypair
    mock_db_session = AsyncMock()
    mock_key_service = _make_mock_key_service(public_pem, "platform")

    with patch("app.modules.iam.dependencies.KeyService", return_value=mock_key_service):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_platform_user_jwt(
                credentials=_credentials("not.a.jwt"),
                session=mock_db_session,
                request=_mock_request(),
            )
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_platform_jwt_dep_raises_401_for_revoked_session(rsa_keypair):
    from fastapi import HTTPException

    private_pem, public_pem = rsa_keypair
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = _make_platform_token(private_pem, user_id, session_id)

    mock_key_service = _make_mock_key_service(public_pem, "platform")
    mock_db_session = AsyncMock()

    with patch("app.modules.iam.dependencies.KeyService", return_value=mock_key_service), \
         patch("app.modules.iam.dependencies.SessionService") as MockSvc:
        mock_svc_instance = AsyncMock()
        mock_svc_instance.get_by_session_id = AsyncMock(
            return_value=_make_mock_session_row(revoked=True)
        )
        MockSvc.return_value = mock_svc_instance

        with pytest.raises(HTTPException) as exc_info:
            await get_current_platform_user_jwt(
                credentials=_credentials(token),
                session=mock_db_session,
                request=_mock_request(),
            )
    assert exc_info.value.status_code == 401


# ── get_current_tenant_user_jwt ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_jwt_dep_returns_user_for_valid_token(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    slug = "test-sacco"
    token = _make_tenant_token(private_pem, user_id, session_id, slug)

    mock_user = _make_mock_tenant_user()
    mock_session_row = _make_mock_session_row()
    mock_tenant_db = AsyncMock()
    mock_tenant_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
    )
    mock_platform_db = AsyncMock()
    mock_key_service = _make_mock_key_service(public_pem, "tenant")

    with patch("app.modules.iam.dependencies.KeyService", return_value=mock_key_service), \
         patch("app.modules.iam.dependencies.SessionService") as MockSvc:
        mock_svc_instance = AsyncMock()
        mock_svc_instance.get_by_session_id = AsyncMock(return_value=mock_session_row)
        MockSvc.return_value = mock_svc_instance

        result = await get_current_tenant_user_jwt(
            credentials=_credentials(token),
            tenant_db=mock_tenant_db,
            platform_db=mock_platform_db,
            request=_mock_request(slug),
        )

    assert result is mock_user


@pytest.mark.anyio
async def test_tenant_jwt_dep_raises_401_for_wrong_audience(rsa_keypair):
    """A token issued for tenant-a must be rejected when presented to tenant-b."""
    from fastapi import HTTPException

    private_pem, public_pem = rsa_keypair
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    # Token issued for "tenant-a"
    token = _make_tenant_token(private_pem, user_id, session_id, "tenant-a")

    mock_key_service = _make_mock_key_service(public_pem, "tenant")
    mock_tenant_db = AsyncMock()
    mock_platform_db = AsyncMock()

    with patch("app.modules.iam.dependencies.KeyService", return_value=mock_key_service):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_tenant_user_jwt(
                credentials=_credentials(token),
                tenant_db=mock_tenant_db,
                platform_db=mock_platform_db,
                # Request is for "tenant-b" — audience mismatch
                request=_mock_request("tenant-b"),
            )
    assert exc_info.value.status_code == 401
