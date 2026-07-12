"""Watermark reconcile beat: bulk-index tenants + members into Elasticsearch.

ES is the index; Postgres is the source of truth. This beat is the ONLY writer
of ES documents. Each (index, scope) advances an ``updated_at`` watermark stored
in ``platform.search_index_state``; the first run (watermark = epoch) backfills.
No domain events are consumed and no module write-path is touched.
"""
from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.search.client import get_search_client
from app.core.search.documents import doc_id, member_document, tenant_document
from app.core.search.indexes import MEMBERS_INDEX, TENANTS_INDEX, ensure_indices
from app.core.search.service import SearchService
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def next_watermark(rows: list[Any], current: datetime) -> datetime:
    """Highest ``updated_at`` among the rows, or ``current`` when none."""
    if not rows:
        return current
    return cast("datetime", max(row.updated_at for row in rows))


@celery_app.task(name="app.core.search.reconcile.reconcile_search_indexes")  # type: ignore[misc]
def reconcile_search_indexes() -> None:
    asyncio.run(_run(get_settings().database_url))


async def _run(database_url: str) -> None:
    engine = create_async_engine(database_url)
    es = get_search_client()
    try:
        await ensure_indices(es)
        svc = SearchService(es)
        # Isolate each pass: one malformed row / bulk error must not abort the
        # whole beat (the watermark is not advanced on failure, so it self-heals
        # next run). Mirrors the per-schema isolation on the members loop.
        try:
            await _reconcile_tenants(engine, svc)
        except Exception:  # noqa: BLE001
            _log.warning("search.reconcile_scope_failed", scope="platform", exc_info=True)
        for schema in await _tenant_schemas(engine):
            try:
                await _reconcile_members(engine, svc, schema)
            except Exception:  # noqa: BLE001
                _log.warning("search.reconcile_scope_failed", scope=schema, exc_info=True)
    finally:
        await es.close()
        await engine.dispose()


async def _tenant_schemas(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
        )
        return [r[0] for r in result.fetchall() if _SCHEMA_RE.match(r[0])]


async def _get_watermark(
    factory: async_sessionmaker[Any], index_name: str, scope: str
) -> datetime:
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT last_watermark FROM platform.search_index_state "
                    "WHERE index_name = :i AND scope = :s"
                ),
                {"i": index_name, "s": scope},
            )
        ).first()
    return row[0] if row else _EPOCH


async def _set_watermark(
    factory: async_sessionmaker[Any], index_name: str, scope: str, wm: datetime
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO platform.search_index_state "
                "(index_name, scope, last_watermark, last_run_at) "
                "VALUES (:i, :s, :wm, now()) "
                "ON CONFLICT (index_name, scope) DO UPDATE "
                "SET last_watermark = :wm, last_run_at = now()"
            ),
            {"i": index_name, "s": scope, "wm": wm},
        )


async def _reconcile_tenants(engine: AsyncEngine, svc: SearchService) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    wm = await _get_watermark(factory, TENANTS_INDEX, "platform")
    async with factory() as session:
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT id, name, slug, schema_name, updated_at "
                        "FROM platform.tenants WHERE updated_at >= :wm "
                        "ORDER BY updated_at"
                    ),
                    {"wm": wm},
                )
            ).all()
        )
    if not rows:
        return
    docs = [(doc_id(None, r.id), tenant_document(r)) for r in rows]
    await svc.bulk_index(TENANTS_INDEX, docs)
    await _set_watermark(factory, TENANTS_INDEX, "platform", next_watermark(rows, wm))
    _log.info("search.reconciled", index=TENANTS_INDEX, scope="platform", count=len(rows))


async def _reconcile_members(
    engine: AsyncEngine, svc: SearchService, schema: str
) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    wm = await _get_watermark(factory, MEMBERS_INDEX, schema)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT id, full_name, member_number, email, phone, updated_at "
                        "FROM members WHERE updated_at >= :wm ORDER BY updated_at"
                    ),
                    {"wm": wm},
                )
            ).all()
        )
    if not rows:
        return
    docs = [(doc_id(schema, r.id), member_document(schema, r)) for r in rows]
    await svc.bulk_index(MEMBERS_INDEX, docs)
    await _set_watermark(factory, MEMBERS_INDEX, schema, next_watermark(rows, wm))
    _log.info("search.reconciled", index=MEMBERS_INDEX, scope=schema, count=len(rows))
