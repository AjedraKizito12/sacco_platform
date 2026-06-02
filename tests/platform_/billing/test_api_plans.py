"""Integration tests for /platform/billing/plans endpoints."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.models import PlatformUser


def _make_platform_session_override(engine: AsyncEngine) -> Any:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


async def _create_superuser(factory: async_sessionmaker[AsyncSession]) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"super-{uuid.uuid4()}@test.example",
            full_name="Super",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup_plans(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.subscription_plans"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


async def test_create_plan(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        r = await client.post(
            "/platform/billing/plans",
            headers={"X-Platform-Actor-ID": str(actor.id)},
            json={
                "code": "starter-test",
                "name": "Starter Test",
                "base_price": "50000.0000",
                "billing_period": "monthly",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["code"] == "starter-test"
        assert Decimal(body["base_price"]) == Decimal("50000.0000")
    finally:
        await _cleanup_plans(factory)


async def test_create_plan_rejects_duplicate_code(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        payload = {
            "code": "dup-test",
            "name": "x",
            "base_price": "1.0000",
            "billing_period": "monthly",
        }
        headers = {"X-Platform-Actor-ID": str(actor.id)}
        first = await client.post("/platform/billing/plans", headers=headers, json=payload)
        assert first.status_code == 201
        r = await client.post("/platform/billing/plans", headers=headers, json=payload)
        assert r.status_code == 409
    finally:
        await _cleanup_plans(factory)


async def test_get_plan(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        headers = {"X-Platform-Actor-ID": str(actor.id)}
        create = await client.post(
            "/platform/billing/plans",
            headers=headers,
            json={
                "code": "get-test",
                "name": "Get Plan",
                "base_price": "1000.0000",
                "billing_period": "monthly",
            },
        )
        plan_id = create.json()["id"]
        r = await client.get(f"/platform/billing/plans/{plan_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["code"] == "get-test"
    finally:
        await _cleanup_plans(factory)


async def test_get_plan_404_for_unknown(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        r = await client.get(
            f"/platform/billing/plans/{uuid.uuid4()}",
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        assert r.status_code == 404
    finally:
        await _cleanup_plans(factory)


async def test_list_plans(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        r = await client.get(
            "/platform/billing/plans",
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)
    finally:
        await _cleanup_plans(factory)


async def test_patch_plan(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        headers = {"X-Platform-Actor-ID": str(actor.id)}
        create = await client.post(
            "/platform/billing/plans",
            headers=headers,
            json={
                "code": "patch-test",
                "name": "Original Name",
                "base_price": "1000.0000",
                "billing_period": "monthly",
            },
        )
        plan_id = create.json()["id"]
        r = await client.patch(
            f"/platform/billing/plans/{plan_id}",
            headers=headers,
            json={"name": "Updated Name"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Updated Name"
    finally:
        await _cleanup_plans(factory)
