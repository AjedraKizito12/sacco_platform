# SACCO Admin Portal — Credit Loans Servicing (Phase 3d-3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-21):** background subagents can't get Edit approval; run **inline**. **Confirm typecheck PASSES before committing** (SP20 lesson). No backend tests (no backend change). Portal/package tests via `pnpm --filter` from `admin/`.
> **Test gotchas (from 3d-2):** checkboxes inside a Radix Dialog need `fireEvent.click(getByRole("checkbox"))` (body scroll-lock breaks `userEvent` label toggling); uuid-typed schema fields require real UUID strings in fixtures or the resolver silently blocks submit.

**Goal:** Make loans live and serviceable — correct the application form so loans are disbursable, add a Disburse action, and build the loans list + detail (balances, schedule, repayments, statement with PDF) + record-repayment + member loans section.

**Architecture:** Add loan read types + a required-field schema fix, a statement-PDF Next API-route proxy (clones the invoice PDF route), and tenant-authed screens under `app/(tenant-authed)/credit/loans/*` plus modifications to the 3d-2 application form/detail and the member detail page. Server-fetch via `getTenantPageContext()`, in-memory `<DataTable>`s, RHF/Zod forms, `<StatusBadge entity="loan">`. Clones the 3a–3d-2 pattern.

**Tech Stack:** Next.js 15, React 19, TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library. No Python changes.

## Global Constraints

- **Branch:** `feat/sacco-portal/04c-credit-loans`, off `main` (no PR stacking).
- **No backend changes, no api-client changes.** `resources.credit.{listLoans,getLoan,disburse,getSchedule,listRepayments,recordRepayment,getStatement,getProduct,listProducts,getApplication}`, `resources.members.list`, `resources.ledger.listAccounts` all exist (cast `{ data?, error? }`).
- **Disburse v1 supports only `cash` / `internal_gl`** (member_savings raises backend error); `application.disbursement_account_id` (a GL account id) is **required** at submit so disburse works.
- **Disburse acts on an approved application** → `POST /credit/loans/{application_id}/disburse` (201 → `LoanOut`).
- **Repayment is direct** (201, no maker-checker). **Loan status → `<StatusBadge entity="loan">`** (existing map; no new entity). Installment status renders as text.
- **Money** → `<Money>`/`<MoneyInput>`; **rate** → `<Percentage>`; **int** (`term_periods`, `period_number`) → `<Count>`; **dates** → `<FormattedDate>` / created_at via `<FormattedDate>`. Idempotency key = fresh UUID per form instance (contract L).
- **No `<AuditBar>`**, tenant-auth gating only. **DRY/YAGNI/TDD, frequent commits.** Typecheck before each commit.

---

## Task 1: `@sacco/schemas` — loan read types + required `disbursement_account_id`

**Files:**
- Modify: `admin/packages/schemas/src/credit.ts`
- Test: `admin/packages/schemas/src/__tests__/credit.test.ts`

**Interfaces:**
- Produces: `LoanOut`, `LoanInstallmentOut`, `LoanRepaymentOut`, `StatementLineOut`, `LoanStatementOut`; `loanApplicationSchema.disbursement_account_id` now **required** `uuid`.

- [ ] **Step 1: Failing test** — append to `credit.test.ts` (the import block already has `loanApplicationSchema`; add the new type imports):

```ts
import type {
  LoanOut,
  LoanInstallmentOut,
  LoanRepaymentOut,
  LoanStatementOut,
} from "../credit";

describe("loans servicing schemas (3d-3)", () => {
  it("requires disbursement_account_id on an application", () => {
    const base = {
      loan_product_id: "550e8400-e29b-41d4-a716-446655440000",
      member_id: "550e8400-e29b-41d4-a716-446655440001",
      requested_amount: "1000000.00",
      requested_term_periods: "12",
      purpose: "Working capital for the family shop",
      disbursement_destination: "cash",
      idempotency_key: "1234567890ab",
    };
    expect(loanApplicationSchema.safeParse(base).success).toBe(false); // no account id
    expect(
      loanApplicationSchema.safeParse({
        ...base,
        disbursement_account_id: "550e8400-e29b-41d4-a716-446655440002",
      }).success,
    ).toBe(true);
  });
  it("loan read types are structurally usable", () => {
    const loan: LoanOut = {
      id: "l1", loan_reference: "LN-202606-000001", loan_application_id: "a1",
      loan_product_id: "p1", member_id: "m1", status: "disbursed",
      principal_amount: "1000000.0000", outstanding_principal: "900000.0000",
      accrued_interest: "0.0000", accrued_penalties: "0.0000",
      annual_interest_rate: "18.5000", interest_method: "reducing_balance",
      repayment_frequency: "monthly", term_periods: 12,
      disbursement_destination: "cash", first_repayment_due: "2026-07-01",
      maturity_date: "2027-06-01", disbursed_at: "2026-06-21T00:00:00Z",
      created_at: "2026-06-21T00:00:00Z",
    };
    const inst: LoanInstallmentOut = {
      id: "i1", loan_id: "l1", period_number: 1, due_date: "2026-07-01",
      principal_due: "80000.0000", interest_due: "15000.0000", total_due: "95000.0000",
      principal_paid: "0.0000", interest_paid: "0.0000", status: "pending", paid_at: null,
    };
    const rep: LoanRepaymentOut = {
      id: "r1", loan_id: "l1", amount: "95000.0000", principal_applied: "80000.0000",
      interest_applied: "15000.0000", penalties_applied: "0.0000", overpayment: "0.0000",
      payment_account_id: "g1", journal_entry_id: "j1", posted_by: "u1",
      narration: null, idempotency_key: "k", created_at: "2026-06-21T00:00:00Z",
    };
    const st: LoanStatementOut = {
      loan_id: "l1", from_date: null, to_date: null,
      lines: [{ date: "2026-06-21", line_type: "disbursement", description: "Disbursed",
        debit: "1000000.0000", credit: "0.0000", running_balance: "1000000.0000" }],
    };
    expect(loan.term_periods).toBe(12);
    expect(inst.period_number).toBe(1);
    expect(rep.amount).toBe("95000.0000");
    expect(st.lines.length).toBe(1);
  });
});
```

Run: `cd admin && pnpm --filter @sacco/schemas test -- credit` → FAIL.

- [ ] **Step 2: Edit `credit.ts`** — make the field required in `loanApplicationSchema`:

```ts
  disbursement_account_id: uuid,
```
(was `uuid.optional()`.) Then add the read types near the other credit interfaces:

```ts
export interface LoanOut {
  id: string;
  loan_reference: string;
  loan_application_id: string;
  loan_product_id: string;
  member_id: string;
  status: string;
  principal_amount: string;
  outstanding_principal: string;
  accrued_interest: string;
  accrued_penalties: string;
  annual_interest_rate: string;
  interest_method: string;
  repayment_frequency: string;
  term_periods: number;
  disbursement_destination: string;
  first_repayment_due: string | null;
  maturity_date: string | null;
  disbursed_at: string | null;
  created_at: string;
}

export interface LoanInstallmentOut {
  id: string;
  loan_id: string;
  period_number: number;
  due_date: string;
  principal_due: string;
  interest_due: string;
  total_due: string;
  principal_paid: string;
  interest_paid: string;
  status: string;
  paid_at: string | null;
}

export interface LoanRepaymentOut {
  id: string;
  loan_id: string;
  amount: string;
  principal_applied: string;
  interest_applied: string;
  penalties_applied: string;
  overpayment: string;
  payment_account_id: string;
  journal_entry_id: string;
  posted_by: string;
  narration: string | null;
  idempotency_key: string;
  created_at: string;
}

export interface StatementLineOut {
  date: string;
  line_type: string;
  description: string;
  debit: string;
  credit: string;
  running_balance: string;
}

export interface LoanStatementOut {
  loan_id: string;
  from_date: string | null;
  to_date: string | null;
  lines: StatementLineOut[];
}
```

- [ ] **Step 3: Run `pnpm --filter @sacco/schemas test -- credit` → PASS.**

> The 3d-2 `loanApplicationSchema` test fixtures (`describe("loanApplicationSchema")` and `describe("application + guarantor schemas (3d-2)")`) submit **without** `disbursement_account_id` and expect success — making the field required breaks them. **Fix:** add `disbursement_account_id: "550e8400-e29b-41d4-a716-446655440002"` to both the `ok` fixture and the 3d-2 `base` fixture. (Their negative cases still hold.)

- [ ] **Step 4: Run full schemas suite + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
git add admin/packages/schemas/src/credit.ts admin/packages/schemas/src/__tests__/credit.test.ts
git commit -m "feat(portal): loan read types + require disbursement_account_id

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Application form correction — GL account + restricted destinations

**Files:**
- Modify: `app/(tenant-authed)/credit/applications/new/_components/CreateApplicationForm.tsx`
- Modify: `app/(tenant-authed)/credit/applications/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/CreateApplicationForm.test.tsx`

**Interfaces:**
- Consumes: `loanApplicationSchema`, `resources.ledger.listAccounts`.
- Produces: `CreateApplicationForm` now takes `glAccounts: GlAccountOption[]` (`{ id; code; name; account_type }`).

- [ ] **Step 1: Update the test** — add `glAccounts` to the render and assert the payload includes `disbursement_account_id`. In `CreateApplicationForm.test.tsx`:
  - Add `const GL = "550e8400-e29b-41d4-a716-446655440050"; const glAccounts = [{ id: GL, code: "1010", name: "Cash in Hand", account_type: "asset" }];` and pass `glAccounts={glAccounts}` to `<CreateApplicationForm>`.
  - In the success case, after picking product/member/amount/term/purpose, also pick the GL account: `await userEvent.click(screen.getByLabelText(/disbursement account/i)); await userEvent.click(await screen.findByRole("option", { name: /Cash in Hand/ }));` and assert `createApplication` called with `expect.objectContaining({ disbursement_account_id: GL, disbursement_destination: "cash" })`.
  - Change the default-destination expectation: the form now defaults `disbursement_destination` to `"cash"`.

> Run it now → FAIL (prop + field missing).

- [ ] **Step 2: Edit `CreateApplicationForm.tsx`:**
  - Add the `GlAccountOption` export interface (`{ id: string; code: string; name: string; account_type: string }`) and the `glAccounts: GlAccountOption[]` prop.
  - `defaultValues`: set `disbursement_destination: "cash"` and add `disbursement_account_id: ""`.
  - Restrict the destination `<Select>` to two items: `<SelectItem value="cash">Cash</SelectItem>` and `<SelectItem value="internal_gl">Internal GL</SelectItem>` (remove member_savings).
  - Add a GL-account `<FormField name="disbursement_account_id" label="Disbursement account" required>` rendering a `<Select>` mapping `glAccounts` → `<SelectItem value={a.id}>{a.code} — {a.name}</SelectItem>` (value = account **id**).

- [ ] **Step 3: Edit `new/page.tsx`** — also fetch `resources.ledger.listAccounts({})` (cast `{ data?: GlAccountOption[] }`) and pass `glAccounts={accounts ?? []}` to the form. Import `GlAccountOption` from the form module.

- [ ] **Step 4: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/CreateApplicationForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/applications/new/" admin/apps/portal/src/__tests__/tenant-credit/CreateApplicationForm.test.tsx
git commit -m "feat(portal): application form — required disbursement GL account

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Disburse action on the approved application

**Files:**
- Create: `app/(tenant-authed)/credit/applications/[id]/_components/DisburseButton.tsx`
- Modify: `app/(tenant-authed)/credit/applications/[id]/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/DisburseButton.test.tsx`

**Interfaces:**
- Consumes: `LoanOut`, `resources.credit.disburse`.
- Produces: `<DisburseButton applicationId={string} />` (client).

- [ ] **Step 1: Test (failing)** — mock `next/navigation` (`push`), `useAuth` (`resources.credit.disburse`). Render in `<QueryClientProvider>` + `<Toaster>`. Click "Disburse" → `<ConfirmDialog>` → confirm (button name "Disburse") → `disburse("a1", { idempotency_key: expect.any(String) })`; on `{ data: { id: "l9" } }` → toast "Loan disbursed" and `push("/credit/loans/l9")`.

```tsx
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
const disburse = vi.fn();
vi.mock("@/auth/use-auth", () => ({ useAuth: () => ({ resources: { credit: { disburse } } }) }));
// …click "Disburse" twice (open + confirm), assert disburse called and push("/credit/loans/l9")
```

- [ ] **Step 2: Implement `DisburseButton.tsx`** (client) — `useState` for `open` + a fresh `idemKey = useState(() => crypto.randomUUID())`. `useTypedMutation<LoanOut, void>` calling `resources.credit.disburse(applicationId, { idempotency_key: idemKey })` cast `{ data?: LoanOut; error? }` (throw on error). onSuccess: `toast.success("Loan disbursed")` + `router.push(\`/credit/loans/${data.id}\`)`. onError: `apiErrorMessage` toast (covers member_savings/not-approved 400s). Render `<Button onClick={() => setOpen(true)}>Disburse</Button>` + `<ConfirmDialog open onOpenChange title="Disburse loan" description="This creates the loan and posts the disbursement. This cannot be undone." confirmLabel="Disburse" busy={mutation.isPending} onConfirm={() => mutation.mutate()} />`.

- [ ] **Step 3: Wire into `applications/[id]/page.tsx`** — import `DisburseButton`; in the header actions area, render it when `application.status === "approved"`:
```tsx
{application.status === "approved" ? <DisburseButton applicationId={id} /> : null}
```
(Place beside the `<StatusBadge>`; the pending banner/actions block is unchanged.)

- [ ] **Step 4: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/DisburseButton
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/applications/[id]/" admin/apps/portal/src/__tests__/tenant-credit/DisburseButton.test.tsx
git commit -m "feat(portal): disburse approved application into a loan

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Loans list — `<LoansTable>` + `/credit/loans` + nav link

> Clone the 3d-2 `ApplicationsTable` + page (client-join member names).

**Files:**
- Create: `app/(tenant-authed)/credit/loans/_components/LoansTable.tsx`, `credit/loans/page.tsx`
- Modify: `app/(tenant-authed)/credit/page.tsx` (add a **Loans** link)
- Test: `apps/portal/src/__tests__/tenant-credit/LoansTable.test.tsx`

**Interfaces:**
- Consumes: `LoanOut`, `MemberOut`, `resources.credit.listLoans`, `resources.members.list`.
- Produces: exported `LoanRow = { id; loan_reference; member_label; principal_amount; outstanding_principal; status }`.

- [ ] **Step 1: `LoansTable` test (failing)** — clone `ApplicationsTable.test.tsx`. Row: `{ id:"l1", loan_reference:"LN-202606-000001", member_label:"Ada Loan (M-0001)", principal_amount:"1000000.00", outstanding_principal:"900000.00", status:"disbursed" }`. Assert reference links to `/credit/loans/l1`; status badge "Disbursed"; empty state "No loans yet".

- [ ] **Step 2: Implement `LoansTable.tsx`** — clone `ApplicationsTable`. Export `LoanRow`. `id="loans"`. Columns: **Reference** → `<Link href={\`/credit/loans/${row.original.id}\`} className="font-medium text-[var(--text-link)] hover:underline">{row.original.loan_reference}</Link>`; **Member** (`member_label`); **Principal** → `<Money amount={row.original.principal_amount} />`; **Outstanding** → `<Money amount={row.original.outstanding_principal} />`; **Status** → `<StatusBadge entity="loan" status={row.original.status} />`. Empty `{ title: "No loans yet", description: "Disburse an approved application to create a loan." }`.

- [ ] **Step 3: Implement `credit/loans/page.tsx`** (server) — Promise.all `credit.listLoans({})` + `members.list({})`; build `memberById`; map to `LoanRow[]` (`member_label = m ? \`${m.full_name} (${m.member_number})\` : a.member_id`). `<h1>Loans</h1>` + a `<Button asChild variant="secondary"><Link href="/credit">Products</Link></Button>`. `<LoansTable rows={rows} />`. `export const metadata = { title: "Loans" }`.

- [ ] **Step 4: Add a Loans link** to `credit/page.tsx` header — add `<Button asChild variant="secondary"><Link href="/credit/loans">Loans</Link></Button>` next to the Applications link.

- [ ] **Step 5: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/LoansTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/loans/page.tsx" "admin/apps/portal/app/(tenant-authed)/credit/loans/_components/LoansTable.tsx" "admin/apps/portal/app/(tenant-authed)/credit/page.tsx" admin/apps/portal/src/__tests__/tenant-credit/LoansTable.test.tsx
git commit -m "feat(portal): SACCO loans list + nav

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Schedule + Repayments tables

> Clone the 3b/3c in-memory `TransactionsTable` pattern.

**Files:**
- Create: `app/(tenant-authed)/credit/loans/[id]/_components/ScheduleTable.tsx`, `_components/RepaymentsTable.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/{ScheduleTable,RepaymentsTable}.test.tsx`

**Interfaces:**
- Consumes: `LoanInstallmentOut`, `LoanRepaymentOut`.

- [ ] **Step 1: `ScheduleTable` test (failing)** — clone the shares `TransactionsTable.test.tsx` pattern (mock `useTableUrlState` + `next/navigation`; `<TenantCurrencyProvider>`). `TData = LoanInstallmentOut`. One row (use the Task 1 `inst` shape). Assert the total-due amount renders and the empty state "No schedule yet".

- [ ] **Step 2: Implement `ScheduleTable.tsx`** (client) — in-memory `<DataTable id="loan-schedule">`. Columns: **#** → `<Count value={row.original.period_number} />`; **Due** → `<FormattedDate value={row.original.due_date} />`; **Principal due** → `<Money amount={row.original.principal_due} />`; **Interest due** → `<Money amount={row.original.interest_due} />`; **Total due** → `<Money amount={row.original.total_due} />`; **Status** → `row.original.status`. Empty `{ title: "No schedule yet", description: "The repayment schedule appears here once the loan is disbursed." }`. Import `Count`, `FormattedDate`, `Money`.

- [ ] **Step 3: `RepaymentsTable` test (failing)** — `TData = LoanRepaymentOut` (Task 1 `rep` shape). Assert the amount renders + empty state "No repayments yet".

- [ ] **Step 4: Implement `RepaymentsTable.tsx`** (client) — in-memory `<DataTable id="loan-repayments">`. Columns: **Date** → `<FormattedDate value={row.original.created_at} />`; **Amount** → `<Money amount={row.original.amount} />`; **Principal** → `<Money amount={row.original.principal_applied} />`; **Interest** → `<Money amount={row.original.interest_applied} />`; **Penalties** → `<Money amount={row.original.penalties_applied} />`. Empty `{ title: "No repayments yet", description: "Recorded repayments appear here." }`.

- [ ] **Step 5: Run both tests + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/ScheduleTable tenant-credit/RepaymentsTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/ScheduleTable.tsx" "admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/RepaymentsTable.tsx" admin/apps/portal/src/__tests__/tenant-credit/ScheduleTable.test.tsx admin/apps/portal/src/__tests__/tenant-credit/RepaymentsTable.test.tsx
git commit -m "feat(portal): loan schedule + repayments tables

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Statement table + PDF proxy route

**Files:**
- Create: `app/(tenant-authed)/credit/loans/[id]/_components/StatementTable.tsx`
- Create: `app/api/credit/loans/[id]/statement-pdf/route.ts`
- Test: `apps/portal/src/__tests__/tenant-credit/StatementTable.test.tsx`, `apps/portal/src/__tests__/tenant-credit/statement-pdf-route.test.ts`

**Interfaces:**
- Consumes: `StatementLineOut`; `getServerAccessToken`, `getServerTenantSlug` (from `@/auth/server-helpers`).

- [ ] **Step 1: `StatementTable` test (failing)** — `TData = StatementLineOut` (Task 1 `st.lines[0]` shape). Render in `<TenantCurrencyProvider>`. Assert the description "Disbursed" renders and the empty state "No statement lines yet". (Plain table — mock `useTableUrlState` + `next/navigation` like the other table tests.)

- [ ] **Step 2: Implement `StatementTable.tsx`** (client) — in-memory `<DataTable id="loan-statement">`, `TData = StatementLineOut`. Columns: **Date** → `<FormattedDate value={row.original.date} />`; **Type** (`line_type`); **Description** (`description`); **Debit** → `<Money amount={row.original.debit} />`; **Credit** → `<Money amount={row.original.credit} />`; **Balance** → `<Money amount={row.original.running_balance} />`. Empty `{ title: "No statement lines yet", description: "Statement entries appear here." }`. (Lines have no id — set `getRowId` via index is unnecessary for in-memory render; the `<DataTable>` `TData` contract wants `{ id: string }` — supply a synthetic `id` by mapping lines to `{ ...line, id: \`${i}\` }` in the component before passing to the table, OR pass `getRowId={(_r, i) => String(i)}` if `<DataTable>` supports it. Verify the `<DataTable>` row-id requirement at execution; simplest: map to add an `id` field locally and use a `StatementRow = StatementLineOut & { id: string }`.)

- [ ] **Step 3: PDF route test (failing)** — clone `tenant-invoice-pdf-route.test.ts`:

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
const ctx = (id: string) => ({ params: Promise.resolve({ id }) });

describe("GET /api/credit/loans/[id]/statement-pdf", () => {
  it("401s without a tenant session", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    getServerTenantSlug.mockResolvedValue("alpha");
    const { GET } = await import("../../../app/api/credit/loans/[id]/statement-pdf/route");
    const res = await GET(new Request("http://localhost/api/credit/loans/l1/statement-pdf"), ctx("l1"));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("proxies with the tenant bearer + X-Tenant-Slug", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "tenant-access" });
    getServerTenantSlug.mockResolvedValue("alpha");
    fetchMock.mockResolvedValue({ ok: true, status: 200, arrayBuffer: async () => new Uint8Array([37,80,68,70]).buffer });
    const { GET } = await import("../../../app/api/credit/loans/[id]/statement-pdf/route");
    const res = await GET(new Request("http://localhost/api/credit/loans/l1/statement-pdf"), ctx("l1"));
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("application/pdf");
    const [url, init] = fetchMock.mock.calls[0] as [string, { headers?: Record<string, string> }];
    expect(String(url)).toContain("/credit/loans/l1/statement.pdf");
    expect(init.headers?.["Authorization"]).toBe("Bearer tenant-access");
    expect(init.headers?.["X-Tenant-Slug"]).toBe("alpha");
  });
});
```

- [ ] **Step 4: Implement `statement-pdf/route.ts`** (clone the invoice route):

```ts
// admin/apps/portal/app/api/credit/loans/[id]/statement-pdf/route.ts
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
  const r = await fetch(`${API_BASE}/credit/loans/${id}/statement.pdf`, {
    headers: { Authorization: `Bearer ${accessToken}`, "X-Tenant-Slug": slug },
    cache: "no-store",
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Failed to load statement PDF" }, { status: r.status });
  }
  const body = await r.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `inline; filename="loan-statement-${id}.pdf"`,
    },
  });
}
```

- [ ] **Step 5: Run both tests + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/StatementTable tenant-credit/statement-pdf-route
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/StatementTable.tsx" "admin/apps/portal/app/api/credit/loans/" admin/apps/portal/src/__tests__/tenant-credit/StatementTable.test.tsx admin/apps/portal/src/__tests__/tenant-credit/statement-pdf-route.test.ts
git commit -m "feat(portal): loan statement table + PDF proxy route

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Record repayment

> Mirror the 3b savings `AccountActions` deposit (direct form dialog).

**Files:**
- Create: `app/(tenant-authed)/credit/loans/[id]/_components/RecordRepaymentButton.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/RecordRepaymentButton.test.tsx`

**Interfaces:**
- Consumes: `loanRepaymentSchema`/`LoanRepaymentInput`, `resources.credit.recordRepayment`.
- Produces: `<RecordRepaymentButton loanId={string} glAccounts={GlAccountOption[]} />` (client). `GlAccountOption = { id; code; name; account_type }`.

- [ ] **Step 1: Test (failing)** — mock `next/navigation` (`refresh`) + `useAuth` (`resources.credit.recordRepayment`). Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`. Props `loanId="l1"`, `glAccounts=[{ id: "550e8400-e29b-41d4-a716-446655440050", code:"1010", name:"Cash in Hand", account_type:"asset" }]`. Click "Record repayment" → fill amount, pick GL account → submit → `recordRepayment("l1", expect.objectContaining({ amount:"95000", payment_account_id:"550e8400-...050" }))`; toast "Repayment recorded".

- [ ] **Step 2: Implement `RecordRepaymentButton.tsx`** (client) — mirror the savings deposit form-dialog. `useForm<LoanRepaymentInput>({ resolver: zodResolver(loanRepaymentSchema), defaultValues: { amount:"", payment_account_id:"", narration:"", idempotency_key: <fresh uuid> } })`. A `<Button onClick>` opens a `<Dialog>` with a `<form>`: amount (`<MoneyInput>`), payment_account_id (`<Select>` from `glAccounts` → `{code} — {name}`, value = id), narration (`<Textarea>`). `useTypedMutation<LoanRepaymentOut, LoanRepaymentInput>` → `resources.credit.recordRepayment(loanId, values)` cast `{ data?, error? }`; onSuccess close, `toast.success("Repayment recorded")`, `router.refresh()`; onError `apiErrorMessage` (covers overpayment 400). **Direct** (no maker-checker). `savings_account_id` omitted.

- [ ] **Step 3: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/RecordRepaymentButton
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/RecordRepaymentButton.tsx" admin/apps/portal/src/__tests__/tenant-credit/RecordRepaymentButton.test.tsx
git commit -m "feat(portal): record loan repayment

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Loan detail page assembly

**Files:**
- Create: `app/(tenant-authed)/credit/loans/[id]/page.tsx`

**Interfaces:**
- Consumes: `LoanOut`, `LoanInstallmentOut`, `LoanRepaymentOut`, `LoanStatementOut`, `MemberOut`; `resources.credit.{getLoan,getSchedule,listRepayments,getStatement}`, `resources.members.list`, `resources.ledger.listAccounts`; `<StatusBadge>`, `<Card>`, `<Money>`, `<Percentage>`, `<Count>`, `<FormattedDate>`, `<Button>`, `<Link>`; `ScheduleTable`, `RepaymentsTable`, `StatementTable`, `RecordRepaymentButton`, `GlAccountOption`.

- [ ] **Step 1: Implement `[id]/page.tsx`** (server). `const { id } = await params;`. `credit.getLoan(id)` cast `{ data?: LoanOut }`; `notFound()` if absent. Promise.all: `credit.getSchedule(id)` (`{ data?: LoanInstallmentOut[] }`), `credit.listRepayments(id)` (`{ data?: LoanRepaymentOut[] }`), `credit.getStatement(id)` (`{ data?: LoanStatementOut }`), `members.list({})` (`{ data?: MemberOut[] }`), `ledger.listAccounts({})` (`{ data?: GlAccountOption[] }`).
  - `memberLabel` from the member map.
  - Header: `<h1>{loan.loan_reference}</h1>` + `<StatusBadge entity="loan" status={loan.status} />` + `<RecordRepaymentButton loanId={id} glAccounts={accounts ?? []} />`.
  - **Balances** `<Card>`: outstanding principal (`<Money>`, emphasised), accrued interest (`<Money>`), accrued penalties (`<Money>`).
  - **Terms** `<Card>`: member (`memberLabel`), principal (`<Money>`), interest rate (`<Percentage value={loan.annual_interest_rate} />`), method, frequency, term (`<Count value={loan.term_periods} />`), destination, disbursed at / first repayment due / maturity (`<FormattedDate>` with `?? "—"` guards).
  - `<h2>Schedule</h2>` + `<ScheduleTable rows={schedule ?? []} />`.
  - `<h2>Repayments</h2>` + `<RepaymentsTable rows={repayments ?? []} />`.
  - `<div className="flex items-center justify-between"><h2>Statement</h2><Button asChild variant="secondary"><a href={\`/api/credit/loans/${id}/statement-pdf\`} target="_blank" rel="noopener noreferrer">Download PDF</a></Button></div>` + `<StatementTable rows={statement?.lines ?? []} />`.
  - No `<AuditBar>`. `export const metadata = { title: "Loan" }`.

- [ ] **Step 2: typecheck + lint (no unit test — server page; covered by component tests); commit.**

```bash
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/page.tsx"
git commit -m "feat(portal): loan detail (balances + schedule + repayments + statement)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Member-detail Loans section

> Clone the 3c `MemberSharesSection`.

**Files:**
- Create: `app/(tenant-authed)/members/[id]/_components/MemberLoansSection.tsx`
- Modify: `app/(tenant-authed)/members/[id]/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/MemberLoansSection.test.tsx`

**Interfaces:**
- Consumes: `LoanOut`, `resources.credit.listLoans`.

- [ ] **Step 1: Test (failing)** — clone `MemberSharesSection.test.tsx`. `MemberLoansSection` takes `{ loans: LoanOut[] }`. Assert a loan row links to `/credit/loans/{id}`, shows the reference + a `<StatusBadge entity="loan">` and outstanding `<Money>`; empty state "No loans." when `loans=[]`.

- [ ] **Step 2: Implement `MemberLoansSection.tsx`** (server component, no `"use client"`) — a `<Card>` titled "Loans". For each loan: `loan_reference` + `<StatusBadge entity="loan" status={l.status} />` + outstanding `<Money amount={l.outstanding_principal} />` + `<Link href={\`/credit/loans/${l.id}\`}>View</Link>`. Empty → "No loans."

- [ ] **Step 3: Modify `members/[id]/page.tsx`** — add `resources.credit.listLoans({ member_id: id })` cast `{ data?: LoanOut[] }` to the existing `Promise.all`; render `<MemberLoansSection loans={loans ?? []} />` below `<MemberSharesSection>`.

- [ ] **Step 4: Run the section test + the existing member/savings/shares tests (no regression) + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-members tenant-savings tenant-shares tenant-credit/MemberLoansSection
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/members/[id]/" admin/apps/portal/src/__tests__/tenant-credit/MemberLoansSection.test.tsx
git commit -m "feat(portal): member-detail loans section

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: Verification + PR

- [ ] **Step 1: Package + portal gate**:
```bash
cd admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test delta over the 227 (3d-2) baseline.

- [ ] **Step 2: Contract spot-checks**:
  - [ ] No backend changes: `git diff --name-only main...HEAD | grep -E '^app/'` empty; `grep -E '^alembic/'` empty.
  - [ ] No api-client changes: `git diff --name-only main...HEAD | grep 'api-client'` empty.
  - [ ] Changes under `admin/` + `docs/` only.
  - [ ] Loan status via `entity="loan"` (no new StatusBadge entity added): `git diff main...HEAD -- admin/packages/ui` empty.

- [ ] **Step 3: Final holistic review** — application form requires a GL account + cash/internal_gl; approved application shows Disburse → creates loan → redirects; loans list (member join, status); loan detail shows balances + terms + schedule + repayments + statement + Download PDF; record repayment refreshes; member detail shows loans. No AuditBar; tenant-auth only.

- [ ] **Step 4: Push + PR** (base `main`):
```bash
git push -u origin feat/sacco-portal/04c-credit-loans
gh pr create --base main --title "feat(portal): SACCO admin — Credit loans servicing (Phase 3d-3)" --body "$(cat <<'EOF'
## Summary
- Third **Credit** sub-module (Phase 3d-3 of 4): loans servicing — disburse → loan → balances/schedule/repayments/statement → record repayment.
- **Correction (prerequisite for disburse):** the 3d-2 application form now captures a required **disbursement GL account** and restricts the destination to **cash / internal_gl** (the backend disburse service does not support member_savings in v1 and requires the account). `loanApplicationSchema.disbursement_account_id` is now required.
- **Disburse** acts on an approved application (`POST /credit/loans/{application_id}/disburse`) → creates the loan → redirects to it.
- **Loans list** (client-join member names, `StatusBadge entity="loan"`) + **loan detail** (balances, terms, schedule, repayments, statement). **Record repayment** is direct (201).
- **Statement**: on-page table **+ Download PDF** via a Next API-route proxy (clones the invoice-PDF route — server-side authed fetch).
- **Member detail** gains a **Loans** section. New loan read types in `@sacco/schemas`.
- **No backend or api-client changes.**

## Test plan
- `@sacco/schemas`, `@sacco/api-client`, `@sacco/portal` test/typecheck/lint green.

> Phase 3d: products (3d-1) → applications+guarantors (3d-2) → loans servicing (this) → workout+payroll (3d-4).
> CI note: Lint fails environmentally on this repo (runner-queue issue); reproduced clean locally.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** read types + schema fix → T1; application-form correction → T2; disburse → T3; loans list + nav → T4; schedule/repayments tables → T5; statement table + PDF route → T6; record repayment → T7; detail assembly → T8; member section → T9; verify/PR → T10.
- **Type consistency:** `LoanOut`/`LoanInstallmentOut`/`LoanRepaymentOut`/`StatementLineOut`/`LoanStatementOut` (T1) consumed by T4–T9; `LoanRow` (T4) page-built; `GlAccountOption` reused (T2 form, T7 repayment, T8 page). Loan status → `entity="loan"`. `disbursement_account_id` required forces the T1 fixture fix in the existing 3d-2 tests (noted).
- **Verify-at-execution:** `<DataTable>` `TData extends { id: string }` — statement lines lack an id, so map to add a synthetic `id` (T6 Step 2); `<ConfirmDialog>` props confirmed (3d-2); PDF route mirrors the invoice route + test (verified); `getServerAccessToken("tenant")` → `{ accessToken }` + `getServerTenantSlug()` (verified); Next 15 `params` Promise; `<FormattedDate>` import from `@sacco/ui`.
- **No backend tests** — no backend change.
