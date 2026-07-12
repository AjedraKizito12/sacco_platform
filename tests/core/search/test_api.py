"""Integration tests for the search endpoints (require a running ES).

Skips cleanly when Elasticsearch is unreachable so the unit suites stay green
offline. Proves the operator-search schema-isolation guarantee end to end.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import get_tenant_session
from app.core.search.client import get_search_client
from app.core.search.indexes import (
    MEMBERS_INDEX,
    TENANTS_INDEX,
    ensure_indices,
)
from app.core.search.service import SearchService
from app.main import app
from app.modules.iam.dependencies import get_current_tenant_user
from app.platform_.auth import get_current_platform_user

TEST_DB = "postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test"

ALPHA = "tenant_alpha"
BETA = "tenant_beta"
_alpha_member = str(uuid.uuid4())
_beta_member = str(uuid.uuid4())
_tenant_id = str(uuid.uuid4())


async def _es_ready() -> bool:
    es = get_search_client()
    try:
        return bool(await es.ping())
    except Exception:
        return False
    finally:
        await es.close()


@pytest.fixture(scope="module", autouse=True)
def _seed_es():
    if not asyncio.run(_es_ready()):
        pytest.skip("Elasticsearch unreachable")

    async def seed() -> None:
        es = get_search_client()
        try:
            await ensure_indices(es)
            svc = SearchService(es)
            await svc.bulk_index(MEMBERS_INDEX, [
                (f"{ALPHA}:{_alpha_member}", {
                    "entity_type": "member", "record_id": _alpha_member,
                    "tenant_schema": ALPHA, "title": "Grace Alpha",
                    "subtitle": "M-A1", "url": f"/members/{_alpha_member}",
                    "full_name": "Grace Alpha", "member_number": "M-A1",
                }),
                (f"{BETA}:{_beta_member}", {
                    "entity_type": "member", "record_id": _beta_member,
                    "tenant_schema": BETA, "title": "Grace Beta",
                    "subtitle": "M-B1", "url": f"/members/{_beta_member}",
                    "full_name": "Grace Beta", "member_number": "M-B1",
                }),
            ])
            await svc.bulk_index(TENANTS_INDEX, [
                (_tenant_id, {
                    "entity_type": "tenant", "record_id": _tenant_id,
                    "title": "Grace SACCO", "subtitle": "grace-sacco",
                    "url": f"/platform/tenants/{_tenant_id}",
                    "name": "Grace SACCO", "slug": "grace-sacco",
                }),
            ])
            await es.indices.refresh(index=f"{MEMBERS_INDEX},{TENANTS_INDEX}")
        finally:
            await es.close()

    asyncio.run(seed())
    yield

    async def cleanup() -> None:
        es = get_search_client()
        try:
            safe = es.options(ignore_status=404)
            await safe.delete(index=MEMBERS_INDEX, id=f"{ALPHA}:{_alpha_member}")
            await safe.delete(index=MEMBERS_INDEX, id=f"{BETA}:{_beta_member}")
            await safe.delete(index=TENANTS_INDEX, id=_tenant_id)
        finally:
            await es.close()

    asyncio.run(cleanup())


def _tenant_session_override(schema: str):
    engine = create_async_engine(TEST_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {schema}, platform")
            )
            yield session

    return _override


def _make_client(schema: str) -> AsyncClient:
    app.dependency_overrides[get_current_tenant_user] = lambda: object()
    app.dependency_overrides[get_tenant_session] = _tenant_session_override(schema)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_operator_search_is_schema_isolated():
    try:
        client = _make_client(ALPHA)
        r = await client.get("/search", params={"q": "grace"})
        assert r.status_code == 200
        ids = [h["id"] for h in r.json()["hits"]]
        assert _alpha_member in ids
        assert _beta_member not in ids  # the isolation guarantee
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_operator_blank_query_is_empty():
    try:
        client = _make_client(ALPHA)
        r = await client.get("/search", params={"q": "  "})
        assert r.status_code == 200
        assert r.json()["hits"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_platform_search_returns_tenant():
    try:
        # Override the base platform-auth dep with a superuser — passes every
        # role-rank check (support/admin/…) since the role factory depends on it.
        app.dependency_overrides[get_current_platform_user] = lambda: SimpleNamespace(
            id=uuid.uuid4(), role="superuser", is_superuser=True
        )
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
        r = await client.get("/platform/search", params={"q": "grace"})
        assert r.status_code == 200
        ids = [h["id"] for h in r.json()["hits"]]
        assert _tenant_id in ids
    finally:
        app.dependency_overrides.clear()
