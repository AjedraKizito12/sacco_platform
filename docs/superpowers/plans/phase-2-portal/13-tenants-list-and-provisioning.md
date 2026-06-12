# Tenants List + Provisioning Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three SP13 Tenants screens (`/platform/tenants` list with status filter, `/platform/tenants/new` provisioning wizard with async-202 + live status polling, `/platform/tenants/[id]` overview with inline retry-provisioning) as a pure client of the existing `/platform/tenants` API.

**Architecture:** Server components fetch via `getPlatformPageContext()` (established in SP12); the list reuses SP12's in-memory DataTable adapter with a status `filterSlot`. The wizard is a two-phase client component: a details form (slug auto-suggested from name) that POSTs and receives **202**, then a provisioning phase that live-polls `GET /platform/tenants/{id}` via a shared `useTenantProvisioning` hook (TanStack `refetchInterval`, stops on terminal status). The detail page reuses the same hook (seeded with server-fetched `initialData`) so an operator landing mid-provision sees live updates. Retry-provisioning is maker-checker: the failed-tenant detail shows a "Request Provisioning Retry" button wired through `<MakerCheckerConfirmDialog>` with the PR #26 toast-feedback pattern.

**Tech Stack:** Next.js 15 App Router (`apps/portal/app/platform/(authed)/tenants/*`), React 19, TS strict, `@sacco/ui` (DataTable, Stepper, StatusBadge, MakerCheckerConfirmDialog, toast), `@sacco/schemas` (Zod), `@sacco/api-client` (`resources.tenants.*`, `queryKeys.tenants.*`), Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **Zero new backend endpoints** (contract B). SP13 consumes `GET|POST /platform/tenants`, `GET /platform/tenants/{id}`, `POST /platform/tenants/{id}/retry-provisioning` — all existing (`app/platform_/tenants/api.py`). The api-client methods already exist as `resources.tenants.list/get/create/retryProvisioning` (`packages/api-client/src/resources/tenants.ts`) — reuse them. `queryKeys.tenants.{root,list,detail}` already exist. The `TENANT_STATUS` StatusBadge map already covers `pending/provisioning/active/suspended/failed/deprovisioning/archived` — **no `@sacco/ui` or api-client changes needed in SP13.**
- **Backend facts (authoritative):** `POST /platform/tenants` → **202** with `{ tenant: TenantOut, status_url }`, superuser-gated, **409** on duplicate slug. Slug grammar `^[a-z0-9-]{1,40}$`, immutable after create. `GET /platform/tenants/{id}` is the poll target; `provisioning_state` holds the current step name while provisioning; `failed_step` + `failure_reason` populate on failure. `POST .../retry-provisioning` (admin+) requires `status == "failed"` (400 otherwise) and **submits a `tenant.retry_provisioning` approval request** (quorum 1) — it does not retry directly.
- **Permissions already registered** (`apps/portal/src/auth/permissions.ts`): `platform.tenants.read` (support), `platform.tenants.create` (superuser), `platform.tenants.write` (admin — gates retry). Use these; do not invent keys.
- **Maker-checker UX = the PR #26 pattern** (contract K/V): button labeled "Request Provisioning Retry", `<MakerCheckerConfirmDialog>` (locked copy), dialog closes in `onSuccess` only, `toast.success("Approval request created", …)` / `toast.error` via `apiErrorMessage` from `@/lib/api-error`. `<Toaster/>` is already mounted in the root layout.
- **Status filter is client-side.** `useTableUrlState` is shallow nuqs state (no RSC round-trip on change), so the list page fetches ALL tenants server-side and the adapter filters by status client-side before sort/page — same in-memory pattern as SP12, acceptable at platform-operator scale. The backend `?status=` param stays unused by the portal for now; revisit when tenant counts warrant server-driven tables.
- **The `Promise<never>` cast wart applies** to `resources.tenants.*` exactly as in SP12 (`tenants.ts` uses `as never` paths). Every call site casts to the real openapi-fetch `{ data?, error? }` shape with the standard comment. Do not attempt to fix the resource types here (out of scope).
- **Out of SP13 scope** (do not build): edit/suspend/reactivate/assign-plan (SP14), impersonation entry (SP14), `[id]/billing` and `[id]/users` tabs (later sub-plans), `MakerCheckerBanner` after retry submission (needs the approvals-list endpoint — SP17; the toast is the v1 feedback), e2e (seeded-backend sub-plan), next-intl (portal-wide deferral — raw English strings, matching SP12).
- The wizard's "Details" form has 3 fields — `useDraftAutoSave` (contract X) is for long forms and is intentionally NOT used here.

## File Structure

**New files**
- `admin/packages/schemas/src/tenants.ts` (+ `__tests__/tenants.test.ts`; add `export * from "./tenants";` to `index.ts`) — `createTenantSchema`, `TenantOut`, `suggestSlug()`, `TENANT_SLUG_RE`.
- `admin/apps/portal/src/hooks/use-tenant-provisioning.ts` (+ test) — shared polling hook + `isProvisioningSettled()`.
- `admin/apps/portal/app/platform/(authed)/tenants/page.tsx`, `loading.tsx`, `error.tsx`, `_components/TenantsTable.tsx` — list.
- `admin/apps/portal/app/platform/(authed)/tenants/new/page.tsx`, `new/_components/NewTenantWizard.tsx` — wizard.
- `admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx`, `loading.tsx`, `error.tsx`, `_components/TenantDetail.tsx`, `_components/RetryProvisioningButton.tsx` — detail + retry.
- Tests under `admin/apps/portal/src/__tests__/platform-tenants/` (one file per client component).

**Modified files**
- `admin/packages/schemas/src/index.ts` (one export line).
- Possibly none else — the sidebar already renders a Tenants nav item (verify in Task 8).

---

## Task 1: Tenant Zod schemas + slug helper (`@sacco/schemas`)

**Files:**
- Create: `admin/packages/schemas/src/tenants.ts`
- Create: `admin/packages/schemas/src/__tests__/tenants.test.ts`
- Modify: `admin/packages/schemas/src/index.ts`

- [ ] **Step 1: Write the failing test**

```ts
// admin/packages/schemas/src/__tests__/tenants.test.ts
import { describe, expect, it } from "vitest";
import { createTenantSchema, suggestSlug } from "../tenants";

describe("createTenantSchema", () => {
  it("accepts a valid payload", () => {
    const res = createTenantSchema.safeParse({
      slug: "kampala-teachers",
      name: "Kampala Teachers SACCO",
      admin_email: "admin@example.com",
    });
    expect(res.success).toBe(true);
  });

  it("accepts an empty admin_email (optional seed user)", () => {
    const res = createTenantSchema.safeParse({
      slug: "k1",
      name: "K1",
      admin_email: "",
    });
    expect(res.success).toBe(true);
  });

  it("rejects an uppercase slug", () => {
    const res = createTenantSchema.safeParse({ slug: "Kampala", name: "X", admin_email: "" });
    expect(res.success).toBe(false);
  });

  it("rejects a slug over 40 chars", () => {
    const res = createTenantSchema.safeParse({
      slug: "a".repeat(41),
      name: "X",
      admin_email: "",
    });
    expect(res.success).toBe(false);
  });

  it("rejects a junk admin_email", () => {
    const res = createTenantSchema.safeParse({
      slug: "ok",
      name: "X",
      admin_email: "not-an-email",
    });
    expect(res.success).toBe(false);
  });

  it("trims and lowercases admin_email", () => {
    const parsed = createTenantSchema.parse({
      slug: "ok",
      name: "X",
      admin_email: " ADMIN@Example.com ",
    });
    expect(parsed.admin_email).toBe("admin@example.com");
  });

  it("rejects a whitespace-only name", () => {
    const res = createTenantSchema.safeParse({ slug: "ok", name: "   ", admin_email: "" });
    expect(res.success).toBe(false);
  });
});

describe("suggestSlug", () => {
  it("lowercases and hyphenates words", () => {
    expect(suggestSlug("Kampala Teachers SACCO")).toBe("kampala-teachers-sacco");
  });
  it("collapses punctuation runs into single hyphens", () => {
    expect(suggestSlug("St. Mary's -- Co-op!")).toBe("st-mary-s-co-op");
  });
  it("strips leading/trailing hyphens and caps at 40 chars", () => {
    const out = suggestSlug("  --" + "very long sacco name ".repeat(4) + "--  ");
    expect(out.length).toBeLessThanOrEqual(40);
    expect(out.startsWith("-")).toBe(false);
    expect(out.endsWith("-")).toBe(false);
  });
  it("returns empty string for names with no usable characters", () => {
    expect(suggestSlug("!!!")).toBe("");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/schemas test -- tenants`
Expected: FAIL — `Cannot find module '../tenants'`.

- [ ] **Step 3: Write the schema module**

```ts
// admin/packages/schemas/src/tenants.ts
import { z } from "zod";

// Mirrors app/platform_/tenants/schemas.py _SLUG_RE. Slug is immutable
// after create.
export const TENANT_SLUG_RE = /^[a-z0-9-]{1,40}$/;

// Mirrors CreateTenantRequest. admin_email is optional server-side; the
// form models "not provided" as "" and the submit site strips it
// (conditional spread) so the wire payload omits the key entirely.
export const createTenantSchema = z.object({
  slug: z
    .string()
    .regex(TENANT_SLUG_RE, "Lowercase letters, digits and hyphens only (max 40)"),
  name: z.string().trim().min(1, "Name is required").max(200),
  admin_email: z
    .string()
    .trim()
    .toLowerCase()
    .email("Enter a valid email address")
    .or(z.literal("")),
});
export type CreateTenantInput = z.infer<typeof createTenantSchema>;

// Mirrors TenantOut. Dates are ISO strings over the wire.
export interface TenantOut {
  id: string;
  slug: string;
  schema_name: string;
  name: string;
  status: string;
  is_active: boolean;
  provisioning_state: string | null;
  failed_step: string | null;
  failure_reason: string | null;
  provisioning_started_at: string | null;
  provisioning_completed_at: string | null;
  seed_version: number;
  created_at: string;
  updated_at: string;
}

/**
 * Derives a slug suggestion from a tenant name: lowercase, non-alphanumeric
 * runs collapsed to single hyphens, trimmed of edge hyphens, capped at 40.
 * Pure suggestion — the operator can always override; createTenantSchema is
 * the validator.
 */
export function suggestSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/g, "");
}
```

- [ ] **Step 4: Export from the package index**

```ts
// admin/packages/schemas/src/index.ts — add alongside the others
export * from "./tenants";
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/schemas test -- tenants` → PASS.
Also: `pnpm --filter @sacco/schemas typecheck` → clean.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/schemas/src/tenants.ts \
  admin/packages/schemas/src/__tests__/tenants.test.ts \
  admin/packages/schemas/src/index.ts
git commit -m "feat(schemas): tenant create schema + TenantOut + suggestSlug"
```

---

## Task 2: TenantsTable (DataTable adapter + status filter)

Same in-memory adapter as SP12's `UsersTable`, plus a status `<Select>` in the DataTable `filterSlot` wired to `urlState.filters["status"]` (URL key `f_status`).

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/_components/TenantsTable.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-tenants/TenantsTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-tenants/TenantsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TenantOut } from "@sacco/schemas";

// nuqs is a dep of @sacco/ui, not the portal (pnpm isolation) — mock the
// url-state hook like UsersTable.test.tsx does, keeping everything else real.
const mockUrlState = {
  page: 1,
  pageSize: 25,
  sortColumn: null as string | null,
  sortDirection: "asc" as const,
  filters: {} as Record<string, string>,
  density: "default" as const,
  setPage: vi.fn(),
  setPageSize: vi.fn(),
  setSort: vi.fn(),
  setFilter: vi.fn(),
  setFilters: vi.fn(),
  setDensity: vi.fn(),
  reset: vi.fn(),
};
vi.mock("@sacco/ui", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/ui")>();
  return { ...actual, useTableUrlState: () => mockUrlState };
});

import { filterTenants, TenantsTable } from "../../../app/platform/(authed)/tenants/_components/TenantsTable";

function tenant(over: Partial<TenantOut>): TenantOut {
  return {
    id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
    status: "active", is_active: true, provisioning_state: null,
    failed_step: null, failure_reason: null,
    provisioning_started_at: null, provisioning_completed_at: "2026-06-01T00:00:00Z",
    seed_version: 1, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

const rows = [
  tenant({ id: "t1", slug: "alpha", name: "Alpha SACCO", status: "active" }),
  tenant({ id: "t2", slug: "beta", name: "Beta SACCO", status: "failed" }),
];

describe("TenantsTable", () => {
  it("renders a row per tenant with name link and status badge", () => {
    render(<TenantsTable rows={rows} />);
    expect(screen.getByRole("link", { name: "Alpha SACCO" })).toHaveAttribute(
      "href",
      "/platform/tenants/t1",
    );
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders the empty state when there are no tenants", () => {
    render(<TenantsTable rows={[]} />);
    expect(screen.getByText(/no tenants/i)).toBeInTheDocument();
  });

  it("filters by status when the f_status filter is set", () => {
    mockUrlState.filters = { status: "failed" };
    render(<TenantsTable rows={rows} />);
    expect(screen.queryByText("Alpha SACCO")).toBeNull();
    expect(screen.getByText("Beta SACCO")).toBeInTheDocument();
    mockUrlState.filters = {};
  });
});

describe("filterTenants", () => {
  it("returns all rows when no status filter", () => {
    expect(filterTenants(rows, undefined)).toHaveLength(2);
  });
  it("returns only matching rows for a status", () => {
    expect(filterTenants(rows, "failed").map((t) => t.id)).toEqual(["t2"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- TenantsTable`
Expected: FAIL — module not found.

> Check `admin/apps/portal/src/__tests__/platform-users/UsersTable.test.tsx` first: it mocks `useTableUrlState` the same way — match its exact mock shape if `TableUrlState` has fields this snippet missed.

- [ ] **Step 3: Write the component**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/_components/TenantsTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const STATUS_FILTER_OPTIONS = [
  "pending",
  "provisioning",
  "active",
  "failed",
  "suspended",
  "deprovisioning",
  "archived",
] as const;

// ColumnDef is a dep of @sacco/ui (@tanstack/react-table), not the portal.
const columns: DataTableProps<TenantOut>["columns"] = [
  {
    id: "name",
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => (
      <Link
        href={`/platform/tenants/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.name}
      </Link>
    ),
  },
  { id: "slug", accessorKey: "slug", header: "Slug" },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="tenant" status={row.original.status} />,
  },
  {
    id: "created_at",
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => <FormattedDate value={row.original.created_at} />,
  },
];

export function filterTenants(
  rows: TenantOut[],
  status: string | undefined,
): TenantOut[] {
  if (!status) return rows;
  return rows.filter((t) => t.status === status);
}

export function sortTenants(
  rows: TenantOut[],
  column: string | null,
  dir: "asc" | "desc",
): TenantOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof TenantOut];
    const bv = b[column as keyof TenantOut];
    const as = av === null ? "" : String(av);
    const bs = bv === null ? "" : String(bv);
    return as.localeCompare(bs);
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/**
 * Renders the full (unpaginated) tenant list through DataTable. Filter,
 * sort and pagination are client-side because GET /platform/tenants has no
 * paging params (the ?status= param exists but shallow nuqs state cannot
 * re-trigger the server fetch; client filtering is fine at operator scale).
 */
export function TenantsTable({ rows }: { rows: TenantOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "name", direction: "asc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterTenants(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );

  const sorted = useMemo(
    () => sortTenants(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );

  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<TenantOut>
      id="platform-tenants"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: filtered.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No tenants",
        description: "Provision the first tenant to get started.",
      }}
      filterSlot={
        <Select
          value={urlState.filters["status"] ?? "all"}
          onValueChange={(v) => urlState.setFilter("status", v === "all" ? null : v)}
        >
          <SelectTrigger className="w-44" aria-label="Filter by status">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_FILTER_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    />
  );
}
```

> Verify `SelectTrigger` accepts `className`; here `aria-label` is correct (this select has no visible label — icon-only-adjacent rule). Confirm `DataTable` renders `filterSlot` (prop verified in `DataTable/types.ts:68`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal test -- TenantsTable` → PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/_components/TenantsTable.tsx" \
  admin/apps/portal/src/__tests__/platform-tenants/TenantsTable.test.tsx
git commit -m "feat(portal): TenantsTable — DataTable adapter with status filter"
```

---

## Task 3: Tenants list page + loading + error

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/page.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/loading.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/error.tsx`

- [ ] **Step 1: Write the list page (server component)**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/page.tsx
import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { TenantsTable } from "./_components/TenantsTable";

export const metadata = { title: "Tenants" };

export default async function PlatformTenantsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.read");

  // resources.tenants.list is typed Promise<never> because tenants.ts uses
  // `as never` on its openapi-fetch paths; cast to the real openapi-fetch
  // { data, error } shape until those resource types tighten.
  const { data } = await (
    resources.tenants.list() as Promise<{ data?: TenantOut[]; error?: unknown }>
  );
  const rows = data ?? [];
  const canCreate = userHasPermission(user, "platform.tenants.create");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Tenants</h1>
        {canCreate ? (
          <Button asChild>
            <Link href="/platform/tenants/new">New tenant</Link>
          </Button>
        ) : null}
      </div>
      <Card className="p-0">
        <TenantsTable rows={rows} />
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Write loading + error boundaries**

Mirror the SP12 list pair exactly (read `app/platform/(authed)/users/loading.tsx` + `error.tsx` and adapt the copy):

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/loading.tsx
import { Card } from "@sacco/ui";

export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <div className="h-8 w-48 animate-pulse rounded-[var(--radius-sm)] bg-[var(--surface-sunken)]" />
      <Card className="p-4">
        <div className="flex flex-col gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="h-10 w-full animate-pulse rounded-[var(--radius-sm)] bg-[var(--surface-sunken)]"
            />
          ))}
        </div>
      </Card>
    </div>
  );
}
```

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/error.tsx
"use client";

import { useEffect } from "react";
import { Button, Card } from "@sacco/ui";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <Card className="flex flex-col items-start gap-3 p-6">
      <h2 className="text-[var(--text-h5)] font-semibold">Couldn&apos;t load tenants</h2>
      <p className="text-[var(--text-secondary)]">
        Something went wrong fetching the tenant list.
      </p>
      <Button onClick={reset}>Try again</Button>
    </Card>
  );
}
```

- [ ] **Step 3: Verify**

Run: `cd admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint` → clean.

- [ ] **Step 4: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/page.tsx" \
  "admin/apps/portal/app/platform/(authed)/tenants/loading.tsx" \
  "admin/apps/portal/app/platform/(authed)/tenants/error.tsx"
git commit -m "feat(portal): tenants list page (+ loading/error)"
```

---

## Task 4: `useTenantProvisioning` polling hook

Shared by the wizard (poll after 202) and the detail page (live-update mid-provision). Polls every 2s while the status is non-terminal; stops on terminal.

**Files:**
- Create: `admin/apps/portal/src/hooks/use-tenant-provisioning.ts`
- Create: `admin/apps/portal/src/hooks/__tests__/use-tenant-provisioning.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/hooks/__tests__/use-tenant-provisioning.test.tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { TenantOut } from "@sacco/schemas";

const get = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { get } } }),
}));

import {
  isProvisioningSettled,
  useTenantProvisioning,
} from "../use-tenant-provisioning";

const active: TenantOut = {
  id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha",
  status: "active", is_active: true, provisioning_state: null,
  failed_step: null, failure_reason: null,
  provisioning_started_at: "2026-06-01T00:00:00Z",
  provisioning_completed_at: "2026-06-01T00:01:00Z",
  seed_version: 1, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:01:00Z",
};

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("isProvisioningSettled", () => {
  it("treats pending and provisioning as in-flight", () => {
    expect(isProvisioningSettled("pending")).toBe(false);
    expect(isProvisioningSettled("provisioning")).toBe(false);
  });
  it("treats active, failed, suspended, archived as settled", () => {
    for (const s of ["active", "failed", "suspended", "archived"]) {
      expect(isProvisioningSettled(s)).toBe(true);
    }
  });
});

describe("useTenantProvisioning", () => {
  it("fetches the tenant and exposes it", async () => {
    get.mockResolvedValue({ data: active, error: undefined });
    const { result } = renderHook(() => useTenantProvisioning("t1"), { wrapper });
    await waitFor(() => expect(result.current.data?.status).toBe("active"));
    expect(get).toHaveBeenCalledWith("t1");
  });

  it("serves initialData without waiting for a fetch", () => {
    get.mockResolvedValue({ data: active, error: undefined });
    const { result } = renderHook(() => useTenantProvisioning("t1", active), {
      wrapper,
    });
    expect(result.current.data?.id).toBe("t1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- use-tenant-provisioning`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the hook**

```tsx
// admin/apps/portal/src/hooks/use-tenant-provisioning.ts
"use client";

import { queryKeys, useTypedQuery } from "@sacco/api-client";
import type { TenantOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";

const IN_FLIGHT_STATUSES = new Set(["pending", "provisioning"]);

/** Terminal provisioning statuses stop the poll loop. */
export function isProvisioningSettled(status: string): boolean {
  return !IN_FLIGHT_STATUSES.has(status);
}

const POLL_INTERVAL_MS = 2000;

/**
 * Live view of a tenant during provisioning. Polls GET /platform/tenants/{id}
 * every 2s while status is pending/provisioning, then stops. Pass the
 * server-fetched tenant as `initialData` so the first paint never waits on a
 * client fetch (contract M).
 */
export function useTenantProvisioning(tenantId: string, initialData?: TenantOut) {
  const { resources } = useAuth();
  return useTypedQuery<TenantOut>(
    queryKeys.tenants.detail(tenantId),
    async () => {
      // resources.tenants.get is typed Promise<never> (as-never paths in
      // tenants.ts); cast to the real { data, error } shape.
      const res = await (
        resources.tenants.get(tenantId) as Promise<{
          data?: TenantOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      if (!res.data) throw new Error("Tenant not found");
      return res.data;
    },
    {
      ...(initialData !== undefined ? { initialData } : {}),
      refetchInterval: (query) => {
        const status = query.state.data?.status;
        if (!status) return POLL_INTERVAL_MS;
        return isProvisioningSettled(status) ? false : POLL_INTERVAL_MS;
      },
    },
  );
}
```

> `refetchInterval` as a function of the query is TanStack Query v5 API — verify the installed major version (`rg '"@tanstack/react-query"' admin/apps/portal/package.json admin/packages/api-client/package.json`). If v4 is installed, the callback signature is `(data, query)` — adapt. The poll cadence itself is not unit-tested (timer behavior); the interval-decision logic is, via `isProvisioningSettled`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal test -- use-tenant-provisioning` → PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add admin/apps/portal/src/hooks/use-tenant-provisioning.ts \
  admin/apps/portal/src/hooks/__tests__/use-tenant-provisioning.test.tsx
git commit -m "feat(portal): useTenantProvisioning polling hook"
```

---

## Task 5: New-tenant wizard (`/platform/tenants/new`)

Two phases in one client component: **Details** (form, slug auto-suggested from name until manually edited) → submit (202) → **Provisioning** (Stepper + live status via `useTenantProvisioning`). On `active`: success + "View tenant" link. On `failed`: failure reason + link to the tenant detail (where the retry CTA lives).

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/new/page.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/new/_components/NewTenantWizard.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-tenants/NewTenantWizard.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-tenants/NewTenantWizard.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const create = vi.fn();
const get = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { create, get } } }),
}));

import { NewTenantWizard } from "../../../app/platform/(authed)/tenants/new/_components/NewTenantWizard";

function tenant(over: Partial<TenantOut>): TenantOut {
  return {
    id: "t9", slug: "kampala-teachers", schema_name: "tenant_kampala_teachers",
    name: "Kampala Teachers", status: "provisioning", is_active: false,
    provisioning_state: "create_schema", failed_step: null, failure_reason: null,
    provisioning_started_at: "2026-06-11T00:00:00Z", provisioning_completed_at: null,
    seed_version: 1, created_at: "2026-06-11T00:00:00Z", updated_at: "2026-06-11T00:00:00Z",
    ...over,
  };
}

function renderWizard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NewTenantWizard />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("NewTenantWizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("auto-suggests the slug from the name until the slug is edited", async () => {
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "Kampala Teachers");
    expect(screen.getByLabelText(/slug/i)).toHaveValue("kampala-teachers");
    // Manual slug edit stops the sync.
    await userEvent.clear(screen.getByLabelText(/slug/i));
    await userEvent.type(screen.getByLabelText(/slug/i), "kt-sacco");
    await userEvent.type(screen.getByLabelText(/^name/i), " Extra");
    expect(screen.getByLabelText(/slug/i)).toHaveValue("kt-sacco");
  });

  it("rejects an invalid slug before submitting", async () => {
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "X");
    await userEvent.clear(screen.getByLabelText(/slug/i));
    await userEvent.type(screen.getByLabelText(/slug/i), "Bad Slug!");
    await userEvent.click(screen.getByRole("button", { name: /provision tenant/i }));
    expect(await screen.findByText(/lowercase letters, digits and hyphens/i)).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("submits, then shows live provisioning progress until active", async () => {
    create.mockResolvedValue({
      data: { tenant: tenant({}), status_url: "/platform/tenants/t9" },
      error: undefined,
    });
    get.mockResolvedValue({ data: tenant({ status: "active", provisioning_state: null }), error: undefined });
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "Kampala Teachers");
    await userEvent.click(screen.getByRole("button", { name: /provision tenant/i }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        slug: "kampala-teachers",
        name: "Kampala Teachers",
      }),
    );
    // Provisioning phase reached, then poll resolves to active.
    expect(await screen.findByText(/tenant is ready/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view tenant/i })).toHaveAttribute(
      "href",
      "/platform/tenants/t9",
    );
  });

  it("shows the failure panel when provisioning fails", async () => {
    create.mockResolvedValue({
      data: { tenant: tenant({}), status_url: "/platform/tenants/t9" },
      error: undefined,
    });
    get.mockResolvedValue({
      data: tenant({
        status: "failed",
        failed_step: "run_migrations",
        failure_reason: "alembic timeout",
      }),
      error: undefined,
    });
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "Kampala Teachers");
    await userEvent.click(screen.getByRole("button", { name: /provision tenant/i }));
    expect(await screen.findByText(/provisioning failed/i)).toBeInTheDocument();
    expect(screen.getByText(/alembic timeout/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open tenant/i })).toBeInTheDocument();
  });

  it("surfaces a duplicate-slug error and stays on the form", async () => {
    create.mockResolvedValue({
      data: undefined,
      error: { detail: "Tenant slug 'kampala-teachers' already exists" },
    });
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "Kampala Teachers");
    await userEvent.click(screen.getByRole("button", { name: /provision tenant/i }));
    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/slug/i)).toBeInTheDocument(); // still on form
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- NewTenantWizard`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the wizard**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/new/_components/NewTenantWizard.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Card,
  FormField,
  Input,
  StatusBadge,
  Stepper,
  toast,
} from "@sacco/ui";
import { useTypedMutation, queryKeys } from "@sacco/api-client";
import {
  createTenantSchema,
  suggestSlug,
  type CreateTenantInput,
  type TenantOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { useTenantProvisioning } from "@/hooks/use-tenant-provisioning";

const WIZARD_STEPS = [
  { id: "details", label: "Details" },
  { id: "provisioning", label: "Provisioning" },
  { id: "done", label: "Done" },
];

interface CreateTenantResponse {
  tenant: TenantOut;
  status_url: string;
}

export function NewTenantWizard() {
  const { resources } = useAuth();
  const [created, setCreated] = useState<TenantOut | null>(null);

  const form = useForm<CreateTenantInput>({
    resolver: zodResolver(createTenantSchema),
    defaultValues: { slug: "", name: "", admin_email: "" },
  });

  const mutation = useTypedMutation<CreateTenantResponse, CreateTenantInput>(
    async (vars) => {
      // Backend treats admin_email as optional; "" means "no seed admin" —
      // strip it so the wire payload omits the key (exactOptionalPropertyTypes).
      const body = {
        slug: vars.slug,
        name: vars.name,
        ...(vars.admin_email ? { admin_email: vars.admin_email } : {}),
      };
      // resources.tenants.create is typed Promise<never> (as-never paths in
      // tenants.ts); cast to the real { data, error } shape.
      const res = await (
        resources.tenants.create(body) as Promise<{
          data?: CreateTenantResponse;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      if (!res.data) throw new Error("Empty provisioning response");
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.root()],
      onSuccess: (data) => setCreated(data.tenant),
      onError: (error) => {
        toast.error("The tenant was not created", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  // Keep the slug suggestion in sync with the name until the operator edits
  // the slug by hand (dirtyFields tracks manual edits only).
  function onNameChange(name: string) {
    if (!form.formState.dirtyFields.slug) {
      form.setValue("slug", suggestSlug(name));
    }
  }

  if (created) {
    return <ProvisioningProgress tenant={created} />;
  }

  return (
    <div className="flex max-w-xl flex-col gap-6">
      <Stepper steps={WIZARD_STEPS} currentStepId="details" />
      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
      >
        <FormField
          control={form.control}
          name="name"
          label="Name"
          required
          render={({ field, id, describedBy, invalid }) => (
            <Input
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              {...field}
              onChange={(e) => {
                field.onChange(e);
                onNameChange(e.target.value);
              }}
            />
          )}
        />
        <FormField
          control={form.control}
          name="slug"
          label="Slug"
          required
          helpText="URL-safe identifier. Immutable after creation."
          render={({ field, id, describedBy, invalid }) => (
            <Input
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              {...field}
            />
          )}
        />
        <FormField
          control={form.control}
          name="admin_email"
          label="Initial admin email"
          helpText="Optional. Seeds an admin user who sets their password via the reset flow."
          render={({ field, id, describedBy, invalid }) => (
            <Input
              id={id}
              type="email"
              aria-describedby={describedBy}
              aria-invalid={invalid}
              {...field}
            />
          )}
        />
        <div>
          <Button type="submit" disabled={mutation.isPending}>
            Provision tenant
          </Button>
        </div>
      </form>
    </div>
  );
}

function ProvisioningProgress({ tenant }: { tenant: TenantOut }) {
  const live = useTenantProvisioning(tenant.id, tenant);
  const current = live.data ?? tenant;

  const stepId =
    current.status === "active"
      ? "done"
      : "provisioning"; // pending / provisioning / failed all render here

  return (
    <div className="flex max-w-xl flex-col gap-6">
      <Stepper steps={WIZARD_STEPS} currentStepId={stepId} />
      <Card className="flex flex-col gap-4 p-6">
        <div className="flex items-center gap-3">
          <h2 className="text-[var(--text-h5)] font-semibold">{current.name}</h2>
          <StatusBadge entity="tenant" status={current.status} />
        </div>

        {current.status === "active" ? (
          <>
            <p className="text-[var(--text-secondary)]">Tenant is ready.</p>
            <div>
              <Button asChild>
                <Link href={`/platform/tenants/${current.id}`}>View tenant</Link>
              </Button>
            </div>
          </>
        ) : current.status === "failed" ? (
          <>
            <p className="text-[var(--text-secondary)]">
              Provisioning failed
              {current.failed_step ? ` at step "${current.failed_step}"` : ""}.
            </p>
            {current.failure_reason ? (
              <p className="text-[var(--text-danger)]">{current.failure_reason}</p>
            ) : null}
            <p className="text-[var(--text-secondary)]">
              Open the tenant to request a provisioning retry.
            </p>
            <div>
              <Button asChild variant="secondary">
                <Link href={`/platform/tenants/${current.id}`}>Open tenant</Link>
              </Button>
            </div>
          </>
        ) : (
          <p className="text-[var(--text-secondary)]" aria-live="polite">
            Provisioning in progress
            {current.provisioning_state ? ` — ${current.provisioning_state}` : ""}…
            This page updates automatically.
          </p>
        )}
      </Card>
    </div>
  );
}
```

> Verify the exact `StepperStep` shape in `packages/ui/src/components/Stepper/Stepper.tsx` (`{ id, label }` confirmed; if it carries more required fields, extend `WIZARD_STEPS`). Verify `--text-danger` exists in `docs/tokens.css` (UserDetail/FormField already use danger tokens — match the exact token name used there, e.g. `--text-danger`).

- [ ] **Step 4: Write the page (server gate)**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/new/page.tsx
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { NewTenantWizard } from "./_components/NewTenantWizard";

export const metadata = { title: "New Tenant" };

export default async function NewTenantPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.create");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">New tenant</h1>
      <NewTenantWizard />
    </div>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal test -- NewTenantWizard` → PASS (5 tests).
Also `pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/new" \
  admin/apps/portal/src/__tests__/platform-tenants/NewTenantWizard.test.tsx
git commit -m "feat(portal): new-tenant provisioning wizard (202 + live polling)"
```

---

## Task 6: Tenant detail overview (`/platform/tenants/[id]`)

Server page fetches the tenant; `TenantDetail` (client) seeds `useTenantProvisioning` with it so an in-flight tenant live-updates. Shows identity + provisioning panel + `<AuditBar entityType="tenant">`. The retry CTA is Task 7 — `TenantDetail` renders a `canRetry` prop slot for it.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/loading.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/error.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-tenants/TenantDetail.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-tenants/TenantDetail.test.tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { TenantOut } from "@sacco/schemas";

const get = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { get, retryProvisioning: vi.fn() } } }),
}));

import { TenantDetail } from "../../../app/platform/(authed)/tenants/[id]/_components/TenantDetail";

function tenant(over: Partial<TenantOut>): TenantOut {
  return {
    id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
    status: "active", is_active: true, provisioning_state: null,
    failed_step: null, failure_reason: null,
    provisioning_started_at: "2026-06-01T00:00:00Z",
    provisioning_completed_at: "2026-06-01T00:01:00Z",
    seed_version: 1, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:01:00Z",
    ...over,
  };
}

function renderDetail(t: TenantOut, canRetry = false) {
  get.mockResolvedValue({ data: t, error: undefined });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantDetail tenant={t} canRetry={canRetry} />
    </QueryClientProvider>,
  );
}

describe("TenantDetail", () => {
  it("renders identity fields and status badge", () => {
    renderDetail(tenant({}));
    expect(screen.getByText("Alpha SACCO")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("tenant_alpha")).toBeInTheDocument();
  });

  it("renders the audit bar wired to the tenant entity", () => {
    const { container } = renderDetail(tenant({}));
    expect(container.querySelector('[data-entity-type="tenant"]')).not.toBeNull();
  });

  it("shows failure details for a failed tenant", () => {
    renderDetail(
      tenant({
        status: "failed",
        failed_step: "run_migrations",
        failure_reason: "alembic timeout",
      }),
    );
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/run_migrations/)).toBeInTheDocument();
    expect(screen.getByText(/alembic timeout/)).toBeInTheDocument();
  });

  it("does not render a retry button for a non-failed tenant even with permission", () => {
    renderDetail(tenant({ status: "active" }), true);
    expect(screen.queryByRole("button", { name: /request provisioning retry/i })).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- TenantDetail`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the detail component**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx
"use client";

import {
  AuditBar,
  Card,
  FormattedDateTime,
  ReadOnlyField,
  StatusBadge,
} from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";
import { useTenantProvisioning } from "@/hooks/use-tenant-provisioning";
import { RetryProvisioningButton } from "./RetryProvisioningButton";

export function TenantDetail({
  tenant,
  canRetry,
}: {
  tenant: TenantOut;
  canRetry: boolean;
}) {
  // Live-updates while the tenant is mid-provision; settles once terminal.
  const live = useTenantProvisioning(tenant.id, tenant);
  const t = live.data ?? tenant;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[var(--text-h3)] font-semibold">{t.name}</h1>
          <StatusBadge entity="tenant" status={t.status} />
        </div>
        {canRetry && t.status === "failed" ? (
          <RetryProvisioningButton tenant={t} />
        ) : null}
      </div>

      <Card className="grid grid-cols-2 gap-5 p-6">
        <ReadOnlyField label="Slug" value={t.slug} />
        <ReadOnlyField label="Schema" value={t.schema_name} />
        <ReadOnlyField label="Seed version" value={String(t.seed_version)} />
        <ReadOnlyField
          label="Created"
          value={<FormattedDateTime value={t.created_at} />}
        />
      </Card>

      <Card className="flex flex-col gap-4 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Provisioning</h2>
        <div className="grid grid-cols-2 gap-5">
          <ReadOnlyField
            label="State"
            value={t.provisioning_state ?? "—"}
          />
          <ReadOnlyField
            label="Started"
            value={
              t.provisioning_started_at ? (
                <FormattedDateTime value={t.provisioning_started_at} />
              ) : (
                "—"
              )
            }
          />
          <ReadOnlyField
            label="Completed"
            value={
              t.provisioning_completed_at ? (
                <FormattedDateTime value={t.provisioning_completed_at} />
              ) : (
                "—"
              )
            }
          />
          {t.status === "failed" ? (
            <ReadOnlyField
              label="Failed step"
              value={t.failed_step ?? "unknown"}
            />
          ) : null}
        </div>
        {t.status === "failed" && t.failure_reason ? (
          <p className="text-[var(--text-danger)]">{t.failure_reason}</p>
        ) : null}
      </Card>

      <AuditBar entityType="tenant" entityId={t.id} />
    </div>
  );
}
```

> `RetryProvisioningButton` is created in Task 7. For THIS task's tests to run before Task 7 exists, create the stub file now (Task 7 replaces it):
>
> ```tsx
> // admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/RetryProvisioningButton.tsx
> "use client";
> import type { TenantOut } from "@sacco/schemas";
> // Replaced with the maker-checker implementation in the next commit.
> export function RetryProvisioningButton(_props: { tenant: TenantOut }) {
>   return null;
> }
> ```

- [ ] **Step 4: Write the page + boundaries**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx
import { notFound } from "next/navigation";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { TenantDetail } from "./_components/TenantDetail";

export const metadata = { title: "Tenant" };

export default async function TenantDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.read");

  // resources.tenants.get is typed Promise<never> (as-never paths in
  // tenants.ts); cast to the real { data, error } shape.
  const { data } = await (
    resources.tenants.get(id) as Promise<{ data?: TenantOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <TenantDetail
      tenant={data}
      canRetry={userHasPermission(user, "platform.tenants.write")}
    />
  );
}
```

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/loading.tsx
import { Card } from "@sacco/ui";

export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <div className="h-8 w-64 animate-pulse rounded-[var(--radius-sm)] bg-[var(--surface-sunken)]" />
      {Array.from({ length: 2 }).map((_, c) => (
        <Card key={c} className="grid grid-cols-2 gap-5 p-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-12 w-full animate-pulse rounded-[var(--radius-sm)] bg-[var(--surface-sunken)]"
            />
          ))}
        </Card>
      ))}
    </div>
  );
}
```

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/error.tsx
"use client";

import { useEffect } from "react";
import { Button, Card } from "@sacco/ui";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <Card className="flex flex-col items-start gap-3 p-6">
      <h2 className="text-[var(--text-h5)] font-semibold">Couldn&apos;t load this tenant</h2>
      <Button onClick={reset}>Try again</Button>
    </Card>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal test -- TenantDetail` → PASS (4 tests). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]" \
  admin/apps/portal/src/__tests__/platform-tenants/TenantDetail.test.tsx
git commit -m "feat(portal): tenant detail overview with live provisioning panel"
```

---

## Task 7: Retry-provisioning CTA (maker-checker)

Replaces the Task 6 stub. Contract K/V + the PR #26 feedback pattern: "Request Provisioning Retry" button → `<MakerCheckerConfirmDialog>` (locked copy) → on confirm, `POST /platform/tenants/{id}/retry-provisioning` (which submits the `tenant.retry_provisioning` approval) → success toast "Approval request created"; error toast via `apiErrorMessage`; dialog closes only on success.

**Files:**
- Modify: `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/RetryProvisioningButton.tsx` (replace stub)
- Create: `admin/apps/portal/src/__tests__/platform-tenants/RetryProvisioningButton.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-tenants/RetryProvisioningButton.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const retryProvisioning = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { retryProvisioning } } }),
}));

import { RetryProvisioningButton } from "../../../app/platform/(authed)/tenants/[id]/_components/RetryProvisioningButton";

const failed: TenantOut = {
  id: "t2", slug: "beta", schema_name: "tenant_beta", name: "Beta SACCO",
  status: "failed", is_active: false, provisioning_state: null,
  failed_step: "run_migrations", failure_reason: "alembic timeout",
  provisioning_started_at: "2026-06-11T00:00:00Z", provisioning_completed_at: null,
  seed_version: 1, created_at: "2026-06-11T00:00:00Z", updated_at: "2026-06-11T00:00:00Z",
};

function renderButton() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RetryProvisioningButton tenant={failed} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("RetryProvisioningButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("opens the locked maker-checker dialog and does not call the API until confirmed", async () => {
    retryProvisioning.mockResolvedValue({ data: failed, error: undefined });
    renderButton();
    await userEvent.click(
      screen.getByRole("button", { name: /request provisioning retry/i }),
    );
    expect(
      await screen.findByText(/create an approval request, not execute/i),
    ).toBeInTheDocument();
    expect(retryProvisioning).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole("button", { name: /create approval request/i }),
    );
    await waitFor(() => expect(retryProvisioning).toHaveBeenCalledWith("t2"));
    expect(await screen.findByText(/approval request created/i)).toBeInTheDocument();
  });

  it("surfaces an error and keeps the dialog open when the request fails", async () => {
    retryProvisioning.mockResolvedValue({
      data: undefined,
      error: { detail: "retry-provisioning requires status='failed', got 'active'" },
    });
    renderButton();
    await userEvent.click(
      screen.getByRole("button", { name: /request provisioning retry/i }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: /create approval request/i }),
    );
    expect(await screen.findByText(/requires status='failed'/i)).toBeInTheDocument();
    expect(
      screen.getByText(/create an approval request, not execute/i),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- RetryProvisioningButton`
Expected: FAIL — the stub renders null, so the button is not found.

- [ ] **Step 3: Replace the stub with the implementation**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/RetryProvisioningButton.tsx
"use client";

import { useState } from "react";
import { Button, MakerCheckerConfirmDialog, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { TenantOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

/**
 * Maker-checker CTA on a failed tenant. The backend endpoint submits a
 * tenant.retry_provisioning approval request (quorum 1) — it does not retry
 * directly. Contract K: the button is labeled "Request X", not "X".
 */
export function RetryProvisioningButton({ tenant }: { tenant: TenantOut }) {
  const { resources } = useAuth();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const mutation = useTypedMutation<unknown, void>(
    async () => {
      // resources.tenants.retryProvisioning is typed Promise<never>
      // (as-never paths in tenants.ts); cast to the real { data, error } shape.
      const res = await (
        resources.tenants.retryProvisioning(tenant.id) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.root(), queryKeys.tenants.detail(tenant.id)],
      onSuccess: () => {
        toast.success("Approval request created", {
          description:
            "Provisioning will retry once another platform user approves it.",
        });
        setConfirmOpen(false);
      },
      onError: (error) => {
        toast.error("The retry was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Button variant="secondary" onClick={() => setConfirmOpen(true)}>
        Request Provisioning Retry
      </Button>
      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        operationLabel="provisioning retry"
        subjectLabel={tenant.slug}
        busy={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd admin && pnpm --filter @sacco/portal test -- platform-tenants` → all pass (TenantsTable + NewTenantWizard + TenantDetail + RetryProvisioningButton). `typecheck` + `lint` → clean.

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/RetryProvisioningButton.tsx" \
  admin/apps/portal/src/__tests__/platform-tenants/RetryProvisioningButton.test.tsx
git commit -m "feat(portal): retry-provisioning CTA via maker-checker dialog"
```

---

## Task 8: Nav verification + full-module verification

**Files:**
- Possibly modify: `admin/apps/portal/src/components/AppShellSidebar.tsx`

- [ ] **Step 1: Verify the Tenants nav item**

Run: `cd admin && rg -n "tenants" apps/portal/src/components/AppShellSidebar.tsx`
The platform nav group already had a Tenants entry when SP12 verified the sidebar (it sat before Users). Confirm it points at `/platform/tenants` and is gated on `platform.tenants.read` via the same `PermissionGuard` mechanism the other items use. If present and correct, there is nothing to commit for this step. If missing, add it matching the existing item shape exactly.

- [ ] **Step 2: Full verification**

```bash
cd admin
pnpm --filter @sacco/schemas test
pnpm --filter @sacco/portal test
pnpm --filter @sacco/portal typecheck
pnpm --filter @sacco/portal lint
pnpm --filter @sacco/schemas typecheck
```

Expected: all green. The portal suite should be 52 (pre-SP13) + the new platform-tenants and hook tests, with zero failures.

- [ ] **Step 3: Manual smoke (optional but recommended)**

Bring up backend + portal, log in as superuser: list → New tenant (watch the wizard poll through `pending → provisioning → active`) → detail. To exercise the failure path, provision a tenant with a deliberately broken step (or inspect a seeded failed tenant) → confirm "Request Provisioning Retry" → locked dialog → approval request appears for a second operator. Confirm a `support` user sees the list but no "New tenant" button and no retry CTA.

- [ ] **Step 4: Commit (only if the sidebar needed a change)**

```bash
git add admin/apps/portal/src/components/AppShellSidebar.tsx
git commit -m "feat(portal): tenants nav entry (SP13 verification)"
```

---

## Self-Review

**Spec coverage (portal index §653-661):** list with filters (Tasks 2-3) ✓; provisioning wizard with async-202 + status polling (Tasks 4-5) ✓; detail overview (Task 6) ✓; retry surfaces inline on failed tenant detail, maker-checker (Task 7) ✓; tenant-status badges (existing map, consumed in Tasks 2/5/6) ✓. Endpoints: `GET|POST /platform/tenants`, `GET .../{id}`, `POST .../retry-provisioning` — all consumed, none added ✓.

**Deliberate gaps (documented):** edit/suspend/impersonate (SP14); billing/users tabs (later); MakerCheckerBanner after retry submission (SP17 — toast is the v1 feedback); poll cadence not unit-tested (timer behavior; decision logic tested via `isProvisioningSettled`); backend `?status=` param unused (client-side filter, documented rationale); e2e + i18n per portal-wide deferrals.

**Type consistency:** `TenantOut`/`CreateTenantInput`/`suggestSlug`/`TENANT_SLUG_RE` defined in Task 1, consumed in Tasks 2/4/5/6/7. `useTenantProvisioning`/`isProvisioningSettled` defined in Task 4, consumed in 5/6. `filterTenants`/`sortTenants` exported for tests in Task 2. `RetryProvisioningButton({ tenant })` stub signature in Task 6 matches the Task 7 implementation.

**Verify-before-wiring flags:** `StepperStep` exact shape; `SelectTrigger className`; `--text-danger` token name; TanStack Query major version for the `refetchInterval` callback signature; the `useTableUrlState` mock shape against the real `TableUrlState`.
