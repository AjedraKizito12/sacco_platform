# Sub-plan 02 — Guarantors

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans`.

**Goal:** Implement `GuarantorService` (nominate, accept, decline, place_liens, adjust_liens,
release_liens, reactivate_liens), add `SavingsService.get_available_balance`, and wire
guarantor API endpoints.

**Architecture:** `GuarantorService` lives in `app/modules/credit/services/guarantor.py`.
It is called by disbursement, repayment, and write-off services (wired in sub-plan 07).
`SavingsService.get_available_balance` reads from `loan_guarantor_liens` directly —
the credit module is imported locally inside the method to avoid circular imports.

**Tech Stack:** SQLAlchemy 2.0 async, FastAPI, Pydantic v2, pytest-asyncio

---

## Required Reading

- `app/modules/credit/models.py` — `LoanGuarantor`, `LoanGuarantorLien`, `LoanProduct`
- `app/modules/savings/service.py` — `get_balance`, `get_primary_account_for_member`
- `app/modules/credit/services/repayment.py` — `apply_repayment` (shows session pattern)
- `app/modules/credit/api.py` — existing endpoint pattern

---

## Task 1: GuarantorService — nominate and consent

**Files:**
- Create: `app/modules/credit/services/guarantor.py`
- Create: `tests/modules/credit/test_guarantor_service.py`

- [ ] **Step 1: Write failing tests for nominate + accept + decline**

```python
# tests/modules/credit/test_guarantor_service.py
"""Tests for GuarantorService — nominate, accept, decline, lien lifecycle."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.credit.models import LoanGuarantor, LoanProduct, LoanApplication


TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _create_product(session: AsyncSession, required_guarantors: int = 1) -> LoanProduct:
    from app.modules.ledger.models import ChartOfAccount
    acct = await session.scalar(select(ChartOfAccount).limit(1))
    assert acct is not None, "Need at least one GL account in test DB"
    product = LoanProduct(
        name="Guarantor Test Product",
        interest_method="flat",
        annual_interest_rate=Decimal("12.0000"),
        repayment_frequency="monthly",
        max_term_periods=12,
        min_amount=Decimal("1000.0000"),
        max_amount=Decimal("100000.0000"),
        required_approvals=1,
        required_guarantors=required_guarantors,
        disbursement_destinations=["member_savings"],
        gl_principal_receivable_code="1100",
        gl_interest_receivable_code="1110",
        gl_interest_income_code="4100",
    )
    session.add(product)
    await session.commit()
    return product


async def _create_application(session: AsyncSession, product: LoanProduct) -> LoanApplication:
    app = LoanApplication(
        loan_product_id=product.id,
        member_id=uuid.uuid4(),
        requested_amount=Decimal("10000.0000"),
        requested_term_periods=12,
        disbursement_destination="member_savings",
        status="submitted",
        idempotency_key=str(uuid.uuid4()),
    )
    session.add(app)
    await session.commit()
    return app


@pytest.mark.anyio
async def test_nominate_creates_guarantor_rows(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as session:
        await session.execute(
            __import__("sqlalchemy", fromlist=["text"]).text(
                f"SET LOCAL search_path TO tenant_test, platform"
            )
        )
        product = await _create_product(session, required_guarantors=2)
        application = await _create_application(session, product)
        guarantor_ids = [uuid.uuid4(), uuid.uuid4()]

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=guarantor_ids,
            actor_id=uuid.uuid4(),
        )

    assert len(guarantors) == 2
    assert all(g.status == "nominated" for g in guarantors)
    assert {g.guarantor_member_id for g in guarantors} == set(guarantor_ids)


@pytest.mark.anyio
async def test_nominate_wrong_count_raises(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as session:
        from sqlalchemy import text
        await session.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        product = await _create_product(session, required_guarantors=2)
        application = await _create_application(session, product)

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        with pytest.raises(ValueError, match="requires 2 guarantor"):
            await svc.nominate(
                application_id=application.id,
                guarantor_member_ids=[uuid.uuid4()],  # only 1, need 2
                actor_id=uuid.uuid4(),
            )


@pytest.mark.anyio
async def test_nominate_on_zero_guarantor_product_raises(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as session:
        from sqlalchemy import text
        await session.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        product = await _create_product(session, required_guarantors=0)
        application = await _create_application(session, product)

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        with pytest.raises(ValueError, match="does not require guarantors"):
            await svc.nominate(
                application_id=application.id,
                guarantor_member_ids=[uuid.uuid4()],
                actor_id=uuid.uuid4(),
            )


@pytest.mark.anyio
async def test_accept_sets_accepted_status(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    guarantor_member_id = uuid.uuid4()

    async with factory() as session:
        from sqlalchemy import text
        await session.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        product = await _create_product(session, required_guarantors=1)
        application = await _create_application(session, product)

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=[guarantor_member_id],
            actor_id=uuid.uuid4(),
        )
        lg = guarantors[0]
        await svc.accept(loan_guarantor_id=lg.id, guarantor_member_id=guarantor_member_id)

    async with factory() as session:
        from sqlalchemy import text
        await session.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        row = await session.get(LoanGuarantor, lg.id)
        assert row.status == "accepted"
        assert row.consented_at is not None


@pytest.mark.anyio
async def test_decline_sets_declined_status(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    guarantor_member_id = uuid.uuid4()

    async with factory() as session:
        from sqlalchemy import text
        await session.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        product = await _create_product(session, required_guarantors=1)
        application = await _create_application(session, product)

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=[guarantor_member_id],
            actor_id=uuid.uuid4(),
        )
        lg = guarantors[0]
        await svc.decline(loan_guarantor_id=lg.id, guarantor_member_id=guarantor_member_id)

    async with factory() as session:
        from sqlalchemy import text
        await session.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        row = await session.get(LoanGuarantor, lg.id)
        assert row.status == "declined"


@pytest.mark.anyio
async def test_accept_wrong_member_raises(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    guarantor_member_id = uuid.uuid4()

    async with factory() as session:
        from sqlalchemy import text
        await session.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        product = await _create_product(session, required_guarantors=1)
        application = await _create_application(session, product)

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=[guarantor_member_id],
            actor_id=uuid.uuid4(),
        )
        lg = guarantors[0]
        with pytest.raises(ValueError, match="not authorised"):
            await svc.accept(
                loan_guarantor_id=lg.id,
                guarantor_member_id=uuid.uuid4(),  # wrong member
            )
```

- [ ] **Step 2: Run to confirm failure**

```bash
venv/bin/pytest tests/modules/credit/test_guarantor_service.py -v 2>&1 | head -30
```

Expected: ImportError or AttributeError — `GuarantorService` does not exist yet.

- [ ] **Step 3: Implement GuarantorService — nominate + accept + decline**

```python
# app/modules/credit/services/guarantor.py
"""GuarantorService — guarantor lifecycle + savings lien management."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import LoanGuarantor, LoanGuarantorLien, LoanProduct

_log = structlog.get_logger(__name__)


class GuarantorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Nomination ────────────────────────────────────────────────────────────

    async def nominate(
        self,
        *,
        application_id: uuid.UUID,
        guarantor_member_ids: list[uuid.UUID],
        actor_id: uuid.UUID,
    ) -> list[LoanGuarantor]:
        """Nominate guarantors for a loan application."""
        from app.modules.credit.models import LoanApplication

        application = await self._session.get(LoanApplication, application_id)
        if application is None:
            raise ValueError(f"LoanApplication '{application_id}' not found")

        product = await self._session.get(LoanProduct, application.loan_product_id)
        assert product is not None

        if product.required_guarantors == 0:
            raise ValueError(
                f"Loan product '{product.name}' does not require guarantors"
            )
        if len(guarantor_member_ids) != product.required_guarantors:
            raise ValueError(
                f"Product requires {product.required_guarantors} guarantor(s); "
                f"got {len(guarantor_member_ids)}"
            )
        if len(set(guarantor_member_ids)) != len(guarantor_member_ids):
            raise ValueError("Duplicate guarantor member IDs")
        if application.member_id in set(guarantor_member_ids):
            raise ValueError("Borrower cannot be their own guarantor")

        lien_share = application.requested_amount / Decimal(str(product.required_guarantors))

        guarantors: list[LoanGuarantor] = []
        for member_id in guarantor_member_ids:
            lg = LoanGuarantor(
                loan_application_id=application_id,
                guarantor_member_id=member_id,
                guaranteed_amount=lien_share,
                status="nominated",
                idempotency_key=f"guarantee-{application_id}-{member_id}",
            )
            self._session.add(lg)
            guarantors.append(lg)

        await self._session.flush()
        _log.info(
            "credit.guarantors.nominated",
            application_id=str(application_id),
            count=len(guarantors),
        )
        return guarantors

    # ── Consent ───────────────────────────────────────────────────────────────

    async def accept(
        self,
        *,
        loan_guarantor_id: uuid.UUID,
        guarantor_member_id: uuid.UUID,
    ) -> LoanGuarantor:
        """Guarantor accepts nomination. actor must be the nominated guarantor."""
        lg = await self._session.get(LoanGuarantor, loan_guarantor_id)
        if lg is None:
            raise ValueError(f"LoanGuarantor '{loan_guarantor_id}' not found")
        if lg.guarantor_member_id != guarantor_member_id:
            raise ValueError(
                f"Member '{guarantor_member_id}' is not authorised to accept this guarantee"
            )
        if lg.status != "nominated":
            raise ValueError(f"Cannot accept guarantor with status '{lg.status}'")

        lg.status = "accepted"
        lg.consented_at = datetime.now(UTC)
        await self._session.flush()
        _log.info("credit.guarantor.accepted", loan_guarantor_id=str(loan_guarantor_id))
        return lg

    async def decline(
        self,
        *,
        loan_guarantor_id: uuid.UUID,
        guarantor_member_id: uuid.UUID,
    ) -> LoanGuarantor:
        """Guarantor declines nomination."""
        lg = await self._session.get(LoanGuarantor, loan_guarantor_id)
        if lg is None:
            raise ValueError(f"LoanGuarantor '{loan_guarantor_id}' not found")
        if lg.guarantor_member_id != guarantor_member_id:
            raise ValueError(
                f"Member '{guarantor_member_id}' is not authorised to decline this guarantee"
            )
        if lg.status != "nominated":
            raise ValueError(f"Cannot decline guarantor with status '{lg.status}'")

        lg.status = "declined"
        await self._session.flush()
        _log.info("credit.guarantor.declined", loan_guarantor_id=str(loan_guarantor_id))
        return lg

    # ── Lien lifecycle (called by disbursement/repayment/write-off) ───────────

    async def place_liens(
        self,
        *,
        loan_id: uuid.UUID,
        loan_application_id: uuid.UUID,
        principal_amount: Decimal,
    ) -> None:
        """Create lien rows for all accepted guarantors. No-op if none."""
        from app.modules.savings.service import SavingsService

        result = await self._session.execute(
            select(LoanGuarantor)
            .where(LoanGuarantor.loan_application_id == loan_application_id)
            .where(LoanGuarantor.status == "accepted")
        )
        guarantors = list(result.scalars().all())
        if not guarantors:
            return

        lien_share = principal_amount / Decimal(str(len(guarantors)))
        sav_svc = SavingsService(self._session)

        for g in guarantors:
            g.loan_id = loan_id
            savings_acct = await sav_svc.get_primary_account_for_member(
                g.guarantor_member_id
            )
            lien = LoanGuarantorLien(
                loan_guarantor_id=g.id,
                savings_account_id=savings_acct.id,
                original_lien=lien_share,
                current_lien=lien_share,
                is_active=True,
            )
            self._session.add(lien)

        await self._session.flush()
        _log.info("credit.guarantor_liens.placed", loan_id=str(loan_id), count=len(guarantors))

    async def adjust_liens(
        self,
        *,
        loan_id: uuid.UUID,
        principal_applied: Decimal,
        original_principal: Decimal,
    ) -> None:
        """Proportionally reduce liens after a repayment."""
        if principal_applied <= Decimal("0") or original_principal <= Decimal("0"):
            return

        result = await self._session.execute(
            select(LoanGuarantorLien)
            .join(LoanGuarantor, LoanGuarantorLien.loan_guarantor_id == LoanGuarantor.id)
            .where(LoanGuarantor.loan_id == loan_id)
            .where(LoanGuarantorLien.is_active.is_(True))
        )
        liens = list(result.scalars().all())
        if not liens:
            return

        fraction = principal_applied / original_principal
        for lien in liens:
            reduction = lien.original_lien * fraction
            lien.current_lien = max(Decimal("0"), lien.current_lien - reduction)

        await self._session.flush()

    async def release_liens(self, *, loan_id: uuid.UUID) -> None:
        """Release all liens on loan closure or write-off."""
        result = await self._session.execute(
            select(LoanGuarantorLien)
            .join(LoanGuarantor, LoanGuarantorLien.loan_guarantor_id == LoanGuarantor.id)
            .where(LoanGuarantor.loan_id == loan_id)
            .where(LoanGuarantorLien.is_active.is_(True))
        )
        liens = list(result.scalars().all())
        for lien in liens:
            lien.is_active = False
            lien.current_lien = Decimal("0")

        result2 = await self._session.execute(
            select(LoanGuarantor)
            .where(LoanGuarantor.loan_id == loan_id)
            .where(LoanGuarantor.status == "accepted")
        )
        for g in result2.scalars().all():
            g.status = "released"
            g.released_at = datetime.now(UTC)

        await self._session.flush()
        _log.info("credit.guarantor_liens.released", loan_id=str(loan_id))

    async def reactivate_liens(
        self,
        *,
        loan_id: uuid.UUID,
        restored_amount: Decimal,
    ) -> None:
        """Reactivate liens after write-off recovery."""
        result = await self._session.execute(
            select(LoanGuarantor)
            .where(LoanGuarantor.loan_id == loan_id)
            .where(LoanGuarantor.status == "released")
        )
        guarantors = list(result.scalars().all())
        if not guarantors:
            return

        lien_share = restored_amount / Decimal(str(len(guarantors)))

        for g in guarantors:
            g.status = "accepted"
            g.released_at = None

            result2 = await self._session.execute(
                select(LoanGuarantorLien)
                .where(LoanGuarantorLien.loan_guarantor_id == g.id)
                .where(LoanGuarantorLien.is_active.is_(False))
                .order_by(LoanGuarantorLien.created_at.desc())
                .limit(1)
            )
            lien = result2.scalar_one_or_none()
            if lien is not None:
                lien.current_lien = lien_share
                lien.is_active = True

        await self._session.flush()
        _log.info("credit.guarantor_liens.reactivated", loan_id=str(loan_id))

    async def all_accepted(self, *, application_id: uuid.UUID) -> bool:
        """Return True if all required guarantors have accepted (or none required)."""
        from app.modules.credit.models import LoanApplication
        application = await self._session.get(LoanApplication, application_id)
        if application is None:
            return True
        product = await self._session.get(LoanProduct, application.loan_product_id)
        assert product is not None
        if product.required_guarantors == 0:
            return True

        result = await self._session.execute(
            select(LoanGuarantor)
            .where(LoanGuarantor.loan_application_id == application_id)
            .where(LoanGuarantor.status != "accepted")
        )
        not_accepted = result.scalars().first()
        return not_accepted is None
```

- [ ] **Step 4: Run tests**

```bash
venv/bin/pytest tests/modules/credit/test_guarantor_service.py -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/services/guarantor.py tests/modules/credit/test_guarantor_service.py
git commit -m "feat(credit): GuarantorService — nominate, accept, decline, lien lifecycle"
```

---

## Task 2: SavingsService — get_available_balance

**Files:**
- Modify: `app/modules/savings/service.py`

- [ ] **Step 1: Write failing test**

Add to `tests/modules/savings/test_service.py` (or a new file if preferred):

```python
@pytest.mark.anyio
async def test_get_available_balance_subtracts_active_liens(test_engine: AsyncEngine) -> None:
    """Available balance = raw balance - SUM(active current_lien)."""
    from sqlalchemy import text
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async with factory() as session:
        await session.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        # Create a savings account with a known balance via GL
        # (reuse existing helper or create a minimal one)
        # For simplicity, insert a LoanGuarantorLien directly
        from app.modules.savings.service import SavingsService
        from app.modules.credit.models import LoanGuarantor, LoanGuarantorLien, LoanApplication, LoanProduct

        # Create a real savings account via SavingsService
        from app.modules.ledger.models import ChartOfAccount
        acct = await session.scalar(select(ChartOfAccount).limit(1))
        from app.modules.savings.models import SavingsProduct, SavingsAccount
        product = SavingsProduct(
            name="test-avail-bal",
            interest_rate=Decimal("0"),
            liability_account_id=acct.id,
        )
        session.add(product)
        await session.flush()
        member_id = uuid.uuid4()
        sav_svc = SavingsService(session)
        savings_account = await sav_svc.open_account(
            member_id=member_id, product_id=product.id
        )
        # Add a lien directly
        lien = LoanGuarantorLien(
            loan_guarantor_id=uuid.uuid4(),  # not enforced by FK in test schema
            savings_account_id=savings_account.id,
            original_lien=Decimal("5000.0000"),
            current_lien=Decimal("3000.0000"),
            is_active=True,
        )
        session.add(lien)
        await session.commit()

        # Raw balance is 0 (no transactions); available should subtract the lien
        available = await sav_svc.get_available_balance(savings_account.id)
        # raw balance = 0, lien = 3000, available = 0 - 3000 = -3000
        # (negative is valid — the lien was placed when balance was sufficient)
        assert available == Decimal("-3000.0000")
```

- [ ] **Step 2: Run to confirm failure**

```bash
venv/bin/pytest tests/modules/savings/test_service.py -k "test_get_available_balance" -v 2>&1 | tail -10
```

Expected: AttributeError — `get_available_balance` does not exist.

- [ ] **Step 3: Implement `get_available_balance` in SavingsService**

In `app/modules/savings/service.py`, add after `get_balance`:

```python
    async def get_available_balance(self, savings_account_id: uuid.UUID) -> Decimal:
        """Raw balance minus any active guarantor liens on this account."""
        raw = await self.get_balance(savings_account_id)

        # Local import avoids circular dependency (credit imports savings).
        from app.modules.credit.models import LoanGuarantorLien
        from sqlalchemy import func as sa_func

        result = await self._session.execute(
            select(sa_func.coalesce(sa_func.sum(LoanGuarantorLien.current_lien), Decimal("0")))
            .where(LoanGuarantorLien.savings_account_id == savings_account_id)
            .where(LoanGuarantorLien.is_active.is_(True))
        )
        total_lien: Decimal = result.scalar_one()
        return raw - total_lien
```

- [ ] **Step 4: Run test**

```bash
venv/bin/pytest tests/modules/savings/test_service.py -k "test_get_available_balance" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/modules/savings/service.py
git commit -m "feat(savings): get_available_balance — raw balance minus active guarantor liens"
```

---

## Task 3: Guarantor API Endpoints

**Files:**
- Modify: `app/modules/credit/api.py`
- Modify: `app/modules/credit/schemas.py`

- [ ] **Step 1: Add guarantor schemas**

In `app/modules/credit/schemas.py`, append:

```python
# ── Guarantor schemas ─────────────────────────────────────────────────────────

class GuarantorNominateIn(BaseModel):
    guarantor_member_ids: list[uuid.UUID]

class GuarantorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    loan_application_id: uuid.UUID
    guarantor_member_id: uuid.UUID
    guaranteed_amount: Decimal
    status: str
    consented_at: datetime | None = None

class GuarantorConsentIn(BaseModel):
    """The acting member_id is passed by the caller (resolved from X-Actor-ID header)."""
    guarantor_member_id: uuid.UUID
```

- [ ] **Step 2: Add guarantor endpoints to api.py**

In `app/modules/credit/api.py`, add these four endpoints:

```python
@router.post("/applications/{application_id}/guarantors", status_code=201)
async def nominate_guarantors(
    application_id: uuid.UUID,
    body: GuarantorNominateIn,
    session: AsyncSession = Depends(get_tenant_session),
    actor_id: uuid.UUID = Depends(get_actor_id),
) -> list[GuarantorOut]:
    from app.modules.credit.services.guarantor import GuarantorService
    svc = GuarantorService(session)
    guarantors = await svc.nominate(
        application_id=application_id,
        guarantor_member_ids=body.guarantor_member_ids,
        actor_id=actor_id,
    )
    return [GuarantorOut.model_validate(g) for g in guarantors]


@router.get("/applications/{application_id}/guarantors")
async def list_guarantors(
    application_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[GuarantorOut]:
    from sqlalchemy import select as sa_select
    from app.modules.credit.models import LoanGuarantor
    result = await session.execute(
        sa_select(LoanGuarantor).where(LoanGuarantor.loan_application_id == application_id)
    )
    return [GuarantorOut.model_validate(g) for g in result.scalars().all()]


@router.post("/guarantors/{guarantor_id}/accept")
async def accept_guarantor(
    guarantor_id: uuid.UUID,
    body: GuarantorConsentIn,
    session: AsyncSession = Depends(get_tenant_session),
) -> GuarantorOut:
    from app.modules.credit.services.guarantor import GuarantorService
    svc = GuarantorService(session)
    g = await svc.accept(
        loan_guarantor_id=guarantor_id,
        guarantor_member_id=body.guarantor_member_id,
    )
    return GuarantorOut.model_validate(g)


@router.post("/guarantors/{guarantor_id}/decline")
async def decline_guarantor(
    guarantor_id: uuid.UUID,
    body: GuarantorConsentIn,
    session: AsyncSession = Depends(get_tenant_session),
) -> GuarantorOut:
    from app.modules.credit.services.guarantor import GuarantorService
    svc = GuarantorService(session)
    g = await svc.decline(
        loan_guarantor_id=guarantor_id,
        guarantor_member_id=body.guarantor_member_id,
    )
    return GuarantorOut.model_validate(g)
```

Make sure `GuarantorNominateIn`, `GuarantorOut`, `GuarantorConsentIn` are imported in `api.py`.

- [ ] **Step 3: Run guarantor tests**

```bash
venv/bin/pytest tests/modules/credit/test_guarantor_service.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/modules/credit/schemas.py app/modules/credit/api.py
git commit -m "feat(credit): guarantor API endpoints — nominate, list, accept, decline"
```

---

## Verification Criteria

```bash
# All guarantor service tests pass
venv/bin/pytest tests/modules/credit/test_guarantor_service.py -v

# Available balance test passes
venv/bin/pytest tests/modules/savings/ -k "available_balance" -v

# No regressions in existing credit tests
venv/bin/pytest tests/modules/credit/test_service.py -q

# App imports cleanly
venv/bin/python -c "from app.main import app; print('OK')"
```
