# SACCO Admin Portal — Shares Module (Phase 3c) Design

**Date:** 2026-06-21
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan c — Shares
**Status:** Approved

## Context

Phase 3c is the third SACCO-operator module, following Members (3a) and Savings
(3b). Like 3b it is mostly a **client** of a complete backend (`shares`), but it
carries **more groundwork** than 3b because — unlike savings — the shares module
has **no api-client resource, no `@sacco/schemas` entry, and no read/input
schemas** on the portal side yet. (The `/shares` sidebar link does already
exist.) The shares backend exposes products (list/create/get), open-account,
account-detail-by-id (with balance), transactions, purchase, and redeem — but,
exactly like savings before 3b, has **no way to list accounts**, so an operator
cannot browse them.

Per CLAUDE.md contract B ("if a sub-plan thinks it needs a new endpoint, stop and
surface"), the account-list gap was surfaced. The decision (vs the 3b client-join
approach) is to add a **richer** list endpoint returning a new
`ShareAccountListItemOut` that denormalises **same-module** fields
(`product_name`, `par_value`) and **computed holdings** (`shares_held`,
`total_value`) so the index is useful without N balance round-trips. Member names
are **not** included — CLAUDE.md rule 2 forbids the shares module from importing
the members model — so the portal resolves the member label with a single
client-side `members.list()` join (strictly less client work than 3b's
double-fetch, since the product join is now server-side).

This module reuses the tenant-operator pattern from 3a/3b
(`getTenantPageContext()` server-fetch, in-memory `<DataTable>`, RHF/Zod forms,
maker-checker action via `<MakerCheckerConfirmDialog>`).

## Shares-specific forks vs Savings

- **Quantity vs money.** Shares are integer quantities. `shares_held`,
  `minimum_shares`, `maximum_shares`, and the purchase/redeem `quantity` render
  via `<Count>`; `par_value`, transaction `amount`, and `total_value` render via
  `<Money>`. Purchase and redeem forms capture an integer **quantity**, not a
  money amount — the GL amount is derived backend-side (`quantity × par_value`).
- **`ShareAccountOut` has no `product_name`** (savings' did) — hence the richer
  list endpoint rather than a client product join.
- **Purchase = direct (201); Redeem = maker-checker (202)** — the savings
  deposit/withdraw analogue.

## Backend addition (the only backend change)

**`GET /shares/accounts` — optional `?member_id=<uuid>` filter →
`list[ShareAccountListItemOut]`**, gate `CurrentTenantUser`.

- New Pydantic schema `ShareAccountListItemOut`:
  `id, member_id, share_product_id, product_name, par_value (Decimal),
  shares_held (int), total_value (Decimal)`.
- New `ShareService.list_accounts(*, member_id: uuid.UUID | None = None) ->
  list[ShareAccountListItem]` — a **single grouped query**: `MemberShareAccount`
  LEFT JOIN `ShareProduct` (for `name`, `par_value`) LEFT JOIN a per-account
  `ShareTransaction` aggregate sub-select that computes
  `SUM(quantity) FILTER (purchase) - SUM(quantity) FILTER (redemption)` as
  `shares_held`; `total_value = shares_held × par_value` (computed in Python from
  the row, or in SQL). Ordered by `product_name, account.id`. Optional
  `.where(MemberShareAccount.member_id == member_id)`. Returns a list of
  lightweight row objects (a dataclass / `Row` mapping) the route maps to
  `ShareAccountListItemOut`. **Stays within the shares module** — no members
  import.
- Declared after the `POST /accounts` route and before
  `GET /accounts/{account_id}` (distinct paths; no conflict).
- No migration, no maker-checker.
- **Tests:** a service test (returns all with correct `shares_held`/`total_value`
  after purchases/redemptions, filters by member, empty when none) and an API
  test (200 + shape, `member_id` filter, tenant-auth required), following the
  existing `tests/modules/shares/` patterns.

This touches `app/modules/shares/{api.py,service.py,schemas.py}` and
`tests/modules/shares/` only. It does **not** alter any existing endpoint or
existing schema, so it is portal-compatible by construction.

## Backend facts (authoritative — already in place)

Gate on every shares route is `CurrentTenantUser` (no fine-grained tenant RBAC).

- `GET /shares/products` (`?include_inactive`?) → `list[ShareProductOut]`.
- `POST /shares/products` (201) → `ShareProductOut`. `ShareProductIn`:
  `name, par_value (Decimal, >0), minimum_shares (int, ≥1, default 1),
  maximum_shares (int|null), share_capital_account_id (uuid)`.
- `GET /shares/products/{id}` → `ShareProductOut`
  (`id, name, par_value, minimum_shares, maximum_shares,
  share_capital_account_id, is_active, created_at, updated_at`).
- `POST /shares/accounts` (201) → `ShareAccountOut`. `OpenAccountIn`:
  `member_id, share_product_id`. 409 if an account already exists for that
  member+product; 400 if product missing/inactive.
- `GET /shares/accounts/{id}` → `ShareAccountWithBalanceOut`
  (`ShareAccountOut` = `id, member_id, share_product_id, created_at, updated_at`;
  **+** `shares_held (int)`, `total_value (Decimal)`). **No status field, no
  product_name.**
- `GET /shares/accounts/{id}/transactions` → `list[ShareTransactionOut]`
  (`id, share_account_id, transaction_type, quantity (int), amount (Decimal),
  journal_entry_id, posted_by, posted_at, idempotency_key`).
- `POST /shares/accounts/{id}/purchase` (201) → `ShareTransactionOut`.
  `PurchaseSharesIn`: `quantity (int, ≥1), payment_account_id (uuid),
  idempotency_key (str, 1..200)`.
- `POST /shares/accounts/{id}/redeem` (**202**) → `RedemptionOut`
  (`approval_request_id, status`) — **maker-checker** (CLAUDE.md rule 7).
  `RedeemSharesIn`: `quantity (int, ≥1), payment_account_id (uuid),
  reason (str|null), idempotency_key (str, 1..200)`.
- `GET /ledger/accounts` → `list[AccountOut]` — populates the GL-account
  `<Select>`s (product `share_capital_account_id`; purchase/redeem
  `payment_account_id`).

### Portal surface to build (NOT pre-built — differs from 3b)

- **api-client:** **create** `resources/shares.ts` with
  `{ listProducts, createProduct, getProduct, listAccounts, openAccount,
  getAccount, listTransactions, purchase, redeem }` (cast each `{ data?, error? }`
  per the `as never` wart), and wire it into `resources/index.ts`.
  `resources.ledger.listAccounts` + `resources.members.list` already exist.
- **@sacco/schemas:** **create** `src/shares.ts` with input Zod schemas
  (`shareProductSchema`, `openShareAccountSchema`, `purchaseSharesSchema`,
  `redeemSharesSchema`) + inferred `*Input`, **and** read types
  (`ShareProductOut`, `ShareAccountOut`, `ShareAccountWithBalanceOut`,
  `ShareTransactionOut`, `ShareAccountListItemOut`). Export from `src/index.ts`.
  Decimals are JSON strings; integer quantities are `number`.
- **@sacco/ui (exists):** `DataTable`, `FormField`, `Input`, `Select`, `Money`,
  `MoneyInput`, `Count`, `Textarea`, `Dialog`, `MakerCheckerConfirmDialog`,
  `Card`. (There is no `<CountInput>` — integer quantity uses `<Input
  type="number">` via `<FormField>`, or a plain `<Input>` with a numeric Zod
  coercion; confirm against an existing numeric consumer.)
- **portal:** `getTenantPageContext()`, the `(tenant-authed)` layout, and the
  tenant sidebar `/shares` link all exist.

## Screens (under `app/(tenant-authed)/shares/*`)

All server-fetched via `getTenantPageContext()`; cast resource results to
`{ data?, error? }`. Gating is tenant-auth only (no RBAC keys).

### `/shares` — products landing

- Server: `shares.listProducts({})` → `ShareProductOut[]`.
- `<ProductsTable>`: in-memory `<DataTable>` (`id="share-products"`,
  `TData = ShareProductOut`). Columns: **Name**, **Par value** (`<Money>`),
  **Min shares** (`<Count>`), **Max shares** (`<Count>` or "—" when null),
  **Active** (Yes/No). No row link (no product detail screen in v1).
- Header: **Create product** → `/shares/products/new`.
- Empty: "No share products yet."

### `/shares/products/new` — create product

- RHF + `zodResolver(shareProductSchema)`. Fields via `<FormField>`: name
  (`<Input>`), par_value (`<MoneyInput>`), minimum_shares (numeric `<Input>`),
  maximum_shares (numeric `<Input>`, optional), share_capital_account_id
  (`<Select>` from `ledger.listAccounts()`, server-fetched and passed in).
- On submit → `shares.createProduct(values)` → toast + `router.push("/shares")`.

### `/shares/accounts` — global accounts index

- Server: fetch **both** `shares.listAccounts({})` → `ShareAccountListItemOut[]`
  **and** `members.list({})` → `MemberOut[]`; build a `member_id → {name, number}`
  map (single client-side join — member names only). Build an `AccountRow`
  view-model `{ id, member_label, product_name, shares_held, total_value }`.
- `<AccountsTable rows>`: in-memory `<DataTable>` (`id="share-accounts"`).
  Columns: **Member** (name + number, or raw `member_id` when unmapped, linking
  to `/shares/accounts/{id}`), **Product** (`product_name`), **Shares**
  (`<Count>`), **Value** (`<Money>`). Empty: "No share accounts yet."
- Header: **Open account** → `/shares/accounts/new`.

### `/shares/accounts/new` — open account

- RHF + `zodResolver(openShareAccountSchema)`. Fields: member_id (`<Select>` from
  `members.list()`), share_product_id (`<Select>` from `shares.listProducts()`).
  Both server-fetched and passed in.
- Optional `?member_id=` query param pre-selects the member (member-detail link).
- On submit → `shares.openAccount(values)` (201 → `ShareAccountOut`) → toast +
  `router.push("/shares/accounts/${data.id}")`. Handle 409 via `apiErrorMessage`.

### `/shares/accounts/[id]` — account detail

- Server (parallel): `shares.getAccount(id)` → `ShareAccountWithBalanceOut`
  (`notFound()` if absent), `shares.getProduct(account.share_product_id)` →
  `ShareProductOut` (for the product name + par value header — `getAccount`
  resolves first since the product id comes from it; or fetch the account then
  the product), `shares.listTransactions(id)` → `ShareTransactionOut[]`, and
  `ledger.listAccounts({})` for the purchase/redeem GL `<Select>`.
- Header: `<h1>{product.name}</h1>`. Read-only `<Card>`: **par value**
  (`<Money>`), **shares held** (`<Count>`, prominent), **total value**
  (`<Money>`, prominent). A `<TransactionsTable>` (`id="share-transactions"`): **Type**
  (`transaction_type`), **Quantity** (`<Count>`), **Amount** (`<Money>`).
- Header actions: **Purchase** and **Redeem** (`<AccountActions>`).
- **No `<AuditBar>`** (tenant-schema record — same as 3a/3b).

### Purchase / Redeem (`<AccountActions>`, client)

Mirrors 3b `AccountActions`:

- **Purchase** — a form `<Dialog>`: quantity (numeric `<Input>`),
  payment_account_id (`<Select>` from `ledger.listAccounts()`),
  `idempotency_key` (fresh UUID per form instance, contract L). Submit →
  `shares.purchase(id, values)` (201) → toast "Shares purchased" +
  `router.refresh()`. **Direct** (no maker-checker confirm).
- **Redeem** — quantity + payment_account_id + reason (`<Textarea>`) →
  opens `<MakerCheckerConfirmDialog>` (locked "creates an approval request, not
  execute" copy) → `shares.redeem(id, values)` (**202**) → toast "Redemption
  requested — pending approval" + `router.refresh()`.

> **Checker side deferred:** approving a redemption needs the **tenant approvals
> inbox** (not built yet — same deferral as 3a/3b). This module only *creates* the
> approval; the 202 `approval_request_id` surfaces in the toast.

### `/members/[id]` — add a "Share accounts" section (3a/3b modify)

- The member detail page additionally server-fetches
  `shares.listAccounts({ member_id: id })` and renders a **Share accounts**
  `<Card>`: each account's product + shares held (`<Count>`) + a link to
  `/shares/accounts/{accountId}`, plus an **Open account** button linking to
  `/shares/accounts/new?member_id=${id}`. Empty → "No share accounts."

## New supporting pieces

- **Backend:** `ShareAccountListItemOut` schema + `ShareService.list_accounts` +
  `GET /shares/accounts` route + tests.
- **api-client:** new `resources/shares.ts` + index wiring.
- **@sacco/schemas:** new `src/shares.ts` (input schemas + read types) + index
  export.
- **portal:** `ProductsTable`, `CreateProductForm`, `AccountsTable`,
  `OpenAccountForm`, account detail page, `TransactionsTable`, `AccountActions`;
  plus the member-detail share section.

## File structure

**Backend:** `app/modules/shares/{schemas.py,service.py,api.py}` (+list),
`tests/modules/shares/` (+cases).
**`@sacco/schemas`:** create `src/shares.ts`; modify `src/index.ts`.
**`@sacco/api-client`:** create `src/resources/shares.ts`; modify
`src/resources/index.ts`.
**`@sacco/portal`:**
- `app/(tenant-authed)/shares/page.tsx` + `_components/ProductsTable.tsx`.
- `app/(tenant-authed)/shares/products/new/page.tsx` + `_components/CreateProductForm.tsx`.
- `app/(tenant-authed)/shares/accounts/page.tsx` + `_components/AccountsTable.tsx`.
- `app/(tenant-authed)/shares/accounts/new/page.tsx` + `_components/OpenAccountForm.tsx`.
- `app/(tenant-authed)/shares/accounts/[id]/page.tsx` +
  `_components/{TransactionsTable,AccountActions}.tsx`.
- `app/(tenant-authed)/members/[id]/page.tsx` (+share section) +
  a `_components/MemberSharesSection.tsx`.
- Tests under `apps/portal/src/__tests__/tenant-shares/`.

## Out of scope (deferred)

- Product edit/deactivate, account closure, dividend posting UI.
- `<AuditBar>` on tenant records; the **tenant approvals inbox** (redemption
  checker side) — later Phase-3 module.
- Server-side pagination for the accounts index (in-memory like 3a/3b; lists are
  tenant-scoped and modest).
- e2e + next-intl (portal-wide deferral).

## Testing strategy

- **Backend:** pytest (service + API) against the Docker Postgres
  (`DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test`),
  per `tests/modules/shares/` conventions. Ruff + mypy clean.
- **Portal:** Vitest + Testing Library —
  - `@sacco/schemas`: input-schema validation + read-type structural usability.
  - `ProductsTable` (rows + empty), `CreateProductForm` (validation + create →
    redirect; GL select populated).
  - `AccountsTable` (member-name join renders; unmapped falls back to id; empty).
  - `OpenAccountForm` (member/product selects; pre-select via member_id;
    create → redirect; 409 surfaces).
  - `AccountActions` (purchase is direct + posts; redeem opens the maker-checker
    confirm with the locked copy and creates the approval).
  - `MemberSharesSection` (lists accounts; open-account link carries member_id).
- Per-package `test` + `typecheck` + `lint` green.
