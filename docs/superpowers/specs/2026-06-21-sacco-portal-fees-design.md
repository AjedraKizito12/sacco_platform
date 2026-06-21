# SACCO Admin Portal — Fees (Phase 3e) Design

**Date:** 2026-06-21
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan e — Fees
**Status:** Approved

## Context

3e is the fifth SACCO-operator module (after Members, Savings, Shares, Credit).
It manages **fee types**, **assessments** (a fee applied to a target), and
**collections** (recording payment against an assessment — partial collection is
first-class). The fees api-client resource is complete and `@sacco/schemas/fees.ts`
already has the input schemas + enums; what's missing on the portal side: a couple
of **stale-schema fixes**, the **read types**, and the screens. The `fee_assessment`
StatusBadge entity already exists. All flows are **direct (201)** — fees has no
maker-checker in the portal (per CLAUDE.md, maker-checker is on the originating
operation, but the create-assessment/collection endpoints are direct).

Reuses the tenant-operator pattern (server-fetch via `getTenantPageContext()`,
in-memory `<DataTable>`, RHF/Zod forms, GL-code `<Select>`s, `<StatusBadge>`).

## Schema fixes (stale vs the live backend)

`@sacco/schemas/fees.ts` needs three corrections (verified against
`app/modules/fees/models.py` CheckConstraints + `schemas.py`):
- `feeTriggerKindSchema`: `["event","scheduled","manual"]` → **`["event","schedule","manual"]`**
  (`scheduled` is wrong).
- `feeCollectionSchema.contra_account_id`: currently `uuid.optional()` required only
  for `journal_voucher`. The backend requires it for **both `cash` and
  `journal_voucher`** → make it **required `uuid`** (drop the optional + refine).
- `feeAssessmentSchema.period_end`: currently required `isoDate` → **optional**
  (backend `period_end` is `date | None`); and add `share_account` to its
  `target_type` enum (backend `applicable_to` includes it).

## Backend facts (authoritative — already in place, no changes)

Gate on every fees route is `CurrentTenantUser`. The api-client `fees` resource is
complete (`listTypes, getType, createType, patchType, listAssessments,
getAssessment, createAssessment, recordCollection`); cast `{ data?, error? }`.

### Fee types
- `GET /fees/types` (`?include_inactive`?) → `list[FeeTypeOut]`.
- `POST /fees/types` (201) → `FeeTypeOut`. `FeeTypeCreateIn`: `code, name,
  description?, applicable_to, amount_kind (default "fixed"), amount (Decimal),
  currency, trigger_kind, event_name?, schedule_config?, gl_income_account_code,
  gl_receivable_account_code, requires_collection (default false)`.
  - **Enums (backend CheckConstraints):** `amount_kind` ∈ {fixed, percentage,
    tiered}; `trigger_kind` ∈ {event, schedule, manual}; `applicable_to` ∈
    {member, savings_account, loan, share_account}.
- `GET /fees/types/{id}` → `FeeTypeOut`. Missing → 404.
- `PATCH /fees/types/{id}` → `FeeTypeOut`. `FeeTypePatchIn` accepts **only**
  `name?, description?, amount?, is_active?, requires_collection?`.

`FeeTypeOut` fields: `id, code, name, description?, applicable_to, amount_kind,
amount, percentage_basis?, percentage_rate?, currency, trigger_kind, event_name?,
schedule_config?, gl_income_account_code, gl_receivable_account_code, is_active,
requires_collection`.

### Assessments
- `GET /fees/assessments` (`?target_type`, `?target_id`, `?status`?) →
  `list[FeeAssessmentOut]`.
- `POST /fees/assessments` (201) → `FeeAssessmentOut`. `FeeAssessmentCreateIn`:
  `fee_type_id, target_type, target_id, period_start (date), period_end? (date)`.
- `GET /fees/assessments/{id}` → `FeeAssessmentDetailOut` (= `FeeAssessmentOut` +
  `collections: FeeCollectionOut[]`).

`FeeAssessmentOut` fields: `id, fee_type_id, target_type, target_id, period_start,
period_end?, amount, currency, status, assessed_at, due_at?, paid_at?, waived_by?,
waiver_reason?, journal_entry_id`. **Statuses** (existing StatusBadge entity
`fee_assessment`): assessed, partially_paid, paid, waived, cancelled.

### Collections
- `POST /fees/collections` (201) → `FeeCollectionOut`. `FeeCollectionCreateIn`:
  `fee_assessment_id, amount (Decimal), method (cash | journal_voucher),
  contra_account_id (uuid, required), idempotency_key`. (`savings_deduction` is
  auto-only — not offered in the portal.)

`FeeCollectionOut` fields: `id, fee_assessment_id, amount, collected_at, method,
collected_by, journal_entry_id, idempotency_key`.

- `GET /ledger/accounts`, `GET /members`, `GET /credit/loans`,
  `GET /savings/accounts`, `GET /shares/accounts` — for GL-code selects + the
  assessment target selector.

## New supporting pieces (`@sacco/schemas/fees.ts`)
- The three schema fixes above.
- Read types: `FeeTypeOut`, `FeeAssessmentOut`, `FeeCollectionOut`,
  `FeeAssessmentDetailOut` (mirror backend; Decimals as strings).

## Screens (under `app/(tenant-authed)/fees/*`)

All server-fetched via `getTenantPageContext()`; cast `{ data?, error? }`. Tenant-auth.
The sidebar **Fees** link already points to `/fees/types`.

### `/fees/types` — fee types list
- Server: `fees.listTypes({})` → `FeeTypeOut[]`.
- `<FeeTypesTable>`: in-memory `<DataTable>` (`id="fee-types"`, `TData = FeeTypeOut`).
  Columns: **Code**, **Name** (links to `/fees/types/{id}`), **Applies to**
  (`applicable_to`), **Amount** (`<Money>`), **Trigger** (`trigger_kind`),
  **Active** (Yes/No). Empty: "No fee types yet."
- Header: **Create fee type** → `/fees/types/new`; **Assessments** link →
  `/fees/assessments`.

### `/fees/types/new` — create fee type
- RHF + `zodResolver(feeTypeSchema)`. Fields: code (`<Input>`), name (`<Input>`),
  description (`<Textarea>`), applicable_to (`<Select>`: member/savings_account/
  loan/share_account), amount_kind (`<Select>`: fixed/percentage/tiered), amount
  (`<MoneyInput>`), currency (`<Input>` default UGX), trigger_kind (`<Select>`:
  event/schedule/manual), event_name (`<Input>`, optional), gl_income_account_code
  + gl_receivable_account_code (`<Select>` from `ledger.listAccounts()`, value =
  code), requires_collection (`<Checkbox>`). On submit → `fees.createType(values)`
  (drop empty optionals) → toast → `/fees/types`. (`schedule_config` omitted in v1.)

### `/fees/types/[id]` — fee type detail + edit
- Server: `fees.getType(id)` → `FeeTypeOut` (`notFound()` if absent).
- Read-only `<Card>`s: identity (code, name, description, applies-to), pricing
  (amount_kind, `<Money>` amount, currency, percentage rate/basis when set),
  trigger (trigger_kind, event_name), GL mapping (income + receivable codes),
  flags (active, requires_collection).
- `<EditFeeTypeForm>` (client) limited to the PATCH fields: name (`<Input>`),
  description (`<Textarea>`), amount (`<MoneyInput>`), is_active (`<Checkbox>`),
  requires_collection (`<Checkbox>`) → `fees.patchType(id, body)` → toast +
  `router.refresh()`.

### `/fees/assessments` — assessments list
- Server: `fees.listAssessments({})` + `feeTypes` (`fees.listTypes({})`) for the
  type-name column; build a `fee_type_id → name` map.
- `<AssessmentsTable>`: in-memory `<DataTable>` (`id="fee-assessments"`,
  `TData = AssessmentRow`). `AssessmentRow = { id, fee_type_name, target_type,
  amount, period_start, status }`. Columns: **Fee type** (links to
  `/fees/assessments/{id}`), **Target** (`target_type`), **Amount** (`<Money>`),
  **Period** (`<FormattedDate value={period_start} />`), **Status**
  (`<StatusBadge entity="fee_assessment" status />`). Empty: "No assessments yet."
- Header: **New assessment** → `/fees/assessments/new`; **Fee types** link →
  `/fees/types`.

### `/fees/assessments/new` — create assessment (dynamic target)
- Server: fetch `fees.listTypes({})`, `members.list({})`, `credit.listLoans({})`,
  `savings.listAccounts({})`, `shares.listAccounts({})`; build a member map and
  four labelled option arrays:
  `targets = { member: [{id,label:"name (number)"}], loan: [{id,label:"reference · member"}],
  savings_account: [{id,label:"product · member"}], share_account: [{id,label:"product · member"}] }`.
- `<CreateAssessmentForm>` (client) — RHF + `zodResolver(feeAssessmentSchema)`.
  Fields: fee_type_id (`<Select>` from fee types → `{code} — {name}`); target_type
  (`<Select>`: member/loan/savings_account/share_account); **target_id** (`<Select>`
  whose options are `targets[watch("target_type")]` — RHF `watch`; reset target_id
  when target_type changes); period_start (`<DateInput>`); period_end
  (`<DateInput>`, optional). On submit → `fees.createAssessment(values)` (drop empty
  period_end) → toast → `router.push("/fees/assessments/${data.id}")`. 400 →
  `apiErrorMessage` (covers "applicable_to mismatch").

### `/fees/assessments/[id]` — assessment detail + collections
- Server: `fees.getAssessment(id)` → `FeeAssessmentDetailOut` (`notFound()`),
  `fees.getType(assessment.fee_type_id)` (type name) and `ledger.listAccounts({})`
  (contra select).
- Header: `<h1>{feeType?.name ?? "Assessment"}</h1>` + `<StatusBadge
  entity="fee_assessment" status={assessment.status} />` +
  `<RecordCollectionButton assessmentId amount status glAccounts />`.
- Read-only `<Card>`: target (type + id), amount (`<Money>`), period
  (`<FormattedDate>`), assessed/due/paid (`<FormattedDateTime>`/`<FormattedDate>`),
  waiver reason (when set).
- **Collections** `<CollectionsTable>` (in-memory `<DataTable>`,
  `TData = FeeCollectionOut`): amount (`<Money>`), method, collected
  (`<FormattedDateTime value={collected_at} />`). Empty: "No collections yet."
- `<RecordCollectionButton>` (client) — shown unless `status` ∈ {paid, waived,
  cancelled}: a `<Dialog>` form (`feeCollectionSchema`): amount (`<MoneyInput>`),
  method (`<Select>`: cash / journal_voucher), contra_account_id (`<Select>` from
  ledger, value = id), fresh `idempotency_key`. Submit → `fees.recordCollection({
  fee_assessment_id: assessmentId, ...values })` (201) → toast "Collection recorded"
  + `router.refresh()`. **Direct** (partial collection supported — 400 surfaces via
  `apiErrorMessage`).

## File structure
**`@sacco/schemas`:** modify `src/fees.ts`; extend `src/__tests__/fees.test.ts`
(create if absent).
**`@sacco/portal`:**
- `app/(tenant-authed)/fees/types/page.tsx` + `_components/FeeTypesTable.tsx`.
- `app/(tenant-authed)/fees/types/new/page.tsx` + `_components/CreateFeeTypeForm.tsx`.
- `app/(tenant-authed)/fees/types/[id]/page.tsx` + `_components/EditFeeTypeForm.tsx`.
- `app/(tenant-authed)/fees/assessments/page.tsx` + `_components/AssessmentsTable.tsx`.
- `app/(tenant-authed)/fees/assessments/new/page.tsx` + `_components/CreateAssessmentForm.tsx`.
- `app/(tenant-authed)/fees/assessments/[id]/page.tsx` +
  `_components/{CollectionsTable,RecordCollectionButton}.tsx`.
- Tests under `apps/portal/src/__tests__/tenant-fees/`.
- **No api-client changes, no backend changes.**

## Out of scope (deferred)
- `schedule_config` / `percentage_basis` / `percentage_rate` authoring (v1 fixed
  amount; backend create takes only `amount`).
- Fee waiver UI (maker-checker per CLAUDE.md — no portal endpoint surfaced; defer).
- `savings_deduction` collection method (auto-only).
- `<AuditBar>`; server-side pagination (in-memory like prior modules).
- Member-detail fees section (defer; assessments are filterable by target).

## Testing strategy
- **@sacco/schemas:** `feeTriggerKindSchema` accepts `schedule`, rejects
  `scheduled`; `feeCollectionSchema` requires `contra_account_id` for `cash`;
  `feeAssessmentSchema` accepts a missing `period_end`; read types usable.
- **Portal:** Vitest + Testing Library —
  - `FeeTypesTable` (row + link + empty).
  - `CreateFeeTypeForm` (blank code/name blocks; valid submit posts the enums + GL
    codes; redirect).
  - `EditFeeTypeForm` (patches the editable fields; refresh).
  - `AssessmentsTable` (type-name join + status badge; empty).
  - `CreateAssessmentForm` (target_id options switch with target_type; submit posts
    fee_type_id/target_type/target_id/period_start; redirect).
  - `RecordCollectionButton` (cash requires contra; submit posts collection;
    hidden when paid).
- Per-package `test` + `typecheck` + `lint` green. No backend tests.
