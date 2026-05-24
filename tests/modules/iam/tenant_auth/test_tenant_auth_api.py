"""HTTP-level tests for /auth/* tenant endpoints.

Uses FastAPI dependency_overrides to inject a fake TenantAuthService.
The tests verify routing, status codes, and response shapes only —
internal auth logic is covered by test_tenant_auth_service.py.

The X-Tenant-Slug header must be present on all requests because
get_tenant_session (FastAPI dependency) raises 400 without it.
However, since we override get_tenant_auth_service entirely, the
real get_tenant_session is never called — the header is still
included in requests for realism but is not validated.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.main import app
from app.modules.iam.tenant_auth.schemas import TenantTokenResponse

_SLUG_HEADER = {"X-Tenant-Slug": "test-sacco"}


def _ok_token_response(*, with_refresh: bool = True) -> TenantTokenResponse:
    return TenantTokenResponse(
        access_token="access.token.here",
        refresh_token="refresh.token.here" if with_refresh else None,
        expires_in=900,
    )


# ── /auth/token ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_login_returns_200_with_tokens() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.login = AsyncMock(return_value=_ok_token_response())

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/token",
                json={"email": "user@sacco.org", "password": "supersecret123"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "access.token.here"
        assert body["refresh_token"] == "refresh.token.here"
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_login_returns_401_on_invalid_credentials() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.login = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Invalid credentials")
    )

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/token",
                json={"email": "nobody@sacco.org", "password": "wrong"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_login_returns_422_for_missing_fields() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    # Override so get_tenant_session (which needs app.state.redis) is not called.
    # FastAPI still returns 422 for invalid body before calling the handler.
    app.dependency_overrides[get_tenant_auth_service] = lambda: AsyncMock()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/auth/token", json={}, headers=_SLUG_HEADER)
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


# ── /auth/refresh ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_refresh_returns_200_with_new_access_token() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.refresh = AsyncMock(return_value=_ok_token_response(with_refresh=False))

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/refresh",
                json={"refresh_token": "some.refresh.token"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "access.token.here"
        assert body["refresh_token"] is None
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_refresh_returns_401_for_invalid_token() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.refresh = AsyncMock(
        side_effect=HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        )
    )

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/refresh",
                json={"refresh_token": "garbage"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


# ── /auth/logout ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_logout_returns_204() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.logout = AsyncMock(return_value=None)

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/logout",
                headers={**_SLUG_HEADER, "Authorization": "Bearer some.valid.token"},
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_logout_returns_401_or_403_without_bearer() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    # Override so get_tenant_session (which needs app.state.redis) is not called.
    # HTTPBearer still returns 403 before the service handler is invoked.
    app.dependency_overrides[get_tenant_auth_service] = lambda: AsyncMock()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/auth/logout", headers=_SLUG_HEADER)
        # FastAPI HTTPBearer returns 403 when the header is absent
        assert resp.status_code in (401, 403)
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_logout_returns_401_for_invalid_token() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.logout = AsyncMock(
        side_effect=HTTPException(
            status_code=401, detail="Invalid or expired access token"
        )
    )

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/logout",
                headers={**_SLUG_HEADER, "Authorization": "Bearer invalid.token"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


# ── GET /auth/me ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_me_returns_200_with_user() -> None:
    import uuid
    from datetime import UTC, datetime

    from app.modules.iam.tenant_auth.api import get_tenant_auth_service
    from app.modules.iam.tenant_users.models import TenantUser

    fake_user = TenantUser(
        id=uuid.uuid4(),
        email="member@sacco.org",
        full_name="SACCO Member",
        is_active=True,
        is_admin=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_svc = AsyncMock()
    mock_svc.me = AsyncMock(return_value=fake_user)

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/auth/me",
                headers={**_SLUG_HEADER, "Authorization": "Bearer valid.access.token"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "member@sacco.org"
        assert body["full_name"] == "SACCO Member"
        assert "hashed_password" not in body
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_me_returns_401_without_bearer() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    app.dependency_overrides[get_tenant_auth_service] = lambda: AsyncMock()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/auth/me", headers=_SLUG_HEADER)
        assert resp.status_code in (401, 403)
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_me_returns_401_for_revoked_session() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.me = AsyncMock(
        side_effect=HTTPException(
            status_code=401, detail="Session not found or revoked"
        )
    )

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/auth/me",
                headers={**_SLUG_HEADER, "Authorization": "Bearer revoked.token"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


# ── /auth/password-reset/request ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_reset_request_returns_204() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_request = AsyncMock(return_value=None)

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/password-reset/request",
                json={"email": "member@sacco.org"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_reset_request_returns_422_for_invalid_email() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    app.dependency_overrides[get_tenant_auth_service] = lambda: AsyncMock()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/password-reset/request",
                json={"email": "bad-email"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


# ── /auth/password-reset/confirm ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_reset_confirm_returns_204_on_success() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_confirm = AsyncMock(return_value=None)

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/password-reset/confirm",
                json={"token": "valid.tok", "new_password": "GoodPassword123!"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_reset_confirm_returns_400_for_bad_token() -> None:
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_confirm = AsyncMock(
        side_effect=HTTPException(
            status_code=400, detail="Invalid reset token: token has expired"
        )
    )

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/password-reset/confirm",
                json={"token": "expired.tok", "new_password": "GoodPassword123!"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)
