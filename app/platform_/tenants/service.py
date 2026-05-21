"""Tenant service: create, get, list, retry_provisioning."""
import re
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.models import Tenant

_log = structlog.get_logger(__name__)
_SLUG_RE = re.compile(r"^[a-z0-9-]{1,40}$")


def _slug_to_schema(slug: str) -> str:
    return "tenant_" + slug.replace("-", "_")


class TenantService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, *, slug: str, name: str) -> Tenant:
        """Insert a pending tenant row. Raises ValueError on slug conflict."""
        schema_name = _slug_to_schema(slug)
        tenant = Tenant(
            slug=slug,
            schema_name=schema_name,
            name=name,
            status="pending",
            is_active=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._s.add(tenant)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            raise ValueError(f"Slug '{slug}' is already taken") from exc
        return tenant

    async def get(self, tenant_id: uuid.UUID) -> Tenant | None:
        result = await self._s.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def list_tenants(self, *, status: str | None = None) -> list[Tenant]:
        q = select(Tenant).order_by(Tenant.created_at.desc())
        if status:
            q = q.where(Tenant.status == status)
        return list((await self._s.execute(q)).scalars().all())

    async def mark_retry(self, tenant_id: uuid.UUID) -> Tenant:
        """Validate tenant is in failed state; return it for dispatch."""
        tenant = await self.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found")
        if tenant.status != "failed":
            raise ValueError(
                f"retry-provisioning requires status='failed', got '{tenant.status}'"
            )
        return tenant
