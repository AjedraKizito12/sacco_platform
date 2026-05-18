# Core Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core infrastructure module: dual-schema audit log, transactional outbox with SKIP LOCKED relay, and configurable-quorum maker-checker.

**Architecture:** Three subsystems share a dual-table pattern (identical structure in `platform` schema and each `tenant_*` schema). Session identity determines which table is written to. Audit mixin instruments SQLAlchemy mapper events; outbox uses `EventPublisher.publish()` as the sole event-emission path; maker-checker dispatches registered executors inline on quorum.

**Tech Stack:** SQLAlchemy 2.0 async, asyncpg, aio-pika, Celery 5 + Redis broker, pytest-asyncio (auto mode, already configured), structlog context vars.

---

## File Map

```
CREATE app/core/audit/__init__.py
CREATE app/core/audit/models.py
CREATE app/core/audit/mixin.py
CREATE app/core/audit/service.py
CREATE app/core/outbox/__init__.py
CREATE app/core/outbox/models.py
CREATE app/core/outbox/publisher.py
CREATE app/core/outbox/worker.py
CREATE app/core/outbox/retention.py
CREATE app/modules/__init__.py
CREATE app/modules/maker_checker/__init__.py
CREATE app/modules/maker_checker/models/__init__.py
CREATE app/modules/maker_checker/models/mixins.py
CREATE app/modules/maker_checker/models/platform.py
CREATE app/modules/maker_checker/models/tenant.py
CREATE app/modules/maker_checker/registry.py
CREATE app/modules/maker_checker/service.py
CREATE app/modules/maker_checker/schemas.py
CREATE app/modules/maker_checker/api.py
CREATE app/workers/__init__.py
CREATE app/workers/celery_app.py
CREATE alembic/platform/versions/001_core_platform.py
CREATE alembic/tenant/versions/001_core_tenant.py
CREATE tests/core/audit/__init__.py
CREATE tests/core/audit/test_audit_mixin.py
CREATE tests/core/audit/test_audit_service.py
CREATE tests/core/outbox/__init__.py
CREATE tests/core/outbox/test_publisher.py
CREATE tests/core/outbox/test_worker.py
CREATE tests/core/outbox/test_retention.py
CREATE tests/modules/__init__.py
CREATE tests/modules/maker_checker/__init__.py
CREATE tests/modules/maker_checker/test_service.py
CREATE tests/modules/maker_checker/test_registry.py
CREATE tests/modules/maker_checker/test_api.py
CREATE .github/workflows/lint.yml
MODIFY app/core/db.py          — add is_platform flag to get_platform_session
MODIFY alembic/platform/env.py — import new platform models
MODIFY alembic/tenant/env.py   — import new tenant models
MODIFY app/main.py             — register maker_checker router in lifespan
MODIFY tests/conftest.py       — add db fixtures, platform/tenant session fixtures
MODIFY CLAUDE.md               — append core module contracts
```

---

## Task 1: Expand test infrastructure

**Files:**
- Modify: `tests/conftest.py`

Integration tests need a real Postgres with both `platform` and `tenant_test` schemas. All tests share one schema-setup per session; each test gets a rolled-back transaction.

- [ ] **Replace `tests/conftest.py`** with:

```python
import asyncio
import os

import pytest
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sacco:sacco@localhost:5432/sacco_test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-used-in-production")

TEST_TENANT_SCHEMA = "tenant_test"
TEST_TENANT_SLUG = "test-tenant"

# ── structlog: silence during tests unless DEBUG ──────────────────────────────
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(40),  # ERROR level
    logger_factory=structlog.PrintLoggerFactory(),
)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def test_engine():
    """One engine per test session. Schemas created once; dropped on teardown."""
    from app.core.db import Base  # noqa: F401 — triggers metadata registration

    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS platform"))
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {TEST_TENANT_SCHEMA}"))
        # Platform tables have schema="platform" in __table_args__ → created there.
        # Tenant tables have no schema → created wherever search_path points.
        await conn.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_TENANT_SCHEMA} CASCADE"))
        await conn.execute(text("DROP SCHEMA IF EXISTS platform CASCADE"))

    await engine.dispose()


@pytest.fixture
async def platform_session(test_engine) -> AsyncSession:
    """Rolled-back platform session per test."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            yield session
            await session.rollback()


@pytest.fixture
async def tenant_session(test_engine) -> AsyncSession:
    """Rolled-back tenant session per test."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
            )
            yield session
            await session.rollback()
```

- [ ] **Run existing tests to confirm nothing is broken:**

```bash
cd /home/liam/projects/sacco-platform && source venv/bin/activate
pytest tests/core/test_config.py tests/core/test_db.py -v
```

Expected: all pass (these tests don't touch the DB).

---

## Task 2: Migrations — platform schema

**Files:**
- Create: `alembic/platform/versions/001_core_platform.py`

- [ ] **Create the file:**

```python
"""
Create core tables in the platform schema: audit_log, outbox_events,
processed_events, approval_requests, approval_actions.

Platform and tenant Alembic chains are independent.
Version numbers do not correlate across chains.
001 in platform and 001 in tenant are unrelated migrations.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")

    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_label", sa.Text(), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        schema="platform",
    )
    op.create_index("ix_platform_audit_log_table_record", "audit_log", ["table_name", "record_id"], schema="platform")
    op.create_index("ix_platform_audit_log_occurred_at", "audit_log", [sa.text("occurred_at DESC")], schema="platform")

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_dead_lettered", sa.Boolean(), server_default="false", nullable=False),
        schema="platform",
    )
    op.create_index(
        "ix_platform_outbox_pending",
        "outbox_events",
        ["next_attempt_at"],
        schema="platform",
        postgresql_where=sa.text("published_at IS NULL AND is_dead_lettered = false"),
    )

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("consumer_name", sa.Text(), nullable=False),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("event_id", "consumer_name"),
        schema="platform",
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("operation_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("required_approvals", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("execution_result", sa.JSON(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        schema="platform",
    )

    op.create_table(
        "approval_actions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("approval_request_id", sa.UUID(), sa.ForeignKey("platform.approval_requests.id"), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("acted_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.UniqueConstraint("approval_request_id", "actor_user_id", name="uq_platform_approval_actions_no_double_vote"),
        schema="platform",
    )

    # Trigger: prevent maker from being checker
    op.execute("""
        CREATE OR REPLACE FUNCTION platform.check_approval_self_action()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            maker UUID;
        BEGIN
            SELECT requested_by INTO maker
              FROM platform.approval_requests
             WHERE id = NEW.approval_request_id;
            IF NEW.actor_user_id = maker THEN
                RAISE EXCEPTION 'maker cannot be checker (self-approval forbidden)';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_platform_approval_actions_no_self_approval
        BEFORE INSERT ON platform.approval_actions
        FOR EACH ROW EXECUTE FUNCTION platform.check_approval_self_action();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_platform_approval_actions_no_self_approval ON platform.approval_actions")
    op.execute("DROP FUNCTION IF EXISTS platform.check_approval_self_action()")
    op.drop_table("approval_actions", schema="platform")
    op.drop_table("approval_requests", schema="platform")
    op.drop_table("processed_events", schema="platform")
    op.drop_table("outbox_events", schema="platform")
    op.drop_table("audit_log", schema="platform")
```

- [ ] **Verify migration runs (requires Docker Compose running):**

```bash
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco_test \
  alembic -c alembic.ini upgrade head
```

Expected: `Running upgrade  -> 001, Create core tables in the platform schema`

---

## Task 3: Migrations — tenant schema

**Files:**
- Create: `alembic/tenant/versions/001_core_tenant.py`

- [ ] **Create the file:**

```python
"""
Create core tables in the tenant schema: audit_log, outbox_events,
processed_events, approval_requests, approval_actions.

Platform and tenant Alembic chains are independent.
Version numbers do not correlate across chains.
001 in platform and 001 in tenant are unrelated migrations.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables are created in the schema set by TENANT_SCHEMA env var (via SET search_path in env.py).
    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_label", sa.Text(), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
    )
    op.create_index("ix_tenant_audit_log_table_record", "audit_log", ["table_name", "record_id"])
    op.create_index("ix_tenant_audit_log_occurred_at", "audit_log", [sa.text("occurred_at DESC")])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_dead_lettered", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(
        "ix_tenant_outbox_pending",
        "outbox_events",
        ["next_attempt_at"],
        postgresql_where=sa.text("published_at IS NULL AND is_dead_lettered = false"),
    )

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("consumer_name", sa.Text(), nullable=False),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("event_id", "consumer_name"),
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("operation_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("required_approvals", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("execution_result", sa.JSON(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )

    op.create_table(
        "approval_actions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("approval_request_id", sa.UUID(), sa.ForeignKey("approval_requests.id"), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("acted_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.UniqueConstraint("approval_request_id", "actor_user_id", name="uq_tenant_approval_actions_no_double_vote"),
    )

    # Dynamically name the function/trigger using the actual schema from search_path
    op.execute("""
        DO $$
        DECLARE
            schema_name text := current_schema();
        BEGIN
            EXECUTE format($f$
                CREATE OR REPLACE FUNCTION %I.check_approval_self_action()
                RETURNS trigger LANGUAGE plpgsql AS $fn$
                DECLARE maker UUID;
                BEGIN
                    SELECT requested_by INTO maker FROM %I.approval_requests WHERE id = NEW.approval_request_id;
                    IF NEW.actor_user_id = maker THEN
                        RAISE EXCEPTION 'maker cannot be checker';
                    END IF;
                    RETURN NEW;
                END;
                $fn$
            $f$, schema_name, schema_name);

            EXECUTE format($f$
                CREATE TRIGGER trg_approval_actions_no_self_approval
                BEFORE INSERT ON %I.approval_actions
                FOR EACH ROW EXECUTE FUNCTION %I.check_approval_self_action()
            $f$, schema_name, schema_name);
        END;
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_approval_actions_no_self_approval ON approval_actions")
    op.execute("DROP FUNCTION IF EXISTS check_approval_self_action()")
    op.drop_table("approval_actions")
    op.drop_table("approval_requests")
    op.drop_table("processed_events")
    op.drop_table("outbox_events")
    op.drop_table("audit_log")
```

- [ ] **Verify tenant migration runs:**

```bash
TENANT_SCHEMA=tenant_acme DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco_test \
  alembic -c alembic-tenant.ini upgrade head
```

Expected: `Running upgrade  -> 001, Create core tables in the tenant schema`

---

## Task 4: Audit models

**Files:**
- Create: `app/core/audit/__init__.py`
- Create: `app/core/audit/models.py`

- [ ] **Create `app/core/audit/__init__.py`:**

```python
from app.core.audit.mixin import AuditableMixin
from app.core.audit.service import PlatformAuditService, TenantAuditService

__all__ = ["AuditableMixin", "PlatformAuditService", "TenantAuditService"]
```

(This file will be valid once mixin.py and service.py exist in later tasks. For now, create it empty and fill it last.)

Actually create it as:

```python
# Populated after mixin.py and service.py are created (Tasks 5 and 6).
```

- [ ] **Create `app/core/audit/models.py`:**

```python
from __future__ import annotations

import uuid

from sqlalchemy import Index, Text, UUID
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class _AuditLogBase:
    """Column definitions shared by platform and tenant audit_log tables."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)  # insert | update | delete
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)  # platform_user | tenant_user | system | api_client
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlatformAuditLog(_AuditLogBase, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_platform_audit_log_table_record", "table_name", "record_id"),
        {"schema": "platform"},
    )


class TenantAuditLog(_AuditLogBase, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_tenant_audit_log_table_record", "table_name", "record_id"),
    )
```

- [ ] **Run ruff + mypy:**

```bash
ruff check app/core/audit/ && mypy app/core/audit/models.py
```

Expected: no errors.

- [ ] **Commit:**

```bash
git add app/core/audit/ alembic/platform/versions/001_core_platform.py alembic/tenant/versions/001_core_tenant.py tests/conftest.py
git commit -m "feat: add audit models and core migrations (001)"
```

---

## Task 5: AuditableMixin

**Files:**
- Create: `app/core/audit/mixin.py`

The mixin registers SQLAlchemy mapper events on subclasses. In `after_update`, attribute history gives us the pre-flush values. Actor context is read from structlog context vars.

- [ ] **Create `app/core/audit/mixin.py`:**

```python
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import InstanceState, Session, attributes


def _serialize(val: Any) -> Any:
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return str(val)
    return val


def _snapshot(mapper: Any, target: Any) -> dict[str, Any]:
    return {
        attr.key: _serialize(getattr(target, attr.key, None))
        for attr in mapper.column_attrs
    }


def _before_snapshot(mapper: Any, target: Any) -> dict[str, Any]:
    """Return pre-flush values for all columns (for update events)."""
    result: dict[str, Any] = {}
    for attr in mapper.column_attrs:
        hist = attributes.get_history(target, attr.key)
        result[attr.key] = _serialize(hist.deleted[0] if hist.deleted else getattr(target, attr.key, None))
    return result


def _actor_context() -> dict[str, Any]:
    ctx = structlog.contextvars.get_contextvars()
    return {
        "actor_type": ctx.get("actor_type", "system"),
        "actor_id": ctx.get("actor_id"),
        "actor_label": ctx.get("actor_label"),
        "request_id": ctx.get("request_id"),
    }


def _write_audit(
    target: Any,
    operation: str,
    before_state: dict | None,
    after_state: dict | None,
) -> None:
    from app.core.audit.models import PlatformAuditLog, TenantAuditLog

    session = Session.object_session(target)
    if session is None:
        return

    ctx = _actor_context()
    table_args = getattr(target.__class__, "__table_args__", None)
    is_platform = (
        isinstance(table_args, dict) and table_args.get("schema") == "platform"
    ) or (
        isinstance(table_args, tuple)
        and any(isinstance(a, dict) and a.get("schema") == "platform" for a in table_args)
    )

    model_cls = PlatformAuditLog if is_platform else TenantAuditLog
    row = model_cls(
        table_name=target.__tablename__,
        record_id=getattr(target, "id", None),
        operation=operation,
        before_state=before_state,
        after_state=after_state,
        **ctx,
    )
    session.add(row)


class AuditableMixin:
    """Mix into any SQLAlchemy model to auto-write audit_log on insert/update/delete."""

    @classmethod
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        @event.listens_for(cls, "after_insert")
        def after_insert(mapper: Any, connection: Any, target: Any) -> None:
            _write_audit(target, "insert", None, _snapshot(mapper, target))

        @event.listens_for(cls, "after_update")
        def after_update(mapper: Any, connection: Any, target: Any) -> None:
            _write_audit(target, "update", _before_snapshot(mapper, target), _snapshot(mapper, target))

        @event.listens_for(cls, "after_delete")
        def after_delete(mapper: Any, connection: Any, target: Any) -> None:
            _write_audit(target, "delete", _snapshot(mapper, target), None)
```

- [ ] **Run ruff + mypy:**

```bash
ruff check app/core/audit/mixin.py && mypy app/core/audit/mixin.py
```

Expected: no errors.

---

## Task 6: Audit services

**Files:**
- Create: `app/core/audit/service.py`

- [ ] **Create `app/core/audit/service.py`:**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import PlatformAuditLog, TenantAuditLog


class _AuditServiceBase:
    _model_cls: type

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        table_name: str,
        record_id: uuid.UUID,
        operation: str,
        actor_type: str,
        actor_id: uuid.UUID | None = None,
        actor_label: str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        row = self._model_cls(
            table_name=table_name,
            record_id=record_id,
            operation=operation,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_label=actor_label,
            before_state=before_state,
            after_state=after_state,
            occurred_at=datetime.now(timezone.utc),
            request_id=request_id,
        )
        self._session.add(row)


class PlatformAuditService(_AuditServiceBase):
    _model_cls = PlatformAuditLog


class TenantAuditService(_AuditServiceBase):
    _model_cls = TenantAuditLog
```

- [ ] **Update `app/core/audit/__init__.py`:**

```python
from app.core.audit.mixin import AuditableMixin
from app.core.audit.service import PlatformAuditService, TenantAuditService

__all__ = ["AuditableMixin", "PlatformAuditService", "TenantAuditService"]
```

- [ ] **Update `alembic/platform/env.py`** — add import so metadata is populated:

```python
# After the existing Base import, add:
import app.core.audit.models  # noqa: F401
import app.core.outbox.models  # noqa: F401 — added in Task 9
```

(Add only the audit line now; outbox line added in Task 9.)

- [ ] **Update `alembic/tenant/env.py`** — same pattern.

- [ ] **Run ruff + mypy:**

```bash
ruff check app/core/audit/ && mypy app/core/audit/
```

- [ ] **Commit:**

```bash
git add app/core/audit/
git commit -m "feat: add AuditableMixin and audit services"
```

---

## Task 7: Audit tests

**Files:**
- Create: `tests/core/audit/__init__.py`
- Create: `tests/core/audit/test_audit_mixin.py`
- Create: `tests/core/audit/test_audit_service.py`

- [ ] **Create `tests/core/audit/__init__.py`** (empty).

- [ ] **Create `tests/core/audit/test_audit_mixin.py`:**

```python
"""
Tests for AuditableMixin:
- Platform model writes to platform.audit_log
- Tenant model writes to tenant audit_log (current schema)
- actor_type=platform_user recorded when context var is set
"""
import uuid

import structlog
import pytest
from sqlalchemy import select, Text, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.db import Base


# ── Minimal test models ────────────────────────────────────────────────────────

class PlatformWidget(AuditableMixin, Base):
    __tablename__ = "platform_widgets"
    __table_args__ = {"schema": "platform"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)


class TenantWidget(AuditableMixin, Base):
    __tablename__ = "tenant_widgets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)


@pytest.fixture(scope="session", autouse=True)
async def create_widget_tables(test_engine):
    """Create the test-model tables used only in this test module."""
    from app.core.db import Base
    async with test_engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("SET search_path TO tenant_test, platform"))
        await conn.run_sync(Base.metadata.create_all)


async def test_platform_model_writes_to_platform_audit_log(platform_session):
    widget = PlatformWidget(name="alpha")
    platform_session.add(widget)
    await platform_session.flush()

    rows = (await platform_session.execute(select(PlatformAuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].table_name == "platform_widgets"
    assert rows[0].operation == "insert"
    assert rows[0].after_state["name"] == "alpha"
    assert rows[0].before_state is None


async def test_tenant_model_writes_to_tenant_audit_log(tenant_session):
    widget = TenantWidget(name="beta")
    tenant_session.add(widget)
    await tenant_session.flush()

    rows = (await tenant_session.execute(select(TenantAuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].table_name == "tenant_widgets"
    assert rows[0].operation == "insert"


async def test_update_records_before_and_after(tenant_session):
    widget = TenantWidget(name="original")
    tenant_session.add(widget)
    await tenant_session.flush()

    widget.name = "updated"
    await tenant_session.flush()

    rows = (await tenant_session.execute(select(TenantAuditLog))).scalars().all()
    update_rows = [r for r in rows if r.operation == "update"]
    assert len(update_rows) == 1
    assert update_rows[0].before_state["name"] == "original"
    assert update_rows[0].after_state["name"] == "updated"


async def test_cross_context_actor_type_recorded(tenant_session):
    """A platform_user acting via a tenant session writes to tenant log with correct actor_type."""
    actor_id = uuid.uuid4()
    structlog.contextvars.bind_contextvars(
        actor_type="platform_user",
        actor_id=str(actor_id),
        actor_label="admin@platform.com",
    )
    try:
        widget = TenantWidget(name="cross-context")
        tenant_session.add(widget)
        await tenant_session.flush()
    finally:
        structlog.contextvars.clear_contextvars()

    rows = (await tenant_session.execute(select(TenantAuditLog))).scalars().all()
    assert rows[-1].actor_type == "platform_user"
    assert rows[-1].actor_label == "admin@platform.com"
```

- [ ] **Create `tests/core/audit/test_audit_service.py`:**

```python
import uuid

import pytest
from sqlalchemy import select

from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.audit.service import PlatformAuditService, TenantAuditService


async def test_platform_audit_service_writes_row(platform_session):
    svc = PlatformAuditService(platform_session)
    record_id = uuid.uuid4()
    await svc.record(
        table_name="tenants",
        record_id=record_id,
        operation="update",
        actor_type="platform_user",
        before_state={"status": "active"},
        after_state={"status": "suspended"},
    )
    await platform_session.flush()

    rows = (await platform_session.execute(select(PlatformAuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].record_id == record_id
    assert rows[0].before_state == {"status": "active"}


async def test_tenant_audit_service_writes_row(tenant_session):
    svc = TenantAuditService(tenant_session)
    record_id = uuid.uuid4()
    await svc.record(
        table_name="loans",
        record_id=record_id,
        operation="insert",
        actor_type="tenant_user",
        after_state={"amount": "500000"},
    )
    await tenant_session.flush()

    rows = (await tenant_session.execute(select(TenantAuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].operation == "insert"
```

- [ ] **Run audit tests:**

```bash
pytest tests/core/audit/ -v
```

Expected: all pass.

- [ ] **Commit:**

```bash
git add tests/core/audit/
git commit -m "test: audit mixin and service integration tests"
```

---

## Task 8: Outbox models + db.py flag

**Files:**
- Create: `app/core/outbox/__init__.py`
- Create: `app/core/outbox/models.py`
- Modify: `app/core/db.py`

- [ ] **Create `app/core/outbox/models.py`:**

```python
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Index, Integer, Text, UUID
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class _OutboxEventBase:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    published_at: Mapped[object | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[object | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    is_dead_lettered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PlatformOutboxEvent(_OutboxEventBase, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_platform_outbox_pending",
            "next_attempt_at",
            postgresql_where="published_at IS NULL AND is_dead_lettered = false",
        ),
        {"schema": "platform"},
    )


class TenantOutboxEvent(_OutboxEventBase, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_tenant_outbox_pending",
            "next_attempt_at",
            postgresql_where="published_at IS NULL AND is_dead_lettered = false",
        ),
    )
```

- [ ] **Add `is_platform` flag to `get_platform_session` in `app/core/db.py`.** Find the `get_platform_session` function (line ~111) and add one line:

```python
async def get_platform_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an AsyncSession with search_path set to platform."""
    async with AsyncSessionFactory() as session:
        await session.execute(text("SET LOCAL search_path TO platform"))
        session.sync_session.info["is_platform"] = True   # ← add this line
        yield session
```

- [ ] **Create `app/core/outbox/__init__.py`:**

```python
from app.core.outbox.publisher import EventPublisher

__all__ = ["EventPublisher"]
```

- [ ] **Update `alembic/platform/env.py`** — add outbox import:

```python
import app.core.outbox.models  # noqa: F401
```

- [ ] **Update `alembic/tenant/env.py`** — same.

- [ ] **Run ruff + mypy:**

```bash
ruff check app/core/outbox/models.py app/core/db.py && mypy app/core/outbox/models.py app/core/db.py
```

- [ ] **Commit:**

```bash
git add app/core/outbox/ app/core/db.py alembic/
git commit -m "feat: add outbox models and platform session flag"
```

---

## Task 9: EventPublisher

**Files:**
- Create: `app/core/outbox/publisher.py`

- [ ] **Create `app/core/outbox/publisher.py`:**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.outbox.models import PlatformOutboxEvent, TenantOutboxEvent


class EventPublisher:
    """The ONLY permitted path for emitting cross-module events.

    Call publish() inside an open session transaction. The outbox row is
    committed or rolled back with the caller's business transaction.
    Direct aio_pika / pika usage outside app/core/outbox/ is forbidden.
    """

    @staticmethod
    async def publish(
        session: AsyncSession,
        *,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        is_platform = session.sync_session.info.get("is_platform", False)
        model_cls = PlatformOutboxEvent if is_platform else TenantOutboxEvent
        row = model_cls(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            occurred_at=datetime.now(timezone.utc),
        )
        session.add(row)
```

- [ ] **Run ruff + mypy:**

```bash
ruff check app/core/outbox/publisher.py && mypy app/core/outbox/publisher.py
```

---

## Task 10: Outbox publisher tests

**Files:**
- Create: `tests/core/outbox/__init__.py`
- Create: `tests/core/outbox/test_publisher.py`

- [ ] **Create `tests/core/outbox/__init__.py`** (empty).

- [ ] **Create `tests/core/outbox/test_publisher.py`:**

```python
import uuid

from sqlalchemy import select

from app.core.outbox.models import PlatformOutboxEvent, TenantOutboxEvent
from app.core.outbox.publisher import EventPublisher


async def test_publish_writes_to_platform_outbox(platform_session):
    agg_id = uuid.uuid4()
    await EventPublisher.publish(
        platform_session,
        aggregate_type="tenant",
        aggregate_id=agg_id,
        event_type="TenantCreated",
        payload={"slug": "acme"},
    )
    await platform_session.flush()

    rows = (await platform_session.execute(select(PlatformOutboxEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == "TenantCreated"
    assert rows[0].published_at is None
    assert rows[0].is_dead_lettered is False


async def test_publish_writes_to_tenant_outbox(tenant_session):
    agg_id = uuid.uuid4()
    await EventPublisher.publish(
        tenant_session,
        aggregate_type="loan",
        aggregate_id=agg_id,
        event_type="LoanDisbursed",
        payload={"amount": 500000},
    )
    await tenant_session.flush()

    rows = (await tenant_session.execute(select(TenantOutboxEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].aggregate_type == "loan"


async def test_rollback_removes_outbox_row(test_engine):
    """Row written inside a rolled-back transaction must not persist."""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy import text

    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            await EventPublisher.publish(
                session,
                aggregate_type="tenant",
                aggregate_id=uuid.uuid4(),
                event_type="ShouldNotExist",
                payload={},
            )
            await session.rollback()

    async with factory() as session:
        await session.execute(text("SET LOCAL search_path TO platform"))
        rows = (await session.execute(
            select(PlatformOutboxEvent).where(PlatformOutboxEvent.event_type == "ShouldNotExist")
        )).scalars().all()
        assert rows == []
```

- [ ] **Run tests:**

```bash
pytest tests/core/outbox/test_publisher.py -v
```

Expected: all pass.

- [ ] **Commit:**

```bash
git add app/core/outbox/publisher.py tests/core/outbox/
git commit -m "feat: add EventPublisher with tests"
```

---

## Task 11: Celery app + outbox relay worker

**Files:**
- Create: `app/workers/__init__.py`
- Create: `app/workers/celery_app.py`
- Create: `app/core/outbox/worker.py`

- [ ] **Create `app/workers/__init__.py`** (empty).

- [ ] **Create `app/workers/celery_app.py`:**

```python
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "sacco",
    broker=settings.redis_url,  # Redis as broker (rabbitmq for events, redis for tasks)
    include=[
        "app.core.outbox.worker",
        "app.core.outbox.retention",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "relay-platform-outbox": {
            "task": "app.core.outbox.worker.relay_platform_outbox",
            "schedule": 5.0,
        },
        "relay-tenant-outbox": {
            "task": "app.core.outbox.worker.relay_tenant_outbox",
            "schedule": 5.0,
        },
        "purge-outbox-retention": {
            "task": "app.core.outbox.retention.purge_outbox_retention",
            "schedule": 30 * 24 * 3600,  # monthly
        },
        "expire-approval-requests": {
            "task": "app.modules.maker_checker.service.expire_approval_requests",
            "schedule": 3600.0,  # hourly
        },
    },
)
```

- [ ] **Create `app/core/outbox/worker.py`:**

```python
"""
Outbox relay workers. Pull unpublished events from outbox_events and
publish to RabbitMQ with publisher confirms. At-least-once delivery.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aio_pika
import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.outbox.models import PlatformOutboxEvent, TenantOutboxEvent
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)

_MAX_ROWS_PER_TICK = 1_000
_BATCH_SIZE = 100
_WALL_CLOCK_LIMIT = 30.0  # seconds
_MAX_ATTEMPTS = 10


def _next_attempt_delta(attempts: int) -> timedelta:
    delay = min(30 * (2 ** attempts), 3600)
    return timedelta(seconds=delay)


async def _get_rabbitmq_channel(settings: Any) -> aio_pika.Channel:
    conn = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await conn.channel()
    await channel.declare_exchange("sacco.events", aio_pika.ExchangeType.TOPIC, durable=True)
    return channel


async def _relay_outbox(
    session: AsyncSession,
    model_cls: type,
    context: str,
    rabbitmq_url: str,
) -> None:
    """Drain unpublished rows from one outbox table."""
    now = datetime.now(timezone.utc)
    deadline = time.monotonic() + _WALL_CLOCK_LIMIT
    total_processed = 0

    conn = await aio_pika.connect_robust(rabbitmq_url)
    try:
        channel = await conn.channel()
        await channel.set_qos(prefetch_count=_BATCH_SIZE)
        exchange = await channel.declare_exchange("sacco.events", aio_pika.ExchangeType.TOPIC, durable=True)

        while total_processed < _MAX_ROWS_PER_TICK and time.monotonic() < deadline:
            async with session.begin():
                rows = (
                    await session.execute(
                        select(model_cls)
                        .where(
                            model_cls.published_at.is_(None),
                            model_cls.is_dead_lettered.is_(False),
                            (model_cls.next_attempt_at.is_(None)) | (model_cls.next_attempt_at <= now),
                        )
                        .order_by(model_cls.occurred_at)
                        .limit(_BATCH_SIZE)
                        .with_for_update(skip_locked=True)
                    )
                ).scalars().all()

                if not rows:
                    break

                for row in rows:
                    t0 = time.monotonic()
                    routing_key = f"{context}.{row.aggregate_type}.{row.event_type}"
                    try:
                        msg = aio_pika.Message(
                            body=str(row.payload).encode(),
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            message_id=str(row.id),
                        )
                        await exchange.publish(msg, routing_key=routing_key)
                        latency_ms = int((time.monotonic() - t0) * 1000)
                        _log.info(
                            "outbox.published",
                            event_id=str(row.id),
                            event_type=row.event_type,
                            context=context,
                            latency_ms=latency_ms,
                        )
                        row.published_at = datetime.now(timezone.utc)
                        row.attempts += 1
                    except Exception as exc:
                        row.attempts += 1
                        row.last_error = str(exc)
                        row.next_attempt_at = datetime.now(timezone.utc) + _next_attempt_delta(row.attempts)
                        if row.attempts >= _MAX_ATTEMPTS:
                            row.is_dead_lettered = True
                            _log.error(
                                "outbox.dead_lettered",
                                event_id=str(row.id),
                                event_type=row.event_type,
                                context=context,
                                attempts=row.attempts,
                            )

                total_processed += len(rows)
    finally:
        await conn.close()


async def _run_platform_relay() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text("SET LOCAL search_path TO platform"))
        session.sync_session.info["is_platform"] = True
        await _relay_outbox(session, PlatformOutboxEvent, "platform", settings.rabbitmq_url)
    await engine.dispose()


async def _run_tenant_relay() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    # Get active tenant schemas from platform.tenants (table exists after platform_ module).
    # For now, query safely and skip if table doesn't exist yet.
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT schema_name, slug FROM platform.tenants WHERE is_active = true")
            )
            tenants = result.fetchall()
    except Exception:
        await engine.dispose()
        return

    factory = async_sessionmaker(engine, expire_on_commit=False)
    for schema_name, slug in tenants:
        try:
            async with factory() as session:
                await session.execute(text(f"SET LOCAL search_path TO {schema_name}, platform"))  # noqa: S608
                await _relay_outbox(session, TenantOutboxEvent, slug, settings.rabbitmq_url)
        except Exception as exc:
            _log.error("outbox.tenant_relay_error", schema=schema_name, error=str(exc))

    await engine.dispose()


@celery_app.task(name="app.core.outbox.worker.relay_platform_outbox")
def relay_platform_outbox() -> None:
    asyncio.run(_run_platform_relay())


@celery_app.task(name="app.core.outbox.worker.relay_tenant_outbox")
def relay_tenant_outbox() -> None:
    asyncio.run(_run_tenant_relay())
```

- [ ] **Run ruff + mypy:**

```bash
ruff check app/core/outbox/worker.py app/workers/ && mypy app/core/outbox/worker.py
```

- [ ] **Commit:**

```bash
git add app/workers/ app/core/outbox/worker.py
git commit -m "feat: add Celery app and outbox relay worker"
```

---

## Task 12: Outbox retention task

**Files:**
- Create: `app/core/outbox/retention.py`

- [ ] **Create `app/core/outbox/retention.py`:**

```python
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.outbox.models import PlatformOutboxEvent, TenantOutboxEvent
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)


async def _purge(schema: str, model_cls: type, cutoff: datetime, engine: object) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)  # type: ignore[arg-type]
    async with factory() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))  # noqa: S608
            result = await session.execute(
                delete(model_cls).where(
                    model_cls.published_at.is_not(None),
                    model_cls.published_at < cutoff,
                )
            )
            return result.rowcount


async def _run_purge() -> None:
    settings = get_settings()
    retention_days = getattr(settings, "outbox_retention_days", 90)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    engine = create_async_engine(settings.database_url)

    deleted = await _purge("platform", PlatformOutboxEvent, cutoff, engine)
    _log.info("outbox.retention.platform", deleted=deleted, cutoff=cutoff.isoformat())

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            tenants = [row[0] for row in result.fetchall()]
    except Exception:
        tenants = []

    for schema in tenants:
        deleted = await _purge(schema, TenantOutboxEvent, cutoff, engine)
        _log.info("outbox.retention.tenant", schema=schema, deleted=deleted)

    await engine.dispose()


@celery_app.task(name="app.core.outbox.retention.purge_outbox_retention")
def purge_outbox_retention() -> None:
    asyncio.run(_run_purge())
```

- [ ] **Add `outbox_retention_days` to `app/core/config.py`:**

```python
outbox_retention_days: int = 90
```

- [ ] **Run ruff + mypy:**

```bash
ruff check app/core/outbox/retention.py app/core/config.py && mypy app/core/outbox/retention.py
```

- [ ] **Commit:**

```bash
git add app/core/outbox/retention.py app/core/config.py
git commit -m "feat: add outbox retention task"
```

---

## Task 13: Outbox worker tests

**Files:**
- Create: `tests/core/outbox/test_worker.py`
- Create: `tests/core/outbox/test_retention.py`

- [ ] **Create `tests/core/outbox/test_worker.py`:**

```python
"""
Outbox worker integration tests.
These tests call _relay_outbox() directly with a mocked RabbitMQ exchange.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.outbox.models import TenantOutboxEvent
from app.core.outbox.worker import _relay_outbox, _MAX_ATTEMPTS, _next_attempt_delta


def _make_event(session_factory, schema, **overrides):
    """Helper: insert a TenantOutboxEvent and return it."""
    defaults = dict(
        aggregate_type="loan",
        aggregate_id=uuid.uuid4(),
        event_type="LoanDisbursed",
        payload={"amount": 100},
        occurred_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return TenantOutboxEvent(**defaults)


@pytest.fixture
def mock_exchange():
    exchange = AsyncMock()
    exchange.publish = AsyncMock()
    return exchange


@pytest.fixture
def mock_aio_pika(mock_exchange):
    """Patch aio_pika.connect_robust so _relay_outbox never hits real RabbitMQ."""
    channel = AsyncMock()
    channel.declare_exchange = AsyncMock(return_value=mock_exchange)
    channel.set_qos = AsyncMock()
    conn = AsyncMock()
    conn.channel = AsyncMock(return_value=channel)
    conn.close = AsyncMock()
    with patch("app.core.outbox.worker.aio_pika") as mock:
        mock.connect_robust = AsyncMock(return_value=conn)
        mock.ExchangeType.TOPIC = "topic"
        mock.Message = MagicMock(side_effect=lambda **kw: MagicMock())
        mock.DeliveryMode.PERSISTENT = 2
        yield mock, mock_exchange


async def test_happy_path_marks_published(tenant_session, mock_aio_pika):
    _, exchange = mock_aio_pika
    event = _make_event(None, "tenant_test")
    tenant_session.add(event)
    await tenant_session.flush()

    await _relay_outbox(tenant_session, TenantOutboxEvent, "test-tenant", "amqp://")

    rows = (await tenant_session.execute(select(TenantOutboxEvent))).scalars().all()
    assert rows[0].published_at is not None
    assert exchange.publish.called


async def test_skip_locked_prevents_double_publish(test_engine, mock_aio_pika):
    """Two concurrent relay calls must each publish a row exactly once."""
    _, exchange = mock_aio_pika
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    # Insert 2 events
    async with factory() as s:
        async with s.begin():
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            s.add(_make_event(None, "tenant_test", event_type="EventA"))
            s.add(_make_event(None, "tenant_test", event_type="EventB"))

    async def relay():
        async with factory() as s:
            async with s.begin():
                await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
                await _relay_outbox(s, TenantOutboxEvent, "test-tenant", "amqp://")

    await asyncio.gather(relay(), relay())

    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        rows = (await s.execute(select(TenantOutboxEvent))).scalars().all()

    published = [r for r in rows if r.published_at is not None]
    assert len(published) == 2
    # publish called exactly twice total (each row published once)
    assert exchange.publish.call_count == 2


async def test_publish_failure_sets_backoff(tenant_session, mock_aio_pika):
    mock_pkg, exchange = mock_aio_pika
    exchange.publish.side_effect = Exception("connection refused")

    event = _make_event(None, "tenant_test")
    tenant_session.add(event)
    await tenant_session.flush()

    await _relay_outbox(tenant_session, TenantOutboxEvent, "test-tenant", "amqp://")

    rows = (await tenant_session.execute(select(TenantOutboxEvent))).scalars().all()
    row = rows[0]
    assert row.published_at is None
    assert row.attempts == 1
    assert row.next_attempt_at is not None
    assert row.next_attempt_at > datetime.now(timezone.utc)
    assert row.is_dead_lettered is False


async def test_dead_lettering_after_max_attempts(tenant_session, mock_aio_pika):
    _, exchange = mock_aio_pika
    exchange.publish.side_effect = Exception("always fails")

    event = _make_event(None, "tenant_test", attempts=_MAX_ATTEMPTS - 1)
    tenant_session.add(event)
    await tenant_session.flush()

    await _relay_outbox(tenant_session, TenantOutboxEvent, "test-tenant", "amqp://")

    rows = (await tenant_session.execute(select(TenantOutboxEvent))).scalars().all()
    assert rows[0].is_dead_lettered is True


def test_backoff_formula():
    assert _next_attempt_delta(0).total_seconds() == 30
    assert _next_attempt_delta(1).total_seconds() == 60
    assert _next_attempt_delta(7).total_seconds() == 3600   # capped at 1 hour
    assert _next_attempt_delta(20).total_seconds() == 3600  # still capped
```

- [ ] **Create `tests/core/outbox/test_retention.py`:**

```python
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.outbox.models import PlatformOutboxEvent
from app.core.outbox.retention import _purge


async def test_purge_deletes_old_published_rows(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    old_date = cutoff - timedelta(days=1)
    recent_date = datetime.now(timezone.utc)

    async with factory() as s:
        async with s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            old = PlatformOutboxEvent(
                aggregate_type="t", aggregate_id=uuid.uuid4(),
                event_type="Old", payload={},
                occurred_at=old_date, published_at=old_date,
            )
            recent = PlatformOutboxEvent(
                aggregate_type="t", aggregate_id=uuid.uuid4(),
                event_type="Recent", payload={},
                occurred_at=recent_date, published_at=recent_date,
            )
            s.add(old)
            s.add(recent)

    deleted = await _purge("platform", PlatformOutboxEvent, cutoff, test_engine)
    assert deleted == 1

    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        rows = (await s.execute(select(PlatformOutboxEvent))).scalars().all()
    assert all(r.event_type != "Old" for r in rows)


async def test_purge_ignores_unpublished_rows(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    cutoff = datetime.now(timezone.utc)
    old_date = cutoff - timedelta(days=100)

    async with factory() as s:
        async with s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            unpublished = PlatformOutboxEvent(
                aggregate_type="t", aggregate_id=uuid.uuid4(),
                event_type="Unpublished", payload={},
                occurred_at=old_date, published_at=None,
            )
            s.add(unpublished)

    deleted = await _purge("platform", PlatformOutboxEvent, cutoff, test_engine)
    assert deleted == 0
```

- [ ] **Run outbox tests:**

```bash
pytest tests/core/outbox/ -v
```

Expected: all pass.

- [ ] **Commit:**

```bash
git add tests/core/outbox/
git commit -m "test: outbox worker — SKIP LOCKED concurrency, backoff, dead-lettering, retention"
```

---

## Task 14: Maker-checker models

**Files:**
- Create: `app/modules/__init__.py`
- Create: `app/modules/maker_checker/__init__.py`
- Create: `app/modules/maker_checker/models/__init__.py`
- Create: `app/modules/maker_checker/models/mixins.py`
- Create: `app/modules/maker_checker/models/platform.py`
- Create: `app/modules/maker_checker/models/tenant.py`

- [ ] **Create all `__init__.py` files** (empty).

- [ ] **Create `app/modules/maker_checker/models/mixins.py`:**

```python
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, Text, UUID, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column


class ApprovalRequestMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    expires_at: Mapped[object | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    executed_at: Mapped[object | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    execution_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApprovalActionMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)  # approve | reject
    acted_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Create `app/modules/maker_checker/models/platform.py`:**

```python
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, UUID, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.maker_checker.models.mixins import ApprovalActionMixin, ApprovalRequestMixin


class PlatformApprovalRequest(ApprovalRequestMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = {"schema": "platform"}


class PlatformApprovalAction(ApprovalActionMixin, Base):
    __tablename__ = "approval_actions"
    __table_args__ = (
        UniqueConstraint("approval_request_id", "actor_user_id", name="uq_platform_approval_actions_no_double_vote"),
        {"schema": "platform"},
    )
    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.approval_requests.id"),
        nullable=False,
    )
```

- [ ] **Create `app/modules/maker_checker/models/tenant.py`:**

```python
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, UUID, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.maker_checker.models.mixins import ApprovalActionMixin, ApprovalRequestMixin


class TenantApprovalRequest(ApprovalRequestMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = ()


class TenantApprovalAction(ApprovalActionMixin, Base):
    __tablename__ = "approval_actions"
    __table_args__ = (
        UniqueConstraint("approval_request_id", "actor_user_id", name="uq_tenant_approval_actions_no_double_vote"),
    )
    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_requests.id"),
        nullable=False,
    )
```

- [ ] **Create `app/modules/maker_checker/models/__init__.py`:**

```python
from app.modules.maker_checker.models.platform import PlatformApprovalAction, PlatformApprovalRequest
from app.modules.maker_checker.models.tenant import TenantApprovalAction, TenantApprovalRequest

__all__ = [
    "PlatformApprovalRequest", "PlatformApprovalAction",
    "TenantApprovalRequest", "TenantApprovalAction",
]
```

- [ ] **Update Alembic env files to import maker_checker models:**

In `alembic/platform/env.py` add:
```python
import app.modules.maker_checker.models  # noqa: F401
```

Same in `alembic/tenant/env.py`.

- [ ] **Run ruff + mypy:**

```bash
ruff check app/modules/maker_checker/models/ && mypy app/modules/maker_checker/models/
```

- [ ] **Commit:**

```bash
git add app/modules/ alembic/
git commit -m "feat: add maker-checker SQLAlchemy models"
```

---

## Task 15: Maker-checker registry and ApprovalService

**Files:**
- Create: `app/modules/maker_checker/registry.py`
- Create: `app/modules/maker_checker/service.py`

- [ ] **Create `app/modules/maker_checker/registry.py`:**

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# Maps operation_type → async executor callable.
# Callable signature: (session: AsyncSession, payload: dict) -> dict
approval_registry: dict[str, Callable[..., Any]] = {}

# Maps operation_type → required permission string (used by API dependency).
operation_type_permissions: dict[str, str] = {}


def approval_executor(operation_type: str, *, required_permission: str = "") -> Callable:
    """Decorator: register an async function as the executor for operation_type.

    Usage:
        @approval_executor("loan.disburse", required_permission="loans:approve")
        async def execute_loan_disburse(session: AsyncSession, payload: dict) -> dict:
            ...

    The decorated function is called inline when quorum is met.
    """
    def decorator(fn: Callable) -> Callable:
        approval_registry[operation_type] = fn
        if required_permission:
            operation_type_permissions[operation_type] = required_permission
        return fn

    return decorator
```

- [ ] **Create `app/modules/maker_checker/service.py`:**

```python
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.audit.service import PlatformAuditService, TenantAuditService
from app.core.outbox.publisher import EventPublisher
from app.modules.maker_checker.models.mixins import ApprovalActionMixin, ApprovalRequestMixin
from app.modules.maker_checker.models.platform import PlatformApprovalAction, PlatformApprovalRequest
from app.modules.maker_checker.models.tenant import TenantApprovalAction, TenantApprovalRequest
from app.modules.maker_checker.registry import approval_registry
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)

VALID_STATUSES_FOR_ACTION = {"pending"}


def _audit_svc(session: AsyncSession) -> PlatformAuditService | TenantAuditService:
    if session.sync_session.info.get("is_platform"):
        return PlatformAuditService(session)
    return TenantAuditService(session)


def _request_models(session: AsyncSession) -> tuple[type, type]:
    if session.sync_session.info.get("is_platform"):
        return PlatformApprovalRequest, PlatformApprovalAction
    return TenantApprovalRequest, TenantApprovalAction


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._req_cls, self._act_cls = _request_models(session)

    async def submit(
        self,
        *,
        operation_type: str,
        payload: dict[str, Any],
        requested_by: uuid.UUID,
        required_approvals: int = 1,
        expires_at: datetime | None = None,
    ) -> ApprovalRequestMixin:
        if operation_type not in approval_registry:
            raise ValueError(f"No executor registered for operation_type '{operation_type}'")

        request = self._req_cls(
            operation_type=operation_type,
            payload=payload,
            requested_by=requested_by,
            requested_at=datetime.now(timezone.utc),
            required_approvals=required_approvals,
            status="pending",
            expires_at=expires_at,
        )
        self._session.add(request)
        await self._session.flush()

        await EventPublisher.publish(
            self._session,
            aggregate_type="approval_request",
            aggregate_id=request.id,
            event_type="ApprovalRequested",
            payload={"operation_type": operation_type, "requested_by": str(requested_by)},
        )
        await _audit_svc(self._session).record(
            table_name="approval_requests",
            record_id=request.id,
            operation="insert",
            actor_type="system",
            after_state={"status": "pending", "operation_type": operation_type},
        )
        return request

    async def approve(
        self,
        *,
        request_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        comment: str | None = None,
    ) -> ApprovalRequestMixin:
        request = await self._get_pending(request_id)
        if actor_user_id == request.requested_by:
            raise ValueError("Self-approval is forbidden")

        action = self._act_cls(
            approval_request_id=request.id,
            actor_user_id=actor_user_id,
            action="approve",
            acted_at=datetime.now(timezone.utc),
            comment=comment,
        )
        self._session.add(action)
        await self._session.flush()

        count = await self._approval_count(request.id)
        await EventPublisher.publish(
            self._session,
            aggregate_type="approval_request",
            aggregate_id=request.id,
            event_type="ApprovalGranted",
            payload={"actor_user_id": str(actor_user_id), "approval_count": count},
        )

        if count >= request.required_approvals:
            request.status = "approved"
            await self._execute(request)

        return request

    async def reject(
        self,
        *,
        request_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        reason: str | None = None,
    ) -> ApprovalRequestMixin:
        request = await self._get_pending(request_id)
        if actor_user_id == request.requested_by:
            raise ValueError("Self-rejection is forbidden")

        action = self._act_cls(
            approval_request_id=request.id,
            actor_user_id=actor_user_id,
            action="reject",
            acted_at=datetime.now(timezone.utc),
            comment=reason,
        )
        self._session.add(action)
        request.status = "rejected"
        request.rejection_reason = reason
        await self._session.flush()

        await EventPublisher.publish(
            self._session,
            aggregate_type="approval_request",
            aggregate_id=request.id,
            event_type="ApprovalRejected",
            payload={"actor_user_id": str(actor_user_id), "reason": reason},
        )
        return request

    async def cancel(self, *, request_id: uuid.UUID, requested_by: uuid.UUID) -> ApprovalRequestMixin:
        request = await self._get_pending(request_id)
        if request.requested_by != requested_by:
            raise ValueError("Only the maker can cancel their own request")

        action_count_result = await self._session.execute(
            select(func.count()).where(self._act_cls.approval_request_id == request.id)
        )
        if action_count_result.scalar_one() > 0:
            raise ValueError("Cannot cancel after a checker has acted — use reject instead")

        request.status = "cancelled"
        await self._session.flush()
        return request

    async def _get_pending(self, request_id: uuid.UUID) -> Any:
        result = await self._session.execute(
            select(self._req_cls).where(self._req_cls.id == request_id)
        )
        request = result.scalar_one_or_none()
        if request is None:
            raise ValueError(f"Approval request {request_id} not found")
        if request.status not in VALID_STATUSES_FOR_ACTION:
            raise ValueError(f"Request is in status '{request.status}', not 'pending'")
        return request

    async def _approval_count(self, request_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count()).where(
                self._act_cls.approval_request_id == request_id,
                self._act_cls.action == "approve",
            )
        )
        return result.scalar_one()

    async def _execute(self, request: Any) -> None:
        executor = approval_registry[request.operation_type]
        try:
            result = await executor(self._session, request.payload)
            request.status = "executed"
            request.executed_at = datetime.now(timezone.utc)
            request.execution_result = result or {}
            await EventPublisher.publish(
                self._session,
                aggregate_type="approval_request",
                aggregate_id=request.id,
                event_type="ApprovalExecuted",
                payload={"operation_type": request.operation_type},
            )
        except Exception as exc:
            request.status = "execution_failed"
            request.execution_result = {"error": str(exc)}
            _log.error(
                "maker_checker.execution_failed",
                request_id=str(request.id),
                operation_type=request.operation_type,
                error=str(exc),
            )
            await EventPublisher.publish(
                self._session,
                aggregate_type="approval_request",
                aggregate_id=request.id,
                event_type="ApprovalExecutionFailed",
                payload={"error": str(exc)},
            )


async def _run_expiry() -> None:
    from app.core.config import get_settings
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)

    # Expire platform requests
    async with factory() as session:
        async with session.begin():
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            await session.execute(
                update(PlatformApprovalRequest)
                .where(
                    PlatformApprovalRequest.status == "pending",
                    PlatformApprovalRequest.expires_at < now,
                )
                .values(status="expired")
            )

    # Expire per-tenant requests
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            schemas = [row[0] for row in result.fetchall()]
    except Exception:
        schemas = []

    for schema in schemas:
        async with factory() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))  # noqa: S608
                await session.execute(
                    update(TenantApprovalRequest)
                    .where(
                        TenantApprovalRequest.status == "pending",
                        TenantApprovalRequest.expires_at < now,
                    )
                    .values(status="expired")
                )

    await engine.dispose()


@celery_app.task(name="app.modules.maker_checker.service.expire_approval_requests")
def expire_approval_requests() -> None:
    asyncio.run(_run_expiry())
```

- [ ] **Run ruff + mypy:**

```bash
ruff check app/modules/maker_checker/ && mypy app/modules/maker_checker/registry.py app/modules/maker_checker/service.py
```

- [ ] **Commit:**

```bash
git add app/modules/maker_checker/registry.py app/modules/maker_checker/service.py
git commit -m "feat: add maker-checker registry and ApprovalService"
```

---

## Task 16: Maker-checker schemas and API

**Files:**
- Create: `app/modules/maker_checker/schemas.py`
- Create: `app/modules/maker_checker/api.py`

- [ ] **Create `app/modules/maker_checker/schemas.py`:**

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SubmitApprovalRequest(BaseModel):
    operation_type: str
    payload: dict[str, Any]
    required_approvals: int = 1
    expires_at: datetime | None = None


class ApprovalActionRequest(BaseModel):
    comment: str | None = None


class RejectRequest(BaseModel):
    reason: str | None = None


class ApprovalActionOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID
    action: str
    acted_at: datetime
    comment: str | None

    model_config = {"from_attributes": True}


class ApprovalRequestOut(BaseModel):
    id: uuid.UUID
    operation_type: str
    payload: dict[str, Any]
    requested_by: uuid.UUID
    requested_at: datetime
    required_approvals: int
    status: str
    expires_at: datetime | None
    executed_at: datetime | None
    execution_result: dict[str, Any] | None
    rejection_reason: str | None

    model_config = {"from_attributes": True}
```

- [ ] **Create `app/modules/maker_checker/api.py`:**

```python
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.maker_checker.models.tenant import TenantApprovalRequest
from app.modules.maker_checker.schemas import (
    ApprovalActionRequest,
    ApprovalRequestOut,
    RejectRequest,
    SubmitApprovalRequest,
)
from app.modules.maker_checker.service import ApprovalService

router = APIRouter(prefix="/approvals", tags=["maker-checker"])

Session = Annotated[AsyncSession, Depends(get_tenant_session)]

# Actor resolution is a stub until the IAM module provides JWT-based identity.
# Caller passes X-Actor-ID header for now; IAM will replace this.
from fastapi import Header


async def _get_actor(x_actor_id: str = Header(...)) -> uuid.UUID:
    try:
        return uuid.UUID(x_actor_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-Actor-ID header")

Actor = Annotated[uuid.UUID, Depends(_get_actor)]


@router.post("", response_model=ApprovalRequestOut, status_code=201)
async def submit_approval(
    body: SubmitApprovalRequest,
    session: Session,
    actor_id: Actor,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.submit(
            operation_type=body.operation_type,
            payload=body.payload,
            requested_by=actor_id,
            required_approvals=body.required_approvals,
            expires_at=body.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await session.commit()
    return ApprovalRequestOut.model_validate(request)


@router.get("", response_model=list[ApprovalRequestOut])
async def list_approvals(
    session: Session,
    status: str | None = Query(None),
    operation_type: str | None = Query(None),
) -> list[ApprovalRequestOut]:
    q = select(TenantApprovalRequest)
    if status:
        q = q.where(TenantApprovalRequest.status == status)
    if operation_type:
        q = q.where(TenantApprovalRequest.operation_type == operation_type)
    rows = (await session.execute(q)).scalars().all()
    return [ApprovalRequestOut.model_validate(r) for r in rows]


@router.get("/{request_id}", response_model=ApprovalRequestOut)
async def get_approval(request_id: uuid.UUID, session: Session) -> ApprovalRequestOut:
    row = (
        await session.execute(
            select(TenantApprovalRequest).where(TenantApprovalRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return ApprovalRequestOut.model_validate(row)


@router.post("/{request_id}/approve", response_model=ApprovalRequestOut)
async def approve(
    request_id: uuid.UUID,
    body: ApprovalActionRequest,
    session: Session,
    actor_id: Actor,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.approve(
            request_id=request_id, actor_user_id=actor_id, comment=body.comment
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await session.commit()
    return ApprovalRequestOut.model_validate(request)


@router.post("/{request_id}/reject", response_model=ApprovalRequestOut)
async def reject(
    request_id: uuid.UUID,
    body: RejectRequest,
    session: Session,
    actor_id: Actor,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.reject(
            request_id=request_id, actor_user_id=actor_id, reason=body.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await session.commit()
    return ApprovalRequestOut.model_validate(request)


@router.post("/{request_id}/cancel", response_model=ApprovalRequestOut)
async def cancel(
    request_id: uuid.UUID,
    body: ApprovalActionRequest,
    session: Session,
    actor_id: Actor,
) -> ApprovalRequestOut:
    svc = ApprovalService(session)
    try:
        request = await svc.cancel(request_id=request_id, requested_by=actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await session.commit()
    return ApprovalRequestOut.model_validate(request)
```

- [ ] **Run ruff + mypy:**

```bash
ruff check app/modules/maker_checker/ && mypy app/modules/maker_checker/schemas.py app/modules/maker_checker/api.py
```

- [ ] **Commit:**

```bash
git add app/modules/maker_checker/schemas.py app/modules/maker_checker/api.py
git commit -m "feat: add maker-checker Pydantic schemas and FastAPI router"
```

---

## Task 17: Maker-checker tests

**Files:**
- Create: `tests/modules/__init__.py`
- Create: `tests/modules/maker_checker/__init__.py`
- Create: `tests/modules/maker_checker/test_registry.py`
- Create: `tests/modules/maker_checker/test_service.py`
- Create: `tests/modules/maker_checker/test_api.py`

- [ ] **Create `__init__.py` files** (both empty).

- [ ] **Create `tests/modules/maker_checker/test_registry.py`:**

```python
import pytest
from app.modules.maker_checker.registry import approval_executor, approval_registry, operation_type_permissions


def test_approval_executor_registers_function():
    @approval_executor("test.noop", required_permission="test:approve")
    async def _noop(session, payload):
        return {}

    assert "test.noop" in approval_registry
    assert approval_registry["test.noop"] is _noop
    assert operation_type_permissions["test.noop"] == "test:approve"


def test_approval_executor_without_permission():
    @approval_executor("test.noop2")
    async def _noop2(session, payload):
        return {}

    assert "test.noop2" in approval_registry
    assert "test.noop2" not in operation_type_permissions
```

- [ ] **Create `tests/modules/maker_checker/test_service.py`:**

```python
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.modules.maker_checker.models.tenant import TenantApprovalRequest
from app.modules.maker_checker.registry import approval_registry
from app.modules.maker_checker.service import ApprovalService


# Register a test executor
_exec_calls: list = []

async def _test_executor(session, payload):
    _exec_calls.append(payload)
    return {"done": True}

approval_registry["test.op"] = _test_executor


async def _submit(session, **kwargs):
    svc = ApprovalService(session)
    defaults = dict(
        operation_type="test.op",
        payload={"x": 1},
        requested_by=uuid.uuid4(),
    )
    defaults.update(kwargs)
    return await svc.submit(**defaults)


async def test_submit_creates_pending_request(tenant_session):
    req = await _submit(tenant_session)
    await tenant_session.flush()
    assert req.status == "pending"
    assert req.id is not None


async def test_submit_unknown_operation_raises(tenant_session):
    svc = ApprovalService(tenant_session)
    with pytest.raises(ValueError, match="No executor registered"):
        await svc.submit(operation_type="unknown.op", payload={}, requested_by=uuid.uuid4())


async def test_approve_below_quorum_stays_pending(tenant_session):
    req = await _submit(tenant_session, required_approvals=2)
    await tenant_session.flush()

    svc = ApprovalService(tenant_session)
    checker = uuid.uuid4()
    updated = await svc.approve(request_id=req.id, actor_user_id=checker)
    assert updated.status == "pending"


async def test_approve_meeting_quorum_executes(tenant_session):
    _exec_calls.clear()
    maker = uuid.uuid4()
    req = await _submit(tenant_session, requested_by=maker, required_approvals=1)
    await tenant_session.flush()

    svc = ApprovalService(tenant_session)
    checker = uuid.uuid4()
    updated = await svc.approve(request_id=req.id, actor_user_id=checker)
    assert updated.status == "executed"
    assert len(_exec_calls) == 1


async def test_self_approval_raises(tenant_session):
    maker = uuid.uuid4()
    req = await _submit(tenant_session, requested_by=maker)
    await tenant_session.flush()

    svc = ApprovalService(tenant_session)
    with pytest.raises(ValueError, match="Self-approval"):
        await svc.approve(request_id=req.id, actor_user_id=maker)


async def test_reject_terminates_request(tenant_session):
    req = await _submit(tenant_session)
    await tenant_session.flush()

    svc = ApprovalService(tenant_session)
    checker = uuid.uuid4()
    updated = await svc.reject(request_id=req.id, actor_user_id=checker, reason="policy")
    assert updated.status == "rejected"
    assert updated.rejection_reason == "policy"


async def test_action_on_rejected_request_raises(tenant_session):
    req = await _submit(tenant_session)
    await tenant_session.flush()

    svc = ApprovalService(tenant_session)
    checker = uuid.uuid4()
    await svc.reject(request_id=req.id, actor_user_id=checker)
    with pytest.raises(ValueError, match="not 'pending'"):
        await svc.approve(request_id=req.id, actor_user_id=uuid.uuid4())


async def test_cancel_before_any_action(tenant_session):
    maker = uuid.uuid4()
    req = await _submit(tenant_session, requested_by=maker)
    await tenant_session.flush()

    svc = ApprovalService(tenant_session)
    updated = await svc.cancel(request_id=req.id, requested_by=maker)
    assert updated.status == "cancelled"


async def test_cancel_after_action_raises(tenant_session):
    maker = uuid.uuid4()
    req = await _submit(tenant_session, requested_by=maker, required_approvals=2)
    await tenant_session.flush()

    svc = ApprovalService(tenant_session)
    checker = uuid.uuid4()
    await svc.approve(request_id=req.id, actor_user_id=checker)

    with pytest.raises(ValueError, match="Cannot cancel"):
        await svc.cancel(request_id=req.id, requested_by=maker)


async def test_double_vote_raises(tenant_session):
    req = await _submit(tenant_session, required_approvals=2)
    await tenant_session.flush()

    svc = ApprovalService(tenant_session)
    checker = uuid.uuid4()
    await svc.approve(request_id=req.id, actor_user_id=checker)

    # Second approve from same checker should hit unique constraint
    from sqlalchemy.exc import IntegrityError
    with pytest.raises((IntegrityError, ValueError)):
        await svc.approve(request_id=req.id, actor_user_id=checker)


async def test_executor_failure_marks_execution_failed(tenant_session):
    async def _failing_executor(session, payload):
        raise RuntimeError("boom")

    approval_registry["test.failing"] = _failing_executor
    req = await _submit(tenant_session, operation_type="test.failing", required_approvals=1)
    await tenant_session.flush()

    svc = ApprovalService(tenant_session)
    updated = await svc.approve(request_id=req.id, actor_user_id=uuid.uuid4())
    assert updated.status == "execution_failed"
    assert "boom" in (updated.execution_result or {}).get("error", "")
```

- [ ] **Create `tests/modules/maker_checker/test_api.py`:**

```python
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan
from app.modules.maker_checker.registry import approval_registry


approval_registry["api.test.op"] = AsyncMock(return_value={"done": True})

MAKER_ID = str(uuid.uuid4())
CHECKER_ID = str(uuid.uuid4())


@pytest.fixture
async def client():
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_submit_returns_201(client):
    resp = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}, "required_approvals": 1},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["operation_type"] == "api.test.op"


async def test_get_approval(client):
    post = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    rid = post.json()["id"]
    resp = await client.get(f"/approvals/{rid}", headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID})
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


async def test_approve_executes_on_quorum(client):
    post = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}, "required_approvals": 1},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    rid = post.json()["id"]
    resp = await client.post(
        f"/approvals/{rid}/approve",
        json={},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": CHECKER_ID},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "executed"


async def test_cancel_by_maker(client):
    post = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}, "required_approvals": 2},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    rid = post.json()["id"]
    resp = await client.post(
        f"/approvals/{rid}/cancel",
        json={},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_unknown_operation_returns_400(client):
    resp = await client.post(
        "/approvals",
        json={"operation_type": "no.such.op", "payload": {}},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    assert resp.status_code == 400
```

- [ ] **Run maker-checker tests:**

```bash
pytest tests/modules/maker_checker/ -v
```

Expected: all pass.

- [ ] **Commit:**

```bash
git add tests/modules/
git commit -m "test: maker-checker registry, service, and API integration tests"
```

---

## Task 18: Wire router into app + CLAUDE.md + CI lint rule

**Files:**
- Modify: `app/main.py`
- Modify: `CLAUDE.md`
- Create: `.github/workflows/lint.yml`

- [ ] **Add maker_checker router to `app/main.py`** — add after the CORS middleware block:

```python
# After existing middleware setup, before health endpoints:
from app.modules.maker_checker.api import router as maker_checker_router
app.include_router(maker_checker_router)
```

- [ ] **Append to `CLAUDE.md`:**

```markdown

## Core module contracts (do not violate)
- Direct RabbitMQ client usage is forbidden outside `app/core/outbox/`. All events go through `EventPublisher.publish()`.
- All event consumers must check `processed_events` before acting. At-least-once delivery is the contract.
- Approvable operations must be registered via `@approval_executor` and invoked through `ApprovalService`. Direct execution paths for approvable operations are forbidden.
```

- [ ] **Create `.github/workflows/lint.yml`:**

```yaml
name: Lint

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dev dependencies
        run: pip install -e ".[dev]"

      - name: ruff check
        run: ruff check app/ tests/

      - name: mypy
        run: mypy app/

      - name: Enforce outbox import boundary
        run: |
          # Fail if aio_pika / pika / kombu is imported outside app/core/outbox/
          if rg "import (pika|aio_pika|kombu)" --glob "**/*.py" \
               --glob "!app/core/outbox/**" app/ tests/ 2>/dev/null; then
            echo "ERROR: Direct RabbitMQ client import detected outside app/core/outbox/"
            exit 1
          fi
          echo "Outbox boundary check passed."
```

- [ ] **Run full test suite:**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Run ruff + mypy on full project:**

```bash
ruff check app/ tests/ && mypy app/
```

Expected: clean.

- [ ] **Final commit:**

```bash
git add app/main.py CLAUDE.md .github/
git commit -m "feat: wire maker-checker router, add core contracts to CLAUDE.md, add CI lint workflow"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] §3 Audit — dual-table models, AuditableMixin, PlatformAuditService/TenantAuditService → Tasks 4–7
- [x] §3.3 actor_type from structlog context vars → Task 5 (mixin.py `_actor_context`)
- [x] §4 Outbox — dual-table models, EventPublisher, SKIP LOCKED relay, backoff, dead-lettering → Tasks 8–13
- [x] §4.2 processed_events table → Tasks 2–3 (migrations)
- [x] §4.5 sacco.events topic exchange, routing key format → Task 11 (worker.py)
- [x] §4.7 CI lint rule (rg check) → Task 18
- [x] §5 Maker-checker — models, registry, ApprovalService, schemas, API → Tasks 14–17
- [x] §5.3 Expiry beat task → Task 15 (service.py `expire_approval_requests`)
- [x] §5.2 DB trigger for self-approval → Tasks 2–3 (migrations)
- [x] §8 CLAUDE.md additions → Task 18
- [x] §9 Permission stub until IAM → Task 16 (api.py comment + `_get_actor`)

**Type consistency check:**
- `ApprovalService.submit/approve/reject/cancel` — signatures match what test_service.py calls ✓
- `EventPublisher.publish(session, aggregate_type=, aggregate_id=, event_type=, payload=)` — keyword args used consistently ✓
- `PlatformAuditService / TenantAuditService` constructor takes `AsyncSession` ✓
- `_relay_outbox(session, model_cls, context, rabbitmq_url)` — matches test mocking ✓
