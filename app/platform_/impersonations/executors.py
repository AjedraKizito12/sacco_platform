"""Maker-checker executor for impersonation start.

Registered at import time via @approval_executor("platform.start_impersonation").
Imported at app startup from app/main.py so the decorator runs.

The executor runs inside the platform session of the checker's approval
HTTP request — same transaction as the ApprovalRequest status flip. If this
function raises, ApprovalService catches the exception and marks the request
status='execution_failed' (the row stays uncreated).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.modules.maker_checker.registry import approval_executor
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.service import ImpersonationService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("platform.start_impersonation")  # type: ignore[misc]
async def execute_start_impersonation(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Create the support_impersonations row when a request is approved.

    payload keys:
        platform_user_id: str (UUID) — the requester
        tenant_id:        str (UUID) — target tenant
        reason:           str
        approval_request_id: str (UUID) — set by ApprovalService.approve at
            execute time; used as the idempotency key

    Returns:
        {"impersonation_id": "<uuid>", "expires_at": "<iso>"}

    Idempotency: if a row already exists for approval_request_id, returns
    {"impersonation_id": "<uuid>", "idempotent": True} without creating
    a second row.
    """
    platform_user_id = uuid.UUID(payload["platform_user_id"])
    tenant_id = uuid.UUID(payload["tenant_id"])
    reason = str(payload["reason"])
    # approval_request_id is injected by ApprovalService._execute when the
    # executor is invoked. If the executor is invoked directly (e.g. in tests),
    # the caller is responsible for passing it.
    approval_request_id_raw = payload.get("approval_request_id")
    approval_request_id = (
        uuid.UUID(str(approval_request_id_raw))
        if approval_request_id_raw is not None
        else None
    )

    # Idempotency check
    if approval_request_id is not None:
        existing = await session.scalar(
            select(SupportImpersonation).where(
                SupportImpersonation.approval_request_id == approval_request_id
            )
        )
        if existing is not None:
            return {
                "impersonation_id": str(existing.id),
                "expires_at": existing.expires_at.isoformat(),
                "idempotent": True,
            }

    now = datetime.now(UTC)
    row = SupportImpersonation(
        platform_user_id=platform_user_id,
        tenant_id=tenant_id,
        reason=reason,
        approval_request_id=approval_request_id,
        started_at=now,
        expires_at=ImpersonationService.compute_expires_at(started_at=now),
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()

    return {
        "impersonation_id": str(row.id),
        "expires_at": row.expires_at.isoformat(),
    }
