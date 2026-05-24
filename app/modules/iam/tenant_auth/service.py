"""TenantAuthService — login, refresh, and logout for tenant users.

Mirrors PlatformAuthService (Plan 05) with three differences:
  1. Queries TenantUser instead of PlatformUser.
  2. Creates TenantSession rows (no schema= — resolved via search_path).
  3. JWT audience claim is "tenant:<slug>" rather than "platform".
     KeyService is still called with audience="tenant" (the DB column value).

Plans that modify this file later:
  Plan 10: lockout.record_attempt() / lockout.is_locked() calls in login()
  Plan 11: structlog audit event calls in login(), refresh(), logout()
  Plan 07: add me() method
  Plan 08: add reset_request() and reset_confirm() methods
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.config import get_settings
from app.modules.iam.auth_audit import write_tenant_auth_event
from app.modules.iam.lockout import is_locked, record_attempt
from app.modules.iam.lockout import reset as reset_lockout
from app.modules.iam.passwords.service import hash_password, needs_rehash, verify_password
from app.modules.iam.reset_tokens import make_reset_token, verify_reset_token
from app.modules.iam.sessions.models import TenantSession
from app.modules.iam.sessions.service import SessionService
from app.modules.iam.tenant_auth.schemas import TenantTokenResponse
from app.modules.iam.tenant_users.models import TenantUser
from app.modules.iam.tokens.service import (
    decode_token,
    encode_access_token,
    encode_refresh_token,
    get_unverified_kid,
)

_log = structlog.get_logger(__name__)

# Signing key DB column value — used to look up the key, not the JWT aud claim.
_KEY_AUDIENCE = "tenant"


class TenantAuthService:
    """Orchestrates tenant user authentication.

    Args:
        db:          AsyncSession scoped to the tenant schema (search_path set).
        key_service: KeyService instance backed by a platform schema session.
        redis:       Optional Redis async client for O(1) jti revocation checks.
        tenant_slug: Slug of the current tenant (from X-Tenant-Slug header).
                     Embedded in the JWT ``aud`` claim as ``"tenant:<slug>"``.
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
        self._audience = f"tenant:{tenant_slug}"
        self._session_svc = SessionService(
            db=db,
            model_cls=TenantSession,
            redis=redis,
        )

    async def _decode(self, token: str, detail: str) -> dict[str, object]:
        """Extract kid, fetch verification key, then decode and verify the JWT.

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
    ) -> TenantTokenResponse:
        """Full login flow: verify credentials → create session → issue tokens.

        Raises:
            HTTPException 401: unknown email, wrong password, or inactive user.
            HTTPException 423: account locked due to too many failed attempts.
        """
        settings = get_settings()

        # 1. Look up user — generic 401 for both unknown and inactive to
        #    prevent user enumeration.
        result = await self._db.execute(
            select(TenantUser).where(TenantUser.email == email)
        )
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            await record_attempt(email, self._redis)
            await write_tenant_auth_event(
                db=self._db,
                operation="login_failed",
                actor_id=None,
                actor_label=email,
                tenant_slug=self._slug,
                after_state={"email": email, "reason": "user_not_found_or_inactive"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 2. Check lockout — only for users that actually exist.
        locked, retry_after = await is_locked(email, self._redis)
        if locked:
            await write_tenant_auth_event(
                db=self._db,
                operation="login_locked",
                actor_id=user.id,
                actor_label=user.email,
                tenant_slug=self._slug,
                after_state={"email": email, "retry_after": retry_after},
            )
            raise HTTPException(
                status_code=423,
                detail="Account locked due to too many failed attempts",
                headers={"Retry-After": str(retry_after)},
            )

        # 3. Verify password.
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            await record_attempt(email, self._redis)
            await write_tenant_auth_event(
                db=self._db,
                operation="login_failed",
                actor_id=user.id,
                actor_label=user.email,
                tenant_slug=self._slug,
                after_state={"reason": "bad_password"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 4. Successful auth — clear lockout state.
        await reset_lockout(email, self._redis)

        # 5. Transparent rehash — upgrade argon2id parameters if needed.
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)

        # 6. Fetch active signing key for the tenant audience (DB column = "tenant").
        kid, private_key_pem, algorithm = await self._key_service.get_active_signing_key(
            _KEY_AUDIENCE
        )

        # 7. Pre-generate JTI — same value stored on session row and in the
        #    refresh token claims.
        jti = str(uuid.uuid4())

        # 8. Create session row (also writes jti to Redis if redis is set).
        session_row = await self._session_svc.create(
            user_id=user.id,
            jti=jti,
            user_agent=user_agent,
            ip_address=ip_address,
            refresh_ttl_seconds=settings.jwt_refresh_ttl_tenant_seconds,
        )
        # Flush so the ORM applies the Python-side default for session_row.id
        # before we embed it in the JWT payload.
        await self._db.flush()

        # 9. Issue tokens. JWT aud = "tenant:<slug>".
        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=str(user.id),
            audience=self._audience,
            session_id=str(session_row.id),
            actor_type="tenant_user",
            kid=kid,
            private_key_pem=private_key_pem,
            algorithm=algorithm,
            ttl_seconds=access_ttl,
        )
        refresh_token = encode_refresh_token(
            sub=str(user.id),
            audience=self._audience,
            session_id=str(session_row.id),
            jti=jti,
            kid=kid,
            private_key_pem=private_key_pem,
            algorithm=algorithm,
            ttl_seconds=settings.jwt_refresh_ttl_tenant_seconds,
        )

        await write_tenant_auth_event(
            db=self._db,
            operation="login_success",
            actor_id=user.id,
            actor_label=user.email,
            tenant_slug=self._slug,
            after_state={
                "session_id": str(session_row.id),
                "user_agent": user_agent,
                "ip_address": ip_address,
            },
        )

        _log.info("tenant_auth.login_success", user_id=str(user.id), tenant=self._slug)
        return TenantTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=access_ttl,
        )

    # ── refresh ───────────────────────────────────────────────────────────

    async def refresh(self, refresh_token: str) -> TenantTokenResponse:
        """Issue a new access token from a valid, non-revoked refresh token.

        Does NOT rotate the refresh token — the same session stays active.

        Raises:
            HTTPException 401: malformed token, invalid signature, expired token,
                               or revoked/expired session.
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

        # Fetch session — must exist, not be revoked, not be expired.
        session_row = await self._session_svc.get_by_session_id(session_id)
        if session_row is None:
            raise HTTPException(status_code=401, detail="Session not found")
        if session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session has been revoked")
        if session_row.expires_at < datetime.now(UTC):
            raise HTTPException(status_code=401, detail="Session has expired")

        # Defense in depth: jti must match stored value.
        if session_row.jti != str(jti):
            raise HTTPException(status_code=401, detail="Token jti mismatch")

        # Check jti is still valid in Redis (fast revocation path).
        if not await self._session_svc.is_jti_valid(str(jti)):
            raise HTTPException(status_code=401, detail="Session has been revoked")

        # Issue new access token with fresh signing key.
        kid, private_key_pem, algorithm = await self._key_service.get_active_signing_key(
            _KEY_AUDIENCE
        )
        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=str(claims["sub"]),
            audience=self._audience,
            session_id=str(session_id_str),
            actor_type="tenant_user",
            kid=kid,
            private_key_pem=private_key_pem,
            algorithm=algorithm,
            ttl_seconds=access_ttl,
        )

        await self._session_svc.update_last_used(session_id)

        await write_tenant_auth_event(
            db=self._db,
            operation="refresh",
            actor_id=uuid.UUID(str(claims["sub"])),
            tenant_slug=self._slug,
            after_state={"session_id": str(session_id_str)},
        )

        _log.info("tenant_auth.refresh", session_id=str(session_id_str), tenant=self._slug)
        return TenantTokenResponse(
            access_token=access_token,
            refresh_token=None,
            expires_in=access_ttl,
        )

    # ── logout ────────────────────────────────────────────────────────────

    async def logout(self, access_token: str) -> None:
        """Revoke the session associated with the given access token.

        Raises:
            HTTPException 401: malformed or invalid access token.
        """
        claims = await self._decode(access_token, "Invalid or expired access token")

        session_id_str = claims.get("session_id")
        if not session_id_str:
            raise HTTPException(status_code=401, detail="Malformed token claims")

        try:
            session_id = uuid.UUID(str(session_id_str))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Malformed session_id claim") from exc

        await self._session_svc.revoke(session_id)

        await write_tenant_auth_event(
            db=self._db,
            operation="logout",
            actor_id=uuid.UUID(str(claims["sub"])),
            tenant_slug=self._slug,
            after_state={"session_id": str(session_id_str)},
        )

        _log.info("tenant_auth.logout", session_id=str(session_id_str), tenant=self._slug)

    # ── me ────────────────────────────────────────────────────────────────

    async def me(self, access_token: str) -> TenantUser:
        """Return the authenticated TenantUser for the given access token.

        Decodes the token using the tenant-specific audience ("tenant:<slug>"),
        verifies the session is not revoked, and returns the user row.
        The caller (API layer) converts it to TenantUserOut.

        Raises:
            HTTPException 401: invalid/expired token, revoked session, or
                               user not found.
        """
        claims = await self._decode(access_token, "Invalid or expired access token")

        session_id_str = claims.get("session_id")
        sub = claims.get("sub")
        if not session_id_str or not sub:
            raise HTTPException(status_code=401, detail="Malformed token claims")

        try:
            session_id = uuid.UUID(str(session_id_str))
            user_id = uuid.UUID(str(sub))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Malformed token claims") from exc

        session_row = await self._session_svc.get_by_session_id(session_id)
        if session_row is None or session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session not found or revoked")

        result = await self._db.execute(
            select(TenantUser).where(TenantUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        await write_tenant_auth_event(
            db=self._db,
            operation="me",
            actor_id=user.id,
            actor_label=user.email,
            tenant_slug=self._slug,
            after_state={"session_id": str(session_id_str)},
        )

        return user

    # ── reset_request ─────────────────────────────────────────────────────

    async def reset_request(self, email: str) -> None:
        """Request a password reset for a tenant user.

        Always returns None to prevent user enumeration. Identical flow to
        PlatformAuthService.reset_request() but queries TenantUser.
        Writes an audit event to the tenant audit_log.
        """
        settings = get_settings()

        result = await self._db.execute(
            select(TenantUser).where(TenantUser.email == email)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return

        token, jti = make_reset_token(str(user.id), settings.app_secret_key)

        if self._redis is not None:
            await self._redis.set(f"iam:pwreset:{jti}", "1", ex=900)

        _log.warning(
            "PASSWORD RESET TOKEN — dev only, configure email notifier for production",
            email=email,
            tenant=self._slug,
            reset_token=token,
        )

        await write_tenant_auth_event(
            db=self._db,
            operation="password_reset_requested",
            actor_id=user.id,
            actor_label=user.email,
            tenant_slug=self._slug,
            table_name="tenant_users",
        )

    # ── reset_confirm ─────────────────────────────────────────────────────

    async def reset_confirm(self, token: str, new_password: str) -> None:
        """Confirm a tenant user password reset.

        Raises:
            HTTPException 400: invalid/expired token, already-consumed JTI,
                               user not found, or new password too short.
        """
        settings = get_settings()

        try:
            payload = verify_reset_token(token, settings.app_secret_key)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid reset token: {exc}"
            ) from exc

        jti = str(payload["jti"])
        user_id_str = str(payload["sub"])

        if self._redis is not None:
            exists = await self._redis.exists(f"iam:pwreset:{jti}")
            if not exists:
                raise HTTPException(
                    status_code=400,
                    detail="Reset token has already been used or has expired",
                )

        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Malformed token payload"
            ) from exc

        result = await self._db.execute(
            select(TenantUser).where(TenantUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=400, detail="Invalid reset token")

        try:
            user.hashed_password = hash_password(new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if self._redis is not None:
            await self._redis.delete(f"iam:pwreset:{jti}")

        await self._session_svc.revoke_all_for_user(user_id)

        await write_tenant_auth_event(
            db=self._db,
            operation="password_reset_confirmed",
            actor_id=user_id,
            actor_label=user.email,
            tenant_slug=self._slug,
            table_name="tenant_users",
        )

        _log.info(
            "tenant_auth.password_reset_confirmed",
            user_id=str(user.id),
            tenant=self._slug,
        )
