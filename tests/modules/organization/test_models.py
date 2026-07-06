from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.modules.organization.models import OrganizationProfile

SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _cleanup(engine: AsyncEngine) -> None:
    async with _factory(engine)() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM organization_profile"))
        await s.commit()


async def test_singleton_second_insert_fails(test_engine: AsyncEngine) -> None:
    try:
        async with _factory(test_engine)() as s:
            await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
            s.add(OrganizationProfile(id=uuid.uuid4(), created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
            await s.commit()
        with pytest.raises(IntegrityError):
            async with _factory(test_engine)() as s:
                await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
                s.add(OrganizationProfile(id=uuid.uuid4(), created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
                await s.commit()
    finally:
        await _cleanup(test_engine)


async def test_defaults(test_engine: AsyncEngine) -> None:
    row_id = uuid.uuid4()
    try:
        async with _factory(test_engine)() as s:
            await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
            s.add(OrganizationProfile(id=row_id, created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
            await s.commit()

        async with _factory(test_engine)() as s:
            await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
            row = await s.get(OrganizationProfile, row_id)
            assert row is not None
            assert row.verified is False
            assert row.legal_name is None
    finally:
        await _cleanup(test_engine)
