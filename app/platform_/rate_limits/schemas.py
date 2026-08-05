"""Response schemas for the read-only /platform/rate-limits* endpoints."""
from __future__ import annotations

import uuid

from pydantic import BaseModel


class PolicyOut(BaseModel):
    name: str
    limit: int
    window_seconds: int


class RateLimitConfigOut(BaseModel):
    """The code-default policy table plus per-plan overrides across all plans.

    ``plan_overrides`` is keyed by plan ``code``; each value is that plan's
    ``features.rate_limit_overrides`` map (``{policy_name: {limit?, window_seconds?}}``).
    """

    defaults: list[PolicyOut]
    plan_overrides: dict[str, dict[str, dict[str, int]]]


class TenantBucketOut(BaseModel):
    policy: str
    remaining: int
    limit: int


class TenantLiveOut(BaseModel):
    """Per-policy worst-case (minimum) remaining tokens across a tenant's users.

    Buckets are keyed per authenticated user, not per tenant, so ``remaining``
    is the minimum across all of the tenant's active users (and members) for
    each effective policy — the user closest to being throttled.
    """

    tenant_id: uuid.UUID
    buckets: list[TenantBucketOut]
