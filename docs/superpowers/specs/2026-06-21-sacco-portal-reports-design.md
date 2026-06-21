# SACCO Admin Portal — Reports (Phase 3f) Design

**Date:** 2026-06-21
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan f — Reports
**Status:** Approved

## Context

3f is the **final Phase-3 module**. It surfaces the five reporting endpoints
(trial balance, loan portfolio, income statement, savings statement, fee
collection) plus the report-runs list, each as a filterable on-screen table with
PDF/CSV download. The reporting api-client resource is complete; there is **no
`@sacco/schemas` reporting file** yet, and no `report_run` StatusBadge entity — both
are added here. Reports read **precomputed runs** (Celery beat tasks); the portal is
a pure read client. All endpoints are `CurrentTenantUser`-gated and support
`format=json|pdf|csv` (json renders the table; pdf/csv download a file).

Reuses the tenant-operator pattern (`getTenantPageContext()` server-fetch, in-memory
`<DataTable>`, `<StatusBadge>`), adds **filter-driven report pages** (URL-query
state) and a **dynamic download proxy route**.

## Backend facts (authoritative — already in place, no changes)

Gate is `CurrentTenantUser`. api-client `reporting.{trialBalance, loanPortfolio,
incomeStatement, savingsStatement, feeCollection, listRuns}` all exist (cast
`{ data?, error? }`). Each report endpoint: `format` ∈ {json, pdf, csv} (default
json). JSON returns the structured Out below; pdf/csv return a file `Response`.
Reports read the **latest successful run**; if no run exists the endpoint errors
(surface via `apiErrorMessage`).

- `GET /reporting/trial-balance` — `as_of? (date)`, `format`. JSON `TrialBalanceOut`:
  `as_of_date, generated_at, lines[]`; line = `account_id, account_code,
  account_name, account_type, debit_total, credit_total, balance`.
- `GET /reporting/loan-portfolio` — `as_of?`, `status` ∈ {all, disbursed, in_arrears,
  written_off} (default all), `format`. JSON `LoanPortfolioOut`: `as_of_date,
  generated_at, rows[]`; row = `loan_id, loan_reference, member_id, product_name,
  disbursed_at, maturity_date?, status, outstanding_principal, accrued_interest,
  total_written_off, days_in_arrears, aging_bucket`.
- `GET /reporting/income-statement` — `from_date` (**required**), `to_date`
  (**required**), `format`. JSON `IncomeStatementOut`: `period_start, period_end,
  generated_at, lines[]`; line = `account_id, account_code, account_name,
  account_type, debit_total, credit_total, net_movement`.
- `GET /reporting/savings-statement` — `member_id` (**required**, uuid), `from_date?`,
  `to_date?`, `format`. JSON `SavingsStatementOut`: `member_id, period_start,
  period_end, generated_at, lines[]`; line = `savings_account_id, member_id,
  posted_at, transaction_type, narration?, amount, running_balance`.
- `GET /reporting/fee-collection` — `from_date` (**required**), `to_date`
  (**required**), `fee_type_id?` (uuid), `format`. JSON `FeeCollectionOut`:
  `period_start, period_end, generated_at, rows[]`; row = `fee_type_id,
  fee_type_name, target_type, assessed_total, collected_total, outstanding_total,
  waived_total`.
- `GET /reporting/runs` (`?report_type`?) → `list[ReportRunOut]`: `id, report_type,
  as_of_date, status (running|done|failed), started_at, completed_at?, error_detail?`.
- `GET /members`, `GET /fees/types` — for the savings-statement member select and
  the fee-collection fee-type filter.

## New supporting pieces

### `@sacco/ui` — `report_run` StatusBadge entity (contract S)
Add `StatusEntity` `+ "report_run"`, a `REPORT_RUN_STATUS` map (running→`info`
"Running", done→`success` "Done", failed→`danger` "Failed"), register in `ENTITY_MAPS`.

### `@sacco/schemas/reporting.ts` (new)
Read types mirroring the backend (Decimals as strings; ints as numbers; counts via
`<Count>`): `TrialBalanceLineOut`, `TrialBalanceOut`, `LoanPortfolioRowOut`,
`LoanPortfolioOut`, `IncomeStatementLineOut`, `IncomeStatementOut`,
`SavingsStatementLineOut`, `SavingsStatementOut`, `FeeCollectionRowOut`,
`FeeCollectionOut`, `ReportRunOut`. Export from `src/index.ts`. (No input/Zod
schemas — filters are URL query params, not forms.)

### Download proxy — `app/api/reporting/[report]/route.ts` (new)
One dynamic route handles all five reports' pdf/csv downloads (clones the
loan-statement PDF proxy). It validates `report` against an allow-list
(`trial-balance | loan-portfolio | income-statement | savings-statement |
fee-collection`), reads `format` (pdf|csv) + forwards the remaining query, and
proxies `GET ${API_BASE}/reporting/{report}?format=…&<query>` with the tenant
access token (`getServerAccessToken("tenant")`) + `X-Tenant-Slug`
(`getServerTenantSlug()`), returning the upstream `Content-Type` +
`Content-Disposition`. Unknown report → 404; no session → 401.

## Screens (under `app/(tenant-authed)/reports/*`)

All server-fetched via `getTenantPageContext()`; cast `{ data?, error? }`. Tenant-auth.
The sidebar **Reports** link already points to `/reports`. Filters are URL-query
state; each page has a small **client filter form** that `router.push`es the new
query. Each report page renders **Download PDF / CSV** links pointing to
`/api/reporting/{report}?format=pdf|csv&<sameQuery>`.

### `/reports` — index
- A simple page with a `<Card>` of links to each report + the runs list. No data fetch.

### `/reports/trial-balance`
- `searchParams`: `as_of?`. Filter: an `<AsOfFilter>` (a `<DateInput>` "As of" +
  Apply). Server: `reporting.trialBalance({ as_of })` → `TrialBalanceOut`.
- `<TrialBalanceTable>` (in-memory `<DataTable id="trial-balance">`): Account code,
  Account name, Type, Debit (`<Money>`), Credit (`<Money>`), Balance (`<Money>`).
  Header shows `as_of_date` + Download PDF/CSV.

### `/reports/loan-portfolio`
- `searchParams`: `as_of?`, `status?`. Filter: `<DateInput>` "As of" + a status
  `<Select>` (all/disbursed/in_arrears/written_off). Server:
  `reporting.loanPortfolio({ as_of, status })`.
- `<LoanPortfolioTable>` (`id="loan-portfolio"`): Loan ref, Product, Status
  (`<StatusBadge entity="loan">`), Outstanding (`<Money>`), Accrued interest
  (`<Money>`), Days in arrears (`<Count>`), Aging bucket. Download PDF/CSV.

### `/reports/income-statement`
- `searchParams`: `from_date?`, `to_date?`. Both **required** to fetch — render the
  filter alone until both present. Filter: two `<DateInput>`s + Apply. Server (when
  both set): `reporting.incomeStatement({ from_date, to_date })`.
- `<IncomeStatementTable>` (`id="income-statement"`): Account code, Account name,
  Type, Debit (`<Money>`), Credit (`<Money>`), Net movement (`<Money>`). Download
  PDF/CSV (enabled when both dates set).

### `/reports/savings-statement`
- `searchParams`: `member_id?`, `from_date?`, `to_date?`. `member_id` **required** to
  fetch. Filter: a member `<Select>` (from `members.list()`, passed in) + two
  `<DateInput>`s + Apply. Server (when member set): `reporting.savingsStatement({
  member_id, from_date, to_date })`.
- `<SavingsStatementTable>` (`id="savings-statement"`): Posted (`<FormattedDateTime>`),
  Type, Narration (`?? "—"`), Amount (`<Money>`), Running balance (`<Money>`).
  Download PDF/CSV.

### `/reports/fee-collection`
- `searchParams`: `from_date?`, `to_date?`, `fee_type_id?`. from/to **required**.
  Filter: two `<DateInput>`s + an optional fee-type `<Select>` (from
  `fees.listTypes()`, passed in) + Apply. Server (when both dates set):
  `reporting.feeCollection({ from_date, to_date, fee_type_id })`.
- `<FeeCollectionTable>` (`id="fee-collection"`): Fee type, Target, Assessed
  (`<Money>`), Collected (`<Money>`), Outstanding (`<Money>`), Waived (`<Money>`).
  Download PDF/CSV.

### `/reports/runs`
- Server: `reporting.listRuns({})` → `ReportRunOut[]`.
- `<RunsTable>` (`id="report-runs"`): Report type, As of (`<FormattedDate>`), Status
  (`<StatusBadge entity="report_run">`), Started (`<FormattedDateTime>`), Completed
  (`<FormattedDateTime>` or "—"). Empty: "No report runs yet."

## DataTable row ids
`<DataTable>` requires `TData extends { id: string }`. Several report rows have no
unique id (savings-statement lines repeat `savings_account_id`; fee-collection rows
key on `fee_type_id` which may repeat across `target_type`; income/trial-balance can
use `account_id`). Each table maps its rows to add a synthetic `id: String(index)`
before passing to `<DataTable>` (the 3d-3 statement-table pattern) — render the
backend fields from the row, use the synthetic id only for `getRowId`.

## Filter components (client)
Small client components that read current params (`useSearchParams`) and on Apply
`router.push(\`?${new URLSearchParams(...)}\`)`. Reuse where shapes match:
- `<AsOfFilter>` (single date) — trial balance.
- `<DateRangeFilter>` (from/to) — income statement, fee collection (with an extra
  fee-type select), savings (with member select).
- Loan portfolio uses as_of + status.
Keep them per-page-simple; do not over-abstract. Each renders a `<DateInput>` /
`<Select>` and an Apply `<Button>`.

## File structure
**`@sacco/ui`:** modify `StatusBadge/status-maps.ts` + test.
**`@sacco/schemas`:** create `src/reporting.ts`; modify `src/index.ts`; test
`src/__tests__/reporting.test.ts`.
**`@sacco/portal`:**
- `app/api/reporting/[report]/route.ts` + route test.
- `app/(tenant-authed)/reports/page.tsx` (index).
- `app/(tenant-authed)/reports/trial-balance/page.tsx` + `_components/{AsOfFilter,TrialBalanceTable}.tsx`.
- `app/(tenant-authed)/reports/loan-portfolio/page.tsx` + `_components/{LoanPortfolioFilter,LoanPortfolioTable}.tsx`.
- `app/(tenant-authed)/reports/income-statement/page.tsx` + `_components/{DateRangeFilter,IncomeStatementTable}.tsx`.
- `app/(tenant-authed)/reports/savings-statement/page.tsx` + `_components/{SavingsStatementFilter,SavingsStatementTable}.tsx`.
- `app/(tenant-authed)/reports/fee-collection/page.tsx` + `_components/{FeeCollectionFilter,FeeCollectionTable}.tsx`.
- `app/(tenant-authed)/reports/runs/page.tsx` + `_components/RunsTable.tsx`.
- Tests under `apps/portal/src/__tests__/tenant-reports/`.
- **No api-client changes, no backend changes.**

## Out of scope (deferred)
- Triggering report runs on demand (beat-task only; the portal reads precomputed
  runs). The runs list is read-only.
- HTML report format (json table + pdf/csv cover it).
- `<AuditBar>`; server-side pagination (in-memory; reports are run-scoped snapshots).
- Member/loan name resolution beyond what the report rows carry (loan portfolio
  shows `member_id`; the report is a precomputed snapshot).

## Testing strategy
- **@sacco/ui:** `report_run` status renders a known status + fallback.
- **@sacco/schemas:** read types structurally usable.
- **@sacco/portal:**
  - Download route: 401 without session; 404 for an unknown report; proxies a known
    report with bearer + slug + format (mirror the loan-statement route test).
  - Each report table: a row renders + empty/zero-state (the in-memory `<DataTable>`s).
  - `RunsTable`: row + `report_run` badge + empty.
  - One filter component (`DateRangeFilter`): Apply pushes the expected query string
    (mock `useRouter`/`useSearchParams`).
- Per-package `test` + `typecheck` + `lint` green. No backend tests.
