import time

import pytest
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.rate_limit.bucket import check_bucket
from app.core.rate_limit.policies import Policy


@pytest.fixture
async def redis():
    r = Redis.from_url(get_settings().redis_url, decode_responses=False)
    yield r


async def test_allows_up_to_capacity_then_blocks(redis):
    key = f"rl:test:{time.time()}"
    pol = Policy("t", 3, 60)  # capacity 3, refill 0.05/s
    now = time.time()
    r1 = await check_bucket(redis, key, pol, now=now)
    r2 = await check_bucket(redis, key, pol, now=now)
    r3 = await check_bucket(redis, key, pol, now=now)
    r4 = await check_bucket(redis, key, pol, now=now)
    assert [r1.allowed, r2.allowed, r3.allowed, r4.allowed] == [True, True, True, False]
    assert r1.remaining == 2 and r4.remaining == 0
    assert r4.reset >= 1  # seconds until one token refills


async def test_refill_over_time(redis):
    key = f"rl:test:{time.time()}:refill"
    pol = Policy("t", 2, 2)  # 1 token/sec
    now = time.time()
    await check_bucket(redis, key, pol, now=now)
    await check_bucket(redis, key, pol, now=now)
    blocked = await check_bucket(redis, key, pol, now=now)
    assert blocked.allowed is False
    allowed_after = await check_bucket(redis, key, pol, now=now + 1.1)
    assert allowed_after.allowed is True


async def test_cost_zero_peek(redis):
    key = f"rl:test:{time.time()}:peek"
    pol = Policy("t", 3, 60)  # capacity 3
    now = time.time()
    # Use up 2 tokens
    await check_bucket(redis, key, pol, now=now)
    await check_bucket(redis, key, pol, now=now)
    # Peek with cost=0 should return remaining=1 but not decrement
    peek = await check_bucket(redis, key, pol, now=now, cost=0)
    assert peek.allowed is True
    assert peek.remaining == 1
    # Next regular request should still see 1 token available
    next_req = await check_bucket(redis, key, pol, now=now)
    assert next_req.allowed is True
    assert next_req.remaining == 0
