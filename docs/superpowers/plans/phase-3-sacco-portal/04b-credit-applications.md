# SACCO Admin Portal — Credit Applications + Guarantors (Phase 3d-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-21):** background subagents can't get Edit approval; run **inline**. **Confirm typecheck PASSES before committing** (SP20 lesson). No backend tests (no backend change). Portal/package tests via `pnpm --filter` from the `admin/` dir.

**Goal:** The credit application lifecycle (submit → approve/reject/withdraw) plus guarantors (nominate/accept/decline), as a near-pure client — the first operator-portal screens with a real maker-checker **checker** side.

**Architecture:** Add two `StatusBadge` entities + read/input schemas, then tenant-authed screens under `app/(tenant-authed)/credit/applications/*` server-fetched via `getTenantPageContext()`. List with client-side member/product name joins; submit form; detail page that (when pending) fetches the linked tenant approval request to drive a `<MakerCheckerBanner>` whose action slot houses Approve/Reject, plus Withdraw; and a guarantors section. Clones the 3a–3d-1 tenant-operator pattern.

**Tech Stack:** Next.js 15, React 19, TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library. No Python changes.

## Global Constraints

- **Branch:** `feat/sacco-portal/04b-credit-applications`, off `main` (no PR stacking).
- **No backend changes, no api-client changes.** `resources.credit.{listApplications,createApplication,getApplication,approveApplication,rejectApplication,withdrawApplication,listGuarantors,addGuarantor,acceptGuarantor,declineGuarantor,getProduct,listProducts}`, `resources.members.list`, and `resources.makerChecker.getTenant` all exist (cast `{ data?, error? }`).
- **Application statuses:** pending, approved, rejected, withdrawn, cancelled. **Guarantor statuses:** pending, accepted, declined, released.
- **Submit** is the maker step (creates app + `credit.approve_application` request, quorum = product `required_approvals`). **Approve** is the checker step (`ApprovalService.approve`; self-approval → 400). **Reject**/**withdraw** set terminal status.
- **`disbursement_account_id` omitted from the form** (optional at submit; bound at disburse-time in 3d-3). `disbursement_destination` must be in the product's allowed set (else 400 → surface via `apiErrorMessage`).
- **Money** → `<Money>`/`<MoneyInput>`; **integer term** → `intString` + `<Input inputMode="numeric">` / `<Count>`. Idempotency key = fresh UUID per form instance (contract L).
- **Domain status → `<StatusBadge entity status />`** (contract S). **No `<AuditBar>`**, tenant-auth gating only.
- **DRY/YAGNI/TDD, frequent commits.** Confirm typecheck before each commit.

---

## Task 1: `@sacco/ui` — `loan_application` + `guarantor` StatusBadge entities

**Files:**
- Modify: `admin/packages/ui/src/components/StatusBadge/status-maps.ts`
- Test: `admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx`

**Interfaces:**
- Produces: `StatusEntity` gains `"loan_application" | "guarantor"`; `<StatusBadge entity="loan_application"|"guarantor" status=… />` renders.

- [ ] **Step 1: Failing test** — append cases to `StatusBadge.test.tsx`:

```tsx
it("renders a loan_application status", () => {
  render(<StatusBadge entity="loan_application" status="pending" />);
  expect(screen.getByText("Pending")).toBeInTheDocument();
});

it("renders a guarantor status", () => {
  render(<StatusBadge entity="guarantor" status="accepted" />);
  expect(screen.getByText("Accepted")).toBeInTheDocument();
});
```

> Match the existing import/render style already in the file (it imports `StatusBadge` + `@testing-library/react`). If the file lacks `render`/`screen` imports add them.

Run: `cd admin && pnpm --filter @sacco/ui test -- StatusBadge` → FAIL (entity not in union / no map).

- [ ] **Step 2: Add the entities** to `status-maps.ts`. Extend the `StatusEntity` union with `| "loan_application" | "guarantor"`, add the two maps, and register them in `ENTITY_MAPS`:

```ts
export const LOAN_APPLICATION_STATUS: StatusMap = {
  pending: { variant: "info", label: "Pending" },
  approved: { variant: "success", label: "Approved" },
  rejected: { variant: "danger", label: "Rejected" },
  withdrawn: { variant: "neutral", label: "Withdrawn" },
  cancelled: { variant: "neutral", label: "Cancelled" },
};

export const GUARANTOR_STATUS: StatusMap = {
  pending: { variant: "info", label: "Pending" },
  accepted: { variant: "success", label: "Accepted" },
  declined: { variant: "danger", label: "Declined" },
  released: { variant: "neutral", label: "Released" },
};
```

Add to `ENTITY_MAPS`: `loan_application: LOAN_APPLICATION_STATUS,` and `guarantor: GUARANTOR_STATUS,`.

- [ ] **Step 3: Run test → PASS. Then typecheck + lint + commit.**

```bash
pnpm --filter @sacco/ui test -- StatusBadge && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
git add admin/packages/ui/src/components/StatusBadge/status-maps.ts admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx
git commit -m "feat(portal): loan_application + guarantor StatusBadge entities

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `@sacco/schemas` — read types + nominate/reject schemas + term fix

**Files:**
- Modify: `admin/packages/schemas/src/credit.ts`
- Test: `admin/packages/schemas/src/__tests__/credit.test.ts`

**Interfaces:**
- Produces: `LoanApplicationOut`, `GuarantorOut`; `guarantorNominateSchema` + `GuarantorNominateInput`; `loanApplicationRejectSchema` + `LoanApplicationRejectInput`; `loanApplicationSchema.requested_term_periods` now `intString`.

- [ ] **Step 1: Failing test** — append to `credit.test.ts`:

```ts
import {
  guarantorNominateSchema,
  loanApplicationRejectSchema,
  type GuarantorOut,
  type LoanApplicationOut,
} from "../credit";

describe("application + guarantor schemas (3d-2)", () => {
  it("accepts an integer-string term and rejects a non-numeric one", () => {
    const base = {
      loan_product_id: "550e8400-e29b-41d4-a716-446655440000",
      member_id: "550e8400-e29b-41d4-a716-446655440001",
      requested_amount: "1000000.00",
      purpose: "Working capital for the family shop",
      disbursement_destination: "member_savings",
      idempotency_key: "1234567890ab",
    };
    expect(loanApplicationSchema.safeParse({ ...base, requested_term_periods: "12" }).success).toBe(true);
    expect(loanApplicationSchema.safeParse({ ...base, requested_term_periods: "x" }).success).toBe(false);
  });
  it("guarantorNominateSchema requires at least one member", () => {
    expect(guarantorNominateSchema.safeParse({ guarantor_member_ids: [] }).success).toBe(false);
    expect(
      guarantorNominateSchema.safeParse({
        guarantor_member_ids: ["550e8400-e29b-41d4-a716-446655440009"],
      }).success,
    ).toBe(true);
  });
  it("loanApplicationRejectSchema requires a reason", () => {
    expect(loanApplicationRejectSchema.safeParse({ reason: "" }).success).toBe(false);
    expect(loanApplicationRejectSchema.safeParse({ reason: "Insufficient collateral" }).success).toBe(true);
  });
  it("read types are structurally usable", () => {
    const a: LoanApplicationOut = {
      id: "a1", loan_product_id: "p1", member_id: "m1", requested_amount: "1000000.0000",
      requested_term_periods: 12, approved_amount: null, approved_term_periods: null,
      reviewed_by: null, reviewed_at: null, purpose: "x", disbursement_destination: "member_savings",
      disbursement_account_id: null, status: "pending", rejection_reason: null, decided_by: null,
      decided_at: null, approval_request_id: "r1", idempotency_key: "k", created_at: "t", updated_at: "t",
    };
    const g: GuarantorOut = {
      id: "g1", loan_application_id: "a1", guarantor_member_id: "m2",
      guaranteed_amount: "500000.0000", status: "pending", consented_at: null,
    };
    expect(a.status).toBe("pending");
    expect(g.status).toBe("pending");
  });
});
```

> `loanApplicationSchema` is already imported at the top of the test file (3d-1). Add the new imports to the existing import block (don't duplicate).

Run: `pnpm --filter @sacco/schemas test -- credit` → FAIL.

- [ ] **Step 2: Edit `credit.ts`** — change `requested_term_periods` in `loanApplicationSchema`:

```ts
  requested_term_periods: intString({ min: 1 }),
```
(`intString` is already imported as of 3d-1.) Then add the two schemas (after `loanApplicationSchema`):

```ts
export const guarantorNominateSchema = z.object({
  guarantor_member_ids: z.array(uuid).min(1, "Select at least one guarantor"),
});

export const loanApplicationRejectSchema = z.object({
  reason: z.string().trim().min(1, "A reason is required").max(1000),
});
```

And the inferred types + read types (near the other `export type` lines):

```ts
export type GuarantorNominateInput = z.infer<typeof guarantorNominateSchema>;
export type LoanApplicationRejectInput = z.infer<typeof loanApplicationRejectSchema>;

// Mirror app/modules/credit/schemas.py. Decimals/uuids/datetimes are JSON strings.
export interface LoanApplicationOut {
  id: string;
  loan_product_id: string;
  member_id: string;
  requested_amount: string;
  requested_term_periods: number;
  approved_amount: string | null;
  approved_term_periods: number | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  purpose: string | null;
  disbursement_destination: string;
  disbursement_account_id: string | null;
  status: string;
  rejection_reason: string | null;
  decided_by: string | null;
  decided_at: string | null;
  approval_request_id: string | null;
  idempotency_key: string;
  created_at: string;
  updated_at: string;
}

export interface GuarantorOut {
  id: string;
  loan_application_id: string;
  guarantor_member_id: string;
  guaranteed_amount: string;
  status: string;
  consented_at: string | null;
}
```

- [ ] **Step 3: Run test → PASS. Run the full schemas suite (the 3d-1 application test used `requested_term_periods: 12` (number) — confirm it still parses, since `intString` rejects numbers).**

```bash
pnpm --filter @sacco/schemas test -- credit
```

> **If the pre-existing 3d-1 test `loanApplicationSchema` case fails** because its `ok` fixture used `requested_term_periods: 12` (a number) — update that fixture value to the string `"12"` (and the "rejects fractional"/"out-of-range" cases to use strings like `"12.5"`→ now just a non-integer string which `intString` rejects, and `"0"`/`"400"`). Adjust those three existing assertions to the `intString` reality: `"12.5"` → fails (non-digit), `"0"` → fails (min 1), `"400"` → **passes** intString (no max) so change that assertion or drop the max bound expectation. Simplest: replace the "out-of-range" case with just the `"0"` rejection.

- [ ] **Step 4: typecheck + lint + commit.**

```bash
pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
git add admin/packages/schemas/src/credit.ts admin/packages/schemas/src/__tests__/credit.test.ts
git commit -m "feat(portal): application/guarantor read types + nominate/reject schemas

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Applications list — `<ApplicationsTable>` + `/credit/applications` + link from `/credit`

> Clone the 3b/3c accounts-index pattern (`AccountsTable` + the page's client-side join). Apply the application deltas.

**Files:**
- Create: `app/(tenant-authed)/credit/applications/_components/ApplicationsTable.tsx`, `credit/applications/page.tsx`
- Modify: `app/(tenant-authed)/credit/page.tsx` (add an **Applications** link)
- Test: `apps/portal/src/__tests__/tenant-credit/ApplicationsTable.test.tsx`

**Interfaces:**
- Consumes: `LoanApplicationOut`, `MemberOut`, `LoanProductOut`, `resources.credit.{listApplications,listProducts}`, `resources.members.list`.
- Produces: exported `ApplicationRow = { id; member_label; product_name; requested_amount; requested_term_periods; status }`.

- [ ] **Step 1: `ApplicationsTable` test (failing)** — clone `tenant-shares/AccountsTable.test.tsx`. `TData = ApplicationRow`. A row: `{ id:"a1", member_label:"Ada Loan (M-0001)", product_name:"Personal Loan", requested_amount:"1000000.00", requested_term_periods:12, status:"pending" }`. Assert: member label links to `/credit/applications/a1`; the status badge renders "Pending"; empty state "No loan applications yet".

- [ ] **Step 2: Implement `ApplicationsTable.tsx`** — clone shares `AccountsTable`. Export `ApplicationRow`. `id="loan-applications"`. Columns:
  - **Member** → `<Link href={\`/credit/applications/${row.original.id}\`} className="font-medium text-[var(--text-link)] hover:underline">{row.original.member_label}</Link>`
  - **Product** (`product_name`)
  - **Amount** → `<Money amount={row.original.requested_amount} />`
  - **Term** → `<Count value={row.original.requested_term_periods} />`
  - **Status** → `<StatusBadge entity="loan_application" status={row.original.status} />`
  Empty `{ title: "No loan applications yet", description: "Submit an application to get started." }`. Import `Count`, `Money`, `StatusBadge` from `@sacco/ui`.

- [ ] **Step 3: Implement `credit/applications/page.tsx`** (server) — Promise.all `credit.listApplications({})` (`{ data?: LoanApplicationOut[] }`), `members.list({})` (`{ data?: MemberOut[] }`), `credit.listProducts({})` (`{ data?: LoanProductOut[] }`). Build `memberById` + `productById` maps; map to `ApplicationRow[]` (`member_label = m ? \`${m.full_name} (${m.member_number})\` : a.member_id`; `product_name = productById.get(a.loan_product_id)?.name ?? a.loan_product_id`). Header **New application** → `/credit/applications/new`. `<h1>Loan applications</h1>`. `<ApplicationsTable rows={rows} />`. `export const metadata = { title: "Loan applications" }`.

- [ ] **Step 4: Add an Applications link** to `credit/page.tsx` header — alongside "Create product", add `<Button asChild variant="secondary"><Link href="/credit/applications">Applications</Link></Button>`.

- [ ] **Step 5: Run the test + portal typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/ApplicationsTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/applications/page.tsx" "admin/apps/portal/app/(tenant-authed)/credit/applications/_components/ApplicationsTable.tsx" "admin/apps/portal/app/(tenant-authed)/credit/page.tsx" admin/apps/portal/src/__tests__/tenant-credit/ApplicationsTable.test.tsx
git commit -m "feat(portal): SACCO loan applications list

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Submit application — `<CreateApplicationForm>` + `/credit/applications/new`

> Clone the 3b `OpenAccountForm` (selects + redirect-to-detail) plus a fresh idempotency key.

**Files:**
- Create: `app/(tenant-authed)/credit/applications/new/_components/CreateApplicationForm.tsx`, `credit/applications/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/CreateApplicationForm.test.tsx`

**Interfaces:**
- Consumes: `loanApplicationSchema`/`LoanApplicationInput`, `LoanApplicationOut`, `resources.credit.createApplication`.
- Produces: exported `MemberOption = { id; full_name; member_number }`, `ProductOption = { id; name }`.

- [ ] **Step 1: `CreateApplicationForm` test (failing)** — clone `tenant-shares/OpenAccountForm.test.tsx`. Mock push + `useAuth` (`resources.credit.createApplication`). Props `members`, `products`, optional `defaultMemberId`. Fill: pick product, pick member, amount, term, purpose (≥10 chars), pick destination "Member savings"; submit → `createApplication` called with `expect.objectContaining({ loan_product_id, member_id, requested_amount:"1000000", requested_term_periods:"12", disbursement_destination:"member_savings" })` and `push("/credit/applications/a9")` on `{ data:{ id:"a9" } }`. Also assert a blank required field blocks submit.

- [ ] **Step 2: Implement `CreateApplicationForm.tsx`** (client). `useForm<LoanApplicationInput>({ resolver: zodResolver(loanApplicationSchema), defaultValues: { loan_product_id:"", member_id: defaultMemberId ?? "", requested_amount:"", requested_term_periods:"", purpose:"", disbursement_destination:"member_savings", idempotency_key: <fresh uuid via useState> } })`. Props `{ members: MemberOption[]; products: ProductOption[]; defaultMemberId?: string }`. Fields via `<FormField>`:
  - loan_product_id (`<Select>` from products → `{name}`).
  - member_id (`<Select>` from members → `{full_name} ({member_number})`).
  - requested_amount (`<MoneyInput>`).
  - requested_term_periods (`<Input inputMode="numeric">`).
  - purpose (`<Textarea>`).
  - disbursement_destination (`<Select>`: Member savings / Cash / Internal GL — values member_savings/cash/internal_gl).
  `useTypedMutation<LoanApplicationOut, LoanApplicationInput>` → `resources.credit.createApplication(values)` cast `{ data?, error? }`; onSuccess `toast.success("Application submitted")` + `router.push(\`/credit/applications/${data.id}\`)`; onError `apiErrorMessage` (covers the 400 "destination not allowed by product"). Cancel → `/credit/applications`.

  > `loanApplicationSchema` does not include `disbursement_account_id` in the form payload — it stays optional in the schema and is simply not a field here. If `zodResolver` complains about the missing optional, it won't (optional). The `idempotency_key` is set in defaultValues.

- [ ] **Step 3: Implement `applications/new/page.tsx`** (server) — reads `searchParams` (`{ searchParams: Promise<{ member_id?: string }> }`, `const sp = await searchParams;`); Promise.all `members.list({})` + `credit.listProducts({})`; map to `MemberOption[]`/`ProductOption[]`; `<h1>New loan application</h1>`; `<CreateApplicationForm members={…} products={…} {...(sp.member_id ? { defaultMemberId: sp.member_id } : {})} />`.

- [ ] **Step 4: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/CreateApplicationForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/applications/new/" admin/apps/portal/src/__tests__/tenant-credit/CreateApplicationForm.test.tsx
git commit -m "feat(portal): SACCO loan application submit form

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `<ApplicationActions>` — Approve / Reject / Withdraw (checker side)

**Files:**
- Create: `app/(tenant-authed)/credit/applications/[id]/_components/ApplicationActions.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/ApplicationActions.test.tsx`

**Interfaces:**
- Consumes: `loanApplicationRejectSchema`/`LoanApplicationRejectInput`, `resources.credit.{approveApplication,rejectApplication,withdrawApplication}`.
- Produces: `<ApplicationActions applicationId={string} />` (client) rendering three actions.

- [ ] **Step 1: Test (failing)** — mock `next/navigation` (`refresh`) + `useAuth` (`resources.credit.{approveApplication,rejectApplication,withdrawApplication}`). Render in `<QueryClientProvider>` + `<Toaster>`. Cases:
  - **Approve:** click "Approve" → `<ConfirmDialog>` opens → click the confirm ("Approve") → `approveApplication("a1", {})` called; toast "Application approved".
  - **Reject:** click "Reject" → dialog with reason `<Textarea>`; submit empty → not called; type a reason → submit → `rejectApplication("a1", { reason: "…" })`; toast "Application rejected".
  - **Withdraw:** click "Withdraw" → `<ConfirmDialog>` → confirm → `withdrawApplication("a1", {})`; toast "Application withdrawn".

```tsx
// key wiring (mirror; ConfirmDialog confirmLabel becomes the button name)
const approve = vi.fn(); const reject = vi.fn(); const withdraw = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { credit: {
    approveApplication: approve, rejectApplication: reject, withdrawApplication: withdraw,
  } } }),
}));
```

- [ ] **Step 2: Implement `ApplicationActions.tsx`** (client). State: `approveOpen`, `rejectOpen`, `withdrawOpen` booleans. A reject `useForm<LoanApplicationRejectInput>({ resolver: zodResolver(loanApplicationRejectSchema), defaultValues: { reason: "" } })`. Three `useTypedMutation` (approve/reject/withdraw) each calling the matching resource cast `{ data?, error? }`, onSuccess: toast + close + `router.refresh()`, onError: `toast.error(..., { description: apiErrorMessage(error, …) })` (self-approval/quorum errors surface here).
  - Buttons row: `<Button onClick={()=>setApproveOpen(true)}>Approve</Button>`, `<Button variant="secondary" onClick={()=>setRejectOpen(true)}>Reject</Button>`, `<Button variant="ghost" onClick={()=>setWithdrawOpen(true)}>Withdraw</Button>`.
  - **Approve** `<ConfirmDialog open={approveOpen} onOpenChange={setApproveOpen} title="Approve loan application" description="This records your approval. When the required number of approvals is reached, the application is approved." confirmLabel="Approve" busy={approveMutation.isPending} onConfirm={() => approveMutation.mutate({})} />`.
  - **Withdraw** `<ConfirmDialog ... destructive title="Withdraw application" description="This withdraws the pending application." confirmLabel="Withdraw" onConfirm={() => withdrawMutation.mutate({})} />`.
  - **Reject** a `<Dialog open={rejectOpen} onOpenChange={setRejectOpen}>` containing a `<form onSubmit={rejectForm.handleSubmit((v)=>rejectMutation.mutate(v))}>` with `<FormField name="reason" label="Reason" required render={Textarea}>` and a submit `<Button>Reject application</Button>`.
  - Mutations: `approveMutation.mutate({})` → `resources.credit.approveApplication(applicationId, {})`; `rejectMutation.mutate({reason})` → `rejectApplication(applicationId, { reason })`; `withdrawMutation.mutate({})` → `withdrawApplication(applicationId, {})`.

- [ ] **Step 3: Run test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/ApplicationActions
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/applications/[id]/_components/ApplicationActions.tsx" admin/apps/portal/src/__tests__/tenant-credit/ApplicationActions.test.tsx
git commit -m "feat(portal): loan application approve/reject/withdraw actions

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `<GuarantorsSection>` — list + nominate + accept/decline

**Files:**
- Create: `app/(tenant-authed)/credit/applications/[id]/_components/GuarantorsSection.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/GuarantorsSection.test.tsx`

**Interfaces:**
- Consumes: `GuarantorOut`, `guarantorNominateSchema`/`GuarantorNominateInput`, `resources.credit.{addGuarantor,acceptGuarantor,declineGuarantor}`.
- Produces: `<GuarantorsSection applicationId={string} guarantors={GuarantorOut[]} members={MemberOption[]} />` (client). `MemberOption = { id; full_name; member_number }`.

- [ ] **Step 1: Test (failing)** — mock `next/navigation` (`refresh`) + `useAuth`. Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`. Props: one pending guarantor `{ id:"g1", loan_application_id:"a1", guarantor_member_id:"m2", guaranteed_amount:"500000.00", status:"pending", consented_at:null }`, `members=[{id:"m2",full_name:"Ben Okello",member_number:"M-0002"},{id:"m3",full_name:"Cara N",member_number:"M-0003"}]`. Cases:
  - renders the guarantor's member label "Ben Okello (M-0002)" + a "Pending" badge.
  - **Accept:** click "Accept" → ConfirmDialog → confirm → `acceptGuarantor("g1", { guarantor_member_id: "m2" })`; toast.
  - **Nominate:** click "Add guarantor" → dialog with member checkboxes (only members NOT already a guarantor, i.e. m3) → check Cara → submit → `addGuarantor("a1", { guarantor_member_ids: ["m3"] })`; toast.

- [ ] **Step 2: Implement `GuarantorsSection.tsx`** (client). A `<Card>` titled "Guarantors". Build `memberById` from `members`. For each guarantor: a row with `memberById.get(g.guarantor_member_id)` label (fallback id), `<Money amount={g.guaranteed_amount} />`, `<StatusBadge entity="guarantor" status={g.status} />`, and when `g.status === "pending"`: **Accept** / **Decline** buttons each opening a `<ConfirmDialog>` → `resources.credit.acceptGuarantor(g.id, { guarantor_member_id: g.guarantor_member_id })` / `declineGuarantor(...)` → toast + `router.refresh()`.
  - Header **Add guarantor** button → opens a `<Dialog>` with a `useForm<GuarantorNominateInput>({ resolver: zodResolver(guarantorNominateSchema), defaultValues: { guarantor_member_ids: [] } })`. The member picker is a checkbox group (mirror the 3d-1 destinations checkbox group) over members NOT already nominated (`members.filter(m => !guarantors.some(g => g.guarantor_member_id === m.id))`), bound to the `guarantor_member_ids` array field. Submit → `resources.credit.addGuarantor(applicationId, values)` cast `{ data?, error? }` → toast "Guarantors added" + `router.refresh()`; onError `apiErrorMessage`.
  - Use `useTypedMutation` for each of add / accept / decline.

- [ ] **Step 3: Run test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/GuarantorsSection
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/applications/[id]/_components/GuarantorsSection.tsx" admin/apps/portal/src/__tests__/tenant-credit/GuarantorsSection.test.tsx
git commit -m "feat(portal): loan application guarantors section

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Application detail page — assemble banner + actions + guarantors

**Files:**
- Create: `app/(tenant-authed)/credit/applications/[id]/page.tsx`

**Interfaces:**
- Consumes: `LoanApplicationOut`, `GuarantorOut`, `LoanProductOut`, `MemberOut`, `ApprovalRequestOut` (from `@sacco/schemas`), `resources.credit.{getApplication,listGuarantors,getProduct}`, `resources.members.list`, `resources.makerChecker.getTenant`; `<MakerCheckerBanner>`, `<StatusBadge>`, `<Card>`, `<Money>`, `<Count>`, `<FormattedDateTime>`; `<ApplicationActions>`, `<GuarantorsSection>`.

- [ ] **Step 1: Implement `[id]/page.tsx`** (server). `const { id } = await params;` (`params: Promise<{ id: string }>`). Fetch `credit.getApplication(id)` cast `{ data?: LoanApplicationOut }`; `notFound()` if absent. Then Promise.all: `credit.listGuarantors(id)` (`{ data?: GuarantorOut[] }`), `members.list({})` (`{ data?: MemberOut[] }`), `credit.getProduct(application.loan_product_id)` (`{ data?: LoanProductOut }`). If `application.status === "pending" && application.approval_request_id`, also fetch `makerChecker.getTenant(application.approval_request_id)` cast `{ data?: ApprovalRequestOut }` (guard for absence).
  - Build `memberById`; `memberLabel = m ? \`${m.full_name} (${m.member_number})\` : application.member_id`.
  - Header: `<h1>{product?.name ?? "Loan application"}</h1>` + `<StatusBadge entity="loan_application" status={application.status} />`.
  - When pending **and** the approval request loaded, render `<MakerCheckerBanner approvalRequestId={req.id} operationLabel="Loan approval" requesterName={req.requested_by} requestedAt={<FormattedDateTime value={req.requested_at} />} quorumRequired={req.required_approvals} quorumCurrent={req.current_approvals} action={<ApplicationActions applicationId={id} />} />`. When pending but no request data, render `<ApplicationActions applicationId={id} />` directly above the body.
  - Read-only `<Card>` "Details": member (`memberLabel`), requested amount (`<Money>`), term (`<Count>`), purpose (`?? "—"`), disbursement destination, approved amount (`<Money>` when set), approved term (`<Count>` when set), rejection reason (when set), decided at (`<FormattedDateTime>` when set).
  - `<GuarantorsSection applicationId={id} guarantors={guarantors ?? []} members={(members ?? []).map(m => ({ id: m.id, full_name: m.full_name, member_number: m.member_number }))} />`.
  - No `<AuditBar>`. `export const metadata = { title: "Loan application" }`.

  > `ApprovalRequestOut` is exported from `@sacco/schemas` (3a/Phase-2). Verify the import name; if absent, type the cast inline as `{ id: string; requested_by: string; requested_at: string; required_approvals: number; current_approvals: number }`.

- [ ] **Step 2: typecheck + lint (no unit test — server page; covered by component tests + holistic review); commit.**

```bash
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/applications/[id]/page.tsx"
git commit -m "feat(portal): loan application detail (banner + actions + guarantors)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Verification + PR

- [ ] **Step 1: Package + portal gate**:
```bash
cd admin
pnpm --filter @sacco/ui test && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test delta over the 217 (3d-1) baseline (+ ApplicationsTable, CreateApplicationForm, ApplicationActions, GuarantorsSection cases).

- [ ] **Step 2: Contract spot-checks**:
  - [ ] No backend changes: `git diff --name-only main...HEAD | grep -E '^app/'` empty; `grep -E '^alembic/'` empty.
  - [ ] No api-client changes: `git diff --name-only main...HEAD | grep 'api-client'` empty.
  - [ ] Changes under `admin/` + `docs/` only.
  - [ ] Status via StatusBadge (no hand-picked Badge for app/guarantor status): `rg "entity=\"loan_application\"|entity=\"guarantor\"" "admin/apps/portal/app/(tenant-authed)/credit"` shows the table + detail + guarantors usages.

- [ ] **Step 3: Final holistic review** — applications list (member/product joins, status badges); submit redirects to detail; pending detail shows the maker-checker banner with quorum + Approve/Reject in the action slot + Withdraw; approve/reject/withdraw refresh and reflect the new status; self-approval error surfaces; guarantors list + nominate + accept/decline. No AuditBar; tenant-auth only.

- [ ] **Step 4: Push + PR** (base `main`):
```bash
git push -u origin feat/sacco-portal/04b-credit-applications
gh pr create --base main --title "feat(portal): SACCO admin — Credit applications + guarantors (Phase 3d-2)" --body "$(cat <<'EOF'
## Summary
- Second **Credit** sub-module (Phase 3d-2 of 4): the loan application lifecycle + guarantors.
- **First real maker-checker checker side in the operator portal**: the application detail page renders a `<MakerCheckerBanner>` (quorum from the linked tenant approval request) whose action slot houses **Approve** / **Reject**, plus **Withdraw** — all when status is pending. Self-approval is blocked server-side and surfaces as a toast.
- Submit (maker) → list (client-join member + product names, status badges) → detail (decisions + guarantors). Guarantors: nominate (member multi-select), accept/decline (operator records consent).
- New `StatusBadge` entities `loan_application` + `guarantor`; read types `LoanApplicationOut`/`GuarantorOut`; `guarantorNominateSchema`/`loanApplicationRejectSchema`; `requested_term_periods` → `intString`.
- `disbursement_account_id` is captured at disburse-time (3d-3), not at application time (it is optional at submit).
- **No backend or api-client changes** (credit resource + makerChecker.getTenant already exist).

## Test plan
- `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, `@sacco/portal` test/typecheck/lint green.

> Phase 3d: products (3d-1, merged) → applications+guarantors (this) → loans servicing (3d-3) → workout+payroll (3d-4).
> CI note: Lint fails environmentally on this repo (runner-queue issue); reproduced clean locally.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** status entities → T1; read/input schemas → T2; list → T3; submit → T4; checker actions → T5; guarantors → T6; detail assembly + banner → T7; verify/PR → T8.
- **Type consistency:** `LoanApplicationOut`/`GuarantorOut` (T2) consumed by T3/T5/T6/T7; `ApplicationRow` (T3) is a page-built view-model; `MemberOption`/`ProductOption` reused across T4/T6/T7; `requested_term_periods` is `intString` (string in form, `number` in read type → `<Count>`); idempotency key fresh-per-instance (contract L).
- **Pre-existing test risk (T2 Step 3):** the 3d-1 `loanApplicationSchema` test fixture used `requested_term_periods: 12` (number) — `intString` now requires a string; that fixture/assertions must be updated (noted inline).
- **Verify-at-execution:** `<ConfirmDialog>` props (`open/onOpenChange/title/description/confirmLabel/destructive/onConfirm/busy` — confirmed); `<MakerCheckerBanner>` props (`approvalRequestId/operationLabel/requesterName/requestedAt/quorumRequired/quorumCurrent/action` — confirmed; `requesterName` gets the raw `requested_by` uuid, acceptable v1); `ApprovalRequestOut` exported from `@sacco/schemas`; `<Checkbox>` Radix (`checked`/`onCheckedChange`); Next 15 `params`/`searchParams` are Promises.
- **No backend tests** — no backend change.
