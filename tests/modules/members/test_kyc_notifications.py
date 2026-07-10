"""KYC decision notices to members (notifications increment 2)."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.notifications.models import TenantNotificationEvent
from app.core.notifications.seed_templates import seed_default_templates
from app.modules.members.kyc_submissions import KycReviewService, MemberSelfService
from app.modules.members.models import Member

SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture(autouse=True)
async def _clean(test_engine: AsyncEngine):  # noqa: ANN201
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        await seed_default_templates(s)
        await s.commit()
    yield
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text(f"DELETE FROM {SCHEMA}.notification_events"))  # noqa: S608
        await s.execute(text("DELETE FROM kyc_submissions"))
        await s.execute(
            text(
                "DELETE FROM audit_log WHERE table_name IN "
                "('members', 'kyc_submissions')"
            )
        )
        await s.execute(text("DELETE FROM members WHERE email LIKE 'kycn-%'"))
        await s.commit()


async def _member_with_submission(s: AsyncSession) -> tuple[Member, uuid.UUID]:
    member = Member(
        member_number=f"M-{uuid.uuid4().hex[:8]}",
        full_name="KYC Member",
        date_of_birth=date(1990, 1, 1),
        gender="female",
        status="active",
        email=f"kycn-{uuid.uuid4().hex[:6]}@m.test",
    )
    s.add(member)
    await s.flush()
    submission = await MemberSelfService(s).submit_kyc(
        member.id, {"phone": "+256700000001"}
    )
    return member, submission.id


async def test_approve_publishes_notice(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        member, submission_id = await _member_with_submission(s)
        await KycReviewService(s).approve(submission_id, reviewer_id=uuid.uuid4())
        await s.commit()
        member_id, member_email = member.id, member.email
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.dedupe_key == f"kyc_approved:{submission_id}"
                )
            )
        ).scalars().one()
    assert row.event_code == "kyc_submission_approved"
    assert row.recipient_kind == "member"
    assert row.recipient_user_id == member_id
    assert row.recipient_email == member_email


async def test_reject_publishes_notice_with_reason(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        member, submission_id = await _member_with_submission(s)
        await KycReviewService(s).reject(
            submission_id, reviewer_id=uuid.uuid4(), reason="ID number unreadable"
        )
        await s.commit()
        member_id = member.id
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.dedupe_key == f"kyc_rejected:{submission_id}"
                )
            )
        ).scalars().one()
    assert row.event_code == "kyc_submission_rejected"
    assert row.recipient_user_id == member_id
    assert row.context["reason"] == "ID number unreadable"
