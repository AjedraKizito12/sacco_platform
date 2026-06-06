"""Lifecycle management for platform-user → tenant impersonation sessions.

The service handles the *request*, *end*, *revoke*, and *queries* paths.
The *create-on-approval* path runs inside the maker-checker executor
(see executors.py), so callers never insert support_impersonations rows
directly.

All methods operate against a platform-scoped session (the caller is
responsible for SET LOCAL search_path TO platform + setting
session.sync_session.info["is_platform"]=True; the standard
get_platform_session dependency does both).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.config import get_settings
from app.modules.maker_checker.models.platform import PlatformApprovalRequest
from app.modules.maker_checker.service import ApprovalService
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.models import Tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ImpersonationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def request(
        self,
        *,
        platform_user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        reason: str,
    ) -> PlatformApprovalRequest:
        """Submit an ApprovalRequest for a new impersonation session.

        Returns the pending approval request; the impersonation row is
        created later by the executor when the checker approves.

        Raises:
            ValueError: if reason is too short, tenant unknown/inactive,
                or platform_user_id has no matching active user.
        """
        if len(reason.strip()) < 10:
            raise ValueError("reason must be at least 10 characters")

        tenant = await self._session.get(Tenant, tenant_id)
        if tenant is None or not tenant.is_active:
            raise ValueError(f"Tenant {tenant_id} not found or inactive")

        settings = get_settings()
        approval = await ApprovalService(self._session).submit(
            operation_type="platform.start_impersonation",
            payload={
                "platform_user_id": str(platform_user_id),
                "tenant_id": str(tenant_id),
                "reason": reason,
            },
            requested_by=platform_user_id,
            required_approvals=settings.impersonation_default_required_approvals,
        )
        return approval  # type: ignore[return-value]

    async def get_by_id(
        self, impersonation_id: uuid.UUID
    ) -> SupportImpersonation | None:
        return await self._session.get(SupportImpersonation, impersonation_id)

    async def get_active_for_user(
        self, *, platform_user_id: uuid.UUID
    ) -> list[SupportImpersonation]:
        """Return non-ended, non-revoked, non-expired impersonations for a user."""
        now = datetime.now(UTC)
        q = (
            select(SupportImpersonation)
            .where(
                SupportImpersonation.platform_user_id == platform_user_id,
                SupportImpersonation.ended_at.is_(None),
                SupportImpersonation.revoked_at.is_(None),
                SupportImpersonation.expires_at > now,
            )
            .order_by(SupportImpersonation.started_at.desc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_all_active(self) -> list[SupportImpersonation]:
        """Return ALL non-ended, non-revoked, non-expired impersonations."""
        now = datetime.now(UTC)
        q = (
            select(SupportImpersonation)
            .where(
                SupportImpersonation.ended_at.is_(None),
                SupportImpersonation.revoked_at.is_(None),
                SupportImpersonation.expires_at > now,
            )
            .order_by(SupportImpersonation.started_at.desc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def is_active(self, impersonation_id: uuid.UUID) -> bool:
        """True iff the row exists, is not ended, not revoked, not expired."""
        row = await self.get_by_id(impersonation_id)
        if row is None:
            return False
        if row.ended_at is not None or row.revoked_at is not None:
            return False
        return row.expires_at > datetime.now(UTC)

    async def end(
        self,
        *,
        impersonation_id: uuid.UUID,
        ended_by: uuid.UUID,
    ) -> SupportImpersonation:
        """Mark an impersonation as ended by its owner.

        The shadow tenant_user deactivation and session revocation
        happen in 02b — this sub-plan only marks the platform-side state.

        Idempotent: re-calling end() on an already-ended row is a no-op.
        """
        row = await self._session.get(SupportImpersonation, impersonation_id)
        if row is None:
            raise ValueError(f"Impersonation {impersonation_id} not found")
        if row.ended_at is None and row.revoked_at is None:
            row.ended_at = datetime.now(UTC)
            row.ended_by = ended_by
        return row

    async def revoke(
        self,
        *,
        impersonation_id: uuid.UUID,
        revoked_by: uuid.UUID,
    ) -> SupportImpersonation:
        """Forcibly revoke an impersonation (admin action).

        Caller must verify revoked_by has the authority. 02b's API gates
        this on a role check via P1.7-05.

        Self-revocation by the impersonator is permitted (functionally
        equivalent to end()). Distinguishing the two preserves audit
        intent.

        Idempotent: re-calling revoke() on an already-revoked row is a no-op.
        """
        row = await self._session.get(SupportImpersonation, impersonation_id)
        if row is None:
            raise ValueError(f"Impersonation {impersonation_id} not found")
        if row.revoked_at is None and row.ended_at is None:
            row.revoked_at = datetime.now(UTC)
            row.revoked_by = revoked_by
        return row

    @staticmethod
    def compute_expires_at(*, started_at: datetime | None = None) -> datetime:
        """Compute expires_at from settings.impersonation_max_minutes.

        Pure helper exposed so the executor and any future re-mint code
        can stay in sync.
        """
        settings = get_settings()
        anchor = started_at or datetime.now(UTC)
        return anchor + timedelta(minutes=settings.impersonation_max_minutes)
