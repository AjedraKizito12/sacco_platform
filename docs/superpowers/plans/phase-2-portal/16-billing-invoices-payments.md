# Billing — Invoices + Payments + Tenant Self-Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Billing nav group — platform finance/admin Invoices (list/detail/PDF/void/record-payment) and the Payments confirmation queue (reject) — plus the first tenant self-service billing views (`/billing/me/*`), as a pure client of existing endpoints.

**Architecture:** Reuses the SP15 server-page-context + in-memory `<DataTable>` adapter + RHF/Zod form + maker-checker patterns for the platform side, and introduces `getTenantPageContext()` (the tenant analog of `getPlatformPageContext()`) for the `(tenant-authed)` side. Invoice PDFs are delivered through server-side proxy route handlers that attach the bearer (and `X-Tenant-Slug` for the tenant route), because the access token lives in memory and a plain link can't carry auth.

**Tech Stack:** Next.js 15 App Router, React 19, TS strict, `@sacco/ui` (DataTable, FormField, MoneyInput, Select, Textarea, ConfirmDialog, MakerCheckerConfirmDialog, StatusBadge, Money, FormattedDate, AuditBar), `@sacco/schemas` (Zod + new Out types), `@sacco/api-client` (`resources.billing.*`), Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **Zero new backend endpoints** (contract B); everything under `admin/` (contract N). All api-client methods exist (`listInvoices/getInvoice/getInvoicePdf/voidInvoice/recordPayment/listPendingPayments/rejectPayment`, `mySubscription/myInvoices/myInvoice/myInvoicePdf`). Zod schemas exist (`recordPaymentSchema`, `invoiceVoidSchema`, `paymentRejectSchema`, `paymentMethodSchema`). StatusBadge `invoice`+`payment` maps exist. Permission keys `billing.read` (finance) / `billing.write` (admin) exist.
- **The `Promise<never>` cast wart applies to every billing resource call** — cast to `{ data?, error? }` with the standard comment at each call site (see SP15).
- **Permission gating (drives the UI):** invoice/payment reads → `billing.read`; **record payment** is a finance action (`CurrentFinance`) → `billing.read`; **void** + **reject** are admin → `billing.write`. UI gating is UX-only; the API enforces (contract D).
- **Backend facts (authoritative):**
  - `GET /platform/billing/invoices` (finance) unpaginated; `tenant_id`+`status_filter` query params → in-memory adapter.
  - `GET /platform/billing/invoices/{id}` (finance) → `InvoiceDetailOut` (= `InvoiceOut` + `line_items`).
  - `POST .../{id}/void` (admin) → submits `billing.void_invoice` approval; `{status:"pending_approval", approval_request_id}`. Backend voids only when `amount_paid == 0`.
  - `POST .../{id}/payments` (finance) → `Payment(pending)` + approval; body `PaymentRecordIn` incl. `idempotency_key` (≥8 chars).
  - `POST .../payments/{id}/reject` (admin) → `{status:"rejected", payment_id}`; 409 conflict.
  - `GET .../payments/pending-confirmation` (finance) → `PaymentOut[]` (pending).
  - Tenant `/billing/me/*` require tenant auth + `X-Tenant-Slug`; ownership enforced (cross-tenant → 404).
- **Confirm-payment / approval gap (documented):** approving a recorded payment needs the platform Approvals inbox (SP17, not built). SP16 ships **Reject** on the Payments queue; approve is out of band until SP17. `<MakerCheckerBanner>` on records with open approvals also waits on SP17.
- **Out of scope:** confirm-payment approval UI (SP17); MakerCheckerBanner (SP17); e2e + next-intl (portal-wide deferrals — raw English).

## File Structure

**`@sacco/schemas`**
- Modify `packages/schemas/src/billing.ts` — add `InvoiceLineItemOut`, `InvoiceOut`, `InvoiceDetailOut`, `PaymentOut` interfaces + `PAYMENT_METHOD_OPTIONS`.
- Modify `packages/schemas/src/__tests__/billing.test.ts` — assert `PAYMENT_METHOD_OPTIONS`.

**`@sacco/portal` — shared**
- Modify `apps/portal/src/auth/server-page-context.ts` — add `getTenantPageContext()`.
- Modify `apps/portal/app/platform/(authed)/billing/_components/BillingTabs.tsx` — add Invoices + Payments tabs.

**Platform invoices/payments**
- `app/platform/(authed)/billing/invoices/_components/InvoicesTable.tsx`
- `app/platform/(authed)/billing/invoices/page.tsx`
- `app/platform/(authed)/billing/invoices/[id]/page.tsx`
- `app/platform/(authed)/billing/invoices/[id]/_components/InvoiceActions.tsx`
- `app/api/billing/invoices/[id]/pdf/route.ts`
- `app/platform/(authed)/billing/payments/_components/PendingPaymentsTable.tsx`
- `app/platform/(authed)/billing/payments/page.tsx`

**Tenant self-service**
- `app/api/billing/me/invoices/[id]/pdf/route.ts`
- `app/(tenant-authed)/billing/page.tsx` + `_components/TenantInvoicesTable.tsx`
- `app/(tenant-authed)/billing/invoices/[id]/page.tsx`
- Modify `apps/portal/src/components/AppShellSidebar.tsx` — add tenant "Billing" nav item.

**Tests** under `apps/portal/src/__tests__/platform-billing/` and `.../tenant-billing/`.

---

## Task 1: Invoice/Payment Out types + payment-method options (`@sacco/schemas`)

**Files:**
- Modify: `admin/packages/schemas/src/billing.ts`
- Modify: `admin/packages/schemas/src/__tests__/billing.test.ts`

- [ ] **Step 1: Write the failing test (append to billing.test.ts)**

```ts
import { PAYMENT_METHOD_OPTIONS } from "../billing";

describe("PAYMENT_METHOD_OPTIONS", () => {
  it("lists the four backend payment methods with labels", () => {
    expect(PAYMENT_METHOD_OPTIONS.map((o) => o.value)).toEqual([
      "bank_transfer",
      "mobile_money",
      "cash",
      "cheque",
    ]);
    expect(PAYMENT_METHOD_OPTIONS.every((o) => o.label.length > 0)).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/schemas test -- billing`
Expected: FAIL — `PAYMENT_METHOD_OPTIONS` not exported.

- [ ] **Step 3: Add the options + Out types to `billing.ts`**

Append (after the existing `paymentRejectSchema` / type exports):

```ts
export const PAYMENT_METHOD_OPTIONS = [
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "mobile_money", label: "Mobile money" },
  { value: "cash", label: "Cash" },
  { value: "cheque", label: "Cheque" },
] as const;

// ── Read models (hand-written, mirror app/platform_/billing/schemas.py) ──────

export interface InvoiceLineItemOut {
  id: string;
  invoice_id: string;
  description: string;
  quantity: number;
  unit_price: string;
  amount: string;
  line_order: number;
}

export interface InvoiceOut {
  id: string;
  invoice_number: string;
  subscription_id: string;
  tenant_id: string;
  billing_period_start: string;
  billing_period_end: string;
  amount_subtotal: string;
  amount_tax: string;
  amount_total: string;
  amount_paid: string;
  currency: string;
  status: string;
  issued_at: string | null;
  due_at: string;
  paid_at: string | null;
  voided_at: string | null;
  void_reason: string | null;
  pdf_storage_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvoiceDetailOut extends InvoiceOut {
  line_items: InvoiceLineItemOut[];
}

export interface PaymentOut {
  id: string;
  invoice_id: string;
  amount: string;
  currency: string;
  payment_method: string;
  external_reference: string | null;
  notes: string | null;
  recorded_by: string;
  recorded_at: string;
  approval_request_id: string | null;
  status: string;
  confirmed_at: string | null;
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd admin && pnpm --filter @sacco/schemas test -- billing` → PASS. `pnpm --filter @sacco/schemas typecheck` → clean.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/schemas/src/billing.ts admin/packages/schemas/src/__tests__/billing.test.ts
git commit -m "feat(schemas): invoice/payment Out types + payment-method options"
```

---

## Task 2: `getTenantPageContext()` server helper

**Files:**
- Modify: `admin/apps/portal/src/auth/server-page-context.ts`
- Create: `admin/apps/portal/src/__tests__/tenant-billing/tenant-page-context.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// admin/apps/portal/src/__tests__/tenant-billing/tenant-page-context.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest";

const redirect = vi.fn((url: string) => {
  throw new Error(`REDIRECT:${url}`);
});
vi.mock("next/navigation", () => ({ redirect: (u: string) => redirect(u) }));

const getServerAccessToken = vi.fn();
const getServerCurrentUser = vi.fn();
const getServerTenantSlug = vi.fn();
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerCurrentUser: (...a: unknown[]) => getServerCurrentUser(...a),
  getServerTenantSlug: (...a: unknown[]) => getServerTenantSlug(...a),
}));

import { getTenantPageContext } from "../../auth/server-page-context";

describe("getTenantPageContext", () => {
  beforeEach(() => vi.clearAllMocks());

  it("redirects to /login when there is no tenant access token", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    getServerTenantSlug.mockResolvedValue("alpha");
    await expect(getTenantPageContext()).rejects.toThrow("REDIRECT:/login");
  });

  it("redirects to /login when /me fails", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "ta" });
    getServerTenantSlug.mockResolvedValue("alpha");
    getServerCurrentUser.mockResolvedValue(null);
    await expect(getTenantPageContext()).rejects.toThrow("REDIRECT:/login");
  });

  it("returns user, slug and resources when authenticated", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "ta" });
    getServerTenantSlug.mockResolvedValue("alpha");
    getServerCurrentUser.mockResolvedValue({ id: "u1", email: "a@b.c", role: "admin" });
    const ctx = await getTenantPageContext();
    expect(ctx.slug).toBe("alpha");
    expect(ctx.user.id).toBe("u1");
    expect(ctx.resources.billing).toBeDefined();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- tenant-page-context` → FAIL (export missing).

- [ ] **Step 3: Add `getTenantPageContext` to `server-page-context.ts`**

Add the import for `getServerTenantSlug` to the existing `./server-helpers` import, then append:

```ts
export interface TenantPageContext {
  user: CurrentUserShape;
  slug: string;
  resources: Resources;
}

/**
 * Server-component entrypoint for (tenant-authed) pages. Mirrors
 * getPlatformPageContext but uses the tenant refresh cookie + slug so the
 * typed client sends X-Tenant-Slug on /billing/me/* calls. Redirects to
 * /login when unauthenticated.
 */
export async function getTenantPageContext(): Promise<TenantPageContext> {
  const slug = await getServerTenantSlug();
  const { accessToken } = await getServerAccessToken("tenant");
  if (!slug || !accessToken) redirect("/login");
  const user = await getServerCurrentUser("tenant", accessToken);
  if (!user) redirect("/login");

  const store = new InMemoryTokenStore("/auth/refresh");
  store.setAccessToken(accessToken);
  const client = createApiClient({
    baseUrl: API_BASE,
    tokenStore: store,
    tenantContext: new FixedTenantContext(slug),
  });
  return { user, slug, resources: buildResources(client) };
}
```

> `getServerTenantSlug` is exported from `./server-helpers`. `redirect("/login")` (tenant login), not `/platform/login`. The platform helper's narrowing `if (!slug || !accessToken) redirect(...)` then a second `redirect` after the user check is needed because TS doesn't know `redirect` never returns; keep both guards.

- [ ] **Step 4: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- tenant-page-context` → PASS (3). `typecheck` + `lint` → clean.

- [ ] **Step 5: Commit**

```bash
git add admin/apps/portal/src/auth/server-page-context.ts admin/apps/portal/src/__tests__/tenant-billing/tenant-page-context.test.ts
git commit -m "feat(portal): getTenantPageContext server helper"
```

---

## Task 3: Extend `<BillingTabs>` to four tabs

**Files:**
- Modify: `admin/apps/portal/app/platform/(authed)/billing/_components/BillingTabs.tsx`
- Modify: `admin/apps/portal/src/__tests__/platform-billing/BillingTabs.test.tsx`

- [ ] **Step 1: Update the test to expect four tabs**

Replace the body of `BillingTabs.test.tsx` with:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let pathname = "/platform/billing/plans";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

import { BillingTabs } from "../../../app/platform/(authed)/billing/_components/BillingTabs";

describe("BillingTabs", () => {
  it("links to all four billing sections", () => {
    pathname = "/platform/billing/plans";
    render(<BillingTabs />);
    expect(screen.getByRole("link", { name: /plans/i })).toHaveAttribute("href", "/platform/billing/plans");
    expect(screen.getByRole("link", { name: /subscriptions/i })).toHaveAttribute("href", "/platform/billing/subscriptions");
    expect(screen.getByRole("link", { name: /invoices/i })).toHaveAttribute("href", "/platform/billing/invoices");
    expect(screen.getByRole("link", { name: /payments/i })).toHaveAttribute("href", "/platform/billing/payments");
  });

  it("marks the active section with aria-current", () => {
    pathname = "/platform/billing/invoices";
    render(<BillingTabs />);
    expect(screen.getByRole("link", { name: /invoices/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /plans/i })).not.toHaveAttribute("aria-current");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- BillingTabs` → FAIL (no invoices/payments links).

- [ ] **Step 3: Add the two tabs**

In `BillingTabs.tsx`, extend the `TABS` array:

```tsx
const TABS = [
  { href: "/platform/billing/plans", label: "Plans" },
  { href: "/platform/billing/subscriptions", label: "Subscriptions" },
  { href: "/platform/billing/invoices", label: "Invoices" },
  { href: "/platform/billing/payments", label: "Payments" },
] as const;
```

> `startsWith` active-matching already handles `/platform/billing/invoices/{id}` keeping the Invoices tab active. No other change needed.

- [ ] **Step 4: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- BillingTabs` → PASS (2). `typecheck` + `lint` → clean.

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/_components/BillingTabs.tsx" admin/apps/portal/src/__tests__/platform-billing/BillingTabs.test.tsx
git commit -m "feat(portal): add Invoices + Payments billing tabs"
```

---

## Task 4: Invoices list (`/platform/billing/invoices`)

In-memory DataTable adapter with server-side tenant-name resolution (SP15 subscriptions pattern).

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/invoices/_components/InvoicesTable.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/billing/invoices/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-billing/InvoicesTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-billing/InvoicesTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/platform/billing/invoices",
}));

import {
  InvoicesTable,
  type InvoiceRow,
} from "../../../app/platform/(authed)/billing/invoices/_components/InvoicesTable";

const row: InvoiceRow = {
  id: "i1", invoice_number: "INV-2026-000001", tenant_id: "t1",
  tenant_name: "Alpha SACCO", amount_total: "120000", amount_paid: "0",
  currency: "UGX", status: "issued", due_at: "2026-07-01",
};

function renderTable(rows: InvoiceRow[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <InvoicesTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("InvoicesTable", () => {
  it("renders an invoice row with a linked number, tenant and total", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: /INV-2026-000001/i })).toHaveAttribute(
      "href",
      "/platform/billing/invoices/i1",
    );
    expect(screen.getByText(/alpha sacco/i)).toBeInTheDocument();
    expect(screen.getByText(/120,000/)).toBeInTheDocument();
  });

  it("renders the empty state with no rows", () => {
    renderTable([]);
    expect(screen.getByText(/no invoices/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- InvoicesTable` → FAIL.

- [ ] **Step 3: Write `InvoicesTable.tsx`**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/invoices/_components/InvoicesTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Money,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";

export interface InvoiceRow {
  id: string;
  invoice_number: string;
  tenant_id: string;
  tenant_name: string;
  amount_total: string;
  amount_paid: string;
  currency: string;
  status: string;
  due_at: string;
}

const STATUS_FILTER_OPTIONS = [
  "draft",
  "issued",
  "partial",
  "paid",
  "overdue",
  "void",
] as const;

const columns: DataTableProps<InvoiceRow>["columns"] = [
  {
    id: "invoice_number",
    accessorKey: "invoice_number",
    header: "Invoice",
    cell: ({ row }) => (
      <Link
        href={`/platform/billing/invoices/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.invoice_number}
      </Link>
    ),
  },
  { id: "tenant_name", accessorKey: "tenant_name", header: "Tenant" },
  {
    id: "amount_total",
    accessorKey: "amount_total",
    header: "Total",
    cell: ({ row }) => <Money amount={row.original.amount_total} currency={row.original.currency} />,
  },
  {
    id: "amount_paid",
    accessorKey: "amount_paid",
    header: "Paid",
    cell: ({ row }) => <Money amount={row.original.amount_paid} currency={row.original.currency} />,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="invoice" status={row.original.status} />,
  },
  {
    id: "due_at",
    accessorKey: "due_at",
    header: "Due",
    cell: ({ row }) => <FormattedDate value={row.original.due_at} />,
  },
];

export function filterInvoices(rows: InvoiceRow[], status: string | undefined): InvoiceRow[] {
  if (!status) return rows;
  return rows.filter((r) => r.status === status);
}

export function sortInvoices(
  rows: InvoiceRow[],
  column: string | null,
  dir: "asc" | "desc",
): InvoiceRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof InvoiceRow];
    const bv = b[column as keyof InvoiceRow];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/** Full (unpaginated) invoice list through DataTable; client-side filter/sort/paginate. */
export function InvoicesTable({ rows }: { rows: InvoiceRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "invoice_number", direction: "desc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterInvoices(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );
  const sorted = useMemo(
    () => sortInvoices(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<InvoiceRow>
      id="billing-invoices"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: filtered.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No invoices",
        description: "Invoices are generated automatically from active subscriptions.",
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
              <SelectItem key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    />
  );
}
```

- [ ] **Step 4: Write the page**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/invoices/page.tsx
import { Card } from "@sacco/ui";
import type { InvoiceOut, TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { BillingTabs } from "../_components/BillingTabs";
import { InvoicesTable, type InvoiceRow } from "./_components/InvoicesTable";

export const metadata = { title: "Invoices" };

export default async function BillingInvoicesPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const [{ data: invoices }, { data: tenants }] = await Promise.all([
    resources.billing.listInvoices() as Promise<{ data?: InvoiceOut[]; error?: unknown }>,
    resources.tenants.list() as Promise<{ data?: TenantOut[]; error?: unknown }>,
  ]);

  const tenantName = new Map((tenants ?? []).map((t) => [t.id, t.name]));
  const rows: InvoiceRow[] = (invoices ?? []).map((inv) => ({
    id: inv.id,
    invoice_number: inv.invoice_number,
    tenant_id: inv.tenant_id,
    tenant_name: tenantName.get(inv.tenant_id) ?? inv.tenant_id,
    amount_total: inv.amount_total,
    amount_paid: inv.amount_paid,
    currency: inv.currency,
    status: inv.status,
    due_at: inv.due_at,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Billing</h1>
      <BillingTabs />
      <Card className="p-0">
        <InvoicesTable rows={rows} />
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- InvoicesTable` → PASS (2). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/invoices/_components/InvoicesTable.tsx" "admin/apps/portal/app/platform/(authed)/billing/invoices/page.tsx" admin/apps/portal/src/__tests__/platform-billing/InvoicesTable.test.tsx
git commit -m "feat(portal): billing invoices list"
```

---

## Task 5: Invoice detail (read-only overview + line items + PDF link)

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/invoices/[id]/page.tsx`

This task is self-contained: a read-only detail page with an inline "Download PDF"
link. Task 6 adds `<InvoiceActions>` (record-payment/void) to the header.

- [ ] **Step 1: Write the page (no test — server component rendering primitives; InvoiceActions tested in Task 6)**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/invoices/[id]/page.tsx
import { notFound } from "next/navigation";
import { AuditBar, Button, Card, FormattedDate, Money, StatusBadge } from "@sacco/ui";
import type { InvoiceDetailOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";

export const metadata = { title: "Invoice" };

export default async function InvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const { data } = await (
    resources.billing.getInvoice(id) as Promise<{ data?: InvoiceDetailOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">{data.invoice_number}</h1>
        <Button asChild variant="secondary">
          <a href={`/api/billing/invoices/${data.id}/pdf`} target="_blank" rel="noreferrer">
            Download PDF
          </a>
        </Button>
      </div>
      <Card className="flex flex-col gap-3 p-6">
        <Row label="Status" value={<StatusBadge entity="invoice" status={data.status} />} />
        <Row label="Period" value={<><FormattedDate value={data.billing_period_start} /> – <FormattedDate value={data.billing_period_end} /></>} />
        <Row label="Due" value={<FormattedDate value={data.due_at} />} />
        <Row label="Subtotal" value={<Money amount={data.amount_subtotal} currency={data.currency} />} />
        <Row label="Tax" value={<Money amount={data.amount_tax} currency={data.currency} />} />
        <Row label="Total" value={<Money amount={data.amount_total} currency={data.currency} />} />
        <Row label="Paid" value={<Money amount={data.amount_paid} currency={data.currency} />} />
        {data.void_reason ? <Row label="Void reason" value={data.void_reason} /> : null}
      </Card>

      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Line items</h2>
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          <div className="flex justify-between py-2 text-[13px] text-[var(--text-tertiary)]">
            <span>Description</span>
            <span>Amount</span>
          </div>
          {data.line_items.map((li) => (
            <div key={li.id} className="flex justify-between py-2">
              <span className="text-[var(--text-primary)]">
                {li.description}
                {li.quantity > 1 ? ` × ${li.quantity}` : ""}
              </span>
              <Money amount={li.amount} currency={data.currency} />
            </div>
          ))}
        </div>
      </Card>

      <AuditBar entityType="invoice" entityId={data.id} />
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

> Line items render as div rows (not a `<table>`) — they are a fixed nested collection on a detail page, not a list screen, so DataTable (contract T) does not apply, and a hand-rolled `<table>` is avoided. Confirm `--border-subtle` exists (used by BillingTabs already). If `React.ReactNode` trips eslint, import `type { ReactNode } from "react"` and use `ReactNode` (SP15 plan-detail precedent).

- [ ] **Step 2: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal typecheck` → clean. `pnpm --filter @sacco/portal lint` → clean.

- [ ] **Step 3: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/invoices/[id]/page.tsx"
git commit -m "feat(portal): billing invoice detail (read-only)"
```

---

## Task 6: Invoice actions — record payment + void (maker-checker)

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/invoices/[id]/_components/InvoiceActions.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-billing/InvoiceActions.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-billing/InvoiceActions.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";
import type { InvoiceDetailOut } from "@sacco/schemas";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const recordPayment = vi.fn();
const voidInvoice = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { billing: { recordPayment, voidInvoice } } }),
}));

import { InvoiceActions } from "../../../app/platform/(authed)/billing/invoices/[id]/_components/InvoiceActions";

function invoice(over: Partial<InvoiceDetailOut>): InvoiceDetailOut {
  return {
    id: "i1", invoice_number: "INV-2026-000001", subscription_id: "s1", tenant_id: "t1",
    billing_period_start: "2026-06-01", billing_period_end: "2026-06-30",
    amount_subtotal: "120000", amount_tax: "0", amount_total: "120000", amount_paid: "0",
    currency: "UGX", status: "issued", issued_at: "2026-06-01T00:00:00Z", due_at: "2026-07-01",
    paid_at: null, voided_at: null, void_reason: null, pdf_storage_key: null,
    created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z", line_items: [],
    ...over,
  };
}

function renderActions(inv: InvoiceDetailOut, caps?: { canRecord?: boolean; canVoid?: boolean }) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <InvoiceActions invoice={inv} canRecord={caps?.canRecord ?? true} canVoid={caps?.canVoid ?? true} />
        <Toaster />
      </TenantCurrencyProvider>
    </QueryClientProvider>,
  );
}

describe("InvoiceActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("records a payment via the maker-checker dialog", async () => {
    recordPayment.mockResolvedValue({ data: { status: "pending_approval", payment_id: "pay1" }, error: undefined });
    renderActions(invoice({ status: "issued" }));
    await userEvent.click(screen.getByRole("button", { name: /record payment/i }));
    await userEvent.type(screen.getByLabelText(/amount/i), "120000");
    await userEvent.click(screen.getByRole("combobox", { name: /method/i }));
    await userEvent.click(await screen.findByRole("option", { name: /bank transfer/i }));
    await userEvent.click(screen.getByRole("button", { name: /^record$/i }));
    expect(await screen.findByText(/create an approval request, not execute/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /create approval request/i }));
    await waitFor(() => expect(recordPayment).toHaveBeenCalledTimes(1));
    const [invId, body] = recordPayment.mock.calls[0] as [string, Record<string, unknown>];
    expect(invId).toBe("i1");
    expect(body).toMatchObject({ amount: "120000", payment_method: "bank_transfer" });
    expect(typeof body["idempotency_key"]).toBe("string");
    expect((body["idempotency_key"] as string).length).toBeGreaterThanOrEqual(8);
    expect(await screen.findByText(/payment recorded/i)).toBeInTheDocument();
  });

  it("requests a void via the maker-checker dialog", async () => {
    voidInvoice.mockResolvedValue({ data: { status: "pending_approval" }, error: undefined });
    renderActions(invoice({ status: "issued", amount_paid: "0" }));
    await userEvent.click(screen.getByRole("button", { name: /void/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "Issued against the wrong tenant");
    await userEvent.click(screen.getByRole("button", { name: /^request void$/i }));
    await userEvent.click(await screen.findByRole("button", { name: /create approval request/i }));
    await waitFor(() => expect(voidInvoice).toHaveBeenCalledWith("i1", { reason: "Issued against the wrong tenant" }));
    expect(await screen.findByText(/void requested/i)).toBeInTheDocument();
  });

  it("hides Void when the invoice has payments or lacks permission", () => {
    const { rerender } = renderActions(invoice({ status: "partial", amount_paid: "5000" }));
    expect(screen.queryByRole("button", { name: /void/i })).toBeNull();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
          <InvoiceActions invoice={invoice({ status: "issued", amount_paid: "0" })} canRecord canVoid={false} />
        </TenantCurrencyProvider>
      </QueryClientProvider>,
    );
    expect(screen.queryByRole("button", { name: /void/i })).toBeNull();
  });

  it("links Download PDF to the proxy route", () => {
    renderActions(invoice({}));
    expect(screen.getByRole("link", { name: /download pdf/i })).toHaveAttribute(
      "href",
      "/api/billing/invoices/i1/pdf",
    );
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- InvoiceActions` → FAIL.

- [ ] **Step 3: Write `InvoiceActions.tsx`**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/invoices/[id]/_components/InvoiceActions.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  FormField,
  Input,
  MakerCheckerConfirmDialog,
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
import {
  PAYMENT_METHOD_OPTIONS,
  invoiceVoidSchema,
  recordPaymentSchema,
  type InvoiceDetailOut,
  type InvoiceVoidInput,
  type RecordPaymentInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function InvoiceActions({
  invoice,
  canRecord,
  canVoid,
}: {
  invoice: InvoiceDetailOut;
  canRecord: boolean;
  canVoid: boolean;
}) {
  const router = useRouter();
  const { resources } = useAuth();

  const [payOpen, setPayOpen] = useState(false);
  const [payConfirm, setPayConfirm] = useState(false);
  const [pendingPayment, setPendingPayment] = useState<RecordPaymentInput | null>(null);
  const [voidOpen, setVoidOpen] = useState(false);
  const [voidConfirm, setVoidConfirm] = useState(false);
  const [pendingVoid, setPendingVoid] = useState<InvoiceVoidInput | null>(null);

  const invalidates = [queryKeys.billing.invoices(), queryKeys.billing.invoice(invoice.id)];

  // Fresh idempotency key per form instance; persists across confirm retries.
  const [idemKey] = useState(() => crypto.randomUUID());
  const payForm = useForm<RecordPaymentInput>({
    resolver: zodResolver(recordPaymentSchema),
    defaultValues: {
      amount: "",
      currency: invoice.currency,
      payment_method: "bank_transfer",
      external_reference: "",
      notes: "",
      idempotency_key: idemKey,
    },
  });

  const voidForm = useForm<InvoiceVoidInput>({
    resolver: zodResolver(invoiceVoidSchema),
    defaultValues: { reason: "" },
  });

  const payMutation = useTypedMutation<unknown, RecordPaymentInput>(
    async (vars) => {
      // resources.billing.recordPayment is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.billing.recordPayment(invoice.id, vars as Record<string, unknown>) as Promise<{
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
        toast.success("Payment recorded", {
          description: "It will apply to the invoice once another platform user approves it.",
        });
        setPayConfirm(false);
        setPayOpen(false);
        setPendingPayment(null);
        payForm.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The payment was not recorded", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const voidMutation = useTypedMutation<unknown, InvoiceVoidInput>(
    async (vars) => {
      const res = await (
        resources.billing.voidInvoice(invoice.id, vars as Record<string, unknown>) as Promise<{
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
        toast.success("Void requested", {
          description: "The invoice will be voided once another platform user approves it.",
        });
        setVoidConfirm(false);
        setVoidOpen(false);
        setPendingVoid(null);
        voidForm.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The void was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const payable =
    invoice.status === "issued" || invoice.status === "partial" || invoice.status === "overdue";
  const voidable =
    Number(invoice.amount_paid) === 0 &&
    invoice.status !== "void" &&
    invoice.status !== "paid";

  return (
    <div className="flex items-center gap-2">
      <Button asChild variant="secondary">
        <a href={`/api/billing/invoices/${invoice.id}/pdf`} target="_blank" rel="noreferrer">
          Download PDF
        </a>
      </Button>

      {canRecord && payable ? (
        <Button variant="primary" onClick={() => { payForm.reset({ ...payForm.getValues() }); setPayOpen(true); }}>
          Record payment
        </Button>
      ) : null}
      {canVoid && voidable ? (
        <Button variant="destructive" onClick={() => { voidForm.reset(); setVoidOpen(true); }}>
          Void
        </Button>
      ) : null}

      {/* Record-payment form dialog */}
      <Dialog open={payOpen} onOpenChange={(o) => { if (!o) setPayOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Record payment</DialogTitle>
            <DialogDescription>
              Capture an offline payment against {invoice.invoice_number}. This creates an approval
              request; the payment applies once another platform user approves it.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={payForm.handleSubmit((values) => {
              setPendingPayment(values);
              setPayOpen(false);
              setPayConfirm(true);
            })}
          >
            <FormField control={payForm.control} name="amount" label="Amount" required
              render={({ field, id, describedBy, invalid }) => (
                <MoneyInput id={id} currency={invoice.currency}
                  aria-describedby={describedBy} aria-invalid={invalid}
                  value={field.value ?? ""} onValueChange={field.onChange}
                  onBlur={field.onBlur} name={field.name} ref={field.ref} />
              )} />
            <FormField control={payForm.control} name="payment_method" label="Method" required
              render={({ field, id, describedBy, invalid }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PAYMENT_METHOD_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )} />
            <FormField control={payForm.control} name="external_reference" label="Reference"
              render={({ field, id, describedBy, invalid }) => (
                <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <FormField control={payForm.control} name="notes" label="Notes"
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit">Record</Button>
              <Button type="button" variant="ghost" onClick={() => setPayOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <MakerCheckerConfirmDialog
        open={payConfirm}
        onOpenChange={(o) => { setPayConfirm(o); if (!o) setPendingPayment(null); }}
        operationLabel="payment recording"
        subjectLabel={invoice.invoice_number}
        busy={payMutation.isPending}
        onConfirm={() => { if (pendingPayment) payMutation.mutate(pendingPayment); }}
      />

      {/* Void form dialog */}
      <Dialog open={voidOpen} onOpenChange={(o) => { if (!o) setVoidOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Void {invoice.invoice_number}</DialogTitle>
            <DialogDescription>
              Voiding cancels this invoice. This creates an approval request; the invoice is voided
              once another platform user approves it.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={voidForm.handleSubmit((values) => {
              setPendingVoid(values);
              setVoidOpen(false);
              setVoidConfirm(true);
            })}
          >
            <FormField control={voidForm.control} name="reason" label="Reason" required
              helpText="Recorded on the approval request and the audit log. Minimum 10 characters."
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" variant="destructive">Request void</Button>
              <Button type="button" variant="ghost" onClick={() => setVoidOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <MakerCheckerConfirmDialog
        open={voidConfirm}
        onOpenChange={(o) => { setVoidConfirm(o); if (!o) setPendingVoid(null); }}
        operationLabel="invoice void"
        subjectLabel={invoice.invoice_number}
        busy={voidMutation.isPending}
        onConfirm={() => { if (pendingVoid) voidMutation.mutate(pendingVoid); }}
      />
    </div>
  );
}
```

> Confirm `DialogDescription` is exported from `@sacco/ui` (the SP15 Task 9 a11y fix added/used it; grep `packages/ui/src/components/Dialog`). `recordPaymentSchema` includes `idempotency_key` — it is carried in `defaultValues` (no rendered field) so it validates and submits. The `Select` for method is found by accessible name "Method"; the amount MoneyInput by "Amount". If `crypto.randomUUID` is unavailable in the jsdom test env, the test still passes because vitest's jsdom polyfills it (Node ≥ 18 exposes `crypto.randomUUID` globally); if not, the implementer should add `import { randomUUID } from "crypto"` fallback — report if needed.

- [ ] **Step 4: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- InvoiceActions` → PASS (4). `typecheck` + `lint` → clean.

- [ ] **Step 5: Wire `<InvoiceActions>` into the invoice detail page**

In `app/platform/(authed)/billing/invoices/[id]/page.tsx` (from Task 5): add the imports `import { userHasPermission } from "@/auth/permissions";` and `import { InvoiceActions } from "./_components/InvoiceActions";`, drop the now-unused `Button` import, compute `const canRecord = userHasPermission(user, "billing.read");` and `const canVoid = userHasPermission(user, "billing.write");` after the `notFound()` guard, and replace the inline Download-PDF `<Button asChild>…</Button>` in the header with:

```tsx
        <InvoiceActions invoice={data} canRecord={canRecord} canVoid={canVoid} />
```

(`InvoiceActions` renders its own Download PDF link, so the inline one is removed.) Run `cd admin && pnpm --filter @sacco/portal typecheck` → clean.

- [ ] **Step 6: Commit (actions + detail-page wiring together)**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/invoices/[id]" admin/apps/portal/src/__tests__/platform-billing/InvoiceActions.test.tsx
git commit -m "feat(portal): invoice record-payment + void actions"
```

---

## Task 7: Platform invoice PDF proxy route

**Files:**
- Create: `admin/apps/portal/app/api/billing/invoices/[id]/pdf/route.ts`
- Create: `admin/apps/portal/src/__tests__/platform-billing/invoice-pdf-route.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// admin/apps/portal/src/__tests__/platform-billing/invoice-pdf-route.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getServerAccessToken = vi.fn();
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
}));

const fetchMock = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function ctx(id: string) {
  return { params: Promise.resolve({ id }) };
}

describe("GET /api/billing/invoices/[id]/pdf", () => {
  it("401s without a platform session", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    const { GET } = await import("../../../app/api/billing/invoices/[id]/pdf/route");
    const res = await GET(new Request("http://localhost/api/billing/invoices/i1/pdf"), ctx("i1"));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("proxies the PDF with the platform bearer and application/pdf", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "plat-access" });
    fetchMock.mockResolvedValue({
      ok: true, status: 200,
      arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer, // %PDF
    });
    const { GET } = await import("../../../app/api/billing/invoices/[id]/pdf/route");
    const res = await GET(new Request("http://localhost/api/billing/invoices/i1/pdf"), ctx("i1"));
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("application/pdf");
    const [url, init] = fetchMock.mock.calls[0] as [string, { headers?: Record<string, string> }];
    expect(String(url)).toContain("/platform/billing/invoices/i1.pdf");
    expect(init.headers?.["Authorization"]).toBe("Bearer plat-access");
  });

  it("propagates a non-ok status", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "plat-access" });
    fetchMock.mockResolvedValue({ ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) });
    const { GET } = await import("../../../app/api/billing/invoices/[id]/pdf/route");
    const res = await GET(new Request("http://localhost/api/billing/invoices/x/pdf"), ctx("x"));
    expect(res.status).toBe(404);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- invoice-pdf-route` → FAIL.

- [ ] **Step 3: Write the route**

```ts
// admin/apps/portal/app/api/billing/invoices/[id]/pdf/route.ts
import { NextResponse } from "next/server";
import { getServerAccessToken } from "@/auth/server-helpers";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const { accessToken } = await getServerAccessToken("platform");
  if (!accessToken) {
    return NextResponse.json({ error: "No platform session" }, { status: 401 });
  }

  const r = await fetch(`${API_BASE}/platform/billing/invoices/${id}.pdf`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Failed to load invoice PDF" }, { status: r.status });
  }
  const body = await r.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `inline; filename="invoice-${id}.pdf"`,
    },
  });
}
```

- [ ] **Step 4: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- invoice-pdf-route` → PASS (3). `typecheck` + `lint` → clean.

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/api/billing/invoices" admin/apps/portal/src/__tests__/platform-billing/invoice-pdf-route.test.ts
git commit -m "feat(portal): platform invoice PDF proxy route"
```

---

## Task 8: Payments confirmation queue (`/platform/billing/payments`) + reject

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/billing/payments/_components/PendingPaymentsTable.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/billing/payments/page.tsx`
- Create: `admin/apps/portal/src/__tests__/platform-billing/PendingPaymentsTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/platform-billing/PendingPaymentsTable.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/platform/billing/payments",
}));

const rejectPayment = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { billing: { rejectPayment } } }),
}));

import {
  PendingPaymentsTable,
  type PendingPaymentRow,
} from "../../../app/platform/(authed)/billing/payments/_components/PendingPaymentsTable";

const row: PendingPaymentRow = {
  id: "pay1", invoice_id: "i1", invoice_number: "INV-2026-000001",
  amount: "120000", currency: "UGX", payment_method: "bank_transfer",
  recorded_at: "2026-06-10T00:00:00Z", status: "pending",
};

function renderTable(rows: PendingPaymentRow[], canReject = true) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <PendingPaymentsTable rows={rows} canReject={canReject} />
        <Toaster />
      </TenantCurrencyProvider>
    </QueryClientProvider>,
  );
}

describe("PendingPaymentsTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("renders a pending payment with a linked invoice + amount", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: /INV-2026-000001/i })).toHaveAttribute(
      "href",
      "/platform/billing/invoices/i1",
    );
    expect(screen.getByText(/120,000/)).toBeInTheDocument();
  });

  it("rejects a payment with a reason via the confirm dialog", async () => {
    rejectPayment.mockResolvedValue({ data: { status: "rejected" }, error: undefined });
    renderTable([row]);
    await userEvent.click(screen.getByRole("button", { name: /reject/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "Bank reference does not match");
    await userEvent.click(screen.getByRole("button", { name: /^reject payment$/i }));
    await waitFor(() =>
      expect(rejectPayment).toHaveBeenCalledWith("pay1", { reason: "Bank reference does not match" }),
    );
    expect(await screen.findByText(/payment rejected/i)).toBeInTheDocument();
  });

  it("hides Reject without permission", () => {
    renderTable([row], false);
    expect(screen.queryByRole("button", { name: /reject/i })).toBeNull();
  });

  it("renders the empty state with no rows", () => {
    renderTable([]);
    expect(screen.getByText(/no payments awaiting/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- PendingPaymentsTable` → FAIL.

- [ ] **Step 3: Write `PendingPaymentsTable.tsx`**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/payments/_components/PendingPaymentsTable.tsx
"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  DataTable,
  type DataTableProps,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  FormField,
  FormattedDate,
  Money,
  StatusBadge,
  Textarea,
  toast,
  useTableUrlState,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import { paymentRejectSchema, type PaymentRejectInput } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface PendingPaymentRow {
  id: string;
  invoice_id: string;
  invoice_number: string;
  amount: string;
  currency: string;
  payment_method: string;
  recorded_at: string;
  status: string;
}

export function PendingPaymentsTable({
  rows,
  canReject,
}: {
  rows: PendingPaymentRow[];
  canReject: boolean;
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [rejecting, setRejecting] = useState<PendingPaymentRow | null>(null);

  const form = useForm<PaymentRejectInput>({
    resolver: zodResolver(paymentRejectSchema),
    defaultValues: { reason: "" },
  });

  const mutation = useTypedMutation<unknown, { id: string; reason: string }>(
    async ({ id, reason }) => {
      // resources.billing.rejectPayment is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.billing.rejectPayment(id, { reason }) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.billing.pendingPayments()],
      onSuccess: () => {
        toast.success("Payment rejected");
        setRejecting(null);
        form.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The payment was not rejected", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const columns: DataTableProps<PendingPaymentRow>["columns"] = useMemo(
    () => [
      {
        id: "invoice_number",
        accessorKey: "invoice_number",
        header: "Invoice",
        cell: ({ row }) => (
          <Link
            href={`/platform/billing/invoices/${row.original.invoice_id}`}
            className="font-medium text-[var(--text-link)] hover:underline"
          >
            {row.original.invoice_number}
          </Link>
        ),
      },
      {
        id: "amount",
        accessorKey: "amount",
        header: "Amount",
        cell: ({ row }) => <Money amount={row.original.amount} currency={row.original.currency} />,
      },
      { id: "payment_method", accessorKey: "payment_method", header: "Method" },
      {
        id: "recorded_at",
        accessorKey: "recorded_at",
        header: "Recorded",
        cell: ({ row }) => <FormattedDate value={row.original.recorded_at} />,
      },
      {
        id: "status",
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <StatusBadge entity="payment" status={row.original.status} />,
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) =>
          canReject ? (
            <Button variant="destructive" size="sm" onClick={() => { form.reset(); setRejecting(row.original); }}>
              Reject
            </Button>
          ) : null,
      },
    ],
    [canReject, form],
  );

  const urlState = useTableUrlState({
    defaultSort: { column: "recorded_at", direction: "desc" },
    defaultPageSize: 25,
  });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <>
      <DataTable<PendingPaymentRow>
        id="billing-pending-payments"
        columns={columns}
        data={pageRows}
        urlState={urlState}
        state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
        emptyState={{
          title: "No payments awaiting confirmation",
          description: "Recorded payments appear here until a second platform user approves or rejects them.",
        }}
      />

      <Dialog open={rejecting !== null} onOpenChange={(o) => { if (!o) setRejecting(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject payment</DialogTitle>
            <DialogDescription>
              {rejecting ? `Reject the payment recorded against ${rejecting.invoice_number}.` : ""}
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={form.handleSubmit(({ reason }) => {
              if (rejecting) mutation.mutate({ id: rejecting.id, reason });
            })}
          >
            <FormField control={form.control} name="reason" label="Reason" required
              helpText="Recorded on the audit log. Minimum 10 characters."
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" variant="destructive" disabled={mutation.isPending}>Reject payment</Button>
              <Button type="button" variant="ghost" onClick={() => setRejecting(null)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
```

> Reject uses a reason `<Dialog>` then a direct `rejectPayment` (reject is a direct admin action, not itself maker-checker — it terminates the maker's pending payment). `<Button size="sm">` for the row action (sizes are sm/md/lg). The queue is unpaginated server-side; client paginate only.

- [ ] **Step 4: Write the page**

```tsx
// admin/apps/portal/app/platform/(authed)/billing/payments/page.tsx
import { Card } from "@sacco/ui";
import type { InvoiceOut, PaymentOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { BillingTabs } from "../_components/BillingTabs";
import {
  PendingPaymentsTable,
  type PendingPaymentRow,
} from "./_components/PendingPaymentsTable";

export const metadata = { title: "Payments" };

export default async function BillingPaymentsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const [{ data: payments }, { data: invoices }] = await Promise.all([
    resources.billing.listPendingPayments() as Promise<{ data?: PaymentOut[]; error?: unknown }>,
    resources.billing.listInvoices() as Promise<{ data?: InvoiceOut[]; error?: unknown }>,
  ]);

  const invoiceNumber = new Map((invoices ?? []).map((inv) => [inv.id, inv.invoice_number]));
  const rows: PendingPaymentRow[] = (payments ?? []).map((p) => ({
    id: p.id,
    invoice_id: p.invoice_id,
    invoice_number: invoiceNumber.get(p.invoice_id) ?? p.invoice_id,
    amount: p.amount,
    currency: p.currency,
    payment_method: p.payment_method,
    recorded_at: p.recorded_at,
    status: p.status,
  }));

  const canReject = userHasPermission(user, "billing.write");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Billing</h1>
      <BillingTabs />
      <p className="text-[13px] text-[var(--text-secondary)]">
        Approving a payment is done from the Approvals inbox. Rejecting is available here.
      </p>
      <Card className="p-0">
        <PendingPaymentsTable rows={rows} canReject={canReject} />
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- PendingPaymentsTable` → PASS (4). `typecheck` + `lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/billing/payments" admin/apps/portal/src/__tests__/platform-billing/PendingPaymentsTable.test.tsx
git commit -m "feat(portal): payments confirmation queue with reject"
```

---

## Task 9: Tenant invoice PDF proxy route

**Files:**
- Create: `admin/apps/portal/app/api/billing/me/invoices/[id]/pdf/route.ts`
- Create: `admin/apps/portal/src/__tests__/tenant-billing/tenant-invoice-pdf-route.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// admin/apps/portal/src/__tests__/tenant-billing/tenant-invoice-pdf-route.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getServerAccessToken = vi.fn();
const getServerTenantSlug = vi.fn();
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerTenantSlug: (...a: unknown[]) => getServerTenantSlug(...a),
}));

const fetchMock = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function ctx(id: string) {
  return { params: Promise.resolve({ id }) };
}

describe("GET /api/billing/me/invoices/[id]/pdf", () => {
  it("401s without a tenant session", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    getServerTenantSlug.mockResolvedValue("alpha");
    const { GET } = await import("../../../app/api/billing/me/invoices/[id]/pdf/route");
    const res = await GET(new Request("http://localhost/api/billing/me/invoices/i1/pdf"), ctx("i1"));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("proxies with the tenant bearer + X-Tenant-Slug", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "tenant-access" });
    getServerTenantSlug.mockResolvedValue("alpha");
    fetchMock.mockResolvedValue({
      ok: true, status: 200, arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer,
    });
    const { GET } = await import("../../../app/api/billing/me/invoices/[id]/pdf/route");
    const res = await GET(new Request("http://localhost/api/billing/me/invoices/i1/pdf"), ctx("i1"));
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("application/pdf");
    const [url, init] = fetchMock.mock.calls[0] as [string, { headers?: Record<string, string> }];
    expect(String(url)).toContain("/billing/me/invoices/i1.pdf");
    expect(init.headers?.["Authorization"]).toBe("Bearer tenant-access");
    expect(init.headers?.["X-Tenant-Slug"]).toBe("alpha");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- tenant-invoice-pdf-route` → FAIL.

- [ ] **Step 3: Write the route**

```ts
// admin/apps/portal/app/api/billing/me/invoices/[id]/pdf/route.ts
import { NextResponse } from "next/server";
import { getServerAccessToken, getServerTenantSlug } from "@/auth/server-helpers";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const slug = await getServerTenantSlug();
  const { accessToken } = await getServerAccessToken("tenant");
  if (!slug || !accessToken) {
    return NextResponse.json({ error: "No tenant session" }, { status: 401 });
  }

  const r = await fetch(`${API_BASE}/billing/me/invoices/${id}.pdf`, {
    headers: { Authorization: `Bearer ${accessToken}`, "X-Tenant-Slug": slug },
    cache: "no-store",
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Failed to load invoice PDF" }, { status: r.status });
  }
  const body = await r.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `inline; filename="invoice-${id}.pdf"`,
    },
  });
}
```

- [ ] **Step 4: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- tenant-invoice-pdf-route` → PASS (2). `typecheck` + `lint` → clean.

- [ ] **Step 5: Commit**

```bash
git add "admin/apps/portal/app/api/billing/me" admin/apps/portal/src/__tests__/tenant-billing/tenant-invoice-pdf-route.test.ts
git commit -m "feat(portal): tenant invoice PDF proxy route"
```

---

## Task 10: Tenant billing page (`/billing`) + sidebar item

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/billing/_components/TenantInvoicesTable.tsx`
- Create: `admin/apps/portal/app/(tenant-authed)/billing/page.tsx`
- Modify: `admin/apps/portal/src/components/AppShellSidebar.tsx`
- Create: `admin/apps/portal/src/__tests__/tenant-billing/TenantInvoicesTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// admin/apps/portal/src/__tests__/tenant-billing/TenantInvoicesTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/billing",
}));

import {
  TenantInvoicesTable,
  type TenantInvoiceRow,
} from "../../../app/(tenant-authed)/billing/_components/TenantInvoicesTable";

const row: TenantInvoiceRow = {
  id: "i1", invoice_number: "INV-2026-000001", amount_total: "120000",
  currency: "UGX", status: "issued", due_at: "2026-07-01",
};

function renderTable(rows: TenantInvoiceRow[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <TenantInvoicesTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("TenantInvoicesTable", () => {
  it("links the invoice number to the tenant invoice detail", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: /INV-2026-000001/i })).toHaveAttribute(
      "href",
      "/billing/invoices/i1",
    );
    expect(screen.getByText(/120,000/)).toBeInTheDocument();
  });

  it("renders the empty state with no rows", () => {
    renderTable([]);
    expect(screen.getByText(/no invoices/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- TenantInvoicesTable` → FAIL.

- [ ] **Step 3: Write `TenantInvoicesTable.tsx`**

```tsx
// admin/apps/portal/app/(tenant-authed)/billing/_components/TenantInvoicesTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Money,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";

export interface TenantInvoiceRow {
  id: string;
  invoice_number: string;
  amount_total: string;
  currency: string;
  status: string;
  due_at: string;
}

const columns: DataTableProps<TenantInvoiceRow>["columns"] = [
  {
    id: "invoice_number",
    accessorKey: "invoice_number",
    header: "Invoice",
    cell: ({ row }) => (
      <Link
        href={`/billing/invoices/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.invoice_number}
      </Link>
    ),
  },
  {
    id: "amount_total",
    accessorKey: "amount_total",
    header: "Total",
    cell: ({ row }) => <Money amount={row.original.amount_total} currency={row.original.currency} />,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="invoice" status={row.original.status} />,
  },
  {
    id: "due_at",
    accessorKey: "due_at",
    header: "Due",
    cell: ({ row }) => <FormattedDate value={row.original.due_at} />,
  },
];

export function TenantInvoicesTable({ rows }: { rows: TenantInvoiceRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "invoice_number", direction: "desc" },
    defaultPageSize: 25,
  });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<TenantInvoiceRow>
      id="tenant-invoices"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{ title: "No invoices", description: "Your invoices will appear here." }}
    />
  );
}
```

- [ ] **Step 4: Write the page**

```tsx
// admin/apps/portal/app/(tenant-authed)/billing/page.tsx
import { Card, FormattedDate, StatusBadge } from "@sacco/ui";
import type { InvoiceOut, SubscriptionOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { TenantInvoicesTable, type TenantInvoiceRow } from "./_components/TenantInvoicesTable";

export const metadata = { title: "Billing" };

export default async function TenantBillingPage() {
  const { resources } = await getTenantPageContext();

  const [{ data: sub }, { data: invoices }] = await Promise.all([
    resources.billing.mySubscription() as Promise<{ data?: SubscriptionOut; error?: unknown }>,
    resources.billing.myInvoices() as Promise<{ data?: InvoiceOut[]; error?: unknown }>,
  ]);

  const rows: TenantInvoiceRow[] = (invoices ?? []).map((inv) => ({
    id: inv.id,
    invoice_number: inv.invoice_number,
    amount_total: inv.amount_total,
    currency: inv.currency,
    status: inv.status,
    due_at: inv.due_at,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Billing</h1>
      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Subscription</h2>
        {sub ? (
          <>
            <div className="flex justify-between gap-4">
              <span className="text-[var(--text-secondary)]">Status</span>
              <StatusBadge entity="subscription" status={sub.status} />
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-[var(--text-secondary)]">Current period ends</span>
              <FormattedDate value={sub.current_period_end} />
            </div>
          </>
        ) : (
          <p className="text-[var(--text-secondary)]">No active subscription.</p>
        )}
      </Card>
      <Card className="p-0">
        <TenantInvoicesTable rows={rows} />
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Add the tenant sidebar "Billing" item**

In `AppShellSidebar.tsx`, inside the tenant `groups` array, add a new group after "Books" (before "Approvals & Audit"), matching the existing `SidebarItem` shape:

```tsx
        {
          label: "Billing",
          items: [
            <SidebarItem
              key="billing"
              href="/billing"
              label="Billing"
              active={isActive("/billing")}
            />,
          ],
        },
```

> Match the exact `SidebarItem` props/shape used by the surrounding tenant items (read the file — `href`/`label`/`active`/`icon?`). If items take an `icon`, omit it or reuse a neutral one consistent with siblings. Confirm `isActive` is in scope in this component (it is — used by every item).

- [ ] **Step 6: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal test -- TenantInvoicesTable` → PASS (2). `typecheck` + `lint` → clean.

- [ ] **Step 7: Commit**

```bash
git add "admin/apps/portal/app/(tenant-authed)/billing/page.tsx" "admin/apps/portal/app/(tenant-authed)/billing/_components/TenantInvoicesTable.tsx" admin/apps/portal/src/components/AppShellSidebar.tsx admin/apps/portal/src/__tests__/tenant-billing/TenantInvoicesTable.test.tsx
git commit -m "feat(portal): tenant billing page + sidebar item"
```

---

## Task 11: Tenant invoice detail (`/billing/invoices/[id]`)

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/billing/invoices/[id]/page.tsx`

- [ ] **Step 1: Write the page (server component; no separate test — renders primitives, fetch is the typed client)**

```tsx
// admin/apps/portal/app/(tenant-authed)/billing/invoices/[id]/page.tsx
import { notFound } from "next/navigation";
import { Button, Card, FormattedDate, Money, StatusBadge } from "@sacco/ui";
import type { InvoiceDetailOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";

export const metadata = { title: "Invoice" };

export default async function TenantInvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();

  const { data } = await (
    resources.billing.myInvoice(id) as Promise<{ data?: InvoiceDetailOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">{data.invoice_number}</h1>
        <Button asChild variant="secondary">
          <a href={`/api/billing/me/invoices/${data.id}/pdf`} target="_blank" rel="noreferrer">
            Download PDF
          </a>
        </Button>
      </div>
      <Card className="flex flex-col gap-3 p-6">
        <Row label="Status" value={<StatusBadge entity="invoice" status={data.status} />} />
        <Row label="Due" value={<FormattedDate value={data.due_at} />} />
        <Row label="Total" value={<Money amount={data.amount_total} currency={data.currency} />} />
        <Row label="Paid" value={<Money amount={data.amount_paid} currency={data.currency} />} />
      </Card>
      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Line items</h2>
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {data.line_items.map((li) => (
            <div key={li.id} className="flex justify-between py-2">
              <span className="text-[var(--text-primary)]">
                {li.description}
                {li.quantity > 1 ? ` × ${li.quantity}` : ""}
              </span>
              <Money amount={li.amount} currency={data.currency} />
            </div>
          ))}
        </div>
      </Card>
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

> If `React.ReactNode` trips eslint, import `type { ReactNode } from "react"` and use `ReactNode` (SP15 precedent). No `<AuditBar>` here — the audit trail is a platform-operator concern, not a tenant-facing one.

- [ ] **Step 2: Run + verify**

Run: `cd admin && pnpm --filter @sacco/portal typecheck` → clean. `pnpm --filter @sacco/portal lint` → clean.

- [ ] **Step 3: Commit**

```bash
git add "admin/apps/portal/app/(tenant-authed)/billing/invoices"
git commit -m "feat(portal): tenant invoice detail"
```

---

## Task 12: Full-module verification

**Files:** none (verification only, unless a fix is needed).

- [ ] **Step 1: Full verification**

```bash
cd admin
pnpm --filter @sacco/schemas test
pnpm --filter @sacco/schemas typecheck
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/ui test
pnpm --filter @sacco/portal test
pnpm --filter @sacco/portal typecheck
pnpm --filter @sacco/portal lint
```

All green. Portal suite = pre-SP16 count plus tenant-page-context / BillingTabs (updated) / InvoicesTable / InvoiceActions / invoice-pdf-route / PendingPaymentsTable / tenant-invoice-pdf-route / TenantInvoicesTable.

- [ ] **Step 2: Confirm no out-of-scope changes**

Run `git diff main..HEAD --stat` and confirm every path is under `admin/` or `docs/`. No `app/` (backend) changes (contracts B/N).

- [ ] **Step 3: Manual smoke (recommended)**

Backend + portal up. As finance: Billing → Invoices (list, filter) → invoice detail → Record payment (form → maker-checker dialog → "pending approval") → Payments tab shows the pending payment. As admin: Reject it (reason → rejected); Void an unpaid invoice (reason → maker-checker → pending approval). Download PDF opens the PDF. Then as a tenant user: Billing nav → subscription summary + own invoices → invoice detail → Download PDF. Confirm a `support` user is denied billing entirely; a `finance` user sees invoices + record-payment but not Void/Reject.

- [ ] **Step 4: Commit (only if a fix was needed)**

```bash
git add -A && git commit -m "fix(portal): SP16 verification fixes"
```

---

## Self-Review

**Spec coverage (`2026-06-15-portal-billing-invoices-payments-design.md`):**
Out types + PAYMENT_METHOD_OPTIONS (Task 1) ✓; `getTenantPageContext` (Task 2) ✓; BillingTabs 4 tabs (Task 3) ✓; invoices list w/ name resolution (Task 4) ✓; invoice detail + line items + AuditBar (Task 5) ✓; record-payment (maker-checker, idempotency key) + void (maker-checker) (Task 6) ✓; platform PDF proxy (Task 7) ✓; payments queue + reject (Task 8) ✓; tenant PDF proxy (Task 9) ✓; tenant billing page + sidebar (Task 10) ✓; tenant invoice detail (Task 11) ✓; permission mapping (record=billing.read, void/reject=billing.write) applied on every screen ✓; Money/StatusBadge/FormattedDate/FormField/DataTable throughout ✓. **Out of scope honored:** confirm-payment approval UI, MakerCheckerBanner (TODO/notes), e2e, i18n.

**Placeholder scan:** no TBD/TODO; every code step has full code. Verify-before-wiring flags are explicit (`DialogDescription` export in Task 6; `crypto.randomUUID` availability in Task 6; `--border-subtle` in Tasks 5/11; `SidebarItem` shape in Task 10; `React.ReactNode`→`ReactNode` in Tasks 5/11).

**Type consistency:** `InvoiceOut`/`InvoiceDetailOut`/`PaymentOut`/`InvoiceLineItemOut`/`PAYMENT_METHOD_OPTIONS` defined in Task 1, consumed in Tasks 4–11. `InvoiceRow` (Task 4), `PendingPaymentRow` (Task 8), `TenantInvoiceRow` (Task 10) each defined in their table and consumed by their page. `getTenantPageContext()` (Task 2) consumed in Tasks 10/11 + the tenant PDF route reads the same tenant token/slug helpers. `recordPayment(id, body)` / `voidInvoice(id, {reason})` / `rejectPayment(id, {reason})` call shapes match the api-client and the tests. `queryKeys.billing.invoices()/invoice(id)/pendingPayments()` used consistently.
