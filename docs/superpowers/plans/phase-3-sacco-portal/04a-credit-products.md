# SACCO Admin Portal — Credit / Loan Products (Phase 3d-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-21):** background subagents can't get Edit approval; run **inline**. **Confirm typecheck PASSES before committing** (SP20 lesson). No backend tests in this sub-module (no backend change). Portal/package tests run via `pnpm --filter`.

**Goal:** The first credit sub-module — loan products list/create/detail/edit — as a near-pure client, plus a correction of the stale `loanProductSchema` enums to match the live backend.

**Architecture:** Correct `@sacco/schemas/credit.ts` (enums + read type + patch schema), then tenant-authed portal screens under `app/(tenant-authed)/credit/*` server-fetched via `getTenantPageContext()`. In-memory `<DataTable>`, RHF/Zod forms, GL-code `<Select>`s from `ledger.listAccounts()` (value = account code), and the operator portal's first detail+edit screen pair. Clones the 3a–3c tenant-operator pattern.

**Tech Stack:** Next.js 15, React 19, TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library. No Python changes.

## Global Constraints

- **Branch:** `feat/sacco-portal/04a-credit-products`, off `main` (no PR stacking — 3b/3c lesson).
- **No backend changes, no api-client changes.** `resources.credit.{listProducts,createProduct,getProduct,patchProduct}` already exist (carry the `as never` wart → cast `{ data?, error? }`). `resources.ledger.listAccounts` exists.
- **Backend enum values are authoritative** (`app/modules/credit/services/product.py`): `interest_method` ∈ {flat, reducing_balance}; `repayment_frequency` ∈ {weekly, biweekly, monthly, quarterly, lump_sum}; `disbursement_destinations` item ∈ {member_savings, cash, internal_gl}; `repayment_allocation` = INTEREST_PRINCIPAL (only value).
- **PATCH accepts only** `name, description, penalty_fee_type_code, write_off_threshold`.
- **Money** (`min_amount`/`max_amount`/`write_off_threshold`) → `<Money>` / `<MoneyInput>`; **rate** → `<Percentage>` / `<PercentageInput>`; **integer** fields (`max_term_periods`, `required_approvals`) → `intString` + `<Input inputMode="numeric">` (Pydantic lax-coerces "5"→5).
- **No StatusBadge** (`is_active` is a bool), **no `<AuditBar>`**, tenant-auth gating only via `getTenantPageContext()`.
- **DRY/YAGNI/TDD, frequent commits.** Confirm typecheck passes before each commit.

---

## Task 1: `@sacco/schemas` — correct enums + `LoanProductOut` + `loanProductPatchSchema`

**Files:**
- Modify: `admin/packages/schemas/src/credit.ts`
- Test: `admin/packages/schemas/src/__tests__/credit.test.ts` (create)

**Interfaces:**
- Produces: corrected `disbursementDestinationSchema`, `loanProductSchema`; new `loanProductPatchSchema` + `LoanProductPatchInput`; `LoanProductOut` read type.

- [ ] **Step 1: Failing test** — create `src/__tests__/credit.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  loanProductSchema,
  loanProductPatchSchema,
  disbursementDestinationSchema,
  type LoanProductOut,
} from "../credit";

const validProduct = {
  name: "Personal Loan",
  description: "",
  interest_method: "reducing_balance",
  annual_interest_rate: "18.5",
  repayment_frequency: "monthly",
  max_term_periods: "24",
  min_amount: "100000",
  max_amount: "5000000",
  required_approvals: "1",
  repayment_allocation: "INTEREST_PRINCIPAL",
  disbursement_destinations: ["member_savings"],
  gl_principal_receivable_code: "1200",
  gl_interest_receivable_code: "1210",
  gl_interest_income_code: "4100",
  gl_loan_loss_expense_code: "5100",
  penalty_fee_type_code: "",
  write_off_threshold: "0",
};

describe("credit product schema (corrected to backend)", () => {
  it("accepts the backend's real enum values", () => {
    expect(loanProductSchema.safeParse(validProduct).success).toBe(true);
  });
  it("rejects stale destination values", () => {
    expect(disbursementDestinationSchema.safeParse("savings_account").success).toBe(false);
    expect(disbursementDestinationSchema.safeParse("member_savings").success).toBe(true);
  });
  it("rejects a stale repayment_frequency", () => {
    expect(
      loanProductSchema.safeParse({ ...validProduct, repayment_frequency: "annual" }).success,
    ).toBe(false);
    expect(
      loanProductSchema.safeParse({ ...validProduct, repayment_frequency: "lump_sum" }).success,
    ).toBe(true);
  });
  it("rejects a blank name and an empty destinations list", () => {
    expect(loanProductSchema.safeParse({ ...validProduct, name: "" }).success).toBe(false);
    expect(
      loanProductSchema.safeParse({ ...validProduct, disbursement_destinations: [] }).success,
    ).toBe(false);
  });
  it("patch schema accepts a partial payload", () => {
    expect(loanProductPatchSchema.safeParse({ name: "Renamed" }).success).toBe(true);
    expect(loanProductPatchSchema.safeParse({}).success).toBe(true);
  });
  it("LoanProductOut is structurally usable", () => {
    const p: LoanProductOut = {
      id: "p1", name: "Personal Loan", description: null,
      interest_method: "reducing_balance", annual_interest_rate: "18.5000",
      repayment_frequency: "monthly", max_term_periods: 24,
      min_amount: "100000.0000", max_amount: "5000000.0000", required_approvals: 1,
      disbursement_destinations: ["member_savings"], repayment_allocation: "INTEREST_PRINCIPAL",
      gl_principal_receivable_code: "1200", gl_interest_receivable_code: "1210",
      gl_interest_income_code: "4100", gl_loan_loss_expense_code: "5100",
      penalty_fee_type_code: null, write_off_threshold: "0.0000", is_active: true,
      created_at: "2026-06-21T00:00:00Z", updated_at: "2026-06-21T00:00:00Z",
    };
    expect(p.max_term_periods).toBe(24);
  });
});
```

Run: `cd admin && pnpm --filter @sacco/schemas test -- credit` → FAIL (compile/enum errors).

- [ ] **Step 2: Correct `disbursementDestinationSchema`** in `credit.ts`:

```ts
export const disbursementDestinationSchema = z.enum([
  "member_savings",
  "cash",
  "internal_gl",
]);
```

- [ ] **Step 3: Correct `loanProductSchema`** in `credit.ts` (import `intString` from `./common`):

```ts
export const loanProductSchema = z.object({
  name: z.string().trim().min(1).max(200),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
  interest_method: z.enum(["flat", "reducing_balance"]),
  annual_interest_rate: percentageString({ max: 100 }),
  repayment_frequency: z.enum([
    "weekly",
    "biweekly",
    "monthly",
    "quarterly",
    "lump_sum",
  ]),
  max_term_periods: intString({ min: 1 }),
  min_amount: moneyString({ min: "0.01" }),
  max_amount: moneyString({ min: "0.01" }),
  required_approvals: intString({ min: 1 }),
  repayment_allocation: z.enum(["INTEREST_PRINCIPAL"]),
  disbursement_destinations: z.array(disbursementDestinationSchema).min(1),
  gl_principal_receivable_code: z.string().trim().min(1).max(20),
  gl_interest_receivable_code: z.string().trim().min(1).max(20),
  gl_interest_income_code: z.string().trim().min(1).max(20),
  gl_loan_loss_expense_code: z.string().trim().max(20).optional().or(z.literal("")),
  penalty_fee_type_code: z.string().trim().max(40).optional().or(z.literal("")),
  write_off_threshold: moneyString({ min: "0" }).optional().or(z.literal("")),
});
```

> Update the `./common` import line to include `intString`:
> `import { idempotencyKey, intString, moneyString, percentageString, uuid } from "./common";`
> Leave `loanApplicationSchema` and the other schemas untouched (the shared
> `disbursementDestinationSchema` correction flows into the application schema
> automatically and is correct there too).

- [ ] **Step 4: Add `loanProductPatchSchema` + read type** (after `loanProductSchema`):

```ts
export const loanProductPatchSchema = z.object({
  name: z.string().trim().min(1).max(200).optional(),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
  penalty_fee_type_code: z.string().trim().max(40).optional().or(z.literal("")),
  write_off_threshold: moneyString({ min: "0" }).optional().or(z.literal("")),
});

export type LoanProductPatchInput = z.infer<typeof loanProductPatchSchema>;
```

And add `LoanProductOut` (after the existing `export type LoanProductInput` line):

```ts
export interface LoanProductOut {
  id: string;
  name: string;
  description: string | null;
  interest_method: string;
  annual_interest_rate: string;
  repayment_frequency: string;
  max_term_periods: number;
  min_amount: string;
  max_amount: string;
  required_approvals: number;
  disbursement_destinations: string[];
  repayment_allocation: string;
  gl_principal_receivable_code: string;
  gl_interest_receivable_code: string;
  gl_interest_income_code: string;
  gl_loan_loss_expense_code: string | null;
  penalty_fee_type_code: string | null;
  write_off_threshold: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
```

> `credit.ts` is already exported from `src/index.ts` (verify `export * from "./credit";` is present — it is).

- [ ] **Step 5: Run test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/schemas test -- credit && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
git add admin/packages/schemas/src/credit.ts admin/packages/schemas/src/__tests__/credit.test.ts
git commit -m "feat(portal): correct loan-product schema enums + add read/patch types

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Products table + `/credit` landing + sidebar

> Clone the 3c shares equivalents: `app/(tenant-authed)/shares/_components/ProductsTable.tsx`, `shares/page.tsx`, and the test `apps/portal/src/__tests__/tenant-shares/ProductsTable.test.tsx`. Apply the credit deltas below.

**Files:**
- Create: `app/(tenant-authed)/credit/_components/ProductsTable.tsx`, `credit/page.tsx`
- Modify: `admin/apps/portal/src/components/AppShellSidebar.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/ProductsTable.test.tsx`

**Interfaces:**
- Consumes: `LoanProductOut`, `resources.credit.listProducts`.

- [ ] **Step 1: `ProductsTable` test (failing)** — clone the shares `ProductsTable.test.tsx`. `TData = LoanProductOut` (use the read-type object from Task 1's test as the row). Mock `useTableUrlState` + `next/navigation`; wrap in `<TenantCurrencyProvider>`. Assert: a row links the name to `/credit/products/p1`; renders interest "18.50%"; the empty state "No loan products yet".

- [ ] **Step 2: Implement `ProductsTable.tsx`** — clone shares `ProductsTable`. `"use client"`, in-memory filter/sort/paginate, `useTableUrlState`. `id="loan-products"`, `TData = LoanProductOut`. Columns:
  - **Name** → `<Link href={\`/credit/products/${row.original.id}\`} className="font-medium text-[var(--text-link)] hover:underline">{row.original.name}</Link>`
  - **Interest** → `<Percentage value={row.original.annual_interest_rate} />`
  - **Method** → `row.original.interest_method`
  - **Frequency** → `row.original.repayment_frequency`
  - **Min** → `<Money amount={row.original.min_amount} />`
  - **Max** → `<Money amount={row.original.max_amount} />`
  - **Active** → `row.original.is_active ? "Yes" : "No"`

  Empty `{ title: "No loan products yet", description: "Create a product to start taking applications." }`. `state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}`. Import `Money`, `Percentage` from `@sacco/ui`.

- [ ] **Step 3: Implement `credit/page.tsx`** (server) — clone shares `page.tsx`: `getTenantPageContext()`, `resources.credit.listProducts({})` cast `{ data?: LoanProductOut[] }`, `<h1>Loan products</h1>`, **Create product** `<Button asChild><Link href="/credit/products/new">`, `<ProductsTable rows={data ?? []} />`. `export const metadata = { title: "Credit" }`.

- [ ] **Step 4: Repoint the sidebar** — in `AppShellSidebar.tsx`, change the credit `SidebarItem` so the operator can reach the (only) credit page that exists:

```tsx
              <SidebarItem
                href="/credit"
                icon={<Banknote size={ICON_SIZE} strokeWidth={1.75} />}
                label="Credit"
                active={isActive("/credit")}
              />
```
(was `href="/credit/loans"` label `"Loans"`. 3d-3 revisits nav when the loans servicing screens land.)

- [ ] **Step 5: Run the test + portal typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/ProductsTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/page.tsx" "admin/apps/portal/app/(tenant-authed)/credit/_components/ProductsTable.tsx" admin/apps/portal/src/components/AppShellSidebar.tsx admin/apps/portal/src/__tests__/tenant-credit/ProductsTable.test.tsx
git commit -m "feat(portal): SACCO loan products list + Credit nav

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Create product — `<CreateProductForm>` + `/credit/products/new`

> Clone the 3c shares `CreateProductForm` wiring (RHF + zodResolver + useTypedMutation + GL `<Select>` + drop-empty-optional on submit). Apply the larger credit field set below.

**Files:**
- Create: `app/(tenant-authed)/credit/products/new/_components/CreateProductForm.tsx`, `credit/products/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/CreateProductForm.test.tsx`

**Interfaces:**
- Consumes: `loanProductSchema`/`LoanProductInput`, `LoanProductOut`, `resources.credit.createProduct`, `resources.ledger.listAccounts`.
- Produces: exported `GlAccountOption` `{ id; code; name; account_type }`.

- [ ] **Step 1: `CreateProductForm` test (failing)** — clone shares `CreateProductForm.test.tsx`. Mock `next/navigation` push + `useAuth` (`resources.credit.createProduct`). Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`. Pass `glAccounts={[{id:"g1",code:"1200",name:"Loans Receivable",account_type:"asset"}]}` (reuse the same single account id for all four GL selects). Two cases:
  - blank name → `createProduct` not called.
  - fill name, rate, term, min/max, pick interest_method/frequency, check a destination, pick the four GL accounts → submit → `createProduct` called with `expect.objectContaining({ name, interest_method: "reducing_balance", repayment_frequency: "monthly", repayment_allocation: "INTEREST_PRINCIPAL", disbursement_destinations: ["member_savings"], gl_principal_receivable_code: "1200" })` and `push("/credit")`.

  > Selecting all four GL `<Select>`s in one test is verbose; query each by its label (`/principal receivable/i`, `/interest receivable/i`, `/interest income/i`, `/loan loss/i`) and pick the single option. `required_approvals` defaults to "1"; `repayment_allocation` defaults to "INTEREST_PRINCIPAL" — no interaction needed if defaulted.

- [ ] **Step 2: Implement `CreateProductForm.tsx`** (client). Structure mirrors shares `CreateProductForm`. Props `{ glAccounts: GlAccountOption[] }`. `useForm<LoanProductInput>({ resolver: zodResolver(loanProductSchema), defaultValues: { name:"", description:"", interest_method:"reducing_balance", annual_interest_rate:"", repayment_frequency:"monthly", max_term_periods:"", min_amount:"", max_amount:"", required_approvals:"1", repayment_allocation:"INTEREST_PRINCIPAL", disbursement_destinations:[], gl_principal_receivable_code:"", gl_interest_receivable_code:"", gl_interest_income_code:"", gl_loan_loss_expense_code:"", penalty_fee_type_code:"", write_off_threshold:"" } })`.

  Fields via `<FormField>`:
  - name (`<Input>`), description (`<Textarea>`).
  - interest_method (`<Select>`: flat, reducing_balance).
  - annual_interest_rate (`<PercentageInput value onValueChange onBlur name ref>`).
  - repayment_frequency (`<Select>`: weekly, biweekly, monthly, quarterly, lump_sum).
  - max_term_periods (`<Input inputMode="numeric">`).
  - min_amount, max_amount, write_off_threshold (`<MoneyInput>`).
  - required_approvals (`<Input inputMode="numeric">`).
  - repayment_allocation (`<Select>`: single item INTEREST_PRINCIPAL).
  - disbursement_destinations — a checkbox group. Use a small local helper bound to the RHF field:

```tsx
const DESTS = [
  { value: "member_savings", label: "Member savings" },
  { value: "cash", label: "Cash" },
  { value: "internal_gl", label: "Internal GL" },
] as const;

<FormField control={form.control} name="disbursement_destinations" label="Disbursement destinations" required
  render={({ field }) => (
    <div className="flex flex-col gap-2">
      {DESTS.map((d) => {
        const checked = (field.value ?? []).includes(d.value);
        return (
          <label key={d.value} className="flex items-center gap-2">
            <Checkbox
              checked={checked}
              onCheckedChange={(c) => {
                const next = new Set<string>(field.value ?? []);
                if (c) next.add(d.value); else next.delete(d.value);
                field.onChange([...next]);
              }}
            />
            <span>{d.label}</span>
          </label>
        );
      })}
    </div>
  )} />
```

  - The four GL `<Select>`s — one `glSelect(field, id, describedBy, invalid)` helper (mirror shares `AccountActions.glSelect`) mapping `glAccounts` → `<SelectItem value={a.code}>{a.code} — {a.name}</SelectItem>` (**value = code**). Labels: "Principal receivable GL", "Interest receivable GL", "Interest income GL", "Loan-loss expense GL (optional)".
  - penalty_fee_type_code (`<Input>`, optional).

  `useTypedMutation<LoanProductOut, LoanProductInput>` → on mutate build `body = { ...values }` and **drop empties**: for `description`, `gl_loan_loss_expense_code`, `penalty_fee_type_code`, `write_off_threshold` — `if (!body[k]) delete body[k];` (bracket access — `Record<string, unknown>`). `resources.credit.createProduct(body)` cast `{ data?, error? }`; onSuccess `toast.success("Product created")` + `router.push("/credit")`; onError `apiErrorMessage`. Cancel → `/credit`.

- [ ] **Step 3: Implement `products/new/page.tsx`** (server) — `getTenantPageContext()`, fetch `resources.ledger.listAccounts({})` cast `{ data?: GlAccountOption[] }`, `<h1>Create loan product</h1>`, `<CreateProductForm glAccounts={data ?? []} />`.

- [ ] **Step 4: Run the test + portal typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/CreateProductForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/products/new/" admin/apps/portal/src/__tests__/tenant-credit/CreateProductForm.test.tsx
git commit -m "feat(portal): SACCO loan product create form

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Product detail + edit — `[id]/page.tsx` + `<EditProductForm>`

**Files:**
- Create: `app/(tenant-authed)/credit/products/[id]/page.tsx`, `_components/EditProductForm.tsx`
- Test: `apps/portal/src/__tests__/tenant-credit/EditProductForm.test.tsx`

**Interfaces:**
- Consumes: `LoanProductOut`, `loanProductPatchSchema`/`LoanProductPatchInput`, `resources.credit.{getProduct,patchProduct}`.

- [ ] **Step 1: `EditProductForm` test (failing)** — mock `next/navigation` (`refresh`) + `useAuth` (`resources.credit.patchProduct`). Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`. Props `{ product: LoanProductOut }`. Cases:
  - renders with the product's current name/threshold prefilled.
  - change the name → submit → `patchProduct(product.id, expect.objectContaining({ name: "New name" }))`; toast "Product updated"; `refresh()` called.

- [ ] **Step 2: Implement `EditProductForm.tsx`** (client) — `useForm<LoanProductPatchInput>({ resolver: zodResolver(loanProductPatchSchema), defaultValues: { name: product.name, description: product.description ?? "", penalty_fee_type_code: product.penalty_fee_type_code ?? "", write_off_threshold: product.write_off_threshold } })`. Fields via `<FormField>`: name (`<Input>`), description (`<Textarea>`), penalty_fee_type_code (`<Input>`), write_off_threshold (`<MoneyInput>`). `useTypedMutation<LoanProductOut, LoanProductPatchInput>` → build `body` dropping empty `description`/`penalty_fee_type_code` (bracket access) → `resources.credit.patchProduct(product.id, body)` cast `{ data?, error? }`; onSuccess `toast.success("Product updated")` + `router.refresh()`; onError `apiErrorMessage`.

- [ ] **Step 3: Implement `[id]/page.tsx`** (server) — `const { id } = await params;` (`params: Promise<{ id: string }>`); `resources.credit.getProduct(id)` cast `{ data?: LoanProductOut }`; `notFound()` if absent. Header `<h1>{product.name}</h1>`. Read-only `<Card>`s:
  - **Terms**: interest method, `<Percentage value={annual_interest_rate} />`, frequency, max term (`max_term_periods`), `<Money amount={min_amount} />`–`<Money amount={max_amount} />`, required approvals, allocation, destinations (`disbursement_destinations.join(", ")`).
  - **GL mapping**: the four GL codes (raw text).
  - **Risk**: penalty fee type (`?? "—"`), `<Money amount={write_off_threshold} />`.
  - **Meta**: active (Yes/No), created/updated via `<FormattedDateTime value={…} />`.
  Then `<EditProductForm product={product} />` (place it in an "Edit" `<Card>` below, or behind a details/summary — keep it simple: render the form in its own `<Card>` titled "Edit"). No StatusBadge, no AuditBar. `export const metadata = { title: "Loan product" }`.

- [ ] **Step 4: Run the test + portal typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-credit/EditProductForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/credit/products/[id]/" admin/apps/portal/src/__tests__/tenant-credit/EditProductForm.test.tsx
git commit -m "feat(portal): SACCO loan product detail + edit

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Verification + PR

- [ ] **Step 1: Packages + portal gate**:
```bash
cd admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test delta over the 211 (3c) baseline (+ ProductsTable, CreateProductForm, EditProductForm cases).

- [ ] **Step 2: Contract spot-checks**:
  - [ ] No backend changes: `git diff --name-only main...HEAD | grep -E '^app/'` empty; `grep -E '^alembic/'` empty.
  - [ ] No api-client changes: `git diff --name-only main...HEAD | grep 'api-client'` empty.
  - [ ] Portal/schemas changes under `admin/` + `docs/` only.
  - [ ] No StatusBadge for products: `rg 'entity="loan_product"' "admin/apps/portal/app/(tenant-authed)/credit"` empty.

- [ ] **Step 3: Final holistic review** — products list (links to detail); create form posts the corrected enums + GL codes and redirects; detail shows all fields read-only; edit patches only the 4 mutable fields; sidebar "Credit" → `/credit` works. No AuditBar/StatusBadge; tenant-auth gating only.

- [ ] **Step 4: Push + PR** (base `main`):
```bash
git push -u origin feat/sacco-portal/04a-credit-products
gh pr create --base main --title "feat(portal): SACCO admin — Credit loan products (Phase 3d-1)" --body "$(cat <<'EOF'
## Summary
- First **Credit** sub-module (Phase 3d-1 of 4): loan products list / create / detail / edit.
- **Schema correction**: the existing `loanProductSchema` / `disbursementDestinationSchema` enums were stale vs the live backend (`product.py`). Corrected `repayment_frequency` (weekly/biweekly/monthly/quarterly/lump_sum), `disbursement_destinations` (member_savings/cash/internal_gl), `repayment_allocation` (INTEREST_PRINCIPAL); numeric fields → `intString`. Added `LoanProductOut` read type + `loanProductPatchSchema`. (The shared destination fix also unblocks 3d-2's application form.)
- Pure client otherwise — the credit api-client resource and most input schemas already existed. No backend or api-client changes.
- GL account codes captured via `<Select>` from `ledger.listAccounts()` (value = code). Destinations via a checkbox group. First operator-portal **detail + edit** screen pair; the edit form exposes only the 4 fields the backend PATCH accepts.
- Sidebar "Loans → /credit/loans" repointed to "Credit → /credit" (the only credit page that exists yet); 3d-3 revisits nav when loans servicing ships.

## Test plan
- `@sacco/schemas`, `@sacco/api-client`, `@sacco/portal` test/typecheck/lint green.

> Phase 3d is decomposed into 4 sub-modules (products → applications+guarantors → loans servicing → workout+payroll), each its own PR off main.
> CI note: Lint fails environmentally on this repo (runner-queue issue); reproduced clean locally.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** schema correction + read/patch types → T1; products list + nav → T2; create form (all fields, GL selects, checkbox destinations) → T3; detail + limited edit → T4; verify/PR → T5.
- **Type consistency:** `LoanProductOut` (T1) consumed by T2/T3/T4; `LoanProductInput` (corrected `loanProductSchema`) by T3; `LoanProductPatchInput` by T4. Integer fields are `intString` (string in form, `number` in read type). GL `<Select>` value = `code` (string), matching the create payload.
- **Verify-at-execution:** `<Checkbox>` is a Radix fork → `checked` + `onCheckedChange(boolean | "indeterminate")`; `<PercentageInput>`/`<MoneyInput>` prop shape (value/onValueChange/onBlur/name/ref — proven in savings/shares); `ledger.listAccounts` AccountOut fields (`id, code, name, account_type`); Next 15 `params` is a Promise; `<FormattedDateTime>` import from `@sacco/ui`.
- **No backend tests** — no backend change in this sub-module.
