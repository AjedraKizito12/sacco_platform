"""DB-backed reconcile round-trip (requires a running ES + migrated test DB).

Closes the Increment-1 review gap: the reconcile SQL → mapper → bulk_index →
watermark path was only exercised by the live smoke. Skips cleanly when ES is
unreachable or the test DB lacks the platform tables.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.search.client import get_search_client
from app.core.search.indexes import TENANTS_INDEX, ensure_indices
from app.core.search.reconcile import _reconcile_entity
from app.core.search.registry import SEARCH_ENTITIES
from app.core.search.service import SearchService

TEST_DB = "postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test"
_TENANT_ENTITY = next(e for e in SEARCH_ENTITIES if e.entity_type == "tenant")


async def _es_ready() -> bool:
    es = get_search_client()
    try:
        return bool(await es.ping())
    except Exception:
        return False
    finally:
        await es.close()


async def _db_ready(engine) -> bool:
    try:
        async with engine.connect() as conn:
            got = (
                await conn.execute(
                    text("SELECT to_regclass('platform.search_index_state')")
                )
            ).scalar()
        return got is not None
    except Exception:
        return False


@pytest.mark.asyncio
async def test_reconcile_indexes_a_tenant_and_advances_watermark():
    if not await _es_ready():
        pytest.skip("Elasticsearch unreachable")

    engine = create_async_engine(TEST_DB)
    if not await _db_ready(engine):
        await engine.dispose()
        pytest.skip("test DB missing platform.search_index_state")

    tid = uuid.uuid4()
    suffix = uuid.uuid4().hex[:8]
    factory = async_sessionmaker(engine, expire_on_commit=False)
    es = get_search_client()
    try:
        await ensure_indices(es)
        # Seed a tenant + reset this index's watermark so the backfill picks it up.
        async with factory() as s, s.begin():
            await s.execute(
                text(
                    "INSERT INTO platform.tenants "
                    "(id, slug, schema_name, name, status, is_active, "
                    " subscription_status, created_at, updated_at) "
                    "VALUES (:id, :slug, :schema, :name, 'active', true, "
                    " 'active', now(), now())"
                ),
                {
                    "id": tid,
                    "slug": f"recon-{suffix}",
                    "schema": f"tenant_recon_{suffix}",
                    "name": f"Recon SACCO {suffix}",
                },
            )
            await s.execute(
                text(
                    "DELETE FROM platform.search_index_state "
                    "WHERE index_name = :i AND scope = 'platform'"
                ),
                {"i": TENANTS_INDEX},
            )

        await _reconcile_entity(engine, SearchService(es), _TENANT_ENTITY, "platform")
        await es.indices.refresh(index=TENANTS_INDEX)

        doc = await es.get(index=TENANTS_INDEX, id=str(tid))
        src = doc["_source"]
        assert src["entity_type"] == "tenant"
        assert src["record_id"] == str(tid)
        assert src["status"] == "active"
        assert src["url"] == f"/platform/tenants/{tid}"

        # Watermark row now exists for (index, platform).
        async with factory() as s:
            wm = (
                await s.execute(
                    text(
                        "SELECT last_watermark FROM platform.search_index_state "
                        "WHERE index_name = :i AND scope = 'platform'"
                    ),
                    {"i": TENANTS_INDEX},
                )
            ).scalar()
        assert wm is not None
    finally:
        async with factory() as s, s.begin():
            await s.execute(
                text("DELETE FROM platform.tenants WHERE id = :id"), {"id": tid}
            )
        await es.options(ignore_status=404).delete(index=TENANTS_INDEX, id=str(tid))
        await es.close()
        await engine.dispose()
