"""HTTP-level tests for /platform/auth/* endpoints.

Uses FastAPI's dependency_overrides to inject a fake PlatformAuthService so
tests do not need a real DB or real RSA keys. This verifies routing, HTTP
status codes, and response shapes — not the internal auth logic (covered by
test_platform_auth_service.py).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.iam.platform_auth.schemas import PlatformTokenResponse

# ── Helpers ────────────────────────────────────────────────────────────────────


def _ok_token_response(*, with_refresh: bool = True) -> PlatformTokenResponse:
    return PlatformTokenResponse(
        access_token="access.token.here",
        refresh_token="refresh.token.here" if with_refresh else None,
        expires_in=900,
    )


# ── /platform/auth/token ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_login_returns_200_with_tokens() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.login = AsyncMock(return_value=_ok_token_response())

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/token",
                json={"email": "user@example.com", "password": "supersecret123"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "access.token.here"
        assert body["refresh_token"] == "refresh.token.here"
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_login_returns_401_on_invalid_credentials() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.login = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Invalid credentials")
    )

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/token",
                json={"email": "nobody@example.com", "password": "wrong"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_login_returns_422_for_missing_fields() -> None:
    """FastAPI validates the request body schema — no service call needed."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/platform/auth/token", json={})
    assert resp.status_code == 422


# ── /platform/auth/refresh ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_refresh_returns_200_with_new_access_token() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.refresh = AsyncMock(return_value=_ok_token_response(with_refresh=False))

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/refresh",
                json={"refresh_token": "some.refresh.token"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "access.token.here"
        assert body["refresh_token"] is None
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_refresh_returns_401_for_invalid_token() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.refresh = AsyncMock(
        side_effect=HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        )
    )

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/refresh",
                json={"refresh_token": "garbage"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


# ── /platform/auth/logout ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_logout_returns_204() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.logout = AsyncMock(return_value=None)

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/logout",
                headers={"Authorization": "Bearer some.valid.access.token"},
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_logout_returns_401_without_bearer_header() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/platform/auth/logout")
    # FastAPI HTTPBearer returns 403 when the header is absent
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_logout_returns_401_for_invalid_token() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.logout = AsyncMock(
        side_effect=HTTPException(
            status_code=401, detail="Invalid or expired access token"
        )
    )

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/logout",
                headers={"Authorization": "Bearer invalid.token"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


# ── GET /platform/auth/me ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_platform_me_returns_200_with_user() -> None:
    import uuid
    from datetime import UTC, datetime

    from app.modules.iam.platform_auth.api import get_platform_auth_service
    from app.platform_.models import PlatformUser

    fake_user = PlatformUser(
        id=uuid.uuid4(),
        email="me@example.com",
        full_name="Me User",
        is_active=True,
        is_superuser=False,
        role="support",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_login_at=None,
    )
    mock_svc = AsyncMock()
    mock_svc.me = AsyncMock(return_value=fake_user)

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/platform/auth/me",
                headers={"Authorization": "Bearer valid.access.token"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "me@example.com"
        assert body["full_name"] == "Me User"
        assert "hashed_password" not in body
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_platform_me_returns_401_without_bearer() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/platform/auth/me")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_platform_me_returns_401_for_revoked_session() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.me = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Session not found or revoked")
    )

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/platform/auth/me",
                headers={"Authorization": "Bearer revoked.token"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


# ── /platform/auth/password-reset/request ─────────────────────────────────────


@pytest.mark.anyio
async def test_platform_reset_request_returns_204_for_known_email() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_request = AsyncMock(return_value=None)

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/password-reset/request",
                json={"email": "user@example.com"},
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_platform_reset_request_returns_204_for_unknown_email() -> None:
    """Unknown emails must also return 204 — no enumeration."""
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_request = AsyncMock(return_value=None)

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/password-reset/request",
                json={"email": "nobody@example.com"},
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_platform_reset_request_returns_422_for_invalid_email() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    app.dependency_overrides[get_platform_auth_service] = lambda: AsyncMock()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/password-reset/request",
                json={"email": "not-an-email"},
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


# ── /platform/auth/password-reset/confirm ─────────────────────────────────────


@pytest.mark.anyio
async def test_platform_reset_confirm_returns_204_on_success() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_confirm = AsyncMock(return_value=None)

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/password-reset/confirm",
                json={"token": "some.valid.token", "new_password": "NewSecurePass123!"},
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_platform_reset_confirm_returns_400_for_invalid_token() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_confirm = AsyncMock(
        side_effect=HTTPException(
            status_code=400, detail="Invalid reset token: token has expired"
        )
    )

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/password-reset/confirm",
                json={"token": "expired.token", "new_password": "NewSecurePass123!"},
            )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_platform_reset_confirm_returns_422_for_missing_fields() -> None:
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    app.dependency_overrides[get_platform_auth_service] = lambda: AsyncMock()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/password-reset/confirm",
                json={"token": "tok"},  # missing new_password
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)
