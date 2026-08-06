"""Tenant offboarding outbox event types + publish helper (Phase 7).

Each lifecycle transition publishes a platform-outbox event; the
notifications.offboarding_consumer bridges it to tenant-admin feeds
(offboarding runs in platform transactions, but recipients read
tenant-schema feeds). Notices only — no secrets/PII in the payload.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.outbox.publisher import EventPublisher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.platform_.models import Tenant

TENANT_OFFBOARDING_CANCELLED = "TenantOffboardingCancelled"
TENANT_OFFBOARDING_READ_ONLY = "TenantOffboardingReadOnly"
TENANT_OFFBOARDING_ARCHIVED = "TenantOffboardingArchived"
TENANT_OFFBOARDING_RESTORED = "TenantOffboardingRestored"

# to_state → outbox event_type. hard_deleted has no notice (the feed is gone);
# "active" is only reached via restore.
_EVENT_FOR_STATE: dict[str, str] = {
    "cancelled": TENANT_OFFBOARDING_CANCELLED,
    "read_only": TENANT_OFFBOARDING_READ_ONLY,
    "archived": TENANT_OFFBOARDING_ARCHIVED,
    "active": TENANT_OFFBOARDING_RESTORED,
}


async def publish_lifecycle_event(
    session: AsyncSession, *, tenant: Tenant, to_state: str
) -> None:
    """Publish the platform-outbox notice for a lifecycle transition, if any."""
    event_type = _EVENT_FOR_STATE.get(to_state)
    if event_type is None:
        return
    await EventPublisher.publish(
        session,
        aggregate_type="tenant",
        aggregate_id=tenant.id,
        event_type=event_type,
        payload={
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "to_state": to_state,
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
