"""Member KYC requirements: model roundtrip, service, completion helper."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.members.models import MemberKycRequirement

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
