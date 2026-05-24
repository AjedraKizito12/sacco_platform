from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan

TEST_TENANT_SCHEMA = "tenant_test"
ACTOR_ID = str(uuid.uuid4())


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


HEADERS = {"X-Tenant-Slug": "test-tenant", "X-Actor-ID": ACTOR_ID}


async def test_create_account_returns_201(client):
    resp = await client.post(
        "/ledger/accounts",
        json={
            "code": f"API-{uuid.uuid4().hex[:6]}",
            "name": "Test Cash",
            "account_type": "asset",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["account_type"] == "asset"
    assert data["is_active"] is True


async def test_create_account_duplicate_code_returns_409(client):
    code = f"DUP-{uuid.uuid4().hex[:6]}"
    await client.post(
        "/ledger/accounts",
        json={"code": code, "name": "First", "account_type": "asset"},
        headers=HEADERS,
    )
    resp = await client.post(
        "/ledger/accounts",
        json={"code": code, "name": "Second", "account_type": "asset"},
        headers=HEADERS,
    )
    assert resp.status_code == 409, resp.text


async def test_list_accounts_returns_200(client):
    await client.post(
        "/ledger/accounts",
        json={"code": f"LST-{uuid.uuid4().hex[:6]}", "name": "Listed", "account_type": "income"},
        headers=HEADERS,
    )
    resp = await client.get("/ledger/accounts", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


async def test_get_account_with_balance_returns_200(client):
    code = f"BAL-{uuid.uuid4().hex[:6]}"
    created = (
        await client.post(
            "/ledger/accounts",
            json={"code": code, "name": "Balance Account", "account_type": "asset"},
            headers=HEADERS,
        )
    ).json()
    account_id = created["id"]

    resp = await client.get(f"/ledger/accounts/{account_id}", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "balance" in data


async def test_submit_manual_entry_returns_202(client):
    code_a = f"A-{uuid.uuid4().hex[:6]}"
    code_b = f"B-{uuid.uuid4().hex[:6]}"
    acc_a = (
        await client.post(
            "/ledger/accounts",
            json={"code": code_a, "name": "Asset A", "account_type": "asset"},
            headers=HEADERS,
        )
    ).json()
    acc_b = (
        await client.post(
            "/ledger/accounts",
            json={"code": code_b, "name": "Liability B", "account_type": "liability"},
            headers=HEADERS,
        )
    ).json()

    resp = await client.post(
        "/ledger/journal-entries/submit",
        json={
            "reference": "API-MANUAL-001",
            "description": "Test manual GL",
            "idempotency_key": f"api-manual-{uuid.uuid4().hex}",
            "lines": [
                {"account_id": acc_a["id"], "debit_amount": "500.00", "credit_amount": "0"},
                {"account_id": acc_b["id"], "debit_amount": "0", "credit_amount": "500.00"},
            ],
        },
        headers=HEADERS,
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert "approval_request_id" in data
    assert data["status"] == "pending"


async def test_list_journal_entries_returns_200(client):
    resp = await client.get("/ledger/journal-entries", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)
