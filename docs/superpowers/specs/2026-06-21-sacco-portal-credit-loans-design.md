# SACCO Admin Portal — Credit / Loans Servicing (Phase 3d-3) Design

**Date:** 2026-06-21
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan d (Credit), part 3 — Loans servicing
**Status:** Approved

## Context

3d-3 is the third credit sub-module (after products 3d-1 and applications+guarantors
3d-2, both merged). It makes loans **live and serviceable**: disburse an approved
application into a loan, then view balances / schedule / repayments / statement and
record repayments. The credit api-client resource is complete; what's missing on
the portal side: loan read types, the screens, a statement-PDF proxy route, and a
**correction to the 3d-2 application form** without which nothing is disbursable.

### Prerequisite correction (carried from 3d-2)

The disburse service (`app/modules/credit/services/disbursement.py`) shows two hard
facts:
- **`member_savings` disbursement is not supported in this version** (raises
  ValueError outright).
- For **`cash` / `internal_gl`**, `application.disbursement_account_id` (a GL account)
  is **required** at disburse — it is read from the application, not supplied at
  disburse (DisburseIn carries only `idempotency_key`).

3d-2's application form omitted `disbursement_account_id` and defaulted the
destination to `member_savings`, so **no application can currently be disbursed**.
3d-3 corrects this:
- `@sacco/schemas`: `loanApplicationSchema.disbursement_account_id` → **required**
  `uuid`.
- The 3d-2 `CreateApplicationForm` gains a required **GL-account `<Select>`**
  (from `ledger.listAccounts()`, value = account id) and its destination `<Select>`
  is restricted to **cash / internal_gl** (member_savings is unsupported by the
  backend disburse in v1). Its `new` page fetches ledger accounts and passes them in;
  the 3d-2 form test is updated.

## Backend facts (authoritative — already in place, no changes)

Gate on every credit route is `CurrentTenantUser`. The api-client `credit` resource
is complete (`listLoans, getLoan, disburse, getSchedule, listRepayments,
recordRepayment, getStatement, getStatementPdf, …`); cast `{ data?, error? }`.

- `POST /credit/loans/{application_id}/disburse` (201) → `LoanOut`. `DisburseIn`:
  `idempotency_key`. Acts on an **approved application**; creates the loan. Errors
  (e.g. member_savings unsupported, missing GL account, not approved) → 400 → toast.
- `GET /credit/loans` (`?member_id`, `?status`) → `list[LoanOut]`.
- `GET /credit/loans/{id}` → `LoanOut`. Missing → 404.
- `GET /credit/loans/{id}/schedule` → `list[LoanInstallmentOut]`.
- `GET /credit/loans/{id}/repayments` → `list[LoanRepaymentOut]`.
- `POST /credit/loans/{id}/repayments` (201) → `LoanRepaymentOut`. **Direct (no
  maker-checker).** `LoanRepaymentCreateIn`: `amount (Decimal > 0),
  payment_account_id (uuid), narration?, idempotency_key, savings_account_id?`.
- `GET /credit/loans/{id}/statement` → `LoanStatementOut` (`loan_id, from_date?,
  to_date?, lines: StatementLineOut[]`). `StatementLineOut`: `date, line_type,
  description, debit (Decimal), credit (Decimal), running_balance (Decimal)`.
- `GET /credit/loans/{id}/statement.pdf` → PDF (WeasyPrint).
- `GET /ledger/accounts` → `list[AccountOut]` (`id, code, name, account_type`) —
  for the repayment GL select and the application-form GL select.

`LoanOut` fields: `id, loan_reference, loan_application_id, loan_product_id,
member_id, status, principal_amount, outstanding_principal, accrued_interest,
accrued_penalties, annual_interest_rate, interest_method, repayment_frequency,
term_periods, disbursement_destination, first_repayment_due?, maturity_date?,
disbursed_at?, created_at`. (Decimals/uuids/dates as JSON strings; ints as numbers.)

`LoanInstallmentOut`: `id, loan_id, period_number (int), due_date, principal_due,
interest_due, total_due, principal_paid, interest_paid, status, paid_at?`.

`LoanRepaymentOut`: `id, loan_id, amount, principal_applied, interest_applied,
penalties_applied, overpayment, payment_account_id, journal_entry_id, posted_by,
narration?, idempotency_key, created_at`.

- **Loan status** uses the existing `StatusBadge entity="loan"` map (draft,
  submitted, approved, disbursing, disbursed, in_arrears, restructured, written_off,
  closed, rejected, withdrawn). No new StatusBadge entity. Installment status
  renders as plain text (no `loan_installment` entity in v1).

## New supporting pieces

### `@sacco/schemas/credit.ts`
- Make `loanApplicationSchema.disbursement_account_id` **required** `uuid`.
- Add read types: `LoanOut`, `LoanInstallmentOut`, `LoanRepaymentOut`,
  `StatementLineOut`, `LoanStatementOut`. (`loanRepaymentSchema` input already exists.)

### Statement-PDF proxy route
`app/api/credit/loans/[id]/statement-pdf/route.ts` — clones the invoice-PDF proxy
(`app/api/billing/me/invoices/[id]/pdf/route.ts`): server-side `GET
${API_BASE}/credit/loans/{id}/statement.pdf` with the tenant access token
(`getServerAccessToken("tenant")`) + `X-Tenant-Slug` (`getServerTenantSlug()`),
returns `application/pdf`. The detail page's "Download PDF" is a plain link to
`/api/credit/loans/{id}/statement-pdf` (no client blob handling).

## Screens

All server-fetched via `getTenantPageContext()`; cast `{ data?, error? }`. Tenant-auth
gating only.

### Application form correction + disburse (3d-2 modifies)
- `credit/applications/new` page + `CreateApplicationForm`: add the required GL
  `<Select>` (`disbursement_account_id`), restrict destination to cash/internal_gl;
  fetch `ledger.listAccounts()` on the page.
- `credit/applications/[id]` detail: when `application.status === "approved"`, render
  a **Disburse** action (`<DisburseButton applicationId>`): `<ConfirmDialog>` ("Disburse
  this loan? This creates the loan and posts the disbursement.") →
  `credit.disburse(applicationId, { idempotency_key })` (201 → `LoanOut`) → toast
  "Loan disbursed" → `router.push("/credit/loans/${loan.id}")`. Fresh idempotency key.

### `/credit/loans` — loans list
- Server: `credit.listLoans({})` + `members.list({})`; client-join member names.
- `<LoansTable>`: in-memory `<DataTable>` (`id="loans"`, `TData = LoanRow`).
  `LoanRow = { id, loan_reference, member_label, principal_amount,
  outstanding_principal, status }`. Columns: **Reference** (links to
  `/credit/loans/{id}`), **Member**, **Principal** (`<Money>`), **Outstanding**
  (`<Money>`), **Status** (`<StatusBadge entity="loan" status />`). Empty: "No loans
  yet."
- Header: link back to `/credit`.
- A **Loans** link is added to the `/credit` landing header (alongside Applications).

### `/credit/loans/[id]` — loan detail
- Server (Promise.all after `getLoan`): `credit.getLoan(id)` (`notFound()` if absent),
  `credit.getSchedule(id)`, `credit.listRepayments(id)`, `credit.getStatement(id)`,
  `members.list({})` (member label), and `ledger.listAccounts({})` (repayment GL select).
- Header: `<h1>{loan.loan_reference}</h1>` + `<StatusBadge entity="loan"
  status={loan.status} />` + `<RecordRepaymentButton loanId glAccounts />`.
- **Balances** `<Card>` (prominent): outstanding principal, accrued interest, accrued
  penalties (`<Money>`).
- **Terms** `<Card>`: member label, principal (`<Money>`), rate (`<Percentage>`),
  method, frequency, term (`<Count>`), destination, disbursed at / first due /
  maturity (`<FormattedDate>`).
- **Schedule** `<ScheduleTable>` (`id="loan-schedule"`, `TData = LoanInstallmentOut`):
  period (`<Count>`), due date (`<FormattedDate>`), principal due / interest due /
  total due (`<Money>`), paid (principal_paid + interest_paid `<Money>`), status (text).
- **Repayments** `<RepaymentsTable>` (`id="loan-repayments"`, `TData =
  LoanRepaymentOut`): date (`<FormattedDate value={created_at} />`), amount, principal
  applied, interest applied, penalties applied (`<Money>`).
- **Statement** `<StatementTable>` (lines: date, type, description, debit, credit,
  running balance) + a **Download PDF** link → `/api/credit/loans/{id}/statement-pdf`.
- No `<AuditBar>`.

### Record repayment (`<RecordRepaymentButton>` / form, client)
- A `<Dialog>` form (`zodResolver(loanRepaymentSchema)`, fresh `idempotency_key`):
  amount (`<MoneyInput>`), payment_account_id (`<Select>` from `ledger.listAccounts()`),
  narration (`<Textarea>`). (`savings_account_id` omitted in v1.) Submit →
  `credit.recordRepayment(loanId, body)` (201) → toast "Repayment recorded" +
  `router.refresh()`. **Direct.** 400 (e.g. overpayment) surfaces via `apiErrorMessage`.

### `/members/[id]` — Loans section (the 3d-2 deferral)
- Member detail additionally fetches `credit.listLoans({ member_id: id })` and renders
  a **Loans** `<Card>`: each loan's reference + outstanding (`<Money>`) +
  `<StatusBadge entity="loan">` + link to `/credit/loans/{id}`; empty → "No loans."

## File structure

**`@sacco/schemas`:** modify `src/credit.ts`; extend `src/__tests__/credit.test.ts`.
**`@sacco/portal`:**
- `app/api/credit/loans/[id]/statement-pdf/route.ts` (new).
- `app/(tenant-authed)/credit/applications/new/_components/CreateApplicationForm.tsx` (modify) + `new/page.tsx` (modify).
- `app/(tenant-authed)/credit/applications/[id]/_components/DisburseButton.tsx` (new) + `[id]/page.tsx` (modify).
- `app/(tenant-authed)/credit/loans/page.tsx` + `_components/LoansTable.tsx`.
- `app/(tenant-authed)/credit/loans/[id]/page.tsx` + `_components/{ScheduleTable,RepaymentsTable,StatementTable,RecordRepaymentButton}.tsx`.
- `app/(tenant-authed)/credit/page.tsx` (modify — Loans link).
- `app/(tenant-authed)/members/[id]/page.tsx` (modify) + `_components/MemberLoansSection.tsx`.
- Tests under `apps/portal/src/__tests__/tenant-credit/`.
- **No api-client changes, no backend changes.**

## Out of scope (deferred)
- member_savings disbursement (backend-unsupported in v1).
- Write-off / recover / restructure / payroll (3d-4).
- Statement date-range filter; repayment `savings_account_id` source.
- `<AuditBar>`; server-side list pagination (in-memory like prior modules).

## Testing strategy
- **@sacco/schemas:** `loanApplicationSchema` now rejects a missing
  `disbursement_account_id`; read types structurally usable.
- **Portal:** Vitest + Testing Library —
  - `CreateApplicationForm` (updated): GL select populated; submit includes
    `disbursement_account_id`; destination options are cash/internal_gl.
  - `DisburseButton` (confirm → `disburse` → redirect to the loan).
  - `LoansTable` (member join + status badge; empty).
  - `ScheduleTable` / `RepaymentsTable` / `StatementTable` (rows render; empty states).
  - `RecordRepaymentButton` (submit calls `recordRepayment`; refresh).
  - `MemberLoansSection` (lists loans; links; empty).
  - Statement-PDF route: a route unit test (mirrors the invoice-pdf-route test) —
    401 without a tenant session; proxies on success. (Match the existing
    `tenant-invoice-pdf-route.test.ts` shape.)
- Per-package `test` + `typecheck` + `lint` green. No backend tests.
