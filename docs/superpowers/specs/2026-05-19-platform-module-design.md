# Platform_ Module Design

**Date:** 2026-05-19
**Module:** `platform_` (bounded context #2)
**Depends on:** core (audit, outbox, maker-checker)

---

## 1. Purpose

The `platform_` module owns two things:

1. **Tenant registry** — the `platform.tenants` table that every other subsystem references, plus an async multi-step provisioning workflow that creates a tenant's Postgres schema, runs migrations, seeds defaults, and activates the tenant.
2. **Platform users** — super-admin identities (`platform.platform_users`) that manage tenants and each other, with a stub auth dependency that exercises the full request/audit flow today and is replaced by JWT auth when the IAM module ships.

This module unblocks `get_tenant_session` (which reads `platform.tenants`) and `migrate_all_tenants.py` (which iterates active tenants on deploy).

---

## 2. Data Model

### 2.1 `platform.tenants`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID | PK, default gen_random_uuid() |
| `slug` | text | UNIQUE NOT NULL |
| `schema_name` | text | UNIQUE NOT NULL |
| `name` | text | NOT NULL |
| `status` | text | NOT NULL, CHECK IN (pending\|provisioning\|active\|suspended\|failed\|deprovisioning\|archived) |
| `is_active` | bool | NOT NULL DEFAULT false — set true only on finalize |
| `provisioning_state` | text | nullable — current step name |
| `failed_step` | text | nullable |
| `failure_reason` | text | nullable |
| `provisioning_started_at` | timestamptz | nullable |
| `provisioning_completed_at` | timestamptz | nullable |
| `seed_version` | int | NOT NULL DEFAULT 1 |
| `created_at` | timestamptz | NOT NULL DEFAULT now() |
| `updated_at` | timestamptz | NOT NULL DEFAULT now() |

`slug` must match `^[a-z0-9-]{1,40}$`. `schema_name` is derived as `tenant_<slug_with_hyphens_replaced_by_underscores>` and validated against `^tenant_[a-z0-9_]{1,40}$`. Both constraints enforced in the service layer and at the DB via UNIQUE.

`is_active` is the flag read by `get_tenant_session` (backward compatible). It is set `true` only when `status` transitions to `"active"` (finalize step). Suspension sets `is_active=false` while keeping `status="suspended"`.

### 2.2 `platform.platform_users`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID | PK, default gen_random_uuid() |
| `email` | text | UNIQUE NOT NULL |
| `full_name` | text | NOT NULL |
| `hashed_password` | text | nullable — populated by IAM |
| `is_active` | bool | NOT NULL DEFAULT true |
| `is_superuser` | bool | NOT NULL DEFAULT false |
| `created_at` | timestamptz | NOT NULL DEFAULT now() |
| `updated_at` | timestamptz | NOT NULL DEFAULT now() |
| `last_login_at` | timestamptz | nullable |

`PlatformUser` carries `AuditableMixin`. Audit entries land in `platform.audit_log` with `actor_type='platform_user'`.

### 2.3 Bootstrap seed (idempotent)

Run at the end of migration `002_platform_module.py`. If no `is_superuser=true` row exists in `platform.platform_users`, insert one using:
- `PLATFORM_BOOTSTRAP_EMAIL` env var
- `PLATFORM_BOOTSTRAP_FULL_NAME` env var
- `hashed_password=NULL` (cannot log in until IAM ships)
- `is_active=true`, `is_superuser=true`

Wrapped in `ON CONFLICT (email) DO NOTHING` and an existence check so re-running the migration is safe.

---

## 3. Alembic Migration

**File:** `alembic/platform/versions/002_platform_module.py`

Creates both tables (with indexes, CHECK constraints, FKs between `approval_requests.requested_by` and `platform_users.id`), then seeds the bootstrap superuser.

**Note on existing FK gap:** `platform.approval_requests.requested_by` and `platform.approval_actions.actor_user_id` currently have no FK target. Migration 002 adds the FK from those columns to `platform_users(id)`. The tenant equivalents (`tenant.approval_requests.requested_by`) will be FK'd to the tenant's own `users` table when the IAM module ships.

---

## 4. Provisioning Workflow

### 4.1 Steps

```
pending → [dispatch task] → provisioning
  Step 1: create_schema      provisioning_state = 'create_schema'
  Step 2: run_migrations     provisioning_state = 'run_migrations'
  Step 3: seed_defaults      provisioning_state = 'seed_defaults'
  Step 4: finalize           provisioning_state = 'finalize'
→ active (is_active=true, provisioning_completed_at=now())

On any step failure:
  status = 'failed', failed_step = '<step_name>', failure_reason = str(exc)
```

Each step:
1. Acquires advisory lock: `pg_try_advisory_lock(hashtext('provision:' || tenant_id::text))` — exits immediately (no wait) if already locked. Concurrent invocations on the same tenant are silently dropped.
2. Re-reads the tenant row inside the lock to check current state.
3. Does idempotent work.
4. Updates `provisioning_state` and commits before moving to the next step.

### 4.2 Idempotency

| Step | Idempotency mechanism |
|---|---|
| create_schema | `CREATE SCHEMA IF NOT EXISTS` |
| run_migrations | `alembic upgrade head` is naturally idempotent |
| seed_defaults | All inserts use `ON CONFLICT DO NOTHING` |
| finalize | Sets `status='active'`, `is_active=true` — idempotent on repeat |

### 4.3 Retry

`POST /platform/tenants/{id}/retry-provisioning` is valid only when `status='failed'`. It re-dispatches `provision_tenant.delay(tenant_id)`. The task resumes from `failed_step` (skips already-completed steps based on `provisioning_state`). Maker-checker required.

### 4.4 Shared Alembic helper

`app/platform_/provisioning/migrations.py` exports:

```python
def run_tenant_migrations(schema_name: str) -> None:
    """Run alembic upgrade head for a tenant schema.
    Uses alembic.command.upgrade() programmatically — no subprocess.
    Sets TENANT_SCHEMA env var that alembic/tenant/env.py reads.
    """
```

`scripts/migrate_all_tenants.py` is refactored to call this function (removing the subprocess call). Both the provisioning task and the script use the same code path.

### 4.5 Events

On success, `EventPublisher.publish()` writes to `platform.outbox_events`:
```
aggregate_type = "tenant"
aggregate_id   = tenant.id
event_type     = "TenantProvisioned"
payload        = {"slug": tenant.slug, "schema_name": tenant.schema_name, "seed_version": tenant.seed_version}
```

On failure, structured ERROR log with `tenant_id`, `slug`, `failed_step`, `failure_reason`. No failure event (retryable state; event fires on eventual success).

---

## 5. Seed Defaults

**Location:** `app/platform_/seeds/`

The `seed_defaults(session, schema_name)` function inserts into the newly provisioned tenant schema:

| Entity | Details |
|---|---|
| Chart of accounts | Standard SACCO COA: Assets (cash, member loans, shares), Liabilities (member savings, deposits), Equity (retained surplus), Income (interest, fees), Expense. Defined in `app/platform_/seeds/chart_of_accounts.py`. |
| Default roles | `admin`, `manager`, `loan_officer`, `teller`, `member_services`, `auditor`. Defined as a list — IAM module populates permissions. |
| System user | A non-human `actor_type='system'` placeholder row in the tenant users table. Used as FK for system-generated audit records before real users exist. Only inserted once IAM defines the tenant users table — **deferred to IAM module**. |
| Default fee types | `membership_fee`, `annual_subscription`. Amounts are configurable; seed sets sensible defaults. |
| Default product templates | Savings product template, share product template, loan product template (all inactive/draft status — configurable before activation). |

**Seed version:** `seed_version=1` on the tenant row marks which seed run was applied. Future seeds increment this and check before applying.

**Scope note:** Chart of accounts, roles, fee types, and product templates are seeded here even though the ledger, iam, fees, and credit modules haven't shipped yet. The seed inserts into tables that will be created by those modules' migrations. To avoid ordering issues, the seed step runs **after** `run_migrations` (which applies all tenant migrations up to head). If those tables don't exist yet, the seed runner catches `sqlalchemy.exc.ProgrammingError` (UndefinedTable) per seed entity, logs a warning, and continues — the seed_version still advances so the step is not retried unnecessarily.

---

## 6. Platform Auth Stub

### 6.1 Dependency: `app/platform_/auth.py`

```python
async def get_current_platform_user(
    x_platform_actor_id: str = Header(...),
    session: AsyncSession = Depends(get_platform_session),
) -> PlatformUser:
    """Stub: validates X-Platform-Actor-ID exists and is active.
    Does NOT authenticate — production requires PLATFORM_AUTH_MODE != 'stub'.
    """
    _log.warning("PLATFORM STUB AUTH: actor_id=%s — not production auth", x_platform_actor_id)
    # validate UUID, query platform_users, check is_active
    ...

async def get_current_superuser(
    user: PlatformUser = Depends(get_current_platform_user),
) -> PlatformUser:
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required")
    return user
```

### 6.2 Production boot guard

In `app/main.py` lifespan (before yield):
```python
if settings.app_env == "production" and settings.platform_auth_mode == "stub":
    raise RuntimeError(
        "Refusing to boot: PLATFORM_AUTH_MODE=stub is not allowed in production. "
        "Set PLATFORM_AUTH_MODE to a non-stub value when IAM ships."
    )
```

New settings fields:
- `platform_auth_mode: str = "stub"` — default stub, IAM will change
- `platform_bootstrap_email: str = ""`
- `platform_bootstrap_full_name: str = "Platform Admin"`

### 6.3 Cross-context: platform actor in tenant session

When a platform user acts within a tenant (e.g., support operations), the request carries both `X-Platform-Actor-ID` and `X-Tenant-Slug`. The middleware resolves the **tenant session first** (sets `search_path` to tenant schema), then resolves the platform actor **second** via a brief platform session. The audit entry in the **tenant's** `audit_log` carries `actor_type='platform_user'` and `actor_id=<platform_user.id>`.

This is achieved by binding structlog context vars (`actor_type`, `actor_id`) after platform actor resolution. The `AuditableMixin` reads from context vars, so no explicit wiring is needed per-endpoint.

---

## 7. API Surface

All `/platform/*` routes require `get_current_platform_user` except `GET /platform/health`.

### 7.1 Tenants

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/platform/tenants` | superuser | Validates slug uniqueness, creates row (status=pending), dispatches task, returns 202 with `status_url` |
| `GET` | `/platform/tenants` | any platform user | List with optional `status` filter |
| `GET` | `/platform/tenants/{id}` | any platform user | Full state including provisioning detail |
| `POST` | `/platform/tenants/{id}/retry-provisioning` | superuser | Maker-checker required; only valid when status=failed |

### 7.2 Platform Users

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/platform/users` | any platform user | List |
| `GET` | `/platform/users/{id}` | any platform user | Detail |
| `POST` | `/platform/users` | superuser | Maker-checker required |
| `PATCH` | `/platform/users/{id}` | superuser | Maker-checker required for `is_active`/`is_superuser` changes; not required for `full_name` |

No `/login`, `/me`, or password endpoints — those belong to IAM.

---

## 8. File Structure

```
app/platform_/
  __init__.py
  models.py                  — Tenant, PlatformUser SQLAlchemy models
  auth.py                    — get_current_platform_user, get_current_superuser
  seeds/
    __init__.py
    chart_of_accounts.py     — COA seed data
    defaults.py              — roles, fee types, product templates seed data
    runner.py                — seed_defaults(session, schema_name) orchestrator
  provisioning/
    __init__.py
    steps.py                 — create_schema_step, run_migrations_step, seed_defaults_step, finalize_step
    tasks.py                 — provision_tenant Celery task
    migrations.py            — run_tenant_migrations(schema_name) shared helper
  tenants/
    __init__.py
    schemas.py
    service.py               — TenantService: create, get, list, retry_provisioning
    api.py                   — /platform/tenants router
  users/
    __init__.py
    schemas.py
    service.py               — PlatformUserService: create, get, list, update
    api.py                   — /platform/users router

alembic/platform/versions/
  002_platform_module.py     — creates tenants, platform_users; seeds bootstrap superuser; adds FKs

scripts/
  migrate_all_tenants.py     — refactored to use run_tenant_migrations() directly

tests/platform_/
  __init__.py
  test_provisioning.py       — step idempotency, state transitions, failure injection, retry, advisory lock
  test_auth.py               — stub dependency: missing header, unknown ID, inactive, non-superuser, prod boot guard
  test_tenants_api.py        — POST /platform/tenants, GET, retry-provisioning
  test_users_api.py          — CRUD for platform users
```

---

## 9. Testing Requirements

### Provisioning
- Each step is idempotent (run twice, second is a no-op)
- State transitions correct: pending → provisioning → active
- Injected failure at each step leaves status=failed with correct failed_step
- Retry resumes from failed_step, not from start
- Advisory lock prevents concurrent execution (two tasks on same tenant, only one proceeds)
- Slug uniqueness enforced at API layer (unique constraint raises 409)

### Auth stub
- Rejects missing `X-Platform-Actor-ID` header (422)
- Rejects unknown actor UUID (401)
- Rejects inactive user (403)
- Rejects non-superuser when route requires superuser (403)
- Prod boot guard: `app_env=production` + `platform_auth_mode=stub` → RuntimeError on startup
- Cross-context: platform actor in tenant session writes `actor_type='platform_user'` to tenant audit_log

### Bootstrap seed
- Idempotent: running migration 002 twice inserts only one bootstrap user

---

## 10. CLAUDE.md Additions

```
## Platform_ module contracts (do not violate)
- Tenant provisioning is asynchronous. POST /platform/tenants returns 202 with a status_url. Clients poll. Direct schema creation outside the provisioning workflow is forbidden.
- Platform auth is a stub. get_current_platform_user validates X-Platform-Actor-ID against platform.platform_users but does NOT authenticate. Production deployment requires PLATFORM_AUTH_MODE != stub.
- Do not add password handling, login routes, or /me endpoints to platform_. Those belong in IAM.
- Platform users acting inside a tenant context send both X-Platform-Actor-ID and X-Tenant-Slug. Audit records actor_type='platform_user' and actor_id=<platform_user.id> in the tenant audit_log.
```

---

## 11. Config / Environment Variables

New additions to `app/core/config.py` and `.env.example`:

```
PLATFORM_AUTH_MODE=stub           # change to 'jwt' when IAM lands
PLATFORM_BOOTSTRAP_EMAIL=admin@example.com
PLATFORM_BOOTSTRAP_FULL_NAME=Platform Admin
APP_ENV=development               # set to 'production' in prod
```

`APP_ENV` already exists as `app_env` in Settings; `PLATFORM_AUTH_MODE`, `PLATFORM_BOOTSTRAP_EMAIL`, `PLATFORM_BOOTSTRAP_FULL_NAME` are new.
