"""Platform-admin operations on a tenant's tenant_users table.

The service runs in a TENANT-schema-scoped session (yielded by the new
get_session_for_tenant_schema dep). Audit log writes are automatic via
AuditableMixin on TenantUser; the structlog contextvars carry the
platform actor identity so audit rows show actor_type='platform_user'.

The admin-initiated reset token has a longer TTL than the self-service
flow (24h vs 15min) — this gives the operator time to deliver the token
out of band (phone call, secure messenger) until Phase 3 ships email.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.modules.iam.reset_tokens import make_reset_token
from app.modules.iam.tenant_users.models import TenantUser

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# 24h reset TTL for admin-initiated resets (vs 15min for self-service).
_ADMIN_RESET_TTL_SECONDS = 24 * 60 * 60


class TenantUserConflict(Exception):
    """Raised when a tenant_user with the requested email already exists."""


class TenantUsersAdminService:
    def __init__(
        self,
        session: AsyncSession,
        redis: Any | None = None,
    ) -> None:
        self._db = session
        self._redis = redis

    async def list_users(
        self, *, include_shadows: bool = False
    ) -> list[TenantUser]:
        """List tenant users in the current tenant schema.

        By default filters out shadow users (impersonation_id IS NOT NULL)
        because they exist solely for cross-context impersonation and would
        confuse operators. The portal NEVER includes them.
        """
        q = select(TenantUser).order_by(TenantUser.email)
        if not include_shadows:
            q = q.where(TenantUser.impersonation_id.is_(None))
        return list((await self._db.execute(q)).scalars().all())

    async def get_user(self, user_id: uuid.UUID) -> TenantUser | None:
        """Fetch a real (non-shadow) tenant user by id. Returns None for
        shadow users so the portal cannot accidentally surface them.
        """
        row = await self._db.scalar(
            select(TenantUser).where(
                TenantUser.id == user_id,
                TenantUser.impersonation_id.is_(None),
            )
        )
        return row

    async def create_user(
        self,
        *,
        email: str,
        full_name: str,
        is_admin: bool,
    ) -> tuple[TenantUser, str]:
        """Create a new tenant_user and return (user, password_reset_token).

        The token is a single-use HMAC with a 24h TTL stored in Redis. The
        caller delivers it out of band until Phase 3 ships email.

        Raises:
            TenantUserConflict: a tenant_user with this email already exists.
        """
        settings = get_settings()
        now = datetime.now(UTC)
        user = TenantUser(
            email=email,
            full_name=full_name,
            is_active=True,
            is_admin=is_admin,
            hashed_password=None,
            created_at=now,
            updated_at=now,
        )
        self._db.add(user)
        try:
            await self._db.flush()
        except IntegrityError as exc:
            await self._db.rollback()
            raise TenantUserConflict(
                f"A tenant user with email {email!r} already exists"
            ) from exc

        token, jti = make_reset_token(
            user_id=str(user.id),
            secret=settings.app_secret_key,
            ttl=_ADMIN_RESET_TTL_SECONDS,
        )
        if self._redis is not None:
            await self._redis.set(
                f"iam:pwreset:{jti}", "1", ex=_ADMIN_RESET_TTL_SECONDS
            )

        from app.core.notifications.service import NotificationService  # noqa: PLC0415

        await NotificationService(self._db).publish(
            event_code="password_reset",
            recipient_kind="tenant_user",
            recipient_user_id=user.id,
            recipient_email=user.email,
            context={},
        )
        return user, token

    async def update_user(
        self,
        *,
        user_id: uuid.UUID,
        full_name: str | None = None,
        is_active: bool | None = None,
        is_admin: bool | None = None,
    ) -> TenantUser:
        """Patch a tenant_user. Only the named fields may change.

        Cannot patch shadow users (raises ValueError) — they're managed by
        the impersonation flow.
        """
        user = await self.get_user(user_id)
        if user is None:
            raise ValueError(f"Tenant user {user_id} not found")
        changed = False
        if full_name is not None and user.full_name != full_name:
            user.full_name = full_name
            changed = True
        if is_active is not None and user.is_active != is_active:
            user.is_active = is_active
            changed = True
        if is_admin is not None and user.is_admin != is_admin:
            user.is_admin = is_admin
            changed = True
        if changed:
            user.updated_at = datetime.now(UTC)
        return user

    async def initiate_password_reset(
        self, *, user_id: uuid.UUID
    ) -> tuple[TenantUser, str]:
        """Generate a one-time admin reset token for a tenant_user.

        Returns (user, token). The token has a 24h TTL (longer than the
        self-service flow). JTI stored in Redis.
        """
        settings = get_settings()
        user = await self.get_user(user_id)
        if user is None:
            raise ValueError(f"Tenant user {user_id} not found")
        token, jti = make_reset_token(
            user_id=str(user.id),
            secret=settings.app_secret_key,
            ttl=_ADMIN_RESET_TTL_SECONDS,
        )
        if self._redis is not None:
            await self._redis.set(
                f"iam:pwreset:{jti}", "1", ex=_ADMIN_RESET_TTL_SECONDS
            )

        from app.core.notifications.service import NotificationService  # noqa: PLC0415

        await NotificationService(self._db).publish(
            event_code="password_reset",
            recipient_kind="tenant_user",
            recipient_user_id=user.id,
            recipient_email=user.email,
            context={},
        )
        return user, token

    @staticmethod
    def admin_reset_ttl_seconds() -> int:
        """Exposed so the API layer can include it in the response shape."""
        return _ADMIN_RESET_TTL_SECONDS
