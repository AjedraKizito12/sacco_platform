"""FastAPI router for /member/auth/* endpoints (Phase 4a)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.config import get_settings
from app.core.db import get_platform_session, get_tenant_session
from app.modules.iam.keys.service import KeyService
from app.modules.iam.member_auth.schemas import (
    MemberLoginRequest,
    MemberOut,
    MemberPasswordResetConfirmBody,
    MemberPasswordResetRequestBody,
    MemberRefreshRequest,
    MemberTokenResponse,
)
from app.modules.iam.member_auth.service import MemberAuthService

router = APIRouter(prefix="/member/auth", tags=["member-auth"])
_bearer = HTTPBearer()


async def get_member_auth_service(
    request: Request,
    tenant_db: Annotated[AsyncSession, Depends(get_tenant_session)],
    platform_db: Annotated[AsyncSession, Depends(get_platform_session)],
) -> MemberAuthService:
    """Construct a MemberAuthService per request.

    tenant_db: tenant-schema session for Member / MemberSession.
    platform_db: platform-schema session for KeyService (jwt_signing_keys).
    """
    settings = get_settings()
    tenant_slug = request.headers.get(settings.tenant_header, "")
    redis = getattr(request.app.state, "redis", None)
    return MemberAuthService(
        db=tenant_db,
        key_service=KeyService(session=platform_db),
        redis=redis,
        tenant_slug=tenant_slug,
    )


MemberAuth = Annotated[MemberAuthService, Depends(get_member_auth_service)]


@router.post("/token", response_model=MemberTokenResponse)
async def member_login(
    body: MemberLoginRequest, request: Request, svc: MemberAuth
) -> MemberTokenResponse:
    """Exchange email + password for an access token and refresh token."""
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return await svc.login(
        email=str(body.email),
        password=body.password,
        user_agent=user_agent,
        ip_address=ip_address,
    )


@router.post("/refresh", response_model=MemberTokenResponse)
async def member_refresh(body: MemberRefreshRequest, svc: MemberAuth) -> MemberTokenResponse:
    """Exchange a valid refresh token for a new access token."""
    return await svc.refresh(body.refresh_token)


@router.post("/logout", status_code=204)
async def member_logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)], svc: MemberAuth
) -> Response:
    """Revoke the session associated with the provided Bearer access token."""
    await svc.logout(credentials.credentials)
    return Response(status_code=204)


@router.get("/me", response_model=MemberOut)
async def member_me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)], svc: MemberAuth
) -> MemberOut:
    """Return the current member's profile from a valid Bearer access token."""
    member = await svc.me(credentials.credentials)
    return MemberOut.model_validate(member)


@router.post("/password-reset/request", status_code=204)
async def member_reset_request(
    body: MemberPasswordResetRequestBody, svc: MemberAuth
) -> Response:
    """Request a member password reset. Always 204 (anti-enumeration)."""
    await svc.reset_request(str(body.email))
    return Response(status_code=204)


@router.post("/password-reset/confirm", status_code=204)
async def member_reset_confirm(
    body: MemberPasswordResetConfirmBody, svc: MemberAuth
) -> Response:
    """Confirm a member password reset using the one-time token."""
    await svc.reset_confirm(token=body.token, new_password=body.new_password)
    return Response(status_code=204)
