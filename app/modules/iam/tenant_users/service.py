"""TenantUserService: CRUD for tenant_users.

Operates within the tenant schema — the caller must supply an AsyncSession
with the correct search_path already set (i.e., via get_tenant_session).

hashed_password is intentionally excluded from create() — users receive a
password reset link (Plan 08) to set their own password. Callers that need
to update hashed_password (auth service, plan 05/06) use update() with the
hashed_password kwarg.
"""
from __future__ import annotations

import uuid  # noqa: TC003
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.modules.iam.tenant_users.models import TenantUser

_log = structlog.get_logger(__name__)


class TenantUserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        email: str,
        full_name: str,
        is_admin: bool = False,
        hashed_password: str | None = None,
    ) -> TenantUser:
        """Insert a new tenant user. Raises ``ValueError`` on duplicate email."""
        now = datetime.now(UTC)
        user = TenantUser(
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            is_active=True,
            is_admin=is_admin,
            created_at=now,
            updated_at=now,
        )
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ValueError(f"Email '{email}' is already registered") from exc
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> TenantUser | None:
        result = await self._session.execute(
            select(TenantUser).where(TenantUser.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> TenantUser | None:
        result = await self._session.execute(
            select(TenantUser).where(TenantUser.email == email)
        )
        return result.scalar_one_or_none()

    async def list(self, *, is_active: bool | None = None) -> list[TenantUser]:
        q = select(TenantUser).order_by(TenantUser.created_at.desc())
        if is_active is not None:
            q = q.where(TenantUser.is_active == is_active)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def update(self, user_id: uuid.UUID, **fields: Any) -> TenantUser | None:
        """Update arbitrary fields on a tenant user.

        Allowed kwargs: full_name, is_active, is_admin, hashed_password,
        last_login_at. Always sets updated_at to now().

        Returns the updated row, or ``None`` if not found.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        allowed = {"full_name", "is_active", "is_admin", "hashed_password", "last_login_at"}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"update() does not accept field '{key}'")
            setattr(user, key, value)
        user.updated_at = datetime.now(UTC)
        return user
