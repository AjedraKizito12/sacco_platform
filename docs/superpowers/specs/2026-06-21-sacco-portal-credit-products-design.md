# SACCO Admin Portal — Credit / Loan Products (Phase 3d-1) Design

**Date:** 2026-06-21
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan d (Credit), part 1 — Loan products
**Status:** Approved

## Phase 3d decomposition (context)

Credit is far larger than the savings/shares modules (~30 backend endpoints).
It is built as **four independently-shippable sub-modules**, each its own
spec → plan → PR, each branched off `main` after the previous merges (no PR
stacking — lesson from 3b/3c):

1. **3d-1 Loan products** (this doc) — products list/create/detail/edit.
2. **3d-2 Applications + Guarantors** — application lifecycle (incl. maker-checker
   approve, reject, withdraw) + guarantor add/accept/decline.
3. **3d-3 Loans (servicing)** — loans list/detail (snapshot balances), schedule,
   disburse, repayments, statement (view + PDF).
4. **3d-4 Workout + Payroll** — write-off (maker-checker), recover, restructure
   (maker-checker) + payroll batches.

## Context

3d-1 is the foundational credit sub-module. Loan applications (3d-2) reference a
product, so products come first. Unlike savings/shares, the credit **api-client
resource already exists and is complete** (`resources.credit.{listProducts,
createProduct, getProduct, patchProduct, …}`), and `@sacco/schemas/credit.ts`
already has **input** Zod schemas — but the product schema is **stale** (its
enums predate the live backend) and there are **no read types**. So 3d-1 is a
near-pure client plus a schema correction.

This module reuses the tenant-operator pattern from 3a–3c
(`getTenantPageContext()` server-fetch, in-memory `<DataTable>`, RHF/Zod forms),
and adds the first **detail + edit** screen pair in the SACCO-operator portal.

## Schema correction (the only non-screen deliverable)

The existing `loanProductSchema` / `disbursementDestinationSchema` in
`@sacco/schemas/credit.ts` do **not** match the live backend
(`app/modules/credit/services/product.py`). They must be corrected, or product
creation 400s. Verified backend enum values:

| Field | Backend (`product.py`, authoritative) |
|---|---|
| `interest_method` | `flat`, `reducing_balance` |
| `repayment_frequency` | `weekly`, `biweekly`, `monthly`, `quarterly`, `lump_sum` |
| `disbursement_destinations` (per item) | `member_savings`, `cash`, `internal_gl` |
| `repayment_allocation` | `INTEREST_PRINCIPAL` (single value) |

Corrections (all in `@sacco/schemas/credit.ts`):
- `disbursementDestinationSchema` → `z.enum(["member_savings","cash","internal_gl"])`.
  (Shared with `loanApplicationSchema.disbursement_destination` — fixing it now
  also unblocks 3d-2.)
- `loanProductSchema.repayment_frequency` → the 5-value enum above.
- `loanProductSchema.repayment_allocation` → `z.enum(["INTEREST_PRINCIPAL"])`
  (default `"INTEREST_PRINCIPAL"`).
- `loanProductSchema.max_term_periods` and `required_approvals` → `intString({min})`
  (string-on-wire, Pydantic lax-coerces — the shares pattern; form-friendly).
  `interest_method` already matches (no change).

> Changing these is allowed (contract J — form schemas live in `@sacco/schemas`).
> No current consumer uses `loanProductSchema` in a form yet, so the type changes
> are safe. `loanApplicationSchema.requested_term_periods` stays `z.number()` for
> now (3d-2 will revisit if needed) — only the shared destination enum changes.

## Read type to add

`@sacco/schemas/credit.ts` — add `LoanProductOut` mirroring
`app/modules/credit/schemas.py::LoanProductOut`:

```ts
export interface LoanProductOut {
  id: string;
  name: string;
  description: string | null;
  interest_method: string;
  annual_interest_rate: string;     // Decimal as JSON string
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

## Backend facts (authoritative — already in place, no changes)

Gate on every credit route is `CurrentTenantUser`.

- `GET /credit/products` (`?include_inactive`) → `list[LoanProductOut]`.
- `POST /credit/products` (201) → `LoanProductOut`. `LoanProductCreateIn`:
  `name, description?, interest_method, annual_interest_rate (Decimal),
  repayment_frequency, max_term_periods (int), min_amount, max_amount,
  required_approvals (int, default 1), disbursement_destinations (list[str]),
  repayment_allocation (default "INTEREST_PRINCIPAL"),
  gl_principal_receivable_code, gl_interest_receivable_code,
  gl_interest_income_code, gl_loan_loss_expense_code?, penalty_fee_type_code?,
  write_off_threshold (default 0)`. Invalid enum/amount → **400**.
- `GET /credit/products/{id}` → `LoanProductOut`. Missing → **404**.
- `PATCH /credit/products/{id}` → `LoanProductOut`. `LoanProductPatchIn` accepts
  **only** `name?, description?, penalty_fee_type_code?, write_off_threshold?`.
  Missing → 404; invalid → 400.
- `GET /ledger/accounts` → `list[AccountOut]` (`id, code, name, account_type`) —
  populates the GL-code `<Select>`s (value = `code`).

### Pre-built portal surface (verified)

- **api-client:** `resources.credit.{listProducts, createProduct, getProduct,
  patchProduct}` all exist (carry the `as never` wart → cast `{ data?, error? }`).
- **@sacco/schemas:** `loanProductSchema` (to be corrected) + `LoanProductInput`;
  `intString`, `moneyString`, `percentageString` helpers exist. **Add**
  `LoanProductOut` read type.
- **@sacco/ui:** `DataTable`, `FormField`, `Input`, `MoneyInput`,
  `PercentageInput`, `Select`, `Checkbox`, `Money`, `Percentage`, `Card`,
  `Button`, `toast`. (No StatusBadge for products — `is_active` is a bool.)
- **portal:** `getTenantPageContext()`, the `(tenant-authed)` layout, and the
  tenant sidebar `/credit` link (verify; add if absent — see Open items).

## Screens (under `app/(tenant-authed)/credit/*`)

All server-fetched via `getTenantPageContext()`; cast resource results to
`{ data?, error? }`. Gating is tenant-auth only.

### `/credit` — products landing

- Server: `credit.listProducts({})` → `LoanProductOut[]`.
- `<ProductsTable>`: in-memory `<DataTable>` (`id="loan-products"`,
  `TData = LoanProductOut`). Columns: **Name** (links to
  `/credit/products/{id}`), **Interest** (`<Percentage value={annual_interest_rate} />`),
  **Method** (`interest_method`), **Frequency** (`repayment_frequency`),
  **Min** (`<Money amount={min_amount} />`), **Max** (`<Money amount={max_amount} />`),
  **Active** (Yes/No). Empty: "No loan products yet."
- Header: **Create product** → `/credit/products/new`.

### `/credit/products/new` — create product

- RHF + `zodResolver(loanProductSchema)`. Fields via `<FormField>`:
  - name (`<Input>`), description (`<Textarea>`, optional).
  - interest_method (`<Select>`: flat / reducing_balance).
  - annual_interest_rate (`<PercentageInput>`).
  - repayment_frequency (`<Select>`: weekly/biweekly/monthly/quarterly/lump_sum).
  - max_term_periods (`<Input inputMode="numeric">`).
  - min_amount, max_amount (`<MoneyInput>`).
  - required_approvals (`<Input inputMode="numeric">`, default "1").
  - repayment_allocation (`<Select>`: single option `INTEREST_PRINCIPAL`,
    defaulted).
  - disbursement_destinations (**checkbox group** — `<Checkbox>` per value
    member_savings / cash / internal_gl; at least one required).
  - gl_principal_receivable_code, gl_interest_receivable_code,
    gl_interest_income_code, gl_loan_loss_expense_code (each `<Select>` from
    `ledger.listAccounts()`, **value = account `code`**, label `{code} — {name}`).
  - penalty_fee_type_code (`<Input>`, optional), write_off_threshold
    (`<MoneyInput>`, optional).
- On submit: drop empty optionals (`description`, `penalty_fee_type_code`,
  `gl_loan_loss_expense_code`, `write_off_threshold`) → `credit.createProduct` →
  toast "Product created" → `router.push("/credit")`. 400 surfaces via
  `apiErrorMessage`.
- The GL `<Select>` options come from `ledger.listAccounts()`, server-fetched on
  the page and passed in.

### `/credit/products/[id]` — product detail + edit

- Server: `credit.getProduct(id)` → `LoanProductOut` (`notFound()` if absent).
  No ledger fetch needed — the detail page shows GL **codes** as read-only text,
  and the limited edit form touches no GL fields.
- Read-only `<Card>`s grouping: **Terms** (interest method, rate, frequency,
  max term, min–max amount, required approvals, allocation, destinations),
  **GL mapping** (the four GL codes), **Risk** (penalty fee type, write-off
  threshold), **Meta** (active, created/updated via `<FormattedDateTime>`).
- An **Edit** button reveals `<EditProductForm>` (client) limited to the PATCH
  fields: name (`<Input>`), description (`<Textarea>`), penalty_fee_type_code
  (`<Input>`), write_off_threshold (`<MoneyInput>`). On submit →
  `credit.patchProduct(id, body)` (drop unchanged/empty) → toast → `router.refresh()`.
- A new `loanProductPatchSchema` (Zod) covers the 4 editable fields (all
  optional). No StatusBadge, no AuditBar.

## New supporting pieces

- **@sacco/schemas:** correct `loanProductSchema` + `disbursementDestinationSchema`;
  add `loanProductPatchSchema` + `LoanProductPatchInput`; add `LoanProductOut`.
- **portal:** `ProductsTable`, `CreateProductForm`, product detail page,
  `EditProductForm`.
- **No api-client changes** (resource complete). **No backend changes.**

## File structure

**`@sacco/schemas`:** modify `src/credit.ts`; (test) `src/__tests__/credit.test.ts`.
**`@sacco/portal`:**
- `app/(tenant-authed)/credit/page.tsx` + `_components/ProductsTable.tsx`.
- `app/(tenant-authed)/credit/products/new/page.tsx` + `_components/CreateProductForm.tsx`.
- `app/(tenant-authed)/credit/products/[id]/page.tsx` + `_components/EditProductForm.tsx`.
- Tests under `apps/portal/src/__tests__/tenant-credit/`.

## Open items to verify at execution

- **Sidebar `/credit` link**: confirm it exists in `AppShellSidebar.tsx`; if not,
  add it (within `admin/`, allowed). (Members/Savings/Shares links exist; the
  memory says all module links exist — verify.)
- **`<Checkbox>` props** (checked/onCheckedChange) for the destinations group.
- **`<PercentageInput>` / `<MoneyInput>` prop shape** (value/onValueChange/onBlur/
  name/ref) — proven in savings/shares forms.
- **`ledger.listAccounts` AccountOut** fields (`id, code, name, account_type`).

## Out of scope (deferred)

- Product deactivation/archival (no backend endpoint).
- Applications, loans, guarantors, repayments, workout, payroll (3d-2 … 3d-4).
- `<AuditBar>` on tenant records; tenant approvals inbox.
- Server-side pagination (in-memory like 3a–3c).

## Testing strategy

- **@sacco/schemas:** `credit.test.ts` — corrected enums accept the backend
  values and reject the old wrong ones; `loanProductSchema` rejects a blank name;
  `loanProductPatchSchema` accepts a partial payload; `LoanProductOut` structurally
  usable.
- **Portal:** Vitest + Testing Library —
  - `ProductsTable` (row renders name + interest; empty state).
  - `CreateProductForm` (blank name blocks; full valid submit calls
    `createProduct` with the corrected enums + GL codes and redirects; at-least-one
    destination enforced).
  - `EditProductForm` (patches only the 4 editable fields; redirects/refreshes).
- Per-package `test` + `typecheck` + `lint` green. (No backend tests — no backend
  change.)
