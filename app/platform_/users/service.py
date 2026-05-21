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
MAKER_CHECKER_FIELDS = {"is_active", "is_superuser"}


class PlatformUserService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self, *, email: str, full_name: str, is_superuser: bool = False
    ) -> PlatformUser:
        """Create a new platform user. Raises ValueError on email conflict."""
        user = PlatformUser(
            email=email,
            full_name=full_name,
            is_superuser=is_superuser,
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
    ) -> PlatformUser:
        """Update user fields. is_active/is_superuser require maker-checker (enforced in API)."""
        user = await self.get(user_id)
        if user is None:
            raise ValueError(f"Platform user {user_id} not found")
        if full_name is not None:
            user.full_name = full_name
        if is_active is not None:
            user.is_active = is_active
        if is_superuser is not None:
            user.is_superuser = is_superuser
        user.updated_at = datetime.now(UTC)
        await self._s.flush()
        return user
