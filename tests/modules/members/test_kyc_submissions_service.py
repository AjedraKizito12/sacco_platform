"""Member KYC submissions: model constraints + MemberSelfService + KycReviewService."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.members.models import KycSubmission, Member

SCHEMA = "tenant_test"


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> AsyncGenerator[async_sessionmaker, None]:
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    yield maker
    async with maker() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM kyc_submissions"))
        await s.execute(text("DELETE FROM member_kyc_requirements"))
        await s.execute(text("DELETE FROM audit_log WHERE table_name IN ('members', 'kyc_submissions')"))
        await s.execute(text("DELETE FROM members"))
        await s.commit()


def _member(**overrides: object) -> Member:
    defaults: dict[str, object] = {
        "member_number": f"M-{uuid.uuid4().hex[:5]}",
        "full_name": "Jane Doe",
        "date_of_birth": date(1990, 5, 15),
        "gender": "female",
    }
    defaults.update(overrides)
    return Member(**defaults)


async def test_member_has_next_of_kin_and_occupation_columns(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member(next_of_kin_name="John Doe", next_of_kin_phone="+256700000001", occupation="Teacher")
        s.add(m)
        await s.commit()
        member_id = m.id
    async with factory() as s:
        await _set_path(s)
        row = (await s.execute(select(Member).where(Member.id == member_id))).scalar_one()
    assert row.next_of_kin_name == "John Doe"
    assert row.occupation == "Teacher"


async def test_at_most_one_pending_submission_per_member(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member()
        s.add(m)
        await s.flush()
        s.add(KycSubmission(member_id=m.id, phone="+256700000001"))
        await s.flush()
        s.add(KycSubmission(member_id=m.id, phone="+256700000002"))
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()


# ── Services ──────────────────────────────────────────────────────────────────

from app.modules.members.kyc_submissions import (  # noqa: E402
    EDITABLE_KYC_FIELDS,
    KycFieldConflict,
    KycReviewService,
    MemberSelfService,
    SubmissionNotPending,
)


def test_editable_fields_are_the_non_locked_catalog_keys() -> None:
    assert EDITABLE_KYC_FIELDS == (
        "phone",
        "email",
        "physical_address",
        "national_id_number",
        "id_document_type",
        "id_document_number",
        "id_issued_date",
        "id_expiry_date",
        "next_of_kin_name",
        "next_of_kin_phone",
        "occupation",
    )


async def test_submit_creates_pending_then_supersedes_in_place(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member()
        s.add(m)
        await s.flush()
        svc = MemberSelfService(s)
        first = await svc.submit_kyc(m.id, {"phone": "+256700000001", "occupation": "Farmer"})
        first_id = first.id
        assert first.status == "pending"
        assert first.occupation == "Farmer"
        second = await svc.submit_kyc(m.id, {"phone": "+256700000002"})
        await s.commit()
    assert second.id == first_id  # superseded in place, not a new row
    assert second.phone == "+256700000002"
    assert second.occupation is None  # full snapshot replace: omitted key clears


async def test_latest_submission_orders_by_submitted_at(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member()
        s.add(m)
        await s.flush()
        self_svc = MemberSelfService(s)
        review_svc = KycReviewService(s)
        first = await self_svc.submit_kyc(m.id, {"phone": "+256700000001"})
        await review_svc.reject(first.id, reviewer_id=uuid.uuid4(), reason="Blurry data")
        second = await self_svc.submit_kyc(m.id, {"phone": "+256700000002"})
        latest = await self_svc.latest_submission(m.id)
        await s.commit()
    assert latest is not None
    assert latest.id == second.id
    assert latest.status == "pending"


async def test_approve_applies_full_snapshot_to_member(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member(phone="+256700000000", occupation=None)
        s.add(m)
        await s.flush()
        sub = await MemberSelfService(s).submit_kyc(
            m.id,
            {
                "phone": "+256700000009",
                "national_id_number": "CM123456",
                "next_of_kin_name": "John Doe",
                "id_issued_date": date(2020, 1, 1),
            },
        )
        reviewer = uuid.uuid4()
        approved = await KycReviewService(s).approve(sub.id, reviewer_id=reviewer)
        await s.commit()
        member_id = m.id
    assert approved.status == "approved"
    assert approved.reviewed_by == reviewer
    assert approved.reviewed_at is not None
    async with factory() as s:
        await _set_path(s)
        row = (await s.execute(select(Member).where(Member.id == member_id))).scalar_one()
    assert row.phone == "+256700000009"
    assert row.national_id_number == "CM123456"
    assert row.next_of_kin_name == "John Doe"
    assert row.id_issued_date == date(2020, 1, 1)
    assert row.email is None  # full replace: proposed None clears


async def test_approve_conflicting_national_id_raises(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        other = _member(national_id_number="CM999999")
        m = _member()
        s.add_all([other, m])
        await s.flush()
        sub = await MemberSelfService(s).submit_kyc(m.id, {"national_id_number": "CM999999"})
        with pytest.raises(KycFieldConflict):
            await KycReviewService(s).approve(sub.id, reviewer_id=uuid.uuid4())
        await s.rollback()


async def test_reject_then_re_review_raises_not_pending(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member()
        s.add(m)
        await s.flush()
        sub = await MemberSelfService(s).submit_kyc(m.id, {"phone": "+256700000001"})
        rejected = await KycReviewService(s).reject(
            sub.id, reviewer_id=uuid.uuid4(), reason="Incomplete"
        )
        assert rejected.status == "rejected"
        assert rejected.rejection_reason == "Incomplete"
        with pytest.raises(SubmissionNotPending):
            await KycReviewService(s).approve(sub.id, reviewer_id=uuid.uuid4())
        await s.rollback()


async def test_list_filters_by_status_and_joins_member(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member(full_name="Queue Member")
        s.add(m)
        await s.flush()
        await MemberSelfService(s).submit_kyc(m.id, {"phone": "+256700000001"})
        rows = await KycReviewService(s).list(status="pending")
        empty = await KycReviewService(s).list(status="approved")
        await s.commit()
    assert len(rows) == 1
    submission, member = rows[0]
    assert submission.status == "pending"
    assert member.full_name == "Queue Member"
    assert empty == []
