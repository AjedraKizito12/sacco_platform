"""Search query endpoints.

Operator search is schema-isolated SERVER-SIDE: the caller's tenant schema is
read off the tenant session's ``search_path`` (set by ``get_tenant_session``)
and passed to the query as a mandatory ``term`` filter — the client never
supplies a schema, so cross-tenant results are impossible.
"""
from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.core.search.client import get_search_client
from app.core.search.indexes import MEMBERS_INDEX, TENANTS_INDEX
from app.core.search.schemas import SearchHitOut, SearchResultsOut
from app.core.search.service import SearchHit, SearchService
from app.modules.iam.dependencies import CurrentTenantUser
from app.platform_.auth import CurrentSupport

platform_search_router = APIRouter(prefix="/platform/search", tags=["search"])
tenant_search_router = APIRouter(prefix="/search", tags=["search"])

TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]


def _results(hits: list[SearchHit], started: float) -> SearchResultsOut:
    return SearchResultsOut(
        hits=[
            SearchHitOut(
                entity_type=h.entity_type,
                id=h.id,
                title=h.title,
                subtitle=h.subtitle,
                url=h.url,
            )
            for h in hits
        ],
        took_ms=int((time.perf_counter() - started) * 1000),
    )


async def _caller_schema(session: AsyncSession) -> str:
    """The tenant schema from the session's search_path (server-derived)."""
    raw = (await session.execute(text("SHOW search_path"))).scalar()
    return str(raw).split(",")[0].strip().strip('"')


@platform_search_router.get("", response_model=SearchResultsOut)
async def platform_search(
    _user: CurrentSupport,
    q: str = Query(""),
    limit: int = Query(20, ge=1, le=50),
) -> SearchResultsOut:
    started = time.perf_counter()
    es = get_search_client()
    try:
        hits = await SearchService(es).search([TENANTS_INDEX], q, limit=limit)
    finally:
        await es.close()
    return _results(hits, started)


@tenant_search_router.get("", response_model=SearchResultsOut)
async def tenant_search(
    session: TenantSession,
    _user: CurrentTenantUser,
    q: str = Query(""),
    limit: int = Query(20, ge=1, le=50),
) -> SearchResultsOut:
    started = time.perf_counter()
    schema = await _caller_schema(session)
    es = get_search_client()
    try:
        hits = await SearchService(es).search(
            [MEMBERS_INDEX], q, tenant_schema=schema, limit=limit
        )
    finally:
        await es.close()
    return _results(hits, started)
