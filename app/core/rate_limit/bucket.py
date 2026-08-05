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


async def peek_remaining_many(
    redis: Redis,
    items: list[tuple[str, Policy]],
    *,
    now: float | None = None,
) -> list[int]:
    """Read-only estimate of each bucket's current tokens, WITHOUT mutating it.

    Unlike ``check_bucket(cost=0)`` — whose Lua unconditionally ``HSET``s and
    ``EXPIRE``s the key, materialising a full bucket for every key touched —
    this only ``HMGET``s ``(tokens, ts)`` and recomputes the refill in Python.
    A missing key means the identity has never been rate-limited under that
    policy, so it reports the full ``policy.limit``. Pipelined into a single
    round-trip so the admin live-view can peek many per-user buckets cheaply.
    """
    now = time.time() if now is None else now
    async with redis.pipeline(transaction=False) as pipe:
        for key, _policy in items:
            pipe.hmget(key, ["tokens", "ts"])
        rows = await pipe.execute()

    out: list[int] = []
    for (_key, policy), row in zip(items, rows, strict=True):
        raw_tokens, raw_ts = row[0], row[1]
        if raw_tokens is None or raw_ts is None:
            out.append(policy.limit)
            continue
        tokens = float(raw_tokens)
        ts = float(raw_ts)
        refill = policy.limit / policy.window_seconds
        elapsed = max(0.0, now - ts)
        out.append(int(min(float(policy.limit), tokens + elapsed * refill)))
    return out
