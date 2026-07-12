"""Watermark reconcile beat: bulk-index all search entities into Elasticsearch.

ES is the index; Postgres is the source of truth. This beat is the ONLY writer
of ES documents (alongside the delete-sweep). Each (index, scope) advances an
``updated_at`` watermark stored in ``platform.search_index_state``; the first
run (watermark = epoch) backfills. No domain events are consumed and no module
write-path is touched. The entity set is driven by ``registry.SEARCH_ENTITIES``.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
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
from app.core.search.documents import (
    doc_id,
    invoice_document,
    loan_application_document,
    loan_document,
    member_document,
    platform_user_document,
    savings_account_document,
    subscription_document,
    tenant_document,
)
from app.core.search.indexes import ensure_indices
from app.core.search.registry import SEARCH_ENTITIES, SearchEntity
from app.core.search.service import SearchService
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# Mapper dispatch by entity_type. Tenant mappers take (schema, row); platform
# mappers take (row). Keyed off registry entity_type so the reconcile loop stays
# entity-agnostic.
_TENANT_DOC: dict[str, Callable[[str, Any], dict[str, Any]]] = {
    "member": member_document,
    "loan": loan_document,
    "savings_account": savings_account_document,
    "loan_application": loan_application_document,
}
_PLATFORM_DOC: dict[str, Callable[[Any], dict[str, Any]]] = {
    "tenant": tenant_document,
    "platform_user": platform_user_document,
    "invoice": invoice_document,
    "subscription": subscription_document,
}


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
        platform_entities = [e for e in SEARCH_ENTITIES if e.scope_kind == "platform"]
        tenant_entities = [e for e in SEARCH_ENTITIES if e.scope_kind == "tenant"]

        # Per (entity, scope) isolation: one malformed row / bulk error must not
        # abort the whole beat. The watermark is not advanced on failure, so it
        # self-heals next run.
        for entity in platform_entities:
            await _safe_reconcile(engine, svc, entity, "platform")
        for schema in await _tenant_schemas(engine):
            for entity in tenant_entities:
                await _safe_reconcile(engine, svc, entity, schema)
    finally:
        await es.close()
        await engine.dispose()


async def _safe_reconcile(
    engine: AsyncEngine, svc: SearchService, entity: SearchEntity, scope: str
) -> None:
    try:
        await _reconcile_entity(engine, svc, entity, scope)
    except Exception:  # noqa: BLE001
        _log.warning(
            "search.reconcile_scope_failed",
            index=entity.index,
            scope=scope,
            exc_info=True,
        )


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


async def _reconcile_entity(
    engine: AsyncEngine, svc: SearchService, entity: SearchEntity, scope: str
) -> None:
    """Index rows of one entity for one scope, advancing its watermark.

    ``table`` and ``timestamp_col`` come from the trusted registry (not user
    input) — safe to interpolate. Tenant entities read under the scope's
    ``search_path``; platform entities read the ``platform.``-qualified table.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    wm = await _get_watermark(factory, entity.index, scope)
    query = (
        f"SELECT * FROM {entity.table} "  # noqa: S608 — registry-controlled identifier
        f"WHERE {entity.timestamp_col} >= :wm ORDER BY {entity.timestamp_col}"
    )
    async with factory() as session:
        if entity.scope_kind == "tenant":
            await session.execute(
                text(f"SET LOCAL search_path TO {scope}, platform")  # noqa: S608
            )
        rows = list((await session.execute(text(query), {"wm": wm})).all())
    if not rows:
        return

    if entity.scope_kind == "tenant":
        tenant_mapper = _TENANT_DOC[entity.entity_type]
        docs = [(doc_id(scope, r.id), tenant_mapper(scope, r)) for r in rows]
    else:
        platform_mapper = _PLATFORM_DOC[entity.entity_type]
        docs = [(doc_id(None, r.id), platform_mapper(r)) for r in rows]

    await svc.bulk_index(entity.index, docs)
    await _set_watermark(factory, entity.index, scope, next_watermark(rows, wm))
    _log.info("search.reconciled", index=entity.index, scope=scope, count=len(rows))
