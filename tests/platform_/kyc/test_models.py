from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.platform_.kyc.models import SaccoKycRequirement


async def test_sacco_requirement_roundtrip(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(SaccoKycRequirement(field_key="tax_id", is_required=False))
        await s.commit()

    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        row = await s.get(SaccoKycRequirement, "tax_id")
        assert row is not None
        assert row.is_required is False

    # cleanup
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.sacco_kyc_requirements"))
        await s.commit()
