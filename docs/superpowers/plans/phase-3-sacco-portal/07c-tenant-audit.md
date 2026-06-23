# SACCO Admin Portal — Tenant Audit Log (Phase 3g-3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-23):** run **inline** (background subagents can't get Edit approval). **Confirm typecheck PASSES before committing.** Backend tests use real Postgres: `export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test` after `docker compose up -d postgres-test`. Portal/package tests via `pnpm --filter` from `admin/`; **`git` from the repo root** (the shell cwd drifts into `admin/` after pnpm runs).
> **Test gotchas (carry-over):** DataTable tests `vi.mock("@sacco/ui", …)` `useTableUrlState`; `TData` extends `{ id: string }`; FormattedDate(Time) needs no extra provider here (the existing AuditTable test renders without one — keep it that way); `git mv` to preserve history.

**Goal:** Fill the last dead tenant sidebar link (`/audit`) with an operator audit-log viewer, backed by one new tenant-context endpoint.

**Architecture:** Add a tenant-context `GET /audit-log` (gated `CurrentTenantUser`, `get_tenant_session`, querying `TenantAuditLog` via the reused schema-agnostic `AuditQueryService`) as a second router in `app/platform_/audit/api.py`. Relocate the SP19 audit viewer components to a shared `src/components/audit/`, add an `audit.listOperator` api-client method, and clone the platform `/audit` index page as the operator `/audit` page. Un-gate the tenant sidebar's audit link.

**Tech Stack:** FastAPI + SQLAlchemy (one new endpoint), Next.js 15 / React 19 / TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library, pytest (real Postgres).

## Global Constraints

- **Branch:** `feat/sacco-portal/07c-tenant-audit`, off `main` (no PR stacking).
- **One new backend endpoint** (`GET /audit-log`, operator). Reuse `AuditQueryService` + `AuditEntryOut`/`AuditLogPage` unchanged. Gate `CurrentTenantUser`. No new permission tier.
- **One api-client change** (`audit.listOperator`). No schema changes (`@sacco/schemas/audit.ts` is complete).
- **Tenant gating only** in the portal — `/audit` page uses `getTenantPageContext()` (auth-only, no permission keys). UI gating is UX; the API enforces (contract D).
- Relocation of audit viewer components must keep the **platform** audit pages + their tests green (regression guard).
- Money/dates via `@sacco/ui` primitives; server-side paginated `<DataTable>` via `useTableUrlState({ shallow: false })`. **DRY/YAGNI/TDD, frequent commits.**

---

## Task 1: Backend — operator `GET /audit-log`

**Files:**
- Modify: `app/platform_/audit/api.py` (add `tenant_router`)
- Modify: `app/main.py` (mount it)
- Test: `tests/platform_/audit/test_audit_api.py` (add operator-route test)

**Interfaces:**
- Consumes: `AuditQueryService`, `TenantAuditLog`, `get_tenant_session`, `CurrentTenantUser`, `AuditEntryOut`, `AuditLogPage` (all exist).
- Produces: `GET /audit-log` → `AuditLogPage` (operator's own tenant schema).

- [ ] **Step 1: Write the failing test**

Add to `tests/platform_/audit/test_audit_api.py`. Mirror the existing tenant-schema override + the `tests/modules/maker_checker/test_api.py` tenant-auth pattern (stub headers `X-Tenant-Slug` + `X-Tenant-Actor-ID`; the actor must exist in `tenant_users`):

```python
from app.core.db import get_tenant_session


async def _seed_tenant_user(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        uid = uuid.uuid4()
        await s.execute(
            text(
                "INSERT INTO tenant_users "
                "(id, email, full_name, is_active, is_admin, created_at, updated_at) "
                "VALUES (:id, :email, 'Op', true, true, now(), now())"
            ),
            {"id": uid, "email": f"op-{uid.hex[:6]}@test.example"},
        )
    return uid


async def test_operator_audit_endpoint_lists_own_tenant(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    rid = uuid.uuid4()
    actor_id = await _seed_tenant_user(factory)
    try:
        async with factory() as s, s.begin():
            await s.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
            for op in ("insert", "update"):
                s.add(
                    TenantAuditLog(
                        table_name="members",
                        record_id=rid,
                        operation=op,
                        actor_type="tenant_user",
                        actor_id=actor_id,
                        actor_label="op@test",
                        before_state=None,
                        after_state={"status": "active"},
                        occurred_at=datetime.now(UTC),
                    )
                )
        app.dependency_overrides[get_tenant_session] = _make_tenant_schema_override(test_engine)
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get(
                    f"/audit-log?record_id={rid}&page_size=10",
                    headers={"X-Tenant-Slug": "test-tenant", "X-Tenant-Actor-ID": str(actor_id)},
                )
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["total"] == 2
                assert {i["operation"] for i in body["items"]} == {"insert", "update"}
                # filter narrows
                r2 = await client.get(
                    f"/audit-log?record_id={rid}&operation=update",
                    headers={"X-Tenant-Slug": "test-tenant", "X-Tenant-Actor-ID": str(actor_id)},
                )
                assert r2.json()["total"] == 1
    finally:
        app.dependency_overrides.clear()
        async with factory() as s, s.begin():
            await s.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
            await s.execute(text(f"DELETE FROM {TEST_TENANT_SCHEMA}.audit_log"))  # noqa: S608
            await s.execute(
                text(f"DELETE FROM {TEST_TENANT_SCHEMA}.tenant_users WHERE id = :id"),  # noqa: S608
                {"id": actor_id},
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test && python -m pytest tests/platform_/audit/test_audit_api.py::test_operator_audit_endpoint_lists_own_tenant -v`
Expected: FAIL — 404 (route `/audit-log` does not exist yet).

- [ ] **Step 3: Add the operator router**

In `app/platform_/audit/api.py`, add the imports and a second router. Add to the existing imports:

```python
from app.core.db import get_platform_session, get_session_for_tenant_schema, get_tenant_session
from app.modules.iam.dependencies import CurrentTenantUser
```

After the existing `router` definition + `TenantSchemaSession` alias, add:

```python
tenant_router = APIRouter(tags=["audit"])

TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]


@tenant_router.get("/audit-log", response_model=AuditLogPage)
async def list_operator_audit(
    session: TenantSession,
    _user: CurrentTenantUser,
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
        table_name=table_name,
        record_id=record_id,
        actor_id=actor_id,
        actor_type=actor_type,
        operation=operation,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        page=page,
        page_size=page_size,
    )
    return _page(rows, total, page, page_size)
```

- [ ] **Step 4: Mount it in `app/main.py`**

Next to the existing platform audit import + include:

```python
from app.platform_.audit.api import router as platform_audit_router
from app.platform_.audit.api import tenant_router as tenant_audit_router
```

```python
app.include_router(platform_audit_router)
app.include_router(tenant_audit_router)
```

- [ ] **Step 5: Run test + lint to verify it passes**

Run: `python -m pytest tests/platform_/audit/test_audit_api.py -v && ruff check app/platform_/audit/api.py app/main.py && mypy app/platform_/audit/api.py`
Expected: PASS (all audit tests), ruff/mypy clean.

- [ ] **Step 6: Commit**

```bash
git add app/platform_/audit/api.py app/main.py tests/platform_/audit/test_audit_api.py
git commit -m "feat(audit): operator GET /audit-log (tenant-context)"
```

---

## Task 2: Portal — relocate audit viewer to shared components

**Files:**
- Move: `app/platform/(authed)/audit/_components/{AuditTable,JsonDiff,AuditOperationLabel}.tsx` → `src/components/audit/`
- Modify: `app/platform/(authed)/audit/page.tsx`, `app/platform/(authed)/tenants/[id]/audit/page.tsx` (import paths)
- Modify: `src/__tests__/platform-audit/{AuditTable,JsonDiff}.test.tsx` (import paths)
- Modify: `src/components/audit/AuditTable.tsx` (add `tableId` prop)

**Interfaces:**
- Produces: `@sacco`-style shared `@/components/audit/AuditTable` with new optional `tableId?: string` (default `"platform-audit"`).

- [ ] **Step 1: Move the three components (preserve history)**

```bash
mkdir -p admin/apps/portal/src/components/audit
git mv "admin/apps/portal/app/platform/(authed)/audit/_components/AuditTable.tsx" admin/apps/portal/src/components/audit/AuditTable.tsx
git mv "admin/apps/portal/app/platform/(authed)/audit/_components/JsonDiff.tsx" admin/apps/portal/src/components/audit/JsonDiff.tsx
git mv "admin/apps/portal/app/platform/(authed)/audit/_components/AuditOperationLabel.tsx" admin/apps/portal/src/components/audit/AuditOperationLabel.tsx
```

(`AuditTable.tsx`'s `./JsonDiff` + `./AuditOperationLabel` relative imports stay valid — all three moved together.)

- [ ] **Step 2: Add the `tableId` prop to `AuditTable.tsx`**

Change the component signature + the `<DataTable>` id. From:

```tsx
export function AuditTable({
  items,
  total,
  showImpersonation,
}: {
  items: AuditEntryOut[];
  total: number;
  showImpersonation: boolean;
}) {
```

to:

```tsx
export function AuditTable({
  items,
  total,
  showImpersonation,
  tableId = "platform-audit",
}: {
  items: AuditEntryOut[];
  total: number;
  showImpersonation: boolean;
  tableId?: string;
}) {
```

and change `<DataTable<AuditEntryOut> id="platform-audit"` to `<DataTable<AuditEntryOut> id={tableId}`.

- [ ] **Step 3: Update the two platform page imports**

In `app/platform/(authed)/audit/page.tsx`, replace
`import { AuditTable } from "./_components/AuditTable";`
with
`import { AuditTable } from "@/components/audit/AuditTable";`

In `app/platform/(authed)/tenants/[id]/audit/page.tsx`, replace
`import { AuditTable } from "../../../audit/_components/AuditTable";`
with
`import { AuditTable } from "@/components/audit/AuditTable";`

- [ ] **Step 4: Update the two test imports**

In `src/__tests__/platform-audit/AuditTable.test.tsx`, replace
`import { AuditTable } from "../../../app/platform/(authed)/audit/_components/AuditTable";`
with
`import { AuditTable } from "../../components/audit/AuditTable";`

In `src/__tests__/platform-audit/JsonDiff.test.tsx`, replace
`import { JsonDiff } from "../../../app/platform/(authed)/audit/_components/JsonDiff";`
with
`import { JsonDiff } from "../../components/audit/JsonDiff";`

- [ ] **Step 5: Verify platform audit unchanged (regression guard)**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- platform-audit && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS (AuditTable + JsonDiff tests green from the new path), typecheck/lint clean.

- [ ] **Step 6: Commit**

```bash
git add admin/apps/portal/src/components/audit admin/apps/portal/app admin/apps/portal/src/__tests__/platform-audit
git commit -m "refactor(portal): relocate audit viewer to shared components/audit + tableId prop"
```

---

## Task 3: Portal — operator `/audit` page + api-client + sidebar

**Files:**
- Modify: `admin/packages/api-client/src/resources/audit.ts` (add `listOperator`)
- Create: `admin/apps/portal/app/(tenant-authed)/audit/page.tsx`
- Modify: `admin/apps/portal/src/components/AppShellSidebar.tsx` (un-gate tenant `/audit`)

**Interfaces:**
- Consumes: `resources.audit.listOperator(query)` → `AuditLogPage`; `AuditTable`; `getTenantPageContext()`.

- [ ] **Step 1: Add the api-client method**

In `admin/packages/api-client/src/resources/audit.ts`, add inside the returned object:

```ts
    listOperator: (query?: Record<string, unknown>) =>
      api.GET("/audit-log" as never, { params: { query } } as never),
```

- [ ] **Step 2: Typecheck the api-client**

Run (from `admin/`): `pnpm --filter @sacco/api-client typecheck`
Expected: clean.

- [ ] **Step 3: Create the operator `/audit` page**

`admin/apps/portal/app/(tenant-authed)/audit/page.tsx` (clone of the platform `/audit` index page; auth-only, `listOperator`, distinct `tableId`):

```tsx
import type { AuditLogPage } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { AuditTable } from "@/components/audit/AuditTable";

export const metadata = { title: "Audit" };

const FILTER_KEYS = [
  ["f_table_name", "table_name"],
  ["f_operation", "operation"],
  ["f_actor_id", "actor_id"],
  ["f_record_id", "record_id"],
  ["f_occurred_from", "occurred_from"],
  ["f_occurred_to", "occurred_to"],
] as const;

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const { resources } = await getTenantPageContext();

  const one = (k: string): string | undefined =>
    typeof sp[k] === "string" ? (sp[k] as string) : undefined;

  const query: Record<string, unknown> = {
    page: Number(one("page") ?? "1"),
    page_size: Number(one("pageSize") ?? "25"),
  };
  for (const [spKey, apiKey] of FILTER_KEYS) {
    const v = one(spKey);
    if (v) query[apiKey] = v;
  }

  const { data } = await (resources.audit.listOperator(query) as Promise<{
    data?: AuditLogPage;
    error?: unknown;
  }>);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Audit log</h1>
      <AuditTable
        items={data?.items ?? []}
        total={data?.total ?? 0}
        tableId="tenant-audit"
        showImpersonation={false}
      />
    </div>
  );
}
```

- [ ] **Step 4: Un-gate the tenant sidebar `/audit` link**

In `admin/apps/portal/src/components/AppShellSidebar.tsx`, inside the `variant === "tenant"` "Approvals & Audit" group, remove the `<PermissionGuard permission="audit.read">` wrapper around the `/audit` `SidebarItem` so it reads:

```tsx
              <SidebarItem
                href="/audit"
                icon={<History size={ICON_SIZE} strokeWidth={1.75} />}
                label="Audit"
                active={isActive("/audit")}
              />
```

Leave the **platform** variant's `audit.read`-guarded `/platform/audit` item unchanged.

- [ ] **Step 5: Full verification**

Run (from `admin/`):
```bash
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Run (from repo root):
```bash
export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test
python -m pytest tests/platform_/audit/ -v && ruff check app/platform_/audit/ app/main.py && mypy app/platform_/audit/
```
Expected: all green. Record the portal test count.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/api-client/src/resources/audit.ts \
        "admin/apps/portal/app/(tenant-authed)/audit/page.tsx" \
        admin/apps/portal/src/components/AppShellSidebar.tsx
git commit -m "feat(portal): tenant operator audit log page (Phase 3g-3)"
```

---

## Self-Review checklist (run before finishing)

- **Spec coverage:** new operator endpoint (Task 1) ✓, viewer relocation + reuse (Task 2) ✓, api-client method + operator page + sidebar un-gate (Task 3) ✓.
- **No schema changes**; `AuditQueryService` + `AuditEntryOut`/`AuditLogPage` reused unchanged.
- **Regression:** platform audit tests pass from the relocated path (Task 2 Step 5).
- **Contracts:** operator gate = `CurrentTenantUser`; portal page auth-only via `getTenantPageContext()`; UI gating is UX (sidebar un-gated, API enforces); server-side paginated `<DataTable>`.
- **Type consistency:** `AuditTable` `tableId` optional default preserves platform behavior; operator passes `"tenant-audit"` + `showImpersonation={false}`.
