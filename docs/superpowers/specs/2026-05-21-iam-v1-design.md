# IAM v1 Design

**Date:** 2026-05-21
**Module:** `app/modules/iam/`
**Bounded context:** #3 (after core, platform_)
**ADR:** `docs/superpowers/decisions/2026-05-21-iam-architecture.md`
**Depends on:** core (audit, outbox, maker-checker), platform_ (platform_users, tenants)

---

## 1. Scope

### In scope (v1)

- Asymmetric JWT signing: RS256 or EdDSA, `kid` registry, key lifecycle, rotation API and beat job
- Envelope encryption of private keys (AES-256-GCM, KEK from env)
- Password hashing (argon2id via passlib)
- `platform.platform_sessions` and `<tenant>.tenant_sessions` tables + session service
- `<tenant>.tenant_users` table + bootstrap seed during tenant provisioning
- Platform auth endpoints: `POST /platform/auth/token`, `/refresh`, `/logout`, `GET /platform/auth/me`
- Tenant auth endpoints: `POST /auth/token`, `/refresh`, `/logout`, `GET /auth/me` (tenant resolved via `X-Tenant-Slug`)
- Password reset flow (request + confirm) for both platform and tenant users
- Real implementations of `get_current_platform_user` and `get_current_tenant_user` replacing the stub
- Account lockout: configurable failed-attempt threshold, window, and duration — stored in Redis
- Audit records on every auth event
- `PLATFORM_AUTH_MODE` and `TENANT_AUTH_MODE` wired into production boot check

### Out of scope (IAM v2)

- Roles and permissions tables / resolution
- MFA (TOTP / WebAuthn)
- Support impersonation
- Self-service registration
- SSO / OIDC
- API keys / service accounts
- Password complexity policies beyond minimum length

**Interim gating:** Downstream modules requiring authorization check `is_superuser` (platform) or `is_admin` (tenant) directly. v2 layers a permission system on top; these flags remain as "implies all permissions" until explicitly downgraded.

---

## 2. Module Layout

```
app/modules/iam/
├── __init__.py
├── keys/
│   ├── __init__.py
│   ├── models.py          # JwtSigningKey (platform table)
│   ├── crypto.py          # AES-256-GCM encrypt/decrypt, KEK validation
│   ├── service.py         # KeyService: get_active, get_verification, rotate, advance_lifecycle
│   ├── schemas.py         # JwtKeyOut, RotateRequest
│   └── api.py             # /platform/jwt-keys/* + /.well-known/jwks.json
├── tokens/
│   ├── __init__.py
│   └── service.py         # encode_token, decode_token, claim validation
├── passwords/
│   ├── __init__.py
│   └── service.py         # hash_password, verify_password (argon2id via passlib)
├── sessions/
│   ├── __init__.py
│   ├── models.py          # PlatformSession, TenantSession
│   └── service.py         # SessionService: create, get, revoke, cleanup
├── platform_auth/
│   ├── __init__.py
│   ├── schemas.py
│   ├── service.py         # PlatformAuthService: login, refresh, logout, me, reset_request, reset_confirm
│   └── api.py             # /platform/auth/*
├── tenant_auth/
│   ├── __init__.py
│   ├── schemas.py
│   ├── service.py         # TenantAuthService: login, refresh, logout, me, reset_request, reset_confirm
│   └── api.py             # /auth/*
├── tenant_users/
│   ├── __init__.py
│   ├── models.py          # TenantUser (no schema — resolved via search_path)
│   └── service.py         # TenantUserService: create, get, list, update
├── dependencies.py        # Real implementations of get_current_platform_user, get_current_tenant_user
├── lockout.py             # Redis-backed lockout: record_attempt, is_locked, reset
└── beat.py                # Celery beat task definitions: rotate_signing_keys_if_due, advance_key_lifecycle
```

---

## 3. Data Model

### 3.1 `platform.jwt_signing_keys`

Platform table (schema="platform"), carries `AuditableMixin`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `kid` | TEXT UNIQUE NOT NULL | e.g. `platform-2026-001` |
| `algorithm` | TEXT NOT NULL | `'RS256'` or `'EdDSA'` |
| `audience` | TEXT NOT NULL | `'platform'` or `'tenant'` |
| `public_key` | TEXT NOT NULL | PEM plaintext — safe to store/log |
| `private_key_encrypted` | BYTEA NOT NULL | AES-256-GCM ciphertext |
| `private_key_nonce` | BYTEA NOT NULL | 12 bytes |
| `private_key_tag` | BYTEA NOT NULL | 16 bytes (GCM auth tag) |
| `status` | TEXT NOT NULL | `'active'` \| `'retiring'` \| `'retired'` |
| `created_at` | timestamptz NOT NULL | |
| `activated_at` | timestamptz | nullable |
| `retired_at` | timestamptz | nullable |
| `deleted_at` | timestamptz | nullable |
| `created_by` | UUID FK `platform_users(id)` | nullable — null for system-generated |
| `notes` | TEXT | nullable |

**Indexes:**
- `UNIQUE` partial index: `WHERE status = 'active'` per `audience` — enforces at most one active key per audience at the DB level.

**Lifecycle transitions:**
```
active → retiring  (new key promoted; old starts retiring)
retiring → retired (after max_token_lifetime + 1h: access_ttl=15m, so 1h 15m minimum)
retired  → deleted (after 7-day buffer — soft delete via deleted_at)
```
Lifecycle advancement driven by `advance_key_lifecycle` beat job (hourly).

### 3.2 `platform.platform_sessions`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK (= `session_id` in JWT) | |
| `platform_user_id` | UUID FK `platform_users(id)` NOT NULL | |
| `jti` | TEXT UNIQUE NOT NULL | refresh token `jti` |
| `user_agent` | TEXT | nullable |
| `ip_address` | TEXT | nullable |
| `created_at` | timestamptz NOT NULL | |
| `expires_at` | timestamptz NOT NULL | created_at + refresh TTL |
| `revoked_at` | timestamptz | nullable — set on logout or admin revocation |
| `last_used_at` | timestamptz | updated on each successful refresh |

### 3.3 `<tenant>.tenant_sessions`

Same schema as `platform_sessions` but `tenant_user_id` (FK `tenant_users(id)`) instead of `platform_user_id`. Lives in tenant schema (no explicit schema= in `__table_args__`).

### 3.4 `<tenant>.tenant_users`

Lives in tenant schema (no explicit schema=).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `email` | TEXT UNIQUE NOT NULL | |
| `full_name` | TEXT NOT NULL | |
| `hashed_password` | TEXT | nullable — null until user sets password via reset flow |
| `is_active` | BOOL NOT NULL DEFAULT true | |
| `is_admin` | BOOL NOT NULL DEFAULT false | coarse gating until v2 permission system |
| `created_at` | timestamptz NOT NULL | |
| `updated_at` | timestamptz NOT NULL | |
| `last_login_at` | timestamptz | nullable |

`TenantUser` carries `AuditableMixin`. Audit entries land in the tenant's `audit_log` with `actor_type='tenant_user'`.

### 3.5 Bootstrap Seed Changes

The existing `provision_tenant` task's step 3 (`seed_defaults`) is extended to accept an optional `admin_email` payload key. If present:

1. Insert into `tenant_users` (email=admin_email, full_name="Admin", is_admin=true, hashed_password=null) using `ON CONFLICT (email) DO NOTHING`.
2. Trigger a password reset email (or log the reset token if email not configured) so the user can activate their account.

The provisioning task payload schema gains an optional `admin_email` field. `CreateTenantRequest` schema gains the same optional field, passed through to `provision_tenant.delay(...)` call.

---

## 4. JWT Infrastructure

### 4.1 Envelope Encryption

**File:** `app/modules/iam/keys/crypto.py`

- `encrypt_private_key(pem: bytes, kek: bytes) -> (ciphertext, nonce, tag)` — AES-256-GCM, random 12-byte nonce
- `decrypt_private_key(ciphertext, nonce, tag, kek: bytes) -> bytes` — raises `ValueError` on auth tag failure
- `validate_kek(kek_b64: str) -> bytes` — base64-decode, assert exactly 32 bytes
- Uses `cryptography` (pyca) library

**KEK source:** `settings.jwt_kek` — base64-encoded 32-byte value from env var `JWT_KEK`.

### 4.2 KeyService

**File:** `app/modules/iam/keys/service.py`

- `get_active_signing_key(audience) -> (kid, private_key, algorithm)` — in-process LRU cache (TTL 60s), decrypts with KEK on miss
- `get_verification_key(kid) -> (public_key, algorithm, audience)` — in-process LRU cache (TTL 60s); returns retiring keys too; rejects retired/deleted
- `rotate(audience, actor_id) -> JwtSigningKey` — generates new keypair, encrypts, inserts as active, sets prior active to retiring, emits audit; requires maker-checker wrapper at API layer
- `advance_lifecycle(now) -> dict` — promotes retiring→retired, retired→deleted based on configured thresholds

### 4.3 Token Service

**File:** `app/modules/iam/tokens/service.py`

- `encode_access_token(sub, audience, session_id, actor_type, kid, private_key, algorithm, ttl) -> str`
- `encode_refresh_token(sub, audience, session_id, kid, private_key, algorithm, ttl) -> str`
- `decode_token(token, audience, key_service) -> claims` — validates signature, expiry, `aud` matches key's audience column (defense in depth), returns claims dict
- Claims: `sub`, `aud`, `iat`, `exp`, `jti`, `kid`, `actor_type`, `session_id`
- Uses `python-jose` (or `PyJWT`) — decision: **PyJWT** (lighter, well-maintained)

### 4.4 Boot Check

Added to `app/main.py` lifespan — after existing stub check:

```python
if settings.platform_auth_mode == "jwt":
    from app.modules.iam.keys.service import verify_boot_keys
    await verify_boot_keys()  # raises RuntimeError if KEK invalid or no active key per audience
```

Also: `JWT_KEK` validated on settings load (`@validator`) — fail fast before DB connection attempt.

### 4.5 JWKS Endpoint

`GET /.well-known/jwks.json` — public, no auth. Returns active and retiring public keys in JWK Set format. Used by external verifiers (future API gateway, mobile app). Cached in-process (TTL 60s), refreshed on key rotation event.

---

## 5. Password Hashing

**File:** `app/modules/iam/passwords/service.py`

- `hash_password(plain: str) -> str` — argon2id, memory=64MB, time=3, parallelism=4 (OWASP recommended for server-side)
- `verify_password(plain: str, hashed: str) -> bool` — constant-time compare
- `needs_rehash(hashed: str) -> bool` — returns True if parameters have changed; called on login success to transparently upgrade

Uses `passlib[argon2]` (`pip install passlib[argon2]`). Falls back gracefully if `argon2-cffi` not installed (test environments can opt out).

Minimum password length: 12 characters (config: `AUTH_PASSWORD_MIN_LENGTH=12`). No complexity rules beyond length in v1.

---

## 6. Session Service

**File:** `app/modules/iam/sessions/service.py`

`SessionService(session: AsyncSession)` — initialized with the appropriate session (platform or tenant).

- `create(user_id, jti, user_agent, ip, refresh_ttl) -> session_row`
- `get_by_session_id(session_id) -> row | None`
- `revoke(session_id)` — sets `revoked_at`
- `revoke_all_for_user(user_id)` — bulk revoke on password change / admin action
- `cleanup_expired()` — called by beat job, deletes rows where `expires_at < now() - 7d`

---

## 7. Auth Endpoints

### 7.1 Platform Auth (`/platform/auth/`)

All endpoints use `get_platform_session` (platform schema). No tenant slug header required.

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/platform/auth/token` | none | `{email, password}` | `{access_token, refresh_token, token_type, expires_in}` |
| POST | `/platform/auth/refresh` | none | `{refresh_token}` | `{access_token, token_type, expires_in}` |
| POST | `/platform/auth/logout` | Bearer access token | — | 204 |
| GET | `/platform/auth/me` | Bearer access token | — | `PlatformUserOut` |
| POST | `/platform/auth/password-reset/request` | none | `{email}` | 204 (always, no user enumeration) |
| POST | `/platform/auth/password-reset/confirm` | none | `{token, new_password}` | 204 |

**Login flow:**
1. Look up `PlatformUser` by email. If not found or `is_active=False`: record lockout attempt, return 401.
2. Check lockout: if locked, return 423 with `retry_after`.
3. Verify password. If wrong: record attempt, possibly trigger lockout, return 401.
4. Rehash if needed (transparent upgrade).
5. Create `PlatformSession` row.
6. Issue access token (15m) + refresh token (1h).
7. Store refresh token `jti` on session row.
8. Audit: `platform_auth.login_success`.
9. Clear failed-attempt counter in Redis.

**Refresh flow:**
1. Decode refresh token (allow expired access token, but refresh must be valid).
2. Look up session by `session_id`. Must be non-revoked, non-expired.
3. Verify `jti` matches session row's stored `jti`.
4. Issue new access token. Update `last_used_at`.
5. Audit: `platform_auth.refresh`.

**Logout:** Revoke session row. Audit: `platform_auth.logout`.

**Password reset request:**
1. Look up user by email — always return 204 regardless.
2. If found: generate HMAC-signed reset token (sub=user_id, exp=15m), store `jti` in Redis.
3. Log reset token to structlog (prod: send email instead — pluggable notifier interface).
4. Audit: `platform_auth.password_reset_requested`.

**Password reset confirm:**
1. Verify HMAC token, check Redis jti not consumed.
2. Validate new password (min length).
3. Hash and save. Consume Redis jti. Revoke all sessions for user.
4. Audit: `platform_auth.password_reset_confirmed`.

### 7.2 Tenant Auth (`/auth/`)

Same flow as platform auth. Uses `get_tenant_session` (resolves tenant from `X-Tenant-Slug`). Operates on `TenantUser` and `TenantSession` tables. Refresh TTL is 8h.

| Method | Path |
|---|---|
| POST | `/auth/token` |
| POST | `/auth/refresh` |
| POST | `/auth/logout` |
| GET | `/auth/me` |
| POST | `/auth/password-reset/request` |
| POST | `/auth/password-reset/confirm` |

---

## 8. Dependency Implementations

**File:** `app/modules/iam/dependencies.py`

Replaces stub implementations in `app/platform_/auth.py` and introduces the tenant equivalent.

```python
async def get_current_platform_user_jwt(
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_platform_session),
) -> PlatformUser:
    token = _extract_bearer(authorization)
    claims = decode_token(token, audience="platform", key_service=key_service)
    session_row = await SessionService(session).get_by_session_id(claims["session_id"])
    if session_row is None or session_row.revoked_at is not None:
        raise HTTPException(401, "Session revoked or not found")
    # ... return user


async def get_current_tenant_user(
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_tenant_session),
) -> TenantUser:
    token = _extract_bearer(authorization)
    claims = decode_token(token, audience=f"tenant:{slug}", key_service=key_service)
    # ... validate session, return user
```

**Wiring:** `PLATFORM_AUTH_MODE` env var selects which implementation is bound in `app/platform_/auth.py` at module load time (import-time switch, not per-request conditional). When `jwt`, the stub body is replaced by delegation to `app.modules.iam.dependencies`.

---

## 9. Account Lockout

**File:** `app/modules/iam/lockout.py`

Redis-backed. No DB writes for lockout state — Redis TTLs handle expiry automatically.

```
Key: iam:lockout:{audience}:{email}    → failed attempt count (INCR + EXPIRE)
Key: iam:locked:{audience}:{email}     → set on lockout (TTL = lockout_duration)
```

- `record_attempt(audience, email)` — INCR attempt key, EXPIRE to window. If count >= threshold: set locked key, audit lockout event.
- `is_locked(audience, email) -> bool` — check locked key existence.
- `reset(audience, email)` — DEL both keys (called on successful login).

Config (all from `app/core/config.py`):
- `AUTH_LOCKOUT_THRESHOLD=5`
- `AUTH_LOCKOUT_WINDOW_MINUTES=15`
- `AUTH_LOCKOUT_DURATION_MINUTES=30`

---

## 10. Audit Events

All auth audit records written to `PlatformAuditService` (platform events) or `TenantAuditService` (tenant events) within the same transaction.

| Event type | Audience | Data fields |
|---|---|---|
| `platform_auth.login_success` | platform | user_id, ip, user_agent |
| `platform_auth.login_failure` | platform | email, reason, ip |
| `platform_auth.refresh` | platform | session_id |
| `platform_auth.logout` | platform | session_id |
| `platform_auth.lockout_triggered` | platform | email, attempt_count |
| `platform_auth.password_reset_requested` | platform | email |
| `platform_auth.password_reset_confirmed` | platform | user_id |
| `tenant_auth.login_success` | tenant | user_id, ip, user_agent |
| `tenant_auth.login_failure` | tenant | email, reason, ip |
| `tenant_auth.refresh` | tenant | session_id |
| `tenant_auth.logout` | tenant | session_id |
| `tenant_auth.lockout_triggered` | tenant | email, attempt_count |
| `tenant_auth.password_reset_requested` | tenant | email |
| `tenant_auth.password_reset_confirmed` | tenant | user_id |
| `iam.key_rotated` | platform | audience, old_kid, new_kid, actor_id |
| `iam.key_lifecycle_advanced` | platform | kid, old_status, new_status |

---

## 11. Celery Beat Jobs

**File:** `app/modules/iam/beat.py`

- `rotate_signing_keys_if_due` — runs daily. For each audience: if active key age > `JWT_KEY_ROTATION_DAYS`, call `KeyService.rotate`. Configurable threshold.
- `advance_key_lifecycle` — runs hourly. Calls `KeyService.advance_lifecycle(now)`. Promotes retiring→retired→deleted per age thresholds.
- `cleanup_sessions` — runs daily. Calls `SessionService.cleanup_expired()` for both platform and tenant schemas.

Added to `app/workers/celery_app.py` `include` list: `"app.modules.iam.beat"`.

---

## 12. Configuration Additions

New settings in `app/core/config.py`:

```python
# JWT
jwt_kek: str  # base64 32 bytes — validated at startup
jwt_key_rotation_days: int = 90
jwt_access_ttl_seconds: int = 900        # 15 min
jwt_refresh_ttl_platform_seconds: int = 3600    # 1h
jwt_refresh_ttl_tenant_seconds: int = 28800     # 8h

# Auth mode (one implementation bound at boot)
platform_auth_mode: str = "stub"   # "stub" | "jwt"
tenant_auth_mode: str = "stub"     # "stub" | "jwt"

# Lockout
auth_lockout_threshold: int = 5
auth_lockout_window_minutes: int = 15
auth_lockout_duration_minutes: int = 30

# Password
auth_password_min_length: int = 12
```

`.env.example` additions:
```
JWT_KEK=<base64 32 bytes — generate: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())">
JWT_KEY_ROTATION_DAYS=90
JWT_ACCESS_TTL_SECONDS=900
JWT_REFRESH_TTL_PLATFORM_SECONDS=3600
JWT_REFRESH_TTL_TENANT_SECONDS=28800
TENANT_AUTH_MODE=stub
AUTH_LOCKOUT_THRESHOLD=5
AUTH_LOCKOUT_WINDOW_MINUTES=15
AUTH_LOCKOUT_DURATION_MINUTES=30
AUTH_PASSWORD_MIN_LENGTH=12
```

---

## 13. Migrations

### Platform migration `003_iam_platform.py`

Creates:
- `platform.jwt_signing_keys` (with partial unique index)
- `platform.platform_sessions`

Bootstrap: generates initial keypair per audience (platform + tenant), encrypts with KEK, inserts as active. Migration fails if `JWT_KEK` not set or invalid length.

### Tenant migration `001_iam_tenant.py`

Creates:
- `tenant_users`
- `tenant_sessions`

Also adds `impersonation_id` column stub to `audit_log` (nullable UUID, no FK until impersonation table exists in v2).

---

## 14. Dependency Additions

```
passlib[argon2]    # password hashing
PyJWT              # JWT encode/decode
cryptography       # AES-GCM for envelope encryption (already a transitive dep — make explicit)
```

---

## 15. CLAUDE.md Additions (apply now)

```
## IAM module contracts (do not violate)
- JWT signing keys live in platform.jwt_signing_keys, encrypted with KEK from JWT_KEK env var (envelope encryption).
- Separate signing keys per audience (platform vs tenant). Verifying code must match aud claim against the resolved key's audience column.
- Direct access to jwt_signing_keys table outside app/modules/iam/keys/ is forbidden. Use KeyService.
- Never log KEKs, private keys, or full JWTs. structlog mask processor enforces this at app startup.
- Permissions are never in tokens. Always resolved per-request from DB (Redis-cached, short TTL).
- get_current_platform_user and get_current_tenant_user signatures are frozen. IAM swaps implementations only — callers never change.
- Runbook for KEK loss: documented at docs/runbooks/kek-recovery.md (write when IAM v1 ships).
```

---

## 16. Test Coverage Plan

| Area | Tests |
|---|---|
| `crypto.py` | encrypt/decrypt round-trip; wrong KEK raises; nonce uniqueness per call |
| `keys/service.py` | generate keypair; rotation creates new active, demotes prior; verification accepts retiring, rejects retired; aud mismatch rejects |
| `keys/api.py` | JWKS returns active+retiring; rotation requires superuser; list requires superuser |
| `tokens/service.py` | encode/decode round-trip RS256 and EdDSA; expired token raises; wrong aud raises; tampered token raises |
| `passwords/service.py` | hash is non-deterministic; verify correct; verify wrong; needs_rehash detects stale params |
| `sessions/service.py` | create; get; revoke; revoked session rejects; expired session rejects; cleanup_expired |
| `platform_auth/service.py` | login success; wrong password increments lockout; locked account returns 423; refresh success; refresh revoked session fails; logout revokes session; password reset full flow |
| `tenant_auth/service.py` | same set as platform_auth |
| `lockout.py` | threshold triggers lock; lock expires after duration; reset clears |
| `dependencies.py` | valid token returns user; expired token raises 401; revoked session raises 401; wrong audience raises 401 |
| Boot check | missing KEK refuses start; wrong length KEK refuses start; no active key refuses start |
| Bootstrap migration | idempotent (double-run is safe) |

---

## 17. Implementation Order

Steps are independent enough to parallelize some, but session depends on keys+tokens, auth depends on sessions+passwords.

1. JWT infrastructure: `keys/` (crypto, model, service) + `tokens/service.py`
2. Password hashing: `passwords/service.py`
3. Sessions: `sessions/models.py` + `sessions/service.py`
4. Platform migration 003 (jwt_signing_keys + platform_sessions)
5. Tenant migration 001 (tenant_users + tenant_sessions)
6. `tenant_users/models.py` + `tenant_users/service.py` + bootstrap seed changes
7. Platform auth service + endpoints (`/platform/auth/*`)
8. Tenant auth service + endpoints (`/auth/*`)
9. `/me` endpoints (both)
10. Password reset flow (both)
11. Lockout (`lockout.py`) — wired into login flow
12. Audit events (wired throughout — mostly already inline above)
13. `dependencies.py` — real implementations; swap stubs
14. Beat jobs (`beat.py`); add to celery include
15. Boot check additions; wire `PLATFORM_AUTH_MODE`/`TENANT_AUTH_MODE`
16. CLAUDE.md + `.env.example` updates; full suite run
