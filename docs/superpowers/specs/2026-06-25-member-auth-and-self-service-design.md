# Phase 4a — Member Authentication & Self-Service Read API

**Status:** Design approved 2026-06-25
**Scope:** Backend only. Unblocks Phase 4b (member self-service portal UI).

## Problem

Members are KYC-vetted *records* in the tenant schema; they are not *users*. The
`members` table has no credentials, there is no member-auth bounded context, and
there are no member-scoped endpoints. The Phase 4 member self-service portal
cannot be built until members can authenticate and read their own data. Every
other portal surface shipped as a near-pure client because its backend already
existed; the member portal is the one remaining surface blocked on backend work.

This spec delivers, in one cut, the member authentication context **and** the
read-only member-scoped endpoints the UI consumes, so Phase 4b is a pure-client
build.

## Decisions (locked during brainstorming)

1. **Credentials live on the `members` table** (columns), not a separate
   `member_users` table. One table; record and login are co-located.
2. **Operator-provisioned access.** An operator enables portal access on a
   member; the backend mints a one-time set-password token (reuse the existing
   HMAC reset-token infra, 24h TTL). The member redeems it via the password-reset
   confirm flow and chooses their own password. No password travels through the
   operator. No member self-registration.
3. **This spec covers auth + read endpoints**, read-only. Member-scoped reads for
   profile, savings, shares, loans, and fees ship here. No member mutations.
4. **Member endpoints are subscription-gated** exactly like operator endpoints —
   they reuse `get_tenant_session`. Login and reads fail 402/403 when the SACCO
   is past-due/suspended.
5. **Read-endpoints are distributed per-module** (each domain module owns its
   `/member/*` route), not centralized in a new aggregation module.

## Architecture & module layout

Auth lives in IAM (per the IAM contract that all password/login logic belongs in
IAM). Member-facing reads live in each domain module. The operator "enable
access" action lives in the members module but delegates to an IAM service (no
direct cross-module model writes — architectural rule 2).

```
app/modules/iam/
  member_auth/
    __init__.py
    schemas.py        # MemberTokenResponse, login/refresh/reset DTOs
    service.py        # MemberAuthService: login/refresh/logout/me/reset_request/
                      #   reset_confirm + enable_access (mint set-password token)
    api.py            # /member/auth/* router
  sessions/
    models.py         # + MemberSession (new model, tenant schema)
  dependencies.py     # + get_current_member_jwt / _stub / CurrentMember
  auth_audit.py       # + write_member_auth_event

app/modules/members/
  models.py           # + auth columns (hashed_password, portal_enabled, last_login_at)
  api.py              # + GET /member/me
                      # + operator POST /members/{id}/enable-portal-access
  service.py          # enable_portal_access delegates to MemberAuthService

app/modules/savings/api.py   # + GET /member/savings
                             # + GET /member/savings/{account_id}/transactions
app/modules/shares/api.py    # + GET /member/shares
app/modules/credit/api.py    # + GET /member/loans
                             # + GET /member/loans/{loan_id}
                             # + GET /member/loans/{loan_id}/schedule
                             # + GET /member/loans/{loan_id}/statement
app/modules/fees/api.py      # + GET /member/fees

app/main.py                  # include the new /member/auth router
```

## Data model & migration

New migration in `alembic/tenant/` (per-tenant schema; tenant models declare no
`schema=`).

### Columns added to `members`

| Column | Type | Notes |
|---|---|---|
| `hashed_password` | `Text NULL` | argon2id hash; NULL until the member sets a password |
| `portal_enabled` | `bool NOT NULL DEFAULT false` | operator gate; login refused when false |
| `last_login_at` | `TIMESTAMPTZ NULL` | updated on each successful login |

### New table `member_sessions` (tenant schema)

Mirrors `tenant_sessions`:

| Column | Type |
|---|---|
| `id` | `UUID` PK |
| `member_id` | `UUID` FK → `members.id` |
| `jti` | `Text NOT NULL` |
| `user_agent` | `Text NULL` |
| `ip_address` | `Text NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `expires_at` | `TIMESTAMPTZ NOT NULL` |
| `revoked_at` | `TIMESTAMPTZ NULL` |
| `last_used_at` | `TIMESTAMPTZ NULL` |

Index on `member_id`; index/unique consideration on `jti` consistent with
`tenant_sessions`.

### Login eligibility

A member may log in only when:

```
portal_enabled = true
AND hashed_password IS NOT NULL
AND status = 'active'
```

`status IN ('suspended', 'exited', 'pending')` cannot log in. Email is the login
identifier (already `UNIQUE`, nullable) — a member without an email cannot be
enabled (the enable endpoint rejects it with 400).

### Audit behaviour

`Member` carries `AuditableMixin`, so `hashed_password` / `portal_enabled`
changes audit naturally with before/after JSON. `last_login_at` is written via a
targeted UPDATE that does **not** route through the mixin diff, to avoid an audit
row on every login (same spirit as session `last_used_at`).

## Token & session design

- **Audience namespace is the isolation boundary.** Member access/refresh tokens
  carry `aud="member:<slug>"`. Operators use `aud="tenant:<slug>"`; platform uses
  `aud="platform"`. `decode_token`'s audience check rejects a member token on an
  operator endpoint and vice versa. No additional cross-checks needed.
- **Signing key reuses the `"tenant"` DB-column audience.** `MemberAuthService`
  calls `KeyService.get_active_signing_key("tenant")` and
  `get_verification_key(kid)` exactly as tenant auth does. The JWT `aud` claim is
  decoupled from the signing-key audience (already true for tenant auth, where
  the key column is `"tenant"` but the claim is `"tenant:<slug>"`). **No change to
  `verify_boot_keys()` or key rotation** — no new boot-key requirement.
- **Sessions** use the already-generic `SessionService(model_cls=MemberSession)`.
  Immediate revocation via the existing Redis jti check on every decode.
- `access_token` claims: `sub=<member.id>`, `aud="member:<slug>"`,
  `actor_type="member"`, `session_id`, `kid`. No impersonation claim.

## Auth flows

### Provisioning (operator)

`POST /members/{id}/enable-portal-access` — operator router, `CurrentTenantUser`,
subscription-gated.

- 400 if the member has no email.
- Sets `portal_enabled = true`.
- Mints a one-time set-password token via `make_reset_token(member_id, secret)`
  (reuse `reset_tokens.py`), 24h TTL, jti stored in Redis.
- Returns the token once in the response body (portal renders it in a
  `OneTimeModal`; delivered out-of-band until Phase 3 email).
- **Idempotent:** re-calling on an already-enabled member re-issues a fresh token
  (operator can re-send if the member lost the first).
- Delegates to `MemberAuthService.enable_access()` (the members service does not
  write credentials directly).

### Set password / reset

- `POST /member/auth/password-reset` — self-service request. Always returns
  `None` regardless of whether the email exists (anti-enumeration). Mints a
  15-minute token (self-service TTL, vs the 24h operator-issued TTL).
- `POST /member/auth/password-reset/confirm` — `{ token, new_password }`. Reuses
  `verify_reset_token` + Redis jti consumption + `hash_password`. Single-use.
  Revokes all the member's existing sessions on success.

### Login / refresh / logout / me

`MemberAuthService` mirrors `TenantAuthService`:

- `POST /member/auth/token` — `{ email, password }` → `MemberTokenResponse`.
  Lockout check (`lockout.py`), password verify, eligibility check, create
  `MemberSession`, issue tokens, write `login_success` / `login_failed` audit.
  Generic 401 for unknown or ineligible member (anti-enumeration); 423 on
  lockout. Updates `last_login_at`.
- `POST /member/auth/refresh` — does **not** rotate the refresh token; reissues
  the access token only; validates session jti via Redis.
- `POST /member/auth/logout` — revokes the session.
- `GET /member/auth/me` — returns the member profile for the bearer token.

### `CurrentMember` dependency

In `iam/dependencies.py`, mirroring `get_current_tenant_user_jwt`:

- Validates the Bearer JWT with `aud="member:<slug>"` (slug from the tenant
  header), checks `MemberSession` (exists, not revoked), loads the `Member`,
  confirms eligibility, binds structlog `actor_type="member"`, `actor_id`,
  `actor_label` (member full name / email).
- A `MEMBER_AUTH_MODE` setting (default `jwt`) selects the real dependency; a stub
  (`X-Member-Actor-ID` header) is used in tests. `stub` is forbidden when
  `APP_ENV=production`, mirroring the platform/tenant contracts.
- Exported as `CurrentMember = Annotated[Member, Depends(get_current_member)]`.
  Route handlers import `CurrentMember`, never the underlying function.

## Member-scoped read endpoints (read-only, v1)

All depend on `CurrentMember` + `get_tenant_session` (gated) and filter strictly
to `current_member.id`. They **reuse existing query services** and never accept a
client-supplied `member_id`.

| Endpoint | Module | Source |
|---|---|---|
| `GET /member/me` | members | the resolved `Member` |
| `GET /member/savings` | savings | `list_accounts(member_id=current.id)` (exists) |
| `GET /member/savings/{account_id}/transactions` | savings | ownership-checked → 404 if not theirs |
| `GET /member/shares` | shares | member-filtered share accounts |
| `GET /member/loans` | credit | member-filtered loans |
| `GET /member/loans/{loan_id}` | credit | ownership-checked → 404 |
| `GET /member/loans/{loan_id}/schedule` | credit | ownership-checked → 404 |
| `GET /member/loans/{loan_id}/statement` | credit | ownership-checked → 404 (JSON; PDF deferred) |
| `GET /member/fees` | fees | member-filtered fee assessments |

**Cross-member access returns 404, not 403** — do not leak row existence (matches
the billing tenant-ownership precedent). Any `{id}` path param is verified to
belong to the current member before returning.

## Security & isolation

- Audience namespace (`member:` vs `tenant:` vs `platform`) is the hard boundary;
  enforced by `decode_token`.
- Member routes are subscription-gated via `get_tenant_session` — login and reads
  return 402/403 when the SACCO is past-due/suspended.
- No member mutations in v1: no profile edit, no loan application, no withdrawal,
  no maker-checker from the member side.
- `MEMBER_AUTH_MODE` defaults to `jwt`; `stub` forbidden in production.
- Reset tokens never appear in URLs/query strings/logs (existing contract).

## Error semantics

| Status | Condition |
|---|---|
| 401 | invalid/expired token; bad credentials; **ineligible member at login** (generic, anti-enumeration) |
| 403 | **ineligible member at the dependency layer** — an already-authenticated member whose status flipped to suspended/exited mid-session (no enumeration risk; caller is that member) |
| 404 | cross-member resource (ownership mismatch) |
| 400 | reset token invalid / already consumed; enable on member without email |
| 423 | login lockout (with `Retry-After`) |
| 402 / 403 | subscription gate (from `get_tenant_session`) |

## Testing

Real-Postgres integration tests (`tests/modules/iam/member_auth/` and per-module
`test_member_api.py`):

- Full lifecycle: enable → set-password → login → refresh → logout → revocation.
- Lockout after N failed attempts; `Retry-After`.
- Anti-enumeration: unknown email and ineligible member both return generic 401;
  `password-reset` always returns None.
- **Audience isolation**: a member token is rejected (401) by an operator
  endpoint, and an operator/tenant token is rejected by a `/member/*` endpoint.
- Ownership 404s: member A cannot read member B's savings account, loan,
  schedule, statement, or fees.
- Subscription gate: `/member/*` returns 402/403 when the tenant is
  past-due/suspended.
- Stub-mode tests use `X-Member-Actor-ID`.

Service methods are unit-tested per project convention. `ruff` + `mypy --strict`
clean.

## Out of scope (YAGNI)

- Member self-registration / identity-proofing.
- Any member mutation (profile edit, loan apply, withdrawal request, transfers).
- Member-facing maker-checker.
- Email / SMS delivery of tokens (Phase 3 notifications).
- Joint accounts / multiple members per login / member RBAC.
- Member statement **PDF** (JSON statement only in v1).
- The member portal UI — that is Phase 4b, a separate pure-client spec.

## Follow-ups unblocked by this spec

- Phase 4b: member self-service portal UI (new authed route group, consumes
  `/member/*`).
- Phase 3 email wiring will later deliver set-password/reset tokens instead of
  the out-of-band/one-time-modal interim.
