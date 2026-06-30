from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session, get_session_for_tenant_schema
from app.main import app, lifespan
from app.modules.organization.models import OrganizationProfile
from app.platform_.models import PlatformUser

SCHEMA = "tenant_test"
TENANT_ID = uuid.uuid4()


def _platform_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    return _override


def _tenant_schema_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override(tenant_id: uuid.UUID) -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    return _override


async def _seed_admin(engine: AsyncEngine) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    admin_id = uuid.uuid4()
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(
            PlatformUser(
                id=admin_id,
                email=f"admin-{admin_id.hex[:6]}@p.test",
                full_name="Admin",
                is_active=True,
                is_superuser=False,
                role="admin",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    return admin_id


async def _seed_full_profile(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
        s.add(
            OrganizationProfile(
                id=uuid.uuid4(),
                legal_name="Umoja SACCO Ltd",
                registration_number="RS-1",
                registered_address="1 Rd",
                primary_contact_name="Jane",
                primary_contact_email="jane@umoja.test",
                registration_date=date(2015, 1, 1),
                regulator_name="UMRA",
                license_number="LIC-9",
                tax_id="TIN-5",
                primary_contact_phone="+256700000000",
                postal_address="PO 1",
                district_region="Central",
                country="Uganda",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    admin_id = await _seed_admin(test_engine)
    app.dependency_overrides[get_platform_session] = _platform_override(test_engine)
    app.dependency_overrides[get_session_for_tenant_schema] = _tenant_schema_override(test_engine)
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Platform-Actor-ID"] = str(admin_id)
        yield c
    app.dependency_overrides.pop(get_platform_session, None)
    app.dependency_overrides.pop(get_session_for_tenant_schema, None)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM organization_profile"))
        await s.execute(text("DELETE FROM platform.sacco_kyc_requirements"))
        await s.execute(
            text("DELETE FROM platform.platform_users WHERE id = :id"), {"id": admin_id}
        )
        await s.commit()


async def test_get_sacco_requirements(client: AsyncClient) -> None:
    resp = await client.get("/platform/kyc/sacco-requirements")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert "legal_name" in {i["key"] for i in items if i["locked"]}


async def test_put_sacco_requirements_toggles_off(client: AsyncClient) -> None:
    resp = await client.put(
        "/platform/kyc/sacco-requirements", json={"required": {"tax_id": False}}
    )
    assert resp.status_code == 200
    tax = next(i for i in resp.json()["items"] if i["key"] == "tax_id")
    assert tax["required"] is False


async def test_verify_incomplete_returns_409(client: AsyncClient) -> None:
    resp = await client.post(f"/platform/tenants/{TENANT_ID}/kyc/verify")
    assert resp.status_code == 409


async def test_verify_after_complete(client: AsyncClient, test_engine: AsyncEngine) -> None:
    await _seed_full_profile(test_engine)
    resp = await client.post(f"/platform/tenants/{TENANT_ID}/kyc/verify")
    assert resp.status_code == 200
    assert resp.json()["verified"] is True
