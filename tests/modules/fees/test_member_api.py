"""HTTP test: member self-service fees read endpoint (stub auth)."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from app.core.db import get_tenant_session
from app.main import app, lifespan

TEST_TENANT_SCHEMA = "tenant_test"
HEADERS = {"X-Tenant-Slug": "test-tenant"}


async def _make_tenant_session_override(engine: AsyncEngine):  # noqa: ANN202
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


@pytest.fixture
async def client(test_engine: AsyncEngine, tenant_actor_id: uuid.UUID):  # noqa: ANN201
    override = await _make_tenant_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = "test-tenant"
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


@pytest.fixture(autouse=True)
async def _clean_tables(test_engine: AsyncEngine):  # noqa: ANN201
    yield
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        for tbl in (
            "fee_collections",
            "fee_assessments",
            "fee_types",
            "journal_lines",
            "journal_entries",
            "chart_of_accounts",
            "members",
        ):
            await session.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        await session.commit()


def _member_headers(member_id: str) -> dict[str, str]:
    return {**HEADERS, "X-Member-Actor-ID": member_id}


async def _create_member(client) -> str:  # noqa: ANN001
    resp = await client.post(
        "/members",
        json={
            "full_name": f"Member {uuid.uuid4().hex[:6]}",
            "date_of_birth": "1990-05-15",
            "gender": "female",
            "email": f"m-{uuid.uuid4().hex[:6]}@example.com",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _activate(engine: AsyncEngine, member_id: str) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(
            text("UPDATE members SET status='active', portal_enabled=true WHERE id = :mid"),
            {"mid": member_id},
        )
        await session.commit()


async def _assess_member_fee(client, member_id: str) -> str:  # noqa: ANN001
    for code, name, acct_type in [
        ("1101", "Fee Receivable", "asset"),
        ("4001", "Fee Income", "income"),
    ]:
        await client.post(
            "/ledger/accounts",
            json={"code": code, "name": name, "account_type": acct_type},
            headers=HEADERS,
        )
    fee_type = await client.post(
        "/fees/types",
        json={
            "code": f"FEE_{uuid.uuid4().hex[:5]}",
            "name": "Membership Fee",
            "applicable_to": "member",
            "amount_kind": "fixed",
            "amount": "10000.00",
            "currency": "UGX",
            "trigger_kind": "manual",
            "gl_income_account_code": "4001",
            "gl_receivable_account_code": "1101",
            "requires_collection": False,
        },
        headers=HEADERS,
    )
    assert fee_type.status_code == 201, fee_type.text
    assessment = await client.post(
        "/fees/assessments",
        json={
            "fee_type_id": fee_type.json()["id"],
            "target_type": "member",
            "target_id": member_id,
            "period_start": "2026-01-01",
        },
        headers=HEADERS,
    )
    assert assessment.status_code == 201, assessment.text
    return assessment.json()["id"]


async def test_member_fees_lists_only_own(client, test_engine: AsyncEngine) -> None:  # noqa: ANN001
    member_id = await _create_member(client)
    assessment_id = await _assess_member_fee(client, member_id)
    await _activate(test_engine, member_id)

    resp = await client.get("/member/fees", headers=_member_headers(member_id))
    assert resp.status_code == 200, resp.text
    ids = [f["id"] for f in resp.json()]
    assert assessment_id in ids
