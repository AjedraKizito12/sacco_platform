"""Redis-backed login lockout for platform and tenant auth.

Three functions — record_attempt, is_locked, reset — are called from
PlatformAuthService.login() and TenantAuthService.login() after this plan.

Redis key namespaces:
    iam:lockout:attempts:{email}  — INCR counter with sliding TTL
    iam:lockout:locked:{email}    — existence flag with fixed TTL

When redis is None (test environments or degraded state) all three
functions are no-ops. This means lockout is disabled rather than broken
— a deliberate tradeoff for service availability.

Configuration (from settings):
    auth_lockout_threshold       — failed attempts before lockout (default 5)
    auth_lockout_window_minutes  — sliding window for attempt counting (default 15)
    auth_lockout_duration_minutes — lock duration after threshold (default 30)
"""
from __future__ import annotations

from typing import Any

from app.core.config import get_settings

_ATTEMPTS_PREFIX = "iam:lockout:attempts:"
_LOCKED_PREFIX = "iam:lockout:locked:"


async def record_attempt(email: str, redis: Any | None) -> None:
    """Record a failed login attempt for the given email.

    Increments the attempt counter. On the first increment within a window,
    sets the key TTL to ``auth_lockout_window_minutes``. When the counter
    reaches ``auth_lockout_threshold``, creates a lockout key that expires
    after ``auth_lockout_duration_minutes``.

    Safe to call for emails that do not exist in the database — this is by
    design to prevent timing-based user enumeration.

    No-op when redis is None.
    """
    if redis is None:
        return

    settings = get_settings()
    attempts_key = f"{_ATTEMPTS_PREFIX}{email}"

    count: int = await redis.incr(attempts_key)
    if count == 1:
        # First attempt in this window — start the expiry clock.
        await redis.expire(attempts_key, settings.auth_lockout_window_minutes * 60)
    if count >= settings.auth_lockout_threshold:
        locked_key = f"{_LOCKED_PREFIX}{email}"
        await redis.set(locked_key, "1", ex=settings.auth_lockout_duration_minutes * 60)


async def is_locked(email: str, redis: Any | None) -> tuple[bool, int]:
    """Check whether the given email is currently locked out.

    Returns:
        (is_locked, retry_after_seconds)
        ``retry_after_seconds`` is the number of seconds until the lockout
        expires (from the Redis TTL of the locked key). Returns ``(False, 0)``
        when not locked or when redis is None.
    """
    if redis is None:
        return False, 0

    locked_key = f"{_LOCKED_PREFIX}{email}"
    exists: int = await redis.exists(locked_key)
    if not exists:
        return False, 0

    ttl: int = await redis.ttl(locked_key)
    return True, max(ttl, 0)


async def reset(email: str, redis: Any | None) -> None:
    """Clear the failed-attempt counter and any lockout for the given email.

    Called after a successful login. Deleting both keys lets the next failure
    window start fresh rather than compounding previous failures.

    No-op when redis is None.
    """
    if redis is None:
        return

    await redis.delete(
        f"{_ATTEMPTS_PREFIX}{email}",
        f"{_LOCKED_PREFIX}{email}",
    )
