# Member Loan Apply Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an active member apply for a loan from the member portal; the application flows into the existing operator `credit.approve_application` maker-checker workflow unchanged.

**Architecture:** A thin member-facing HTTP layer over the existing `LoanApplicationService.submit`: `POST /member/loan-applications` sets `member_id = submitted_by = current_member.id`, derives `disbursement_destination` from the product (`member_savings` if the product allows it, else the product's first allowed destination), leaves `disbursement_account_id` NULL for the operator, and reads the idempotency key from the `Idempotency-Key` header (the portal client auto-injects it). A new slim `GET /member/loan-products` read feeds the portal's product select. The portal Loans page gains an "Apply for a loan" `FormDialog` (product select with min/max helper text, amount, term, purpose). No new services, no new tables, no migration.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async (backend), pytest/httpx with stub auth headers (backend tests), Next.js 15 App Router + React 19 + `@sacco/ui` + TanStack Query (portal), vitest + Testing Library (portal tests).

This is increment 2 of the 2026-06-29 member self-service design
(`docs/superpowers/specs/2026-06-29-member-self-service-design.md`). Increment 1
(application progress reads) and increment 3 (KYC submissions) are already on `main`.
Branch: `feat/member-loan-apply` (from `main`).

## Global Constraints

- Member endpoints are gated by `CurrentMember` (from `app.modules.iam.dependencies`); they never accept a client-supplied `member_id` and scope everything to `current_member.id`. Cross-member access returns **404**, never 403.
- Loan apply **reuses the existing operator approval** (`credit.approve_application` maker-checker) unchanged. No new approval path, no member-side maker-checker, no approval executors.
- Non-active members cannot apply — enforced by the member auth dependency itself (both `get_current_member_stub` and `get_current_member_jwt` reject `portal_enabled=false OR status != 'active'` with **403** before any handler runs). **Spec deviation:** the 2026-06-29 spec predates the 4a dep-level eligibility check and called for a handler-level 409; the handler needs NO status guard — do not add dead code. Pin the 403 in tests.
- Loan apply outside product min/max amount or over max term → **422** from the member endpoint (the operator endpoint keeps its existing 400 mapping — do not change it).
- `disbursement_destination` is derived server-side: `member_savings` if the product allows it, else the first allowed destination. `disbursement_account_id` stays NULL for the operator to finalize.
- The `Idempotency-Key` header is required on the member POST (min 8 / max 200 chars). The portal API client auto-injects a UUID per request (contract L); retried form submissions reuse the same key only if the caller pins it — natural idempotent replay converges on the same application.
- Guarantor nomination by members is **out of scope** (operators manage guarantors at review).
- `GET /member/loan-products` returns **active products only** and a slim shape — no GL account codes, no `required_approvals`, no `write_off_threshold` (operator-internal config).
- Portal contracts: forms via `FormField`/RHF/Zod with schemas in `@sacco/schemas` (J, U); money input via `<MoneyInput>` and display via `<Money>` (R); statuses via `<StatusBadge entity="loan_application">` (S); no client-side fetching for initial render — the server component fetches products (M); dialogs via `FormDialog`.
- All DB access async; Pydantic schemas in `schemas.py`, routers in `api.py`; ruff + mypy (strict) stay clean.

## Prerequisites

Branch `feat/member-loan-apply` checked out (created from `main`). Docker Postgres test DB up (`docker compose ps` shows `postgres-test` healthy). Backend venv active; `pnpm` available in `admin/`.

## File Structure

```
app/modules/credit/schemas.py                    (modify: +MemberLoanProductOut, +MemberLoanApplicationIn)
app/modules/credit/api.py                        (modify: +member_products_router, +member apply handler)
app/main.py                                      (modify: register member_products_router)
tests/modules/credit/test_member_apply_api.py    (create: products read + apply tests)

admin/packages/schemas/src/credit.ts             (modify: +memberLoanApplySchema, +MemberLoanProductOut)
admin/packages/schemas/src/__tests__/credit.test.ts (modify: +member apply schema tests)
admin/packages/api-client/src/resources/member.ts (modify: +listLoanProducts, +applyForLoan)
admin/packages/api-client/src/query-keys.ts      (modify: +member.loanProducts)

admin/apps/portal/app/member/(authed)/loans/page.tsx (modify: fetch products, render apply section)
admin/apps/portal/app/member/(authed)/loans/_components/MemberApplySection.tsx (create)
admin/apps/portal/app/member/(authed)/loans/__tests__/MemberApplySection.test.tsx (create)

CLAUDE.md                                        (modify: member-write contract, Task 5)
```

---

### Task 1: `GET /member/loan-products` — slim active-products read

**Files:**
- Modify: `app/modules/credit/schemas.py`
- Modify: `app/modules/credit/api.py`
- Modify: `app/main.py`
- Test: `tests/modules/credit/test_member_apply_api.py` (create)

**Interfaces:**
- Consumes: `LoanProductService.list(include_inactive=False)` (existing), `CurrentMember` (existing).
- Produces (consumed by Task 2's tests and Task 3's TS types):
  - `MemberLoanProductOut` Pydantic schema: `id: uuid.UUID`, `name: str`, `description: str | None`, `interest_method: str`, `annual_interest_rate: Decimal`, `repayment_frequency: str`, `max_term_periods: int`, `min_amount: Decimal`, `max_amount: Decimal`.
  - `member_products_router` (`APIRouter(prefix="/member/loan-products")`) exported from `app/modules/credit/api.py`, registered in `app/main.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/credit/test_member_apply_api.py` (fixture pattern copied from `tests/modules/credit/test_member_applications_api.py`; the member stub auth header is `X-Member-Actor-ID`):

```python
"""HTTP tests: member loan-products read + member loan apply (stub auth)."""
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
from app.modules.credit.models import LoanProduct
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
        # Order respects FKs: actions → requests; applications → products/members.
        for tbl in (
            "approval_actions",
            "loan_applications",
            "approval_requests",
            "loan_products",
        ):
            await session.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        await session.execute(
            text(
                "DELETE FROM audit_log WHERE table_name IN "
                "('loan_applications', 'loan_products', 'members')"
            )
        )
        await session.execute(text("DELETE FROM members"))
        await session.commit()


def _member_headers(member_id: str) -> dict[str, str]:
    return {**HEADERS, "X-Member-Actor-ID": member_id}


async def _seed_member(engine: AsyncEngine, *, status: str = "active") -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        m = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}",
            full_name="Applicant",
            date_of_birth=date(1990, 1, 1),
            gender="male",
            status=status,
            email=f"m-{uuid.uuid4().hex[:6]}@example.com",
            portal_enabled=True,
        )
        session.add(m)
        await session.commit()
        return m.id


async def _seed_product(
    engine: AsyncEngine,
    *,
    destinations: list[str] | None = None,
    is_active: bool = True,
    min_amount: str = "100.00",
    max_amount: str = "100000.00",
    max_term_periods: int = 24,
) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        product = LoanProduct(
            name=f"Product {uuid.uuid4().hex[:6]}",
            interest_method="flat",
            annual_interest_rate=Decimal("12.00"),
            repayment_frequency="monthly",
            max_term_periods=max_term_periods,
            min_amount=Decimal(min_amount),
            max_amount=Decimal(max_amount),
            disbursement_destinations=destinations or ["member_savings", "cash"],
            gl_principal_receivable_code="1300",
            gl_interest_receivable_code="1310",
            gl_interest_income_code="4100",
            is_active=is_active,
        )
        session.add(product)
        await session.commit()
        return product.id


# ── GET /member/loan-products ────────────────────────────────────────────────


async def test_member_products_lists_active_only_slim_shape(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member(test_engine)
    await _seed_product(test_engine, is_active=True)
    await _seed_product(test_engine, is_active=False)

    resp = await client.get("/member/loan-products", headers=_member_headers(str(member_id)))
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["min_amount"] == "100.00"
    assert row["max_term_periods"] == 24
    # Slim view: operator-internal config must not leak to members.
    assert "gl_principal_receivable_code" not in row
    assert "required_approvals" not in row
    assert "write_off_threshold" not in row
    assert "disbursement_destinations" not in row


async def test_member_products_requires_member_auth(client: AsyncClient) -> None:
    # Operator headers only. In stub mode the required X-Member-Actor-ID header
    # is missing → FastAPI validation 422 (jwt mode would 401 on missing Bearer).
    resp = await client.get("/member/loan-products", headers=HEADERS)
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/modules/credit/test_member_apply_api.py -q`
Expected: FAIL — both tests 404 (route does not exist).

- [ ] **Step 3: Write the implementation**

In `app/modules/credit/schemas.py`, append after `LoanProductPatchIn` (keeping product schemas together):

```python
class MemberLoanProductOut(BaseModel):
    """Slim product view for member self-service (no GL / approval config)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    interest_method: str
    annual_interest_rate: Decimal
    repayment_frequency: str
    max_term_periods: int
    min_amount: Decimal
    max_amount: Decimal
```

In `app/modules/credit/api.py`:

Add `MemberLoanProductOut` to the existing `from app.modules.credit.schemas import (...)` list (alphabetical position: after `LoanStatementOut`).

Add the router next to the other member routers (after the `member_app_router` line):

```python
# Member self-service loan products (read-only; active products, slim shape).
member_products_router = APIRouter(prefix="/member/loan-products", tags=["member-loans"])
```

Add the handler after `member_loan_application_detail` (end of the member endpoints block):

```python
@member_products_router.get("", response_model=list[MemberLoanProductOut])
async def member_loan_products(
    session: Session, member: CurrentMember
) -> list[MemberLoanProductOut]:
    """List active loan products a member can apply for (slim view)."""
    svc = LoanProductService(session)
    products = await svc.list(include_inactive=False)
    return [MemberLoanProductOut.model_validate(p) for p in products]
```

In `app/main.py`:

Extend the credit imports (line ~17):

```python
from app.modules.credit.api import member_products_router as credit_member_products_router
```

Register it directly after `app.include_router(credit_member_app_router)` (line ~160):

```python
app.include_router(credit_member_products_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/modules/credit/test_member_apply_api.py -q`
Expected: PASS (2 tests).

Also: `python -m pytest tests/modules/credit/ -q` — no regressions.

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/credit/schemas.py app/modules/credit/api.py app/main.py tests/modules/credit/test_member_apply_api.py
git commit -m "feat(credit): member loan-products read endpoint (slim, active only)"
```

---

### Task 2: `POST /member/loan-applications` — member apply endpoint

**Files:**
- Modify: `app/modules/credit/schemas.py`
- Modify: `app/modules/credit/api.py`
- Test: `tests/modules/credit/test_member_apply_api.py` (append)

**Interfaces:**
- Consumes: `LoanApplicationService.submit(...)` (existing — signature: `loan_product_id, member_id, requested_amount, requested_term_periods, purpose, disbursement_destination, disbursement_account_id, submitted_by, idempotency_key`), `LoanProductService.get(product_id)` (existing, raises `ValueError` "not found"), `CurrentMember` (a `Member` row — `.id`, `.status` available), Task 1's test fixtures.
- Produces (wire contract, consumed by Task 3's TS types):
  - `POST /member/loan-applications` — body `MemberLoanApplicationIn {loan_product_id, requested_amount, requested_term_periods, purpose?}`, required `Idempotency-Key` header → **201** `LoanApplicationOut` (existing schema). Errors: 403 non-active member (from the auth dep, not the handler), 409 inactive product, 404 unknown product / foreign idempotency replay, 422 amount/term out of product bounds or missing header.

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/credit/test_member_apply_api.py`:

```python
# ── POST /member/loan-applications ───────────────────────────────────────────


def _apply_headers(member_id: str, key: str | None = None) -> dict[str, str]:
    return {
        **_member_headers(member_id),
        "Idempotency-Key": key or f"apply-{uuid.uuid4().hex}",
    }


async def test_member_apply_happy_path_derives_destination(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member(test_engine)
    product_id = await _seed_product(
        test_engine, destinations=["cash", "member_savings"]
    )
    resp = await client.post(
        "/member/loan-applications",
        json={
            "loan_product_id": str(product_id),
            "requested_amount": "5000.00",
            "requested_term_periods": 12,
            "purpose": "School fees for my daughter",
        },
        headers=_apply_headers(str(member_id)),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "submitted"
    assert body["member_id"] == str(member_id)
    # member_savings preferred whenever the product allows it.
    assert body["disbursement_destination"] == "member_savings"
    assert body["disbursement_account_id"] is None
    assert body["approval_request_id"] is not None


async def test_member_apply_falls_back_to_first_destination(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member(test_engine)
    product_id = await _seed_product(test_engine, destinations=["cash"])
    resp = await client.post(
        "/member/loan-applications",
        json={
            "loan_product_id": str(product_id),
            "requested_amount": "5000.00",
            "requested_term_periods": 12,
            "purpose": "Working capital for my shop",
        },
        headers=_apply_headers(str(member_id)),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["disbursement_destination"] == "cash"


async def test_member_apply_creates_approval_request_by_member(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member(test_engine)
    product_id = await _seed_product(test_engine)
    resp = await client.post(
        "/member/loan-applications",
        json={
            "loan_product_id": str(product_id),
            "requested_amount": "5000.00",
            "requested_term_periods": 12,
            "purpose": "Home improvement project",
        },
        headers=_apply_headers(str(member_id)),
    )
    assert resp.status_code == 201, resp.text
    request_id = resp.json()["approval_request_id"]

    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        row = (
            await session.execute(
                text(
                    "SELECT operation_type, requested_by, status "
                    "FROM approval_requests WHERE id = :rid"
                ),
                {"rid": request_id},
            )
        ).one()
    assert row.operation_type == "credit.approve_application"
    assert row.requested_by == uuid.UUID(str(member_id))
    assert row.status == "pending"


async def test_member_apply_non_active_member_rejected_by_auth(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    """Regression pin: the member auth dep (4a eligibility) rejects non-active
    members with 403 before the handler runs — no handler-level guard needed."""
    member_id = await _seed_member(test_engine, status="pending")
    product_id = await _seed_product(test_engine)
    resp = await client.post(
        "/member/loan-applications",
        json={
            "loan_product_id": str(product_id),
            "requested_amount": "5000.00",
            "requested_term_periods": 12,
            "purpose": "Anything at all here",
        },
        headers=_apply_headers(str(member_id)),
    )
    assert resp.status_code == 403


async def test_member_apply_amount_and_term_bounds_422(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member(test_engine)
    product_id = await _seed_product(
        test_engine, min_amount="1000.00", max_amount="2000.00", max_term_periods=6
    )
    below = await client.post(
        "/member/loan-applications",
        json={
            "loan_product_id": str(product_id),
            "requested_amount": "500.00",
            "requested_term_periods": 6,
            "purpose": "Below the minimum amount",
        },
        headers=_apply_headers(str(member_id)),
    )
    assert below.status_code == 422
    over_term = await client.post(
        "/member/loan-applications",
        json={
            "loan_product_id": str(product_id),
            "requested_amount": "1500.00",
            "requested_term_periods": 12,
            "purpose": "Term is over the maximum",
        },
        headers=_apply_headers(str(member_id)),
    )
    assert over_term.status_code == 422


async def test_member_apply_inactive_product_409_unknown_404(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member(test_engine)
    inactive_id = await _seed_product(test_engine, is_active=False)
    resp = await client.post(
        "/member/loan-applications",
        json={
            "loan_product_id": str(inactive_id),
            "requested_amount": "5000.00",
            "requested_term_periods": 12,
            "purpose": "Product is switched off",
        },
        headers=_apply_headers(str(member_id)),
    )
    assert resp.status_code == 409

    unknown = await client.post(
        "/member/loan-applications",
        json={
            "loan_product_id": str(uuid.uuid4()),
            "requested_amount": "5000.00",
            "requested_term_periods": 12,
            "purpose": "Product does not exist",
        },
        headers=_apply_headers(str(member_id)),
    )
    assert unknown.status_code == 404


async def test_member_apply_idempotent_replay_same_member(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member(test_engine)
    product_id = await _seed_product(test_engine)
    key = f"apply-{uuid.uuid4().hex}"
    body = {
        "loan_product_id": str(product_id),
        "requested_amount": "5000.00",
        "requested_term_periods": 12,
        "purpose": "Retried form submission",
    }
    first = await client.post(
        "/member/loan-applications", json=body, headers=_apply_headers(str(member_id), key)
    )
    second = await client.post(
        "/member/loan-applications", json=body, headers=_apply_headers(str(member_id), key)
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]


async def test_member_apply_foreign_idempotency_key_404(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    """Replaying another member's key must not leak their application."""
    member_a = await _seed_member(test_engine)
    member_b = await _seed_member(test_engine)
    product_id = await _seed_product(test_engine)
    key = f"apply-{uuid.uuid4().hex}"
    body = {
        "loan_product_id": str(product_id),
        "requested_amount": "5000.00",
        "requested_term_periods": 12,
        "purpose": "Original application by A",
    }
    first = await client.post(
        "/member/loan-applications", json=body, headers=_apply_headers(str(member_a), key)
    )
    assert first.status_code == 201
    replay = await client.post(
        "/member/loan-applications", json=body, headers=_apply_headers(str(member_b), key)
    )
    assert replay.status_code == 404


async def test_member_apply_missing_idempotency_header_422(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member(test_engine)
    product_id = await _seed_product(test_engine)
    resp = await client.post(
        "/member/loan-applications",
        json={
            "loan_product_id": str(product_id),
            "requested_amount": "5000.00",
            "requested_term_periods": 12,
            "purpose": "No idempotency header sent",
        },
        headers=_member_headers(str(member_id)),
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/modules/credit/test_member_apply_api.py -q`
Expected: the new tests FAIL with 405 (`POST` not allowed on the member applications route); Task 1's two tests still pass.

- [ ] **Step 3: Write the implementation**

In `app/modules/credit/schemas.py`, append after `MemberLoanProductOut`:

```python
class MemberLoanApplicationIn(BaseModel):
    """Member self-service application. member_id, destination, and the
    idempotency key are supplied server-side — never by the client body."""

    loan_product_id: uuid.UUID
    requested_amount: Decimal = Field(gt=0)
    requested_term_periods: int = Field(ge=1)
    purpose: str | None = Field(default=None, max_length=500)
```

In `app/modules/credit/api.py`:

Add `Header` to the `fastapi` import; add `MemberLoanApplicationIn` to the schemas import list.

Add the handler directly after `member_loan_application_detail` (before the products handler added in Task 1):

```python
@member_app_router.post("", response_model=LoanApplicationOut, status_code=201)
async def member_apply_for_loan(
    body: MemberLoanApplicationIn,
    session: Session,
    member: CurrentMember,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
    ],
) -> LoanApplicationOut:
    """Member loan apply: thin wrapper over LoanApplicationService.submit.

    Derives the disbursement destination from the product (member_savings
    when allowed) and leaves disbursement_account_id NULL for the operator.
    The application flows into the unchanged credit.approve_application
    maker-checker — this endpoint adds no approval surface. No member-status
    guard here: CurrentMember already rejects non-active members (403).
    """
    svc = LoanApplicationService(session)
    try:
        product = await LoanProductService(session).get(body.loan_product_id)
        destination = (
            "member_savings"
            if "member_savings" in product.disbursement_destinations
            else product.disbursement_destinations[0]
        )
        application = await svc.submit(
            loan_product_id=body.loan_product_id,
            member_id=member.id,
            requested_amount=body.requested_amount,
            requested_term_periods=body.requested_term_periods,
            purpose=body.purpose,
            disbursement_destination=destination,
            disbursement_account_id=None,
            submitted_by=member.id,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail="Product not found") from exc
        if "not active" in message:
            raise HTTPException(
                status_code=409, detail="This loan product is not available"
            ) from exc
        # Product min/max amount or term bounds from the existing service.
        raise HTTPException(status_code=422, detail=message) from exc
    if application.member_id != member.id:
        # Idempotent replay of a key created by a different member: behave as
        # if nothing exists rather than leaking another member's application.
        raise HTTPException(status_code=404, detail="Application not found")
    return LoanApplicationOut.model_validate(application)
```

Notes for the implementer:
- `ApprovalService.submit` stores `requested_by` as a plain UUID column (no FK to `tenant_users`), so the member's id is safe there. `ApprovalService.approve` rejects maker == checker; a member id never equals an operator id, so any operator can act.
- Do NOT modify `LoanApplicationService` — the wrapper is handler-level by design (guards + derivation only; everything else is the existing service).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/modules/credit/ -q`
Expected: all green (new file 11 tests; no regressions in the operator/application suites).

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/credit/schemas.py app/modules/credit/api.py tests/modules/credit/test_member_apply_api.py
git commit -m "feat(credit): member loan apply endpoint (POST /member/loan-applications)"
```

---

### Task 3: Portal wire types, Zod form schema, api-client resources, query key

**Files:**
- Modify: `admin/packages/schemas/src/credit.ts`
- Modify: `admin/packages/schemas/src/__tests__/credit.test.ts`
- Modify: `admin/packages/api-client/src/resources/member.ts`
- Modify: `admin/packages/api-client/src/query-keys.ts`

**Interfaces:**
- Consumes: Task 1/2 wire shapes; existing `moneyString`, `intString`, `uuid` from `./common`; existing `LoanApplicationOut` TS interface.
- Produces (consumed by Task 4):
  - `memberLoanApplySchema` (Zod) + `MemberLoanApplyInput` type: `{loan_product_id: string, requested_amount: string, requested_term_periods: string, purpose: string}`.
  - `MemberLoanProductOut` TS interface: `{id, name, description, interest_method, annual_interest_rate, repayment_frequency, max_term_periods, min_amount, max_amount}` (decimals as strings).
  - `member.listLoanProducts()`, `member.applyForLoan(body)` on the api-client member resource.
  - `queryKeys.member.loanProducts()`.

- [ ] **Step 1: Write the failing tests**

Append to `admin/packages/schemas/src/__tests__/credit.test.ts`:

```ts
import { memberLoanApplySchema } from "../credit";

describe("memberLoanApplySchema", () => {
  const valid = {
    loan_product_id: "018f6a3e-1111-7000-8000-000000000001",
    requested_amount: "5000.00",
    requested_term_periods: "12",
    purpose: "School fees for my daughter",
  };

  it("accepts a valid member application", () => {
    expect(memberLoanApplySchema.safeParse(valid).success).toBe(true);
  });

  it("requires a purpose of at least 10 characters", () => {
    expect(
      memberLoanApplySchema.safeParse({ ...valid, purpose: "too short" }).success,
    ).toBe(false);
  });

  it("rejects a zero amount and a non-integer term", () => {
    expect(
      memberLoanApplySchema.safeParse({ ...valid, requested_amount: "0" }).success,
    ).toBe(false);
    expect(
      memberLoanApplySchema.safeParse({ ...valid, requested_term_periods: "1.5" })
        .success,
    ).toBe(false);
  });

  it("has no member_id, destination, or idempotency_key fields", () => {
    const parsed = memberLoanApplySchema.parse(valid);
    expect(Object.keys(parsed).sort()).toEqual([
      "loan_product_id",
      "purpose",
      "requested_amount",
      "requested_term_periods",
    ]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/schemas test`
Expected: FAIL — `memberLoanApplySchema` not exported.

- [ ] **Step 3: Write the implementation**

In `admin/packages/schemas/src/credit.ts`, append after `loanApplicationRejectSchema`:

```ts
// Member self-service apply (increment 2 of the member self-service design).
// member_id, disbursement destination, and the idempotency key are server-side.
export const memberLoanApplySchema = z.object({
  loan_product_id: uuid,
  requested_amount: moneyString({ min: "0.01" }),
  requested_term_periods: intString({ min: 1 }),
  purpose: z
    .string()
    .trim()
    .min(10, "Tell us the purpose (at least 10 characters)")
    .max(500),
});
```

Add to the type-exports block (next to `LoanApplicationInput`):

```ts
export type MemberLoanApplyInput = z.infer<typeof memberLoanApplySchema>;
```

Append next to the existing `LoanProductOut` interface:

```ts
// Mirror app/modules/credit/schemas.py::MemberLoanProductOut (slim member view).
export interface MemberLoanProductOut {
  id: string;
  name: string;
  description: string | null;
  interest_method: string;
  annual_interest_rate: string;
  repayment_frequency: string;
  max_term_periods: number;
  min_amount: string;
  max_amount: string;
}
```

In `admin/packages/api-client/src/resources/member.ts`, add inside the returned object (after `getLoanApplication`):

```ts
    listLoanProducts: () => api.GET("/member/loan-products" as never),
    applyForLoan: (body: Record<string, unknown>) =>
      api.POST("/member/loan-applications" as never, { body } as never),
```

In `admin/packages/api-client/src/query-keys.ts`, add inside the `member` block (after `loanApplication`):

```ts
    loanProducts: () => ["member", "loan-products"] as const,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `admin/`): `pnpm --filter @sacco/schemas test && pnpm --filter @sacco/api-client test`
Expected: PASS.

- [ ] **Step 5: Lint, typecheck, commit**

Run (from `admin/`): `pnpm lint && pnpm typecheck`
Expected: clean.

```bash
git add admin/packages/schemas/src/credit.ts admin/packages/schemas/src/__tests__/credit.test.ts admin/packages/api-client/src/resources/member.ts admin/packages/api-client/src/query-keys.ts
git commit -m "feat(api-client): member loan apply schema, product type, resources"
```

---

### Task 4: Member portal — "Apply for a loan" section on the Loans page

**Files:**
- Modify: `admin/apps/portal/app/member/(authed)/loans/page.tsx`
- Create: `admin/apps/portal/app/member/(authed)/loans/_components/MemberApplySection.tsx`
- Test: `admin/apps/portal/app/member/(authed)/loans/__tests__/MemberApplySection.test.tsx` (create)

**Interfaces:**
- Consumes: Task 3's `memberLoanApplySchema`, `MemberLoanApplyInput`, `MemberLoanProductOut`, `member.applyForLoan`, `queryKeys.member.loanApplications()`; existing `FormDialog`, `FormField`, `MoneyInput`, `Money`, `Textarea`, `Select*`, `Button`, `toast` from `@sacco/ui`; `useTypedMutation` from `@sacco/api-client`; `useAuth` from `@/auth/use-auth`; `apiErrorMessage` from `@/lib/api-error`; `LoanApplicationOut` from `@sacco/schemas`.
- Produces: `MemberApplySection({ products })` client component rendered by the Loans page header.

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/app/member/(authed)/loans/__tests__/MemberApplySection.test.tsx` (mock pattern copied from `admin/apps/portal/app/member/(authed)/profile/__tests__/MemberKycSection.test.tsx` — check that file for the exact `useAuth` / `next/navigation` mock helpers used in this app and mirror them):

```tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemberApplySection } from "../_components/MemberApplySection";
import type { MemberLoanProductOut } from "@sacco/schemas";

const applyForLoan = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({
    resources: { member: { applyForLoan } },
  }),
}));

const PRODUCTS: MemberLoanProductOut[] = [
  {
    id: "018f6a3e-1111-7000-8000-000000000001",
    name: "School Fees Loan",
    description: null,
    interest_method: "flat",
    annual_interest_rate: "12.00",
    repayment_frequency: "monthly",
    max_term_periods: 24,
    min_amount: "1000.00",
    max_amount: "50000.00",
  },
];

beforeEach(() => {
  applyForLoan.mockReset();
  refresh.mockReset();
});

describe("MemberApplySection", () => {
  it("opens the dialog and shows the selected product's bounds as helper text", async () => {
    const user = userEvent.setup();
    render(<MemberApplySection products={PRODUCTS} />);
    await user.click(screen.getByRole("button", { name: /apply for a loan/i }));
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: /school fees loan/i }));
    expect(screen.getByText(/up to 24/i)).toBeInTheDocument();
  });

  it("submits a valid application and refreshes", async () => {
    applyForLoan.mockResolvedValue({
      data: { id: "app-1", status: "submitted" },
    });
    const user = userEvent.setup();
    render(<MemberApplySection products={PRODUCTS} />);
    await user.click(screen.getByRole("button", { name: /apply for a loan/i }));
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: /school fees loan/i }));
    await user.type(screen.getByLabelText(/amount/i), "5000");
    await user.type(screen.getByLabelText(/term/i), "12");
    await user.type(screen.getByLabelText(/purpose/i), "School fees for my daughter");
    await user.click(screen.getByRole("button", { name: /submit application/i }));
    await waitFor(() => expect(applyForLoan).toHaveBeenCalledTimes(1));
    expect(applyForLoan.mock.calls[0]![0]).toMatchObject({
      loan_product_id: PRODUCTS[0]!.id,
      requested_amount: "5000",
      requested_term_periods: "12",
    });
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("blocks a too-short purpose", async () => {
    const user = userEvent.setup();
    render(<MemberApplySection products={PRODUCTS} />);
    await user.click(screen.getByRole("button", { name: /apply for a loan/i }));
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: /school fees loan/i }));
    await user.type(screen.getByLabelText(/amount/i), "5000");
    await user.type(screen.getByLabelText(/term/i), "12");
    await user.type(screen.getByLabelText(/purpose/i), "short");
    await user.click(screen.getByRole("button", { name: /submit application/i }));
    expect(await screen.findByText(/at least 10 characters/i)).toBeInTheDocument();
    expect(applyForLoan).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- MemberApplySection`
Expected: FAIL — module `../_components/MemberApplySection` not found.

- [ ] **Step 3: Write the implementation**

Create `admin/apps/portal/app/member/(authed)/loans/_components/MemberApplySection.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormDialog,
  FormField,
  Input,
  Money,
  MoneyInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  memberLoanApplySchema,
  type LoanApplicationOut,
  type MemberLoanApplyInput,
  type MemberLoanProductOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function MemberApplySection({
  products,
}: {
  products: MemberLoanProductOut[];
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [open, setOpen] = useState(false);

  const form = useForm<MemberLoanApplyInput>({
    resolver: zodResolver(memberLoanApplySchema),
    defaultValues: {
      loan_product_id: "",
      requested_amount: "",
      requested_term_periods: "",
      purpose: "",
    },
  });

  const selectedId = form.watch("loan_product_id");
  const selected = products.find((p) => p.id === selectedId);

  const mutation = useTypedMutation<LoanApplicationOut, MemberLoanApplyInput>(
    async (input) => {
      const res = await (resources.member.applyForLoan(
        input as unknown as Record<string, unknown>,
      ) as Promise<{ data?: LoanApplicationOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.member.loanApplications()],
      onSuccess: () => {
        toast.success("Application submitted", {
          description: "SACCO staff will review your application.",
        });
        setOpen(false);
        form.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("Your application was not submitted", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  if (products.length === 0) return null;

  return (
    <>
      <Button onClick={() => setOpen(true)}>Apply for a loan</Button>
      {open ? (
        <FormDialog
          title="Apply for a loan"
          description="Your application is reviewed and approved by SACCO staff."
          onDismiss={() => setOpen(false)}
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
          footer={
            <>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setOpen(false)}
                disabled={mutation.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={mutation.isPending}>
                Submit application
              </Button>
            </>
          }
        >
          <FormField
            control={form.control}
            name="loan_product_id"
            label="Product"
            required
            render={({ field, id, describedBy, invalid }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                  <SelectValue placeholder="Choose a product…" />
                </SelectTrigger>
                <SelectContent>
                  {products.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          {selected ? (
            <p className="text-[var(--text-secondary)]">
              <Money amount={selected.min_amount} /> –{" "}
              <Money amount={selected.max_amount} /> · up to{" "}
              {selected.max_term_periods} {selected.repayment_frequency} periods
            </p>
          ) : null}
          <FormField
            control={form.control}
            name="requested_amount"
            label="Amount"
            required
            render={({ field, id, describedBy, invalid }) => (
              <MoneyInput
                id={id}
                aria-describedby={describedBy}
                aria-invalid={invalid}
                value={field.value ?? ""}
                onValueChange={field.onChange}
                onBlur={field.onBlur}
                name={field.name}
                ref={field.ref}
              />
            )}
          />
          <FormField
            control={form.control}
            name="requested_term_periods"
            label="Term (periods)"
            required
            render={({ field, id, describedBy, invalid }) => (
              <Input
                id={id}
                inputMode="numeric"
                aria-describedby={describedBy}
                aria-invalid={invalid}
                {...field}
              />
            )}
          />
          <FormField
            control={form.control}
            name="purpose"
            label="Purpose"
            required
            render={({ field, id, describedBy, invalid }) => (
              <Textarea
                id={id}
                rows={3}
                aria-describedby={describedBy}
                aria-invalid={invalid}
                {...field}
              />
            )}
          />
        </FormDialog>
      ) : null}
    </>
  );
}
```

Note for the implementer: `FormField`'s helper prop is `helpText?: string`
(string only — verified), which cannot carry `<Money>` elements; that is why
the product-bounds line renders as a separate `<p>` under the product field
(contract R requires `<Money>` for money display). Keep the copy shape
"min – max · up to N {frequency} periods" so the test's `/up to 24/i`
assertion holds.

Modify `admin/apps/portal/app/member/(authed)/loans/page.tsx` — fetch products server-side and render the section in the header row:

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
import { MemberApplySection } from "./_components/MemberApplySection";
import type { MemberLoanProductOut } from "@sacco/schemas";

export const metadata = { title: "Your loans" };

export default async function MemberLoansPage() {
  const { resources } = await getMemberPageContext();
  const [loansRes, appsRes, productsRes] = await Promise.all([
    resources.member.listLoans(),
    resources.member.listLoanApplications(),
    resources.member.listLoanProducts(),
  ]);
  const loanRows = (loansRes.data ?? []) as MemberLoanRow[];
  const appRows = (appsRes.data ?? []) as MemberApplicationRow[];
  const products = (productsRes.data ?? []) as MemberLoanProductOut[];
  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-[length:var(--text-h4)] font-semibold">Your loans</h1>
          <MemberApplySection products={products} />
        </div>
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

- [ ] **Step 4: Run tests to verify they pass**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- MemberApplySection`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint, typecheck, commit**

Run (from `admin/`): `pnpm lint && pnpm typecheck`
Expected: clean.

```bash
git add "admin/apps/portal/app/member/(authed)/loans"
git commit -m "feat(portal): member loan apply dialog on the Loans page"
```

---

### Task 5: Close-out — full suites + CLAUDE.md member-write contract

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Backend suite**

Run: `python -m ruff check app/ tests/ && python -m mypy app/ && python -m pytest tests/modules/credit/ tests/modules/members/ tests/core/ -q`
Expected: all clean/green.

- [ ] **Step 2: Admin suite**

Run (from `admin/`): `pnpm lint && pnpm typecheck && pnpm test`
Expected: all exit 0.

- [ ] **Step 3: Update the CLAUDE.md contracts**

(a) In "## Member auth contracts (Phase 4a — do not violate)", replace:

```markdown
  Cross-member access returns **404**, never 403. Members may write **only** a
  KYC submission (`POST /member/me/kyc`) — no other member mutations, no
  member-side maker-checker.
```

with:

```markdown
  Cross-member access returns **404**, never 403. Members may write **only**: a
  KYC submission (`POST /member/me/kyc`) and a loan application
  (`POST /member/loan-applications`) — no other member mutations, no
  member-side maker-checker.
```

(b) In the same section, add a new bullet after the `/member/savings` bullet:

```markdown
- Member loan apply (`POST /member/loan-applications`) is a handler-level wrapper
  over `LoanApplicationService.submit`: `member_id` = `submitted_by` = the current
  member, `disbursement_destination` derived from the product (`member_savings`
  if allowed, else the first allowed destination), `disbursement_account_id` left
  NULL for the operator, idempotency key from the required `Idempotency-Key`
  header. No handler-level status guard — the member auth dep already rejects
  non-active members (403, the 4a eligibility rule); product bound violations
  → 422. The application flows into the UNCHANGED `credit.approve_application`
  maker-checker (`requested_by` = the member's id — a plain UUID column, no FK).
  `GET /member/loan-products` is the member-facing product read: active products
  only, slim shape (no GL codes / approval / write-off config).
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): member loan apply contract (self-service increment 2)"
```

---

## Out of scope for this plan

- Member withdraw of their own application (operators use the existing withdraw path).
- Guarantor nomination by members (operators manage guarantors at review).
- The consolidated member statement (`GET /member/statement`) — increment 4 of the
  2026-06-29 member self-service design, planned separately.
- Notifications on application decision (Phase 3 dependency).
- Draft auto-save on the apply dialog (contract X targets long forms; this 4-field
  dialog does not qualify).
