# Phase 1.7 Sub-Plan 06: Audit Log Query API

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/phase-1-7/06-audit-log-query-api` from `main` before starting.

**Goal:** Expose `platform.audit_log` and `tenant.audit_log` as read-only HTTP endpoints with structured filters, cursor pagination, and detail views. Portal v1 sub-plan 31 (audit viewer, both contexts) is the consumer.

**Architecture:**
- One new file, `app/core/audit/api.py`, exposes two routers: `platform_router` at `/platform/audit-log` (gated `CurrentAdmin` from P1.7-05) and `tenant_router` at `/audit-log` (any authenticated tenant user where `is_admin=true`; enforced inline). Filters supported: `actor_type`, `actor_id`, `table_name`, `operation`, `from_date`, `to_date`, `record_id`, plus `impersonation_id` on the tenant side. Pagination is opaque-cursor (base64-encoded `(occurred_at, id)` tuple) so callers don't need to compute offsets.
- Both routers hit `PlatformAuditLog` / `TenantAuditLog` directly via SQLAlchemy. The existing indexes (`ix_*_audit_log_occurred_at`, `ix_*_audit_log_table_record`) cover the typical filter shapes.
- The list response excludes `before_state` / `after_state` (those can be hundreds of KB per row); the detail response includes them.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2.

**Roadmap reference:** `docs/superpowers/plans/phase-1-7-backend-foundation/00-index.md` §P1.7-06.

**Prerequisite:** **P1.7-05 must be merged** so `CurrentAdmin` is available for the platform router.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/core/audit/schemas.py` | Create | `AuditLogOut` (no before/after), `AuditLogDetailOut` (with), `AuditLogListPage` (rows + next_cursor) |
| `app/core/audit/api.py` | Create | Two routers (`platform_router`, `tenant_router`), four endpoints |
| `app/core/audit/cursor.py` | Create | Encode/decode opaque `(occurred_at, id)` cursor |
| `app/main.py` | Modify | Mount the two routers |
| `tests/core/audit/test_api.py` | Create | Integration tests for platform + tenant endpoints, filters, cursor pagination |
| `tests/core/audit/test_cursor.py` | Create | Unit tests for cursor encode/decode (round-trip + tampering) |
| `CLAUDE.md` | Modify | Append the audit query API contract under `## Core module contracts (do not violate)` |

---

## Task 1: Cursor encode/decode

**Files:**
- Create: `app/core/audit/cursor.py`
- Create: `tests/core/audit/test_cursor.py`

- [ ] **Step 1: Write failing cursor tests**

```python
# tests/core/audit/test_cursor.py
"""Cursor encoding round-trips correctly and rejects tampered payloads."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.core.audit.cursor import decode_cursor, encode_cursor


def test_round_trip() -> None:
    ts = datetime(2026, 6, 3, 14, 32, 7, tzinfo=UTC)
    rid = uuid.uuid4()
    cur = encode_cursor(ts, rid)
    assert isinstance(cur, str)
    ts2, rid2 = decode_cursor(cur)
    assert ts2 == ts
    assert rid2 == rid


def test_decode_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        decode_cursor("not-a-cursor")


def test_decode_rejects_bad_json() -> None:
    import base64
    bad = base64.urlsafe_b64encode(b"not json").decode()
    with pytest.raises(ValueError):
        decode_cursor(bad)


def test_decode_rejects_missing_fields() -> None:
    import base64
    import json
    bad = base64.urlsafe_b64encode(json.dumps({"ts": "x"}).encode()).decode()
    with pytest.raises(ValueError):
        decode_cursor(bad)
```

- [ ] **Step 2: Run — expected to fail (ImportError)**

```bash
make test-fast T=tests/core/audit/test_cursor.py
```
Expected: `ImportError`.

- [ ] **Step 3: Implement the cursor module**

```python
# app/core/audit/cursor.py
"""Opaque cursor for audit log pagination.

Cursor encodes a (occurred_at, id) tuple so the next page query uses
ROW VALUE comparison: WHERE (occurred_at, id) < (cur_ts, cur_id).

The cursor is not signed — it is opaque from the client's perspective
but tampering only lets the caller skip rows, not see ones they
couldn't otherwise. Filter authorization is enforced by the route.
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime


def encode_cursor(occurred_at: datetime, row_id: uuid.UUID) -> str:
    payload = json.dumps(
        {"ts": occurred_at.isoformat(), "id": str(row_id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    # Restore padding
    rem = len(cursor) % 4
    padded = cursor + ("=" * (4 - rem) if rem else "")
    try:
        raw = base64.urlsafe_b64decode(padded)
        obj = json.loads(raw)
        ts = datetime.fromisoformat(obj["ts"])
        row_id = uuid.UUID(obj["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"Malformed cursor: {exc}") from exc
    return ts, row_id
```

- [ ] **Step 4: Run — should pass**

```bash
make test-fast T=tests/core/audit/test_cursor.py
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/core/audit/cursor.py tests/core/audit/test_cursor.py
git commit -m "feat(audit): opaque (occurred_at, id) pagination cursor"
```

---

## Task 2: Schemas

**Files:**
- Create: `app/core/audit/schemas.py`

- [ ] **Step 1: Write the schemas**

```python
# app/core/audit/schemas.py
"""Pydantic types for the audit-log query API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    """Lean row shape for the list endpoint — excludes before/after_state
    since those can be very large.
    """

    id: uuid.UUID
    table_name: str
    record_id: uuid.UUID
    operation: str
    actor_type: str
    actor_id: uuid.UUID | None
    actor_label: str | None
    occurred_at: datetime
    request_id: str | None
    # Tenant-only column. Always None on platform rows. None on tenant rows
    # too unless the action was inside an impersonation session.
    impersonation_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class AuditLogDetailOut(AuditLogOut):
    """Full row shape including before/after state."""

    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None


class AuditLogListPage(BaseModel):
    rows: list[AuditLogOut]
    next_cursor: str | None
```

- [ ] **Step 2: Commit**

```bash
git add app/core/audit/schemas.py
git commit -m "feat(audit): list / detail / page Pydantic schemas"
```

---

## Task 3: Failing API tests

**Files:**
- Create: `tests/core/audit/test_api.py`

- [ ] **Step 1: Write the test file**

```python
# tests/core/audit/test_api.py
"""Integration tests for the audit-log query API.

Covers:
- Platform: list + filter + cursor pagination + detail + role gate
- Tenant: list + filter + detail + is_admin gate
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.db import get_platform_session, get_tenant_session
from app.main import app, lifespan
from app.modules.iam.tenant_users.models import TenantUser
from app.platform_.models import PlatformUser


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


async def _create_platform_actor(
    factory: async_sessionmaker[AsyncSession],
    *,
    role: str = "admin",
    is_superuser: bool = False,
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"a-{uuid.uuid4().hex[:6]}@test.example",
            full_name="A",
            role=role,
            is_active=True,
            is_superuser=is_superuser,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _create_tenant_user(
    factory: async_sessionmaker[AsyncSession],
    schema: str,
    *,
    is_admin: bool,
) -> TenantUser:
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {schema}, platform"))
        u = TenantUser(
            email=f"t-{uuid.uuid4().hex[:6]}@test.example",
            full_name="T",
            is_active=True,
            is_admin=is_admin,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _seed_platform_rows(
    factory: async_sessionmaker[AsyncSession], count: int,
) -> list[PlatformAuditLog]:
    """Triggering AuditableMixin is the cleanest seed. Insert N platform_users
    to produce N audit_log rows.
    """
    rows: list[PlatformAuditLog] = []
    for _ in range(count):
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            u = PlatformUser(
                email=f"seed-{uuid.uuid4().hex[:6]}@test.example",
                full_name="seed",
                role="support",
                is_active=True, is_superuser=False,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(u)
    # Read them back
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        from sqlalchemy import select
        result = await s.execute(
            select(PlatformAuditLog)
            .where(PlatformAuditLog.table_name == "platform_users")
            .order_by(PlatformAuditLog.occurred_at.desc())
        )
        rows = list(result.scalars().all())
    return rows


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
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
    app.dependency_overrides[get_tenant_session] = (
        _make_tenant_session_override(test_engine, "tenant_test")
    )
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)
    app.dependency_overrides.pop(get_tenant_session, None)


def _phdr(uid: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(uid)}


def _thdr(uid: uuid.UUID, slug: str = "test-tenant") -> dict[str, str]:
    return {"X-Tenant-Slug": slug, "X-Tenant-Actor-ID": str(uid)}


# ── Platform ──────────────────────────────────────────────────────────────────


async def test_platform_list_returns_rows(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_actor(factory, role="admin")
    await _seed_platform_rows(factory, count=3)
    try:
        r = await client.get(
            "/platform/audit-log?limit=10", headers=_phdr(actor.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # 3 seed rows + 1 for the actor itself = 4
        assert len(body["rows"]) >= 3
        # Lean shape — no before/after on list
        assert "before_state" not in body["rows"][0]
    finally:
        await _cleanup(factory)


async def test_platform_filter_by_table_name(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_actor(factory, role="admin")
    await _seed_platform_rows(factory, count=2)
    try:
        r = await client.get(
            "/platform/audit-log?table_name=platform_users",
            headers=_phdr(actor.id),
        )
        assert r.status_code == 200
        rows = r.json()["rows"]
        assert all(row["table_name"] == "platform_users" for row in rows)
    finally:
        await _cleanup(factory)


async def test_platform_cursor_pagination(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_actor(factory, role="admin")
    await _seed_platform_rows(factory, count=5)
    try:
        page1 = await client.get(
            "/platform/audit-log?limit=2", headers=_phdr(actor.id),
        )
        assert page1.status_code == 200
        b1 = page1.json()
        assert len(b1["rows"]) == 2
        assert b1["next_cursor"] is not None

        page2 = await client.get(
            f"/platform/audit-log?limit=2&cursor={b1['next_cursor']}",
            headers=_phdr(actor.id),
        )
        assert page2.status_code == 200
        b2 = page2.json()
        # No overlap
        ids1 = {r["id"] for r in b1["rows"]}
        ids2 = {r["id"] for r in b2["rows"]}
        assert ids1.isdisjoint(ids2)
    finally:
        await _cleanup(factory)


async def test_platform_detail_includes_state(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_actor(factory, role="admin")
    rows = await _seed_platform_rows(factory, count=1)
    target = rows[0]
    try:
        r = await client.get(
            f"/platform/audit-log/{target.id}", headers=_phdr(actor.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == str(target.id)
        # Detail includes before/after state
        assert "before_state" in body
        assert "after_state" in body
        assert body["after_state"] is not None  # insert event
    finally:
        await _cleanup(factory)


async def test_platform_404_for_unknown(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_actor(factory, role="admin")
    try:
        r = await client.get(
            f"/platform/audit-log/{uuid.uuid4()}", headers=_phdr(actor.id),
        )
        assert r.status_code == 404
    finally:
        await _cleanup(factory)


async def test_platform_403_for_non_admin(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_actor(factory, role="finance")
    try:
        r = await client.get(
            "/platform/audit-log", headers=_phdr(actor.id),
        )
        assert r.status_code == 403, r.text
    finally:
        await _cleanup(factory)


async def test_platform_400_for_bad_cursor(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_platform_actor(factory, role="admin")
    try:
        r = await client.get(
            "/platform/audit-log?cursor=not-a-cursor",
            headers=_phdr(actor.id),
        )
        assert r.status_code == 400
    finally:
        await _cleanup(factory)


# ── Tenant ────────────────────────────────────────────────────────────────────


async def test_tenant_list_returns_rows(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_tenant_user(factory, "tenant_test", is_admin=True)
    # The actor's own insert created one audit row
    try:
        r = await client.get(
            "/audit-log?limit=10",
            headers=_thdr(actor.id),
        )
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert any(row["table_name"] == "tenant_users" for row in rows)
    finally:
        await _cleanup(factory)


async def test_tenant_403_for_non_admin(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_tenant_user(factory, "tenant_test", is_admin=False)
    try:
        r = await client.get(
            "/audit-log",
            headers=_thdr(actor.id),
        )
        assert r.status_code == 403, r.text
    finally:
        await _cleanup(factory)


async def test_tenant_filter_by_operation(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_tenant_user(factory, "tenant_test", is_admin=True)
    try:
        r = await client.get(
            "/audit-log?operation=insert",
            headers=_thdr(actor.id),
        )
        assert r.status_code == 200
        rows = r.json()["rows"]
        assert all(row["operation"] == "insert" for row in rows)
    finally:
        await _cleanup(factory)


async def test_tenant_detail(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_tenant_user(factory, "tenant_test", is_admin=True)
    # Find the audit row for the actor's own insert
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        from sqlalchemy import select
        row = (
            await s.execute(
                select(TenantAuditLog)
                .where(TenantAuditLog.record_id == actor.id)
                .order_by(TenantAuditLog.occurred_at.desc())
                .limit(1)
            )
        ).scalar_one()
    try:
        r = await client.get(
            f"/audit-log/{row.id}",
            headers=_thdr(actor.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == str(row.id)
        assert "after_state" in body
    finally:
        await _cleanup(factory)
```

- [ ] **Step 2: Run — expected to fail (no router yet)**

```bash
make test-fast T=tests/core/audit/test_api.py
```
Expected: every test fails with 404 or 405.

- [ ] **Step 3: Commit**

```bash
git add tests/core/audit/test_api.py
git commit -m "test(audit): API integration tests (red)"
```

---

## Task 4: Implement the two routers

**Files:**
- Create: `app/core/audit/api.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the router file**

```python
# app/core/audit/api.py
"""Audit log query API.

Two routers:
    platform_router → /platform/audit-log/*   (CurrentAdmin)
    tenant_router   → /audit-log/*            (inline is_admin check)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.cursor import decode_cursor, encode_cursor
from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.audit.schemas import (
    AuditLogDetailOut,
    AuditLogListPage,
    AuditLogOut,
)
from app.core.db import get_platform_session, get_tenant_session
from app.modules.iam.dependencies import CurrentTenantUser
from app.platform_.auth import CurrentAdmin

platform_router = APIRouter(prefix="/platform/audit-log", tags=["platform-audit"])
tenant_router = APIRouter(prefix="/audit-log", tags=["tenant-audit"])

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 50

M = TypeVar("M", PlatformAuditLog, TenantAuditLog)


def _apply_common_filters(
    q: object,  # SQLAlchemy Select; typed loosely so the same fn handles both models
    model: type[M],
    *,
    actor_type: str | None,
    actor_id: uuid.UUID | None,
    table_name: str | None,
    operation: str | None,
    from_date: date | None,
    to_date: date | None,
    record_id: uuid.UUID | None,
) -> object:
    if actor_type is not None:
        q = q.where(model.actor_type == actor_type)
    if actor_id is not None:
        q = q.where(model.actor_id == actor_id)
    if table_name is not None:
        q = q.where(model.table_name == table_name)
    if operation is not None:
        q = q.where(model.operation == operation)
    if from_date is not None:
        q = q.where(model.occurred_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date is not None:
        q = q.where(model.occurred_at <= datetime.combine(to_date, datetime.max.time()))
    if record_id is not None:
        q = q.where(model.record_id == record_id)
    return q


async def _list_paginated(
    session: AsyncSession,
    model: type[M],
    *,
    actor_type: str | None,
    actor_id: uuid.UUID | None,
    table_name: str | None,
    operation: str | None,
    from_date: date | None,
    to_date: date | None,
    record_id: uuid.UUID | None,
    impersonation_id: uuid.UUID | None,
    cursor: str | None,
    limit: int,
) -> AuditLogListPage:
    q = select(model).order_by(model.occurred_at.desc(), model.id.desc())
    q = _apply_common_filters(
        q, model,
        actor_type=actor_type, actor_id=actor_id, table_name=table_name,
        operation=operation, from_date=from_date, to_date=to_date,
        record_id=record_id,
    )
    if impersonation_id is not None and hasattr(model, "impersonation_id"):
        q = q.where(model.impersonation_id == impersonation_id)

    if cursor:
        try:
            cur_ts, cur_id = decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # Tuple comparison: keep rows strictly older than (cur_ts, cur_id)
        q = q.where(tuple_(model.occurred_at, model.id) < (cur_ts, cur_id))

    # Fetch limit+1 to detect if there's a next page
    fetched = limit + 1
    result = await session.execute(q.limit(fetched))
    rows = list(result.scalars().all())

    has_more = len(rows) == fetched
    page_rows = rows[:limit]
    next_cursor = (
        encode_cursor(page_rows[-1].occurred_at, page_rows[-1].id)
        if has_more and page_rows
        else None
    )
    return AuditLogListPage(
        rows=[AuditLogOut.model_validate(r) for r in page_rows],
        next_cursor=next_cursor,
    )


# ── Platform ─────────────────────────────────────────────────────────────────


@platform_router.get("", response_model=AuditLogListPage)
async def list_platform_audit(
    _user: CurrentAdmin,
    session: PlatformSession,
    actor_type: str | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    table_name: str | None = Query(None),
    operation: str | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    record_id: uuid.UUID | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
) -> AuditLogListPage:
    return await _list_paginated(
        session, PlatformAuditLog,
        actor_type=actor_type, actor_id=actor_id, table_name=table_name,
        operation=operation, from_date=from_date, to_date=to_date,
        record_id=record_id,
        impersonation_id=None,  # platform rows have no such column
        cursor=cursor, limit=limit,
    )


@platform_router.get("/{audit_id}", response_model=AuditLogDetailOut)
async def get_platform_audit(
    audit_id: uuid.UUID,
    _user: CurrentAdmin,
    session: PlatformSession,
) -> AuditLogDetailOut:
    row = await session.get(PlatformAuditLog, audit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit row not found")
    return AuditLogDetailOut.model_validate(row)


# ── Tenant ───────────────────────────────────────────────────────────────────


def _require_tenant_admin(user: CurrentTenantUser) -> None:
    if not user.is_admin:
        raise HTTPException(
            status_code=403, detail="Tenant admin role required"
        )


@tenant_router.get("", response_model=AuditLogListPage)
async def list_tenant_audit(
    user: CurrentTenantUser,
    session: TenantSession,
    actor_type: str | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    table_name: str | None = Query(None),
    operation: str | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    record_id: uuid.UUID | None = Query(None),
    impersonation_id: uuid.UUID | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
) -> AuditLogListPage:
    _require_tenant_admin(user)
    return await _list_paginated(
        session, TenantAuditLog,
        actor_type=actor_type, actor_id=actor_id, table_name=table_name,
        operation=operation, from_date=from_date, to_date=to_date,
        record_id=record_id,
        impersonation_id=impersonation_id,
        cursor=cursor, limit=limit,
    )


@tenant_router.get("/{audit_id}", response_model=AuditLogDetailOut)
async def get_tenant_audit(
    audit_id: uuid.UUID,
    user: CurrentTenantUser,
    session: TenantSession,
) -> AuditLogDetailOut:
    _require_tenant_admin(user)
    row = await session.get(TenantAuditLog, audit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit row not found")
    return AuditLogDetailOut.model_validate(row)
```

- [ ] **Step 2: Mount the routers**

In `app/main.py`, add imports:

```python
from app.core.audit.api import (
    platform_router as audit_platform_router,
    tenant_router as audit_tenant_router,
)
```

Add the mounts alongside other platform routers:

```python
app.include_router(audit_platform_router)
app.include_router(audit_tenant_router)
```

- [ ] **Step 3: Run the API tests — they should pass**

```bash
make test-fast T=tests/core/audit/test_api.py
```
Expected: 11 tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/core/audit/api.py app/main.py
git commit -m "feat(audit): platform + tenant query routers with filters + cursor pagination"
```

---

## Task 5: CLAUDE.md contract

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append a bullet to `## Core module contracts (do not violate)`**

Find the existing core-module contracts subsection. Append:

```markdown
- The audit log is queryable via `/platform/audit-log` (platform schema,
  `CurrentAdmin` gate) and `/audit-log` (tenant schema, requires
  `tenant_user.is_admin=true`). Both return a lean list shape via
  `AuditLogListPage` (no before/after JSON) with cursor pagination on
  `(occurred_at DESC, id)`; the `GET /{id}` detail endpoint includes the
  full before/after state. Filters: `actor_type`, `actor_id`,
  `table_name`, `operation`, `from_date`, `to_date`, `record_id`, plus
  `impersonation_id` on the tenant side. The cursor is an opaque
  base64-encoded `(occurred_at, id)` pair — clients should not parse it.
- The audit log is append-only by construction (writes happen via
  `AuditableMixin._write_audit` only). The query API exposes no mutation
  endpoints. PR reviewers should reject any PR adding update or delete
  endpoints to `app/core/audit/`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): audit log query API contract"
```

---

## Task 6: Final verification

- [ ] **Step 1: Full lint + type-check + test suite**

```bash
make lint
make mypy
make test
```
Expected: all clean. New tests: 4 cursor + 11 API = 15.

- [ ] **Step 2: Manual smoke check**

```bash
make up
make migrate
make api &
sleep 3
TOKEN=$(make -s platform-token)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8001/platform/audit-log?limit=5" \
  | python -m json.tool
pkill -f "uvicorn app.main:app" || true
```
Expected: JSON object with `rows` array and `next_cursor`.

- [ ] **Step 3: PR**

```bash
git push -u origin feat/phase-1-7/06-audit-log-query-api
gh pr create --title "feat(audit): query API (platform + tenant)" --body "$(cat <<'EOF'
## Summary
- `GET /platform/audit-log` (CurrentAdmin) + `GET /platform/audit-log/{id}` — platform schema
- `GET /audit-log` (tenant_user.is_admin) + `GET /audit-log/{id}` — tenant schema
- Filters: actor_type, actor_id, table_name, operation, from_date, to_date, record_id, plus impersonation_id on the tenant side
- Opaque cursor pagination on `(occurred_at DESC, id)` — base64 of `{ts, id}`
- Lean list shape (no before/after JSON); detail endpoint includes full state
- CLAUDE.md contract: audit log is queryable but never mutable via this API

## Test plan
- [ ] `make test-fast T=tests/core/audit/test_cursor.py` — 4 cursor tests
- [ ] `make test-fast T=tests/core/audit/test_api.py` — 11 endpoint tests (platform + tenant + filters + cursor + gates)
- [ ] `make ci`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `app/core/audit/cursor.py` round-trips `(occurred_at, id)` and rejects tampered cursors
- [ ] `AuditLogOut`, `AuditLogDetailOut`, `AuditLogListPage` schemas in place
- [ ] Two routers in `app/core/audit/api.py` covering the four endpoints
- [ ] Filters + cursor pagination work; `limit` capped at 100
- [ ] Platform list/detail gate on `CurrentAdmin`; tenant gate on `tenant_user.is_admin`
- [ ] List excludes before/after JSON; detail includes it
- [ ] All 15 new tests pass
- [ ] CLAUDE.md updated
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** add update or delete endpoints. The audit log is append-only by construction.
- **Do not** use offset/limit pagination. The cursor design ensures stable order regardless of new inserts and avoids the deep-page performance cliff.
- **Do not** sign the cursor. Tampering only lets a caller skip rows; it cannot reveal rows the caller couldn't otherwise see (the filter and gate enforce authorization).
- **Do not** add `impersonation_id` as a filter on the platform router — the platform audit_log table has no such column.
- The `tuple_(model.occurred_at, model.id) < (cur_ts, cur_id)` clause uses Postgres ROW comparison and benefits from the existing `ix_*_audit_log_occurred_at` index. Verify EXPLAIN shows the index in use if performance becomes a concern.
- The `from_date` filter uses `datetime.combine(from_date, datetime.min.time())` — this is `00:00:00` on that date. The `to_date` end uses `datetime.max.time()` — `23:59:59.999999` of that date. Both are inclusive. Document this in the OpenAPI description if a portal user reports off-by-one boundary surprises.
- If `make mypy` complains about the `q: object` parameter in `_apply_common_filters`, it's loosely typed because SQLAlchemy's `Select` is generic over the model and the two routers share the helper. The type annotation can be tightened with TypeVar bounds if the type checker insists.
- The list shape omits `before_state` and `after_state` for size reasons. Anyone needing them must hit the detail endpoint. The portal's audit viewer table renders a "View details" link per row.
- The portal sub-plan 31 (audit viewer, both contexts) consumes both routers. The query parameter names here are stable — do not rename them.
