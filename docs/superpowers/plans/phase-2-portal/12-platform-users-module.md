# Platform Users Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the four Platform Users screens (`list`, `new`, `[id]` detail, `[id]/edit`) in the admin portal — the first Phase 2 feature module — proving the Part A foundation (DataTable + RHF/Zod forms + permission gating + maker-checker UX) end-to-end against the existing `/platform/users` API.

**Architecture:** Server components fetch via a per-request typed `@sacco/api-client` (new `getPlatformPageContext()` helper — SP12 is the first server-fetching page, so it establishes that helper); data is handed to client components as props. Mutations run client-side through `useTypedMutation` + `useAuth().resources`. `GET /platform/users` is **unpaginated**, so the list table holds the full result in memory and adapts it to `<DataTable>`'s server-side contract client-side. Sensitive edits (`is_active`, `role`) are routed by the backend through the `platform_user.update_sensitive` maker-checker executor; the edit form surfaces this with `<MakerCheckerConfirmDialog>`.

**Tech Stack:** Next.js 15 App Router (`apps/portal/app/platform/(authed)/users/*`), React 19, TypeScript strict, `@sacco/ui` (DataTable, FormField, StatusBadge, ConfirmDialog, AuditBar, Select, Input), `@sacco/schemas` (Zod), `@sacco/api-client` (typed fetch + TanStack hooks), Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **Zero new backend endpoints** (CLAUDE.md contract B). SP12 consumes only `GET|POST /platform/users` and `GET|PATCH /platform/users/{id}`, which already exist (`app/platform_/users/api.py`). The api-client methods already exist as `resources.admin.listUsers/getUser/createUser/patchUser` (`packages/api-client/src/resources/admin.ts`) — **reuse them; do not add a resource file.**
- **Permission keys already exist** in `apps/portal/src/auth/permissions.ts`: `platform.users.read` (min role `support`) and `platform.users.write` (min role `superuser`). Use them; do not invent keys.
- **Backend maker-checker split (authoritative, do not reimplement client-side):** `PATCH /platform/users/{id}` applies `full_name` immediately and routes any of `{is_active, role, is_superuser}` through an approval request (`MAKER_CHECKER_FIELDS = {"is_active", "is_superuser", "role"}` in `app/platform_/users/service.py`). The form's only job is UX: show `<MakerCheckerConfirmDialog>` when a sensitive field is dirty.
- **i18n:** the portal does **not** yet wire next-intl (the existing `app/platform/(authed)/page.tsx` uses raw strings). Follow the existing pattern — raw English strings. String extraction is a later, dedicated sub-plan; do not introduce next-intl here.
- **Status rendering (contract S):** `is_active` renders through `<StatusBadge>`. `platform_user` is **not** yet a registered status entity, so Task 2 adds it (active/inactive). Never hand-pick a `Badge` variant for it.
- **`<MakerCheckerBanner>` on the detail page is deliberately deferred.** Detecting an open approval requires the `/platform/approvals` list endpoint, which is out of SP12's declared endpoint scope (it lands with the approvals-consuming sub-plan). The detail page therefore renders no banner in v1. This is an intentional gap, documented here and in the wrap-up — not an oversight. `<AuditBar>` *is* rendered (it is a self-contained placeholder per contract W).
- **e2e:** Playwright e2e against a seeded backend is deferred to the dedicated e2e sub-plan (matches the auth-shell precedent). SP12 ships Vitest component/unit tests only.

## File Structure

**New files**
- `admin/packages/schemas/src/platform.ts` — Zod schemas + `PlatformUserOut` type. Responsibility: the single source of form/response types for platform users.
- `admin/packages/schemas/src/__tests__/platform.test.ts` — schema validation tests.
- `admin/apps/portal/src/auth/server-page-context.ts` — `getPlatformPageContext()` (token → `/me` → typed `resources`) + `requirePlatformPermission()`. Responsibility: the reusable server-component data/permission entrypoint for all `/platform/*` pages.
- `admin/apps/portal/src/auth/__tests__/server-page-context.test.ts`
- `admin/apps/portal/app/platform/(authed)/users/page.tsx` — list (server).
- `admin/apps/portal/app/platform/(authed)/users/loading.tsx` — list skeleton.
- `admin/apps/portal/app/platform/(authed)/users/error.tsx` — list error boundary.
- `admin/apps/portal/app/platform/(authed)/users/_components/UsersTable.tsx` — client table (in-memory DataTable adapter).
- `admin/apps/portal/app/platform/(authed)/users/new/page.tsx` — create (server gate + form host).
- `admin/apps/portal/app/platform/(authed)/users/new/_components/CreateUserForm.tsx` — client form.
- `admin/apps/portal/app/platform/(authed)/users/[id]/page.tsx` — detail (server).
- `admin/apps/portal/app/platform/(authed)/users/[id]/loading.tsx`
- `admin/apps/portal/app/platform/(authed)/users/[id]/error.tsx`
- `admin/apps/portal/app/platform/(authed)/users/[id]/_components/UserDetail.tsx` — client detail body.
- `admin/apps/portal/app/platform/(authed)/users/[id]/edit/page.tsx` — edit (server).
- `admin/apps/portal/app/platform/(authed)/users/[id]/edit/_components/EditUserForm.tsx` — client form (maker-checker aware).
- Test files under `admin/apps/portal/src/__tests__/platform-users/` (one per client component).

**Modified files**
- `admin/packages/schemas/src/index.ts` — `export * from "./platform";`
- `admin/packages/ui/src/components/StatusBadge/status-maps.ts` — add `platform_user` entity + map.
- `admin/packages/api-client/src/query-keys.ts` — add `platformUsers` key factory.
- `admin/apps/portal/src/components/AppShellSidebar.tsx` (or its nav config) — ensure a "Users" nav item under the platform group, gated on `platform.users.read`.

---

## Task 1: Zod schemas for platform users (`@sacco/schemas`)

**Files:**
- Create: `admin/packages/schemas/src/platform.ts`
- Create: `admin/packages/schemas/src/__tests__/platform.test.ts`
- Modify: `admin/packages/schemas/src/index.ts`

- [ ] **Step 1: Write the failing test**

```ts
// admin/packages/schemas/src/__tests__/platform.test.ts
import { describe, expect, it } from "vitest";
import {
  createPlatformUserSchema,
  platformRoleSchema,
  updatePlatformUserSchema,
} from "../platform";

describe("platformRoleSchema", () => {
  it("accepts the four roles", () => {
    for (const r of ["superuser", "admin", "finance", "support"]) {
      expect(platformRoleSchema.safeParse(r).success).toBe(true);
    }
  });
  it("rejects unknown roles", () => {
    expect(platformRoleSchema.safeParse("root").success).toBe(false);
  });
});

describe("createPlatformUserSchema", () => {
  it("accepts a valid payload and defaults role to support", () => {
    const parsed = createPlatformUserSchema.parse({
      email: "ops@example.com",
      full_name: "Ops Person",
    });
    expect(parsed.role).toBe("support");
  });
  it("rejects an invalid email", () => {
    const res = createPlatformUserSchema.safeParse({
      email: "not-an-email",
      full_name: "X",
    });
    expect(res.success).toBe(false);
  });
  it("rejects an empty full_name", () => {
    const res = createPlatformUserSchema.safeParse({
      email: "ops@example.com",
      full_name: "",
    });
    expect(res.success).toBe(false);
  });
});

describe("updatePlatformUserSchema", () => {
  it("requires full_name, is_active, role together", () => {
    const res = updatePlatformUserSchema.safeParse({
      full_name: "Renamed",
      is_active: true,
      role: "admin",
    });
    expect(res.success).toBe(true);
  });
  it("rejects a missing role", () => {
    const res = updatePlatformUserSchema.safeParse({
      full_name: "Renamed",
      is_active: true,
    });
    expect(res.success).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/schemas test -- platform`
Expected: FAIL — `Cannot find module '../platform'`.

- [ ] **Step 3: Write the schema module**

```ts
// admin/packages/schemas/src/platform.ts
import { z } from "zod";

export const platformRoleSchema = z.enum([
  "superuser",
  "admin",
  "finance",
  "support",
]);
export type PlatformRole = z.infer<typeof platformRoleSchema>;

/** Mirrors app/platform_/users/schemas.py CreatePlatformUserRequest.
 *  is_superuser is deprecated server-side (role is authoritative); the
 *  portal only sends role. */
export const createPlatformUserSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  full_name: z.string().min(1, "Full name is required").max(200),
  role: platformRoleSchema.default("support"),
});
export type CreatePlatformUserInput = z.infer<typeof createPlatformUserSchema>;

/** Mirrors UpdatePlatformUserRequest. The portal always sends all three
 *  fields; the backend applies full_name immediately and routes is_active
 *  / role through maker-checker. */
export const updatePlatformUserSchema = z.object({
  full_name: z.string().min(1, "Full name is required").max(200),
  is_active: z.boolean(),
  role: platformRoleSchema,
});
export type UpdatePlatformUserInput = z.infer<typeof updatePlatformUserSchema>;

/** Mirrors PlatformUserOut. Dates are ISO strings over the wire. */
export interface PlatformUserOut {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  role: PlatformRole;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}
```

- [ ] **Step 4: Export from the package index**

```ts
// admin/packages/schemas/src/index.ts — add this line alongside the others
export * from "./platform";
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/schemas test -- platform`
Expected: PASS (8 assertions).

- [ ] **Step 6: Commit**

```bash
git add admin/packages/schemas/src/platform.ts \
  admin/packages/schemas/src/__tests__/platform.test.ts \
  admin/packages/schemas/src/index.ts
git commit -m "feat(schemas): platform user Zod schemas + PlatformUserOut type"
```

---

## Task 2: StatusBadge `platform_user` entity (`@sacco/ui`)

**Files:**
- Modify: `admin/packages/ui/src/components/StatusBadge/status-maps.ts`
- Modify: `admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to `StatusBadge.test.tsx`:

```tsx
it("renders a platform_user active status", () => {
  render(<StatusBadge entity="platform_user" status="active" />);
  expect(screen.getByText("Active")).toBeInTheDocument();
});

it("renders a platform_user inactive status", () => {
  render(<StatusBadge entity="platform_user" status="inactive" />);
  expect(screen.getByText("Inactive")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/ui test -- StatusBadge`
Expected: FAIL — `platform_user` is not assignable to `StatusEntity` (type error) and/or the lookup returns null.

- [ ] **Step 3: Add the entity to the union and the map**

In `status-maps.ts`, add `"platform_user"` to the `StatusEntity` union:

```ts
export type StatusEntity =
  | "loan"
  | "member"
  | "tenant"
  | "savings_account"
  | "fee_assessment"
  | "approval_request"
  | "subscription"
  | "invoice"
  | "payment"
  | "platform_user";
```

Add the map (place it alongside the other `export const *_STATUS` maps):

```ts
export const PLATFORM_USER_STATUS: StatusMap = {
  active: { variant: "success", label: "Active" },
  inactive: { variant: "neutral", label: "Inactive" },
};
```

Register it in the `ENTITY_MAPS` lookup object (find the existing `ENTITY_MAPS` record near the bottom of the file and add the row):

```ts
  platform_user: PLATFORM_USER_STATUS,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/ui test -- StatusBadge`
Expected: PASS. Run `cd admin && pnpm --filter @sacco/ui typecheck` — Expected: clean (the `ENTITY_MAPS` record now exhaustively covers the union).

- [ ] **Step 5: Commit**

```bash
git add admin/packages/ui/src/components/StatusBadge/status-maps.ts \
  admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx
git commit -m "feat(ui): StatusBadge platform_user entity (active/inactive)"
```

---

## Task 3: Server page-context helper + `platformUsers` query keys

This is the first server-fetching page in the portal, so we establish the reusable helper here. It refreshes the access token, fetches `/me`, builds a per-request typed `resources`, and exposes a redirect-on-deny permission check.

**Files:**
- Create: `admin/apps/portal/src/auth/server-page-context.ts`
- Create: `admin/apps/portal/src/auth/__tests__/server-page-context.test.ts`
- Modify: `admin/packages/api-client/src/query-keys.ts`

- [ ] **Step 1: Add the `platformUsers` query-key factory**

In `admin/packages/api-client/src/query-keys.ts`, add a top-level factory alongside `tenants`:

```ts
  platformUsers: {
    root: () => ["platformUsers"] as const,
    list: () => ["platformUsers", "list"] as const,
    detail: (id: string) => ["platformUsers", "detail", id] as const,
  },
```

- [ ] **Step 2: Write the failing test**

```ts
// admin/apps/portal/src/auth/__tests__/server-page-context.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest";

const redirectMock = vi.fn((url: string) => {
  throw new Error(`REDIRECT:${url}`);
});
vi.mock("next/navigation", () => ({ redirect: redirectMock }));

const getServerAccessToken = vi.fn();
const getServerCurrentUser = vi.fn();
vi.mock("../server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerCurrentUser: (...a: unknown[]) => getServerCurrentUser(...a),
}));

import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "../server-page-context";

beforeEach(() => {
  redirectMock.mockClear();
  getServerAccessToken.mockReset();
  getServerCurrentUser.mockReset();
});

describe("getPlatformPageContext", () => {
  it("redirects to login when there is no access token", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    await expect(getPlatformPageContext()).rejects.toThrow(
      "REDIRECT:/platform/login",
    );
  });

  it("returns user + resources when authenticated", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "tok" });
    getServerCurrentUser.mockResolvedValue({
      id: "u1",
      email: "a@b.c",
      full_name: "A",
      is_active: true,
      is_superuser: true,
      role: "superuser",
    });
    const ctx = await getPlatformPageContext();
    expect(ctx.user.id).toBe("u1");
    expect(typeof ctx.resources.admin.listUsers).toBe("function");
  });
});

describe("requirePlatformPermission", () => {
  it("redirects to /permission-denied when the user lacks the permission", () => {
    const supportUser = {
      id: "u2",
      email: "s@b.c",
      full_name: "S",
      is_active: true,
      is_superuser: false,
      role: "support" as const,
    };
    expect(() =>
      requirePlatformPermission(supportUser, "platform.users.write"),
    ).toThrow("REDIRECT:/permission-denied");
  });

  it("does not redirect when the user has the permission", () => {
    const adminUser = {
      id: "u3",
      email: "ad@b.c",
      full_name: "Ad",
      is_active: true,
      is_superuser: false,
      role: "admin" as const,
    };
    expect(() =>
      requirePlatformPermission(adminUser, "platform.users.read"),
    ).not.toThrow();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- server-page-context`
Expected: FAIL — `Cannot find module '../server-page-context'`.

- [ ] **Step 4: Write the helper**

```ts
// admin/apps/portal/src/auth/server-page-context.ts
import "server-only";
import { redirect } from "next/navigation";
import {
  buildResources,
  createApiClient,
  FixedTenantContext,
  InMemoryTokenStore,
  type Resources,
} from "@sacco/api-client";
import {
  getServerAccessToken,
  getServerCurrentUser,
} from "./server-helpers";
import {
  type CurrentUserShape,
  userHasPermission,
} from "./permissions";

const API_BASE =
  process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export interface PlatformPageContext {
  user: CurrentUserShape;
  resources: Resources;
}

/**
 * Server-component entrypoint for /platform/* pages: refreshes the access
 * token from the httpOnly cookie, fetches /me, and builds a per-request
 * typed api-client. Redirects to /platform/login when unauthenticated.
 *
 * A fresh InMemoryTokenStore per request avoids any cross-request token
 * bleed (server components run concurrently).
 */
export async function getPlatformPageContext(): Promise<PlatformPageContext> {
  const { accessToken } = await getServerAccessToken("platform");
  if (!accessToken) redirect("/platform/login");
  const user = await getServerCurrentUser("platform", accessToken);
  if (!user) redirect("/platform/login");

  const store = new InMemoryTokenStore("/platform/auth/refresh");
  store.setAccessToken(accessToken);
  const client = createApiClient({
    baseUrl: API_BASE,
    tokenStore: store,
    tenantContext: new FixedTenantContext(null),
  });
  return { user, resources: buildResources(client) };
}

/**
 * UX-layer permission gate for server components. Redirects to the
 * permission-denied page when the user lacks `permission`. The API is the
 * real enforcement boundary (CLAUDE.md contract D); this only prevents a
 * data fetch + render for a user who would be rejected anyway.
 */
export function requirePlatformPermission(
  user: CurrentUserShape,
  permission: string,
): void {
  if (!userHasPermission(user, permission)) {
    redirect("/permission-denied");
  }
}
```

> Note: `InMemoryTokenStore`, `FixedTenantContext`, `createApiClient`, `buildResources`, and `Resources` are all exported from `@sacco/api-client` (verified in `packages/api-client/src/index.ts`). `getServerAccessToken` / `getServerCurrentUser` are in `./server-helpers`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal test -- server-page-context`
Expected: PASS (4 assertions).

- [ ] **Step 6: Commit**

```bash
git add admin/apps/portal/src/auth/server-page-context.ts \
  admin/apps/portal/src/auth/__tests__/server-page-context.test.ts \
  admin/packages/api-client/src/query-keys.ts
git commit -m "feat(portal): server page-context helper + platformUsers query keys"
```

---

## Task 4: UsersTable client component (in-memory DataTable adapter)

`GET /platform/users` returns the full list with no pagination/sort/filter params, but `<DataTable>` is hardwired to server-side mode (`manualPagination/Sorting/Filtering: true`). The adapter holds the full list, derives the current page slice + total from `useTableUrlState`, and feeds DataTable as if server-driven. When a platform list endpoint later gains real server pagination, swap the in-memory slicing for a `useTypedQuery` keyed on the url state — the DataTable wiring stays identical.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/users/_components/UsersTable.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-users/UsersTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-users/UsersTable.test.tsx
import { render, screen } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { describe, expect, it } from "vitest";
import type { PlatformUserOut } from "@sacco/schemas";
import { UsersTable } from "../../../app/platform/(authed)/users/_components/UsersTable";

const rows: PlatformUserOut[] = [
  {
    id: "u1",
    email: "ada@example.com",
    full_name: "Ada Ops",
    is_active: true,
    is_superuser: false,
    role: "admin",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    last_login_at: "2026-06-10T08:00:00Z",
  },
  {
    id: "u2",
    email: "ben@example.com",
    full_name: "Ben Finance",
    is_active: false,
    is_superuser: false,
    role: "finance",
    created_at: "2026-06-02T00:00:00Z",
    updated_at: "2026-06-02T00:00:00Z",
    last_login_at: null,
  },
];

function renderTable(data: PlatformUserOut[]) {
  return render(
    <NuqsTestingAdapter>
      <UsersTable rows={data} />
    </NuqsTestingAdapter>,
  );
}

describe("UsersTable", () => {
  it("renders a row per user with email and status", () => {
    renderTable(rows);
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("ben@example.com")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("renders the empty state when there are no users", () => {
    renderTable([]);
    expect(screen.getByText(/no platform users/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- UsersTable`
Expected: FAIL — module not found.

> If `nuqs/adapters/testing` import errors, confirm the installed nuqs version exposes it (`nuqs@2.8.9` does). The DataTable stories already mock url state at module level — fall back to that pattern only if the testing adapter is unavailable.

- [ ] **Step 3: Write the component**

```tsx
// admin/apps/portal/app/platform/(authed)/users/_components/UsersTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import { type ColumnDef } from "@tanstack/react-table";
import {
  DataTable,
  FormattedDate,
  RelativeTime,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { PlatformUserOut } from "@sacco/schemas";

const ROLE_LABELS: Record<PlatformUserOut["role"], string> = {
  superuser: "Superuser",
  admin: "Admin",
  finance: "Finance",
  support: "Support",
};

const columns: ColumnDef<PlatformUserOut>[] = [
  {
    id: "email",
    accessorKey: "email",
    header: "Email",
    cell: ({ row }) => (
      <Link
        href={`/platform/users/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.email}
      </Link>
    ),
  },
  { id: "full_name", accessorKey: "full_name", header: "Name" },
  {
    id: "role",
    accessorKey: "role",
    header: "Role",
    cell: ({ row }) => ROLE_LABELS[row.original.role],
  },
  {
    id: "is_active",
    accessorKey: "is_active",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge
        entity="platform_user"
        status={row.original.is_active ? "active" : "inactive"}
      />
    ),
  },
  {
    id: "last_login_at",
    accessorKey: "last_login_at",
    header: "Last login",
    cell: ({ row }) =>
      row.original.last_login_at ? (
        <RelativeTime value={row.original.last_login_at} />
      ) : (
        <span className="text-[var(--text-tertiary)]">Never</span>
      ),
  },
  {
    id: "created_at",
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => <FormattedDate value={row.original.created_at} />,
  },
];

function sortRows(
  rows: PlatformUserOut[],
  column: string | null,
  dir: "asc" | "desc",
): PlatformUserOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof PlatformUserOut];
    const bv = b[column as keyof PlatformUserOut];
    const as = av === null ? "" : String(av);
    const bs = bv === null ? "" : String(bv);
    return as.localeCompare(bs);
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/**
 * Renders the full (unpaginated) platform-user list through DataTable.
 * Pagination/sort are applied client-side over `rows` because
 * GET /platform/users does not accept paging params.
 */
export function UsersTable({ rows }: { rows: PlatformUserOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "email", direction: "asc" },
    defaultPageSize: 25,
  });

  const sorted = useMemo(
    () => sortRows(rows, urlState.sortColumn, urlState.sortDirection),
    [rows, urlState.sortColumn, urlState.sortDirection],
  );

  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<PlatformUserOut>
      id="platform-users"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: rows.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No platform users",
        description: "Create the first platform user to get started.",
      }}
    />
  );
}
```

> `FormattedDate`, `RelativeTime`, `StatusBadge`, `DataTable`, `useTableUrlState` are all exported from `@sacco/ui` (verified). If `RelativeTime` is not exported under that exact name, use `FormattedDateTime` instead — check `packages/ui/src/components/FormattedDate` exports before substituting.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal test -- UsersTable`
Expected: PASS (renders both rows + statuses; empty state).

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/users/_components/UsersTable.tsx" \
  admin/apps/portal/src/__tests__/platform-users/UsersTable.test.tsx
git commit -m "feat(portal): UsersTable — DataTable adapter over unpaginated list"
```

---

## Task 5: Users list page + loading + error

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/users/page.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/users/loading.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/users/error.tsx`

- [ ] **Step 1: Write the list page (server component)**

```tsx
// admin/apps/portal/app/platform/(authed)/users/page.tsx
import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { PlatformUserOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { UsersTable } from "./_components/UsersTable";

export const metadata = { title: "Platform Users" };

export default async function PlatformUsersPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.users.read");

  const { data } = await resources.admin.listUsers();
  const rows = (data ?? []) as PlatformUserOut[];
  const canCreate = userHasPermission(user, "platform.users.write");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Platform Users</h1>
        {canCreate ? (
          <Button asChild>
            <Link href="/platform/users/new">New user</Link>
          </Button>
        ) : null}
      </div>
      <Card className="p-0">
        <UsersTable rows={rows} />
      </Card>
    </div>
  );
}
```

> The "New user" button is gated client-of-server via `userHasPermission` (UX only — contract D). `Button asChild` renders the `<Link>` as the button; if `@sacco/ui` `Button` does not support `asChild`, wrap the link instead: `<Link href="/platform/users/new"><Button>New user</Button></Link>`. Check `packages/ui/src/components/Button` before choosing.

- [ ] **Step 2: Write the loading skeleton**

```tsx
// admin/apps/portal/app/platform/(authed)/users/loading.tsx
import { Card, Skeleton } from "@sacco/ui";

export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-8 w-48" />
      <Card className="p-4">
        <div className="flex flex-col gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      </Card>
    </div>
  );
}
```

> If `@sacco/ui` does not export `Skeleton`, use the DataTable's own skeleton state instead, or a `<div className="animate-pulse ...">`. Verify the export first (`packages/ui/src/index.ts`). No spinners (skill rule).

- [ ] **Step 3: Write the error boundary**

```tsx
// admin/apps/portal/app/platform/(authed)/users/error.tsx
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
      <h2 className="text-[18px] font-semibold">Couldn’t load platform users</h2>
      <p className="text-[var(--text-secondary)]">
        Something went wrong fetching the user list.
      </p>
      <Button onClick={reset}>Try again</Button>
    </Card>
  );
}
```

- [ ] **Step 4: Verify it renders against the running app (manual smoke)**

Run: `cd admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: clean. (Full e2e against a seeded backend is deferred to the e2e sub-plan.)

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/users/page.tsx" \
  "admin/apps/portal/app/platform/(authed)/users/loading.tsx" \
  "admin/apps/portal/app/platform/(authed)/users/error.tsx"
git commit -m "feat(portal): platform users list page (+ loading/error)"
```

---

## Task 6: Create-user screen (`/platform/users/new`)

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/users/new/page.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/users/new/_components/CreateUserForm.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-users/CreateUserForm.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-users/CreateUserForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createUser = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { admin: { createUser } } }),
}));

import { CreateUserForm } from "../../../app/platform/(authed)/users/new/_components/CreateUserForm";

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <CreateUserForm />
    </QueryClientProvider>,
  );
}

describe("CreateUserForm", () => {
  it("shows a validation error for an invalid email", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText(/email/i), "nope");
    await userEvent.type(screen.getByLabelText(/full name/i), "Ada");
    await userEvent.click(screen.getByRole("button", { name: /create user/i }));
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(createUser).not.toHaveBeenCalled();
  });

  it("submits a valid payload and redirects", async () => {
    createUser.mockResolvedValue({ data: { id: "new-id" }, error: undefined });
    renderForm();
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.type(screen.getByLabelText(/full name/i), "Ada Ops");
    await userEvent.click(screen.getByRole("button", { name: /create user/i }));
    await waitFor(() =>
      expect(createUser).toHaveBeenCalledWith({
        email: "ada@example.com",
        full_name: "Ada Ops",
        role: "support",
      }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/users"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- CreateUserForm`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the form**

```tsx
// admin/apps/portal/app/platform/(authed)/users/new/_components/CreateUserForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormField,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@sacco/ui";
import { useTypedMutation, queryKeys } from "@sacco/api-client";
import {
  createPlatformUserSchema,
  type CreatePlatformUserInput,
  type PlatformRole,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";

const ROLE_OPTIONS: { value: PlatformRole; label: string }[] = [
  { value: "support", label: "Support" },
  { value: "finance", label: "Finance" },
  { value: "admin", label: "Admin" },
  { value: "superuser", label: "Superuser" },
];

export function CreateUserForm() {
  const router = useRouter();
  const { resources } = useAuth();
  const form = useForm<CreatePlatformUserInput>({
    resolver: zodResolver(createPlatformUserSchema),
    defaultValues: { email: "", full_name: "", role: "support" },
  });

  const mutation = useTypedMutation<unknown, CreatePlatformUserInput>(
    async (vars) => {
      const res = await resources.admin.createUser(vars);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.platformUsers.root()],
      onSuccess: () => router.push("/platform/users"),
    },
  );

  return (
    <form
      className="flex max-w-xl flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <FormField
        control={form.control}
        name="email"
        label="Email"
        required
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
      <FormField
        control={form.control}
        name="full_name"
        label="Full name"
        required
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
        name="role"
        label="Role"
        required
        render={({ field, id }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id}>
              <SelectValue placeholder="Select a role" />
            </SelectTrigger>
            <SelectContent>
              {ROLE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>
          Create user
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => router.push("/platform/users")}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
```

> `Select`/`SelectTrigger`/`SelectContent`/`SelectItem`/`SelectValue` are the forked shadcn exports from `@sacco/ui` (index line `export * from "./components/Select"`). Confirm the exact subcomponent export names in `packages/ui/src/components/Select` before wiring; adjust import names if the fork re-exports under different identifiers. `@hookform/resolvers` is already a portal dep (auth-shell forms use it) — verify in `apps/portal/package.json`; if absent, add it (`pnpm --filter @sacco/portal add @hookform/resolvers`) and justify in the commit per CLAUDE.md.

- [ ] **Step 4: Write the create page (server gate)**

```tsx
// admin/apps/portal/app/platform/(authed)/users/new/page.tsx
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { CreateUserForm } from "./_components/CreateUserForm";

export const metadata = { title: "New Platform User" };

export default async function NewPlatformUserPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.users.write");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">New platform user</h1>
      <CreateUserForm />
    </div>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal test -- CreateUserForm`
Expected: PASS (validation blocks invalid email; valid submit calls `createUser` + redirects).

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/users/new" \
  admin/apps/portal/src/__tests__/platform-users/CreateUserForm.test.tsx
git commit -m "feat(portal): create platform user screen (superuser-gated)"
```

---

## Task 7: Detail screen (`/platform/users/[id]`)

Read-only detail: identity fields via `<ReadOnlyField>`, status via `<StatusBadge>`, and `<AuditBar entityType="platform_user" entityId={id} />` (placeholder until the audit-query endpoint ships). No `<MakerCheckerBanner>` in v1 (see scope notes — approvals endpoint is out of scope). An "Edit" button links to the edit screen, gated on `platform.users.write`.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/users/[id]/page.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/users/[id]/loading.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/users/[id]/error.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/users/[id]/_components/UserDetail.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-users/UserDetail.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-users/UserDetail.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PlatformUserOut } from "@sacco/schemas";
import { UserDetail } from "../../../app/platform/(authed)/users/[id]/_components/UserDetail";

const user: PlatformUserOut = {
  id: "u1",
  email: "ada@example.com",
  full_name: "Ada Ops",
  is_active: true,
  is_superuser: false,
  role: "admin",
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
  last_login_at: null,
};

describe("UserDetail", () => {
  it("renders identity fields and an active status", () => {
    render(<UserDetail user={user} canEdit />);
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Ada Ops")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /edit/i })).toBeInTheDocument();
  });

  it("hides the edit link without permission", () => {
    render(<UserDetail user={user} canEdit={false} />);
    expect(screen.queryByRole("link", { name: /edit/i })).toBeNull();
  });

  it("renders the audit bar wired to the platform_user entity", () => {
    const { container } = render(<UserDetail user={user} canEdit />);
    expect(
      container.querySelector('[data-entity-type="platform_user"]'),
    ).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- UserDetail`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the detail body**

```tsx
// admin/apps/portal/app/platform/(authed)/users/[id]/_components/UserDetail.tsx
import Link from "next/link";
import {
  AuditBar,
  Button,
  Card,
  FormattedDateTime,
  ReadOnlyField,
  RelativeTime,
  StatusBadge,
} from "@sacco/ui";
import type { PlatformUserOut } from "@sacco/schemas";

const ROLE_LABELS: Record<PlatformUserOut["role"], string> = {
  superuser: "Superuser",
  admin: "Admin",
  finance: "Finance",
  support: "Support",
};

export function UserDetail({
  user,
  canEdit,
}: {
  user: PlatformUserOut;
  canEdit: boolean;
}) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[var(--text-h3)] font-semibold">
            {user.full_name}
          </h1>
          <StatusBadge
            entity="platform_user"
            status={user.is_active ? "active" : "inactive"}
          />
        </div>
        {canEdit ? (
          <Button asChild variant="secondary">
            <Link href={`/platform/users/${user.id}/edit`}>Edit</Link>
          </Button>
        ) : null}
      </div>

      <Card className="grid grid-cols-2 gap-5 p-6">
        <ReadOnlyField label="Email" value={user.email} />
        <ReadOnlyField label="Role" value={ROLE_LABELS[user.role]} />
        <ReadOnlyField
          label="Last login"
          value={
            user.last_login_at ? (
              <RelativeTime value={user.last_login_at} />
            ) : (
              "Never"
            )
          }
        />
        <ReadOnlyField
          label="Created"
          value={<FormattedDateTime value={user.created_at} />}
        />
      </Card>

      <AuditBar entityType="platform_user" entityId={user.id} />
    </div>
  );
}
```

> `ReadOnlyField`'s `value` prop type: confirm it accepts `ReactNode` (the FormField sub-plan built it to render arbitrary content). If it is `string`-only, render the dates as pre-formatted strings or pass a child instead. Check `packages/ui/src/components/ReadOnlyField` before finalizing. `Button asChild variant="secondary"` — same `asChild` caveat as Task 5.

- [ ] **Step 4: Write the detail page (server)**

```tsx
// admin/apps/portal/app/platform/(authed)/users/[id]/page.tsx
import { notFound } from "next/navigation";
import type { PlatformUserOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { UserDetail } from "./_components/UserDetail";

export const metadata = { title: "Platform User" };

export default async function PlatformUserDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.users.read");

  const { data } = await resources.admin.getUser(id);
  if (!data) notFound();

  return (
    <UserDetail
      user={data as PlatformUserOut}
      canEdit={userHasPermission(user, "platform.users.write")}
    />
  );
}
```

> Next.js 15 makes `params` a Promise — await it (matches the App Router version in use). If `getUser` throws a typed `NotFoundError` on 404 rather than returning `{ data: undefined }`, wrap the call in try/catch and call `notFound()` in the catch. Check the error-middleware behavior for 404 (it currently only throws for 402/403-gate/5xx, so 404 returns `{ error }` and `data` is undefined — the `if (!data)` guard handles it).

- [ ] **Step 5: Write loading + error boundaries**

```tsx
// admin/apps/portal/app/platform/(authed)/users/[id]/loading.tsx
import { Card, Skeleton } from "@sacco/ui";

export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-8 w-64" />
      <Card className="grid grid-cols-2 gap-5 p-6">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </Card>
    </div>
  );
}
```

```tsx
// admin/apps/portal/app/platform/(authed)/users/[id]/error.tsx
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
      <h2 className="text-[18px] font-semibold">Couldn’t load this user</h2>
      <Button onClick={reset}>Try again</Button>
    </Card>
  );
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal test -- UserDetail`
Expected: PASS (3 assertions).

- [ ] **Step 7: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/users/[id]/page.tsx" \
  "admin/apps/portal/app/platform/(authed)/users/[id]/loading.tsx" \
  "admin/apps/portal/app/platform/(authed)/users/[id]/error.tsx" \
  "admin/apps/portal/app/platform/(authed)/users/[id]/_components/UserDetail.tsx" \
  admin/apps/portal/src/__tests__/platform-users/UserDetail.test.tsx
git commit -m "feat(portal): platform user detail screen (+ audit bar)"
```

---

## Task 8: Edit screen with maker-checker UX (`/platform/users/[id]/edit`)

The backend applies `full_name` immediately and routes `is_active` / `role` through the `platform_user.update_sensitive` approval request. The form's job is purely UX: if a **sensitive** field (`is_active`, `role`) is dirty on submit, show `<MakerCheckerConfirmDialog>` first (contract V); if only `full_name` changed, submit directly.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/users/[id]/edit/page.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/users/[id]/edit/_components/EditUserForm.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-users/EditUserForm.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-users/EditUserForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { PlatformUserOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const patchUser = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { admin: { patchUser } } }),
}));

import { EditUserForm } from "../../../app/platform/(authed)/users/[id]/edit/_components/EditUserForm";

const user: PlatformUserOut = {
  id: "u1",
  email: "ada@example.com",
  full_name: "Ada Ops",
  is_active: true,
  is_superuser: false,
  role: "support",
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
  last_login_at: null,
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <EditUserForm user={user} />
    </QueryClientProvider>,
  );
}

describe("EditUserForm", () => {
  it("submits a name-only change directly without the maker-checker dialog", async () => {
    patchUser.mockResolvedValue({ data: { ...user }, error: undefined });
    renderForm();
    const name = screen.getByLabelText(/full name/i);
    await userEvent.clear(name);
    await userEvent.type(name, "Ada Renamed");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(patchUser).toHaveBeenCalledWith("u1", {
        full_name: "Ada Renamed",
        is_active: true,
        role: "support",
      }),
    );
    expect(
      screen.queryByText(/create an approval request, not execute/i),
    ).toBeNull();
  });

  it("requires confirmation via the maker-checker dialog when role changes", async () => {
    patchUser.mockResolvedValue({ data: { ...user }, error: undefined });
    renderForm();
    // change role support -> admin via the select (test id wiring in component)
    await userEvent.click(screen.getByLabelText(/role/i));
    await userEvent.click(screen.getByRole("option", { name: /admin/i }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    // Dialog appears; patch not called yet.
    expect(
      await screen.findByText(/create an approval request, not execute/i),
    ).toBeInTheDocument();
    expect(patchUser).not.toHaveBeenCalled();

    await userEvent.click(
      screen.getByRole("button", { name: /create approval request/i }),
    );
    await waitFor(() =>
      expect(patchUser).toHaveBeenCalledWith("u1", {
        full_name: "Ada Ops",
        is_active: true,
        role: "admin",
      }),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- EditUserForm`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the edit form**

```tsx
// admin/apps/portal/app/platform/(authed)/users/[id]/edit/_components/EditUserForm.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Checkbox,
  FormField,
  Input,
  MakerCheckerConfirmDialog,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  updatePlatformUserSchema,
  type PlatformRole,
  type PlatformUserOut,
  type UpdatePlatformUserInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";

const ROLE_OPTIONS: { value: PlatformRole; label: string }[] = [
  { value: "support", label: "Support" },
  { value: "finance", label: "Finance" },
  { value: "admin", label: "Admin" },
  { value: "superuser", label: "Superuser" },
];

export function EditUserForm({ user }: { user: PlatformUserOut }) {
  const router = useRouter();
  const { resources } = useAuth();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState<UpdatePlatformUserInput | null>(null);

  const form = useForm<UpdatePlatformUserInput>({
    resolver: zodResolver(updatePlatformUserSchema),
    defaultValues: {
      full_name: user.full_name,
      is_active: user.is_active,
      role: user.role,
    },
  });

  const mutation = useTypedMutation<unknown, UpdatePlatformUserInput>(
    async (vars) => {
      const res = await resources.admin.patchUser(user.id, vars);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [
        queryKeys.platformUsers.root(),
        queryKeys.platformUsers.detail(user.id),
      ],
      onSuccess: () => router.push(`/platform/users/${user.id}`),
    },
  );

  function onValid(values: UpdatePlatformUserInput) {
    const sensitiveDirty =
      values.is_active !== user.is_active || values.role !== user.role;
    if (sensitiveDirty) {
      setPending(values);
      setConfirmOpen(true);
      return;
    }
    mutation.mutate(values);
  }

  return (
    <>
      <form
        className="flex max-w-xl flex-col gap-5"
        onSubmit={form.handleSubmit(onValid)}
      >
        <FormField
          control={form.control}
          name="full_name"
          label="Full name"
          required
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
          name="role"
          label="Role"
          required
          helpText="Changing the role creates an approval request."
          render={({ field, id }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger id={id}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
        <FormField
          control={form.control}
          name="is_active"
          label="Active"
          helpText="Deactivating a user creates an approval request."
          render={({ field, id }) => (
            <Checkbox
              id={id}
              checked={field.value}
              onCheckedChange={(v) => field.onChange(Boolean(v))}
            />
          )}
        />
        <div className="flex gap-3">
          <Button type="submit" disabled={mutation.isPending}>
            Save
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => router.push(`/platform/users/${user.id}`)}
          >
            Cancel
          </Button>
        </div>
      </form>

      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        operationLabel="platform user change"
        subjectLabel={user.email}
        busy={mutation.isPending}
        onConfirm={() => {
          if (pending) mutation.mutate(pending);
          setConfirmOpen(false);
        }}
      />
    </>
  );
}
```

> `MakerCheckerConfirmDialog` props verified: `{ open, onOpenChange, operationLabel, subjectLabel?, onConfirm, busy?, cancelLabel? }` — it injects the locked title/description/confirm-label ("Create Approval Request"). `Checkbox` is exported from `@sacco/ui` (used inside DataTable). Confirm its `checked` / `onCheckedChange` prop names in `packages/ui/src/components/Checkbox` (Radix-style, verified in DataTable usage).

- [ ] **Step 4: Write the edit page (server gate + fetch current values)**

```tsx
// admin/apps/portal/app/platform/(authed)/users/[id]/edit/page.tsx
import { notFound } from "next/navigation";
import type { PlatformUserOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { EditUserForm } from "./_components/EditUserForm";

export const metadata = { title: "Edit Platform User" };

export default async function EditPlatformUserPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.users.write");

  const { data } = await resources.admin.getUser(id);
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Edit platform user</h1>
      <EditUserForm user={data as PlatformUserOut} />
    </div>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal test -- EditUserForm`
Expected: PASS — name-only path skips the dialog and patches directly; role change opens the locked dialog and patches only after "Create Approval Request".

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/users/[id]/edit" \
  admin/apps/portal/src/__tests__/platform-users/EditUserForm.test.tsx
git commit -m "feat(portal): edit platform user screen with maker-checker UX"
```

---

## Task 9: Navigation entry + full-module verification

**Files:**
- Modify: `admin/apps/portal/src/components/AppShellSidebar.tsx` (or the sidebar nav config it reads)

- [ ] **Step 1: Locate the platform sidebar nav config**

Run: `cd admin && rg -n "platform" apps/portal/src/components/AppShellSidebar.tsx`
Inspect how nav items are declared (label, href, permission). If a "Users" item already exists pointing at `/platform/users`, skip to Step 3.

- [ ] **Step 2: Add the Users nav item**

Add an entry to the platform nav group following the file's existing item shape, for example:

```tsx
{ label: "Users", href: "/platform/users", permission: "platform.users.read" },
```

Match the exact property names the existing items use (the gating likely flows through `PermissionGuard` / `userHasPermission`). Do not invent a new gating mechanism — reuse what the sidebar already does.

- [ ] **Step 3: Run the full module verification**

```bash
cd admin
pnpm --filter @sacco/schemas test
pnpm --filter @sacco/ui test -- StatusBadge
pnpm --filter @sacco/portal test -- platform-users server-page-context
pnpm --filter @sacco/portal typecheck
pnpm --filter @sacco/portal lint
pnpm --filter @sacco/ui typecheck
```

Expected: all green. Address any `exactOptionalPropertyTypes` / `noUncheckedIndexedAccess` strictness errors (the established pattern in this repo is conditional spreads for optional props — see prior sub-plans' deviation notes).

- [ ] **Step 4: Manual smoke against the running stack (optional but recommended)**

Bring up the backend + portal (`make admin-dev` or the documented target), log in as a superuser, and walk: list → new (create) → detail → edit (rename = immediate; change role = maker-checker dialog → approval request created). Confirm a `support`-role user sees the list but no "New user"/"Edit" buttons, and that the API rejects a forged write (gating is UX-only).

- [ ] **Step 5: Commit**

```bash
git add admin/apps/portal/src/components/AppShellSidebar.tsx
git commit -m "feat(portal): platform Users nav entry + SP12 verification"
```

---

## Self-Review

**Spec coverage (portal index §642):**
- Screens `/platform/users` (Task 5), `/new` (Task 6), `/[id]` (Task 7), `/[id]/edit` (Task 8) — all covered.
- Endpoints consumed `GET|POST /platform/users`, `GET|PATCH /platform/users/{id}` — via `resources.admin.listUsers/createUser/getUser/patchUser`. No new backend endpoints (contract B ✓).
- Foundation validated: DataTable (Task 4), RHF/Zod form (Tasks 6, 8), permission gating (Task 3 helper + Tasks 5–8), maker-checker pattern for sensitive fields (Task 8) ✓.

**Deliberate gaps (documented, not omissions):**
- `<MakerCheckerBanner>` on detail is deferred — no approvals-list endpoint in SP12's scope. Lands with the approvals-consuming sub-plan.
- `<AuditBar>` renders its placeholder (contract W) until the audit-query endpoint (P1.7-F) ships.
- Playwright e2e deferred to the dedicated e2e sub-plan (seeded backend).
- next-intl not introduced (portal has not wired it; matches existing pages).

**Type consistency:** `PlatformUserOut`, `PlatformRole`, `CreatePlatformUserInput`, `UpdatePlatformUserInput` defined in Task 1 and reused verbatim in Tasks 4–8. `platform_user` StatusEntity defined in Task 2 and consumed in Tasks 4, 7. `queryKeys.platformUsers` defined in Task 3 and consumed in Tasks 6, 8. `getPlatformPageContext` / `requirePlatformPermission` defined in Task 3 and consumed in Tasks 5–8.

**Verification-before-substitution flags:** Several steps note "verify the exact export name before wiring" for `@sacco/ui` primitives whose precise sub-export identifiers (`Select*`, `Skeleton`, `RelativeTime`, `Button asChild`, `ReadOnlyField` value type, `Checkbox` props) were not all individually opened during planning. These are explicitly called out at each call site so the implementer confirms against `packages/ui/src/index.ts` rather than guessing.
