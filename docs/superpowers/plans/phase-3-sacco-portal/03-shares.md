# SACCO Admin Portal — Shares Module (Phase 3c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Environment note (2026-06-21):** background subagents can't get Edit approval; run **inline**. **Confirm typecheck PASSES before committing** (SP20 lesson). Backend tests need the Docker Postgres — the `postgres-test` container is on **:5433** with creds **sacco/sacco** (NOT `postgres/postgres`, NOT the stale `.env` :5532/:5533). Export the right URL before running pytest:
> `export DATABASE_URL="postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test"`

**Goal:** The third SACCO-operator module — Shares products, accounts (with a new richer list endpoint), purchases, and maker-checker redemptions — as a near-pure client plus one backend list route, an api-client resource, and a schemas entry (the latter two do not exist yet for shares).

**Architecture:** One backend addition (`GET /shares/accounts?member_id=` → richer `ShareAccountListItemOut` with `product_name`/`par_value`/computed holdings), then a new `@sacco/schemas` `shares.ts`, a new `@sacco/api-client` `resources/shares.ts`, then tenant-authed portal screens under `app/(tenant-authed)/shares/*` server-fetched via `getTenantPageContext()`. In-memory `<DataTable>`s, RHF/Zod forms, GL-account `<Select>`s from `ledger.listAccounts()`, purchase (direct 201) and redeem (maker-checker 202). The accounts index joins the richer list with `members.list()` client-side for member display names. Clones the 3b tenant-operator pattern.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async (backend route/service + pytest); Next.js 15, React 19, TS strict, `@sacco/ui`, `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library.

## Global Constraints

- **Branch:** `feat/sacco-portal/03-shares`, **stacked on `feat/sacco-portal/02-savings`** (both touch `members/[id]/page.tsx`; 3b PR #40 not yet merged). PR base = `feat/sacco-portal/02-savings`.
- **One new backend endpoint only** (`GET /shares/accounts`), explicitly approved (CLAUDE.md contract B "surface" path). It does not alter any existing endpoint or schema. Backend changes confined to `app/modules/shares/{schemas.py,service.py,api.py}` + `tests/modules/shares/`.
- **Shares module contracts still apply:** never write journals/balances directly (this route is read-only — fine); the shares module must NOT import the members model (CLAUDE.md rule 2) — member names resolved client-side.
- **No StatusBadge** (accounts have no status). **No `<AuditBar>`** (tenant records). Tenant-auth gating only via `getTenantPageContext()`.
- **Money** (`par_value`, transaction `amount`, `total_value`) renders via `<Money>`; **quantities** (`shares_held`, `minimum_shares`, `maximum_shares`, `quantity`) via `<Count value={number}>`. Money/quantity on the wire are JSON strings for Decimals; integer counts are `number` in read types.
- **Quantities sent as strings** on input (validated integer-strings); Pydantic lax-coerces `"5" → 5`. `idempotency_key` is a fresh UUID per form instance (contract L).
- **DRY/YAGNI/TDD, frequent commits.** Confirm typecheck passes before each commit.

---

## Task 1: Backend — `GET /shares/accounts` (schema + service + route + tests)

**Files:**
- Modify: `app/modules/shares/schemas.py` (add `ShareAccountListItemOut`)
- Modify: `app/modules/shares/service.py` (add `ShareAccountListItem` dataclass + `list_accounts` after `get_balance`, ~line 138; add imports `case`, `dataclass`)
- Modify: `app/modules/shares/api.py` (add route after `open_account`, before `get_account`; import the new schema)
- Test: `tests/modules/shares/test_service.py`, `tests/modules/shares/test_api.py`

**Interfaces:**
- Produces: `ShareService.list_accounts(*, member_id: uuid.UUID | None = None) -> list[ShareAccountListItem]`; `ShareAccountListItem` dataclass with `id, member_id, share_product_id, product_name, par_value, shares_held, total_value`; route `GET /shares/accounts` → `list[ShareAccountListItemOut]`.

- [ ] **Step 1: Service test (failing)** — append to `test_service.py` (uses existing `_setup_gl_accounts`/`_setup_product`/`_setup_member` + `_cleanup` helpers):

```python
async def test_list_accounts_returns_holdings_and_filters_by_member(test_engine):
    _, equity_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, equity_id)
    member_a = await _setup_member(test_engine)
    member_b = await _setup_member(test_engine)

    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        acct_a = await svc.open_account(member_id=member_a, share_product_id=product_id)
        await svc.open_account(member_id=member_b, share_product_id=product_id)
        await svc.purchase_shares(
            share_account_id=acct_a.id,
            quantity=5,
            payment_account_id=_,
            posted_by=uuid.uuid4(),
            idempotency_key=uuid.uuid4().hex,
        )
        await session.commit()

        all_accounts = await svc.list_accounts()
        assert len(all_accounts) >= 2

        only_a = await svc.list_accounts(member_id=member_a)
        assert len(only_a) == 1
        row = only_a[0]
        assert row.member_id == member_a
        assert row.product_name == "Ordinary Shares"
        assert row.shares_held == 5
        assert row.total_value == Decimal("5000.00")  # 5 × 1000.00 par
    finally:
        await session.close()
        await _cleanup(test_engine)
```

> `_` is the cash account id from `_setup_gl_accounts` (it returns `(cash_id, equity_id)`); bind it: change the first line to `cash_id, equity_id = await _setup_gl_accounts(test_engine)` and pass `payment_account_id=cash_id`.

Run:
```bash
export DATABASE_URL="postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test"
pytest tests/modules/shares/test_service.py::test_list_accounts_returns_holdings_and_filters_by_member -v
```
Expected: FAIL (`AttributeError: 'ShareService' object has no attribute 'list_accounts'`).

- [ ] **Step 2: Implement the dataclass + `list_accounts`** in `service.py`.

Add to imports (line 8): `from sqlalchemy import case, func, select` and at top `from dataclasses import dataclass`.

After the `get_balance` method (and before `# ── Transactions`), add:

```python
@dataclass(frozen=True)
class ShareAccountListItem:
    id: uuid.UUID
    member_id: uuid.UUID
    share_product_id: uuid.UUID
    product_name: str
    par_value: Decimal
    shares_held: int
    total_value: Decimal
```

> Place the dataclass at module top-level (after `_log`), not nested in the class.

Add the method (after `get_balance`):

```python
    async def list_accounts(
        self, *, member_id: uuid.UUID | None = None
    ) -> list[ShareAccountListItem]:
        net = func.coalesce(
            func.sum(
                case(
                    (
                        ShareTransaction.transaction_type == "purchase",
                        ShareTransaction.quantity,
                    ),
                    (
                        ShareTransaction.transaction_type == "redemption",
                        -ShareTransaction.quantity,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("shares_held")
        tx = (
            select(ShareTransaction.share_account_id.label("acct_id"), net)
            .group_by(ShareTransaction.share_account_id)
            .subquery()
        )
        q = (
            select(
                MemberShareAccount.id,
                MemberShareAccount.member_id,
                MemberShareAccount.share_product_id,
                ShareProduct.name.label("product_name"),
                ShareProduct.par_value,
                func.coalesce(tx.c.shares_held, 0).label("shares_held"),
            )
            .join(ShareProduct, ShareProduct.id == MemberShareAccount.share_product_id)
            .outerjoin(tx, tx.c.acct_id == MemberShareAccount.id)
            .order_by(ShareProduct.name, MemberShareAccount.id)
        )
        if member_id is not None:
            q = q.where(MemberShareAccount.member_id == member_id)
        rows = (await self._session.execute(q)).all()
        return [
            ShareAccountListItem(
                id=r.id,
                member_id=r.member_id,
                share_product_id=r.share_product_id,
                product_name=r.product_name,
                par_value=r.par_value,
                shares_held=int(r.shares_held),
                total_value=Decimal(int(r.shares_held)) * r.par_value,
            )
            for r in rows
        ]
```

- [ ] **Step 3: Run service test → PASS.**

- [ ] **Step 4: Add the Pydantic schema** to `schemas.py` (after `ShareAccountWithBalanceOut`):

```python
class ShareAccountListItemOut(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    share_product_id: uuid.UUID
    product_name: str
    par_value: Decimal
    shares_held: int
    total_value: Decimal

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: API test (failing)** — append to `test_api.py` (uses existing `_create_gl_account`/`_create_product`/`_create_member`/`_open_account` helpers):

```python
async def test_list_accounts_returns_200_and_filters(client):
    equity_id = await _create_gl_account(
        client, f"3-{uuid.uuid4().hex[:6]}", "Share Capital", "equity"
    )
    product_id = await _create_product(client, equity_id)
    member_a = await _create_member(client)
    member_b = await _create_member(client)
    await _open_account(client, product_id, member_a)
    await _open_account(client, product_id, member_b)

    resp = await client.get("/shares/accounts", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 2
    assert "product_name" in resp.json()[0]
    assert "shares_held" in resp.json()[0]

    resp_a = await client.get(
        "/shares/accounts", params={"member_id": member_a}, headers=HEADERS
    )
    assert resp_a.status_code == 200, resp_a.text
    data = resp_a.json()
    assert len(data) == 1
    assert data[0]["member_id"] == member_a
    assert data[0]["product_name"] == "Ordinary Shares"


async def test_list_accounts_requires_tenant(client):
    resp = await client.get("/shares/accounts")  # no X-Tenant-Slug
    assert resp.status_code in (401, 403, 422), resp.text
```

Run:
```bash
pytest tests/modules/shares/test_api.py::test_list_accounts_returns_200_and_filters tests/modules/shares/test_api.py::test_list_accounts_requires_tenant -v
```
Expected: FAIL (404 — route not defined).

- [ ] **Step 6: Implement the route** in `api.py`. Add `ShareAccountListItemOut` to the schema import block, then insert between `open_account` and `get_account`:

```python
@router.get("/accounts", response_model=list[ShareAccountListItemOut])
async def list_accounts(
    session: Session,
    user: CurrentTenantUser,
    member_id: uuid.UUID | None = None,
) -> list[ShareAccountListItemOut]:
    svc = ShareService(session)
    items = await svc.list_accounts(member_id=member_id)
    return [ShareAccountListItemOut.model_validate(i) for i in items]
```

- [ ] **Step 7: Run both API tests → PASS. Then ruff + mypy + full shares suite.**

```bash
pytest tests/modules/shares/ -q
ruff check app/modules/shares/ tests/modules/shares/
mypy app/modules/shares/
```

- [ ] **Step 8: Commit.**

```bash
git add app/modules/shares/schemas.py app/modules/shares/service.py app/modules/shares/api.py tests/modules/shares/test_service.py tests/modules/shares/test_api.py
git commit -m "feat(shares): list accounts endpoint with holdings (member filter)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `@sacco/schemas` — `shares.ts` (input schemas + read types) + `intString` helper

**Files:**
- Modify: `admin/packages/schemas/src/common.ts` (add `intString` helper)
- Create: `admin/packages/schemas/src/shares.ts`
- Modify: `admin/packages/schemas/src/index.ts` (add `export * from "./shares";`)
- Test: `admin/packages/schemas/src/__tests__/shares.test.ts`

**Interfaces:**
- Produces: `shareProductSchema`, `openShareAccountSchema`, `purchaseSharesSchema`, `redeemSharesSchema` (+ inferred `*Input`); read types `ShareProductOut`, `ShareAccountOut`, `ShareAccountWithBalanceOut`, `ShareTransactionOut`, `ShareAccountListItemOut`; `intString(opts?)` in common.

- [ ] **Step 1: Add `intString` to `common.ts`** (after `percentageString`):

```ts
/** Whole-number string (integer-as-string on the wire; Pydantic lax-coerces). */
export const intString = (opts?: { min?: number }) => {
  let schema: z.ZodType<string> = z
    .string()
    .trim()
    .regex(/^\d+$/, "Must be a whole number");
  if (opts?.min !== undefined) {
    const m = opts.min;
    schema = schema.refine((v) => Number.parseInt(v, 10) >= m, `Must be ≥ ${m}`);
  }
  return schema;
};
```

- [ ] **Step 2: Failing test** — create `src/__tests__/shares.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  shareProductSchema,
  purchaseSharesSchema,
  type ShareAccountListItemOut,
} from "../shares";

describe("shares schemas + read types", () => {
  it("product schema rejects a blank name and non-positive par value", () => {
    expect(
      shareProductSchema.safeParse({
        name: "",
        par_value: "1000",
        minimum_shares: "1",
        share_capital_account_id: "11111111-1111-1111-1111-111111111111",
      }).success,
    ).toBe(false);
  });
  it("purchase schema rejects a zero quantity", () => {
    expect(
      purchaseSharesSchema.safeParse({
        quantity: "0",
        payment_account_id: "11111111-1111-1111-1111-111111111111",
        idempotency_key: "abcd1234efgh",
      }).success,
    ).toBe(false);
  });
  it("ShareAccountListItemOut is structurally usable", () => {
    const a: ShareAccountListItemOut = {
      id: "a1",
      member_id: "m1",
      share_product_id: "p1",
      product_name: "Ordinary Shares",
      par_value: "1000.00",
      shares_held: 5,
      total_value: "5000.00",
    };
    expect(a.shares_held).toBe(5);
  });
});
```

Run: `cd admin && pnpm --filter @sacco/schemas test -- shares` → FAIL.

- [ ] **Step 3: Create `src/shares.ts`:**

```ts
// admin/packages/schemas/src/shares.ts
import { z } from "zod";
import { idempotencyKey, intString, moneyString, uuid } from "./common";

export const openShareAccountSchema = z.object({
  member_id: uuid,
  share_product_id: uuid,
});

export const purchaseSharesSchema = z.object({
  quantity: intString({ min: 1 }),
  payment_account_id: uuid,
  idempotency_key: idempotencyKey,
});

export const redeemSharesSchema = z.object({
  quantity: intString({ min: 1 }),
  payment_account_id: uuid,
  reason: z.string().trim().max(280).optional().or(z.literal("")),
  idempotency_key: idempotencyKey,
});

export const shareProductSchema = z.object({
  name: z.string().trim().min(1).max(200),
  par_value: moneyString({ min: "0.01" }),
  minimum_shares: intString({ min: 1 }),
  maximum_shares: intString({ min: 1 }).optional().or(z.literal("")),
  share_capital_account_id: uuid,
});

export type OpenShareAccountInput = z.infer<typeof openShareAccountSchema>;
export type PurchaseSharesInput = z.infer<typeof purchaseSharesSchema>;
export type RedeemSharesInput = z.infer<typeof redeemSharesSchema>;
export type ShareProductInput = z.infer<typeof shareProductSchema>;

// Mirror app/modules/shares/schemas.py. Decimals are JSON strings; counts are numbers.
export interface ShareProductOut {
  id: string;
  name: string;
  par_value: string;
  minimum_shares: number;
  maximum_shares: number | null;
  share_capital_account_id: string;
  is_active: boolean;
}

export interface ShareAccountOut {
  id: string;
  member_id: string;
  share_product_id: string;
}

export interface ShareAccountWithBalanceOut extends ShareAccountOut {
  shares_held: number;
  total_value: string;
}

export interface ShareTransactionOut {
  id: string;
  share_account_id: string;
  transaction_type: string;
  quantity: number;
  amount: string;
  journal_entry_id: string;
  posted_by: string;
}

export interface ShareAccountListItemOut {
  id: string;
  member_id: string;
  share_product_id: string;
  product_name: string;
  par_value: string;
  shares_held: number;
  total_value: string;
}
```

- [ ] **Step 4: Export** from `src/index.ts` — add `export * from "./shares";`.

- [ ] **Step 5: Run test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/schemas test -- shares && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
git add admin/packages/schemas/src/common.ts admin/packages/schemas/src/shares.ts admin/packages/schemas/src/index.ts admin/packages/schemas/src/__tests__/shares.test.ts
git commit -m "feat(portal): shares schemas (input + read types) + intString helper

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `@sacco/api-client` — `resources/shares.ts`

**Files:**
- Create: `admin/packages/api-client/src/resources/shares.ts`
- Modify: `admin/packages/api-client/src/resources/index.ts` (import + register)

**Interfaces:**
- Produces: `resources.shares.{listProducts, createProduct, getProduct, listAccounts, openAccount, getAccount, listTransactions, purchase, redeem}` — each returns the `{ data?, error? }` shape after the `as never` wart cast at call sites.

- [ ] **Step 1: Create `src/resources/shares.ts`** (mirror `resources/savings.ts`):

```ts
import type { FetchClient } from "../client";

export function shares(api: FetchClient) {
  return {
    listProducts: (query?: Record<string, unknown>) =>
      api.GET("/shares/products" as never, { params: { query } } as never),
    createProduct: (body: Record<string, unknown>) =>
      api.POST("/shares/products" as never, { body } as never),
    getProduct: (id: string) =>
      api.GET("/shares/products/{product_id}" as never, {
        params: { path: { product_id: id } },
      } as never),
    listAccounts: (query?: Record<string, unknown>) =>
      api.GET("/shares/accounts" as never, { params: { query } } as never),
    openAccount: (body: Record<string, unknown>) =>
      api.POST("/shares/accounts" as never, { body } as never),
    getAccount: (id: string) =>
      api.GET("/shares/accounts/{account_id}" as never, {
        params: { path: { account_id: id } },
      } as never),
    listTransactions: (id: string, query?: Record<string, unknown>) =>
      api.GET("/shares/accounts/{account_id}/transactions" as never, {
        params: { path: { account_id: id }, query },
      } as never),
    purchase: (id: string, body: Record<string, unknown>) =>
      api.POST("/shares/accounts/{account_id}/purchase" as never, {
        params: { path: { account_id: id } },
        body,
      } as never),
    redeem: (id: string, body: Record<string, unknown>) =>
      api.POST("/shares/accounts/{account_id}/redeem" as never, {
        params: { path: { account_id: id } },
        body,
      } as never),
  } as const;
}
```

- [ ] **Step 2: Register in `resources/index.ts`** — add `import { shares } from "./shares";` (after the `savings` import) and `shares: shares(api),` (after the `savings:` line) in `buildResources`.

- [ ] **Step 3: Typecheck; commit.**

```bash
pnpm --filter @sacco/api-client typecheck
git add admin/packages/api-client/src/resources/shares.ts admin/packages/api-client/src/resources/index.ts
git commit -m "feat(portal): shares api-client resource

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Products — `<ProductsTable>` + `/shares` + `<CreateProductForm>` + `/shares/products/new`

> Clone the 3b savings equivalents: `app/(tenant-authed)/savings/page.tsx`, `savings/_components/ProductsTable.tsx`, `savings/products/new/page.tsx`, `savings/products/new/_components/CreateProductForm.tsx`, and the tests `apps/portal/src/__tests__/tenant-savings/{ProductsTable,CreateProductForm}.test.tsx`. Apply the shares deltas below.

**Files:**
- Create: `app/(tenant-authed)/shares/_components/ProductsTable.tsx`, `shares/page.tsx`
- Create: `app/(tenant-authed)/shares/products/new/_components/CreateProductForm.tsx`, `shares/products/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-shares/{ProductsTable,CreateProductForm}.test.tsx`

**Interfaces:**
- Consumes: `ShareProductOut`, `shareProductSchema`/`ShareProductInput`, `resources.shares.{listProducts,createProduct}`, `resources.ledger.listAccounts`.

- [ ] **Step 1: `ProductsTable` test (failing)** — clone the savings `ProductsTable.test.tsx`. `TData = ShareProductOut`. Assert a row renders the name + par value (e.g. "UGX 1,000") + min shares "1"; assert the empty state "No share products yet". Mock `useTableUrlState`; wrap in `<TenantCurrencyProvider>`.

- [ ] **Step 2: Implement `ProductsTable.tsx`** — clone savings `ProductsTable` structure (`"use client"`, in-memory filter/sort/paginate, `useTableUrlState`). `id="share-products"`, `TData = ShareProductOut`. Columns: **Name**; **Par value** → `<Money amount={row.original.par_value} />`; **Min shares** → `<Count value={row.original.minimum_shares} />`; **Max shares** → `row.original.maximum_shares == null ? "—" : <Count value={row.original.maximum_shares} />`; **Active** → `row.original.is_active ? "Yes" : "No"`. Empty `{ title: "No share products yet", description: "Create a product to start opening accounts." }`. `state={{ totalRows: filtered.length, isError: false, isPermissionDenied: false }}`. Import `Count`, `Money` from `@sacco/ui`.

- [ ] **Step 3: Implement `shares/page.tsx`** (server) — clone savings `page.tsx`: `getTenantPageContext()`, `resources.shares.listProducts({})` cast `{ data?: ShareProductOut[] }`, `<h1>Share products</h1>`, a **Create product** `<Button asChild><Link href="/shares/products/new">`, `<ProductsTable rows={data ?? []} />`. `export const metadata = { title: "Shares" }`.

- [ ] **Step 4: `CreateProductForm` test (failing)** — clone savings `CreateProductForm.test.tsx`. Mock `next/navigation` push + `useAuth` (`resources.shares.createProduct`). Render in `<QueryClientProvider>`. Pass `glAccounts={[{id:"g1",code:"3000",name:"Share Capital",account_type:"equity"}]}`. Fill name, par value, min shares, pick the GL account; submit; assert `createProduct` called with `{ name, par_value, minimum_shares, share_capital_account_id }` (no `maximum_shares` key when blank) and `push("/shares")`. Assert a blank name blocks submit.

- [ ] **Step 5: Implement `CreateProductForm.tsx`** (client) — clone savings `CreateProductForm` wiring (RHF + `zodResolver(shareProductSchema)`, `useTypedMutation` → `resources.shares.createProduct`). Props `{ glAccounts: { id: string; code: string; name: string; account_type: string }[] }`. Fields via `<FormField>`: name (`<Input>`); par_value (`<MoneyInput>`); minimum_shares (`<Input inputMode="numeric">`); maximum_shares (`<Input inputMode="numeric">`, optional); share_capital_account_id (`<Select>` mapping `glAccounts` → `<SelectItem value={a.id}>{a.code} — {a.name}</SelectItem>`). `defaultValues: { name: "", par_value: "", minimum_shares: "1", maximum_shares: "", share_capital_account_id: "" }`. **In onSubmit, strip the empty optional:** `const body = { ...values }; if (!body.maximum_shares) delete body.maximum_shares;` then `mutate(body)`. onSuccess `toast.success("Product created")` + `router.push("/shares")`; onError `apiErrorMessage`. Cancel → `/shares`.

- [ ] **Step 6: Implement `products/new/page.tsx`** (server) — `getTenantPageContext()`, fetch `resources.ledger.listAccounts({})` cast `{ data?: { id:string; code:string; name:string; account_type:string }[] }`, `<h1>Create share product</h1>`, `<CreateProductForm glAccounts={accounts ?? []} />`.

- [ ] **Step 7: Run the two tests + portal typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-shares/ProductsTable tenant-shares/CreateProductForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/shares/page.tsx" "admin/apps/portal/app/(tenant-authed)/shares/_components/ProductsTable.tsx" "admin/apps/portal/app/(tenant-authed)/shares/products/" admin/apps/portal/src/__tests__/tenant-shares/ProductsTable.test.tsx admin/apps/portal/src/__tests__/tenant-shares/CreateProductForm.test.tsx
git commit -m "feat(portal): SACCO shares products list + create

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Accounts index + open — `<AccountsTable>` + `/shares/accounts` + `<OpenAccountForm>` + `/shares/accounts/new`

> Clone the 3b savings equivalents under `savings/accounts/`. Apply the shares deltas below. Key difference: the page joins the **richer** list (which already carries `product_name`) with `members.list()` for the member label only.

**Files:**
- Create: `app/(tenant-authed)/shares/accounts/_components/AccountsTable.tsx`, `shares/accounts/page.tsx`
- Create: `app/(tenant-authed)/shares/accounts/new/_components/OpenAccountForm.tsx`, `shares/accounts/new/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-shares/{AccountsTable,OpenAccountForm}.test.tsx`

**Interfaces:**
- Consumes: `ShareAccountListItemOut`, `MemberOut` (from `@sacco/schemas`), `openShareAccountSchema`/`OpenShareAccountInput`, `resources.shares.{listAccounts,openAccount,listProducts}`, `resources.members.list`.
- Produces: exported `AccountRow` interface `{ id: string; member_label: string; product_name: string; shares_held: number; total_value: string }`.

- [ ] **Step 1: `AccountsTable` test (failing)** — clone savings `AccountsTable.test.tsx`. `TData = AccountRow`. Assert a row links `member_label` to `/shares/accounts/a1`, renders `product_name`, shares (`<Count>`), value (`<Money>`); empty state "No share accounts yet".

- [ ] **Step 2: Implement `AccountsTable.tsx`** — clone savings `AccountsTable`. Export `AccountRow` (shape above). `id="share-accounts"`. Columns: **Member** → `<Link href={\`/shares/accounts/${row.original.id}\`}>{row.original.member_label}</Link>`; **Product** (`product_name`); **Shares** → `<Count value={row.original.shares_held} />`; **Value** → `<Money amount={row.original.total_value} />`. Empty `{ title: "No share accounts yet", description: "Open an account from a member or here." }`.

- [ ] **Step 3: Implement `shares/accounts/page.tsx`** (server) — the **client-side member join**:

```tsx
const { resources } = await getTenantPageContext();
const [{ data: accounts }, { data: members }] = await Promise.all([
  resources.shares.listAccounts({}) as Promise<{ data?: ShareAccountListItemOut[]; error?: unknown }>,
  resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
]);
const byId = new Map((members ?? []).map((m) => [m.id, m]));
const rows: AccountRow[] = (accounts ?? []).map((a) => {
  const m = byId.get(a.member_id);
  return {
    id: a.id,
    member_label: m ? `${m.full_name} (${m.member_number})` : a.member_id,
    product_name: a.product_name,
    shares_held: a.shares_held,
    total_value: a.total_value,
  };
});
```
Header **Open account** → `/shares/accounts/new`. `<h1>Share accounts</h1>`. `<AccountsTable rows={rows} />`. `export const metadata = { title: "Share accounts" }`.

> Verify `MemberOut`'s field names (`full_name`, `member_number`) against `@sacco/schemas` (3a added it) before relying on them.

- [ ] **Step 4: `OpenAccountForm` test (failing)** — clone savings `OpenAccountForm.test.tsx`. Mock push + `useAuth` (`resources.shares.openAccount`). Props `members` + `products` arrays + optional `defaultMemberId`. Pick member + product, submit → `openAccount({ member_id, share_product_id })` → `push("/shares/accounts/a9")` on `{ data: { id: "a9" } }`. Assert `defaultMemberId` pre-selects.

- [ ] **Step 5: Implement `OpenAccountForm.tsx`** (client) — clone savings `OpenAccountForm`. RHF + `zodResolver(openShareAccountSchema)`, `defaultValues: { member_id: defaultMemberId ?? "", share_product_id: "" }`. Props `{ members: {id:string;full_name:string;member_number:string}[]; products: {id:string;name:string}[]; defaultMemberId?: string }`. Two `<Select>`s via `<FormField>` (member → `{full_name} ({member_number})`; product → `{name}`). `useTypedMutation` → `resources.shares.openAccount(values)` cast `{ data?: ShareAccountOut }`; onSuccess `toast.success("Account opened")` + `router.push(\`/shares/accounts/${data.id}\`)`; onError `apiErrorMessage` (covers 409 "already exists"). Cancel → `/shares/accounts`.

- [ ] **Step 6: Implement `accounts/new/page.tsx`** (server) — reads `searchParams` (Next 15: `const sp = await searchParams;`, signature `{ searchParams: Promise<{ member_id?: string }> }`); fetches `resources.members.list({})` + `resources.shares.listProducts({})`; passes `members`, `products`, `defaultMemberId={sp.member_id}`. `<h1>Open share account</h1>`.

- [ ] **Step 7: Run tests + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-shares/AccountsTable tenant-shares/OpenAccountForm
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/shares/accounts/page.tsx" "admin/apps/portal/app/(tenant-authed)/shares/accounts/_components/AccountsTable.tsx" "admin/apps/portal/app/(tenant-authed)/shares/accounts/new/" admin/apps/portal/src/__tests__/tenant-shares/AccountsTable.test.tsx admin/apps/portal/src/__tests__/tenant-shares/OpenAccountForm.test.tsx
git commit -m "feat(portal): SACCO shares accounts index + open account

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Account detail + purchase/redeem — `[id]/page.tsx` + `<TransactionsTable>` + `<AccountActions>`

> Clone the 3b savings `accounts/[id]/page.tsx`, `_components/TransactionsTable.tsx`, `_components/AccountActions.tsx`, and `AccountActions.test.tsx`. Apply the shares deltas below.

**Files:**
- Create: `app/(tenant-authed)/shares/accounts/[id]/page.tsx`, `_components/TransactionsTable.tsx`, `_components/AccountActions.tsx`
- Test: `apps/portal/src/__tests__/tenant-shares/AccountActions.test.tsx`

**Interfaces:**
- Consumes: `ShareAccountWithBalanceOut`, `ShareProductOut`, `ShareTransactionOut`, `purchaseSharesSchema`/`PurchaseSharesInput`, `redeemSharesSchema`/`RedeemSharesInput`, `resources.shares.{getAccount,getProduct,listTransactions,purchase,redeem}`, `resources.ledger.listAccounts`.

- [ ] **Step 1: `TransactionsTable.tsx`** (client) — clone savings `TransactionsTable`. `id="share-transactions"`, `TData = ShareTransactionOut`. Columns: **Type** (`transaction_type`); **Quantity** → `<Count value={row.original.quantity} />`; **Amount** → `<Money amount={row.original.amount} />`. Empty `{ title: "No transactions yet", description: "Purchases and redemptions appear here." }`.

- [ ] **Step 2: `[id]/page.tsx`** (server) — fetch in sequence/parallel: `resources.shares.getAccount(id)` cast `{ data?: ShareAccountWithBalanceOut }` (`notFound()` if absent), then `resources.shares.getProduct(account.share_product_id)` cast `{ data?: ShareProductOut }`, `resources.shares.listTransactions(id)` cast `{ data?: ShareTransactionOut[] }`, and `resources.ledger.listAccounts({})` cast `{ data?: GlAccountOption[] }`. Header: `<h1>{product?.name ?? "Share account"}</h1>` + `<AccountActions accountId={id} glAccounts={accounts ?? []} />`. A summary `<Card>`: **Par value** `<Money amount={product.par_value} />`, **Shares held** `<Count value={account.shares_held} />` (emphasised), **Total value** `<Money amount={account.total_value} />` (emphasised). Then `<TransactionsTable rows={txns ?? []} />`. No `<AuditBar>`.

> `getAccount` must resolve before `getProduct` (product id comes from it). Run `listTransactions` + `ledger.listAccounts` in the same `Promise.all` as `getProduct`.

- [ ] **Step 3: `AccountActions` test (failing)** — clone savings `AccountActions.test.tsx`. Mock `next/navigation` (`refresh`), `useAuth` (`resources.shares.{purchase,redeem}`). Props `accountId`, `glAccounts`. Render in `<QueryClientProvider>` + `<TenantCurrencyProvider>` + `<Toaster>`.
  - **Purchase:** click "Purchase" → fill quantity, pick GL account → submit → `purchase("a1", { quantity, payment_account_id, idempotency_key })` called; toast "Shares purchased". (No maker-checker dialog.)
  - **Redeem:** click "Redeem" → fill quantity + GL → submit opens `<MakerCheckerConfirmDialog>`; assert the locked copy "create an approval request, not execute" + the "Create Approval Request" button; confirm → `redeem("a1", {...})` called; toast "Redemption requested — pending approval".

- [ ] **Step 4: Implement `AccountActions.tsx`** (client) — clone savings `AccountActions`. Props `{ accountId: string; glAccounts: GlAccountOption[] }` (reuse the exported `GlAccountOption` interface shape `{ id; code; name; account_type }`).
  - Two RHF forms: purchase (`zodResolver(purchaseSharesSchema)`, `defaultValues: { quantity: "", payment_account_id: "", idempotency_key: <fresh uuid via useState> }`) and redeem (`zodResolver(redeemSharesSchema)`, `defaultValues: { quantity: "", payment_account_id: "", reason: "", idempotency_key: <fresh uuid> }`).
  - Fields via `<FormField>`: quantity (`<Input inputMode="numeric">`), payment_account_id (`<Select>` from `glAccounts` → `{code} — {name}`), reason on redeem (`<Textarea>`).
  - **Purchase mutation** → `resources.shares.purchase(accountId, values)` cast `{ data?, error? }`; onSuccess close dialog, `toast.success("Shares purchased")`, `router.refresh()`. **Direct** — submit calls `mutate` directly (no confirm dialog).
  - **Redeem**: the form submit stashes `pendingRedeem` + opens `<MakerCheckerConfirmDialog open operationLabel="share redemption" subjectLabel={\`${quantity} shares\`}>`; `onConfirm` → `resources.shares.redeem(accountId, pending)` (202). onSuccess `toast.success("Redemption requested — pending approval")`, `router.refresh()`.

> Verify `MakerCheckerConfirmDialog` props (`open`/`onOpenChange`/`operationLabel`/`subjectLabel`/`busy`/`onConfirm`) against the savings `AccountActions` usage — it is the proven reference.

- [ ] **Step 5: Run test + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-shares/AccountActions
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/shares/accounts/[id]/" admin/apps/portal/src/__tests__/tenant-shares/AccountActions.test.tsx
git commit -m "feat(portal): SACCO shares account detail + purchase/redeem

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Member-detail shares section

> Clone the 3b `MemberSavingsSection.tsx` + its test, and add a second section to the member detail page (which already has the savings section from 3b).

**Files:**
- Create: `app/(tenant-authed)/members/[id]/_components/MemberSharesSection.tsx`
- Modify: `app/(tenant-authed)/members/[id]/page.tsx`
- Test: `apps/portal/src/__tests__/tenant-shares/MemberSharesSection.test.tsx`

**Interfaces:**
- Consumes: `ShareAccountListItemOut`, `resources.shares.listAccounts`.

- [ ] **Step 1: Test (failing)** — clone `MemberSavingsSection.test.tsx`. `MemberSharesSection` is a presentational server component taking `{ memberId: string; accounts: ShareAccountListItemOut[] }`. Assert: an account row links to `/shares/accounts/{id}` and shows the product name + shares held; the **Open account** link points to `/shares/accounts/new?member_id={memberId}`; empty state "No share accounts" when `accounts=[]`.

- [ ] **Step 2: Implement `MemberSharesSection.tsx`** — clone `MemberSavingsSection`. A `<Card>` titled "Share accounts". For each account: `product_name` + shares held `<Count value={a.shares_held} />` + a `<Link href={\`/shares/accounts/${a.id}\`}>View</Link>`. Header has `<Button asChild variant="secondary"><Link href={\`/shares/accounts/new?member_id=${memberId}\`}>Open account</Link></Button>`. Empty → "No share accounts." Server component — no `"use client"`.

- [ ] **Step 3: Modify `members/[id]/page.tsx`** — add `resources.shares.listAccounts({ member_id: id })` cast `{ data?: ShareAccountListItemOut[] }` to the existing `Promise.all` (which already fetches `members.get` + `savings.listAccounts`). Render `<MemberSharesSection memberId={data.id} accounts={shareAccounts ?? []} />` below the existing `<MemberSavingsSection>`.

- [ ] **Step 4: Run the section test + the existing 3a/3b member & savings tests (no regression) + typecheck + lint; commit.**

```bash
pnpm --filter @sacco/portal test -- tenant-members tenant-savings tenant-shares
pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
git add "admin/apps/portal/app/(tenant-authed)/members/[id]/" admin/apps/portal/src/__tests__/tenant-shares/MemberSharesSection.test.tsx
git commit -m "feat(portal): member-detail share accounts section

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Verification + PR

- [ ] **Step 1: Backend gate** (Docker DB up):
```bash
export DATABASE_URL="postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test"
pytest tests/modules/shares/ -q
ruff check app/modules/shares/ tests/modules/shares/ && mypy app/modules/shares/
```

- [ ] **Step 2: Packages + portal gate**:
```bash
cd admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test delta over the 199 (3b) baseline (+ ProductsTable, CreateProductForm, AccountsTable, OpenAccountForm, AccountActions, MemberSharesSection cases).

- [ ] **Step 3: Contract spot-checks**:
  - [ ] Backend diff confined to shares + tests: `git diff --name-only feat/sacco-portal/02-savings...HEAD | grep -E '^app/'` shows only `app/modules/shares/{schemas,service,api}.py`.
  - [ ] No migrations: `git diff --name-only feat/sacco-portal/02-savings...HEAD | grep -E '^alembic/'` empty.
  - [ ] No members-model import in the shares service: `rg "modules.members" app/modules/shares/` empty.
  - [ ] Portal changes under `admin/` + `docs/` only.
  - [ ] No StatusBadge for accounts: `rg 'entity="share_account"' "admin/apps/portal/app/(tenant-authed)/shares"` empty.

- [ ] **Step 4: Final holistic review** — products list/create (par value Money, shares Count); accounts index joins member names + shows holdings; open-account redirects to detail; detail shows shares held + total value + transactions; purchase is direct, redeem is maker-checker (locked copy, creates a tenant approval); member detail links to its share accounts. No AuditBar; tenant-auth gating only.

- [ ] **Step 5: Push + PR** (base is the stacked 3b branch):
```bash
git push -u origin feat/sacco-portal/03-shares
gh pr create --base feat/sacco-portal/02-savings --title "feat(portal): SACCO admin — Shares module (Phase 3c)" --body "$(cat <<'EOF'
## Summary
- Third **SACCO-operator** module: Shares products, accounts index, open-account, purchases, and maker-checker redemptions.
- **One backend addition** (explicitly approved): `GET /shares/accounts?member_id=` → a richer `ShareAccountListItemOut` (product_name, par_value, computed shares_held + total_value via one grouped query). The shares backend had no account-list endpoint. Schema + service + route + tests; no migration; existing endpoints untouched. Member names stay client-side (CLAUDE.md rule 2 — no members-model import).
- New `@sacco/schemas` `shares.ts` (input Zod schemas + read types) and `@sacco/api-client` `resources/shares.ts` — neither existed for shares before.
- Portal screens: products (list/create), accounts index (member names resolved by a client-side `members.list()` join), open account, account detail (shares held + total value + transactions), purchase (direct 201) + redeem (maker-checker 202). GL-account selects come from `ledger.listAccounts()`.
- Member detail gains a **Share accounts** section.

## Notable points
- Redeem is **maker-checker** (202 → creates a tenant-scoped approval). Approving needs the **tenant approvals inbox** (a later Phase-3 module); this only *creates* the approval.
- Shares accounts have **no status field** — no StatusBadge. Quantities render via `<Count>`, money via `<Money>`.
- No `<AuditBar>` on tenant records; tenant-auth gating only.
- **Stacked on PR #40 (3b savings)** — base will retarget to `main` once #40 merges.

## Test plan
- Backend: `pytest tests/modules/shares/` green; ruff + mypy clean.
- Packages/portal: `@sacco/schemas`, `@sacco/api-client`, `@sacco/portal` test/typecheck/lint green.

> CI note: Lint fails environmentally on this repo (runner-queue issue); reproduced clean locally.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** backend richer list → T1; schemas (input + read types) → T2; api-client resource → T3; products → T4; accounts index + open → T5; detail + purchase/redeem → T6; member section → T7; verify/PR → T8.
- **Type consistency:** `ShareProductOut`/`ShareAccountOut`/`ShareAccountWithBalanceOut`/`ShareTransactionOut`/`ShareAccountListItemOut` (T2) consumed by T4–T7. `AccountRow` (T5) is a page-built view-model (member-label join lives on the page). `shares_held`/`minimum_shares`/`maximum_shares` are `number` (→ `<Count value>`); `par_value`/`amount`/`total_value` are `string` (→ `<Money amount>`). `idempotency_key` fresh-per-instance on purchase/redeem (contract L).
- **Verify-at-execution:** Pydantic lax-coerces integer-strings (`"5" → 5`) — confirmed default (non-strict) BaseModel; `<Count>` takes `value: number` (confirmed); `MemberOut` field names `full_name`/`member_number` (from 3a); `MakerCheckerConfirmDialog` props + dialog role (proven in savings `AccountActions`); Next 15 `searchParams`/`params` are Promises.
- **DB URL:** backend tests need `DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test` (corrected from the stale `postgres/postgres` in earlier plans).
