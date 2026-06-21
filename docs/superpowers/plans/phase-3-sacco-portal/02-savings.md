# SACCO Admin Portal — Savings Module (Phase 3b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-21):** background subagents can't get Edit approval; run **inline**. **Confirm typecheck PASSES before committing** (SP20 lesson). Backend tests need the Docker Postgres — `DATABASE_URL` points at the postgres-test container on **:5433** (not the stale `.env` :5532/:5533). Export the right URL before running pytest.

**Goal:** The second SACCO-operator module — Savings products, accounts (with a new list endpoint), deposits, and maker-checker withdrawals — as a near-pure client plus one minimal backend list route.

**Architecture:** One backend addition (`GET /savings/accounts?member_id=`), then tenant-authed portal screens under `app/(tenant-authed)/savings/*` server-fetched via `getTenantPageContext()`. In-memory `<DataTable>`s, RHF/Zod forms, GL-account `<Select>`s from `ledger.listAccounts()`, deposit (direct 201) and withdraw (maker-checker 202) actions. The accounts index joins `savings.listAccounts()` with `members.list()` client-side for display names. Clones the 3a tenant-operator pattern.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async (backend route/service + pytest); Next.js 15, React 19, TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **One new backend endpoint** (`GET /savings/accounts`), explicitly approved (CLAUDE.md contract B "surface" path). It does not alter any existing endpoint or `SavingsAccountOut`. Backend changes confined to `app/modules/savings/{api.py,service.py}` + `tests/modules/savings/`.
- **Savings module contracts still apply:** never write journals/balances directly here (this route is read-only — fine); `SavingsAccountOut` has **no status** (no StatusBadge for accounts).
- **api-client (exists):** `resources.savings.{listProducts, createProduct, getProduct, createAccount, getAccount, deposit, withdraw, listTransactions}` + add `listAccounts`. `resources.ledger.listAccounts` exists. `resources.members.list` exists (3a). All carry the `as never` wart → cast to `{ data?, error? }`.
- **@sacco/schemas (exist):** `savingsProductSchema`, `openAccountSchema`, `depositSchema`, `withdrawSchema`. Add read types `SavingsProductOut`, `SavingsAccountOut`, `SavingsAccountWithBalanceOut`, `SavingsTransactionOut`.
- **Gating:** tenant-auth only via `getTenantPageContext()`.
- **Withdraw is maker-checker** (202 → tenant approval); checker side deferred to the future tenant approvals inbox (same as 3a). Deposit is direct (201).
- **No `<AuditBar>`** on tenant records.

## File structure

**Backend:** `app/modules/savings/service.py` (+`list_accounts`), `app/modules/savings/api.py` (+route), `tests/modules/savings/{test_service.py,test_api.py}` (+cases).
**`@sacco/schemas`:** `src/savings.ts` (+4 read types).
**`@sacco/api-client`:** `src/resources/savings.ts` (+`listAccounts`).
**`@sacco/portal`** (all under `app/(tenant-authed)/`):
- `savings/page.tsx` + `_components/ProductsTable.tsx`
- `savings/products/new/page.tsx` + `_components/CreateProductForm.tsx`
- `savings/accounts/page.tsx` + `_components/AccountsTable.tsx`
- `savings/accounts/new/page.tsx` + `_components/OpenAccountForm.tsx`
- `savings/accounts/[id]/page.tsx` + `_components/{TransactionsTable,AccountActions}.tsx`
- `members/[id]/page.tsx` (+savings section) + `_components/MemberSavingsSection.tsx`
- Tests under `apps/portal/src/__tests__/tenant-savings/`.

---

## Task 1: Backend — `GET /savings/accounts` (service + route + tests)

**Files:**
- Modify: `app/modules/savings/service.py` (add `list_accounts` after `get_account`, ~line 123)
- Modify: `app/modules/savings/api.py` (add route after `open_account`, before `get_account`)
- Test: `tests/modules/savings/test_service.py`, `tests/modules/savings/test_api.py`

- [ ] **Step 1: Service test (failing)** — append to `test_service.py`:

```python
async def test_list_accounts_returns_all_and_filters_by_member(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    member_a = await _setup_member(test_engine)
    member_b = await _setup_member(test_engine)

    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        await svc.open_account(member_id=member_a, savings_product_id=product_id)
        await svc.open_account(member_id=member_b, savings_product_id=product_id)
        await session.commit()

        all_accounts = await svc.list_accounts()
        assert len(all_accounts) >= 2

        only_a = await svc.list_accounts(member_id=member_a)
        assert len(only_a) == 1
        assert only_a[0].member_id == member_a
    finally:
        await session.close()
        await _cleanup(test_engine)
```

Run (export the Docker DB URL first):
```bash
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/sacco_test"
pytest tests/modules/savings/test_service.py::test_list_accounts_returns_all_and_filters_by_member -v
```
Expected: FAIL (`AttributeError: 'SavingsService' object has no attribute 'list_accounts'`).

- [ ] **Step 2: Implement `list_accounts`** in `service.py` (after `get_account`):

```python
    async def list_accounts(
        self, *, member_id: uuid.UUID | None = None
    ) -> list[SavingsAccount]:
        q = select(SavingsAccount).order_by(
            SavingsAccount.product_name, SavingsAccount.id
        )
        if member_id is not None:
            q = q.where(SavingsAccount.member_id == member_id)
        result = await self._session.execute(q)
        return list(result.scalars().all())
```

- [ ] **Step 3: Run service test → PASS.**

- [ ] **Step 4: API test (failing)** — append to `test_api.py`:

```python
async def test_list_accounts_returns_200_and_filters(client):
    liability_id = await _create_gl_account(
        client, f"2-{uuid.uuid4().hex[:6]}", "Member Savings", "liability"
    )
    product_id = await _create_product(client, liability_id)
    member_a = await _create_member(client)
    member_b = await _create_member(client)
    await _open_account(client, product_id, member_a)
    await _open_account(client, product_id, member_b)

    resp = await client.get("/savings/accounts", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 2

    resp_a = await client.get(
        "/savings/accounts", params={"member_id": member_a}, headers=HEADERS
    )
    assert resp_a.status_code == 200, resp_a.text
    data = resp_a.json()
    assert len(data) == 1
    assert data[0]["member_id"] == member_a


async def test_list_accounts_requires_tenant(client):
    resp = await client.get("/savings/accounts")  # no X-Tenant-Slug
    assert resp.status_code in (401, 403, 422), resp.text
```

Run:
```bash
pytest tests/modules/savings/test_api.py::test_list_accounts_returns_200_and_filters tests/modules/savings/test_api.py::test_list_accounts_requires_tenant -v
```
Expected: FAIL (404 — route not defined).

- [ ] **Step 5: Implement the route** in `api.py` (insert between `open_account` and `get_account`):

```python
@router.get("/accounts", response_model=list[SavingsAccountOut])
async def list_accounts(
    session: Session,
    user: CurrentTenantUser,
    member_id: uuid.UUID | None = None,
) -> list[SavingsAccountOut]:
    svc = SavingsService(session)
    accounts = await svc.list_accounts(member_id=member_id)
    return [SavingsAccountOut.model_validate(a) for a in accounts]
```

- [ ] **Step 6: Run both API tests → PASS. Then ruff + mypy + full savings suite.**

```bash
pytest tests/modules/savings/ -q
ruff check app/modules/savings/ tests/modules/savings/
mypy app/modules/savings/
```

- [ ] **Step 7: Commit.**

```bash
git add app/modules/savings/service.py app/modules/savings/api.py tests/modules/savings/test_service.py tests/modules/savings/test_api.py
git commit -m "feat(savings): list accounts endpoint (member filter)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `@sacco/schemas` read types + `listAccounts` resource

**Files:**
- Modify: `admin/packages/schemas/src/savings.ts`
- Modify: `admin/packages/api-client/src/resources/savings.ts`
- Test: `admin/packages/schemas/src/__tests__/savings.test.ts` (create or extend)

- [ ] **Step 1: Failing test** — assert the new read types are usable:

```ts
import { describe, expect, it } from "vitest";
import { savingsProductSchema, type SavingsAccountWithBalanceOut } from "../savings";

describe("savings read types", () => {
  it("product schema rejects a blank name", () => {
    expect(savingsProductSchema.safeParse({ name: "", interest_rate: "5", liability_account_id: "x", minimum_balance: "0" }).success).toBe(false);
  });
  it("SavingsAccountWithBalanceOut is structurally usable", () => {
    const a: SavingsAccountWithBalanceOut = {
      id: "a1", member_id: "m1", savings_product_id: "p1", product_name: "Regular",
      interest_rate: "5.00", minimum_balance: "500.00", liability_account_id: "g1", balance: "1000.00",
    };
    expect(a.balance).toBe("1000.00");
  });
});
```

Run: `cd admin && pnpm --filter @sacco/schemas test -- savings` → FAIL.

- [ ] **Step 2: Add read types** to `savings.ts` (after the inferred input types). Money/rate as strings (the api returns Decimals as JSON strings):

```ts
// Mirror app/modules/savings/schemas.py. Decimals are JSON strings.
export interface SavingsProductOut {
  id: string;
  name: string;
  interest_rate: string;
  minimum_balance: string;
  liability_account_id: string;
  is_active: boolean;
}

export interface SavingsAccountOut {
  id: string;
  member_id: string;
  savings_product_id: string;
  product_name: string;
  interest_rate: string;
  minimum_balance: string;
  liability_account_id: string;
}

export interface SavingsAccountWithBalanceOut extends SavingsAccountOut {
  balance: string;
}

export interface SavingsTransactionOut {
  id: string;
  savings_account_id: string;
  transaction_type: string;
  amount: string;
  narration: string | null;
  journal_entry_id: string;
  posted_by: string;
}
```

- [ ] **Step 3: Add `listAccounts`** to `resources/savings.ts` (after `getProduct`, before `createAccount`):

```ts
    listAccounts: (query?: Record<string, unknown>) =>
      api.GET("/savings/accounts" as never, { params: { query } } as never),
```

- [ ] **Step 4: Run schemas test + typecheck both packages; commit.**

```bash
pnpm --filter @sacco/schemas test -- savings && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/api-client typecheck
git add admin/packages/schemas/src/savings.ts admin/packages/schemas/src/__tests__/savings.test.ts admin/packages/api-client/src/resources/savings.ts
git commit -m "feat(portal): savings read types + listAccounts resource

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Products — `<ProductsTable>` + `/savings` + `<CreateProductForm>` + `/savings/products/new`

**Files:**
- Create: `savings/_components/ProductsTable.tsx`, `savings/page.tsx`
- Create: `savings/products/new/_components/CreateProductForm.tsx`, `savings/products/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-savings/{ProductsTable,CreateProductForm}.test.tsx`

- [ ] **Step 1: `ProductsTable` test (failing)** — clone 3a `MembersTable.test.tsx` (mock `useTableUrlState`; `TenantCurrencyProvider` wrapper). `TData = SavingsProductOut`. Assert a row renders the name + interest "5%" + the empty state "No savings products yet".

- [ ] **Step 2: Implement `ProductsTable.tsx`** — clone 3a `MembersTable` structure exactly (`"use client"`, in-memory filter/sort/paginate, `useTableUrlState`). `id="savings-products"`. Columns: Name; Interest → `<Percentage value={row.original.interest_rate} />`; Min balance → `<Money amount={row.original.minimum_balance} />`; Active → `row.original.is_active ? "Yes" : "No"`. No filterSlot needed (or keep an active filter — optional). Empty `{ title: "No savings products yet", description: "Create a product to start opening accounts." }`. `state={{ totalRows: filtered.length, isError:false, isPermissionDenied:false }}`.

> `<Money>` reads currency from `<TenantCurrencyProvider>` (already in the tenant layout). `<Percentage>` takes `value` as a string/number.

- [ ] **Step 3: Implement `savings/page.tsx`** (server) — clone 3a members `page.tsx`: `getTenantPageContext()`, `savings.listProducts({})` cast `{ data?: SavingsProductOut[] }`, `<h1>Savings products</h1>`, a **Create product** `<Button asChild><Link href="/savings/products/new">`, `<ProductsTable rows={data ?? []} />`. `export const metadata = { title: "Savings" }`.

- [ ] **Step 4: `CreateProductForm` test (failing)** — clone 3a `CreateMemberForm.test.tsx`: mock `next/navigation` push + `useAuth` (`resources.savings.createProduct`). Render in `<QueryClientProvider>`. Pass a `glAccounts` prop `[{id:"g1",code:"2000",name:"Member Savings",account_type:"liability"}]`. Fill name, interest, min balance, pick the GL account, submit; assert `createProduct` called with the payload and `push("/savings")` (or to the products list). Also assert a blank name blocks submit.

- [ ] **Step 5: Implement `CreateProductForm.tsx`** (client) — clone 3a `CreateMemberForm` wiring (RHF + `zodResolver(savingsProductSchema)`, `useTypedMutation` → `savings.createProduct`). Props `{ glAccounts: AccountOut[] }` (type it locally as `{ id: string; code: string; name: string; account_type: string }[]`). Fields via `<FormField>`: name (`<Input>`); interest_rate (`<PercentageInput>` — confirm prop shape `value`/`onValueChange`/`onBlur`/`name`/`ref` against `AssignPlanForm`'s `<DateInput>` analog and an existing `<MoneyInput>`/`<PercentageInput>` consumer); minimum_balance (`<MoneyInput>`); liability_account_id (`<Select>` mapping `glAccounts` → `<SelectItem value={a.id}>{a.code} — {a.name}</SelectItem>`). `defaultValues: { name: "", interest_rate: "", minimum_balance: "", liability_account_id: "" }`. onSuccess `toast.success("Product created")` + `router.push("/savings")`; onError `apiErrorMessage`. Cancel → `/savings`.

- [ ] **Step 6: Implement `products/new/page.tsx`** (server) — `getTenantPageContext()`, fetch `ledger.listAccounts({})` cast `{ data?: { id:string; code:string; name:string; account_type:string }[] }`, `<h1>Create savings product</h1>`, `<CreateProductForm glAccounts={accounts ?? []} />`.

- [ ] **Step 7: Run the two tests + portal typecheck + lint; commit.**

```bash
git add "admin/apps/portal/app/(tenant-authed)/savings/page.tsx" "admin/apps/portal/app/(tenant-authed)/savings/_components/ProductsTable.tsx" "admin/apps/portal/app/(tenant-authed)/savings/products/" admin/apps/portal/src/__tests__/tenant-savings/ProductsTable.test.tsx admin/apps/portal/src/__tests__/tenant-savings/CreateProductForm.test.tsx
git commit -m "feat(portal): SACCO savings products list + create

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Accounts index + open — `<AccountsTable>` + `/savings/accounts` + `<OpenAccountForm>` + `/savings/accounts/new`

**Files:**
- Create: `savings/accounts/_components/AccountsTable.tsx`, `savings/accounts/page.tsx`
- Create: `savings/accounts/new/_components/OpenAccountForm.tsx`, `savings/accounts/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-savings/{AccountsTable,OpenAccountForm}.test.tsx`

- [ ] **Step 1: `AccountsTable` test (failing)** — `TData` is a view-model row `AccountRow = { id; member_label; product_name; interest_rate; minimum_balance }`. The component does **not** fetch members; the page builds `member_label`. Assert: a row links member_label to `/savings/accounts/a1`; empty state "No savings accounts yet".

- [ ] **Step 2: Implement `AccountsTable.tsx`** — clone the in-memory DataTable. Export an `AccountRow` interface. `id="savings-accounts"`. Columns: Member → `<Link href={/savings/accounts/${id}}>{member_label}</Link>`; Product (`product_name`); Interest (`<Percentage>`); Min balance (`<Money>`). Empty `{ title: "No savings accounts yet", description: "Open an account from a member or here." }`.

- [ ] **Step 3: Implement `savings/accounts/page.tsx`** (server) — the **client-side join**:

```tsx
const { resources } = await getTenantPageContext();
const [{ data: accounts }, { data: members }] = await Promise.all([
  resources.savings.listAccounts({}) as Promise<{ data?: SavingsAccountOut[]; error?: unknown }>,
  resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
]);
const byId = new Map((members ?? []).map((m) => [m.id, m]));
const rows: AccountRow[] = (accounts ?? []).map((a) => {
  const m = byId.get(a.member_id);
  return {
    id: a.id,
    member_label: m ? `${m.full_name} (${m.member_number})` : a.member_id,
    product_name: a.product_name,
    interest_rate: a.interest_rate,
    minimum_balance: a.minimum_balance,
  };
});
```
Header **Open account** → `/savings/accounts/new`. `<AccountsTable rows={rows} />`.

- [ ] **Step 4: `OpenAccountForm` test (failing)** — mock push + `useAuth` (`resources.savings.createAccount`). Props `members` + `products` arrays. Optional `defaultMemberId`. Pick member + product, submit → `createAccount({member_id, savings_product_id})` → `push("/savings/accounts/a9")` on `{ data: { id: "a9" } }`. Assert `defaultMemberId` pre-selects.

- [ ] **Step 5: Implement `OpenAccountForm.tsx`** (client) — RHF + `zodResolver(openAccountSchema)`, `defaultValues: { member_id: defaultMemberId ?? "", savings_product_id: "" }`. Props `{ members: {id;full_name;member_number}[]; products: {id;name}[]; defaultMemberId?: string }`. Two `<Select>`s via `<FormField>`. `useTypedMutation` → `savings.createAccount(values)` cast `{ data?: SavingsAccountOut }`; onSuccess `toast.success("Account opened")` + `router.push(/savings/accounts/${data.id})`; onError `apiErrorMessage` (covers 409 "already exists"). Cancel → `/savings/accounts`.

- [ ] **Step 6: Implement `accounts/new/page.tsx`** (server) — reads `searchParams` for `member_id`; fetches `members.list({})` + `savings.listProducts({})`; passes `defaultMemberId`. Next 15: `searchParams` is a `Promise` — `const sp = await searchParams;`. Signature: `{ searchParams: Promise<{ member_id?: string }> }`. `<h1>Open savings account</h1>`.

- [ ] **Step 7: Run tests + typecheck + lint; commit.**

```bash
git add "admin/apps/portal/app/(tenant-authed)/savings/accounts/page.tsx" "admin/apps/portal/app/(tenant-authed)/savings/accounts/_components/AccountsTable.tsx" "admin/apps/portal/app/(tenant-authed)/savings/accounts/new/" admin/apps/portal/src/__tests__/tenant-savings/AccountsTable.test.tsx admin/apps/portal/src/__tests__/tenant-savings/OpenAccountForm.test.tsx
git commit -m "feat(portal): SACCO savings accounts index + open account

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Account detail + deposit/withdraw — `[id]/page.tsx` + `<TransactionsTable>` + `<AccountActions>`

**Files:**
- Create: `savings/accounts/[id]/page.tsx`, `_components/TransactionsTable.tsx`, `_components/AccountActions.tsx`
- Test: `apps/portal/src/__tests__/tenant-savings/AccountActions.test.tsx`

- [ ] **Step 1: `TransactionsTable.tsx`** (client) — in-memory DataTable, `id="savings-transactions"`, `TData = SavingsTransactionOut`. Columns: Type (`transaction_type`); Amount (`<Money amount={amount} />`); Narration (`?? "—"`). Empty `{ title: "No transactions yet", description: "Deposits and withdrawals appear here." }`. (No timestamp column — the Out has none.)

- [ ] **Step 2: `[id]/page.tsx`** (server) — fetch in parallel: `savings.getAccount(id)` cast `{ data?: SavingsAccountWithBalanceOut }` (`notFound()` if absent), `savings.listTransactions(id)` cast `{ data?: SavingsTransactionOut[] }`, and `ledger.listAccounts({})` for the deposit/withdraw GL select. Header: `<h1>{account.product_name}</h1>` + `<AccountActions accountId={id} glAccounts={accounts ?? []} />`. A summary `<Card>`: product, interest `<Percentage>`, min balance `<Money>`, **Balance** `<Money amount={account.balance} />` (emphasised). Then `<TransactionsTable rows={txns ?? []} />`. No `<AuditBar>`.

- [ ] **Step 3: `AccountActions` test (failing)** — mock `next/navigation` (`refresh`), `useAuth` (`resources.savings.{deposit,withdraw}`). Props `accountId`, `glAccounts`. Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`.
  - **Deposit:** click "Deposit" → fill amount, pick GL account → submit → `deposit("a1", {...})` called; toast "Deposit posted". (No maker-checker dialog.)
  - **Withdraw:** click "Withdraw" → fill amount + GL → submit opens `<MakerCheckerConfirmDialog>`; assert the locked copy "create an approval request, not execute" + the "Create Approval Request" button; confirm → `withdraw("a1", {...})` called; toast "Withdrawal requested — pending approval".

- [ ] **Step 4: Implement `AccountActions.tsx`** (client) — mirror SP16 `InvoiceActions` (two form dialogs) + 3a `ChangeMemberStatusButton` (maker-checker wiring). Props `{ accountId: string; glAccounts: {id;code;name;account_type}[] }`.
  - Two RHF forms: deposit (`zodResolver(depositSchema)`) and withdraw (`zodResolver(withdrawSchema)`), each `defaultValues: { amount: "", payment_account_id: "", idempotency_key: <fresh uuid via useState>, narration: "" }`.
  - Fields via `<FormField>`: amount (`<MoneyInput>`), payment_account_id (`<Select>` from `glAccounts` → `{code} — {name}`), narration (`<Textarea>`).
  - **Deposit mutation** → `savings.deposit(accountId, values)` cast `{ data?, error? }`; onSuccess close dialog, `toast.success("Deposit posted")`, `router.refresh()`. **Direct** — the deposit form's submit calls `mutate` directly (no confirm dialog).
  - **Withdraw**: the form submit stashes `pendingWithdraw` + opens `<MakerCheckerConfirmDialog open operationLabel="savings withdrawal" subjectLabel={amount}>`; `onConfirm` → `withdraw(accountId, pending)` (202). onSuccess `toast.success("Withdrawal requested — pending approval")`, `router.refresh()`.

- [ ] **Step 5: Run test + typecheck + lint; commit.**

```bash
git add "admin/apps/portal/app/(tenant-authed)/savings/accounts/[id]/" admin/apps/portal/src/__tests__/tenant-savings/AccountActions.test.tsx
git commit -m "feat(portal): SACCO savings account detail + deposit/withdraw

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Member-detail savings section (3a modify)

**Files:**
- Create: `members/[id]/_components/MemberSavingsSection.tsx`
- Modify: `members/[id]/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-savings/MemberSavingsSection.test.tsx`

- [ ] **Step 1: Test (failing)** — `MemberSavingsSection` is a presentational client/server component taking `{ memberId: string; accounts: SavingsAccountOut[] }`. Assert: an account row links to `/savings/accounts/{id}` and shows the product name; the **Open account** link points to `/savings/accounts/new?member_id={memberId}`; empty state "No savings accounts" when `accounts=[]`.

- [ ] **Step 2: Implement `MemberSavingsSection.tsx`** — a `<Card>` titled "Savings accounts". For each account: product_name + interest `<Percentage>` + a `<Link href={/savings/accounts/${a.id}}>View</Link>`. Header has a `<Button asChild variant="secondary"><Link href={/savings/accounts/new?member_id=${memberId}}>Open account</Link></Button>`. Empty → "No savings accounts." (It's a server component — no hooks — so no `"use client"`.)

- [ ] **Step 3: Modify `members/[id]/page.tsx`** — additionally fetch `savings.listAccounts({ member_id: id })` cast `{ data?: SavingsAccountOut[] }` (add to the existing fetch; use `Promise.all` with the `members.get`). Render `<MemberSavingsSection memberId={data.id} accounts={accounts ?? []} />` below the KYC card.

- [ ] **Step 4: Run the section test + the existing 3a member tests (ensure no regression) + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-members tenant-savings
git add "admin/apps/portal/app/(tenant-authed)/members/[id]/" admin/apps/portal/src/__tests__/tenant-savings/MemberSavingsSection.test.tsx
git commit -m "feat(portal): member-detail savings accounts section

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Verification + PR

- [ ] **Step 1: Backend gate** (Docker DB up):
```bash
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/sacco_test"
pytest tests/modules/savings/ -q
ruff check app/modules/savings/ tests/modules/savings/ && mypy app/modules/savings/
```

- [ ] **Step 2: Portal/packages gate**:
```bash
cd admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test delta (+ ProductsTable, CreateProductForm, AccountsTable, OpenAccountForm, AccountActions, MemberSavingsSection cases over the 187 baseline).

- [ ] **Step 3: Contract spot-checks**:
  - [ ] Backend diff confined to savings + tests: `git diff --name-only main...HEAD | grep -E '^app/' ` shows only `app/modules/savings/{api,service}.py`.
  - [ ] No migrations: `git diff --name-only main...HEAD | grep -E '^alembic/'` empty.
  - [ ] Portal changes under `admin/` + `docs/` only.
  - [ ] No StatusBadge misuse for accounts: `rg "entity=\"savings_account\"" "admin/apps/portal/app/(tenant-authed)/savings"` empty.

- [ ] **Step 4: Final holistic review** — products list/create; accounts index joins member names; open-account redirects to detail; detail shows balance + transactions; deposit is direct, withdraw is maker-checker (locked copy, creates a tenant approval); member detail links to its accounts. No AuditBar; tenant-auth gating only.

- [ ] **Step 5: Push + PR**:
```bash
git push -u origin feat/sacco-portal/02-savings
gh pr create --title "feat(portal): SACCO admin — Savings module (Phase 3b)" --body "$(cat <<'EOF'
## Summary
- Second **SACCO-operator** module: Savings products, accounts index, open-account, deposits, and maker-checker withdrawals.
- **One backend addition** (explicitly approved): `GET /savings/accounts?member_id=` — the savings backend had no account-list endpoint, so an operator couldn't browse accounts. Service + route + tests; no migration; existing endpoints and `SavingsAccountOut` untouched.
- Portal screens are otherwise a pure client: products (list/create), accounts index (member names resolved by a **client-side join** of `savings.listAccounts()` + `members.list()`), open account, account detail (balance + transactions), deposit (direct 201) + withdraw (maker-checker 202). GL-account selects come from `ledger.listAccounts()`.
- Member detail gains a **Savings accounts** section linking to each account + scoped open-account.

## Notable points
- Withdraw is **maker-checker** (202 → creates a tenant-scoped approval). Approving needs the **tenant approvals inbox** (a later Phase-3 module); this only *creates* the approval.
- Savings accounts have **no status field** — no StatusBadge.
- No `<AuditBar>` on tenant records; tenant-auth gating only.

## Test plan
- Backend: `pytest tests/modules/savings/` green; ruff + mypy clean.
- Packages/portal: `@sacco/schemas`, `@sacco/api-client`, `@sacco/portal` test/typecheck/lint green.

> CI note: Lint fails environmentally on this repo (runner-queue issue); reproduced clean locally.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** backend list → T1; read types + resource → T2; products → T3; accounts index + open → T4; detail + deposit/withdraw → T5; member section → T6; verify/PR → T7.
- **Type consistency:** `SavingsAccountOut`/`WithBalanceOut`/`SavingsProductOut`/`SavingsTransactionOut` (T2) consumed by T3–T6. `AccountRow` (T4) is a page-built view-model, not the API type (the member-name join lives on the page, not the table). `idempotency_key` fresh-per-instance on deposit/withdraw (contract L).
- **Verify-at-execution:** `<PercentageInput>`/`<MoneyInput>` prop shape (check an existing consumer — likely `value`/`onValueChange`/`onBlur`/`name`/`ref` like `<DateInput>`/`<MoneyInput>` in `InvoiceActions`/`AssignPlanForm`); `ledger.listAccounts` AccountOut fields (`id, code, name, account_type, ...`); Next 15 `searchParams`/`params` are Promises; `MakerCheckerConfirmDialog` props (open/onOpenChange/operationLabel/subjectLabel/busy/onConfirm) and that its dialog role is `dialog` (3a lesson — not `alertdialog`).
- **DB URL:** backend tests need `DATABASE_URL=...@localhost:5433/sacco_test` (Docker postgres-test), not the stale `.env` value.
