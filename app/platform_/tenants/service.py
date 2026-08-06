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

    async def list_tenants(
        self, *, status: str | None = None, lifecycle_state: str | None = None
    ) -> list[Tenant]:
        q = select(Tenant).order_by(Tenant.created_at.desc())
        if status:
            q = q.where(Tenant.status == status)
        if lifecycle_state:
            q = q.where(Tenant.lifecycle_state == lifecycle_state)
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

    async def update_name(
        self, *, tenant_id: uuid.UUID, name: str
    ) -> Tenant:
        """Edit the tenant's display name. Slug and schema are immutable."""
        tenant = await self.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found")
        tenant.name = name
        tenant.updated_at = datetime.now(UTC)
        return tenant

    async def suspend(
        self, *, tenant_id: uuid.UUID
    ) -> Tenant:
        """Flip the tenant into the suspended state.

        Called from the `tenant.suspend` maker-checker executor only. Sets:
        - is_active = false (subscription gate denies all tenant requests)
        - status = 'suspended' (lifecycle state)
        - subscription_status = 'suspended' (denormalised gate signal)

        Idempotent — if already suspended, no fields change.
        """
        tenant = await self.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found")
        if tenant.status == "suspended":
            return tenant  # idempotent
        tenant.is_active = False
        tenant.status = "suspended"
        tenant.subscription_status = "suspended"
        tenant.updated_at = datetime.now(UTC)
        return tenant

    async def reactivate(
        self, *, tenant_id: uuid.UUID
    ) -> Tenant:
        """Restore a suspended tenant.

        Sets:
        - is_active = true
        - status = 'active'
        - subscription_status: re-derived from any live subscription. If a
          live subscription exists, use its status; otherwise 'pending'.

        Raises:
            ValueError: tenant unknown, or current status is not 'suspended'.
        """
        # Lazy import to avoid a circular dep at module load time.
        from app.platform_.billing.models import Subscription

        tenant = await self.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found")
        if tenant.status != "suspended":
            raise ValueError(
                f"Tenant {tenant_id} is in status '{tenant.status}', "
                "not 'suspended' — reactivate is only valid from suspended state"
            )

        live = await self._s.scalar(
            select(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.status.in_(("trialing", "active", "past_due")),
            )
            .order_by(Subscription.started_at.desc())
            .limit(1)
        )

        tenant.is_active = True
        tenant.status = "active"
        tenant.subscription_status = live.status if live is not None else "pending"
        if live is not None:
            tenant.current_subscription_id = live.id
        tenant.updated_at = datetime.now(UTC)
        return tenant
