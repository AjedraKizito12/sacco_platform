from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from redis.asyncio import Redis

from app.core.rate_limit.policies import Policy

_LUA = (Path(__file__).parent / "redis_bucket.lua").read_text()


@dataclass(frozen=True)
class BucketResult:
    allowed: bool
    remaining: int
    reset: int
    limit: int


async def check_bucket(
    redis: Redis, key: str, policy: Policy, *, now: float | None = None, cost: int = 1
) -> BucketResult:
    now = time.time() if now is None else now
    refill = policy.limit / policy.window_seconds
    ttl = policy.window_seconds * 2
    res = await redis.eval(  # type: ignore[misc]
        _LUA,
        1,
        key,
        str(policy.limit),
        str(refill),
        str(now),
        str(cost),
        str(ttl),
    )
    allowed, remaining, reset, limit = (int(x) for x in res)
    return BucketResult(bool(allowed), remaining, reset, limit)
