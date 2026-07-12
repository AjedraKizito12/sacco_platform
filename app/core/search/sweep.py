"""Delete-sweep beat: remove ES docs whose source row has genuinely vanished.

The incremental reconcile only ADDS/UPDATES docs (watermark on ``updated_at``);
it never notices a hard-deleted row. This daily sweep, per (index, scope), diffs
the ES doc-id set against the current source-row id set and deletes the orphans.
Hard-deletes are rare in this system (financial data is append-only; members are
never hard-deleted), so a daily cadence is ample.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog
from elasticsearch.helpers import async_scan
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.search.client import get_search_client
from app.core.search.documents import doc_id
from app.core.search.registry import SEARCH_ENTITIES, SearchEntity
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


def orphan_ids(es_ids: set[str], source_ids: set[str]) -> set[str]:
    """ES doc ids with no matching source row."""
    return es_ids - source_ids


@celery_app.task(name="app.core.search.sweep.sweep_deleted_search_docs")  # type: ignore[misc]
def sweep_deleted_search_docs() -> None:
    asyncio.run(_run(get_settings().database_url))


async def _run(database_url: str) -> None:
    engine = create_async_engine(database_url)
    es = get_search_client()
    try:
        platform_entities = [e for e in SEARCH_ENTITIES if e.scope_kind == "platform"]
        tenant_entities = [e for e in SEARCH_ENTITIES if e.scope_kind == "tenant"]
        for entity in platform_entities:
            await _safe_sweep(engine, es, entity, "platform")
        for schema in await _tenant_schemas(engine):
            for entity in tenant_entities:
                await _safe_sweep(engine, es, entity, schema)
    finally:
        await es.close()
        await engine.dispose()


async def _safe_sweep(
    engine: AsyncEngine, es: Any, entity: SearchEntity, scope: str
) -> None:
    try:
        await _sweep_entity(engine, es, entity, scope)
    except Exception:  # noqa: BLE001
        _log.warning(
            "search.sweep_scope_failed", index=entity.index, scope=scope, exc_info=True
        )


async def _tenant_schemas(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
        )
        return [r[0] for r in result.fetchall() if _SCHEMA_RE.match(r[0])]


async def _es_ids(es: Any, entity: SearchEntity, scope: str) -> set[str]:
    query: dict[str, Any] = {"match_all": {}}
    if entity.scope_kind == "tenant":
        query = {"bool": {"filter": [{"term": {"tenant_schema": scope}}]}}
    ids: set[str] = set()
    async for hit in async_scan(
        es, index=entity.index, query={"query": query}, _source=False
    ):
        ids.add(hit["_id"])
    return ids


async def _source_ids(
    engine: AsyncEngine, entity: SearchEntity, scope: str
) -> set[str]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        if entity.scope_kind == "tenant":
            await session.execute(
                text(f"SET LOCAL search_path TO {scope}, platform")  # noqa: S608
            )
            rows = (
                await session.execute(
                    text(f"SELECT id FROM {entity.table}")  # noqa: S608 — registry table
                )
            ).all()
            return {doc_id(scope, r.id) for r in rows}
        rows = (
            await session.execute(
                text(f"SELECT id FROM {entity.table}")  # noqa: S608 — registry table
            )
        ).all()
        return {doc_id(None, r.id) for r in rows}


async def _sweep_entity(
    engine: AsyncEngine, es: Any, entity: SearchEntity, scope: str
) -> None:
    es_ids = await _es_ids(es, entity, scope)
    if not es_ids:
        return
    source_ids = await _source_ids(engine, entity, scope)
    orphans = orphan_ids(es_ids, source_ids)
    if not orphans:
        return
    safe = es.options(ignore_status=404)
    for oid in orphans:
        await safe.delete(index=entity.index, id=oid)
    _log.info(
        "search.swept", index=entity.index, scope=scope, deleted=len(orphans)
    )
