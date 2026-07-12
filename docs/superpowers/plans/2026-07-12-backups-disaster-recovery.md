# Phase 4 — Backups & Disaster Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A provable, locally-tested PostgreSQL backup + point-in-time-recovery pipeline (pgBackRest → MinIO), an automated restore-verify drill, two platform status tables, three superuser ops endpoints, and a portal backups widget — with the whole pipeline exercised end-to-end in Docker Compose.

**Architecture:** pgBackRest runs WAL archiving + nightly base backups from the `postgres` container into a MinIO S3 bucket. A `backup` sidecar container runs cron jobs (base/verify/prune) plus a poll loop for on-demand verifications. Backup and drill scripts report status into `platform.backup_runs` / `platform.backup_verifications` via psql. A new `app/platform_/ops/` module exposes read + trigger endpoints over those tables; a portal page renders freshness tiles, a size-trend chart, a runs table, and a "Verify now" button.

**Tech Stack:** Docker Compose, PostgreSQL 16, pgBackRest, MinIO + mc, supercronic, FastAPI, SQLAlchemy 2.0 async, Alembic (platform chain), Next.js 15 App Router, `@sacco/ui`/`api-client`/`schemas`, vitest.

**Spec:** `docs/superpowers/specs/2026-07-12-backups-disaster-recovery-design.md`

Branch: `feat/backups-dr` (from `main`).

## Global Constraints

- **Money/tenancy rules unaffected** — this phase adds no financial tables and no tenant-schema tables. Both new tables live in the `platform` schema (`__table_args__ = {"schema": "platform"}`).
- **Platform Alembic chain:** new migration `012`, `down_revision = "011"`. Migrations live in `alembic/platform/versions/`.
- **Offline `alembic upgrade --sql` is broken repo-wide** (migration 002 executes queries). Smoke migrations against a scratch DB, never `--sql`.
- **Ops endpoints are `CurrentSuperuser`** (from `app.platform_.auth`), direct action, no maker-checker. Route handlers import the dep alias, never the underlying function.
- **`OpsService` is the only app-side writer** of `backup_runs` / `backup_verifications`. Backup scripts write via psql (the app image never gets the pgBackRest binary or an S3 client).
- **Portal contracts:** dates via `<RelativeTime>` / `<FormattedDateTime>` (H); tables via `<DataTable>` (T); confirmations via `<ConfirmDialog>` (V — direct action, not maker-checker); statuses via `<StatusBadge>` with new entities (S); no client-side fetch for initial render (M); `Idempotency-Key` auto-injected by the client (L).
- **This phase is a sanctioned exception to CLAUDE.md contract N** (portal-only): it edits `docker-compose.yml`, adds `infra/`, adds `app/platform_/ops/` + a platform migration, and adds a portal page. Documented in Task 12.
- pnpm lint/typecheck/test clean; ruff + mypy (strict) clean; backend tests use the platform-session fixture pattern (`async_sessionmaker` + commit + cleanup, NOT `flush()` — see `feedback_test_patterns`).

## File Structure

```
infra/backups/pgbackrest.conf                        (create: single pgBackRest config)
infra/backups/Dockerfile.postgres                    (create: postgres:16 + pgbackrest binary)
infra/backups/Dockerfile.backup                      (create: pgbackrest + supercronic + psql + mc)
infra/backups/crontab                                (create: base/verify/prune/poll schedules)
infra/backups/scripts/backup.sh                      (create: base backup + report)
infra/backups/scripts/restore-staging.sh             (create: the verify drill)
infra/backups/scripts/prune.sh                       (create: expire per retention)
infra/backups/scripts/poll-verify-requests.sh        (create: on-demand drill trigger)
infra/backups/scripts/lib.sh                         (create: shared psql-report helpers)
infra/backups/systemd/pgbackrest-backup.service      (create: prod host, documented)
infra/backups/systemd/pgbackrest-backup.timer        (create)
infra/backups/systemd/pgbackrest-verify.service      (create)
infra/backups/systemd/pgbackrest-verify.timer        (create)
infra/backups/README.md                              (create: local run + prod swap)
docker-compose.yml                                   (modify: minio, minio-setup, backup services; postgres build+archive)

app/platform_/ops/__init__.py                        (create)
app/platform_/ops/models.py                          (create: BackupRun, BackupVerification)
app/platform_/ops/schemas.py                         (create: Pydantic out-shapes)
app/platform_/ops/service.py                         (create: OpsService)
app/platform_/ops/api.py                             (create: 3 endpoints)
app/main.py                                           (modify: mount ops_router)
alembic/platform/versions/012_backup_ops.py          (create: two tables)
tests/platform_/ops/__init__.py                      (create)
tests/platform_/ops/test_api.py                      (create)
tests/platform_/ops/test_service.py                  (create)

admin/packages/schemas/src/ops.ts                    (create: wire types + Zod)
admin/packages/schemas/src/index.ts                  (modify: export)
admin/packages/schemas/src/__tests__/ops.test.ts     (create)
admin/packages/api-client/src/resources/ops.ts       (create)
admin/packages/api-client/src/resources/index.ts     (modify: register)
admin/packages/api-client/src/query-keys.ts          (modify: +ops keys)
admin/packages/api-client/src/__tests__/query-keys-ops.test.ts (create)
admin/packages/ui/src/components/StatusBadge/status-maps.ts (modify: +backup_run/backup_verification)

admin/apps/portal/app/platform/(authed)/operations/backups/page.tsx (create)
admin/apps/portal/app/platform/(authed)/operations/backups/_components/BackupFreshnessTiles.tsx (create)
admin/apps/portal/app/platform/(authed)/operations/backups/_components/BackupRunsTable.tsx (create)
admin/apps/portal/app/platform/(authed)/operations/backups/_components/VerifyNowButton.tsx (create)
admin/apps/portal/app/platform/(authed)/operations/backups/__tests__/BackupFreshnessTiles.test.tsx (create)
admin/apps/portal/app/platform/(authed)/operations/backups/__tests__/VerifyNowButton.test.tsx (create)
admin/apps/portal/src/components/shell/nav-config.tsx (modify: Operations children)

docs/runbooks/restore-from-pitr.md                   (create)
docs/runbooks/single-tenant-recovery.md              (create)
docs/runbooks/backup-verification.md                 (create)
docs/runbooks/drills/<date>-first-drill.md           (create: real drill output)
CLAUDE.md                                            (modify: Ops contracts + scope note)
```

---

### Task 1: Platform migration + models (`backup_runs`, `backup_verifications`)

**Files:**
- Create: `alembic/platform/versions/012_backup_ops.py`
- Create: `app/platform_/ops/__init__.py`, `app/platform_/ops/models.py`
- Test: `tests/platform_/ops/__init__.py`, `tests/platform_/ops/test_service.py` (models exercised via service in Task 2; this task's test is a migration smoke)

**Interfaces:**
- Produces: `BackupRun` (cols `id: UUID pk`, `backup_type: str`, `started_at: datetime`, `finished_at: datetime|None`, `status: str`, `repo_size_bytes: int|None`, `wal_lag_seconds: int|None`, `detail: str|None`, `created_at: datetime`), `BackupVerification` (cols `id: UUID pk`, `requested_by: UUID|None`, `status: str`, `detail: str|None`, `started_at: datetime|None`, `finished_at: datetime|None`, `created_at: datetime`). Both `__tablename__` in `platform` schema. No `AuditableMixin` (these are operational telemetry, not audited business state).

- [ ] **Step 1: Write the models**

`app/platform_/ops/models.py`:
```python
"""Operational telemetry for the backup/restore pipeline (platform schema).

These tables are written by the backup container's scripts (via psql) and by
OpsService. They are NOT audited business state — no AuditableMixin.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — runtime use by SQLAlchemy

from sqlalchemy import CheckConstraint, Index, Integer, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class BackupRun(Base):
    __tablename__ = "backup_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','succeeded','failed')",
            name="ck_backup_runs_status",
        ),
        CheckConstraint(
            "backup_type IN ('full','incr','diff')",
            name="ck_backup_runs_type",
        ),
        Index("ix_platform_backup_runs_created_at", "created_at"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    backup_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    repo_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wal_lag_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class BackupVerification(Base):
    __tablename__ = "backup_verifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested','running','passed','failed')",
            name="ck_backup_verifications_status",
        ),
        Index("ix_platform_backup_verifications_created_at", "created_at"),
        Index("ix_platform_backup_verifications_status", "status"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="requested")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
```

`app/platform_/ops/__init__.py`: empty file.

- [ ] **Step 2: Write the migration**

`alembic/platform/versions/012_backup_ops.py`:
```python
"""Backup/restore operational telemetry tables.

Revision: 012
Depends on: 011
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("backup_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("repo_size_bytes", sa.Integer(), nullable=True),
        sa.Column("wal_lag_seconds", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('running','succeeded','failed')", name="ck_backup_runs_status"),
        sa.CheckConstraint("backup_type IN ('full','incr','diff')", name="ck_backup_runs_type"),
        schema="platform",
    )
    op.create_index("ix_platform_backup_runs_created_at", "backup_runs", ["created_at"], schema="platform")
    op.create_table(
        "backup_verifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("requested_by", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("started_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('requested','running','passed','failed')", name="ck_backup_verifications_status"),
        schema="platform",
    )
    op.create_index("ix_platform_backup_verifications_created_at", "backup_verifications", ["created_at"], schema="platform")
    op.create_index("ix_platform_backup_verifications_status", "backup_verifications", ["status"], schema="platform")


def downgrade() -> None:
    op.drop_table("backup_verifications", schema="platform")
    op.drop_table("backup_runs", schema="platform")
```

- [ ] **Step 3: Smoke the migration against a scratch DB**

Run (postgres container is up):
```bash
docker compose exec -T postgres psql -U sacco -d sacco -c "CREATE DATABASE ops_smoke;"
DATABASE_URL="postgresql+asyncpg://sacco:sacco@localhost:5432/ops_smoke" venv/bin/alembic upgrade head
docker compose exec -T postgres psql -U sacco -d ops_smoke -c "\dt platform.*" | grep backup
docker compose exec -T postgres psql -U sacco -d sacco -c "DROP DATABASE ops_smoke;"
```
Expected: both `platform.backup_runs` and `platform.backup_verifications` listed.

- [ ] **Step 4: mypy + ruff on the new module**

Run: `venv/bin/mypy app/platform_/ops/models.py && venv/bin/ruff check app/platform_/ops/`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add app/platform_/ops/__init__.py app/platform_/ops/models.py alembic/platform/versions/012_backup_ops.py tests/platform_/ops/__init__.py
git commit -m "feat(ops): backup telemetry models + platform migration 012"
```

---

### Task 2: `OpsService` (read status, last-verified-at, request verification)

**Files:**
- Create: `app/platform_/ops/service.py`
- Test: `tests/platform_/ops/test_service.py`

**Interfaces:**
- Consumes: `BackupRun`, `BackupVerification` from Task 1.
- Produces: `OpsService(session)` with:
  - `async list_recent_runs(limit: int = 20) -> list[BackupRun]`
  - `async latest_verification() -> BackupVerification | None`
  - `async last_verified_at() -> datetime | None` (most recent `passed`, by `finished_at`)
  - `async request_verification(requested_by: uuid.UUID) -> BackupVerification` — raises `VerificationInProgress` if a row is `requested` or `running`.
  - Exception `VerificationInProgress(Exception)`.

- [ ] **Step 1: Write failing service tests**

`tests/platform_/ops/test_service.py` — use the platform-session pattern from `tests/platform_/tenant_users_admin/test_api.py` (async_sessionmaker + commit + explicit cleanup; NOT flush):
```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.platform_.ops.models import BackupRun, BackupVerification
from app.platform_.ops.service import OpsService, VerificationInProgress


@pytest.mark.asyncio
async def test_last_verified_at_returns_latest_passed(platform_engine):
    factory = async_sessionmaker(platform_engine, expire_on_commit=False)
    ids: list[uuid.UUID] = []
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        old = BackupVerification(
            status="passed", started_at=datetime.now(UTC) - timedelta(days=2),
            finished_at=datetime.now(UTC) - timedelta(days=2),
        )
        new = BackupVerification(
            status="passed", started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        failed = BackupVerification(
            status="failed", started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        s.add_all([old, new, failed])
        await s.flush()
        ids.extend([old.id, new.id, failed.id])
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            got = await OpsService(s).last_verified_at()
            assert got is not None
    finally:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(
                text("DELETE FROM platform.backup_verifications WHERE id = ANY(:ids)"),
                {"ids": ids},
            )


@pytest.mark.asyncio
async def test_request_verification_conflicts_when_pending(platform_engine):
    factory = async_sessionmaker(platform_engine, expire_on_commit=False)
    made: list[uuid.UUID] = []
    actor = uuid.uuid4()
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await OpsService(s).request_verification(requested_by=actor)
            await s.commit()
            made.append(row.id)
            assert row.status == "requested"
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            with pytest.raises(VerificationInProgress):
                await OpsService(s).request_verification(requested_by=actor)
    finally:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(
                text("DELETE FROM platform.backup_verifications WHERE id = ANY(:ids)"),
                {"ids": made},
            )
```

Add a `platform_engine` fixture if not already shared — check `tests/platform_/conftest.py` first; reuse the existing engine fixture (billing/tenant_users tests already have one). If none is importable, add:
```python
# tests/platform_/ops/conftest.py
import os
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

@pytest_asyncio.fixture
async def platform_engine():
    url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test")
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/platform_/ops/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: app.platform_.ops.service` / `VerificationInProgress`.

- [ ] **Step 3: Implement the service**

`app/platform_/ops/service.py`:
```python
"""Read/trigger operations over backup telemetry tables.

OpsService is the ONLY app-side writer of backup_verifications (via
request_verification). backup_runs are written exclusively by the backup
container's scripts; the app only reads them.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.platform_.ops.models import BackupRun, BackupVerification

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class VerificationInProgress(Exception):
    """A verification is already requested or running."""


class OpsService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def list_recent_runs(self, *, limit: int = 20) -> list[BackupRun]:
        q = select(BackupRun).order_by(BackupRun.created_at.desc()).limit(limit)
        return list((await self._db.execute(q)).scalars())

    async def latest_verification(self) -> BackupVerification | None:
        q = (
            select(BackupVerification)
            .order_by(BackupVerification.created_at.desc())
            .limit(1)
        )
        return (await self._db.execute(q)).scalars().first()

    async def last_verified_at(self) -> datetime | None:
        q = (
            select(BackupVerification.finished_at)
            .where(BackupVerification.status == "passed")
            .order_by(BackupVerification.finished_at.desc())
            .limit(1)
        )
        return (await self._db.execute(q)).scalars().first()

    async def request_verification(
        self, *, requested_by: uuid.UUID
    ) -> BackupVerification:
        pending = (
            select(BackupVerification.id)
            .where(BackupVerification.status.in_(("requested", "running")))
            .limit(1)
        )
        if (await self._db.execute(pending)).scalars().first() is not None:
            raise VerificationInProgress
        row = BackupVerification(requested_by=requested_by, status="requested")
        self._db.add(row)
        await self._db.flush()
        await self._db.refresh(row)
        return row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/platform_/ops/test_service.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: mypy + ruff**

Run: `venv/bin/mypy app/platform_/ops/service.py && venv/bin/ruff check app/platform_/ops/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/platform_/ops/service.py tests/platform_/ops/
git commit -m "feat(ops): OpsService for backup status + verification requests"
```

---

### Task 3: Ops API endpoints + router mount

**Files:**
- Create: `app/platform_/ops/schemas.py`, `app/platform_/ops/api.py`
- Modify: `app/main.py` (import + `app.include_router(ops_router)`)
- Test: `tests/platform_/ops/test_api.py`

**Interfaces:**
- Consumes: `OpsService`, `VerificationInProgress` (Task 2); `CurrentSuperuser`, `get_platform_session` (existing).
- Produces: `router` at prefix `/platform/ops` with:
  - `GET /platform/ops/backups` → `BackupStatusOut` (`{recent_runs: BackupRunOut[], latest_verification: BackupVerificationOut | null}`).
  - `GET /platform/ops/backups/last-verified-at` → `LastVerifiedOut` (`{last_verified_at: datetime | null}`).
  - `POST /platform/ops/backups/trigger-verification` → `BackupVerificationOut` (201), 409 on `VerificationInProgress`.

- [ ] **Step 1: Write the schemas**

`app/platform_/ops/schemas.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class BackupRunOut(BaseModel):
    id: uuid.UUID
    backup_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    repo_size_bytes: int | None
    wal_lag_seconds: int | None
    detail: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class BackupVerificationOut(BaseModel):
    id: uuid.UUID
    requested_by: uuid.UUID | None
    status: str
    detail: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class BackupStatusOut(BaseModel):
    recent_runs: list[BackupRunOut]
    latest_verification: BackupVerificationOut | None


class LastVerifiedOut(BaseModel):
    last_verified_at: datetime | None
```

- [ ] **Step 2: Write failing API tests**

`tests/platform_/ops/test_api.py` — mirror `tests/platform_/tenant_users_admin/test_api.py`: override `get_platform_session` with the async_sessionmaker+commit pattern, seed a superuser, use stub platform auth headers. Cover: (a) GET backups returns seeded runs + latest verification; (b) last-verified-at returns the passed row's finished_at; (c) trigger returns 201 `requested`; (d) trigger again → 409; (e) non-superuser → 403. (Copy the auth-override and superuser-seed helpers from the tenant_users_admin test verbatim — the engine, `_make_platform_session_override`, and stub-actor header setup are identical.)
```python
# Key assertions (full harness mirrors tenant_users_admin/test_api.py):
async def test_trigger_then_conflict(client, superuser_headers):
    r1 = await client.post("/platform/ops/backups/trigger-verification", headers=superuser_headers)
    assert r1.status_code == 201
    assert r1.json()["status"] == "requested"
    r2 = await client.post("/platform/ops/backups/trigger-verification", headers=superuser_headers)
    assert r2.status_code == 409

async def test_backups_requires_superuser(client, support_headers):
    r = await client.get("/platform/ops/backups", headers=support_headers)
    assert r.status_code == 403
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `venv/bin/pytest tests/platform_/ops/test_api.py -v`
Expected: FAIL (router not mounted / 404).

- [ ] **Step 4: Implement the API**

`app/platform_/ops/api.py`:
```python
"""FastAPI router for /platform/ops/backups (superuser-only, direct action)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.platform_.auth import CurrentSuperuser
from app.platform_.ops.schemas import (
    BackupRunOut,
    BackupStatusOut,
    BackupVerificationOut,
    LastVerifiedOut,
)
from app.platform_.ops.service import OpsService, VerificationInProgress

router = APIRouter(prefix="/platform/ops", tags=["platform-ops"])

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]


@router.get("/backups", response_model=BackupStatusOut)
async def get_backup_status(
    session: PlatformSession, _user: CurrentSuperuser
) -> BackupStatusOut:
    svc = OpsService(session)
    runs = await svc.list_recent_runs()
    latest = await svc.latest_verification()
    return BackupStatusOut(
        recent_runs=[BackupRunOut.model_validate(r) for r in runs],
        latest_verification=(
            BackupVerificationOut.model_validate(latest) if latest else None
        ),
    )


@router.get("/backups/last-verified-at", response_model=LastVerifiedOut)
async def get_last_verified_at(
    session: PlatformSession, _user: CurrentSuperuser
) -> LastVerifiedOut:
    return LastVerifiedOut(last_verified_at=await OpsService(session).last_verified_at())


@router.post(
    "/backups/trigger-verification",
    response_model=BackupVerificationOut,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_verification(
    session: PlatformSession, user: CurrentSuperuser
) -> BackupVerificationOut:
    try:
        row = await OpsService(session).request_verification(requested_by=user.id)
    except VerificationInProgress as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A verification is already requested or running.",
        ) from exc
    return BackupVerificationOut.model_validate(row)
```

`app/main.py`: add import beside the other platform imports and mount beside the other `app.include_router(...)` calls:
```python
from app.platform_.ops.api import router as ops_router
...
app.include_router(ops_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/platform_/ops/test_api.py -v`
Expected: PASS (all cases).

- [ ] **Step 6: mypy + ruff + full ops suite**

Run: `venv/bin/mypy app/platform_/ops/ && venv/bin/ruff check app/platform_/ops/ && venv/bin/pytest tests/platform_/ops/ -q`
Expected: clean, all green.

- [ ] **Step 7: Commit**

```bash
git add app/platform_/ops/schemas.py app/platform_/ops/api.py app/main.py tests/platform_/ops/test_api.py
git commit -m "feat(ops): /platform/ops/backups endpoints (superuser)"
```

---

### Task 4: pgBackRest config + postgres image with archiving

**Files:**
- Create: `infra/backups/pgbackrest.conf`, `infra/backups/Dockerfile.postgres`, `infra/backups/README.md`
- Modify: `docker-compose.yml` (minio + minio-setup services; postgres `build` + archive command + env)

**Interfaces:**
- Produces: a `postgres` service that archives WAL to MinIO via pgBackRest; a MinIO service reachable at `minio:9000` with bucket `sacco-backups`. Stanza name: `sacco`.

- [ ] **Step 1: Write pgbackrest.conf**

`infra/backups/pgbackrest.conf`:
```ini
[global]
repo1-type=s3
repo1-s3-endpoint=minio:9000
repo1-s3-uri-style=path
repo1-s3-bucket=sacco-backups
repo1-s3-region=us-east-1
repo1-s3-key=${PGBACKREST_S3_KEY}
repo1-s3-key-secret=${PGBACKREST_S3_SECRET}
repo1-path=/sacco
repo1-retention-full=6
repo1-retention-full-type=count
repo1-cipher-type=aes-256-cbc
repo1-cipher-pass=${PGBACKREST_CIPHER_PASS}
start-fast=y
log-level-console=info
log-level-file=detail

[sacco]
pg1-path=/var/lib/postgresql/data
pg1-host-user=postgres
```
Note for prod swap (also in README): change `repo1-s3-endpoint`, keys, and `repo1-s3-uri-style=host` for AWS.

- [ ] **Step 2: Write the postgres image**

`infra/backups/Dockerfile.postgres`:
```dockerfile
FROM postgres:16
RUN apt-get update \
 && apt-get install -y --no-install-recommends pgbackrest ca-certificates \
 && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 3: Wire compose (minio, minio-setup, postgres build + archive)**

In `docker-compose.yml`, add volumes `miniodata:` and (later task) `pgbackrest_spool:`. Add services:
```yaml
  minio:
    image: minio/minio:latest
    restart: unless-stopped
    networks: [sacco_net]
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: sacco-minio
      MINIO_ROOT_PASSWORD: sacco-minio-secret
    volumes:
      - miniodata:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 10

  minio-setup:
    image: minio/mc:latest
    networks: [sacco_net]
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set local http://minio:9000 sacco-minio sacco-minio-secret &&
      mc mb --ignore-existing local/sacco-backups &&
      mc version enable local/sacco-backups &&
      echo minio-setup-done
      "
```
Modify the `postgres` service: replace `image: postgres:16` with
```yaml
    build:
      context: .
      dockerfile: infra/backups/Dockerfile.postgres
    command: >
      postgres
      -c archive_mode=on
      -c archive_command='pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf archive-push %p'
      -c max_wal_senders=3
      -c wal_level=replica
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./infra/backups/pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro
    environment:
      POSTGRES_USER: sacco
      POSTGRES_PASSWORD: sacco
      POSTGRES_DB: sacco
      PGBACKREST_S3_KEY: sacco-minio
      PGBACKREST_S3_SECRET: sacco-minio-secret
      PGBACKREST_CIPHER_PASS: local-dev-cipher-change-in-prod
```
(Keep the existing healthcheck. `archive_command` failing before the stanza exists is expected until Task 5 creates it; postgres still starts.)

- [ ] **Step 4: Write the README**

`infra/backups/README.md`: document local bring-up order (`docker compose up -d minio minio-setup postgres backup`), the one-time `stanza-create` (Task 5), how to run an on-demand drill, and the exact prod-swap diff (endpoint, keys, uri-style, cipher pass from secrets manager, run systemd timers instead of the container crontab).

- [ ] **Step 5: Rebuild + verify MinIO bucket and postgres archiving**

Run:
```bash
docker compose build postgres
docker compose up -d minio minio-setup postgres
docker compose logs minio-setup | grep minio-setup-done
docker compose exec -T postgres pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf stanza-create
docker compose exec -T postgres psql -U sacco -d sacco -c "SELECT pg_switch_wal();"
docker compose exec -T minio mc ls --recursive local/sacco-backups | grep archive
```
Expected: `minio-setup-done` present; `stanza-create` succeeds; at least one archived WAL segment listed under the bucket.

- [ ] **Step 6: Commit**

```bash
git add infra/backups/pgbackrest.conf infra/backups/Dockerfile.postgres infra/backups/README.md docker-compose.yml
git commit -m "feat(infra): pgBackRest + MinIO + postgres WAL archiving"
```

---

### Task 5: Backup sidecar — image, scripts, schedules

**Files:**
- Create: `infra/backups/Dockerfile.backup`, `infra/backups/crontab`, `infra/backups/scripts/lib.sh`, `backup.sh`, `prune.sh`, `poll-verify-requests.sh`
- Modify: `docker-compose.yml` (backup service)

**Interfaces:**
- Consumes: MinIO bucket + stanza `sacco` (Task 4); `platform.backup_runs` / `backup_verifications` (Task 1).
- Produces: a `backup` service running scheduled base backups + prune + verify-request polling, reporting into the platform tables. Restore drill script itself is Task 6 (referenced by crontab + poll here, created there).

- [ ] **Step 1: Write the shared report helpers**

`infra/backups/scripts/lib.sh`:
```bash
#!/usr/bin/env bash
# Shared helpers: report backup/verify status into the platform tables via psql.
set -euo pipefail

: "${PGHOST:=postgres}"
: "${PGUSER:=sacco}"
: "${PGDATABASE:=sacco}"
export PGPASSWORD="${PGPASSWORD:-sacco}"

psql_platform() { psql -v ON_ERROR_STOP=1 -qtA -c "SET search_path TO platform; $1"; }

report_run_start() { # type -> prints run id
  psql_platform "INSERT INTO backup_runs (id, backup_type, status, started_at)
    VALUES (gen_random_uuid(), '$1', 'running', now()) RETURNING id;"
}
report_run_finish() { # id status repo_size_bytes(optional)
  local size="${3:-NULL}"
  psql_platform "UPDATE backup_runs SET status='$2', finished_at=now(),
    repo_size_bytes=${size} WHERE id='$1';"
}
claim_verification() { # id -> mark running, set started_at
  psql_platform "UPDATE backup_verifications SET status='running', started_at=now()
    WHERE id='$1';"
}
finish_verification() { # id status detail
  psql_platform "UPDATE backup_verifications SET status='$2', finished_at=now(),
    detail=\$\$${3:-}\$\$ WHERE id='$1';"
}
insert_scheduled_verification() { # -> prints id (requested, requested_by NULL)
  psql_platform "INSERT INTO backup_verifications (id, status)
    VALUES (gen_random_uuid(), 'requested') RETURNING id;"
}
repo_size_bytes() { # prints total bytes of the repo via pgbackrest info
  pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf info --output=json \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(b['info']['repository']['size'] for s in d for b in s['backup']) or 'NULL')" 2>/dev/null || echo NULL
}
```

- [ ] **Step 2: Write backup.sh + prune.sh + poll-verify-requests.sh**

`infra/backups/scripts/backup.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/lib.sh"
RUN_ID="$(report_run_start full)"
if pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf --type=full backup; then
  report_run_finish "$RUN_ID" succeeded "$(repo_size_bytes)"
else
  report_run_finish "$RUN_ID" failed
  exit 1
fi
```
`infra/backups/scripts/prune.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf expire
```
`infra/backups/scripts/poll-verify-requests.sh`:
```bash
#!/usr/bin/env bash
# Every minute: if a verification is 'requested', claim + run the drill.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/lib.sh"
ID="$(psql_platform "SELECT id FROM backup_verifications WHERE status='requested' ORDER BY created_at LIMIT 1;")"
[ -z "$ID" ] && exit 0
claim_verification "$ID"
if "$DIR/restore-staging.sh" "$ID"; then :; else echo "drill failed for $ID"; fi
```

- [ ] **Step 3: Write the backup image + crontab**

`infra/backups/Dockerfile.backup`:
```dockerfile
FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      pgbackrest postgresql-client python3 ca-certificates curl docker.io \
 && rm -rf /var/lib/apt/lists/*
# supercronic for container-friendly cron
ADD https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN chmod +x /usr/local/bin/supercronic
COPY infra/backups/scripts/ /opt/backups/scripts/
COPY infra/backups/crontab /opt/backups/crontab
RUN chmod +x /opt/backups/scripts/*.sh
CMD ["supercronic", "/opt/backups/crontab"]
```
`infra/backups/crontab`:
```
# min hour dom mon dow  command
0 2 * * *   /opt/backups/scripts/backup.sh
0 3 * * 0   /opt/backups/scripts/restore-staging.sh
0 4 * * *   /opt/backups/scripts/prune.sh
* * * * *   /opt/backups/scripts/poll-verify-requests.sh
```
(The drill needs to launch an ephemeral postgres. Simplest local approach: the backup container talks to the Docker socket — hence `docker.io` + the socket mount below. Documented in README as a local-only convenience; prod uses a dedicated restore host per the systemd units.)

- [ ] **Step 4: Wire the backup service into compose**

```yaml
  backup:
    build:
      context: .
      dockerfile: infra/backups/Dockerfile.backup
    restart: unless-stopped
    networks: [sacco_net]
    depends_on:
      postgres:
        condition: service_healthy
      minio:
        condition: service_healthy
    volumes:
      - ./infra/backups/pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      PGHOST: postgres
      PGUSER: sacco
      PGPASSWORD: sacco
      PGDATABASE: sacco
      PGBACKREST_S3_KEY: sacco-minio
      PGBACKREST_S3_SECRET: sacco-minio-secret
      PGBACKREST_CIPHER_PASS: local-dev-cipher-change-in-prod
      COMPOSE_PROJECT: sacco-platform
```

- [ ] **Step 5: Verify a scheduled base backup reports a run row**

Run:
```bash
docker compose build backup && docker compose up -d backup
docker compose exec -T backup /opt/backups/scripts/backup.sh
docker compose exec -T postgres psql -U sacco -d sacco -c "SELECT backup_type,status,repo_size_bytes FROM platform.backup_runs ORDER BY created_at DESC LIMIT 1;"
```
Expected: one `full / succeeded` row with a non-null `repo_size_bytes`.

- [ ] **Step 6: Commit**

```bash
git add infra/backups/Dockerfile.backup infra/backups/crontab infra/backups/scripts/lib.sh infra/backups/scripts/backup.sh infra/backups/scripts/prune.sh infra/backups/scripts/poll-verify-requests.sh docker-compose.yml
git commit -m "feat(infra): backup sidecar — base backup, prune, verify polling"
```

---

### Task 6: Restore-verify drill

**Files:**
- Create: `infra/backups/scripts/restore-staging.sh`
- Modify: `infra/backups/README.md` (drill section)

**Interfaces:**
- Consumes: `lib.sh` helpers (Task 5); the stanza + repo (Task 4). Optional arg `$1` = a `backup_verifications.id` to update (poll passes it; scheduled cron passes none → the script inserts its own row).
- Produces: a drill that restores to an ephemeral postgres, smoke-queries it, and records `passed`/`failed`.

- [ ] **Step 1: Write the drill script**

`infra/backups/scripts/restore-staging.sh`:
```bash
#!/usr/bin/env bash
# Restore the latest backup into a throwaway postgres, smoke-test, record result.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/lib.sh"

VERIFY_ID="${1:-}"
[ -z "$VERIFY_ID" ] && VERIFY_ID="$(insert_scheduled_verification)" && claim_verification "$VERIFY_ID"

STAGING="sacco-restore-staging-$$"
NET="${COMPOSE_PROJECT:-sacco-platform}_sacco_net"
cleanup() { docker rm -f "$STAGING" >/dev/null 2>&1 || true; }
trap cleanup EXIT

fail() { finish_verification "$VERIFY_ID" failed "$1"; echo "DRILL FAIL: $1" >&2; exit 1; }

# 1. Ephemeral postgres with pgbackrest (reuse the archiving postgres image).
docker run -d --name "$STAGING" --network "$NET" \
  -e POSTGRES_USER=sacco -e POSTGRES_PASSWORD=sacco -e POSTGRES_DB=sacco \
  -v "$(pwd)/infra/backups/pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro" \
  -e PGBACKREST_S3_KEY=sacco-minio -e PGBACKREST_S3_SECRET=sacco-minio-secret \
  -e PGBACKREST_CIPHER_PASS=local-dev-cipher-change-in-prod \
  sacco-platform-postgres >/dev/null || fail "could not start staging container"

# 2. Stop postgres inside it, restore into the data dir, start again.
sleep 5
docker exec "$STAGING" bash -lc "pg_ctl -D /var/lib/postgresql/data stop -m fast || true" || true
docker exec "$STAGING" bash -lc \
  "rm -rf /var/lib/postgresql/data/* && pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf --delta restore" \
  || fail "pgbackrest restore failed"
docker exec -u postgres "$STAGING" bash -lc \
  "pg_ctl -D /var/lib/postgresql/data -w -t 120 start" || fail "restored cluster did not start"

# 3. Smoke queries — cluster starts AND known rows are present.
TENANTS="$(docker exec "$STAGING" psql -U sacco -d sacco -tAqc 'SELECT count(*) FROM platform.tenants;')" || fail "platform.tenants query failed"
[ "${TENANTS:-0}" -ge 1 ] || fail "platform.tenants empty after restore"
MEMBERS="$(docker exec "$STAGING" psql -U sacco -d sacco -tAqc 'SELECT count(*) FROM tenant_demo_sacco.members;' 2>/dev/null || echo 0)"

finish_verification "$VERIFY_ID" passed "tenants=$TENANTS members=$MEMBERS"
echo "DRILL PASS: tenants=$TENANTS members=$MEMBERS"
```
(Image name `sacco-platform-postgres` matches the compose-built tag; adjust if the project prefix differs — verify with `docker images | grep postgres`.)

- [ ] **Step 2: Make it executable and run a manual drill**

Run:
```bash
chmod +x infra/backups/scripts/restore-staging.sh
docker compose exec -T backup /opt/backups/scripts/restore-staging.sh
docker compose exec -T postgres psql -U sacco -d sacco -c "SELECT status, detail FROM platform.backup_verifications ORDER BY created_at DESC LIMIT 1;"
```
Expected: script prints `DRILL PASS`; the latest verification row is `passed` with a `tenants=… members=…` detail.

- [ ] **Step 3: Verify the on-demand path (poll picks up an API request)**

Run:
```bash
docker compose exec -T postgres psql -U sacco -d sacco -c "INSERT INTO platform.backup_verifications (id,status) VALUES (gen_random_uuid(),'requested');"
# wait up to ~70s for the minute poll, or run the poller directly:
docker compose exec -T backup /opt/backups/scripts/poll-verify-requests.sh
docker compose exec -T postgres psql -U sacco -d sacco -c "SELECT status FROM platform.backup_verifications ORDER BY created_at DESC LIMIT 1;"
```
Expected: the row transitions `requested → running → passed`.

- [ ] **Step 4: Commit**

```bash
git add infra/backups/scripts/restore-staging.sh infra/backups/README.md
git commit -m "feat(infra): restore-verify drill with smoke queries"
```

---

### Task 7: systemd units for the production host

**Files:**
- Create: `infra/backups/systemd/pgbackrest-backup.service`, `pgbackrest-backup.timer`, `pgbackrest-verify.service`, `pgbackrest-verify.timer`

**Interfaces:**
- Produces: documented (not locally-run) prod scheduling. No code depends on these; they are the prod-swap deliverable.

- [ ] **Step 1: Write the units**

`pgbackrest-backup.service` (oneshot running `backup.sh`), `pgbackrest-backup.timer` (`OnCalendar=*-*-* 02:00`), `pgbackrest-verify.service` (oneshot running `restore-staging.sh`), `pgbackrest-verify.timer` (`OnCalendar=Sun *-*-* 03:00`). Each `.service` sets `EnvironmentFile=/etc/sacco/backups.env` and `ExecStart=/opt/backups/scripts/<script>.sh`.

Example `pgbackrest-verify.timer`:
```ini
[Unit]
Description=Weekly pgBackRest restore-verify drill

[Timer]
OnCalendar=Sun *-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 2: Lint the unit files**

Run: `systemd-analyze verify infra/backups/systemd/*.service 2>&1 || echo "systemd-analyze unavailable — visual check only"`
Expected: no errors (or a note that the tool isn't installed locally; the units are prod artifacts).

- [ ] **Step 3: Commit**

```bash
git add infra/backups/systemd/
git commit -m "feat(infra): systemd timers for production backup + verify"
```

---

### Task 8: `@sacco/schemas` — ops wire types

**Files:**
- Create: `admin/packages/schemas/src/ops.ts`, `admin/packages/schemas/src/__tests__/ops.test.ts`
- Modify: `admin/packages/schemas/src/index.ts`

**Interfaces:**
- Produces: `BackupRunOut`, `BackupVerificationOut`, `BackupStatusOut`, `LastVerifiedOut` interfaces mirroring `app/platform_/ops/schemas.py`; `BACKUP_FRESHNESS` constants (`BACKUP_STALE_HOURS = 24`, `VERIFY_STALE_DAYS = 7`); helper `isStale(iso: string | null, maxAgeMs: number, now?: number): boolean`.

- [ ] **Step 1: Write failing test**

`admin/packages/schemas/src/__tests__/ops.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { isStale, BACKUP_STALE_HOURS, VERIFY_STALE_DAYS } from "../ops";

describe("ops freshness", () => {
  it("thresholds match the roadmap", () => {
    expect(BACKUP_STALE_HOURS).toBe(24);
    expect(VERIFY_STALE_DAYS).toBe(7);
  });
  it("null is always stale", () => {
    expect(isStale(null, 1000)).toBe(true);
  });
  it("recent is fresh, old is stale", () => {
    const now = Date.parse("2026-07-12T12:00:00Z");
    expect(isStale("2026-07-12T11:00:00Z", 24 * 3600_000, now)).toBe(false);
    expect(isStale("2026-07-10T11:00:00Z", 24 * 3600_000, now)).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/schemas test -- ops`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

`admin/packages/schemas/src/ops.ts`:
```ts
export interface BackupRunOut {
  id: string;
  backup_type: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  repo_size_bytes: number | null;
  wal_lag_seconds: number | null;
  detail: string | null;
  created_at: string;
}
export interface BackupVerificationOut {
  id: string;
  requested_by: string | null;
  status: string;
  detail: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}
export interface BackupStatusOut {
  recent_runs: BackupRunOut[];
  latest_verification: BackupVerificationOut | null;
}
export interface LastVerifiedOut {
  last_verified_at: string | null;
}

export const BACKUP_STALE_HOURS = 24;
export const VERIFY_STALE_DAYS = 7;

export function isStale(iso: string | null, maxAgeMs: number, now = Date.now()): boolean {
  if (iso === null) return true;
  return now - Date.parse(iso) > maxAgeMs;
}
```
Add `export * from "./ops";` to `index.ts`.

- [ ] **Step 4: Run test + lint + typecheck**

Run: `pnpm --filter @sacco/schemas test -- ops && pnpm --filter @sacco/schemas lint && pnpm --filter @sacco/schemas typecheck`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/schemas/src/ops.ts admin/packages/schemas/src/__tests__/ops.test.ts admin/packages/schemas/src/index.ts
git commit -m "feat(schemas): backup ops wire types + freshness helper"
```

---

### Task 9: api-client ops resource + query keys + StatusBadge entities

**Files:**
- Create: `admin/packages/api-client/src/resources/ops.ts`, `admin/packages/api-client/src/__tests__/query-keys-ops.test.ts`
- Modify: `admin/packages/api-client/src/resources/index.ts`, `admin/packages/api-client/src/query-keys.ts`, `admin/packages/ui/src/components/StatusBadge/status-maps.ts`

**Interfaces:**
- Produces: `ops(api)` registered as `ops` with `getBackups()`, `lastVerifiedAt()`, `triggerVerification()`. Query keys `ops.root()`, `ops.backups()`, `ops.lastVerified()`. StatusBadge entities `backup_run` (`running: info, succeeded: success, failed: danger`) and `backup_verification` (`requested: neutral, running: info, passed: success, failed: danger`).

- [ ] **Step 1: Write failing query-keys test**

`admin/packages/api-client/src/__tests__/query-keys-ops.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { queryKeys } from "../query-keys";

describe("ops query keys", () => {
  it("nest under a common root", () => {
    expect(queryKeys.ops.root()).toEqual(["ops"]);
    expect(queryKeys.ops.backups()).toEqual(["ops", "backups"]);
    expect(queryKeys.ops.lastVerified()).toEqual(["ops", "lastVerified"]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm --filter @sacco/api-client test -- query-keys-ops`
Expected: FAIL.

- [ ] **Step 3: Implement resource + keys + status maps**

`admin/packages/api-client/src/resources/ops.ts`:
```ts
import type { FetchClient } from "../client";

export function ops(api: FetchClient) {
  return {
    getBackups: () => api.GET("/platform/ops/backups" as never),
    lastVerifiedAt: () => api.GET("/platform/ops/backups/last-verified-at" as never),
    triggerVerification: () =>
      api.POST("/platform/ops/backups/trigger-verification" as never),
  } as const;
}
```
Register in `resources/index.ts` (`import { ops }` + `ops: ops(api)`). Add to `query-keys.ts`:
```ts
  ops: {
    root: () => ["ops"] as const,
    backups: () => ["ops", "backups"] as const,
    lastVerified: () => ["ops", "lastVerified"] as const,
  },
```
In `status-maps.ts`: add `"backup_run"` and `"backup_verification"` to `StatusEntity`, add the two maps, and register in `ENTITY_MAPS`:
```ts
export const BACKUP_RUN_STATUS: StatusMap = {
  running: { variant: "info", label: "Running" },
  succeeded: { variant: "success", label: "Succeeded" },
  failed: { variant: "danger", label: "Failed" },
};
export const BACKUP_VERIFICATION_STATUS: StatusMap = {
  requested: { variant: "neutral", label: "Requested" },
  running: { variant: "info", label: "Running" },
  passed: { variant: "success", label: "Passed" },
  failed: { variant: "danger", label: "Failed" },
};
```

- [ ] **Step 4: Run tests + lint + typecheck (api-client + ui)**

Run: `pnpm --filter @sacco/api-client test && pnpm --filter @sacco/api-client lint && pnpm --filter @sacco/api-client typecheck && pnpm --filter @sacco/ui test && pnpm --filter @sacco/ui typecheck`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/api-client/src/resources/ops.ts admin/packages/api-client/src/resources/index.ts admin/packages/api-client/src/query-keys.ts admin/packages/api-client/src/__tests__/query-keys-ops.test.ts admin/packages/ui/src/components/StatusBadge/status-maps.ts
git commit -m "feat(api-client): ops resource + query keys + backup status badges"
```

---

### Task 10: Portal backups widget

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/operations/backups/page.tsx` + `_components/BackupFreshnessTiles.tsx`, `BackupRunsTable.tsx`, `VerifyNowButton.tsx`
- Create tests: `__tests__/BackupFreshnessTiles.test.tsx`, `__tests__/VerifyNowButton.test.tsx`
- Modify: `admin/apps/portal/src/components/shell/nav-config.tsx`

**Interfaces:**
- Consumes: `resources.ops` + `queryKeys.ops` (Task 9); `BackupStatusOut`, `isStale`, `BACKUP_STALE_HOURS`, `VERIFY_STALE_DAYS` (Task 8); `<StatusBadge entity="backup_run">` (Task 9).
- Produces: `/platform/operations/backups` page (server component fetching initial status; superuser-gated), a freshness-tiles component, a runs `<DataTable>`, and a client `VerifyNowButton` (`<ConfirmDialog>` → `triggerVerification`, invalidates `ops.backups`).

- [ ] **Step 1: Write failing component tests**

`__tests__/BackupFreshnessTiles.test.tsx`: renders "danger" styling when last backup >24h and last verify >7d; fresh when recent. `__tests__/VerifyNowButton.test.tsx`: clicking opens `<ConfirmDialog>`, confirming calls `triggerVerification` (mock `@/auth/use-auth` + `useTypedMutation`, QueryClient wrapper — mirror `AppShellNotificationBell.test.tsx` / `VerifyNow`-style patterns).
```tsx
// BackupFreshnessTiles.test.tsx (essence)
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BackupFreshnessTiles } from "../_components/BackupFreshnessTiles";

it("flags a stale backup and stale verify", () => {
  render(
    <BackupFreshnessTiles
      lastBackupAt="2026-07-01T00:00:00Z"
      lastVerifiedAt="2026-07-01T00:00:00Z"
      now={Date.parse("2026-07-12T00:00:00Z")}
    />,
  );
  expect(screen.getAllByTestId("tile-stale")).toHaveLength(2);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `pnpm --filter @sacco/portal test -- backups/__tests__`
Expected: FAIL (components missing).

- [ ] **Step 3: Implement the components + page**

`BackupFreshnessTiles.tsx` (client, presentational): two tiles using `isStale` + `BACKUP_STALE_HOURS*3600_000` / `VERIFY_STALE_DAYS*86400_000`; stale tiles get `data-testid="tile-stale"` and a danger tint (`bg-[var(--status-danger-bg)]`), fresh get neutral; render `<RelativeTime>` for each timestamp, "Never" when null.
`BackupRunsTable.tsx` (client): `<DataTable>` over `recent_runs` — columns created (`<FormattedDateTime>`), type, status (`<StatusBadge entity="backup_run">`), repo size (bytes → human via a small formatter), duration (finished−started). Client-only (data passed from the server page; no `useTableUrlState` server round-trip needed — pass a static `urlState` like the notifications events table).
`VerifyNowButton.tsx` (client): `<ConfirmDialog>` copy "Run a restore-verify drill now?"; `useTypedMutation(resources.ops.triggerVerification, { invalidates: [queryKeys.ops.backups()] })`; toast + `router.refresh()`; 409 → toast "A verification is already running."
`page.tsx` (server): `getPlatformPageContext()`, `requirePlatformPermission(user, "operations.read")`, fetch `resources.ops.getBackups()` (cast to `{data,error}`), render heading + `VerifyNowButton` + tiles + trend note + `BackupRunsTable`. Trend: reuse `@sacco/ui` `Chart` over `recent_runs` `repo_size_bytes` (skip if <2 runs).
Add to `nav-config.tsx` Operations group a child `{ label: "Backups", href: "/platform/operations/backups" }` (convert the current single `Operations` link to a parent with children `Overview` + `Backups`, matching the Settings pattern).

- [ ] **Step 4: Run tests + lint + typecheck**

Run: `pnpm --filter @sacco/portal test -- backups && pnpm --filter @sacco/portal lint && pnpm --filter @sacco/portal typecheck`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/operations/backups" admin/apps/portal/src/components/shell/nav-config.tsx
git commit -m "feat(portal): backups operations widget (tiles, runs table, verify now)"
```

---

### Task 11: Runbooks + first real drill report

**Files:**
- Create: `docs/runbooks/restore-from-pitr.md`, `docs/runbooks/single-tenant-recovery.md`, `docs/runbooks/backup-verification.md`, `docs/runbooks/drills/<today>-first-drill.md`

**Interfaces:**
- Consumes: the working pipeline (Tasks 4-6). The drill report is captured from a real run.

- [ ] **Step 1: Write the three runbooks**

- `restore-from-pitr.md`: full-cluster restore — stop app, `pgbackrest --stanza=sacco --type=time "--target=<ts>" restore`, start, verify. Include the prod-vs-local endpoint note.
- `single-tenant-recovery.md`: restore to an ephemeral instance (reuse the drill container), `pg_dump -n tenant_<slug>` from it, `pg_restore` into the live primary; caution about the `platform` schema and search_path.
- `backup-verification.md`: what the weekly drill does, how to read the portal widget, what "stale" thresholds mean, what to do on a `failed` verification.

- [ ] **Step 2: Run a real drill and capture the report**

Run:
```bash
docker compose exec -T backup /opt/backups/scripts/restore-staging.sh | tee /tmp/drill.txt
docker compose exec -T postgres psql -U sacco -d sacco -c "SELECT status, detail, finished_at-started_at AS duration FROM platform.backup_verifications ORDER BY created_at DESC LIMIT 1;"
```
Paste the output (RTO duration, tenants/members counts, PASS) into `docs/runbooks/drills/<today>-first-drill.md` with a one-paragraph summary and the date. This is the roadmap's required proof deliverable.

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/
git commit -m "docs(runbooks): PITR restore, single-tenant recovery, verification + first drill"
```

---

### Task 12: CLAUDE.md contracts + close-out

**Files:**
- Modify: `CLAUDE.md` (roadmap row 4 → Done/In progress; new Ops contracts subsection; scope-exception note)

- [ ] **Step 1: Update CLAUDE.md**

- Roadmap table row 4 (Backups & DR): status → **Done**.
- Add an **Ops module contracts (Phase 4 — do not violate)** subsection:
  - `OpsService` (app/platform_/ops/service.py) is the only app-side writer of `platform.backup_verifications`; `platform.backup_runs` is written exclusively by the backup container's scripts. The app reads both, never writes `backup_runs`.
  - The three `/platform/ops/backups*` endpoints are `CurrentSuperuser`, direct action (no maker-checker). `trigger-verification` is idempotent-by-conflict: 409 while any verification is `requested` or `running`.
  - The backup pipeline lives in `infra/backups/` and runs against MinIO locally; production is a `pgbackrest.conf` credential/endpoint swap plus the systemd timers. The pgBackRest binary and S3 credentials never enter the app image.
  - The restore-verify drill (`restore-staging.sh`) is the source of truth that backups are recoverable; a `passed` `backup_verifications` row is the signal the portal surfaces.
- Add a one-line **scope exception** note near contract N: Phase 4 intentionally edits `docker-compose.yml`, adds `infra/`, `app/platform_/ops/` + platform migration 012, and the operations/backups portal page.

- [ ] **Step 2: Full backend + admin gates**

Run:
```bash
venv/bin/ruff check app/platform_/ops/ && venv/bin/mypy app/platform_/ops/ && venv/bin/pytest tests/platform_/ops/ -q
cd admin && pnpm lint && pnpm typecheck && pnpm test
```
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): ops/backup contracts + Phase 4 scope (Phase 4 complete)"
```

## Out of scope (reminder)

- Phase 5 metrics/alerting (tables record data; paging is Phase 5).
- KMS-managed encryption key custody (local uses a static cipher pass; prod = runbook TODO).
- Arbitrary-timestamp PITR via the API (runbook procedure only).
- Incremental/differential backup tuning (nightly fulls in v1).
- Multi-region repo replication.
