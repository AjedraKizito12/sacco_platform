# SACCO Admin Portal — Ledger / Books (Phase 3g-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-22):** run **inline** (background subagents can't get Edit approval). **Confirm typecheck PASSES before committing.** No backend tests. Portal/package tests via `pnpm --filter` from `admin/`; **`git` from the repo root** (the shell cwd drifts into `admin/` after pnpm runs).
> **Test gotchas (carry-over):** `<Money>` exposes `data-amount`; `<DataTable>` `TData` must extend `{ id: string }`; checkboxes/selects in a Radix Dialog may need `fireEvent`; uuid-typed schema fields need real-UUID fixtures; required-asterisk + prefix labels collide in `getByLabelText` (use distinct labels or `data-amount`).

**Goal:** The Ledger/Books operator module — chart of accounts (list/create/detail), journal entries (list/detail), and manual GL posting (maker-checker) — filling the dead `/ledger/accounts` nav link.

**Architecture:** Add ledger read types to `@sacco/schemas`, then tenant-authed screens under `app/(tenant-authed)/ledger/*` server-fetched via `getTenantPageContext()`. In-memory `<DataTable>`s, RHF/Zod forms (the existing `accountSchema` + `manualJournalEntrySchema`), and a dynamic-row balanced GL form (`useFieldArray`, like payroll). Clones the prior tenant-operator pattern.

**Tech Stack:** Next.js 15, React 19, TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library. No Python changes.

## Global Constraints

- **Branch:** `feat/sacco-portal/07a-ledger`, off `main` (no PR stacking).
- **No backend changes, no api-client changes.** `resources.ledger.{listAccounts,createAccount,getAccount,listJournalEntries,getJournalEntry,submitJournalEntry}` exist (cast `{ data?, error? }`).
- **Account types:** asset/liability/equity/income/expense. **Manual GL** (`submitJournalEntry`) is **202 maker-checker** → `{approval_request_id, status}`; debits must equal credits; each line is debit **XOR** credit (enforced by `manualJournalEntrySchema`).
- **Money** → `<Money>`/`<MoneyInput>`; **counts** → `<Count>`; **dates** → `<FormattedDateTime>`. Manual-GL idempotency key = fresh UUID per form instance (contract L). No new StatusBadge entity.
- **No `<AuditBar>`**, tenant-auth gating only. **DRY/YAGNI/TDD, frequent commits.**

---

## Task 1: `@sacco/schemas/ledger.ts` — read types

**Files:**
- Modify: `admin/packages/schemas/src/ledger.ts`
- Test: `admin/packages/schemas/src/__tests__/ledger.test.ts` (create)

**Interfaces:**
- Produces: `AccountOut`, `AccountWithBalanceOut`, `JournalLineOut`, `JournalEntryOut`, `ManualGLSubmitOut`.

- [ ] **Step 1: Failing test** — create `src/__tests__/ledger.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { manualJournalEntrySchema, type AccountWithBalanceOut, type JournalEntryOut } from "../ledger";

const U = "550e8400-e29b-41d4-a716-446655440000";
const V = "550e8400-e29b-41d4-a716-446655440001";

describe("ledger schemas", () => {
  it("manualJournalEntrySchema rejects unbalanced + both-sided lines, accepts a balanced pair", () => {
    const base = { reference: "JV-1", description: "Test", idempotency_key: "abcd1234efgh" };
    // unbalanced
    expect(manualJournalEntrySchema.safeParse({ ...base, lines: [
      { account_id: U, debit_amount: "100", credit_amount: "0" },
      { account_id: V, debit_amount: "0", credit_amount: "50" },
    ] }).success).toBe(false);
    // both debit AND credit on one line
    expect(manualJournalEntrySchema.safeParse({ ...base, lines: [
      { account_id: U, debit_amount: "100", credit_amount: "100" },
      { account_id: V, debit_amount: "0", credit_amount: "100" },
    ] }).success).toBe(false);
    // balanced
    expect(manualJournalEntrySchema.safeParse({ ...base, lines: [
      { account_id: U, debit_amount: "100", credit_amount: "0" },
      { account_id: V, debit_amount: "0", credit_amount: "100" },
    ] }).success).toBe(true);
  });
  it("read types are structurally usable", () => {
    const a: AccountWithBalanceOut = {
      id: "a1", code: "1000", name: "Cash", account_type: "asset", parent_id: null,
      is_active: true, description: null, created_at: "t", updated_at: "t", balance: "100.0000",
    };
    const e: JournalEntryOut = {
      id: "e1", reference: "JV-1", description: "Test", posted_by: "u1", posted_at: "t",
      idempotency_key: "k", lines: [
        { id: "l1", account_id: "a1", debit_amount: "100.0000", credit_amount: "0.0000", description: null },
      ],
    };
    expect(a.balance).toBe("100.0000");
    expect(e.lines.length).toBe(1);
  });
});
```

Run: `cd admin && pnpm --filter @sacco/schemas test -- ledger` → FAIL (missing type exports; the schema cases pass already — they exercise the existing refinements).

- [ ] **Step 2: Add read types** to `ledger.ts` (after the `export type` lines):

```ts
export interface AccountOut {
  id: string;
  code: string;
  name: string;
  account_type: string;
  parent_id: string | null;
  is_active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccountWithBalanceOut extends AccountOut {
  balance: string;
}

export interface JournalLineOut {
  id: string;
  account_id: string;
  debit_amount: string;
  credit_amount: string;
  description: string | null;
}

export interface JournalEntryOut {
  id: string;
  reference: string;
  description: string;
  posted_by: string;
  posted_at: string;
  idempotency_key: string;
  lines: JournalLineOut[];
}

export interface ManualGLSubmitOut {
  approval_request_id: string;
  status: string;
}
```

> `ledger.ts` is already exported from `src/index.ts` (verify `export * from "./ledger";`).

- [ ] **Step 3: Run test + typecheck + lint; commit (from repo root).**

```bash
pnpm --filter @sacco/schemas test -- ledger && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
cd /home/liam/projects/sacco-platform && git add admin/packages/schemas/src/ledger.ts admin/packages/schemas/src/__tests__/ledger.test.ts
git commit -m "feat(portal): ledger read types

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Accounts list — `<AccountsTable>` + `/ledger/accounts`

> Clone the 3d-1 loan `ProductsTable` + page (in-memory DataTable, code links to detail).

**Files:**
- Create: `app/(tenant-authed)/ledger/accounts/_components/AccountsTable.tsx`, `ledger/accounts/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-ledger/AccountsTable.test.tsx`

**Interfaces:**
- Consumes: `AccountOut`, `resources.ledger.listAccounts`.

- [ ] **Step 1: `AccountsTable` test (failing)** — clone an in-memory table test (mock `useTableUrlState` + `next/navigation`; `<TenantCurrencyProvider>`). `TData = AccountOut` (Task-1 `a` shape minus balance, `id:"a1"`). Assert **Code** "1000" links to `/ledger/accounts/a1`; the name "Cash" renders; empty state "No accounts yet".

- [ ] **Step 2: Implement `AccountsTable.tsx`** — clone the loan `ProductsTable`. `id="ledger-accounts"`, `TData = AccountOut`. Columns: **Code** → `<Link href={\`/ledger/accounts/${row.original.id}\`} className="font-medium text-[var(--text-link)] hover:underline">{row.original.code}</Link>`; **Name** (`name`); **Type** (`account_type`); **Active** → `row.original.is_active ? "Yes" : "No"`. Empty `{ title: "No accounts yet", description: "Create an account to build the chart of accounts." }`.

- [ ] **Step 3: Implement `ledger/accounts/page.tsx`** (server) — `getTenantPageContext()`, `resources.ledger.listAccounts({})` cast `{ data?: AccountOut[] }`, `<h1>Chart of accounts</h1>`, header buttons: **Journal** `<Button asChild variant="secondary"><Link href="/ledger/journal-entries">` + **Create account** `<Button asChild><Link href="/ledger/accounts/new">`. `<AccountsTable rows={data ?? []} />`. `export const metadata = { title: "Ledger" }`.

- [ ] **Step 4: Run the test + portal typecheck + lint; commit (repo root).**

```bash
pnpm --filter @sacco/portal test -- tenant-ledger/AccountsTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
cd /home/liam/projects/sacco-platform && git add "admin/apps/portal/app/(tenant-authed)/ledger/accounts/page.tsx" "admin/apps/portal/app/(tenant-authed)/ledger/accounts/_components/AccountsTable.tsx" admin/apps/portal/src/__tests__/tenant-ledger/AccountsTable.test.tsx
git commit -m "feat(portal): SACCO chart of accounts list

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Create account — `<CreateAccountForm>` + `/ledger/accounts/new`

> Clone the 3d-1 loan `CreateProductForm` (Select + drop-empty-optional).

**Files:**
- Create: `app/(tenant-authed)/ledger/accounts/new/_components/CreateAccountForm.tsx`, `ledger/accounts/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-ledger/CreateAccountForm.test.tsx`

**Interfaces:**
- Consumes: `accountSchema`/`AccountInput`, `AccountOut`, `resources.ledger.createAccount`.
- Produces: exported `AccountOption = { id: string; code: string; name: string }`.

- [ ] **Step 1: Test (failing)** — clone the loan `CreateProductForm.test.tsx`. Mock push + `useAuth` (`resources.ledger.createAccount`). Pass `parents={[{id:"p1",code:"1000",name:"Assets"}]}`. Fill code "1010", name "Cash", pick account_type "Asset"; submit → `createAccount` called with `expect.objectContaining({ code:"1010", name:"Cash", account_type:"asset" })` (no `parent_id`/`description` keys when blank) + `push("/ledger/accounts")`. Also a blank code blocks submit.

- [ ] **Step 2: Implement `CreateAccountForm.tsx`** (client) — `useForm<AccountInput>({ resolver: zodResolver(accountSchema), defaultValues: { code:"", name:"", account_type:"asset", parent_id:"", description:"" } })`. Props `{ parents: AccountOption[] }`. Fields via `<FormField>`: code (`<Input>`), name (`<Input>`), account_type (`<Select>`: asset/liability/equity/income/expense), parent_id (`<Select>` with an "all"/"none" sentinel `<SelectItem value="none">None</SelectItem>` + `parents` → `{code} — {name}`), description (`<Textarea>`). `useTypedMutation<AccountOut, AccountInput>` → build `body={...vars}`; if `!body.description` delete it; if `!body.parent_id || body.parent_id==="none"` delete `parent_id` → `resources.ledger.createAccount(body)` cast `{data?,error?}`; onSuccess `toast.success("Account created")` + `router.push("/ledger/accounts")`; onError `apiErrorMessage`. Cancel → `/ledger/accounts`.
  > `accountSchema.parent_id` is `uuid.optional()` — the "none" sentinel must be stripped before submit (it isn't a uuid). Use bracket access (`body["parent_id"]`) for `Record<string,unknown>`.

- [ ] **Step 3: Implement `accounts/new/page.tsx`** (server) — `getTenantPageContext()`, fetch `resources.ledger.listAccounts({})` cast `{ data?: AccountOption[] }` (for the parent select), `<h1>Create account</h1>`, `<CreateAccountForm parents={data ?? []} />`.

- [ ] **Step 4: Run the test + typecheck + lint; commit (repo root).**

```bash
pnpm --filter @sacco/portal test -- tenant-ledger/CreateAccountForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
cd /home/liam/projects/sacco-platform && git add "admin/apps/portal/app/(tenant-authed)/ledger/accounts/new/" admin/apps/portal/src/__tests__/tenant-ledger/CreateAccountForm.test.tsx
git commit -m "feat(portal): SACCO ledger account create

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Account detail — `/ledger/accounts/[id]`

**Files:**
- Create: `app/(tenant-authed)/ledger/accounts/[id]/page.tsx`

**Interfaces:**
- Consumes: `AccountWithBalanceOut`, `resources.ledger.getAccount`.

- [ ] **Step 1: Implement `[id]/page.tsx`** (server) — `const { id } = await params;`; `resources.ledger.getAccount(id)` cast `{ data?: AccountWithBalanceOut }`; `notFound()` if absent. Header `<h1>{account.code} — {account.name}</h1>`. Read-only `<Card>`: a prominent balance row (`<Money amount={account.balance} />`), then `Row`s: Type (`account_type`), Active (Yes/No), Description (`?? "—"`), Parent (`parent_id ?? "—"`), Created (`<FormattedDateTime value={account.created_at} />`). No AuditBar. `export const metadata = { title: "Account" }`. (Reuse the `Row` helper pattern from the loan-product detail page.)

- [ ] **Step 2: typecheck + lint (no unit test — server page); commit (repo root).**

```bash
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
cd /home/liam/projects/sacco-platform && git add "admin/apps/portal/app/(tenant-authed)/ledger/accounts/[id]/page.tsx"
git commit -m "feat(portal): SACCO ledger account detail

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Journal entries list — `<JournalEntriesTable>` + `/ledger/journal-entries`

**Files:**
- Create: `app/(tenant-authed)/ledger/journal-entries/_components/JournalEntriesTable.tsx`, `ledger/journal-entries/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-ledger/JournalEntriesTable.test.tsx`

**Interfaces:**
- Consumes: `JournalEntryOut`, `resources.ledger.listJournalEntries`.

- [ ] **Step 1: `JournalEntriesTable` test (failing)** — `TData = JournalEntryOut` (Task-1 `e` shape). Assert **Reference** "JV-1" links to `/ledger/journal-entries/e1`; the line count "1" renders (Count via `data-value="1"`); empty state "No journal entries yet".

- [ ] **Step 2: Implement `JournalEntriesTable.tsx`** (client) — in-memory `<DataTable id="ledger-journal">`, `TData = JournalEntryOut`. Columns: **Reference** → `<Link href={\`/ledger/journal-entries/${row.original.id}\`} …>{row.original.reference}</Link>`; **Description** (`description`); **Posted** → `<FormattedDateTime value={row.original.posted_at} />`; **Lines** → `<Count value={row.original.lines.length} />`. Empty `{ title: "No journal entries yet", description: "Post a manual GL entry to get started." }`. Import `Count`, `FormattedDateTime`.

- [ ] **Step 3: Implement `journal-entries/page.tsx`** (server) — `resources.ledger.listJournalEntries({})` cast `{ data?: JournalEntryOut[] }`, `<h1>Journal</h1>`, header: **Accounts** link `/ledger/accounts` + **Post GL entry** → `/ledger/journal-entries/new`. `<JournalEntriesTable rows={data ?? []} />`. `export const metadata = { title: "Journal" }`.

- [ ] **Step 4: Run the test + typecheck + lint; commit (repo root).**

```bash
pnpm --filter @sacco/portal test -- tenant-ledger/JournalEntriesTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
cd /home/liam/projects/sacco-platform && git add "admin/apps/portal/app/(tenant-authed)/ledger/journal-entries/page.tsx" "admin/apps/portal/app/(tenant-authed)/ledger/journal-entries/_components/JournalEntriesTable.tsx" admin/apps/portal/src/__tests__/tenant-ledger/JournalEntriesTable.test.tsx
git commit -m "feat(portal): SACCO ledger journal list

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Manual GL posting — `<ManualGLForm>` + `/ledger/journal-entries/new`

> Clone the 3d-4 payroll `CreatePayrollBatchForm` (`useFieldArray` dynamic rows).

**Files:**
- Create: `app/(tenant-authed)/ledger/journal-entries/new/_components/ManualGLForm.tsx`, `ledger/journal-entries/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-ledger/ManualGLForm.test.tsx`

**Interfaces:**
- Consumes: `manualJournalEntrySchema`/`ManualJournalEntryInput`, `ManualGLSubmitOut`, `resources.ledger.submitJournalEntry`.
- Produces: exported `AccountOption = { id: string; code: string; name: string }`.

- [ ] **Step 1: Test (failing)** — mock push + `useAuth` (`resources.ledger.submitJournalEntry`). Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`. Props `accounts=[{id:A,code:"1010",name:"Cash"},{id:B,code:"4000",name:"Income"}]` (A,B real uuids). Two cases:
  - fill reference + description; line 0 = account A, debit 100; line 1 = account B, credit 100 → submit → `submitJournalEntry(expect.objectContaining({ reference:"JV-1", lines:[ {account_id:A,debit_amount:"100",credit_amount:"0",...}, {account_id:B,debit_amount:"0",credit_amount:"100",...} ] }))`; on `{data:{approval_request_id:"r1",status:"pending"}}` → toast /pending approval/ + `push("/ledger/journal-entries")`.
  - unbalanced (line1 credit 50) → submit → `submitJournalEntry` NOT called (schema refine blocks).
  > Select interactions: open each line's account `<Select>` by label and pick the option; type debit/credit into the `<MoneyInput>`s. Per-line labels must be unique → suffix with the row index (see Step 2). Defaults keep the unfilled side at "0".

- [ ] **Step 2: Implement `ManualGLForm.tsx`** (client) — `useForm<ManualJournalEntryInput>({ resolver: zodResolver(manualJournalEntrySchema), defaultValues: { reference:"", description:"", idempotency_key:<fresh uuid>, lines:[ {account_id:"",debit_amount:"0",credit_amount:"0",description:""}, {account_id:"",debit_amount:"0",credit_amount:"0",description:""} ] } })` + `useFieldArray("lines")`. Props `{ accounts: AccountOption[] }`. Top fields: reference (`<Input>`), description (`<Input>`). Per row `i`: account `<FormField name={\`lines.${i}.account_id\`} label={\`Account ${i + 1}\`}>` (`<Select>` from accounts → `{code} — {name}`); debit `<FormField name={\`lines.${i}.debit_amount\`} label={\`Debit ${i + 1}\`}>` (`<MoneyInput>`); credit `<FormField name={\`lines.${i}.credit_amount\`} label={\`Credit ${i + 1}\`}>` (`<MoneyInput>`); Remove (disabled when `fields.length === 2`). **Add line** appends `{account_id:"",debit_amount:"0",credit_amount:"0",description:""}`. Surface `formState.errors.lines?.root?.message` / `.message` (the balance + XOR refines attach to `lines`) as a small error line. `useTypedMutation<ManualGLSubmitOut, ManualJournalEntryInput>` → `resources.ledger.submitJournalEntry(values)` cast `{data?,error?}`; onSuccess `toast.success("GL entry submitted — pending approval")` + `router.push("/ledger/journal-entries")`; onError `apiErrorMessage`. Cancel → `/ledger/journal-entries`. A note under the heading: "Posting a manual GL entry creates a maker-checker approval (quorum applies); it posts once approved."

- [ ] **Step 3: Implement `journal-entries/new/page.tsx`** (server) — `resources.ledger.listAccounts({})` cast `{ data?: AccountOption[] }`, `<h1>Post manual GL entry</h1>`, `<ManualGLForm accounts={data ?? []} />`.

- [ ] **Step 4: Run the test + typecheck + lint; commit (repo root).**

```bash
pnpm --filter @sacco/portal test -- tenant-ledger/ManualGLForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
cd /home/liam/projects/sacco-platform && git add "admin/apps/portal/app/(tenant-authed)/ledger/journal-entries/new/" admin/apps/portal/src/__tests__/tenant-ledger/ManualGLForm.test.tsx
git commit -m "feat(portal): SACCO manual GL posting (maker-checker)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Journal entry detail — `[id]/page.tsx` + `<LinesTable>`

**Files:**
- Create: `app/(tenant-authed)/ledger/journal-entries/[id]/page.tsx`, `_components/LinesTable.tsx`
- Test: `apps/portal/src/__tests__/tenant-ledger/LinesTable.test.tsx`

**Interfaces:**
- Consumes: `JournalEntryOut`, `JournalLineOut`, `resources.ledger.getJournalEntry`.

- [ ] **Step 1: `LinesTable` test (failing)** — `TData = JournalLineOut`. One line (Task-1 shape). Assert the debit amount renders (`data-amount="100.0000"`) + empty state "No lines".

- [ ] **Step 2: Implement `LinesTable.tsx`** (client) — in-memory `<DataTable id="ledger-entry-lines">`, `TData = JournalLineOut` (has `id`). Columns: **Account** (`account_id`); **Debit** → `<Money amount={row.original.debit_amount} />`; **Credit** → `<Money amount={row.original.credit_amount} />`; **Description** (`?? "—"`). Empty `{ title: "No lines", description: "This entry has no lines." }`.

- [ ] **Step 3: Implement `journal-entries/[id]/page.tsx`** (server) — `const { id } = await params;`; `resources.ledger.getJournalEntry(id)` cast `{ data?: JournalEntryOut }`; `notFound()` if absent. Header `<h1>{entry.reference}</h1>`. Read-only `<Card>`: description, posted (`<FormattedDateTime value={entry.posted_at} />`). `<h2>Lines</h2>` + `<LinesTable rows={entry.lines} />`. No AuditBar. `export const metadata = { title: "Journal entry" }`.

- [ ] **Step 4: Run the test + typecheck + lint; commit (repo root).**

```bash
pnpm --filter @sacco/portal test -- tenant-ledger/LinesTable
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
cd /home/liam/projects/sacco-platform && git add "admin/apps/portal/app/(tenant-authed)/ledger/journal-entries/[id]/" admin/apps/portal/src/__tests__/tenant-ledger/LinesTable.test.tsx
git commit -m "feat(portal): SACCO journal entry detail

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Verification + PR

- [ ] **Step 1: Package + portal gate** (from `admin/`):
```bash
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test delta over the 281 (post-#49) baseline.

- [ ] **Step 2: Contract spot-checks** (from repo root):
  - [ ] No backend changes: `git diff --name-only main...HEAD | grep -E '^app/'` empty; `grep -E '^alembic/'` empty.
  - [ ] No api-client changes: `git diff --name-only main...HEAD | grep 'api-client'` empty.
  - [ ] Changes under `admin/` + `docs/` only.

- [ ] **Step 3: Browser smoke** (the live stack is up — backend :8001, portal :3000; tenant `e2e-sacco`, `ops@saccodemo.com`). Drive `/ledger/accounts`, `/ledger/accounts/new`, `/ledger/journal-entries`, `/ledger/journal-entries/new`, an account detail, and an entry detail; confirm 200 + no console errors (reuse the `/tmp/sweep.mjs` Playwright harness with these routes — the `/ledger` link is no longer dead).

- [ ] **Step 4: Push + PR** (base `main`):
```bash
cd /home/liam/projects/sacco-platform
git push -u origin feat/sacco-portal/07a-ledger
gh pr create --base main --title "feat(portal): SACCO admin — Ledger / Books (Phase 3g-1)" --body "$(cat <<'EOF'
## Summary
- First of three **dead-link fills** (Phase 3g) found during manual testing: builds `/ledger/accounts` (was a 404 in the tenant sidebar).
- **Ledger / Books** operator module: chart of accounts (list / create / detail with balance), journal entries (list / detail), and **manual GL posting** — a dynamic balanced debit/credit form (`useFieldArray`) that submits a **202 maker-checker** request (approved later in the tenant approvals inbox, 3g-2).
- New `@sacco/schemas/ledger.ts` read types. Pure client — **no backend or api-client changes** (the ledger resource + input schemas already existed).

## Test plan
- `@sacco/schemas`, `@sacco/api-client`, `@sacco/portal` test/typecheck/lint green; browser smoke of all `/ledger/*` routes (200, no console errors).

> Phase 3g (dead-link fills): Ledger (this) → Approvals inbox (3g-2) → Audit (3g-3).
> CI note: Lint fails environmentally on this repo (runner-queue issue); reproduced clean locally.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** read types → T1; accounts list → T2; account create → T3; account detail → T4; journal list → T5; manual GL post → T6; entry detail → T7; verify/PR → T8.
- **Type consistency:** `AccountOut`/`AccountWithBalanceOut`/`JournalEntryOut`/`JournalLineOut`/`ManualGLSubmitOut` (T1) consumed by T2–T7; `AccountOption` (T3/T6) is a page-built lite shape; manual-GL lines keep the unfilled side at `"0"` so `moneyString` passes and the XOR refine forces exactly one side > 0.
- **Verify-at-execution:** `manualJournalEntrySchema` refine errors attach to `lines` (`formState.errors.lines`); Radix `<Select>` "none" sentinel for optional parent (can't use `""`); `useFieldArray` row field-name template strings with `<FormField>`; per-line labels suffixed with the row index to keep `getByLabelText` unambiguous; Next 15 `params` Promise; `<Money>` `data-amount` for test assertions.
- **No backend tests** — no backend change.
