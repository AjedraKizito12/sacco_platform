"""FastAPI router for /platform/auth/* endpoints.

Three endpoints in this file:
  POST /platform/auth/token   — login (no auth required)
  POST /platform/auth/refresh — exchange refresh token for new access token
  POST /platform/auth/logout  — revoke session (Bearer access token required)

GET /platform/auth/me is added in Plan 07.
Password reset endpoints are added in Plan 08.
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.db import get_platform_session
from app.modules.iam.keys.service import KeyService
from app.modules.iam.platform_auth.schemas import (
    PlatformLoginRequest,
    PlatformPasswordResetConfirmBody,
    PlatformPasswordResetRequestBody,
    PlatformRefreshRequest,
    PlatformTokenResponse,
)
from app.modules.iam.platform_auth.service import PlatformAuthService
from app.platform_.users.schemas import PlatformUserOut

router = APIRouter(prefix="/platform/auth", tags=["platform-auth"])
_log = structlog.get_logger(__name__)
_bearer = HTTPBearer()


async def get_platform_auth_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_platform_session)],
) -> PlatformAuthService:
    """FastAPI dependency that constructs a PlatformAuthService per request.

    Redis is pulled from app.state.redis (set in lifespan). If Redis is not
    configured on app state, falls back to None — SessionService handles that
    gracefully with a DB fallback for jti checks.
    """
    redis = getattr(request.app.state, "redis", None)
    key_service = KeyService(session=session)
    return PlatformAuthService(db=session, key_service=key_service, redis=redis)


PlatformAuth = Annotated[PlatformAuthService, Depends(get_platform_auth_service)]


@router.post("/token", response_model=PlatformTokenResponse)
async def platform_login(
    body: PlatformLoginRequest,
    request: Request,
    svc: PlatformAuth,
) -> PlatformTokenResponse:
    """Exchange email + password for an access token and refresh token."""
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return await svc.login(
        email=str(body.email),
        password=body.password,
        user_agent=user_agent,
        ip_address=ip_address,
    )


@router.post("/refresh", response_model=PlatformTokenResponse)
async def platform_refresh(
    body: PlatformRefreshRequest,
    svc: PlatformAuth,
) -> PlatformTokenResponse:
    """Exchange a valid refresh token for a new access token."""
    return await svc.refresh(body.refresh_token)


@router.post("/logout", status_code=204)
async def platform_logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    svc: PlatformAuth,
) -> Response:
    """Revoke the session associated with the provided Bearer access token."""
    await svc.logout(credentials.credentials)
    return Response(status_code=204)


@router.get("/me", response_model=PlatformUserOut)
async def platform_me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    svc: PlatformAuth,
) -> PlatformUserOut:
    """Return the current platform user's profile from a valid Bearer access token."""
    user = await svc.me(credentials.credentials)
    return PlatformUserOut.model_validate(user)


@router.post("/password-reset/request", status_code=204)
async def platform_reset_request(
    body: PlatformPasswordResetRequestBody,
    svc: PlatformAuth,
) -> Response:
    """Request a password reset link.

    Always returns 204 — the response is identical whether or not the email
    exists in the system, preventing user enumeration.
    """
    await svc.reset_request(str(body.email))
    return Response(status_code=204)


@router.post("/password-reset/confirm", status_code=204)
async def platform_reset_confirm(
    body: PlatformPasswordResetConfirmBody,
    svc: PlatformAuth,
) -> Response:
    """Confirm a password reset using the token from the request email."""
    await svc.reset_confirm(token=body.token, new_password=body.new_password)
    return Response(status_code=204)
