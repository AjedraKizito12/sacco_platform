# Phase 7 — Tenant Offboarding & Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a staged, reversible-until-archived tenant lifecycle
(`active → cancelled → read_only → archived → hard_deleted`) with audit trail,
customer notifications, a method-aware read-only gate, and Phase-4-style
infra-side encrypted archival.

**Architecture:** The app owns the lifecycle state machine
(`OffboardingService`, the only writer of `lifecycle_state` + telemetry columns
+ `tenant_lifecycle_events`); the subscription gate enforces `read_only`
method-awarely; three daily beat jobs drive the time-based transitions; a
host-side script (`infra/offboarding/`) does the physical `pg_dump → encrypt →
upload → DROP SCHEMA` off an app-written "ready" signal. Notifications reuse the
Phase-3 outbox→tenant-admin bridge.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic (platform schema),
Celery beat, structlog, Pydantic v2; Next.js 15 portal; pytest. Spec:
`docs/superpowers/specs/2026-08-05-tenant-offboarding-design.md`.

## Global Constraints

- **`OffboardingService` is the ONLY writer** of `tenants.lifecycle_state`,
  `cancelled_at`, `read_only_at`, `archived_at`, `hard_deleted_at`,
  `retention_hold_until`, and the ONLY inserter of `tenant_lifecycle_events`.
  Add `lifecycle_state` (+ the `*_at`/`retention_hold_until` columns) to the
  existing "only `TenantService` mutates tenant columns" contract.
- **Offboarding NEVER sets `is_active = false`.** `_resolve_tenant_schema`
  filters `is_active = true`; a `read_only` tenant must stay resolvable so
  GETs reach the gate. Access is governed by `lifecycle_state`, not
  `is_active`.
- **`subscription_status` stays owned solely by `SubscriptionService`.**
  Offboarding `cancel` stops billing via
  `SubscriptionService.cancel(cancel_at_period_end=False)` in the same
  transaction; it never writes `subscription_status` directly.
- **Maker-checker:** `cancel` → `tenant.cancel` executor, quorum 2. `restore`
  and `extend-retention` → direct (`CurrentSuperuser`).
- **No tenant-schema migration.** All DDL is `alembic/platform/`. Money/async
  rules from CLAUDE.md still apply. No new top-level Python dependency.
- **Physical archival (pg_dump/encrypt/upload/DROP SCHEMA) is infra-side
  only.** No S3 client, `pg_dump`, or `DROP SCHEMA` in app code.
- **Retention windows are settings:** `OFFBOARDING_READ_ONLY_DAYS=7`,
  `OFFBOARDING_ARCHIVE_DAYS=83`, `OFFBOARDING_HARD_DELETE_DAYS=2555`. Per-tenant
  deviation only via `retention_hold_until`.
- **Gates:** `python -m ruff check app/ && python -m mypy app/` clean;
  `env -u DATABASE_URL pytest <path> -q` (Redis + Postgres via docker compose).
  Portal: `pnpm --filter @sacco/portal <test|lint|typecheck>`.

## File Structure

```
alembic/platform/versions/015_tenant_offboarding.py   Task 1 (migration)
app/platform_/tenants/models.py                        Task 2 (TenantLifecycleEvent; Tenant columns)
app/core/config.py                                     Task 2 (OFFBOARDING_* settings)
app/platform_/tenants/offboarding_service.py           Task 3 (state machine)
app/core/db.py                                          Task 4 (read_only gate)
app/platform_/tenants/executors.py                     Task 5 (tenant.cancel)
app/platform_/tenants/api.py                           Task 5 (endpoints)
app/platform_/tenants/schemas.py                       Task 5 (I/O schemas)
app/platform_/tenants/events.py                        Task 6 (outbox event types)
app/core/notifications/offboarding_consumer.py         Task 6 (bridge → tenant-admin feed)
app/platform_/tenants/beat.py                          Task 7 (3 sweep tasks)
app/workers/celery_app.py                              Task 7 (beat_schedule)
infra/offboarding/{archive.sh,delete-archive.sh,lib.sh,systemd/}  Task 8
admin/packages/schemas/src/tenants.ts                  Task 9
admin/packages/api-client/src/resources/tenants.ts     Task 9
admin/packages/ui/src/components/StatusBadge/status-maps.ts  Task 9
admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/OffboardingSection.tsx  Task 10
admin/apps/portal/app/platform/(authed)/tenants/archived/…    Task 10
docs/tenant-offboarding.md, CLAUDE.md                  Task 11
infra/observability/logfire/alerts/offboarding-archive-stuck.json  Task 11
```

---

# Increment 1 — Data model + state machine

### Task 1: Platform migration 015

**Files:**
- Create: `alembic/platform/versions/015_tenant_offboarding.py`

**Interfaces:**
- Produces: `platform.tenants` columns `lifecycle_state`, `cancelled_at`,
  `read_only_at`, `archived_at`, `hard_deleted_at`, `retention_hold_until`,
  `archive_storage_key`, `archive_size_bytes`, `archive_checksum`; table
  `platform.tenant_lifecycle_events`.

- [ ] **Step 1: Write the migration.** Chain onto current head `014`.

```python
"""Tenant offboarding lifecycle state + archival telemetry + audit.

Revision: 015
Depends on: 014
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

_STATES = "('active','cancelled','read_only','archived','hard_deleted')"


def upgrade() -> None:
    op.add_column("tenants", sa.Column("lifecycle_state", sa.Text(), nullable=False, server_default="active"), schema="platform")
    for col in ("cancelled_at", "read_only_at", "archived_at", "hard_deleted_at", "retention_hold_until"):
        op.add_column("tenants", sa.Column(col, TIMESTAMP(timezone=True), nullable=True), schema="platform")
    op.add_column("tenants", sa.Column("archive_storage_key", sa.Text(), nullable=True), schema="platform")
    op.add_column("tenants", sa.Column("archive_size_bytes", sa.BigInteger(), nullable=True), schema="platform")
    op.add_column("tenants", sa.Column("archive_checksum", sa.Text(), nullable=True), schema="platform")
    op.create_check_constraint("ck_tenants_lifecycle_state", "tenants", f"lifecycle_state IN {_STATES}", schema="platform")
    op.create_index("ix_platform_tenants_lifecycle_state", "tenants", ["lifecycle_state"], schema="platform")

    op.create_table(
        "tenant_lifecycle_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("platform.tenants.id"), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=False),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("occurred_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("platform.platform_users.id"), nullable=True),
        sa.Column("metadata", JSONB(), server_default="{}", nullable=False),
        schema="platform",
    )
    op.create_index("ix_platform_tenant_lifecycle_events_tenant", "tenant_lifecycle_events", ["tenant_id", "occurred_at"], schema="platform")


def downgrade() -> None:
    op.drop_table("tenant_lifecycle_events", schema="platform")
    op.drop_index("ix_platform_tenants_lifecycle_state", table_name="tenants", schema="platform")
    op.drop_constraint("ck_tenants_lifecycle_state", "tenants", schema="platform")
    for col in ("archive_checksum", "archive_size_bytes", "archive_storage_key", "retention_hold_until",
                "hard_deleted_at", "archived_at", "read_only_at", "cancelled_at", "lifecycle_state"):
        op.drop_column("tenants", col, schema="platform")
```

- [ ] **Step 2: Apply + verify.** Run `alembic -c alembic/platform/alembic.ini upgrade head` against the test DB; confirm `platform.tenants.lifecycle_state` and `platform.tenant_lifecycle_events` exist (`\d+ platform.tenants`). Then `downgrade -1` and `upgrade head` again to prove the migration is reversible.

- [ ] **Step 3: Commit** `feat(offboarding): platform migration 015 — lifecycle_state + archival telemetry + audit table`.

---

### Task 2: Models + settings

**Files:**
- Modify: `app/platform_/tenants/models.py` (Tenant columns + `TenantLifecycleEvent`)
- Modify: `app/core/config.py` (`OFFBOARDING_*` settings)
- Test: `tests/platform_/tenants/test_lifecycle_models.py`

**Interfaces:**
- Produces: `Tenant.lifecycle_state`, `Tenant.cancelled_at`, `.read_only_at`,
  `.archived_at`, `.hard_deleted_at`, `.retention_hold_until`,
  `.archive_storage_key`, `.archive_size_bytes`, `.archive_checksum`;
  `TenantLifecycleEvent`; `Settings.offboarding_read_only_days` (int, 7),
  `.offboarding_archive_days` (int, 83), `.offboarding_hard_delete_days`
  (int, 2555).

- [ ] **Step 1: Write the failing test.**

```python
# tests/platform_/tenants/test_lifecycle_models.py
from app.platform_.tenants.models import Tenant, TenantLifecycleEvent

def test_tenant_has_lifecycle_columns():
    cols = Tenant.__table__.columns
    assert "lifecycle_state" in cols
    assert cols["lifecycle_state"].default.arg == "active"
    for c in ("cancelled_at", "read_only_at", "archived_at", "hard_deleted_at",
              "retention_hold_until", "archive_storage_key", "archive_size_bytes",
              "archive_checksum"):
        assert c in cols

def test_lifecycle_event_table():
    cols = TenantLifecycleEvent.__table__.columns
    assert {"tenant_id", "from_state", "to_state", "occurred_at", "reason",
            "actor_id", "metadata"} <= set(cols.keys())

def test_offboarding_settings_defaults():
    from app.core.config import Settings
    s = Settings()
    assert (s.offboarding_read_only_days, s.offboarding_archive_days,
            s.offboarding_hard_delete_days) == (7, 83, 2555)
```

- [ ] **Step 2: Run → FAIL** (`ImportError: TenantLifecycleEvent`).

- [ ] **Step 3: Add the columns to `Tenant`** (mirror existing mapped_column style; `lifecycle_state: Mapped[str] = mapped_column(Text, nullable=False, default="active")`, the five `datetime | None` timestamptz columns, `archive_storage_key: Mapped[str | None]`, `archive_size_bytes: Mapped[int | None]` (`BigInteger`), `archive_checksum: Mapped[str | None]`). **Add `TenantLifecycleEvent`** in the same module:

```python
class TenantLifecycleEvent(Base):
    __tablename__ = "tenant_lifecycle_events"
    __table_args__ = {"schema": "platform"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("platform.tenants.id"), nullable=False)
    from_state: Mapped[str] = mapped_column(Text, nullable=False)
    to_state: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("platform.platform_users.id"), nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)
```

  Add the three `offboarding_*` int settings to `Settings` in `app/core/config.py` near the `rate_limit_*` block.

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit** `feat(offboarding): Tenant lifecycle columns + TenantLifecycleEvent model + settings`.

---

### Task 3: OffboardingService state machine

**Files:**
- Create: `app/platform_/tenants/offboarding_service.py`
- Test: `tests/platform_/tenants/test_offboarding_service.py`

**Interfaces:**
- Consumes: `TenantService` (`app/platform_/tenants/service.py`),
  `SubscriptionService.cancel(subscription_id, *, cancel_at_period_end)`
  (`app/platform_/billing/services/subscription_service.py`),
  `TenantLifecycleEvent` (Task 2).
- Produces: `class OffboardingService(session)` with:
  `async cancel(*, tenant_id: UUID, actor_id: UUID, reason: str) -> Tenant`;
  `async restore(*, tenant_id: UUID, actor_id: UUID) -> Tenant`;
  `async extend_retention(*, tenant_id: UUID, actor_id: UUID, hold_until: datetime) -> Tenant`;
  `async sweep_cancelled_to_read_only(*, now: datetime) -> list[UUID]`;
  `async sweep_read_only_to_archived(*, now: datetime) -> list[UUID]`;
  `async sweep_archived_to_hard_deleted(*, now: datetime) -> list[UUID]`;
  `async lifecycle_events(*, tenant_id: UUID) -> list[TenantLifecycleEvent]`.
  Raises `OffboardingError` (subclass of `ValueError`) for illegal transitions.

Notes for the implementer:
- Every state change goes through a private
  `_transition(tenant, to_state, *, actor_id, reason=None, metadata=None)` that
  sets `tenant.lifecycle_state`, the matching `*_at` timestamp
  (`cancelled_at`/`read_only_at`/`archived_at`/`hard_deleted_at`), and inserts a
  `TenantLifecycleEvent(from_state=<old>, to_state=<new>, actor_id=..., reason=...)`.
  Do NOT commit inside the service — the caller (executor / endpoint / beat) owns
  the transaction.
- `cancel`: require `lifecycle_state == "active"` (else `OffboardingError`);
  `_transition(..., "cancelled")`; then hard-cancel billing —
  `sub = tenant.current_subscription_id`; if set,
  `await SubscriptionService(session).cancel(sub, cancel_at_period_end=False)`.
  This is the amended billing-contract path (see Task 5 executor).
- `restore`: allow from `{cancelled, read_only, archived}` **only while
  `tenant.archive_checksum is None`** (schema still present); else
  `OffboardingError` ("already physically archived"). `_transition(..., "active")`;
  clear `cancelled_at/read_only_at/archived_at = None`; leave
  `subscription_status` untouched (operator re-assigns a plan separately).
- `extend_retention`: set `tenant.retention_hold_until = hold_until`; record a
  lifecycle event with `to_state == from_state` and
  `metadata={"retention_hold_until": hold_until.isoformat()}`.
- `sweep_cancelled_to_read_only(now)`: select tenants where
  `lifecycle_state='cancelled' AND cancelled_at <= now - INTERVAL '<N> days'`
  (N = `settings.offboarding_read_only_days`); `_transition(..., "read_only")`
  each; return their ids.
- `sweep_read_only_to_archived(now)`: select `lifecycle_state='read_only' AND
  read_only_at <= now - <M> days AND (retention_hold_until IS NULL OR
  retention_hold_until <= now)`; `_transition(..., "archived")`. The physical
  dump is infra-side (Task 8); this only sets state + `archived_at`.
- `sweep_archived_to_hard_deleted(now)`: select `lifecycle_state='archived' AND
  archived_at <= now - <H> days`; `_transition(..., "hard_deleted")`.

- [ ] **Step 1: Write the failing tests** (use the `platform_session` fixture
  pattern — `async_sessionmaker` + commit + cleanup — per the repo test
  conventions; seed a `Tenant` row directly).

```python
# tests/platform_/tenants/test_offboarding_service.py (abridged — implementer fills seeding)
from datetime import UTC, datetime, timedelta
import pytest
from app.platform_.tenants.offboarding_service import OffboardingService, OffboardingError

async def test_cancel_from_active_sets_state_and_event(session, tenant, actor):
    svc = OffboardingService(session)
    t = await svc.cancel(tenant_id=tenant.id, actor_id=actor.id, reason="customer left")
    assert t.lifecycle_state == "cancelled"
    assert t.cancelled_at is not None
    events = await svc.lifecycle_events(tenant_id=tenant.id)
    assert events[-1].to_state == "cancelled" and events[-1].from_state == "active"

async def test_cancel_twice_rejected(session, tenant, actor):
    svc = OffboardingService(session)
    await svc.cancel(tenant_id=tenant.id, actor_id=actor.id, reason="x")
    with pytest.raises(OffboardingError):
        await svc.cancel(tenant_id=tenant.id, actor_id=actor.id, reason="x")

async def test_restore_blocked_after_physical_archive(session, tenant, actor):
    svc = OffboardingService(session)
    tenant.lifecycle_state = "archived"; tenant.archive_checksum = "sha256:abc"
    with pytest.raises(OffboardingError):
        await svc.restore(tenant_id=tenant.id, actor_id=actor.id)

async def test_sweep_cancelled_to_read_only_respects_window(session, tenant, actor):
    svc = OffboardingService(session)
    tenant.lifecycle_state = "cancelled"
    tenant.cancelled_at = datetime.now(UTC) - timedelta(days=8)
    now = datetime.now(UTC)
    ids = await svc.sweep_cancelled_to_read_only(now=now)
    assert tenant.id in ids
    assert (await svc.lifecycle_events(tenant_id=tenant.id))[-1].to_state == "read_only"

async def test_sweep_to_archived_blocked_by_hold(session, tenant, actor):
    svc = OffboardingService(session)
    tenant.lifecycle_state = "read_only"
    tenant.read_only_at = datetime.now(UTC) - timedelta(days=90)
    tenant.retention_hold_until = datetime.now(UTC) + timedelta(days=30)
    ids = await svc.sweep_read_only_to_archived(now=datetime.now(UTC))
    assert tenant.id not in ids
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement `offboarding_service.py`** per the notes above.
- [ ] **Step 4: Run → PASS + gates** (`ruff`, `mypy`).
- [ ] **Step 5: Commit** `feat(offboarding): OffboardingService state machine + lifecycle audit`.

---

# Increment 2 — Gate + API + notifications

### Task 4: read_only gate enforcement

**Files:**
- Modify: `app/core/db.py` (`get_tenant_session`, new `_check_offboarding_gate`)
- Test: `tests/core/test_offboarding_gate.py`

**Interfaces:**
- Consumes: `Tenant.lifecycle_state` (Task 2).
- Produces: `async _check_offboarding_gate(slug: str, method: str) -> None`,
  called from `get_tenant_session` **before** `_check_subscription_gate(slug)`.

Notes:
- New function mirrors `_check_subscription_gate` (own `engine.connect()`,
  fully-qualified query, no `is_active` filter):
  `SELECT lifecycle_state FROM platform.tenants WHERE slug = :slug`.
  - `read_only` → allow if `method in {"GET","HEAD","OPTIONS"}`, else
    `raise HTTPException(403, detail="Tenant is read-only (offboarding).")`.
  - `cancelled | archived | hard_deleted` →
    `raise HTTPException(403, detail="Tenant has been offboarded.")`.
  - `active` (or row None) → return.
- In `get_tenant_session`, call `await _check_offboarding_gate(slug, request.method)`
  immediately before the existing `await _check_subscription_gate(slug)`.

- [ ] **Step 1: Write the failing test** (httpx `ASGITransport` + a tenant seeded
  in `tenant_test`; hit a real tenant-scoped GET and POST route with
  `X-Tenant-Slug`). Assert: `read_only` → GET 200 / POST 403; `cancelled` →
  GET 403; `active` → unchanged. (Reuse the tenant-session override pattern from
  `tests/platform_/tenant_users_admin/test_api.py`; set `lifecycle_state` via a
  direct UPDATE on `platform.tenants`.)

```python
# tests/core/test_offboarding_gate.py (abridged)
async def test_read_only_allows_get_blocks_write(client, set_lifecycle):
    await set_lifecycle("read_only")
    assert (await client.get("/members", headers=H)).status_code != 403
    assert (await client.post("/members", json={}, headers=H)).status_code == 403

async def test_cancelled_blocks_all(client, set_lifecycle):
    await set_lifecycle("cancelled")
    assert (await client.get("/members", headers=H)).status_code == 403
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `_check_offboarding_gate` + wire the call.
- [ ] **Step 4: Run → PASS + gates.** Confirm the existing subscription-gate tests still pass (`pytest tests/ -k subscription_gate`).
- [ ] **Step 5: Commit** `feat(offboarding): method-aware read_only gate in get_tenant_session`.

---

### Task 5: Endpoints + tenant.cancel executor + schemas

**Files:**
- Modify: `app/platform_/tenants/executors.py` (`tenant.cancel`)
- Modify: `app/platform_/tenants/api.py` (4 endpoints)
- Modify: `app/platform_/tenants/schemas.py` (`TenantCancelIn`, `ExtendRetentionIn`, `TenantLifecycleEventOut`; add fields to `TenantOut`)
- Modify: `CLAUDE.md` billing contract (one-line amendment — see Step 4)
- Test: `tests/platform_/tenants/test_offboarding_api.py`

**Interfaces:**
- Consumes: `OffboardingService` (Task 3), `ApprovalService.submit` (as used by
  the existing `suspend` endpoint), `CurrentSuperuser` / `Session` deps already
  imported in `api.py`.
- Produces: `POST /platform/tenants/{id}/cancel`, `.../restore`,
  `.../extend-retention`, `GET /platform/tenants/{id}/lifecycle`; executor
  `@approval_executor("tenant.cancel")`.

- [ ] **Step 1: Write the failing tests** (mirror `tests/platform_/ops/test_api.py`
  auth+session pattern): cancel submits a `tenant.cancel` approval (202,
  `pending_approval`) and a non-superuser is 403; restore flips a cancelled
  tenant back to active (direct); extend-retention sets `retention_hold_until`;
  lifecycle returns the event timeline; restore on a physically-archived tenant
  → 409.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Add the executor** (mirror `execute_tenant_suspend`):

```python
@approval_executor("tenant.cancel")  # type: ignore[misc]
async def execute_tenant_cancel(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    """Runs when a tenant.cancel approval reaches quorum (q=2).
    payload: {tenant_id, reason, requested_by}."""
    from app.platform_.tenants.offboarding_service import OffboardingService
    tenant_id = uuid.UUID(payload["tenant_id"])
    actor_id = uuid.UUID(payload["requested_by"])
    tenant = await OffboardingService(session).cancel(
        tenant_id=tenant_id, actor_id=actor_id, reason=payload["reason"],
    )
    return {"tenant_id": str(tenant.id), "lifecycle_state": tenant.lifecycle_state}
```

- [ ] **Step 4: Add the endpoints** to `api.py`. `cancel` mirrors `suspend_tenant`
  (submit `operation_type="tenant.cancel"`, `payload={"tenant_id":…,"reason":…,
  "requested_by":str(actor.id)}`, `required_approvals=2`); guard 409 if
  `lifecycle_state != "active"`. `restore` and `extend_retention` call the
  service directly then `await session.commit()`, translating `OffboardingError`
  → `HTTPException(409, str(e))`. `lifecycle` returns
  `[TenantLifecycleEventOut.model_validate(e) for e in events]`. Add
  `lifecycle_state` + the archival telemetry fields to `TenantOut`.

  **Amend the billing contract in `CLAUDE.md`** (billing section): the line
  "Hard cancellation … is only callable from the `billing.cancel_subscription`
  executor" gains: "…and from the `tenant.cancel` offboarding executor (Phase 7),
  which has already cleared quorum-2 maker-checker."

- [ ] **Step 5: Register the executor import.** Confirm `app/main.py` already
  imports `app.platform_.tenants.executors` (it does, for `tenant.suspend`) — the
  new decorator registers with it. Add an assertion-free note; no code change if
  the module import is already present.

- [ ] **Step 6: Run → PASS + gates.**
- [ ] **Step 7: Commit** `feat(offboarding): cancel/restore/extend/lifecycle endpoints + tenant.cancel executor`.

---

### Task 6: Notifications (outbox events + tenant-admin bridge)

**Files:**
- Create: `app/platform_/tenants/events.py` (event-type constants + publish helper)
- Modify: `app/platform_/tenants/offboarding_service.py` (publish on transition)
- Create: `app/core/notifications/offboarding_consumer.py`
- Modify: platform notification template seed data (wherever Phase 3 seeds live — `grep -rn "invoice_issued" app/core/notifications` to find the seed module)
- Test: `tests/core/notifications/test_offboarding_consumer.py`

**Interfaces:**
- Consumes: `EventPublisher.publish` (the outbox path used by billing —
  `grep -rn "BillingSubscriptionSuspended" app/platform_/billing` for the call
  site to mirror), `NotificationService.publish` (Task-6 recipient loop mirrors
  `app/core/notifications/... billing_consumer._publish_to_tenant_admins`).
- Produces: outbox event types `TenantOffboardingCancelled`,
  `TenantOffboardingReadOnly`, `TenantOffboardingArchived`,
  `TenantOffboardingRestored`; consumer task
  `consume_offboarding_notification_events`; notification event codes
  `tenant_offboarding_{cancelled,read_only,archived,restored}`.

Notes:
- Offboarding runs in platform transactions but recipients (tenant admins) read
  tenant-schema feeds — so mirror `notifications.billing_consumer` exactly: each
  transition publishes a platform-outbox event; the consumer bridges to every
  active admin `tenant_user` with a `dedupe_key` of
  `f"offboarding:{event_id}:{tenant_user_id}"`.
- `OffboardingService._transition` gains an optional `publish: bool = True`; after
  the state change it calls the Task-6 publish helper with the tenant + to_state.
  (The sweeps publish too; `restore`/`cancel` publish their own codes.)
- Notices only — context carries `{tenant_name, to_state, occurred_at}`, no
  secrets/PII.

- [ ] **Step 1: Write the failing test** — seed a `TenantOffboardingCancelled`
  outbox event + an admin `tenant_user`, run
  `consume_offboarding_notification_events`, assert one `notification_events` row
  with `event_code="tenant_offboarding_cancelled"` for that admin, and that a
  second run is idempotent (dedupe). Mirror
  `tests/.../test_billing_consumer.py`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `events.py`, the `_transition` publish hook, the
  consumer (copy `billing_consumer.py`, swap the event set + `_notification`
  mapping), and add the four template seeds + one portal-catalog mirror row each
  in `admin/packages/schemas/src/notifications.ts` (per contract O).
- [ ] **Step 4: Register the consumer** in `celery_app.py beat_schedule` (60s,
  mirroring the billing consumer entry).
- [ ] **Step 5: Run → PASS + gates.**
- [ ] **Step 6: Commit** `feat(offboarding): lifecycle notifications via outbox→tenant-admin bridge`.

---

# Increment 3 — Beat jobs + infra archival

### Task 7: Daily transition beat jobs

**Files:**
- Create: `app/platform_/tenants/beat.py`
- Modify: `app/workers/celery_app.py` (`beat_schedule`)
- Test: `tests/platform_/tenants/test_offboarding_beat.py`

**Interfaces:**
- Consumes: `OffboardingService` sweeps (Task 3).
- Produces: Celery tasks
  `app.platform_.tenants.beat.transition_cancelled_to_read_only`,
  `…transition_read_only_to_archived`,
  `…transition_archived_to_hard_deleted`.

Notes:
- Each task opens a platform session (`async_sessionmaker(engine)` +
  `SET LOCAL search_path TO platform`), calls the matching sweep with
  `now=datetime.now(UTC)`, and commits. Mirror the structure of
  `app/core/observability/beat.py` (async body wrapped for Celery). Failures are
  logged; a per-tenant failure must not abort the batch (wrap each id in the
  service, or catch+continue in the task).
- Schedules (daily, staggered): `transition_cancelled_to_read_only` 00:00 UTC,
  `transition_read_only_to_archived` 00:30, `transition_archived_to_hard_deleted`
  01:00. Use `crontab(hour=…, minute=…)` (import already present in
  `celery_app.py`).

- [ ] **Step 1: Write the failing test** — seed tenants at each due boundary,
  invoke each task body, assert transitions occurred and events written (frozen
  `now` via seeding `*_at` in the past).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement `beat.py`** + register the three schedule entries.
- [ ] **Step 4: Run → PASS + gates.**
- [ ] **Step 5: Commit** `feat(offboarding): daily lifecycle transition beat jobs`.

---

### Task 8: Infra-side archival scripts

**Files:**
- Create: `infra/offboarding/lib.sh`, `infra/offboarding/archive.sh`,
  `infra/offboarding/delete-archive.sh`, `infra/offboarding/systemd/*.{service,timer}`,
  `infra/offboarding/README.md`
- Test: `infra/offboarding/archive.sh` exercised against MinIO-local + a
  throwaway schema (manual/CI drill, mirroring `infra/backups/restore-staging.sh`)

**Interfaces:**
- Consumes: the "ready" signal — `platform.tenants` rows where
  `lifecycle_state='archived' AND archive_checksum IS NULL`.
- Produces: writes `archive_storage_key`, `archive_size_bytes`,
  `archive_checksum` back and `DROP SCHEMA … CASCADE`; the delete script clears
  the archive object for `hard_deleted` rows.

Notes:
- Copy the poll/lib structure from `infra/backups/` (`lib.sh`,
  `poll-verify-requests.sh`). `archive.sh`:
  1. `psql -t -c "SELECT id, schema_name FROM platform.tenants WHERE lifecycle_state='archived' AND archive_checksum IS NULL"`.
  2. For each: `pg_dump --schema="<schema>" "$DB_URL"` →
     `age -r "$AGE_RECIPIENT"` → upload to
     `"$OFFBOARDING_BUCKET/offboarding/<schema>-<ts>.sql.age"`; capture size +
     `sha256sum`.
  3. `psql -c 'DROP SCHEMA "<schema>" CASCADE'`.
  4. `psql -c "UPDATE platform.tenants SET archive_storage_key=…, archive_size_bytes=…, archive_checksum=… WHERE id=…"`.
  Never runs as root; DB access via the postgres role; S3/age creds from the
  host env only (never the app image), per the Phase-4 contract.
- `delete-archive.sh`: for `lifecycle_state='hard_deleted'` rows with a
  non-null `archive_storage_key`, delete the object and null the key.
- systemd timers: `archive` daily 02:00 UTC, `delete-archive` weekly.

- [ ] **Step 1: Write `lib.sh` + `archive.sh` + `delete-archive.sh` + systemd units + README** (no app code).
- [ ] **Step 2: Drill** — against the local MinIO + a throwaway schema
  (`CREATE SCHEMA tenant_drill; …`), set a fake `archived`/`checksum IS NULL`
  tenant row pointing at it, run `archive.sh`, and assert: object uploaded, row
  telemetry populated, `tenant_drill` dropped. Mirror the Phase-4 restore drill's
  assert style.
- [ ] **Step 3: Commit** `feat(offboarding): infra-side pg_dump→encrypt→upload→drop archival scripts`.

---

# Increment 4 — Portal + docs close-out

### Task 9: Portal types + api-client + StatusBadge

**Files:**
- Modify: `admin/packages/schemas/src/tenants.ts` (`lifecycle_state` +
  telemetry on the tenant type; `TenantLifecycleEventOut`; `CancelTenantIn`,
  `ExtendRetentionIn`)
- Modify: `admin/packages/api-client/src/resources/tenants.ts` (`cancel`,
  `restore`, `extendRetention`, `lifecycle`, `listArchived`)
- Modify: `admin/packages/api-client/src/query-keys.ts` (tenant lifecycle keys)
- Modify: `admin/packages/ui/src/components/StatusBadge/status-maps.ts` (tenant
  lifecycle states → variants)
- Test: `admin/packages/api-client/src/__tests__/query-keys-tenants.test.ts` (extend)

- [ ] **Step 1–4:** Add the types + resource methods (mirror the ops/rateLimits
  resource style: `api.POST("/platform/tenants/{tenant_id}/cancel" as never, …)`),
  query keys, and StatusBadge rows (`active→success`, `cancelled→warning`,
  `read_only→info`, `archived→neutral`, `hard_deleted→neutral`). Run
  `pnpm --filter @sacco/api-client --filter @sacco/schemas --filter @sacco/ui typecheck`.
- [ ] **Step 5: Commit** `feat(portal): tenant lifecycle schemas + api-client + StatusBadge`.

---

### Task 10: Offboarding UI (detail section + archived list)

**Files:**
- Create: `.../tenants/[id]/_components/OffboardingSection.tsx` (+ `CancelTenantDialog`, `RestoreButton`, `ExtendRetentionDialog`, `LifecycleTimeline`)
- Modify: `.../tenants/[id]/page.tsx` (render `<OffboardingSection>`)
- Create: `.../tenants/archived/page.tsx` + `_components/ArchivedTenantsTable.tsx`
- Modify: settings/tenants nav as needed
- Test: `.../tenants/[id]/__tests__/OffboardingSection.test.tsx`

- [ ] **Step 1–4:** Follow the portal conventions (contracts H–V) and the
  `new-portal-page` structure. **Cancel** → `<MakerCheckerConfirmDialog>` (a
  reason field + optional customer-message; copy locked per contract V).
  **Restore** / **Extend** → base `<ConfirmDialog>`. **Timeline** renders
  `GET /platform/tenants/{id}/lifecycle` with `<AuditTimestamp>` +
  `<StatusBadge entity="tenant" status=…>`. **Archived list** → `<DataTable>`
  (contract T) of `listArchived` with size (`<Count>`) + age (`<RelativeTime>`).
  Permission-gate on the platform superuser context. Component test asserts the
  Cancel dialog uses the maker-checker copy and Restore uses the plain confirm.
  Run `pnpm --filter @sacco/portal test|lint|typecheck` — all green.
- [ ] **Step 5: Commit** `feat(portal): tenant offboarding section + archived tenants list`.

---

### Task 11: Docs + CLAUDE.md close-out + archival alert

**Files:**
- Create: `docs/tenant-offboarding.md`, `docs/alert-runbooks/offboarding-archive-stuck.md`, `infra/observability/logfire/alerts/offboarding-archive-stuck.json`
- Modify: `CLAUDE.md`, `infra/observability/logfire/alerts/README.md`, `docs/metrics-catalogue.md` (if a metric is added)

- [ ] **Step 1:** `docs/tenant-offboarding.md` — the lifecycle diagram, state
  semantics, gate behaviour, retention settings + legal-hold, the restore
  boundary, and the infra archival runbook (how to retrieve an archive via
  `archive_storage_key`, since there is no in-app download).
- [ ] **Step 2:** Committed Logfire alert `offboarding-archive-stuck.json`
  (`source: metric` or `spans` depending on Task 7/8 telemetry — a tenant in
  `archived` with `archive_checksum IS NULL` for > 24h; if no metric exists,
  file it as `source: unavailable` with a note, matching the Phase-5 staged-alert
  convention) + its runbook; update the alerts README catalogue table and count.
- [ ] **Step 3: CLAUDE.md close-out** — roadmap row 7 → **Done**; add a "Tenant
  offboarding contracts (Phase 7 — do not violate)" section (the Global
  Constraints above: `OffboardingService` sole writer, never touch `is_active`,
  `subscription_status` stays billing-owned, cancel=MC-q2 / restore+extend
  direct, infra-side archival, restore-boundary at `archive_checksum`); add a
  Phase 7 scope note under contract N (touches `app/platform_/tenants/`,
  `app/core/db.py`, `app/core/notifications/`, `app/workers/celery_app.py`,
  `alembic/platform/015`, `infra/offboarding/`, `admin/…/tenants/`, `docs/`).
- [ ] **Step 4: Gates** + commit `feat(offboarding): docs + archival alert + CLAUDE.md close-out (Phase 7 complete)`.

---

## Self-Review

**Spec coverage:**
- Lifecycle state machine + reversible-until-archived → Tasks 2, 3. ✓
- Dedicated `lifecycle_state` column + telemetry + audit table → Tasks 1, 2. ✓
- Method-aware `read_only` gate; never touch `is_active` → Task 4. ✓
- cancel(MC q=2) / restore / extend / lifecycle endpoints → Task 5. ✓
- Billing coupling + contract amendment; restore doesn't re-bill → Tasks 3, 5. ✓
- Notifications at each transition (outbox→tenant-admin bridge) → Task 6. ✓
- Beat-driven transitions with retention-hold guard → Tasks 3, 7. ✓
- Infra-side dump→encrypt→upload→DROP SCHEMA + telemetry write-back → Task 8. ✓
- Portal offboarding UI + archived list → Tasks 9, 10. ✓
- Settings (`OFFBOARDING_*`) → Task 2. ✓
- Cuts (no in-app archive download; no retention_policy enum; restore after
  physical archive → runbook) → honored (Tasks 5, 8; spec §Out of scope). ✓
- Docs + CLAUDE.md close-out + alert → Task 11. ✓

**Placeholder scan:** No TBD/TODO. The two spots that reference existing code by
grep (billing outbox publish call site in Task 6; template-seed module) name the
exact `grep` to locate them, because those modules were not re-read verbatim
while writing this plan — the implementer confirms the signature at that point,
not a vague "add notifications."

**Type consistency:** `OffboardingService.{cancel,restore,extend_retention,
sweep_*,lifecycle_events}`, `TenantLifecycleEvent`, `_check_offboarding_gate(
slug, method)`, `@approval_executor("tenant.cancel")`, event types
`TenantOffboarding{Cancelled,ReadOnly,Archived,Restored}`, event codes
`tenant_offboarding_{cancelled,read_only,archived,restored}`, settings
`offboarding_{read_only_days,archive_days,hard_delete_days}` — consistent across
tasks.
