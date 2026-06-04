# Phase 1.7 Sub-Plan 05: Platform User 4-Tier Roles

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/phase-1-7/05-platform-user-roles` from `main` before starting.

**Goal:** Replace the binary `is_superuser` flag with a four-tier role hierarchy (`superuser > admin > finance > support`) enforced at the API layer. After this sub-plan merges, `CLAUDE.md`'s "Platform Superuser / Admin / Finance / Support — 4 tiers, enforced at API layer" promise is true, and Portal v1's role-based UI hiding (sub-plan 09 `<PermissionGuard>`) can derive permissions from a real backend signal.

**Architecture:**
- Migration adds `platform.platform_users.role` (text, NOT NULL, default `'support'`) with a `CHECK (role IN (...))` constraint, then back-fills `role='superuser'` for every existing row where `is_superuser=true`.
- `is_superuser` stays for backward compatibility. `PlatformUserService.create()` and `update()` keep the two in sync: `role='superuser'` implies `is_superuser=true` and vice versa.
- `app/platform_/auth.py` gains a numeric role hierarchy + a `get_current_platform_user_with_role(role)` dep factory + three new `Current{Admin,Finance,Support}` shortcuts. `CurrentSuperuser` continues to work unchanged.
- All `/platform/*` routes are audited for their gate. The default policy is: **support+ for read, admin+ for write**, with explicit exceptions (superuser-only for security-critical writes like JWT keys and platform user creation).

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, FastAPI dependency injection, Pydantic v2.

**Roadmap reference:** `docs/superpowers/plans/phase-1-7-backend-foundation/00-index.md` §P1.7-05.

**Prerequisite:** None. P1.7-05 is foundational — P1.7-04 specifically waits on it to swap its gate from `CurrentSuperuser` to `CurrentAdmin`.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `alembic/platform/versions/010_platform_user_roles.py` | Create | Add `role` column + check constraint; back-fill superusers |
| `app/platform_/models.py` | Modify | Expose `role` on `PlatformUser` |
| `app/platform_/users/schemas.py` | Modify | Add `role` to In/Out schemas |
| `app/platform_/users/service.py` | Modify | Set/sync `role` on create + update; keep `is_superuser` ↔ `role='superuser'` invariant |
| `app/platform_/auth.py` | Modify | Add role hierarchy, dep factory, `CurrentAdmin`/`CurrentFinance`/`CurrentSupport` shortcuts |
| `app/platform_/users/api.py` | Modify | Apply role gates (list/get → support+, create → superuser, patch → superuser) |
| `app/platform_/tenants/api.py` | Modify | Apply role gates (list/get/retry → support+, create → superuser, edit/reactivate/assign-plan → admin+, suspend → admin+) |
| `app/platform_/billing/api.py` | Modify | Apply role gates (read → finance+, mutations → admin+) |
| `app/modules/maker_checker/platform_api.py` | Modify | List/get → support+, approve/reject/cancel → admin+ |
| `app/platform_/impersonations/api.py` | Modify | submit/active/get/end/mint → any platform user (unchanged); `GET /all` and revoke → admin+ |
| `app/platform_/tenant_users_admin/api.py` | Modify | All five endpoints swap `CurrentSuperuser` → `CurrentAdmin` |
| `tests/platform_/test_roles.py` | Create | Unit tests for the dep factory + hierarchy + each shortcut |
| `tests/platform_/test_users_api.py` | Modify | Cover the new `role` field on create/patch |
| `CLAUDE.md` | Modify | Replace the "Platform Superuser / Admin / Finance / Support — 4 tiers, enforced at API layer" promise with a contract describing the hierarchy and how to gate new routes |

---

## Task 1: Migration

**Files:**
- Create: `alembic/platform/versions/010_platform_user_roles.py`

- [ ] **Step 1: Write the migration**

```python
# alembic/platform/versions/010_platform_user_roles.py
"""Phase 1.7 — platform_users.role four-tier hierarchy.

Adds the role column with a CHECK constraint, back-fills role='superuser'
for every is_superuser=true row, and leaves is_superuser in place for
backward compat. Future cleanup may drop is_superuser.

Revision: 010
Depends on: 009
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_users",
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
            server_default="support",
        ),
        schema="platform",
    )
    op.create_check_constraint(
        "ck_platform_users_role",
        "platform_users",
        "role IN ('superuser', 'admin', 'finance', 'support')",
        schema="platform",
    )
    op.create_index(
        "ix_platform_users_role",
        "platform_users",
        ["role"],
        schema="platform",
    )
    # Back-fill: every existing superuser gets role='superuser'.
    op.execute(
        "UPDATE platform.platform_users SET role = 'superuser' "
        "WHERE is_superuser = true"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_users_role", table_name="platform_users", schema="platform",
    )
    op.drop_constraint(
        "ck_platform_users_role", "platform_users", schema="platform",
    )
    op.drop_column("platform_users", "role", schema="platform")
```

- [ ] **Step 2: Run up + down + up**

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```
Expected: clean cycle.

Verify in psql:

```bash
docker compose exec postgres psql -U sacco -d sacco -c "\d platform.platform_users" | grep role
docker compose exec postgres psql -U sacco -d sacco \
  -c "SELECT role, count(*) FROM platform.platform_users GROUP BY role"
```
Expected: `role` column present with check constraint; existing superusers grouped as `superuser`.

- [ ] **Step 3: Commit**

```bash
git add alembic/platform/versions/010_platform_user_roles.py
git commit -m "feat(iam): platform_users.role column + back-fill superusers"
```

---

## Task 2: Model + schema additions

**Files:**
- Modify: `app/platform_/models.py`
- Modify: `app/platform_/users/schemas.py`

- [ ] **Step 1: Expose `role` on `PlatformUser`**

In `app/platform_/models.py`, find the `PlatformUser` class. After the `is_superuser` column (around line 72), add:

```python
    role: Mapped[str] = mapped_column(Text, nullable=False, default="support")
```

- [ ] **Step 2: Update Pydantic schemas**

Open `app/platform_/users/schemas.py`. Update `CreatePlatformUserRequest`:

```python
class CreatePlatformUserRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(default="support", pattern="^(superuser|admin|finance|support)$")
    # Deprecated — kept for backward compat. If both are sent and conflict,
    # role wins. If only is_superuser=true is sent, role is coerced to 'superuser'.
    is_superuser: bool = False
```

Update `UpdatePlatformUserRequest`:

```python
class UpdatePlatformUserRequest(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=200)
    is_active: bool | None = None
    role: str | None = Field(
        default=None, pattern="^(superuser|admin|finance|support)$"
    )
    # Deprecated mirror — see CreatePlatformUserRequest.
    is_superuser: bool | None = None
```

Update `PlatformUserOut`:

```python
class PlatformUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    role: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Commit**

```bash
git add app/platform_/models.py app/platform_/users/schemas.py
git commit -m "feat(iam): PlatformUser.role + role on Create/Update/Out schemas"
```

---

## Task 3: PlatformUserService keeps `role` ↔ `is_superuser` in sync

**Files:**
- Modify: `app/platform_/users/service.py`

- [ ] **Step 1: Update `MAKER_CHECKER_FIELDS`**

```python
MAKER_CHECKER_FIELDS = {"is_active", "is_superuser", "role"}
```

- [ ] **Step 2: Update `create`**

Replace the existing `create` method body:

```python
    async def create(
        self,
        *,
        email: str,
        full_name: str,
        role: str = "support",
        is_superuser: bool | None = None,
    ) -> PlatformUser:
        """Create a new platform user. Raises ValueError on email conflict.

        ``role`` is authoritative. If ``is_superuser=True`` is passed but
        ``role`` is not 'superuser', role is coerced to 'superuser'. The
        ``is_superuser`` column is kept in sync with role for backward compat:
        is_superuser == (role == 'superuser').
        """
        effective_role = "superuser" if is_superuser else role
        if effective_role == "superuser":
            super_flag = True
        else:
            super_flag = False
        user = PlatformUser(
            email=email,
            full_name=full_name,
            role=effective_role,
            is_superuser=super_flag,
            is_active=True,
            hashed_password=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._s.add(user)
        try:
            await self._s.flush()
        except IntegrityError as exc:
            raise ValueError(f"Email '{email}' is already registered") from exc
        return user
```

- [ ] **Step 3: Update `update`**

Replace the `update` method body:

```python
    async def update(
        self,
        user_id: uuid.UUID,
        *,
        full_name: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
        role: str | None = None,
    ) -> PlatformUser:
        """Update user fields. is_active/is_superuser/role changes require
        maker-checker (enforced in API).

        Keeps the is_superuser ↔ role='superuser' invariant. If the caller
        passes ``is_superuser=True``, role is forced to 'superuser'. If
        ``role`` is set to or away from 'superuser', is_superuser tracks.
        """
        user = await self.get(user_id)
        if user is None:
            raise ValueError(f"Platform user {user_id} not found")
        if full_name is not None:
            user.full_name = full_name
        if is_active is not None:
            user.is_active = is_active
        if role is not None:
            user.role = role
            user.is_superuser = role == "superuser"
        if is_superuser is not None:
            # Explicit is_superuser overrides role coercion.
            user.is_superuser = is_superuser
            user.role = "superuser" if is_superuser else (
                role if role is not None and role != "superuser" else user.role
            )
            # If user said is_superuser=False but role is still 'superuser',
            # demote role to 'admin' as the next-highest tier.
            if not is_superuser and user.role == "superuser":
                user.role = "admin"
        user.updated_at = datetime.now(UTC)
        await self._s.flush()
        return user
```

- [ ] **Step 4: Commit**

```bash
git add app/platform_/users/service.py
git commit -m "feat(iam): PlatformUserService keeps role and is_superuser in sync"
```

---

## Task 4: Auth dep factory + four shortcuts

**Files:**
- Create: `tests/platform_/test_roles.py`
- Modify: `app/platform_/auth.py`

- [ ] **Step 1: Write the failing role-hierarchy unit test**

```python
# tests/platform_/test_roles.py
"""Role hierarchy + dep factory tests.

The factory returns a dep that requires the authenticated platform user
to have role rank >= the specified role's rank.

    superuser=4 > admin=3 > finance=2 > support=1
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.platform_.auth import (
    _ROLE_RANK,
    get_current_platform_user_with_role,
)
from app.platform_.models import PlatformUser


async def _make_user(
    factory: async_sessionmaker, *, role: str, is_superuser: bool = False,
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"u-{uuid.uuid4().hex[:6]}@test.example",
            full_name="U",
            role=role,
            is_superuser=is_superuser,
            is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup(factory: async_sessionmaker) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


def test_rank_constants() -> None:
    assert _ROLE_RANK == {"superuser": 4, "admin": 3, "finance": 2, "support": 1}


async def test_factory_allows_equal_or_higher_rank(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    super_u = await _make_user(factory, role="superuser", is_superuser=True)
    admin = await _make_user(factory, role="admin")
    finance = await _make_user(factory, role="finance")
    support = await _make_user(factory, role="support")
    try:
        gate = get_current_platform_user_with_role("finance")
        # superuser, admin, finance — all pass; support — rejected
        assert (await gate(super_u)).id == super_u.id
        assert (await gate(admin)).id == admin.id
        assert (await gate(finance)).id == finance.id
        with pytest.raises(HTTPException) as exc:
            await gate(support)
        assert exc.value.status_code == 403
    finally:
        await _cleanup(factory)


async def test_factory_admin_excludes_finance(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    admin = await _make_user(factory, role="admin")
    finance = await _make_user(factory, role="finance")
    try:
        gate = get_current_platform_user_with_role("admin")
        assert (await gate(admin)).id == admin.id
        with pytest.raises(HTTPException):
            await gate(finance)
    finally:
        await _cleanup(factory)


async def test_factory_rejects_unknown_role(test_engine: AsyncEngine) -> None:
    with pytest.raises(ValueError, match="unknown role"):
        get_current_platform_user_with_role("operator")


async def test_factory_rejects_user_with_unknown_role_value(
    test_engine: AsyncEngine,
) -> None:
    """A user whose role somehow ended up outside the enum is denied access
    regardless of rank. Defense in depth against a corrupt row.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    # Bypass the model validation and check constraint by going around it
    # would require dropping the constraint; instead, simulate the bad-state
    # path by directly invoking the factory's inner check.
    gate = get_current_platform_user_with_role("support")
    fake = PlatformUser(
        email="bad@example.com", full_name="bad", is_active=True,
        is_superuser=False, role="operator",  # not in the enum
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    with pytest.raises(HTTPException) as exc:
        await gate(fake)
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Run — expected to fail (factory + `_ROLE_RANK` not yet exported)**

```bash
make test-fast T=tests/platform_/test_roles.py
```
Expected: `ImportError`.

- [ ] **Step 3: Extend `app/platform_/auth.py`**

Add at the top of the file (after the existing imports):

```python
from collections.abc import Awaitable, Callable
```

After the existing `CurrentSuperuser` annotation block, append:

```python
# ── Role hierarchy ────────────────────────────────────────────────────────────

_ROLE_RANK: dict[str, int] = {
    "superuser": 4,
    "admin": 3,
    "finance": 2,
    "support": 1,
}


def get_current_platform_user_with_role(
    role: str,
) -> Callable[[PlatformUser], Awaitable[PlatformUser]]:
    """Dep factory: returns a FastAPI dep requiring role rank >= ``role``.

    Use as:
        CurrentAdmin = Annotated[
            PlatformUser, Depends(get_current_platform_user_with_role("admin"))
        ]

    A user with role='admin' passes ``with_role('admin')`` and
    ``with_role('finance')`` and ``with_role('support')`` but is rejected by
    ``with_role('superuser')``.

    Raises:
        ValueError: if ``role`` is not one of the four valid values
            (programmer error — fail fast at module import time).
    """
    if role not in _ROLE_RANK:
        raise ValueError(
            f"unknown role {role!r}; must be one of {sorted(_ROLE_RANK)}"
        )
    required_rank = _ROLE_RANK[role]

    async def _dep(
        user: CurrentPlatformUser,
    ) -> PlatformUser:
        user_rank = _ROLE_RANK.get(user.role, 0)
        # Backward compat: is_superuser=true overrides role rank.
        if user.is_superuser:
            user_rank = max(user_rank, _ROLE_RANK["superuser"])
        if user_rank < required_rank:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Requires role >= {role!r}; "
                    f"current role is {user.role!r}"
                ),
            )
        return user

    return _dep


# Pre-built dep shortcuts.
CurrentAdmin = Annotated[
    PlatformUser, Depends(get_current_platform_user_with_role("admin"))
]
CurrentFinance = Annotated[
    PlatformUser, Depends(get_current_platform_user_with_role("finance"))
]
CurrentSupport = Annotated[
    PlatformUser, Depends(get_current_platform_user_with_role("support"))
]
```

Extend `__all__`:

```python
__all__ = [
    "CurrentAdmin",
    "CurrentFinance",
    "CurrentPlatformUser",
    "CurrentSuperuser",
    "CurrentSupport",
    "get_current_platform_user",
    "get_current_platform_user_with_role",
    "get_current_superuser",
]
```

- [ ] **Step 4: Run the role tests — they should pass**

```bash
make test-fast T=tests/platform_/test_roles.py
```
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/platform_/auth.py tests/platform_/test_roles.py
git commit -m "feat(auth): role hierarchy + dep factory + Current{Admin,Finance,Support} shortcuts"
```

---

## Task 5: Apply role gates to existing platform routers

This task is mechanical. For every file listed below, find the matching route and swap its dependency type. Stick to the convention in the table.

**Gate selection convention:**

| Operation | Required role |
|---|---|
| Read (list / get / detail), non-sensitive | `CurrentSupport` (anyone authenticated) |
| Read of billing data | `CurrentFinance` |
| Mutation, non-financial | `CurrentAdmin` |
| Mutation, billing | `CurrentAdmin` |
| Security-critical mutations (create platform user, JWT keys, tenant create) | `CurrentSuperuser` |
| Self-service surfaces (e.g. impersonator-only endpoints) | `CurrentPlatformUser` (any logged-in platform user) |

### 5a — `app/platform_/users/api.py`

- [ ] **Step 1: Apply gates**

| Route | Current dep | New dep |
|---|---|---|
| `GET /platform/users` (list) | `AnyPlatformUser` | `CurrentSupport` |
| `GET /platform/users/{id}` | `AnyPlatformUser` | `CurrentSupport` |
| `POST /platform/users` (create) | `Superuser` | `CurrentSuperuser` (rename for consistency) |
| `PATCH /platform/users/{id}` | `Superuser` | `CurrentSuperuser` |

Import the new shortcuts:

```python
from app.platform_.auth import (
    CurrentSuperuser,
    CurrentSupport,
    get_current_platform_user,
)
```

Replace the existing `AnyPlatformUser` / `Superuser` Annotated aliases at the top of the file with these (or update the route handlers to use the new types directly).

- [ ] **Step 2: Run existing user-api tests**

```bash
make test-fast T=tests/platform_/test_users_api.py
```
Expected: still green (the existing tests use superusers everywhere; superuser passes every gate).

### 5b — `app/platform_/tenants/api.py`

- [ ] **Step 1: Apply gates**

| Route | New dep |
|---|---|
| `GET /platform/tenants` | `CurrentSupport` |
| `GET /platform/tenants/{id}` | `CurrentSupport` |
| `POST /platform/tenants` (create) | `CurrentSuperuser` (keep — high blast radius) |
| `POST /platform/tenants/{id}/retry-provisioning` | `CurrentAdmin` |
| `PATCH /platform/tenants/{id}` (P1.7-03) | `CurrentAdmin` |
| `POST /platform/tenants/{id}/suspend` (P1.7-03) | `CurrentAdmin` |
| `POST /platform/tenants/{id}/reactivate` (P1.7-03) | `CurrentAdmin` |
| `POST /platform/tenants/{id}/assign-plan` (P1.7-03) | `CurrentAdmin` |

Import:

```python
from app.platform_.auth import CurrentAdmin, CurrentSuperuser, CurrentSupport
```

- [ ] **Step 2: Run existing tests**

```bash
make test-fast T=tests/platform_/test_tenants_api.py
make test-fast T=tests/platform_/tenants/test_lifecycle.py
```
Expected: still green.

### 5c — `app/platform_/billing/api.py`

- [ ] **Step 1: Apply gates**

All read endpoints get `CurrentFinance`; mutations get `CurrentAdmin`.

| Route | New dep |
|---|---|
| `GET /platform/billing/plans` | `CurrentFinance` |
| `POST /platform/billing/plans` | `CurrentAdmin` |
| `GET /platform/billing/plans/{id}` | `CurrentFinance` |
| `PATCH /platform/billing/plans/{id}` | `CurrentAdmin` |
| `GET /platform/billing/subscriptions` | `CurrentFinance` |
| `POST /platform/billing/subscriptions` | `CurrentAdmin` |
| `GET /platform/billing/subscriptions/{id}` | `CurrentFinance` |
| `POST /platform/billing/subscriptions/{id}/cancel` | `CurrentAdmin` |
| `POST /platform/billing/subscriptions/{id}/reactivate` | `CurrentAdmin` |
| `GET /platform/billing/invoices` | `CurrentFinance` |
| `GET /platform/billing/invoices/{id}` | `CurrentFinance` |
| `GET /platform/billing/invoices/{id}.pdf` | `CurrentFinance` |
| `POST /platform/billing/invoices/{id}/payments` (record) | `CurrentFinance` (finance staff record payments; admins approve) |
| `POST /platform/billing/invoices/{id}/void` (submit approval) | `CurrentAdmin` |
| `POST /platform/billing/payments/{id}/reject` | `CurrentAdmin` |
| `GET /platform/billing/payments/pending-confirmation` | `CurrentFinance` |
| Tenant-facing `/billing/me/*` | unchanged (`CurrentTenantUser`) |

Import:

```python
from app.platform_.auth import CurrentAdmin, CurrentFinance
```

- [ ] **Step 2: Run existing billing tests**

```bash
make test-fast T=tests/platform_/billing/
```
Expected: still green (existing tests seed superusers; superuser passes finance+ and admin+).

### 5d — `app/modules/maker_checker/platform_api.py` (P1.7-01)

- [ ] **Step 1: Apply gates**

| Route | New dep |
|---|---|
| `GET /platform/approvals` (list) | `CurrentSupport` |
| `GET /platform/approvals/{id}` | `CurrentSupport` |
| `POST /platform/approvals` (submit) | `CurrentAdmin` |
| `POST /platform/approvals/{id}/approve` | `CurrentAdmin` |
| `POST /platform/approvals/{id}/reject` | `CurrentAdmin` |
| `POST /platform/approvals/{id}/cancel` | `CurrentAdmin` |

Import + swap.

- [ ] **Step 2: Run existing tests**

```bash
make test-fast T=tests/modules/maker_checker/test_platform_api.py
make test-fast T=tests/platform_/billing/test_payment_confirmation_e2e.py
```
Expected: still green.

### 5e — `app/platform_/impersonations/api.py` (P1.7-02b)

- [ ] **Step 1: Apply gates**

| Route | New dep |
|---|---|
| `POST /platform/impersonations` (submit) | unchanged (`CurrentPlatformUser`) |
| `GET /platform/impersonations/active` (mine) | unchanged (`CurrentPlatformUser`) |
| `GET /platform/impersonations/all` | `CurrentAdmin` (was `CurrentSuperuser`) |
| `GET /platform/impersonations/{id}` | unchanged (`CurrentPlatformUser`) |
| `DELETE /platform/impersonations/{id}` (end) | unchanged (impersonator-only) |
| `POST /platform/impersonations/{id}/revoke` | `CurrentAdmin` (was `CurrentSuperuser`) |
| `POST /platform/impersonations/{id}/mint-tenant-token` | unchanged (impersonator-only) |

Import + swap the two endpoints noted.

- [ ] **Step 2: Run impersonation tests**

```bash
make test-fast T=tests/platform_/impersonations/
```
Expected: still green.

### 5f — `app/platform_/tenant_users_admin/api.py` (P1.7-04)

- [ ] **Step 1: Apply gates**

All five endpoints swap `CurrentSuperuser` → `CurrentAdmin`:

| Route | New dep |
|---|---|
| `GET /platform/tenants/{tenant_id}/users` | `CurrentAdmin` |
| `POST /platform/tenants/{tenant_id}/users` | `CurrentAdmin` |
| `GET /platform/tenants/{tenant_id}/users/{user_id}` | `CurrentAdmin` |
| `PATCH /platform/tenants/{tenant_id}/users/{user_id}` | `CurrentAdmin` |
| `POST /platform/tenants/{tenant_id}/users/{user_id}/password-reset` | `CurrentAdmin` |

Single import swap; the call sites stay frozen.

- [ ] **Step 2: Run tests**

```bash
make test-fast T=tests/platform_/tenant_users_admin/
```
Expected: still green.

### 5g — `app/modules/iam/keys/api.py`

- [ ] **Step 1: Verify unchanged**

The `key_mgmt_router` is mounted with `dependencies=[Depends(get_current_superuser)]` in `app/main.py`. **Leave this as superuser-only**; signing key administration is the most security-critical surface in the system. No changes needed in this sub-plan.

### 5h — Single combined commit for 5a–5g

- [ ] **Step 1: Commit the gate swap**

```bash
git add app/platform_/users/api.py \
        app/platform_/tenants/api.py \
        app/platform_/billing/api.py \
        app/modules/maker_checker/platform_api.py \
        app/platform_/impersonations/api.py \
        app/platform_/tenant_users_admin/api.py
git commit -m "feat(auth): apply role gates to all /platform/* routes"
```

---

## Task 6: Update existing user-api tests for the new `role` field

**Files:**
- Modify: `tests/platform_/test_users_api.py`

- [ ] **Step 1: Cover create + patch with the new `role` field**

Add these tests at the end of `tests/platform_/test_users_api.py`:

```python
async def test_create_user_with_explicit_role(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        r = await client.post(
            "/platform/users",
            json={
                "email": f"finance-{uuid.uuid4().hex[:6]}@test.example",
                "full_name": "Finance Person",
                "role": "finance",
            },
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["role"] == "finance"
        assert body["is_superuser"] is False
    finally:
        await _cleanup(factory)


async def test_create_user_legacy_is_superuser_coerces_role(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        r = await client.post(
            "/platform/users",
            json={
                "email": f"legacy-{uuid.uuid4().hex[:6]}@test.example",
                "full_name": "Legacy",
                "is_superuser": True,
            },
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # Legacy is_superuser=true coerces role to 'superuser'
        assert body["role"] == "superuser"
        assert body["is_superuser"] is True
    finally:
        await _cleanup(factory)
```

(The helpers `_create_superuser` and `_cleanup` already exist in the file — reuse them.)

- [ ] **Step 2: Run the tests**

```bash
make test-fast T=tests/platform_/test_users_api.py
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/platform_/test_users_api.py
git commit -m "test(users-api): cover role field on create"
```

---

## Task 7: CLAUDE.md contracts

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Phase 2 decisions section**

Find the line `Roles: Platform Superuser / Admin / Finance / Support (4 tiers, enforced at API layer).` Add a parenthetical:

```markdown
- **Roles**: Platform Superuser / Admin / Finance / Support (4 tiers, enforced at API layer via `app/platform_/auth.py`'s `get_current_platform_user_with_role(role)` factory and the `CurrentAdmin` / `CurrentFinance` / `CurrentSupport` shortcuts).
```

- [ ] **Step 2: Append a new subsection under `## IAM module contracts (do not violate)`**

```markdown
- Platform user roles follow a strict hierarchy: `superuser > admin > finance > support`.
  Enforced by `get_current_platform_user_with_role(role)` in `app/platform_/auth.py`.
  `with_role("admin")` accepts admin and superuser; `with_role("finance")`
  accepts finance, admin, and superuser; `with_role("support")` accepts
  anyone authenticated; `with_role("superuser")` accepts superuser only.
- `is_superuser` is the deprecated mirror of `role='superuser'`. The
  `PlatformUserService` keeps the two in sync on create and update. Existing
  code that depends on `is_superuser` continues to work. New code should
  depend on `role` and the role-based dep shortcuts.
- Default gate policy on `/platform/*` routes: **support+ for read,
  admin+ for write**, with explicit exceptions:
  - `POST /platform/users` (create), JWT key admin routes, and
    `POST /platform/tenants` (create) require `CurrentSuperuser`.
  - Billing read endpoints require `CurrentFinance` (billing data is
    sensitive even read-only).
  - `POST /platform/billing/invoices/{id}/payments` (record) requires
    `CurrentFinance` — recording is the finance staff's job; approval
    requires `CurrentAdmin`.
  - Impersonation submit / active / detail / end / mint-token endpoints
    accept any authenticated platform user (the maker-checker quorum and
    impersonator-only checks provide the gate).
- New `/platform/*` routes should declare the required role explicitly at
  the dep level. Choose the lowest tier that is operationally correct —
  raising the bar later requires coordinating with portal permission UX.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): 4-tier platform role hierarchy + gate policy"
```

---

## Task 8: Final verification

- [ ] **Step 1: Full lint + type-check + test suite**

```bash
make lint
make mypy
make test
```
Expected: all clean. Specifically, the new `tests/platform_/test_roles.py` appears in the pass count and no existing platform test regresses.

- [ ] **Step 2: Manual smoke check (non-superuser walks through gates)**

```bash
make up
make migrate
make api &
sleep 3

# Promote a non-superuser via psql
docker compose exec postgres psql -U sacco -d sacco -c \
  "INSERT INTO platform.platform_users (id, email, full_name, role, is_active, is_superuser, created_at, updated_at) VALUES (gen_random_uuid(), 'finance@test.example', 'Finance', 'finance', true, false, now(), now())"
FINANCE_ID=$(docker compose exec -T postgres psql -U sacco -d sacco -tA \
  -c "SELECT id FROM platform.platform_users WHERE email='finance@test.example'")

# Finance can list invoices
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-Platform-Actor-ID: $FINANCE_ID" \
  http://127.0.0.1:8001/platform/billing/invoices
# Expected: 200

# Finance cannot create a plan
curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST -H "X-Platform-Actor-ID: $FINANCE_ID" -H "Content-Type: application/json" \
  -d '{"code":"x","name":"x","base_price":"0","billing_period":"monthly"}' \
  http://127.0.0.1:8001/platform/billing/plans
# Expected: 403

# Finance cannot list tenant users (admin gate)
TENANT_ID=$(docker compose exec -T postgres psql -U sacco -d sacco -tA \
  -c "SELECT id FROM platform.tenants LIMIT 1")
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-Platform-Actor-ID: $FINANCE_ID" \
  "http://127.0.0.1:8001/platform/tenants/$TENANT_ID/users"
# Expected: 403

pkill -f "uvicorn app.main:app" || true
```
Expected codes: 200 / 403 / 403.

- [ ] **Step 3: PR**

```bash
git push -u origin feat/phase-1-7/05-platform-user-roles
gh pr create --title "feat(auth): 4-tier platform role hierarchy" --body "$(cat <<'EOF'
## Summary
- Migration: `platform_users.role` text NOT NULL DEFAULT 'support' with CHECK constraint; back-fills `role='superuser'` for existing `is_superuser=true` rows.
- ORM exposes `role`; schemas accept it on create/patch; service keeps `role='superuser'` ↔ `is_superuser=true` in sync (deprecated mirror).
- Auth layer: `_ROLE_RANK` hierarchy, `get_current_platform_user_with_role(role)` factory, `CurrentAdmin` / `CurrentFinance` / `CurrentSupport` shortcuts. `CurrentSuperuser` unchanged.
- All `/platform/*` routes gated per the policy in CLAUDE.md (support+ read, admin+ write, superuser for security-critical mutations, finance+ for billing reads).
- P1.7-04's `tenant_users_admin` and P1.7-02b's impersonation `all` + `revoke` swap from `CurrentSuperuser` to `CurrentAdmin`.
- CLAUDE.md updated with the hierarchy + gate policy + which routes are the explicit exceptions.

## Backward compatibility
- `is_superuser` column stays. Existing code that depends on it continues to work.
- Existing tests pass unchanged because superusers pass every gate.

## Test plan
- [ ] `make test-fast T=tests/platform_/test_roles.py` — 5 dep factory + hierarchy tests
- [ ] `make test-fast T=tests/platform_/` — no regression in platform tests
- [ ] `make ci` (ruff + mypy + full pytest)
- [ ] Manual: finance-role user smoke walk

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] Migration 010 applied + rollback verified
- [ ] `PlatformUser.role` exposed on the ORM
- [ ] Pydantic schemas accept `role` on create/patch; `PlatformUserOut` includes `role`
- [ ] `PlatformUserService.create` and `update` keep `role='superuser'` ↔ `is_superuser=true` in sync
- [ ] `_ROLE_RANK`, `get_current_platform_user_with_role`, and `Current{Admin,Finance,Support}` exported from `app/platform_/auth.py`
- [ ] Every `/platform/*` route uses one of the four shortcut deps; the policy table in this sub-plan is the source of truth
- [ ] `tests/platform_/test_roles.py` passes (5 tests)
- [ ] No regression elsewhere — `make test` clean
- [ ] CLAUDE.md updated
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** drop the `is_superuser` column. Backward compat is a hard requirement; a future cleanup PR can remove it after every consumer has been audited.
- **Do not** add a fifth role tier. Four is the contract; the portal's UX (Portal v1 sub-plan 09) maps cleanly to four. Introduce a permission system if granular gates are needed later.
- **Do not** retrofit `with_role` to support multi-arg "OR" semantics. The hierarchy already covers the common case. If a route truly needs "finance OR support but NOT admin", express it with an explicit conditional inside the handler.
- **Do not** silently change a route's gate to a lower tier than this sub-plan's table specifies. If a sub-plan disagrees with the table, raise the question — the table is the source of truth.
- The migration back-fills `role='superuser'` based on `is_superuser`. After this lands, NEW users created without an explicit role default to `'support'` — the lowest tier. The bootstrap user in `app/platform_/seeds/` should be audited to ensure it still creates a superuser (the existing `is_superuser=True` will trigger the coercion in `PlatformUserService.create`, but cross-check).
- If `make mypy` flags the `_ROLE_RANK` dict access (`_ROLE_RANK.get(user.role, 0)` returning `int | None`), use `_ROLE_RANK.get(user.role, 0) or 0` or cast — it should already be `int` because the default is `0`.
- The gate-swap commit (Task 5h) is intentionally one big commit. Splitting per file produces 6 commits with each test pass in between; that's fine if preferred. Either way, the PR shows the diff cleanly.
