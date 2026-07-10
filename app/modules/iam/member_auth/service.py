"""MemberAuthService — member portal authentication (Phase 4a).

Mirrors TenantAuthService but queries Member (not TenantUser), creates
MemberSession rows, and issues JWTs with aud="member:<slug>". The signing key
is still looked up with audience "tenant" (the DB column value) — the aud claim
alone provides member/operator isolation.

Login/refresh/logout/me are added in the next task.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.config import get_settings
from app.modules.iam.auth_audit import write_member_auth_event
from app.modules.iam.lockout import is_locked, record_attempt
from app.modules.iam.lockout import reset as reset_lockout
from app.modules.iam.member_auth.schemas import MemberTokenResponse
from app.modules.iam.passwords.service import hash_password, needs_rehash, verify_password
from app.modules.iam.reset_tokens import make_reset_token, verify_reset_token
from app.modules.iam.sessions.models import MemberSession
from app.modules.iam.sessions.service import SessionService
from app.modules.iam.tokens.service import (
    decode_token,
    encode_access_token,
    encode_refresh_token,
    get_unverified_kid,
)
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

    @staticmethod
    def _is_eligible(member: Member) -> bool:
        """A member may log in only when enabled, password-set, and active."""
        return bool(
            member.portal_enabled
            and member.hashed_password
            and member.status == "active"
        )

    async def _decode(self, token: str, detail: str) -> dict[str, object]:
        """Extract kid, fetch verification key, decode + verify the JWT.

        Raises HTTPException 401 with *detail* on any failure.
        """
        try:
            kid = get_unverified_kid(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=detail) from exc
        try:
            public_key_pem, algorithm, _aud = await self._key_service.get_verification_key(kid)
        except Exception as exc:
            raise HTTPException(status_code=401, detail=detail) from exc
        try:
            return decode_token(
                token,
                audience=self._audience,
                public_key_pem=public_key_pem,
                algorithm=algorithm,
            )
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=detail) from exc

    # ── login ─────────────────────────────────────────────────────────────

    async def login(
        self,
        email: str,
        password: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> MemberTokenResponse:
        """Verify credentials → create session → issue tokens.

        Raises:
            HTTPException 401: unknown email, wrong password, or ineligible member.
            HTTPException 423: account locked due to too many failed attempts.
        """
        settings = get_settings()
        member = await self._get_member_by_email(email)

        # Generic 401 for unknown or ineligible — prevents enumeration.
        if member is None or not self._is_eligible(member):
            await record_attempt(email, self._redis)
            await write_member_auth_event(
                db=self._db,
                operation="login_failed",
                actor_id=None,
                actor_label=email,
                tenant_slug=self._slug,
                after_state={"reason": "not_found_or_ineligible"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        locked, retry_after = await is_locked(email, self._redis)
        if locked:
            await write_member_auth_event(
                db=self._db,
                operation="login_locked",
                actor_id=member.id,
                actor_label=member.email,
                tenant_slug=self._slug,
                after_state={"retry_after": retry_after},
            )
            raise HTTPException(
                status_code=423,
                detail="Account locked due to too many failed attempts",
                headers={"Retry-After": str(retry_after)},
            )

        # _is_eligible already guarantees a non-null hash; the explicit check
        # also narrows the type for verify_password.
        if not member.hashed_password or not verify_password(password, member.hashed_password):
            await record_attempt(email, self._redis)
            await write_member_auth_event(
                db=self._db,
                operation="login_failed",
                actor_id=member.id,
                actor_label=member.email,
                tenant_slug=self._slug,
                after_state={"reason": "bad_password"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        await reset_lockout(email, self._redis)
        if needs_rehash(member.hashed_password):
            member.hashed_password = hash_password(password)

        kid, private_key_pem, algorithm = await self._key_service.get_active_signing_key(
            _KEY_AUDIENCE
        )
        jti = str(uuid.uuid4())
        session_row = await self._session_svc.create(
            user_id=member.id,
            jti=jti,
            user_agent=user_agent,
            ip_address=ip_address,
            refresh_ttl_seconds=settings.jwt_refresh_ttl_member_seconds,
        )
        await self._db.flush()

        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=str(member.id),
            audience=self._audience,
            session_id=str(session_row.id),
            actor_type="member",
            kid=kid,
            private_key_pem=private_key_pem,
            algorithm=algorithm,
            ttl_seconds=access_ttl,
        )
        refresh_token = encode_refresh_token(
            sub=str(member.id),
            audience=self._audience,
            session_id=str(session_row.id),
            jti=jti,
            kid=kid,
            private_key_pem=private_key_pem,
            algorithm=algorithm,
            ttl_seconds=settings.jwt_refresh_ttl_member_seconds,
        )

        # last_login_at via targeted UPDATE — bypasses the AuditableMixin diff so
        # routine logins don't spam the audit log (same spirit as last_used_at).
        await self._db.execute(
            update(Member)
            .where(Member.id == member.id)
            .values(last_login_at=datetime.now(UTC))
        )

        await write_member_auth_event(
            db=self._db,
            operation="login_success",
            actor_id=member.id,
            actor_label=member.email,
            tenant_slug=self._slug,
            after_state={"session_id": str(session_row.id), "ip_address": ip_address},
        )
        _log.info("member_auth.login_success", member_id=str(member.id), tenant=self._slug)
        return MemberTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=access_ttl,
        )

    # ── refresh ───────────────────────────────────────────────────────────

    async def refresh(self, refresh_token: str) -> MemberTokenResponse:
        """Issue a new access token from a valid, non-revoked refresh token.

        Does NOT rotate the refresh token — the same session stays active.
        """
        settings = get_settings()
        claims = await self._decode(refresh_token, "Invalid or expired refresh token")

        session_id_str = claims.get("session_id")
        jti = claims.get("jti")
        if not session_id_str or not jti:
            raise HTTPException(status_code=401, detail="Malformed token claims")
        try:
            session_id = uuid.UUID(str(session_id_str))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Malformed session_id claim") from exc

        session_row = await self._session_svc.get_by_session_id(session_id)
        if session_row is None:
            raise HTTPException(status_code=401, detail="Session not found")
        if session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session has been revoked")
        if session_row.expires_at < datetime.now(UTC):
            raise HTTPException(status_code=401, detail="Session has expired")
        if session_row.jti != str(jti):
            raise HTTPException(status_code=401, detail="Token jti mismatch")
        if not await self._session_svc.is_jti_valid(str(jti)):
            raise HTTPException(status_code=401, detail="Session has been revoked")

        kid, private_key_pem, algorithm = await self._key_service.get_active_signing_key(
            _KEY_AUDIENCE
        )
        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=str(claims["sub"]),
            audience=self._audience,
            session_id=str(session_id_str),
            actor_type="member",
            kid=kid,
            private_key_pem=private_key_pem,
            algorithm=algorithm,
            ttl_seconds=access_ttl,
        )
        await self._session_svc.update_last_used(session_id)
        await write_member_auth_event(
            db=self._db,
            operation="refresh",
            actor_id=uuid.UUID(str(claims["sub"])),
            tenant_slug=self._slug,
            after_state={"session_id": str(session_id_str)},
        )
        return MemberTokenResponse(
            access_token=access_token, refresh_token=None, expires_in=access_ttl
        )

    # ── logout ────────────────────────────────────────────────────────────

    async def logout(self, access_token: str) -> None:
        """Revoke the session associated with the given access token."""
        claims = await self._decode(access_token, "Invalid or expired access token")
        session_id_str = claims.get("session_id")
        if not session_id_str:
            raise HTTPException(status_code=401, detail="Malformed token claims")
        try:
            session_id = uuid.UUID(str(session_id_str))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Malformed session_id claim") from exc

        await self._session_svc.revoke(session_id)
        await write_member_auth_event(
            db=self._db,
            operation="logout",
            actor_id=uuid.UUID(str(claims["sub"])),
            tenant_slug=self._slug,
            after_state={"session_id": str(session_id_str)},
        )

    # ── me ────────────────────────────────────────────────────────────────

    async def me(self, access_token: str) -> Member:
        """Return the authenticated Member for the given access token."""
        claims = await self._decode(access_token, "Invalid or expired access token")
        session_id_str = claims.get("session_id")
        sub = claims.get("sub")
        if not session_id_str or not sub:
            raise HTTPException(status_code=401, detail="Malformed token claims")
        try:
            session_id = uuid.UUID(str(session_id_str))
            member_id = uuid.UUID(str(sub))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Malformed token claims") from exc

        session_row = await self._session_svc.get_by_session_id(session_id)
        if session_row is None or session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session not found or revoked")

        member = await self._get_member_by_id(member_id)
        if member is None:
            raise HTTPException(status_code=401, detail="Member not found")
        return member

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

        from app.core.notifications.service import NotificationService  # noqa: PLC0415

        await NotificationService(self._db).publish(
            event_code="password_reset",
            recipient_kind="member",
            recipient_user_id=member.id,
            recipient_email=member.email,
            context={},
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
