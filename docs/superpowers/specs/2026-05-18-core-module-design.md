# Core Module Design

**Date:** 2026-05-18
**Status:** Approved
**Scope:** Bounded context #1 — cross-cutting infrastructure: audit log, outbox, maker-checker

---

## 1. Overview

This document specifies the core module: the foundational infrastructure that every subsequent bounded context depends on. Nothing here is domain-specific; these are the rails every module runs on.

Three subsystems:

1. **Audit log** — append-only record of every sensitive state change, with before/after JSON and actor context.
2. **Outbox** — transactional event relay to RabbitMQ. The only permitted path for cross-module events.
3. **Maker-checker** — approval workflow framework for sensitive operations (loan approvals, reversals, GL entries, fee waivers, member status changes).

All three follow the dual-table pattern: identical structure in both `platform` schema and each `tenant_*` schema. The session you hold determines which table you write to — no runtime schema routing.

---

## 2. File Structure

```
app/core/
  config.py                   # existing
  db.py                       # existing
  audit/
    __init__.py               # re-exports: AuditableMixin, PlatformAuditService, TenantAuditService
    mixin.py                  # AuditableMixin (SQLAlchemy event hooks)
    models.py                 # PlatformAuditLog, TenantAuditLog
    service.py                # PlatformAuditService, TenantAuditService
  outbox/
    __init__.py               # re-exports: EventPublisher
    models.py                 # PlatformOutboxEvent, TenantOutboxEvent
    publisher.py              # EventPublisher.publish()
    worker.py                 # Celery tasks: relay_platform_outbox, relay_tenant_outbox
    retention.py              # Celery beat: purge published rows older than OUTBOX_RETENTION_DAYS

app/modules/maker_checker/
  __init__.py
  models/
    __init__.py               # re-exports all models
    mixins.py                 # ApprovalRequestMixin, ApprovalActionMixin
    platform.py               # PlatformApprovalRequest, PlatformApprovalAction
    tenant.py                 # TenantApprovalRequest, TenantApprovalAction
  schemas.py                  # Pydantic request/response schemas
  service.py                  # ApprovalService
  registry.py                 # approval_registry, @approval_executor decorator
  api.py                      # FastAPI router

alembic/platform/versions/
  001_core_platform.py        # platform schema: audit_log, outbox_events,
                              #   approval_requests, approval_actions, processed_events

alembic/tenant/versions/
  001_core_tenant.py          # tenant schema: same five tables, no schema prefix

tests/core/
  audit/
    test_audit_mixin.py       # mixin auto-routing, cross-context actor_type
    test_audit_service.py
  outbox/
    test_publisher.py
    test_worker.py            # concurrent SKIP LOCKED, backoff, dead-lettering
    test_retention.py

tests/modules/
  maker_checker/
    test_service.py
    test_registry.py
    test_api.py
```

---

## 3. Audit Log

### 3.1 Tables (platform and tenant, identical columns)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` default |
| `table_name` | TEXT NOT NULL | e.g. `"loans"` |
| `record_id` | UUID NOT NULL | PK of the audited row |
| `operation` | TEXT NOT NULL | `insert \| update \| delete` |
| `actor_type` | TEXT NOT NULL | `platform_user \| tenant_user \| system \| api_client` |
| `actor_id` | UUID NULLABLE | NULL for `system` |
| `actor_label` | TEXT NULLABLE | Display name / API client ID snapshot |
| `before_state` | JSONB NULLABLE | NULL on insert |
| `after_state` | JSONB NULLABLE | NULL on delete |
| `occurred_at` | TIMESTAMPTZ NOT NULL | `now()` default |
| `request_id` | TEXT NULLABLE | From structlog context |

Index: `(table_name, record_id)`, `(occurred_at DESC)`.
No updates, no deletes — append-only enforced at application layer and documented in CLAUDE.md.

### 3.2 SQLAlchemy models

`_AuditLogBase` mixin defines all columns. `PlatformAuditLog` adds `__table_args__ = {"schema": "platform"}`. `TenantAuditLog` declares no schema (resolved by `search_path`).

Both inherit from `app.core.db.Base`.

### 3.3 AuditableMixin

A SQLAlchemy `MapperEvents`-based mixin. Consuming models declare:

```python
class Loan(Base, AuditableMixin):
    ...
```

`AuditableMixin` registers `after_insert`, `after_update`, `after_delete` listeners. On each event it:

1. Snapshots the row's `__dict__` (stripping SQLAlchemy internals) as `after_state` (or `before_state` for deletes).
2. Reads `actor_type`, `actor_id`, `actor_label`, `request_id` from structlog context vars (set by request middleware).
3. Calls the bound session's `add()` with the appropriate model — if the target model's `__table_args__` contains `schema="platform"`, it adds a `PlatformAuditLog` row; otherwise it adds a `TenantAuditLog` row.

This means a platform admin acting inside a tenant (via `get_tenant_session`) naturally writes to the tenant's `audit_log` with `actor_type='platform_user'` — the session's `search_path` is the determinant, not the actor.

**Opt-out:** Models that should not be audited (e.g. `outbox_events` itself) simply do not mix in `AuditableMixin`.

### 3.4 Services

`PlatformAuditService` and `TenantAuditService` are thin wrappers for manual audit writes (cases where the mixin isn't sufficient, e.g. bulk operations or service-level events with no model row):

```python
await platform_audit_service.record(
    table_name="tenants",
    record_id=tenant_id,
    operation="update",
    actor_type="platform_user",
    actor_id=actor_id,
    before_state={...},
    after_state={...},
)
```

Both services take their respective `AsyncSession` in the constructor. No polymorphic dispatch.

---

## 4. Outbox

### 4.1 Tables (platform and tenant, identical columns)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` default |
| `aggregate_type` | TEXT NOT NULL | e.g. `"loan"` |
| `aggregate_id` | UUID NOT NULL | |
| `event_type` | TEXT NOT NULL | e.g. `"LoanDisbursed"` |
| `payload` | JSONB NOT NULL | |
| `occurred_at` | TIMESTAMPTZ NOT NULL | `now()` default |
| `published_at` | TIMESTAMPTZ NULLABLE | Set after RabbitMQ confirm |
| `attempts` | INT NOT NULL DEFAULT 0 | |
| `last_error` | TEXT NULLABLE | |
| `next_attempt_at` | TIMESTAMPTZ NULLABLE | NULL = eligible immediately |
| `is_dead_lettered` | BOOLEAN NOT NULL DEFAULT false | |

Partial index: `(next_attempt_at) WHERE published_at IS NULL AND is_dead_lettered = false`.

### 4.2 processed_events (platform and tenant, identical)

| Column | Type | Notes |
|---|---|---|
| `event_id` | UUID NOT NULL | |
| `consumer_name` | TEXT NOT NULL | |
| `processed_at` | TIMESTAMPTZ NOT NULL | `now()` default |

PK: `(event_id, consumer_name)`. Consumers `INSERT ... ON CONFLICT DO NOTHING` and skip if 0 rows inserted.

### 4.3 EventPublisher

`EventPublisher.publish(session, aggregate_type, aggregate_id, event_type, payload)` — writes one row to `outbox_events` in the **caller's session transaction**. This is the only permitted event emission path. The row is committed or rolled back with the business transaction — no two-phase commit needed.

```python
# Inside a service method, within an open session:
await EventPublisher.publish(
    session=session,
    aggregate_type="loan",
    aggregate_id=loan.id,
    event_type="LoanDisbursed",
    payload={"amount": 500000, "currency": "UGX"},
)
```

`EventPublisher` detects which table to write to by inspecting the session's `search_path` context — it uses `PlatformOutboxEvent` if the session is a platform session, `TenantOutboxEvent` otherwise. Platform sessions are identified by a flag set in `get_platform_session()`.

### 4.4 Celery relay workers

**`relay_platform_outbox`** (platform context):

```
loop until drained or 30s wall clock, max 1000 rows total:
  SELECT ... FOR UPDATE SKIP LOCKED LIMIT 100
    WHERE published_at IS NULL
      AND is_dead_lettered = false
      AND (next_attempt_at IS NULL OR next_attempt_at <= now())
    ORDER BY occurred_at
  for each row:
    publish to RabbitMQ topic exchange sacco.events
      routing key: platform.<aggregate_type>.<event_type>
      delivery_mode=2 (persistent), await publisher confirm
    UPDATE attempts=attempts+1, published_at=now()
  commit
```

On any publish failure: `attempts += 1`, `last_error = str(exc)`, `next_attempt_at = now() + min(30s * 2^attempts, 3600s)`. If `attempts >= 10`: `is_dead_lettered = true`, emit a structlog `error` with metric tag `outbox.dead_lettered`.

**`relay_tenant_outbox`** — same logic but iterates active tenants. Each tenant runs in its own `tenant_context()` (sets `search_path`). A failure in one tenant's loop logs the error and continues to the next tenant.

**Beat schedule:** both tasks every 5 seconds.

**`purge_outbox_retention`** — monthly beat task, deletes `published_at < now() - OUTBOX_RETENTION_DAYS days` (default 90, configurable via settings).

### 4.5 RabbitMQ topology

- Exchange: `sacco.events`, type `topic`, durable.
- Routing key: `<context>.<aggregate_type>.<event_type>` where `<context>` is `platform` or the tenant slug.
- All messages: `delivery_mode=2` (persistent), publisher confirms enabled.

### 4.6 Observability

Structlog on every publish: `event_id`, `event_type`, `context`, `latency_ms`.
Metrics (structlog key-value for now, Prometheus-compatible labels): `outbox.backlog` (gauge per context), `outbox.publish_success` / `outbox.publish_failure` (counters), `outbox.publish_latency_ms` (histogram).

### 4.7 CI lint rule

A `rg` step in the lint workflow fails if `pika`, `aio_pika`, or `kombu` is imported outside `app/core/outbox/`:

```bash
rg "import (pika|aio_pika|kombu)" --glob "**/*.py" \
  --glob "!app/core/outbox/**" && exit 1 || exit 0
```

---

## 5. Maker-Checker

### 5.1 approval_requests table (platform and tenant)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `operation_type` | TEXT NOT NULL | e.g. `"loan.approve"`, `"gl.manual_entry"` |
| `payload` | JSONB NOT NULL | Full context for executor |
| `requested_by` | UUID NOT NULL | actor_id of maker |
| `requested_at` | TIMESTAMPTZ NOT NULL | `now()` default |
| `required_approvals` | INT NOT NULL DEFAULT 1 | Set by caller |
| `status` | TEXT NOT NULL | `pending\|approved\|rejected\|executed\|execution_failed\|expired\|cancelled` |
| `expires_at` | TIMESTAMPTZ NULLABLE | |
| `executed_at` | TIMESTAMPTZ NULLABLE | |
| `execution_result` | JSONB NULLABLE | |
| `rejection_reason` | TEXT NULLABLE | |

### 5.2 approval_actions table (platform and tenant)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `approval_request_id` | UUID FK → approval_requests.id | |
| `actor_user_id` | UUID NOT NULL | |
| `action` | TEXT NOT NULL | `approve \| reject` |
| `acted_at` | TIMESTAMPTZ NOT NULL | `now()` default |
| `comment` | TEXT NULLABLE | |

Unique constraint: `(approval_request_id, actor_user_id)` — no double-voting.
DB trigger (both schemas): `actor_user_id != requested_by` on insert — maker cannot be checker. A `CHECK` constraint cannot reference another table in PostgreSQL, so a `BEFORE INSERT` trigger on `approval_actions` looks up `requested_by` from `approval_requests` and raises an exception if they match.

### 5.3 Workflow

- **Submit:** `ApprovalService.submit(session, operation_type, payload, requested_by, required_approvals, expires_at)` → inserts `approval_requests` with `status=pending`, publishes `ApprovalRequested` event.
- **Approve:** Inserts `approval_action`. If approval count equals `required_approvals`: sets status `approved`, calls executor inline in the same transaction. On executor success: `executed`. On executor raise: `execution_failed` (records `execution_result` with error). Publishes `ApprovalGranted` then `ApprovalExecuted` or `ApprovalExecutionFailed`.
- **Reject:** First reject action → `status=rejected`, `rejection_reason` set. No further actions accepted (service raises if request not `pending`). Publishes `ApprovalRejected`.
- **Cancel:** Maker only, only if `approval_actions` count is zero (no checker has acted). Status → `cancelled`.
- **Expiry:** Hourly Celery beat task: `UPDATE approval_requests SET status='expired' WHERE status='pending' AND expires_at < now()`.

Every state transition calls `TenantAuditService` (or `PlatformAuditService`) explicitly — these rows have no `AuditableMixin` since the before/after model state isn't meaningful; a structured audit record is more useful.

### 5.4 Registry

```python
# In registry.py:
approval_registry: dict[str, Callable] = {}

def approval_executor(operation_type: str):
    def decorator(fn: Callable) -> Callable:
        approval_registry[operation_type] = fn
        return fn
    return decorator

# In a consuming module (e.g. credit/service.py):
@approval_executor("loan.disburse")
async def execute_loan_disburse(session: AsyncSession, payload: dict) -> dict:
    ...
```

`ApprovalService` looks up `approval_registry[operation_type]` and calls it. If `operation_type` is not registered, raises `ValueError` at submit time (fail fast).

Modules register their executors at app startup via FastAPI's `lifespan`. `ApprovalService` imports `approval_registry` from `app.modules.maker_checker.registry` only. Consuming modules import `approval_executor` from the same place.

### 5.5 Permission map

`operation_type_permissions: dict[str, str]` maps operation type to a required permission string (e.g. `"loan.disburse" → "loans:approve"`). FastAPI dependency `require_approval_permission(operation_type)` is defined now as a stub that reads actor context vars — actual role checking is wired up when the `iam` module (bounded context #3) is built. Defined in `registry.py` alongside the executor registry.

### 5.6 API surface (`/approvals`)

| Method | Path | Description |
|---|---|---|
| POST | `/approvals` | Submit approval request |
| GET | `/approvals` | List (filter by status, operation_type) |
| GET | `/approvals/{id}` | Get single request with actions |
| POST | `/approvals/{id}/approve` | Approve (checker only) |
| POST | `/approvals/{id}/reject` | Reject (checker only) |
| POST | `/approvals/{id}/cancel` | Cancel (maker only, no prior actions) |

All endpoints use `get_tenant_session` (or `get_platform_session` for platform operations — same router, different mount point).

---

## 6. Migrations

### `alembic/platform/versions/001_core_platform.py`
Creates (in `platform` schema): `audit_log`, `outbox_events`, `processed_events`, `approval_requests`, `approval_actions`.

### `alembic/tenant/versions/001_core_tenant.py`
Creates (in tenant schema via `search_path`): same five tables without schema prefix.

Both files carry a module-level docstring:

```
Platform and tenant Alembic chains are independent.
Version numbers do not correlate across chains.
001 in platform and 001 in tenant are unrelated migrations.
```

---

## 7. Testing

### Audit
- `test_audit_mixin.py`: A platform model with `AuditableMixin` writes to `platform.audit_log`; a tenant model writes to `tenant_*.audit_log`. Cross-context: a `platform_user` actor acting via a tenant session writes to tenant log with `actor_type='platform_user'`.
- `test_audit_service.py`: Manual `record()` calls produce correct rows; appends only (no update/delete path exposed).

### Outbox
- `test_publisher.py`: `EventPublisher.publish()` committed with business transaction; rolled-back transaction produces no row.
- `test_worker.py`:
  - **SKIP LOCKED concurrency:** Two concurrent workers run simultaneously; each row published exactly once (verified by count and `published_at` not null).
  - **Backoff:** Inject a publish failure; verify `next_attempt_at` follows exponential formula, row not re-attempted until `next_attempt_at` passes.
  - **Dead-lettering:** Inject 10 consecutive failures; verify `is_dead_lettered=true` and no further processing.
- `test_retention.py`: Rows older than retention threshold deleted; recent rows untouched.

### Maker-checker
- `test_service.py`: Full happy path (submit → approve → execute), reject, cancel, expiry, double-vote rejection, self-approval rejection.
- `test_registry.py`: `@approval_executor` registers correctly; unknown `operation_type` raises at submit.
- `test_api.py`: HTTP-level integration tests for all six endpoints.

---

## 8. CLAUDE.md Additions

After implementation, append to `CLAUDE.md`:

```
## Core module contracts (do not violate)
- Direct RabbitMQ client usage is forbidden outside app/core/outbox/. All events go through EventPublisher.publish().
- All event consumers must check processed_events before acting. At-least-once delivery is the contract.
- Approvable operations must be registered via @approval_executor and invoked through ApprovalService. Direct execution paths for approvable operations are forbidden.
```

---

## 9. Open decisions (deferred)

- **JWT-based actor resolution:** Currently actors come from structlog contextvars (set by middleware). Once `iam` module is built, the middleware will populate these from the JWT. No changes needed to audit or maker-checker at that point — they read from context vars, not the request directly.
- **Platform-level maker-checker API mount point:** Will be decided when `platform_` module is built. The framework is schema-agnostic; mounting is a routing concern.
- **Dead-letter alerting:** Currently `structlog.error` with a metric tag. Prometheus/alerting integration is a future concern.
