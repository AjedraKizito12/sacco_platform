# Phase 1.7 Sub-Plan 02a: Impersonation Data Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/phase-1-7/02a-impersonation-data` from `main` before starting.

**Goal:** Ship the migrations, models, service, and maker-checker executor that let a platform user *request* an impersonation session in a tenant, have it approved by another platform user, and produce a row in `platform.support_impersonations`. **No HTTP integration. No token mint. No tenant JWT changes.** That's all 02b. After 02a merges, an approved impersonation exists as a DB row but cannot yet be used to access tenant routes.

**Architecture:** New module under `app/platform_/impersonations/` follows the project convention (`models.py`, `schemas.py`, `service.py`, `executors.py` — `api.py` is added in 02b). The flow is: caller invokes `ImpersonationService.request(...)` → that submits an `ApprovalRequest` with `operation_type="platform.start_impersonation"` against the platform schema. Once a checker approves via `/platform/approvals/{id}/approve` (P1.7-01), `ApprovalService.approve()` invokes the executor, which creates the `support_impersonations` row inside the same transaction as the approval execution. The row is the durable artifact 02b will read on mint-token calls.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, Pydantic v2, FastAPI dependency injection.

**Roadmap reference:** `docs/superpowers/plans/phase-1-7-backend-foundation/00-index.md` §P1.7-02 (split into 02a + 02b).

**ADR reference:** `docs/superpowers/decisions/2026-05-21-iam-architecture.md` §7 (the original "cross-context access via support_impersonations" decision that this sub-plan begins to implement).

**Prerequisite:** **P1.7-01 must be merged.** The executor delegates to `ApprovalService.approve()` which, via the new `/platform/approvals/{id}/approve` route, is how a checker triggers execution. Without P1.7-01 there is no HTTP path for the checker.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `alembic/platform/versions/008_support_impersonations.py` | Create | New `platform.support_impersonations` table |
| `alembic/tenant/versions/014_audit_log_impersonation_id.py` | Create | Add nullable `impersonation_id` column to `audit_log` and `tenant_users` (columns shipped now; populated in 02b) |
| `app/core/config.py` | Modify | Add `impersonation_max_minutes` and `impersonation_default_required_approvals` settings |
| `app/platform_/impersonations/__init__.py` | Create | Package marker |
| `app/platform_/impersonations/models.py` | Create | `SupportImpersonation` SQLAlchemy model |
| `app/platform_/impersonations/schemas.py` | Create | Pydantic types `ImpersonationStartIn`, `ImpersonationOut` |
| `app/platform_/impersonations/service.py` | Create | `ImpersonationService` (request/get/end/revoke/queries) |
| `app/platform_/impersonations/executors.py` | Create | `@approval_executor("platform.start_impersonation")` |
| `app/main.py` | Modify | Import `impersonations.executors` at startup so the decorator registers |
| `tests/conftest.py` | Modify | Register `SupportImpersonation` model in `test_engine` so the table is created |
| `tests/platform_/impersonations/__init__.py` | Create | Package marker |
| `tests/platform_/impersonations/test_service.py` | Create | Unit tests for `ImpersonationService` (request, end, revoke, queries) |
| `tests/platform_/impersonations/test_executor.py` | Create | Integration test: request → approve → executor creates row |
| `docs/superpowers/decisions/2026-06-02-impersonation-design.md` | Create | Architectural Decision Record locking the design before 02b |
| `CLAUDE.md` | Modify | Append "Impersonation contracts (data layer)" subsection — partial; full contracts added in 02b |

---

## Task 1: Migrations

**Files:**
- Create: `alembic/platform/versions/008_support_impersonations.py`
- Create: `alembic/tenant/versions/014_audit_log_impersonation_id.py`

- [ ] **Step 1: Write the platform migration**

```python
# alembic/platform/versions/008_support_impersonations.py
"""Phase 1.7 — platform.support_impersonations table.

Tracks active and historical platform-user → tenant impersonation sessions.

Revision: 008
Depends on: 007
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_impersonations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("platform_user_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        # tenant_user_id is the shadow tenant_user this impersonation maps to;
        # populated lazily by 02b on the first mint-token call. Null until then.
        sa.Column("tenant_user_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ended_by", sa.UUID(), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["platform_user_id"], ["platform.platform_users.id"],
            name="fk_support_impersonations_platform_user",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["platform.tenants.id"],
            name="fk_support_impersonations_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["approval_request_id"], ["platform.approval_requests.id"],
            name="fk_support_impersonations_approval_request",
        ),
        sa.ForeignKeyConstraint(
            ["ended_by"], ["platform.platform_users.id"],
            name="fk_support_impersonations_ended_by",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"], ["platform.platform_users.id"],
            name="fk_support_impersonations_revoked_by",
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR revoked_at IS NULL",
            name="ck_support_impersonations_not_both_ended_and_revoked",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_support_impersonations_platform_user_active",
        "support_impersonations",
        ["platform_user_id"],
        postgresql_where=sa.text("ended_at IS NULL AND revoked_at IS NULL"),
        schema="platform",
    )
    op.create_index(
        "ix_support_impersonations_tenant_active",
        "support_impersonations",
        ["tenant_id"],
        postgresql_where=sa.text("ended_at IS NULL AND revoked_at IS NULL"),
        schema="platform",
    )
    op.create_index(
        "ix_support_impersonations_expires_at",
        "support_impersonations",
        ["expires_at"],
        postgresql_where=sa.text("ended_at IS NULL AND revoked_at IS NULL"),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_impersonations_expires_at",
        table_name="support_impersonations",
        schema="platform",
    )
    op.drop_index(
        "ix_support_impersonations_tenant_active",
        table_name="support_impersonations",
        schema="platform",
    )
    op.drop_index(
        "ix_support_impersonations_platform_user_active",
        table_name="support_impersonations",
        schema="platform",
    )
    op.drop_table("support_impersonations", schema="platform")
```

- [ ] **Step 2: Write the tenant migration**

```python
# alembic/tenant/versions/014_audit_log_impersonation_id.py
"""Phase 1.7 — add impersonation_id column to tenant_users and audit_log.

Both columns ship in 02a. They are populated in 02b (shadow tenant_user
creation on first mint; AuditableMixin extension reads from contextvars).

Revision: 014
Depends on: 013
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_users",
        sa.Column("impersonation_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_tenant_users_impersonation_id",
        "tenant_users",
        ["impersonation_id"],
        postgresql_where=sa.text("impersonation_id IS NOT NULL"),
    )

    op.add_column(
        "audit_log",
        sa.Column("impersonation_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_tenant_audit_log_impersonation_id",
        "audit_log",
        ["impersonation_id"],
        postgresql_where=sa.text("impersonation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_audit_log_impersonation_id", table_name="audit_log")
    op.drop_column("audit_log", "impersonation_id")
    op.drop_index("ix_tenant_users_impersonation_id", table_name="tenant_users")
    op.drop_column("tenant_users", "impersonation_id")
```

- [ ] **Step 3: Run migrations against the dev DB and verify**

```bash
make up
alembic upgrade head
# For tenant migrations we need a tenant schema; the test schema works:
alembic -c alembic-tenant.ini -x schema=tenant_test upgrade head
```
Expected: both heads advance. No errors.

Verify in psql:
```bash
docker compose exec postgres psql -U sacco -d sacco -c "\d platform.support_impersonations"
docker compose exec postgres psql -U sacco -d sacco -c "\d tenant_test.audit_log" | grep impersonation_id
docker compose exec postgres psql -U sacco -d sacco -c "\d tenant_test.tenant_users" | grep impersonation_id
```
Expected: table and both columns exist. Indexes present.

- [ ] **Step 4: Verify downgrade works**

```bash
alembic downgrade -1
alembic -c alembic-tenant.ini -x schema=tenant_test downgrade -1
```
Expected: both downgrade cleanly. Then re-upgrade head before committing.

- [ ] **Step 5: Commit**

```bash
git add alembic/platform/versions/008_support_impersonations.py \
        alembic/tenant/versions/014_audit_log_impersonation_id.py
git commit -m "feat(impersonation): migrations for support_impersonations + audit_log/tenant_users.impersonation_id"
```

---

## Task 2: Settings additions

**Files:**
- Modify: `app/core/config.py`

- [ ] **Step 1: Add two new fields to the `Settings` class**

Find the "JWT signing key infrastructure" block in `app/core/config.py`. Immediately AFTER `jwt_refresh_ttl_tenant_seconds`, add:

```python
    # Impersonation
    impersonation_max_minutes: int = 30  # max duration of a single impersonation session
    impersonation_default_required_approvals: int = 1  # checker quorum for start_impersonation
```

- [ ] **Step 2: Document in `.env.example`**

Append to `.env.example` (under the JWT section):

```
# ── Impersonation ─────────────────────────────────────────────────────────────
# Maximum minutes an approved impersonation session is valid.
IMPERSONATION_MAX_MINUTES=30
# Checker quorum required to approve a start_impersonation request.
IMPERSONATION_DEFAULT_REQUIRED_APPROVALS=1
```

- [ ] **Step 3: Sanity-check that settings load**

```bash
make test-fast T=tests/core/
```
Expected: existing core tests still pass (new fields have defaults).

- [ ] **Step 4: Commit**

```bash
git add app/core/config.py .env.example
git commit -m "feat(config): impersonation_max_minutes + impersonation_default_required_approvals"
```

---

## Task 3: SQLAlchemy model + conftest registration

**Files:**
- Create: `app/platform_/impersonations/__init__.py`
- Create: `app/platform_/impersonations/models.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Create the package marker**

```python
# app/platform_/impersonations/__init__.py
```
(empty file)

- [ ] **Step 2: Write the model**

```python
# app/platform_/impersonations/models.py
"""SQLAlchemy model for platform.support_impersonations.

Carries AuditableMixin so every insert/update/delete writes to platform.audit_log.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — used at runtime by SQLAlchemy

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class SupportImpersonation(AuditableMixin, Base):
    __tablename__ = "support_impersonations"
    __table_args__ = (
        CheckConstraint(
            "ended_at IS NULL OR revoked_at IS NULL",
            name="ck_support_impersonations_not_both_ended_and_revoked",
        ),
        Index(
            "ix_support_impersonations_platform_user_active",
            "platform_user_id",
            postgresql_where=text("ended_at IS NULL AND revoked_at IS NULL"),
        ),
        Index(
            "ix_support_impersonations_tenant_active",
            "tenant_id",
            postgresql_where=text("ended_at IS NULL AND revoked_at IS NULL"),
        ),
        Index(
            "ix_support_impersonations_expires_at",
            "expires_at",
            postgresql_where=text("ended_at IS NULL AND revoked_at IS NULL"),
        ),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    platform_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.platform_users.id", name="fk_support_impersonations_platform_user"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.tenants.id", name="fk_support_impersonations_tenant"),
        nullable=False,
    )
    # tenant_user_id is the shadow tenant_user created lazily on first mint
    # in 02b. Null until then.
    tenant_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "platform.approval_requests.id",
            name="fk_support_impersonations_approval_request",
        ),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    ended_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.platform_users.id", name="fk_support_impersonations_ended_by"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "platform.platform_users.id", name="fk_support_impersonations_revoked_by"
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
```

- [ ] **Step 3: Register the model in the conftest test_engine fixture**

In `tests/conftest.py`, find the block of `import app.modules.*` and `import app.platform_.*` calls inside `test_engine`. Add the impersonation import alongside (alphabetical):

```python
    import app.platform_.impersonations.models  # noqa: F401 — registers SupportImpersonation in Base.metadata
```

It should land between `import app.platform_.billing.models` and `import app.platform_.models`.

- [ ] **Step 4: Run the test suite to confirm the table is created cleanly**

```bash
make test-fast T=tests/platform_/billing/test_api_invoices.py
```
Expected: passes. (Just a smoke test — any platform test will exercise the schema bootstrap.)

- [ ] **Step 5: Commit**

```bash
git add app/platform_/impersonations/__init__.py \
        app/platform_/impersonations/models.py \
        tests/conftest.py
git commit -m "feat(impersonation): SupportImpersonation model"
```

---

## Task 4: Pydantic schemas

**Files:**
- Create: `app/platform_/impersonations/schemas.py`

- [ ] **Step 1: Write the schemas**

```python
# app/platform_/impersonations/schemas.py
"""Pydantic schemas for the impersonation API surface.

ImpersonationStartIn — body of POST /platform/impersonations (02b API)
ImpersonationOut     — response shape for GET endpoints (02b API)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ImpersonationStartIn(BaseModel):
    tenant_id: uuid.UUID
    reason: str = Field(min_length=10, max_length=500)


class ImpersonationOut(BaseModel):
    id: uuid.UUID
    platform_user_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_user_id: uuid.UUID | None
    reason: str
    approval_request_id: uuid.UUID | None
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    ended_by: uuid.UUID | None
    revoked_at: datetime | None
    revoked_by: uuid.UUID | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Commit**

```bash
git add app/platform_/impersonations/schemas.py
git commit -m "feat(impersonation): Pydantic schemas"
```

---

## Task 5: ImpersonationService — failing tests

**Files:**
- Create: `tests/platform_/impersonations/__init__.py`
- Create: `tests/platform_/impersonations/test_service.py`

- [ ] **Step 1: Create the package marker**

```python
# tests/platform_/impersonations/__init__.py
```
(empty file)

- [ ] **Step 2: Write the failing service tests**

```python
# tests/platform_/impersonations/test_service.py
"""Unit tests for ImpersonationService.

The service handles the lifecycle of an impersonation request:
    request → returns approval_request_id (no impersonation row yet)
    (checker approves via /platform/approvals, executor creates the row)
    end / revoke / queries → operate on the row

The executor is tested separately in test_executor.py.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.maker_checker.registry import approval_registry
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.service import ImpersonationService
from app.platform_.models import PlatformUser, Tenant


async def _seed(factory: async_sessionmaker[AsyncSession]) -> tuple[PlatformUser, Tenant]:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"u-{uuid.uuid4().hex[:6]}@test.example",
            full_name="U",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:6]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:6]}",
            name="T",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add_all([u, t])
    return u, t


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.support_impersonations"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


# Register a no-op stub for the executor — the real one lands in Task 6;
# the service tests do not exercise the executor.
approval_registry.setdefault(
    "platform.start_impersonation",
    AsyncMock(return_value={"impersonation_id": str(uuid.uuid4())}),
)


async def test_request_submits_approval(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user, tenant = await _seed(factory)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            approval = await ImpersonationService(s).request(
                platform_user_id=user.id,
                tenant_id=tenant.id,
                reason="Investigating reported balance discrepancy in tenant",
            )
            assert approval.operation_type == "platform.start_impersonation"
            assert approval.payload["platform_user_id"] == str(user.id)
            assert approval.payload["tenant_id"] == str(tenant.id)
            assert approval.payload["reason"].startswith("Investigating")
            assert approval.status == "pending"
    finally:
        await _cleanup(factory)


async def test_request_rejects_short_reason(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user, tenant = await _seed(factory)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            with pytest.raises(ValueError, match="reason"):
                await ImpersonationService(s).request(
                    platform_user_id=user.id,
                    tenant_id=tenant.id,
                    reason="short",
                )
    finally:
        await _cleanup(factory)


async def test_request_rejects_unknown_tenant(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user, _ = await _seed(factory)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            with pytest.raises(ValueError, match="not found"):
                await ImpersonationService(s).request(
                    platform_user_id=user.id,
                    tenant_id=uuid.uuid4(),
                    reason="Reason long enough to pass validation",
                )
    finally:
        await _cleanup(factory)


async def test_end_marks_ended(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user, tenant = await _seed(factory)
    # Create an impersonation row directly (simulating a post-approval state)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        imp = SupportImpersonation(
            platform_user_id=user.id,
            tenant_id=tenant.id,
            reason="r" * 10,
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(imp)
    imp_id = imp.id
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            await ImpersonationService(s).end(impersonation_id=imp_id, ended_by=user.id)

        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, imp_id)
            assert row is not None
            assert row.ended_at is not None
            assert row.ended_by == user.id
    finally:
        await _cleanup(factory)


async def test_revoke_marks_revoked_by_different_user(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, tenant = await _seed(factory)
    other, _ = await _seed(factory)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        imp = SupportImpersonation(
            platform_user_id=maker.id,
            tenant_id=tenant.id,
            reason="r" * 10,
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(imp)
    imp_id = imp.id
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            await ImpersonationService(s).revoke(
                impersonation_id=imp_id, revoked_by=other.id
            )
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, imp_id)
            assert row is not None
            assert row.revoked_at is not None
            assert row.revoked_by == other.id
    finally:
        await _cleanup(factory)


async def test_is_active_helper(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user, tenant = await _seed(factory)
    now = datetime.now(UTC)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        active = SupportImpersonation(
            platform_user_id=user.id, tenant_id=tenant.id, reason="r" * 10,
            started_at=now, expires_at=now + timedelta(minutes=10),
            created_at=now, updated_at=now,
        )
        expired = SupportImpersonation(
            platform_user_id=user.id, tenant_id=tenant.id, reason="r" * 10,
            started_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
            created_at=now, updated_at=now,
        )
        ended = SupportImpersonation(
            platform_user_id=user.id, tenant_id=tenant.id, reason="r" * 10,
            started_at=now, expires_at=now + timedelta(minutes=10),
            ended_at=now, ended_by=user.id,
            created_at=now, updated_at=now,
        )
        s.add_all([active, expired, ended])
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            svc = ImpersonationService(s)
            assert await svc.is_active(active.id) is True
            assert await svc.is_active(expired.id) is False
            assert await svc.is_active(ended.id) is False
    finally:
        await _cleanup(factory)


async def test_get_active_for_user_filters_correctly(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user_a, tenant = await _seed(factory)
    user_b, _ = await _seed(factory)
    now = datetime.now(UTC)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        # 2 active for user_a, 1 active for user_b
        for _ in range(2):
            s.add(
                SupportImpersonation(
                    platform_user_id=user_a.id, tenant_id=tenant.id, reason="r" * 10,
                    started_at=now, expires_at=now + timedelta(minutes=10),
                    created_at=now, updated_at=now,
                )
            )
        s.add(
            SupportImpersonation(
                platform_user_id=user_b.id, tenant_id=tenant.id, reason="r" * 10,
                started_at=now, expires_at=now + timedelta(minutes=10),
                created_at=now, updated_at=now,
            )
        )
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            svc = ImpersonationService(s)
            rows_a = await svc.get_active_for_user(platform_user_id=user_a.id)
            rows_b = await svc.get_active_for_user(platform_user_id=user_b.id)
            assert len(rows_a) == 2
            assert len(rows_b) == 1
    finally:
        await _cleanup(factory)
```

- [ ] **Step 3: Run the tests — they should all fail with ImportError**

```bash
make test-fast T=tests/platform_/impersonations/test_service.py
```
Expected: collection error / `ImportError: cannot import name 'ImpersonationService'`.

- [ ] **Step 4: Commit**

```bash
git add tests/platform_/impersonations/__init__.py \
        tests/platform_/impersonations/test_service.py
git commit -m "test(impersonation): service tests (red)"
```

---

## Task 6: ImpersonationService implementation

**Files:**
- Create: `app/platform_/impersonations/service.py`

- [ ] **Step 1: Write the service**

```python
# app/platform_/impersonations/service.py
"""Lifecycle management for platform-user → tenant impersonation sessions.

The service handles the *request*, *end*, *revoke*, and *queries* paths.
The *create-on-approval* path runs inside the maker-checker executor
(see executors.py), so callers never insert support_impersonations rows
directly.

All methods operate against a platform-scoped session (the caller is
responsible for SET LOCAL search_path TO platform + setting
session.sync_session.info["is_platform"]=True; the standard
get_platform_session dependency does both).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.config import get_settings
from app.modules.maker_checker.models.platform import PlatformApprovalRequest
from app.modules.maker_checker.service import ApprovalService
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.models import Tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ImpersonationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def request(
        self,
        *,
        platform_user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        reason: str,
    ) -> PlatformApprovalRequest:
        """Submit an ApprovalRequest for a new impersonation session.

        Returns the pending approval request; the impersonation row is
        created later by the executor when the checker approves.

        Raises:
            ValueError: if reason is too short, tenant unknown/inactive,
                or platform_user_id has no matching active user.
        """
        if len(reason.strip()) < 10:
            raise ValueError("reason must be at least 10 characters")

        tenant = await self._session.get(Tenant, tenant_id)
        if tenant is None or not tenant.is_active:
            raise ValueError(f"Tenant {tenant_id} not found or inactive")

        settings = get_settings()
        approval = await ApprovalService(self._session).submit(
            operation_type="platform.start_impersonation",
            payload={
                "platform_user_id": str(platform_user_id),
                "tenant_id": str(tenant_id),
                "reason": reason,
            },
            requested_by=platform_user_id,
            required_approvals=settings.impersonation_default_required_approvals,
        )
        return approval  # type: ignore[return-value]

    async def get_by_id(
        self, impersonation_id: uuid.UUID
    ) -> SupportImpersonation | None:
        return await self._session.get(SupportImpersonation, impersonation_id)

    async def get_active_for_user(
        self, *, platform_user_id: uuid.UUID
    ) -> list[SupportImpersonation]:
        """Return non-ended, non-revoked, non-expired impersonations for a user."""
        now = datetime.now(UTC)
        q = (
            select(SupportImpersonation)
            .where(
                SupportImpersonation.platform_user_id == platform_user_id,
                SupportImpersonation.ended_at.is_(None),
                SupportImpersonation.revoked_at.is_(None),
                SupportImpersonation.expires_at > now,
            )
            .order_by(SupportImpersonation.started_at.desc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_all_active(self) -> list[SupportImpersonation]:
        """Return ALL non-ended, non-revoked, non-expired impersonations."""
        now = datetime.now(UTC)
        q = (
            select(SupportImpersonation)
            .where(
                SupportImpersonation.ended_at.is_(None),
                SupportImpersonation.revoked_at.is_(None),
                SupportImpersonation.expires_at > now,
            )
            .order_by(SupportImpersonation.started_at.desc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def is_active(self, impersonation_id: uuid.UUID) -> bool:
        """True iff the row exists, is not ended, not revoked, not expired."""
        row = await self.get_by_id(impersonation_id)
        if row is None:
            return False
        if row.ended_at is not None or row.revoked_at is not None:
            return False
        return row.expires_at > datetime.now(UTC)

    async def end(
        self,
        *,
        impersonation_id: uuid.UUID,
        ended_by: uuid.UUID,
    ) -> SupportImpersonation:
        """Mark an impersonation as ended by its owner.

        The shadow tenant_user deactivation and session revocation
        happen in 02b — this sub-plan only marks the platform-side state.

        Idempotent: re-calling end() on an already-ended row is a no-op.
        """
        row = await self._session.get(SupportImpersonation, impersonation_id)
        if row is None:
            raise ValueError(f"Impersonation {impersonation_id} not found")
        if row.ended_at is None and row.revoked_at is None:
            row.ended_at = datetime.now(UTC)
            row.ended_by = ended_by
        return row

    async def revoke(
        self,
        *,
        impersonation_id: uuid.UUID,
        revoked_by: uuid.UUID,
    ) -> SupportImpersonation:
        """Forcibly revoke an impersonation (admin action).

        Caller must verify revoked_by has the authority. 02b's API gates
        this on a role check via P1.7-05.

        Self-revocation by the impersonator is permitted (functionally
        equivalent to end()). Distinguishing the two preserves audit
        intent.

        Idempotent: re-calling revoke() on an already-revoked row is a no-op.
        """
        row = await self._session.get(SupportImpersonation, impersonation_id)
        if row is None:
            raise ValueError(f"Impersonation {impersonation_id} not found")
        if row.revoked_at is None and row.ended_at is None:
            row.revoked_at = datetime.now(UTC)
            row.revoked_by = revoked_by
        return row

    @staticmethod
    def compute_expires_at(*, started_at: datetime | None = None) -> datetime:
        """Compute expires_at from settings.impersonation_max_minutes.

        Pure helper exposed so the executor and any future re-mint code
        can stay in sync.
        """
        settings = get_settings()
        anchor = started_at or datetime.now(UTC)
        return anchor + timedelta(minutes=settings.impersonation_max_minutes)
```

- [ ] **Step 2: Run the failing tests — they should pass now**

```bash
make test-fast T=tests/platform_/impersonations/test_service.py
```
Expected: all 7 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/platform_/impersonations/service.py
git commit -m "feat(impersonation): ImpersonationService (request/end/revoke/queries)"
```

---

## Task 7: Maker-checker executor

**Files:**
- Create: `app/platform_/impersonations/executors.py`
- Create: `tests/platform_/impersonations/test_executor.py`

- [ ] **Step 1: Write the failing executor integration test**

```python
# tests/platform_/impersonations/test_executor.py
"""Integration: request → checker approves via ApprovalService.approve
→ platform.start_impersonation executor inserts the support_impersonations row.

The test calls ApprovalService.approve directly (not via HTTP) because we
want to validate the executor's behaviour in isolation. The HTTP path is
tested in 02b.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Importing this module registers the executor in approval_registry.
import app.platform_.impersonations.executors  # noqa: F401
from app.modules.maker_checker.service import ApprovalService
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.service import ImpersonationService
from app.platform_.models import PlatformUser, Tenant


async def _seed(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[PlatformUser, PlatformUser, Tenant]:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        maker = PlatformUser(
            email=f"maker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Maker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        checker = PlatformUser(
            email=f"checker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Checker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        tenant = Tenant(
            slug=f"t-{uuid.uuid4().hex[:6]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:6]}",
            name="T", is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add_all([maker, checker, tenant])
    return maker, checker, tenant


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.support_impersonations"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


async def test_executor_creates_impersonation_row(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    try:
        # 1. Request the impersonation (creates pending ApprovalRequest)
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            approval = await ImpersonationService(s).request(
                platform_user_id=maker.id,
                tenant_id=tenant.id,
                reason="Investigating member balance issue reported by ops",
            )
            approval_id = approval.id

        # 2. Checker approves — executor runs inside the same tx
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            executed = await ApprovalService(s).approve(
                request_id=approval_id,
                actor_user_id=checker.id,
                comment="Verified ticket #1234",
            )
            assert executed.status == "executed"
            execution_result = executed.execution_result or {}
            impersonation_id = uuid.UUID(execution_result["impersonation_id"])

        # 3. Confirm a row exists and is well-formed
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, impersonation_id)
            assert row is not None
            assert row.platform_user_id == maker.id
            assert row.tenant_id == tenant.id
            assert row.tenant_user_id is None  # 02b populates this
            assert row.approval_request_id == approval_id
            assert row.ended_at is None
            assert row.revoked_at is None
            now = datetime.now(UTC)
            assert row.started_at <= now
            assert row.expires_at > now
            # Expires within 30 min by default
            assert row.expires_at <= now + timedelta(minutes=31)
    finally:
        await _cleanup(factory)


async def test_executor_idempotent_on_re_execution(test_engine: AsyncEngine) -> None:
    """If executor runs twice for the same approval payload (shouldn't happen
    but defensive), the second run should not create a duplicate row.

    The executor uses approval_request_id as the natural key for dedup.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    try:
        # Request + approve (creates row #1)
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            approval = await ImpersonationService(s).request(
                platform_user_id=maker.id,
                tenant_id=tenant.id,
                reason="Investigating member balance issue reported by ops",
            )
            approval_id = approval.id

        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            await ApprovalService(s).approve(
                request_id=approval_id, actor_user_id=checker.id,
            )

        # Call the executor again directly with the same payload
        from app.platform_.impersonations.executors import (
            execute_start_impersonation,
        )
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            result = await execute_start_impersonation(
                s,
                {
                    "platform_user_id": str(maker.id),
                    "tenant_id": str(tenant.id),
                    "reason": "Investigating member balance issue reported by ops",
                    "approval_request_id": str(approval_id),
                },
            )
            assert result.get("idempotent") is True

        # Still only one row
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            rows = (
                await s.execute(
                    select(SupportImpersonation).where(
                        SupportImpersonation.approval_request_id == approval_id
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Write the executor**

```python
# app/platform_/impersonations/executors.py
"""Maker-checker executor for impersonation start.

Registered at import time via @approval_executor("platform.start_impersonation").
Imported at app startup from app/main.py so the decorator runs.

The executor runs inside the platform session of the checker's approval
HTTP request — same transaction as the ApprovalRequest status flip. If this
function raises, ApprovalService catches the exception and marks the request
status='execution_failed' (the row stays uncreated).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.modules.maker_checker.registry import approval_executor
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.service import ImpersonationService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("platform.start_impersonation")  # type: ignore[misc]
async def execute_start_impersonation(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Create the support_impersonations row when a request is approved.

    payload keys:
        platform_user_id: str (UUID) — the requester
        tenant_id:        str (UUID) — target tenant
        reason:           str
        approval_request_id: str (UUID) — set by ApprovalService.approve at
            execute time; used as the idempotency key

    Returns:
        {"impersonation_id": "<uuid>", "expires_at": "<iso>"}

    Idempotency: if a row already exists for approval_request_id, returns
    {"impersonation_id": "<uuid>", "idempotent": True} without creating
    a second row.
    """
    platform_user_id = uuid.UUID(payload["platform_user_id"])
    tenant_id = uuid.UUID(payload["tenant_id"])
    reason = str(payload["reason"])
    # approval_request_id is injected by ApprovalService._execute when the
    # executor is invoked. If the executor is invoked directly (e.g. in tests),
    # the caller is responsible for passing it.
    approval_request_id_raw = payload.get("approval_request_id")
    approval_request_id = (
        uuid.UUID(str(approval_request_id_raw))
        if approval_request_id_raw is not None
        else None
    )

    # Idempotency check
    if approval_request_id is not None:
        existing = await session.scalar(
            select(SupportImpersonation).where(
                SupportImpersonation.approval_request_id == approval_request_id
            )
        )
        if existing is not None:
            return {
                "impersonation_id": str(existing.id),
                "expires_at": existing.expires_at.isoformat(),
                "idempotent": True,
            }

    now = datetime.now()  # naive; SQLAlchemy will coerce based on column tz
    row = SupportImpersonation(
        platform_user_id=platform_user_id,
        tenant_id=tenant_id,
        reason=reason,
        approval_request_id=approval_request_id,
        started_at=now,
        expires_at=ImpersonationService.compute_expires_at(),
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()

    return {
        "impersonation_id": str(row.id),
        "expires_at": row.expires_at.isoformat(),
    }
```

- [ ] **Step 3: Wire the executor's approval_request_id into the payload**

`ApprovalService._execute` currently calls `executor(session, request.payload)` — it does NOT inject `approval_request_id`. We need it for idempotency. Two options:

(a) Modify `ApprovalService._execute` to inject `approval_request_id` into the payload before calling the executor. Risk: changes signature for ALL executors.

(b) Have `ImpersonationService.request` put `approval_request_id` into the payload at submit time. Problem: the approval ID doesn't exist yet at submit time.

(c) Post-flush the payload inside `submit` — after the row is created, update payload to include `approval_request_id`. Possible but feels hacky.

**Adopt option (a)** — it's the most general, and adding `approval_request_id` to every executor's payload is harmless (existing executors just ignore the extra key).

Modify `app/modules/maker_checker/service.py:202-232` — the `_execute` method. Find:

```python
    async def _execute(self, request: Any) -> None:
        executor = approval_registry[request.operation_type]
        try:
            result = await executor(self._session, request.payload)
```

Replace with:

```python
    async def _execute(self, request: Any) -> None:
        executor = approval_registry[request.operation_type]
        # Inject the request's id into the payload so executors can use it
        # for idempotency or for back-linking. Existing executors that ignore
        # the extra key are unaffected.
        enriched_payload = {**request.payload, "approval_request_id": str(request.id)}
        try:
            result = await executor(self._session, enriched_payload)
```

- [ ] **Step 4: Run executor tests — they should pass**

```bash
make test-fast T=tests/platform_/impersonations/test_executor.py
```
Expected: 2 tests pass.

- [ ] **Step 5: Run the full maker_checker tests to confirm no regression**

```bash
make test-fast T=tests/modules/maker_checker/
```
Expected: existing tests still pass — the extra `approval_request_id` payload key is ignored by existing executors.

- [ ] **Step 6: Commit**

```bash
git add app/platform_/impersonations/executors.py \
        app/modules/maker_checker/service.py \
        tests/platform_/impersonations/test_executor.py
git commit -m "feat(impersonation): platform.start_impersonation executor + ApprovalService payload enrichment"
```

---

## Task 8: Register the executor at startup

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add the import**

In `app/main.py`, find the existing executor imports (around lines 16, 22, 25, 28, 30, 33):

```python
from app.modules.credit import executors as _credit_executors  # noqa: F401
...
from app.platform_.billing import executors as _billing_executors  # noqa: F401
```

Add immediately after the billing executor import:

```python
from app.platform_.impersonations import executors as _impersonation_executors  # noqa: F401
```

- [ ] **Step 2: Sanity check**

```bash
make test-fast T=tests/platform_/impersonations/
```
Expected: still pass; the registry now contains `platform.start_impersonation` on app boot.

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat(impersonation): register executor at app startup"
```

---

## Task 9: Architectural Decision Record

**Files:**
- Create: `docs/superpowers/decisions/2026-06-02-impersonation-design.md`

- [ ] **Step 1: Write the ADR**

```markdown
# ADR-002: Platform-User Impersonation Design

**Date:** 2026-06-02
**Status:** Accepted (Phase 1.7, sub-plans 02a + 02b)
**Deciders:** Liam / Claude
**Context:** ADR-001 (`2026-05-21-iam-architecture.md`) §7 mandated that cross-context access by platform users to tenant routes must go through `platform.support_impersonations`. That ADR named the table but did not specify the lifecycle, the token model, the audit semantics, or how downstream tenant code would see the actor identity. This ADR locks all of that in before 02b writes the HTTP integration.

---

## Decisions

### 1. Lifecycle: request → approve → mint → use → end/revoke

Five distinct states:

1. **request** — `POST /platform/impersonations` (02b) submits an `ApprovalRequest` with `operation_type="platform.start_impersonation"`. No `support_impersonations` row exists yet; only the pending approval.
2. **approve** — A checker calls `POST /platform/approvals/{id}/approve` (P1.7-01). `ApprovalService.approve()` invokes the executor, which inserts the `support_impersonations` row with `started_at=now()`, `expires_at=now()+IMPERSONATION_MAX_MINUTES`, and `approval_request_id=<id>`. Self-approval is rejected by `ApprovalService`. Quorum is configurable per env (`IMPERSONATION_DEFAULT_REQUIRED_APPROVALS`, default 1).
3. **mint** — `POST /platform/impersonations/{id}/mint-tenant-token` (02b). Lazily creates the shadow `tenant_users` row in the target tenant's schema (decision §3), then issues a standard tenant access+refresh token with the shadow user's `sub`. The token is a normal tenant JWT — no new claims, no audience change.
4. **use** — The platform user calls tenant routes with the minted token + `X-Tenant-Slug`. The existing `get_current_tenant_user_jwt` dep validates the token and returns the shadow `TenantUser`. Downstream code uses `user.id` (the shadow id) for `posted_by` / `recorded_by` etc. — those columns are plain UUID without FK constraints, so no integrity issues.
5. **end / revoke** — `DELETE /platform/impersonations/{id}` (02b, by the impersonator) sets `ended_at`. `POST /platform/impersonations/{id}/revoke` (02b, by another admin) sets `revoked_at`. Both deactivate the shadow `tenant_user` and revoke all its tenant sessions.

### 2. Maximum duration: 30 minutes, configurable

`IMPERSONATION_MAX_MINUTES` defaults to 30. Production may tune. Sessions auto-expire — no separate Celery beat job is required, because `expires_at > now()` is part of every `is_active` check.

### 3. Shadow tenant_users: lazy creation on first mint

Rather than rewriting `get_current_tenant_user_jwt` to handle a synthetic non-DB identity, we create a real `tenant_users` row per impersonation session:

- `email` = `f"imp.{impersonation_id.hex[:12]}@platform.local"` — guaranteed unique, clearly non-real, never collides with a real tenant user's address
- `full_name` = `<platform_user.full_name> + " (Platform Admin Impersonation)"`
- `is_active` = `true`
- `is_admin` = `true`
- `hashed_password` = `NULL` (cannot self-login)
- `impersonation_id` = the `support_impersonations.id` (new column, indexed where NOT NULL)

The shadow row is created **lazily on the first `mint-tenant-token` call** for this impersonation, and reused for subsequent mints during the same session. On `end` / `revoke`, `is_active` flips to `false` and the row stays for audit traceability.

**Trade-off:** an extra `tenant_users` row per impersonation session, with the `impersonation_id` column marking it as a shadow. The portal's `/settings/users` list (P1.7-04) MUST filter `impersonation_id IS NULL` so shadows don't leak into the operator's UI.

### 4. Audit identity: actor_type='tenant_user', actor_id=shadow_id, impersonation_id=link

Every audit_log row written during an impersonated request gets:
- `actor_type = 'tenant_user'` (NOT `'platform_user'`)
- `actor_id = <shadow_tenant_user.id>`
- `actor_label = "<platform_user.email> (impersonating)"`
- `impersonation_id = <support_impersonations.id>` (new column on `audit_log`)

This makes the audit trail uniformly tenant-actor-shaped (no `posted_by` resolves to a non-existent tenant_user), while `impersonation_id` provides instant traceability back to the real platform actor. The portal's audit viewer (sub-plan 31 of Portal v1) joins on `impersonation_id` to resolve and display the real actor identity.

The mechanism: 02b extends `AuditableMixin._actor_context` to read `impersonation_id` from structlog contextvars. The tenant JWT dep (extended in 02b) binds `impersonation_id` to contextvars when the resolved tenant_user has a non-null `impersonation_id` column.

### 5. Tokens: regular tenant JWT with shadow user as `sub`

No new claim. No new audience. No new TTL. The shadow user has a `tenant_users.id` like any other; the minted token has `sub=<that id>`, `aud=tenant:<slug>`, normal access TTL (15 min). The shadow lives in the tenant schema, so the existing `get_current_tenant_user_jwt` dep resolves it transparently.

Re-mint within the impersonation window is unrestricted: the impersonator can call `mint-tenant-token` repeatedly to get fresh access tokens (or use the refresh token flow). Every mint creates a new tenant session row tied to the same shadow user.

### 6. Self-approval still forbidden

`ApprovalService.approve` already rejects `actor_user_id == request.requested_by`. This applies to impersonation requests too — the requester cannot approve their own request even if they hold a sufficiently privileged role.

### 7. Listing impersonations is restricted

- `GET /platform/impersonations/active` (mine) — any authenticated platform user.
- `GET /platform/impersonations/all` (system-wide) — admin role or above (P1.7-05).

Both list endpoints exclude shadow `tenant_users` from any tenant-user listing API.

### 8. Failure modes

| Scenario | Behaviour |
|----------|-----------|
| Executor fails inserting `support_impersonations` | `ApprovalService._execute` catches; request `status='execution_failed'`; no row, no shadow user. The maker can request again. |
| Mint called before approval | 404 — no impersonation row exists with that id. |
| Mint called after expiry / revoke / end | 410 Gone (02b). |
| Tenant request with an expired impersonation token | 401 — the shadow user's tenant session is revoked when `end` / `revoke` runs. Tokens still valid until 15-min expiry returns 401 from the JTI check. |
| Maker tries to revoke their own session | Returns 200; treated as `end()` (their `ended_at` is set). Audit captures the action. |

### 9. What is explicitly NOT in scope (Phase 1.7)

- **MFA step-up for impersonation start.** Future hardening; the maker-checker quorum is the gate in v1.
- **Per-tenant policy on impersonation** (e.g., a tenant opting out). Tenants are notified via audit log; opt-out is a future control.
- **Read-only impersonation mode.** v1 impersonations have full tenant_user privileges of the shadow user (i.e., `is_admin=true`). A read-only mode would require a permission flag on the shadow user; deferred.
- **Cross-tenant impersonation in a single session.** A session is scoped to one tenant. Operating across tenants requires multiple sessions.

---

## CLAUDE.md Contracts Added (02a)

See the Impersonation contracts subsection in CLAUDE.md (added in Task 10 of this sub-plan). The full set of contracts is augmented in 02b once the HTTP and audit-mixin pieces land.

## Consequences

- Phase 1.7 can ship 02a as a backend-only, schema-only PR. The data layer becomes correct and reviewable in isolation.
- 02b becomes a focused PR about cross-context auth wiring with no schema surprises.
- Portal sub-plan 14 (Tenants edit/suspend + impersonation entry point) has a clean API contract once 02b lands.
- ADR-001 §7 is now implementable. Future hardening (MFA step-up, read-only mode, per-tenant opt-out) can extend this design without rewriting it.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/decisions/2026-06-02-impersonation-design.md
git commit -m "docs(adr): ADR-002 platform-user impersonation design"
```

---

## Task 10: CLAUDE.md contracts (data-layer partial)

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a new section after the IAM module contracts**

In `CLAUDE.md`, find `## IAM module contracts (do not violate)`. Immediately AFTER that section (before the next `##` heading), insert:

```markdown
## Impersonation contracts (do not violate)

These contracts are partial — 02a (data layer) establishes the foundational rules below. 02b adds the HTTP, token mint, AuditableMixin, and tenant JWT dep contracts.

- `platform.support_impersonations` rows are created **only** by the
  `platform.start_impersonation` maker-checker executor in
  `app/platform_/impersonations/executors.py`. Direct insertion is forbidden.
  Direct UPDATE is forbidden except via `ImpersonationService.end()` and
  `ImpersonationService.revoke()`.
- `ImpersonationService.request()` is the only path to submitting a
  `platform.start_impersonation` approval. The reason field must be at least
  10 characters. The tenant must exist and be active at request time.
- Self-approval is rejected by `ApprovalService.approve()` (existing rule,
  applies here too). The requester cannot approve their own impersonation.
- Default required-approvals quorum is `IMPERSONATION_DEFAULT_REQUIRED_APPROVALS`
  (settings; default 1). Production tenants may raise this.
- `IMPERSONATION_MAX_MINUTES` (default 30) caps the session duration. Sessions
  expire automatically — the `is_active` check (used by every downstream gate
  in 02b) includes `expires_at > now()`. No Celery beat job is required.
- Once a row is in the `ended` or `revoked` state, it is terminal — the
  `ck_support_impersonations_not_both_ended_and_revoked` constraint disallows
  setting both. To "re-impersonate" after end/revoke, request a new
  impersonation (new approval cycle).
- `ApprovalService._execute` enriches the executor payload with
  `approval_request_id` (added in 02a). Executors should treat that key as
  reserved; existing executors that ignore it are unaffected.
- The full set of impersonation contracts — token mint, shadow tenant_user
  pattern, audit identity, tenant JWT dep extension — is documented after
  02b merges.

See `docs/superpowers/decisions/2026-06-02-impersonation-design.md` for the
full design rationale.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): impersonation contracts (data layer)"
```

---

## Task 11: Final verification

- [ ] **Step 1: Full lint + type-check + test suite**

```bash
make lint
make mypy
make test
```
Expected: all clean. Specifically: new test files appear in the pass count, no existing regressions, no mypy errors in the new module.

- [ ] **Step 2: Manual migration up/down**

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
alembic -c alembic-tenant.ini -x schema=tenant_test upgrade head
alembic -c alembic-tenant.ini -x schema=tenant_test downgrade -1
alembic -c alembic-tenant.ini -x schema=tenant_test upgrade head
```
Expected: clean up/down/up cycle for both platform and tenant migrations.

- [ ] **Step 3: PR**

```bash
git push -u origin feat/phase-1-7/02a-impersonation-data
gh pr create --title "feat(impersonation): data layer + service + executor" --body "$(cat <<'EOF'
## Summary
- New `platform.support_impersonations` table and `SupportImpersonation` SQLAlchemy model
- Adds nullable `impersonation_id` columns to `tenant.tenant_users` and `tenant.audit_log` (populated in 02b)
- `ImpersonationService`: request (submits approval), end, revoke, queries, is_active, compute_expires_at
- `platform.start_impersonation` maker-checker executor — creates the impersonation row on checker approval
- `ApprovalService._execute` payload enrichment: injects `approval_request_id` so executors can dedupe (existing executors ignore the new key)
- Settings: `IMPERSONATION_MAX_MINUTES` (default 30), `IMPERSONATION_DEFAULT_REQUIRED_APPROVALS` (default 1)
- ADR-002 locks the cross-context design before 02b writes the HTTP layer
- Partial CLAUDE.md contracts; full contracts land with 02b

## Out of scope
- HTTP API surface, token mint, tenant JWT dep extension, AuditableMixin update, e2e cross-context test — all in 02b.

## Test plan
- [ ] `make test-fast T=tests/platform_/impersonations/` — 9 tests (7 service + 2 executor)
- [ ] `make test-fast T=tests/modules/maker_checker/` — confirm no regression from payload enrichment
- [ ] `make ci` (ruff + mypy + full pytest)
- [ ] Migration up/down cycle (platform + tenant)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opens cleanly, CI green.

---

## Acceptance criteria (sub-plan exits here)

- [ ] Migrations 008 (platform) and 014 (tenant) created, reversible, applied
- [ ] `SupportImpersonation` model + Pydantic schemas implemented and registered in conftest
- [ ] `ImpersonationService` covers request/end/revoke/queries with passing unit tests (7 tests)
- [ ] `platform.start_impersonation` executor creates the row with proper idempotency (2 tests)
- [ ] `ApprovalService._execute` enriches payload with `approval_request_id` — existing executors unchanged
- [ ] `app/main.py` imports `_impersonation_executors` so the decorator registers at boot
- [ ] ADR-002 written and committed
- [ ] CLAUDE.md gains the partial "Impersonation contracts" subsection
- [ ] `make ci` clean
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** add `api.py` to `app/platform_/impersonations/`. That's 02b. If you find yourself wanting to add an HTTP route, stop — the data layer is the only scope here.
- **Do not** modify `AuditableMixin` or the tenant JWT dep. Those are 02b. The columns shipped here are nullable so 02a's tests don't depend on the mixin change.
- **Do not** create shadow `tenant_users`. That's 02b's responsibility (lazy on first mint).
- The `ApprovalService._execute` payload enrichment is cross-cutting. Run the FULL `make test` suite, not just the new tests, to confirm no executor relies on the absence of the `approval_request_id` key.
- The `compute_expires_at` static method is exposed because 02b's mint endpoint may want to enforce token TTL ≤ remaining impersonation time. Don't remove it.
- If the migration cannot drop the index because PostgreSQL holds a session reference, run `docker compose restart postgres` and re-try the downgrade. This is a known dev-env quirk, not a migration bug.
- If `make mypy` flags the executor's `payload.get("approval_request_id")` as `Any`, that's expected — payload is `dict[str, Any]`. Don't add a TypedDict for it; the variance with other executors isn't worth the indirection.
