# Billing — Plans + Subscriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Billing nav group's **Plans** (list/detail/new/edit) and **Subscriptions** (list/detail/cancel/reactivate) screens to the admin portal, plus the tenant-context **assign-plan** flow deferred from SP14 — as a pure client of existing `/platform/billing/*` and `/platform/tenants/{id}/assign-plan` endpoints.

**Architecture:** Reuses the SP12–14 server-page-context + in-memory `<DataTable>` adapter + RHF/Zod form + maker-checker patterns. Plans + Subscriptions live under `app/platform/(authed)/billing/*` joined by a shared `<BillingTabs>` strip; assign-plan lives under the tenant route as a `TenantActions` button. Two small foundation fixes precede the screens: hand-written `SubscriptionPlanOut`/`SubscriptionOut` types + `assignPlanSchema` in `@sacco/schemas`, and a body fix to `billing.cancelSubscription` in `@sacco/api-client`.

**Tech Stack:** Next.js 15 App Router, React 19, TS strict, `@sacco/ui` (DataTable, FormField, MoneyInput, DateInput, Select, ConfirmDialog, MakerCheckerConfirmDialog, StatusBadge, Money, FormattedDate), `@sacco/schemas` (Zod), `@sacco/api-client` (`resources.billing.*`, `resources.tenants.assignPlan`), Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **Zero new backend endpoints** (contract B). All exist: `GET/POST /platform/billing/plans`, `GET/PATCH /platform/billing/plans/{id}`, `GET/POST /platform/billing/subscriptions`, `GET /platform/billing/subscriptions/{id}`, `POST .../{id}/cancel?mode=`, `POST .../{id}/reactivate`, `POST /platform/tenants/{id}/assign-plan`. api-client methods exist (`resources.billing.listPlans/createPlan/getPlan/patchPlan/listSubscriptions/getSubscription/cancelSubscription/reactivateSubscription`, `resources.tenants.assignPlan`). queryKeys exist (`queryKeys.billing.plans/plan/subscriptions/subscription`).
- **The `Promise<never>` cast wart applies to every billing + tenants resource call** — cast to `{ data?, error? }` with the standard comment at every call site (see SP12/13/14).
- **Permissions** (already in `permissions.ts`): `billing.read` (finance) gates all reads; `billing.write` (admin) gates plan create/edit, subscription cancel/reactivate, and assign-plan. **Note the keys are `billing.read`/`billing.write` — NOT prefixed with `platform.`** (unlike `platform.tenants.write`). Gate before fetch on every server page.
- **Backend facts (authoritative, do not reimplement):**
  - `GET /platform/billing/plans` is **unpaginated** → in-memory DataTable adapter (SP12 UsersTable pattern). `only_active` query filter exists.
  - `POST`/`PATCH` plans are **direct** admin calls (no maker-checker). Backend `SubscriptionPlanPatch` treats `code`/`billing_period`/`currency` as immutable (omitted from the patch schema).
  - `GET /platform/billing/subscriptions` accepts `tenant_id` + `status_filter` query params (unused by the client filter — we filter client-side like SP13).
  - `POST .../{id}/cancel` **requires a `SubscriptionCancelIn` body `{ reason, cancel_at_period_end }`** AND a `mode` query param (`at_period_end` default → direct, `immediate` → maker-checker `billing.cancel_subscription` approval). The body's `cancel_at_period_end` is ignored by the handler (mode decides); only `reason` matters. `at_period_end` returns `{status:"cancellation_scheduled"}`; `immediate` returns `{status:"pending_approval", approval_request_id}`.
  - `POST .../{id}/reactivate` returns `SubscriptionOut`; 409 `InvalidTransition`, 404 unknown.
  - `POST /platform/tenants/{id}/assign-plan` (admin) and `POST /platform/billing/subscriptions` both delegate to `SubscriptionService.assign` and return `SubscriptionOut` (201); 409 if a live subscription exists or the plan is inactive, 404 if tenant/plan unknown. **SP15 uses the tenant-context path.**
  - `SubscriptionOut` carries `tenant_id`/`plan_id` only — **no embedded names**.
- **Out of scope:** invoices + payments (SP16); the `features` dict editor on the plan form (YAGNI — defaults `{}`); e2e (seeded-backend sub-plan); next-intl (portal-wide deferral — raw English); `<MakerCheckerBanner>` on subscription detail (needs the approvals-list endpoint, SP17); `<AuditBar>` lights up when the P1.7-F audit endpoint ships (placeholder until then).

## File Structure

**New — `@sacco/schemas`**
- Modify `packages/schemas/src/billing.ts` — add `SubscriptionPlanOut`, `SubscriptionOut` interfaces + `assignPlanSchema` + `AssignPlanInput`.
- Modify `packages/schemas/src/__tests__/billing.test.ts` — add `assignPlanSchema` cases.

**Modify — `@sacco/api-client`**
- `packages/api-client/src/resources/billing.ts` — `cancelSubscription` sends a `{ reason }` body.

**New — portal**
- `apps/portal/app/platform/(authed)/billing/_components/BillingTabs.tsx` — shared Plans|Subscriptions strip.
- `apps/portal/app/platform/(authed)/billing/plans/_components/PlansTable.tsx`
- `apps/portal/app/platform/(authed)/billing/plans/page.tsx`
- `apps/portal/app/platform/(authed)/billing/plans/[id]/page.tsx`
- `apps/portal/app/platform/(authed)/billing/plans/new/_components/PlanForm.tsx`
- `apps/portal/app/platform/(authed)/billing/plans/new/page.tsx`
- `apps/portal/app/platform/(authed)/billing/plans/[id]/edit/_components/EditPlanForm.tsx`
- `apps/portal/app/platform/(authed)/billing/plans/[id]/edit/page.tsx`
- `apps/portal/app/platform/(authed)/billing/subscriptions/_components/SubscriptionsTable.tsx`
- `apps/portal/app/platform/(authed)/billing/subscriptions/page.tsx`
- `apps/portal/app/platform/(authed)/billing/subscriptions/[id]/_components/SubscriptionActions.tsx`
- `apps/portal/app/platform/(authed)/billing/subscriptions/[id]/page.tsx`
- `apps/portal/app/platform/(authed)/tenants/[id]/assign-plan/_components/AssignPlanForm.tsx`
- `apps/portal/app/platform/(authed)/tenants/[id]/assign-plan/page.tsx`
- Tests under `apps/portal/src/__tests__/platform-billing/`.

**Modify — portal**
- `apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantActions.tsx` — add `canAssignPlan` prop + "Assign plan" button.
- `apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx` — thread `canAssignPlan`.
- `apps/portal/app/platform/(authed)/tenants/[id]/page.tsx` — pass `canAssignPlan={userHasPermission(user, "billing.write")}`.

---

# PART A — Foundation (schemas + api-client)

## Task 1: Plan/Subscription Out types + assign-plan schema (`@sacco/schemas`)

**Files:**
- Modify: `admin/packages/schemas/src/billing.ts`
- Modify: `admin/packages/schemas/src/__tests__/billing.test.ts`

- [ ] **Step 1: Write the failing test (append to billing.test.ts)**

```ts
import { assignPlanSchema } from "../billing";

describe("assignPlanSchema", () => {
  it("accepts a plan_id alone", () => {
    expect(
      assignPlanSchema.safeParse({ plan_id: "11111111-1111-1111-1111-111111111111" })
        .success,
    ).toBe(true);
  });
  it("accepts a plan_id with an ISO start_date", () => {
    expect(
      assignPlanSchema.safeParse({
        plan_id: "11111111-1111-1111-1111-111111111111",
        start_date: "2026-07-01",
      }).success,
    ).toBe(true);
  });
  it("rejects a missing plan_id", () => {
    expect(assignPlanSchema.safeParse({ start_date: "2026-07-01" }).success).toBe(false);
  });
  it("rejects a non-uuid plan_id", () => {
    expect(assignPlanSchema.safeParse({ plan_id: "nope" }).success).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/schemas test -- billing`
Expected: FAIL — `assignPlanSchema` is not exported.

- [ ] **Step 3: Add the schema + Out types to `billing.ts`**

Append after the existing `subscriptionCancelSchema` block:

```ts
// Tenant-context assign-plan body (tenant_id comes from the URL path).
// Mirrors AssignPlanIn in app/platform_/tenants/schemas.py.
export const assignPlanSchema = z.object({
  // Inline uuid (not the shared `uuid` helper) so the empty-default Select
  // surfaces a natural "Select a plan" message on submit.
  plan_id: z.string().uuid("Select a plan"),
  start_date: isoDate.optional(),
});
export type AssignPlanInput = z.infer<typeof assignPlanSchema>;

// ── Read models (hand-written, mirror app/platform_/billing/schemas.py) ──────

export interface SubscriptionPlanOut {
  id: string;
  code: string;
  name: string;
  description: string | null;
  currency: string;
  base_price: string;
  per_user_price: string;
  per_member_price: string;
  billing_period: "monthly" | "quarterly" | "annual";
  member_limit: number | null;
  user_limit: number | null;
  features: Record<string, unknown>;
  trial_period_days: number;
  grace_period_days: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionOut {
  id: string;
  tenant_id: string;
  plan_id: string;
  status: string;
  started_at: string;
  current_period_start: string;
  current_period_end: string;
  grace_period_ends_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  next_billing_date: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}
```

> `base_price`/`per_user_price`/`per_member_price` are `string` (the backend returns `Decimal` serialized as a string; this matches the `moneyString` Zod helper and `<Money>`/`<MoneyInput>` which take string amounts).

- [ ] **Step 4: Run to verify it passes**

Run: `cd admin && pnpm --filter @sacco/schemas test -- billing` → PASS. `pnpm --filter @sacco/schemas typecheck` → clean.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/schemas/src/billing.ts admin/packages/schemas/src/__tests__/billing.test.ts
git commit -m "feat(schemas): billing plan/subscription Out types + assign-plan schema"
```

---

## Task 2: Fix `billing.cancelSubscription` to send the reason body (`@sacco/api-client`)

The backend cancel endpoint requires a `SubscriptionCancelIn` body (`reason`). The current client method sends only the `mode` query, so a real call 422s. Add the body parameter.

**Files:**
- Modify: `admin/packages/api-client/src/resources/billing.ts`

- [ ] **Step 1: Read the current method**

In `packages/api-client/src/resources/billing.ts`, the current `cancelSubscription` is:

```ts
    cancelSubscription: (
      id: string,
      query?: { mode?: "at_period_end" | "immediate" },
    ) =>
      api.POST("/platform/billing/subscriptions/{subscription_id}/cancel" as never, {
        params: { path: { subscription_id: id }, query },
      } as never),
```

- [ ] **Step 2: Replace it with the body-carrying version**

```ts
    cancelSubscription: (
      id: string,
      body: { reason: string },
      query?: { mode?: "at_period_end" | "immediate" },
    ) =>
      api.POST("/platform/billing/subscriptions/{subscription_id}/cancel" as never, {
        params: { path: { subscription_id: id }, query },
        body,
      } as never),
```

> Signature is now `cancelSubscription(id, body, query?)`. The screen test in Task 9 asserts this exact call shape. No other caller exists yet.

- [ ] **Step 3: Verify**

Run: `cd admin && pnpm --filter @sacco/api-client typecheck` → clean. `pnpm --filter @sacco/api-client lint` → clean.

- [ ] **Step 4: Commit**

```bash
git add admin/packages/api-client/src/resources/billing.ts
git commit -m "fix(api-client): cancelSubscription sends the required reason body"
```

---

# PART B — Plans

## Task 3: `<BillingTabs>` sub-nav strip

A shared client strip with Plans | Subscriptions links, highlighting the active section via `usePathname`. Rendered at the top of every billing page.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/_components/BillingTabs.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-billing/BillingTabs.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-billing/BillingTabs.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let pathname = "/platform/billing/plans";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

import { BillingTabs } from "../../../app/platform/(authed)/billing/_components/BillingTabs";

describe("BillingTabs", () => {
  it("links to plans and subscriptions", () => {
    pathname = "/platform/billing/plans";
    render(<BillingTabs />);
    expect(screen.getByRole("link", { name: /plans/i })).toHaveAttribute(
      "href",
      "/platform/billing/plans",
    );
    expect(screen.getByRole("link", { name: /subscriptions/i })).toHaveAttribute(
      "href",
      "/platform/billing/subscriptions",
    );
  });

  it("marks the active section with aria-current", () => {
    pathname = "/platform/billing/subscriptions";
    render(<BillingTabs />);
    expect(screen.getByRole("link", { name: /subscriptions/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: /plans/i })).not.toHaveAttribute(
      "aria-current",
    );
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- BillingTabs` → FAIL (module not found).

- [ ] **Step 3: Write the component**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/_components/BillingTabs.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/platform/billing/plans", label: "Plans" },
  { href: "/platform/billing/subscriptions", label: "Subscriptions" },
] as const;

export function BillingTabs() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 border-b border-[var(--border-subtle)]" aria-label="Billing sections">
      {TABS.map((tab) => {
        const active = pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={
              active
                ? "border-b-2 border-[var(--interactive-primary-bg)] px-4 py-2 text-[var(--text-primary)] font-medium"
                : "border-b-2 border-transparent px-4 py-2 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
```

> Verify `--border-subtle` exists in `packages/ui/src/tokens.css` (grep `border-`); if the closest name differs (e.g. `--border-default`), use that. `--interactive-primary-bg` is used by Button and is known-good.

- [ ] **Step 4: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- BillingTabs` → PASS (2). `typecheck` + `lint` → clean.

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/_components/BillingTabs.tsx" admin/apps/portal/src/__tests__/platform-billing/BillingTabs.test.tsx
git commit -m "feat(portal): billing Plans/Subscriptions tab strip"
```

---

## Task 4: Plans list (`/platform/billing/plans`)

In-memory DataTable adapter over the unpaginated `listPlans`, mirroring SP12 `UsersTable`.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/plans/_components/PlansTable.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/billing/plans/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-billing/PlansTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-billing/PlansTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/platform/billing/plans",
}));

import { PlansTable } from "../../../app/platform/(authed)/billing/plans/_components/PlansTable";

function plan(over: Partial<SubscriptionPlanOut>): SubscriptionPlanOut {
  return {
    id: "p1", code: "starter", name: "Starter", description: null, currency: "UGX",
    base_price: "50000", per_user_price: "0", per_member_price: "0",
    billing_period: "monthly", member_limit: null, user_limit: null, features: {},
    trial_period_days: 0, grace_period_days: 30, is_active: true,
    created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

describe("PlansTable", () => {
  it("renders plan rows with a linked name and formatted price", () => {
    render(
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <PlansTable rows={[plan({ id: "p1", name: "Starter", base_price: "50000" })]} />
      </TenantCurrencyProvider>,
    );
    const link = screen.getByRole("link", { name: /starter/i });
    expect(link).toHaveAttribute("href", "/platform/billing/plans/p1");
    expect(screen.getByText(/50,000/)).toBeInTheDocument();
  });

  it("renders the empty state with no rows", () => {
    render(
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <PlansTable rows={[]} />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByText(/no plans/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- PlansTable` → FAIL.

- [ ] **Step 3: Write `PlansTable.tsx`**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/plans/_components/PlansTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  Money,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";

const columns: DataTableProps<SubscriptionPlanOut>["columns"] = [
  {
    id: "name",
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => (
      <Link
        href={`/platform/billing/plans/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.name}
      </Link>
    ),
  },
  { id: "code", accessorKey: "code", header: "Code" },
  {
    id: "base_price",
    accessorKey: "base_price",
    header: "Base price",
    cell: ({ row }) => (
      <Money amount={row.original.base_price} currency={row.original.currency} />
    ),
  },
  { id: "billing_period", accessorKey: "billing_period", header: "Period" },
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
];

export function sortPlans(
  rows: SubscriptionPlanOut[],
  column: string | null,
  dir: "asc" | "desc",
): SubscriptionPlanOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof SubscriptionPlanOut];
    const bv = b[column as keyof SubscriptionPlanOut];
    const as = av === null ? "" : String(av);
    const bs = bv === null ? "" : String(bv);
    return as.localeCompare(bs);
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/**
 * Renders the full (unpaginated) plan list through DataTable. Sort +
 * pagination are client-side because GET /platform/billing/plans has no
 * paging params.
 */
export function PlansTable({ rows }: { rows: SubscriptionPlanOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "name", direction: "asc" },
    defaultPageSize: 25,
  });

  const sorted = useMemo(
    () => sortPlans(rows, urlState.sortColumn, urlState.sortDirection),
    [rows, urlState.sortColumn, urlState.sortDirection],
  );

  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<SubscriptionPlanOut>
      id="billing-plans"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No plans",
        description: "Create the first subscription plan to get started.",
      }}
    />
  );
}
```

> `StatusBadge entity="platform_user"` is reused for the active/inactive pill (its map has `active`/`inactive`) — same choice SP12 made for users. Do NOT invent a "plan" entity (contract S: the map lives in `status-maps.ts`; adding one is a separate PR and unnecessary here).

- [ ] **Step 4: Write the page**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/plans/page.tsx
import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { BillingTabs } from "../_components/BillingTabs";
import { PlansTable } from "./_components/PlansTable";

export const metadata = { title: "Plans" };

export default async function BillingPlansPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  // resources.billing.listPlans is typed Promise<never>; cast to the real shape.
  const { data } = await (
    resources.billing.listPlans() as Promise<{
      data?: SubscriptionPlanOut[];
      error?: unknown;
    }>
  );
  const rows = data ?? [];
  const canWrite = userHasPermission(user, "billing.write");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Billing</h1>
        {canWrite ? (
          <Button asChild>
            <Link href="/platform/billing/plans/new">New plan</Link>
          </Button>
        ) : null}
      </div>
      <BillingTabs />
      <Card className="p-0">
        <PlansTable rows={rows} />
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- PlansTable` → PASS (2). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/plans/_components/PlansTable.tsx" "admin/apps/portal/app/platform/(authed)/billing/plans/page.tsx" admin/apps/portal/src/__tests__/platform-billing/PlansTable.test.tsx
git commit -m "feat(portal): billing plans list"
```

---

## Task 5: Plan detail (`/platform/billing/plans/[id]`)

Read-only overview + Edit action + AuditBar placeholder.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/plans/[id]/page.tsx`

- [ ] **Step 1: Write the page (no separate test — it's a server component that only fetches + renders primitives; the PlansTable/EditPlanForm tests cover the interactive parts)**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/plans/[id]/page.tsx
import Link from "next/link";
import { notFound } from "next/navigation";
import { AuditBar, Button, Card, Money, StatusBadge } from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";

export const metadata = { title: "Plan" };

export default async function PlanDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const { data } = await (
    resources.billing.getPlan(id) as Promise<{
      data?: SubscriptionPlanOut;
      error?: unknown;
    }>
  );
  if (!data) notFound();
  const canWrite = userHasPermission(user, "billing.write");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">{data.name}</h1>
        {canWrite ? (
          <Button asChild variant="secondary">
            <Link href={`/platform/billing/plans/${data.id}/edit`}>Edit</Link>
          </Button>
        ) : null}
      </div>
      <Card className="flex flex-col gap-3 p-6">
        <Row label="Code" value={data.code} />
        <Row label="Status" value={
          <StatusBadge entity="platform_user" status={data.is_active ? "active" : "inactive"} />
        } />
        <Row label="Base price" value={<Money amount={data.base_price} currency={data.currency} />} />
        <Row label="Per user" value={<Money amount={data.per_user_price} currency={data.currency} />} />
        <Row label="Per member" value={<Money amount={data.per_member_price} currency={data.currency} />} />
        <Row label="Billing period" value={data.billing_period} />
        <Row label="Trial days" value={String(data.trial_period_days)} />
        <Row label="Grace days" value={String(data.grace_period_days)} />
        {data.description ? <Row label="Description" value={data.description} /> : null}
      </Card>
      <AuditBar entityType="subscription_plan" entityId={data.id} />
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-[var(--text-primary)]">{value}</span>
    </div>
  );
}
```

> Confirm `<AuditBar>` prop names from `packages/ui/src/components/AuditBar/AuditBar.tsx` (the spec said `entityType`/`entityId`). If they differ, match the component. `entityType="subscription_plan"` is a free-form string fed to the placeholder; it does not need a registry entry.

- [ ] **Step 2: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal typecheck` → clean. `pnpm --filter @sacco/portal lint` → clean.

- [ ] **Step 3: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/plans/[id]/page.tsx"
git commit -m "feat(portal): billing plan detail"
```

---

## Task 6: New-plan form (`/platform/billing/plans/new`)

RHF + `subscriptionPlanSchema` → `createPlan` (direct, admin). First portal use of `<MoneyInput>` inside `<FormField>`.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/plans/new/_components/PlanForm.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/billing/plans/new/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-billing/PlanForm.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-billing/PlanForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createPlan = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { billing: { createPlan } } }),
}));

import { PlanForm } from "../../../app/platform/(authed)/billing/plans/new/_components/PlanForm";

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <PlanForm />
        <Toaster />
      </TenantCurrencyProvider>
    </QueryClientProvider>,
  );
}

describe("PlanForm (create)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("rejects a blank name + code", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: /create plan/i }));
    expect(await screen.findByText(/code is required/i)).toBeInTheDocument();
    expect(createPlan).not.toHaveBeenCalled();
  });

  it("submits a new plan and redirects with a toast", async () => {
    createPlan.mockResolvedValue({ data: { id: "p9" }, error: undefined });
    renderForm();
    await userEvent.type(screen.getByLabelText(/code/i), "growth");
    await userEvent.type(screen.getByLabelText(/^name/i), "Growth");
    await userEvent.type(screen.getByLabelText(/base price/i), "150000");
    await userEvent.click(screen.getByRole("button", { name: /create plan/i }));
    await waitFor(() => expect(createPlan).toHaveBeenCalledTimes(1));
    const body = createPlan.mock.calls[0][0] as Record<string, unknown>;
    expect(body).toMatchObject({ code: "growth", name: "Growth", base_price: "150000", billing_period: "monthly" });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/billing/plans/p9"));
    expect(await screen.findByText(/plan created/i)).toBeInTheDocument();
  });

  it("surfaces an error and does not redirect", async () => {
    createPlan.mockResolvedValue({ data: undefined, error: { detail: "Code already exists" } });
    renderForm();
    await userEvent.type(screen.getByLabelText(/code/i), "growth");
    await userEvent.type(screen.getByLabelText(/^name/i), "Growth");
    await userEvent.type(screen.getByLabelText(/base price/i), "150000");
    await userEvent.click(screen.getByRole("button", { name: /create plan/i }));
    expect(await screen.findByText(/code already exists/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- PlanForm` → FAIL.

- [ ] **Step 3: Write `PlanForm.tsx`**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/plans/new/_components/PlanForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormField,
  Input,
  MoneyInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import { subscriptionPlanSchema, type SubscriptionPlanInput } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

const CURRENCIES = ["UGX", "KES", "TZS", "RWF", "USD", "EUR", "GBP"] as const;
const PERIODS = ["monthly", "quarterly", "annual"] as const;

export function PlanForm() {
  const router = useRouter();
  const { resources } = useAuth();
  const form = useForm<SubscriptionPlanInput>({
    resolver: zodResolver(subscriptionPlanSchema),
    defaultValues: {
      code: "",
      name: "",
      description: "",
      currency: "UGX",
      base_price: "",
      per_user_price: "0",
      per_member_price: "0",
      billing_period: "monthly",
      features: {},
      trial_period_days: 0,
      grace_period_days: 30,
    },
  });

  const mutation = useTypedMutation<{ id: string }, SubscriptionPlanInput>(
    async (vars) => {
      // resources.billing.createPlan is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.billing.createPlan(vars as Record<string, unknown>) as Promise<{
          data?: { id: string };
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as { id: string };
    },
    {
      invalidates: [queryKeys.billing.plans()],
      onSuccess: (data) => {
        toast.success("Plan created");
        router.push(`/platform/billing/plans/${data.id}`);
      },
      onError: (error) => {
        toast.error("The plan was not created", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <form
      noValidate
      className="flex max-w-xl flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <FormField control={form.control} name="code" label="Code" required
        helpText="Lowercase letters, digits, _ or -. Immutable after creation."
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="name" label="Name" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="description" label="Description"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="currency" label="Currency" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="base_price" label="Base price" required
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="per_user_price" label="Per-user price"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="per_member_price" label="Per-member price"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="billing_period" label="Billing period" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIODS.map((p) => (
                <SelectItem key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="trial_period_days" label="Trial days" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} type="number" inputMode="numeric"
            aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""}
            onChange={(e) => field.onChange(e.target.value === "" ? undefined : Number(e.target.value))}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="grace_period_days" label="Grace days" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} type="number" inputMode="numeric"
            aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""}
            onChange={(e) => field.onChange(e.target.value === "" ? undefined : Number(e.target.value))}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Create plan</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/platform/billing/plans")}>Cancel</Button>
      </div>
    </form>
  );
}
```

> `subscriptionPlanSchema` omits `member_limit`/`user_limit` from the form here intentionally (optional, rarely set at create; add later if needed — YAGNI). They stay `undefined` and the backend treats them as "no limit". `features` defaults `{}` and is not surfaced (out of scope).

- [ ] **Step 4: Write the page**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/plans/new/page.tsx
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { PlanForm } from "./_components/PlanForm";

export const metadata = { title: "New Plan" };

export default async function NewPlanPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.write");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">New plan</h1>
      <PlanForm />
    </div>
  );
}
```

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- PlanForm` → PASS (3). `typecheck` + `lint` → clean.

> If `getByLabelText(/^name/i)` is ambiguous (matches "Name" and nothing else — fine; "Per-user price" etc. won't match `^name`), keep the anchored regex. If the number-field clearing causes a Zod "expected number, received nan" in a test, ensure the `onChange` converts `""`→`undefined` exactly as shown.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/plans/new" admin/apps/portal/src/__tests__/platform-billing/PlanForm.test.tsx
git commit -m "feat(portal): new-plan form"
```

---

## Task 7: Edit-plan form (`/platform/billing/plans/[id]/edit`)

RHF + `subscriptionPlanPatchSchema` → `patchPlan` (direct). `code`/`billing_period`/`currency` are immutable (not in the patch schema), shown read-only.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/plans/[id]/edit/_components/EditPlanForm.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/billing/plans/[id]/edit/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-billing/EditPlanForm.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-billing/EditPlanForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const patchPlan = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { billing: { patchPlan } } }),
}));

import { EditPlanForm } from "../../../app/platform/(authed)/billing/plans/[id]/edit/_components/EditPlanForm";

const plan: SubscriptionPlanOut = {
  id: "p1", code: "starter", name: "Starter", description: null, currency: "UGX",
  base_price: "50000", per_user_price: "0", per_member_price: "0",
  billing_period: "monthly", member_limit: null, user_limit: null, features: {},
  trial_period_days: 0, grace_period_days: 30, is_active: true,
  created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
};

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <EditPlanForm plan={plan} />
        <Toaster />
      </TenantCurrencyProvider>
    </QueryClientProvider>,
  );
}

describe("EditPlanForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("submits the changed name + redirects to detail with a toast", async () => {
    patchPlan.mockResolvedValue({ data: { ...plan, name: "Starter+" }, error: undefined });
    renderForm();
    await userEvent.clear(screen.getByLabelText(/^name/i));
    await userEvent.type(screen.getByLabelText(/^name/i), "Starter+");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(patchPlan).toHaveBeenCalledWith("p1", expect.objectContaining({ name: "Starter+" })),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/billing/plans/p1"));
    expect(await screen.findByText(/changes saved/i)).toBeInTheDocument();
  });

  it("surfaces an error and does not redirect", async () => {
    patchPlan.mockResolvedValue({ data: undefined, error: { detail: "Plan not found" } });
    renderForm();
    await userEvent.clear(screen.getByLabelText(/^name/i));
    await userEvent.type(screen.getByLabelText(/^name/i), "Starter+");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/plan not found/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- EditPlanForm` → FAIL.

- [ ] **Step 3: Write `EditPlanForm.tsx`**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/plans/[id]/edit/_components/EditPlanForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Checkbox,
  FormField,
  Input,
  MoneyInput,
  ReadOnlyField,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  subscriptionPlanPatchSchema,
  type SubscriptionPlanOut,
  type SubscriptionPlanPatchInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function EditPlanForm({ plan }: { plan: SubscriptionPlanOut }) {
  const router = useRouter();
  const { resources } = useAuth();
  const form = useForm<SubscriptionPlanPatchInput>({
    resolver: zodResolver(subscriptionPlanPatchSchema),
    defaultValues: {
      name: plan.name,
      description: plan.description ?? "",
      base_price: plan.base_price,
      per_user_price: plan.per_user_price,
      per_member_price: plan.per_member_price,
      trial_period_days: plan.trial_period_days,
      grace_period_days: plan.grace_period_days,
      is_active: plan.is_active,
    },
  });

  const mutation = useTypedMutation<unknown, SubscriptionPlanPatchInput>(
    async (vars) => {
      // resources.billing.patchPlan is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.billing.patchPlan(plan.id, vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.billing.plans(), queryKeys.billing.plan(plan.id)],
      onSuccess: () => {
        toast.success("Changes saved");
        router.push(`/platform/billing/plans/${plan.id}`);
      },
      onError: (error) => {
        toast.error("The plan was not updated", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <form
      noValidate
      className="flex max-w-xl flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <ReadOnlyField label="Code" value={plan.code} />
      <ReadOnlyField label="Currency" value={plan.currency} />
      <ReadOnlyField label="Billing period" value={plan.billing_period} />
      <FormField control={form.control} name="name" label="Name" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="description" label="Description"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="base_price" label="Base price"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} currency={plan.currency} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="per_user_price" label="Per-user price"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} currency={plan.currency} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="per_member_price" label="Per-member price"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} currency={plan.currency} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="trial_period_days" label="Trial days"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} type="number" inputMode="numeric"
            aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""}
            onChange={(e) => field.onChange(e.target.value === "" ? undefined : Number(e.target.value))}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="grace_period_days" label="Grace days"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} type="number" inputMode="numeric"
            aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""}
            onChange={(e) => field.onChange(e.target.value === "" ? undefined : Number(e.target.value))}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="is_active" label="Active"
        render={({ field, id, describedBy }) => (
          <Checkbox id={id} aria-describedby={describedBy}
            checked={field.value ?? false}
            onCheckedChange={(c) => field.onChange(c === true)} />
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Save</Button>
        <Button type="button" variant="ghost" onClick={() => router.push(`/platform/billing/plans/${plan.id}`)}>Cancel</Button>
      </div>
    </form>
  );
}
```

> Confirm `ReadOnlyField` props (`label`, `value`) and `Checkbox` props (`checked`, `onCheckedChange`) in `packages/ui/src/components/{ReadOnlyField,Checkbox}/`. The SP12 EditUserForm used Checkbox for `is_active` — copy its exact binding if this differs.

- [ ] **Step 4: Write the page**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/plans/[id]/edit/page.tsx
import { notFound } from "next/navigation";
import type { SubscriptionPlanOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { EditPlanForm } from "./_components/EditPlanForm";

export const metadata = { title: "Edit Plan" };

export default async function EditPlanPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.write");

  const { data } = await (
    resources.billing.getPlan(id) as Promise<{
      data?: SubscriptionPlanOut;
      error?: unknown;
    }>
  );
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Edit {data.name}</h1>
      <EditPlanForm plan={data} />
    </div>
  );
}
```

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- EditPlanForm` → PASS (2). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/plans/[id]/edit" admin/apps/portal/src/__tests__/platform-billing/EditPlanForm.test.tsx
git commit -m "feat(portal): edit-plan form"
```

---

# PART C — Subscriptions

## Task 8: Subscriptions list (`/platform/billing/subscriptions`)

DataTable over `listSubscriptions`, with client-side status filter (SP13 pattern) and name resolution: the page fetches plans + tenants, builds `plan_id→name` and `tenant_id→name` maps, and passes enriched rows.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/subscriptions/_components/SubscriptionsTable.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/billing/subscriptions/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-billing/SubscriptionsTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-billing/SubscriptionsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/platform/billing/subscriptions",
}));

import {
  SubscriptionsTable,
  type SubscriptionRow,
} from "../../../app/platform/(authed)/billing/subscriptions/_components/SubscriptionsTable";

const row: SubscriptionRow = {
  id: "s1", tenant_id: "t1", tenant_name: "Alpha SACCO", plan_id: "p1",
  plan_name: "Starter", status: "active",
  current_period_start: "2026-06-01", current_period_end: "2026-06-30",
  next_billing_date: "2026-07-01",
};

describe("SubscriptionsTable", () => {
  it("renders the tenant link, plan name and status badge", () => {
    render(<SubscriptionsTable rows={[row]} />);
    expect(screen.getByRole("link", { name: /alpha sacco/i })).toHaveAttribute(
      "href",
      "/platform/billing/subscriptions/s1",
    );
    expect(screen.getByText("Starter")).toBeInTheDocument();
    expect(screen.getByText(/active/i)).toBeInTheDocument();
  });

  it("renders the empty state with no rows", () => {
    render(<SubscriptionsTable rows={[]} />);
    expect(screen.getByText(/no subscriptions/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- SubscriptionsTable` → FAIL.

- [ ] **Step 3: Write `SubscriptionsTable.tsx`**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/subscriptions/_components/SubscriptionsTable.tsx
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

export interface SubscriptionRow {
  id: string;
  tenant_id: string;
  tenant_name: string;
  plan_id: string;
  plan_name: string;
  status: string;
  current_period_start: string;
  current_period_end: string;
  next_billing_date: string | null;
}

const STATUS_FILTER_OPTIONS = [
  "pending",
  "trialing",
  "active",
  "past_due",
  "suspended",
  "cancelled",
] as const;

const columns: DataTableProps<SubscriptionRow>["columns"] = [
  {
    id: "tenant_name",
    accessorKey: "tenant_name",
    header: "Tenant",
    cell: ({ row }) => (
      <Link
        href={`/platform/billing/subscriptions/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.tenant_name}
      </Link>
    ),
  },
  { id: "plan_name", accessorKey: "plan_name", header: "Plan" },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="subscription" status={row.original.status} />,
  },
  {
    id: "current_period_end",
    accessorKey: "current_period_end",
    header: "Period ends",
    cell: ({ row }) => <FormattedDate value={row.original.current_period_end} />,
  },
  {
    id: "next_billing_date",
    accessorKey: "next_billing_date",
    header: "Next billing",
    cell: ({ row }) =>
      row.original.next_billing_date ? (
        <FormattedDate value={row.original.next_billing_date} />
      ) : (
        <span className="text-[var(--text-tertiary)]">—</span>
      ),
  },
];

export function filterSubscriptions(
  rows: SubscriptionRow[],
  status: string | undefined,
): SubscriptionRow[] {
  if (!status) return rows;
  return rows.filter((s) => s.status === status);
}

export function sortSubscriptions(
  rows: SubscriptionRow[],
  column: string | null,
  dir: "asc" | "desc",
): SubscriptionRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof SubscriptionRow];
    const bv = b[column as keyof SubscriptionRow];
    const as = av === null ? "" : String(av);
    const bs = bv === null ? "" : String(bv);
    return as.localeCompare(bs);
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/**
 * Renders the full (unpaginated) subscription list through DataTable. Filter,
 * sort and pagination are client-side (GET /platform/billing/subscriptions has
 * no usable paging; status filter via shallow nuqs state — same as SP13).
 */
export function SubscriptionsTable({ rows }: { rows: SubscriptionRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "tenant_name", direction: "asc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterSubscriptions(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );
  const sorted = useMemo(
    () => sortSubscriptions(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<SubscriptionRow>
      id="billing-subscriptions"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: filtered.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No subscriptions",
        description: "Assign a plan to a tenant to create the first subscription.",
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
                {s.charAt(0).toUpperCase() + s.slice(1).replace("_", " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    />
  );
}
```

- [ ] **Step 4: Write the page (server-side name resolution)**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/subscriptions/page.tsx
import { Card } from "@sacco/ui";
import type { SubscriptionOut, SubscriptionPlanOut, TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { BillingTabs } from "../_components/BillingTabs";
import {
  SubscriptionsTable,
  type SubscriptionRow,
} from "./_components/SubscriptionsTable";

export const metadata = { title: "Subscriptions" };

export default async function BillingSubscriptionsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const [{ data: subs }, { data: plans }, { data: tenants }] = await Promise.all([
    resources.billing.listSubscriptions() as Promise<{ data?: SubscriptionOut[]; error?: unknown }>,
    resources.billing.listPlans() as Promise<{ data?: SubscriptionPlanOut[]; error?: unknown }>,
    resources.tenants.list() as Promise<{ data?: TenantOut[]; error?: unknown }>,
  ]);

  const planName = new Map((plans ?? []).map((p) => [p.id, p.name]));
  const tenantName = new Map((tenants ?? []).map((t) => [t.id, t.name]));

  const rows: SubscriptionRow[] = (subs ?? []).map((s) => ({
    id: s.id,
    tenant_id: s.tenant_id,
    tenant_name: tenantName.get(s.tenant_id) ?? s.tenant_id,
    plan_id: s.plan_id,
    plan_name: planName.get(s.plan_id) ?? s.plan_id,
    status: s.status,
    current_period_start: s.current_period_start,
    current_period_end: s.current_period_end,
    next_billing_date: s.next_billing_date,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Billing</h1>
      <BillingTabs />
      <Card className="p-0">
        <SubscriptionsTable rows={rows} />
      </Card>
    </div>
  );
}
```

> The tenant link points at the subscription detail (`/platform/billing/subscriptions/{id}`), not the tenant — the operator is in the billing context. If a name lookup misses (tenant/plan deleted), the raw id is the fallback label.

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- SubscriptionsTable` → PASS (2). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/subscriptions/_components/SubscriptionsTable.tsx" "admin/apps/portal/app/platform/(authed)/billing/subscriptions/page.tsx" admin/apps/portal/src/__tests__/platform-billing/SubscriptionsTable.test.tsx
git commit -m "feat(portal): billing subscriptions list with name resolution"
```

---

## Task 9: Subscription detail + actions (`/platform/billing/subscriptions/[id]`)

Overview + `<SubscriptionActions>`: **Cancel** with both modes (`at_period_end` direct `<ConfirmDialog>`; `immediate` `<MakerCheckerConfirmDialog>`) and **Reactivate** (direct, suspended only). Both modes collect a reason first.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/subscriptions/[id]/_components/SubscriptionActions.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/billing/subscriptions/[id]/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-billing/SubscriptionActions.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-billing/SubscriptionActions.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { SubscriptionOut } from "@sacco/schemas";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const cancelSubscription = vi.fn();
const reactivateSubscription = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { billing: { cancelSubscription, reactivateSubscription } } }),
}));

import { SubscriptionActions } from "../../../app/platform/(authed)/billing/subscriptions/[id]/_components/SubscriptionActions";

function sub(over: Partial<SubscriptionOut>): SubscriptionOut {
  return {
    id: "s1", tenant_id: "t1", plan_id: "p1", status: "active",
    started_at: "2026-06-01T00:00:00Z", current_period_start: "2026-06-01",
    current_period_end: "2026-06-30", grace_period_ends_at: null,
    cancelled_at: null, cancellation_reason: null, next_billing_date: "2026-07-01",
    metadata_json: {}, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

function renderActions(s: SubscriptionOut) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SubscriptionActions subscription={s} canWrite />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("SubscriptionActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("schedules an at-period-end cancel (direct) with a reason", async () => {
    cancelSubscription.mockResolvedValue({ data: { status: "cancellation_scheduled" }, error: undefined });
    renderActions(sub({ status: "active" }));
    await userEvent.click(screen.getByRole("button", { name: /cancel at period end/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "Customer downgraded plans");
    await userEvent.click(screen.getByRole("button", { name: /schedule cancellation/i }));
    await waitFor(() =>
      expect(cancelSubscription).toHaveBeenCalledWith(
        "s1",
        { reason: "Customer downgraded plans" },
        { mode: "at_period_end" },
      ),
    );
    expect(await screen.findByText(/cancellation scheduled/i)).toBeInTheDocument();
  });

  it("requests an immediate cancel via the maker-checker dialog", async () => {
    cancelSubscription.mockResolvedValue({
      data: { status: "pending_approval", approval_request_id: "ar1" },
      error: undefined,
    });
    renderActions(sub({ status: "active" }));
    await userEvent.click(screen.getByRole("button", { name: /cancel immediately/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "Fraudulent tenant account");
    await userEvent.click(screen.getByRole("button", { name: /^request/i }));
    expect(await screen.findByText(/create an approval request, not execute/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /create approval request/i }));
    await waitFor(() =>
      expect(cancelSubscription).toHaveBeenCalledWith(
        "s1",
        { reason: "Fraudulent tenant account" },
        { mode: "immediate" },
      ),
    );
    expect(await screen.findByText(/approval request created/i)).toBeInTheDocument();
  });

  it("reactivates a suspended subscription (direct)", async () => {
    reactivateSubscription.mockResolvedValue({ data: { id: "s1", status: "active" }, error: undefined });
    renderActions(sub({ status: "suspended" }));
    await userEvent.click(screen.getByRole("button", { name: /reactivate/i }));
    await userEvent.click(screen.getByRole("button", { name: /reactivate subscription/i }));
    await waitFor(() => expect(reactivateSubscription).toHaveBeenCalledWith("s1"));
    expect(await screen.findByText(/subscription reactivated/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- SubscriptionActions` → FAIL.

- [ ] **Step 3: Write `SubscriptionActions.tsx`**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/subscriptions/[id]/_components/SubscriptionActions.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  FormField,
  MakerCheckerConfirmDialog,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  subscriptionCancelSchema,
  type SubscriptionCancelInput,
  type SubscriptionOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

type CancelMode = "at_period_end" | "immediate";

export function SubscriptionActions({
  subscription,
  canWrite,
}: {
  subscription: SubscriptionOut;
  canWrite: boolean;
}) {
  const router = useRouter();
  const { resources } = useAuth();

  // Reason-collection dialog (shared by both cancel modes).
  const [reasonMode, setReasonMode] = useState<CancelMode | null>(null);
  // Maker-checker confirm for the immediate path.
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingReason, setPendingReason] = useState<string | null>(null);
  const [reactivateOpen, setReactivateOpen] = useState(false);

  const form = useForm<SubscriptionCancelInput>({
    resolver: zodResolver(subscriptionCancelSchema),
    defaultValues: { reason: "" },
  });

  const invalidates = [
    queryKeys.billing.subscriptions(),
    queryKeys.billing.subscription(subscription.id),
  ];

  const cancelMutation = useTypedMutation<unknown, { reason: string; mode: CancelMode }>(
    async ({ reason, mode }) => {
      // resources.billing.cancelSubscription is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.billing.cancelSubscription(subscription.id, { reason }, { mode }) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: (_data, vars) => {
        if (vars.mode === "immediate") {
          toast.success("Approval request created", {
            description: "The subscription will be cancelled once another platform user approves it.",
          });
        } else {
          toast.success("Cancellation scheduled", {
            description: "The subscription will end at the close of the current period.",
          });
        }
        setReasonMode(null);
        setConfirmOpen(false);
        setPendingReason(null);
        form.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The cancellation was not processed", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const reactivation = useTypedMutation<unknown, void>(
    async () => {
      const res = await (
        resources.billing.reactivateSubscription(subscription.id) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Subscription reactivated");
        setReactivateOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The subscription was not reactivated", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  if (!canWrite) return null;

  const status = subscription.status;
  const cancellable = status === "active" || status === "trialing" || status === "past_due";
  const reactivatable = status === "suspended";

  return (
    <div className="flex items-center gap-2">
      {cancellable ? (
        <>
          <Button variant="secondary" onClick={() => { form.reset(); setReasonMode("at_period_end"); }}>
            Cancel at period end
          </Button>
          <Button variant="destructive" onClick={() => { form.reset(); setReasonMode("immediate"); }}>
            Cancel immediately
          </Button>
        </>
      ) : null}
      {reactivatable ? (
        <Button variant="primary" onClick={() => setReactivateOpen(true)}>Reactivate</Button>
      ) : null}

      {/* Reason collection — both modes funnel through here first. */}
      <Dialog open={reasonMode !== null} onOpenChange={(o) => { if (!o) setReasonMode(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {reasonMode === "immediate" ? "Cancel immediately" : "Cancel at period end"}
            </DialogTitle>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={form.handleSubmit(({ reason }) => {
              if (reasonMode === "immediate") {
                setPendingReason(reason);
                setReasonMode(null);
                setConfirmOpen(true);
              } else {
                cancelMutation.mutate({ reason, mode: "at_period_end" });
              }
            })}
          >
            <FormField control={form.control} name="reason" label="Reason" required
              helpText="Recorded on the subscription and the audit log. Minimum 10 characters."
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" variant={reasonMode === "immediate" ? "destructive" : "primary"} disabled={cancelMutation.isPending}>
                {reasonMode === "immediate" ? "Request immediate cancellation" : "Schedule cancellation"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setReasonMode(null)}>Back</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Immediate cancel = maker-checker. */}
      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        operationLabel="immediate subscription cancellation"
        busy={cancelMutation.isPending}
        onConfirm={() => {
          if (pendingReason) cancelMutation.mutate({ reason: pendingReason, mode: "immediate" });
        }}
      />

      <ConfirmDialog
        open={reactivateOpen}
        onOpenChange={setReactivateOpen}
        title="Reactivate subscription?"
        description="This restores the subscription to active immediately. No approval is required."
        confirmLabel="Reactivate subscription"
        busy={reactivation.isPending}
        onConfirm={() => reactivation.mutate()}
      />
    </div>
  );
}
```

> Confirm `Dialog`/`DialogContent`/`DialogHeader`/`DialogTitle` are exported from `@sacco/ui` (`grep -n "Dialog" packages/ui/src/index.ts` → it re-exports `./components/Dialog`; check the named exports inside). If the names differ, match them. `MakerCheckerConfirmDialog` `subjectLabel` is optional (omitted here) — confirm in its props; if required, pass the subscription id or tenant name.

- [ ] **Step 4: Write the page**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/subscriptions/[id]/page.tsx
import { notFound } from "next/navigation";
import { Card, FormattedDate, StatusBadge } from "@sacco/ui";
import type { SubscriptionOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { SubscriptionActions } from "./_components/SubscriptionActions";

export const metadata = { title: "Subscription" };

export default async function SubscriptionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const { data } = await (
    resources.billing.getSubscription(id) as Promise<{
      data?: SubscriptionOut;
      error?: unknown;
    }>
  );
  if (!data) notFound();
  const canWrite = userHasPermission(user, "billing.write");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Subscription</h1>
        <SubscriptionActions subscription={data} canWrite={canWrite} />
      </div>
      <Card className="flex flex-col gap-3 p-6">
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Status</span>
          <StatusBadge entity="subscription" status={data.status} />
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Current period</span>
          <span>
            <FormattedDate value={data.current_period_start} /> – <FormattedDate value={data.current_period_end} />
          </span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Next billing</span>
          <span>
            {data.next_billing_date ? <FormattedDate value={data.next_billing_date} /> : "—"}
          </span>
        </div>
        {data.cancellation_reason ? (
          <div className="flex justify-between gap-4">
            <span className="text-[var(--text-secondary)]">Cancellation reason</span>
            <span>{data.cancellation_reason}</span>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- SubscriptionActions` → PASS (3). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/subscriptions/[id]" admin/apps/portal/src/__tests__/platform-billing/SubscriptionActions.test.tsx
git commit -m "feat(portal): subscription detail with cancel (both modes) + reactivate"
```

---

# PART D — Assign plan (tenant context)

## Task 10: Assign-plan screen + TenantActions button

A form on the tenant route picking an active plan + optional start date → `tenants.assignPlan`. Plus an "Assign plan" button on `TenantActions` gated by `billing.write`.

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/assign-plan/_components/AssignPlanForm.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/assign-plan/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-billing/AssignPlanForm.test.tsx`
- Modify: `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantActions.tsx`
- Modify: `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx`
- Modify: `admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx`
- Modify: `admin/apps/portal/src/__tests__/platform-tenants/TenantActions.test.tsx`

- [ ] **Step 1: Write the failing test (AssignPlanForm)**

```tsx
// admin/apps/portal/src/__tests__/platform-billing/AssignPlanForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const assignPlan = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { assignPlan } } }),
}));

import { AssignPlanForm } from "../../../app/platform/(authed)/tenants/[id]/assign-plan/_components/AssignPlanForm";

function plan(over: Partial<SubscriptionPlanOut>): SubscriptionPlanOut {
  return {
    id: "p1", code: "starter", name: "Starter", description: null, currency: "UGX",
    base_price: "50000", per_user_price: "0", per_member_price: "0",
    billing_period: "monthly", member_limit: null, user_limit: null, features: {},
    trial_period_days: 0, grace_period_days: 30, is_active: true,
    created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AssignPlanForm tenantId="t1" plans={[plan({ id: "p1", name: "Starter" }), plan({ id: "p2", name: "Growth" })]} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("AssignPlanForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("requires a plan selection", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: /assign plan/i }));
    expect(await screen.findByText(/select a plan/i)).toBeInTheDocument();
    expect(assignPlan).not.toHaveBeenCalled();
  });

  it("assigns the selected plan and redirects to the new subscription", async () => {
    assignPlan.mockResolvedValue({ data: { id: "s9" }, error: undefined });
    renderForm();
    await userEvent.click(screen.getByLabelText(/plan/i));
    await userEvent.click(await screen.findByRole("option", { name: /growth/i }));
    await userEvent.click(screen.getByRole("button", { name: /assign plan/i }));
    await waitFor(() => expect(assignPlan).toHaveBeenCalledWith("t1", { plan_id: "p2" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/billing/subscriptions/s9"));
    expect(await screen.findByText(/plan assigned/i)).toBeInTheDocument();
  });

  it("surfaces a 409 (tenant already has a live subscription)", async () => {
    assignPlan.mockResolvedValue({ data: undefined, error: { detail: "Tenant already has a live subscription" } });
    renderForm();
    await userEvent.click(screen.getByLabelText(/plan/i));
    await userEvent.click(await screen.findByRole("option", { name: /starter/i }));
    await userEvent.click(screen.getByRole("button", { name: /assign plan/i }));
    expect(await screen.findByText(/already has a live subscription/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- AssignPlanForm` → FAIL.

- [ ] **Step 3: Write `AssignPlanForm.tsx`**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/assign-plan/_components/AssignPlanForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  DateInput,
  FormField,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  assignPlanSchema,
  type AssignPlanInput,
  type SubscriptionPlanOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function AssignPlanForm({
  tenantId,
  plans,
}: {
  tenantId: string;
  plans: SubscriptionPlanOut[];
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const form = useForm<AssignPlanInput>({
    resolver: zodResolver(assignPlanSchema),
    defaultValues: { plan_id: "" },
  });

  const mutation = useTypedMutation<{ id: string }, AssignPlanInput>(
    async (vars) => {
      // resources.tenants.assignPlan is typed Promise<never>; cast to { data, error }.
      const body = vars.start_date ? vars : { plan_id: vars.plan_id };
      const res = await (
        resources.tenants.assignPlan(tenantId, body) as Promise<{
          data?: { id: string };
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as { id: string };
    },
    {
      invalidates: [queryKeys.billing.subscriptions(), queryKeys.tenants.detail(tenantId)],
      onSuccess: (data) => {
        toast.success("Plan assigned");
        router.push(`/platform/billing/subscriptions/${data.id}`);
      },
      onError: (error) => {
        toast.error("The plan was not assigned", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <form
      noValidate
      className="flex max-w-xl flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <FormField control={form.control} name="plan_id" label="Plan" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Select a plan" />
            </SelectTrigger>
            <SelectContent>
              {plans.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="start_date" label="Start date"
        helpText="Optional. Defaults to today if left blank."
        render={({ field, id, describedBy, invalid }) => (
          <DateInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Assign plan</Button>
        <Button type="button" variant="ghost" onClick={() => router.push(`/platform/tenants/${tenantId}`)}>Cancel</Button>
      </div>
    </form>
  );
}
```

> `assignPlanSchema` requires a non-empty uuid `plan_id`; the default `""` fails the uuid check → "select a plan" only after submit. If the uuid error message isn't "select a plan", give `plan_id` a custom message in Task 1's schema (`uuid` is a shared helper — instead add `.min(1, "Select a plan")` is not possible on uuid; simplest: in the FormField the Zod message surfaces — adjust the test's regex to match the actual uuid error, OR wrap: `z.string().uuid("Select a plan")`). **Decision:** in Task 1, define `plan_id: z.string().uuid("Select a plan")` inline instead of the shared `uuid` so the message reads naturally. Update Task 1's `assignPlanSchema` accordingly.

- [ ] **Step 4: Write the page**

```tsx
// admin/apps/portal/app/platform/(authed)/tenants/[id]/assign-plan/page.tsx
import { notFound } from "next/navigation";
import type { SubscriptionPlanOut, TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { AssignPlanForm } from "./_components/AssignPlanForm";

export const metadata = { title: "Assign Plan" };

export default async function AssignPlanPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.write");

  const [{ data: tenant }, { data: plans }] = await Promise.all([
    resources.tenants.get(id) as Promise<{ data?: TenantOut; error?: unknown }>,
    resources.billing.listPlans({ only_active: true }) as Promise<{
      data?: SubscriptionPlanOut[];
      error?: unknown;
    }>,
  ]);
  if (!tenant) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Assign a plan to {tenant.name}</h1>
      <AssignPlanForm tenantId={id} plans={plans ?? []} />
    </div>
  );
}
```

- [ ] **Step 5: Add the button to `TenantActions` + thread `canAssignPlan`**

In `TenantActions.tsx`, add `canAssignPlan: boolean` to the props interface and render the button (after the Impersonate button, before Edit):

```tsx
      {canAssignPlan ? (
        <Button asChild variant="secondary">
          <Link href={`/platform/tenants/${tenant.id}/assign-plan`}>Assign plan</Link>
        </Button>
      ) : null}
```

Update the props destructure to include `canAssignPlan`. In `TenantDetail.tsx`, add `canAssignPlan: boolean` to its props and pass it through to `<TenantActions ... canAssignPlan={canAssignPlan} />`. In `[id]/page.tsx`, pass `canAssignPlan={userHasPermission(user, "billing.write")}` to `<TenantDetail>`.

- [ ] **Step 6: Update the existing TenantActions test**

In `TenantActions.test.tsx`, update `renderActions` to pass `canAssignPlan={caps.canAssignPlan ?? true}` to `<TenantActions>`, add `canAssignPlan?` to the `caps` type, and add one assertion:

```tsx
  it("shows Assign plan when canAssignPlan", () => {
    renderActions(tenant({ status: "active" }), { canAssignPlan: true });
    expect(screen.getByRole("link", { name: /assign plan/i })).toHaveAttribute(
      "href",
      "/platform/tenants/t1/assign-plan",
    );
  });
```

Also update the existing `TenantDetail.test.tsx` `renderDetail` helper to pass `canAssignPlan={false}` so existing tests compile.

- [ ] **Step 7: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- "AssignPlanForm|TenantActions|TenantDetail"` → PASS. `typecheck` + `lint` → clean.

- [ ] **Step 8: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/assign-plan" "admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantActions.tsx" "admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx" "admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx" admin/apps/portal/src/__tests__/platform-billing/AssignPlanForm.test.tsx admin/apps/portal/src/__tests__/platform-tenants/TenantActions.test.tsx admin/apps/portal/src/__tests__/platform-tenants/TenantDetail.test.tsx
git commit -m "feat(portal): assign-plan screen + tenant action button"
```

---

## Task 11: Full-module verification

**Files:** none (verification only, unless a fix is needed).

- [ ] **Step 1: Full verification**

```bash
cd admin
pnpm --filter @sacco/schemas test
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/ui test
pnpm --filter @sacco/portal test
pnpm --filter @sacco/portal typecheck
pnpm --filter @sacco/portal lint
pnpm --filter @sacco/schemas typecheck
pnpm --filter @sacco/api-client lint
```

All green. Portal suite = pre-SP15 count plus BillingTabs / PlansTable / PlanForm / EditPlanForm / SubscriptionsTable / SubscriptionActions / AssignPlanForm + the new TenantActions assertion.

- [ ] **Step 2: Confirm no out-of-scope changes**

Run `git diff main..HEAD --stat` and confirm every path is under `admin/` or `docs/`. No `app/` (backend) changes (contracts B/N).

- [ ] **Step 3: Manual smoke (recommended)**

Backend + portal up. As an admin: Billing → Plans → New plan (create) → detail → Edit (save) → Subscriptions tab (list, status filter) → a tenant detail → Assign plan (pick plan → redirected to subscription detail) → Cancel at period end (reason → scheduled) on another sub → Cancel immediately (reason → maker-checker dialog → approval request) → as a second operator approve → suspended sub → Reactivate. Confirm a `finance` user sees Plans/Subscriptions read-only (no New/Edit/Cancel/Assign buttons); a `support` user is denied billing entirely (403 from `requirePlatformPermission`).

- [ ] **Step 4: Commit (only if a fix was needed)**

```bash
git add -A && git commit -m "fix(portal): SP15 verification fixes"
```

---

## Self-Review

**Spec coverage (`2026-06-13-portal-billing-plans-subscriptions-design.md`):**
plans list (Task 4) ✓; plan detail + AuditBar (Task 5) ✓; new plan (Task 6) ✓; edit plan, immutable code/period/currency (Task 7) ✓; subscriptions list + name resolution (Task 8) ✓; subscription detail + both cancel modes + reactivate (Task 9) ✓; assign-plan as a tenant action (Task 10) ✓; tab-strip sub-nav (Task 3) ✓; permissions `billing.read`/`billing.write` gated before fetch on every page ✓; `<Money>`/`<StatusBadge entity="subscription">`/`<FormattedDate>` used throughout ✓. Foundation gaps the spec implied: Out types + assign schema (Task 1) and the cancel-body api-client fix (Task 2) ✓. **Out of scope honored:** invoices/payments, `features` editor, e2e, i18n, MakerCheckerBanner all absent.

**Placeholder scan:** no TBD/TODO; every code step has full code. Verify-before-wiring flags are explicit (border token name in Task 3; `AuditBar` prop names in Task 5; `ReadOnlyField`/`Checkbox` props in Task 7; `Dialog` export names + `MakerCheckerConfirmDialog.subjectLabel` optionality in Task 9; the `uuid`-message decision in Task 10 Step 3).

**Type consistency:** `SubscriptionPlanOut`/`SubscriptionOut`/`AssignPlanInput` defined in Task 1, consumed in Tasks 4–10. `SubscriptionRow` defined in Task 8, consumed by its page. `cancelSubscription(id, {reason}, {mode})` defined in Task 2, called exactly that way in Task 9's mutation + test. `assignPlan(tenantId, {plan_id, start_date?})` matches the api-client `assignPlan(id, body)` signature. `TenantActions({tenant, canWrite, canImpersonate, canAssignPlan})` in Task 10 matches the TenantDetail + page wiring. `queryKeys.billing.plans()/plan(id)/subscriptions()/subscription(id)` used consistently.
