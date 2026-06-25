from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.members.models import Member

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"active", "exited"},
    "active": {"suspended", "exited"},
    "suspended": {"active", "exited"},
    "exited": set(),  # terminal state
}

_log = structlog.get_logger(__name__)


class MemberService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enable_portal_access(
        self, member_id: uuid.UUID, *, key_service: Any, redis: Any, tenant_slug: str
    ) -> tuple[str, int]:
        """Enable member portal access via the IAM MemberAuthService.

        Credential writes are owned by IAM (architectural rule 2 — cross-module
        work goes through a service interface, not direct model writes here).
        Returns (set_password_token, ttl_seconds).
        """
        from app.modules.iam.member_auth.service import MemberAuthService

        auth_svc = MemberAuthService(
            db=self._session, key_service=key_service, redis=redis, tenant_slug=tenant_slug
        )
        return await auth_svc.enable_access(member_id)

    # ── Aggregates (read-only, dashboard) ─────────────────────────────────────

    async def count_by_status(self) -> dict[str, int]:
        """Return member counts grouped by status (pending/active/suspended/exited).

        Read-only aggregate used by the tenant dashboard. Statuses with no
        members are simply absent from the dict; callers sum values for the
        total.
        """
        result = await self._session.execute(
            select(Member.status, func.count()).group_by(Member.status)
        )
        return {row[0]: row[1] for row in result.all()}

    # ── Member Number ─────────────────────────────────────────────────────────

    async def _next_member_number(self) -> str:
        """Fetch next value from the tenant-schema sequence and format it."""
        row = await self._session.execute(text("SELECT nextval('member_number_seq')"))
        n = row.scalar_one()
        return f"M-{n:05d}"

    # ── Registration ──────────────────────────────────────────────────────────

    async def register_member(
        self,
        *,
        full_name: str,
        date_of_birth: date,
        gender: str,
        created_by: uuid.UUID,
        phone: str | None = None,
        email: str | None = None,
        physical_address: str | None = None,
        national_id_number: str | None = None,
        id_document_type: str | None = None,
        id_document_number: str | None = None,
        id_issued_date: date | None = None,
        id_expiry_date: date | None = None,
    ) -> Member:
        """Register a new member in 'pending' status.

        Raises ValueError on duplicate email or national_id_number.
        created_by is stored in the audit log via AuditableMixin context vars.
        """
        if email is not None:
            existing = await self._session.scalar(
                select(Member).where(Member.email == email)
            )
            if existing is not None:
                raise ValueError(f"Member with email '{email}' already exists")

        if national_id_number is not None:
            existing = await self._session.scalar(
                select(Member).where(Member.national_id_number == national_id_number)
            )
            if existing is not None:
                raise ValueError(
                    f"Member with national ID '{national_id_number}' already exists"
                )

        member_number = await self._next_member_number()
        member = Member(
            member_number=member_number,
            full_name=full_name,
            date_of_birth=date_of_birth,
            gender=gender,
            phone=phone,
            email=email,
            physical_address=physical_address,
            national_id_number=national_id_number,
            id_document_type=id_document_type,
            id_document_number=id_document_number,
            id_issued_date=id_issued_date,
            id_expiry_date=id_expiry_date,
        )
        self._session.add(member)
        await self._session.flush()
        _log.info("member.registered", member_number=member_number)
        return member

    # ── Queries ───────────────────────────────────────────────────────────────

    async def list_members(self, *, status: str | None = None) -> list[Member]:
        q = select(Member).order_by(Member.member_number)
        if status is not None:
            q = q.where(Member.status == status)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_member(self, member_id: uuid.UUID) -> Member:
        member = await self._session.get(Member, member_id)
        if member is None:
            raise ValueError(f"Member '{member_id}' not found")
        return member

    # ── Status Change (Maker-Checker) ─────────────────────────────────────────

    async def submit_status_change(
        self,
        *,
        member_id: uuid.UUID,
        new_status: str,
        submitted_by: uuid.UUID,
        reason: str | None = None,
        idempotency_key: str,
    ) -> uuid.UUID:
        """Submit a status change for maker-checker approval.

        Validates the transition is legal before creating the approval request.
        Returns the approval_request.id.
        """
        member = await self.get_member(member_id)

        valid_targets = _VALID_TRANSITIONS.get(member.status, set())
        if new_status not in valid_targets:
            raise ValueError(
                f"Cannot transition member from '{member.status}' to '{new_status}'. "
                f"Valid targets: {sorted(valid_targets) or 'none (terminal state)'}"
            )

        from app.modules.maker_checker.service import ApprovalService

        payload = {
            "member_id": str(member_id),
            "new_status": new_status,
            "changed_by": str(submitted_by),
            "reason": reason,
            "idempotency_key": idempotency_key,
        }

        approval_svc = ApprovalService(self._session)
        request = await approval_svc.submit(
            operation_type="members.change_status",
            payload=payload,
            requested_by=submitted_by,
        )
        _log.info(
            "member.status_change_submitted",
            member_id=str(member_id),
            new_status=new_status,
            approval_id=str(request.id),
        )
        return request.id
