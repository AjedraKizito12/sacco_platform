"""Maker-checker executors for member lifecycle operations."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.maker_checker.registry import approval_executor


@approval_executor("members.change_status")
async def execute_change_status(
    session: AsyncSession, payload: dict
) -> dict:
    """Executor: called by ApprovalService.approve() when quorum is met.

    payload keys (all strings — JSON round-tripped through JSONB):
        member_id: str (UUID)
        new_status: str
        changed_by: str (UUID)
        reason: str | None
        idempotency_key: str
    """
    from app.core.outbox.publisher import EventPublisher
    from app.modules.members.service import MemberService

    member_id = uuid.UUID(payload["member_id"])
    new_status = payload["new_status"]

    svc = MemberService(session)
    member = await svc.get_member(member_id)

    old_status = member.status
    member.status = new_status

    if new_status == "active" and member.joined_at is None:
        member.joined_at = date.today()

    await session.flush()

    # Publish domain event so fee engine and other consumers can react.
    if new_status == "active":
        await EventPublisher.publish(
            session,
            aggregate_type="member",
            aggregate_id=member_id,
            event_type="MemberActivated",
            payload={
                "member_id": str(member_id),
                "member_number": member.member_number,
                "activated_at": member.joined_at.isoformat() if member.joined_at else None,
            },
        )

    return {
        "member_id": str(member_id),
        "old_status": old_status,
        "new_status": new_status,
    }
