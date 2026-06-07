"""Platform user service: create, get, list, update."""
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.models import PlatformUser

_log = structlog.get_logger(__name__)

# Fields that require maker-checker approval when changed.
MAKER_CHECKER_FIELDS = {"is_active", "is_superuser", "role"}


class PlatformUserService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        email: str,
        full_name: str,
        role: str = "support",
        is_superuser: bool | None = None,
    ) -> PlatformUser:
        """Create a new platform user. Raises ValueError on email conflict.

        ``role`` is authoritative. If ``is_superuser=True`` is passed but
        ``role`` is not 'superuser', role is coerced to 'superuser'. The
        ``is_superuser`` column is kept in sync with role for backward
        compat: is_superuser == (role == 'superuser').
        """
        effective_role = "superuser" if is_superuser else role
        super_flag = effective_role == "superuser"
        user = PlatformUser(
            email=email,
            full_name=full_name,
            role=effective_role,
            is_superuser=super_flag,
            is_active=True,
            hashed_password=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._s.add(user)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            raise ValueError(f"Email '{email}' is already registered") from exc
        return user

    async def get(self, user_id: uuid.UUID) -> PlatformUser | None:
        result = await self._s.execute(
            select(PlatformUser).where(PlatformUser.id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_users(self) -> list[PlatformUser]:
        result = await self._s.execute(
            select(PlatformUser).order_by(PlatformUser.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(
        self,
        user_id: uuid.UUID,
        *,
        full_name: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
        role: str | None = None,
    ) -> PlatformUser:
        """Update user fields. is_active/is_superuser/role changes require
        maker-checker (enforced in API).

        Keeps the is_superuser ↔ role='superuser' invariant. If the caller
        passes ``is_superuser=True``, role is forced to 'superuser'. If
        ``role`` is set to or away from 'superuser', is_superuser tracks.
        """
        user = await self.get(user_id)
        if user is None:
            raise ValueError(f"Platform user {user_id} not found")
        if full_name is not None:
            user.full_name = full_name
        if is_active is not None:
            user.is_active = is_active
        if role is not None:
            user.role = role
            user.is_superuser = role == "superuser"
        if is_superuser is not None:
            # Explicit is_superuser overrides role coercion.
            user.is_superuser = is_superuser
            if is_superuser:
                user.role = "superuser"
            elif user.role == "superuser":
                # Demote role from 'superuser' when is_superuser is being
                # cleared. 'admin' is the next-highest tier.
                user.role = "admin"
        user.updated_at = datetime.now(UTC)
        await self._s.flush()
        return user
