"""Unit tests for the lockout module.

Uses FakeRedis — an in-process dict-backed Redis substitute — to test
lockout state transitions without a real Redis server.

FakeRedis implements only the commands used by lockout.py:
  incr, expire, set (with ex=), exists, ttl, delete.
"""
from __future__ import annotations

import time

import pytest

from app.modules.iam.lockout import is_locked, record_attempt, reset


# ── FakeRedis ─────────────────────────────────────────────────────────────────


class FakeRedis:
    """Minimal synchronous-under-the-hood Redis substitute for tests.

    All methods are async (return coroutines) to match redis-py's async API.
    Internal state is a plain dict with optional expiry timestamps.
    """

    def __init__(self) -> None:
        # key → (value: str, expires_at: float | None)
        self._store: dict[str, tuple[str, float | None]] = {}

    def _is_alive(self, key: str) -> bool:
        if key not in self._store:
            return False
        _, exp = self._store[key]
        if exp is not None and time.monotonic() > exp:
            del self._store[key]
            return False
        return True

    async def incr(self, key: str) -> int:
        if not self._is_alive(key):
            self._store[key] = ("0", None)
        val, exp = self._store[key]
        new_val = int(val) + 1
        self._store[key] = (str(new_val), exp)
        return new_val

    async def expire(self, key: str, seconds: int) -> int:
        if not self._is_alive(key):
            return 0
        val, _ = self._store[key]
        self._store[key] = (val, time.monotonic() + seconds)
        return 1

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
    ) -> None:
        exp = time.monotonic() + ex if ex is not None else None
        self._store[key] = (value, exp)

    async def exists(self, key: str) -> int:
        return 1 if self._is_alive(key) else 0

    async def ttl(self, key: str) -> int:
        if not self._is_alive(key):
            return -2
        _, exp = self._store[key]
        if exp is None:
            return -1
        return max(0, int(exp - time.monotonic()))

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                count += 1
        return count


# ── is_locked: no Redis ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_is_locked_returns_false_when_redis_is_none():
    locked, retry_after = await is_locked("user@example.com", redis=None)
    assert locked is False
    assert retry_after == 0


# ── is_locked: fresh state ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_is_locked_returns_false_for_new_email():
    redis = FakeRedis()
    locked, retry_after = await is_locked("new@example.com", redis=redis)
    assert locked is False
    assert retry_after == 0


# ── record_attempt: threshold triggers lockout ────────────────────────────────


@pytest.mark.anyio
async def test_record_attempt_no_lockout_below_threshold():
    redis = FakeRedis()
    email = "user@example.com"
    # threshold=5 by default; 4 attempts should NOT lock
    for _ in range(4):
        await record_attempt(email, redis=redis)
    locked, _ = await is_locked(email, redis=redis)
    assert locked is False


@pytest.mark.anyio
async def test_record_attempt_locks_at_threshold():
    redis = FakeRedis()
    email = "user@example.com"
    # Default threshold is 5
    for _ in range(5):
        await record_attempt(email, redis=redis)
    locked, retry_after = await is_locked(email, redis=redis)
    assert locked is True
    assert retry_after > 0


@pytest.mark.anyio
async def test_record_attempt_is_noop_when_redis_is_none():
    # Must not raise regardless of call count
    for _ in range(10):
        await record_attempt("user@example.com", redis=None)
    locked, _ = await is_locked("user@example.com", redis=None)
    assert locked is False


# ── reset ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_reset_clears_lockout():
    redis = FakeRedis()
    email = "user@example.com"
    for _ in range(5):
        await record_attempt(email, redis=redis)
    locked, _ = await is_locked(email, redis=redis)
    assert locked is True

    await reset(email, redis=redis)

    locked2, _ = await is_locked(email, redis=redis)
    assert locked2 is False


@pytest.mark.anyio
async def test_reset_clears_attempt_counter():
    """After reset, subsequent failures must start a fresh attempt count."""
    redis = FakeRedis()
    email = "user@example.com"
    for _ in range(5):
        await record_attempt(email, redis=redis)
    await reset(email, redis=redis)
    # 4 more attempts — should NOT re-lock (counter reset to 0)
    for _ in range(4):
        await record_attempt(email, redis=redis)
    locked, _ = await is_locked(email, redis=redis)
    assert locked is False


@pytest.mark.anyio
async def test_reset_is_noop_when_redis_is_none():
    await reset("nobody@example.com", redis=None)  # must not raise


# ── retry_after is positive when locked ───────────────────────────────────────


@pytest.mark.anyio
async def test_is_locked_returns_positive_retry_after():
    redis = FakeRedis()
    email = "locked@example.com"
    for _ in range(5):
        await record_attempt(email, redis=redis)
    _, retry_after = await is_locked(email, redis=redis)
    # Lock duration is 30 minutes by default — retry_after should be close to 1800 s
    assert 0 < retry_after <= 1800
