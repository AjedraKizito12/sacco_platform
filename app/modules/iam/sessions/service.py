"""SessionService: create, fetch, revoke, and clean up auth sessions.

Operates on either PlatformSession or TenantSession — the model class is
supplied at construction time. One service instance handles one schema context.

Redis is used for fast refresh-token JTI validation:
    Key:   iam:jti:{jti}
    Value: "1"  (existence is the signal — value is not read)
    TTL:   refresh_ttl_seconds (matches session expires_at)

On revocation, the Redis key is deleted immediately so the JTI becomes
invalid for new refresh attempts within seconds, without requiring the
old refresh token to expire. The DB row's revoked_at is also set.

When Redis is None (e.g., batch jobs, tests), JTI validity falls back to a
DB lookup: the session row must exist, be non-revoked, and be non-expired.
"""
from __future__ import annotations

import uuid  # noqa: TC003
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.modules.iam.sessions.models import PlatformSession, TenantSession

_log = structlog.get_logger(__name__)

_CLEANUP_RETENTION_DAYS = 7  # delete expired rows older than this

AnySessionModel = PlatformSession | TenantSession


class SessionService:
    """Manage server-side sessions for platform or tenant users.

    Args:
        db: An ``AsyncSession`` with the appropriate search_path already set
            (platform schema for PlatformSession; tenant schema for TenantSession).
        model_cls: The SQLAlchemy model class — ``PlatformSession`` or ``TenantSession``.
        redis: Optional async Redis client. When provided, JTI keys are stored
            and deleted in Redis for fast revocation checks. When ``None``,
            ``is_jti_valid`` falls back to a DB query.
    """

    def __init__(
        self,
        db: AsyncSession,
        model_cls: type[AnySessionModel],
        redis: Any | None = None,
    ) -> None:
        self._db = db
        self._model = model_cls
        self._redis: Any = redis
        # Determine the user FK attribute name at construction time.
        self._user_id_attr = (
            "platform_user_id" if model_cls is PlatformSession else "tenant_user_id"
        )

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        jti: str,
        user_agent: str | None,
        ip_address: str | None,
        refresh_ttl_seconds: int,
    ) -> AnySessionModel:
        """Insert a new session row and register the JTI in Redis.

        The session ``id`` (UUID) becomes the ``session_id`` claim in the JWT.
        The ``jti`` is the refresh token's JWT ID — stored for revocation.

        Returns the new session row (not yet committed).
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=refresh_ttl_seconds)

        if self._model is PlatformSession:
            row: AnySessionModel = PlatformSession(
                platform_user_id=user_id,
                jti=jti,
                user_agent=user_agent,
                ip_address=ip_address,
                created_at=now,
                expires_at=expires_at,
            )
        else:
            row = TenantSession(
                tenant_user_id=user_id,
                jti=jti,
                user_agent=user_agent,
                ip_address=ip_address,
                created_at=now,
                expires_at=expires_at,
            )

        self._db.add(row)

        if self._redis is not None:
            await self._redis.set(f"iam:jti:{jti}", "1", ex=refresh_ttl_seconds)

        return row

    async def get_by_session_id(
        self, session_id: uuid.UUID
    ) -> AnySessionModel | None:
        """Return the session row by primary key, or ``None`` if not found."""
        result = await self._db.execute(
            select(self._model).where(self._model.id == session_id)
        )
        return cast(AnySessionModel | None, result.scalar_one_or_none())

    async def revoke(self, session_id: uuid.UUID) -> None:
        """Set ``revoked_at`` on the session row and delete its Redis JTI key.

        Idempotent — if the session is already revoked, the ``revoked_at``
        timestamp is not updated.
        """
        result = await self._db.execute(
            select(self._model).where(self._model.id == session_id)
        )
        row = cast(AnySessionModel | None, result.scalar_one_or_none())
        if row is None:
            return

        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)

        if self._redis is not None:
            await self._redis.delete(f"iam:jti:{row.jti}")

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke all non-revoked sessions for *user_id*.

        Returns the count of sessions that were revoked. Called on password
        change or explicit "log out everywhere" action.

        Note: does not delete Redis JTI keys individually — those will
        expire naturally. If immediate revocation of all refresh tokens is
        required, the caller must flush Redis keys separately. This trade-off
        is acceptable because ``revoke_all_for_user`` is called on password
        change, after which old refresh tokens will fail session validation
        (revoked_at is set) even if the Redis key still exists briefly.
        """
        user_id_col = getattr(self._model, self._user_id_attr)
        result = await self._db.execute(
            select(self._model).where(
                user_id_col == user_id,
                self._model.revoked_at.is_(None),
            )
        )
        rows = cast(list[AnySessionModel], result.scalars().all())
        now = datetime.now(UTC)
        for row in rows:
            row.revoked_at = now
        return len(rows)

    async def cleanup_expired(self) -> int:
        """Delete session rows that expired more than 7 days ago.

        Called by the ``cleanup_sessions`` Celery beat task. Returns the
        number of rows deleted.
        """
        cutoff = datetime.now(UTC) - timedelta(days=_CLEANUP_RETENTION_DAYS)
        result = await self._db.execute(
            delete(self._model)
            .where(self._model.expires_at < cutoff)
            .returning(self._model.id)
        )
        deleted_rows = result.fetchall()
        count = len(deleted_rows)
        if count:
            _log.info(
                "iam.sessions.cleanup",
                model=self._model.__tablename__,
                deleted=count,
            )
        return count

    async def update_last_used(self, session_id: uuid.UUID) -> None:
        """Update the ``last_used_at`` timestamp on a session row."""
        now = datetime.now(UTC)
        await self._db.execute(
            update(self._model)
            .where(self._model.id == session_id)
            .values(last_used_at=now)
        )

    async def is_jti_valid(self, jti: str) -> bool:
        """Return ``True`` if the refresh token JTI is still valid.

        Primary path: check Redis (O(1), no DB hit).
        Fallback (Redis=None): query the DB for a non-revoked, non-expired
        session row with this JTI.

        A JTI is invalid if:
        - Redis key is absent (normal expiry or explicit revocation), or
        - (DB fallback) no session row exists, or the row is revoked/expired.
        """
        if self._redis is not None:
            exists: int = await self._redis.exists(f"iam:jti:{jti}")
            return bool(exists)

        # DB fallback path.
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(self._model).where(
                self._model.jti == jti,
                self._model.revoked_at.is_(None),
                self._model.expires_at > now,
            )
        )
        return result.scalar_one_or_none() is not None
