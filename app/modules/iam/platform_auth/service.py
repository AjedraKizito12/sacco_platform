"""PlatformAuthService — login, refresh, and logout for platform users.

Each method is intentionally stateless between calls (no cached user objects).
Lockout tracking (Plan 10) and audit events (Plan 11) will be added as
in-place modifications to login(), refresh(), and logout() respectively.

The service receives a DB session scoped to the platform schema, a KeyService
(for signing/verification key lookups), and an optional Redis client (passed
through to SessionService for O(1) jti revocation checks).

Plans that modify this file later:
- Plan 10: lockout.record_attempt() / lockout.is_locked() calls in login()
- Plan 11: structlog audit event calls in login(), refresh(), logout()
- Plan 07: add me() method
- Plan 08: add reset_request() and reset_confirm() methods
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
from app.core.observability import metrics
from app.modules.iam.auth_audit import write_platform_auth_event
from app.modules.iam.lockout import is_locked, record_attempt
from app.modules.iam.lockout import reset as reset_lockout
from app.modules.iam.passwords.service import hash_password, needs_rehash, verify_password
from app.modules.iam.platform_auth.schemas import PlatformTokenResponse
from app.modules.iam.reset_tokens import make_reset_token, verify_reset_token
from app.modules.iam.sessions.models import PlatformSession
from app.modules.iam.sessions.service import SessionService
from app.modules.iam.tokens.service import (
    decode_token,
    encode_access_token,
    encode_refresh_token,
    get_unverified_kid,
)
from app.platform_.models import PlatformUser

_log = structlog.get_logger(__name__)

_AUDIENCE = "platform"


class PlatformAuthService:
    """Orchestrates platform user authentication.

    Args:
        db:          SQLAlchemy async session bound to the platform schema.
        key_service: KeyService instance for signing and verification key lookups.
        redis:       Optional Redis async client. When present, jti lookups are
                     O(1) Redis GETs; when absent (tests), falls back to DB query.
    """

    def __init__(
        self,
        db: AsyncSession,
        key_service: Any,
        redis: Any | None = None,
    ) -> None:
        self._db = db
        self._key_service = key_service
        self._redis = redis
        self._session_svc = SessionService(
            db=db,
            model_cls=PlatformSession,
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
                audience=_AUDIENCE,
                public_key_pem=public_key_pem,
                algorithm=algorithm,
            )
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=detail) from exc

    # ── login ──────────────────────────────────────────────────────────────

    async def login(
        self,
        email: str,
        password: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> PlatformTokenResponse:
        """Full login flow: verify credentials → create session → issue tokens.

        Raises:
            HTTPException 401: unknown email, wrong password, or inactive user.
            HTTPException 423: account locked due to too many failed attempts.
        """
        settings = get_settings()

        # 1. Look up user — generic 401 for both unknown and inactive to
        #    prevent user enumeration.
        result = await self._db.execute(
            select(PlatformUser).where(PlatformUser.email == email)
        )
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            await record_attempt(email, self._redis)
            await write_platform_auth_event(
                db=self._db,
                operation="login_failed",
                actor_id=None,
                actor_label=email,
                after_state={"email": email, "reason": "user_not_found_or_inactive"},
            )
            metrics.auth_login_attempts.add(
                1, {"outcome": "invalid_credentials", "actor_type": "platform_user"}
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 2. Check lockout — only for users that actually exist.
        locked, retry_after = await is_locked(email, self._redis)
        if locked:
            await write_platform_auth_event(
                db=self._db,
                operation="login_locked",
                actor_id=user.id,
                actor_label=user.email,
                after_state={"email": email, "retry_after": retry_after},
            )
            metrics.auth_login_attempts.add(
                1, {"outcome": "locked", "actor_type": "platform_user"}
            )
            raise HTTPException(
                status_code=423,
                detail="Account locked due to too many failed attempts",
                headers={"Retry-After": str(retry_after)},
            )

        # 3. Verify password.
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            await record_attempt(email, self._redis)
            await write_platform_auth_event(
                db=self._db,
                operation="login_failed",
                actor_id=user.id,
                actor_label=user.email,
                after_state={"reason": "bad_password"},
            )
            metrics.auth_login_attempts.add(
                1, {"outcome": "invalid_credentials", "actor_type": "platform_user"}
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 4. Successful auth — clear lockout state.
        await reset_lockout(email, self._redis)

        # 5. Transparent rehash — upgrade argon2id parameters if needed.
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)

        # 6. Fetch active signing key for this audience.
        kid, private_key_pem, algorithm = await self._key_service.get_active_signing_key(
            _AUDIENCE
        )

        # 7. Pre-generate JTI so the same value lands on the session row and
        #    inside the refresh token's claims.
        jti = str(uuid.uuid4())

        # 8. Create session row (also writes jti to Redis if redis is set).
        session_row = await self._session_svc.create(
            user_id=user.id,
            jti=jti,
            user_agent=user_agent,
            ip_address=ip_address,
            refresh_ttl_seconds=settings.jwt_refresh_ttl_platform_seconds,
        )
        # Flush so the ORM applies the Python-side default for session_row.id
        # before we embed it in the JWT payload.
        await self._db.flush()

        # 9. Issue tokens.
        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=str(user.id),
            audience=_AUDIENCE,
            session_id=str(session_row.id),
            actor_type="platform_user",
            kid=kid,
            private_key_pem=private_key_pem,
            algorithm=algorithm,
            ttl_seconds=access_ttl,
        )
        refresh_token = encode_refresh_token(
            sub=str(user.id),
            audience=_AUDIENCE,
            session_id=str(session_row.id),
            jti=jti,
            kid=kid,
            private_key_pem=private_key_pem,
            algorithm=algorithm,
            ttl_seconds=settings.jwt_refresh_ttl_platform_seconds,
        )

        await write_platform_auth_event(
            db=self._db,
            operation="login_success",
            actor_id=user.id,
            actor_label=user.email,
            after_state={
                "session_id": str(session_row.id),
                "user_agent": user_agent,
                "ip_address": ip_address,
            },
        )

        _log.info("platform_auth.login_success", user_id=str(user.id))
        metrics.auth_login_attempts.add(
            1, {"outcome": "success", "actor_type": "platform_user"}
        )
        return PlatformTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=access_ttl,
        )

    # ── refresh ────────────────────────────────────────────────────────────

    async def refresh(self, refresh_token: str) -> PlatformTokenResponse:
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
            _AUDIENCE
        )
        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=str(claims["sub"]),
            audience=_AUDIENCE,
            session_id=str(session_id_str),
            actor_type="platform_user",
            kid=kid,
            private_key_pem=private_key_pem,
            algorithm=algorithm,
            ttl_seconds=access_ttl,
        )

        await self._session_svc.update_last_used(session_id)

        await write_platform_auth_event(
            db=self._db,
            operation="refresh",
            actor_id=uuid.UUID(str(claims["sub"])),
            after_state={"session_id": str(session_id_str)},
        )

        _log.info("platform_auth.refresh", session_id=str(session_id_str))
        return PlatformTokenResponse(
            access_token=access_token,
            refresh_token=None,
            expires_in=access_ttl,
        )

    # ── logout ─────────────────────────────────────────────────────────────

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

        await write_platform_auth_event(
            db=self._db,
            operation="logout",
            actor_id=uuid.UUID(str(claims["sub"])),
            after_state={"session_id": str(session_id_str)},
        )

        _log.info("platform_auth.logout", session_id=str(session_id_str))

    # ── me ─────────────────────────────────────────────────────────────────

    async def me(self, access_token: str) -> PlatformUser:
        """Return the authenticated PlatformUser for the given access token.

        Decodes the token, verifies the session is not revoked, then fetches
        and returns the user row. The caller (API layer) converts it to
        PlatformUserOut.

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

        # Verify session is not revoked (revocation takes effect immediately).
        session_row = await self._session_svc.get_by_session_id(session_id)
        if session_row is None or session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session not found or revoked")

        result = await self._db.execute(
            select(PlatformUser).where(PlatformUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        await write_platform_auth_event(
            db=self._db,
            operation="me",
            actor_id=user.id,
            actor_label=user.email,
            after_state={"session_id": str(session_id_str)},
        )

        return user

    # ── reset_request ─────────────────────────────────────────────────────

    async def reset_request(self, email: str) -> None:
        """Send a password reset token to the given email address.

        Always returns None — never reveals whether the email exists
        (prevents user enumeration).

        If the user exists:
          1. Generates a signed HMAC token (15-minute expiry).
          2. Stores the JTI in Redis for single-use enforcement.
          3. Logs the token to structlog (replace with email notifier in prod).
          4. Writes an audit event to platform.audit_log.
        """
        settings = get_settings()

        result = await self._db.execute(
            select(PlatformUser).where(PlatformUser.email == email)
        )
        user = result.scalar_one_or_none()
        if user is None:
            # Return silently — caller gets the same 204 regardless.
            return

        token, jti = make_reset_token(str(user.id), settings.app_secret_key)

        if self._redis is not None:
            await self._redis.set(f"iam:pwreset:{jti}", "1", ex=900)

        # Production: replace this log call with an email send.
        _log.warning(
            "PASSWORD RESET TOKEN — dev only, configure email notifier for production",
            email=email,
            reset_token=token,
        )

        await write_platform_auth_event(
            db=self._db,
            operation="password_reset_requested",
            actor_id=user.id,
            actor_label=user.email,
            table_name="platform_users",
        )

        from app.core.notifications.service import NotificationService  # noqa: PLC0415

        await NotificationService(self._db, platform=True).publish(
            event_code="password_reset",
            recipient_kind="platform_user",
            recipient_user_id=user.id,
            recipient_email=user.email,
            context={},
        )

    # ── reset_confirm ─────────────────────────────────────────────────────

    async def reset_confirm(self, token: str, new_password: str) -> None:
        """Confirm a password reset: validate token, set new password, revoke sessions.

        Raises:
            HTTPException 400: invalid/expired token, already-consumed JTI,
                               user not found, or new password too short.
        """
        settings = get_settings()

        # 1. Verify token signature and expiry.
        try:
            payload = verify_reset_token(token, settings.app_secret_key)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid reset token: {exc}"
            ) from exc

        jti = str(payload["jti"])
        user_id_str = str(payload["sub"])

        # 2. Check Redis: token must not have been consumed already.
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

        # 3. Fetch user.
        result = await self._db.execute(
            select(PlatformUser).where(PlatformUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=400, detail="Invalid reset token")

        # 4. Hash new password — hash_password raises ValueError if too short.
        try:
            user.hashed_password = hash_password(new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # 5. Consume the JTI so the token cannot be reused.
        if self._redis is not None:
            await self._redis.delete(f"iam:pwreset:{jti}")

        # 6. Revoke all active sessions — forces re-login with new password.
        await self._session_svc.revoke_all_for_user(user_id)

        await write_platform_auth_event(
            db=self._db,
            operation="password_reset_confirmed",
            actor_id=user_id,
            actor_label=user.email,
            table_name="platform_users",
        )

        _log.info("platform_auth.password_reset_confirmed", user_id=str(user.id))
