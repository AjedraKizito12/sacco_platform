from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.platform_.kyc.service import SaccoKycRequirementsService


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> AsyncGenerator[async_sessionmaker, None]:
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    yield maker
    async with maker() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.sacco_kyc_requirements"))
        await s.commit()


async def test_effective_required_defaults_when_no_overrides(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        eff = await SaccoKycRequirementsService(s).effective_required()
    # locked + all toggleable default to required
    assert eff["legal_name"] is True
    assert eff["tax_id"] is True


async def test_override_turns_off_toggleable(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        svc = SaccoKycRequirementsService(s)
        await svc.replace({"tax_id": False, "country": False})
        await s.commit()
        eff = await svc.effective_required()
    assert eff["tax_id"] is False
    assert eff["country"] is False
    assert eff["regulator_name"] is True  # untouched → default


async def test_replace_ignores_locked_keys(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        svc = SaccoKycRequirementsService(s)
        await svc.replace({"legal_name": False, "tax_id": False})
        await s.commit()
        eff = await svc.effective_required()
    assert eff["legal_name"] is True  # locked, override ignored
    assert eff["tax_id"] is False


async def test_replace_is_idempotent_replacement(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        svc = SaccoKycRequirementsService(s)
        await svc.replace({"tax_id": False})
        await s.commit()
        await svc.replace({"country": False})  # tax_id no longer overridden
        await s.commit()
        eff = await svc.effective_required()
    assert eff["tax_id"] is True
    assert eff["country"] is False
