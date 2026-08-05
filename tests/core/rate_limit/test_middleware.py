"""Integration tests for RateLimitMiddleware.

Uses httpx.ASGITransport + `async with lifespan(app)` (see tests/test_main.py)
so requests travel through the real Starlette middleware stack, including
request_id_middleware and RateLimitMiddleware. Requires real Redis +
Postgres test infra (same as the rest of the suite).

These tests also exercise the deferred paths from earlier tasks:
- derive_identity's verified-JWT branch (a real tenant-audience token,
  signed with a real signing key fetched via KeyService).
- resolve_policy's code-default path (no plan override wired up here).
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import get_settings
from app.main import app, lifespan
from app.modules.iam.keys.service import KeyService
from app.modules.iam.tokens.service import encode_access_token
from tests.conftest import TEST_TENANT_SLUG


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """RATE_LIMIT_ENABLED monkeypatching requires a fresh Settings() build."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class _RedisCtx:
    """Opens/closes a Redis client within the test's own event-loop lifetime.

    A function-scoped async fixture's teardown runs *after* the test body
    (and the `async with lifespan(app)` block inside it) has already exited,
    which — under this repo's session-scoped asyncio fixture loop — raced
    with loop teardown. Scoping the client's lifetime to the test body itself
    (via `async with`) sidesteps that ordering issue while still guaranteeing
    `aclose()` runs.
    """

    async def __aenter__(self) -> Redis:
        self._r = Redis.from_url(get_settings().redis_url, decode_responses=False)
        return self._r

    async def __aexit__(self, *exc: object) -> None:
        await self._r.aclose()


async def _get_or_create_tenant_signing_key(
    test_engine: AsyncEngine,
) -> tuple[str, bytes, str]:
    """Return (kid, private_key_pem, algorithm) for the 'tenant' audience.

    Reuses an existing active key if one is already present (other test
    files may have created one in this session-scoped engine); otherwise
    creates one. Mirrors the pattern in tests/modules/iam/keys/test_key_service.py.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text("SET search_path TO platform"))
        svc = KeyService(s)
        try:
            return await svc.get_active_signing_key("tenant")
        except RuntimeError:
            pass

    async with factory() as s:
        await s.execute(text("SET search_path TO platform"))
        svc = KeyService(s)
        await svc.generate_and_insert(audience="tenant")
        await s.commit()

    async with factory() as s:
        await s.execute(text("SET search_path TO platform"))
        svc = KeyService(s)
        return await svc.get_active_signing_key("tenant")


# ── 1. Anonymous 429 ──────────────────────────────────────────────────────────


async def test_anonymous_login_blocks_after_limit(test_engine):
    ip = "203.0.113.7"

    async with _RedisCtx() as redis:
        await redis.delete(f"rl:auth_login:ip:{ip}")

    async with lifespan(app), await _client() as c:
        responses = []
        for _ in range(12):
            r = await c.post(
                "/auth/token",
                json={"email": "x@y.z", "password": "bad"},
                headers={
                    "X-Forwarded-For": ip,
                    "X-Tenant-Slug": TEST_TENANT_SLUG,
                },
            )
            responses.append(r)

    statuses = [r.status_code for r in responses]
    assert 429 in statuses

    blocked = next(r for r in responses if r.status_code == 429)
    body = blocked.json()
    assert body["detail"] == "Rate limit exceeded"
    assert isinstance(body["retry_after"], int)
    assert "Retry-After" in blocked.headers
    assert "X-RateLimit-Limit" in blocked.headers
    assert "X-RateLimit-Remaining" in blocked.headers
    assert "X-RateLimit-Reset" in blocked.headers
    assert blocked.headers["X-RateLimit-Remaining"] == "0"


# ── 2. Authenticated identity — derive_identity verify-path ─────────────────


async def test_authenticated_request_is_keyed_by_verified_user(test_engine):
    kid, private_pem, algorithm = await _get_or_create_tenant_signing_key(test_engine)
    sub = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    token = encode_access_token(
        sub=sub,
        audience=f"tenant:{TEST_TENANT_SLUG}",
        session_id=session_id,
        actor_type="tenant_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm=algorithm,
        ttl_seconds=900,
    )
    bucket_key = f"rl:authenticated_default:u:tenant:{sub}"

    async with lifespan(app), await _client() as c:
        r = await c.get(
            "/healthz",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Forwarded-For": "198.51.100.1",
            },
        )

    assert r.status_code == 200
    assert "X-RateLimit-Limit" in r.headers
    assert r.headers["X-RateLimit-Limit"] == "300"  # authenticated_default
    # The bucket was created under the verified-user key, not an IP key —
    # proves derive_identity's verify-path (not IP) drove the rate limit.
    async with _RedisCtx() as redis:
        assert await redis.exists(bucket_key) == 1


# ── 3. 200 carries X-RateLimit-* ─────────────────────────────────────────────


async def test_normal_get_carries_rate_limit_headers():
    async with lifespan(app), await _client() as c:
        r = await c.get("/healthz")

    assert r.status_code == 200
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers
    assert "X-RateLimit-Reset" in r.headers


# ── 4. Fail-open ──────────────────────────────────────────────────────────────


async def test_fail_open_on_redis_error(monkeypatch):
    import app.core.rate_limit.middleware as mw

    async def boom(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(mw, "check_bucket", boom)

    async with lifespan(app), await _client() as c:
        r = await c.get("/healthz")

    assert r.status_code == 200
    # Failure path never attaches rate-limit headers (call_next is invoked
    # directly, no result to hang headers off of).
    assert "X-RateLimit-Limit" not in r.headers


# ── 5. Kill switch ────────────────────────────────────────────────────────────


async def test_kill_switch_disables_rate_limiting(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()

    async with lifespan(app), await _client() as c:
        r = await c.get("/healthz")

    assert r.status_code == 200
    assert "X-RateLimit-Limit" not in r.headers


# ── 6. request_id survives a 429 (proves middleware ordering) ───────────────


async def test_request_id_echoed_on_429(test_engine):
    ip = "203.0.113.99"

    async with _RedisCtx() as redis:
        await redis.delete(f"rl:auth_login:ip:{ip}")

    async with lifespan(app), await _client() as c:
        blocked = None
        for _ in range(12):
            r = await c.post(
                "/auth/token",
                json={"email": "x@y.z", "password": "bad"},
                headers={
                    "X-Forwarded-For": ip,
                    "X-Tenant-Slug": TEST_TENANT_SLUG,
                    "X-Request-ID": "rl-test-trace-id",
                },
            )
            if r.status_code == 429:
                blocked = r
                break

    assert blocked is not None
    assert blocked.headers.get("x-request-id") == "rl-test-trace-id"
