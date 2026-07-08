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
