# Member Authentication & Self-Service Read API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give SACCO members their own authenticated login and read-only access to their own profile, savings, shares, loans, and fees.

**Architecture:** A new `member_auth` bounded context inside IAM mirrors the existing `tenant_auth` (login/refresh/logout/me/reset + a session model), issuing JWTs with a distinct `aud="member:<slug>"` namespace signed by the existing `"tenant"` signing key. Credentials live as columns on the `members` table; a `member_sessions` table tracks sessions. Each domain module (members/savings/shares/credit/fees) exposes its own `/member/*` read route gated by a shared `CurrentMember` dependency and the existing `get_tenant_session` subscription gate.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Alembic, PyJWT (RS256), argon2 (passwords), Redis (jti revocation), pytest + pytest-asyncio.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-25-member-auth-and-self-service-design.md`.
- Money is integer minor units or `DECIMAL(19,4)`; never float. (No money is written here — read-only — but read DTOs must not coerce to float.)
- Tenant model tables declare **no** `schema=`; resolved at runtime via `search_path`. Migration goes in `alembic/tenant/`.
- All DB access is async. Pydantic schemas in `schemas.py`, models in `models.py`, business logic in `service.py`, routers in `api.py`.
- `ruff` + `mypy --strict` must stay clean.
- JWT `aud` claim for members is exactly `member:<slug>`. Signing-key DB-column audience is `"tenant"` (reused).
- `actor_type` for member audit rows is `"member"`.
- Anti-enumeration: login returns generic 401 for unknown/ineligible; `password-reset/request` always returns 204.
- Cross-member resource access returns **404**, never 403.
- `MEMBER_AUTH_MODE` defaults to `jwt`; `stub` is forbidden when `APP_ENV=production`.
- Backend test DB: `export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test` after `docker compose up -d postgres-test`. Tests set `PLATFORM_AUTH_MODE=stub`/`TENANT_AUTH_MODE=stub` via `tests/conftest.py`; add `MEMBER_AUTH_MODE=stub` there too (Task 7).
- Branch: `feat/member-auth/4a` (already created). Commit after every task.

---

### Task 1: Settings — member auth mode + refresh TTL + prod guard

**Files:**
- Modify: `app/core/config.py`
- Test: `tests/core/test_config_member_auth.py`

**Interfaces:**
- Produces: `settings.member_auth_mode: str` (default `"jwt"`), `settings.jwt_refresh_ttl_member_seconds: int` (default `28800`). Stub forbidden in production via the existing validation block.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_config_member_auth.py
from __future__ import annotations

import pytest

from app.core.config import Settings


def _base_env() -> dict[str, str]:
    return {
        "APP_SECRET_KEY": "x" * 32,
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "JWT_KEK": "0" * 44,  # any non-empty value; jwt modes set below
    }


def test_member_auth_mode_defaults_to_jwt() -> None:
    s = Settings(**_base_env())
    assert s.member_auth_mode == "jwt"
    assert s.jwt_refresh_ttl_member_seconds == 28800


def test_member_stub_forbidden_in_production() -> None:
    with pytest.raises(ValueError, match="stub"):
        Settings(
            **_base_env(),
            app_env="production",
            member_auth_mode="stub",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_config_member_auth.py -v`
Expected: FAIL — `member_auth_mode` attribute does not exist.

- [ ] **Step 3: Add the settings fields and guard**

In `app/core/config.py`, next to `tenant_auth_mode` (line ~54) add:

```python
    member_auth_mode: str = "jwt"  # "stub" | "jwt" — stub requires explicit opt-in
```

Next to `jwt_refresh_ttl_tenant_seconds` (line ~61) add:

```python
    jwt_refresh_ttl_member_seconds: int = 28800   # 8 h
```

Find the production-guard block that forbids `stub` when `app_env == "production"` (the block that currently checks `platform_auth_mode`/`tenant_auth_mode`). Extend its condition to include member mode. For example, where it raises for stub-in-prod:

```python
        stub_modes = {
            "platform": self.platform_auth_mode,
            "tenant": self.tenant_auth_mode,
            "member": self.member_auth_mode,
        }
        if self.app_env == "production":
            for name, mode in stub_modes.items():
                if mode == "stub":
                    raise ValueError(
                        f"{name}_auth_mode='stub' is forbidden when APP_ENV=production"
                    )
```

(Adapt to the existing block's exact shape — the requirement is: `member_auth_mode='stub'` + `app_env='production'` raises `ValueError` mentioning "stub". Also ensure the JWT_KEK-required condition includes `member_auth_mode == "jwt"`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_config_member_auth.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run ruff + mypy**

Run: `ruff check app/core/config.py tests/core/test_config_member_auth.py && mypy app/core/config.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py tests/core/test_config_member_auth.py
git commit -m "feat(iam): member_auth_mode + member refresh TTL settings"
```

---

### Task 2: Migration + Member auth columns + MemberSession model

**Files:**
- Create: `alembic/tenant/versions/015_member_auth.py`
- Modify: `app/modules/members/models.py`
- Modify: `app/modules/iam/sessions/models.py`
- Test: `tests/modules/iam/member_auth/test_models.py`

**Interfaces:**
- Produces: `Member.hashed_password: str | None`, `Member.portal_enabled: bool`, `Member.last_login_at: datetime | None`. `MemberSession` model (tenant schema) with columns `id, member_id, jti, user_agent, ip_address, created_at, expires_at, revoked_at, last_used_at`.

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/iam/member_auth/test_models.py
from __future__ import annotations

from app.modules.iam.sessions.models import MemberSession
from app.modules.members.models import Member


def test_member_has_auth_columns() -> None:
    cols = Member.__table__.columns
    assert "hashed_password" in cols
    assert cols["hashed_password"].nullable is True
    assert "portal_enabled" in cols
    assert cols["portal_enabled"].nullable is False
    assert "last_login_at" in cols


def test_member_session_table_shape() -> None:
    assert MemberSession.__tablename__ == "member_sessions"
    # Tenant-schema table: no explicit schema.
    assert MemberSession.__table__.schema is None
    cols = MemberSession.__table__.columns
    for name in (
        "id", "member_id", "jti", "user_agent", "ip_address",
        "created_at", "expires_at", "revoked_at", "last_used_at",
    ):
        assert name in cols
```

Also create `tests/modules/iam/member_auth/__init__.py` (empty).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/modules/iam/member_auth/test_models.py -v`
Expected: FAIL — `MemberSession` import error / columns missing.

- [ ] **Step 3: Add the Member auth columns**

In `app/modules/members/models.py`, after the `# Status lifecycle` block (after `joined_at`), add:

```python
    # Portal authentication (Phase 4a). NULL hashed_password until the member
    # sets a password via the operator-issued set-password token. portal_enabled
    # is the operator gate; both must be satisfied (plus status='active') to log in.
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    portal_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
```

Update the imports at the top of the file: add `Boolean` to the `from sqlalchemy import (...)` list, and add `TIMESTAMP` if not already imported there (it currently imports `TIMESTAMP` from `sqlalchemy`). Confirm `datetime` is imported (it is).

- [ ] **Step 4: Add the MemberSession model**

In `app/modules/iam/sessions/models.py`, append after `TenantSession`:

```python
class MemberSession(Base):
    """Server-side session for a SACCO member (portal login).

    Identical layout to TenantSession except the user FK column is
    ``member_id``. Lives in the tenant schema — no ``schema=``; resolved at
    runtime via ``SET LOCAL search_path``.
    """

    __tablename__ = "member_sessions"
    __table_args__ = (
        Index("ix_member_sessions_member_id", "member_id"),
        Index("ix_member_sessions_jti", "jti"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    jti: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
```

- [ ] **Step 5: Write the migration**

```python
# alembic/tenant/versions/015_member_auth.py
"""Phase 4a — member portal auth: members credential columns + member_sessions.

Revision: 015
Depends on: 014
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "members",
        sa.Column("hashed_password", sa.Text(), nullable=True),
    )
    op.add_column(
        "members",
        sa.Column(
            "portal_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "members",
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "member_sessions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("jti", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("jti", name="uq_member_sessions_jti"),
    )
    op.create_index("ix_member_sessions_member_id", "member_sessions", ["member_id"])
    op.create_index("ix_member_sessions_jti", "member_sessions", ["jti"])


def downgrade() -> None:
    op.drop_index("ix_member_sessions_jti", table_name="member_sessions")
    op.drop_index("ix_member_sessions_member_id", table_name="member_sessions")
    op.drop_table("member_sessions")
    op.drop_column("members", "last_login_at")
    op.drop_column("members", "portal_enabled")
    op.drop_column("members", "hashed_password")
```

- [ ] **Step 6: Run the model test + apply migration to the test DB**

Run:
```bash
pytest tests/modules/iam/member_auth/test_models.py -v
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test \
  python scripts/migrate_all_tenants.py || alembic -c alembic/tenant/alembic.ini upgrade head
```
Expected: model test PASS; migration applies cleanly (revision 015). (Use the project's standard tenant-migration command — `run_tenant_migrations()` per the platform_ contract; `scripts/migrate_all_tenants.py` is the script wrapper used in the run-book.)

- [ ] **Step 7: Run ruff + mypy**

Run: `ruff check app/modules/members/models.py app/modules/iam/sessions/models.py alembic/tenant/versions/015_member_auth.py && mypy app/modules/members/models.py app/modules/iam/sessions/models.py`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add app/modules/members/models.py app/modules/iam/sessions/models.py \
  alembic/tenant/versions/015_member_auth.py tests/modules/iam/member_auth/
git commit -m "feat(iam): member auth columns + member_sessions (migration 015)"
```

---

### Task 3: Generalize SessionService for MemberSession

**Files:**
- Modify: `app/modules/iam/sessions/service.py`
- Test: `tests/modules/iam/member_auth/test_session_service_member.py`

**Interfaces:**
- Consumes: `MemberSession` (Task 2), `SessionService` (existing).
- Produces: `SessionService(db, model_cls=MemberSession, redis=...)` works — `create()` writes `member_id`, `revoke_all_for_user()` filters on `member_id`.

- [ ] **Step 1: Write the failing test**

This is an integration test (real Postgres, tenant schema). Use the project's existing tenant-session test fixture pattern (`async_sessionmaker` + commit + cleanup — see `feedback_test_patterns`). Pseudocode of the assertion:

```python
# tests/modules/iam/member_auth/test_session_service_member.py
from __future__ import annotations

import uuid

import pytest

from app.modules.iam.sessions.models import MemberSession
from app.modules.iam.sessions.service import SessionService


@pytest.mark.asyncio
async def test_create_member_session_sets_member_id(tenant_db_session) -> None:
    svc = SessionService(db=tenant_db_session, model_cls=MemberSession, redis=None)
    member_id = uuid.uuid4()
    row = await svc.create(
        user_id=member_id,
        jti=str(uuid.uuid4()),
        user_agent="pytest",
        ip_address="127.0.0.1",
        refresh_ttl_seconds=3600,
    )
    await tenant_db_session.flush()
    assert isinstance(row, MemberSession)
    assert row.member_id == member_id


@pytest.mark.asyncio
async def test_revoke_all_for_member(tenant_db_session) -> None:
    svc = SessionService(db=tenant_db_session, model_cls=MemberSession, redis=None)
    member_id = uuid.uuid4()
    for _ in range(2):
        await svc.create(
            user_id=member_id, jti=str(uuid.uuid4()),
            user_agent=None, ip_address=None, refresh_ttl_seconds=3600,
        )
    await tenant_db_session.flush()
    revoked = await svc.revoke_all_for_user(member_id)
    assert revoked == 2
```

(Use the same `tenant_db_session` fixture style other IAM tenant-session tests use; if none exists, build it with `async_sessionmaker` against the test DB with `search_path` set to a test tenant schema, per `feedback_test_patterns`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test pytest tests/modules/iam/member_auth/test_session_service_member.py -v`
Expected: FAIL — `create()` builds a `TenantSession` (the `else` branch) and sets `tenant_user_id`, not `member_id`; `isinstance(row, MemberSession)` fails.

- [ ] **Step 3: Generalize the service**

In `app/modules/iam/sessions/service.py`:

1. Import `MemberSession`:
```python
from app.modules.iam.sessions.models import MemberSession, PlatformSession, TenantSession
```
2. Widen the union:
```python
AnySessionModel = PlatformSession | TenantSession | MemberSession
```
3. Replace the `_user_id_attr` assignment in `__init__` with an explicit map:
```python
        self._user_id_attr = {
            PlatformSession: "platform_user_id",
            TenantSession: "tenant_user_id",
            MemberSession: "member_id",
        }[model_cls]
```
4. Replace the `create()` row-construction branch with a generic build keyed on the FK attr:
```python
        row: AnySessionModel = self._model(
            **{self._user_id_attr: user_id},
            jti=jti,
            user_agent=user_agent,
            ip_address=ip_address,
            created_at=now,
            expires_at=expires_at,
        )
```
(This replaces the `if self._model is PlatformSession: ... else: ...` block. `self._db.add(row)` and the Redis write stay unchanged.)

- [ ] **Step 4: Run test to verify it passes + regression on existing session tests**

Run:
```bash
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test \
  pytest tests/modules/iam/member_auth/test_session_service_member.py \
         tests/modules/iam/ -k session -v
```
Expected: new tests PASS; existing platform/tenant session tests still PASS.

- [ ] **Step 5: Run ruff + mypy**

Run: `ruff check app/modules/iam/sessions/service.py && mypy app/modules/iam/sessions/service.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/sessions/service.py tests/modules/iam/member_auth/test_session_service_member.py
git commit -m "feat(iam): SessionService supports MemberSession"
```

---

### Task 4: Member auth schemas + audit helper

**Files:**
- Create: `app/modules/iam/member_auth/__init__.py`
- Create: `app/modules/iam/member_auth/schemas.py`
- Modify: `app/modules/iam/auth_audit.py`
- Test: `tests/modules/iam/member_auth/test_auth_audit_member.py`

**Interfaces:**
- Produces: `MemberLoginRequest`, `MemberRefreshRequest`, `MemberTokenResponse`, `MemberOut`, `MemberPasswordResetRequestBody`, `MemberPasswordResetConfirmBody`, `EnablePortalAccessOut`. `write_member_auth_event(...)` writing rows with `actor_type="member"` to the tenant `audit_log`.

- [ ] **Step 1: Write the failing test (audit helper)**

```python
# tests/modules/iam/member_auth/test_auth_audit_member.py
from __future__ import annotations

import uuid

import pytest

from app.modules.iam.auth_audit import write_member_auth_event


@pytest.mark.asyncio
async def test_write_member_auth_event_records_member_actor(tenant_db_session) -> None:
    member_id = uuid.uuid4()
    await write_member_auth_event(
        db=tenant_db_session,
        operation="login_success",
        actor_id=member_id,
        actor_label="jane@example.com",
        after_state={"session_id": "s1"},
    )
    # Audit row written to tenant audit_log with actor_type='member'.
    from sqlalchemy import text
    row = (
        await tenant_db_session.execute(
            text(
                "SELECT actor_type, table_name FROM audit_log "
                "WHERE actor_id = :aid ORDER BY occurred_at DESC LIMIT 1"
            ),
            {"aid": member_id},
        )
    ).first()
    assert row is not None
    assert row.actor_type == "member"
    assert row.table_name == "member_sessions"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=... pytest tests/modules/iam/member_auth/test_auth_audit_member.py -v`
Expected: FAIL — `write_member_auth_event` does not exist.

- [ ] **Step 3: Add the audit helper**

In `app/modules/iam/auth_audit.py`, add a member table resolver and writer:

```python
def _member_table(operation: str, override: str | None) -> str:
    if override:
        return override
    return "member_sessions" if operation in _SESSION_OPERATIONS else "members"


async def write_member_auth_event(
    *,
    db: AsyncSession,
    operation: str,
    actor_id: uuid.UUID | None,
    actor_label: str | None = None,
    tenant_slug: str | None = None,
    after_state: dict[str, Any] | None = None,
    table_name: str | None = None,
) -> None:
    """Write a single member auth audit row to the tenant audit_log.

    actor_type is "member" when actor_id is known, else "anonymous".
    """
    svc = TenantAuditService(db)
    state: dict[str, Any] = dict(after_state or {})
    if tenant_slug:
        state["tenant"] = tenant_slug
    await svc.record(
        table_name=_member_table(operation, table_name),
        record_id=actor_id if actor_id is not None else _NIL_UUID,
        operation=operation,
        actor_type="member" if actor_id is not None else "anonymous",
        actor_id=actor_id,
        actor_label=actor_label,
        after_state=state if state else None,
    )
```

- [ ] **Step 4: Write the schemas**

```python
# app/modules/iam/member_auth/schemas.py
"""Pydantic schemas for member auth endpoints (Phase 4a)."""
from __future__ import annotations

import uuid  # noqa: TC003
from datetime import date, datetime  # noqa: TC003

from pydantic import BaseModel, EmailStr, Field


class MemberLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class MemberRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class MemberTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class MemberOut(BaseModel):
    id: uuid.UUID
    member_number: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    status: str
    date_of_birth: date
    gender: str
    joined_at: date | None = None
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class MemberPasswordResetRequestBody(BaseModel):
    email: EmailStr


class MemberPasswordResetConfirmBody(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class EnablePortalAccessOut(BaseModel):
    """Returned to the operator. set_password_token is shown once, OOB-delivered."""

    member_id: uuid.UUID
    portal_enabled: bool
    set_password_token: str
    expires_in: int
```

Create empty `app/modules/iam/member_auth/__init__.py`.

- [ ] **Step 5: Run tests + ruff + mypy**

Run:
```bash
DATABASE_URL=... pytest tests/modules/iam/member_auth/test_auth_audit_member.py -v
ruff check app/modules/iam/member_auth/ app/modules/iam/auth_audit.py && mypy app/modules/iam/member_auth/schemas.py app/modules/iam/auth_audit.py
```
Expected: PASS + clean.

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/member_auth/__init__.py app/modules/iam/member_auth/schemas.py \
  app/modules/iam/auth_audit.py tests/modules/iam/member_auth/test_auth_audit_member.py
git commit -m "feat(iam): member auth schemas + write_member_auth_event"
```

---

### Task 5: MemberAuthService — enable_access + reset

**Files:**
- Create: `app/modules/iam/member_auth/service.py`
- Test: `tests/modules/iam/member_auth/test_service_enable_reset.py`

**Interfaces:**
- Consumes: `MemberSession`, `SessionService`, `make_reset_token`/`verify_reset_token`, `hash_password`, `write_member_auth_event`, `Member`.
- Produces: `MemberAuthService(db, key_service, redis, tenant_slug)` with:
  - `async enable_access(member_id: uuid.UUID) -> tuple[str, int]` → `(set_password_token, ttl_seconds)`; sets `portal_enabled=True`; raises `HTTPException(400)` if member has no email or member not found (404).
  - `async reset_request(email: str) -> None` (always None; 15-min TTL).
  - `async reset_confirm(token: str, new_password: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/iam/member_auth/test_service_enable_reset.py
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.modules.iam.member_auth.service import MemberAuthService, OPERATOR_SET_PASSWORD_TTL
from app.modules.iam.passwords.service import verify_password
from app.modules.iam.reset_tokens import verify_reset_token
from app.modules.members.models import Member


def _member(**kw) -> Member:
    defaults = dict(
        id=uuid.uuid4(), member_number="M-00001", full_name="Jane Doe",
        date_of_birth=date(1990, 1, 1), gender="female", status="active",
        email="jane@example.com",
    )
    defaults.update(kw)
    return Member(**defaults)


@pytest.mark.asyncio
async def test_enable_access_sets_flag_and_returns_token(tenant_db_session, fake_key_service) -> None:
    m = _member()
    tenant_db_session.add(m)
    await tenant_db_session.flush()
    svc = MemberAuthService(db=tenant_db_session, key_service=fake_key_service, redis=None, tenant_slug="acme")
    token, ttl = await svc.enable_access(m.id)
    assert ttl == OPERATOR_SET_PASSWORD_TTL
    payload = verify_reset_token(token, _secret())
    assert payload["sub"] == str(m.id)
    await tenant_db_session.refresh(m)
    assert m.portal_enabled is True


@pytest.mark.asyncio
async def test_enable_access_rejects_member_without_email(tenant_db_session, fake_key_service) -> None:
    m = _member(email=None)
    tenant_db_session.add(m)
    await tenant_db_session.flush()
    svc = MemberAuthService(db=tenant_db_session, key_service=fake_key_service, redis=None, tenant_slug="acme")
    with pytest.raises(HTTPException) as exc:
        await svc.enable_access(m.id)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_reset_confirm_sets_password(tenant_db_session, fake_key_service) -> None:
    m = _member(portal_enabled=True)
    tenant_db_session.add(m)
    await tenant_db_session.flush()
    svc = MemberAuthService(db=tenant_db_session, key_service=fake_key_service, redis=None, tenant_slug="acme")
    token, _ = await svc.enable_access(m.id)
    await svc.reset_confirm(token=token, new_password="N3wPassw0rd!")
    await tenant_db_session.refresh(m)
    assert m.hashed_password is not None
    assert verify_password("N3wPassw0rd!", m.hashed_password)


def _secret() -> str:
    from app.core.config import get_settings
    return get_settings().app_secret_key
```

Add a `fake_key_service` fixture in `tests/modules/iam/member_auth/conftest.py` that returns a stub with `get_active_signing_key` and `get_verification_key` — not used by enable/reset but imported by the service constructor. Minimal:

```python
# tests/modules/iam/member_auth/conftest.py
import pytest


class _FakeKeyService:
    async def get_active_signing_key(self, audience):  # noqa: ANN001
        raise NotImplementedError

    async def get_verification_key(self, kid):  # noqa: ANN001
        raise NotImplementedError


@pytest.fixture
def fake_key_service() -> _FakeKeyService:
    return _FakeKeyService()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=... pytest tests/modules/iam/member_auth/test_service_enable_reset.py -v`
Expected: FAIL — `MemberAuthService` does not exist.

- [ ] **Step 3: Write the service (enable + reset only)**

```python
# app/modules/iam/member_auth/service.py
"""MemberAuthService — member portal authentication (Phase 4a).

Mirrors TenantAuthService but queries Member (not TenantUser), creates
MemberSession rows, and issues JWTs with aud="member:<slug>". The signing key
is still looked up with audience "tenant" (the DB column value).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.config import get_settings
from app.modules.iam.auth_audit import write_member_auth_event
from app.modules.iam.lockout import is_locked, record_attempt
from app.modules.iam.lockout import reset as reset_lockout
from app.modules.iam.member_auth.schemas import MemberTokenResponse
from app.modules.iam.passwords.service import hash_password, needs_rehash, verify_password
from app.modules.iam.reset_tokens import make_reset_token, verify_reset_token
from app.modules.iam.sessions.models import MemberSession
from app.modules.iam.sessions.service import SessionService
from app.modules.iam.tokens.service import (
    decode_token,
    encode_access_token,
    encode_refresh_token,
    get_unverified_kid,
)
from app.modules.members.models import Member

_log = structlog.get_logger(__name__)

_KEY_AUDIENCE = "tenant"  # signing-key DB column value (reused)
OPERATOR_SET_PASSWORD_TTL = 86400  # 24h for operator-issued set-password tokens
_SELF_RESET_TTL = 900  # 15 min for self-service reset


class MemberAuthService:
    def __init__(
        self,
        db: AsyncSession,
        key_service: Any,
        redis: Any | None,
        tenant_slug: str,
    ) -> None:
        self._db = db
        self._key_service = key_service
        self._redis = redis
        self._slug = tenant_slug
        self._audience = f"member:{tenant_slug}"
        self._session_svc = SessionService(db=db, model_cls=MemberSession, redis=redis)

    async def _get_member_by_id(self, member_id: uuid.UUID) -> Member | None:
        result = await self._db.execute(select(Member).where(Member.id == member_id))
        return result.scalar_one_or_none()

    async def _get_member_by_email(self, email: str) -> Member | None:
        result = await self._db.execute(select(Member).where(Member.email == email))
        return result.scalar_one_or_none()

    # ── enable_access (operator) ────────────────────────────────────────────

    async def enable_access(self, member_id: uuid.UUID) -> tuple[str, int]:
        """Enable portal access for a member and mint a one-time set-password token.

        Raises:
            HTTPException 404: member not found.
            HTTPException 400: member has no email.
        """
        settings = get_settings()
        member = await self._get_member_by_id(member_id)
        if member is None:
            raise HTTPException(status_code=404, detail="Member not found")
        if not member.email:
            raise HTTPException(
                status_code=400, detail="Member has no email; cannot enable portal access"
            )

        member.portal_enabled = True

        token, jti = make_reset_token(
            str(member.id), settings.app_secret_key, ttl=OPERATOR_SET_PASSWORD_TTL
        )
        if self._redis is not None:
            await self._redis.set(f"iam:pwreset:{jti}", "1", ex=OPERATOR_SET_PASSWORD_TTL)

        await write_member_auth_event(
            db=self._db,
            operation="portal_access_enabled",
            actor_id=member.id,
            actor_label=member.email,
            tenant_slug=self._slug,
            table_name="members",
        )
        _log.info("member_auth.enable_access", member_id=str(member.id), tenant=self._slug)
        return token, OPERATOR_SET_PASSWORD_TTL

    # ── reset_request (self-service) ────────────────────────────────────────

    async def reset_request(self, email: str) -> None:
        """Always returns None (anti-enumeration). 15-min token."""
        settings = get_settings()
        member = await self._get_member_by_email(email)
        if member is None or not member.portal_enabled:
            return
        token, jti = make_reset_token(str(member.id), settings.app_secret_key, ttl=_SELF_RESET_TTL)
        if self._redis is not None:
            await self._redis.set(f"iam:pwreset:{jti}", "1", ex=_SELF_RESET_TTL)
        _log.warning(
            "MEMBER PASSWORD RESET TOKEN — dev only, configure email notifier for production",
            email=email, tenant=self._slug, reset_token=token,
        )
        await write_member_auth_event(
            db=self._db, operation="password_reset_requested",
            actor_id=member.id, actor_label=member.email, tenant_slug=self._slug,
            table_name="members",
        )

    # ── reset_confirm ───────────────────────────────────────────────────────

    async def reset_confirm(self, token: str, new_password: str) -> None:
        settings = get_settings()
        try:
            payload = verify_reset_token(token, settings.app_secret_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid reset token: {exc}") from exc

        jti = str(payload["jti"])
        member_id_str = str(payload["sub"])

        if self._redis is not None:
            if not await self._redis.exists(f"iam:pwreset:{jti}"):
                raise HTTPException(
                    status_code=400, detail="Reset token has already been used or has expired"
                )

        try:
            member_id = uuid.UUID(member_id_str)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Malformed token payload") from exc

        member = await self._get_member_by_id(member_id)
        if member is None:
            raise HTTPException(status_code=400, detail="Invalid reset token")

        try:
            member.hashed_password = hash_password(new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if self._redis is not None:
            await self._redis.delete(f"iam:pwreset:{jti}")

        await self._session_svc.revoke_all_for_user(member_id)
        await write_member_auth_event(
            db=self._db, operation="password_reset_confirmed",
            actor_id=member_id, actor_label=member.email, tenant_slug=self._slug,
            table_name="members",
        )
        _log.info("member_auth.password_reset_confirmed", member_id=str(member.id), tenant=self._slug)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DATABASE_URL=... pytest tests/modules/iam/member_auth/test_service_enable_reset.py -v`
Expected: PASS.

- [ ] **Step 5: Run ruff + mypy**

Run: `ruff check app/modules/iam/member_auth/service.py && mypy app/modules/iam/member_auth/service.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/member_auth/service.py tests/modules/iam/member_auth/test_service_enable_reset.py tests/modules/iam/member_auth/conftest.py
git commit -m "feat(iam): MemberAuthService enable_access + password reset"
```

---

### Task 6: MemberAuthService — login / refresh / logout / me

**Files:**
- Modify: `app/modules/iam/member_auth/service.py`
- Test: `tests/modules/iam/member_auth/test_service_login.py`

**Interfaces:**
- Consumes: everything from Task 5 + `encode_access_token`/`encode_refresh_token`/`decode_token`/`get_unverified_kid`.
- Produces, on `MemberAuthService`:
  - `async login(email, password, user_agent, ip_address) -> MemberTokenResponse`
  - `async refresh(refresh_token) -> MemberTokenResponse`
  - `async logout(access_token) -> None`
  - `async me(access_token) -> Member`

  Eligibility: `portal_enabled and hashed_password and status == "active"`. Generic 401 for unknown/ineligible at login; 423 on lockout. Updates `last_login_at` via targeted UPDATE.

- [ ] **Step 1: Write the failing test**

This test needs real signing keys. Reuse the existing IAM auth test harness that seeds a `tenant` signing key (see how `tests/modules/iam/.../test_tenant_auth*` build `KeyService` with a real key, or the e2e seed's `KeyService.generate_and_insert("tenant")`). Outline:

```python
# tests/modules/iam/member_auth/test_service_login.py
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.modules.iam.member_auth.service import MemberAuthService
from app.modules.iam.passwords.service import hash_password
from app.modules.members.models import Member


def _enabled_member(pw: str = "S3cret-pass!") -> Member:
    return Member(
        id=uuid.uuid4(), member_number="M-00002", full_name="Eli M",
        date_of_birth=date(1991, 2, 2), gender="male", status="active",
        email="eli@example.com", portal_enabled=True, hashed_password=hash_password(pw),
    )


@pytest.mark.asyncio
async def test_login_success_issues_tokens(tenant_db_session, real_key_service) -> None:
    m = _enabled_member()
    tenant_db_session.add(m)
    await tenant_db_session.flush()
    svc = MemberAuthService(db=tenant_db_session, key_service=real_key_service, redis=None, tenant_slug="acme")
    resp = await svc.login(email="eli@example.com", password="S3cret-pass!", user_agent="pytest", ip_address="127.0.0.1")
    assert resp.access_token and resp.refresh_token
    assert resp.expires_in > 0
    # me() round-trips the access token.
    who = await svc.me(resp.access_token)
    assert who.id == m.id


@pytest.mark.asyncio
async def test_login_rejects_disabled_portal(tenant_db_session, real_key_service) -> None:
    m = _enabled_member()
    m.portal_enabled = False
    tenant_db_session.add(m)
    await tenant_db_session.flush()
    svc = MemberAuthService(db=tenant_db_session, key_service=real_key_service, redis=None, tenant_slug="acme")
    with pytest.raises(HTTPException) as exc:
        await svc.login(email="eli@example.com", password="S3cret-pass!", user_agent=None, ip_address=None)
    assert exc.value.status_code == 401  # generic, anti-enumeration


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(tenant_db_session, real_key_service) -> None:
    m = _enabled_member()
    tenant_db_session.add(m)
    await tenant_db_session.flush()
    svc = MemberAuthService(db=tenant_db_session, key_service=real_key_service, redis=None, tenant_slug="acme")
    with pytest.raises(HTTPException) as exc:
        await svc.login(email="eli@example.com", password="wrong", user_agent=None, ip_address=None)
    assert exc.value.status_code == 401
```

Provide a `real_key_service` fixture (module conftest) that inserts an active `tenant` signing key into the platform schema and returns a `KeyService` bound to a platform session — copy the construction the existing tenant-auth service tests use.

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=... pytest tests/modules/iam/member_auth/test_service_login.py -v`
Expected: FAIL — `login`/`me` not defined.

- [ ] **Step 3: Add the methods**

Append to `MemberAuthService` in `app/modules/iam/member_auth/service.py`. Add a module-level helper and the eligibility check:

```python
    def _is_eligible(self, member: Member) -> bool:
        return bool(member.portal_enabled and member.hashed_password and member.status == "active")

    async def _decode(self, token: str, detail: str) -> dict[str, object]:
        try:
            kid = get_unverified_kid(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=detail) from exc
        try:
            public_key_pem, algorithm, _aud = await self._key_service.get_verification_key(kid)
        except Exception as exc:
            raise HTTPException(status_code=401, detail=detail) from exc
        try:
            return decode_token(
                token, audience=self._audience,
                public_key_pem=public_key_pem, algorithm=algorithm,
            )
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=detail) from exc

    async def login(
        self, email: str, password: str, user_agent: str | None, ip_address: str | None
    ) -> MemberTokenResponse:
        settings = get_settings()
        member = await self._get_member_by_email(email)

        if member is None or not self._is_eligible(member):
            await record_attempt(email, self._redis)
            await write_member_auth_event(
                db=self._db, operation="login_failed", actor_id=None, actor_label=email,
                tenant_slug=self._slug, after_state={"reason": "not_found_or_ineligible"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        locked, retry_after = await is_locked(email, self._redis)
        if locked:
            await write_member_auth_event(
                db=self._db, operation="login_locked", actor_id=member.id, actor_label=member.email,
                tenant_slug=self._slug, after_state={"retry_after": retry_after},
            )
            raise HTTPException(
                status_code=423, detail="Account locked due to too many failed attempts",
                headers={"Retry-After": str(retry_after)},
            )

        assert member.hashed_password is not None  # _is_eligible guarantees this
        if not verify_password(password, member.hashed_password):
            await record_attempt(email, self._redis)
            await write_member_auth_event(
                db=self._db, operation="login_failed", actor_id=member.id, actor_label=member.email,
                tenant_slug=self._slug, after_state={"reason": "bad_password"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        await reset_lockout(email, self._redis)
        if needs_rehash(member.hashed_password):
            member.hashed_password = hash_password(password)

        kid, private_key_pem, algorithm = await self._key_service.get_active_signing_key(_KEY_AUDIENCE)
        jti = str(uuid.uuid4())
        session_row = await self._session_svc.create(
            user_id=member.id, jti=jti, user_agent=user_agent, ip_address=ip_address,
            refresh_ttl_seconds=settings.jwt_refresh_ttl_member_seconds,
        )
        await self._db.flush()

        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=str(member.id), audience=self._audience, session_id=str(session_row.id),
            actor_type="member", kid=kid, private_key_pem=private_key_pem,
            algorithm=algorithm, ttl_seconds=access_ttl,
        )
        refresh_token = encode_refresh_token(
            sub=str(member.id), audience=self._audience, session_id=str(session_row.id),
            jti=jti, kid=kid, private_key_pem=private_key_pem,
            algorithm=algorithm, ttl_seconds=settings.jwt_refresh_ttl_member_seconds,
        )

        # last_login_at via targeted UPDATE — bypasses the AuditableMixin diff
        # so routine logins don't spam the audit log.
        await self._db.execute(
            update(Member).where(Member.id == member.id).values(last_login_at=datetime.now(UTC))
        )

        await write_member_auth_event(
            db=self._db, operation="login_success", actor_id=member.id, actor_label=member.email,
            tenant_slug=self._slug, after_state={"session_id": str(session_row.id), "ip_address": ip_address},
        )
        _log.info("member_auth.login_success", member_id=str(member.id), tenant=self._slug)
        return MemberTokenResponse(
            access_token=access_token, refresh_token=refresh_token, expires_in=access_ttl
        )

    async def refresh(self, refresh_token: str) -> MemberTokenResponse:
        settings = get_settings()
        claims = await self._decode(refresh_token, "Invalid or expired refresh token")
        session_id_str = claims.get("session_id")
        jti = claims.get("jti")
        if not session_id_str or not jti:
            raise HTTPException(status_code=401, detail="Malformed token claims")
        try:
            session_id = uuid.UUID(str(session_id_str))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Malformed session_id claim") from exc

        session_row = await self._session_svc.get_by_session_id(session_id)
        if session_row is None:
            raise HTTPException(status_code=401, detail="Session not found")
        if session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session has been revoked")
        if session_row.expires_at < datetime.now(UTC):
            raise HTTPException(status_code=401, detail="Session has expired")
        if session_row.jti != str(jti):
            raise HTTPException(status_code=401, detail="Token jti mismatch")
        if not await self._session_svc.is_jti_valid(str(jti)):
            raise HTTPException(status_code=401, detail="Session has been revoked")

        kid, private_key_pem, algorithm = await self._key_service.get_active_signing_key(_KEY_AUDIENCE)
        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=str(claims["sub"]), audience=self._audience, session_id=str(session_id_str),
            actor_type="member", kid=kid, private_key_pem=private_key_pem,
            algorithm=algorithm, ttl_seconds=access_ttl,
        )
        await self._session_svc.update_last_used(session_id)
        await write_member_auth_event(
            db=self._db, operation="refresh", actor_id=uuid.UUID(str(claims["sub"])),
            tenant_slug=self._slug, after_state={"session_id": str(session_id_str)},
        )
        return MemberTokenResponse(access_token=access_token, refresh_token=None, expires_in=access_ttl)

    async def logout(self, access_token: str) -> None:
        claims = await self._decode(access_token, "Invalid or expired access token")
        session_id_str = claims.get("session_id")
        if not session_id_str:
            raise HTTPException(status_code=401, detail="Malformed token claims")
        try:
            session_id = uuid.UUID(str(session_id_str))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Malformed session_id claim") from exc
        await self._session_svc.revoke(session_id)
        await write_member_auth_event(
            db=self._db, operation="logout", actor_id=uuid.UUID(str(claims["sub"])),
            tenant_slug=self._slug, after_state={"session_id": str(session_id_str)},
        )

    async def me(self, access_token: str) -> Member:
        claims = await self._decode(access_token, "Invalid or expired access token")
        session_id_str = claims.get("session_id")
        sub = claims.get("sub")
        if not session_id_str or not sub:
            raise HTTPException(status_code=401, detail="Malformed token claims")
        try:
            session_id = uuid.UUID(str(session_id_str))
            member_id = uuid.UUID(str(sub))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Malformed token claims") from exc
        session_row = await self._session_svc.get_by_session_id(session_id)
        if session_row is None or session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session not found or revoked")
        member = await self._get_member_by_id(member_id)
        if member is None:
            raise HTTPException(status_code=401, detail="Member not found")
        return member
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DATABASE_URL=... pytest tests/modules/iam/member_auth/test_service_login.py -v`
Expected: PASS.

- [ ] **Step 5: Run ruff + mypy**

Run: `ruff check app/modules/iam/member_auth/service.py && mypy app/modules/iam/member_auth/service.py`
Expected: clean. (Note: `cast`/`assert` may be needed for mypy on `session_row.jti`; `AnySessionModel` covers MemberSession.)

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/member_auth/service.py tests/modules/iam/member_auth/test_service_login.py
git commit -m "feat(iam): MemberAuthService login/refresh/logout/me"
```

---

### Task 7: CurrentMember dependency + MEMBER_AUTH_MODE switch

**Files:**
- Modify: `app/modules/iam/dependencies.py`
- Modify: `tests/conftest.py`
- Test: `tests/modules/iam/member_auth/test_dependency.py`

**Interfaces:**
- Produces: `CurrentMember = Annotated[Member, Depends(get_current_member)]` exported from `app.modules.iam.dependencies`. JWT impl validates `aud="member:<slug>"`, checks `MemberSession`, loads `Member`, requires eligibility (403 if mid-session ineligible), binds structlog `actor_type="member"`. Stub impl reads `X-Member-Actor-ID`. Switch on `settings.member_auth_mode`.

- [ ] **Step 1: Write the failing test (stub path — no crypto)**

```python
# tests/modules/iam/member_auth/test_dependency.py
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.modules.iam.dependencies import get_current_member_stub
from app.modules.members.models import Member


@pytest.mark.asyncio
async def test_stub_resolves_active_enabled_member(tenant_db_session) -> None:
    m = Member(
        id=uuid.uuid4(), member_number="M-1", full_name="A", date_of_birth=date(1990, 1, 1),
        gender="male", status="active", email="a@example.com", portal_enabled=True,
        hashed_password="x",
    )
    tenant_db_session.add(m)
    await tenant_db_session.flush()
    out = await get_current_member_stub(x_member_actor_id=str(m.id), session=tenant_db_session)
    assert out.id == m.id


@pytest.mark.asyncio
async def test_stub_rejects_suspended_member(tenant_db_session) -> None:
    m = Member(
        id=uuid.uuid4(), member_number="M-2", full_name="B", date_of_birth=date(1990, 1, 1),
        gender="male", status="suspended", email="b@example.com", portal_enabled=True,
        hashed_password="x",
    )
    tenant_db_session.add(m)
    await tenant_db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await get_current_member_stub(x_member_actor_id=str(m.id), session=tenant_db_session)
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=... pytest tests/modules/iam/member_auth/test_dependency.py -v`
Expected: FAIL — `get_current_member_stub` does not exist.

- [ ] **Step 3: Add the dependencies**

In `app/modules/iam/dependencies.py` add imports:

```python
from app.modules.iam.sessions.models import MemberSession  # add to the sessions.models import
from app.modules.members.models import Member
```

Append before the binding-switch block:

```python
# ── Member stub ───────────────────────────────────────────────────────────────


async def get_current_member_stub(
    x_member_actor_id: Annotated[str, Header(alias="X-Member-Actor-ID")],
    session: Annotated[AsyncSession, Depends(get_tenant_session)],
) -> Member:
    """Stub: validates X-Member-Actor-ID against members. NOT production auth."""
    _log.warning("MEMBER STUB AUTH: actor_id=%s — not production auth", x_member_actor_id)
    try:
        member_id = uuid.UUID(x_member_actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid X-Member-Actor-ID: must be a UUID") from exc
    result = await session.execute(select(Member).where(Member.id == member_id))
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=401, detail="Member not found")
    if not (member.portal_enabled and member.status == "active"):
        raise HTTPException(status_code=403, detail="Member portal access is not active")
    structlog.contextvars.bind_contextvars(
        actor_type="member", actor_id=str(member.id), actor_label=member.email or member.member_number
    )
    return member


# ── Member JWT implementation ─────────────────────────────────────────────────


async def get_current_member_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    tenant_db: Annotated[AsyncSession, Depends(get_tenant_session)],
    platform_db: Annotated[AsyncSession, Depends(get_platform_session)],
    request: Request,
) -> Member:
    """Real member auth dependency: validates Bearer JWT (aud=member:<slug>)."""
    settings = get_settings()
    tenant_slug = request.headers.get(settings.tenant_header, "")
    redis = getattr(request.app.state, "redis", None)
    key_service = KeyService(session=platform_db)
    audience = f"member:{tenant_slug}"

    try:
        kid = get_unverified_kid(credentials.credentials)
        public_key_pem, algorithm, _aud = await key_service.get_verification_key(kid)
        claims = decode_token(
            credentials.credentials, audience=audience,
            public_key_pem=public_key_pem, algorithm=algorithm,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    session_id_str = claims.get("session_id")
    sub = claims.get("sub")
    if not session_id_str or not sub:
        raise HTTPException(status_code=401, detail="Malformed token claims")
    try:
        session_id = uuid.UUID(str(session_id_str))
        member_id = uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Malformed token claims") from exc

    svc = SessionService(db=tenant_db, model_cls=MemberSession, redis=redis)
    session_row = await svc.get_by_session_id(session_id)
    if session_row is None or session_row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session not found or revoked")

    result = await tenant_db.execute(select(Member).where(Member.id == member_id))
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=401, detail="Member not found")
    if not (member.portal_enabled and member.status == "active"):
        raise HTTPException(status_code=403, detail="Member portal access is not active")

    structlog.contextvars.bind_contextvars(
        actor_type="member", actor_id=str(member.id), actor_label=member.email or member.member_number
    )
    return member
```

At the binding-switch block at the bottom, add:

```python
if _settings.member_auth_mode == "jwt":
    get_current_member = get_current_member_jwt
else:
    get_current_member = get_current_member_stub  # type: ignore[assignment]

CurrentMember = Annotated[Member, Depends(get_current_member)]
```

- [ ] **Step 4: Set stub mode for tests**

In `tests/conftest.py`, where `PLATFORM_AUTH_MODE`/`TENANT_AUTH_MODE` are `setdefault`-ed to `stub`, add:

```python
os.environ.setdefault("MEMBER_AUTH_MODE", "stub")
```

- [ ] **Step 5: Run test + ruff + mypy**

Run:
```bash
DATABASE_URL=... pytest tests/modules/iam/member_auth/test_dependency.py -v
ruff check app/modules/iam/dependencies.py && mypy app/modules/iam/dependencies.py
```
Expected: PASS + clean.

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/dependencies.py tests/conftest.py tests/modules/iam/member_auth/test_dependency.py
git commit -m "feat(iam): CurrentMember dependency + MEMBER_AUTH_MODE switch"
```

---

### Task 8: /member/auth router + operator enable endpoint + wiring

**Files:**
- Create: `app/modules/iam/member_auth/api.py`
- Modify: `app/modules/members/api.py`
- Modify: `app/modules/members/service.py`
- Modify: `app/main.py`
- Test: `tests/modules/iam/member_auth/test_api.py`

**Interfaces:**
- Consumes: `MemberAuthService`, `CurrentMember`, `CurrentTenantUser`.
- Produces: router with `POST /member/auth/token`, `/refresh`, `/logout`, `GET /member/auth/me`, `POST /member/auth/password-reset/request`, `/password-reset/confirm`. Operator endpoint `POST /members/{member_id}/enable-portal-access` (gated `CurrentTenantUser`) → `EnablePortalAccessOut`. `MemberService.enable_portal_access(member_id)` delegates to `MemberAuthService`.

- [ ] **Step 1: Write the failing test (operator enable + member login via stub-mode API)**

```python
# tests/modules/iam/member_auth/test_api.py
from __future__ import annotations

# Uses the shared `client` fixture (real Postgres, stub auth) + tenant headers,
# mirroring tests/modules/savings/test_api.py. Seed a member via the members
# create endpoint or a direct insert, then:
#   1. POST /members/{id}/enable-portal-access (operator) -> 200 + set_password_token
#   2. POST /member/auth/password-reset/confirm {token, new_password} -> 204
# Assert the response shapes / status codes. (Login via JWT requires real keys;
# the full login flow is unit-tested in Task 6 and integration-tested in Task 11.)


def test_enable_portal_access_returns_token(client, seeded_member_id, tenant_headers) -> None:
    resp = client.post(
        f"/members/{seeded_member_id}/enable-portal-access", headers=tenant_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["portal_enabled"] is True
    assert body["set_password_token"]
    assert body["expires_in"] == 86400


def test_enable_then_set_password(client, seeded_member_id, tenant_headers) -> None:
    token = client.post(
        f"/members/{seeded_member_id}/enable-portal-access", headers=tenant_headers
    ).json()["set_password_token"]
    resp = client.post(
        "/member/auth/password-reset/confirm",
        json={"token": token, "new_password": "Br4nd-New-Pass!"},
        headers=tenant_headers,
    )
    assert resp.status_code == 204
```

Add `seeded_member_id` / `tenant_headers` fixtures consistent with existing member API tests (`tests/modules/members/`). If Redis is unavailable in the test client, the service's `redis is None` branch skips the jti check, so confirm succeeds.

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=... pytest tests/modules/iam/member_auth/test_api.py -v`
Expected: FAIL — routes 404 / not wired.

- [ ] **Step 3: Write the member-auth router**

```python
# app/modules/iam/member_auth/api.py
"""FastAPI router for /member/auth/* endpoints (Phase 4a)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.config import get_settings
from app.core.db import get_platform_session, get_tenant_session
from app.modules.iam.keys.service import KeyService
from app.modules.iam.member_auth.schemas import (
    MemberLoginRequest,
    MemberOut,
    MemberPasswordResetConfirmBody,
    MemberPasswordResetRequestBody,
    MemberRefreshRequest,
    MemberTokenResponse,
)
from app.modules.iam.member_auth.service import MemberAuthService

router = APIRouter(prefix="/member/auth", tags=["member-auth"])
_bearer = HTTPBearer()


async def get_member_auth_service(
    request: Request,
    tenant_db: Annotated[AsyncSession, Depends(get_tenant_session)],
    platform_db: Annotated[AsyncSession, Depends(get_platform_session)],
) -> MemberAuthService:
    settings = get_settings()
    tenant_slug = request.headers.get(settings.tenant_header, "")
    redis = getattr(request.app.state, "redis", None)
    return MemberAuthService(
        db=tenant_db, key_service=KeyService(session=platform_db),
        redis=redis, tenant_slug=tenant_slug,
    )


MemberAuth = Annotated[MemberAuthService, Depends(get_member_auth_service)]


@router.post("/token", response_model=MemberTokenResponse)
async def member_login(body: MemberLoginRequest, request: Request, svc: MemberAuth) -> MemberTokenResponse:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return await svc.login(email=str(body.email), password=body.password, user_agent=user_agent, ip_address=ip_address)


@router.post("/refresh", response_model=MemberTokenResponse)
async def member_refresh(body: MemberRefreshRequest, svc: MemberAuth) -> MemberTokenResponse:
    return await svc.refresh(body.refresh_token)


@router.post("/logout", status_code=204)
async def member_logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)], svc: MemberAuth
) -> Response:
    await svc.logout(credentials.credentials)
    return Response(status_code=204)


@router.get("/me", response_model=MemberOut)
async def member_me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)], svc: MemberAuth
) -> MemberOut:
    member = await svc.me(credentials.credentials)
    return MemberOut.model_validate(member)


@router.post("/password-reset/request", status_code=204)
async def member_reset_request(body: MemberPasswordResetRequestBody, svc: MemberAuth) -> Response:
    await svc.reset_request(str(body.email))
    return Response(status_code=204)


@router.post("/password-reset/confirm", status_code=204)
async def member_reset_confirm(body: MemberPasswordResetConfirmBody, svc: MemberAuth) -> Response:
    await svc.reset_confirm(token=body.token, new_password=body.new_password)
    return Response(status_code=204)
```

- [ ] **Step 4: Add the operator enable endpoint + service delegation**

In `app/modules/members/service.py`, add a method on `MemberService` that constructs and delegates to `MemberAuthService` (service-interface call; no direct credential writes in the members service beyond the column the IAM service owns):

```python
    async def enable_portal_access(
        self, member_id: uuid.UUID, *, key_service: Any, redis: Any, tenant_slug: str
    ) -> tuple[str, int]:
        """Delegate to MemberAuthService to enable portal access + mint a token."""
        from app.modules.iam.member_auth.service import MemberAuthService

        auth_svc = MemberAuthService(
            db=self._session, key_service=key_service, redis=redis, tenant_slug=tenant_slug
        )
        return await auth_svc.enable_access(member_id)
```

(Match the actual attribute name the members service uses for its session — e.g. `self._session` or `self._db`; read the file first.)

In `app/modules/members/api.py`, add the operator route (gated `CurrentTenantUser`):

```python
from app.core.config import get_settings
from app.core.db import get_platform_session
from app.modules.iam.keys.service import KeyService
from app.modules.iam.member_auth.schemas import EnablePortalAccessOut


@router.post("/{member_id}/enable-portal-access", response_model=EnablePortalAccessOut)
async def enable_portal_access(
    member_id: uuid.UUID,
    request: Request,
    session: Session,
    user: CurrentTenantUser,
    platform_db: Annotated[AsyncSession, Depends(get_platform_session)],
) -> EnablePortalAccessOut:
    settings = get_settings()
    tenant_slug = request.headers.get(settings.tenant_header, "")
    redis = getattr(request.app.state, "redis", None)
    svc = MemberService(session)  # match existing construction in this file
    token, ttl = await svc.enable_portal_access(
        member_id, key_service=KeyService(session=platform_db), redis=redis, tenant_slug=tenant_slug
    )
    return EnablePortalAccessOut(
        member_id=member_id, portal_enabled=True, set_password_token=token, expires_in=ttl
    )
```

(Read `app/modules/members/api.py` first to match its existing imports, `Session`/`MemberService` construction, and `Request` import.)

- [ ] **Step 5: Wire the router in main.py**

In `app/main.py`, add the import near the other iam imports:

```python
from app.modules.iam.member_auth.api import router as member_auth_router
```

And include it near `tenant_auth_router`:

```python
app.include_router(member_auth_router)
```

- [ ] **Step 6: Run test + ruff + mypy + members regression**

Run:
```bash
DATABASE_URL=... pytest tests/modules/iam/member_auth/test_api.py tests/modules/members/ -v
ruff check app/modules/iam/member_auth/api.py app/modules/members/api.py app/modules/members/service.py app/main.py
mypy app/modules/iam/member_auth/api.py app/modules/members/api.py app/modules/members/service.py
```
Expected: PASS + clean.

- [ ] **Step 7: Commit**

```bash
git add app/modules/iam/member_auth/api.py app/modules/members/api.py app/modules/members/service.py app/main.py tests/modules/iam/member_auth/test_api.py
git commit -m "feat(iam): /member/auth router + operator enable-portal-access endpoint"
```

---

### Task 9: GET /member/me + GET /member/savings (+transactions)

**Files:**
- Modify: `app/modules/members/api.py`
- Modify: `app/modules/savings/api.py`
- Test: `tests/modules/members/test_member_self_api.py`
- Test: `tests/modules/savings/test_member_api.py`

**Interfaces:**
- Consumes: `CurrentMember` (Task 7), existing `MemberOut`, savings `list_accounts(member_id=...)`, `get_account`, `list_transactions`.
- Produces: `GET /member/me` → `MemberOut`; `GET /member/savings` → `list[SavingsAccountOut]` (own only); `GET /member/savings/{account_id}/transactions` → own txns, 404 if the account is not the member's.

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/members/test_member_self_api.py
def test_member_me_returns_own_profile(client, seeded_member_id, member_headers) -> None:
    resp = client.get("/member/me", headers=member_headers(seeded_member_id))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(seeded_member_id)
```

```python
# tests/modules/savings/test_member_api.py
def test_member_savings_lists_only_own(client, member_with_account, member_headers) -> None:
    member_id, account_id = member_with_account
    resp = client.get("/member/savings", headers=member_headers(member_id))
    assert resp.status_code == 200
    ids = [a["id"] for a in resp.json()]
    assert str(account_id) in ids


def test_member_cannot_read_other_members_account_txns(
    client, member_with_account, other_member_account, member_headers
) -> None:
    member_id, _ = member_with_account
    other_account_id = other_member_account
    resp = client.get(
        f"/member/savings/{other_account_id}/transactions", headers=member_headers(member_id)
    )
    assert resp.status_code == 404
```

Add a `member_headers` fixture: in stub mode it returns `{**tenant_headers, "X-Member-Actor-ID": str(member_id)}`. Add `member_with_account` / `other_member_account` fixtures seeding members (with `portal_enabled=True, status='active'`) + savings accounts.

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL=... pytest tests/modules/members/test_member_self_api.py tests/modules/savings/test_member_api.py -v`
Expected: FAIL — routes 404.

- [ ] **Step 3: Add GET /member/me**

In `app/modules/members/api.py`:

```python
from fastapi import APIRouter

from app.modules.iam.dependencies import CurrentMember
from app.modules.iam.member_auth.schemas import MemberOut  # the single MemberOut from Task 4

# The existing members router has prefix="/members"; the self path is "/member/me",
# so add a dedicated prefix-distinct router in this file and wire it in main.py.
member_router = APIRouter(prefix="/member", tags=["member-self"])


@member_router.get("/me", response_model=MemberOut)
async def member_self(member: CurrentMember) -> MemberOut:
    return MemberOut.model_validate(member)
```

Use the **same `MemberOut`** defined in Task 4 (`app.modules.iam.member_auth.schemas`) for both `/member/auth/me` and `/member/me` — one schema, one shape. Do not create a second member-out type.

- [ ] **Step 4: Add the savings member routes**

In `app/modules/savings/api.py`:

```python
from app.modules.iam.dependencies import CurrentMember

member_router = APIRouter(prefix="/member/savings", tags=["member-savings"])


@member_router.get("", response_model=list[SavingsAccountOut])
async def member_savings(session: Session, member: CurrentMember) -> list[SavingsAccountOut]:
    svc = SavingsService(session)  # match existing construction
    accounts = await svc.list_accounts(member_id=member.id)
    return [SavingsAccountOut.model_validate(a) for a in accounts]


@member_router.get("/{account_id}/transactions", response_model=list[SavingsTransactionOut])
async def member_savings_txns(
    account_id: uuid.UUID, session: Session, member: CurrentMember
) -> list[SavingsTransactionOut]:
    svc = SavingsService(session)
    account = await svc.get_account(account_id)
    if account is None or account.member_id != member.id:
        raise HTTPException(status_code=404, detail="Savings account not found")
    txns = await svc.list_transactions(account_id)
    return [SavingsTransactionOut.model_validate(t) for t in txns]
```

(Read `app/modules/savings/api.py` first to match `Session`, `SavingsService` construction, `get_account`/`list_transactions` signatures, and `HTTPException` import. Register `member_router` in `app/main.py` alongside `savings_router`.)

- [ ] **Step 5: Wire the new routers in main.py**

```python
from app.modules.members.api import member_router as members_self_router
from app.modules.savings.api import member_router as savings_member_router
...
app.include_router(members_self_router)
app.include_router(savings_member_router)
```

- [ ] **Step 6: Run tests + ruff + mypy + regression**

Run:
```bash
DATABASE_URL=... pytest tests/modules/members/ tests/modules/savings/ -v
ruff check app/modules/members/api.py app/modules/savings/api.py app/main.py
mypy app/modules/members/api.py app/modules/savings/api.py
```
Expected: PASS + clean.

- [ ] **Step 7: Commit**

```bash
git add app/modules/members/api.py app/modules/savings/api.py app/main.py \
  tests/modules/members/test_member_self_api.py tests/modules/savings/test_member_api.py
git commit -m "feat: GET /member/me + /member/savings read endpoints"
```

---

### Task 10: GET /member/shares + /member/loans (+detail/schedule/statement)

**Files:**
- Modify: `app/modules/shares/api.py`
- Modify: `app/modules/credit/api.py`
- Modify: `app/main.py`
- Test: `tests/modules/shares/test_member_api.py`
- Test: `tests/modules/credit/test_member_api.py`

**Interfaces:**
- Consumes: `CurrentMember`, shares `list_accounts(member_id=...)`, credit loan/schedule/statement services.
- Produces: `GET /member/shares`; `GET /member/loans`; `GET /member/loans/{loan_id}` (404 if not own); `GET /member/loans/{loan_id}/schedule`; `GET /member/loans/{loan_id}/statement`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/shares/test_member_api.py
def test_member_shares_lists_only_own(client, member_with_share_account, member_headers) -> None:
    member_id, account_id = member_with_share_account
    resp = client.get("/member/shares", headers=member_headers(member_id))
    assert resp.status_code == 200
    assert any(a["id"] == str(account_id) for a in resp.json())
```

```python
# tests/modules/credit/test_member_api.py
def test_member_loans_lists_only_own(client, member_with_loan, member_headers) -> None:
    member_id, loan_id = member_with_loan
    resp = client.get("/member/loans", headers=member_headers(member_id))
    assert resp.status_code == 200
    assert any(loan["id"] == str(loan_id) for loan in resp.json())


def test_member_cannot_read_other_members_loan(
    client, member_with_loan, other_member_loan, member_headers
) -> None:
    member_id, _ = member_with_loan
    resp = client.get(f"/member/loans/{other_member_loan}", headers=member_headers(member_id))
    assert resp.status_code == 404
```

Add fixtures seeding share accounts / loans for two distinct members.

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL=... pytest tests/modules/shares/test_member_api.py tests/modules/credit/test_member_api.py -v`
Expected: FAIL — routes 404.

- [ ] **Step 3: Add the shares member route**

In `app/modules/shares/api.py`:

```python
from app.modules.iam.dependencies import CurrentMember

member_router = APIRouter(prefix="/member/shares", tags=["member-shares"])


@member_router.get("", response_model=list[ShareAccountListItemOut])
async def member_shares(session: Session, member: CurrentMember) -> list[ShareAccountListItemOut]:
    svc = SharesService(session)  # match existing construction
    accounts = await svc.list_accounts(member_id=member.id)
    return [ShareAccountListItemOut.model_validate(a) for a in accounts]
```

(Read `app/modules/shares/api.py` to match the exact list-account response model and service. Use whatever the operator `GET /shares/accounts?member_id=` returns — `ShareAccountListItemOut`.)

- [ ] **Step 4: Add the credit member routes**

In `app/modules/credit/api.py`:

```python
from sqlalchemy import select
from app.modules.iam.dependencies import CurrentMember
from app.modules.credit.models import Loan

member_router = APIRouter(prefix="/member/loans", tags=["member-loans"])


async def _member_loan_or_404(session, loan_id: uuid.UUID, member_id: uuid.UUID) -> Loan:
    loan = await session.get(Loan, loan_id)
    if loan is None or loan.member_id != member_id:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


@member_router.get("", response_model=list[LoanOut])
async def member_loans(session: Session, member: CurrentMember) -> list[LoanOut]:
    result = await session.execute(select(Loan).where(Loan.member_id == member.id))
    loans = result.scalars().all()
    return [LoanOut.model_validate(loan) for loan in loans]


@member_router.get("/{loan_id}", response_model=LoanOut)
async def member_loan_detail(loan_id: uuid.UUID, session: Session, member: CurrentMember) -> LoanOut:
    loan = await _member_loan_or_404(session, loan_id, member.id)
    return LoanOut.model_validate(loan)


@member_router.get("/{loan_id}/schedule", response_model=list[LoanInstallmentOut])
async def member_loan_schedule(
    loan_id: uuid.UUID, session: Session, member: CurrentMember
) -> list[LoanInstallmentOut]:
    await _member_loan_or_404(session, loan_id, member.id)
    svc = CreditService(session)  # match existing construction used by /credit/loans/{id}/schedule
    schedule = await svc.list_schedule(loan_id)  # match the actual method name
    return [LoanInstallmentOut.model_validate(i) for i in schedule]


@member_router.get("/{loan_id}/statement", response_model=LoanStatementOut)
async def member_loan_statement(
    loan_id: uuid.UUID, session: Session, member: CurrentMember
) -> LoanStatementOut:
    await _member_loan_or_404(session, loan_id, member.id)
    svc = CreditService(session)
    return await svc.build_statement(loan_id)  # match the actual method used by /credit/loans/{id}/statement
```

(Read `app/modules/credit/api.py` to match the schedule/statement service method names and response models exactly — reuse the same ones the operator routes use. `Loan.member_id` exists.)

- [ ] **Step 5: Wire routers in main.py**

```python
from app.modules.shares.api import member_router as shares_member_router
from app.modules.credit.api import member_router as credit_member_router
...
app.include_router(shares_member_router)
app.include_router(credit_member_router)
```

- [ ] **Step 6: Run tests + ruff + mypy + regression**

Run:
```bash
DATABASE_URL=... pytest tests/modules/shares/ tests/modules/credit/ -v
ruff check app/modules/shares/api.py app/modules/credit/api.py app/main.py
mypy app/modules/shares/api.py app/modules/credit/api.py
```
Expected: PASS + clean.

- [ ] **Step 7: Commit**

```bash
git add app/modules/shares/api.py app/modules/credit/api.py app/main.py \
  tests/modules/shares/test_member_api.py tests/modules/credit/test_member_api.py
git commit -m "feat: GET /member/shares + /member/loans read endpoints"
```

---

### Task 11: GET /member/fees + cross-cutting integration tests

**Files:**
- Modify: `app/modules/fees/api.py`
- Modify: `app/main.py`
- Test: `tests/modules/fees/test_member_api.py`
- Test: `tests/modules/iam/member_auth/test_integration.py`

**Interfaces:**
- Consumes: `CurrentMember`, fees `list_assessments(target_type="member", target_id=...)`.
- Produces: `GET /member/fees` → own fee assessments. Plus integration coverage of audience isolation + subscription gating.

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/fees/test_member_api.py
def test_member_fees_lists_only_own(client, member_with_fee, member_headers) -> None:
    member_id, assessment_id = member_with_fee
    resp = client.get("/member/fees", headers=member_headers(member_id))
    assert resp.status_code == 200
    assert any(f["id"] == str(assessment_id) for f in resp.json())
```

```python
# tests/modules/iam/member_auth/test_integration.py
# Audience isolation: a member stub header must NOT authorise an operator route,
# and a tenant actor header must NOT authorise a /member/* route.

def test_operator_route_rejects_member_only_header(client, seeded_member_id, tenant_slug_header) -> None:
    # No X-Tenant-Actor-ID, only X-Member-Actor-ID -> operator route 401/403.
    headers = {**tenant_slug_header, "X-Member-Actor-ID": str(seeded_member_id)}
    resp = client.get("/savings/accounts", headers=headers)
    assert resp.status_code in (401, 403)


def test_member_route_rejects_tenant_actor_header(client, seeded_tenant_user_id, tenant_slug_header) -> None:
    # No X-Member-Actor-ID, only X-Tenant-Actor-ID -> /member route 401/403/400.
    headers = {**tenant_slug_header, "X-Tenant-Actor-ID": str(seeded_tenant_user_id)}
    resp = client.get("/member/savings", headers=headers)
    assert resp.status_code in (400, 401, 403)
```

(In stub mode the isolation is enforced by which header each dependency reads — `CurrentMember` reads `X-Member-Actor-ID`, `CurrentTenantUser` reads `X-Tenant-Actor-ID`. In JWT mode it is enforced by the `aud` mismatch. A subscription-gate test belongs here too if the test harness can seed a `past_due` tenant; otherwise document it as covered by the billing gate tests.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL=... pytest tests/modules/fees/test_member_api.py tests/modules/iam/member_auth/test_integration.py -v`
Expected: FAIL — `/member/fees` 404 (and isolation tests fail if a route is mis-gated).

- [ ] **Step 3: Add the fees member route**

In `app/modules/fees/api.py`:

```python
from app.modules.iam.dependencies import CurrentMember

member_router = APIRouter(prefix="/member/fees", tags=["member-fees"])


@member_router.get("", response_model=list[FeeAssessmentOut])
async def member_fees(session: Session, member: CurrentMember) -> list[FeeAssessmentOut]:
    svc = FeeAssessmentService(session)  # match existing construction
    assessments = await svc.list_assessments(target_type="member", target_id=member.id)
    return [FeeAssessmentOut.model_validate(a) for a in assessments]
```

(Read `app/modules/fees/api.py` to match the service construction, `list_assessments` signature — it takes `target_type` and `target_id` — and the `FeeAssessmentOut` model.)

- [ ] **Step 4: Wire the router in main.py**

```python
from app.modules.fees.api import member_router as fees_member_router
...
app.include_router(fees_member_router)
```

- [ ] **Step 5: Run tests + ruff + mypy**

Run:
```bash
DATABASE_URL=... pytest tests/modules/fees/ tests/modules/iam/member_auth/ -v
ruff check app/modules/fees/api.py app/main.py && mypy app/modules/fees/api.py
```
Expected: PASS + clean.

- [ ] **Step 6: Full suite + lint gate**

Run:
```bash
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test pytest -q
ruff check app/ tests/ && mypy app/
```
Expected: full green; ruff + mypy clean.

- [ ] **Step 7: Commit**

```bash
git add app/modules/fees/api.py app/main.py \
  tests/modules/fees/test_member_api.py tests/modules/iam/member_auth/test_integration.py
git commit -m "feat: GET /member/fees + member auth isolation integration tests"
```

---

## Final wrap-up (after Task 11)

- [ ] Update `CLAUDE.md`: add a "Member auth (Phase 4a) contracts" subsection summarising the audience namespace (`member:<slug>`), the `members` credential columns, `member_sessions`, the gated read endpoints, and that members are read-only in v1.
- [ ] Update memory `project_phase_3_sacco_portal.md` (or a new `project_phase_4_members.md`) with the 4a outcome and that 4b (member portal UI) is now unblocked.
- [ ] Open the PR from `feat/member-auth/4a` → `main`.

## Self-review notes (spec coverage)

- Credential columns on `members` → Task 2. ✓
- Operator-issued set-password token (24h, reuse reset_tokens) → Task 5 (`OPERATOR_SET_PASSWORD_TTL=86400`) + Task 8 endpoint. ✓
- Auth flows (login/refresh/logout/me/reset) → Tasks 5–6, exposed Task 8. ✓
- `aud="member:<slug>"`, signing key reuses `"tenant"` → Task 6 (`_audience`, `_KEY_AUDIENCE`). ✓
- `member_sessions` + SessionService generalization → Tasks 2–3. ✓
- `CurrentMember` + `MEMBER_AUTH_MODE` switch → Task 7. ✓
- Subscription gating via `get_tenant_session` → every `/member/*` route depends on it through the session dep (Tasks 9–11). ✓
- Read endpoints (me/savings/shares/loans/fees) with ownership 404 → Tasks 9–11. ✓
- Anti-enumeration (generic 401 login, 204 reset request) → Tasks 6, 8. ✓
- Audience isolation + ownership 404 tests → Tasks 9–11 + Task 11 integration. ✓
- `actor_type="member"` audit → Task 4. ✓
- No member mutations / out-of-scope items → not implemented (correct). ✓
