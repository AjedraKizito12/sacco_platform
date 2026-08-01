"""Real JWT-validating FastAPI dependencies for platform and tenant users.

Platform dependency (get_current_platform_user_jwt):
    Imported by app/platform_/auth.py when PLATFORM_AUTH_MODE=jwt.
    Callers continue to use CurrentPlatformUser from app/platform_/auth.py
    — no call-site changes needed.

Tenant dependency (get_current_tenant_user / CurrentTenantUser):
    Exported directly from this module. Tenant route handlers import
    CurrentTenantUser here:
        from app.modules.iam.dependencies import CurrentTenantUser

Binding switch:
    PLATFORM_AUTH_MODE controls which platform function is active (done in
    app/platform_/auth.py, not here).
    TENANT_AUTH_MODE controls which tenant function is active (done here,
    at module import time).

Test safety:
    tests/conftest.py sets PLATFORM_AUTH_MODE=stub and TENANT_AUTH_MODE=stub
    via os.environ.setdefault BEFORE any module imports, so the binding
    resolves to the stub in all existing tests.
"""
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.config import get_settings
from app.core.db import get_platform_session, get_tenant_session
from app.core.observability import bind_actor_context
from app.modules.iam.keys.service import KeyService
from app.modules.iam.sessions.models import MemberSession, PlatformSession, TenantSession
from app.modules.iam.sessions.service import SessionService
from app.modules.iam.tenant_users.models import TenantUser
from app.modules.iam.tokens.service import decode_token, get_unverified_kid
from app.modules.members.models import Member
from app.platform_.models import PlatformUser

_log = structlog.get_logger(__name__)
_bearer = HTTPBearer()


# ── Platform JWT implementation ───────────────────────────────────────────────


async def get_current_platform_user_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    request: Request,
) -> PlatformUser:
    """Real platform auth dependency: validates Bearer JWT, checks session.

    Imported by app/platform_/auth.py when PLATFORM_AUTH_MODE=jwt.
    Returns the same PlatformUser type as the stub — callers are unaffected.
    """
    redis = getattr(request.app.state, "redis", None)
    key_service = KeyService(session=session)

    try:
        kid = get_unverified_kid(credentials.credentials)
        public_key_pem, algorithm, _aud = await key_service.get_verification_key(kid)
        claims = decode_token(
            credentials.credentials,
            audience="platform",
            public_key_pem=public_key_pem,
            algorithm=algorithm,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    session_id_str = claims.get("session_id")
    sub = claims.get("sub")
    if not session_id_str or not sub:
        raise HTTPException(status_code=401, detail="Malformed token claims")

    try:
        session_id = uuid.UUID(str(session_id_str))
        user_id = uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Malformed token claims") from exc

    svc = SessionService(db=session, model_cls=PlatformSession, redis=redis)
    session_row = await svc.get_by_session_id(session_id)
    if session_row is None or session_row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session not found or revoked")

    result = await session.execute(
        select(PlatformUser).where(PlatformUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    bind_actor_context(
        actor_type="platform_user",
        actor_id=str(user.id),
        actor_label=user.email,
    )

    return user


# ── Tenant stub ───────────────────────────────────────────────────────────────


async def get_current_tenant_user_stub(
    x_tenant_actor_id: Annotated[str, Header(alias="X-Tenant-Actor-ID")],
    session: Annotated[AsyncSession, Depends(get_tenant_session)],
) -> TenantUser:
    """Stub: validates X-Tenant-Actor-ID against tenant_users. NOT production auth.

    Emits a WARNING on every call. Active when TENANT_AUTH_MODE=stub (default).
    Does NOT verify the caller is who the header claims.
    """
    _log.warning(
        "TENANT STUB AUTH: actor_id=%s — not production auth",
        x_tenant_actor_id,
    )

    try:
        actor_id = uuid.UUID(x_tenant_actor_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid X-Tenant-Actor-ID: must be a UUID",
        ) from exc

    result = await session.execute(
        select(TenantUser).where(TenantUser.id == actor_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="Tenant actor not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tenant actor is inactive")

    bind_kwargs: dict[str, str] = {
        "actor_type": "tenant_user",
        "actor_id": str(user.id),
        "actor_label": user.email,
    }
    if user.impersonation_id is not None:
        bind_kwargs["impersonation_id"] = str(user.impersonation_id)
        # Annotate the label so log lines and audit show this is impersonation.
        bind_kwargs["actor_label"] = f"{user.email} (impersonating)"
    bind_actor_context(**bind_kwargs)

    return user


# ── Tenant JWT implementation ─────────────────────────────────────────────────


async def get_current_tenant_user_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    tenant_db: Annotated[AsyncSession, Depends(get_tenant_session)],
    platform_db: Annotated[AsyncSession, Depends(get_platform_session)],
    request: Request,
) -> TenantUser:
    """Real tenant auth dependency: validates Bearer JWT, checks session.

    Two sessions are injected: tenant_db for TenantUser / TenantSession
    lookups; platform_db for KeyService (reads platform.jwt_signing_keys).

    The JWT audience is "tenant:<slug>" where slug comes from X-Tenant-Slug.
    get_tenant_session has already validated the slug — we re-read it here
    for the audience claim only.
    """
    settings = get_settings()
    tenant_slug = request.headers.get(settings.tenant_header, "")
    redis = getattr(request.app.state, "redis", None)

    key_service = KeyService(session=platform_db)
    audience = f"tenant:{tenant_slug}"

    try:
        kid = get_unverified_kid(credentials.credentials)
        public_key_pem, algorithm, _aud = await key_service.get_verification_key(kid)
        claims = decode_token(
            credentials.credentials,
            audience=audience,
            public_key_pem=public_key_pem,
            algorithm=algorithm,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    session_id_str = claims.get("session_id")
    sub = claims.get("sub")
    if not session_id_str or not sub:
        raise HTTPException(status_code=401, detail="Malformed token claims")

    try:
        session_id = uuid.UUID(str(session_id_str))
        user_id = uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Malformed token claims") from exc

    svc = SessionService(db=tenant_db, model_cls=TenantSession, redis=redis)
    session_row = await svc.get_by_session_id(session_id)
    if session_row is None or session_row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session not found or revoked")

    result = await tenant_db.execute(
        select(TenantUser).where(TenantUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    bind_kwargs: dict[str, str] = {
        "actor_type": "tenant_user",
        "actor_id": str(user.id),
        "actor_label": user.email,
    }
    if user.impersonation_id is not None:
        bind_kwargs["impersonation_id"] = str(user.impersonation_id)
        bind_kwargs["actor_label"] = f"{user.email} (impersonating)"
    bind_actor_context(**bind_kwargs)

    return user


# ── Member stub ───────────────────────────────────────────────────────────────


async def get_current_member_stub(
    x_member_actor_id: Annotated[str, Header(alias="X-Member-Actor-ID")],
    session: Annotated[AsyncSession, Depends(get_tenant_session)],
) -> Member:
    """Stub: validates X-Member-Actor-ID against members. NOT production auth.

    Active when MEMBER_AUTH_MODE=stub (default in tests). Emits a WARNING.
    """
    _log.warning("MEMBER STUB AUTH: actor_id=%s — not production auth", x_member_actor_id)
    try:
        member_id = uuid.UUID(x_member_actor_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid X-Member-Actor-ID: must be a UUID"
        ) from exc

    result = await session.execute(select(Member).where(Member.id == member_id))
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=401, detail="Member not found")
    if not (member.portal_enabled and member.status == "active"):
        raise HTTPException(status_code=403, detail="Member portal access is not active")

    bind_actor_context(
        actor_type="member",
        actor_id=str(member.id),
        actor_label=member.email or member.member_number,
    )
    return member


# ── Member JWT implementation ─────────────────────────────────────────────────


async def get_current_member_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    tenant_db: Annotated[AsyncSession, Depends(get_tenant_session)],
    platform_db: Annotated[AsyncSession, Depends(get_platform_session)],
    request: Request,
) -> Member:
    """Real member auth dependency: validates Bearer JWT (aud=member:<slug>).

    The signing key is read with audience "tenant" (the DB column); the JWT aud
    claim "member:<slug>" is what isolates members from operators.
    """
    settings = get_settings()
    tenant_slug = request.headers.get(settings.tenant_header, "")
    redis = getattr(request.app.state, "redis", None)
    key_service = KeyService(session=platform_db)
    audience = f"member:{tenant_slug}"

    try:
        kid = get_unverified_kid(credentials.credentials)
        public_key_pem, algorithm, _aud = await key_service.get_verification_key(kid)
        claims = decode_token(
            credentials.credentials,
            audience=audience,
            public_key_pem=public_key_pem,
            algorithm=algorithm,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    session_id_str = claims.get("session_id")
    sub = claims.get("sub")
    if not session_id_str or not sub:
        raise HTTPException(status_code=401, detail="Malformed token claims")
    try:
        session_id = uuid.UUID(str(session_id_str))
        member_id = uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Malformed token claims") from exc

    svc = SessionService(db=tenant_db, model_cls=MemberSession, redis=redis)
    session_row = await svc.get_by_session_id(session_id)
    if session_row is None or session_row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session not found or revoked")

    result = await tenant_db.execute(select(Member).where(Member.id == member_id))
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=401, detail="Member not found")
    if not (member.portal_enabled and member.status == "active"):
        raise HTTPException(status_code=403, detail="Member portal access is not active")

    bind_actor_context(
        actor_type="member",
        actor_id=str(member.id),
        actor_label=member.email or member.member_number,
    )
    return member


# ── Tenant + member binding switch (runs at import time) ───────────────────────

_settings = get_settings()

if _settings.tenant_auth_mode == "jwt":
    get_current_tenant_user = get_current_tenant_user_jwt
else:
    get_current_tenant_user = get_current_tenant_user_stub  # type: ignore[assignment]

CurrentTenantUser = Annotated[TenantUser, Depends(get_current_tenant_user)]

get_current_member = (
    get_current_member_jwt
    if _settings.member_auth_mode == "jwt"
    else get_current_member_stub
)

CurrentMember = Annotated[Member, Depends(get_current_member)]
