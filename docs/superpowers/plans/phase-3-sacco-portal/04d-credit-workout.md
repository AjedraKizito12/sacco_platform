# SACCO Admin Portal — Credit Workout + Payroll (Phase 3d-4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-21):** background subagents can't get Edit approval; run **inline**. **Confirm typecheck PASSES before committing** (SP20 lesson). No backend tests (no backend change). Portal/package tests via `pnpm --filter` from `admin/`.
> **Test gotchas (carry-over):** `<Money>` exposes `data-amount`, `<Count>` `data-value`; checkboxes inside a Radix Dialog need `fireEvent.click(getByRole("checkbox"))`; uuid-typed schema fields need real UUID fixtures; `<DataTable>` `TData` must extend `{ id: string }`.

**Goal:** The final credit sub-module — loan workout (write-off / recover / restructure) on the loan detail page, plus payroll batches (JSON create + detail + reject).

**Architecture:** Add a `payroll_batch` StatusBadge entity, fix the stale restructuring enum + add workout/payroll read & input schemas, then a `<LoanWorkoutActions>` + restructurings table on the 3d-3 loan detail, and payroll create/detail screens under `app/(tenant-authed)/credit/payroll/*`. Server-fetch via `getTenantPageContext()`, RHF/Zod form dialogs, `<ConfirmDialog>`, `<StatusBadge>`. Clones the 3a–3d-3 pattern.

**Tech Stack:** Next.js 15, React 19, TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library. No Python changes.

## Global Constraints

- **Branch:** `feat/sacco-portal/04d-credit-workout`, off `main` (no PR stacking).
- **No backend changes, no api-client changes.** `resources.credit.{writeOff,recover,restructure,listRestructurings,createPayrollBatch,getPayrollBatch,rejectPayrollBatch}`, `resources.members.list`, `resources.ledger.listAccounts` exist (cast `{ data?, error? }`).
- **Write-off** (201 → `{direct, approval_request_id?, journal_entry_id?}`) is **dual**: `direct=true` posts immediately; `direct=false` created a quorum-2 approval. **Restructure** (202 → `{approval_request_id}`) is always maker-checker (quorum 2). **Recover** (201) is direct, written-off only.
- **Checker side deferred** — write-off/restructure create generic tenant approvals (no inbox yet); 3d-4 only creates them.
- **Restructuring types (backend authoritative):** `term_extension`, `payment_holiday`. **Payroll statuses:** `pending_review`, `applied`, `rejected`.
- **Money** → `<Money>`/`<MoneyInput>`; **int** (`periods_added`, row counts) → `intString` + `<Input inputMode="numeric">` / `<Count>`. Idempotency key = fresh UUID per form instance (contract L). Domain status → `<StatusBadge entity status />`.
- **No `<AuditBar>`**, tenant-auth gating only. **DRY/YAGNI/TDD, frequent commits.** Typecheck before each commit.

---

## Task 1: `@sacco/ui` — `payroll_batch` StatusBadge entity

**Files:**
- Modify: `admin/packages/ui/src/components/StatusBadge/status-maps.ts`
- Test: `admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx`

**Interfaces:**
- Produces: `<StatusBadge entity="payroll_batch" status=… />`.

- [ ] **Step 1: Failing test** — append to `StatusBadge.test.tsx`:

```tsx
it("renders a payroll_batch status", () => {
  render(<StatusBadge entity="payroll_batch" status="pending_review" />);
  expect(screen.getByText("Pending review")).toBeInTheDocument();
});
```

Run: `cd admin && pnpm --filter @sacco/ui test -- StatusBadge` → FAIL.

- [ ] **Step 2: Add the entity** to `status-maps.ts`: extend `StatusEntity` with `| "payroll_batch"`, add the map, register in `ENTITY_MAPS`:

```ts
export const PAYROLL_BATCH_STATUS: StatusMap = {
  pending_review: { variant: "info", label: "Pending review" },
  applied: { variant: "success", label: "Applied" },
  rejected: { variant: "danger", label: "Rejected" },
};
```
Add `payroll_batch: PAYROLL_BATCH_STATUS,` to `ENTITY_MAPS`.

- [ ] **Step 3: Run test → PASS; typecheck + lint + commit.**

```bash
pnpm --filter @sacco/ui test -- StatusBadge && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
git add admin/packages/ui/src/components/StatusBadge/status-maps.ts admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx
git commit -m "feat(portal): payroll_batch StatusBadge entity

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `@sacco/schemas` — fix restructuring enum + workout/payroll types

**Files:**
- Modify: `admin/packages/schemas/src/credit.ts`
- Test: `admin/packages/schemas/src/__tests__/credit.test.ts`

**Interfaces:**
- Produces: corrected `restructuringTypeSchema`; `loanRestructureSchema.periods_added` as `intString`; `payrollRowSchema`/`payrollBatchSchema` (+ `PayrollBatchInput`); read types `WriteOffOut`, `LoanRecoveryOut`, `RestructuringOut`, `PayrollBatchOut`.

- [ ] **Step 1: Failing test** — append to `credit.test.ts` (add the new imports to the existing import block):

```ts
import {
  payrollBatchSchema,
  restructuringTypeSchema,
  type PayrollBatchOut,
  type RestructuringOut,
  type WriteOffOut,
  type LoanRecoveryOut,
} from "../credit";

describe("workout + payroll schemas (3d-4)", () => {
  it("restructuring type matches the backend (term_extension/payment_holiday)", () => {
    expect(restructuringTypeSchema.safeParse("payment_holiday").success).toBe(true);
    expect(restructuringTypeSchema.safeParse("term_extension").success).toBe(true);
    expect(restructuringTypeSchema.safeParse("principal_holiday").success).toBe(false);
  });
  it("loanRestructureSchema accepts an integer-string periods_added", () => {
    const ok = {
      restructuring_type: "term_extension",
      periods_added: "3",
      reason: "Borrower lost job, extending the term to ease repayment",
      idempotency_key: "1234567890ab",
    };
    expect(loanRestructureSchema.safeParse(ok).success).toBe(true);
    expect(loanRestructureSchema.safeParse({ ...ok, periods_added: "x" }).success).toBe(false);
  });
  it("payrollBatchSchema requires at least one row", () => {
    const row = { member_id: "550e8400-e29b-41d4-a716-446655440001", amount: "50000" };
    const cl = "550e8400-e29b-41d4-a716-446655440099";
    expect(
      payrollBatchSchema.safeParse({ rows: [], clearing_account_id: cl, idempotency_key: "1234567890ab" }).success,
    ).toBe(false);
    expect(
      payrollBatchSchema.safeParse({ rows: [row], clearing_account_id: cl, idempotency_key: "1234567890ab" }).success,
    ).toBe(true);
  });
  it("read types are structurally usable", () => {
    const w: WriteOffOut = { direct: true, approval_request_id: null, journal_entry_id: "j1" };
    const r: LoanRecoveryOut = { journal_entry_id: "j2" };
    const rs: RestructuringOut = {
      id: "rs1", loan_id: "l1", restructuring_type: "term_extension", periods_added: 3,
      new_term_periods: 15, new_maturity_date: "2027-09-01", reason: "x", executed_at: "2026-06-21T00:00:00Z",
    };
    const pb: PayrollBatchOut = {
      id: "b1", reference: "PB-202606-0001", status: "pending_review", total_rows: 2,
      matched_rows: 2, unmatched_rows: 0, total_amount: "100000.0000", source_format: "json",
      approval_request_id: null,
    };
    expect(w.direct).toBe(true);
    expect(r.journal_entry_id).toBe("j2");
    expect(rs.periods_added).toBe(3);
    expect(pb.status).toBe("pending_review");
  });
});
```

> `loanRestructureSchema` is already imported at the top of the test file (3d-1). Run → FAIL.

- [ ] **Step 2: Edit `credit.ts`** — fix the enum and the term field:

```ts
export const restructuringTypeSchema = z.enum([
  "term_extension",
  "payment_holiday",
]);
```
In `loanRestructureSchema`, change `periods_added` to `intString({ min: 1 })` (remove the old `z.number().int().min(1).max(120)`). (`intString` is already imported.)

- [ ] **Step 3: Add the payroll schema** (after `loanProductPatchSchema` or near the other schemas):

```ts
export const payrollRowSchema = z.object({
  member_id: uuid,
  amount: moneyString({ min: "0.01" }),
});

export const payrollBatchSchema = z.object({
  rows: z.array(payrollRowSchema).min(1, "Add at least one row"),
  clearing_account_id: uuid,
  idempotency_key: idempotencyKey,
});
```

- [ ] **Step 4: Add inferred + read types** (near the other `export type` lines / interfaces):

```ts
export type PayrollRowInput = z.infer<typeof payrollRowSchema>;
export type PayrollBatchInput = z.infer<typeof payrollBatchSchema>;

export interface WriteOffOut {
  direct: boolean;
  approval_request_id: string | null;
  journal_entry_id: string | null;
}

export interface LoanRecoveryOut {
  journal_entry_id: string;
}

export interface RestructuringOut {
  id: string;
  loan_id: string;
  restructuring_type: string;
  periods_added: number;
  new_term_periods: number;
  new_maturity_date: string;
  reason: string;
  executed_at: string;
}

export interface PayrollBatchOut {
  id: string;
  reference: string;
  status: string;
  total_rows: number;
  matched_rows: number;
  unmatched_rows: number;
  total_amount: string;
  source_format: string;
  approval_request_id: string | null;
}
```

- [ ] **Step 5: Run full schemas suite + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
git add admin/packages/schemas/src/credit.ts admin/packages/schemas/src/__tests__/credit.test.ts
git commit -m "feat(portal): fix restructuring enum + workout/payroll schemas

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `<LoanWorkoutActions>` — write-off / restructure / recover

**Files:**
- Create: `app/(tenant-authed)/credit/loans/[id]/_components/LoanWorkoutActions.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/LoanWorkoutActions.test.tsx`

**Interfaces:**
- Consumes: `loanWriteOffSchema`/`LoanWriteOffInput`, `loanRestructureSchema`/`LoanRestructureInput`, `loanRecoverySchema`/`LoanRecoveryInput`, `WriteOffOut`, `resources.credit.{writeOff,restructure,recover}`.
- Produces: `<LoanWorkoutActions loanId={string} status={string} glAccounts={GlAccountOption[]} />` (client). `GlAccountOption = { id; code; name; account_type }`.

- [ ] **Step 1: Test (failing)** — mock `next/navigation` (`refresh`) + `useAuth` (`resources.credit.{writeOff,restructure,recover}`). Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`. `glAccounts=[{ id:"g1", code:"5100", name:"Loan Loss", account_type:"expense" }]`. Cases:
  - **status="disbursed": write-off direct** → click "Write off" → fill amount + reason → submit → `writeOff("l1", expect.objectContaining({ amount:"500000" }))`; mock resolves `{ data: { direct: true, approval_request_id: null, journal_entry_id: "j1" } }`; toast "Loan written off".
  - **status="disbursed": restructure** → click "Restructure" → pick type term_extension, periods "3", reason (≥20) → submit → `restructure("l1", expect.objectContaining({ restructuring_type:"term_extension", periods_added:"3" }))`; toast /pending approval/.
  - **status="written_off": recover shown** → render with `status="written_off"`; assert no "Write off" button, a "Recover" button present; click → amount + reason → submit → `recover("l1", expect.objectContaining({ amount:"100000" }))`; toast "Recovery posted".

- [ ] **Step 2: Implement `LoanWorkoutActions.tsx`** (client). Three `useState` open flags (`writeOffOpen`, `restructureOpen`, `recoverOpen`) + three fresh idempotency keys. Three RHF forms (`zodResolver` for each schema). `isWrittenOff = status === "written_off"`.
  - Buttons: when `isWrittenOff` → `<Button onClick={()=>setRecoverOpen(true)}>Recover</Button>`; else → `<Button onClick={()=>setWriteOffOpen(true)}>Write off</Button>` + `<Button variant="secondary" onClick={()=>setRestructureOpen(true)}>Restructure</Button>`.
  - **Write-off** `useTypedMutation<WriteOffOut, LoanWriteOffInput>` → build body, drop empty `loan_loss_account_code`, `resources.credit.writeOff(loanId, body)` cast `{ data?: WriteOffOut; error? }`; onSuccess: `toast.success(data.direct ? "Loan written off" : "Write-off requested — pending approval (2 required)")`, close, `router.refresh()`; onError `apiErrorMessage`. Form dialog fields: amount (`<MoneyInput>`), reason (`<Textarea>`), loan_loss_account_code (`<Select>` from glAccounts value=code, optional). Dialog description notes: "At or above the product's write-off threshold this creates a maker-checker approval (quorum 2); otherwise it posts immediately."
  - **Restructure** `useTypedMutation<unknown, LoanRestructureInput>` → `resources.credit.restructure(loanId, values)` cast `{ data?, error? }`; onSuccess toast "Restructuring requested — pending approval (2 required)", close, refresh. Fields: restructuring_type (`<Select>`: term_extension / payment_holiday), periods_added (`<Input inputMode="numeric">`), reason (`<Textarea>`). Dialog description: "This creates a maker-checker approval (quorum 2)."
  - **Recover** `useTypedMutation<LoanRecoveryOut, LoanRecoveryInput>` → `resources.credit.recover(loanId, values)`; onSuccess toast "Recovery posted", close, refresh. Fields: amount (`<MoneyInput>`), reason (`<Textarea>`).
  - Each form dialog: `<Dialog open onOpenChange>` + `<DialogContent><DialogHeader><DialogTitle/><DialogDescription/></DialogHeader><form .../></DialogContent>`. Fresh idempotency_key in defaultValues.

- [ ] **Step 3: Run test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/LoanWorkoutActions
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/LoanWorkoutActions.tsx" admin/apps/portal/src/__tests__/tenant-credit/LoanWorkoutActions.test.tsx
git commit -m "feat(portal): loan workout actions (write-off/restructure/recover)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Restructurings table + wire workout into loan detail

**Files:**
- Create: `app/(tenant-authed)/credit/loans/[id]/_components/RestructuringsTable.tsx`
- Modify: `app/(tenant-authed)/credit/loans/[id]/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/RestructuringsTable.test.tsx`

**Interfaces:**
- Consumes: `RestructuringOut`, `resources.credit.listRestructurings`, `<LoanWorkoutActions>`.

- [ ] **Step 1: `RestructuringsTable` test (failing)** — clone the 3d-3 `ScheduleTable.test.tsx` pattern (mock `useTableUrlState` + `next/navigation`; `<TenantCurrencyProvider>`). `TData = RestructuringOut`. Row: `{ id:"rs1", loan_id:"l1", restructuring_type:"term_extension", periods_added:3, new_term_periods:15, new_maturity_date:"2027-09-01", reason:"x", executed_at:"2026-06-21T00:00:00Z" }`. Assert "term_extension" renders + empty state "No restructurings yet".

- [ ] **Step 2: Implement `RestructuringsTable.tsx`** (client) — in-memory `<DataTable id="loan-restructurings">`, `TData = RestructuringOut`. Columns: **Type** (`restructuring_type`); **Periods added** → `<Count value={row.original.periods_added} />`; **New term** → `<Count value={row.original.new_term_periods} />`; **New maturity** → `<FormattedDate value={row.original.new_maturity_date} />`; **Executed** → `<FormattedDate value={row.original.executed_at} />`. Empty `{ title: "No restructurings yet", description: "Approved restructurings appear here." }`. Import `Count`, `FormattedDate`.

- [ ] **Step 3: Modify `loans/[id]/page.tsx`** — add `resources.credit.listRestructurings(id)` cast `{ data?: RestructuringOut[] }` to the existing `Promise.all`. In the header actions area (next to `<RecordRepaymentButton>`), add `<LoanWorkoutActions loanId={id} status={loan.status} glAccounts={accounts ?? []} />`. After the Repayments section, add a **Restructurings** section: `<h2>Restructurings</h2>` + `<RestructuringsTable rows={restructurings ?? []} />`. Import both components + `RestructuringOut`.

- [ ] **Step 4: Run the test + the existing loan tests (no regression) + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/RestructuringsTable tenant-credit/RecordRepaymentButton
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/" admin/apps/portal/src/__tests__/tenant-credit/RestructuringsTable.test.tsx
git commit -m "feat(portal): loan restructurings table + workout actions on detail

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Payroll batch create — `<CreatePayrollBatchForm>` + `/credit/payroll/new` + nav

**Files:**
- Create: `app/(tenant-authed)/credit/payroll/new/_components/CreatePayrollBatchForm.tsx`, `credit/payroll/new/page.tsx`
- Modify: `app/(tenant-authed)/credit/page.tsx` (add a **Payroll** link)
- Test: `apps/portal/src/__tests__/tenant-credit/CreatePayrollBatchForm.test.tsx`

**Interfaces:**
- Consumes: `payrollBatchSchema`/`PayrollBatchInput`, `PayrollBatchOut`, `resources.credit.createPayrollBatch`, `resources.members.list`, `resources.ledger.listAccounts`.
- Produces: exported `MemberOption = { id; full_name; member_number }`, `GlAccountOption = { id; code; name; account_type }`.

- [ ] **Step 1: Test (failing)** — mock push + `useAuth` (`resources.credit.createPayrollBatch`). Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`. Props `members=[{id:M1,full_name:"Ada Loan",member_number:"M-0001"}]` (M1 a real uuid), `glAccounts=[{id:CL,code:"1099",name:"Payroll Clearing",account_type:"liability"}]` (CL a real uuid). The form starts with one empty row. Fill row member (Select → Ada Loan) + amount "50000"; pick clearing account; submit → `createPayrollBatch(expect.objectContaining({ clearing_account_id: CL, rows: [{ member_id: M1, amount: "50000" }] }))`; on `{ data: { id: "b9" } }` → `push("/credit/payroll/b9")`. Also assert submitting with an empty member blocks (createPayrollBatch not called).

- [ ] **Step 2: Implement `CreatePayrollBatchForm.tsx`** (client) — RHF `useForm<PayrollBatchInput>({ resolver: zodResolver(payrollBatchSchema), defaultValues: { rows: [{ member_id: "", amount: "" }], clearing_account_id: "", idempotency_key: <fresh uuid> } })` + `useFieldArray({ control, name: "rows" })`. Props `{ members: MemberOption[]; glAccounts: GlAccountOption[] }`.
  - For each `fields` row: a member `<FormField name={\`rows.${i}.member_id\`}>` (`<Select>` from members) + amount `<FormField name={\`rows.${i}.amount\`}>` (`<MoneyInput>`) + a **Remove** `<Button type="button" variant="ghost" onClick={() => remove(i)}>` (disabled when `fields.length === 1`).
  - **Add row** `<Button type="button" variant="secondary" onClick={() => append({ member_id: "", amount: "" })}>`.
  - clearing_account_id `<FormField>` (`<Select>` from glAccounts, value = id).
  - `useTypedMutation<PayrollBatchOut, PayrollBatchInput>` → `resources.credit.createPayrollBatch(values)` cast `{ data?: PayrollBatchOut; error? }`; onSuccess `toast.success("Batch created")` + `router.push(\`/credit/payroll/${data.id}\`)`; onError `apiErrorMessage`. Submit button "Create batch"; Cancel → `/credit`.

  > `<MoneyInput>` value/onValueChange/onBlur/name/ref shape (proven). `useFieldArray` row field names use template strings; FormField `name` accepts them.

- [ ] **Step 3: Implement `payroll/new/page.tsx`** (server) — `getTenantPageContext()`, Promise.all `members.list({})` + `ledger.listAccounts({})`; map to `MemberOption[]`/`GlAccountOption[]`; `<h1>New payroll batch</h1>`; `<CreatePayrollBatchForm members={…} glAccounts={…} />`.

- [ ] **Step 4: Add a Payroll link** to `credit/page.tsx` header — `<Button asChild variant="secondary"><Link href="/credit/payroll/new">Payroll</Link></Button>` next to Loans.

- [ ] **Step 5: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/CreatePayrollBatchForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/payroll/new/" "admin/apps/portal/app/(tenant-authed)/credit/page.tsx" admin/apps/portal/src/__tests__/tenant-credit/CreatePayrollBatchForm.test.tsx
git commit -m "feat(portal): SACCO payroll batch create + nav

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Payroll batch detail + reject

**Files:**
- Create: `app/(tenant-authed)/credit/payroll/[id]/page.tsx`, `_components/RejectPayrollBatchButton.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/RejectPayrollBatchButton.test.tsx`

**Interfaces:**
- Consumes: `PayrollBatchOut`, `resources.credit.{getPayrollBatch,rejectPayrollBatch}`.
- Produces: `<RejectPayrollBatchButton batchId={string} status={string} />` (client).

- [ ] **Step 1: `RejectPayrollBatchButton` test (failing)** — mock `next/navigation` (`refresh`) + `useAuth` (`resources.credit.rejectPayrollBatch`). Render in `<QueryClientProvider>` + `<Toaster>`. With `status="pending_review"`: click "Reject batch" → `<ConfirmDialog>` → confirm (button "Reject") → `rejectPayrollBatch("b1", {})`; toast "Batch rejected". With `status="applied"`: assert no "Reject batch" button.

- [ ] **Step 2: Implement `RejectPayrollBatchButton.tsx`** (client) — return `null` unless `status === "pending_review"`. `useState` open + `useTypedMutation<PayrollBatchOut, void>` → `resources.credit.rejectPayrollBatch(batchId, {})` cast `{ data?, error? }`; onSuccess toast "Batch rejected" + close + `router.refresh()`; onError `apiErrorMessage`. `<Button variant="secondary" onClick={()=>setOpen(true)}>Reject batch</Button>` + `<ConfirmDialog open onOpenChange title="Reject payroll batch" description="This rejects the batch. This cannot be undone." confirmLabel="Reject" destructive busy={mutation.isPending} onConfirm={() => mutation.mutate()} />`.

- [ ] **Step 3: Implement `payroll/[id]/page.tsx`** (server) — `const { id } = await params;`; `credit.getPayrollBatch(id)` cast `{ data?: PayrollBatchOut }`; `notFound()` if absent. Header: `<h1>{batch.reference}</h1>` + `<StatusBadge entity="payroll_batch" status={batch.status} />` + `<RejectPayrollBatchButton batchId={id} status={batch.status} />`. Summary `<Card>`: total rows (`<Count>`), matched (`<Count>`), unmatched (`<Count>`), total amount (`<Money>`), source format. No `<AuditBar>`. `export const metadata = { title: "Payroll batch" }`.

- [ ] **Step 4: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/RejectPayrollBatchButton
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/payroll/[id]/" admin/apps/portal/src/__tests__/tenant-credit/RejectPayrollBatchButton.test.tsx
git commit -m "feat(portal): payroll batch detail + reject

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Verification + PR

- [ ] **Step 1: Package + portal gate**:
```bash
cd admin
pnpm --filter @sacco/ui test && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test delta over the 241 (3d-3) baseline.

- [ ] **Step 2: Contract spot-checks**:
  - [ ] No backend changes: `git diff --name-only main...HEAD | grep -E '^app/'` empty; `grep -E '^alembic/'` empty.
  - [ ] No api-client changes: `git diff --name-only main...HEAD | grep 'api-client'` empty.
  - [ ] Changes under `admin/` + `docs/` only.
  - [ ] Payroll status via `entity="payroll_batch"`: `rg 'entity="payroll_batch"' "admin/apps/portal/app/(tenant-authed)/credit"` shows the detail usage.

- [ ] **Step 3: Final holistic review** — loan detail shows workout actions (write-off direct/approval branch, restructure approval, recover only when written-off) + restructurings list; payroll create (dynamic rows) → redirect to detail; batch detail shows summary + status + reject (pending_review only). No AuditBar; tenant-auth only.

- [ ] **Step 4: Push + PR** (base `main`):
```bash
git push -u origin feat/sacco-portal/04d-credit-workout
gh pr create --base main --title "feat(portal): SACCO admin — Credit workout + payroll (Phase 3d-4)" --body "$(cat <<'EOF'
## Summary
- Final **Credit** sub-module (Phase 3d-4 of 4): loan **workout** + **payroll batches** — completes the Credit module.
- **Workout** on the loan detail page (status-gated): **write-off** (dual — posts directly below the product threshold, creates a quorum-2 approval at/above it; the `direct` flag drives the toast), **restructure** (always maker-checker, quorum 2), **recover** (direct, written-off only), plus an executed-**restructurings** table.
- **Payroll**: JSON-row **create** (dynamic `useFieldArray` rows: member + amount, clearing account) → **detail** (summary + status) → **reject** (pending_review only). No list/CSV/per-line (the backend exposes none).
- Fixed the stale `restructuringTypeSchema` (→ term_extension / payment_holiday); added a `payroll_batch` StatusBadge entity + workout/payroll read & input schemas.
- **Checker side deferred**: write-off/restructure create *generic* tenant approvals — approving them needs the future tenant approvals inbox (this only creates them).
- **No backend or api-client changes.**

## Test plan
- `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, `@sacco/portal` test/typecheck/lint green.

> Phase 3d (Credit) COMPLETE: products (3d-1) + applications/guarantors (3d-2) + loans servicing (3d-3) + workout/payroll (this).
> CI note: Lint fails environmentally on this repo (runner-queue issue); reproduced clean locally.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** payroll_batch status entity → T1; enum fix + workout/payroll schemas/read types → T2; workout actions → T3; restructurings table + detail wiring → T4; payroll create + nav → T5; payroll detail + reject → T6; verify/PR → T7.
- **Type consistency:** `WriteOffOut`/`LoanRecoveryOut`/`RestructuringOut`/`PayrollBatchOut` (T2) consumed by T3/T4/T5/T6; `GlAccountOption`/`MemberOption` reused; `periods_added`/row amounts are strings in forms (`intString`/`moneyString`), `<Count>` takes numbers from read types. Write-off branches on `data.direct`. Restructure type enum = term_extension/payment_holiday everywhere.
- **Verify-at-execution:** `<ConfirmDialog>` props (proven 3d-2/3); `useFieldArray` row field-name template strings with `<FormField>`; `<Select>` in a Dialog (workout dialogs) — interactions proven; `loanWriteOffSchema`/`loanRecoverySchema` field names (amount/reason/idempotency_key, write-off + `loan_loss_account_code` optional); Next 15 `params` Promise.
- **No backend tests** — no backend change.
