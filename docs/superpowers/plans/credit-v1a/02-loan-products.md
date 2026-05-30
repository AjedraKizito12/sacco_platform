# Sub-plan 02 — Loan Products

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Implement `LoanProductService` (create, get, list, deactivate, update), Pydantic
schemas, and the four product API endpoints. No GL posting, no disbursement, no other
credit resources — pure product configuration CRUD.

**Architecture:** `LoanProductService` validates business rules (min_amount ≤ max_amount,
rate ≥ 0, required_approvals ≥ 1, valid enum values) then creates/reads/updates
`loan_products` rows. GL account codes are stored as text only at this stage —
they are resolved to UUIDs at disbursement time (sub-plan 04). The API router
delegates entirely to the service with a TODO stub for actor identity (wired in sub-plan 12).

**Tech Stack:** SQLAlchemy 2.0 async, pytest-asyncio, Pydantic v2, FastAPI

---

## Required Reading

Before starting, read these files in full:

- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §3.1, §10
- `app/modules/fees/service.py` — CRUD service pattern
- `app/modules/fees/api.py` — router + error mapping pattern
- `app/modules/fees/schemas.py` — Pydantic schema pattern
- `tests/modules/savings/test_service.py` lines 1–80 — `_new_session` / `_cleanup` helper pattern

---

## File Map

```
New
  app/modules/credit/services/product.py     LoanProductService
  app/modules/credit/schemas.py              product schemas (initial — more added in 03, 04, 07, 10)
  app/modules/credit/api.py                  product endpoints (initial — more added in 03, 04, 07, 10)
  tests/modules/credit/test_service.py       product integration tests (more tests added in later sub-plans)
```

No modifications to existing files in this sub-plan.

---

## Task 1 — `LoanProductService.create` (TDD)

**Files:**
- Create: `tests/modules/credit/test_service.py`
- Create: `app/modules/credit/services/product.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/credit/test_service.py`:

```python
# tests/modules/credit/test_service.py
"""Integration tests for credit module services.

Uses async_sessionmaker + commit + cleanup pattern (not rollback fixture)
to avoid asyncpg protocol-state errors with flush().
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.credit.models import (
    Loan,
    LoanApplication,
    LoanInstallment,
    LoanProduct,
    LoanRepayment,
)
from app.modules.credit.services.product import LoanProductService

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
    from sqlalchemy import event as sa_event

    session = _factory(engine)()

    @sa_event.listens_for(session.sync_session, "after_begin")
    def _reapply_search_path(sess, transaction, connection):  # type: ignore[misc]
        connection.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )

    await session.execute(
        text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
    )
    return session


async def _cleanup(engine: AsyncEngine) -> None:
    """Delete all credit + related rows in dependency order."""
    async with _factory(engine)() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(delete(LoanRepayment))
        await session.execute(delete(LoanInstallment))
        await session.execute(delete(Loan))
        await session.execute(delete(LoanApplication))
        await session.execute(delete(LoanProduct))
        await session.commit()


def _product_kwargs(**overrides) -> dict:
    """Minimal valid kwargs for LoanProductService.create."""
    defaults = dict(
        name="Standard Loan",
        description=None,
        interest_method="flat",
        annual_interest_rate=Decimal("18.0000"),
        repayment_frequency="monthly",
        max_term_periods=24,
        min_amount=Decimal("50000"),
        max_amount=Decimal("5000000"),
        required_approvals=1,
        disbursement_destinations=["member_savings", "cash"],
        repayment_allocation="INTEREST_PRINCIPAL",
        gl_principal_receivable_code="1300",
        gl_interest_receivable_code="1310",
        gl_interest_income_code="4100",
        gl_loan_loss_expense_code=None,
        penalty_fee_type_code=None,
        write_off_threshold=Decimal("0"),
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    return defaults


@pytest.mark.asyncio
async def test_create_loan_product_success(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        product = await svc.create(**_product_kwargs(name="Test Loan Product"))
        await session.commit()

        assert product.id is not None
        assert product.name == "Test Loan Product"
        assert product.interest_method == "flat"
        assert product.annual_interest_rate == Decimal("18.0000")
        assert product.is_active is True
        assert "member_savings" in product.disbursement_destinations
        assert product.repayment_allocation == "INTEREST_PRINCIPAL"
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_create_loan_product_min_gt_max_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        with pytest.raises(ValueError, match="min_amount"):
            await svc.create(
                **_product_kwargs(
                    min_amount=Decimal("1000000"),
                    max_amount=Decimal("500000"),
                )
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_create_loan_product_negative_rate_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        with pytest.raises(ValueError, match="annual_interest_rate"):
            await svc.create(**_product_kwargs(annual_interest_rate=Decimal("-1")))
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_create_loan_product_required_approvals_lt_1_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        with pytest.raises(ValueError, match="required_approvals"):
            await svc.create(**_product_kwargs(required_approvals=0))
    finally:
        await session.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_service.py -k "product" -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.modules.credit.services.product'`

- [ ] **Step 3: Create `app/modules/credit/services/product.py`**

```python
# app/modules/credit/services/product.py
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import LoanProduct

_log = structlog.get_logger(__name__)

_VALID_INTEREST_METHODS = frozenset({"flat", "reducing_balance"})
_VALID_FREQUENCIES = frozenset({"weekly", "biweekly", "monthly", "quarterly"})
_VALID_DESTINATIONS = frozenset({"member_savings", "cash", "internal_gl"})


class LoanProductService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        name: str,
        description: str | None = None,
        interest_method: str,
        annual_interest_rate: Decimal,
        repayment_frequency: str,
        max_term_periods: int,
        min_amount: Decimal,
        max_amount: Decimal,
        required_approvals: int = 1,
        disbursement_destinations: list[str],
        repayment_allocation: str = "INTEREST_PRINCIPAL",
        gl_principal_receivable_code: str,
        gl_interest_receivable_code: str,
        gl_interest_income_code: str,
        gl_loan_loss_expense_code: str | None = None,
        penalty_fee_type_code: str | None = None,
        write_off_threshold: Decimal = Decimal("0"),
        created_by: uuid.UUID,
    ) -> LoanProduct:
        """Create and persist a new loan product. Validates all business rules."""
        if interest_method not in _VALID_INTEREST_METHODS:
            raise ValueError(
                f"interest_method must be one of: {sorted(_VALID_INTEREST_METHODS)}"
            )
        if repayment_frequency not in _VALID_FREQUENCIES:
            raise ValueError(
                f"repayment_frequency must be one of: {sorted(_VALID_FREQUENCIES)}"
            )
        if annual_interest_rate < Decimal("0"):
            raise ValueError("annual_interest_rate must be >= 0")
        if min_amount <= Decimal("0"):
            raise ValueError("min_amount must be > 0")
        if max_amount < min_amount:
            raise ValueError("max_amount must be >= min_amount")
        if max_term_periods < 1:
            raise ValueError("max_term_periods must be >= 1")
        if required_approvals < 1:
            raise ValueError("required_approvals must be >= 1")
        if write_off_threshold < Decimal("0"):
            raise ValueError("write_off_threshold must be >= 0")
        if not disbursement_destinations:
            raise ValueError("disbursement_destinations must not be empty")
        invalid_destinations = set(disbursement_destinations) - _VALID_DESTINATIONS
        if invalid_destinations:
            raise ValueError(
                f"Invalid disbursement_destinations: {invalid_destinations}. "
                f"Valid values: {sorted(_VALID_DESTINATIONS)}"
            )

        product = LoanProduct(
            name=name,
            description=description,
            interest_method=interest_method,
            annual_interest_rate=annual_interest_rate,
            repayment_frequency=repayment_frequency,
            max_term_periods=max_term_periods,
            min_amount=min_amount,
            max_amount=max_amount,
            required_approvals=required_approvals,
            disbursement_destinations=disbursement_destinations,
            repayment_allocation=repayment_allocation,
            gl_principal_receivable_code=gl_principal_receivable_code,
            gl_interest_receivable_code=gl_interest_receivable_code,
            gl_interest_income_code=gl_interest_income_code,
            gl_loan_loss_expense_code=gl_loan_loss_expense_code,
            penalty_fee_type_code=penalty_fee_type_code,
            write_off_threshold=write_off_threshold,
        )
        self._session.add(product)
        await self._session.flush()
        _log.info(
            "loan_product.created",
            product_id=str(product.id),
            name=name,
            interest_method=interest_method,
            created_by=str(created_by),
        )
        return product

    async def get(self, product_id: uuid.UUID) -> LoanProduct:
        p = await self._session.get(LoanProduct, product_id)
        if p is None:
            raise ValueError(f"LoanProduct '{product_id}' not found")
        return p

    async def list(self, *, include_inactive: bool = False) -> list[LoanProduct]:
        q = select(LoanProduct).order_by(LoanProduct.name)
        if not include_inactive:
            q = q.where(LoanProduct.is_active.is_(True))
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def update(
        self,
        product_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        penalty_fee_type_code: str | None = None,
        write_off_threshold: Decimal | None = None,
        updated_by: uuid.UUID,
    ) -> LoanProduct:
        """Patch non-financial fields only. Financial/structural fields (rates,
        amounts, GL codes, interest method) are immutable after creation to
        protect the snapshots on existing loan rows."""
        p = await self.get(product_id)
        if name is not None:
            p.name = name
        if description is not None:
            p.description = description
        if penalty_fee_type_code is not None:
            p.penalty_fee_type_code = penalty_fee_type_code
        if write_off_threshold is not None:
            if write_off_threshold < Decimal("0"):
                raise ValueError("write_off_threshold must be >= 0")
            p.write_off_threshold = write_off_threshold
        await self._session.flush()
        _log.info(
            "loan_product.updated",
            product_id=str(product_id),
            updated_by=str(updated_by),
        )
        return p

    async def deactivate(
        self, product_id: uuid.UUID, *, deactivated_by: uuid.UUID
    ) -> LoanProduct:
        p = await self.get(product_id)
        p.is_active = False
        await self._session.flush()
        _log.info(
            "loan_product.deactivated",
            product_id=str(product_id),
            deactivated_by=str(deactivated_by),
        )
        return p
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/modules/credit/test_service.py -k "product" -v
```

Expected: 4 tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/services/product.py tests/modules/credit/test_service.py
git commit -m "feat(credit): LoanProductService + create/validation tests"
```

---

## Task 2 — Get, List, Deactivate, Update Tests

**Files:**
- Modify: `tests/modules/credit/test_service.py`

The service methods `get`, `list`, `deactivate`, and `update` were already implemented
in Task 1. This task writes and runs the integration tests for them.

- [ ] **Step 1: Append tests to `tests/modules/credit/test_service.py`**

```python
@pytest.mark.asyncio
async def test_get_loan_product_success(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        created = await svc.create(**_product_kwargs(name="Get Test Product"))
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanProductService(session2)
        fetched = await svc2.get(created.id)
        assert fetched.id == created.id
        assert fetched.name == "Get Test Product"
        assert fetched.interest_method == "flat"
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_get_unknown_product_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        with pytest.raises(ValueError, match="not found"):
            await svc.get(uuid.uuid4())
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_list_products_active_only_by_default(test_engine):
    actor = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        p_active = await svc.create(**_product_kwargs(name="Active Product", created_by=actor))
        p_inactive = await svc.create(**_product_kwargs(name="Inactive Product", created_by=actor))
        await svc.deactivate(p_inactive.id, deactivated_by=actor)
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanProductService(session2)
        active_list = await svc2.list(include_inactive=False)
        all_list = await svc2.list(include_inactive=True)
        active_ids = {p.id for p in active_list}
        all_ids = {p.id for p in all_list}
        assert p_active.id in active_ids
        assert p_inactive.id not in active_ids
        assert p_active.id in all_ids
        assert p_inactive.id in all_ids
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_deactivate_product(test_engine):
    actor = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        product = await svc.create(**_product_kwargs(name="To Deactivate", created_by=actor))
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanProductService(session2)
        deactivated = await svc2.deactivate(product.id, deactivated_by=actor)
        await session2.commit()
        assert deactivated.is_active is False
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_update_product_name(test_engine):
    actor = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        product = await svc.create(**_product_kwargs(name="Original Name", created_by=actor))
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanProductService(session2)
        updated = await svc2.update(product.id, name="Updated Name", updated_by=actor)
        await session2.commit()
        assert updated.name == "Updated Name"
        # Immutable financial fields unchanged
        assert updated.annual_interest_rate == Decimal("18.0000")
        assert updated.min_amount == Decimal("50000")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_update_write_off_threshold(test_engine):
    actor = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        product = await svc.create(**_product_kwargs(write_off_threshold=Decimal("0")))
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanProductService(session2)
        updated = await svc2.update(
            product.id,
            write_off_threshold=Decimal("100000"),
            updated_by=actor,
        )
        await session2.commit()
        assert updated.write_off_threshold == Decimal("100000")
    finally:
        await session2.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run all product tests**

```bash
pytest tests/modules/credit/test_service.py -k "product" -v
```

Expected: all 10 product tests `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add tests/modules/credit/test_service.py
git commit -m "test(credit): LoanProductService.get, list, deactivate, update tests"
```

---

## Task 3 — Product Schemas

**Files:**
- Create: `app/modules/credit/schemas.py`

- [ ] **Step 1: Create `app/modules/credit/schemas.py`**

```python
# app/modules/credit/schemas.py
"""Pydantic v2 schemas for the credit module.

Organised by sub-resource. Additional schemas are appended in subsequent
sub-plans: applications (03), disbursement (04), repayment (07), write-off (10).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ── Loan Products ─────────────────────────────────────────────────────────────


class LoanProductOut(BaseModel):
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
    required_approvals: int
    disbursement_destinations: list[str]
    repayment_allocation: str
    gl_principal_receivable_code: str
    gl_interest_receivable_code: str
    gl_interest_income_code: str
    gl_loan_loss_expense_code: str | None
    penalty_fee_type_code: str | None
    write_off_threshold: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoanProductCreateIn(BaseModel):
    name: str
    description: str | None = None
    interest_method: str
    annual_interest_rate: Decimal
    repayment_frequency: str
    max_term_periods: int
    min_amount: Decimal
    max_amount: Decimal
    required_approvals: int = 1
    disbursement_destinations: list[str]
    repayment_allocation: str = "INTEREST_PRINCIPAL"
    gl_principal_receivable_code: str
    gl_interest_receivable_code: str
    gl_interest_income_code: str
    gl_loan_loss_expense_code: str | None = None
    penalty_fee_type_code: str | None = None
    write_off_threshold: Decimal = Decimal("0")


class LoanProductPatchIn(BaseModel):
    name: str | None = None
    description: str | None = None
    penalty_fee_type_code: str | None = None
    write_off_threshold: Decimal | None = None
```

- [ ] **Step 2: Verify schemas import**

```bash
python -c "from app.modules.credit.schemas import LoanProductOut, LoanProductCreateIn, LoanProductPatchIn; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/modules/credit/schemas.py
git commit -m "feat(credit): Pydantic schemas — LoanProductOut, LoanProductCreateIn, LoanProductPatchIn"
```

---

## Task 4 — Product API Endpoints

**Files:**
- Create: `app/modules/credit/api.py`

Note: The credit router is **not** wired into `app/main.py` yet — that happens in sub-plan 13 when all endpoints exist. This step creates the router file and verifies it imports cleanly.

- [ ] **Step 1: Create `app/modules/credit/api.py`**

```python
# app/modules/credit/api.py
"""Credit module FastAPI router.

Product endpoints are implemented here (sub-plan 02).
Remaining endpoints are added in sub-plans 03, 04, 07, 10, 12.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.credit.schemas import (
    LoanProductCreateIn,
    LoanProductOut,
    LoanProductPatchIn,
)
from app.modules.credit.services.product import LoanProductService

router = APIRouter(prefix="/credit", tags=["credit"])
Session = Annotated[AsyncSession, Depends(get_tenant_session)]


# ── Loan Products ─────────────────────────────────────────────────────────────


@router.post("/products", response_model=LoanProductOut, status_code=201)
async def create_loan_product(body: LoanProductCreateIn, session: Session) -> LoanProductOut:
    try:
        svc = LoanProductService(session)
        product = await svc.create(
            name=body.name,
            description=body.description,
            interest_method=body.interest_method,
            annual_interest_rate=body.annual_interest_rate,
            repayment_frequency=body.repayment_frequency,
            max_term_periods=body.max_term_periods,
            min_amount=body.min_amount,
            max_amount=body.max_amount,
            required_approvals=body.required_approvals,
            disbursement_destinations=body.disbursement_destinations,
            repayment_allocation=body.repayment_allocation,
            gl_principal_receivable_code=body.gl_principal_receivable_code,
            gl_interest_receivable_code=body.gl_interest_receivable_code,
            gl_interest_income_code=body.gl_interest_income_code,
            gl_loan_loss_expense_code=body.gl_loan_loss_expense_code,
            penalty_fee_type_code=body.penalty_fee_type_code,
            write_off_threshold=body.write_off_threshold,
            created_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LoanProductOut.model_validate(product)


@router.get("/products", response_model=list[LoanProductOut])
async def list_loan_products(
    session: Session,
    include_inactive: bool = Query(default=False),
) -> list[LoanProductOut]:
    svc = LoanProductService(session)
    products = await svc.list(include_inactive=include_inactive)
    return [LoanProductOut.model_validate(p) for p in products]


@router.get("/products/{product_id}", response_model=LoanProductOut)
async def get_loan_product(product_id: uuid.UUID, session: Session) -> LoanProductOut:
    try:
        svc = LoanProductService(session)
        product = await svc.get(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LoanProductOut.model_validate(product)


@router.patch("/products/{product_id}", response_model=LoanProductOut)
async def patch_loan_product(
    product_id: uuid.UUID,
    body: LoanProductPatchIn,
    session: Session,
) -> LoanProductOut:
    try:
        svc = LoanProductService(session)
        product = await svc.update(
            product_id,
            name=body.name,
            description=body.description,
            penalty_fee_type_code=body.penalty_fee_type_code,
            write_off_threshold=body.write_off_threshold,
            updated_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanProductOut.model_validate(product)
```

- [ ] **Step 2: Verify API module imports without errors**

```bash
python -c "from app.modules.credit.api import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/modules/credit/api.py
git commit -m "feat(credit): product API endpoints — POST/GET/PATCH /credit/products"
```

---

## Verification Criteria

Run all of the following before marking this sub-plan complete:

```bash
# 1. All product service tests pass
pytest tests/modules/credit/test_service.py -k "product" -v

# 2. Full test suite — no regressions
pytest -x -q

# 3. All imports clean
python -c "
from app.modules.credit.services.product import LoanProductService
from app.modules.credit.schemas import LoanProductOut, LoanProductCreateIn, LoanProductPatchIn
from app.modules.credit.api import router
print('All imports OK')
"
```

All commands must exit 0. Confirm the following are enforced by the service tests:
- `min_amount > max_amount` → `ValueError` matching `"min_amount"`
- `annual_interest_rate < 0` → `ValueError` matching `"annual_interest_rate"`
- `required_approvals < 1` → `ValueError` matching `"required_approvals"`
- Unknown `product_id` → `ValueError` matching `"not found"`
