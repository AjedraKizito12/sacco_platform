# Phase 1.7 Sub-Plan 02b: Impersonation HTTP + Cross-Context Auth Wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/phase-1-7/02b-impersonation-http` from `main` after 02a is merged.

**Goal:** Wire the impersonation data layer from 02a into HTTP, tenant authentication, and the audit pipeline so a platform admin can request → be approved → mint a tenant token → operate inside a tenant → end the session, with every action audit-trailed to the original platform identity. After 02b merges, ADR-001 §7 (cross-context access) is fully implemented and Portal sub-plans 14 / 31 / 32 unblock.

**Architecture:**
- `app/platform_/impersonations/api.py` exposes six endpoints under `/platform/impersonations/*`.
- `ImpersonationService` gains a `mint_tenant_token` method that lazily provisions a **shadow tenant_user** in the target tenant's schema, then issues a normal tenant access+refresh JWT pair using the existing `KeyService` / `SessionService` / `tokens.service` primitives (the same path `TenantAuthService.login` uses; see `app/modules/iam/tenant_auth/service.py:160-238` for the template).
- Both `get_current_tenant_user_jwt` and `get_current_tenant_user_stub` are extended to read `tenant_users.impersonation_id` and, when non-null, bind `impersonation_id` to structlog contextvars.
- `AuditableMixin._actor_context` reads `impersonation_id` from contextvars and `_write_audit` propagates it onto `tenant.audit_log` rows (the column was added in 02a's tenant migration). `PlatformAuditLog` is unchanged.
- A `DELETE /platform/impersonations/{id}` (impersonator) and `POST /platform/impersonations/{id}/revoke` (admin) both deactivate the shadow tenant_user and revoke all its tenant sessions in one transaction.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2, PyJWT (via existing `tokens.service`).

**Roadmap reference:** `docs/superpowers/plans/phase-1-7-backend-foundation/00-index.md` §P1.7-02 (split into 02a + 02b).

**ADR reference:** `docs/superpowers/decisions/2026-06-02-impersonation-design.md` — particularly decisions §3 (shadow tenant_user), §4 (audit identity), §5 (regular tenant JWT).

**Prerequisite:** **P1.7-02a must be merged.** This sub-plan modifies the existing `ImpersonationService` and depends on the `SupportImpersonation` model, the `impersonation_id` columns on `tenant_users` and `audit_log`, the `platform.start_impersonation` executor, and ADR-002.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/core/audit/mixin.py` | Modify | Add `impersonation_id` to `_actor_context`; conditionally include it when writing to `TenantAuditLog` |
| `app/modules/iam/dependencies.py` | Modify | Extend both tenant deps (stub + JWT) to bind `impersonation_id` contextvar when the resolved tenant_user has a non-null `impersonation_id` column |
| `app/modules/iam/tenant_users/models.py` | Modify | Add the `impersonation_id` column to the `TenantUser` model (column itself was added by 02a's migration; this exposes it to the ORM) |
| `app/platform_/impersonations/exceptions.py` | Create | `ImpersonationGone`, `ImpersonationNotActive` |
| `app/platform_/impersonations/service.py` | Modify | Add `mint_tenant_token`; extend `end` and `revoke` to clean up shadow + sessions |
| `app/platform_/impersonations/api.py` | Create | Six endpoints under `/platform/impersonations/*` |
| `app/platform_/impersonations/schemas.py` | Modify | Add `MintTenantTokenOut` |
| `app/main.py` | Modify | Mount the new router |
| `tests/platform_/impersonations/test_api.py` | Create | Endpoint integration tests with stub auth |
| `tests/platform_/impersonations/test_mint_and_shadow.py` | Create | Direct tests of the mint flow (shadow user lazy creation + idempotency) |
| `tests/platform_/impersonations/test_end_to_end.py` | Create | Full cross-context flow: request → approve → mint → call /members → audit_log row with impersonation_id → end → 401 |
| `tests/core/audit/test_impersonation_propagation.py` | Create | Unit test: audit mixin writes impersonation_id when the contextvar is bound |
| `tests/modules/iam/test_tenant_dep_impersonation.py` | Create | Unit test: tenant deps bind impersonation_id contextvar when user.impersonation_id is set |
| `CLAUDE.md` | Modify | Replace the partial "Impersonation contracts (data layer)" subsection with the full set |

---

## Task 1: Expose `impersonation_id` on the `TenantUser` model

**Files:**
- Modify: `app/modules/iam/tenant_users/models.py`

- [ ] **Step 1: Add the field to `TenantUser`**

Find the `TenantUser` class. After the `is_admin` column (around line 45), insert:

```python
    # Populated by 02b's shadow-user creation. NULL for real tenant users.
    impersonation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
```

- [ ] **Step 2: Sanity-check the existing tenant-user tests still pass**

```bash
make test-fast T=tests/modules/iam/tenant_users/
```
Expected: green. The new field is optional and defaults to NULL; no existing test mutates it.

- [ ] **Step 3: Commit**

```bash
git add app/modules/iam/tenant_users/models.py
git commit -m "feat(iam): expose tenant_users.impersonation_id on the ORM model"
```

---

## Task 2: AuditableMixin propagates `impersonation_id`

**Files:**
- Create: `tests/core/audit/test_impersonation_propagation.py`
- Modify: `app/core/audit/mixin.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/audit/test_impersonation_propagation.py
"""When impersonation_id is bound to structlog contextvars, AuditableMixin
writes it onto tenant.audit_log rows. PlatformAuditLog rows do NOT carry
the column and must be unaffected.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.modules.iam.tenant_users.models import TenantUser
from app.platform_.models import PlatformUser


async def test_tenant_audit_row_carries_impersonation_id(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    imp_id = uuid.uuid4()
    structlog.contextvars.bind_contextvars(
        actor_type="tenant_user",
        actor_id=str(uuid.uuid4()),
        actor_label="imp.abc@platform.local",
        impersonation_id=str(imp_id),
    )
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            u = TenantUser(
                email=f"u-{uuid.uuid4().hex[:6]}@test.example",
                full_name="U", is_active=True, is_admin=False,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(u)

        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            rows = (
                await s.execute(
                    select(TenantAuditLog)
                    .where(TenantAuditLog.table_name == "tenant_users")
                    .order_by(TenantAuditLog.occurred_at.desc())
                    .limit(1)
                )
            ).scalars().all()
            assert rows, "no tenant_users audit row found"
            assert rows[0].impersonation_id == imp_id
    finally:
        structlog.contextvars.clear_contextvars()
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            await s.execute(text("DELETE FROM tenant_users"))
            await s.execute(text("DELETE FROM audit_log"))


async def test_platform_audit_row_unaffected_by_impersonation_id(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    structlog.contextvars.bind_contextvars(
        actor_type="platform_user",
        actor_id=str(uuid.uuid4()),
        impersonation_id=str(uuid.uuid4()),
    )
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            u = PlatformUser(
                email=f"p-{uuid.uuid4().hex[:6]}@test.example",
                full_name="P", is_active=True, is_superuser=False,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(u)
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            rows = (
                await s.execute(
                    select(PlatformAuditLog)
                    .where(PlatformAuditLog.table_name == "platform_users")
                    .order_by(PlatformAuditLog.occurred_at.desc())
                    .limit(1)
                )
            ).scalars().all()
            assert rows, "no platform_users audit row found"
            # PlatformAuditLog has no impersonation_id column; the mixin must
            # have silently dropped the key from the insert payload.
            assert not hasattr(rows[0], "impersonation_id")
    finally:
        structlog.contextvars.clear_contextvars()
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(text("DELETE FROM platform.platform_users"))
            await s.execute(text("DELETE FROM platform.audit_log"))
```

- [ ] **Step 2: Run — expected to fail**

```bash
make test-fast T=tests/core/audit/test_impersonation_propagation.py
```
Expected: first test fails — `impersonation_id` is `None` on the audit row.

- [ ] **Step 3: Extend `_actor_context` and `_write_audit`**

Open `app/core/audit/mixin.py`. Modify the `_actor_context` helper (currently around lines 42–56) to read `impersonation_id`:

```python
def _actor_context() -> dict[str, Any]:
    ctx = structlog.contextvars.get_contextvars()
    raw_actor_id = ctx.get("actor_id")
    try:
        actor_id: uuid.UUID | None = (
            uuid.UUID(str(raw_actor_id)) if raw_actor_id is not None else None
        )
    except ValueError:
        actor_id = None
    raw_impersonation_id = ctx.get("impersonation_id")
    try:
        impersonation_id: uuid.UUID | None = (
            uuid.UUID(str(raw_impersonation_id))
            if raw_impersonation_id is not None
            else None
        )
    except ValueError:
        impersonation_id = None
    return {
        "actor_type": ctx.get("actor_type", "system"),
        "actor_id": actor_id,
        "actor_label": ctx.get("actor_label"),
        "request_id": ctx.get("request_id"),
        "impersonation_id": impersonation_id,
    }
```

Modify `_write_audit` (currently around lines 77–120) to filter `impersonation_id` from the values dict when writing to `PlatformAuditLog`. Locate this block:

```python
    model_cls = PlatformAuditLog if is_platform else TenantAuditLog
    connection.execute(
        insert(model_cls).values(
            id=uuid.uuid4(),
            table_name=target.__tablename__,
            record_id=record_id,
            operation=operation,
            before_state=before_state,
            after_state=after_state,
            occurred_at=datetime.now(UTC),
            **ctx,
        )
    )
```

Replace with:

```python
    model_cls = PlatformAuditLog if is_platform else TenantAuditLog
    values_ctx = dict(ctx)
    # PlatformAuditLog has no impersonation_id column (only TenantAuditLog does).
    # Drop the key for platform writes so SQLAlchemy doesn't bind a non-existent
    # column.
    if is_platform:
        values_ctx.pop("impersonation_id", None)
    connection.execute(
        insert(model_cls).values(
            id=uuid.uuid4(),
            table_name=target.__tablename__,
            record_id=record_id,
            operation=operation,
            before_state=before_state,
            after_state=after_state,
            occurred_at=datetime.now(UTC),
            **values_ctx,
        )
    )
```

- [ ] **Step 4: Run tests — they should pass**

```bash
make test-fast T=tests/core/audit/test_impersonation_propagation.py
```
Expected: both tests pass.

Then sanity-check no other audit-touching tests regressed:

```bash
make test-fast T=tests/core/audit/
make test-fast T=tests/platform_/impersonations/
```
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add app/core/audit/mixin.py tests/core/audit/test_impersonation_propagation.py
git commit -m "feat(audit): propagate impersonation_id from contextvars to tenant.audit_log"
```

---

## Task 3: Tenant deps bind `impersonation_id` contextvar

**Files:**
- Create: `tests/modules/iam/test_tenant_dep_impersonation.py`
- Modify: `app/modules/iam/dependencies.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/iam/test_tenant_dep_impersonation.py
"""Both tenant deps (stub + JWT) bind impersonation_id to structlog
contextvars when the resolved TenantUser has a non-null impersonation_id.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan
from app.modules.iam.dependencies import get_current_tenant_user_stub
from app.modules.iam.tenant_users.models import TenantUser


async def _seed_shadow(
    factory: async_sessionmaker[AsyncSession],
    impersonation_id: uuid.UUID,
) -> uuid.UUID:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        u = TenantUser(
            email=f"imp.{impersonation_id.hex[:12]}@platform.local",
            full_name="Shadow",
            is_active=True,
            is_admin=True,
            impersonation_id=impersonation_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u.id


async def test_stub_dep_binds_impersonation_id(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    imp_id = uuid.uuid4()
    user_id = await _seed_shadow(factory, imp_id)
    try:
        # Call the dep directly. It binds contextvars as a side effect.
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            await get_current_tenant_user_stub(
                x_tenant_actor_id=str(user_id), session=s
            )
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("impersonation_id") == str(imp_id)
    finally:
        structlog.contextvars.clear_contextvars()
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            await s.execute(text("DELETE FROM tenant_users"))
            await s.execute(text("DELETE FROM audit_log"))


async def test_stub_dep_does_not_bind_for_real_user(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        u = TenantUser(
            email=f"u-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Real", is_active=True, is_admin=False,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    user_id = u.id
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            await get_current_tenant_user_stub(
                x_tenant_actor_id=str(user_id), session=s
            )
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("impersonation_id") is None
    finally:
        structlog.contextvars.clear_contextvars()
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            await s.execute(text("DELETE FROM tenant_users"))
            await s.execute(text("DELETE FROM audit_log"))
```

- [ ] **Step 2: Run — expected to fail**

```bash
make test-fast T=tests/modules/iam/test_tenant_dep_impersonation.py
```
Expected: first test fails — `impersonation_id` contextvar is unset.

- [ ] **Step 3: Extend `get_current_tenant_user_stub` and `get_current_tenant_user_jwt`**

Open `app/modules/iam/dependencies.py`. In `get_current_tenant_user_stub`, find the existing `bind_contextvars` block (around lines 143–148):

```python
    structlog.contextvars.bind_contextvars(
        actor_type="tenant_user",
        actor_id=str(user.id),
        actor_label=user.email,
    )
```

Replace with:

```python
    bind_kwargs: dict[str, str] = {
        "actor_type": "tenant_user",
        "actor_id": str(user.id),
        "actor_label": user.email,
    }
    if user.impersonation_id is not None:
        bind_kwargs["impersonation_id"] = str(user.impersonation_id)
        # Annotate the label so log lines and audit show this is impersonation.
        bind_kwargs["actor_label"] = f"{user.email} (impersonating)"
    structlog.contextvars.bind_contextvars(**bind_kwargs)
```

Apply the same change to `get_current_tenant_user_jwt` (around lines 212–216).

- [ ] **Step 4: Run tests — they should pass**

```bash
make test-fast T=tests/modules/iam/test_tenant_dep_impersonation.py
make test-fast T=tests/modules/iam/
```
Expected: green, no regressions in the existing tenant-user dep tests.

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/dependencies.py tests/modules/iam/test_tenant_dep_impersonation.py
git commit -m "feat(iam): tenant deps bind impersonation_id contextvar for shadow users"
```

---

## Task 4: Custom exceptions + schema additions

**Files:**
- Create: `app/platform_/impersonations/exceptions.py`
- Modify: `app/platform_/impersonations/schemas.py`

- [ ] **Step 1: Write the exceptions module**

```python
# app/platform_/impersonations/exceptions.py
"""Exceptions raised by ImpersonationService."""
from __future__ import annotations


class ImpersonationGone(Exception):
    """The impersonation has ended, been revoked, or expired.

    Mapped to HTTP 410 by the API layer.
    """


class ImpersonationNotActive(Exception):
    """The impersonation row exists but is not yet usable (no approval has
    executed yet, or the row is in a transient state).

    Mapped to HTTP 409 by the API layer.
    """
```

- [ ] **Step 2: Add the mint response schema**

In `app/platform_/impersonations/schemas.py`, append:

```python
class MintTenantTokenOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int  # seconds (access TTL)
    tenant_slug: str
    impersonation_id: uuid.UUID
    impersonation_expires_at: datetime
```

- [ ] **Step 3: Commit**

```bash
git add app/platform_/impersonations/exceptions.py app/platform_/impersonations/schemas.py
git commit -m "feat(impersonation): exceptions module + MintTenantTokenOut schema"
```

---

## Task 5: `ImpersonationService.mint_tenant_token` + shadow user lazy creation

This is the most architecturally complex task. The mint method runs in the **platform** session but must write the shadow tenant_user into the **tenant** schema, then mint tokens. It opens a secondary `AsyncSession` bound to the tenant schema for the cross-schema work.

**Files:**
- Create: `tests/platform_/impersonations/test_mint_and_shadow.py`
- Modify: `app/platform_/impersonations/service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/platform_/impersonations/test_mint_and_shadow.py
"""mint_tenant_token: lazily provisions the shadow tenant_user on first call,
reuses it on subsequent calls, idempotent, gone-on-revoke/end/expire.
"""
from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.platform_.impersonations.executors  # noqa: F401 — register executor
from app.modules.iam.tenant_users.models import TenantUser
from app.modules.maker_checker.service import ApprovalService
from app.platform_.impersonations.exceptions import ImpersonationGone
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.service import ImpersonationService
from app.platform_.models import PlatformUser, Tenant


# These tests need real signing keys to mint actual tokens. Each test seeds
# one via KeyService.generate_and_insert.
async def _seed_signing_key(factory: async_sessionmaker[AsyncSession]) -> None:
    from app.modules.iam.keys.service import KeyService, clear_key_caches

    clear_key_caches()
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await KeyService(s).generate_and_insert(audience="tenant", algorithm="RS256")


async def _seed(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[PlatformUser, PlatformUser, Tenant]:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        maker = PlatformUser(
            email=f"maker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Jane Maker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        checker = PlatformUser(
            email=f"checker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Pat Checker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        # The test schema is tenant_test (set up by conftest)
        tenant = Tenant(
            slug="test-tenant",  # matches TEST_TENANT_SLUG in conftest
            schema_name="tenant_test",
            name="Test Tenant",
            is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add_all([maker, checker, tenant])
    return maker, checker, tenant


async def _approve_request(
    factory: async_sessionmaker[AsyncSession],
    maker_id: uuid.UUID,
    checker_id: uuid.UUID,
    tenant_id: uuid.UUID,
    reason: str = "Investigating member balance issue reported by ops",
) -> uuid.UUID:
    """Create impersonation request and approve it. Returns impersonation_id."""
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        approval = await ImpersonationService(s).request(
            platform_user_id=maker_id, tenant_id=tenant_id, reason=reason,
        )
        approval_id = approval.id

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        executed = await ApprovalService(s).approve(
            request_id=approval_id, actor_user_id=checker_id,
        )
        return uuid.UUID(executed.execution_result["impersonation_id"])  # type: ignore[index]


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
        await s.execute(text("DELETE FROM platform.jwt_signing_keys"))
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        await s.execute(text("DELETE FROM tenant_sessions"))
        await s.execute(text("DELETE FROM tenant_users"))
        await s.execute(text("DELETE FROM audit_log"))


async def test_mint_creates_shadow_user_first_call(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_signing_key(factory)
    maker, checker, tenant = await _seed(factory)
    imp_id = await _approve_request(factory, maker.id, checker.id, tenant.id)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            result = await ImpersonationService(s).mint_tenant_token(
                impersonation_id=imp_id, user_agent="pytest", ip_address="127.0.0.1",
            )
            assert result.access_token
            assert result.refresh_token
            assert result.tenant_slug == tenant.slug
            assert result.impersonation_id == imp_id
            assert result.expires_in > 0

        # Verify shadow tenant_user exists with impersonation_id set
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            shadow = await s.scalar(
                select(TenantUser).where(TenantUser.impersonation_id == imp_id)
            )
            assert shadow is not None
            assert shadow.is_admin is True
            assert shadow.hashed_password is None
            assert shadow.is_active is True
            assert shadow.email.startswith(f"imp.{imp_id.hex[:12]}")

        # Verify the impersonation row was updated with tenant_user_id
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, imp_id)
            assert row is not None
            assert row.tenant_user_id == shadow.id
    finally:
        await _cleanup(factory)


async def test_mint_reuses_shadow_user_on_subsequent_calls(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_signing_key(factory)
    maker, checker, tenant = await _seed(factory)
    imp_id = await _approve_request(factory, maker.id, checker.id, tenant.id)
    try:
        # Mint twice
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            r1 = await ImpersonationService(s).mint_tenant_token(
                impersonation_id=imp_id, user_agent="ua1", ip_address="1.1.1.1",
            )
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            r2 = await ImpersonationService(s).mint_tenant_token(
                impersonation_id=imp_id, user_agent="ua2", ip_address="2.2.2.2",
            )
        # Tokens differ (different JTIs) but slug + imp_id are stable
        assert r1.access_token != r2.access_token
        assert r1.tenant_slug == r2.tenant_slug
        assert r1.impersonation_id == r2.impersonation_id

        # Only one shadow user exists
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            rows = (
                await s.execute(
                    select(TenantUser).where(TenantUser.impersonation_id == imp_id)
                )
            ).scalars().all()
            assert len(rows) == 1
    finally:
        await _cleanup(factory)


async def test_mint_rejects_when_ended(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_signing_key(factory)
    maker, checker, tenant = await _seed(factory)
    imp_id = await _approve_request(factory, maker.id, checker.id, tenant.id)
    # Force-end the impersonation
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        await ImpersonationService(s).end(impersonation_id=imp_id, ended_by=maker.id)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            with pytest.raises(ImpersonationGone):
                await ImpersonationService(s).mint_tenant_token(
                    impersonation_id=imp_id, user_agent="x", ip_address="x",
                )
    finally:
        await _cleanup(factory)


async def test_mint_rejects_when_expired(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_signing_key(factory)
    maker, checker, tenant = await _seed(factory)
    imp_id = await _approve_request(factory, maker.id, checker.id, tenant.id)
    # Force-expire by setting expires_at in the past
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(
            text(
                "UPDATE platform.support_impersonations "
                "SET expires_at = now() - interval '1 minute' "
                "WHERE id = :id"
            ),
            {"id": imp_id},
        )
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            with pytest.raises(ImpersonationGone):
                await ImpersonationService(s).mint_tenant_token(
                    impersonation_id=imp_id, user_agent="x", ip_address="x",
                )
    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Run — expected to fail (no `mint_tenant_token` yet)**

```bash
make test-fast T=tests/platform_/impersonations/test_mint_and_shadow.py
```
Expected: `AttributeError: 'ImpersonationService' object has no attribute 'mint_tenant_token'`.

- [ ] **Step 3: Implement `mint_tenant_token`**

Open `app/platform_/impersonations/service.py`. Add these imports at the top of the file:

```python
from sqlalchemy import text as sql_text

from app.core.db import AsyncSessionFactory
from app.modules.iam.keys.service import KeyService
from app.modules.iam.sessions.models import TenantSession
from app.modules.iam.sessions.service import SessionService
from app.modules.iam.tenant_users.models import TenantUser
from app.modules.iam.tokens.service import (
    encode_access_token,
    encode_refresh_token,
)
from app.platform_.impersonations.exceptions import ImpersonationGone
from app.platform_.impersonations.schemas import MintTenantTokenOut
from app.platform_.models import PlatformUser
```

Add the method to `ImpersonationService`:

```python
    async def mint_tenant_token(
        self,
        *,
        impersonation_id: uuid.UUID,
        user_agent: str | None,
        ip_address: str | None,
        redis: object | None = None,
    ) -> MintTenantTokenOut:
        """Mint a tenant access+refresh token pair for an active impersonation.

        Side effects:
        - Lazily creates the shadow tenant_user on first call (idempotent).
        - Creates a tenant_sessions row + Redis JTI key.
        - Updates support_impersonations.tenant_user_id on first call.

        Raises:
            ValueError: impersonation not found
            ImpersonationGone: ended, revoked, or expired
        """
        imp = await self._session.get(SupportImpersonation, impersonation_id)
        if imp is None:
            raise ValueError(f"Impersonation {impersonation_id} not found")
        if imp.ended_at is not None or imp.revoked_at is not None:
            raise ImpersonationGone("Impersonation has ended or been revoked")
        if imp.expires_at <= datetime.now(UTC):
            raise ImpersonationGone("Impersonation has expired")

        tenant = await self._session.get(Tenant, imp.tenant_id)
        if tenant is None or not tenant.is_active:
            raise ValueError(f"Tenant {imp.tenant_id} unavailable")

        platform_user = await self._session.get(PlatformUser, imp.platform_user_id)
        if platform_user is None:
            raise ValueError(f"Platform user {imp.platform_user_id} not found")

        # Fetch signing material BEFORE opening the secondary session — the
        # KeyService reads from the platform schema and we already hold that.
        kid, private_key_pem, algorithm = await KeyService(
            self._session
        ).get_active_signing_key("tenant")

        settings = get_settings()
        audience = f"tenant:{tenant.slug}"

        # Cross-schema work: a new session bound to the tenant's schema.
        # Validation of schema_name was performed when the tenant was created.
        shadow_id: uuid.UUID
        access_token: str
        refresh_token: str
        async with AsyncSessionFactory() as tenant_db:
            await tenant_db.execute(
                sql_text(
                    f"SET LOCAL search_path TO {tenant.schema_name}, platform"
                )
            )

            # Look up or create shadow tenant_user.
            shadow = await tenant_db.scalar(
                select(TenantUser).where(
                    TenantUser.impersonation_id == impersonation_id
                )
            )
            if shadow is None:
                shadow = TenantUser(
                    email=f"imp.{impersonation_id.hex[:12]}@platform.local",
                    full_name=(
                        f"{platform_user.full_name} "
                        f"(Platform Admin Impersonation)"
                    ),
                    is_active=True,
                    is_admin=True,
                    hashed_password=None,
                    impersonation_id=impersonation_id,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                tenant_db.add(shadow)
                await tenant_db.flush()
            elif not shadow.is_active:
                shadow.is_active = True
            shadow_id = shadow.id

            # Create the tenant session row.
            jti = str(uuid.uuid4())
            sess_row = await SessionService(
                tenant_db, TenantSession, redis=redis
            ).create(
                user_id=shadow.id,
                jti=jti,
                user_agent=user_agent,
                ip_address=ip_address,
                refresh_ttl_seconds=settings.jwt_refresh_ttl_tenant_seconds,
            )
            await tenant_db.flush()

            access_token = encode_access_token(
                sub=str(shadow.id),
                audience=audience,
                session_id=str(sess_row.id),
                actor_type="tenant_user",
                kid=kid,
                private_key_pem=private_key_pem,
                algorithm=algorithm,
                ttl_seconds=settings.jwt_access_ttl_seconds,
            )
            refresh_token = encode_refresh_token(
                sub=str(shadow.id),
                audience=audience,
                session_id=str(sess_row.id),
                jti=jti,
                kid=kid,
                private_key_pem=private_key_pem,
                algorithm=algorithm,
                ttl_seconds=settings.jwt_refresh_ttl_tenant_seconds,
            )
            await tenant_db.commit()

        # Back in the platform session: link the shadow into the impersonation row.
        if imp.tenant_user_id is None:
            imp.tenant_user_id = shadow_id

        return MintTenantTokenOut(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_ttl_seconds,
            tenant_slug=tenant.slug,
            impersonation_id=impersonation_id,
            impersonation_expires_at=imp.expires_at,
        )
```

- [ ] **Step 4: Extend `end` and `revoke` to deactivate the shadow + revoke sessions**

Find the existing `end` and `revoke` methods. Replace them with versions that also clean up the tenant-side state.

Replace the `end` method body with:

```python
        row = await self._session.get(SupportImpersonation, impersonation_id)
        if row is None:
            raise ValueError(f"Impersonation {impersonation_id} not found")
        if row.ended_at is not None or row.revoked_at is not None:
            return row
        row.ended_at = datetime.now(UTC)
        row.ended_by = ended_by
        await self._deactivate_shadow_and_revoke_sessions(row)
        return row
```

Replace the `revoke` method body with:

```python
        row = await self._session.get(SupportImpersonation, impersonation_id)
        if row is None:
            raise ValueError(f"Impersonation {impersonation_id} not found")
        if row.revoked_at is not None or row.ended_at is not None:
            return row
        row.revoked_at = datetime.now(UTC)
        row.revoked_by = revoked_by
        await self._deactivate_shadow_and_revoke_sessions(row)
        return row
```

Add the private helper:

```python
    async def _deactivate_shadow_and_revoke_sessions(
        self, row: SupportImpersonation
    ) -> None:
        """Flip the shadow tenant_user inactive and revoke its tenant sessions.

        Runs in a secondary tenant-scoped session for cross-schema work.
        No-op if no shadow user has been minted yet (tenant_user_id IS NULL).
        """
        if row.tenant_user_id is None:
            return

        tenant = await self._session.get(Tenant, row.tenant_id)
        if tenant is None:
            return  # tenant gone; nothing to clean up

        async with AsyncSessionFactory() as tenant_db:
            await tenant_db.execute(
                sql_text(
                    f"SET LOCAL search_path TO {tenant.schema_name}, platform"
                )
            )
            shadow = await tenant_db.get(TenantUser, row.tenant_user_id)
            if shadow is not None and shadow.is_active:
                shadow.is_active = False
                shadow.updated_at = datetime.now(UTC)
            # Revoke every session belonging to the shadow user.
            await SessionService(
                tenant_db, TenantSession, redis=None
            ).revoke_all_for_user(row.tenant_user_id)
            await tenant_db.commit()
```

- [ ] **Step 5: Run the mint tests — should pass**

```bash
make test-fast T=tests/platform_/impersonations/test_mint_and_shadow.py
```
Expected: 4 tests pass.

Also re-run the existing service tests to confirm the modified `end` and `revoke` still pass with the new shadow-cleanup helper:

```bash
make test-fast T=tests/platform_/impersonations/test_service.py
```
Expected: 7 tests pass (`end` and `revoke` tests now exercise the no-op branch where `tenant_user_id IS NULL`).

- [ ] **Step 6: Commit**

```bash
git add app/platform_/impersonations/service.py \
        tests/platform_/impersonations/test_mint_and_shadow.py
git commit -m "feat(impersonation): mint_tenant_token + shadow user lazy creation + cleanup on end/revoke"
```

---

## Task 6: API router

**Files:**
- Create: `tests/platform_/impersonations/test_api.py`
- Create: `app/platform_/impersonations/api.py`

- [ ] **Step 1: Write failing API tests**

```python
# tests/platform_/impersonations/test_api.py
"""HTTP integration tests for /platform/impersonations/*.

Uses stub auth + the platform session override pattern from
tests/platform_/billing/test_api_invoices.py.

Note: the mint-tenant-token endpoint requires a real signing key in the DB.
The dedicated end-to-end test in test_end_to_end.py exercises that path.
These tests focus on the lifecycle endpoints (submit/list/get/end/revoke).
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.platform_.impersonations.executors  # noqa: F401
from app.core.db import get_platform_session
from app.main import app, lifespan
from app.modules.maker_checker.service import ApprovalService
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.service import ImpersonationService
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


async def _approve(
    factory: async_sessionmaker[AsyncSession],
    maker_id: uuid.UUID, checker_id: uuid.UUID, tenant_id: uuid.UUID,
) -> uuid.UUID:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        approval = await ImpersonationService(s).request(
            platform_user_id=maker_id, tenant_id=tenant_id,
            reason="Investigating reported issue with member balance",
        )
        approval_id = approval.id
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        executed = await ApprovalService(s).approve(
            request_id=approval_id, actor_user_id=checker_id,
        )
        return uuid.UUID(executed.execution_result["impersonation_id"])  # type: ignore[index]


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


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


async def test_post_submit_returns_approval_request(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, _checker, tenant = await _seed(factory)
    try:
        r = await client.post(
            "/platform/impersonations",
            json={
                "tenant_id": str(tenant.id),
                "reason": "Investigating member balance reported by tenant admin",
            },
            headers=_hdr(maker.id),
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert "approval_request_id" in body
        assert body["status"] == "pending_approval"
    finally:
        await _cleanup(factory)


async def test_post_submit_rejects_short_reason(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, _, tenant = await _seed(factory)
    try:
        r = await client.post(
            "/platform/impersonations",
            json={"tenant_id": str(tenant.id), "reason": "short"},
            headers=_hdr(maker.id),
        )
        # Pydantic rejects at the validator layer
        assert r.status_code == 422, r.text
    finally:
        await _cleanup(factory)


async def test_get_active_returns_only_mine(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    other = await _seed_extra_user(factory)
    await _approve(factory, maker.id, checker.id, tenant.id)
    await _approve_with_actor(factory, other.id, checker.id, tenant.id)
    try:
        r = await client.get("/platform/impersonations/active", headers=_hdr(maker.id))
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["platform_user_id"] == str(maker.id)
    finally:
        await _cleanup(factory)


async def test_get_all_returns_every_active(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    other = await _seed_extra_user(factory)
    await _approve(factory, maker.id, checker.id, tenant.id)
    await _approve_with_actor(factory, other.id, checker.id, tenant.id)
    try:
        r = await client.get("/platform/impersonations/all", headers=_hdr(maker.id))
        assert r.status_code == 200
        assert len(r.json()) == 2
    finally:
        await _cleanup(factory)


async def test_delete_marks_ended_by_owner(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    imp_id = await _approve(factory, maker.id, checker.id, tenant.id)
    try:
        r = await client.delete(
            f"/platform/impersonations/{imp_id}", headers=_hdr(maker.id),
        )
        assert r.status_code == 204, r.text

        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, imp_id)
            assert row is not None
            assert row.ended_at is not None
            assert row.ended_by == maker.id
    finally:
        await _cleanup(factory)


async def test_delete_rejects_non_owner(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    other = await _seed_extra_user(factory)
    imp_id = await _approve(factory, maker.id, checker.id, tenant.id)
    try:
        r = await client.delete(
            f"/platform/impersonations/{imp_id}", headers=_hdr(other.id),
        )
        assert r.status_code == 403, r.text
    finally:
        await _cleanup(factory)


async def test_revoke_by_other_user(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    revoker = await _seed_extra_user(factory)
    imp_id = await _approve(factory, maker.id, checker.id, tenant.id)
    try:
        r = await client.post(
            f"/platform/impersonations/{imp_id}/revoke",
            json={"reason": "policy violation"},
            headers=_hdr(revoker.id),
        )
        assert r.status_code == 204, r.text
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, imp_id)
            assert row is not None
            assert row.revoked_at is not None
            assert row.revoked_by == revoker.id
    finally:
        await _cleanup(factory)


# helpers used above ----------------------------------------------------------

async def _seed_extra_user(
    factory: async_sessionmaker[AsyncSession],
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"x-{uuid.uuid4().hex[:6]}@test.example",
            full_name="X", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _approve_with_actor(
    factory: async_sessionmaker[AsyncSession],
    actor_id: uuid.UUID, checker_id: uuid.UUID, tenant_id: uuid.UUID,
) -> uuid.UUID:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        approval = await ImpersonationService(s).request(
            platform_user_id=actor_id, tenant_id=tenant_id,
            reason="Investigating reported issue with member balance",
        )
        approval_id = approval.id
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        executed = await ApprovalService(s).approve(
            request_id=approval_id, actor_user_id=checker_id,
        )
        return uuid.UUID(executed.execution_result["impersonation_id"])  # type: ignore[index]
```

- [ ] **Step 2: Write the API router**

```python
# app/platform_/impersonations/api.py
"""HTTP API for /platform/impersonations/*.

Endpoints:
    POST   /platform/impersonations                        — submit (maker-checker)
    GET    /platform/impersonations/active                 — list mine
    GET    /platform/impersonations/all                    — list all (admin)
    GET    /platform/impersonations/{id}                   — detail
    DELETE /platform/impersonations/{id}                   — end (owner only)
    POST   /platform/impersonations/{id}/revoke            — revoke (admin)
    POST   /platform/impersonations/{id}/mint-tenant-token — mint a tenant JWT pair

Role gating (admin / superuser) currently delegates to the existing
get_current_superuser dep. When P1.7-05 ships 4-tier roles, swap the
`get_all` and `revoke` deps to require role>=admin without changing
call sites.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.platform_.auth import (
    CurrentPlatformUser,
    CurrentSuperuser,
)
from app.platform_.impersonations.exceptions import (
    ImpersonationGone,
    ImpersonationNotActive,
)
from app.platform_.impersonations.schemas import (
    ImpersonationOut,
    ImpersonationStartIn,
    MintTenantTokenOut,
)
from app.platform_.impersonations.service import ImpersonationService

router = APIRouter(prefix="/platform/impersonations", tags=["platform-impersonations"])

Session = Annotated[AsyncSession, Depends(get_platform_session)]


class _SubmitOut(BaseModel):
    approval_request_id: uuid.UUID
    status: str


class _RevokeIn(BaseModel):
    reason: str = ""


@router.post("", response_model=_SubmitOut, status_code=202)
async def submit_impersonation(
    body: ImpersonationStartIn,
    session: Session,
    user: CurrentPlatformUser,
) -> _SubmitOut:
    try:
        approval = await ImpersonationService(session).request(
            platform_user_id=user.id,
            tenant_id=body.tenant_id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return _SubmitOut(
        approval_request_id=approval.id, status="pending_approval"
    )


@router.get("/active", response_model=list[ImpersonationOut])
async def list_active_mine(
    session: Session, user: CurrentPlatformUser,
) -> list[ImpersonationOut]:
    rows = await ImpersonationService(session).get_active_for_user(
        platform_user_id=user.id
    )
    return [ImpersonationOut.model_validate(r) for r in rows]


@router.get("/all", response_model=list[ImpersonationOut])
async def list_all_active(
    session: Session, _user: CurrentSuperuser,
) -> list[ImpersonationOut]:
    rows = await ImpersonationService(session).get_all_active()
    return [ImpersonationOut.model_validate(r) for r in rows]


@router.get("/{impersonation_id}", response_model=ImpersonationOut)
async def get_impersonation(
    impersonation_id: uuid.UUID,
    session: Session,
    _user: CurrentPlatformUser,
) -> ImpersonationOut:
    row = await ImpersonationService(session).get_by_id(impersonation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Impersonation not found")
    return ImpersonationOut.model_validate(row)


@router.delete("/{impersonation_id}", status_code=204)
async def end_impersonation(
    impersonation_id: uuid.UUID,
    session: Session,
    user: CurrentPlatformUser,
) -> Response:
    svc = ImpersonationService(session)
    row = await svc.get_by_id(impersonation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Impersonation not found")
    if row.platform_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the impersonator can end this session (use /revoke instead)",
        )
    await svc.end(impersonation_id=impersonation_id, ended_by=user.id)
    await session.commit()
    return Response(status_code=204)


@router.post("/{impersonation_id}/revoke", status_code=204)
async def revoke_impersonation(
    impersonation_id: uuid.UUID,
    body: _RevokeIn,
    session: Session,
    user: CurrentSuperuser,
) -> Response:
    svc = ImpersonationService(session)
    row = await svc.get_by_id(impersonation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Impersonation not found")
    await svc.revoke(impersonation_id=impersonation_id, revoked_by=user.id)
    await session.commit()
    return Response(status_code=204)


@router.post(
    "/{impersonation_id}/mint-tenant-token", response_model=MintTenantTokenOut
)
async def mint_tenant_token(
    impersonation_id: uuid.UUID,
    request: Request,
    session: Session,
    user: CurrentPlatformUser,
) -> MintTenantTokenOut:
    svc = ImpersonationService(session)
    row = await svc.get_by_id(impersonation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Impersonation not found")
    if row.platform_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the impersonator can mint a token for this session",
        )
    redis = getattr(request.app.state, "redis", None)
    try:
        return await svc.mint_tenant_token(
            impersonation_id=impersonation_id,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
            redis=redis,
        )
    except ImpersonationGone as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ImpersonationNotActive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 3: Mount the router**

In `app/main.py`, add the import alongside the other platform imports:

```python
from app.platform_.impersonations.api import router as impersonations_router
```

Add the mount line after `platform_users_router`:

```python
app.include_router(impersonations_router)
```

- [ ] **Step 4: Run API tests — they should pass**

```bash
make test-fast T=tests/platform_/impersonations/test_api.py
```
Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/platform_/impersonations/api.py app/main.py \
        tests/platform_/impersonations/test_api.py
git commit -m "feat(impersonation): API router + 6 endpoints"
```

---

## Task 7: End-to-end cross-context test

This test exercises the entire happy path against the real FastAPI app: request → approve → mint → use the minted token (via stub auth, since the test schema lacks a real RS256 setup) → end → 401. The audit_log assertion is the critical observation that proves the cross-cutting wiring works.

**Files:**
- Create: `tests/platform_/impersonations/test_end_to_end.py`

- [ ] **Step 1: Write the e2e test**

```python
# tests/platform_/impersonations/test_end_to_end.py
"""End-to-end cross-context flow:
    1. Maker submits impersonation request
    2. Checker approves via /platform/approvals/{id}/approve
    3. Maker mints a tenant token
    4. Shadow tenant_user exists with impersonation_id set
    5. Using stub auth against the shadow user, /members responds
    6. The audit_log row for the member registration has impersonation_id set
    7. Maker DELETEs the impersonation
    8. Shadow user is_active=False; tenant sessions revoked
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.platform_.impersonations.executors  # noqa: F401
from app.core.audit.models import TenantAuditLog
from app.core.db import get_platform_session, get_tenant_session
from app.main import app, lifespan
from app.modules.iam.tenant_users.models import TenantUser
from app.platform_.impersonations.models import SupportImpersonation
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


def _make_tenant_session_override(engine: AsyncEngine, schema: str):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {schema}, platform")
            )
            yield session

    return _override


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_platform_session] = (
        _make_platform_session_override(test_engine)
    )
    app.dependency_overrides[get_tenant_session] = (
        _make_tenant_session_override(test_engine, "tenant_test")
    )
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)
    app.dependency_overrides.pop(get_tenant_session, None)


async def _seed_signing_key(factory: async_sessionmaker[AsyncSession]) -> None:
    from app.modules.iam.keys.service import KeyService, clear_key_caches

    clear_key_caches()
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await KeyService(s).generate_and_insert(audience="tenant", algorithm="RS256")


async def _seed_platform_actors(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[PlatformUser, PlatformUser, Tenant]:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        maker = PlatformUser(
            email=f"maker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Jane Maker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        checker = PlatformUser(
            email=f"checker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Pat Checker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        tenant = Tenant(
            slug="test-tenant", schema_name="tenant_test", name="T",
            is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add_all([maker, checker, tenant])
    return maker, checker, tenant


async def _cleanup_all(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.support_impersonations"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.execute(text("DELETE FROM platform.jwt_signing_keys"))
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        await s.execute(text("DELETE FROM members"))
        await s.execute(text("DELETE FROM tenant_sessions"))
        await s.execute(text("DELETE FROM tenant_users"))
        await s.execute(text("DELETE FROM audit_log"))


async def test_full_cross_context_flow(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_signing_key(factory)
    maker, checker, tenant = await _seed_platform_actors(factory)
    try:
        # 1. Submit
        sub = await client.post(
            "/platform/impersonations",
            json={
                "tenant_id": str(tenant.id),
                "reason": "Investigating member balance reported by tenant admin",
            },
            headers={"X-Platform-Actor-ID": str(maker.id)},
        )
        assert sub.status_code == 202, sub.text
        approval_id = sub.json()["approval_request_id"]

        # 2. Approve
        apr = await client.post(
            f"/platform/approvals/{approval_id}/approve",
            json={"comment": "ticket verified"},
            headers={"X-Platform-Actor-ID": str(checker.id)},
        )
        assert apr.status_code == 200, apr.text
        assert apr.json()["status"] == "executed"
        imp_id = uuid.UUID(apr.json()["execution_result"]["impersonation_id"])

        # 3. Mint
        mint = await client.post(
            f"/platform/impersonations/{imp_id}/mint-tenant-token",
            headers={"X-Platform-Actor-ID": str(maker.id)},
        )
        assert mint.status_code == 200, mint.text
        # We won't use the JWT in the test (the stub auth is in effect),
        # but the mint must have produced one.
        assert mint.json()["access_token"]
        assert mint.json()["tenant_slug"] == tenant.slug

        # 4. Shadow tenant_user exists
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            shadow = await s.scalar(
                select(TenantUser).where(TenantUser.impersonation_id == imp_id)
            )
            assert shadow is not None
            shadow_id = shadow.id

        # 5. Use the shadow identity via stub auth to register a member
        reg = await client.post(
            "/members",
            json={
                "full_name": "Mary Test",
                "date_of_birth": "1990-01-01",
                "gender": "F",
            },
            headers={
                "X-Tenant-Slug": tenant.slug,
                "X-Tenant-Actor-ID": str(shadow_id),
            },
        )
        assert reg.status_code == 201, reg.text

        # 6. Audit row for the registration carries impersonation_id
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            audit_rows = (
                await s.execute(
                    select(TenantAuditLog)
                    .where(TenantAuditLog.table_name == "members")
                    .order_by(TenantAuditLog.occurred_at.desc())
                    .limit(1)
                )
            ).scalars().all()
            assert audit_rows, "no audit row for member insert"
            assert audit_rows[0].impersonation_id == imp_id
            assert audit_rows[0].actor_type == "tenant_user"
            assert audit_rows[0].actor_id == shadow_id

        # 7. End
        end = await client.delete(
            f"/platform/impersonations/{imp_id}",
            headers={"X-Platform-Actor-ID": str(maker.id)},
        )
        assert end.status_code == 204, end.text

        # 8. Shadow inactive; sessions revoked
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            shadow2 = await s.get(TenantUser, shadow_id)
            assert shadow2 is not None
            assert shadow2.is_active is False
            revoked_count = await s.scalar(
                text(
                    "SELECT COUNT(*) FROM tenant_sessions "
                    "WHERE tenant_user_id = :uid AND revoked_at IS NOT NULL"
                ),
                {"uid": shadow_id},
            )
            assert revoked_count and revoked_count > 0

        # Subsequent stub-auth request as the shadow returns 403 (inactive)
        reg2 = await client.post(
            "/members",
            json={
                "full_name": "Late Mary",
                "date_of_birth": "1990-01-01",
                "gender": "F",
            },
            headers={
                "X-Tenant-Slug": tenant.slug,
                "X-Tenant-Actor-ID": str(shadow_id),
            },
        )
        assert reg2.status_code == 403, reg2.text
    finally:
        await _cleanup_all(factory)
```

- [ ] **Step 2: Run the e2e test**

```bash
make test-fast T=tests/platform_/impersonations/test_end_to_end.py
```
Expected: PASS.

If this test fails, the failure mode is the most informative diagnostic for the whole 02b sub-plan — typical causes:
- Mint endpoint cannot find an active signing key → `_seed_signing_key` didn't run or KeyService API changed.
- Tenant dep didn't bind `impersonation_id` → Task 3 incomplete.
- Audit row missing `impersonation_id` → Task 2 incomplete.
- Subsequent stub-auth request returns 401 instead of 403 → the tenant stub's `is_active` check should turn deactivated shadows into 403 per the existing stub code.

- [ ] **Step 3: Commit**

```bash
git add tests/platform_/impersonations/test_end_to_end.py
git commit -m "test(impersonation): end-to-end cross-context flow"
```

---

## Task 8: CLAUDE.md — full Impersonation contracts

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace the partial subsection with the full one**

In `CLAUDE.md`, find the `## Impersonation contracts (do not violate)` section added by 02a (Task 10). Replace its entire body with:

```markdown
## Impersonation contracts (do not violate)

### Data layer (from 02a, unchanged)

- `platform.support_impersonations` rows are created **only** by the
  `platform.start_impersonation` maker-checker executor. Direct insertion is
  forbidden. Direct UPDATE is forbidden except via `ImpersonationService.end()`
  and `ImpersonationService.revoke()`.
- `ImpersonationService.request()` is the only path to submitting a
  `platform.start_impersonation` approval. Reason must be at least 10 chars.
  Tenant must be active at request time.
- Self-approval is rejected by `ApprovalService.approve()`.
- Default required-approvals quorum is `IMPERSONATION_DEFAULT_REQUIRED_APPROVALS`
  (settings; default 1).
- `IMPERSONATION_MAX_MINUTES` (default 30) caps the session duration. Sessions
  expire automatically — no Celery beat job required.
- A row in `ended` or `revoked` state is terminal — the
  `ck_support_impersonations_not_both_ended_and_revoked` constraint disallows
  setting both. Re-impersonation requires a new approval cycle.
- `ApprovalService._execute` enriches the executor payload with
  `approval_request_id`. Executors must treat that key as reserved.

### HTTP + auth + audit (added in 02b)

- The `/platform/impersonations/*` router in
  `app/platform_/impersonations/api.py` is the only HTTP surface for the
  impersonation lifecycle. Direct service calls from outside this router
  or the executor are forbidden.
- `POST /platform/impersonations/{id}/mint-tenant-token` is the only path
  to obtain a tenant access token via impersonation. The endpoint is
  restricted to the original impersonator (platform_user_id match).
- Shadow `tenant_users` rows are auto-provisioned by
  `ImpersonationService.mint_tenant_token` on the first mint for an
  impersonation. They have `hashed_password=NULL`, `is_admin=true`,
  `is_active=true`, and `impersonation_id` set to the link. They cannot
  self-login (no password). They are reused for subsequent mints during
  the same impersonation.
- `tenant_users` listing endpoints (P1.7-04 / portal sub-plan 32) MUST
  filter `impersonation_id IS NULL` so shadows are invisible in operator UI.
- `tenant.audit_log` rows produced during an impersonated request carry
  `actor_type='tenant_user'`, `actor_id=<shadow_id>`,
  `actor_label='<platform_email> (impersonating)'`, and
  `impersonation_id=<support_impersonation.id>`.
  `platform.audit_log` is unchanged — it has no `impersonation_id` column.
- The tenant JWT and stub deps (`get_current_tenant_user_*`) both bind
  `impersonation_id` to structlog contextvars when the resolved tenant
  user has a non-null `impersonation_id` column. `AuditableMixin` reads
  the contextvar; do not bind `impersonation_id` from any other code path
  unless you are extending the audit trail intentionally.
- `DELETE /platform/impersonations/{id}` is restricted to the impersonator
  (`platform_user_id` match). `POST /platform/impersonations/{id}/revoke`
  is restricted to superuser (and admin once P1.7-05 ships). Both
  deactivate the shadow tenant_user and revoke all its tenant sessions
  in the same transaction.
- Token minting reuses the existing
  `KeyService.get_active_signing_key("tenant")` + `SessionService.create`
  + `tokens.service.encode_*_token` primitives. No bespoke crypto path.
- The minted token has `aud="tenant:<slug>"`, `sub=<shadow_tenant_user.id>`,
  `actor_type="tenant_user"`, and no `impersonation_id` claim. The audit
  trail is established at the dep layer (via contextvars) rather than at
  the token layer (via claims).
- HTTP responses for impersonation lifecycle endpoints:
  410 Gone — ended/revoked/expired; 409 Conflict — not yet active (no
  approval yet); 403 Forbidden — caller is not the impersonator;
  404 Not Found — id unknown.

See `docs/superpowers/decisions/2026-06-02-impersonation-design.md` for
the full design rationale.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): full impersonation contracts (HTTP + auth + audit)"
```

---

## Task 9: Final verification

- [ ] **Step 1: Full lint + type-check + test suite**

```bash
make lint
make mypy
make test
```
Expected: all clean. The full suite must include the new test files for service, executor (02a), mint+shadow, api, end-to-end (02b), the audit propagation test, and the tenant dep impersonation test — and must not regress any pre-existing test.

- [ ] **Step 2: Manual smoke check**

```bash
make up
make migrate
alembic -c alembic-tenant.ini -x schema=tenant_test upgrade head
make api &
sleep 3

# Substitute a real platform actor id when running this manually.
PLATFORM_ID=$(docker compose exec -T postgres psql -U sacco -d sacco -tA \
  -c "SELECT id FROM platform.platform_users LIMIT 1")

curl -s -X POST http://127.0.0.1:8001/platform/impersonations \
  -H "X-Platform-Actor-ID: $PLATFORM_ID" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "00000000-0000-0000-0000-000000000000", "reason": "smoke test reason long enough"}' \
  | python -m json.tool
```
Expected: 400 (tenant not found) or 202 with `approval_request_id`. Validates that the router is mounted and the validation chain runs.

Kill the API server:
```bash
pkill -f "uvicorn app.main:app" || true
```

- [ ] **Step 3: PR**

```bash
git push -u origin feat/phase-1-7/02b-impersonation-http
gh pr create --title "feat(impersonation): HTTP + cross-context auth + audit wiring" --body "$(cat <<'EOF'
## Summary
- `POST /platform/impersonations` (submit), `GET .../active`, `GET .../all`, `GET .../{id}`, `DELETE .../{id}` (end), `POST .../{id}/revoke`, `POST .../{id}/mint-tenant-token`
- Shadow `tenant_users` lazy provisioning on first mint (idempotent, reused for subsequent mints)
- `mint_tenant_token` reuses existing `KeyService.get_active_signing_key` + `SessionService.create` + `tokens.service.encode_*_token` — no new crypto
- Tenant JWT and stub deps now bind `impersonation_id` to structlog contextvars when the user has a non-null `impersonation_id` column
- `AuditableMixin` writes `impersonation_id` to `tenant.audit_log` from contextvars; platform audit log unchanged (no column)
- `end` and `revoke` clean up the shadow user (is_active=false) and revoke all its tenant sessions in the same transaction
- End-to-end cross-context test proves request → approve → mint → /members works and produces an audit row with impersonation_id set
- Full Impersonation contracts subsection in CLAUDE.md (replaces the partial section from 02a)

## Architecture references
- ADR-002 (`docs/superpowers/decisions/2026-06-02-impersonation-design.md`) decisions §3, §4, §5
- Existing token issuance pattern in `app/modules/iam/tenant_auth/service.py:160-238`

## Test plan
- [ ] `make test-fast T=tests/platform_/impersonations/` — service + executor + mint + api + e2e
- [ ] `make test-fast T=tests/core/audit/test_impersonation_propagation.py`
- [ ] `make test-fast T=tests/modules/iam/test_tenant_dep_impersonation.py`
- [ ] `make ci` (ruff + mypy + full pytest)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opens cleanly, CI green.

---

## Acceptance criteria (sub-plan exits here)

- [ ] `AuditableMixin` propagates `impersonation_id` to `tenant.audit_log` rows; platform writes unchanged
- [ ] Both tenant deps (stub + JWT) bind `impersonation_id` contextvar for shadow users
- [ ] `ImpersonationService.mint_tenant_token` creates shadow tenant_user lazily, issues real tenant JWTs, updates `support_impersonations.tenant_user_id`
- [ ] `ImpersonationService.end` and `revoke` deactivate shadow + revoke sessions in the same tenant-schema transaction
- [ ] `/platform/impersonations/*` router exposes 6 endpoints with appropriate auth and HTTP semantics
- [ ] End-to-end test passes — full request → approve → mint → /members → audit → end → 403 flow
- [ ] CLAUDE.md "Impersonation contracts" subsection now lists the full HTTP + auth + audit contracts
- [ ] `make ci` clean
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** add `impersonation_id` as a JWT claim. The audit trail is established at the dep layer via contextvars, not at the token layer. The token is a regular tenant JWT.
- **Do not** add a Celery beat job to expire impersonations. The `expires_at > now()` check is part of `is_active` and runs on every gate. Sessions expire passively.
- **Do not** modify `PlatformAuditLog` to add `impersonation_id`. Platform-scoped audit happens against the impersonator's real identity; the link is provided by `support_impersonations.platform_user_id`.
- The cross-schema `AsyncSessionFactory()` opens a fresh session that is NOT tied to the FastAPI dependency lifecycle. Always wrap it in `async with` so it closes deterministically.
- `KeyService.get_active_signing_key("tenant")` requires a row with `audience='tenant'` and `status='active'`. The e2e test seeds one via `KeyService.generate_and_insert(audience="tenant", algorithm="RS256")`. In dev/prod, the bootstrap migrations or rotation job handle key seeding.
- The `_RevokeIn` body model has `reason` defaulting to empty string — the reason field is recorded in the audit_log via the standard mixin path (since `revoke()` triggers an UPDATE on the row, the before/after JSON captures the state change). A formal "revocation reason" column on `support_impersonations` is **not** in scope; if needed later, add a separate migration.
- If `make mypy` flags the `redis: object | None` parameter on `mint_tenant_token`, change it to `redis: Any | None = None` — the parameter is forwarded as-is to `SessionService`.
- The `make test` suite must include the e2e test by default. If pytest discovery skips it for any reason (missing fixture, etc.), fix discovery rather than excluding the test.
- If any existing audit-related test asserts a precise dict-shape that now includes `impersonation_id=None`, update it to allow the new key (`impersonation_id: None | UUID`) rather than removing the assertion.
