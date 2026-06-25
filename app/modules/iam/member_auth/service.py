"""MemberAuthService — member portal authentication (Phase 4a).

Mirrors TenantAuthService but queries Member (not TenantUser), creates
MemberSession rows, and issues JWTs with aud="member:<slug>". The signing key
is still looked up with audience "tenant" (the DB column value) — the aud claim
alone provides member/operator isolation.

Login/refresh/logout/me are added in the next task.
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.config import get_settings
from app.modules.iam.auth_audit import write_member_auth_event
from app.modules.iam.passwords.service import hash_password
from app.modules.iam.reset_tokens import make_reset_token, verify_reset_token
from app.modules.iam.sessions.models import MemberSession
from app.modules.iam.sessions.service import SessionService
from app.modules.members.models import Member

_log = structlog.get_logger(__name__)

# Signing-key DB column value — reused; the JWT aud claim is "member:<slug>".
_KEY_AUDIENCE = "tenant"
# Operator-issued set-password tokens live longer than self-service resets:
# the operator delivers them out of band (until Phase 3 email).
OPERATOR_SET_PASSWORD_TTL = 86400  # 24h
_SELF_RESET_TTL = 900  # 15 min


class MemberAuthService:
    """Orchestrates member portal authentication.

    Args:
        db:          AsyncSession scoped to the tenant schema (search_path set).
        key_service: KeyService instance backed by a platform schema session.
        redis:       Optional Redis async client for jti + reset-token tracking.
        tenant_slug: Slug of the current tenant; embedded in aud as "member:<slug>".
    """

    def __init__(
        self,
        db: AsyncSession,
        key_service: Any,
        redis: Any | None,
        tenant_slug: str,
    ) -> None:
        self._db = db
        self._key_service = key_service
        self._redis = redis
        self._slug = tenant_slug
        self._audience = f"member:{tenant_slug}"
        self._session_svc = SessionService(db=db, model_cls=MemberSession, redis=redis)

    async def _get_member_by_id(self, member_id: uuid.UUID) -> Member | None:
        result = await self._db.execute(select(Member).where(Member.id == member_id))
        return result.scalar_one_or_none()

    async def _get_member_by_email(self, email: str) -> Member | None:
        result = await self._db.execute(select(Member).where(Member.email == email))
        return result.scalar_one_or_none()

    # ── enable_access (operator) ────────────────────────────────────────────

    async def enable_access(self, member_id: uuid.UUID) -> tuple[str, int]:
        """Enable portal access for a member and mint a one-time set-password token.

        Raises:
            HTTPException 404: member not found.
            HTTPException 400: member has no email.
        """
        settings = get_settings()
        member = await self._get_member_by_id(member_id)
        if member is None:
            raise HTTPException(status_code=404, detail="Member not found")
        if not member.email:
            raise HTTPException(
                status_code=400,
                detail="Member has no email; cannot enable portal access",
            )

        member.portal_enabled = True

        token, jti = make_reset_token(
            str(member.id), settings.app_secret_key, ttl=OPERATOR_SET_PASSWORD_TTL
        )
        if self._redis is not None:
            await self._redis.set(f"iam:pwreset:{jti}", "1", ex=OPERATOR_SET_PASSWORD_TTL)

        await write_member_auth_event(
            db=self._db,
            operation="portal_access_enabled",
            actor_id=member.id,
            actor_label=member.email,
            tenant_slug=self._slug,
            table_name="members",
        )
        _log.info("member_auth.enable_access", member_id=str(member.id), tenant=self._slug)
        return token, OPERATOR_SET_PASSWORD_TTL

    # ── reset_request (self-service) ────────────────────────────────────────

    async def reset_request(self, email: str) -> None:
        """Request a member password reset. Always returns None (anti-enumeration)."""
        settings = get_settings()
        member = await self._get_member_by_email(email)
        if member is None or not member.portal_enabled:
            return

        token, jti = make_reset_token(
            str(member.id), settings.app_secret_key, ttl=_SELF_RESET_TTL
        )
        if self._redis is not None:
            await self._redis.set(f"iam:pwreset:{jti}", "1", ex=_SELF_RESET_TTL)

        _log.warning(
            "MEMBER PASSWORD RESET TOKEN — dev only, configure email notifier for production",
            email=email,
            tenant=self._slug,
            reset_token=token,
        )
        await write_member_auth_event(
            db=self._db,
            operation="password_reset_requested",
            actor_id=member.id,
            actor_label=member.email,
            tenant_slug=self._slug,
            table_name="members",
        )

    # ── reset_confirm ───────────────────────────────────────────────────────

    async def reset_confirm(self, token: str, new_password: str) -> None:
        """Confirm a member password reset.

        Raises:
            HTTPException 400: invalid/expired token, already-consumed JTI,
                               member not found, or new password too short.
        """
        settings = get_settings()
        try:
            payload = verify_reset_token(token, settings.app_secret_key)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid reset token: {exc}"
            ) from exc

        jti = str(payload["jti"])
        member_id_str = str(payload["sub"])

        if self._redis is not None and not await self._redis.exists(f"iam:pwreset:{jti}"):
            raise HTTPException(
                status_code=400,
                detail="Reset token has already been used or has expired",
            )

        try:
            member_id = uuid.UUID(member_id_str)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Malformed token payload") from exc

        member = await self._get_member_by_id(member_id)
        if member is None:
            raise HTTPException(status_code=400, detail="Invalid reset token")

        try:
            member.hashed_password = hash_password(new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if self._redis is not None:
            await self._redis.delete(f"iam:pwreset:{jti}")

        await self._session_svc.revoke_all_for_user(member_id)
        await write_member_auth_event(
            db=self._db,
            operation="password_reset_confirmed",
            actor_id=member_id,
            actor_label=member.email,
            tenant_slug=self._slug,
            table_name="members",
        )
        _log.info(
            "member_auth.password_reset_confirmed",
            member_id=str(member.id),
            tenant=self._slug,
        )
