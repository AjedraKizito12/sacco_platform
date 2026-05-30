"""API integration tests for the fees module."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from app.core.db import get_tenant_session
from app.main import app, lifespan
from app.modules.fees.models import FeeAssessment, FeeCollection, FeeType
from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.members.models import Member
from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction

TEST_TENANT_SCHEMA = "tenant_test"
HEADERS = {"X-Tenant-Slug": "test-tenant"}


async def _make_session_override(engine: AsyncEngine):
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
    override = await _make_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = "test-tenant"
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


async def _cleanup(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await s.execute(delete(FeeCollection))
        await s.execute(delete(FeeAssessment))
        await s.execute(delete(FeeType))
        await s.execute(delete(JournalLine))
        await s.execute(delete(JournalEntry))
        await s.execute(delete(ChartOfAccount))
        await s.execute(delete(Member))
        await s.commit()


async def _create_gl_accounts(client) -> None:
    for code, name, acct_type in [
        ("1101", "Fee Receivable", "asset"),
        ("4001", "Fee Income", "income"),
    ]:
        await client.post(
            "/ledger/accounts",
            json={"code": code, "name": name, "account_type": acct_type},
            headers=HEADERS,
        )


async def test_create_fee_type(client, test_engine):
    await _create_gl_accounts(client)
    resp = await client.post(
        "/fees/types",
        json={
            "code": "TEST_FEE",
            "name": "Test Fee",
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
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["code"] == "TEST_FEE"
    assert data["is_active"] is True
    await _cleanup(test_engine)


async def test_list_fee_types(client, test_engine):
    await _create_gl_accounts(client)
    await client.post(
        "/fees/types",
        json={
            "code": "LIST_FEE",
            "name": "List Fee",
            "applicable_to": "member",
            "amount_kind": "fixed",
            "amount": "5000.00",
            "currency": "UGX",
            "trigger_kind": "manual",
            "gl_income_account_code": "4001",
            "gl_receivable_account_code": "1101",
            "requires_collection": False,
        },
        headers=HEADERS,
    )
    resp = await client.get("/fees/types", headers=HEADERS)
    assert resp.status_code == 200
    codes = [ft["code"] for ft in resp.json()]
    assert "LIST_FEE" in codes
    await _cleanup(test_engine)


async def test_list_assessments_empty(client, test_engine):
    resp = await client.get("/fees/assessments", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == []
    await _cleanup(test_engine)
