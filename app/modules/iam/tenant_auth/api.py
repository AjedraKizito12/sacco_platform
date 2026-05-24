"""FastAPI router for /auth/* tenant endpoints.

Three endpoints in this file:
  POST /auth/token   — login (no auth required; X-Tenant-Slug required)
  POST /auth/refresh — exchange refresh token for new access token (no auth)
  POST /auth/logout  — revoke session (Bearer access token required)

GET /auth/me is added in Plan 07.
Password reset endpoints are added in Plan 08.

Design note: the FastAPI dependency `get_tenant_auth_service` must inject
BOTH a tenant session (for TenantUser / TenantSession DB operations) AND a
platform session (for KeyService, which reads platform.jwt_signing_keys).
The tenant slug is extracted from the X-Tenant-Slug request header.
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.config import get_settings
from app.core.db import get_platform_session, get_tenant_session
from app.modules.iam.keys.service import KeyService
from app.modules.iam.tenant_auth.schemas import (
    TenantLoginRequest,
    TenantPasswordResetConfirmBody,
    TenantPasswordResetRequestBody,
    TenantRefreshRequest,
    TenantTokenResponse,
    TenantUserOut,
)
from app.modules.iam.tenant_auth.service import TenantAuthService

router = APIRouter(prefix="/auth", tags=["tenant-auth"])
_log = structlog.get_logger(__name__)
_bearer = HTTPBearer()


async def get_tenant_auth_service(
    request: Request,
    tenant_db: Annotated[AsyncSession, Depends(get_tenant_session)],
    platform_db: Annotated[AsyncSession, Depends(get_platform_session)],
) -> TenantAuthService:
    """FastAPI dependency that constructs a TenantAuthService per request.

    Two sessions are injected:
    - tenant_db: scoped to the tenant schema (search_path set by get_tenant_session).
      Used for TenantUser lookups and TenantSession creation.
    - platform_db: scoped to the platform schema.
      Used by KeyService to read platform.jwt_signing_keys.

    The tenant slug is read from the configured tenant_header (X-Tenant-Slug by
    default). get_tenant_session has already validated it — re-reading here is
    safe since the header value is immutable within a single request.
    """
    settings = get_settings()
    tenant_slug = request.headers.get(settings.tenant_header, "")
    redis = getattr(request.app.state, "redis", None)
    key_service = KeyService(session=platform_db)
    return TenantAuthService(
        db=tenant_db,
        key_service=key_service,
        redis=redis,
        tenant_slug=tenant_slug,
    )


TenantAuth = Annotated[TenantAuthService, Depends(get_tenant_auth_service)]


@router.post("/token", response_model=TenantTokenResponse)
async def tenant_login(
    body: TenantLoginRequest,
    request: Request,
    svc: TenantAuth,
) -> TenantTokenResponse:
    """Exchange email + password for an access token and refresh token."""
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return await svc.login(
        email=str(body.email),
        password=body.password,
        user_agent=user_agent,
        ip_address=ip_address,
    )


@router.post("/refresh", response_model=TenantTokenResponse)
async def tenant_refresh(
    body: TenantRefreshRequest,
    svc: TenantAuth,
) -> TenantTokenResponse:
    """Exchange a valid refresh token for a new access token."""
    return await svc.refresh(body.refresh_token)


@router.post("/logout", status_code=204)
async def tenant_logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    svc: TenantAuth,
) -> Response:
    """Revoke the session associated with the provided Bearer access token."""
    await svc.logout(credentials.credentials)
    return Response(status_code=204)


@router.get("/me", response_model=TenantUserOut)
async def tenant_me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    svc: TenantAuth,
) -> TenantUserOut:
    """Return the current tenant user's profile from a valid Bearer access token."""
    user = await svc.me(credentials.credentials)
    return TenantUserOut.model_validate(user)


@router.post("/password-reset/request", status_code=204)
async def tenant_reset_request(
    body: TenantPasswordResetRequestBody,
    svc: TenantAuth,
) -> Response:
    """Request a password reset link for a tenant user.

    Always returns 204 — response is identical whether or not the email
    exists, preventing user enumeration.
    """
    await svc.reset_request(str(body.email))
    return Response(status_code=204)


@router.post("/password-reset/confirm", status_code=204)
async def tenant_reset_confirm(
    body: TenantPasswordResetConfirmBody,
    svc: TenantAuth,
) -> Response:
    """Confirm a tenant user password reset using the token from the request email."""
    await svc.reset_confirm(token=body.token, new_password=body.new_password)
    return Response(status_code=204)
