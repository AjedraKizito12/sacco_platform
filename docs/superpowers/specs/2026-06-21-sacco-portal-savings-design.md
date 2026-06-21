# SACCO Admin Portal — Savings Module (Phase 3b) Design

**Date:** 2026-06-21
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan b — Savings
**Status:** Approved

## Context

Phase 3b is the second SACCO-operator module, following Members (3a). It is
mostly a **client** of the complete `savings` backend, with **one small backend
addition**: a savings-account list endpoint. The savings backend exposes products
(list/create/get), open-account, account-detail-by-id (with balance),
transactions, deposit, and withdraw — but has **no way to list accounts**, so an
operator cannot browse them. Per CLAUDE.md contract B ("if a sub-plan thinks it
needs a new endpoint, stop and surface"), this was surfaced and the decision was
to **add the list endpoint** rather than ship a browse-less module.

This module reuses the tenant-operator pattern established in 3a
(`getTenantPageContext()` server-fetch, in-memory `<DataTable>`, RHF/Zod forms,
maker-checker action via `<MakerCheckerConfirmDialog>`).

## Backend addition (the only backend change)

**`GET /savings/accounts` — optional `?member_id=<uuid>` filter →
`list[SavingsAccountOut]`**, gate `CurrentTenantUser`.

- New `SavingsService.list_accounts(*, member_id: uuid.UUID | None = None) ->
  list[SavingsAccount]` — mirrors the existing `list_products`: a single
  `select(SavingsAccount)` ordered by `product_name, id`, with an optional
  `.where(SavingsAccount.member_id == member_id)`.
- Route returns the **cheap** shape (`SavingsAccountOut`, no balance), matching
  the existing cheap-list / rich-detail-by-id split (`get_account` is the only
  endpoint that derives balance). Balance stays on the detail page.
- Declared after the `POST /accounts` route and before
  `GET /accounts/{account_id}` (distinct paths; no conflict).
- No migration, no new Pydantic schema, no maker-checker.
- **Tests:** a service test (`list_accounts` returns all, filters by member,
  empty when none) and an API test (200 + shape, member_id filter, tenant-auth
  required), following the existing `tests/modules/savings/` patterns.

This touches `app/modules/savings/{api.py,service.py}` and `tests/modules/savings/`
only. It does **not** alter any existing endpoint or the `SavingsAccountOut`
shape, so it is portal-compatible by construction.

## Backend facts (authoritative — already in place)

Gate on every savings route is `CurrentTenantUser` (no fine-grained tenant RBAC).

- `GET /savings/products` (`?include_inactive`?) → `list[SavingsProductOut]`.
- `POST /savings/products` (201) → `SavingsProductOut`.
  `SavingsProductIn`: `name, interest_rate (Decimal), liability_account_id (uuid),
  minimum_balance (Decimal, default 0)`.
- `GET /savings/products/{id}` → `SavingsProductOut`
  (`id, name, interest_rate, minimum_balance, liability_account_id, is_active`).
- `POST /savings/accounts` (201) → `SavingsAccountOut`. `OpenAccountIn`:
  `member_id, savings_product_id`. 409 if an account already exists for that
  member+product; 400 if product missing/inactive.
- `GET /savings/accounts/{id}` → `SavingsAccountWithBalanceOut`
  (`SavingsAccountOut` + `balance: Decimal`).
  `SavingsAccountOut`: `id, member_id, savings_product_id, product_name,
  interest_rate, minimum_balance, liability_account_id`. **No status field.**
- `GET /savings/accounts/{id}/transactions` → `list[SavingsTransactionOut]`
  (`id, savings_account_id, transaction_type, amount, narration, journal_entry_id,
  posted_by`).
- `POST /savings/accounts/{id}/deposit` (201) → `SavingsTransactionOut`.
  `DepositIn`: `amount, payment_account_id (uuid), idempotency_key, narration?`.
- `POST /savings/accounts/{id}/withdraw` (**202**) → `WithdrawalOut`
  (`approval_request_id, status`) — **maker-checker** (CLAUDE.md rule 7).
  `WithdrawIn`: same fields as deposit.
- `GET /ledger/accounts` → `list[AccountOut]` — used to populate the
  GL-account `<Select>`s (product `liability_account_id`; deposit/withdraw
  `payment_account_id`).

### Pre-built portal surface (verified)

- **api-client** `resources.savings.{listProducts, createProduct, getProduct,
  createAccount, getAccount, deposit, withdraw, listTransactions}` — all carry the
  `as never` wart → cast to `{ data?, error? }`. **Add** `listAccounts(query?)`
  → `GET /savings/accounts`. `resources.ledger.listAccounts` exists.
- **@sacco/schemas** (`savings.ts`): `openAccountSchema`, `depositSchema`,
  `withdrawSchema`, `savingsProductSchema` + inferred `*Input`. **Add** read
  types: `SavingsProductOut`, `SavingsAccountOut`, `SavingsAccountWithBalanceOut`,
  `SavingsTransactionOut`.
- **@sacco/ui**: `DataTable`, `FormField`, `Input`, `Select`, `Money`,
  `MoneyInput`, `Percentage`, `Textarea`, `Dialog`, `MakerCheckerConfirmDialog`,
  `Card`, `FormattedDateTime`. (`savings_account` StatusBadge entity exists but
  is unused — the account has no status field.)
- **portal**: `getTenantPageContext()`, the `(tenant-authed)` layout, and the
  tenant sidebar `/savings` link all exist.

## Screens (under `app/(tenant-authed)/savings/*`)

All server-fetched via `getTenantPageContext()`; cast resource results to
`{ data?, error? }`. Gating is tenant-auth only (no RBAC keys).

### `/savings` — products landing

- Server: `savings.listProducts({})` → `SavingsProductOut[]`.
- `<ProductsTable>`: in-memory `<DataTable>` (`id="savings-products"`,
  `TData = SavingsProductOut`). Columns: **Name**, **Interest** (`<Percentage>`),
  **Min balance** (`<Money>`), **Active** (Yes/No). No row link (products have no
  detail screen in v1 beyond the row).
- Header: **Create product** → `/savings/products/new`.
- Empty: "No savings products yet."

### `/savings/products/new` — create product

- RHF + `zodResolver(savingsProductSchema)`. Fields via `<FormField>`: name
  (`<Input>`), interest_rate (`<PercentageInput>` or `<Input>` — confirm against
  an existing consumer), minimum_balance (`<MoneyInput>`), liability_account_id
  (`<Select>` from `ledger.listAccounts()`, server-fetched and passed in).
- On submit → `savings.createProduct(values)` → toast + `router.push("/savings")`.

### `/savings/accounts` — global accounts index

- Server: fetch **both** `savings.listAccounts({})` → `SavingsAccountOut[]`
  **and** `members.list({})` → `MemberOut[]`; build a `member_id → {name, number}`
  map (client-side join — no backend cross-module coupling).
- `<AccountsTable rows>`: in-memory `<DataTable>` (`id="savings-accounts"`).
  Columns: **Member** (name + number, or the raw `member_id` when unmapped),
  **Product** (`product_name`), **Interest** (`<Percentage>`), **Min balance**
  (`<Money>`), with the **Member**/**Product** linking to
  `/savings/accounts/{id}`. Empty: "No savings accounts yet."
- Header: **Open account** → `/savings/accounts/new`.

### `/savings/accounts/new` — open account

- RHF + `zodResolver(openAccountSchema)`. Fields: member_id (`<Select>` from
  `members.list()`), savings_product_id (`<Select>` from `savings.listProducts()`).
  Both server-fetched and passed in.
- An optional `?member_id=` query param pre-selects the member (used by the
  member-detail "Open account" link).
- On submit → `savings.createAccount(values)` (201 → `SavingsAccountOut`) →
  toast + `router.push("/savings/accounts/${data.id}")`. Handle 409
  ("already exists") via `apiErrorMessage`.

### `/savings/accounts/[id]` — account detail

- Server: `savings.getAccount(id)` → `SavingsAccountWithBalanceOut`
  (`notFound()` if absent) and `savings.listTransactions(id)` →
  `SavingsTransactionOut[]`.
- Read-only `<Card>`s: account summary (product, interest `<Percentage>`,
  min balance `<Money>`, **balance** `<Money>` prominent). A `<TransactionsTable>`
  (`id="savings-transactions"`): **Type**, **Amount** (`<Money>`), **Narration**
  (`?? "—"`). (No timestamp column — `SavingsTransactionOut` has none.)
- Header actions: **Deposit** and **Withdraw** (`<AccountActions>`).
- **No `<AuditBar>`** (tenant-schema record — same as 3a).

### Deposit / Withdraw (`<AccountActions>`, client)

Mirrors 3a `ChangeMemberStatusButton` + SP16 `InvoiceActions`:

- **Deposit** — a form `<Dialog>`: amount (`<MoneyInput>`), payment_account_id
  (`<Select>` from `ledger.listAccounts()`), narration (`<Textarea>`),
  `idempotency_key` (fresh UUID per form instance, contract L). Submit →
  `savings.deposit(id, values)` (201) → toast "Deposit posted" + `router.refresh()`.
  **Direct** (no maker-checker confirm).
- **Withdraw** — same form fields → opens `<MakerCheckerConfirmDialog>` (locked
  "creates an approval request, not execute" copy) → `savings.withdraw(id, values)`
  (**202**) → toast "Withdrawal requested — pending approval" + `router.refresh()`.
  The GL accounts list is server-fetched on the detail page and passed into
  `<AccountActions>`.

> **Checker side deferred:** approving a withdrawal needs the **tenant approvals
> inbox** (not built yet — same deferral as 3a). This module only *creates* the
> approval; the 202 `approval_request_id` surfaces in the toast.

### `/members/[id]` — add a "Savings accounts" section (3a modify)

- The member detail page additionally server-fetches
  `savings.listAccounts({ member_id: id })` and renders a **Savings accounts**
  `<Card>`: each account's product + interest + a link to
  `/savings/accounts/{accountId}`, plus an **Open account** button linking to
  `/savings/accounts/new?member_id=${id}`. Empty → "No savings accounts."

## New supporting pieces

- **Backend:** `SavingsService.list_accounts` + `GET /savings/accounts` route +
  tests.
- **api-client:** `resources.savings.listAccounts(query?)`.
- **@sacco/schemas** (`savings.ts`): the four read types above.
- **portal:** `ProductsTable`, `CreateProductForm`, `AccountsTable`,
  `OpenAccountForm`, account detail page, `TransactionsTable`, `AccountActions`;
  plus the member-detail savings section.

## File structure

**Backend:** `app/modules/savings/service.py` (+`list_accounts`),
`app/modules/savings/api.py` (+route), `tests/modules/savings/` (+cases).
**`@sacco/schemas`:** modify `src/savings.ts` (+4 read types).
**`@sacco/api-client`:** modify `src/resources/savings.ts` (+`listAccounts`).
**`@sacco/portal`:**
- `app/(tenant-authed)/savings/page.tsx` + `_components/ProductsTable.tsx`.
- `app/(tenant-authed)/savings/products/new/page.tsx` + `_components/CreateProductForm.tsx`.
- `app/(tenant-authed)/savings/accounts/page.tsx` + `_components/AccountsTable.tsx`.
- `app/(tenant-authed)/savings/accounts/new/page.tsx` + `_components/OpenAccountForm.tsx`.
- `app/(tenant-authed)/savings/accounts/[id]/page.tsx` +
  `_components/{TransactionsTable,AccountActions}.tsx`.
- `app/(tenant-authed)/members/[id]/page.tsx` (+savings section) +
  a `_components/MemberSavingsSection.tsx`.
- Tests under `apps/portal/src/__tests__/tenant-savings/`.

## Out of scope (deferred)

- Product edit/deactivate, account closure, interest posting UI.
- `<AuditBar>` on tenant records; the **tenant approvals inbox** (withdrawal
  checker side) — later Phase-3 module.
- Server-side pagination for the accounts index (in-memory like 3a; the lists
  are tenant-scoped and modest).
- e2e + next-intl (portal-wide deferral).

## Testing strategy

- **Backend:** pytest (service + API) against the Docker Postgres, per
  `tests/modules/savings/` conventions. Ruff + mypy clean.
- **Portal:** Vitest + Testing Library —
  - `ProductsTable` (rows + empty), `CreateProductForm` (validation + create →
    redirect; GL select populated).
  - `AccountsTable` (member-name join renders; unmapped falls back to id; empty).
  - `OpenAccountForm` (member/product selects; pre-select via member_id;
    create → redirect; 409 surfaces).
  - `AccountActions` (deposit is direct + posts; withdraw opens the maker-checker
    confirm with the locked copy and creates the approval).
  - `MemberSavingsSection` (lists accounts; open-account link carries member_id).
- Per-package `test` + `typecheck` + `lint` green.
