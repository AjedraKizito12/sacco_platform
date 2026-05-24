# IAM v1-04: Tenant Users Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `tenant_users` table, its SQLAlchemy model with `AuditableMixin`, a `TenantUserService` for CRUD, the tenant migration that also retrofits the FK from `tenant_sessions.tenant_user_id → tenant_users.id`, and the provisioning bootstrap that seeds an initial admin tenant user when `admin_email` is supplied at tenant creation time.

**Architecture:** `TenantUser` lives in the tenant schema (no `schema=` in `__table_args__`; resolved via `search_path`). `TenantUserService` mirrors the pattern established by `KeyService` and `SessionService`. The provisioning bootstrap threads `admin_email` through `CreateTenantRequest → provision_tenant.delay() → _execute_steps → run_seed_defaults_step → seed_defaults → _seed_admin_user`. The seed uses `ON CONFLICT (email) DO NOTHING` so re-running provisioning is safe. Password is left `null` — the user activates via Plan 08 password reset.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, pydantic-settings, FastAPI, Celery 5, pytest-anyio

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — tenant model rules (no schema=, resolved via search_path); AuditableMixin requirement
2. `docs/superpowers/decisions/2026-05-21-iam-architecture.md` §9 — password handling boundary (hashed_password null until IAM ships is fine)
3. `docs/superpowers/specs/2026-05-21-iam-v1-design.md` §3.4, §3.5 — TenantUser schema and bootstrap seed spec
4. `app/platform_/provisioning/steps.py` — `run_seed_defaults_step` and `seed_defaults` call chain (this plan extends both)
5. `app/platform_/provisioning/tasks.py` — `provision_tenant` Celery task signature (add `admin_email` param)
6. `app/platform_/tenants/schemas.py` — `CreateTenantRequest` (add `admin_email` field)
7. `app/platform_/tenants/api.py` — `create_tenant` endpoint (thread `admin_email` to task)
8. `app/platform_/seeds/runner.py` — `seed_defaults` function (extend with `admin_email` param)
9. `app/core/audit/mixin.py` — `AuditableMixin` (used by TenantUser)
10. `alembic/tenant/versions/002_iam_tenant_sessions.py` — `down_revision` for the new tenant migration
11. `tests/conftest.py` — `tenant_session` fixture; `test_engine` (add model import)
12. `tests/platform_/test_provisioning.py` — existing provisioning tests (add seed bootstrap tests)

---

## File Map

```
CREATE app/modules/iam/tenant_users/__init__.py
CREATE app/modules/iam/tenant_users/models.py   — TenantUser (tenant schema, AuditableMixin)
CREATE app/modules/iam/tenant_users/service.py  — TenantUserService: create, get_by_id, get_by_email, list, update
CREATE app/modules/iam/tenant_users/schemas.py  — TenantUserOut, CreateTenantUserRequest, UpdateTenantUserRequest
CREATE tests/modules/iam/tenant_users/__init__.py
CREATE tests/modules/iam/tenant_users/test_tenant_user_service.py
CREATE alembic/tenant/versions/003_iam_tenant_users.py  — tenant_users DDL + FK on tenant_sessions
MODIFY tests/conftest.py                       — import TenantUser model into test_engine
MODIFY app/platform_/seeds/runner.py           — seed_defaults gains optional admin_email param; add _seed_admin_user
MODIFY app/platform_/provisioning/steps.py     — run_seed_defaults_step threads admin_email
MODIFY app/platform_/provisioning/tasks.py     — provision_tenant(tenant_id_str, admin_email=None)
MODIFY app/platform_/tenants/schemas.py        — CreateTenantRequest gains optional admin_email field
MODIFY app/platform_/tenants/api.py            — create_tenant passes admin_email to provision_tenant.delay()
```

---

### Task 1: TenantUser model

**Files:**
- Create: `app/modules/iam/tenant_users/__init__.py`
- Create: `app/modules/iam/tenant_users/models.py`
- Create: `tests/modules/iam/tenant_users/__init__.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/iam/tenant_users/test_tenant_user_service.py
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.modules.iam.tenant_users.models import TenantUser


@pytest.mark.anyio
async def test_tenant_user_model_persists(tenant_session):
    user = TenantUser(
        email="admin@example.com",
        full_name="Test Admin",
        is_active=True,
        is_admin=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    tenant_session.add(user)
    await tenant_session.flush()

    result = await tenant_session.execute(
        select(TenantUser).where(TenantUser.email == "admin@example.com")
    )
    fetched = result.scalar_one()
    assert isinstance(fetched.id, uuid.UUID)
    assert fetched.full_name == "Test Admin"
    assert fetched.hashed_password is None
    assert fetched.last_login_at is None
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/modules/iam/tenant_users/test_tenant_user_service.py::test_tenant_user_model_persists -v
```

Expected: `ImportError` — `models.py` does not exist yet

- [ ] **Step 3: Create directory structure**

```bash
mkdir -p app/modules/iam/tenant_users tests/modules/iam/tenant_users
touch app/modules/iam/tenant_users/__init__.py tests/modules/iam/tenant_users/__init__.py
```

- [ ] **Step 4: Create `app/modules/iam/tenant_users/models.py`**

```python
"""SQLAlchemy model for the tenant_users table.

Lives in the tenant schema — no ``schema=`` in ``__table_args__``.
Search path is set by ``get_tenant_session`` before any query runs.

Carries ``AuditableMixin`` so that every insert, update, and delete writes
a row to the tenant's ``audit_log`` with ``actor_type='tenant_user'``
(or ``'platform_user'`` when a platform actor is the active context var).

``hashed_password`` is ``null`` until the user completes the password reset
flow (Plan 08). Authentication is blocked for users with null password.

``is_admin`` is a coarse gate used by all downstream modules until the full
role/permission system ships in IAM v2.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — used at runtime by SQLAlchemy

from sqlalchemy import Boolean, Index, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class TenantUser(AuditableMixin, Base):
    __tablename__ = "tenant_users"
    __table_args__ = (
        Index("ix_tenant_users_email", "email"),
        # No schema= — resolved at runtime via SET LOCAL search_path.
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Null until the user sets a password via the reset flow (Plan 08).
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Coarse superuser gate; replaced by the permission system in IAM v2.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
```

- [ ] **Step 5: Register TenantUser in `tests/conftest.py`**

Inside the `test_engine` fixture body, add after the existing model imports:

```python
import app.modules.iam.tenant_users.models  # noqa: F401 — registers TenantUser in Base.metadata
```

> `TenantUser` has no `schema=` so `create_all` with `SET search_path TO tenant_test, platform`
> places it in the `tenant_test` schema.

- [ ] **Step 6: Run test to confirm pass**

```bash
pytest tests/modules/iam/tenant_users/test_tenant_user_service.py::test_tenant_user_model_persists -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/modules/iam/tenant_users/ tests/modules/iam/tenant_users/ tests/conftest.py
git commit -m "feat(iam): TenantUser SQLAlchemy model (tenant schema, AuditableMixin)"
```

---

### Task 2: Tenant migration 003 — tenant_users DDL + tenant_sessions FK

**Files:**
- Create: `alembic/tenant/versions/003_iam_tenant_users.py`

This migration creates `tenant_users` and adds the FK from `tenant_sessions.tenant_user_id → tenant_users.id` that was intentionally deferred in migration 002.

- [ ] **Step 1: Verify the tenant migration chain**

```bash
ls alembic/tenant/versions/
```

Expected: `001_core_tenant.py  002_iam_tenant_sessions.py`

- [ ] **Step 2: Create `alembic/tenant/versions/003_iam_tenant_users.py`**

```python
"""Create tenant_users; add FK from tenant_sessions to tenant_users.

Revision: 003
Depends on: 002 (tenant_sessions must exist for the FK addition)

The tenant_sessions.tenant_user_id FK was deferred in migration 002
because tenant_users did not exist yet. We add it here now that the
referencing table exists.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_users",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_tenant_users_email"),
        # No schema= — resolved at runtime via search_path.
    )
    op.create_index("ix_tenant_users_email", "tenant_users", ["email"])

    # Retrofit the FK that was deferred in migration 002.
    op.create_foreign_key(
        "fk_tenant_sessions_tenant_user_id",
        "tenant_sessions",
        "tenant_users",
        ["tenant_user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tenant_sessions_tenant_user_id",
        "tenant_sessions",
        type_="foreignkey",
    )
    op.drop_index("ix_tenant_users_email", table_name="tenant_users")
    op.drop_table("tenant_users")
```

- [ ] **Step 3: Verify syntax**

```bash
python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('m003t', 'alembic/tenant/versions/003_iam_tenant_users.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.revision == '003' and m.down_revision == '002'
print('Tenant migration 003 OK')
"
```

Expected: `Tenant migration 003 OK`

- [ ] **Step 4: Commit**

```bash
git add alembic/tenant/versions/003_iam_tenant_users.py
git commit -m "feat(iam): tenant migration 003 — tenant_users + retrofit FK on tenant_sessions"
```

---

### Task 3: TenantUserService — CRUD

**Files:**
- Create: `app/modules/iam/tenant_users/schemas.py`
- Create: `app/modules/iam/tenant_users/service.py`
- Modify: `tests/modules/iam/tenant_users/test_tenant_user_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/iam/tenant_users/test_tenant_user_service.py`:

```python
import pytest
from datetime import UTC, datetime

from app.modules.iam.tenant_users.models import TenantUser
from app.modules.iam.tenant_users.service import TenantUserService


# ── create ──────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_create_tenant_user_inserts_row(tenant_session):
    svc = TenantUserService(tenant_session)
    user = await svc.create(email="alice@example.com", full_name="Alice Smith")
    await tenant_session.flush()

    assert user.email == "alice@example.com"
    assert user.full_name == "Alice Smith"
    assert user.hashed_password is None
    assert user.is_active is True
    assert user.is_admin is False


@pytest.mark.anyio
async def test_create_tenant_user_as_admin(tenant_session):
    svc = TenantUserService(tenant_session)
    user = await svc.create(
        email="bob@example.com", full_name="Bob Admin", is_admin=True
    )
    await tenant_session.flush()

    assert user.is_admin is True


@pytest.mark.anyio
async def test_create_tenant_user_duplicate_email_raises(tenant_session):
    from sqlalchemy.exc import IntegrityError

    svc = TenantUserService(tenant_session)
    await svc.create(email="dup@example.com", full_name="First")
    await tenant_session.flush()

    with pytest.raises((ValueError, IntegrityError)):
        await svc.create(email="dup@example.com", full_name="Second")
        await tenant_session.flush()


# ── get_by_id ────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_by_id_returns_user(tenant_session):
    svc = TenantUserService(tenant_session)
    created = await svc.create(email="carol@example.com", full_name="Carol")
    await tenant_session.flush()

    fetched = await svc.get_by_id(created.id)
    assert fetched is not None
    assert fetched.email == "carol@example.com"


@pytest.mark.anyio
async def test_get_by_id_returns_none_for_missing(tenant_session):
    import uuid
    svc = TenantUserService(tenant_session)
    assert await svc.get_by_id(uuid.uuid4()) is None


# ── get_by_email ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_by_email_returns_user(tenant_session):
    svc = TenantUserService(tenant_session)
    await svc.create(email="dave@example.com", full_name="Dave")
    await tenant_session.flush()

    fetched = await svc.get_by_email("dave@example.com")
    assert fetched is not None
    assert fetched.full_name == "Dave"


@pytest.mark.anyio
async def test_get_by_email_returns_none_for_missing(tenant_session):
    svc = TenantUserService(tenant_session)
    assert await svc.get_by_email("nobody@example.com") is None


# ── list ─────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_returns_all_users(tenant_session):
    svc = TenantUserService(tenant_session)
    await svc.create(email="e1@example.com", full_name="E1")
    await svc.create(email="e2@example.com", full_name="E2")
    await tenant_session.flush()

    users = await svc.list()
    emails = {u.email for u in users}
    assert "e1@example.com" in emails
    assert "e2@example.com" in emails


@pytest.mark.anyio
async def test_list_filters_by_is_active(tenant_session):
    svc = TenantUserService(tenant_session)
    await svc.create(email="active@example.com", full_name="Active")
    inactive = await svc.create(email="inactive@example.com", full_name="Inactive")
    await tenant_session.flush()
    await svc.update(inactive.id, is_active=False)
    await tenant_session.flush()

    active_users = await svc.list(is_active=True)
    emails = {u.email for u in active_users}
    assert "active@example.com" in emails
    assert "inactive@example.com" not in emails


# ── update ───────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_update_full_name(tenant_session):
    svc = TenantUserService(tenant_session)
    user = await svc.create(email="frank@example.com", full_name="Frank Old")
    await tenant_session.flush()

    updated = await svc.update(user.id, full_name="Frank New")
    assert updated is not None
    assert updated.full_name == "Frank New"
    assert updated.updated_at >= user.created_at


@pytest.mark.anyio
async def test_update_returns_none_for_missing_user(tenant_session):
    import uuid
    svc = TenantUserService(tenant_session)
    result = await svc.update(uuid.uuid4(), full_name="Ghost")
    assert result is None
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/tenant_users/test_tenant_user_service.py -v -k "not model_persists"
```

Expected: `ImportError` — `service.py` does not exist yet

- [ ] **Step 3: Create `app/modules/iam/tenant_users/schemas.py`**

```python
"""Pydantic schemas for tenant user API responses."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class CreateTenantUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    is_admin: bool = False


class UpdateTenantUserRequest(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None


class TenantUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Create `app/modules/iam/tenant_users/service.py`**

```python
"""TenantUserService: CRUD for tenant_users.

Operates within the tenant schema — the caller must supply an AsyncSession
with the correct search_path already set (i.e., via get_tenant_session).

hashed_password is intentionally excluded from create() — users receive a
password reset link (Plan 08) to set their own password. Callers that need
to update hashed_password (auth service, plan 05/06) use update() with the
hashed_password kwarg.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.tenant_users.models import TenantUser

_log = structlog.get_logger(__name__)


class TenantUserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        email: str,
        full_name: str,
        is_admin: bool = False,
        hashed_password: str | None = None,
    ) -> TenantUser:
        """Insert a new tenant user. Raises ``ValueError`` on duplicate email."""
        now = datetime.now(UTC)
        user = TenantUser(
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            is_active=True,
            is_admin=is_admin,
            created_at=now,
            updated_at=now,
        )
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ValueError(f"Email '{email}' is already registered") from exc
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> TenantUser | None:
        result = await self._session.execute(
            select(TenantUser).where(TenantUser.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> TenantUser | None:
        result = await self._session.execute(
            select(TenantUser).where(TenantUser.email == email)
        )
        return result.scalar_one_or_none()

    async def list(self, *, is_active: bool | None = None) -> list[TenantUser]:
        q = select(TenantUser).order_by(TenantUser.created_at.desc())
        if is_active is not None:
            q = q.where(TenantUser.is_active == is_active)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def update(
        self, user_id: uuid.UUID, **fields: Any
    ) -> TenantUser | None:
        """Update arbitrary fields on a tenant user.

        Allowed kwargs: full_name, is_active, is_admin, hashed_password,
        last_login_at. Always sets updated_at to now().

        Returns the updated row, or ``None`` if not found.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        allowed = {"full_name", "is_active", "is_admin", "hashed_password", "last_login_at"}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"update() does not accept field '{key}'")
            setattr(user, key, value)
        user.updated_at = datetime.now(UTC)
        return user
```

- [ ] **Step 5: Run all TenantUserService tests to confirm pass**

```bash
pytest tests/modules/iam/tenant_users/test_tenant_user_service.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/tenant_users/schemas.py app/modules/iam/tenant_users/service.py
git add tests/modules/iam/tenant_users/test_tenant_user_service.py
git commit -m "feat(iam): TenantUserService — create, get_by_id, get_by_email, list, update"
```

---

### Task 4: Bootstrap seed extension

**Files:**
- Modify: `app/platform_/seeds/runner.py`
- Modify: `app/platform_/provisioning/steps.py`
- Modify: `app/platform_/provisioning/tasks.py`
- Modify: `app/platform_/tenants/schemas.py`
- Modify: `app/platform_/tenants/api.py`

Thread `admin_email` from `CreateTenantRequest` all the way to `_seed_admin_user`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/platform_/test_provisioning.py`:

```python
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.platform_.seeds.runner import seed_defaults


@pytest.mark.anyio
async def test_seed_defaults_creates_admin_user_when_email_provided(
    test_engine: AsyncEngine,
):
    """seed_defaults with admin_email inserts a tenant_users row."""
    schema = "tenant_test"  # matches TEST_TENANT_SCHEMA in conftest
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    await seed_defaults(test_engine, schema, admin_email="seedadmin@example.com")

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema}, platform")  # noqa: S608
        )
        result = await session.execute(
            text(
                "SELECT email, is_admin, hashed_password "
                "FROM tenant_users WHERE email = 'seedadmin@example.com'"
            )
        )
        row = result.fetchone()

    assert row is not None, "Admin user was not inserted"
    assert row[1] is True, "is_admin should be True"
    assert row[2] is None, "hashed_password should be null"


@pytest.mark.anyio
async def test_seed_defaults_admin_seed_is_idempotent(test_engine: AsyncEngine):
    """Running seed_defaults twice with the same admin_email does not raise."""
    schema = "tenant_test"
    await seed_defaults(test_engine, schema, admin_email="idempotent@example.com")
    # Second run must not raise (ON CONFLICT DO NOTHING)
    await seed_defaults(test_engine, schema, admin_email="idempotent@example.com")


@pytest.mark.anyio
async def test_seed_defaults_without_admin_email_does_not_create_user(
    test_engine: AsyncEngine,
):
    schema = "tenant_test"
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    await seed_defaults(test_engine, schema, admin_email=None)

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema}, platform")  # noqa: S608
        )
        result = await session.execute(
            text("SELECT COUNT(*) FROM tenant_users WHERE email = 'no-email-user@example.com'")
        )
        count = result.scalar_one()

    assert count == 0
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/platform_/test_provisioning.py -v -k "admin_user or admin_seed or admin_email"
```

Expected: FAIL — `seed_defaults` does not accept `admin_email` yet

- [ ] **Step 3: Update `app/platform_/seeds/runner.py`**

Change the `seed_defaults` signature and add `_seed_admin_user`:

```python
async def seed_defaults(
    engine: AsyncEngine,
    schema_name: str,
    admin_email: str | None = None,
) -> None:
    """Seed all default data into *schema_name*.

    Skips entity types whose tables don't exist yet.
    Called by the provisioning task after run_migrations step.

    Args:
        admin_email: If provided, inserts an admin tenant user with this email
            (hashed_password=null). The user activates via the password reset
            flow (Plan 08). Idempotent — safe to call multiple times.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session, session.begin():
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        await _seed_roles(session, schema_name)
        await _seed_fee_types(session, schema_name)
        await _seed_chart_of_accounts(session, schema_name)
        await _seed_product_templates(session, schema_name)
        if admin_email:
            await _seed_admin_user(session, schema_name, admin_email)
```

Add `_seed_admin_user` after `_seed_product_templates`:

```python
async def _seed_admin_user(
    session: AsyncSession, schema_name: str, email: str
) -> None:
    """Insert an admin tenant user if one does not already exist for this email."""
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    "INSERT INTO tenant_users "
                    "(email, full_name, is_active, is_admin, created_at, updated_at) "
                    "VALUES (:email, 'Admin', true, true, now(), now()) "
                    "ON CONFLICT (email) DO NOTHING"
                ),
                {"email": email},
            )
        _log.info(
            "seed.admin_user_seeded",
            schema=schema_name,
            email=email,
            note="hashed_password is null — user must set password via reset flow",
        )
    except ProgrammingError:
        _log.warning("seed.tenant_users_table_missing", schema=schema_name)
```

- [ ] **Step 4: Update `app/platform_/provisioning/steps.py`**

Change `run_seed_defaults_step` to accept and thread `admin_email`:

```python
async def run_seed_defaults_step(
    engine: AsyncEngine,
    schema_name: str,
    admin_email: str | None = None,
) -> None:
    """Step 3: seed default data. All inserts are ON CONFLICT DO NOTHING."""
    await seed_defaults(engine, schema_name, admin_email=admin_email)
    _log.info("provision.seed_done", schema=schema_name)
```

- [ ] **Step 5: Update `app/platform_/provisioning/tasks.py`**

Change `provision_tenant` and its helpers to accept and thread `admin_email`:

```python
@celery_app.task(name="app.platform_.provisioning.tasks.provision_tenant")  # type: ignore[misc]
def provision_tenant(tenant_id_str: str, admin_email: str | None = None) -> None:
    asyncio.run(_run_provision(uuid.UUID(tenant_id_str), admin_email=admin_email))


async def _run_provision(
    tenant_id: uuid.UUID, admin_email: str | None = None
) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.connect() as lock_conn:
            await lock_conn.execute(text("SET search_path TO platform"))
            lock_key = f"provision:{tenant_id}"
            acquired = (
                await lock_conn.execute(
                    text("SELECT pg_try_advisory_lock(hashtext(:key))"),
                    {"key": lock_key},
                )
            ).scalar_one()

            if not acquired:
                _log.info("provision.already_running", tenant_id=str(tenant_id))
                return

            try:
                await _execute_steps(engine, factory, tenant_id, admin_email=admin_email)
            finally:
                await lock_conn.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:key))"),
                    {"key": lock_key},
                )
    finally:
        await engine.dispose()


async def _execute_steps(
    engine: Any,
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    admin_email: str | None = None,
) -> None:
    tenant_data = await load_tenant(factory, tenant_id)
    if tenant_data is None:
        _log.error("provision.tenant_not_found", tenant_id=str(tenant_id))
        return

    schema_name = tenant_data["schema_name"]
    if not _SCHEMA_RE.match(schema_name):
        _log.error("provision.invalid_schema", schema=schema_name, tenant_id=str(tenant_id))
        return

    failed_step = tenant_data["failed_step"]
    start_idx = STEP_SEQUENCE.index(failed_step) if failed_step in STEP_SEQUENCE else 0
    steps_to_run = STEP_SEQUENCE[start_idx:]

    await update_tenant_fields(
        factory,
        tenant_id,
        status="provisioning",
        provisioning_started_at=datetime.now(UTC),
        failed_step=None,
        failure_reason=None,
    )

    for step_name in steps_to_run:
        await update_tenant_fields(factory, tenant_id, provisioning_state=step_name)

        try:
            if step_name == "create_schema":
                await run_create_schema(engine, schema_name)

            elif step_name == "run_migrations":
                run_migrations_step(schema_name)

            elif step_name == "seed_defaults":
                await run_seed_defaults_step(
                    engine, schema_name, admin_email=admin_email
                )

            elif step_name == "finalize":
                await run_finalize(
                    factory,
                    tenant_id,
                    slug=tenant_data["slug"],
                    schema_name=schema_name,
                    seed_version=tenant_data["seed_version"],
                )

            _log.info("provision.step_ok", step=step_name, tenant_id=str(tenant_id))

        except Exception as exc:
            await update_tenant_fields(
                factory,
                tenant_id,
                status="failed",
                failed_step=step_name,
                failure_reason=str(exc),
            )
            _log.error(
                "provision.step_failed",
                step=step_name,
                error=str(exc),
                tenant_id=str(tenant_id),
                exc_info=True,
            )
            return
```

- [ ] **Step 6: Update `app/platform_/tenants/schemas.py`**

Add `admin_email` to `CreateTenantRequest`:

```python
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9-]{1,40}$")


class CreateTenantRequest(BaseModel):
    slug: str = Field(
        ...,
        description="URL-safe slug, lowercase letters/digits/hyphens, max 40 chars",
    )
    name: str = Field(..., min_length=1, max_length=200)
    admin_email: EmailStr | None = Field(
        None,
        description=(
            "If provided, seeds an initial admin user in the tenant. "
            "The user must set their password via the reset flow."
        ),
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("slug must match ^[a-z0-9-]{1,40}$")
        return v
```

- [ ] **Step 7: Update `app/platform_/tenants/api.py`**

Thread `admin_email` into `provision_tenant.delay()` in `create_tenant`:

```python
@router.post("", response_model=TenantCreateResponse, status_code=202)
async def create_tenant(
    body: CreateTenantRequest,
    session: Session,
    actor: Superuser,
) -> TenantCreateResponse:
    svc = TenantService(session)
    try:
        tenant = await svc.create(slug=body.slug, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()

    provision_tenant.delay(str(tenant.id), body.admin_email)

    return TenantCreateResponse(
        tenant=TenantOut.model_validate(tenant),
        status_url=f"/platform/tenants/{tenant.id}",
    )
```

- [ ] **Step 8: Run provisioning tests to confirm pass**

```bash
pytest tests/platform_/test_provisioning.py -v -k "admin"
```

Expected: 3 new tests PASS

- [ ] **Step 9: Run full platform provisioning suite to confirm no regressions**

```bash
pytest tests/platform_/ -v
```

Expected: All tests PASS

- [ ] **Step 10: Commit**

```bash
git add app/platform_/seeds/runner.py app/platform_/provisioning/steps.py
git add app/platform_/provisioning/tasks.py app/platform_/tenants/schemas.py
git add app/platform_/tenants/api.py tests/platform_/test_provisioning.py
git commit -m "feat(iam): thread admin_email through provisioning — seed initial admin tenant user"
```

---

## Verification Criteria

Before marking this plan complete, run the following:

```bash
# 1. Linting
ruff check app/modules/iam/tenant_users/ app/platform_/seeds/ app/platform_/provisioning/ app/platform_/tenants/

# 2. Type checking
mypy app/modules/iam/tenant_users/ --strict
mypy app/platform_/seeds/runner.py app/platform_/provisioning/tasks.py app/platform_/tenants/schemas.py

# 3. TenantUser service tests
pytest tests/modules/iam/tenant_users/ -v

# 4. Provisioning tests (includes new bootstrap seed tests)
pytest tests/platform_/test_provisioning.py -v

# 5. Migration syntax checks
python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('m003t', 'alembic/tenant/versions/003_iam_tenant_users.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.revision == '003' and m.down_revision == '002'
print('Tenant migration 003 OK')
"

# 6. Full regression suite
pytest tests/ -v
```

All commands must exit cleanly before this plan is considered complete.

---

## What is NOT in this plan

- Login, refresh, logout for tenant users — **Plans 05 and 06**
- Password reset token generation and email delivery — **Plan 08** (hooks into the provisioned admin user's null password)
- The FK from `tenant_sessions.tenant_user_id` was deferred in migration 002 and is now added in migration 003 — no further migration changes needed for this relationship
- Tenant user API endpoints (`GET /auth/users/`, etc.) — these belong to a future IAM v2 plan once role/permission scoping is defined; for now `TenantUserService` is used internally by auth endpoints only
