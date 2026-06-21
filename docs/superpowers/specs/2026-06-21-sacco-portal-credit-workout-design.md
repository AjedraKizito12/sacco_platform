# SACCO Admin Portal — Credit / Workout + Payroll (Phase 3d-4) Design

**Date:** 2026-06-21
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan d (Credit), part 4 — Workout + Payroll
**Status:** Approved

## Context

3d-4 is the **final credit sub-module** (after products 3d-1, applications 3d-2,
loans servicing 3d-3 — all merged). It adds loan **workout** (write-off, recover,
restructure) onto the existing loan detail page, plus **payroll batches**
(JSON-row creation + detail + reject). The credit api-client resource is complete;
what's missing on the portal side: workout/payroll read types, a corrected
restructuring-type enum, a `payroll_batch` StatusBadge entity, and the screens.

Reuses the tenant-operator pattern (server-fetch via `getTenantPageContext()`,
RHF/Zod form dialogs, `<StatusBadge>`, `<ConfirmDialog>`, in-memory `<DataTable>`).

## Backend facts (authoritative — already in place, no changes)

Gate on every credit route is `CurrentTenantUser`. The api-client `credit`
resource is complete (`writeOff, recover, restructure, listRestructurings,
createPayrollBatch, getPayrollBatch, rejectPayrollBatch, getLoan, …`); cast
`{ data?, error? }`.

### Workout (act on a loan)
- `POST /credit/loans/{id}/write-off` (201) → `WriteOffOut`
  (`direct: bool, approval_request_id: uuid|null, journal_entry_id: uuid|null`).
  **Dual behaviour:** below the product's `write_off_threshold` it posts directly
  (`direct=true`, `journal_entry_id` set); at/above threshold it creates a
  **quorum-2** maker-checker approval (`direct=false`, `approval_request_id` set).
  `WriteOffIn`: `amount (Decimal>0), reason, idempotency_key,
  loan_loss_account_code (str, default "5100")`.
- `POST /credit/loans/{id}/recover` (201) → `LoanRecoveryOut`
  (`journal_entry_id`). **Direct (no maker-checker).** Only valid on a written-off
  loan. `LoanRecoveryIn`: `amount (Decimal>0), reason (1..500), idempotency_key`.
- `POST /credit/loans/{id}/restructure` (**202**) → `{ approval_request_id }`.
  **Always maker-checker (quorum 2).** `RestructureIn`: `restructuring_type
  ('term_extension' | 'payment_holiday'), periods_added (int≥1), reason,
  idempotency_key`.
- `GET /credit/loans/{id}/restructurings` → `list[RestructuringOut]`
  (`id, loan_id, restructuring_type, periods_added, new_term_periods,
  new_maturity_date, reason, executed_at`). Lists **executed** restructurings.

> **Checker side deferred.** Write-off (above threshold) and restructure create
> **generic** tenant approval requests (`operation_type` `credit.write_off` /
> `credit.restructure`), approved via the generic `/approvals/{id}/approve` — i.e.
> the **tenant approvals inbox**, which is not built yet. So 3d-4 *creates* these
> approvals (the maker step); approving them is a later Phase-3 module. (This
> differs from 3d-2 applications, whose approve/reject lived on the application
> resource.)

### Payroll batches
- `POST /credit/payroll-batches` (201) → `PayrollBatchOut`. `PayrollBatchJsonIn`:
  `rows: [{ member_id: str, amount: Decimal }], clearing_account_id (uuid),
  idempotency_key`.
- `GET /credit/payroll-batches/{id}` → `PayrollBatchOut`
  (`id, reference, status, total_rows, matched_rows, unmatched_rows,
  total_amount, source_format, approval_request_id?`).
- `POST /credit/payroll-batches/{id}/reject` → `PayrollBatchOut`. 409 if not
  `pending_review`.
- **No payroll list endpoint** and **no per-line read** in `PayrollBatchOut` →
  the UI is create → redirect to detail-by-id → (reject). No browse, no line table.
- **Payroll statuses:** `pending_review, applied, rejected`.
- CSV upload (`POST /payroll-batches/csv`) is **out of scope** (multipart; deferred).
- `GET /ledger/accounts` → for the write-off GL-code select + payroll clearing
  account select.

## New supporting pieces

### `@sacco/ui` — `payroll_batch` StatusBadge entity (contract S)
Add `StatusEntity` `+ "payroll_batch"`, a `PAYROLL_BATCH_STATUS` map
(pending_review→`info` "Pending review", applied→`success` "Applied",
rejected→`danger` "Rejected"), and register it in `ENTITY_MAPS`.

### `@sacco/schemas/credit.ts`
- **Fix** `restructuringTypeSchema` → `z.enum(["term_extension","payment_holiday"])`
  (was the stale `interest_only_period`/`principal_holiday`).
- `loanRestructureSchema.periods_added` → `intString({ min: 1 })` (form-friendly;
  Pydantic coerces). (`loanWriteOffSchema` and `loanRecoverySchema` already exist
  and match the backend — `loan_loss_account_code` stays optional.)
- Add `payrollBatchSchema`:
  ```ts
  payrollRowSchema = z.object({ member_id: uuid, amount: moneyString({ min: "0.01" }) });
  payrollBatchSchema = z.object({
    rows: z.array(payrollRowSchema).min(1, "Add at least one row"),
    clearing_account_id: uuid,
    idempotency_key: idempotencyKey,
  });
  ```
- Add read types: `WriteOffOut` (`direct: boolean; approval_request_id: string|null;
  journal_entry_id: string|null`), `LoanRecoveryOut` (`journal_entry_id: string`),
  `RestructuringOut`, `PayrollBatchOut` (mirror backend).

## Screens

All server-fetched via `getTenantPageContext()`; cast `{ data?, error? }`. Tenant-auth.

### Loan detail (3d-3 modify) — workout actions + restructurings
- The `[id]/page.tsx` additionally fetches `credit.listRestructurings(id)`.
- Header actions gain `<LoanWorkoutActions loanId glAccounts status={loan.status} />`
  (the page already fetches `ledger.listAccounts()` for repayment).
- `<LoanWorkoutActions>` (client) — status-gated buttons + form dialogs:
  - `status === "written_off"` → **Recover** (`<Dialog>` form: amount, reason →
    `credit.recover(id, {...})` 201 → toast "Recovery posted" → `router.refresh()`).
  - otherwise (disbursed / in_arrears / restructured) → **Write-off** and
    **Restructure**:
    - **Write-off** form (amount, reason, loan_loss_account_code optional GL
      `<Select>` value=code) → `credit.writeOff(id, body)` (drop empty GL code).
      On success branch on `data.direct`: `true` → toast "Loan written off";
      `false` → toast "Write-off requested — pending approval (2 required)".
      `router.refresh()`.
    - **Restructure** form (restructuring_type `<Select>`: term_extension /
      payment_holiday; periods_added numeric `<Input>`; reason `<Textarea>`) →
      `credit.restructure(id, body)` (202) → toast "Restructuring requested —
      pending approval (2 required)" → `router.refresh()`. The dialog copy states
      it creates a maker-checker approval.
  - Fresh `idempotency_key` per dialog instance (contract L).
- A **Restructurings** `<RestructuringsTable>` section (in-memory `<DataTable>`,
  `TData = RestructuringOut`): type, periods added (`<Count>`), new term
  (`<Count>`), new maturity (`<FormattedDate>`), executed (`<FormattedDate>`).
  Empty: "No restructurings yet."

### `/credit/payroll/new` — create batch
- Server: `ledger.listAccounts({})` + `members.list({})` passed in.
- `<CreatePayrollBatchForm>` (client) — RHF `useFieldArray` over `rows`
  (`payrollBatchSchema`): each row a member `<Select>` (from members) + amount
  `<MoneyInput>`; **Add row** / **Remove row** buttons; a clearing-account
  `<Select>` (from ledger); fresh `idempotency_key`. Submit →
  `credit.createPayrollBatch(values)` (201 → `PayrollBatchOut`) → toast "Batch
  created" → `router.push("/credit/payroll/${data.id}")`. 400 → `apiErrorMessage`.

### `/credit/payroll/[id]` — batch detail
- Server: `credit.getPayrollBatch(id)` → `PayrollBatchOut` (`notFound()` if absent).
- Header: `<h1>{batch.reference}</h1>` + `<StatusBadge entity="payroll_batch"
  status={batch.status} />` + `<RejectPayrollBatchButton batchId status />`.
- Summary `<Card>`: total rows (`<Count>`), matched (`<Count>`), unmatched
  (`<Count>`), total amount (`<Money>`), source format.
- `<RejectPayrollBatchButton>` (client) — shown when `status === "pending_review"`:
  `<ConfirmDialog destructive>` → `credit.rejectPayrollBatch(id, {})` → toast
  "Batch rejected" → `router.refresh()`.

### Nav
- `/credit` landing header gains a **Payroll** link → `/credit/payroll/new`
  (alongside Applications / Loans). (No payroll list to link to.)

## File structure

**`@sacco/ui`:** modify `StatusBadge/status-maps.ts`; extend `StatusBadge.test.tsx`.
**`@sacco/schemas`:** modify `src/credit.ts`; extend `src/__tests__/credit.test.ts`.
**`@sacco/portal`:**
- `app/(tenant-authed)/credit/loans/[id]/_components/LoanWorkoutActions.tsx` (new),
  `_components/RestructuringsTable.tsx` (new); `[id]/page.tsx` (modify).
- `app/(tenant-authed)/credit/payroll/new/page.tsx` + `_components/CreatePayrollBatchForm.tsx`.
- `app/(tenant-authed)/credit/payroll/[id]/page.tsx` + `_components/RejectPayrollBatchButton.tsx`.
- `app/(tenant-authed)/credit/page.tsx` (modify — Payroll link).
- Tests under `apps/portal/src/__tests__/tenant-credit/`.
- **No api-client changes, no backend changes.**

## Out of scope (deferred)
- The **tenant approvals inbox** (checker side for write-off/restructure approvals).
- CSV payroll upload; per-line payroll breakdown (no API); payroll batch list (no API).
- `<AuditBar>`; server-side pagination.

## Testing strategy
- **@sacco/ui:** `payroll_batch` status renders a known status + fallback.
- **@sacco/schemas:** `restructuringTypeSchema` accepts `payment_holiday`, rejects
  the stale `principal_holiday`; `loanRestructureSchema` accepts an integer-string
  `periods_added`; `payrollBatchSchema` requires ≥1 row; read types usable.
- **Portal:** Vitest + Testing Library —
  - `LoanWorkoutActions` (write-off branches toast on `direct`; restructure creates
    approval; recover shown only when written_off — render with `status` prop).
  - `RestructuringsTable` (row renders; empty state).
  - `CreatePayrollBatchForm` (add/remove rows; submit calls `createPayrollBatch`
    with rows + clearing account; redirect).
  - `RejectPayrollBatchButton` (confirm → `rejectPayrollBatch`).
- Per-package `test` + `typecheck` + `lint` green. No backend tests.
