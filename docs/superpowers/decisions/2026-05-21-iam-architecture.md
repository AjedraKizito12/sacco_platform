# ADR-001: IAM Module Architecture

**Date:** 2026-05-21
**Status:** Accepted
**Deciders:** Liam / Claude
**Context:** IAM is bounded context #3. These decisions were locked in before implementation began so the module build doesn't re-litigate them.

---

## Context

The `platform_` module ships with a stub auth dependency (`get_current_platform_user`, `get_current_tenant_user`) that validates an `X-Platform-Actor-ID` header without cryptographic proof. IAM replaces the *implementations* of those dependencies while keeping their signatures unchanged. It also introduces tenant-side auth (tenant users, roles, permissions).

---

## Decisions

### 1. Two Parallel JWT Systems

Platform users and tenant users each get their own JWT auth stack, sharing low-level primitives (signing key management, password hashing, MFA) but issuing tokens with separate audiences.

- Platform tokens: `aud=platform`
- Tenant tokens: `aud=tenant:<slug>`

**Not** a unified token. Mixing audiences is forbidden.

### 2. Asymmetric Signing — RS256 or EdDSA

No HS256. Keys are identified by `kid` in the token header. Public-key verification at all trust boundaries. Key rotation is handled by adding a new key pair and retiring the old one (not by rekeying).

### 3. Token Lifetimes

| Token type | Lifetime |
|---|---|
| Access token (tenant) | 15 min |
| Refresh token (tenant) | 8 h |
| Access token (platform) | 15 min |
| Refresh token (platform) | 1 h |

Refresh tokens are stored server-side in Redis (keyed by `jti`) for individual revocation. An expired or missing Redis entry invalidates the refresh token regardless of its cryptographic validity.

### 4. Minimal Token Claims — Permissions Resolved Per-Request

Token claims: `sub`, `aud`, `iat`, `exp`, `jti`, `kid`, `actor_type`, `session_id`.

**Permissions are never in the token.** They are resolved per-request from DB and cached in Redis (short TTL). This means permission changes take effect within one cache TTL without requiring re-login.

### 5. Server-Side Session Tables

Every authenticated request validates `session_id` from the JWT against a session table. Sessions can be revoked individually (logout, admin action, suspicious activity).

- `platform.platform_sessions` — platform user sessions
- `<tenant>.tenant_sessions` — tenant user sessions per schema

### 6. Dependency Signature Freeze

`get_current_platform_user` and `get_current_tenant_user` signatures do **not** change when IAM ships. Only the implementations swap (stub → JWT). This is the contractual guarantee of the stub discipline — callers never need to change.

`PLATFORM_AUTH_MODE` env var controls which implementation is bound at boot:
- `stub` — current header-based stub (forbidden in `APP_ENV=production`)
- `jwt` — post-IAM JWT implementation

No per-request conditionals; the binding happens once at startup.

### 7. Cross-Context Access (Support Impersonation)

Platform users accessing tenant routes must have an active row in `platform.support_impersonations`:

```
platform.support_impersonations
  platform_user_id  UUID FK platform_users(id)
  tenant_id         UUID FK tenants(id)
  reason            text NOT NULL
  started_at        timestamptz NOT NULL
  expires_at        timestamptz NOT NULL
  revoked_at        timestamptz nullable
```

- Maker-checker required to start an impersonation session
- Max duration configurable via env (default 30 min)
- `tenant.audit_log` gains an `impersonation_id` column — every operation within an impersonation session carries this FK
- A platform user without an active, unexpired, unrevoked impersonation row is rejected on all tenant routes — no exceptions

### 8. MFA Scaffolding from Day One

- `platform_users.mfa_required` (bool, default `true` for `is_superuser=true`)
- `platform_users.mfa_methods` (JSONB, nullable — populated when MFA is configured)
- Production platform login without MFA configured is rejected for users with `mfa_required=true`
- MFA method support: TOTP (minimum), WebAuthn (stretch)

### 9. Password Handling Boundary

The `hashed_password` column exists now on `platform_users` (and will exist on `tenant_users`) but stays `null` until IAM ships. All password hashing logic lives in IAM. `platform_` never touches it.

### 10. Auth Event Audit (IAM Responsibility)

IAM emits audit records for:
- Login success / failure
- Token refresh
- Logout
- Session revocation
- Impersonation start / stop
- Account lockout

Failed login threshold triggers a configurable lockout (default: 5 attempts → 15 min lockout). Lockout state stored in Redis.

---

## Module Boundary Summary

| Concern | Owner |
|---|---|
| `platform_users` table, user CRUD, tenant CRUD, provisioning | `platform_` |
| `platform.support_impersonations` table and lifecycle | `platform_` |
| Platform login/refresh/logout, platform JWT issue | `iam` |
| Platform session management, MFA, lockout | `iam` |
| `get_current_platform_user` JWT implementation | `iam` |
| `tenant_users` table, tenant user CRUD, role assignments | `iam` |
| Tenant login/refresh/logout, tenant JWT issue | `iam` |
| Tenant session management | `iam` |
| `get_current_tenant_user` JWT implementation | `iam` |
| Password hashing (both platform and tenant) | `iam` |
| Signing key management (shared primitive) | `iam` |

---

## CLAUDE.md Additions (apply when IAM ships)

Add to the "What NOT to do" section:

```
- Do not put permissions in JWT tokens. Always resolve per-request from DB (Redis-cached).
- Do not allow cross-context (platform→tenant) access without an active platform.support_impersonations row.
```

Add a new "IAM module contracts" section:

```
## IAM module contracts (do not violate)
- Two parallel JWT systems: platform and tenant. They share signing key primitives and password hashing but issue separate tokens with separate audiences (aud=platform vs aud=tenant:<slug>).
- Permissions are never in tokens. Always resolved per-request from DB (Redis-cached, short TTL).
- Cross-context access by platform users requires an active row in platform.support_impersonations. No exceptions.
- Production refuses PLATFORM_AUTH_MODE=stub at boot (already enforced in main.py lifespan).
- Signing keys use RS256 or EdDSA. HS256 is forbidden.
- get_current_platform_user and get_current_tenant_user signatures are frozen. IAM swaps implementations only.
```

---

## Consequences

- IAM can be built independently on the current codebase — `platform_` is ready to receive it.
- `tenant.approval_requests.requested_by` has no FK target until IAM creates `tenant_users`. This gap is acceptable and documented in the platform_ spec.
- The support_impersonations table will be created in a `platform_` migration when IAM ships (it belongs to `platform_` ownership even though IAM triggers its use).
- Refresh token Redis storage adds a Redis dependency to auth. If Redis is down, refresh fails (access tokens continue working until they expire).
