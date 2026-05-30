# Sub-plan 12 — API and Permissions

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Complete `app/modules/credit/api.py` with all 18 endpoints wired and tested.
Write `tests/modules/credit/test_api.py` covering one HTTP test per endpoint. The
internal `GET /credit/query/loans-eligible-for-fee` endpoint is also tested.

**Architecture:** Follows `tests/modules/savings/test_api.py` exactly — ASGITransport
client, `app.dependency_overrides[get_tenant_session]`, `X-Tenant-Slug` + `X-Actor-ID`
headers. All tests share a single `client` fixture.

**Tech Stack:** FastAPI, httpx, pytest-asyncio

---

## Required Reading

- Sub-plans 01–11 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §10 (API Endpoints)
- `app/modules/credit/api.py` — current state (check which endpoints are already wired)
- `tests/modules/savings/test_api.py` — API test pattern (client fixture, helpers)
- `app/modules/fees/api.py` — router pattern with `get_actor_id` dependency

---

## File Map

```
Modified
  app/modules/credit/api.py      ensure all 18 endpoints wired
  app/modules/credit/schemas.py  ensure all response schemas present

New
  tests/modules/credit/test_api.py   API integration tests
```

---

## Task 1 — Verify and Complete `api.py`

**Files:**
- Modify: `app/modules/credit/api.py`

- [ ] **Step 1: Audit existing endpoints**

Read `app/modules/credit/api.py` and verify the following routes exist. Add any that are
missing, following the patterns already in the file.

Required endpoints (all require `X-Tenant-Slug` + `X-Actor-ID` headers):

| Method | Path | Handler function | Service |
|--------|------|-----------------|---------|
| `POST` | `/credit/products` | `create_product` | `LoanProductService.create` |
| `GET` | `/credit/products` | `list_products` | `LoanProductService.list` |
| `GET` | `/credit/products/{id}` | `get_product` | `LoanProductService.get` → 404 if None |
| `PATCH` | `/credit/products/{id}` | `update_product` | `LoanProductService.update` |
| `POST` | `/credit/applications` | `submit_application` | `LoanApplicationService.submit` |
| `GET` | `/credit/applications` | `list_applications` | `LoanApplicationService.list` |
| `GET` | `/credit/applications/{id}` | `get_application` | `LoanApplicationService.get` → 404 if None |
| `POST` | `/credit/applications/{id}/withdraw` | `withdraw_application` | `LoanApplicationService.withdraw` |
| `POST` | `/credit/applications/{id}/approve` | `approve_application` | `LoanApplicationService.approve` |
| `POST` | `/credit/applications/{id}/reject` | `reject_application` | `LoanApplicationService.reject` |
| `POST` | `/credit/loans/{application_id}/disburse` | `disburse_loan` | `LoanDisbursementService.disburse` |
| `GET` | `/credit/loans` | `list_loans` | direct select |
| `GET` | `/credit/loans/{id}` | `get_loan` | direct select → 404 if None |
| `GET` | `/credit/loans/{id}/schedule` | `get_schedule` | direct select |
| `POST` | `/credit/loans/{id}/repayments` | `post_repayment` | `LoanRepaymentService.apply_repayment` |
| `GET` | `/credit/loans/{id}/repayments` | `list_repayments` | `LoanRepaymentService.list_repayments` |
| `POST` | `/credit/loans/{id}/write-off` | `write_off_loan` | `LoanWriteOffService.write_off` |
| `GET` | `/credit/query/loans-eligible-for-fee` | `loans_eligible_for_fee` | `CreditQueryService.find_loans_eligible_for_fee` |

For the `GET /credit/loans` endpoint, add to `api.py`:

```python
@router.get("/loans", response_model=list[LoanOut])
async def list_loans(
    member_id: uuid.UUID | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[LoanOut]:
    stmt = select(Loan)
    if member_id is not None:
        stmt = stmt.where(Loan.member_id == member_id)
    if status is not None:
        stmt = stmt.where(Loan.status == status)
    loans = list((await session.execute(stmt)).scalars().all())
    return [LoanOut.model_validate(l) for l in loans]
```

For `GET /credit/query/loans-eligible-for-fee`, add to `api.py`:

```python
@router.get("/query/loans-eligible-for-fee", response_model=list[dict])
async def loans_eligible_for_fee(
    min_days_past_due: int = 0,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[dict]:
    svc = CreditQueryService(session)
    return await svc.find_loans_eligible_for_fee(
        as_of_date=date.today(),
        min_days_past_due=min_days_past_due,
    )
```

For the `GET /credit/loans/{id}` endpoint add 404 handling:

```python
@router.get("/loans/{loan_id}", response_model=LoanOut)
async def get_loan(
    loan_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_session),
) -> LoanOut:
    loan = await session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    return LoanOut.model_validate(loan)
```

Ensure `from fastapi import HTTPException` is imported at the top of `api.py`.

- [ ] **Step 2: Verify app starts**

```bash
python -c "from app.modules.credit.api import router; print(f'{len(router.routes)} routes registered')"
```

Expected: prints `18 routes registered` (or similar non-zero number — count may vary
slightly depending on path parameter vs query parameter routes).

- [ ] **Step 3: Commit**

```bash
git add app/modules/credit/api.py app/modules/credit/schemas.py
git commit -m "feat(credit): complete all 18 API endpoints"
```

---

## Task 2 — Write API Integration Tests

**Files:**
- Create: `tests/modules/credit/test_api.py`

- [ ] **Step 1: Create `tests/modules/credit/test_api.py`**

```python
# tests/modules/credit/test_api.py
"""API integration tests for the credit module.

One test per endpoint. Uses ASGITransport + real Postgres (test_engine fixture).
"""
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

TEST_TENANT_SCHEMA = "tenant_test"
ACTOR_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-Slug": "test-tenant", "X-Actor-ID": ACTOR_ID}


async def _make_session_override(engine: AsyncEngine):
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
async def client(test_engine: AsyncEngine):
    override = await _make_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


# ── Setup helpers ─────────────────────────────────────────────────────────────


async def _create_gl_account(client, code: str, name: str, account_type: str) -> str:
    resp = await client.post(
        "/ledger/accounts",
        json={"code": code, "name": name, "account_type": account_type},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_member(client) -> str:
    resp = await client.post(
        "/members",
        json={
            "full_name": f"Test Member {uuid.uuid4().hex[:6]}",
            "date_of_birth": "1985-01-01",
            "gender": "male",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_loan_product(client, principal_recv_id: str, interest_recv_id: str, interest_income_id: str) -> str:
    resp = await client.post(
        "/credit/products",
        json={
            "name": "Test Loan Product",
            "interest_method": "flat",
            "annual_interest_rate": "12.0000",
            "repayment_frequency": "monthly",
            "max_term_periods": 24,
            "min_amount": "1000.0000",
            "max_amount": "100000.0000",
            "required_approvals": 1,
            "disbursement_destinations": ["cash"],
            "repayment_allocation": "INTEREST_PRINCIPAL",
            "gl_principal_receivable_code": "LOAN-PRINCIPAL-RECV",
            "gl_interest_receivable_code": "LOAN-INTEREST-RECV",
            "gl_interest_income_code": "LOAN-INTEREST-INCOME",
            "write_off_threshold": "0.0000",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _setup_gl_and_product(client) -> dict:
    """Create GL accounts and a loan product. Returns dict of ids."""
    principal_recv_id = await _create_gl_account(
        client, "LOAN-PRINCIPAL-RECV", "Loans Principal Receivable", "asset"
    )
    interest_recv_id = await _create_gl_account(
        client, "LOAN-INTEREST-RECV", "Loans Interest Receivable", "asset"
    )
    interest_income_id = await _create_gl_account(
        client, "LOAN-INTEREST-INCOME", "Loan Interest Income", "income"
    )
    disbursement_acct_id = await _create_gl_account(
        client, "CASH-DISBURSEMENT", "Cash Disbursement Account", "asset"
    )
    loan_loss_id = await _create_gl_account(
        client, "LOAN-LOSS-EXPENSE", "Loan Loss Expense", "expense"
    )
    product_id = await _create_loan_product(
        client, principal_recv_id, interest_recv_id, interest_income_id
    )
    member_id = await _create_member(client)
    return {
        "principal_recv_id": principal_recv_id,
        "interest_recv_id": interest_recv_id,
        "interest_income_id": interest_income_id,
        "disbursement_acct_id": disbursement_acct_id,
        "loan_loss_id": loan_loss_id,
        "product_id": product_id,
        "member_id": member_id,
    }


async def _submit_application(client, ids: dict) -> str:
    resp = await client.post(
        "/credit/applications",
        json={
            "loan_product_id": ids["product_id"],
            "member_id": ids["member_id"],
            "requested_amount": "5000.0000",
            "requested_term_periods": 12,
            "disbursement_destination": "cash",
            "disbursement_account_id": ids["disbursement_acct_id"],
            "idempotency_key": f"app-{uuid.uuid4()}",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _approve_application(client, application_id: str) -> None:
    resp = await client.post(
        f"/credit/applications/{application_id}/approve",
        json={"approved_amount": "5000.0000", "approved_term_periods": 12},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text


async def _disburse_loan(client, application_id: str) -> str:
    resp = await client.post(
        f"/credit/loans/{application_id}/disburse",
        json={"idempotency_key": f"disb-{uuid.uuid4()}"},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── Product endpoints ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_product_201(client):
    """POST /credit/products → 201."""
    await _create_gl_account(client, "LOAN-PRINCIPAL-RECV", "Loans Principal Receivable", "asset")
    await _create_gl_account(client, "LOAN-INTEREST-RECV", "Loans Interest Receivable", "asset")
    await _create_gl_account(client, "LOAN-INTEREST-INCOME", "Loan Interest Income", "income")

    resp = await client.post(
        "/credit/products",
        json={
            "name": "Standard Loan",
            "interest_method": "reducing_balance",
            "annual_interest_rate": "18.0000",
            "repayment_frequency": "monthly",
            "max_term_periods": 36,
            "min_amount": "500.0000",
            "max_amount": "50000.0000",
            "required_approvals": 1,
            "disbursement_destinations": ["cash"],
            "repayment_allocation": "INTEREST_PRINCIPAL",
            "gl_principal_receivable_code": "LOAN-PRINCIPAL-RECV",
            "gl_interest_receivable_code": "LOAN-INTEREST-RECV",
            "gl_interest_income_code": "LOAN-INTEREST-INCOME",
            "write_off_threshold": "0.0000",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Standard Loan"


@pytest.mark.asyncio
async def test_get_products_200(client):
    """GET /credit/products → 200, list."""
    ids = await _setup_gl_and_product(client)
    resp = await client.get("/credit/products", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(p["id"] == ids["product_id"] for p in data)


@pytest.mark.asyncio
async def test_get_product_by_id_200(client):
    """GET /credit/products/{id} → 200."""
    ids = await _setup_gl_and_product(client)
    resp = await client.get(f"/credit/products/{ids['product_id']}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == ids["product_id"]


@pytest.mark.asyncio
async def test_get_product_unknown_id_404(client):
    """GET /credit/products/{unknown_id} → 404."""
    resp = await client.get(f"/credit/products/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


# ── Application endpoints ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_application_201(client):
    """POST /credit/applications → 201, status=submitted."""
    ids = await _setup_gl_and_product(client)
    application_id = await _submit_application(client, ids)

    resp = await client.get(f"/credit/applications/{application_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "submitted"


@pytest.mark.asyncio
async def test_get_applications_200(client):
    """GET /credit/applications → 200, list."""
    ids = await _setup_gl_and_product(client)
    await _submit_application(client, ids)
    resp = await client.get("/credit/applications", headers=HEADERS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_approve_application_200(client):
    """POST /credit/applications/{id}/approve → 200, quorum=1 → status=approved."""
    ids = await _setup_gl_and_product(client)
    application_id = await _submit_application(client, ids)
    await _approve_application(client, application_id)

    resp = await client.get(f"/credit/applications/{application_id}", headers=HEADERS)
    assert resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_reject_application_200(client):
    """POST /credit/applications/{id}/reject → 200, status=rejected."""
    ids = await _setup_gl_and_product(client)
    application_id = await _submit_application(client, ids)

    resp = await client.post(
        f"/credit/applications/{application_id}/reject",
        json={"rejection_reason": "Insufficient income"},
        headers=HEADERS,
    )
    assert resp.status_code == 200

    resp2 = await client.get(f"/credit/applications/{application_id}", headers=HEADERS)
    assert resp2.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_withdraw_application_200(client):
    """POST /credit/applications/{id}/withdraw → 200."""
    ids = await _setup_gl_and_product(client)
    application_id = await _submit_application(client, ids)

    resp = await client.post(
        f"/credit/applications/{application_id}/withdraw",
        headers=HEADERS,
    )
    assert resp.status_code == 200


# ── Loan endpoints ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disburse_loan_201(client):
    """POST /credit/loans/{application_id}/disburse → 201, outstanding_principal set."""
    ids = await _setup_gl_and_product(client)
    application_id = await _submit_application(client, ids)
    await _approve_application(client, application_id)

    resp = await client.post(
        f"/credit/loans/{application_id}/disburse",
        json={"idempotency_key": f"disb-{uuid.uuid4()}"},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert Decimal(data["outstanding_principal"]) == Decimal("5000.0000")
    assert data["status"] == "disbursed"


@pytest.mark.asyncio
async def test_get_loan_200(client):
    """GET /credit/loans/{id} → 200, balance fields present."""
    ids = await _setup_gl_and_product(client)
    application_id = await _submit_application(client, ids)
    await _approve_application(client, application_id)
    loan_id = await _disburse_loan(client, application_id)

    resp = await client.get(f"/credit/loans/{loan_id}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "outstanding_principal" in data
    assert "accrued_interest" in data
    assert "status" in data


@pytest.mark.asyncio
async def test_get_loan_unknown_id_404(client):
    """GET /credit/loans/{unknown_id} → 404."""
    resp = await client.get(f"/credit/loans/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_schedule_200(client):
    """GET /credit/loans/{id}/schedule → 200, installment list, SUM(total_due) > 0."""
    ids = await _setup_gl_and_product(client)
    application_id = await _submit_application(client, ids)
    await _approve_application(client, application_id)
    loan_id = await _disburse_loan(client, application_id)

    resp = await client.get(f"/credit/loans/{loan_id}/schedule", headers=HEADERS)
    assert resp.status_code == 200
    installments = resp.json()
    assert len(installments) == 12  # 12 monthly periods
    total_due = sum(Decimal(i["total_due"]) for i in installments)
    assert total_due > Decimal("5000")


@pytest.mark.asyncio
async def test_post_repayment_201(client):
    """POST /credit/loans/{id}/repayments → 201."""
    ids = await _setup_gl_and_product(client)
    application_id = await _submit_application(client, ids)
    await _approve_application(client, application_id)
    loan_id = await _disburse_loan(client, application_id)

    resp = await client.post(
        f"/credit/loans/{loan_id}/repayments",
        json={
            "amount": "500.0000",
            "payment_account_id": ids["disbursement_acct_id"],
            "idempotency_key": f"rpy-{uuid.uuid4()}",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert Decimal(data["amount"]) == Decimal("500.0000")


@pytest.mark.asyncio
async def test_get_repayments_200(client):
    """GET /credit/loans/{id}/repayments → 200, list."""
    ids = await _setup_gl_and_product(client)
    application_id = await _submit_application(client, ids)
    await _approve_application(client, application_id)
    loan_id = await _disburse_loan(client, application_id)

    await client.post(
        f"/credit/loans/{loan_id}/repayments",
        json={
            "amount": "250.0000",
            "payment_account_id": ids["disbursement_acct_id"],
            "idempotency_key": f"rpy-{uuid.uuid4()}",
        },
        headers=HEADERS,
    )

    resp = await client.get(f"/credit/loans/{loan_id}/repayments", headers=HEADERS)
    assert resp.status_code == 200
    repayments = resp.json()
    assert len(repayments) == 1


@pytest.mark.asyncio
async def test_write_off_below_threshold_201(client):
    """POST /credit/loans/{id}/write-off (below threshold) → 201, direct=true."""
    ids = await _setup_gl_and_product(client)
    # Update product to set high write_off_threshold so any amount is direct.
    # (Product write_off_threshold defaults to 0 → need to update via PATCH)
    resp = await client.patch(
        f"/credit/products/{ids['product_id']}",
        json={"write_off_threshold": "999999.0000"},
        headers=HEADERS,
    )
    assert resp.status_code == 200

    application_id = await _submit_application(client, ids)
    await _approve_application(client, application_id)
    loan_id = await _disburse_loan(client, application_id)

    resp = await client.post(
        f"/credit/loans/{loan_id}/write-off",
        json={
            "amount": "100.0000",
            "reason": "Test write-off",
            "idempotency_key": f"wo-{uuid.uuid4()}",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["direct"] is True


@pytest.mark.asyncio
async def test_missing_tenant_header_422(client):
    """Missing X-Tenant-Slug header → 422 or error response."""
    resp = await client.get("/credit/products")  # no headers
    assert resp.status_code in (422, 400, 401)


@pytest.mark.asyncio
async def test_loans_eligible_for_fee_200(client):
    """GET /credit/query/loans-eligible-for-fee → 200."""
    resp = await client.get(
        "/credit/query/loans-eligible-for-fee",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Run API tests**

```bash
pytest tests/modules/credit/test_api.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add tests/modules/credit/test_api.py
git commit -m "test(credit): API integration tests — one test per endpoint"
```

---

## Verification Criteria

```bash
# 1. All API tests pass
pytest tests/modules/credit/test_api.py -v

# 2. Full suite — no regressions
pytest -x -q
```

All commands must exit 0. Confirm:
- `POST /credit/products` → 201
- `GET /credit/products` → 200, list
- `GET /credit/products/{id}` → 200; unknown id → 404
- `POST /credit/applications` → 201, status=`submitted`
- `POST /credit/applications/{id}/approve` → 200 (quorum=1 → status=`approved`)
- `POST /credit/applications/{id}/reject` → 200, status=`rejected`
- `POST /credit/applications/{id}/withdraw` → 200
- `POST /credit/loans/{application_id}/disburse` → 201, `outstanding_principal` = amount
- `GET /credit/loans/{id}` → 200, balance fields present; unknown id → 404
- `GET /credit/loans/{id}/schedule` → 200, installment list, `SUM(total_due)` > disbursed amount
- `POST /credit/loans/{id}/repayments` → 201
- `GET /credit/loans/{id}/repayments` → 200, list
- `POST /credit/loans/{id}/write-off` (below threshold) → 201, `direct=true`
- Missing `X-Tenant-Slug` → 422/400/401
- `GET /credit/query/loans-eligible-for-fee` → 200, list
