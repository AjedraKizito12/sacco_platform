# Phase 6 — Rate Limiting & Abuse Protection — Design

**Status:** Approved (brainstorming, 2026-08-02)
**Roadmap:** `docs/superpowers/plans/saas-launch-roadmap.md` §Phase 6
**Register:** cross-cutting infrastructure (`app/core/rate_limit/`) + a read-only
platform endpoint + one admin-portal settings page. Not a bounded context.

## Goal

Stop any caller — malicious or buggy — from flooding the API, drowning the DB,
or brute-forcing auth. Add Redis-backed token-bucket rate limits with
per-audience, per-endpoint policies and optional per-plan overrides, enforced by
a single HTTP middleware, before real customer money flows at scale.

## Key decisions (settled in brainstorming)

1. **Scope:** full Phase 6 — limiter core, policy resolver, middleware
   enforcement, 429 + `X-RateLimit-*` headers, Phase-5 block metrics, fail-open,
   docs, AND the read-only admin-portal `/settings/rate-limits` page (a
   sanctioned contract-N scope exception, like Phase 4).
2. **Enforcement = HTTP middleware with verify-only JWT identity.** The
   middleware runs before routing/auth deps. For authenticated requests it
   cheaply verifies the bearer JWT (signature + `aud` + `exp` via the cached
   signing key; NO session/DB check) to key on the user; anonymous/invalid
   tokens key on the trusted client IP. This rejects floods before the expensive
   auth path (Redis session + DB user) runs, and keys on an unspoofable
   (verified) identity.
3. **Fail-open on Redis outage** (roadmap posture): allow the request, emit a
   health gauge + WARN. Fail-closed would turn a Redis blip into a full-platform
   DoS; IAM lockout still guards `/auth/token` brute-force if the limiter is down.
4. **Per-plan overrides only** — no per-tenant ad-hoc overrides in v1.

## Architecture

New library `app/core/rate_limit/`, one middleware wired into `app/main.py`
after the `request_id` middleware and before routing:

```
app/core/rate_limit/
  __init__.py        public surface
  middleware.py      RateLimitMiddleware — identity → policy → bucket → 429/headers/metric
  identity.py        derive rate-limit key (verify-only JWT → u:<aud>:<sub>; else ip:<addr>)
  policies.py        default policy table (in code) + Policy dataclass
  resolver.py        resolve (path, audience) → Policy; layer per-plan overrides (Redis-cached)
  bucket.py          token-bucket check via the Lua script
  redis_bucket.lua   atomic token-bucket script
  errors.py          RateLimited (Retry-After / X-RateLimit-*)
```

### Per-request flow (middleware)

1. **Identity** (`identity.py`): if `Authorization: Bearer <jwt>` present, verify
   signature + `aud` + `exp` using the cached signing key (reuse
   `KeyService`/`tokens.decode_token` primitives; NO `SessionService` jti check —
   a not-yet-expired revoked token sharing its own bucket is harmless). On
   success → key `u:{aud}:{sub}` and audience ∈ {`tenant:<slug>`, `platform`,
   `member:<slug>`}. On absent/invalid → key `ip:{client_ip}`, audience
   `anonymous`.
2. **Policy** (`resolver.py`): match the request path against an ordered,
   most-specific-first pattern list to get a `policy` label, then resolve the
   `Policy` (limit, window seconds, burst) from code defaults, layering the
   caller's plan overrides when present.
3. **Bucket** (`bucket.py` + `redis_bucket.lua`): one atomic Lua eval computes
   refill, checks/decrements, returns `{allowed, remaining, reset, limit}`.
4. **Respond:** allowed → call downstream, attach `X-RateLimit-{Limit,Remaining,
   Reset}` to the response. Exceeded → short-circuit **429** with `Retry-After`
   + the same headers, before any route/auth work; increment the block metric.

## Policy model

**Defaults in code** (`policies.py`), keyed by `(path pattern, audience)`:

| Scope (audience) | Path pattern | Limit |
|---|---|---|
| anonymous (IP) | `/auth/token`, `/platform/auth/token`, `/member/auth/token` | 10 / min |
| anonymous (IP) | `**/password-reset/**` | 3 / 15 min |
| authenticated | default (any authed route) | 300 / min / user |
| authenticated | `/reporting/**`, `**/statement*` | 60 / min / user |
| authenticated | export (member statement, CSV) | 10 / min / user |
| platform admin | `/platform/**` | 600 / min / user |

**Per-plan overrides:** read from the existing `subscription_plans.features`
JSONB (`rate_limit_overrides` key — **no migration**). The resolver layers a
tenant's plan overrides over defaults. The middleware must not do a per-request
DB read, so the resolved per-tenant policy set is **cached in Redis with a short
TTL** (mirror the existing 5-minute `schema_name` cache pattern); plan changes
take effect within the TTL. Plan-level only — no per-tenant ad-hoc overrides.

## Identity, client IP & fail-open

- **Key namespace:** `rl:{policy}:{identity}` (`u:{aud}:{sub}` or `ip:{addr}`).
  Audience is part of the identity so a tenant user, member, and platform user
  never share a bucket.
- **Client IP behind proxy (correctness-critical):** Caddy is the sole ingress,
  so the socket peer is always Caddy. Derive the client IP from
  `X-Forwarded-For` (left-most untrusted hop); trusted-proxy behavior
  configurable via `RATE_LIMIT_TRUSTED_PROXY` (default on). Without this, every
  anonymous request shares Caddy's IP and the login limiter is useless.
- **Fail-open:** on any Redis error/timeout in the bucket call, allow the
  request, set `sacco_rate_limit_redis_health=0`, and WARN-log. Deliberate
  availability-over-strictness tradeoff; complementary to IAM lockout.

## Response semantics (fixed contracts)

- **429** body `{"detail": "Rate limit exceeded", "retry_after": <seconds>}`,
  headers `Retry-After: <seconds>` + `X-RateLimit-{Limit,Remaining,Reset}`.
- **2xx/other** responses carry `X-RateLimit-{Limit,Remaining,Reset}`.
- `Reset` is epoch seconds when the bucket refills to allow the next request.

## Metrics (Phase 5 integration)

Add two handles to `app/core/observability/metrics.py`:

- `sacco_rate_limit_blocks_total{policy, audience}` — counter, incremented per
  429. **Deliberately NO `user_id` label** (cardinality explosion + PII, against
  the Phase 5 metric contract); per-user detail lives on the request span/log.
- `sacco_rate_limit_redis_health` — gauge (1 healthy / 0 during fail-open).

Add committed Phase-6 definitions under `infra/observability/logfire/` (applied
at deploy time, like Phase 5): a rate-limit alert **block rate > 100/min
sustained** and an optional overview panel. No live provisioning.

## Portal & read-only config API

- **New read-only endpoint** (backend, this phase): `GET /platform/rate-limits`
  (`CurrentAdmin`) → default policy table + per-plan overrides.
  `GET /platform/rate-limits/tenants/{id}/live` (`CurrentAdmin`) → a tenant's
  current bucket state (remaining tokens per policy) read straight from Redis.
  (The Phase-2 "zero new endpoints" ban was Phase-2-scoped; new backend
  endpoints are in-scope for Phase 6.)
- **Portal page** `admin/apps/portal/app/platform/(authed)/settings/rate-limits`
  (read-only): default policies + per-plan overrides via `<DataTable>`, and a
  per-tenant live-consumption view (remaining tokens now). **The roadmap's
  "last-hour consumption bar chart" is deferred** — that history lives in
  Logfire, not a portal-readable store; a Logfire dashboard covers it. Contract-N
  scope exception (edits `admin/`).

## Testing

- `test_policies.py` — resolution + override layering (pure).
- `test_identity.py` — verify-only JWT keying, `X-Forwarded-For` IP derivation,
  spoof-resistance (forged/unsigned token → treated anonymous).
- `test_redis_bucket.py` — real Redis: refill, burst up to capacity, atomicity,
  idle-bucket TTL expiry.
- `test_middleware.py` — 429 + headers, 200 header injection, fail-open on a
  simulated Redis error, anonymous vs authenticated keying.
- Portal test for the settings page (renders policies/overrides; permission gate).

## Contracts to establish (into CLAUDE.md at close-out)

- All rate-limit code lives in `app/core/rate_limit/`. The token bucket is the
  only limiter; the Lua script is the only atomic decrement path.
- The middleware verifies the JWT for identity only (sig+aud+exp) — it must NOT
  perform the session/jti check (that stays in the auth deps).
- Rate limiting fails OPEN on Redis errors; never fail-closed.
- Metric labels are `{policy, audience}` only — never user_id/PII.
- Per-plan overrides come only from `subscription_plans.features.rate_limit_overrides`;
  no per-tenant ad-hoc overrides.
- Client IP for anonymous limits derives from `X-Forwarded-For` (trusted proxy),
  not the socket peer.

## Dependencies & non-goals

- **Prerequisite met:** Phase 5 (metrics) landed — blocks are observable.
- **Downstream:** production launch.
- **Non-goals (v1):** per-tenant ad-hoc overrides; historical consumption charts
  in the portal; global/distributed limits beyond per-identity buckets;
  CAPTCHA/challenge flows. The limiter complements, does not replace, IAM lockout.

## Effort

Medium — S/M per the roadmap (1 week). Bucket + middleware + policies is the
core; portal page + read-only endpoint + metrics + docs are the remainder.
