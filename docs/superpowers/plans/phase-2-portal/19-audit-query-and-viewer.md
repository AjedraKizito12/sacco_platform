# Audit Query Endpoint + Viewer (SP19 / P1.7-F) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Environment note (2026-06-20):** background subagents in this harness cannot obtain Edit-permission approval (they stall at the first edit). SP17/SP18 ran **inline** via executing-plans. Expect the same. **Test DB:** `.env` has a stale `DATABASE_URL` (port 5532); the real test DB is the compose `postgres-test` service — `export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test` after `docker compose up -d postgres-test`.

**Goal:** Ship the Phase-1.7-F audit-log query endpoints (platform schema + per-tenant schema), then the portal Audit Viewer (platform + per-tenant) and the now-live `<AuditBar>` on all 6 platform detail pages.

**Architecture:** New read-only `app/platform_/audit/` module with a schema-agnostic `AuditQueryService` serving two `CurrentAdmin`-gated, paginated, filtered endpoints. Portal: hand-written `@sacco/schemas` types + filled `resources.audit`; an additive `shallow` option on `useTableUrlState` enables the portal's first **true server-side paginated** `<DataTable>`; the platform + tenant `/audit` viewers fetch server-side and render an inline before/after `<JsonDiff>`; the `@sacco/ui` `<AuditBar>` gains presentational `entries`/`viewAllHref` props and a portal `<AuditBarConnected>` wrapper lights it up on the 6 detail pages. Backend lands first; portal consumes it.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2.0 async / pytest (backend); Next.js 15 App Router, React 19, TS strict, `@sacco/ui` (DataTable, FormattedDateTime, RelativeTime, Select, Card), `@sacco/schemas`, `@sacco/api-client`, nuqs, Vitest + Testing Library (portal).

---

## Contract & scope notes (read before starting)

- **Backend-first**, one PR; backend commits precede portal commits (SP17 pattern). Backend under `app/` + `tests/`; portal under `admin/`.
- **Two endpoints, both `CurrentAdmin`:** `GET /platform/audit-log` (platform schema, `get_platform_session`) and `GET /platform/tenants/{tenant_id}/audit-log` (tenant schema, `get_session_for_tenant_schema` — NOT subscription-gated). Shared params + paginated envelope; tenant adds `impersonation_id`.
- **`_AuditLogBase` columns:** `id, table_name, record_id, operation, actor_type, actor_id, actor_label, before_state, after_state, occurred_at, request_id`; `TenantAuditLog` adds `impersonation_id`. Indexes `(table_name, record_id)` + `occurred_at DESC`. `AuditableMixin` writes `table_name = __tablename__`.
- **entityType → table_name** (AuditBar): `subscription→subscriptions`, `subscription_plan→subscription_plans`, `invoice→invoices`, `platform_user→platform_users`, `tenant→tenants`, `approval_request→approval_requests`.
- **Pagination:** offset (`page`, `page_size` 1..100, default 25); envelope `{items, total, page, page_size}`; order `occurred_at DESC, id DESC`.
- **No `GET /audit-log/{id}`** — the before/after diff renders inline from the row's own `before_state`/`after_state`.
- **Permission:** `audit.read → admin` (already exists). UI gating UX-only; API enforces (contract D).
- **Out of scope:** CSV export, retention/archival, cursor pagination, real-time, e2e + next-intl.

## File Structure

**Backend (`app/`, separate commits)**
- Create `app/platform_/audit/__init__.py`, `schemas.py`, `service.py`, `api.py`.
- Modify `app/main.py` — mount the audit router.
- Test `tests/platform_/audit/test_audit_api.py` (+ `__init__.py`).

**`@sacco/schemas`**
- Create `packages/schemas/src/audit.ts`; export from `index.ts`.

**`@sacco/api-client`**
- Modify `packages/api-client/src/resources/audit.ts` — fill `listPlatform` / `listTenant`.

**`@sacco/ui`**
- Modify `packages/ui/src/components/DataTable/use-table-url-state.ts` — add `shallow` option.
- Modify `packages/ui/src/components/AuditBar/AuditBar.tsx` — add `entries`/`viewAllHref`/`isLoading`.

**`@sacco/portal`**
- Create `app/platform/(authed)/audit/_components/AuditTable.tsx`, `JsonDiff.tsx`, `AuditOperationLabel.tsx`, `page.tsx`.
- Create `app/platform/(authed)/tenants/[id]/audit/_components/...` (reuse) + `page.tsx`.
- Create `src/components/AuditBarConnected.tsx` + `src/lib/audit-tables.ts` (entityType→table map).
- Modify the 6 detail pages to use `<AuditBarConnected>`.
- Modify `TenantDetail` — add "Audit log" link.
- Tests under `apps/portal/src/__tests__/platform-audit/`.

---

## Task 1: Backend — schemas + `AuditQueryService`

**Files:**
- Create: `app/platform_/audit/__init__.py` (empty), `app/platform_/audit/schemas.py`, `app/platform_/audit/service.py`
- Test: `tests/platform_/audit/__init__.py` (empty), `tests/platform_/audit/test_audit_api.py` (service-level test here; HTTP in Tasks 2–3)

- [ ] **Step 1: Write `schemas.py`**

```python
"""Pydantic types for the audit-log query endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    table_name: str
    record_id: uuid.UUID
    operation: str
    actor_type: str
    actor_id: uuid.UUID | None
    actor_label: str | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    occurred_at: datetime
    request_id: str | None
    impersonation_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    items: list[AuditEntryOut]
    total: int
    page: int
    page_size: int
```

> `impersonation_id` defaults to `None`; `PlatformAuditLog` has no such attribute, so `model_validate` of a platform row leaves it `None` (it's not an ORM field there — `from_attributes` only reads attributes that exist; the default covers the platform case). The tenant model HAS the attribute, so it populates.

- [ ] **Step 2: Write `service.py`**

```python
"""Read-only audit-log query service (schema-agnostic)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class AuditQueryService:
    """Queries an audit_log table. The model class (PlatformAuditLog or
    TenantAuditLog) is supplied by the caller so the service stays
    schema-agnostic, like ApprovalService."""

    def __init__(self, session: AsyncSession, model_cls: type[Any]) -> None:
        self._session = session
        self._m = model_cls

    async def query(
        self,
        *,
        table_name: str | None = None,
        record_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        actor_type: str | None = None,
        operation: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[Any], int]:
        conds = []
        if table_name:
            conds.append(self._m.table_name == table_name)
        if record_id is not None:
            conds.append(self._m.record_id == record_id)
        if actor_id is not None:
            conds.append(self._m.actor_id == actor_id)
        if actor_type:
            conds.append(self._m.actor_type == actor_type)
        if operation:
            conds.append(self._m.operation == operation)
        if occurred_from is not None:
            conds.append(self._m.occurred_at >= occurred_from)
        if occurred_to is not None:
            conds.append(self._m.occurred_at <= occurred_to)

        total = (
            await self._session.execute(
                select(func.count()).select_from(self._m).where(*conds)
            )
        ).scalar_one()

        rows = (
            await self._session.execute(
                select(self._m)
                .where(*conds)
                .order_by(self._m.occurred_at.desc(), self._m.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return list(rows), total
```

- [ ] **Step 3: Write a service-level test (real Postgres)**

Create `tests/platform_/audit/__init__.py` (empty) and `tests/platform_/audit/test_audit_api.py` with a first service test that inserts a couple of `PlatformAuditLog` rows on the `test_engine` and asserts `query()` filters + paginates. Model the engine/session/cleanup on `tests/modules/maker_checker/test_platform_api.py` (async_sessionmaker on `test_engine`, `SET LOCAL search_path TO platform`, delete rows in `finally`). Example core:

```python
async def test_query_filters_by_record_and_paginates(test_engine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    rid = uuid.uuid4()
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            for i in range(3):
                s.add(PlatformAuditLog(
                    table_name="tenants", record_id=rid, operation="update",
                    actor_type="platform_user", actor_id=uuid.uuid4(),
                    actor_label="op@test", before_state={"a": i},
                    after_state={"a": i + 1}, occurred_at=datetime.now(UTC),
                ))
            # a noise row for a different record
            s.add(PlatformAuditLog(
                table_name="tenants", record_id=uuid.uuid4(), operation="insert",
                actor_type="system", occurred_at=datetime.now(UTC),
            ))
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = AuditQueryService(s, PlatformAuditLog)
            rows, total = await svc.query(record_id=rid, page=1, page_size=2)
            assert total == 3
            assert len(rows) == 2
    finally:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(text("DELETE FROM platform.audit_log"))
```

- [ ] **Step 4: Run it**

Run: `cd /home/liam/projects/sacco-platform && export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test && python -m pytest tests/platform_/audit/test_audit_api.py -q`
Expected: PASS.

- [ ] **Step 5: ruff + mypy + commit**

```bash
cd /home/liam/projects/sacco-platform
ruff check app/ tests/ && mypy app/
git add app/platform_/audit/ tests/platform_/audit/
git commit -m "feat(audit): AuditEntryOut/AuditLogPage schemas + AuditQueryService

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Backend — platform endpoint `GET /platform/audit-log`

**Files:**
- Create: `app/platform_/audit/api.py`
- Modify: `app/main.py`
- Test: `tests/platform_/audit/test_audit_api.py`

- [ ] **Step 1: Write the failing HTTP test (append)**

Use the maker-checker test harness conventions: `_make_platform_session_override(test_engine)` overriding `get_platform_session`, the `X-Platform-Actor-ID` stub-auth header, `lifespan(app)` + `AsyncClient`. Seed a couple of rows (via a direct session as in Task 1), then:

```python
async def test_platform_audit_endpoint_lists_and_filters(test_engine) -> None:
    # ... seed 2 rows for record rid (table_name="tenants") via factory ...
    # ... app.dependency_overrides[get_platform_session] = override ...
    # ... actor = a platform user (reuse _create_platform_user pattern) ...
    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(
                f"/platform/audit-log?table_name=tenants&record_id={rid}&page_size=10",
                headers={"X-Platform-Actor-ID": str(actor.id)},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] == 2
            assert len(body["items"]) == 2
            assert body["items"][0]["table_name"] == "tenants"
            assert body["items"][0]["impersonation_id"] is None
```

Run to verify it fails (404 — route not mounted).

- [ ] **Step 2: Write `api.py`**

```python
"""FastAPI router for the platform audit-log query endpoint."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.db import get_platform_session, get_session_for_tenant_schema
from app.platform_.audit.schemas import AuditEntryOut, AuditLogPage
from app.platform_.audit.service import AuditQueryService
from app.platform_.auth import CurrentAdmin

router = APIRouter(tags=["platform-audit"])

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]
TenantSchemaSession = Annotated[AsyncSession, Depends(get_session_for_tenant_schema)]


def _page(rows: list, total: int, page: int, page_size: int) -> AuditLogPage:
    return AuditLogPage(
        items=[AuditEntryOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/platform/audit-log", response_model=AuditLogPage)
async def list_platform_audit(
    session: PlatformSession,
    _user: CurrentAdmin,
    table_name: str | None = Query(None),
    record_id: uuid.UUID | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    actor_type: str | None = Query(None),
    operation: str | None = Query(None),
    occurred_from: datetime | None = Query(None),
    occurred_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> AuditLogPage:
    rows, total = await AuditQueryService(session, PlatformAuditLog).query(
        table_name=table_name, record_id=record_id, actor_id=actor_id,
        actor_type=actor_type, operation=operation,
        occurred_from=occurred_from, occurred_to=occurred_to,
        page=page, page_size=page_size,
    )
    return _page(rows, total, page, page_size)


@router.get("/platform/tenants/{tenant_id}/audit-log", response_model=AuditLogPage)
async def list_tenant_audit(
    tenant_id: uuid.UUID,
    session: TenantSchemaSession,
    _user: CurrentAdmin,
    table_name: str | None = Query(None),
    record_id: uuid.UUID | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    actor_type: str | None = Query(None),
    operation: str | None = Query(None),
    occurred_from: datetime | None = Query(None),
    occurred_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> AuditLogPage:
    rows, total = await AuditQueryService(session, TenantAuditLog).query(
        table_name=table_name, record_id=record_id, actor_id=actor_id,
        actor_type=actor_type, operation=operation,
        occurred_from=occurred_from, occurred_to=occurred_to,
        page=page, page_size=page_size,
    )
    return _page(rows, total, page, page_size)
```

> Both endpoints live in this one router (Task 3's tenant test exercises the second handler). `tenant_id` is the first param so `get_session_for_tenant_schema` receives it (FastAPI injects path params into deps).

- [ ] **Step 3: Mount in `app/main.py`**

Add alongside the other platform routers:

```python
from app.platform_.audit.api import router as platform_audit_router
# ...
app.include_router(platform_audit_router)
```

- [ ] **Step 4: Run the platform test → PASS; then ruff + mypy.**

Run: `export DATABASE_URL=... && python -m pytest tests/platform_/audit/ -q && ruff check app/ tests/ && mypy app/`

- [ ] **Step 5: Commit**

```bash
git add app/platform_/audit/api.py app/main.py tests/platform_/audit/test_audit_api.py
git commit -m "feat(audit): platform + tenant audit-log query endpoints

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Backend — tenant endpoint test (`impersonation_id` surfacing)

**Files:**
- Test: `tests/platform_/audit/test_audit_api.py`

> The tenant handler shipped in Task 2; this task proves it against a tenant schema and that `impersonation_id` surfaces.

- [ ] **Step 1: Write the tenant test**

Use the conftest `TEST_TENANT_SCHEMA` + a `get_session_for_tenant_schema` override (or seed a tenant row whose `schema_name` is the test schema and let the real dep run). The simplest reliable path mirrors how `tests/` exercises tenant-schema endpoints elsewhere — **read `tests/conftest.py` and an existing tenant-schema test first** to copy the exact override (the dep loads a `platform.tenants` row by id, so the test must insert a tenant row pointing at the test schema, then seed a `TenantAuditLog` row with an `impersonation_id`). Assert the endpoint returns the row with `impersonation_id` populated.

> If wiring the real `get_session_for_tenant_schema` against the test engine proves fragile (cross-loop asyncpg issues — see the memory note on test DB sessions), override the dep with a function that yields a `SET LOCAL search_path TO <test schema>, platform` session, matching the Task-2 platform override. Prefer the override; it's deterministic.

- [ ] **Step 2: Run → PASS; ruff + mypy.**

- [ ] **Step 3: Commit**

```bash
git add tests/platform_/audit/test_audit_api.py
git commit -m "test(audit): tenant audit-log endpoint surfaces impersonation_id

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Portal — `@sacco/schemas` audit types

**Files:**
- Create: `admin/packages/schemas/src/audit.ts`
- Modify: `admin/packages/schemas/src/index.ts`
- Test: `admin/packages/schemas/src/__tests__/audit.test.ts`

- [ ] **Step 1: Failing test**

```ts
import { describe, expect, it } from "vitest";
import { AUDIT_OPERATION_OPTIONS } from "../audit";

describe("AUDIT_OPERATION_OPTIONS", () => {
  it("lists insert/update/delete with labels", () => {
    expect(AUDIT_OPERATION_OPTIONS.map((o) => o.value)).toEqual([
      "insert",
      "update",
      "delete",
    ]);
    expect(AUDIT_OPERATION_OPTIONS.every((o) => o.label.length > 0)).toBe(true);
  });
});
```

Run: `cd admin && pnpm --filter @sacco/schemas test -- audit` → FAIL.

- [ ] **Step 2: Write `audit.ts`**

```ts
export interface AuditEntryOut {
  id: string;
  table_name: string;
  record_id: string;
  operation: string; // insert | update | delete
  actor_type: string;
  actor_id: string | null;
  actor_label: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  occurred_at: string;
  request_id: string | null;
  impersonation_id: string | null;
}

export interface AuditLogPage {
  items: AuditEntryOut[];
  total: number;
  page: number;
  page_size: number;
}

export const AUDIT_OPERATION_OPTIONS = [
  { value: "insert", label: "Insert" },
  { value: "update", label: "Update" },
  { value: "delete", label: "Delete" },
] as const;
```

- [ ] **Step 3: Export from `index.ts`** — add `export * from "./audit";`.

- [ ] **Step 4: Run → PASS; typecheck + lint the package; commit.**

```bash
cd /home/liam/projects/sacco-platform
git add admin/packages/schemas/src/audit.ts admin/packages/schemas/src/index.ts admin/packages/schemas/src/__tests__/audit.test.ts
git commit -m "feat(portal): audit Out types + operation options

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Portal — fill `resources.audit`

**Files:**
- Modify: `admin/packages/api-client/src/resources/audit.ts`

- [ ] **Step 1: Replace the stub body**

```ts
import type { FetchClient } from "../client";

export function audit(api: FetchClient) {
  return {
    listPlatform: (query?: Record<string, unknown>) =>
      api.GET("/platform/audit-log" as never, { params: { query } } as never),
    listTenant: (tenantId: string, query?: Record<string, unknown>) =>
      api.GET("/platform/tenants/{tenant_id}/audit-log" as never, {
        params: { path: { tenant_id: tenantId }, query },
      } as never),
  } as const;
}
```

> Mirrors `makerChecker.ts`'s `as never` pattern; callers cast results to `{ data?, error? }`.

- [ ] **Step 2: Typecheck the package; commit.**

Run: `cd admin && pnpm --filter @sacco/api-client typecheck` (or the repo's check). Then:

```bash
git add admin/packages/api-client/src/resources/audit.ts
git commit -m "feat(portal): audit api-client resource (listPlatform/listTenant)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `@sacco/ui` — `useTableUrlState` `shallow` option

**Files:**
- Modify: `admin/packages/ui/src/components/DataTable/use-table-url-state.ts`
- Test: `admin/packages/ui/src/components/DataTable/__tests__/use-table-url-state.test.tsx` (create or extend; match existing UI test location)

- [ ] **Step 1: Add the option (additive, default true)**

Add `shallow?: boolean;` to `UseTableUrlStateOptions`. Destructure `shallow = true`. Pass `{ shallow }` as the second arg to **both** `useQueryStates` calls:

```ts
  const [{ page, pageSize, sort, dir, density }, setCore] = useQueryStates(
    {
      page: parseAsInteger.withDefault(1),
      pageSize: parseAsInteger.withDefault(defaultPageSize),
      sort: parseAsString.withDefault(defaultSort?.column ?? ""),
      dir: parseAsString.withDefault(defaultSort?.direction ?? "desc"),
      density: parseAsString.withDefault(defaultDensity),
    },
    { shallow },
  );
  // ...
  const [filterRaw, setFiltersRaw] = useQueryStates(filterParsers, { shallow });
```

> Verify the installed nuqs version's `useQueryStates(parsers, options)` accepts `{ shallow }`. If the option name differs, adjust. Default `true` keeps every existing caller (Invoices/Subscriptions/Users/Tenants/Approvals tables) byte-for-byte unchanged.

- [ ] **Step 2: Test**

Add a unit test asserting the hook returns the expected shape with `shallow:false` passed (rendered via nuqs's testing adapter — `@sacco/ui` HAS nuqs as a direct dep, so `NuqsTestingAdapter` resolves here, unlike in the portal app). If an existing `use-table-url-state` test file exists, extend it; otherwise create one using `NuqsTestingAdapter` from `nuqs/adapters/testing` (it resolves in `@sacco/ui`).

- [ ] **Step 3: Run UI tests + typecheck + lint; commit.**

```bash
cd admin && pnpm --filter @sacco/ui test -- use-table-url-state && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
cd /home/liam/projects/sacco-platform
git add admin/packages/ui/src/components/DataTable/use-table-url-state.ts admin/packages/ui/src/components/DataTable/__tests__/
git commit -m "feat(ui): useTableUrlState shallow option for server-side tables

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Portal — `<JsonDiff>` component

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/audit/_components/JsonDiff.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-audit/JsonDiff.test.tsx`

- [ ] **Step 1: Failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JsonDiff } from "../../../app/platform/(authed)/audit/_components/JsonDiff";

describe("JsonDiff", () => {
  it("shows old and new for a changed key (update)", () => {
    render(<JsonDiff before={{ status: "active" }} after={{ status: "suspended" }} />);
    expect(screen.getByText("status")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("suspended")).toBeInTheDocument();
  });

  it("renders insert (null before) and delete (null after)", () => {
    const { rerender } = render(<JsonDiff before={null} after={{ a: 1 }} />);
    expect(screen.getByText("a")).toBeInTheDocument();
    rerender(<JsonDiff before={{ a: 1 }} after={null} />);
    expect(screen.getByText("a")).toBeInTheDocument();
  });
});
```

Run → FAIL.

- [ ] **Step 2: Implement `JsonDiff.tsx`**

```tsx
function fmt(v: unknown): string {
  if (v === undefined) return "—";
  if (v === null) return "null";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export interface JsonDiffProps {
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export function JsonDiff({ before, after }: JsonDiffProps) {
  const keys = Array.from(
    new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]),
  ).sort();

  if (keys.length === 0) {
    return <p className="text-[var(--text-tertiary)]">No field-level detail.</p>;
  }

  return (
    <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
      <div className="flex gap-4 py-1 text-[12px] text-[var(--text-tertiary)]">
        <span className="w-40">Field</span>
        <span className="flex-1">Before</span>
        <span className="flex-1">After</span>
      </div>
      {keys.map((k) => {
        const b = before?.[k];
        const a = after?.[k];
        const changed = fmt(b) !== fmt(a);
        return (
          <div
            key={k}
            className={`flex gap-4 py-1.5 ${changed ? "" : "opacity-60"}`}
          >
            <span className="w-40 font-mono text-[12px] text-[var(--text-secondary)]">{k}</span>
            <span className="flex-1 font-mono text-[12px] text-[var(--text-primary)]">{fmt(b)}</span>
            <span className="flex-1 font-mono text-[12px] text-[var(--text-primary)]">{fmt(a)}</span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Run → PASS; commit.**

```bash
git add "admin/apps/portal/app/platform/(authed)/audit/_components/JsonDiff.tsx" admin/apps/portal/src/__tests__/platform-audit/JsonDiff.test.tsx
git commit -m "feat(portal): JsonDiff before/after audit renderer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: `@sacco/ui` — `<AuditBar>` evolution (entries/viewAllHref)

**Files:**
- Modify: `admin/packages/ui/src/components/AuditBar/AuditBar.tsx`
- Test: `admin/packages/ui/src/components/AuditBar/AuditBar.test.tsx`

- [ ] **Step 1: Extend the test (keep the existing placeholder test green)**

Add cases: with `entries` provided it renders each operation + actorLabel + a "View Full History" link to `viewAllHref`; with `entries={[]}` it shows "No recent activity"; with no `entries` it still shows the existing "Audit history coming soon" placeholder.

```tsx
it("renders entries + an enabled View Full History link when entries provided", () => {
  render(
    <AuditBar
      entityType="tenant"
      entityId="t1"
      viewAllHref="/platform/audit?f_record_id=t1"
      entries={[
        { id: "a1", operation: "update", actorLabel: "op@test", occurredAt: "2026-06-20T10:00:00Z" },
      ]}
    />,
  );
  expect(screen.getByText(/op@test/)).toBeInTheDocument();
  const link = screen.getByRole("link", { name: /view full history/i });
  expect(link).toHaveAttribute("href", "/platform/audit?f_record_id=t1");
});
```

- [ ] **Step 2: Implement the additive props**

```tsx
import { History } from "lucide-react";

export interface AuditBarEntry {
  id: string;
  operation: string;
  actorLabel: string | null;
  occurredAt: string;
}

export interface AuditBarProps {
  entityType: string;
  entityId: string;
  entries?: AuditBarEntry[];
  viewAllHref?: string;
  isLoading?: boolean;
}

export function AuditBar({ entityType, entityId, entries, viewAllHref, isLoading }: AuditBarProps) {
  const showData = entries !== undefined;
  return (
    <section
      aria-label="Activity"
      data-entity-type={entityType}
      data-entity-id={entityId}
      className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-4"
    >
      <header className="mb-2 flex items-center gap-2 text-[var(--text-secondary)]">
        <History size={16} strokeWidth={1.75} aria-hidden />
        <h3 className="text-[13px] font-semibold uppercase tracking-wider">Activity</h3>
      </header>

      {!showData ? (
        <p className="text-[13px] text-[var(--text-tertiary)]">
          Audit history coming soon — the audit-log query endpoint is pending.
        </p>
      ) : isLoading ? (
        <p className="text-[13px] text-[var(--text-tertiary)]">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-[13px] text-[var(--text-tertiary)]">No recent activity.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {entries.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-3 text-[13px]">
              <span className="text-[var(--text-primary)]">
                {e.operation}
                {e.actorLabel ? ` · ${e.actorLabel}` : ""}
              </span>
              <time className="text-[var(--text-tertiary)]" dateTime={e.occurredAt}>
                {e.occurredAt}
              </time>
            </li>
          ))}
        </ul>
      )}

      {viewAllHref ? (
        <a
          href={viewAllHref}
          className="mt-3 inline-block text-[13px] text-[var(--text-link)] underline-offset-2 hover:underline"
        >
          View Full History
        </a>
      ) : showData ? null : (
        <button type="button" disabled className="mt-3 text-[13px] text-[var(--text-tertiary)] underline-offset-2 disabled:cursor-not-allowed disabled:opacity-60">
          View Full History
        </button>
      )}
    </section>
  );
}
```

> The raw `occurredAt` `<time>` keeps `@sacco/ui`'s AuditBar dependency-free (no RelativeTime import cycle worry); the connected wrapper can pass a pre-formatted label later if desired. Existing placeholder test stays green (no `entries` → placeholder + disabled button).

- [ ] **Step 3: Run UI tests + typecheck + lint; commit.**

```bash
cd admin && pnpm --filter @sacco/ui test -- AuditBar && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
cd /home/liam/projects/sacco-platform
git add admin/packages/ui/src/components/AuditBar/AuditBar.tsx admin/packages/ui/src/components/AuditBar/AuditBar.test.tsx
git commit -m "feat(ui): AuditBar renders entries + View Full History when provided

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Portal — `<AuditTable>` (server-side DataTable) + `<AuditOperationLabel>`

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/audit/_components/AuditOperationLabel.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/audit/_components/AuditTable.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-audit/AuditTable.test.tsx`

- [ ] **Step 1: `AuditOperationLabel.tsx`** (plain coloured text, not StatusBadge)

```tsx
const TONE: Record<string, string> = {
  insert: "text-[var(--text-success)]",
  update: "text-[var(--text-primary)]",
  delete: "text-[var(--text-danger)]",
};

export function AuditOperationLabel({ operation }: { operation: string }) {
  return <span className={`font-medium ${TONE[operation] ?? "text-[var(--text-secondary)]"}`}>{operation}</span>;
}
```

> Verify `--text-success` / `--text-danger` exist (`rg "text-success|text-danger" admin/packages/ui/src/tokens.css`); if named differently (e.g. `--status-*`), adjust.

- [ ] **Step 2: Failing test for `AuditTable`** (mock `useTableUrlState`, as every DataTable test does)

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@sacco/ui", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/ui")>();
  return {
    ...actual,
    useTableUrlState: vi.fn().mockReturnValue({
      page: 1, pageSize: 25, sortColumn: "occurred_at", sortDirection: "desc" as const,
      filters: {}, density: "default" as const,
      setPage: vi.fn(), setPageSize: vi.fn(), setSort: vi.fn(),
      setFilter: vi.fn(), setFilters: vi.fn(), setDensity: vi.fn(), reset: vi.fn(),
    }),
  };
});

import { AuditTable } from "../../../app/platform/(authed)/audit/_components/AuditTable";
import type { AuditEntryOut } from "@sacco/schemas";

const rows: AuditEntryOut[] = [{
  id: "a1", table_name: "tenants", record_id: "r1", operation: "update",
  actor_type: "platform_user", actor_id: "u1", actor_label: "op@test",
  before_state: { x: 1 }, after_state: { x: 2 },
  occurred_at: "2026-06-20T10:00:00Z", request_id: null, impersonation_id: null,
}];

describe("AuditTable", () => {
  it("renders a row with table, operation, and actor", () => {
    render(<AuditTable items={rows} total={1} showImpersonation={false} />);
    expect(screen.getByText("tenants")).toBeInTheDocument();
    expect(screen.getByText("update")).toBeInTheDocument();
    expect(screen.getByText("op@test")).toBeInTheDocument();
  });

  it("shows the empty state when no rows", () => {
    render(<AuditTable items={[]} total={0} showImpersonation={false} />);
    expect(screen.getByText("No audit entries")).toBeInTheDocument();
  });
});
```

Run → FAIL.

- [ ] **Step 3: Implement `AuditTable.tsx`**

Client component. Props: `items: AuditEntryOut[]`, `total: number`, `showImpersonation: boolean`. Columns: When (`<FormattedDateTime>`), Table, Record (mono), Operation (`<AuditOperationLabel>`), Actor (`actor_label ?? actor_id ?? actor_type`), optional Impersonation, and a "Details" button that toggles an inline row via local state holding the expanded id → render `<JsonDiff before={row.before_state} after={row.after_state} />` in a panel below the table (or a `<Dialog>`). Wire `useTableUrlState({ shallow: false, defaultSort: { column: "occurred_at", direction: "desc" }, filterKeys: ["table_name","operation","actor_id","record_id","occurred_from","occurred_to"] })`. Feed `<DataTable data={items} state={{ totalRows: total, isError: false, isPermissionDenied: false }} urlState={urlState} emptyState={{ title: "No audit entries", description: "Audit entries appear as operators and the system act on records." }} filterSlot={<operation Select + text inputs that call urlState.setFilter>} />`.

Because the table is **server-driven**, `data` is exactly the current page's `items` (no client slicing) and `totalRows` is the server `total`. Each `setFilter`/page change updates the URL non-shallow → the parent server page refetches → new `items` arrive as props.

> Full concrete code follows the SP16 `InvoicesTable` shape but **without** the in-memory filter/sort/paginate helpers (the server does that). Keep the inline-diff state minimal (`const [openId, setOpenId] = useState<string|null>(null)`).

- [ ] **Step 4: Run → PASS; commit.**

```bash
git add "admin/apps/portal/app/platform/(authed)/audit/_components/AuditTable.tsx" "admin/apps/portal/app/platform/(authed)/audit/_components/AuditOperationLabel.tsx" admin/apps/portal/src/__tests__/platform-audit/AuditTable.test.tsx
git commit -m "feat(portal): server-side AuditTable + operation label

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: Portal — `/platform/audit` page (server)

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/audit/page.tsx`

- [ ] **Step 1: Implement the server page**

Read `searchParams` (a `Promise` in Next 15 — `await props.searchParams`), translate to the query object (`page`, `page_size`, plus `table_name`, `operation`, `actor_id`, `record_id`, `occurred_from`, `occurred_to` from the `f_*` keys), fetch `resources.audit.listPlatform(query)` cast to `{ data?: AuditLogPage; error? }`, and render `<AuditTable items={data?.items ?? []} total={data?.total ?? 0} showImpersonation={false} />` under an `<h1>Audit</h1>`. Gate `requirePlatformPermission(user, "audit.read")`. On error/undefined, pass empty items + total 0 (the table shows its empty state).

```tsx
export const metadata = { title: "Audit" };

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "audit.read");

  const one = (k: string) => (typeof sp[k] === "string" ? (sp[k] as string) : undefined);
  const query: Record<string, unknown> = {
    page: Number(one("page") ?? "1"),
    page_size: Number(one("pageSize") ?? "25"),
  };
  for (const [spKey, apiKey] of [
    ["f_table_name", "table_name"], ["f_operation", "operation"],
    ["f_actor_id", "actor_id"], ["f_record_id", "record_id"],
    ["f_occurred_from", "occurred_from"], ["f_occurred_to", "occurred_to"],
  ] as const) {
    const v = one(spKey);
    if (v) query[apiKey] = v;
  }

  const { data } = await (
    resources.audit.listPlatform(query) as Promise<{ data?: import("@sacco/schemas").AuditLogPage; error?: unknown }>
  );

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Audit</h1>
      <AuditTable items={data?.items ?? []} total={data?.total ?? 0} showImpersonation={false} />
    </div>
  );
}
```

> Server components re-run when `searchParams` change (non-shallow nav from the table). This is the server-side pagination loop. Confirm the import style for `AuditLogPage` (top-level `import type` is cleaner than inline `import(...)`).

- [ ] **Step 2: Typecheck + lint; commit.**

```bash
git add "admin/apps/portal/app/platform/(authed)/audit/page.tsx"
git commit -m "feat(portal): /platform/audit viewer page (server-side)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 11: Portal — `/platform/tenants/[id]/audit` + TenantDetail link

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/audit/page.tsx`
- Modify: `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx`

- [ ] **Step 1: Tenant audit page** — same shape as Task 10 but `await params` for `id`, call `resources.audit.listTenant(id, query)`, and `<AuditTable ... showImpersonation />`. Gate `audit.read`.

- [ ] **Step 2: Add an "Audit log" link on `TenantDetail`** — a link/button to `/platform/tenants/${t.id}/audit`, gated with the existing permission pattern used on that page (wrap in `<PermissionGuard permission="audit.read">` if the page uses guards, else a plain link; match the file's idiom — read it first).

- [ ] **Step 3: Typecheck + lint; commit.**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/audit/page.tsx" "admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx"
git commit -m "feat(portal): per-tenant audit viewer + TenantDetail link

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 12: Portal — `<AuditBarConnected>` + wire the 6 detail pages

**Files:**
- Create: `admin/apps/portal/src/lib/audit-tables.ts`
- Create: `admin/apps/portal/src/components/AuditBarConnected.tsx`
- Modify the 6 detail pages (subscriptions, plans, invoices, approvals, users `UserDetail`, tenants `TenantDetail`).

- [ ] **Step 1: `audit-tables.ts`** — the entityType→table_name map.

```ts
export const AUDIT_TABLE_BY_ENTITY: Record<string, string> = {
  subscription: "subscriptions",
  subscription_plan: "subscription_plans",
  invoice: "invoices",
  platform_user: "platform_users",
  tenant: "tenants",
  approval_request: "approval_requests",
};
```

- [ ] **Step 2: `AuditBarConnected.tsx`** (server component)

```tsx
import { AuditBar, type AuditBarEntry } from "@sacco/ui";
import type { AuditLogPage } from "@sacco/schemas";
import { getPlatformPageContext } from "@/auth/server-page-context";
import { AUDIT_TABLE_BY_ENTITY } from "@/lib/audit-tables";

export async function AuditBarConnected({
  entityType,
  entityId,
}: {
  entityType: string;
  entityId: string;
}) {
  const table = AUDIT_TABLE_BY_ENTITY[entityType];
  if (!table) return <AuditBar entityType={entityType} entityId={entityId} />;

  const { resources } = await getPlatformPageContext();
  const { data } = await (
    resources.audit.listPlatform({ table_name: table, record_id: entityId, page_size: 5 }) as Promise<{
      data?: AuditLogPage;
      error?: unknown;
    }>
  );
  if (!data) return <AuditBar entityType={entityType} entityId={entityId} />;

  const entries: AuditBarEntry[] = data.items.map((e) => ({
    id: e.id,
    operation: e.operation,
    actorLabel: e.actor_label,
    occurredAt: e.occurred_at,
  }));
  const viewAllHref = `/platform/audit?f_table_name=${table}&f_record_id=${entityId}`;

  return (
    <AuditBar entityType={entityType} entityId={entityId} entries={entries} viewAllHref={viewAllHref} />
  );
}
```

> `AuditBarConnected` calls `getPlatformPageContext()` a second time within a page render; per the SP12 dedup work the server-helpers are React-`cache()`'d, so this reuses the request's auth resolution. Safe.

- [ ] **Step 3: Swap on the 6 detail pages** — replace `import { AuditBar }`/usage with `<AuditBarConnected entityType=… entityId=… />`. Since these pages are already `async` server components, awaiting the connected component is fine (render `<AuditBarConnected .../>` directly — it's an async server component). Keep the same entityType/entityId values.

> `UserDetail.tsx` and `TenantDetail.tsx` may be client components — check. If a detail body is a client component, render `<AuditBarConnected>` from the **server** page that renders it (pass it as a child/slot), not from inside the client component. Read each of the 6 before editing; the billing/approvals detail pages are server components (safe inline), the users/tenants details are split — wire `AuditBarConnected` at the server-page level for those.

- [ ] **Step 4: Typecheck + lint; commit.**

```bash
git add admin/apps/portal/src/lib/audit-tables.ts admin/apps/portal/src/components/AuditBarConnected.tsx "admin/apps/portal/app/platform/(authed)/"
git commit -m "feat(portal): AuditBarConnected wires live audit on detail pages

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 13: Full verification + PR

- [ ] **Step 1: Backend gate**

```bash
cd /home/liam/projects/sacco-platform
export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test
ruff check app/ tests/ && mypy app/ && python -m pytest tests/platform_/audit/ -q
```

- [ ] **Step 2: Portal gate**

```bash
cd /home/liam/projects/sacco-platform/admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/ui test && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test count (rises by JsonDiff + AuditTable + AuditBar cases over SP18's 165).

- [ ] **Step 3: Contract spot-checks**

- [ ] Portal changes under `admin/`; backend under `app/` + `tests/` only (`git diff --name-only main...HEAD | grep -vE '^(admin/|app/|tests/|docs/)'` empty).
- [ ] No new endpoint beyond the two audit-log routes (`git diff main...HEAD -- app/main.py` shows only the audit include).
- [ ] Existing DataTable consumers unchanged by the `shallow` default (`git diff main...HEAD -- admin/packages/ui/src/components/DataTable/use-table-url-state.ts` shows only additive option + `{ shallow }` args).
- [ ] AuditBar placeholder still renders with no `entries` (the original test still passes).

- [ ] **Step 4: Final holistic review** — `superpowers:requesting-code-review` against the branch. Confirm: both endpoints admin-gated; tenant endpoint surfaces `impersonation_id`; server-side pagination loop works (URL change → refetch); AuditBar lights up on all 6 pages and falls back to placeholder on error; JsonDiff handles insert/delete; no `GET /audit-log/{id}` added.

- [ ] **Step 5: Push + PR**

```bash
cd /home/liam/projects/sacco-platform
git push -u origin feat/portal-v1/19-audit-query-and-viewer
gh pr create --title "feat(portal): audit query endpoint + viewer (SP19 / P1.7-F)" --body "$(cat <<'EOF'
## Summary
- **Backend (P1.7-F):** new `app/platform_/audit/` module — `GET /platform/audit-log` (platform schema) + `GET /platform/tenants/{id}/audit-log` (tenant schema, surfaces `impersonation_id`), both `CurrentAdmin`, paginated + filtered via a schema-agnostic `AuditQueryService`.
- **Portal:** `@sacco/schemas` audit types + filled `resources.audit`; the portal's first **true server-side paginated** `<DataTable>` (additive `shallow` option on `useTableUrlState`); `/platform/audit` + `/platform/tenants/[id]/audit` viewers with an inline before/after `<JsonDiff>`; the `@sacco/ui` `<AuditBar>` now renders real entries via `<AuditBarConnected>` on all 6 platform detail pages (placeholder fallback on error).
- Unblocks the long-pending Phase-1.7-F dependency.

## Test plan
- Backend: `pytest tests/platform_/audit/` (filters, pagination envelope, ordering, tenant `impersonation_id`); ruff + mypy clean.
- Portal: `@sacco/schemas` + `@sacco/ui` + `@sacco/portal` test/typecheck/lint green (JsonDiff, AuditTable, AuditBar, useTableUrlState shallow). Backend under `app/`+`tests/`; portal under `admin/`.

> CI note: Lint fails environmentally on this repo (account billing lock); reproduced clean locally. Not a required check.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** backend module/service → T1; endpoints + mount → T2; tenant `impersonation_id` proof → T3; schemas → T4; api-client → T5; `shallow` option → T6; JsonDiff → T7; AuditBar evolution → T8; AuditTable → T9; platform viewer → T10; tenant viewer + link → T11; AuditBarConnected + 6-page wiring → T12; verification/PR → T13.
- **Decisions honoured:** two endpoints (T2), proper server-side pagination (T6+T9+T10), presentational AuditBar + connected wrapper (T8+T12), one PR backend-first (commit order T1→T13). No `GET /audit-log/{id}` (inline JsonDiff, T7/T9).
- **Type consistency:** `AuditEntryOut`/`AuditLogPage` fields identical backend (T1) ↔ portal (T4) ↔ consumers (T9/T10/T11/T12). `AuditBarEntry` (T8) matches the map in `AuditBarConnected` (T12). `AuditTable` props (`items`/`total`/`showImpersonation`) match T10/T11 call sites.
- **Verify-at-execution (grep inline):** nuqs `useQueryStates(parsers, {shallow})` option name; `--text-success`/`--text-danger` (or `--status-*`) tokens; whether each of the 6 detail bodies is a server or client component (wire AuditBarConnected at server-page level for client ones); `NuqsTestingAdapter` import path in `@sacco/ui` tests; Next 15 `searchParams`/`params` are Promises.
