"""OffboardingService — the tenant lifecycle state machine (Phase 7).

The ONLY writer of ``tenants.lifecycle_state``, the ``*_at`` lifecycle
timestamps and ``retention_hold_until``, and the ONLY inserter of
``tenant_lifecycle_events``. The caller (executor / endpoint / beat) owns the
transaction — no method commits.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.platform_.billing.services.subscription_service import SubscriptionService
from app.platform_.models import Tenant, TenantLifecycleEvent

_log = structlog.get_logger(__name__)

# lifecycle_state → the timestamp column stamped when entering that state.
_AT_COLUMN: dict[str, str] = {
    "cancelled": "cancelled_at",
    "read_only": "read_only_at",
    "archived": "archived_at",
    "hard_deleted": "hard_deleted_at",
}

# States a tenant may be restored from — only while it is not yet physically
# archived (archive_checksum is None means the schema is still present).
_RESTORABLE = frozenset({"cancelled", "read_only", "archived"})


class OffboardingError(ValueError):
    """Illegal lifecycle transition."""


class OffboardingService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _get(self, tenant_id: uuid.UUID) -> Tenant:
        tenant = await self._s.get(Tenant, tenant_id)
        if tenant is None:
            raise OffboardingError(f"Tenant {tenant_id} not found")
        return tenant

    async def _transition(
        self,
        tenant: Tenant,
        to_state: str,
        *,
        actor_id: uuid.UUID | None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        publish: bool = True,
    ) -> None:
        """Flip lifecycle_state, stamp the matching *_at, audit + notify the move."""
        from_state = tenant.lifecycle_state
        tenant.lifecycle_state = to_state
        col = _AT_COLUMN.get(to_state)
        if col is not None:
            setattr(tenant, col, datetime.now(UTC))
        self._s.add(
            TenantLifecycleEvent(
                tenant_id=tenant.id,
                from_state=from_state,
                to_state=to_state,
                actor_id=actor_id,
                reason=reason,
                event_metadata=metadata or {},
            )
        )
        if publish:
            from app.platform_.tenants.events import publish_lifecycle_event

            await publish_lifecycle_event(self._s, tenant=tenant, to_state=to_state)

    # ── Operator-driven transitions ─────────────────────────────────────────

    async def cancel(
        self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, reason: str
    ) -> Tenant:
        """active → cancelled, and hard-cancel billing in the same transaction."""
        tenant = await self._get(tenant_id)
        if tenant.lifecycle_state != "active":
            raise OffboardingError(
                f"Cannot cancel tenant in state '{tenant.lifecycle_state}'"
            )
        await self._transition(tenant, "cancelled", actor_id=actor_id, reason=reason)
        if tenant.current_subscription_id is not None:
            await SubscriptionService(self._s).cancel(
                subscription_id=tenant.current_subscription_id,
                reason=f"Tenant offboarding: {reason}",
                cancel_at_period_end=False,
            )
        return tenant

    async def restore(
        self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ) -> Tenant:
        """Restore a not-yet-physically-archived tenant back to active."""
        tenant = await self._get(tenant_id)
        if tenant.lifecycle_state not in _RESTORABLE:
            raise OffboardingError(
                f"Cannot restore tenant in state '{tenant.lifecycle_state}'"
            )
        if tenant.archive_checksum is not None:
            raise OffboardingError("Tenant already physically archived")
        await self._transition(tenant, "active", actor_id=actor_id)
        tenant.cancelled_at = None
        tenant.read_only_at = None
        tenant.archived_at = None
        return tenant

    async def extend_retention(
        self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, hold_until: datetime
    ) -> Tenant:
        """Push out the retention window (legal hold). Records a same-state event."""
        tenant = await self._get(tenant_id)
        tenant.retention_hold_until = hold_until
        self._s.add(
            TenantLifecycleEvent(
                tenant_id=tenant.id,
                from_state=tenant.lifecycle_state,
                to_state=tenant.lifecycle_state,
                actor_id=actor_id,
                reason="retention extended",
                event_metadata={"retention_hold_until": hold_until.isoformat()},
            )
        )
        return tenant

    # ── Time-based sweeps (driven by the daily beat) ────────────────────────

    async def sweep_cancelled_to_read_only(self, *, now: datetime) -> list[uuid.UUID]:
        cutoff = now - timedelta(days=get_settings().offboarding_read_only_days)
        rows = (
            await self._s.execute(
                select(Tenant).where(
                    Tenant.lifecycle_state == "cancelled",
                    Tenant.cancelled_at <= cutoff,
                )
            )
        ).scalars().all()
        for tenant in rows:
            await self._transition(tenant, "read_only", actor_id=None)
        return [t.id for t in rows]

    async def sweep_read_only_to_archived(self, *, now: datetime) -> list[uuid.UUID]:
        cutoff = now - timedelta(days=get_settings().offboarding_archive_days)
        rows = (
            await self._s.execute(
                select(Tenant).where(
                    Tenant.lifecycle_state == "read_only",
                    Tenant.read_only_at <= cutoff,
                    (Tenant.retention_hold_until.is_(None))
                    | (Tenant.retention_hold_until <= now),
                )
            )
        ).scalars().all()
        for tenant in rows:
            await self._transition(tenant, "archived", actor_id=None)
        return [t.id for t in rows]

    async def sweep_archived_to_hard_deleted(self, *, now: datetime) -> list[uuid.UUID]:
        cutoff = now - timedelta(days=get_settings().offboarding_hard_delete_days)
        rows = (
            await self._s.execute(
                select(Tenant).where(
                    Tenant.lifecycle_state == "archived",
                    Tenant.archived_at <= cutoff,
                )
            )
        ).scalars().all()
        for tenant in rows:
            await self._transition(tenant, "hard_deleted", actor_id=None)
        return [t.id for t in rows]

    # ── Read ────────────────────────────────────────────────────────────────

    async def lifecycle_events(
        self, *, tenant_id: uuid.UUID
    ) -> list[TenantLifecycleEvent]:
        return list(
            (
                await self._s.execute(
                    select(TenantLifecycleEvent)
                    .where(TenantLifecycleEvent.tenant_id == tenant_id)
                    .order_by(TenantLifecycleEvent.occurred_at)
                )
            )
            .scalars()
            .all()
        )
