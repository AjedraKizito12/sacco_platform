from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan

TEST_TENANT_SCHEMA = "tenant_test"
ACTOR_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-Slug": "test-tenant", "X-Actor-ID": ACTOR_ID}


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
async def client(test_engine: AsyncEngine):
    override = await _make_tenant_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


async def _create_member(client) -> str:
    """Helper: create a member and return its UUID."""
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
    """Helper: create a GL account and return its UUID."""
    resp = await client.post(
        "/ledger/accounts",
        json={"code": code, "name": name, "account_type": account_type},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_product(client, equity_account_id: str) -> str:
    """Helper: create a share product and return its UUID."""
    resp = await client.post(
        "/shares/products",
        json={
            "name": "Ordinary Shares",
            "par_value": "1000.00",
            "share_capital_account_id": equity_account_id,
            "minimum_shares": 1,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _open_account(client, product_id: str, member_id: str | None = None) -> str:
    """Helper: open a member share account and return its UUID."""
    if member_id is None:
        member_id = await _create_member(client)
    resp = await client.post(
        "/shares/accounts",
        json={"member_id": member_id, "share_product_id": product_id},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_create_product_returns_201(client):
    equity_id = await _create_gl_account(
        client, f"3-{uuid.uuid4().hex[:6]}", "Share Capital", "equity"
    )
    resp = await client.post(
        "/shares/products",
        json={
            "name": "Ordinary Shares",
            "par_value": "1000.00",
            "share_capital_account_id": equity_id,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Ordinary Shares"
    assert data["is_active"] is True
    assert Decimal(data["par_value"]) == Decimal("1000.00")


async def test_open_account_returns_201(client):
    member_id = await _create_member(client)
    equity_id = await _create_gl_account(
        client, f"3-{uuid.uuid4().hex[:6]}", "Share Capital", "equity"
    )
    product_id = await _create_product(client, equity_id)
    resp = await client.post(
        "/shares/accounts",
        json={"member_id": member_id, "share_product_id": product_id},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["share_product_id"] == product_id
    assert data["member_id"] == member_id


async def test_get_account_with_balance_returns_200(client):
    equity_id = await _create_gl_account(
        client, f"3-{uuid.uuid4().hex[:6]}", "Share Capital", "equity"
    )
    product_id = await _create_product(client, equity_id)
    account_id = await _open_account(client, product_id)

    resp = await client.get(f"/shares/accounts/{account_id}", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["shares_held"] == 0
    assert Decimal(data["total_value"]) == Decimal("0")


async def test_purchase_shares_returns_201(client):
    cash_id = await _create_gl_account(
        client, f"1-{uuid.uuid4().hex[:6]}", "Cash", "asset"
    )
    equity_id = await _create_gl_account(
        client, f"3-{uuid.uuid4().hex[:6]}", "Share Capital", "equity"
    )
    product_id = await _create_product(client, equity_id)
    account_id = await _open_account(client, product_id)

    resp = await client.post(
        f"/shares/accounts/{account_id}/purchase",
        json={
            "quantity": 5,
            "payment_account_id": cash_id,
            "idempotency_key": f"buy-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["transaction_type"] == "purchase"
    assert data["quantity"] == 5
    assert Decimal(data["amount"]) == Decimal("5000.00")


async def test_purchase_shares_updates_balance(client):
    cash_id = await _create_gl_account(
        client, f"1-{uuid.uuid4().hex[:6]}", "Cash", "asset"
    )
    equity_id = await _create_gl_account(
        client, f"3-{uuid.uuid4().hex[:6]}", "Share Capital", "equity"
    )
    product_id = await _create_product(client, equity_id)
    account_id = await _open_account(client, product_id)

    await client.post(
        f"/shares/accounts/{account_id}/purchase",
        json={
            "quantity": 7,
            "payment_account_id": cash_id,
            "idempotency_key": f"buy-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )

    resp = await client.get(f"/shares/accounts/{account_id}", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["shares_held"] == 7


async def test_list_transactions_returns_200(client):
    cash_id = await _create_gl_account(
        client, f"1-{uuid.uuid4().hex[:6]}", "Cash", "asset"
    )
    equity_id = await _create_gl_account(
        client, f"3-{uuid.uuid4().hex[:6]}", "Share Capital", "equity"
    )
    product_id = await _create_product(client, equity_id)
    account_id = await _open_account(client, product_id)

    await client.post(
        f"/shares/accounts/{account_id}/purchase",
        json={
            "quantity": 3,
            "payment_account_id": cash_id,
            "idempotency_key": f"buy-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )

    resp = await client.get(
        f"/shares/accounts/{account_id}/transactions", headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    txns = resp.json()
    assert len(txns) == 1
    assert txns[0]["transaction_type"] == "purchase"


async def test_submit_redemption_returns_202(client):
    cash_id = await _create_gl_account(
        client, f"1-{uuid.uuid4().hex[:6]}", "Cash", "asset"
    )
    equity_id = await _create_gl_account(
        client, f"3-{uuid.uuid4().hex[:6]}", "Share Capital", "equity"
    )
    product_id = await _create_product(client, equity_id)
    account_id = await _open_account(client, product_id)

    # Buy shares first
    await client.post(
        f"/shares/accounts/{account_id}/purchase",
        json={
            "quantity": 10,
            "payment_account_id": cash_id,
            "idempotency_key": f"buy-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )

    # Submit redemption
    resp = await client.post(
        f"/shares/accounts/{account_id}/redeem",
        json={
            "quantity": 4,
            "payment_account_id": cash_id,
            "reason": "Member exit",
            "idempotency_key": f"redeem-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert "approval_request_id" in data
    assert data["status"] == "pending"


async def test_get_account_not_found_returns_404(client):
    resp = await client.get(f"/shares/accounts/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404, resp.text
