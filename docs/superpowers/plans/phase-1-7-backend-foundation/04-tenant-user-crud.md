# Phase 1.7 Sub-Plan 04: Tenant-User CRUD + Admin-Initiated Password Reset

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/phase-1-7/04-tenant-user-crud` from `main` before starting.

**Goal:** Give platform admins HTTP endpoints to manage tenant users in any tenant: list / create / read / update / admin-initiated password reset. The reset token is returned in the response body — the portal renders it in a one-time modal until Phase 3 (Notifications) ships email delivery.

**Architecture:** New module `app/platform_/tenant_users_admin/` follows the project conventions (`api.py`, `service.py`, `schemas.py`). The endpoints live in **platform context** but operate on the **tenant schema** — a new cross-schema FastAPI dependency `get_session_for_tenant_schema(tenant_id)` in `app/core/db.py` loads the tenant by UUID, validates the `schema_name`, and yields a session with `SET LOCAL search_path TO <schema>, platform`. Token generation reuses the existing `app/modules/iam/reset_tokens.py` HMAC pipeline. List endpoints filter `impersonation_id IS NULL` so shadow tenant_users from P1.7-02b never leak into operator UI.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2, existing HMAC reset-token helpers.

**Roadmap reference:** `docs/superpowers/plans/phase-1-7-backend-foundation/00-index.md` §P1.7-04.

**Prerequisite:**
- **P1.7-02a must be merged** (the `impersonation_id` column on `tenant_users` is what the list-filter `WHERE impersonation_id IS NULL` references).
- **P1.7-05 is a soft dependency.** Until 05 ships 4-tier roles, the endpoints gate on `CurrentSuperuser`. After 05 merges, the dep swaps to `Annotated[..., Depends(get_current_platform_user_with_role("admin"))]` in one place; the call sites stay frozen.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/core/db.py` | Modify | Add `get_session_for_tenant_schema(tenant_id)` dep |
| `app/platform_/tenant_users_admin/__init__.py` | Create | Package marker |
| `app/platform_/tenant_users_admin/schemas.py` | Create | `TenantUserCreateIn`, `TenantUserPatchIn`, `TenantUserOut`, `TenantUserCreateOut`, `PasswordResetOut` |
| `app/platform_/tenant_users_admin/service.py` | Create | `TenantUsersAdminService`: list/get/create/update/initiate_password_reset |
| `app/platform_/tenant_users_admin/api.py` | Create | Five endpoints under `/platform/tenants/{tenant_id}/users` |
| `app/main.py` | Modify | Mount the new router |
| `tests/platform_/tenant_users_admin/__init__.py` | Create | Package marker |
| `tests/platform_/tenant_users_admin/test_api.py` | Create | Integration tests for the five endpoints |
| `tests/platform_/tenant_users_admin/test_cross_schema_dep.py` | Create | Unit test for the new dep |
| `CLAUDE.md` | Modify | Append the tenant-user CRUD subsection under `## IAM module contracts (do not violate)` |

---

## Task 1: Cross-schema dependency

**Files:**
- Modify: `app/core/db.py`
- Create: `tests/platform_/tenant_users_admin/__init__.py`
- Create: `tests/platform_/tenant_users_admin/test_cross_schema_dep.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/platform_/tenant_users_admin/__init__.py
```
(empty file)

```python
# tests/platform_/tenant_users_admin/test_cross_schema_dep.py
"""get_session_for_tenant_schema looks up the tenant by UUID, validates the
schema_name, and yields a session with search_path set. NOT subscription-gated
— platform admins must be able to manage users in any tenant state.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.db import get_session_for_tenant_schema
from app.platform_.models import Tenant


async def _seed_tenant(
    factory: async_sessionmaker, schema: str, *, is_active: bool = True,
) -> Tenant:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=schema,
            name="T",
            is_active=is_active,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(t)
    return t


async def _cleanup(factory: async_sessionmaker) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.tenants"))


async def test_yields_session_with_search_path_set(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    tenant = await _seed_tenant(factory, "tenant_test")
    try:
        gen = get_session_for_tenant_schema(tenant.id)
        session = await gen.__anext__()
        try:
            row = await session.execute(text("SHOW search_path"))
            sp = row.scalar()
            assert "tenant_test" in str(sp)
        finally:
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
    finally:
        await _cleanup(factory)


async def test_404_when_tenant_unknown(test_engine: AsyncEngine) -> None:
    gen = get_session_for_tenant_schema(uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        await gen.__anext__()
    assert exc.value.status_code == 404


async def test_404_when_tenant_inactive(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    tenant = await _seed_tenant(factory, "tenant_test", is_active=False)
    try:
        gen = get_session_for_tenant_schema(tenant.id)
        with pytest.raises(HTTPException) as exc:
            await gen.__anext__()
        assert exc.value.status_code == 404
    finally:
        await _cleanup(factory)


async def test_500_when_schema_name_malformed(test_engine: AsyncEngine) -> None:
    """Defense in depth: even if the DB returns a malformed schema_name
    (data corruption), the dep refuses to SET search_path.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    # Bypass the model's validation by inserting directly via SQL.
    bad_id = uuid.uuid4()
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(
            text(
                "INSERT INTO platform.tenants "
                "(id, slug, schema_name, name, is_active, created_at, updated_at) "
                "VALUES (:id, :slug, 'evil; DROP SCHEMA tenant_test CASCADE; --', "
                "'evil', true, now(), now())"
            ),
            {"id": bad_id, "slug": f"evil-{bad_id.hex[:6]}"},
        )
    try:
        gen = get_session_for_tenant_schema(bad_id)
        with pytest.raises(HTTPException) as exc:
            await gen.__anext__()
        assert exc.value.status_code == 500
    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Run — expected to fail (`ImportError`)**

```bash
make test-fast T=tests/platform_/tenant_users_admin/test_cross_schema_dep.py
```
Expected: `ImportError: cannot import name 'get_session_for_tenant_schema'`.

- [ ] **Step 3: Add the dep to `app/core/db.py`**

Open `app/core/db.py`. Add this function after `get_platform_session` (around line 188):

```python
async def get_session_for_tenant_schema(
    tenant_id: uuid.UUID,
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for **platform** endpoints that operate on a
    **tenant** schema.

    Takes `tenant_id` from the URL path (FastAPI injects path params into
    deps automatically), loads the tenant by UUID, validates the
    schema_name, and yields a session with
    ``SET LOCAL search_path TO <schema>, platform``.

    NOT subscription-gated — platform admins must be able to manage tenant
    users regardless of the tenant's subscription state.

    Raises:
        HTTPException(404): tenant unknown or inactive
        HTTPException(500): schema_name fails defensive validation
            (indicates data corruption)
    """
    # Look up the tenant on a separate, schema-agnostic connection. The
    # `id` column has a proper index, so this is a fast single-row lookup.
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT schema_name FROM platform.tenants "
                    "WHERE id = :id AND is_active = true"
                ),
                {"id": tenant_id},
            )
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant {tenant_id} not found or inactive",
        )

    schema_name: str = row[0]
    if not _SCHEMA_RE.match(schema_name):
        _log.error(
            "Resolved schema_name failed validation — possible data corruption",
            tenant_id=str(tenant_id),
            schema_name=schema_name,
        )
        raise HTTPException(status_code=500, detail="Internal configuration error")

    # schema_name validated; safe to interpolate.
    async with AsyncSessionFactory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

Add the `uuid` import at the top if not present:

```python
import uuid  # noqa: TC003 — used at runtime by FastAPI path-param injection
```

- [ ] **Step 4: Run the tests — they should pass**

```bash
make test-fast T=tests/platform_/tenant_users_admin/test_cross_schema_dep.py
```
Expected: 4 tests pass.

Also re-run existing core/db tests:

```bash
make test-fast T=tests/core/
```
Expected: no regressions.

- [ ] **Step 5: Commit**

```bash
git add app/core/db.py \
        tests/platform_/tenant_users_admin/__init__.py \
        tests/platform_/tenant_users_admin/test_cross_schema_dep.py
git commit -m "feat(core): get_session_for_tenant_schema cross-schema dep"
```

---

## Task 2: Schemas

**Files:**
- Create: `app/platform_/tenant_users_admin/__init__.py`
- Create: `app/platform_/tenant_users_admin/schemas.py`

- [ ] **Step 1: Create the package marker**

```python
# app/platform_/tenant_users_admin/__init__.py
```
(empty file)

- [ ] **Step 2: Write the schemas**

```python
# app/platform_/tenant_users_admin/schemas.py
"""Pydantic schemas for /platform/tenants/{tenant_id}/users."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class TenantUserCreateIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    is_admin: bool = False


class TenantUserPatchIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    is_admin: bool | None = None


class TenantUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Always None on this endpoint — shadow users are filtered out in the list
    # path and looked up explicitly in the detail path (where a 404 is the
    # response if the target user is a shadow).
    impersonation_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class TenantUserCreateOut(BaseModel):
    user: TenantUserOut
    password_reset_token: str  # one-time; deliver out of band until Phase 3
    password_reset_expires_in: int  # seconds


class PasswordResetOut(BaseModel):
    user_id: uuid.UUID
    password_reset_token: str
    password_reset_expires_in: int
```

- [ ] **Step 3: Commit**

```bash
git add app/platform_/tenant_users_admin/__init__.py \
        app/platform_/tenant_users_admin/schemas.py
git commit -m "feat(tenant-users-admin): Pydantic schemas"
```

---

## Task 3: Service implementation

**Files:**
- Create: `app/platform_/tenant_users_admin/service.py`

- [ ] **Step 1: Write the service**

```python
# app/platform_/tenant_users_admin/service.py
"""Platform-admin operations on a tenant's tenant_users table.

The service runs in a TENANT-schema-scoped session (yielded by the new
get_session_for_tenant_schema dep). Audit log writes are automatic via
AuditableMixin on TenantUser; the structlog contextvars carry the
platform actor identity so audit rows show actor_type='platform_user'.

The admin-initiated reset token has a longer TTL than the self-service
flow (24h vs 15min) — this gives the operator time to deliver the token
out of band (phone call, secure messenger) until Phase 3 ships email.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.modules.iam.reset_tokens import make_reset_token
from app.modules.iam.tenant_users.models import TenantUser

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# 24h reset TTL for admin-initiated resets (vs 15min for self-service).
_ADMIN_RESET_TTL_SECONDS = 24 * 60 * 60


class TenantUserConflict(Exception):
    """Raised when a tenant_user with the requested email already exists."""


class TenantUsersAdminService:
    def __init__(
        self,
        session: AsyncSession,
        redis: Any | None = None,
    ) -> None:
        self._db = session
        self._redis = redis

    async def list_users(
        self, *, include_shadows: bool = False
    ) -> list[TenantUser]:
        """List tenant users in the current tenant schema.

        By default filters out shadow users (impersonation_id IS NOT NULL)
        because they exist solely for cross-context impersonation and would
        confuse operators. The portal NEVER includes them.
        """
        q = select(TenantUser).order_by(TenantUser.email)
        if not include_shadows:
            q = q.where(TenantUser.impersonation_id.is_(None))
        return list((await self._db.execute(q)).scalars().all())

    async def get_user(self, user_id: uuid.UUID) -> TenantUser | None:
        """Fetch a real (non-shadow) tenant user by id. Returns None for
        shadow users so the portal cannot accidentally surface them.
        """
        row = await self._db.scalar(
            select(TenantUser).where(
                TenantUser.id == user_id,
                TenantUser.impersonation_id.is_(None),
            )
        )
        return row

    async def create_user(
        self,
        *,
        email: str,
        full_name: str,
        is_admin: bool,
    ) -> tuple[TenantUser, str]:
        """Create a new tenant_user and return (user, password_reset_token).

        The token is a single-use HMAC with a 24h TTL stored in Redis. The
        caller delivers it out of band until Phase 3 ships email.

        Raises:
            TenantUserConflict: a tenant_user with this email already exists.
        """
        settings = get_settings()
        now = datetime.now(UTC)
        user = TenantUser(
            email=email,
            full_name=full_name,
            is_active=True,
            is_admin=is_admin,
            hashed_password=None,
            created_at=now,
            updated_at=now,
        )
        self._db.add(user)
        try:
            await self._db.flush()
        except IntegrityError as exc:
            await self._db.rollback()
            raise TenantUserConflict(
                f"A tenant user with email {email!r} already exists"
            ) from exc

        token, jti = make_reset_token(
            user_id=str(user.id),
            secret=settings.app_secret_key,
            ttl=_ADMIN_RESET_TTL_SECONDS,
        )
        if self._redis is not None:
            await self._redis.set(
                f"iam:pwreset:{jti}", "1", ex=_ADMIN_RESET_TTL_SECONDS
            )
        return user, token

    async def update_user(
        self,
        *,
        user_id: uuid.UUID,
        full_name: str | None = None,
        is_active: bool | None = None,
        is_admin: bool | None = None,
    ) -> TenantUser:
        """Patch a tenant_user. Only the named fields may change.

        Cannot patch shadow users (raises ValueError) — they're managed by
        the impersonation flow.
        """
        user = await self.get_user(user_id)
        if user is None:
            raise ValueError(f"Tenant user {user_id} not found")
        changed = False
        if full_name is not None and user.full_name != full_name:
            user.full_name = full_name
            changed = True
        if is_active is not None and user.is_active != is_active:
            user.is_active = is_active
            changed = True
        if is_admin is not None and user.is_admin != is_admin:
            user.is_admin = is_admin
            changed = True
        if changed:
            user.updated_at = datetime.now(UTC)
        return user

    async def initiate_password_reset(
        self, *, user_id: uuid.UUID
    ) -> tuple[TenantUser, str]:
        """Generate a one-time admin reset token for a tenant_user.

        Returns (user, token). The token has a 24h TTL (longer than the
        self-service flow). JTI stored in Redis.
        """
        settings = get_settings()
        user = await self.get_user(user_id)
        if user is None:
            raise ValueError(f"Tenant user {user_id} not found")
        token, jti = make_reset_token(
            user_id=str(user.id),
            secret=settings.app_secret_key,
            ttl=_ADMIN_RESET_TTL_SECONDS,
        )
        if self._redis is not None:
            await self._redis.set(
                f"iam:pwreset:{jti}", "1", ex=_ADMIN_RESET_TTL_SECONDS
            )
        return user, token

    @staticmethod
    def admin_reset_ttl_seconds() -> int:
        """Exposed so the API layer can include it in the response shape."""
        return _ADMIN_RESET_TTL_SECONDS
```

- [ ] **Step 2: Commit**

```bash
git add app/platform_/tenant_users_admin/service.py
git commit -m "feat(tenant-users-admin): TenantUsersAdminService"
```

---

## Task 4: API router + failing tests

**Files:**
- Create: `tests/platform_/tenant_users_admin/test_api.py`
- Create: `app/platform_/tenant_users_admin/api.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing API tests**

```python
# tests/platform_/tenant_users_admin/test_api.py
"""Integration tests for /platform/tenants/{tenant_id}/users.

Uses stub auth + dependency overrides to bind the test schema as the
tenant schema. The shadow-user filter is exercised by seeding a shadow
and verifying it does not appear in list / detail.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session, get_session_for_tenant_schema
from app.main import app, lifespan
from app.modules.iam.reset_tokens import verify_reset_token
from app.modules.iam.tenant_users.models import TenantUser
from app.platform_.models import PlatformUser, Tenant


def _make_platform_session_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


def _make_tenant_schema_override(engine: AsyncEngine, schema: str):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override(
        tenant_id: uuid.UUID,
    ) -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {schema}, platform")
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


async def _create_superuser(
    factory: async_sessionmaker[AsyncSession],
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"super-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Super",
            is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _create_tenant_record(
    factory: async_sessionmaker[AsyncSession], schema: str,
) -> Tenant:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=schema,
            name="T",
            is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(t)
    return t


async def _seed_existing_user(
    factory: async_sessionmaker[AsyncSession],
    schema: str,
    *,
    email_suffix: str = "",
    impersonation_id: uuid.UUID | None = None,
) -> TenantUser:
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {schema}, platform"))
        u = TenantUser(
            email=f"u{email_suffix}-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Existing",
            is_active=True, is_admin=False,
            impersonation_id=impersonation_id,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        await s.execute(text("DELETE FROM tenant_users"))
        await s.execute(text("DELETE FROM audit_log"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_platform_session] = (
        _make_platform_session_override(test_engine)
    )
    app.dependency_overrides[get_session_for_tenant_schema] = (
        _make_tenant_schema_override(test_engine, "tenant_test")
    )
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)
    app.dependency_overrides.pop(get_session_for_tenant_schema, None)


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


# ── list ─────────────────────────────────────────────────────────────────────


async def test_list_returns_real_users_only(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    await _seed_existing_user(factory, "tenant_test")
    await _seed_existing_user(
        factory, "tenant_test", email_suffix="-imp",
        impersonation_id=uuid.uuid4(),
    )
    try:
        r = await client.get(
            f"/platform/tenants/{tenant.id}/users",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        users = r.json()
        # Only the non-shadow user appears
        assert len(users) == 1
        assert users[0]["impersonation_id"] is None
    finally:
        await _cleanup(factory)


# ── create ───────────────────────────────────────────────────────────────────


async def test_create_returns_user_and_reset_token(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/users",
            json={
                "email": f"new-{uuid.uuid4().hex[:6]}@test.example",
                "full_name": "New User",
                "is_admin": False,
            },
            headers=_hdr(actor.id),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["user"]["is_active"] is True
        assert body["user"]["is_admin"] is False
        token = body["password_reset_token"]
        assert token
        # Verify the token is a valid HMAC reset token
        from app.core.config import get_settings

        payload = verify_reset_token(token, get_settings().app_secret_key)
        assert payload["sub"] == body["user"]["id"]
        # TTL is 24h
        assert body["password_reset_expires_in"] == 86400
    finally:
        await _cleanup(factory)


async def test_create_rejects_duplicate_email(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    existing = await _seed_existing_user(factory, "tenant_test")
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/users",
            json={
                "email": existing.email,
                "full_name": "Dup",
                "is_admin": False,
            },
            headers=_hdr(actor.id),
        )
        assert r.status_code == 409, r.text
    finally:
        await _cleanup(factory)


# ── get ──────────────────────────────────────────────────────────────────────


async def test_get_returns_real_user(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    user = await _seed_existing_user(factory, "tenant_test")
    try:
        r = await client.get(
            f"/platform/tenants/{tenant.id}/users/{user.id}",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        assert r.json()["id"] == str(user.id)
    finally:
        await _cleanup(factory)


async def test_get_404_for_shadow_user(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    shadow = await _seed_existing_user(
        factory, "tenant_test", impersonation_id=uuid.uuid4(),
    )
    try:
        r = await client.get(
            f"/platform/tenants/{tenant.id}/users/{shadow.id}",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 404, r.text
    finally:
        await _cleanup(factory)


# ── patch ────────────────────────────────────────────────────────────────────


async def test_patch_updates_fields(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    user = await _seed_existing_user(factory, "tenant_test")
    try:
        r = await client.patch(
            f"/platform/tenants/{tenant.id}/users/{user.id}",
            json={"is_active": False, "is_admin": True, "full_name": "Updated"},
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_active"] is False
        assert body["is_admin"] is True
        assert body["full_name"] == "Updated"
    finally:
        await _cleanup(factory)


async def test_patch_404_for_shadow(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    shadow = await _seed_existing_user(
        factory, "tenant_test", impersonation_id=uuid.uuid4(),
    )
    try:
        r = await client.patch(
            f"/platform/tenants/{tenant.id}/users/{shadow.id}",
            json={"is_active": False},
            headers=_hdr(actor.id),
        )
        assert r.status_code == 404, r.text
    finally:
        await _cleanup(factory)


# ── password-reset ───────────────────────────────────────────────────────────


async def test_password_reset_returns_token(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    user = await _seed_existing_user(factory, "tenant_test")
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/users/{user.id}/password-reset",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user_id"] == str(user.id)
        token = body["password_reset_token"]
        from app.core.config import get_settings

        payload = verify_reset_token(token, get_settings().app_secret_key)
        assert payload["sub"] == str(user.id)
    finally:
        await _cleanup(factory)


async def test_password_reset_404_for_shadow(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    shadow = await _seed_existing_user(
        factory, "tenant_test", impersonation_id=uuid.uuid4(),
    )
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/users/{shadow.id}/password-reset",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 404, r.text
    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Write the router**

```python
# app/platform_/tenant_users_admin/api.py
"""FastAPI router for /platform/tenants/{tenant_id}/users.

Platform-context endpoints that operate on the tenant schema via the
get_session_for_tenant_schema dep.

Role gate: CurrentSuperuser until P1.7-05 ships 4-tier roles, at which
point swap to:
    Annotated[..., Depends(get_current_platform_user_with_role("admin"))]
All call sites stay frozen.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_for_tenant_schema
from app.platform_.auth import CurrentSuperuser
from app.platform_.tenant_users_admin.schemas import (
    PasswordResetOut,
    TenantUserCreateIn,
    TenantUserCreateOut,
    TenantUserOut,
    TenantUserPatchIn,
)
from app.platform_.tenant_users_admin.service import (
    TenantUserConflict,
    TenantUsersAdminService,
)

router = APIRouter(
    prefix="/platform/tenants/{tenant_id}/users",
    tags=["platform-tenant-users"],
)

# Path-injected cross-schema session.
TenantSchemaSession = Annotated[
    AsyncSession, Depends(get_session_for_tenant_schema)
]


@router.get("", response_model=list[TenantUserOut])
async def list_tenant_users(
    tenant_id: uuid.UUID,  # noqa: ARG001 — consumed by dep injection
    session: TenantSchemaSession,
    _user: CurrentSuperuser,
) -> list[TenantUserOut]:
    users = await TenantUsersAdminService(session).list_users()
    return [TenantUserOut.model_validate(u) for u in users]


@router.post(
    "", response_model=TenantUserCreateOut, status_code=status.HTTP_201_CREATED,
)
async def create_tenant_user(
    tenant_id: uuid.UUID,  # noqa: ARG001
    body: TenantUserCreateIn,
    request: Request,
    session: TenantSchemaSession,
    _user: CurrentSuperuser,
) -> TenantUserCreateOut:
    redis = getattr(request.app.state, "redis", None)
    svc = TenantUsersAdminService(session, redis=redis)
    try:
        user, token = await svc.create_user(
            email=str(body.email),
            full_name=body.full_name,
            is_admin=body.is_admin,
        )
    except TenantUserConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TenantUserCreateOut(
        user=TenantUserOut.model_validate(user),
        password_reset_token=token,
        password_reset_expires_in=TenantUsersAdminService.admin_reset_ttl_seconds(),
    )


@router.get("/{user_id}", response_model=TenantUserOut)
async def get_tenant_user(
    tenant_id: uuid.UUID,  # noqa: ARG001
    user_id: uuid.UUID,
    session: TenantSchemaSession,
    _user: CurrentSuperuser,
) -> TenantUserOut:
    user = await TenantUsersAdminService(session).get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Tenant user not found")
    return TenantUserOut.model_validate(user)


@router.patch("/{user_id}", response_model=TenantUserOut)
async def patch_tenant_user(
    tenant_id: uuid.UUID,  # noqa: ARG001
    user_id: uuid.UUID,
    body: TenantUserPatchIn,
    session: TenantSchemaSession,
    _user: CurrentSuperuser,
) -> TenantUserOut:
    svc = TenantUsersAdminService(session)
    try:
        user = await svc.update_user(
            user_id=user_id,
            full_name=body.full_name,
            is_active=body.is_active,
            is_admin=body.is_admin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TenantUserOut.model_validate(user)


@router.post("/{user_id}/password-reset", response_model=PasswordResetOut)
async def initiate_password_reset(
    tenant_id: uuid.UUID,  # noqa: ARG001
    user_id: uuid.UUID,
    request: Request,
    session: TenantSchemaSession,
    _user: CurrentSuperuser,
) -> PasswordResetOut:
    redis = getattr(request.app.state, "redis", None)
    svc = TenantUsersAdminService(session, redis=redis)
    try:
        user, token = await svc.initiate_password_reset(user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PasswordResetOut(
        user_id=user.id,
        password_reset_token=token,
        password_reset_expires_in=TenantUsersAdminService.admin_reset_ttl_seconds(),
    )
```

- [ ] **Step 3: Mount the router in `app/main.py`**

```python
from app.platform_.tenant_users_admin.api import (
    router as tenant_users_admin_router,
)
```

Add the mount alongside the existing platform router mounts:

```python
app.include_router(tenant_users_admin_router)
```

- [ ] **Step 4: Run the failing tests — they should pass now**

```bash
make test-fast T=tests/platform_/tenant_users_admin/test_api.py
```
Expected: 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/platform_/tenant_users_admin/api.py \
        app/main.py \
        tests/platform_/tenant_users_admin/test_api.py
git commit -m "feat(tenant-users-admin): API router + 5 endpoints"
```

---

## Task 5: CLAUDE.md contracts

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append a subsection under `## IAM module contracts (do not violate)`**

Find the `## IAM module contracts (do not violate)` section. Append at the end of its bullet list:

```markdown
- Tenant-user CRUD from a platform context lives under
  `/platform/tenants/{tenant_id}/users` (see `app/platform_/tenant_users_admin/`).
  These endpoints use the new `get_session_for_tenant_schema(tenant_id)`
  dependency in `app/core/db.py`. They are NOT subscription-gated — platform
  admins must be able to manage users regardless of tenant state.
- The list / get endpoints filter `impersonation_id IS NULL` so shadow
  tenant_users from the impersonation flow (P1.7-02) never appear in
  operator UI. The PATCH and password-reset endpoints also refuse to act
  on shadows (404).
- Admin-initiated password reset returns the HMAC reset token in the
  response body with a 24h TTL (vs 15min for self-service). The operator
  delivers it out of band until Phase 3 ships email. The same JTI/Redis
  consumption rules from `app/modules/iam/reset_tokens.py` apply; the
  user redeems via the existing `POST /auth/password-reset/confirm`.
- Until P1.7-05 lands, these endpoints gate on `CurrentSuperuser`. After
  P1.7-05, the dep swaps to admin-or-above via
  `get_current_platform_user_with_role("admin")` in `api.py` only — call
  sites do not change.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): tenant-user CRUD contracts"
```

---

## Task 6: Final verification

- [ ] **Step 1: Full lint + type-check + test suite**

```bash
make lint
make mypy
make test
```
Expected: all clean.

- [ ] **Step 2: Manual smoke check**

```bash
make up
make migrate
alembic -c alembic-tenant.ini -x schema=tenant_test upgrade head
make api &
sleep 3
TOKEN=$(make -s platform-token)
TENANT_ID=$(curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8001/platform/tenants | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

# List
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8001/platform/tenants/$TENANT_ID/users" \
  | python -m json.tool

# Create
curl -s -X POST "http://127.0.0.1:8001/platform/tenants/$TENANT_ID/users" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"email": "smoke@test.example", "full_name": "Smoke", "is_admin": false}' \
  | python -m json.tool

pkill -f "uvicorn app.main:app" || true
```
Expected: list returns `[]` or existing users; create returns the new user + a token + `password_reset_expires_in: 86400`.

- [ ] **Step 3: PR**

```bash
git push -u origin feat/phase-1-7/04-tenant-user-crud
gh pr create --title "feat(tenant-users-admin): CRUD + admin-initiated password reset" --body "$(cat <<'EOF'
## Summary
- New `get_session_for_tenant_schema(tenant_id)` cross-schema dep in `app/core/db.py` — used by platform endpoints that operate on a specific tenant's schema. Not subscription-gated.
- New module `app/platform_/tenant_users_admin/` with five endpoints under `/platform/tenants/{tenant_id}/users`:
  - `GET /` list (filters shadow users)
  - `POST /` create + return one-time HMAC reset token (24h TTL)
  - `GET /{user_id}` detail (404 for shadow users)
  - `PATCH /{user_id}` patch full_name / is_active / is_admin (404 for shadow users)
  - `POST /{user_id}/password-reset` generate new reset token, return in body
- Admin-initiated reset reuses `app/modules/iam/reset_tokens.py` HMAC pipeline. JTI stored in Redis with 24h TTL; user redeems via existing `/auth/password-reset/confirm`.
- CLAUDE.md updated with the tenant-user-admin contracts subsection.
- Role gate is `CurrentSuperuser` until P1.7-05 ships 4-tier roles, then swaps to admin-or-above in one place.

## Test plan
- [ ] `make test-fast T=tests/platform_/tenant_users_admin/` — 13 tests (4 dep + 9 api)
- [ ] `make test-fast T=tests/modules/iam/` — no regression in existing IAM tests
- [ ] `make ci` (ruff + mypy + full pytest)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `get_session_for_tenant_schema` dep added to `app/core/db.py`, with the 4 unit tests passing
- [ ] `TenantUsersAdminService` covers list / get / create / update / initiate_password_reset
- [ ] `/platform/tenants/{tenant_id}/users` router exposes 5 endpoints with the documented status codes
- [ ] List + get + patch + password-reset refuse to act on shadow users (404)
- [ ] Admin reset token is a valid HMAC token verifiable via `verify_reset_token`; TTL = 86400 seconds
- [ ] All new tests pass + no regression elsewhere
- [ ] CLAUDE.md updated
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** include shadow users in any list output. The portal's user list must never surface impersonation rows. The filter is `WHERE impersonation_id IS NULL`.
- **Do not** add a permanent column on `tenant_users` to track admin-initiated vs self-service resets. The JTI Redis key is the dedup mechanism; the HMAC token's payload tells the user what they need.
- **Do not** rewrite the existing reset_request / reset_confirm flow. The admin flow uses the same HMAC primitive but a longer TTL and skips the email delivery (which doesn't exist yet).
- **Do not** add subscription-gating to the new dep. Platform admins must reach tenant users in any subscription state — including suspended and cancelled — because reactivating a tenant often starts with re-enabling its admin's account.
- The new dep validates `schema_name` defensively against `_SCHEMA_RE`. If the validation fails, log + 500 (data corruption signal). Do NOT silently fall through.
- The role gate swap (CurrentSuperuser → admin-or-above) is one-line per endpoint when P1.7-05 lands. Until then keep the gate strict — superuser only.
- If `make mypy` flags the `tenant_id: uuid.UUID  # noqa: ARG001` lines on the route handlers, that's intentional — FastAPI's dep injection sees the path param but the handler doesn't use it directly (the dep consumes it). Keep the noqa.
- If a test fails because the shadow user filter isn't applied, the most likely cause is that `TenantUser.impersonation_id` was not exposed on the ORM model. That happens in P1.7-02b Task 1. Verify 02b has merged before running this sub-plan's tests.
- The cross-schema dep yields a session that commits on successful exit. Service methods should NOT call `await session.commit()` themselves — let the dep close the transaction. (This matches the existing `get_platform_session` / `get_tenant_session` pattern.)
