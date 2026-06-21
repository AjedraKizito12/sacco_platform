# tests/modules/savings/test_api.py
from __future__ import annotations

import uuid
from decimal import Decimal
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


async def _make_tenant_session_override(engine: AsyncEngine):
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
async def client(test_engine: AsyncEngine, tenant_actor_id: uuid.UUID):
    override = await _make_tenant_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = "test-tenant"
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


async def _create_member(client) -> str:
    resp = await client.post(
        "/members",
        json={
            "full_name": f"Member {uuid.uuid4().hex[:6]}",
            "date_of_birth": "1990-05-15",
            "gender": "female",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_gl_account(client, code: str, name: str, account_type: str) -> str:
    resp = await client.post(
        "/ledger/accounts",
        json={"code": code, "name": name, "account_type": account_type},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_product(client, liability_account_id: str) -> str:
    resp = await client.post(
        "/savings/products",
        json={
            "name": "Regular Savings",
            "interest_rate": "5.00",
            "liability_account_id": liability_account_id,
            "minimum_balance": "500.00",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _open_account(
    client, product_id: str, member_id: str | None = None
) -> str:
    if member_id is None:
        member_id = await _create_member(client)
    resp = await client.post(
        "/savings/accounts",
        json={"member_id": member_id, "savings_product_id": product_id},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_create_product_returns_201(client):
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    resp = await client.post(
        "/savings/products",
        json={
            "name": "Regular Savings",
            "interest_rate": "5.00",
            "liability_account_id": liability_id,
            "minimum_balance": "500.00",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Regular Savings"
    assert Decimal(data["interest_rate"]) == Decimal("5.00")
    assert data["is_active"] is True


async def test_list_products_returns_200(client):
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    await _create_product(client, liability_id)

    resp = await client.get("/savings/products", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


async def test_get_product_returns_200(client):
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    product_id = await _create_product(client, liability_id)

    resp = await client.get(f"/savings/products/{product_id}", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == product_id


async def test_open_account_returns_201_with_snapshots(client):
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    product_id = await _create_product(client, liability_id)
    member_id = await _create_member(client)

    resp = await client.post(
        "/savings/accounts",
        json={"member_id": member_id, "savings_product_id": product_id},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["savings_product_id"] == product_id
    assert data["member_id"] == member_id
    assert data["product_name"] == "Regular Savings"
    assert Decimal(data["minimum_balance"]) == Decimal("500.00")


async def test_open_account_duplicate_returns_409(client):
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    product_id = await _create_product(client, liability_id)
    member_id = await _create_member(client)

    await _open_account(client, product_id, member_id)
    resp = await client.post(
        "/savings/accounts",
        json={"member_id": member_id, "savings_product_id": product_id},
        headers=HEADERS,
    )
    assert resp.status_code == 409, resp.text


async def test_get_account_with_balance_returns_200(client):
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    product_id = await _create_product(client, liability_id)
    account_id = await _open_account(client, product_id)

    resp = await client.get(f"/savings/accounts/{account_id}", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert Decimal(data["balance"]) == Decimal("0")


async def test_deposit_returns_201(client):
    cash_id = await _create_gl_account(
        client, f"1-{uuid.uuid4().hex[:6]}", "Cash", "asset"
    )
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    product_id = await _create_product(client, liability_id)
    account_id = await _open_account(client, product_id)

    resp = await client.post(
        f"/savings/accounts/{account_id}/deposit",
        json={
            "amount": "1000.00",
            "payment_account_id": cash_id,
            "idempotency_key": f"dep-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["transaction_type"] == "deposit"
    assert Decimal(data["amount"]) == Decimal("1000.00")


async def test_deposit_updates_balance(client):
    cash_id = await _create_gl_account(
        client, f"1-{uuid.uuid4().hex[:6]}", "Cash", "asset"
    )
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    product_id = await _create_product(client, liability_id)
    account_id = await _open_account(client, product_id)

    await client.post(
        f"/savings/accounts/{account_id}/deposit",
        json={
            "amount": "3000.00",
            "payment_account_id": cash_id,
            "idempotency_key": f"dep-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )

    resp = await client.get(f"/savings/accounts/{account_id}", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["balance"]) == Decimal("3000.00")


async def test_list_transactions_returns_200(client):
    cash_id = await _create_gl_account(
        client, f"1-{uuid.uuid4().hex[:6]}", "Cash", "asset"
    )
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    product_id = await _create_product(client, liability_id)
    account_id = await _open_account(client, product_id)

    await client.post(
        f"/savings/accounts/{account_id}/deposit",
        json={
            "amount": "2000.00",
            "payment_account_id": cash_id,
            "idempotency_key": f"dep-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )

    resp = await client.get(
        f"/savings/accounts/{account_id}/transactions", headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    txns = resp.json()
    assert len(txns) == 1
    assert txns[0]["transaction_type"] == "deposit"


async def test_submit_withdrawal_returns_202(client):
    cash_id = await _create_gl_account(
        client, f"1-{uuid.uuid4().hex[:6]}", "Cash", "asset"
    )
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    product_id = await _create_product(client, liability_id)
    account_id = await _open_account(client, product_id)

    # Deposit enough to allow withdrawal above minimum_balance
    await client.post(
        f"/savings/accounts/{account_id}/deposit",
        json={
            "amount": "2000.00",
            "payment_account_id": cash_id,
            "idempotency_key": f"dep-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )

    resp = await client.post(
        f"/savings/accounts/{account_id}/withdraw",
        json={
            "amount": "1000.00",
            "payment_account_id": cash_id,
            "idempotency_key": f"wdraw-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert "approval_request_id" in data
    assert data["status"] == "pending"


async def test_list_accounts_returns_200_and_filters(client):
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    product_id = await _create_product(client, liability_id)
    member_a = await _create_member(client)
    member_b = await _create_member(client)
    await _open_account(client, product_id, member_a)
    await _open_account(client, product_id, member_b)

    resp = await client.get("/savings/accounts", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 2

    resp_a = await client.get(
        "/savings/accounts", params={"member_id": member_a}, headers=HEADERS
    )
    assert resp_a.status_code == 200, resp_a.text
    data = resp_a.json()
    assert len(data) == 1
    assert data[0]["member_id"] == member_a
