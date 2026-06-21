# SACCO Admin Portal — Reports (Phase 3f) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-21):** background subagents can't get Edit approval; run **inline**. **Confirm typecheck PASSES before committing** (SP20 lesson). No backend tests (no backend change). Portal/package tests via `pnpm --filter` from `admin/`.
> **Test gotchas (carry-over):** `<Money>` exposes `data-amount`, `<Count>` `data-value`; `<DataTable>` `TData` must extend `{ id: string }` (report rows get a synthetic `id: String(i)`); required-asterisk + prefix labels collide in `getByLabelText` (use distinct labels); PDF/CSV proxy route + test mirror `tenant-credit/statement-pdf-route`.

**Goal:** The Reports module — five filter-driven report pages (trial balance, loan portfolio, income statement, savings statement, fee collection) + a report-runs list, each rendering a precomputed run as a table with PDF/CSV download.

**Architecture:** Add a `report_run` StatusBadge entity + `@sacco/schemas/reporting.ts` read types, one dynamic download proxy route, then tenant-authed pages under `app/(tenant-authed)/reports/*`. Each page: a client filter form (URL-query state) + a server fetch of the JSON report + an in-memory `<DataTable>` + Download PDF/CSV links to the proxy. Clones the prior tenant-operator table pattern.

**Tech Stack:** Next.js 15, React 19, TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library. No Python changes.

## Global Constraints

- **Branch:** `feat/sacco-portal/06-reports`, off `main` (no PR stacking).
- **No backend changes, no api-client changes.** `resources.reporting.{trialBalance,loanPortfolio,incomeStatement,savingsStatement,feeCollection,listRuns}`, `resources.members.list`, `resources.fees.listTypes` exist (cast `{ data?, error? }`).
- **Reports read precomputed runs.** Trial balance / loan portfolio default to the latest run (`as_of` optional). Income statement / fee collection **require** `from_date`+`to_date` (404 if no run for that period → show a message). Savings statement **requires** `member_id`. Each endpoint: `format` ∈ {json, pdf, csv}.
- **Money** → `<Money>`; **int** (`days_in_arrears`) → `<Count>`; **dates** → `<DateInput>` (filters) / `<FormattedDate>`/`<FormattedDateTime>` (display). Loan status → `<StatusBadge entity="loan">`; run status → `<StatusBadge entity="report_run">`.
- **`<DataTable>` `TData extends { id: string }`** — map report rows to add `id: String(i)`.
- **No `<AuditBar>`**, tenant-auth gating only. **DRY/YAGNI/TDD, frequent commits.** Typecheck before each commit.

---

## Task 1: `@sacco/ui` — `report_run` StatusBadge entity

**Files:**
- Modify: `admin/packages/ui/src/components/StatusBadge/status-maps.ts`
- Test: `admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx`

- [ ] **Step 1: Failing test** — append to `StatusBadge.test.tsx`:

```tsx
it("renders a report_run status", () => {
  render(<StatusBadge entity="report_run" status="done" />);
  expect(screen.getByText("Done")).toBeInTheDocument();
});
```

Run: `cd admin && pnpm --filter @sacco/ui test -- StatusBadge` → FAIL.

- [ ] **Step 2: Add the entity** to `status-maps.ts`: extend `StatusEntity` with `| "report_run"`; add the map; register in `ENTITY_MAPS`:

```ts
export const REPORT_RUN_STATUS: StatusMap = {
  running: { variant: "info", label: "Running" },
  done: { variant: "success", label: "Done" },
  failed: { variant: "danger", label: "Failed" },
};
```
Add `report_run: REPORT_RUN_STATUS,` to `ENTITY_MAPS`.

- [ ] **Step 3: Run test → PASS; typecheck + lint + commit.**

```bash
pnpm --filter @sacco/ui test -- StatusBadge && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
git add admin/packages/ui/src/components/StatusBadge/status-maps.ts admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx
git commit -m "feat(portal): report_run StatusBadge entity

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `@sacco/schemas/reporting.ts` — read types

**Files:**
- Create: `admin/packages/schemas/src/reporting.ts`
- Modify: `admin/packages/schemas/src/index.ts`
- Test: `admin/packages/schemas/src/__tests__/reporting.test.ts`

**Interfaces:**
- Produces: `TrialBalanceLineOut`, `TrialBalanceOut`, `LoanPortfolioRowOut`, `LoanPortfolioOut`, `IncomeStatementLineOut`, `IncomeStatementOut`, `SavingsStatementLineOut`, `SavingsStatementOut`, `FeeCollectionRowOut`, `FeeCollectionOut`, `ReportRunOut`.

- [ ] **Step 1: Failing test** — create `src/__tests__/reporting.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type {
  TrialBalanceOut,
  LoanPortfolioOut,
  ReportRunOut,
} from "../reporting";

describe("reporting read types", () => {
  it("are structurally usable", () => {
    const tb: TrialBalanceOut = {
      as_of_date: "2026-06-01", generated_at: "2026-06-01T00:00:00Z",
      lines: [{ account_id: "a1", account_code: "1000", account_name: "Cash",
        account_type: "asset", debit_total: "100.0000", credit_total: "0.0000",
        balance: "100.0000" }],
    };
    const lp: LoanPortfolioOut = {
      as_of_date: "2026-06-01", generated_at: "2026-06-01T00:00:00Z",
      rows: [{ loan_id: "l1", loan_reference: "LN-1", member_id: "m1",
        product_name: "Personal", disbursed_at: "2026-01-01", maturity_date: null,
        status: "disbursed", outstanding_principal: "900.0000", accrued_interest: "0.0000",
        total_written_off: "0.0000", days_in_arrears: 0, aging_bucket: "current" }],
    };
    const run: ReportRunOut = {
      id: "r1", report_type: "trial_balance", as_of_date: "2026-06-01",
      status: "done", started_at: "2026-06-01T00:00:00Z", completed_at: null,
      error_detail: null,
    };
    expect(tb.lines[0]!.balance).toBe("100.0000");
    expect(lp.rows[0]!.days_in_arrears).toBe(0);
    expect(run.status).toBe("done");
  });
});
```

Run: `pnpm --filter @sacco/schemas test -- reporting` → FAIL.

- [ ] **Step 2: Create `src/reporting.ts`:**

```ts
// admin/packages/schemas/src/reporting.ts
// Mirror app/modules/reporting/schemas.py. Decimals/dates/datetimes are JSON strings.

export interface ReportRunOut {
  id: string;
  report_type: string;
  as_of_date: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  error_detail: string | null;
}

export interface TrialBalanceLineOut {
  account_id: string;
  account_code: string;
  account_name: string;
  account_type: string;
  debit_total: string;
  credit_total: string;
  balance: string;
}
export interface TrialBalanceOut {
  as_of_date: string;
  generated_at: string;
  lines: TrialBalanceLineOut[];
}

export interface LoanPortfolioRowOut {
  loan_id: string;
  loan_reference: string;
  member_id: string;
  product_name: string;
  disbursed_at: string;
  maturity_date: string | null;
  status: string;
  outstanding_principal: string;
  accrued_interest: string;
  total_written_off: string;
  days_in_arrears: number;
  aging_bucket: string;
}
export interface LoanPortfolioOut {
  as_of_date: string;
  generated_at: string;
  rows: LoanPortfolioRowOut[];
}

export interface IncomeStatementLineOut {
  account_id: string;
  account_code: string;
  account_name: string;
  account_type: string;
  debit_total: string;
  credit_total: string;
  net_movement: string;
}
export interface IncomeStatementOut {
  period_start: string;
  period_end: string;
  generated_at: string;
  lines: IncomeStatementLineOut[];
}

export interface SavingsStatementLineOut {
  savings_account_id: string;
  member_id: string;
  posted_at: string;
  transaction_type: string;
  narration: string | null;
  amount: string;
  running_balance: string;
}
export interface SavingsStatementOut {
  member_id: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  lines: SavingsStatementLineOut[];
}

export interface FeeCollectionRowOut {
  fee_type_id: string;
  fee_type_name: string;
  target_type: string;
  assessed_total: string;
  collected_total: string;
  outstanding_total: string;
  waived_total: string;
}
export interface FeeCollectionOut {
  period_start: string;
  period_end: string;
  generated_at: string;
  rows: FeeCollectionRowOut[];
}
```

- [ ] **Step 3: Export** from `src/index.ts` — add `export * from "./reporting";`.

- [ ] **Step 4: Run test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/schemas test -- reporting && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
git add admin/packages/schemas/src/reporting.ts admin/packages/schemas/src/index.ts admin/packages/schemas/src/__tests__/reporting.test.ts
git commit -m "feat(portal): reporting read types

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Download proxy route — `app/api/reporting/[report]/route.ts`

**Files:**
- Create: `admin/apps/portal/app/api/reporting/[report]/route.ts`
- Test: `admin/apps/portal/src/__tests__/tenant-reports/reporting-download-route.test.ts`

**Interfaces:**
- Consumes: `getServerAccessToken`, `getServerTenantSlug` from `@/auth/server-helpers`.

- [ ] **Step 1: Test (failing)** — create the route test (mirror `tenant-credit/statement-pdf-route.test.ts`):

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getServerAccessToken = vi.fn();
const getServerTenantSlug = vi.fn();
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerTenantSlug: (...a: unknown[]) => getServerTenantSlug(...a),
}));
const fetchMock = vi.fn();
beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal("fetch", fetchMock); });
afterEach(() => vi.unstubAllGlobals());
const ctx = (report: string) => ({ params: Promise.resolve({ report }) });

describe("GET /api/reporting/[report]", () => {
  it("401s without a tenant session", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    getServerTenantSlug.mockResolvedValue("alpha");
    const { GET } = await import("../../../app/api/reporting/[report]/route");
    const res = await GET(new Request("http://localhost/api/reporting/trial-balance?format=csv"), ctx("trial-balance"));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("404s an unknown report", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "t" });
    getServerTenantSlug.mockResolvedValue("alpha");
    const { GET } = await import("../../../app/api/reporting/[report]/route");
    const res = await GET(new Request("http://localhost/api/reporting/bogus?format=csv"), ctx("bogus"));
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("proxies a known report with bearer + slug + query", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "tenant-access" });
    getServerTenantSlug.mockResolvedValue("alpha");
    fetchMock.mockResolvedValue({
      ok: true, status: 200,
      arrayBuffer: async () => new Uint8Array([1, 2]).buffer,
      headers: new Headers({
        "content-type": "text/csv",
        "content-disposition": 'attachment; filename="trial-balance.csv"',
      }),
    });
    const { GET } = await import("../../../app/api/reporting/[report]/route");
    const res = await GET(
      new Request("http://localhost/api/reporting/loan-portfolio?format=csv&as_of=2026-06-01&status=disbursed"),
      ctx("loan-portfolio"),
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/csv");
    const [url, init] = fetchMock.mock.calls[0] as [string, { headers?: Record<string, string> }];
    expect(String(url)).toContain("/reporting/loan-portfolio?");
    expect(String(url)).toContain("format=csv");
    expect(String(url)).toContain("as_of=2026-06-01");
    expect(String(url)).toContain("status=disbursed");
    expect(init.headers?.["Authorization"]).toBe("Bearer tenant-access");
    expect(init.headers?.["X-Tenant-Slug"]).toBe("alpha");
  });
});
```

- [ ] **Step 2: Implement `route.ts`:**

```ts
// admin/apps/portal/app/api/reporting/[report]/route.ts
import { NextResponse } from "next/server";
import { getServerAccessToken, getServerTenantSlug } from "@/auth/server-helpers";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

const ALLOWED = new Set([
  "trial-balance",
  "loan-portfolio",
  "income-statement",
  "savings-statement",
  "fee-collection",
]);

export async function GET(
  request: Request,
  { params }: { params: Promise<{ report: string }> },
): Promise<NextResponse> {
  const { report } = await params;
  if (!ALLOWED.has(report)) {
    return NextResponse.json({ error: "Unknown report" }, { status: 404 });
  }
  const slug = await getServerTenantSlug();
  const { accessToken } = await getServerAccessToken("tenant");
  if (!slug || !accessToken) {
    return NextResponse.json({ error: "No tenant session" }, { status: 401 });
  }

  const incoming = new URL(request.url);
  const qs = incoming.searchParams.toString();
  const upstream = `${API_BASE}/reporting/${report}${qs ? `?${qs}` : ""}`;

  const r = await fetch(upstream, {
    headers: { Authorization: `Bearer ${accessToken}`, "X-Tenant-Slug": slug },
    cache: "no-store",
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Failed to load report" }, { status: r.status });
  }
  const body = await r.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": r.headers.get("content-type") ?? "application/octet-stream",
      "Content-Disposition": r.headers.get("content-disposition") ?? `attachment; filename="${report}"`,
    },
  });
}
```

- [ ] **Step 3: Run test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-reports/reporting-download-route
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/api/reporting/" admin/apps/portal/src/__tests__/tenant-reports/reporting-download-route.test.ts
git commit -m "feat(portal): reporting PDF/CSV download proxy route

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `/reports` index page

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/reports/page.tsx`

- [ ] **Step 1: Implement `reports/page.tsx`** (server, no fetch) — a `<Card>` with a list of `<Link>`s:

```tsx
import Link from "next/link";
import { Card } from "@sacco/ui";

export const metadata = { title: "Reports" };

const REPORTS = [
  { href: "/reports/trial-balance", label: "Trial balance" },
  { href: "/reports/loan-portfolio", label: "Loan portfolio" },
  { href: "/reports/income-statement", label: "Income statement" },
  { href: "/reports/savings-statement", label: "Savings statement" },
  { href: "/reports/fee-collection", label: "Fee collection" },
  { href: "/reports/runs", label: "Report runs" },
];

export default function ReportsIndexPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Reports</h1>
      <Card className="flex flex-col divide-y divide-[var(--border-subtle)] p-2">
        {REPORTS.map((r) => (
          <Link key={r.href} href={r.href}
            className="px-4 py-3 text-[var(--text-link)] hover:underline">
            {r.label}
          </Link>
        ))}
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/reports/page.tsx"
git commit -m "feat(portal): reports index page

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Trial balance — `<AsOfFilter>` + `<TrialBalanceTable>` + page (reference pattern)

**Files:**
- Create: `app/(tenant-authed)/reports/trial-balance/_components/{AsOfFilter,TrialBalanceTable}.tsx`, `trial-balance/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-reports/TrialBalanceTable.test.tsx`

**Interfaces:**
- Consumes: `TrialBalanceLineOut`, `resources.reporting.trialBalance`.
- Produces: `<AsOfFilter basePath={string} />` (client) — reused conceptually by other single-date reports; `<TrialBalanceTable rows={TrialBalanceLineOut[]} />`.

- [ ] **Step 1: `TrialBalanceTable` test (failing)** — clone an in-memory table test (mock `useTableUrlState` + `next/navigation`; `<TenantCurrencyProvider>`). One line (Task-2 `tb.lines[0]` shape). Assert the account name "Cash" renders + empty state "No trial-balance lines".

- [ ] **Step 2: Implement `TrialBalanceTable.tsx`** (client) — in-memory `<DataTable id="trial-balance">`. `type Row = TrialBalanceLineOut & { id: string }`; map `rows.map((r,i)=>({...r,id:String(i)}))`. Columns: **Code** (`account_code`); **Name** (`account_name`); **Type** (`account_type`); **Debit** → `<Money amount={row.original.debit_total} />`; **Credit** → `<Money amount={row.original.credit_total} />`; **Balance** → `<Money amount={row.original.balance} />`. Empty `{ title: "No trial-balance lines", description: "No data for the selected date." }`. Props `{ rows: TrialBalanceLineOut[] }`.

- [ ] **Step 3: Implement `AsOfFilter.tsx`** (client) — `"use client"`. Uses `useRouter` + `useSearchParams`. A `<DateInput>` (local `useState` seeded from `searchParams.get("as_of")`) + an **Apply** `<Button>` that `router.push(\`${basePath}?${new URLSearchParams(asOf ? { as_of: asOf } : {})}\`)`. Props `{ basePath: string }`.

```tsx
"use client";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, DateInput, Label } from "@sacco/ui";

export function AsOfFilter({ basePath }: { basePath: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const [asOf, setAsOf] = useState(params.get("as_of") ?? "");
  return (
    <div className="flex items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="as_of">As of</Label>
        <DateInput id="as_of" value={asOf} onValueChange={setAsOf} />
      </div>
      <Button
        type="button"
        onClick={() => router.push(`${basePath}?${new URLSearchParams(asOf ? { as_of: asOf } : {}).toString()}`)}
      >
        Apply
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Implement `trial-balance/page.tsx`** (server) — `searchParams: Promise<{ as_of?: string }>`. `const sp = await searchParams;`. `getTenantPageContext()`; `resources.reporting.trialBalance(sp.as_of ? { as_of: sp.as_of } : {})` cast `{ data?: TrialBalanceOut; error?: unknown }`. Header `<h1>Trial balance</h1>` + (when data) Download links:
  `<a href={\`/api/reporting/trial-balance?format=pdf${sp.as_of ? \`&as_of=${sp.as_of}\` : ""}\`}>PDF</a>` and `…format=csv…` (use `<Button asChild variant="secondary">`). Render `<AsOfFilter basePath="/reports/trial-balance" />`. Then: if `error` → a `<Card>` "No report available for this date."; else `<TrialBalanceTable rows={data?.lines ?? []} />` (+ a caption with `data.as_of_date`). `export const metadata = { title: "Trial balance" }`.

- [ ] **Step 5: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-reports/TrialBalanceTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/reports/trial-balance/" admin/apps/portal/src/__tests__/tenant-reports/TrialBalanceTable.test.tsx
git commit -m "feat(portal): trial balance report

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Loan portfolio report

> Same page/table/download structure as Task 5. Deltas below.

**Files:**
- Create: `app/(tenant-authed)/reports/loan-portfolio/_components/{LoanPortfolioFilter,LoanPortfolioTable}.tsx`, `loan-portfolio/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-reports/LoanPortfolioTable.test.tsx`

- [ ] **Step 1: `LoanPortfolioTable` test (failing)** — `TData = LoanPortfolioRowOut` (Task-2 `lp.rows[0]` shape). Assert "LN-1" renders + the loan status badge "Disbursed" + empty state "No loans in the portfolio".

- [ ] **Step 2: Implement `LoanPortfolioTable.tsx`** — in-memory `<DataTable id="loan-portfolio">`, synthetic id from `loan_id` (`id: r.loan_id`). Columns: **Loan ref** (`loan_reference`); **Product** (`product_name`); **Status** → `<StatusBadge entity="loan" status={row.original.status} />`; **Outstanding** → `<Money amount={row.original.outstanding_principal} />`; **Accrued interest** → `<Money amount={row.original.accrued_interest} />`; **Days in arrears** → `<Count value={row.original.days_in_arrears} />`; **Aging** (`aging_bucket`). Empty `{ title: "No loans in the portfolio", description: "No data for the selected date." }`. Props `{ rows: LoanPortfolioRowOut[] }`.

- [ ] **Step 3: Implement `LoanPortfolioFilter.tsx`** (client) — like `AsOfFilter` plus a status `<Select>` (all/disbursed/in_arrears/written_off; seed from `params.get("status") ?? "all"`). Apply → `router.push("/reports/loan-portfolio?" + new URLSearchParams({ ...(asOf?{as_of:asOf}:{}), status }))`.

- [ ] **Step 4: Implement `loan-portfolio/page.tsx`** (server) — `searchParams: Promise<{ as_of?: string; status?: string }>`. Fetch `resources.loanPortfolio({ ...(sp.as_of?{as_of:sp.as_of}:{}), ...(sp.status?{status:sp.status}:{}) })` cast `{ data?: LoanPortfolioOut; error? }`. Download links carry as_of + status. Render `<LoanPortfolioFilter />`, then error card or `<LoanPortfolioTable rows={data?.rows ?? []} />`.

- [ ] **Step 5: Run + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-reports/LoanPortfolioTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/reports/loan-portfolio/" admin/apps/portal/src/__tests__/tenant-reports/LoanPortfolioTable.test.tsx
git commit -m "feat(portal): loan portfolio report

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Income statement report (date range — required)

**Files:**
- Create: `app/(tenant-authed)/reports/income-statement/_components/{DateRangeFilter,IncomeStatementTable}.tsx`, `income-statement/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-reports/{IncomeStatementTable,DateRangeFilter}.test.tsx`

**Interfaces:**
- Produces: `<DateRangeFilter basePath={string} />` (client) — reused by fee collection.

- [ ] **Step 1: `DateRangeFilter` test (failing)** — mock `useRouter` (`push`) + `useSearchParams` (empty). Render `<DateRangeFilter basePath="/reports/income-statement" />`. Type a from + to date (label "From"/"To" `<DateInput>`s) → click Apply → `push` called with `"/reports/income-statement?from_date=2026-01-01&to_date=2026-06-30"` (order-independent: assert the pushed string contains both params).

- [ ] **Step 2: Implement `DateRangeFilter.tsx`** (client) — two `<DateInput>`s ("From", "To") seeded from `params`, Apply → `router.push(\`${basePath}?${new URLSearchParams({ ...(from?{from_date:from}:{}), ...(to?{to_date:to}:{}) })}\`)`. Props `{ basePath: string }`.

- [ ] **Step 3: `IncomeStatementTable` test (failing)** — `TData = IncomeStatementLineOut`. One line (account_code/name/type + debit_total/credit_total/net_movement strings). Assert a name renders + empty state "No income-statement lines".

- [ ] **Step 4: Implement `IncomeStatementTable.tsx`** — in-memory `<DataTable id="income-statement">`, synthetic id `String(i)`. Columns: **Code**, **Name**, **Type**, **Debit** (`<Money>`), **Credit** (`<Money>`), **Net movement** → `<Money amount={row.original.net_movement} />`. Empty `{ title: "No income-statement lines", description: "Choose a period to view." }`. Props `{ rows: IncomeStatementLineOut[] }`.

- [ ] **Step 5: Implement `income-statement/page.tsx`** (server) — `searchParams: Promise<{ from_date?: string; to_date?: string }>`. `const ready = Boolean(sp.from_date && sp.to_date);` Only fetch when `ready`: `resources.incomeStatement({ from_date: sp.from_date, to_date: sp.to_date })` cast `{ data?: IncomeStatementOut; error? }`. Render `<DateRangeFilter basePath="/reports/income-statement" />`; if `!ready` → a `<Card>` "Choose a from and to date."; else if `error` → "No report available for this period."; else Download PDF/CSV links (with from_date+to_date) + `<IncomeStatementTable rows={data?.lines ?? []} />`.

- [ ] **Step 6: Run both tests + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-reports/IncomeStatementTable tenant-reports/DateRangeFilter
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/reports/income-statement/" admin/apps/portal/src/__tests__/tenant-reports/IncomeStatementTable.test.tsx admin/apps/portal/src/__tests__/tenant-reports/DateRangeFilter.test.tsx
git commit -m "feat(portal): income statement report

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Savings statement report (member + range)

**Files:**
- Create: `app/(tenant-authed)/reports/savings-statement/_components/{SavingsStatementFilter,SavingsStatementTable}.tsx`, `savings-statement/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-reports/SavingsStatementTable.test.tsx`

- [ ] **Step 1: `SavingsStatementTable` test (failing)** — `TData = SavingsStatementLineOut`. One line. Assert the transaction_type renders + empty state "No savings transactions".

- [ ] **Step 2: Implement `SavingsStatementTable.tsx`** — in-memory `<DataTable id="savings-statement">`, synthetic id `String(i)`. Columns: **Posted** → `<FormattedDateTime value={row.original.posted_at} />`; **Type** (`transaction_type`); **Narration** (`?? "—"`); **Amount** → `<Money amount={row.original.amount} />`; **Running balance** → `<Money amount={row.original.running_balance} />`. Empty `{ title: "No savings transactions", description: "Choose a member to view." }`. Props `{ rows: SavingsStatementLineOut[] }`.

- [ ] **Step 3: Implement `SavingsStatementFilter.tsx`** (client) — props `{ members: { id: string; label: string }[] }`. A member `<Select>` (seed from `params.get("member_id")`) + two `<DateInput>`s (From/To). Apply → `router.push("/reports/savings-statement?" + new URLSearchParams({ ...(memberId?{member_id:memberId}:{}), ...(from?{from_date:from}:{}), ...(to?{to_date:to}:{}) }))`.

- [ ] **Step 4: Implement `savings-statement/page.tsx`** (server) — `searchParams: Promise<{ member_id?: string; from_date?: string; to_date?: string }>`. Fetch `members.list({})` for the select (label `${full_name} (${member_number})`). `const ready = Boolean(sp.member_id);` When ready: `resources.savingsStatement({ member_id, ...(from_date?), ...(to_date?) })` cast `{ data?: SavingsStatementOut; error? }`. Render `<SavingsStatementFilter members={…} />`; if `!ready` → "Choose a member."; else error card or Download links (member_id + dates) + `<SavingsStatementTable rows={data?.lines ?? []} />`.

- [ ] **Step 5: Run + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-reports/SavingsStatementTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/reports/savings-statement/" admin/apps/portal/src/__tests__/tenant-reports/SavingsStatementTable.test.tsx
git commit -m "feat(portal): savings statement report

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Fee collection report (range + fee-type)

**Files:**
- Create: `app/(tenant-authed)/reports/fee-collection/_components/{FeeCollectionFilter,FeeCollectionTable}.tsx`, `fee-collection/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-reports/FeeCollectionTable.test.tsx`

- [ ] **Step 1: `FeeCollectionTable` test (failing)** — `TData = FeeCollectionRowOut`. One row. Assert the fee_type_name renders + empty state "No fee-collection data".

- [ ] **Step 2: Implement `FeeCollectionTable.tsx`** — in-memory `<DataTable id="fee-collection">`, synthetic id `String(i)`. Columns: **Fee type** (`fee_type_name`); **Target** (`target_type`); **Assessed** → `<Money amount={row.original.assessed_total} />`; **Collected** → `<Money amount={row.original.collected_total} />`; **Outstanding** → `<Money amount={row.original.outstanding_total} />`; **Waived** → `<Money amount={row.original.waived_total} />`. Empty `{ title: "No fee-collection data", description: "Choose a period to view." }`. Props `{ rows: FeeCollectionRowOut[] }`.

- [ ] **Step 3: Implement `FeeCollectionFilter.tsx`** (client) — props `{ feeTypes: { id: string; label: string }[] }`. Two `<DateInput>`s (From/To) + an optional fee-type `<Select>` (include an "All" item with value `""`? — Radix Select can't use `""`; use a literal "all" sentinel and omit `fee_type_id` when "all"). Apply → push with from_date, to_date, and fee_type_id only when not "all".

- [ ] **Step 4: Implement `fee-collection/page.tsx`** (server) — `searchParams: Promise<{ from_date?: string; to_date?: string; fee_type_id?: string }>`. Fetch `fees.listTypes({})` for the select (label `${code} — ${name}`). `const ready = Boolean(sp.from_date && sp.to_date);` When ready: `resources.feeCollection({ from_date, to_date, ...(fee_type_id?) })` cast `{ data?: FeeCollectionOut; error? }`. Render `<FeeCollectionFilter feeTypes={…} />`; if `!ready` → "Choose a from and to date."; else error card or Download links + `<FeeCollectionTable rows={data?.rows ?? []} />`.

- [ ] **Step 5: Run + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-reports/FeeCollectionTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/reports/fee-collection/" admin/apps/portal/src/__tests__/tenant-reports/FeeCollectionTable.test.tsx
git commit -m "feat(portal): fee collection report

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: Report runs list

**Files:**
- Create: `app/(tenant-authed)/reports/runs/_components/RunsTable.tsx`, `reports/runs/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-reports/RunsTable.test.tsx`

- [ ] **Step 1: `RunsTable` test (failing)** — `TData = ReportRunOut` (Task-2 `run` shape, `id:"r1"`). Assert the report_type renders + status badge "Done" + empty state "No report runs yet".

- [ ] **Step 2: Implement `RunsTable.tsx`** — in-memory `<DataTable id="report-runs">`, `TData = ReportRunOut` (has `id`). Columns: **Report type** (`report_type`); **As of** → `<FormattedDate value={row.original.as_of_date} />`; **Status** → `<StatusBadge entity="report_run" status={row.original.status} />`; **Started** → `<FormattedDateTime value={row.original.started_at} />`; **Completed** → `row.original.completed_at ? <FormattedDateTime value={row.original.completed_at} /> : "—"`. Empty `{ title: "No report runs yet", description: "Scheduled report runs appear here." }`.

- [ ] **Step 3: Implement `reports/runs/page.tsx`** (server) — `resources.reporting.listRuns({})` cast `{ data?: ReportRunOut[] }`, `<h1>Report runs</h1>`, `<RunsTable rows={data ?? []} />`. `export const metadata = { title: "Report runs" }`.

- [ ] **Step 4: Run + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-reports/RunsTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/reports/runs/" admin/apps/portal/src/__tests__/tenant-reports/RunsTable.test.tsx
git commit -m "feat(portal): report runs list

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 11: Verification + PR

- [ ] **Step 1: Package + portal gate**:
```bash
cd admin
pnpm --filter @sacco/ui test && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test delta over the 262 (3e) baseline.

- [ ] **Step 2: Contract spot-checks**:
  - [ ] No backend changes: `git diff --name-only main...HEAD | grep -E '^app/'` empty; `grep -E '^alembic/'` empty.
  - [ ] No api-client changes: `git diff --name-only main...HEAD | grep 'api-client'` empty.
  - [ ] Changes under `admin/` + `docs/` only.

- [ ] **Step 3: Final holistic review** — index links to all reports; each report: filter pushes URL, table renders the run, PDF/CSV download links hit the proxy; income/fee require a date range (filter-only until set); savings requires a member; runs list shows statuses. No AuditBar; tenant-auth only.

- [ ] **Step 4: Push + PR** (base `main`):
```bash
git push -u origin feat/sacco-portal/06-reports
gh pr create --base main --title "feat(portal): SACCO admin — Reports module (Phase 3f)" --body "$(cat <<'EOF'
## Summary
- Final Phase-3 module: the **Reports** surface — trial balance, loan portfolio, income statement, savings statement, fee collection (filterable on-screen tables) + a report-runs list.
- Each report reads a **precomputed run** (JSON) and offers **PDF/CSV download** via one **dynamic proxy route** (`/api/reporting/[report]`, tenant-authed, allow-listed). Filters are URL-query state; income/fee require a date range, savings requires a member.
- New `@sacco/schemas/reporting.ts` read types + a `report_run` StatusBadge entity. Loan-portfolio rows reuse `StatusBadge entity="loan"`.
- **No backend or api-client changes.**

## Test plan
- `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, `@sacco/portal` test/typecheck/lint green.

> Phase 3 (SACCO operator portal) COMPLETE: Members + Savings + Shares + Credit + Fees + Reports.
> CI note: Lint fails environmentally on this repo (runner-queue issue); reproduced clean locally.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** report_run badge → T1; read types → T2; download proxy → T3; index → T4; trial balance → T5; loan portfolio → T6; income statement → T7; savings statement → T8; fee collection → T9; runs → T10; verify/PR → T11.
- **Type consistency:** the 11 reporting read types (T2) consumed by T5–T10; each table maps a synthetic `id` (or uses `loan_id`/`account_id`/run `id`); loan-portfolio status → `entity="loan"`, runs status → `entity="report_run"`. `days_in_arrears` is `number` (→ `<Count>`); all monetary totals are strings (→ `<Money>`).
- **Verify-at-execution:** `<DateInput>` value/onValueChange (proven); `<Label>` exported from `@sacco/ui`; Radix `<Select>` cannot use an empty-string item value (use an "all" sentinel for the optional fee-type filter); income/fee endpoints **404 when no run matches the period** → render the error card; Next 15 `searchParams`/`params` are Promises; the download proxy mirrors `tenant-credit/statement-pdf-route`.
- **No backend tests** — no backend change.
