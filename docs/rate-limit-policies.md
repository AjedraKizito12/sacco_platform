# Rate Limiting & Abuse Protection (Phase 6)

The platform enforces per-window request budgets in a single HTTP middleware
(`app/core/rate_limit/middleware.py`), wired in `app/main.py` to run inside
`request_id_middleware` (so a 429 still carries `X-Request-ID`) but before
routing and auth dependencies. It is the only enforcement path. Postgres is
untouched — there is **no migration**; the token buckets live in Redis and the
per-plan overrides ride on the existing `subscription_plans.features` JSONB.

## Default policies

The policy for a request is chosen by `match_policy(path, audience)` against an
ordered, most-specific-first table (`app/core/rate_limit/policies.py:_RULES`).
`audience` is one of `anonymous` / `tenant` / `member` / `platform`; a scope of
`authenticated` matches tenant + member + platform.

| Policy | Limit / window | Applies to |
|---|---|---|
| `auth_login` | 10 / 60s | `anonymous` on `/auth/token`, `/platform/auth/token`, `/member/auth/token` |
| `auth_password_reset` | 3 / 900s | `anonymous` on any `*password-reset*` path |
| `anonymous_default` | 60 / 60s | any other `anonymous` request |
| `platform_admin` | 600 / 60s | `platform` audience on `/platform/*` |
| `reporting` | 60 / 60s | `authenticated` on `/reporting/*` |
| `export` | 10 / 60s | `authenticated` on `*statement*` or `*/export*` |
| `authenticated_default` | 300 / 60s | any other `authenticated` request |

The limiter is a Redis token bucket implemented as a single atomic Lua `EVAL`
(`app/core/rate_limit/redis_bucket.lua`) — capacity = the policy limit, refill =
`limit / window_seconds` tokens per second. There is no check-then-set in
Python; the decrement is atomic.

## Identity keying

`derive_identity` (`app/core/rate_limit/identity.py`) decides what a request is
keyed under:

- **Verified JWT wins.** If a `Bearer` token is present and its signature +
  `exp` verify, the request is keyed `u:<audience>:<sub>` and gets that
  audience's (usually higher) tier. This is **verify-only**: the signature and
  `aud` are checked, but the session/JTI revocation check is **not** performed
  here — that stays in the auth dependencies. A forged or tampered token can
  never pass verification, so it falls through to IP identity rather than
  forging an elevated tier.
- **Otherwise, client IP.** Keyed `ip:<addr>`, audience `anonymous`. The
  address comes from the left-most `X-Forwarded-For` hop when
  `RATE_LIMIT_TRUSTED_PROXY` is on (the default — safe only because Caddy is
  guaranteed to set/overwrite the header); otherwise the socket peer. `X-F-F`
  is never trusted directly from the internet.

Buckets are keyed per user/IP, **not per tenant** — there is no aggregate
tenant bucket. (The read-only per-tenant "live" view reconstructs a tenant
picture by peeking each of its users' buckets; see below.)

## Per-plan overrides

Limits can be raised or lowered per subscription plan — the only override
mechanism (no per-tenant ad-hoc overrides). Set a `rate_limit_overrides` key
in a plan's `features` JSONB:

```json
{
  "rate_limit_overrides": {
    "authenticated_default": { "limit": 1000 },
    "reporting": { "limit": 120, "window_seconds": 60 }
  }
}
```

- Keyed by policy **name**; each inner object may set `limit`, `window_seconds`,
  or both (partial overrides fall back to the code default field-by-field).
- `resolve_policy` (`app/core/rate_limit/resolver.py`) applies the tenant's
  plan overrides on top of the code default for `tenant` / `member` audiences.
  `anonymous` and `platform` audiences never carry plan overrides.
- The tenant → plan override lookup is **Redis-cached for 300s** (key
  `rl:overrides:<slug>`). After editing a plan's overrides, allow up to ~5
  minutes for the change to take effect. The resolver never raises into the
  request path — a cache/DB hiccup degrades to the code default.

## Response contract

- **Blocked → 429** with body `{"detail": "Rate limit exceeded", "retry_after": N}`
  and headers `Retry-After: N`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`
  (`0`), `X-RateLimit-Reset`.
- **Allowed (2xx and other) → the `X-RateLimit-{Limit,Remaining,Reset}` triple**
  is attached to the response.

## Fail-open

Any error/timeout in the Redis bucket path is caught: the request is **allowed
through**, `sacco_rate_limit_redis_health` is set to `0`, and a WARN is logged.
The limiter never fails closed — a limiter outage must not take the platform
down. A spike in *blocks* (`sacco_rate_limit_blocks_total`) means the limiter
is working; `redis_health=0` is the outage signal.

## Settings

| Setting | Default | Effect |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Kill switch. When `false`, the middleware is a pure pass-through — no identity/policy work, no bucket call, no headers. |
| `RATE_LIMIT_TRUSTED_PROXY` | `true` | Trust the left-most `X-Forwarded-For` hop for client IP. Turn off only if the app is exposed without a trusted reverse proxy in front. |

## Metrics & alerting

Two `sacco_rate_limit_*` instruments (see `docs/metrics-catalogue.md`):
`sacco_rate_limit_blocks_total{policy,audience}` (429 counter, no per-user
label) and `sacco_rate_limit_redis_health` (fail-open gauge). Golden signals
(request rate, error rate, latency) come from Logfire's auto-instrumented
FastAPI spans, not custom metrics. The committed block-rate alert lives at
`infra/observability/logfire/alerts/rate-limit-block-rate.json`; its response
runbook is `docs/alert-runbooks/rate-limit-block-rate.md`.

## Operator surface

`GET /platform/rate-limits` (admin) returns the default policy table + every
plan's overrides; `GET /platform/rate-limits/tenants/{id}/live` (admin) returns
the per-policy worst-case (minimum) remaining tokens across the tenant's active
users — a read-only peek (`HMGET`, never a decrementing check). Both are
surfaced in the admin portal at `/platform/settings/rate-limits`. These are
observability only; they cannot change any limit (overrides are edited on the
plan).
