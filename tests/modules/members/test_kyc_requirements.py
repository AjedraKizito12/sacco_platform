"""Member KYC requirements: model roundtrip, service, completion helper."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.members.models import Member, MemberKycRequirement

SCHEMA = "tenant_test"


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> AsyncGenerator[async_sessionmaker, None]:
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    yield maker
    async with maker() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM member_kyc_requirements"))
        await s.execute(text("DELETE FROM audit_log WHERE table_name = 'members'"))
        await s.execute(text("DELETE FROM members"))
        await s.commit()


async def test_member_kyc_requirement_roundtrip(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        s.add(MemberKycRequirement(field_key="occupation", is_required=True))
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(MemberKycRequirement).where(
                    MemberKycRequirement.field_key == "occupation"
                )
            )
        ).scalar_one()
    assert row.is_required is True


async def _make_member(s: AsyncSession, **overrides: object) -> Member:
    member = Member(
        member_number=f"M-{uuid.uuid4().hex[:6]}",
        full_name="Jane Member",
        date_of_birth=date(1990, 5, 15),
        gender="female",
        **overrides,
    )
    s.add(member)
    await s.flush()
    return member


async def test_locked_keys_always_required_and_replace_ignores_them(
    factory: async_sessionmaker,
) -> None:
    from app.modules.members.kyc import MemberKycRequirementsService

    async with factory() as s:
        await _set_path(s)
        svc = MemberKycRequirementsService(s)
        # attempt to disable a locked key and an unknown key; toggle a real one off
        await svc.replace({"full_name": False, "nonsense": True, "phone": False})
        await s.commit()

    async with factory() as s:
        await _set_path(s)
        eff = await MemberKycRequirementsService(s).effective_required()
    assert eff["full_name"] is True  # locked — override ignored
    assert "nonsense" not in eff  # unknown — dropped
    assert eff["phone"] is False  # toggleable — respected
    assert eff["occupation"] is False  # catalog default_required=False


async def test_completion_counts_missing_and_absent_increment5_columns(
    factory: async_sessionmaker,
) -> None:
    from app.modules.members.kyc import member_kyc_completion

    async with factory() as s:
        await _set_path(s)
        member = await _make_member(s, phone="+256700000001")
        completion = await member_kyc_completion(s, member)
        await s.commit()

    by_key = {item.key: item for item in completion.items}
    assert by_key["full_name"].present is True  # locked NOT NULL column
    assert by_key["phone"].present is True
    assert by_key["email"].present is False
    # increment-5 columns don't exist on the model yet → absent, not an error
    assert by_key["next_of_kin_name"].present is False
    assert completion.is_complete is False
    assert "next_of_kin_name" in completion.missing_required


async def test_toggling_off_all_missing_makes_member_complete(
    factory: async_sessionmaker,
) -> None:
    from app.modules.members.kyc import (
        MemberKycRequirementsService,
        member_kyc_completion,
    )

    async with factory() as s:
        await _set_path(s)
        member = await _make_member(
            s,
            phone="+256700000002",
            email=f"jane-{uuid.uuid4().hex[:6]}@example.com",
            physical_address="1 Kampala Rd",
            national_id_number=f"CF{uuid.uuid4().hex[:8].upper()}",
            id_document_type="national_id",
            id_document_number="DOC-1",
        )
        # everything still missing is not collectable yet — toggle it off
        await MemberKycRequirementsService(s).replace(
            {"next_of_kin_name": False, "next_of_kin_phone": False}
        )
        completion = await member_kyc_completion(s, member)
        await s.commit()

    assert completion.is_complete is True
    assert completion.percent == 100
