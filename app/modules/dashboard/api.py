"""GET /dashboard/stats — tenant aggregate for the operator portal.

Mirrors the platform dashboard-stats endpoint: Redis caches the response for
60 seconds (per tenant) to avoid hammering Postgres on dashboard reloads.
When Redis is unavailable, the route falls through to a fresh computation
(degraded but functional). Tenant-scoped, so subscription-gated via
get_tenant_session like every other tenant route.
"""
from __future__ import annotations

import contextlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_tenant_session
from app.modules.dashboard.schemas import TenantDashboardStatsOut
from app.modules.dashboard.service import TenantDashboardStatsService
from app.modules.iam.dependencies import CurrentTenantUser

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

Session = Annotated[AsyncSession, Depends(get_tenant_session)]

_CACHE_TTL_SECONDS = 60


def _cache_key(slug: str) -> str:
    return f"dashboard:tenant:{slug}:stats"


@router.get("/stats", response_model=TenantDashboardStatsOut)
async def get_dashboard_stats(
    request: Request,
    _user: CurrentTenantUser,
    session: Session,
) -> TenantDashboardStatsOut:
    settings = get_settings()
    slug = request.headers.get(settings.tenant_header) or ""
    redis = getattr(request.app.state, "redis", None)
    key = _cache_key(slug)

    if redis is not None:
        cached = await redis.get(key)
        if cached is not None:
            try:
                return TenantDashboardStatsOut.model_validate(json.loads(cached))
            except Exception:  # noqa: BLE001, S110
                # Stale-format cache; ignore and recompute.
                pass

    stats = await TenantDashboardStatsService(session).compute()

    if redis is not None:
        # Cache write failures don't fail the request.
        with contextlib.suppress(Exception):
            await redis.set(key, stats.model_dump_json(), ex=_CACHE_TTL_SECONDS)

    return stats
