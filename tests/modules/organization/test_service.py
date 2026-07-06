from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.organization.service import KycIncomplete, OrganizationKycService

SCHEMA = "tenant_test"

# all 13 catalog fields populated → complete (default requirements)
_FULL = {
    "legal_name": "Umoja SACCO Ltd",
    "registration_number": "RS-12345",
    "registered_address": "1 Kampala Rd",
    "primary_contact_name": "Jane Doe",
    "primary_contact_email": "jane@umoja.test",
    "registration_date": date(2015, 1, 1),
    "regulator_name": "UMRA",
    "license_number": "LIC-99",
    "tax_id": "TIN-555",
    "primary_contact_phone": "+256700000000",
    "postal_address": "PO Box 1",
    "district_region": "Central",
    "country": "Uganda",
}


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> AsyncGenerator[async_sessionmaker, None]:
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    yield maker
    async with maker() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM organization_profile"))
        await s.execute(text("DELETE FROM platform.sacco_kyc_requirements"))
        await s.commit()


async def test_get_or_create_is_idempotent(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        a = await OrganizationKycService(s).get_or_create()
        await s.commit()
        a_id = a.id
    async with factory() as s:
        await _set_path(s)
        b = await OrganizationKycService(s).get_or_create()
    assert a_id == b.id


async def test_upsert_incomplete_then_complete(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        _, comp = await OrganizationKycService(s).upsert({"legal_name": "Umoja SACCO Ltd"})
        await s.commit()
    assert comp.is_complete is False
    assert comp.percent < 100

    async with factory() as s:
        await _set_path(s)
        _, comp2 = await OrganizationKycService(s).upsert(_FULL)
        await s.commit()
    assert comp2.is_complete is True
    assert comp2.percent == 100


async def test_verify_requires_complete(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        await OrganizationKycService(s).upsert({"legal_name": "x"})
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        with pytest.raises(KycIncomplete):
            await OrganizationKycService(s).set_verified(
                verified=True, platform_user_id=uuid.uuid4()
            )


async def test_verify_then_value_change_resets_verified(factory: async_sessionmaker) -> None:
    pid = uuid.uuid4()
    async with factory() as s:
        await _set_path(s)
        await OrganizationKycService(s).upsert(_FULL)
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        row = await OrganizationKycService(s).set_verified(verified=True, platform_user_id=pid)
        await s.commit()
        assert row.verified is True
        assert row.verified_by_platform_user_id == pid

    async with factory() as s:
        await _set_path(s)
        row2, _ = await OrganizationKycService(s).upsert({"legal_name": "Umoja SACCO Limited"})
        await s.commit()
        assert row2.verified is False
        assert row2.verified_at is None
        assert row2.verified_by_platform_user_id is None


async def test_upsert_same_values_keeps_verified(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        await OrganizationKycService(s).upsert(_FULL)
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        await OrganizationKycService(s).set_verified(
            verified=True, platform_user_id=uuid.uuid4()
        )
        await s.commit()
    # re-submit identical values → no material change → verified stays
    async with factory() as s:
        await _set_path(s)
        row, _ = await OrganizationKycService(s).upsert({"legal_name": "Umoja SACCO Ltd"})
        await s.commit()
        assert row.verified is True
