# IAM v1-03: Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement server-side session tables (`platform.platform_sessions`, `<tenant>.tenant_sessions`), the `SessionService` that creates, fetches, and revokes session rows, and a Redis-backed jti validity layer that provides fast refresh-token revocation without a DB hit on every token validation.

**Architecture:** Two separate SQLAlchemy models share the same column layout but live in different schemas. `SessionService` is initialized with a DB session and the model class (`PlatformSession` or `TenantSession`); the same service code drives both contexts. Refresh-token JTIs are written to Redis (`iam:jti:{jti}` key with TTL = refresh lifetime) on session creation and deleted on revocation — making revocation effective immediately without waiting for token expiry. A daily Celery beat task calls `cleanup_expired()` for both schemas to prevent unbounded table growth.

**Tech Stack:** SQLAlchemy 2.0 async, redis-py (async), Alembic, Celery 5, pytest-anyio, unittest.mock

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — architectural rules
2. `docs/superpowers/decisions/2026-05-21-iam-architecture.md` §5 — server-side session tables; §3 — token lifetimes
3. `docs/superpowers/specs/2026-05-21-iam-v1-design.md` §3.2, §3.3, §6 — session table schemas and SessionService spec
4. `app/core/db.py` — `Base`, `AsyncSessionFactory`, `get_platform_session`, `get_tenant_session`
5. `app/modules/iam/keys/service.py` — `KeyService` (model for service structure; sessions follow the same pattern)
6. `app/workers/celery_app.py` — beat schedule (cleanup task added here)
7. `app/modules/iam/beat.py` — existing beat tasks from Plan 01 (cleanup_sessions added here)
8. `tests/conftest.py` — `platform_session`, `tenant_session`, `test_engine` fixtures
9. `alembic/platform/versions/003_iam_platform.py` — last platform migration (`down_revision` for the new one)
10. `alembic/tenant/versions/001_core_tenant.py` — last tenant migration (`down_revision` for the new one)

---

## File Map

```
CREATE app/modules/iam/sessions/__init__.py
CREATE app/modules/iam/sessions/models.py   — PlatformSession, TenantSession
CREATE app/modules/iam/sessions/service.py  — SessionService
CREATE tests/modules/iam/sessions/__init__.py
CREATE tests/modules/iam/sessions/test_session_service.py
CREATE alembic/platform/versions/004_iam_platform_sessions.py  — platform.platform_sessions DDL
CREATE alembic/tenant/versions/002_iam_tenant_sessions.py      — tenant_sessions DDL
MODIFY tests/conftest.py              — import session models into test_engine
MODIFY app/modules/iam/beat.py        — add cleanup_sessions Celery task
MODIFY app/workers/celery_app.py      — add cleanup_sessions to beat schedule
```

---

### Task 1: PlatformSession and TenantSession models

**Files:**
- Create: `app/modules/iam/sessions/__init__.py`
- Create: `app/modules/iam/sessions/models.py`
- Create: `tests/modules/iam/sessions/__init__.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/iam/sessions/test_session_service.py
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.iam.sessions.models import PlatformSession, TenantSession


@pytest.mark.anyio
async def test_platform_session_model_persists(platform_session):
    row = PlatformSession(
        platform_user_id=uuid.uuid4(),
        jti="test-jti-001",
        user_agent="pytest/1.0",
        ip_address="127.0.0.1",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    platform_session.add(row)
    await platform_session.flush()

    result = await platform_session.execute(
        select(PlatformSession).where(PlatformSession.jti == "test-jti-001")
    )
    fetched = result.scalar_one()
    assert isinstance(fetched.id, uuid.UUID)
    assert fetched.revoked_at is None
    assert fetched.last_used_at is None


@pytest.mark.anyio
async def test_tenant_session_model_persists(tenant_session):
    row = TenantSession(
        tenant_user_id=uuid.uuid4(),
        jti="test-jti-002",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=8),
    )
    tenant_session.add(row)
    await tenant_session.flush()

    result = await tenant_session.execute(
        select(TenantSession).where(TenantSession.jti == "test-jti-002")
    )
    fetched = result.scalar_one()
    assert isinstance(fetched.id, uuid.UUID)
    assert fetched.tenant_user_id is not None
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/modules/iam/sessions/test_session_service.py -v -k "model_persists"
```

Expected: `ImportError` — `models.py` does not exist yet

- [ ] **Step 3: Create directory structure**

```bash
mkdir -p app/modules/iam/sessions tests/modules/iam/sessions
touch app/modules/iam/sessions/__init__.py tests/modules/iam/sessions/__init__.py
```

- [ ] **Step 4: Create `app/modules/iam/sessions/models.py`**

```python
"""SQLAlchemy models for server-side session tracking.

Two models — PlatformSession (platform schema) and TenantSession (no schema,
resolved via search_path) — share an identical column layout. The only
structural difference is the user FK column name.

Sessions are NOT auditable (no AuditableMixin). Auth audit events are written
explicitly in the auth service layer (Plan 11) rather than by the ORM hook,
because the audit record needs richer context (IP, user agent, reason) than
the generic mixin captures.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — used at runtime by SQLAlchemy

from sqlalchemy import Index, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PlatformSession(Base):
    """Server-side session for a platform user.

    ``id`` is used as the ``session_id`` claim in the JWT so the session row
    can be fetched directly by primary key on every authenticated request.

    ``jti`` is the refresh token's JWT ID — stored here so the refresh token
    can be revoked individually (delete the Redis jti key; set revoked_at).
    """

    __tablename__ = "platform_sessions"
    __table_args__ = (
        Index("ix_platform_sessions_platform_user_id", "platform_user_id"),
        Index("ix_platform_sessions_jti", "jti"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    platform_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    jti: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class TenantSession(Base):
    """Server-side session for a tenant user.

    Identical layout to PlatformSession except the user FK column is
    ``tenant_user_id``. Lives in the tenant schema — no ``schema=`` in
    ``__table_args__``; resolved at runtime via ``SET LOCAL search_path``.
    """

    __tablename__ = "tenant_sessions"
    __table_args__ = (
        Index("ix_tenant_sessions_tenant_user_id", "tenant_user_id"),
        Index("ix_tenant_sessions_jti", "jti"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    jti: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
```

- [ ] **Step 5: Register session models in `tests/conftest.py`**

Inside the `test_engine` fixture body, add after any existing model imports:

```python
import app.modules.iam.sessions.models  # noqa: F401 — registers PlatformSession, TenantSession in Base.metadata
```

> `TenantSession` has no `schema=` so `create_all` with `SET search_path TO tenant_test, platform` will
> place it in `tenant_test`. `PlatformSession` has `schema="platform"` and lands in the platform schema.

- [ ] **Step 6: Run model tests to confirm pass**

```bash
pytest tests/modules/iam/sessions/test_session_service.py -v -k "model_persists"
```

Expected: 2 tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/modules/iam/sessions/ tests/modules/iam/sessions/ tests/conftest.py
git commit -m "feat(iam): PlatformSession and TenantSession SQLAlchemy models"
```

---

### Task 2: Platform migration 004 — platform_sessions DDL

**Files:**
- Create: `alembic/platform/versions/004_iam_platform_sessions.py`

- [ ] **Step 1: Verify the migration chain**

```bash
ls alembic/platform/versions/
```

Expected: `001_core_platform.py  002_platform_module.py  003_iam_platform.py`

- [ ] **Step 2: Create `alembic/platform/versions/004_iam_platform_sessions.py`**

```python
"""Create platform.platform_sessions.

Revision: 004
Depends on: 003 (platform_users must exist; platform_user_id FK references it)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_sessions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("platform_user_id", sa.UUID(), nullable=False),
        sa.Column("jti", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["platform_user_id"],
            ["platform.platform_users.id"],
            name="fk_platform_sessions_platform_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("jti", name="uq_platform_sessions_jti"),
        schema="platform",
    )
    op.create_index(
        "ix_platform_sessions_platform_user_id",
        "platform_sessions",
        ["platform_user_id"],
        schema="platform",
    )
    op.create_index(
        "ix_platform_sessions_jti",
        "platform_sessions",
        ["jti"],
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_sessions_jti",
        table_name="platform_sessions",
        schema="platform",
    )
    op.drop_index(
        "ix_platform_sessions_platform_user_id",
        table_name="platform_sessions",
        schema="platform",
    )
    op.drop_table("platform_sessions", schema="platform")
```

- [ ] **Step 3: Verify syntax**

```bash
python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('m004', 'alembic/platform/versions/004_iam_platform_sessions.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.revision == '004' and m.down_revision == '003'
print('Migration 004 OK')
"
```

Expected: `Migration 004 OK`

- [ ] **Step 4: Commit**

```bash
git add alembic/platform/versions/004_iam_platform_sessions.py
git commit -m "feat(iam): migration 004 — platform.platform_sessions"
```

---

### Task 3: Tenant migration 002 — tenant_sessions DDL

**Files:**
- Create: `alembic/tenant/versions/002_iam_tenant_sessions.py`

- [ ] **Step 1: Verify the tenant migration chain**

```bash
ls alembic/tenant/versions/
```

Expected: `001_core_tenant.py`

- [ ] **Step 2: Create `alembic/tenant/versions/002_iam_tenant_sessions.py`**

```python
"""Create tenant_sessions in the tenant schema.

Tables are created in whatever schema is set by SET search_path
(see alembic/tenant/env.py). No schema= qualifier is used; the
session applies the search_path before running this migration.

Revision: 002
Depends on: 001 (tenant schema structure must exist)

Note: tenant_user_id has no FK yet — tenant_users does not exist
until Plan 04 migration 003_iam_tenant_users.py runs. The column
stores a UUID and the FK will be added by that migration.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_sessions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("tenant_user_id", sa.UUID(), nullable=False),
        sa.Column("jti", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("jti", name="uq_tenant_sessions_jti"),
        # No schema= — resolved at runtime via search_path.
    )
    op.create_index(
        "ix_tenant_sessions_tenant_user_id",
        "tenant_sessions",
        ["tenant_user_id"],
    )
    op.create_index(
        "ix_tenant_sessions_jti",
        "tenant_sessions",
        ["jti"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_sessions_jti", table_name="tenant_sessions")
    op.drop_index("ix_tenant_sessions_tenant_user_id", table_name="tenant_sessions")
    op.drop_table("tenant_sessions")
```

- [ ] **Step 3: Verify syntax**

```bash
python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('m002t', 'alembic/tenant/versions/002_iam_tenant_sessions.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.revision == '002' and m.down_revision == '001'
print('Tenant migration 002 OK')
"
```

Expected: `Tenant migration 002 OK`

- [ ] **Step 4: Commit**

```bash
git add alembic/tenant/versions/002_iam_tenant_sessions.py
git commit -m "feat(iam): tenant migration 002 — tenant_sessions (no FK to tenant_users yet)"
```

---

### Task 4: SessionService — DB operations

**Files:**
- Create: `app/modules/iam/sessions/service.py`
- Modify: `tests/modules/iam/sessions/test_session_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/iam/sessions/test_session_service.py`:

```python
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.modules.iam.sessions.models import PlatformSession, TenantSession
from app.modules.iam.sessions.service import SessionService


# ── Helper ─────────────────────────────────────────────────────────────────

def _platform_svc(db, redis=None) -> SessionService:
    return SessionService(db=db, model_cls=PlatformSession, redis=redis)


def _tenant_svc(db, redis=None) -> SessionService:
    return SessionService(db=db, model_cls=TenantSession, redis=redis)


# ── create ──────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_create_platform_session_inserts_row(platform_session):
    user_id = uuid.uuid4()
    svc = _platform_svc(platform_session)

    row = await svc.create(
        user_id=user_id,
        jti="jti-platform-001",
        user_agent="Mozilla/5.0",
        ip_address="10.0.0.1",
        refresh_ttl_seconds=3600,
    )
    await platform_session.flush()

    assert isinstance(row.id, uuid.UUID)
    assert row.platform_user_id == user_id
    assert row.jti == "jti-platform-001"
    assert row.revoked_at is None
    assert row.expires_at > row.created_at


@pytest.mark.anyio
async def test_create_tenant_session_inserts_row(tenant_session):
    user_id = uuid.uuid4()
    svc = _tenant_svc(tenant_session)

    row = await svc.create(
        user_id=user_id,
        jti="jti-tenant-001",
        user_agent=None,
        ip_address=None,
        refresh_ttl_seconds=28800,
    )
    await tenant_session.flush()

    assert row.tenant_user_id == user_id
    assert row.jti == "jti-tenant-001"


@pytest.mark.anyio
async def test_create_calls_redis_set_with_ttl(platform_session):
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    svc = _platform_svc(platform_session, redis=mock_redis)

    await svc.create(
        user_id=uuid.uuid4(),
        jti="jti-redis-test",
        user_agent=None,
        ip_address=None,
        refresh_ttl_seconds=3600,
    )

    mock_redis.set.assert_called_once_with(
        "iam:jti:jti-redis-test", "1", ex=3600
    )


@pytest.mark.anyio
async def test_create_without_redis_does_not_raise(platform_session):
    # Redis=None is valid — used in tests and batch contexts without Redis access.
    svc = _platform_svc(platform_session, redis=None)
    row = await svc.create(
        user_id=uuid.uuid4(),
        jti="jti-no-redis",
        user_agent=None,
        ip_address=None,
        refresh_ttl_seconds=3600,
    )
    assert row.jti == "jti-no-redis"


# ── get_by_session_id ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_by_session_id_returns_existing_row(platform_session):
    svc = _platform_svc(platform_session)
    row = await svc.create(
        user_id=uuid.uuid4(), jti="jti-get-001",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()

    fetched = await svc.get_by_session_id(row.id)
    assert fetched is not None
    assert fetched.id == row.id


@pytest.mark.anyio
async def test_get_by_session_id_returns_none_for_missing(platform_session):
    svc = _platform_svc(platform_session)
    result = await svc.get_by_session_id(uuid.uuid4())
    assert result is None


# ── revoke ───────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_revoke_sets_revoked_at(platform_session):
    svc = _platform_svc(platform_session)
    row = await svc.create(
        user_id=uuid.uuid4(), jti="jti-revoke-001",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()

    await svc.revoke(row.id)
    await platform_session.flush()

    await platform_session.refresh(row)
    assert row.revoked_at is not None


@pytest.mark.anyio
async def test_revoke_deletes_redis_jti(platform_session):
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.delete = AsyncMock()
    svc = _platform_svc(platform_session, redis=mock_redis)

    row = await svc.create(
        user_id=uuid.uuid4(), jti="jti-revoke-redis",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()

    await svc.revoke(row.id)

    mock_redis.delete.assert_called_once_with("iam:jti:jti-revoke-redis")


@pytest.mark.anyio
async def test_revoke_is_idempotent(platform_session):
    svc = _platform_svc(platform_session)
    row = await svc.create(
        user_id=uuid.uuid4(), jti="jti-revoke-idem",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()

    first_revoked_at = datetime.now(UTC)
    await svc.revoke(row.id)
    await platform_session.flush()
    await svc.revoke(row.id)  # second call must not raise or change revoked_at
    await platform_session.flush()

    await platform_session.refresh(row)
    # revoked_at should be close to first_revoked_at, not updated on second call
    assert row.revoked_at is not None


# ── revoke_all_for_user ──────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_revoke_all_for_user_revokes_all_active_sessions(platform_session):
    user_id = uuid.uuid4()
    svc = _platform_svc(platform_session)

    s1 = await svc.create(
        user_id=user_id, jti="jti-bulk-001",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    s2 = await svc.create(
        user_id=user_id, jti="jti-bulk-002",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()

    count = await svc.revoke_all_for_user(user_id)
    await platform_session.flush()

    assert count == 2
    await platform_session.refresh(s1)
    await platform_session.refresh(s2)
    assert s1.revoked_at is not None
    assert s2.revoked_at is not None


@pytest.mark.anyio
async def test_revoke_all_for_user_skips_already_revoked_sessions(platform_session):
    user_id = uuid.uuid4()
    svc = _platform_svc(platform_session)

    s1 = await svc.create(
        user_id=user_id, jti="jti-bulk-skip-001",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()
    await svc.revoke(s1.id)
    await platform_session.flush()

    # Create a second, still-active session
    s2 = await svc.create(
        user_id=user_id, jti="jti-bulk-skip-002",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()

    count = await svc.revoke_all_for_user(user_id)
    assert count == 1  # only the non-revoked session


# ── cleanup_expired ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_cleanup_expired_deletes_rows_past_retention(platform_session):
    user_id = uuid.uuid4()
    svc = _platform_svc(platform_session)

    # Session that expired 8 days ago — should be deleted.
    old = await svc.create(
        user_id=user_id, jti="jti-expired-old",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()
    old.expires_at = datetime.now(UTC) - timedelta(days=8)
    await platform_session.flush()

    # Session that expired 1 day ago — still within 7-day retention window.
    recent = await svc.create(
        user_id=user_id, jti="jti-expired-recent",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()
    recent.expires_at = datetime.now(UTC) - timedelta(days=1)
    await platform_session.flush()

    deleted = await svc.cleanup_expired()
    await platform_session.flush()

    assert deleted == 1

    result = await platform_session.execute(
        select(PlatformSession).where(PlatformSession.jti == "jti-expired-old")
    )
    assert result.scalar_one_or_none() is None

    result = await platform_session.execute(
        select(PlatformSession).where(PlatformSession.jti == "jti-expired-recent")
    )
    assert result.scalar_one_or_none() is not None


# ── is_jti_valid ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_is_jti_valid_returns_true_when_redis_has_key(platform_session):
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)
    svc = _platform_svc(platform_session, redis=mock_redis)

    assert await svc.is_jti_valid("jti-exists") is True
    mock_redis.exists.assert_called_once_with("iam:jti:jti-exists")


@pytest.mark.anyio
async def test_is_jti_valid_returns_false_when_redis_missing_key(platform_session):
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=0)
    svc = _platform_svc(platform_session, redis=mock_redis)

    assert await svc.is_jti_valid("jti-missing") is False


@pytest.mark.anyio
async def test_is_jti_valid_falls_back_to_db_when_redis_is_none(platform_session):
    """When Redis is unavailable, fall back to DB lookup.

    A session row that exists and is not revoked and not expired is valid.
    """
    svc = _platform_svc(platform_session, redis=None)
    row = await svc.create(
        user_id=uuid.uuid4(), jti="jti-db-fallback",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()

    assert await svc.is_jti_valid("jti-db-fallback") is True


@pytest.mark.anyio
async def test_is_jti_valid_db_fallback_returns_false_for_revoked(platform_session):
    svc = _platform_svc(platform_session, redis=None)
    row = await svc.create(
        user_id=uuid.uuid4(), jti="jti-db-revoked",
        user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
    )
    await platform_session.flush()
    await svc.revoke(row.id)
    await platform_session.flush()

    assert await svc.is_jti_valid("jti-db-revoked") is False
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/sessions/test_session_service.py -v -k "not model_persists"
```

Expected: `ImportError` — `service.py` does not exist yet

- [ ] **Step 3: Create `app/modules/iam/sessions/service.py`**

```python
"""SessionService: create, fetch, revoke, and clean up auth sessions.

Operates on either PlatformSession or TenantSession — the model class is
supplied at construction time. One service instance handles one schema context.

Redis is used for fast refresh-token JTI validation:
    Key:   iam:jti:{jti}
    Value: "1"  (existence is the signal — value is not read)
    TTL:   refresh_ttl_seconds (matches session expires_at)

On revocation, the Redis key is deleted immediately so the JTI becomes
invalid for new refresh attempts within seconds, without requiring the
old refresh token to expire. The DB row's revoked_at is also set.

When Redis is None (e.g., batch jobs, tests), JTI validity falls back to a
DB lookup: the session row must exist, be non-revoked, and be non-expired.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Union

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.sessions.models import PlatformSession, TenantSession

_log = structlog.get_logger(__name__)

_CLEANUP_RETENTION_DAYS = 7  # delete expired rows older than this

AnySessionModel = Union[PlatformSession, TenantSession]


class SessionService:
    """Manage server-side sessions for platform or tenant users.

    Args:
        db: An ``AsyncSession`` with the appropriate search_path already set
            (platform schema for PlatformSession; tenant schema for TenantSession).
        model_cls: The SQLAlchemy model class — ``PlatformSession`` or ``TenantSession``.
        redis: Optional async Redis client. When provided, JTI keys are stored
            and deleted in Redis for fast revocation checks. When ``None``,
            ``is_jti_valid`` falls back to a DB query.
    """

    def __init__(
        self,
        db: AsyncSession,
        model_cls: type[AnySessionModel],
        redis: object | None = None,
    ) -> None:
        self._db = db
        self._model = model_cls
        self._redis = redis
        # Determine the user FK attribute name at construction time.
        self._user_id_attr = (
            "platform_user_id" if model_cls is PlatformSession else "tenant_user_id"
        )

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        jti: str,
        user_agent: str | None,
        ip_address: str | None,
        refresh_ttl_seconds: int,
    ) -> AnySessionModel:
        """Insert a new session row and register the JTI in Redis.

        The session ``id`` (UUID) becomes the ``session_id`` claim in the JWT.
        The ``jti`` is the refresh token's JWT ID — stored for revocation.

        Returns the new session row (not yet committed).
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=refresh_ttl_seconds)

        if self._model is PlatformSession:
            row: AnySessionModel = PlatformSession(
                platform_user_id=user_id,
                jti=jti,
                user_agent=user_agent,
                ip_address=ip_address,
                created_at=now,
                expires_at=expires_at,
            )
        else:
            row = TenantSession(
                tenant_user_id=user_id,
                jti=jti,
                user_agent=user_agent,
                ip_address=ip_address,
                created_at=now,
                expires_at=expires_at,
            )

        self._db.add(row)

        if self._redis is not None:
            await self._redis.set(f"iam:jti:{jti}", "1", ex=refresh_ttl_seconds)

        return row

    async def get_by_session_id(
        self, session_id: uuid.UUID
    ) -> AnySessionModel | None:
        """Return the session row by primary key, or ``None`` if not found."""
        result = await self._db.execute(
            select(self._model).where(self._model.id == session_id)
        )
        return result.scalar_one_or_none()

    async def revoke(self, session_id: uuid.UUID) -> None:
        """Set ``revoked_at`` on the session row and delete its Redis JTI key.

        Idempotent — if the session is already revoked, the ``revoked_at``
        timestamp is not updated.
        """
        result = await self._db.execute(
            select(self._model).where(self._model.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return

        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)

        if self._redis is not None:
            await self._redis.delete(f"iam:jti:{row.jti}")

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke all non-revoked sessions for *user_id*.

        Returns the count of sessions that were revoked. Called on password
        change or explicit "log out everywhere" action.

        Note: does not delete Redis JTI keys individually — those will
        expire naturally. If immediate revocation of all refresh tokens is
        required, the caller must flush Redis keys separately. This trade-off
        is acceptable because ``revoke_all_for_user`` is called on password
        change, after which old refresh tokens will fail session validation
        (revoked_at is set) even if the Redis key still exists briefly.
        """
        user_id_col = getattr(self._model, self._user_id_attr)
        result = await self._db.execute(
            select(self._model).where(
                user_id_col == user_id,
                self._model.revoked_at.is_(None),
            )
        )
        rows = result.scalars().all()
        now = datetime.now(UTC)
        for row in rows:
            row.revoked_at = now
        return len(rows)

    async def cleanup_expired(self) -> int:
        """Delete session rows that expired more than 7 days ago.

        Called by the ``cleanup_sessions`` Celery beat task. Returns the
        number of rows deleted.
        """
        cutoff = datetime.now(UTC) - timedelta(days=_CLEANUP_RETENTION_DAYS)
        result = await self._db.execute(
            delete(self._model)
            .where(self._model.expires_at < cutoff)
            .returning(self._model.id)
        )
        deleted_rows = result.fetchall()
        count = len(deleted_rows)
        if count:
            _log.info(
                "iam.sessions.cleanup",
                model=self._model.__tablename__,
                deleted=count,
            )
        return count

    async def is_jti_valid(self, jti: str) -> bool:
        """Return ``True`` if the refresh token JTI is still valid.

        Primary path: check Redis (O(1), no DB hit).
        Fallback (Redis=None): query the DB for a non-revoked, non-expired
        session row with this JTI.

        A JTI is invalid if:
        - Redis key is absent (normal expiry or explicit revocation), or
        - (DB fallback) no session row exists, or the row is revoked/expired.
        """
        if self._redis is not None:
            exists: int = await self._redis.exists(f"iam:jti:{jti}")
            return bool(exists)

        # DB fallback path.
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(self._model).where(
                self._model.jti == jti,
                self._model.revoked_at.is_(None),
                self._model.expires_at > now,
            )
        )
        return result.scalar_one_or_none() is not None
```

- [ ] **Step 4: Run all session service tests to confirm pass**

```bash
pytest tests/modules/iam/sessions/test_session_service.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/sessions/service.py tests/modules/iam/sessions/test_session_service.py
git commit -m "feat(iam): SessionService — create, revoke, revoke_all, cleanup, is_jti_valid; Redis jti tracking"
```

---

### Task 5: cleanup_sessions Celery beat task

**Files:**
- Modify: `app/modules/iam/beat.py`
- Modify: `app/workers/celery_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/modules/iam/test_beat.py`:

```python
def test_cleanup_sessions_is_registered_celery_task():
    from app.modules.iam.beat import cleanup_sessions
    from app.workers.celery_app import celery_app

    assert "app.modules.iam.beat.cleanup_sessions" in celery_app.tasks
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/modules/iam/test_beat.py::test_cleanup_sessions_is_registered_celery_task -v
```

Expected: `ImportError` or `AssertionError` — task not registered yet

- [ ] **Step 3: Add `cleanup_sessions` to `app/modules/iam/beat.py`**

Append after the existing `rotate_signing_keys_if_due` function:

```python
async def _run_cleanup_sessions() -> dict[str, int]:
    """Delete expired session rows for both platform and all active tenant schemas."""
    import re

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.modules.iam.sessions.models import PlatformSession, TenantSession
    from app.modules.iam.sessions.service import SessionService

    _SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    totals: dict[str, int] = {"platform": 0, "tenant": 0}

    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)

        # Platform sessions
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            svc = SessionService(db=session, model_cls=PlatformSession)
            totals["platform"] = await svc.cleanup_expired()
            await session.commit()

        # Tenant sessions — iterate active tenant schemas
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT schema_name FROM platform.tenants WHERE is_active = true"
                )
            )
            tenant_schemas = [row[0] for row in result.fetchall()]

        for schema_name in tenant_schemas:
            if not _SCHEMA_RE.match(schema_name):
                _log.error("iam.cleanup.invalid_schema", schema=schema_name)
                continue
            try:
                async with factory() as session:
                    await session.execute(
                        text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
                    )
                    svc = SessionService(db=session, model_cls=TenantSession)
                    deleted = await svc.cleanup_expired()
                    await session.commit()
                    totals["tenant"] += deleted
            except Exception as exc:
                _log.error(
                    "iam.cleanup.tenant_error",
                    schema=schema_name,
                    error=str(exc),
                )
    finally:
        await engine.dispose()

    _log.info("iam.sessions.cleanup_complete", **totals)
    return totals


@celery_app.task(name="app.modules.iam.beat.cleanup_sessions")  # type: ignore[misc]
def cleanup_sessions() -> dict[str, int]:
    """Daily: delete expired session rows for platform and all tenant schemas."""
    return asyncio.run(_run_cleanup_sessions())
```

- [ ] **Step 4: Add `cleanup_sessions` to the beat schedule in `app/workers/celery_app.py`**

Add inside the `beat_schedule` dict:

```python
"cleanup-iam-sessions": {
    "task": "app.modules.iam.beat.cleanup_sessions",
    "schedule": 24 * 3600.0,  # daily
},
```

- [ ] **Step 5: Run beat tests to confirm pass**

```bash
pytest tests/modules/iam/test_beat.py -v
```

Expected: All tests PASS (including the new `cleanup_sessions` test)

- [ ] **Step 6: Run full IAM suite to confirm no regressions**

```bash
pytest tests/modules/iam/ -v
```

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/modules/iam/beat.py app/workers/celery_app.py tests/modules/iam/test_beat.py
git commit -m "feat(iam): cleanup_sessions beat task — daily purge of expired session rows for all schemas"
```

---

## Verification Criteria

Before marking this plan complete, run the following:

```bash
# 1. Linting
ruff check app/modules/iam/sessions/ app/modules/iam/beat.py app/workers/celery_app.py

# 2. Type checking
mypy app/modules/iam/sessions/ --strict

# 3. Session tests
pytest tests/modules/iam/sessions/ -v

# 4. Beat tests (includes new cleanup_sessions entry)
pytest tests/modules/iam/test_beat.py -v

# 5. Migration syntax checks
python -c "
import importlib.util
for path, rev, down in [
    ('alembic/platform/versions/004_iam_platform_sessions.py', '004', '003'),
    ('alembic/tenant/versions/002_iam_tenant_sessions.py', '002', '001'),
]:
    spec = importlib.util.spec_from_file_location('m', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.revision == rev and m.down_revision == down, f'Bad chain: {path}'
    print(f'{path} OK')
"

# 6. Full regression suite
pytest tests/ -v
```

All commands must exit cleanly before this plan is considered complete.

---

## What is NOT in this plan

- `TenantUser` model and its migration — **Plan 04**
- The FK constraint from `tenant_sessions.tenant_user_id → tenant_users.id` — added in **Plan 04** migration `003_iam_tenant_users.py` once the `tenant_users` table exists
- Using `SessionService` from within auth endpoints — **Plans 05 and 06**
- A Redis fixture for integration tests — tests in this plan mock Redis with `AsyncMock`; a real-Redis integration test can be added in **Plan 12** when the full stack is verified
