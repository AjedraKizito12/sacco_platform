"""GET /platform/admin/dashboard-stats — aggregate endpoint for the portal.

Redis caches the response for 60 seconds to avoid hammering Postgres on
dashboard reloads. When Redis is unavailable, the route falls through
to a fresh computation (degraded but functional).
"""
from __future__ import annotations

import contextlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.platform_.admin.schemas import DashboardStatsOut
from app.platform_.admin.service import DashboardStatsService
from app.platform_.auth import CurrentAdmin

router = APIRouter(prefix="/platform/admin", tags=["platform-admin"])

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]

_CACHE_KEY = "dashboard:platform:stats"
_CACHE_TTL_SECONDS = 60


@router.get("/dashboard-stats", response_model=DashboardStatsOut)
async def get_dashboard_stats(
    request: Request,
    _user: CurrentAdmin,
    session: PlatformSession,
) -> DashboardStatsOut:
    redis = getattr(request.app.state, "redis", None)

    if redis is not None:
        cached = await redis.get(_CACHE_KEY)
        if cached is not None:
            try:
                return DashboardStatsOut.model_validate(json.loads(cached))
            except Exception:  # noqa: BLE001, S110
                # Stale-format cache; ignore and recompute.
                pass

    stats = await DashboardStatsService(session).compute()

    if redis is not None:
        # Cache write failures don't fail the request.
        with contextlib.suppress(Exception):
            await redis.set(
                _CACHE_KEY,
                stats.model_dump_json(),
                ex=_CACHE_TTL_SECONDS,
            )

    return stats
