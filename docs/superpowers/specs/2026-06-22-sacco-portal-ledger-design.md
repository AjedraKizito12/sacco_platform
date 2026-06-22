# SACCO Admin Portal — Ledger / Books (Phase 3g-1) Design

**Date:** 2026-06-22
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan g (dead-link fills), part 1 — Ledger
**Status:** Approved

## Context

Manual testing of the operator portal surfaced **three dead sidebar links** — the
tenant nav was scaffolded in Phase 2 with links to `/ledger/accounts`,
`/approvals`, and `/audit`, but those pages were never built (they 404). Phase 3g
fills them, one sub-PR each:
- **3g-1 Ledger** (this doc) — `/ledger/accounts` + the Books surface.
- **3g-2 Tenant approvals inbox** — `/approvals` (the maker-checker *checker* side).
- **3g-3 Tenant audit** — `/audit` (needs a new tenant-scoped audit endpoint).

3g-1 is a **near-pure client**: the `ledger` api-client resource is complete and
`@sacco/schemas/ledger.ts` already has the input schemas (incl. the balanced /
debit-XOR-credit refinements on `manualJournalEntrySchema`). Missing: read types
and the screens. Reuses the tenant-operator pattern (server-fetch via
`getTenantPageContext()`, in-memory `<DataTable>`, RHF/Zod forms, dynamic-row form
like payroll).

## Backend facts (authoritative — already in place, no changes)

Gate on every ledger route is `CurrentTenantUser`. api-client
`resources.ledger.{listAccounts, createAccount, getAccount, listJournalEntries,
getJournalEntry, submitJournalEntry}` all exist (cast `{ data?, error? }`).

- `GET /ledger/accounts` → `list[AccountOut]`.
- `POST /ledger/accounts` (201) → `AccountOut`. `AccountCreateIn` ≅ `accountSchema`:
  `code (^[A-Z0-9.\-_]+$), name, account_type (asset|liability|equity|income|
  expense), parent_id? (uuid), description?`.
- `GET /ledger/accounts/{id}` → `AccountWithBalanceOut` (= `AccountOut` + `balance`).
- `GET /ledger/journal-entries` → `list[JournalEntryOut]`.
- `GET /ledger/journal-entries/{id}` → `JournalEntryOut`.
- `POST /ledger/journal-entries/submit` (**202**) → `ManualGLSubmitOut`
  (`approval_request_id, status`) — **manual GL is maker-checker** (CLAUDE.md rule 7).
  `ManualGLSubmitIn` ≅ `manualJournalEntrySchema`: `reference, description,
  idempotency_key, lines (≥2)`; line = `account_id, debit_amount, credit_amount,
  description?`. Debits must equal credits; each line is debit XOR credit.

`AccountOut`: `id, code, name, account_type, parent_id?, is_active, description?,
created_at, updated_at`. `AccountWithBalanceOut`: `+ balance`.
`JournalEntryOut`: `id, reference, description, posted_by, posted_at,
idempotency_key, lines: JournalLineOut[]`. `JournalLineOut`: `id, account_id,
debit_amount, credit_amount, description?`.

## New supporting pieces (`@sacco/schemas/ledger.ts`)
Add read types (Decimals as JSON strings): `AccountOut`, `AccountWithBalanceOut`,
`JournalLineOut`, `JournalEntryOut`, `ManualGLSubmitOut`. (Input schemas +
`accountTypeSchema` already exist.) No new StatusBadge entity — account `is_active`
is a bool; journal entries have no status.

## Screens (under `app/(tenant-authed)/ledger/*`)

All server-fetched via `getTenantPageContext()`; cast `{ data?, error? }`. Tenant-auth.
The sidebar **Ledger** link already points to `/ledger/accounts` (currently dead).

### `/ledger/accounts` — chart of accounts
- Server: `ledger.listAccounts({})` → `AccountOut[]`.
- `<AccountsTable>`: in-memory `<DataTable id="ledger-accounts">`. Columns: **Code**
  (links to `/ledger/accounts/{id}`), **Name**, **Type** (`account_type`), **Active**
  (Yes/No). Empty: "No accounts yet."
- Header: **Create account** → `/ledger/accounts/new`; **Journal** link →
  `/ledger/journal-entries`.

### `/ledger/accounts/new` — create account
- RHF + `zodResolver(accountSchema)`. Fields: code (`<Input>`), name (`<Input>`),
  account_type (`<Select>`: asset/liability/equity/income/expense), parent_id
  (`<Select>` from `ledger.listAccounts()` server-fetched, optional — "None" sentinel
  → omit), description (`<Textarea>`). Submit → `ledger.createAccount(values)` (drop
  empty description/parent_id) → toast "Account created" → `/ledger/accounts`.

### `/ledger/accounts/[id]` — account detail
- Server: `ledger.getAccount(id)` → `AccountWithBalanceOut` (`notFound()` if absent).
- Read-only `<Card>`: code, name, type, **balance** (`<Money>`, emphasised), active,
  description, created (`<FormattedDateTime>`). No AuditBar.

### `/ledger/journal-entries` — journal
- Server: `ledger.listJournalEntries({})` → `JournalEntryOut[]`.
- `<JournalEntriesTable>`: in-memory `<DataTable id="ledger-journal">`. Columns:
  **Reference** (links to `/ledger/journal-entries/{id}`), **Description**, **Posted**
  (`<FormattedDateTime value={posted_at} />`), **Lines** (`<Count value={lines.length} />`).
  Empty: "No journal entries yet."
- Header: **Post GL entry** → `/ledger/journal-entries/new`; **Accounts** link.

### `/ledger/journal-entries/new` — post manual GL entry (maker-checker)
- Server: fetch `ledger.listAccounts({})` for the per-line account select.
- `<ManualGLForm>` (client) — RHF + `zodResolver(manualJournalEntrySchema)` +
  `useFieldArray("lines")` (mirrors the payroll dynamic-rows form). `defaultValues:
  { reference:"", description:"", idempotency_key:<fresh uuid>, lines:[ {account_id:"",
  debit_amount:"0", credit_amount:"0", description:""} ×2 ] }` (start with 2 lines).
  Per line: account `<Select>` (from accounts → `{code} — {name}`), debit
  `<MoneyInput>`, credit `<MoneyInput>`, optional description `<Input>`, Remove (disabled
  when 2 lines). **Add line** appends `{account_id:"",debit_amount:"0",credit_amount:"0"}`.
  A live "Debits / Credits" total line aids balancing (the schema enforces balance +
  debit-XOR-credit; errors render on `lines`). Submit → `ledger.submitJournalEntry(values)`
  (**202** → `ManualGLSubmitOut`) → toast "GL entry submitted — pending approval" →
  `router.push("/ledger/journal-entries")`. The dialog/page copy notes it creates a
  maker-checker approval (approved later in the 3g-2 inbox).

### `/ledger/journal-entries/[id]` — entry detail
- Server: `ledger.getJournalEntry(id)` → `JournalEntryOut` (`notFound()`).
- Read-only `<Card>`: reference, description, posted (`<FormattedDateTime>`). A
  `<LinesTable>` (in-memory `<DataTable id="ledger-entry-lines">`, `TData = JournalLineOut`):
  Account (account_id — raw; name resolution is a nice-to-have, omit in v1), Debit
  (`<Money>`), Credit (`<Money>`), Description (`?? "—"`). No AuditBar.

## File structure
**`@sacco/schemas`:** modify `src/ledger.ts`; extend `src/__tests__/ledger.test.ts` (create if absent).
**`@sacco/portal`:**
- `app/(tenant-authed)/ledger/accounts/page.tsx` + `_components/AccountsTable.tsx`.
- `app/(tenant-authed)/ledger/accounts/new/page.tsx` + `_components/CreateAccountForm.tsx`.
- `app/(tenant-authed)/ledger/accounts/[id]/page.tsx`.
- `app/(tenant-authed)/ledger/journal-entries/page.tsx` + `_components/JournalEntriesTable.tsx`.
- `app/(tenant-authed)/ledger/journal-entries/new/page.tsx` + `_components/ManualGLForm.tsx`.
- `app/(tenant-authed)/ledger/journal-entries/[id]/page.tsx` + `_components/LinesTable.tsx`.
- Tests under `apps/portal/src/__tests__/tenant-ledger/`.
- **No api-client changes, no backend changes.**

## Out of scope (deferred)
- Approving the manual-GL request (→ 3g-2 approvals inbox).
- Account edit/deactivate (no obvious endpoint); journal-line account-name resolution
  (show account_id in v1); COA tree view (flat table in v1).
- `<AuditBar>`; server-side pagination (in-memory like prior modules).

## Testing strategy
- **@sacco/schemas:** read types structurally usable; `manualJournalEntrySchema`
  rejects unbalanced lines + a both-debit-and-credit line, accepts a balanced pair
  (characterization of the existing refinements).
- **@sacco/portal:** Vitest + Testing Library —
  - `AccountsTable` (row links + empty); `JournalEntriesTable` (row links + line count + empty).
  - `CreateAccountForm` (blank code blocks; valid submit calls `createAccount` + redirect).
  - `ManualGLForm` (add/remove lines; unbalanced submit blocked; a balanced 2-line
    entry calls `submitJournalEntry` and toasts "pending approval" + redirect).
  - `LinesTable` (renders a line; empty state).
- Per-package `test` + `typecheck` + `lint` green. No backend tests.
