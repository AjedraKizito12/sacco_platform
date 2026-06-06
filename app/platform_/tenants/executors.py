"""Maker-checker executors for tenant operations.

Imported at app startup via app/main.py so the @approval_executor
decorator registers in approval_registry at boot.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.modules.maker_checker.registry import approval_executor
from app.platform_.tenants.service import TenantService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("tenant.suspend")  # type: ignore[misc]
async def execute_tenant_suspend(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: runs when a tenant.suspend approval reaches quorum.

    The maker/checker check is enforced by ApprovalService.approve()
    before this executor runs.

    payload keys:
        tenant_id: str (UUID)
        reason:    str
    """
    tenant_id = uuid.UUID(payload["tenant_id"])
    svc = TenantService(session)
    tenant = await svc.suspend(tenant_id=tenant_id)
    return {
        "tenant_id": str(tenant.id),
        "status": tenant.status,
        "is_active": tenant.is_active,
        "subscription_status": tenant.subscription_status,
    }
