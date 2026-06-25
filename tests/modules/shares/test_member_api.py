"""HTTP tests: member self-service shares read endpoint (stub auth)."""
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
            "share_transactions",
            "member_share_accounts",
            "share_products",
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


async def _open_share_account(client, member_id: str) -> str:  # noqa: ANN001
    equity = await client.post(
        "/ledger/accounts",
        json={"code": f"3-{uuid.uuid4().hex[:6]}", "name": "Share Capital", "account_type": "equity"},
        headers=HEADERS,
    )
    assert equity.status_code == 201, equity.text
    product = await client.post(
        "/shares/products",
        json={
            "name": "Ordinary Shares",
            "par_value": "10.00",
            "share_capital_account_id": equity.json()["id"],
            "minimum_shares": 1,
        },
        headers=HEADERS,
    )
    assert product.status_code == 201, product.text
    account = await client.post(
        "/shares/accounts",
        json={"member_id": member_id, "share_product_id": product.json()["id"]},
        headers=HEADERS,
    )
    assert account.status_code == 201, account.text
    return account.json()["id"]


async def test_member_shares_lists_only_own(client, test_engine: AsyncEngine) -> None:  # noqa: ANN001
    member_id = await _create_member(client)
    account_id = await _open_share_account(client, member_id)
    await _activate(test_engine, member_id)

    resp = await client.get("/member/shares", headers=_member_headers(member_id))
    assert resp.status_code == 200, resp.text
    ids = [a["id"] for a in resp.json()]
    assert account_id in ids
