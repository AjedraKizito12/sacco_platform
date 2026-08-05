"""Read-only /platform/rate-limits* endpoints (admin-gated).

Observability of the limiter for operators: the effective policy table + any
per-plan overrides, and a per-tenant live view of how close each of a tenant's
users is to being throttled. Nothing here mutates a bucket — the live view uses
the read-only ``peek_remaining_many`` HMGET path, never ``check_bucket``.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.core.rate_limit.bucket import peek_remaining_many
from app.core.rate_limit.policies import (
    Policy,
    list_authenticated_policies,
    list_default_policies,
)
from app.core.rate_limit.resolver import apply_overrides
from app.platform_.auth import CurrentAdmin
from app.platform_.rate_limits.schemas import (
    PolicyOut,
    RateLimitConfigOut,
    TenantBucketOut,
    TenantLiveOut,
)

router = APIRouter(prefix="/platform/rate-limits", tags=["platform-rate-limits"])

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]


@router.get("", response_model=RateLimitConfigOut)
async def get_rate_limit_config(
    session: PlatformSession, _user: CurrentAdmin
) -> RateLimitConfigOut:
    defaults = [
        PolicyOut(name=p.name, limit=p.limit, window_seconds=p.window_seconds)
        for p in list_default_policies()
    ]
    rows = (
        await session.execute(
            text("SELECT code, features FROM platform.subscription_plans")
        )
    ).all()
    plan_overrides: dict[str, dict[str, dict[str, int]]] = {}
    for code, features in rows:
        overrides = (features or {}).get("rate_limit_overrides")
        if isinstance(overrides, dict) and overrides:
            plan_overrides[code] = overrides
    return RateLimitConfigOut(defaults=defaults, plan_overrides=plan_overrides)


@router.get("/tenants/{tenant_id}/live", response_model=TenantLiveOut)
async def get_tenant_live(
    tenant_id: uuid.UUID,
    request: Request,
    session: PlatformSession,
    _user: CurrentAdmin,
) -> TenantLiveOut:
    tenant = (
        await session.execute(
            text(
                "SELECT schema_name, current_subscription_id"
                " FROM platform.tenants WHERE id = :id"
            ),
            {"id": tenant_id},
        )
    ).fetchone()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    schema_name = tenant[0]

    # Resolve the tenant's plan overrides (platform tables) BEFORE switching
    # search_path to the tenant schema for the per-user enumeration below.
    overrides = await _load_tenant_overrides(session, tenant_id)
    policies = [apply_overrides(p, overrides) for p in list_authenticated_policies()]

    # Every active operator/member of the tenant is a distinct bucket identity.
    # Switch to the tenant schema (search_path) and query unqualified — the
    # multi-tenancy idiom — rather than interpolating schema_name into FROM.
    # Shadow impersonation users are excluded (they never self-authenticate).
    # SET does not accept bind parameters; schema_name is DB-sourced (immutable,
    # validated at provisioning), never caller input.
    await session.execute(text(f'SET LOCAL search_path TO "{schema_name}", platform'))
    tenant_user_ids = (
        await session.execute(
            text(
                "SELECT id FROM tenant_users"
                " WHERE impersonation_id IS NULL AND is_active = true"
            )
        )
    ).scalars().all()
    member_ids = (
        await session.execute(
            text("SELECT id FROM members WHERE status = 'active'")
        )
    ).scalars().all()

    redis = request.app.state.redis
    buckets: list[TenantBucketOut] = []
    for policy in policies:
        keys: list[tuple[str, Policy]] = [
            (f"rl:{policy.name}:u:tenant:{uid}", policy) for uid in tenant_user_ids
        ] + [
            (f"rl:{policy.name}:u:member:{mid}", policy) for mid in member_ids
        ]
        remaining = min(await peek_remaining_many(redis, keys)) if keys else policy.limit
        buckets.append(
            TenantBucketOut(policy=policy.name, remaining=remaining, limit=policy.limit)
        )
    return TenantLiveOut(tenant_id=tenant_id, buckets=buckets)


async def _load_tenant_overrides(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, dict[str, int]]:
    """This tenant's plan ``rate_limit_overrides`` (``{}`` if no plan/feature)."""
    row = (
        await session.execute(
            text(
                "SELECT sp.features"
                " FROM platform.tenants t"
                " JOIN platform.subscriptions s ON s.id = t.current_subscription_id"
                " JOIN platform.subscription_plans sp ON sp.id = s.plan_id"
                " WHERE t.id = :id"
            ),
            {"id": tenant_id},
        )
    ).fetchone()
    if row is None:
        return {}
    overrides = (row[0] or {}).get("rate_limit_overrides")
    return overrides if isinstance(overrides, dict) else {}
