# SACCO Admin Portal — Credit / Applications + Guarantors (Phase 3d-2) Design

**Date:** 2026-06-21
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan d (Credit), part 2 — Applications + Guarantors
**Status:** Approved

## Context

3d-2 is the second credit sub-module (after 3d-1 Loan products, merged). It builds
the **loan application lifecycle** plus **guarantors**. The credit api-client
resource already exists and is complete; `@sacco/schemas/credit.ts` already has
`loanApplicationSchema` (input). What's missing: read types
(`LoanApplicationOut`, `GuarantorOut`), a guarantor-nominate + reject schema, two
new `StatusBadge` entities, and the screens.

Unlike 3a–3c (whose maker-checker actions only *created* approval requests and
deferred the checker side to a future generic inbox), the application
approve/reject/withdraw endpoints live **directly on the application resource**.
So 3d-2 implements a real **checker side** on the application detail page — the
first place the operator portal can decide an approvable operation.

Reuses the tenant-operator pattern (`getTenantPageContext()` server-fetch,
in-memory `<DataTable>`, RHF/Zod forms, `<StatusBadge>`, client-side member/product
name joins).

## Backend facts (authoritative — already in place, no changes)

Gate on every credit route is `CurrentTenantUser`. The credit **api-client
resource is complete** (`resources.credit.{listApplications, createApplication,
getApplication, approveApplication, rejectApplication, withdrawApplication,
listGuarantors, addGuarantor, acceptGuarantor, declineGuarantor, listProducts}`)
— each carries the `as never` wart → cast `{ data?, error? }`.

### Application lifecycle
- `POST /credit/applications` (201) → `LoanApplicationOut`. **The maker step** —
  creates the application **and** a `credit.approve_application` approval request
  (quorum = the product's `required_approvals`). `LoanApplicationCreateIn`:
  `loan_product_id, member_id, requested_amount (Decimal), requested_term_periods
  (int), purpose?, disbursement_destination (str), disbursement_account_id?
  (uuid), idempotency_key`. **Submit validates `disbursement_destination` ∈ the
  product's `disbursement_destinations`** (else 400). `disbursement_account_id` is
  **optional at submit** — bound at disburse-time (3d-3).
- `GET /credit/applications` (`?member_id`, `?status`) → `list[LoanApplicationOut]`.
- `GET /credit/applications/{id}` → `LoanApplicationOut`. Missing → 404.
- `POST /credit/applications/{id}/approve` → `LoanApplicationOut`. **Checker step**
  — calls `ApprovalService.approve(request_id, actor, comment?)`; advances quorum;
  executes when met. `LoanApplicationApproveIn`: `comment?`. Self-approval (maker
  == checker) → 400. No pending request → 400.
- `POST /credit/applications/{id}/reject` → `LoanApplicationOut`. `LoanApplicationRejectIn`:
  `reason?`. Sets status `rejected`.
- `POST /credit/applications/{id}/withdraw` → `LoanApplicationOut`. Withdraws a
  pending application (resolved to the original submitter server-side). Terminal
  statuses (approved/rejected/withdrawn/cancelled) → 400.
- **Application statuses:** `pending, approved, rejected, withdrawn, cancelled`.

`LoanApplicationOut` fields: `id, loan_product_id, member_id, requested_amount,
requested_term_periods, approved_amount?, approved_term_periods?, reviewed_by?,
reviewed_at?, purpose?, disbursement_destination, disbursement_account_id?,
status, rejection_reason?, decided_by?, decided_at?, approval_request_id?,
idempotency_key, created_at, updated_at`. (Decimals as JSON strings; ints as
numbers; uuids/datetimes as strings.)

### Guarantors
- `POST /credit/applications/{id}/guarantors` (201) → `list[GuarantorOut]`.
  `GuarantorNominateIn`: `guarantor_member_ids: list[uuid]`.
- `GET /credit/applications/{id}/guarantors` → `list[GuarantorOut]`.
- `POST /credit/guarantors/{guarantor_id}/accept` → `GuarantorOut`.
  `GuarantorConsentIn`: `guarantor_member_id`. (Operator records consent
  out-of-band; the member id confirms the row.)
- `POST /credit/guarantors/{guarantor_id}/decline` → `GuarantorOut` (same body).
- **Guarantor statuses:** `pending, accepted, declined, released`.

`GuarantorOut` fields: `id, loan_application_id, guarantor_member_id,
guaranteed_amount (Decimal string), status, consented_at?`.

- `GET /credit/products` → `list[LoanProductOut]`; `GET /members` →
  `list[MemberOut]` — for the form selects + client-side name joins.

## New supporting pieces

### `@sacco/ui` — status maps (contract S)
Add to `StatusBadge/status-maps.ts`:
- `StatusEntity` union: `+ "loan_application" | "guarantor"`.
- `LOAN_APPLICATION_STATUS`: pending→`info` "Pending", approved→`success`
  "Approved", rejected→`danger` "Rejected", withdrawn→`neutral` "Withdrawn",
  cancelled→`neutral` "Cancelled".
- `GUARANTOR_STATUS`: pending→`info` "Pending", accepted→`success` "Accepted",
  declined→`danger` "Declined", released→`neutral` "Released".
- Register both in `ENTITY_MAPS`.
(Unknown statuses already fall back to `neutral` with the raw value.)

### `@sacco/schemas/credit.ts`
- Add read types `LoanApplicationOut`, `GuarantorOut` (mirror the backend shapes).
- Convert `loanApplicationSchema.requested_term_periods` from `z.number().int()`
  to `intString({ min: 1 })` (form-friendly; Pydantic lax-coerces). Keep
  `disbursement_account_id` optional but **drop it from the form** (bound later).
- Add `guarantorNominateSchema = z.object({ guarantor_member_ids:
  z.array(uuid).min(1) })`.
- Add `loanApplicationRejectSchema = z.object({ reason: z.string().trim().min(1)
  .max(1000) })` (the form requires a reason even though the backend allows null,
  for audit clarity) → `LoanApplicationRejectInput`.

## Screens (under `app/(tenant-authed)/credit/applications/*`)

All server-fetched via `getTenantPageContext()`; cast resource results to
`{ data?, error? }`. Tenant-auth gating only.

### `/credit/applications` — applications list
- Server: `credit.listApplications({})` + `members.list({})` +
  `credit.listProducts({})` (Promise.all); build a `member_id→label` and
  `product_id→name` map.
- `<ApplicationsTable rows>`: in-memory `<DataTable>` (`id="loan-applications"`,
  `TData = ApplicationRow`). `ApplicationRow = { id, member_label, product_name,
  requested_amount, requested_term_periods, status }`. Columns: **Member** (links
  to `/credit/applications/{id}`), **Product**, **Amount** (`<Money>`), **Term**
  (`<Count>`), **Status** (`<StatusBadge entity="loan_application" status={…} />`).
  Empty: "No loan applications yet."
- Header: **New application** → `/credit/applications/new`.
- (Status filter via the DataTable's filter slot is a nice-to-have; v1 may render
  all and rely on in-memory search. Keep simple — no server-side filter.)

### `/credit/applications/new` — submit application
- Server: `members.list({})` + `credit.listProducts({})` passed in.
- RHF + `zodResolver(loanApplicationSchema)` (a fresh `idempotency_key` via
  `useState(() => crypto.randomUUID())`). Fields via `<FormField>`:
  loan_product_id (`<Select>` from products), member_id (`<Select>` from members),
  requested_amount (`<MoneyInput>`), requested_term_periods (`<Input
  inputMode="numeric">`), purpose (`<Textarea>`), disbursement_destination
  (`<Select>`: member_savings / cash / internal_gl). Optional `?member_id=`
  pre-selects the member.
- On submit → `credit.createApplication(values)` (201 → `LoanApplicationOut`) →
  toast "Application submitted" → `router.push("/credit/applications/${data.id}")`.
  400 (e.g. destination not allowed by product) surfaces via `apiErrorMessage`.

### `/credit/applications/[id]` — detail + decisions + guarantors
- Server (Promise.all): `credit.getApplication(id)` (`notFound()` if absent),
  `credit.listGuarantors(id)`, `members.list({})` (name resolution),
  `credit.getProduct(application.loan_product_id)` (product name + required
  approvals). 
- Header: `<h1>{product?.name ?? "Loan application"}</h1>` +
  `<StatusBadge entity="loan_application" status={application.status} />`.
- `<MakerCheckerBanner>` when `status === "pending"` (shows the operation is
  awaiting approval; `required_approvals` from the product surfaces the quorum).
- Read-only `<Card>`: member (label), requested amount (`<Money>`), term
  (`<Count>`), purpose, disbursement destination, approved amount/term (when set),
  rejection reason (when set), decided by/at (`<FormattedDateTime>`).
- `<ApplicationActions>` (client) — rendered only when `status === "pending"`:
  - **Approve** → `<ConfirmDialog>` ("Approve this loan application? This records
    your approval.") → `credit.approveApplication(id, {})` → toast → `router.refresh()`.
    Self-approval / quorum errors surface via toast.
  - **Reject** → a small `<Dialog>` form with a required reason `<Textarea>`
    (`loanApplicationRejectSchema`) → `credit.rejectApplication(id, { reason })` →
    toast → refresh.
  - **Withdraw** → `<ConfirmDialog destructive>` → `credit.withdrawApplication(id,
    {})` → toast → refresh.
- `<GuarantorsSection>` (client) — always shown:
  - Lists guarantors: member label, `guaranteed_amount` (`<Money>`),
    `<StatusBadge entity="guarantor" status={…} />`; for `pending` rows, **Accept**
    / **Decline** buttons (`<ConfirmDialog>` each) → `credit.acceptGuarantor(gid,
    { guarantor_member_id })` / `declineGuarantor(...)` → refresh.
  - **Nominate guarantor(s)**: a `<Dialog>` form — a member multi-select
    (checkbox list of members not already nominated; `guarantorNominateSchema`) →
    `credit.addGuarantor(applicationId, { guarantor_member_ids })` → refresh.
  - Member names resolved from the `members.list()` map passed down from the page.

## File structure

**`@sacco/ui`:** modify `src/components/StatusBadge/status-maps.ts`;
(test) `src/components/StatusBadge/*.test.tsx` may need a row — verify.
**`@sacco/schemas`:** modify `src/credit.ts`; extend `src/__tests__/credit.test.ts`.
**`@sacco/portal`:**
- `app/(tenant-authed)/credit/applications/page.tsx` + `_components/ApplicationsTable.tsx`.
- `app/(tenant-authed)/credit/applications/new/page.tsx` + `_components/CreateApplicationForm.tsx`.
- `app/(tenant-authed)/credit/applications/[id]/page.tsx` +
  `_components/{ApplicationActions,GuarantorsSection}.tsx`.
- Tests under `apps/portal/src/__tests__/tenant-credit/`.
- **No api-client changes, no backend changes.**

## Open items to verify at execution
- `<MakerCheckerBanner>` props (label / count / variant).
- `<ConfirmDialog>` props (open/onOpenChange/title/description/onConfirm/destructive/busy).
- `<StatusBadge>` test file — does adding entities require updating an exhaustive
  test? (extend if so).
- `<Count>` for integer term display; `<Money>` for amounts.
- Whether a credit "Applications" sidebar sub-link is wanted (the single "Credit"
  nav lands on products; applications reachable via an in-page link from `/credit`
  and from member context). For 3d-2: add a **link from `/credit`** (products
  landing) to `/credit/applications`, and a header link back — no new sidebar
  entry (nav stays one "Credit" item; revisit in 3d-3).

## Out of scope (deferred)
- Disbursement (3d-3) and the `disbursement_account_id` binding at application time.
- Member-detail loan/application section (3d-3 — unified with real loans).
- Restructure / write-off / recover / payroll (3d-4).
- Dynamic destination options per selected product (static 3-value select +
  backend validation in v1).
- `<AuditBar>`; server-side list pagination/filter (in-memory like 3a–3c).

## Testing strategy
- **@sacco/ui:** `status-maps` / StatusBadge test — `loan_application` and
  `guarantor` entities resolve known statuses and fall back for unknown.
- **@sacco/schemas:** `credit.test.ts` — `loanApplicationSchema` accepts an
  integer-string term and rejects a non-numeric one; `guarantorNominateSchema`
  requires ≥1 member; `loanApplicationRejectSchema` requires a reason;
  `LoanApplicationOut`/`GuarantorOut` structurally usable.
- **Portal:** Vitest + Testing Library —
  - `ApplicationsTable` (member-name join + status badge render; empty state).
  - `CreateApplicationForm` (selects populated; submit calls `createApplication`
    and redirects; blank required field blocks).
  - `ApplicationActions` (Approve confirm calls `approveApplication`; Reject
    requires reason then calls `rejectApplication`; Withdraw confirms → call).
  - `GuarantorsSection` (renders guarantor rows with badges; Nominate submits
    member ids; Accept/Decline call with the row's member id).
- Per-package `test` + `typecheck` + `lint` green. No backend tests.
