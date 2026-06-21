# SACCO Admin Portal — Fees (Phase 3e) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-21):** background subagents can't get Edit approval; run **inline**. **Confirm typecheck PASSES before committing** (SP20 lesson). No backend tests (no backend change). Portal/package tests via `pnpm --filter` from `admin/`.
> **Test gotchas (carry-over):** `<Money>` exposes `data-amount`, `<Count>` `data-value`; checkboxes inside a Radix Dialog need `fireEvent.click(getByRole("checkbox"))`; uuid-typed schema fields need real UUID fixtures; `<DataTable>` `TData` must extend `{ id: string }`.

**Goal:** The Fees module — fee types (list/create/detail+edit), assessments (list/create with a dynamic target selector/detail), and collections (recorded from assessment detail).

**Architecture:** Fix three stale `@sacco/schemas/fees.ts` issues + add read types, then tenant-authed screens under `app/(tenant-authed)/fees/*` server-fetched via `getTenantPageContext()`. In-memory `<DataTable>`s, RHF/Zod forms, GL-code `<Select>`s from `ledger.listAccounts()`, the existing `fee_assessment` StatusBadge, and a reactive target selector on the assessment form. Clones the prior tenant-operator modules. All flows direct (201) — no maker-checker.

**Tech Stack:** Next.js 15, React 19, TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library. No Python changes.

## Global Constraints

- **Branch:** `feat/sacco-portal/05-fees`, off `main` (no PR stacking).
- **No backend changes, no api-client changes.** `resources.fees.{listTypes,getType,createType,patchType,listAssessments,getAssessment,createAssessment,recordCollection}`, `resources.members.list`, `resources.credit.listLoans`, `resources.savings.listAccounts`, `resources.shares.listAccounts`, `resources.ledger.listAccounts` exist (cast `{ data?, error? }`).
- **Backend enums (authoritative):** `amount_kind` ∈ {fixed, percentage, tiered}; `trigger_kind` ∈ {event, schedule, manual}; `applicable_to`/assessment `target_type` ∈ {member, savings_account, loan, share_account}; collection `method` ∈ {cash, journal_voucher} (savings_deduction auto-only); `contra_account_id` **required**.
- **PATCH fee type** accepts only `name, description, amount, is_active, requires_collection`.
- **All flows direct (201)** — no maker-checker. **Money** → `<Money>`/`<MoneyInput>`; **dates** → `<DateInput>` (forms) / `<FormattedDate>`/`<FormattedDateTime>` (display); GL codes by **code** via `<Select>` (value=code), contra account by **id**. Assessment status → `<StatusBadge entity="fee_assessment">` (existing). Idempotency key = fresh UUID per collection form (contract L).
- **No `<AuditBar>`**, tenant-auth gating only. **DRY/YAGNI/TDD, frequent commits.** Typecheck before each commit.

---

## Task 1: `@sacco/schemas` — fix stale fee schemas + add read types

**Files:**
- Modify: `admin/packages/schemas/src/fees.ts`
- Test: `admin/packages/schemas/src/__tests__/fees.test.ts` (create)

**Interfaces:**
- Produces: corrected `feeTriggerKindSchema` / `feeCollectionSchema` / `feeAssessmentSchema`; read types `FeeTypeOut`, `FeeAssessmentOut`, `FeeCollectionOut`, `FeeAssessmentDetailOut`.

- [ ] **Step 1: Failing test** — create `src/__tests__/fees.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  feeTriggerKindSchema,
  feeCollectionSchema,
  feeAssessmentSchema,
  type FeeTypeOut,
  type FeeAssessmentDetailOut,
} from "../fees";

const U = "550e8400-e29b-41d4-a716-446655440000";

describe("fees schemas (corrected to backend)", () => {
  it("trigger kind accepts schedule, rejects scheduled", () => {
    expect(feeTriggerKindSchema.safeParse("schedule").success).toBe(true);
    expect(feeTriggerKindSchema.safeParse("scheduled").success).toBe(false);
  });
  it("collection requires contra_account_id for cash", () => {
    expect(
      feeCollectionSchema.safeParse({
        fee_assessment_id: U, amount: "5000", method: "cash", idempotency_key: "abcd1234efgh",
      }).success,
    ).toBe(false);
    expect(
      feeCollectionSchema.safeParse({
        fee_assessment_id: U, amount: "5000", method: "cash", contra_account_id: U, idempotency_key: "abcd1234efgh",
      }).success,
    ).toBe(true);
  });
  it("assessment period_end is optional and share_account is a valid target", () => {
    expect(
      feeAssessmentSchema.safeParse({
        fee_type_id: U, target_type: "share_account", target_id: U, period_start: "2026-06-01",
      }).success,
    ).toBe(true);
  });
  it("read types are structurally usable", () => {
    const t: FeeTypeOut = {
      id: "f1", code: "annual", name: "Annual Fee", description: null, applicable_to: "member",
      amount_kind: "fixed", amount: "20000.0000", percentage_basis: null, percentage_rate: null,
      currency: "UGX", trigger_kind: "schedule", event_name: null, schedule_config: null,
      gl_income_account_code: "4200", gl_receivable_account_code: "1300", is_active: true,
      requires_collection: false,
    };
    const a: FeeAssessmentDetailOut = {
      id: "a1", fee_type_id: "f1", target_type: "member", target_id: "m1", period_start: "2026-06-01",
      period_end: null, amount: "20000.0000", currency: "UGX", status: "assessed",
      assessed_at: "2026-06-01T00:00:00Z", due_at: null, paid_at: null, waived_by: null,
      waiver_reason: null, journal_entry_id: "j1", collections: [],
    };
    expect(t.code).toBe("annual");
    expect(a.collections.length).toBe(0);
  });
});
```

Run: `cd admin && pnpm --filter @sacco/schemas test -- fees` → FAIL.

- [ ] **Step 2: Fix `fees.ts`** — three corrections:

```ts
export const feeTriggerKindSchema = z.enum(["event", "schedule", "manual"]);
```

`feeCollectionSchema` → require `contra_account_id` for both methods (drop the optional + refine):
```ts
export const feeCollectionSchema = z.object({
  fee_assessment_id: uuid,
  amount: moneyString({ min: "0.01" }),
  method: z.enum(["cash", "journal_voucher"]),
  contra_account_id: uuid,
  idempotency_key: idempotencyKey,
});
```

`feeAssessmentSchema` → optional `period_end`, add `share_account`:
```ts
export const feeAssessmentSchema = z.object({
  fee_type_id: uuid,
  target_type: z.enum(["member", "loan", "savings_account", "share_account"]),
  target_id: uuid,
  period_start: isoDate,
  period_end: isoDate.optional(),
});
```

- [ ] **Step 3: Add read types** (after the `export type` lines):

```ts
export interface FeeTypeOut {
  id: string;
  code: string;
  name: string;
  description: string | null;
  applicable_to: string;
  amount_kind: string;
  amount: string;
  percentage_basis: string | null;
  percentage_rate: string | null;
  currency: string;
  trigger_kind: string;
  event_name: string | null;
  schedule_config: Record<string, unknown> | null;
  gl_income_account_code: string;
  gl_receivable_account_code: string;
  is_active: boolean;
  requires_collection: boolean;
}

export interface FeeCollectionOut {
  id: string;
  fee_assessment_id: string;
  amount: string;
  collected_at: string;
  method: string;
  collected_by: string;
  journal_entry_id: string;
  idempotency_key: string;
}

export interface FeeAssessmentOut {
  id: string;
  fee_type_id: string;
  target_type: string;
  target_id: string;
  period_start: string;
  period_end: string | null;
  amount: string;
  currency: string;
  status: string;
  assessed_at: string;
  due_at: string | null;
  paid_at: string | null;
  waived_by: string | null;
  waiver_reason: string | null;
  journal_entry_id: string;
}

export interface FeeAssessmentDetailOut extends FeeAssessmentOut {
  collections: FeeCollectionOut[];
}
```

> `fees.ts` is already exported from `src/index.ts` (verify `export * from "./fees";`).

- [ ] **Step 4: Run test + full schemas suite + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
git add admin/packages/schemas/src/fees.ts admin/packages/schemas/src/__tests__/fees.test.ts
git commit -m "feat(portal): fix fee schema enums + add read types

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Fee types list — `<FeeTypesTable>` + `/fees/types`

> Clone the 3d-1 loan `ProductsTable` + page (in-memory DataTable, name links to detail).

**Files:**
- Create: `app/(tenant-authed)/fees/types/_components/FeeTypesTable.tsx`, `fees/types/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-fees/FeeTypesTable.test.tsx`

**Interfaces:**
- Consumes: `FeeTypeOut`, `resources.fees.listTypes`.

- [ ] **Step 1: `FeeTypesTable` test (failing)** — clone the credit `ProductsTable.test.tsx` (mock `useTableUrlState` + `next/navigation`; `<TenantCurrencyProvider>`). `TData = FeeTypeOut` (use the Task 1 `t` shape, add `id:"f1"`). Assert: **Name** links to `/fees/types/f1`; the code "annual" renders; empty state "No fee types yet".

- [ ] **Step 2: Implement `FeeTypesTable.tsx`** — clone the credit `ProductsTable`. `"use client"`, in-memory sort/paginate, `useTableUrlState`. `id="fee-types"`, `TData = FeeTypeOut`. Columns: **Code** (`code`); **Name** → `<Link href={\`/fees/types/${row.original.id}\`} className="font-medium text-[var(--text-link)] hover:underline">{row.original.name}</Link>`; **Applies to** (`applicable_to`); **Amount** → `<Money amount={row.original.amount} />`; **Trigger** (`trigger_kind`); **Active** → `row.original.is_active ? "Yes" : "No"`. Empty `{ title: "No fee types yet", description: "Create a fee type to start assessing fees." }`. Import `Money`.

- [ ] **Step 3: Implement `fees/types/page.tsx`** (server) — `getTenantPageContext()`, `resources.fees.listTypes({})` cast `{ data?: FeeTypeOut[] }`, `<h1>Fee types</h1>`, header buttons: **Assessments** `<Button asChild variant="secondary"><Link href="/fees/assessments">` + **Create fee type** `<Button asChild><Link href="/fees/types/new">`. `<FeeTypesTable rows={data ?? []} />`. `export const metadata = { title: "Fees" }`.

- [ ] **Step 4: Run the test + portal typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-fees/FeeTypesTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/fees/types/page.tsx" "admin/apps/portal/app/(tenant-authed)/fees/types/_components/FeeTypesTable.tsx" admin/apps/portal/src/__tests__/tenant-fees/FeeTypesTable.test.tsx
git commit -m "feat(portal): SACCO fee types list

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Create fee type — `<CreateFeeTypeForm>` + `/fees/types/new`

> Clone the 3d-1 loan `CreateProductForm` (GL `<Select>` value=code, drop-empty-optionals, `<Checkbox>`).

**Files:**
- Create: `app/(tenant-authed)/fees/types/new/_components/CreateFeeTypeForm.tsx`, `fees/types/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-fees/CreateFeeTypeForm.test.tsx`

**Interfaces:**
- Consumes: `feeTypeSchema`/`FeeTypeInput`, `FeeTypeOut`, `resources.fees.createType`, `resources.ledger.listAccounts`.
- Produces: exported `GlAccountOption = { id; code; name; account_type }`.

- [ ] **Step 1: Test (failing)** — clone the credit `CreateProductForm.test.tsx`. Mock push + `useAuth` (`resources.fees.createType`). Pass `glAccounts=[{id:"g1",code:"4200",name:"Fee Income",account_type:"income"}]`. Fill code "annual", name "Annual Fee", amount "20000"; pick the two GL accounts (`/income gl/i`, `/receivable gl/i` → the single option); submit → `createType` called with `expect.objectContaining({ code:"annual", name:"Annual Fee", applicable_to:"member", amount_kind:"fixed", trigger_kind:"manual", gl_income_account_code:"4200", gl_receivable_account_code:"4200" })` + `push("/fees/types")`. Also a blank code blocks submit.

> defaults: applicable_to "member", amount_kind "fixed", trigger_kind "manual", currency "UGX", requires_collection false — so the test only fills code/name/amount + GL selects.

- [ ] **Step 2: Implement `CreateFeeTypeForm.tsx`** (client). `useForm<FeeTypeInput>({ resolver: zodResolver(feeTypeSchema), defaultValues: { code:"", name:"", description:"", applicable_to:"member", amount_kind:"fixed", amount:"", currency:"UGX", trigger_kind:"manual", event_name:"", gl_income_account_code:"", gl_receivable_account_code:"", requires_collection: false } })`. Props `{ glAccounts: GlAccountOption[] }`. Fields via `<FormField>`:
  - code (`<Input>`), name (`<Input>`), description (`<Textarea>`).
  - applicable_to (`<Select>`: member / savings_account / loan / share_account).
  - amount_kind (`<Select>`: fixed / percentage / tiered).
  - amount (`<MoneyInput>`), currency (`<Input>`).
  - trigger_kind (`<Select>`: event / schedule / manual).
  - event_name (`<Input>`, optional).
  - gl_income_account_code + gl_receivable_account_code — a shared `glSelect` helper (value=code, `{code} — {name}`); labels "Income GL account" / "Receivable GL account".
  - requires_collection (`<Checkbox>` with a wrapping `<label>`).
  `useTypedMutation<FeeTypeOut, FeeTypeInput>` → drop empty `description`/`event_name` → `resources.fees.createType(body)` cast `{ data?, error? }`; onSuccess `toast.success("Fee type created")` + `router.push("/fees/types")`; onError `apiErrorMessage`. Cancel → `/fees/types`.

- [ ] **Step 3: Implement `types/new/page.tsx`** (server) — `getTenantPageContext()`, fetch `resources.ledger.listAccounts({})` cast `{ data?: GlAccountOption[] }`, `<h1>Create fee type</h1>`, `<CreateFeeTypeForm glAccounts={data ?? []} />`.

- [ ] **Step 4: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-fees/CreateFeeTypeForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/fees/types/new/" admin/apps/portal/src/__tests__/tenant-fees/CreateFeeTypeForm.test.tsx
git commit -m "feat(portal): SACCO fee type create form

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Fee type detail + edit — `[id]/page.tsx` + `<EditFeeTypeForm>`

> Clone the 3d-1 loan product detail + `EditProductForm` (limited PATCH form).

**Files:**
- Create: `app/(tenant-authed)/fees/types/[id]/page.tsx`, `_components/EditFeeTypeForm.tsx`
- Test: `apps/portal/src/__tests__/tenant-fees/EditFeeTypeForm.test.tsx`

**Interfaces:**
- Consumes: `FeeTypeOut`, `feeTypePatchSchema`/`FeeTypePatchInput`, `resources.fees.{getType,patchType}`.

- [ ] **Step 1: `EditFeeTypeForm` test (failing)** — clone the credit `EditProductForm.test.tsx`. Mock `refresh` + `useAuth` (`resources.fees.patchType`). Props `{ feeType: FeeTypeOut }`. Cases: renders with the name prefilled; change name → submit → `patchType(feeType.id, expect.objectContaining({ name: "New name" }))`; toast "Fee type updated"; `refresh()`.

- [ ] **Step 2: Implement `EditFeeTypeForm.tsx`** (client) — `useForm<FeeTypePatchInput>({ resolver: zodResolver(feeTypePatchSchema), defaultValues: { name: feeType.name, description: feeType.description ?? "", amount: feeType.amount, is_active: feeType.is_active, requires_collection: feeType.requires_collection } })`. Fields: name (`<Input>`), description (`<Textarea>`), amount (`<MoneyInput>`), is_active (`<Checkbox>`), requires_collection (`<Checkbox>`). `useTypedMutation<FeeTypeOut, FeeTypePatchInput>` → drop empty `description` → `resources.fees.patchType(feeType.id, body)` cast `{ data?, error? }`; onSuccess `toast.success("Fee type updated")` + `router.refresh()`; onError `apiErrorMessage`.

  > `feeTypePatchSchema` is `.strict()` — only send keys it allows (name/description/amount/is_active/requires_collection); do not spread extra keys.

- [ ] **Step 3: Implement `[id]/page.tsx`** (server) — `const { id } = await params;`; `resources.fees.getType(id)` cast `{ data?: FeeTypeOut }`; `notFound()` if absent. Header `<h1>{feeType.name}</h1>`. Read-only `<Card>`s: **Identity** (code, name, description `?? "—"`, applies-to), **Pricing** (amount_kind, `<Money amount={feeType.amount} />`, currency, percentage rate/basis when set), **Trigger** (trigger_kind, event_name `?? "—"`), **GL mapping** (income + receivable codes), **Flags** (active Yes/No, requires_collection Yes/No). Then an **Edit** `<Card>` with `<EditFeeTypeForm feeType={feeType} />`. No StatusBadge (is_active is a bool), no AuditBar. `export const metadata = { title: "Fee type" }`.

- [ ] **Step 4: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-fees/EditFeeTypeForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/fees/types/[id]/" admin/apps/portal/src/__tests__/tenant-fees/EditFeeTypeForm.test.tsx
git commit -m "feat(portal): SACCO fee type detail + edit

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Assessments list — `<AssessmentsTable>` + `/fees/assessments`

> Clone the 3d-2 `ApplicationsTable` + page (client-join the fee-type name; StatusBadge).

**Files:**
- Create: `app/(tenant-authed)/fees/assessments/_components/AssessmentsTable.tsx`, `fees/assessments/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-fees/AssessmentsTable.test.tsx`

**Interfaces:**
- Consumes: `FeeAssessmentOut`, `FeeTypeOut`, `resources.fees.{listAssessments,listTypes}`.
- Produces: exported `AssessmentRow = { id; fee_type_name; target_type; amount; period_start; status }`.

- [ ] **Step 1: `AssessmentsTable` test (failing)** — clone `ApplicationsTable.test.tsx`. Row `{ id:"a1", fee_type_name:"Annual Fee", target_type:"member", amount:"20000.00", period_start:"2026-06-01", status:"assessed" }`. Assert: fee type name links to `/fees/assessments/a1`; status badge "Assessed"; empty state "No assessments yet".

- [ ] **Step 2: Implement `AssessmentsTable.tsx`** — clone `ApplicationsTable`. Export `AssessmentRow`. `id="fee-assessments"`. Columns: **Fee type** → `<Link href={\`/fees/assessments/${row.original.id}\`}>{row.original.fee_type_name}</Link>`; **Target** (`target_type`); **Amount** → `<Money amount={row.original.amount} />`; **Period** → `<FormattedDate value={row.original.period_start} />`; **Status** → `<StatusBadge entity="fee_assessment" status={row.original.status} />`. Empty `{ title: "No assessments yet", description: "Create an assessment to charge a fee." }`. Import `Money`, `FormattedDate`, `StatusBadge`.

- [ ] **Step 3: Implement `fees/assessments/page.tsx`** (server) — Promise.all `fees.listAssessments({})` (`{ data?: FeeAssessmentOut[] }`) + `fees.listTypes({})` (`{ data?: FeeTypeOut[] }`); build `feeTypeById`; map to `AssessmentRow[]` (`fee_type_name = feeTypeById.get(a.fee_type_id)?.name ?? a.fee_type_id`). Header **New assessment** → `/fees/assessments/new`; **Fee types** link → `/fees/types`. `<h1>Fee assessments</h1>`. `<AssessmentsTable rows={rows} />`. `export const metadata = { title: "Fee assessments" }`.

- [ ] **Step 4: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-fees/AssessmentsTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/fees/assessments/page.tsx" "admin/apps/portal/app/(tenant-authed)/fees/assessments/_components/AssessmentsTable.tsx" admin/apps/portal/src/__tests__/tenant-fees/AssessmentsTable.test.tsx
git commit -m "feat(portal): SACCO fee assessments list

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Create assessment — `<CreateAssessmentForm>` (dynamic target) + `/fees/assessments/new`

**Files:**
- Create: `app/(tenant-authed)/fees/assessments/new/_components/CreateAssessmentForm.tsx`, `fees/assessments/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-fees/CreateAssessmentForm.test.tsx`

**Interfaces:**
- Consumes: `feeAssessmentSchema`/`FeeAssessmentInput`, `FeeAssessmentOut`, `resources.fees.createAssessment`.
- Produces: exported `TargetOption = { id: string; label: string }`; `TargetMap = Record<"member"|"loan"|"savings_account"|"share_account", TargetOption[]>`; `FeeTypeOption = { id: string; code: string; name: string }`.

- [ ] **Step 1: Test (failing)** — mock push + `useAuth` (`resources.fees.createAssessment`). Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`. Props `feeTypes=[{id:FT,code:"annual",name:"Annual Fee"}]`, `targets={ member:[{id:M1,label:"Ada Loan (M-0001)"}], loan:[{id:L1,label:"LN-1 · Ada"}], savings_account:[], share_account:[] }` (FT/M1/L1 real uuids). Cases:
  - **target options switch with target_type:** default target_type=member → option "Ada Loan (M-0001)" present; switch target_type to "loan" → option "LN-1 · Ada" present (member option gone).
  - **submit:** pick fee type, target member, type a `period_start` date → submit → `createAssessment(expect.objectContaining({ fee_type_id: FT, target_type: "member", target_id: M1, period_start: "2026-06-01" }))` → `push("/fees/assessments/a9")` on `{ data: { id: "a9" } }`.

  > `<DateInput>` value/onValueChange shape — type into it via `getByLabelText(/period start/i)` (it renders a date input). If interacting is awkward, set the value through the field; mirror an existing `<DateInput>` consumer (billing `AssignPlanForm`).

- [ ] **Step 2: Implement `CreateAssessmentForm.tsx`** (client). `useForm<FeeAssessmentInput>({ resolver: zodResolver(feeAssessmentSchema), defaultValues: { fee_type_id: "", target_type: "member", target_id: "", period_start: "", period_end: "" } })`. Props `{ feeTypes: FeeTypeOption[]; targets: TargetMap }`. Use `const targetType = form.watch("target_type");` and render the `target_id` options from `targets[targetType]`. On a `target_type` change, reset `target_id` (`form.setValue("target_id", "")` in the Select's `onValueChange` before/after calling `field.onChange`). Fields via `<FormField>`:
  - fee_type_id (`<Select>` → `{code} — {name}`).
  - target_type (`<Select>`: member / loan / savings_account / share_account; on change also clear target_id).
  - target_id (`<Select>` whose items come from `targets[targetType]` → `{label}`; placeholder "Choose a target…").
  - period_start (`<DateInput>`), period_end (`<DateInput>`, optional).
  `useTypedMutation<FeeAssessmentOut, FeeAssessmentInput>` → drop empty `period_end` → `resources.fees.createAssessment(body)` cast `{ data?, error? }`; onSuccess `toast.success("Assessment created")` + `router.push(\`/fees/assessments/${data.id}\`)`; onError `apiErrorMessage` (covers applicable_to mismatch). Cancel → `/fees/assessments`.

- [ ] **Step 3: Implement `assessments/new/page.tsx`** (server) — Promise.all `fees.listTypes({})`, `members.list({})`, `credit.listLoans({})`, `savings.listAccounts({})`, `shares.listAccounts({})`. Build a `memberById` map; then:
  ```ts
  const ml = (id: string) => { const m = memberById.get(id); return m ? `${m.full_name} (${m.member_number})` : id; };
  const targets = {
    member: (members ?? []).map((m) => ({ id: m.id, label: `${m.full_name} (${m.member_number})` })),
    loan: (loans ?? []).map((l) => ({ id: l.id, label: `${l.loan_reference} · ${ml(l.member_id)}` })),
    savings_account: (savings ?? []).map((s) => ({ id: s.id, label: `${s.product_name} · ${ml(s.member_id)}` })),
    share_account: (shares ?? []).map((s) => ({ id: s.id, label: `${s.product_name} · ${ml(s.member_id)}` })),
  };
  const feeTypeOptions = (types ?? []).map((t) => ({ id: t.id, code: t.code, name: t.name }));
  ```
  `<h1>New fee assessment</h1>`; `<CreateAssessmentForm feeTypes={feeTypeOptions} targets={targets} />`.
  > Cast each resource result `{ data?: …[] }`. `MemberOut`, `LoanOut`, `SavingsAccountOut`, `ShareAccountListItemOut` from `@sacco/schemas`.

- [ ] **Step 4: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-fees/CreateAssessmentForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/fees/assessments/new/" admin/apps/portal/src/__tests__/tenant-fees/CreateAssessmentForm.test.tsx
git commit -m "feat(portal): SACCO fee assessment create (dynamic target)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Assessment detail + record collection — `[id]/page.tsx` + `<CollectionsTable>` + `<RecordCollectionButton>`

**Files:**
- Create: `app/(tenant-authed)/fees/assessments/[id]/page.tsx`, `_components/CollectionsTable.tsx`, `_components/RecordCollectionButton.tsx`
- Test: `apps/portal/src/__tests__/tenant-fees/RecordCollectionButton.test.tsx`

**Interfaces:**
- Consumes: `FeeAssessmentDetailOut`, `FeeCollectionOut`, `FeeTypeOut`, `feeCollectionSchema`/`FeeCollectionInput`, `resources.fees.{getAssessment,getType,recordCollection}`, `resources.ledger.listAccounts`.
- Produces: `<RecordCollectionButton assessmentId={string} status={string} glAccounts={GlAccountOption[]} />`; `GlAccountOption = { id; code; name; account_type }`.

- [ ] **Step 1: `CollectionsTable.tsx`** (client) — in-memory `<DataTable id="fee-collections">`, `TData = FeeCollectionOut`. Columns: **Amount** → `<Money amount={row.original.amount} />`; **Method** (`method`); **Collected** → `<FormattedDateTime value={row.original.collected_at} />`. Empty `{ title: "No collections yet", description: "Recorded collections appear here." }`.

- [ ] **Step 2: `RecordCollectionButton` test (failing)** — mock `refresh` + `useAuth` (`resources.fees.recordCollection`). Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`. Props `assessmentId="a1"`, `status="assessed"`, `glAccounts=[{id:CA,code:"1010",name:"Cash",account_type:"asset"}]` (CA real uuid). Click "Record collection" → fill amount "5000", pick method "Cash", pick contra account → submit → `recordCollection(expect.objectContaining({ fee_assessment_id:"a1", amount:"5000", method:"cash", contra_account_id: CA }))`; toast "Collection recorded". Also: render with `status="paid"` → assert no "Record collection" button.

- [ ] **Step 3: Implement `RecordCollectionButton.tsx`** (client) — return `null` if `status` ∈ {paid, waived, cancelled}. `useState` open + fresh `idempotency_key`. `useForm<FeeCollectionInput>({ resolver: zodResolver(feeCollectionSchema), defaultValues: { fee_assessment_id: assessmentId, amount: "", method: "cash", contra_account_id: "", idempotency_key: idemKey } })`. `<Button onClick>` opens a `<Dialog>` form: amount (`<MoneyInput>`), method (`<Select>`: cash / journal_voucher), contra_account_id (`<Select>` from glAccounts, value=id), submit. `useTypedMutation<FeeCollectionOut, FeeCollectionInput>` → `resources.fees.recordCollection(values)` cast `{ data?, error? }`; onSuccess close + `toast.success("Collection recorded")` + `router.refresh()`; onError `apiErrorMessage`.

- [ ] **Step 4: Implement `[id]/page.tsx`** (server) — `const { id } = await params;`; `fees.getAssessment(id)` cast `{ data?: FeeAssessmentDetailOut }`; `notFound()` if absent. Promise.all: `fees.getType(assessment.fee_type_id)` (`{ data?: FeeTypeOut }`) + `ledger.listAccounts({})` (`{ data?: GlAccountOption[] }`). Header: `<h1>{feeType?.name ?? "Fee assessment"}</h1>` + `<StatusBadge entity="fee_assessment" status={assessment.status} />` + `<RecordCollectionButton assessmentId={id} status={assessment.status} glAccounts={accounts ?? []} />`. Read-only `<Card>`: target (`{assessment.target_type} · {assessment.target_id}`), amount (`<Money>`), period (`<FormattedDate value={assessment.period_start} />` + period_end when set), assessed (`<FormattedDateTime value={assessment.assessed_at} />`), due/paid (`<FormattedDate>` when set), waiver reason (when set). Then **Collections** `<h2>` + `<CollectionsTable rows={assessment.collections} />`. No AuditBar. `export const metadata = { title: "Fee assessment" }`.

- [ ] **Step 5: Run the test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-fees/RecordCollectionButton
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/fees/assessments/[id]/" admin/apps/portal/src/__tests__/tenant-fees/RecordCollectionButton.test.tsx
git commit -m "feat(portal): SACCO fee assessment detail + record collection

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Verification + PR

- [ ] **Step 1: Package + portal gate**:
```bash
cd admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test delta over the 250 (3d-4) baseline.

- [ ] **Step 2: Contract spot-checks**:
  - [ ] No backend changes: `git diff --name-only main...HEAD | grep -E '^app/'` empty; `grep -E '^alembic/'` empty.
  - [ ] No api-client changes: `git diff --name-only main...HEAD | grep 'api-client'` empty.
  - [ ] No `@sacco/ui` changes (fee_assessment entity already exists): `git diff --name-only main...HEAD | grep 'packages/ui'` empty.
  - [ ] Changes under `admin/` + `docs/` only.

- [ ] **Step 3: Final holistic review** — fee types list/create (GL selects)/detail+edit; assessments list (type-name join + status); create assessment target options switch with target_type; assessment detail shows collections + record-collection (hidden when paid). No AuditBar/maker-checker; tenant-auth only.

- [ ] **Step 4: Push + PR** (base `main`):
```bash
git push -u origin feat/sacco-portal/05-fees
gh pr create --base main --title "feat(portal): SACCO admin — Fees module (Phase 3e)" --body "$(cat <<'EOF'
## Summary
- Fifth SACCO-operator module (Phase 3e): **fee types** (list/create/detail+edit), **assessments** (list/create/detail), and **collections** (recorded from assessment detail; partial collection supported).
- **Schema fixes**: corrected the stale `feeTriggerKindSchema` (`scheduled`→`schedule`), made collection `contra_account_id` required for both cash + journal_voucher, made assessment `period_end` optional + added the `share_account` target. Added fee read types.
- Assessment create uses a **dynamic target selector** — `target_type` (member/loan/savings_account/share_account) drives a reactive `target_id` select populated from the matching resource (members/loans/savings/shares), all labelled on the page.
- Reuses the existing `fee_assessment` StatusBadge. All flows are **direct (201)** — no maker-checker.
- **No backend or api-client changes.**

## Test plan
- `@sacco/schemas`, `@sacco/api-client`, `@sacco/portal` test/typecheck/lint green.

> Phase 3: Members (3a) + Savings (3b) + Shares (3c) + Credit (3d) + Fees (this). Reports (3f) remains.
> CI note: Lint fails environmentally on this repo (runner-queue issue); reproduced clean locally.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** schema fixes + read types → T1; fee types list → T2; fee type create → T3; fee type detail+edit → T4; assessments list → T5; assessment create (dynamic target) → T6; assessment detail + collections → T7; verify/PR → T8.
- **Type consistency:** `FeeTypeOut`/`FeeAssessmentOut`/`FeeAssessmentDetailOut`/`FeeCollectionOut` (T1) consumed by T2–T7; `AssessmentRow` (T5) page-built; `TargetMap`/`TargetOption`/`FeeTypeOption` (T6) page-built; `GlAccountOption` reused (T3 income/receivable codes, T7 contra id). GL codes by **code** in the fee-type form; contra account by **id** in collections. Assessment status → `entity="fee_assessment"`.
- **Verify-at-execution:** `feeTypePatchSchema` is `.strict()` (don't send extra keys); `<DateInput>` interaction shape (mirror billing `AssignPlanForm`); `<Checkbox>` Radix (`checked`/`onCheckedChange`); RHF `watch`/`setValue` for the reactive target select; Next 15 `params` Promise; `FeeTypeOut.percentage_rate`/`percentage_basis` may be null (display guards).
- **No backend tests** — no backend change.
