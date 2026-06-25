"""HTTP tests: member self-service savings read endpoints (stub auth).

Accounts are created via the operator endpoints; the member is then activated +
portal-enabled via a direct DB write (HTTP activation needs maker-checker).
"""
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
    """Delete the rows these tests create so other modules' tests stay isolated."""
    yield
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        for tbl in (
            "savings_transactions",
            "savings_accounts",
            "savings_products",
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


async def _create_account(client, member_id: str) -> str:  # noqa: ANN001
    liability = await client.post(
        "/ledger/accounts",
        json={"code": f"2-{uuid.uuid4().hex[:6]}", "name": "Member Savings", "account_type": "liability"},
        headers=HEADERS,
    )
    assert liability.status_code == 201, liability.text
    product = await client.post(
        "/savings/products",
        json={
            "name": "Regular Savings",
            "interest_rate": "5.00",
            "liability_account_id": liability.json()["id"],
            "minimum_balance": "0.00",
        },
        headers=HEADERS,
    )
    assert product.status_code == 201, product.text
    account = await client.post(
        "/savings/accounts",
        json={"member_id": member_id, "savings_product_id": product.json()["id"]},
        headers=HEADERS,
    )
    assert account.status_code == 201, account.text
    return account.json()["id"]


async def test_member_savings_lists_only_own(client, test_engine: AsyncEngine) -> None:  # noqa: ANN001
    member_id = await _create_member(client)
    account_id = await _create_account(client, member_id)
    await _activate(test_engine, member_id)

    resp = await client.get("/member/savings", headers=_member_headers(member_id))
    assert resp.status_code == 200, resp.text
    ids = [a["id"] for a in resp.json()]
    assert account_id in ids


async def test_member_cannot_read_other_members_account_txns(
    client, test_engine: AsyncEngine
) -> None:  # noqa: ANN001
    member_id = await _create_member(client)
    await _activate(test_engine, member_id)

    other_id = await _create_member(client)
    other_account_id = await _create_account(client, other_id)

    resp = await client.get(
        f"/member/savings/{other_account_id}/transactions",
        headers=_member_headers(member_id),
    )
    assert resp.status_code == 404, resp.text
