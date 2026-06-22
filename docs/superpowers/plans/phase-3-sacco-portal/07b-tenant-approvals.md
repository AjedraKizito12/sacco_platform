# SACCO Admin Portal — Tenant Approvals Inbox (Phase 3g-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-22):** run **inline** (background subagents can't get Edit approval). **Confirm typecheck PASSES before committing.** Backend tests use real Postgres: `export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test` after `docker compose up -d postgres-test`. Portal/package tests via `pnpm --filter` from `admin/`; **`git` from the repo root** (the shell cwd drifts into `admin/` after pnpm runs).
> **Test gotchas (carry-over):** DataTable tests must `vi.mock("@sacco/ui", …)` `useTableUrlState` (nuqs has no resolvable test adapter); `<DataTable>` `TData` must extend `{ id: string }`; checkboxes/selects in a Radix Dialog may need `fireEvent`; uuid-typed schema fields need real-UUID fixtures; required-asterisk + prefix labels collide in `getByLabelText` (use distinct labels).

**Goal:** Build the tenant-operator maker-checker **checker** side — an approvals inbox, my-submissions list, and a detail page with approve / reject / cancel — filling the dead `/approvals` tenant sidebar link.

**Architecture:** A small additive backend parity change brings the tenant `/approvals` list+get endpoints level with the platform SP17 ones (enrich `current_approvals`, add `requested_by` filter + ordering, return `ApprovalRequestDetailOut` with the actions trail). The portal screens clone `app/platform/(authed)/approvals/*`, swapping platform resources/queryKeys/name-resolution for the tenant equivalents and dropping permission gating (tenant auth only).

**Tech Stack:** FastAPI + SQLAlchemy (backend parity), Next.js 15 / React 19 / TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library, pytest (real Postgres).

## Global Constraints

- **Branch:** `feat/sacco-portal/07b-tenant-approvals`, off `main` (no PR stacking).
- **Backend change is additive parity only** — no new endpoints, no renamed/removed fields, gate stays `CurrentTenantUser`. Confined to `app/modules/maker_checker/api.py` + its test.
- **No api-client changes.** `resources.makerChecker.{listTenant, getTenant, approveTenant, rejectTenant, cancelTenant}` exist (cast `{ data?, error? }`). queryKeys `approvals.tenant(filters)` + `approvals.detail(id)` exist.
- **Tenant gating only** — pages use `getTenantPageContext()` (redirects to `/login`); **no permission keys** (`approvals.read`/`approvals.approve` are platform-only). All authed tenant users may approve; the backend rejects self-approval (`ValueError` → 400).
- **No requester name resolution** (no tenant users-list endpoint) → show the requester id, marked **"(you)"** when it equals `currentUser.id`.
- **No `<AuditBar>`** (tenant records; 3g-3 owns `/audit`). **No update_sensitive diff** in `PayloadView` (platform-only).
- Money → `<Money>`; dates → `<FormattedDate>` / `<FormattedDateTime>`; status → `<StatusBadge entity="approval_request">`. The reject reason min is **10 chars** (`rejectActionSchema`). **DRY/YAGNI/TDD, frequent commits.**

---

## Task 1: Backend — tenant `/approvals` list+get parity

**Files:**
- Modify: `app/modules/maker_checker/api.py` (the tenant `list_approvals` + `get_approval` handlers)
- Test: `tests/modules/maker_checker/test_tenant_api.py` (create or extend if present)

**Interfaces:**
- Consumes: `ApprovalService.approval_count(id)`, `ApprovalService.list_actions(id)`, `ApprovalRequestDetailOut`, `ApprovalActionOut` (all already exist).
- Produces: `GET /approvals?requested_by=<uuid>` filter + enriched `current_approvals`; `GET /approvals/{id}` → `ApprovalRequestDetailOut` with `current_approvals` + `actions`.

- [ ] **Step 1: Check for an existing tenant maker-checker test module**

Run: `ls tests/modules/maker_checker/`
If `test_tenant_api.py` exists, extend it; otherwise create it. Read `tests/modules/maker_checker/test_platform_api.py` for the shared `client` fixture + tenant-auth header helper (tenant routes use `CurrentTenantUser`; copy the exact fixture/header pattern that the existing tenant maker-checker tests or other tenant-route tests use — e.g. default tenant headers + `get_tenant_session` override).

- [ ] **Step 2: Write the failing tests**

Add to `tests/modules/maker_checker/test_tenant_api.py` (adapt the auth/fixture wiring to the real harness found in Step 1). A quorum-2 request with one approval must list `current_approvals == 1`, the detail must carry the actions trail, and `requested_by` must filter:

```python
async def test_tenant_list_enriches_current_approvals(client, ...):
    # submit a quorum-2 approval as user A, approve once as user B
    submit = await client.post("/approvals", json={
        "operation_type": "credit.write_off",
        "payload": {"loan_id": str(uuid.uuid4()), "amount": "100.00"},
        "required_approvals": 2,
    }, headers=hdr_user_a)
    rid = submit.json()["id"]
    await client.post(f"/approvals/{rid}/approve", json={"comment": "ok"}, headers=hdr_user_b)

    listed = await client.get("/approvals", headers=hdr_user_a)
    assert listed.status_code == 200
    row = next(r for r in listed.json() if r["id"] == rid)
    assert row["current_approvals"] == 1
    assert row["required_approvals"] == 2


async def test_tenant_get_returns_actions_trail(client, ...):
    submit = await client.post("/approvals", json={
        "operation_type": "members.change_status",
        "payload": {"member_id": str(uuid.uuid4()), "new_status": "suspended"},
        "required_approvals": 2,
    }, headers=hdr_user_a)
    rid = submit.json()["id"]
    await client.post(f"/approvals/{rid}/approve", json={"comment": "looks fine"}, headers=hdr_user_b)

    detail = await client.get(f"/approvals/{rid}", headers=hdr_user_a)
    assert detail.status_code == 200
    body = detail.json()
    assert body["current_approvals"] == 1
    assert len(body["actions"]) == 1
    assert body["actions"][0]["action"] == "approve"
    assert body["actions"][0]["comment"] == "looks fine"


async def test_tenant_list_filters_by_requested_by(client, ...):
    a = await client.post("/approvals", json={
        "operation_type": "savings.withdraw",
        "payload": {"account_id": str(uuid.uuid4()), "amount": "5.00"},
    }, headers=hdr_user_a)
    await client.post("/approvals", json={
        "operation_type": "savings.withdraw",
        "payload": {"account_id": str(uuid.uuid4()), "amount": "6.00"},
    }, headers=hdr_user_b)
    rid_a = a.json()["id"]
    listed = await client.get(f"/approvals?requested_by={user_a_id}", headers=hdr_user_a)
    ids = {r["id"] for r in listed.json()}
    assert rid_a in ids
    assert all(r["requested_by"] == str(user_a_id) for r in listed.json())
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test && python -m pytest tests/modules/maker_checker/test_tenant_api.py -v`
Expected: FAIL — list shows `current_approvals == 0` and detail has no `actions` key.

- [ ] **Step 4: Update the tenant handlers to mirror `platform_api.py`**

In `app/modules/maker_checker/api.py`:

Add the import (alongside the existing schema imports):

```python
from app.modules.maker_checker.schemas import (
    ApprovalActionOut,
    ApprovalActionRequest,
    ApprovalRequestDetailOut,
    ApprovalRequestOut,
    RejectRequest,
    SubmitApprovalRequest,
)
```

Replace `list_approvals` with the enriched, ordered, filterable version:

```python
@router.get("", response_model=list[ApprovalRequestOut])
async def list_approvals(
    session: Session,
    user: CurrentTenantUser,
    status: str | None = Query(None),
    operation_type: str | None = Query(None),
    requested_by: uuid.UUID | None = Query(None),
) -> list[ApprovalRequestOut]:
    q = select(TenantApprovalRequest).order_by(TenantApprovalRequest.requested_at.desc())
    if status:
        q = q.where(TenantApprovalRequest.status == status)
    if operation_type:
        q = q.where(TenantApprovalRequest.operation_type == operation_type)
    if requested_by is not None:
        q = q.where(TenantApprovalRequest.requested_by == requested_by)
    rows = (await session.execute(q)).scalars().all()
    svc = ApprovalService(session)
    out: list[ApprovalRequestOut] = []
    for r in rows:
        dto = ApprovalRequestOut.model_validate(r)
        dto.current_approvals = await svc.approval_count(r.id)
        out.append(dto)
    return out
```

Replace `get_approval` to return the detail variant:

```python
@router.get("/{request_id}", response_model=ApprovalRequestDetailOut)
async def get_approval(
    request_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> ApprovalRequestDetailOut:
    row = (
        await session.execute(
            select(TenantApprovalRequest).where(TenantApprovalRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    svc = ApprovalService(session)
    dto = ApprovalRequestDetailOut.model_validate(row)
    dto.current_approvals = await svc.approval_count(row.id)
    dto.actions = [ApprovalActionOut.model_validate(a) for a in await svc.list_actions(row.id)]
    return dto
```

- [ ] **Step 5: Run tests + lint to verify they pass**

Run: `python -m pytest tests/modules/maker_checker/test_tenant_api.py -v && ruff check app/modules/maker_checker/api.py && mypy app/modules/maker_checker/api.py`
Expected: PASS, ruff/mypy clean.

- [ ] **Step 6: Commit**

```bash
git add app/modules/maker_checker/api.py tests/modules/maker_checker/test_tenant_api.py
git commit -m "feat(maker-checker): tenant /approvals list+get parity with platform"
```

---

## Task 2: `@sacco/schemas` — tenant operation labels

**Files:**
- Modify: `admin/packages/schemas/src/approvals.ts`
- Test: `admin/packages/schemas/src/__tests__/approvals.test.ts` (create if absent)

**Interfaces:**
- Produces: `TENANT_OPERATION_LABELS` map; `operationLabel()` now resolves tenant operations too.

- [ ] **Step 1: Write the failing test**

Create/extend `admin/packages/schemas/src/__tests__/approvals.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { operationLabel } from "../approvals";

describe("operationLabel (tenant)", () => {
  it("labels the tenant operations", () => {
    expect(operationLabel("members.change_status")).toBe("Change member status");
    expect(operationLabel("savings.withdraw")).toBe("Withdraw from savings");
    expect(operationLabel("shares.redeem_shares")).toBe("Redeem shares");
    expect(operationLabel("credit.approve_application")).toBe("Approve loan application");
    expect(operationLabel("credit.write_off")).toBe("Write off loan");
    expect(operationLabel("credit.restructure_schedule")).toBe("Restructure loan schedule");
    expect(operationLabel("credit.apply_payroll_batch")).toBe("Apply payroll batch");
    expect(operationLabel("ledger.post_journal_entry")).toBe("Post manual GL entry");
  });
  it("still humanizes an unknown operation", () => {
    expect(operationLabel("widgets.frobnicate")).toBe("Frobnicate");
  });
  it("still resolves platform operations", () => {
    expect(operationLabel("billing.void_invoice")).toBe("Void invoice");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/schemas test -- approvals`
Expected: FAIL — tenant operations humanize to "Change status" / "Withdraw" / etc., not the friendly labels.

- [ ] **Step 3: Add the tenant labels + consult both maps**

In `admin/packages/schemas/src/approvals.ts`, after `PLATFORM_OPERATION_LABELS`:

```ts
export const TENANT_OPERATION_LABELS: Record<string, string> = {
  "members.change_status": "Change member status",
  "savings.withdraw": "Withdraw from savings",
  "shares.redeem_shares": "Redeem shares",
  "credit.approve_application": "Approve loan application",
  "credit.write_off": "Write off loan",
  "credit.restructure_schedule": "Restructure loan schedule",
  "credit.apply_payroll_batch": "Apply payroll batch",
  "ledger.post_journal_entry": "Post manual GL entry",
};
```

Update `operationLabel` to consult both maps (namespaces don't collide):

```ts
export function operationLabel(operationType: string): string {
  const known = PLATFORM_OPERATION_LABELS[operationType] ?? TENANT_OPERATION_LABELS[operationType];
  if (known) return known;
  const tail = operationType.split(".").pop() ?? operationType;
  const words = tail.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
```

- [ ] **Step 4: Run test + typecheck/lint to verify pass**

Run (from `admin/`): `pnpm --filter @sacco/schemas test -- approvals && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/schemas/src/approvals.ts admin/packages/schemas/src/__tests__/approvals.test.ts
git commit -m "feat(schemas): tenant operation labels for approvals"
```

---

## Task 3: Portal — `ApprovalsTable` + inbox + my-submissions

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/approvals/_components/ApprovalsTable.tsx`
- Create: `admin/apps/portal/app/(tenant-authed)/approvals/page.tsx`
- Create: `admin/apps/portal/app/(tenant-authed)/approvals/my-submissions/page.tsx`
- Test: `admin/apps/portal/src/__tests__/tenant-approvals/ApprovalsTable.test.tsx`

**Interfaces:**
- Consumes: `resources.makerChecker.listTenant(query)` → `ApprovalRequestOut[]`; `operationLabel`; `getTenantPageContext()` → `{ user, resources }`.
- Produces: `ApprovalsTable({ rows: ApprovalRow[] })`; `ApprovalRow` (id, operation_label, status, current_approvals, required_approvals, requested_by_label, requested_at).

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/src/__tests__/tenant-approvals/ApprovalsTable.test.tsx`. Mock `useTableUrlState` (DataTable harness, copy the mock block from `src/__tests__/tenant-ledger/JournalEntriesTable.test.tsx`):

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@sacco/ui", async () => {
  const actual = await vi.importActual<typeof import("@sacco/ui")>("@sacco/ui");
  return {
    ...actual,
    useTableUrlState: () => ({
      page: 1, pageSize: 25, sortColumn: "requested_at", sortDirection: "desc",
      filters: {}, density: "default",
      setPage: vi.fn(), setPageSize: vi.fn(), setSort: vi.fn(),
      setFilter: vi.fn(), setFilters: vi.fn(), setDensity: vi.fn(), reset: vi.fn(),
    }),
  };
});

import { ApprovalsTable, type ApprovalRow } from "../../../app/(tenant-authed)/approvals/_components/ApprovalsTable";

const ROW: ApprovalRow = {
  id: "550e8400-e29b-41d4-a716-446655440000",
  operation_type: "credit.write_off",
  operation_label: "Write off loan",
  status: "pending",
  current_approvals: 1,
  required_approvals: 2,
  requested_by_label: "you",
  requested_at: "2026-06-22T10:00:00Z",
};

describe("ApprovalsTable", () => {
  it("links the operation to the detail page and shows the quorum", () => {
    render(<ApprovalsTable rows={[ROW]} />);
    const link = screen.getByRole("link", { name: "Write off loan" });
    expect(link).toHaveAttribute("href", "/approvals/550e8400-e29b-41d4-a716-446655440000");
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
  });

  it("renders the empty state", () => {
    render(<ApprovalsTable rows={[]} />);
    expect(screen.getByText("No approval requests")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- tenant-approvals/ApprovalsTable`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `ApprovalsTable.tsx`**

Clone the platform table, retarget links to `/approvals/${id}` and keep the in-memory filter/sort/paginate helpers:

```tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable, type DataTableProps, FormattedDate,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  StatusBadge, useTableUrlState,
} from "@sacco/ui";

export interface ApprovalRow {
  id: string;
  operation_type: string;
  operation_label: string;
  status: string;
  current_approvals: number;
  required_approvals: number;
  requested_by_label: string;
  requested_at: string;
}

const STATUS_FILTER_OPTIONS = [
  "pending", "approved", "rejected", "executed", "execution_failed", "expired", "cancelled",
] as const;

const columns: DataTableProps<ApprovalRow>["columns"] = [
  {
    id: "operation_label", accessorKey: "operation_label", header: "Operation",
    cell: ({ row }) => (
      <Link href={`/approvals/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline">
        {row.original.operation_label}
      </Link>
    ),
  },
  {
    id: "status", accessorKey: "status", header: "Status",
    cell: ({ row }) => <StatusBadge entity="approval_request" status={row.original.status} />,
  },
  {
    id: "quorum", accessorKey: "current_approvals", header: "Quorum", enableSorting: false,
    cell: ({ row }) => (
      <span className="tabular-nums">
        {row.original.current_approvals} of {row.original.required_approvals}
      </span>
    ),
  },
  { id: "requested_by_label", accessorKey: "requested_by_label", header: "Requested by" },
  {
    id: "requested_at", accessorKey: "requested_at", header: "Requested",
    cell: ({ row }) => <FormattedDate value={row.original.requested_at} />,
  },
];

export function filterApprovals(rows: ApprovalRow[], status: string | undefined): ApprovalRow[] {
  if (!status) return rows;
  return rows.filter((r) => r.status === status);
}

export function sortApprovals(
  rows: ApprovalRow[], column: string | null, dir: "asc" | "desc",
): ApprovalRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) =>
    String(a[column as keyof ApprovalRow] ?? "").localeCompare(
      String(b[column as keyof ApprovalRow] ?? ""),
    ),
  );
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function ApprovalsTable({ rows }: { rows: ApprovalRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "requested_at", direction: "desc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterApprovals(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );
  const sorted = useMemo(
    () => sortApprovals(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<ApprovalRow>
      id="tenant-approvals"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: filtered.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No approval requests",
        description: "Maker-checker requests from members, savings, shares, credit, and ledger flows appear here.",
      }}
      filterSlot={
        <Select
          value={urlState.filters["status"] ?? "all"}
          onValueChange={(v) => urlState.setFilter("status", v === "all" ? null : v)}
        >
          <SelectTrigger className="w-48" aria-label="Filter by status">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_FILTER_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    />
  );
}
```

- [ ] **Step 4: Create the inbox page**

`admin/apps/portal/app/(tenant-authed)/approvals/page.tsx`:

```tsx
import type { ApprovalRequestOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { ApprovalsTable, type ApprovalRow } from "./_components/ApprovalsTable";

export const metadata = { title: "Approvals" };

function toRows(requests: ApprovalRequestOut[], currentUserId: string): ApprovalRow[] {
  return requests.map((r) => ({
    id: r.id,
    operation_type: r.operation_type,
    operation_label: operationLabel(r.operation_type),
    status: r.status,
    current_approvals: r.current_approvals,
    required_approvals: r.required_approvals,
    requested_by_label: r.requested_by === currentUserId ? "you" : r.requested_by,
    requested_at: r.requested_at,
  }));
}

export default async function ApprovalsInboxPage() {
  const { user, resources } = await getTenantPageContext();
  const { data: requests } = await (
    resources.makerChecker.listTenant({}) as Promise<{
      data?: ApprovalRequestOut[];
      error?: unknown;
    }>
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Approvals</h1>
        <a href="/approvals/my-submissions" className="text-[var(--text-link)] hover:underline">
          My submissions
        </a>
      </div>
      <ApprovalsTable rows={toRows(requests ?? [], user.id)} />
    </div>
  );
}
```

- [ ] **Step 5: Create the my-submissions page**

`admin/apps/portal/app/(tenant-authed)/approvals/my-submissions/page.tsx`:

```tsx
import type { ApprovalRequestOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { ApprovalsTable, type ApprovalRow } from "../_components/ApprovalsTable";

export const metadata = { title: "My submissions" };

export default async function MySubmissionsPage() {
  const { user, resources } = await getTenantPageContext();
  const { data: requests } = await (
    resources.makerChecker.listTenant({ requested_by: user.id }) as Promise<{
      data?: ApprovalRequestOut[];
      error?: unknown;
    }>
  );

  const rows: ApprovalRow[] = (requests ?? []).map((r) => ({
    id: r.id,
    operation_type: r.operation_type,
    operation_label: operationLabel(r.operation_type),
    status: r.status,
    current_approvals: r.current_approvals,
    required_approvals: r.required_approvals,
    requested_by_label: "you",
    requested_at: r.requested_at,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">My submissions</h1>
      <ApprovalsTable rows={rows} />
    </div>
  );
}
```

- [ ] **Step 6: Run test + typecheck/lint to verify pass**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- tenant-approvals/ApprovalsTable && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS, clean.

- [ ] **Step 7: Commit**

```bash
git add "admin/apps/portal/app/(tenant-authed)/approvals/_components/ApprovalsTable.tsx" \
        "admin/apps/portal/app/(tenant-authed)/approvals/page.tsx" \
        "admin/apps/portal/app/(tenant-authed)/approvals/my-submissions/page.tsx" \
        admin/apps/portal/src/__tests__/tenant-approvals/ApprovalsTable.test.tsx
git commit -m "feat(portal): tenant approvals inbox + my-submissions"
```

---

## Task 4: Portal — `PayloadView`

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/approvals/[id]/_components/PayloadView.tsx`
- Test: `admin/apps/portal/src/__tests__/tenant-approvals/PayloadView.test.tsx`

**Interfaces:**
- Produces: `PayloadView({ payload: Record<string, unknown> })` — generic key/value tree + raw-JSON toggle (no update_sensitive diff branch).

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/src/__tests__/tenant-approvals/PayloadView.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PayloadView } from "../../../app/(tenant-authed)/approvals/[id]/_components/PayloadView";

describe("PayloadView", () => {
  it("renders payload keys + values and toggles raw JSON", () => {
    render(<PayloadView payload={{ amount: "100.00", confirmed: true, account_id: null }} />);
    expect(screen.getByText("amount")).toBeInTheDocument();
    expect(screen.getByText("100.00")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument(); // boolean true
    expect(screen.getByText("—")).toBeInTheDocument();   // null
    fireEvent.click(screen.getByText("View raw JSON"));
    expect(screen.getByText("Hide raw JSON")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- tenant-approvals/PayloadView`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `PayloadView.tsx`** (generic only — drop the platform diff branch)

```tsx
"use client";

import { useState } from "react";

function renderValue(v: unknown): string {
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function isUuidish(v: unknown): boolean {
  return typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(v);
}

export interface PayloadViewProps {
  payload: Record<string, unknown>;
}

export function PayloadView({ payload }: PayloadViewProps) {
  const [rawOpen, setRawOpen] = useState(false);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
        {Object.entries(payload).map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 py-2">
            <span className="text-[var(--text-secondary)]">{k}</span>
            <span
              className={
                isUuidish(v)
                  ? "font-mono text-[13px] text-[var(--text-primary)]"
                  : "text-[var(--text-primary)]"
              }
            >
              {renderValue(v)}
            </span>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setRawOpen((o) => !o)}
        className="self-start text-[13px] text-[var(--text-link)] hover:underline"
      >
        {rawOpen ? "Hide raw JSON" : "View raw JSON"}
      </button>
      {rawOpen ? (
        <pre className="overflow-auto rounded-md bg-[var(--surface-sunken)] p-3 text-[12px] text-[var(--text-primary)]">
          {JSON.stringify(payload, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- tenant-approvals/PayloadView`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/(tenant-authed)/approvals/[id]/_components/PayloadView.tsx" \
        admin/apps/portal/src/__tests__/tenant-approvals/PayloadView.test.tsx
git commit -m "feat(portal): tenant approval PayloadView"
```

---

## Task 5: Portal — `ApprovalActions`

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/approvals/[id]/_components/ApprovalActions.tsx`
- Test: `admin/apps/portal/src/__tests__/tenant-approvals/ApprovalActions.test.tsx`

**Interfaces:**
- Consumes: `useAuth()` → `resources.makerChecker.{approveTenant, rejectTenant, cancelTenant}`; `approveActionSchema`, `rejectActionSchema`; `queryKeys.approvals.{tenant, detail}`.
- Produces: `ApprovalActions({ requestId, status, requestedBy, currentUserId, subjectLabel })` — no `canApprove` prop (tenant auth = may approve).

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/src/__tests__/tenant-approvals/ApprovalActions.test.tsx`. Mock `useAuth` + `@sacco/api-client` (copy the mock shape from an existing tenant client-action test, e.g. a member/savings maker-checker button test under `src/__tests__/`):

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const approveTenant = vi.fn(async () => ({ data: {}, error: undefined }));
const rejectTenant = vi.fn(async () => ({ data: {}, error: undefined }));
const cancelTenant = vi.fn(async () => ({ data: {}, error: undefined }));

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { makerChecker: { approveTenant, rejectTenant, cancelTenant } } }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

import { ApprovalActions } from "../../../app/(tenant-authed)/approvals/[id]/_components/ApprovalActions";

const A = "550e8400-e29b-41d4-a716-446655440000"; // request id
const ME = "550e8400-e29b-41d4-a716-446655440001";
const OTHER = "550e8400-e29b-41d4-a716-446655440002";

describe("ApprovalActions", () => {
  it("non-self pending shows Approve + Reject and approves", async () => {
    render(<ApprovalActions requestId={A} status="pending" requestedBy={OTHER}
      currentUserId={ME} subjectLabel="Write off loan" />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    fireEvent.click(screen.getByRole("button", { name: "Approve and execute" }));
    await waitFor(() => expect(approveTenant).toHaveBeenCalledWith(A, expect.any(Object)));
  });

  it("self request shows Cancel + notice, hides Approve", () => {
    render(<ApprovalActions requestId={A} status="pending" requestedBy={ME}
      currentUserId={ME} subjectLabel="Write off loan" />);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel request" })).toBeInTheDocument();
  });

  it("renders nothing when not pending", () => {
    const { container } = render(<ApprovalActions requestId={A} status="approved"
      requestedBy={OTHER} currentUserId={ME} subjectLabel="X" />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- tenant-approvals/ApprovalActions`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `ApprovalActions.tsx`** (clone of platform, tenant resources, drop `canApprove`)

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button, ConfirmDialog, Dialog, DialogContent, DialogDescription, DialogHeader,
  DialogTitle, FormField, Textarea, toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  approveActionSchema, rejectActionSchema,
  type ApproveActionInput, type RejectActionInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface ApprovalActionsProps {
  requestId: string;
  status: string;
  requestedBy: string;
  currentUserId: string;
  subjectLabel: string;
}

export function ApprovalActions({
  requestId, status, requestedBy, currentUserId, subjectLabel,
}: ApprovalActionsProps) {
  const router = useRouter();
  const { resources } = useAuth();

  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);

  const invalidates = [queryKeys.approvals.tenant(), queryKeys.approvals.detail(requestId)];

  const approveForm = useForm<ApproveActionInput>({
    resolver: zodResolver(approveActionSchema), defaultValues: { comment: "" },
  });
  const rejectForm = useForm<RejectActionInput>({
    resolver: zodResolver(rejectActionSchema), defaultValues: { reason: "" },
  });

  const approveMutation = useTypedMutation<unknown, ApproveActionInput>(
    async (vars) => {
      const res = await (
        resources.makerChecker.approveTenant(requestId, vars as Record<string, unknown>) as Promise<{
          data?: unknown; error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Request approved", { description: "The operation has been executed." });
        setApproveOpen(false); approveForm.reset(); router.refresh();
      },
      onError: (error) =>
        toast.error("The request was not approved", { description: apiErrorMessage(error, "Please try again.") }),
    },
  );

  const rejectMutation = useTypedMutation<unknown, RejectActionInput>(
    async (vars) => {
      const res = await (
        resources.makerChecker.rejectTenant(requestId, vars as Record<string, unknown>) as Promise<{
          data?: unknown; error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Request rejected");
        setRejectOpen(false); rejectForm.reset(); router.refresh();
      },
      onError: (error) =>
        toast.error("The request was not rejected", { description: apiErrorMessage(error, "Please try again.") }),
    },
  );

  const cancelMutation = useTypedMutation<unknown, void>(
    async () => {
      const res = await (
        resources.makerChecker.cancelTenant(requestId, {}) as Promise<{ data?: unknown; error?: unknown }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Request cancelled");
        setCancelOpen(false); router.refresh();
      },
      onError: (error) =>
        toast.error("The request was not cancelled", { description: apiErrorMessage(error, "Please try again.") }),
    },
  );

  if (status !== "pending") return null;

  const isOwnRequest = currentUserId === requestedBy;

  return (
    <div className="flex items-center gap-2">
      {isOwnRequest ? (
        <>
          <span className="text-[13px] text-[var(--text-tertiary)]">
            You submitted this request and cannot approve your own request.
          </span>
          <Button variant="destructive" onClick={() => setCancelOpen(true)}>Cancel request</Button>
        </>
      ) : (
        <>
          <Button variant="primary" onClick={() => { approveForm.reset(); setApproveOpen(true); }}>
            Approve
          </Button>
          <Button variant="destructive" onClick={() => { rejectForm.reset(); setRejectOpen(true); }}>
            Reject
          </Button>
        </>
      )}

      <Dialog open={approveOpen} onOpenChange={(o) => { if (!o) setApproveOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve {subjectLabel}</DialogTitle>
            <DialogDescription>
              Approving runs this operation now. When the quorum is met this executes immediately
              and cannot be undone here.
            </DialogDescription>
          </DialogHeader>
          <form noValidate className="flex flex-col gap-4"
            onSubmit={approveForm.handleSubmit((values) => approveMutation.mutate(values))}>
            <FormField control={approveForm.control} name="comment" label="Comment (optional)"
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" disabled={approveMutation.isPending}>Approve and execute</Button>
              <Button type="button" variant="ghost" onClick={() => setApproveOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={rejectOpen} onOpenChange={(o) => { if (!o) setRejectOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject {subjectLabel}</DialogTitle>
            <DialogDescription>
              Rejecting closes this request without running the operation.
            </DialogDescription>
          </DialogHeader>
          <form noValidate className="flex flex-col gap-4"
            onSubmit={rejectForm.handleSubmit((values) => rejectMutation.mutate(values))}>
            <FormField control={rejectForm.control} name="reason" label="Reason" required
              helpText="Recorded on the request and the audit log. Minimum 10 characters."
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" variant="destructive" disabled={rejectMutation.isPending}>Reject</Button>
              <Button type="button" variant="ghost" onClick={() => setRejectOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title={`Cancel ${subjectLabel}?`}
        description="This withdraws your pending request. You can re-submit from the originating screen."
        confirmLabel="Cancel request"
        destructive
        busy={cancelMutation.isPending}
        onConfirm={() => cancelMutation.mutate()}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run test + typecheck/lint to verify pass**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- tenant-approvals/ApprovalActions && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS, clean. (If the `useAuth` mock path or `useTypedMutation` shape differs from the harness found in Step 1, align the test to the real mock used by existing tenant maker-checker button tests.)

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/(tenant-authed)/approvals/[id]/_components/ApprovalActions.tsx" \
        admin/apps/portal/src/__tests__/tenant-approvals/ApprovalActions.test.tsx
git commit -m "feat(portal): tenant approval approve/reject/cancel actions"
```

---

## Task 6: Portal — detail page + final verification

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/approvals/[id]/page.tsx`

**Interfaces:**
- Consumes: `resources.makerChecker.getTenant(id)` → `ApprovalRequestDetailOut`; `PayloadView`, `ApprovalActions`; `getTenantPageContext()`.

- [ ] **Step 1: Create the detail page** (server component; no unit test — wiring only, covered by component tests)

`admin/apps/portal/app/(tenant-authed)/approvals/[id]/page.tsx`:

```tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Card, FormattedDateTime, StatusBadge } from "@sacco/ui";
import type { ApprovalRequestDetailOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { PayloadView } from "./_components/PayloadView";
import { ApprovalActions } from "./_components/ApprovalActions";

export const metadata = { title: "Approval request" };

export default async function ApprovalDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getTenantPageContext();

  const { data } = await (
    resources.makerChecker.getTenant(id) as Promise<{
      data?: ApprovalRequestDetailOut;
      error?: unknown;
    }>
  );
  if (!data) notFound();

  const subjectLabel = operationLabel(data.operation_type);
  const requestedByLabel = data.requested_by === user.id ? "you" : data.requested_by;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[var(--text-h3)] font-semibold">{subjectLabel}</h1>
          <StatusBadge entity="approval_request" status={data.status} />
          <span className="text-[var(--text-tertiary)] tabular-nums">
            {data.current_approvals} of {data.required_approvals}
          </span>
        </div>
        <ApprovalActions
          requestId={data.id}
          status={data.status}
          requestedBy={data.requested_by}
          currentUserId={user.id}
          subjectLabel={subjectLabel}
        />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <Row label="Requested by" value={requestedByLabel} />
        <Row label="Requested" value={<FormattedDateTime value={data.requested_at} />} />
        {data.rejection_reason ? (
          <Row label="Rejection reason" value={data.rejection_reason} />
        ) : null}
      </Card>

      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Details</h2>
        <PayloadView payload={data.payload} />
      </Card>

      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Activity</h2>
        {data.actions.length === 0 ? (
          <p className="text-[var(--text-tertiary)]">No actions yet.</p>
        ) : (
          <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
            {data.actions.map((a) => (
              <div key={a.id} className="flex items-start justify-between gap-4 py-2">
                <div className="flex flex-col">
                  <span className="text-[var(--text-primary)]">
                    {a.actor_user_id === user.id ? "you" : a.actor_user_id}{" "}
                    {a.action === "approve" ? "approved" : "rejected"}
                  </span>
                  {a.comment ? (
                    <span className="text-[13px] text-[var(--text-tertiary)]">{a.comment}</span>
                  ) : null}
                </div>
                <FormattedDateTime value={a.acted_at} />
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-[var(--text-primary)]">{value}</span>
    </div>
  );
}
```

- [ ] **Step 2: Confirm the tenant sidebar already links `/approvals`**

Run: `grep -rn '"/approvals"\|/approvals' admin/packages/ui/src/components/Shell/ admin/apps/portal/ --include=*.tsx | grep -i sidebar`
Expected: the tenant sidebar already has an Approvals item pointing at `/approvals` (the dead link this plan fills). If — and only if — it is missing, add an `Approvals` item to the tenant sidebar group next to Ledger/Books; otherwise no change.

- [ ] **Step 3: Full verification across touched packages**

Run (from `admin/`):
```bash
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Run (from repo root):
```bash
export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test
python -m pytest tests/modules/maker_checker/ -v && ruff check app/modules/maker_checker/ && mypy app/modules/maker_checker/
```
Expected: all green. Record the new portal/schemas test counts.

- [ ] **Step 4: Commit**

```bash
git add "admin/apps/portal/app/(tenant-authed)/approvals/[id]/page.tsx"
# include the sidebar file only if Step 2 required a change
git commit -m "feat(portal): tenant approval detail page (Phase 3g-2)"
```

---

## Self-Review checklist (run before opening the PR)

- **Spec coverage:** inbox (Task 3) ✓, my-submissions (Task 3) ✓, detail + actions trail (Tasks 4–6) ✓, approve/reject/cancel + self-approval guard (Task 5) ✓, tenant operation labels (Task 2) ✓, backend list+get parity (Task 1) ✓.
- **No new endpoints / fields / gate changes** in Task 1 — additive only.
- **Type consistency:** `ApprovalRow` shape identical across table + both pages; `ApprovalActions` props match the detail page call site (no `canApprove`); `PayloadView` takes only `payload`.
- **Contracts:** tenant gating via `getTenantPageContext()` (no permission keys); `<StatusBadge entity="approval_request">`; reject min 10 chars; no `<AuditBar>`.
