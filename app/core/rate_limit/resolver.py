"""Policy resolver: layers per-plan overrides over the code-default policy.

``resolve_policy`` is the entry point the rate-limit middleware calls on
every request. It must never raise into the request path — a cache/DB
hiccup degrades to the code-default :class:`Policy` rather than blocking
traffic.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.core.rate_limit.policies import Policy, match_policy

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.rate_limit.identity import RateLimitIdentity

_OVERRIDES_CACHE_TTL_SECONDS = 300

PolicyOverrides = dict[str, dict[str, int]]


def apply_overrides(base: Policy, overrides: PolicyOverrides) -> Policy:
    """Return a new :class:`Policy` with ``base``'s fields overridden.

    ``overrides`` shape: ``{"<policy_name>": {"limit": int, "window_seconds": int}}``.
    Either key within the inner dict is optional (partial override). If
    ``base.name`` is not a key in ``overrides``, ``base`` is returned
    unchanged. Pure function — no I/O.
    """
    override = overrides.get(base.name)
    if not override:
        return base
    return Policy(
        name=base.name,
        limit=override.get("limit", base.limit),
        window_seconds=override.get("window_seconds", base.window_seconds),
    )


async def _load_plan_overrides(
    slug: str,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> PolicyOverrides:
    """Query the tenant's current plan's ``features.rate_limit_overrides``.

    Path: ``platform.tenants`` (by slug) -> ``current_subscription_id`` ->
    ``platform.subscriptions.plan_id`` -> ``platform.subscription_plans.features``.
    Returns ``{}`` if the tenant has no current subscription, the
    subscription/plan rows are missing, or the feature key is absent.
    """
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT sp.features"
                " FROM platform.tenants t"
                " JOIN platform.subscriptions s ON s.id = t.current_subscription_id"
                " JOIN platform.subscription_plans sp ON sp.id = s.plan_id"
                " WHERE t.slug = :slug"
            ),
            {"slug": slug},
        )
        row = result.fetchone()

    if row is None:
        return {}
    features = row[0] or {}
    overrides = features.get("rate_limit_overrides", {})
    return overrides if isinstance(overrides, dict) else {}


async def _get_tenant_overrides(
    slug: str,
    redis: Redis,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> PolicyOverrides:
    """Return the tenant's plan rate_limit_overrides, Redis-cached (300s).

    Mirrors the cache pattern in ``app/core/db.py:_resolve_tenant_schema``:
    a short-TTL Redis cache in front of a platform DB lookup. Never raises —
    any cache decode failure, Redis outage, or DB error is treated as "no
    overrides" so the caller falls back to the code-default Policy.
    """
    cache_key = f"rl:overrides:{slug}"
    try:
        cached: bytes | None = await redis.get(cache_key)
        if cached is not None:
            payload = json.loads(cached)
            return payload if isinstance(payload, dict) else {}

        overrides = await _load_plan_overrides(slug, session_factory)
        await redis.setex(cache_key, _OVERRIDES_CACHE_TTL_SECONDS, json.dumps(overrides))
        return overrides
    except Exception:
        return {}


async def resolve_policy(
    path: str,
    identity: RateLimitIdentity,
    redis: Redis,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> Policy:
    """Resolve the effective rate-limit :class:`Policy` for *path*/*identity*.

    Starts from the code-default ``match_policy(path, identity.audience)``,
    then layers the tenant's plan-level ``rate_limit_overrides`` (Redis-cached)
    on top for tenant/member audiences with a known ``tenant_slug``. Anonymous
    and platform audiences never carry plan overrides and skip the lookup
    entirely. Never raises into the request path.
    """
    base = match_policy(path, identity.audience)
    if identity.audience in ("anonymous", "platform") or identity.tenant_slug is None:
        return base
    overrides = await _get_tenant_overrides(identity.tenant_slug, redis, session_factory)
    return apply_overrides(base, overrides)
