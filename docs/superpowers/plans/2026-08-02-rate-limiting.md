# Phase 6 — Rate Limiting & Abuse Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Redis token-bucket rate limiting, enforced by one HTTP middleware with verify-only JWT identity (or trusted-proxy client IP), with code-default policies + per-plan overrides, 429/`X-RateLimit-*` headers, fail-open, Phase-5 block metrics, a read-only platform endpoint, and an admin-portal settings page.

**Architecture:** A cross-cutting `app/core/rate_limit/` library — pure policy table + resolver, an atomic Redis Lua token bucket, a verify-only identity deriver, and a `RateLimitMiddleware` that composes them and short-circuits 429 before routing/auth deps run. Fail-open on Redis errors. Two read-only `/platform/rate-limits*` endpoints feed a read-only portal page.

**Tech Stack:** Python 3.11+, FastAPI/Starlette middleware, `redis.asyncio` + Lua (`EVAL`), PyJWT (RS256), SQLAlchemy 2.0 async, pytest; Next.js 15 portal (TanStack `<DataTable>`).

**Spec:** `docs/superpowers/specs/2026-08-02-rate-limiting-design.md`

## Global Constraints

- **Enforcement is a single HTTP middleware** (`app/core/rate_limit/middleware.py`) wired in `app/main.py`, running before routing/auth deps. It is the only enforcement path.
- **Identity = verify-only JWT.** Verify signature + `exp` (and read the signature-covered `aud`); **do NOT** perform the session/jti check (that stays in the auth deps). Invalid/absent token → key on trusted client IP.
- **Fail-open:** any Redis error/timeout in the bucket path → allow the request, set `sacco_rate_limit_redis_health=0`, WARN-log. Never fail-closed.
- **Metric labels are `{policy, audience}` only** — never `user_id`/PII (Phase-5 metric contract). Metric names `sacco_`-prefixed.
- **Per-plan overrides** come only from `subscription_plans.features` JSONB under key `rate_limit_overrides` (**no migration**). No per-tenant ad-hoc overrides.
- **Client IP** for anonymous limits derives from `X-Forwarded-For` (left-most hop) when `RATE_LIMIT_TRUSTED_PROXY` is on (default on); else the socket peer.
- **429** body `{"detail":"Rate limit exceeded","retry_after":N}` + headers `Retry-After` + `X-RateLimit-{Limit,Remaining,Reset}`; 2xx carry the `X-RateLimit-*` triple.
- **Redis token-bucket via one Lua `EVAL`** is the only atomic decrement path (no check-then-set in Python).
- **No changes to `alembic/`** (no migration) or any financial/business-logic behaviour. Money/async rules from CLAUDE.md still apply.
- **ruff + mypy (strict) clean**; tests: `env -u DATABASE_URL pytest <path> -q` (Redis + Postgres test infra via docker compose). Portal: `docker compose exec -T admin pnpm --filter @sacco/portal <test|lint|typecheck>`.
- A kill-switch `RATE_LIMIT_ENABLED` (default `true`) short-circuits the middleware to a pass-through when false.

---

## File Structure

```
app/core/rate_limit/
  __init__.py        public surface (RateLimitMiddleware)
  policies.py        Policy dataclass, DEFAULT_POLICIES table, match_policy(path, audience)
  identity.py        RateLimitIdentity + derive_identity(request, ...) (verify-only JWT / trusted-proxy IP)
  resolver.py        resolve_policy(...) layering per-plan overrides (Redis-cached)
  bucket.py          check_bucket(redis, key, policy, now) -> BucketResult (calls the Lua script)
  redis_bucket.lua   atomic token-bucket script
  errors.py          RateLimited exception (retry_after, limit, remaining, reset)
  middleware.py      RateLimitMiddleware (compose: identity → policy → bucket → 429/headers/metric/fail-open)
app/platform_/rate_limits/
  api.py             GET /platform/rate-limits, GET /platform/rate-limits/tenants/{id}/live
  schemas.py         PolicyOut, RateLimitConfigOut, TenantLiveOut
tests/core/rate_limit/
  test_policies.py, test_identity.py, test_redis_bucket.py, test_resolver.py, test_middleware.py
tests/platform_/test_rate_limits_api.py
admin/apps/portal/app/platform/(authed)/settings/rate-limits/…   (page + tests)
infra/observability/logfire/alerts/rate-limit-block-rate.json
docs/rate-limit-policies.md
```

Modified: `app/main.py` (wire middleware), `app/core/config.py` (2 settings), `app/core/observability/metrics.py` (2 metric handles), `CLAUDE.md` (close-out).

---

## Increment 1 — Limiter core

### Task 1: Policy table + path matcher

**Files:**
- Create: `app/core/rate_limit/__init__.py` (empty), `app/core/rate_limit/policies.py`
- Test: `tests/core/rate_limit/__init__.py`, `tests/core/rate_limit/test_policies.py`

**Interfaces:**
- Produces: `Policy` (frozen dataclass: `name: str`, `limit: int`, `window_seconds: int`); `Audience` = `Literal["anonymous","tenant","member","platform"]`; `match_policy(path: str, audience: Audience) -> Policy`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/rate_limit/test_policies.py
from app.core.rate_limit.policies import match_policy, Policy


def test_anonymous_login_is_10_per_min():
    p = match_policy("/auth/token", "anonymous")
    assert (p.name, p.limit, p.window_seconds) == ("auth_login", 10, 60)


def test_anonymous_password_reset_is_3_per_15min():
    p = match_policy("/member/auth/password-reset/request", "anonymous")
    assert (p.limit, p.window_seconds) == (3, 900)


def test_reporting_is_60_per_min_for_tenant():
    assert match_policy("/reporting/loan-portfolio", "tenant").limit == 60


def test_statement_export_is_10_per_min():
    assert match_policy("/member/statement", "member").limit == 10


def test_platform_admin_is_600_per_min():
    assert match_policy("/platform/tenants", "platform").limit == 600


def test_authenticated_default_is_300_per_min():
    assert match_policy("/savings/accounts", "tenant").name == "authenticated_default"


def test_anonymous_default_catch_all():
    # an anonymous hit to a non-auth path still gets a bucket
    assert match_policy("/savings/accounts", "anonymous").name == "anonymous_default"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u DATABASE_URL pytest tests/core/rate_limit/test_policies.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `policies.py`**

```python
# app/core/rate_limit/policies.py
from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Literal

Audience = Literal["anonymous", "tenant", "member", "platform"]


@dataclass(frozen=True)
class Policy:
    name: str
    limit: int
    window_seconds: int


# Ordered, most-specific first. (audience_scope, glob, Policy).
# audience_scope: "anonymous" | "authenticated" (tenant+member+platform) | "platform".
_RULES: list[tuple[str, str, Policy]] = [
    ("anonymous", "/auth/token", Policy("auth_login", 10, 60)),
    ("anonymous", "/platform/auth/token", Policy("auth_login", 10, 60)),
    ("anonymous", "/member/auth/token", Policy("auth_login", 10, 60)),
    ("anonymous", "*password-reset*", Policy("auth_password_reset", 3, 900)),
    ("anonymous", "*", Policy("anonymous_default", 60, 60)),
    ("platform", "/platform/*", Policy("platform_admin", 600, 60)),
    ("authenticated", "/reporting/*", Policy("reporting", 60, 60)),
    ("authenticated", "*statement*", Policy("export", 10, 60)),
    ("authenticated", "*/export*", Policy("export", 10, 60)),
    ("authenticated", "*", Policy("authenticated_default", 300, 60)),
]


def _scope_matches(scope: str, audience: Audience) -> bool:
    if scope == "anonymous":
        return audience == "anonymous"
    if scope == "platform":
        return audience == "platform"
    # "authenticated"
    return audience in ("tenant", "member", "platform")


def match_policy(path: str, audience: Audience) -> Policy:
    for scope, glob, policy in _RULES:
        if _scope_matches(scope, audience) and fnmatch.fnmatch(path, glob):
            return policy
    # Unreachable in practice (each audience has a "*" catch-all) but keep total.
    return Policy("authenticated_default", 300, 60)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u DATABASE_URL pytest tests/core/rate_limit/test_policies.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/rate_limit/ tests/core/rate_limit/
git commit -m "feat(rate-limit): policy table + path matcher"
```

---

### Task 2: Redis token-bucket (Lua + bucket.py)

**Files:**
- Create: `app/core/rate_limit/redis_bucket.lua`, `app/core/rate_limit/bucket.py`
- Test: `tests/core/rate_limit/test_redis_bucket.py` (real Redis)

**Interfaces:**
- Consumes: `Policy` (Task 1).
- Produces: `BucketResult` (dataclass: `allowed: bool`, `remaining: int`, `reset: int`, `limit: int`); `async def check_bucket(redis: Redis, key: str, policy: Policy, *, now: float | None = None, cost: int = 1) -> BucketResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/rate_limit/test_redis_bucket.py
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
    await r.aclose()


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u DATABASE_URL pytest tests/core/rate_limit/test_redis_bucket.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `redis_bucket.lua`**

```lua
-- KEYS[1] = bucket key
-- ARGV: capacity, refill_per_sec, now(sec float), cost, ttl(sec)
local capacity = tonumber(ARGV[1])
local refill   = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])
local cost     = tonumber(ARGV[4])
local ttl      = tonumber(ARGV[5])
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then tokens = capacity; ts = now end
local elapsed = now - ts
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill)
local allowed = 0
if tokens >= cost then allowed = 1; tokens = tokens - cost end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], ttl)
local reset = 0
if allowed == 0 then reset = math.ceil((cost - tokens) / refill) end
return {allowed, math.floor(tokens), reset, capacity}
```

- [ ] **Step 4: Write `bucket.py`**

```python
# app/core/rate_limit/bucket.py
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
    res = await redis.eval(
        _LUA, 1, key, policy.limit, refill, now, cost, ttl
    )  # type: ignore[no-untyped-call]
    allowed, remaining, reset, limit = (int(x) for x in res)
    return BucketResult(bool(allowed), remaining, reset, limit)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `env -u DATABASE_URL pytest tests/core/rate_limit/test_redis_bucket.py -v`
Expected: PASS (2 tests). Requires Redis up (`docker compose up -d redis`).

- [ ] **Step 6: Commit**

```bash
git add app/core/rate_limit/redis_bucket.lua app/core/rate_limit/bucket.py tests/core/rate_limit/test_redis_bucket.py
git commit -m "feat(rate-limit): atomic Redis token-bucket (Lua)"
```

---

### Task 3: Identity deriver (verify-only JWT / trusted-proxy IP)

**Files:**
- Create: `app/core/rate_limit/identity.py`
- Modify: `app/core/config.py` (add `rate_limit_trusted_proxy: bool = True`, `rate_limit_enabled: bool = True`)
- Test: `tests/core/rate_limit/test_identity.py`

**Interfaces:**
- Consumes: `Audience` (Task 1); `app.modules.iam.tokens.service.get_unverified_kid`; `app.modules.iam.keys.service.KeyService.get_verification_key(kid) -> (public_key_pem: bytes, algorithm: str, key_audience: str)`.
- Produces: `RateLimitIdentity` (dataclass: `key: str`, `audience: Audience`); `async def derive_identity(request: Request, redis: Redis, session_factory) -> RateLimitIdentity`.

Implementation notes for the implementer:
- Extract bearer token from `Authorization`. If absent → IP identity.
- `kid = get_unverified_kid(token)`; look up the public key. **Cache** `(public_pem, algorithm)` per `kid` in Redis (`setex(f"rl:jwk:{kid}", 300, ...)`, mirror `app/core/db.py:_resolve_tenant_schema`) to avoid a DB read per request; on cache miss call `KeyService.get_verification_key` (needs a platform session from `session_factory`).
- Verify with PyJWT **without** pre-known audience: `pyjwt.decode(token, public_pem, algorithms=[algorithm], options={"verify_aud": False})` — this still verifies signature + `exp`. Read `sub` and `aud` from the returned (now-authenticated) claims. Map `aud` → audience: `platform`→`platform`, `tenant:<slug>`→`tenant`, `member:<slug>`→`member`. Key = `u:{aud}:{sub}`.
- Any failure (malformed, bad signature, expired) → fall through to IP identity (audience `anonymous`). A forged token can't pass signature, so identity can't be spoofed.
- IP: if `settings.rate_limit_trusted_proxy` and `X-Forwarded-For` present → left-most entry; else `request.client.host`. Key = `ip:{addr}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/rate_limit/test_identity.py
import time
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from app.core.rate_limit.identity import _map_audience, _client_ip


def test_map_audience():
    assert _map_audience("platform") == "platform"
    assert _map_audience("tenant:acme") == "tenant"
    assert _map_audience("member:acme") == "member"


def test_client_ip_prefers_xff_when_trusted():
    class R:
        headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
        class client: host = "172.17.0.1"
    assert _client_ip(R(), trusted_proxy=True) == "9.9.9.9"
    assert _client_ip(R(), trusted_proxy=False) == "172.17.0.1"
```

(Full `derive_identity` verify-path is covered end-to-end in Task 5's middleware test with a signed-token fixture; here unit-test the two pure helpers `_map_audience` and `_client_ip`, which the implementer must expose.)

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u DATABASE_URL pytest tests/core/rate_limit/test_identity.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `identity.py`** (per the notes above; expose `_map_audience(aud: str) -> Audience` and `_client_ip(request, *, trusted_proxy: bool) -> str`, plus `RateLimitIdentity` and `derive_identity`). Add the two settings to `app/core/config.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u DATABASE_URL pytest tests/core/rate_limit/test_identity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/rate_limit/identity.py app/core/config.py tests/core/rate_limit/test_identity.py
git commit -m "feat(rate-limit): verify-only JWT identity + trusted-proxy client IP"
```

---

### Task 4: Policy resolver (per-plan overrides, Redis-cached)

**Files:**
- Create: `app/core/rate_limit/resolver.py`
- Test: `tests/core/rate_limit/test_resolver.py`

**Interfaces:**
- Consumes: `match_policy`, `Policy`, `RateLimitIdentity`.
- Produces: `async def resolve_policy(path: str, identity: RateLimitIdentity, redis: Redis, session_factory) -> Policy`; pure helper `apply_overrides(base: Policy, overrides: dict) -> Policy`.

Notes:
- `apply_overrides` is pure: given the code-default `Policy` and a plan's `rate_limit_overrides` dict (shape `{ "<policy_name>": {"limit": int, "window_seconds": int} }`), returns a new `Policy` with overridden fields (or `base` unchanged if the policy name isn't overridden). Unit-test this directly.
- `resolve_policy`: `base = match_policy(path, identity.audience)`. For tenant/member audiences, look up the tenant's plan `features.rate_limit_overrides`, **cached in Redis** (`setex(f"rl:overrides:{slug}", 300, json)`, mirror the schema cache) — parse the slug from `identity.key` (`u:tenant:<sub>` won't carry slug; instead the audience map must retain the slug: extend `RateLimitIdentity` with an optional `tenant_slug: str | None` set from the `aud`). On cache miss, query `platform.subscription_plans.features` joined via the tenant's current subscription. Apply overrides; return the effective `Policy`. Anonymous/platform → no overrides (return base).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/rate_limit/test_resolver.py
from app.core.rate_limit.resolver import apply_overrides
from app.core.rate_limit.policies import Policy


def test_apply_overrides_changes_matched_policy():
    base = Policy("reporting", 60, 60)
    out = apply_overrides(base, {"reporting": {"limit": 120, "window_seconds": 60}})
    assert (out.limit, out.window_seconds) == (120, 60)
    assert out.name == "reporting"


def test_apply_overrides_ignores_unrelated_policy():
    base = Policy("reporting", 60, 60)
    out = apply_overrides(base, {"export": {"limit": 5}})
    assert out == base


def test_apply_overrides_partial_limit_only():
    base = Policy("reporting", 60, 60)
    out = apply_overrides(base, {"reporting": {"limit": 90}})
    assert (out.limit, out.window_seconds) == (90, 60)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u DATABASE_URL pytest tests/core/rate_limit/test_resolver.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `resolver.py`** (pure `apply_overrides` + async `resolve_policy` per the notes). Extend `RateLimitIdentity` with `tenant_slug: str | None` in `identity.py` and set it from `aud` (Task 3 amendment — keep `_map_audience` unchanged; add slug extraction where the aud is parsed).

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u DATABASE_URL pytest tests/core/rate_limit/test_resolver.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/rate_limit/resolver.py app/core/rate_limit/identity.py tests/core/rate_limit/test_resolver.py
git commit -m "feat(rate-limit): policy resolver with Redis-cached per-plan overrides"
```

---

## Increment 2 — Middleware + wiring

### Task 5: RateLimitMiddleware + metrics + main.py wiring

**Files:**
- Create: `app/core/rate_limit/errors.py`, `app/core/rate_limit/middleware.py`
- Modify: `app/core/observability/metrics.py` (2 handles), `app/main.py` (wire middleware), `app/core/rate_limit/__init__.py` (export)
- Test: `tests/core/rate_limit/test_middleware.py`

**Interfaces:**
- Consumes: `derive_identity`, `resolve_policy`, `check_bucket`, `BucketResult`.
- Produces: `RateLimitMiddleware` (Starlette `BaseHTTPMiddleware` subclass). Metric handles `rate_limit_blocks` (counter, name `sacco_rate_limit_blocks_total`, labels `policy`,`audience`) and `rate_limit_redis_health` (gauge, `sacco_rate_limit_redis_health`).

Behavior the test pins:
- Bearer with a valid signed token → keyed as user; under-limit passes with `X-RateLimit-*` headers on the 200.
- Exceeding the bucket → **429** with `Retry-After` + `X-RateLimit-*` and body `{"detail":"Rate limit exceeded","retry_after":N}`; `rate_limit_blocks` incremented.
- Anonymous (no token) hitting `/auth/token` 11× in a window → 11th is 429.
- **Fail-open:** if the bucket call raises (simulate by monkeypatching `check_bucket` to raise), the request is allowed (2xx) and `rate_limit_redis_health` set to 0.
- `RATE_LIMIT_ENABLED=false` → pass-through (no headers, no bucket call).

- [ ] **Step 1: Write the failing test** (use `httpx.ASGITransport` + `lifespan(app)` like `tests/test_main.py`; mint a real tenant JWT via the existing key/token services or a small signed-token helper; add a throwaway test route or hit `/healthz`).

```python
# tests/core/rate_limit/test_middleware.py  (abridged — implementer fills token minting)
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app, lifespan


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_anonymous_login_blocks_after_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    async with lifespan(app), await _client() as c:
        statuses = []
        for _ in range(12):
            r = await c.post("/auth/token", json={"email": "x@y.z", "password": "bad"},
                             headers={"X-Forwarded-For": "203.0.113.7"})
            statuses.append(r.status_code)
        assert 429 in statuses
        last = [s for s in statuses if s == 429][0]
        # the 429 carries rate-limit headers
    # (assert Retry-After / X-RateLimit-* on a captured 429 response)


async def test_disabled_is_passthrough(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    async with lifespan(app), await _client() as c:
        r = await c.get("/healthz")
        assert r.status_code == 200
        assert "X-RateLimit-Limit" not in r.headers


async def test_fail_open_on_redis_error(monkeypatch):
    import app.core.rate_limit.middleware as mw
    async def boom(*a, **k):
        raise RuntimeError("redis down")
    monkeypatch.setattr(mw, "check_bucket", boom)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    async with lifespan(app), await _client() as c:
        r = await c.get("/healthz")
        assert r.status_code == 200  # allowed despite redis failure
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u DATABASE_URL pytest tests/core/rate_limit/test_middleware.py -v`
Expected: FAIL (middleware not wired)

- [ ] **Step 3: Write `errors.py`, the 2 metric handles, and `middleware.py`.** `middleware.py` composes: read `settings.rate_limit_enabled` (pass-through if false); `identity = await derive_identity(...)`; `policy = await resolve_policy(...)`; `key = f"rl:{policy.name}:{identity.key}"`; `try: result = await check_bucket(request.app.state.redis, key, policy)` — `except Exception: rate_limit_redis_health.set(0); return await call_next(request)` (fail-open, WARN-log); if `not result.allowed` → return `JSONResponse(429, {...})` with headers + `rate_limit_blocks.add(1, {"policy":policy.name,"audience":identity.audience})`; else `response = await call_next(request)`, attach `X-RateLimit-*`, return. `check_bucket` must be imported at module scope (so the test can monkeypatch `mw.check_bucket`). Reads Redis from `request.app.state.redis` and the platform `session_factory` from `app.core.db`.

- [ ] **Step 4: Wire into `app/main.py`** — register `RateLimitMiddleware` so it runs after `request_id_middleware` binds the contextvar (so 429 logs carry `request_id`) but before routing. Given Starlette runs middleware in reverse registration order, verify ordering with the test; the `@app.middleware("http")` request-id function plus a `app.add_middleware(RateLimitMiddleware)` should be arranged so request-id is outer. Confirm via a test assertion that a 429 response still echoes the `X-Request-ID` header.

- [ ] **Step 5: Run tests + gates**

Run: `env -u DATABASE_URL pytest tests/core/rate_limit/ -v && python -m ruff check app/ tests/ && python -m mypy app/`
Expected: PASS + clean. (Redis + Postgres test infra up.)

- [ ] **Step 6: Commit**

```bash
git add app/core/rate_limit/errors.py app/core/rate_limit/middleware.py app/core/rate_limit/__init__.py app/core/observability/metrics.py app/main.py tests/core/rate_limit/test_middleware.py
git commit -m "feat(rate-limit): RateLimitMiddleware + block metrics + wire into app (Inc 2 complete)"
```

---

## Increment 3 — Read-only API, portal, docs, close-out

### Task 6: Read-only `/platform/rate-limits*` endpoints

**Files:**
- Create: `app/platform_/rate_limits/__init__.py`, `app/platform_/rate_limits/api.py`, `app/platform_/rate_limits/schemas.py`
- Modify: `app/main.py` (include router)
- Test: `tests/platform_/test_rate_limits_api.py`

**Interfaces:**
- Produces: `GET /platform/rate-limits` (`CurrentAdmin`) → `RateLimitConfigOut` (default policy table + per-plan overrides across plans); `GET /platform/rate-limits/tenants/{tenant_id}/live` (`CurrentAdmin`) → `TenantLiveOut` (per-policy remaining tokens for that tenant, read from Redis via a non-mutating `HGET` of each bucket, or `check_bucket` with `cost=0`).

- [ ] **Step 1: Write the failing test** (assert 200 shape for config; assert `CurrentAdmin` gate → 403 for a support/finance token; assert live endpoint returns per-policy remaining for a known tenant). Use the platform-auth test fixtures.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** `schemas.py` (`PolicyOut{name,limit,window_seconds}`, `RateLimitConfigOut{defaults:list[PolicyOut], plan_overrides:dict[str,dict]}`, `TenantLiveOut{tenant_id, buckets:list[{policy,remaining,limit}]}`) + `api.py`. `defaults` derives from the `policies._RULES` table (expose a `list_default_policies() -> list[Policy]` helper in `policies.py` rather than reaching into `_RULES` from the router). `plan_overrides` reads `subscription_plans.features.rate_limit_overrides` for all plans. Live buckets: use `cost=0` (a peek that never decrements — add `cost=0` support already present in `check_bucket`) or `HGET tokens`. Register router in `app/main.py`.

- [ ] **Step 4: Run tests + gates → PASS + clean.**

- [ ] **Step 5: Commit** `feat(rate-limit): read-only /platform/rate-limits config + live endpoints`.

---

### Task 7: Admin-portal `/settings/rate-limits` page (read-only)

**Files:**
- Create the page under `admin/apps/portal/app/platform/(authed)/settings/rate-limits/` (server component fetches via the typed client; `<DataTable>` for policies + overrides; a per-tenant live panel), api-client resource + query keys, types in `@sacco/schemas`.
- Test: portal test (renders policies/overrides; permission-gated).

- [ ] **Step 1–5:** Follow the portal conventions (contracts H–T). Use the `new-portal-page` skill's structure: route + server component + client subcomponents + error/loading boundaries + types + test. Fetch `GET /platform/rate-limits` server-side; render defaults + overrides through `<DataTable>` (contract T); nav under Settings. Permission gate: settings.read to view (API enforces `CurrentAdmin`). Run `docker compose exec -T admin pnpm --filter @sacco/portal test|lint|typecheck` — all green. Commit `feat(portal): read-only rate-limits settings page`.

(This is the contract-N `admin/` scope exception for Phase 6.)

---

### Task 8: Metrics def + docs + CLAUDE.md close-out

**Files:**
- Create: `infra/observability/logfire/alerts/rate-limit-block-rate.json`, `docs/rate-limit-policies.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1:** Add the committed Logfire alert definition (block rate > 100/min sustained, `source: metric` over `sacco_rate_limit_blocks_total`, email channel) matching the Phase-5 alert JSON schema; note in its README-adjacent metrics-catalogue entry.
- [ ] **Step 2:** `docs/rate-limit-policies.md` — the default policy table, override mechanism (`subscription_plans.features.rate_limit_overrides` shape), identity keying, fail-open behavior, the `RATE_LIMIT_*` settings, and the 429/header contract.
- [ ] **Step 3:** Update `docs/metrics-catalogue.md` with the 2 new `sacco_rate_limit_*` metrics.
- [ ] **Step 4: CLAUDE.md close-out** — roadmap row 6 → **Done**; add a "Rate limiting contracts (Phase 6 — do not violate)" section (the Global Constraints above: middleware-only enforcement, verify-only identity/no jti check, fail-open, `{policy,audience}` labels, plan-level overrides only, X-Forwarded-For IP); add a Phase 6 scope note under contract N (touches `app/core/rate_limit/`, `app/platform_/rate_limits/`, `app/main.py`, `app/core/config.py`, `app/core/observability/metrics.py`, `admin/…/settings/rate-limits`, `infra/observability/`, `docs/` — NOT `alembic/`).
- [ ] **Step 5:** Gates: `python -m ruff check app/ && python -m mypy app/ && env -u DATABASE_URL pytest tests/core/rate_limit tests/platform_/test_rate_limits_api.py -q`. Commit `feat(rate-limit): block-rate alert + docs + CLAUDE.md close-out (Phase 6 complete)`.

---

## Self-Review

**Spec coverage:**
- Middleware + verify-only identity → Tasks 3, 5. ✓
- Token bucket (Lua, atomic) → Task 2. ✓
- Policy defaults + per-plan overrides (features jsonb, Redis-cached) → Tasks 1, 4. ✓
- Client IP via X-Forwarded-For + trusted-proxy setting → Task 3. ✓
- Fail-open + redis-health gauge → Task 5. ✓
- 429 + X-RateLimit headers (429 and 2xx) → Task 5. ✓
- Block metric `{policy,audience}` (no user_id) → Task 5. ✓
- Kill-switch `RATE_LIMIT_ENABLED` → Tasks 3 (setting), 5 (honored). ✓
- Read-only `/platform/rate-limits*` endpoints → Task 6. ✓
- Portal `/settings/rate-limits` page → Task 7. ✓
- Logfire block-rate alert def + docs + CLAUDE.md close-out → Task 8. ✓
- No migration / no alembic → confirmed (features jsonb reused). ✓

**Placeholder scan:** No TBD/TODO. The middleware ordering nuance (Task 5 Step 4) and token-minting in the middleware test are called out with the exact verification (assert `X-Request-ID` on a 429; reuse existing key/token services), not left vague.

**Type consistency:** `Policy(name,limit,window_seconds)`, `Audience`, `match_policy`, `list_default_policies`, `BucketResult(allowed,remaining,reset,limit)`, `check_bucket(...,cost=1)`, `RateLimitIdentity(key,audience,tenant_slug)`, `derive_identity`, `apply_overrides`, `resolve_policy`, `rate_limit_blocks`/`rate_limit_redis_health` — consistent across tasks and the read-only endpoint (`list_default_policies`, `check_bucket(cost=0)`).
