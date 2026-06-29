# Member Self-Service — Increment 1: Loan Application Progress (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a logged-in member see their own loan applications and the progress of each (submitted → under review → approved/rejected → disbursed), read-only.

**Architecture:** Add a member-scoped read router in the credit module (`/member/loan-applications`) that reuses the existing `LoanApplicationService.list/get`, filtered to the current member with cross-member access returning 404. The member portal gains an "Applications" section on the Loans page (a `DataTable`) and an application detail route rendering a `Stepper` for progress. No writes, no new tables, no migration.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async (backend), pytest/httpx (backend tests), Next.js 15 App Router + React 19 + `@sacco/ui` (portal), vitest + Testing Library (portal tests).

This is increment 1 of 4 in the member self-service phase (spec:
`docs/superpowers/specs/2026-06-29-member-self-service-design.md`). Increments 2–4
(loan apply, KYC, statement) are planned separately.

## Global Constraints

- Member endpoints are gated by `CurrentMember` (from `app.modules.iam.dependencies`); route handlers import `CurrentMember`, never the underlying function.
- Member endpoints never accept a client-supplied `member_id`; they scope to `current_member.id`. Cross-member access returns **404**, never 403.
- Member access/refresh tokens use `aud="member:<slug>"`. Member-scoped reads run under the subscription gate via `get_tenant_session`.
- Members are read-only in this increment — GET only. No mutations.
- Backend: all DB access is async; Pydantic schemas in `schemas.py`, routers in `api.py`. ruff + mypy (strict) must stay clean.
- Portal: all list views use `<DataTable>` from `@sacco/ui` with `useTableUrlState`; statuses render via `<StatusBadge entity status />`; money via `<Money>`. Server components fetch via the typed client; no client-side fetching for initial render.
- Every `TData` row type extends `{ id: string }`.

---

### Task 1: Member loan-applications read endpoints (backend)

**Files:**
- Modify: `app/modules/credit/api.py` (add a second member router + two handlers + a 404 helper)
- Modify: `app/main.py` (mount the new router)
- Test: `tests/modules/credit/test_member_applications_api.py` (create)

**Interfaces:**
- Consumes: `LoanApplicationService(session).list(member_id=..., status=...) -> list[LoanApplication]`, `LoanApplicationService(session).get(application_id=...) -> LoanApplication` (raises `ValueError` when not found); `LoanApplicationOut` schema; `CurrentMember` dependency.
- Produces: `GET /member/loan-applications` → `list[LoanApplicationOut]`; `GET /member/loan-applications/{application_id}` → `LoanApplicationOut`. A module-level `member_app_router = APIRouter(prefix="/member/loan-applications", tags=["member-loans"])` exported from `app/modules/credit/api.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/credit/test_member_applications_api.py`. Reuse the exact fixture pattern from `tests/modules/credit/test_member_api.py` (the `client`, `_clean_tables`, `_seed_member` helpers), adding an application seeder.

```python
"""HTTP tests: member self-service loan-application read endpoints (stub auth)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from app.core.db import get_tenant_session
from app.main import app, lifespan
from app.modules.credit.models import LoanApplication, LoanProduct
from app.modules.members.models import Member

TEST_TENANT_SCHEMA = "tenant_test"
HEADERS = {"X-Tenant-Slug": "test-tenant"}


async def _make_tenant_session_override(engine: AsyncEngine):  # noqa: ANN202
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


@pytest.fixture
async def client(test_engine: AsyncEngine, tenant_actor_id: uuid.UUID):  # noqa: ANN201
    override = await _make_tenant_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = "test-tenant"
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


@pytest.fixture(autouse=True)
async def _clean_tables(test_engine: AsyncEngine):  # noqa: ANN201
    yield
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        for tbl in ("loan_applications", "loan_products", "members"):
            await session.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        await session.commit()


def _member_headers(member_id: str) -> dict[str, str]:
    return {**HEADERS, "X-Member-Actor-ID": member_id}


async def _seed_member(engine: AsyncEngine) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        m = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}",
            full_name="Applicant",
            date_of_birth=date(1990, 1, 1),
            gender="male",
            status="active",
            email=f"m-{uuid.uuid4().hex[:6]}@example.com",
            portal_enabled=True,
        )
        session.add(m)
        await session.commit()
        return m.id


async def _seed_application(
    engine: AsyncEngine, member_id: uuid.UUID, *, status: str = "submitted"
) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        product = LoanProduct(
            name="Standard Loan",
            interest_method="flat",
            annual_interest_rate=Decimal("12.00"),
            repayment_frequency="monthly",
            max_term_periods=24,
            min_amount=Decimal("100.00"),
            max_amount=Decimal("100000.00"),
            disbursement_destinations=["cash"],
            gl_principal_receivable_code="1300",
            gl_interest_receivable_code="1310",
            gl_interest_income_code="4100",
        )
        session.add(product)
        await session.flush()
        application = LoanApplication(
            loan_product_id=product.id,
            member_id=member_id,
            requested_amount=Decimal("1000.00"),
            requested_term_periods=12,
            disbursement_destination="cash",
            status=status,
            idempotency_key=uuid.uuid4().hex,
        )
        session.add(application)
        await session.commit()
        return application.id


async def test_lists_only_own_applications(client, test_engine: AsyncEngine) -> None:  # noqa: ANN001
    member_id = await _seed_member(test_engine)
    other_id = await _seed_member(test_engine)
    mine = await _seed_application(test_engine, member_id)
    theirs = await _seed_application(test_engine, other_id)

    resp = await client.get(
        "/member/loan-applications", headers=_member_headers(str(member_id))
    )
    assert resp.status_code == 200, resp.text
    ids = [a["id"] for a in resp.json()]
    assert str(mine) in ids
    assert str(theirs) not in ids


async def test_detail_returns_timeline_fields(client, test_engine: AsyncEngine) -> None:  # noqa: ANN001
    member_id = await _seed_member(test_engine)
    app_id = await _seed_application(test_engine, member_id, status="under_review")

    resp = await client.get(
        f"/member/loan-applications/{app_id}", headers=_member_headers(str(member_id))
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "under_review"
    # timeline fields are present (may be null) for the portal progress view
    for key in ("reviewed_at", "decided_at", "rejection_reason", "approved_amount"):
        assert key in body


async def test_cannot_read_other_members_application(
    client, test_engine: AsyncEngine
) -> None:  # noqa: ANN001
    member_id = await _seed_member(test_engine)
    other_id = await _seed_member(test_engine)
    other_app = await _seed_application(test_engine, other_id)

    resp = await client.get(
        f"/member/loan-applications/{other_app}", headers=_member_headers(str(member_id))
    )
    assert resp.status_code == 404, resp.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose exec api pytest tests/modules/credit/test_member_applications_api.py -v`
Expected: FAIL — `GET /member/loan-applications` returns 404 (route not mounted) so the list/detail assertions fail.

- [ ] **Step 3: Add the member application router and handlers**

In `app/modules/credit/api.py`, just after the existing `member_router` definition (around line 57), add a second router:

```python
# Member self-service loan applications (read-only; scoped to the current member).
member_app_router = APIRouter(prefix="/member/loan-applications", tags=["member-loans"])
```

Then add these handlers (place them next to the other `member_router` handlers, e.g. after `member_loan_statement`):

```python
async def _member_application_or_404(
    session: AsyncSession, application_id: uuid.UUID, member_id: uuid.UUID
):  # noqa: ANN202
    """Fetch an application and verify it belongs to *member_id*, else 404."""
    svc = LoanApplicationService(session)
    try:
        application = await svc.get(application_id=application_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Application not found") from exc
    if application.member_id != member_id:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@member_app_router.get("", response_model=list[LoanApplicationOut])
async def member_loan_applications(
    session: Session, member: CurrentMember
) -> list[LoanApplicationOut]:
    """List the current member's own loan applications."""
    svc = LoanApplicationService(session)
    applications = await svc.list(member_id=member.id, status=None)
    return [LoanApplicationOut.model_validate(a) for a in applications]


@member_app_router.get("/{application_id}", response_model=LoanApplicationOut)
async def member_loan_application_detail(
    application_id: uuid.UUID, session: Session, member: CurrentMember
) -> LoanApplicationOut:
    """Return one of the current member's own applications (404 if not theirs)."""
    application = await _member_application_or_404(session, application_id, member.id)
    return LoanApplicationOut.model_validate(application)
```

- [ ] **Step 4: Mount the router in the app**

In `app/main.py`, find where `member_router` from the credit module is included (search for `credit` imports / `include_router`). Add the new router alongside it.

```python
from app.modules.credit.api import member_app_router as credit_member_app_router
from app.modules.credit.api import member_router as credit_member_router
# ...
app.include_router(credit_member_router)
app.include_router(credit_member_app_router)
```

(Match the existing import/include style in `app/main.py` — if the credit member router is imported inline, mirror that.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose exec api pytest tests/modules/credit/test_member_applications_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Lint + type-check the backend**

Run: `docker compose exec api ruff check app/modules/credit/api.py app/main.py && docker compose exec api mypy app/modules/credit/api.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add app/modules/credit/api.py app/main.py tests/modules/credit/test_member_applications_api.py
git commit -m "feat(credit): member-scoped loan-application read endpoints"
```

---

### Task 2: Member api-client resources for loan applications (portal)

**Files:**
- Modify: `admin/packages/api-client/src/resources/member.ts` (add two methods)
- Modify: `admin/packages/api-client/src/query-keys.ts` (add keys)
- Test: `admin/packages/api-client/src/__tests__/member-resources.test.ts` (add cases)

**Interfaces:**
- Consumes: the `FetchClient` `api.GET` shape already used in `member.ts`.
- Produces: `member(api).listLoanApplications(query?)` → GET `/member/loan-applications`; `member(api).getLoanApplication(id)` → GET `/member/loan-applications/{application_id}`. `queryKeys.member.loanApplications()` and `queryKeys.member.loanApplication(id)`.

- [ ] **Step 1: Write the failing test**

In `admin/packages/api-client/src/__tests__/member-resources.test.ts`, add (mirror the existing `listSavings` test that asserts the path passed to a mocked `api.GET`):

```ts
it("listLoanApplications hits /member/loan-applications", () => {
  const api = { GET: vi.fn() } as never;
  member(api).listLoanApplications();
  expect((api as { GET: ReturnType<typeof vi.fn> }).GET).toHaveBeenCalledWith(
    "/member/loan-applications",
    expect.anything(),
  );
});

it("getLoanApplication hits /member/loan-applications/{application_id}", () => {
  const api = { GET: vi.fn() } as never;
  member(api).getLoanApplication("abc");
  expect((api as { GET: ReturnType<typeof vi.fn> }).GET).toHaveBeenCalledWith(
    "/member/loan-applications/{application_id}",
    expect.objectContaining({
      params: { path: { application_id: "abc" } },
    }),
  );
});
```

(If `member` / `vi` are not already imported in this file, add `import { member } from "../resources/member";` and `import { describe, expect, it, vi } from "vitest";` to match the file's existing imports.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/api-client exec vitest run src/__tests__/member-resources.test.ts`
Expected: FAIL — `member(api).listLoanApplications is not a function`.

- [ ] **Step 3: Add the resource methods**

In `admin/packages/api-client/src/resources/member.ts`, add inside the returned object (after `getLoanStatement`):

```ts
    listLoanApplications: (query?: Record<string, unknown>) =>
      api.GET("/member/loan-applications" as never, { params: { query } } as never),
    getLoanApplication: (applicationId: string) =>
      api.GET("/member/loan-applications/{application_id}" as never, {
        params: { path: { application_id: applicationId } },
      } as never),
```

- [ ] **Step 4: Add query keys**

In `admin/packages/api-client/src/query-keys.ts`, inside the `member` key group (next to `loans`), add:

```ts
    loanApplications: () => ["member", "loan-applications"] as const,
    loanApplication: (id: string) => ["member", "loan-applications", id] as const,
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/api-client exec vitest run src/__tests__/member-resources.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/api-client/src/resources/member.ts admin/packages/api-client/src/query-keys.ts admin/packages/api-client/src/__tests__/member-resources.test.ts
git commit -m "feat(api-client): member loan-application resources + query keys"
```

---

### Task 3: Applications table + Loans-page section (portal)

**Files:**
- Create: `admin/apps/portal/app/member/(authed)/loans/_components/MemberApplicationsTable.tsx`
- Modify: `admin/apps/portal/app/member/(authed)/loans/page.tsx` (fetch + render the section)
- Test: `admin/apps/portal/app/member/(authed)/loans/__tests__/MemberApplicationsTable.test.tsx` (create)

**Interfaces:**
- Consumes: `resources.member.listLoanApplications()`; `@sacco/ui` `DataTable`, `Money`, `StatusBadge`, `useTableUrlState`.
- Produces: `MemberApplicationsTable({ rows }: { rows: MemberApplicationRow[] })` and the exported `MemberApplicationRow` type (`{ id: string; loan_product_id: string; requested_amount: string; requested_term_periods: number; status: string }`).

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/app/member/(authed)/loans/__tests__/MemberApplicationsTable.test.tsx` (mirror `MemberLoansTable.test.tsx` in the same folder for providers/wrappers):

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { TenantCurrencyProvider } from "@sacco/ui";
import {
  MemberApplicationsTable,
  type MemberApplicationRow,
} from "../_components/MemberApplicationsTable";

function renderTable(rows: MemberApplicationRow[]) {
  return render(
    <NuqsTestingAdapter>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <MemberApplicationsTable rows={rows} />
      </TenantCurrencyProvider>
    </NuqsTestingAdapter>,
  );
}

describe("MemberApplicationsTable", () => {
  it("renders the status badge and links to the application detail", () => {
    renderTable([
      {
        id: "app-1",
        loan_product_id: "p-1",
        requested_amount: "1000.00",
        requested_term_periods: 12,
        status: "under_review",
      },
    ]);
    expect(
      screen.getByRole("link", { name: /view|track|application|1000/i }),
    ).toHaveAttribute("href", "/member/loans/applications/app-1");
  });

  it("shows an empty state when there are no applications", () => {
    renderTable([]);
    expect(screen.getByText(/no (loan )?applications/i)).toBeInTheDocument();
  });
});
```

(Check `MemberLoansTable.test.tsx` for the exact provider wrapper it uses and match it; if it does not wrap in `NuqsTestingAdapter`/`TenantCurrencyProvider`, copy whatever it does.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal exec vitest run "app/member/(authed)/loans/__tests__/MemberApplicationsTable.test.tsx"`
Expected: FAIL — module `../_components/MemberApplicationsTable` not found.

- [ ] **Step 3: Implement the table**

Create `admin/apps/portal/app/member/(authed)/loans/_components/MemberApplicationsTable.tsx`:

```tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  Money,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";

export interface MemberApplicationRow {
  id: string;
  loan_product_id: string;
  requested_amount: string;
  requested_term_periods: number;
  status: string;
}

const columns: DataTableProps<MemberApplicationRow>["columns"] = [
  {
    id: "requested_amount",
    accessorKey: "requested_amount",
    header: "Requested",
    cell: ({ row }) => (
      <Link
        href={`/member/loans/applications/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        <Money amount={row.original.requested_amount} />
      </Link>
    ),
  },
  {
    id: "requested_term_periods",
    accessorKey: "requested_term_periods",
    header: "Term",
    cell: ({ row }) => <span>{row.original.requested_term_periods} periods</span>,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge entity="loan_application" status={row.original.status} />
    ),
  },
];

function sortRows(
  rows: MemberApplicationRow[],
  column: string | null,
  dir: "asc" | "desc",
): MemberApplicationRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof MemberApplicationRow];
    const bv = b[column as keyof MemberApplicationRow];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function MemberApplicationsTable({
  rows,
}: {
  rows: MemberApplicationRow[];
}) {
  const urlState = useTableUrlState({
    defaultSort: { column: "requested_amount", direction: "desc" },
    defaultPageSize: 25,
  });

  const sorted = useMemo(
    () => sortRows(rows, urlState.sortColumn, urlState.sortDirection),
    [rows, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<MemberApplicationRow>
      id="member-loan-applications"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No loan applications",
        description: "Applications you submit will appear here.",
      }}
    />
  );
}
```

- [ ] **Step 4: Render the section on the Loans page**

Modify `admin/apps/portal/app/member/(authed)/loans/page.tsx`:

```tsx
import { getMemberPageContext } from "@/auth/server-page-context";
import {
  MemberLoansTable,
  type MemberLoanRow,
} from "./_components/MemberLoansTable";
import {
  MemberApplicationsTable,
  type MemberApplicationRow,
} from "./_components/MemberApplicationsTable";

export const metadata = { title: "Your loans" };

export default async function MemberLoansPage() {
  const { resources } = await getMemberPageContext();
  const [loansRes, appsRes] = await Promise.all([
    resources.member.listLoans(),
    resources.member.listLoanApplications(),
  ]);
  const loanRows = (loansRes.data ?? []) as MemberLoanRow[];
  const appRows = (appsRes.data ?? []) as MemberApplicationRow[];
  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <h1 className="text-[length:var(--text-h4)] font-semibold">Your loans</h1>
        <MemberLoansTable rows={loanRows} />
      </section>
      <section className="space-y-4">
        <h2 className="text-[length:var(--text-h4)] font-semibold">
          Loan applications
        </h2>
        <MemberApplicationsTable rows={appRows} />
      </section>
    </div>
  );
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal exec vitest run "app/member/(authed)/loans/__tests__/MemberApplicationsTable.test.tsx"`
Expected: PASS (2 tests).

- [ ] **Step 6: Type-check + lint the portal**

Run: `cd admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add "admin/apps/portal/app/member/(authed)/loans"
git commit -m "feat(member-portal): loan applications list on the loans page"
```

---

### Task 4: Application progress detail view with Stepper (portal)

**Files:**
- Create: `admin/apps/portal/app/member/(authed)/loans/applications/[id]/page.tsx`
- Create: `admin/apps/portal/app/member/(authed)/loans/applications/[id]/_components/ApplicationProgress.tsx`
- Test: `admin/apps/portal/app/member/(authed)/loans/applications/__tests__/ApplicationProgress.test.tsx` (create)

**Interfaces:**
- Consumes: `resources.member.getLoanApplication(id)`; `@sacco/ui` `Stepper`, `StatusBadge`, `Money`, `Card`.
- Produces: `ApplicationProgress({ application }: { application: ApplicationDetail })` where `ApplicationDetail` is `{ id: string; status: string; requested_amount: string; requested_term_periods: number; approved_amount: string | null; approved_term_periods: number | null; rejection_reason: string | null; reviewed_at: string | null; decided_at: string | null }`.

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/app/member/(authed)/loans/applications/__tests__/ApplicationProgress.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TenantCurrencyProvider } from "@sacco/ui";
import {
  ApplicationProgress,
  type ApplicationDetail,
} from "../[id]/_components/ApplicationProgress";

const base: ApplicationDetail = {
  id: "app-1",
  status: "under_review",
  requested_amount: "1000.00",
  requested_term_periods: 12,
  approved_amount: null,
  approved_term_periods: null,
  rejection_reason: null,
  reviewed_at: "2026-06-29T10:00:00Z",
  decided_at: null,
};

function renderProgress(application: ApplicationDetail) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <ApplicationProgress application={application} />
    </TenantCurrencyProvider>,
  );
}

describe("ApplicationProgress", () => {
  it("renders the progress stepper for an in-flight application", () => {
    renderProgress(base);
    expect(screen.getByRole("list", { name: /progress/i })).toBeInTheDocument();
    expect(screen.getByText(/under review/i)).toBeInTheDocument();
  });

  it("shows the rejection reason for a rejected application", () => {
    renderProgress({
      ...base,
      status: "rejected",
      rejection_reason: "Insufficient savings history",
      decided_at: "2026-06-29T12:00:00Z",
    });
    expect(screen.getByText(/insufficient savings history/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal exec vitest run "app/member/(authed)/loans/applications/__tests__/ApplicationProgress.test.tsx"`
Expected: FAIL — module `../[id]/_components/ApplicationProgress` not found.

- [ ] **Step 3: Implement the progress component**

Create `admin/apps/portal/app/member/(authed)/loans/applications/[id]/_components/ApplicationProgress.tsx`:

```tsx
"use client";

import { Card, Money, StatusBadge, Stepper, type StepperStep } from "@sacco/ui";

export interface ApplicationDetail {
  id: string;
  status: string;
  requested_amount: string;
  requested_term_periods: number;
  approved_amount: string | null;
  approved_term_periods: number | null;
  rejection_reason: string | null;
  reviewed_at: string | null;
  decided_at: string | null;
}

const STEPS: StepperStep[] = [
  { id: "submitted", label: "Submitted" },
  { id: "under_review", label: "Under review" },
  { id: "approved", label: "Approved" },
  { id: "disbursed", label: "Disbursed" },
];

// Map the application status onto the linear stepper. Terminal non-linear
// states (rejected / withdrawn / cancelled) are handled separately below.
const STEP_FOR_STATUS: Record<string, string> = {
  draft: "submitted",
  submitted: "submitted",
  under_review: "under_review",
  approved: "approved",
  disbursed: "disbursed",
};

const TERMINAL_NEGATIVE = new Set(["rejected", "withdrawn", "cancelled"]);

export function ApplicationProgress({
  application,
}: {
  application: ApplicationDetail;
}) {
  const isNegative = TERMINAL_NEGATIVE.has(application.status);
  const currentStepId = STEP_FOR_STATUS[application.status] ?? "submitted";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <h1 className="text-[length:var(--text-h4)] font-semibold">
          Loan application
        </h1>
        <StatusBadge entity="loan_application" status={application.status} />
      </div>

      {isNegative ? (
        <Card className="flex flex-col gap-2 p-6">
          <p className="text-[14px] font-medium text-[var(--text-primary)]">
            This application is {application.status}.
          </p>
          {application.rejection_reason ? (
            <p className="text-[13px] text-[var(--text-secondary)]">
              {application.rejection_reason}
            </p>
          ) : null}
        </Card>
      ) : (
        <Card className="p-6">
          <Stepper steps={STEPS} currentStepId={currentStepId} />
        </Card>
      )}

      <Card className="flex flex-col gap-3 p-6">
        <div className="flex justify-between">
          <span className="text-[13px] text-[var(--text-tertiary)]">Requested</span>
          <span className="text-[14px]">
            <Money amount={application.requested_amount} /> ·{" "}
            {application.requested_term_periods} periods
          </span>
        </div>
        {application.approved_amount ? (
          <div className="flex justify-between">
            <span className="text-[13px] text-[var(--text-tertiary)]">Approved</span>
            <span className="text-[14px]">
              <Money amount={application.approved_amount} /> ·{" "}
              {application.approved_term_periods} periods
            </span>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Create the detail page (server component)**

Create `admin/apps/portal/app/member/(authed)/loans/applications/[id]/page.tsx`:

```tsx
import { notFound } from "next/navigation";
import { getMemberPageContext } from "@/auth/server-page-context";
import {
  ApplicationProgress,
  type ApplicationDetail,
} from "./_components/ApplicationProgress";

export const metadata = { title: "Loan application" };

export default async function MemberApplicationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getMemberPageContext();
  const res = (await resources.member.getLoanApplication(id)) as {
    data?: ApplicationDetail;
    error?: unknown;
  };
  if (!res.data) notFound();
  return <ApplicationProgress application={res.data} />;
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd admin && pnpm --filter @sacco/portal exec vitest run "app/member/(authed)/loans/applications/__tests__/ApplicationProgress.test.tsx"`
Expected: PASS (2 tests).

- [ ] **Step 6: Type-check + lint the portal**

Run: `cd admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add "admin/apps/portal/app/member/(authed)/loans/applications"
git commit -m "feat(member-portal): loan application progress detail view"
```

---

## Self-Review

**Spec coverage (Increment 1 only):** "See loan application progress" is covered by Task 1 (member read endpoints), Task 2 (typed client), Task 3 (applications list on the Loans page), and Task 4 (progress detail with Stepper). The remaining spec items (loan apply, KYC, statement) are explicitly out of scope for this plan and will be planned as increments 2–4.

**Placeholder scan:** No TBD/TODO; every code step contains complete code; commands have expected output. Two places say "match/check the existing file" (router include style in `app/main.py`; provider wrapper in `MemberLoansTable.test.tsx`) — these are deliberate "follow the established pattern" instructions, not missing content, because the surrounding file's convention is the source of truth.

**Type consistency:** `MemberApplicationRow` (Task 3) and `ApplicationDetail` (Task 4) field names match `LoanApplicationOut` (status, requested_amount, requested_term_periods, approved_amount, approved_term_periods, rejection_reason, reviewed_at, decided_at). `member(api).listLoanApplications` / `getLoanApplication` (Task 2) are the methods consumed by Tasks 3 and 4. `member_app_router` (Task 1) is the router mounted in `app/main.py`. `StatusBadge entity="loan_application"` matches the existing entity in `status-maps.ts`.
