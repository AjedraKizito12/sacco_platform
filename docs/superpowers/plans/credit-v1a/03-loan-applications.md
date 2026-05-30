# Sub-plan 03 — Loan Applications

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Implement `LoanApplicationService` (submit, withdraw, reject, list, get) and the
`credit.approve_application` maker-checker executor. Approval routing goes through
`ApprovalService` — no direct status-flipping from HTTP routes. Produces application API
endpoints and schemas.

**Architecture:** `LoanApplicationService.submit()` creates a `LoanApplication` row
(`status=submitted`) then immediately calls `ApprovalService.submit()` to create a
`TenantApprovalRequest`. The executor `credit.approve_application` is called by
`ApprovalService` when quorum is met — it sets `application.status='approved'` and
populates `approved_amount`/`approved_term_periods`. Withdrawal and rejection delegate to
`ApprovalService.cancel()` and `ApprovalService.reject()` respectively, so self-approval
and post-action-withdrawal guards are enforced by the existing `ApprovalService` logic.

**Tech Stack:** SQLAlchemy 2.0 async, pytest-asyncio, Pydantic v2, FastAPI,
`ApprovalService`, `@approval_executor`

---

## Required Reading

Before starting, read these files in full:

- Sub-plans 01, 02 (completed — models + product service must exist)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §3.2, §4 (Status Machine), §10
- `app/modules/savings/service.py` — `submit_withdrawal` (lines 242–315) — maker-checker wiring pattern
- `app/modules/savings/executors.py` — `@approval_executor` registration pattern
- `app/modules/maker_checker/service.py` — `ApprovalService.submit`, `.approve`, `.reject`, `.cancel` signatures
- `tests/modules/savings/test_service.py` lines 1–80 — test helper pattern

---

## File Map

```
New
  app/modules/credit/services/application.py   LoanApplicationService
  app/modules/credit/executors.py               credit.approve_application executor

Modified
  app/modules/credit/schemas.py                append application schemas
  app/modules/credit/api.py                    append application endpoints
  tests/modules/credit/test_service.py         append application tests
```

---

## Task 1 — `LoanApplicationService.submit` + Executor (TDD)

**Files:**
- Modify: `tests/modules/credit/test_service.py`
- Create: `app/modules/credit/services/application.py`
- Create: `app/modules/credit/executors.py`

- [ ] **Step 1: Append failing tests to `tests/modules/credit/test_service.py`**

First, add these imports at the top of the file (after existing imports):

```python
import app.modules.credit.executors  # noqa: F401 — registers credit.approve_application
from app.modules.credit.services.application import LoanApplicationService
from app.modules.maker_checker.service import ApprovalService
```

Then append the tests:

```python
# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_product(engine: AsyncEngine, **overrides) -> LoanProduct:
    """Create a committed LoanProduct for use in application tests."""
    session = await _new_session(engine)
    try:
        svc = LoanProductService(session)
        product = await svc.create(**_product_kwargs(**overrides))
        await session.commit()
        return product
    finally:
        await session.close()


# ── Application tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_application_success(test_engine):
    product = await _make_product(test_engine, name="App Test Product", required_approvals=1)

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        actor = uuid.uuid4()
        application = await svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("200000"),
            requested_term_periods=12,
            purpose="Business expansion",
            disbursement_destination="member_savings",
            disbursement_account_id=None,
            submitted_by=actor,
            idempotency_key=f"submit-test-{uuid.uuid4()}",
        )
        await session.commit()

        assert application.id is not None
        assert application.status == "submitted"
        assert application.approval_request_id is not None
        assert application.loan_product_id == product.id
        assert application.requested_amount == Decimal("200000")
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_submit_inactive_product_raises(test_engine):
    product = await _make_product(test_engine, name="Inactive Product")
    # Deactivate the product
    session0 = await _new_session(test_engine)
    try:
        svc0 = LoanProductService(session0)
        await svc0.deactivate(product.id, deactivated_by=uuid.uuid4())
        await session0.commit()
    finally:
        await session0.close()

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        with pytest.raises(ValueError, match="not active"):
            await svc.submit(
                loan_product_id=product.id,
                member_id=uuid.uuid4(),
                requested_amount=Decimal("100000"),
                requested_term_periods=6,
                disbursement_destination="member_savings",
                submitted_by=uuid.uuid4(),
                idempotency_key=f"inactive-{uuid.uuid4()}",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_submit_amount_below_min_raises(test_engine):
    product = await _make_product(test_engine, min_amount=Decimal("50000"), max_amount=Decimal("500000"))

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        with pytest.raises(ValueError, match="min_amount|minimum"):
            await svc.submit(
                loan_product_id=product.id,
                member_id=uuid.uuid4(),
                requested_amount=Decimal("10000"),  # below min_amount=50000
                requested_term_periods=6,
                disbursement_destination="member_savings",
                submitted_by=uuid.uuid4(),
                idempotency_key=f"below-min-{uuid.uuid4()}",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_submit_amount_above_max_raises(test_engine):
    product = await _make_product(test_engine, min_amount=Decimal("50000"), max_amount=Decimal("500000"))

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        with pytest.raises(ValueError, match="max_amount|maximum"):
            await svc.submit(
                loan_product_id=product.id,
                member_id=uuid.uuid4(),
                requested_amount=Decimal("1000000"),  # above max_amount=500000
                requested_term_periods=6,
                disbursement_destination="member_savings",
                submitted_by=uuid.uuid4(),
                idempotency_key=f"above-max-{uuid.uuid4()}",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_submit_term_above_max_raises(test_engine):
    product = await _make_product(test_engine, max_term_periods=12)

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        with pytest.raises(ValueError, match="max_term_periods|term"):
            await svc.submit(
                loan_product_id=product.id,
                member_id=uuid.uuid4(),
                requested_amount=Decimal("100000"),
                requested_term_periods=24,  # above max_term_periods=12
                disbursement_destination="member_savings",
                submitted_by=uuid.uuid4(),
                idempotency_key=f"over-term-{uuid.uuid4()}",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_submit_idempotency(test_engine):
    """Same idempotency_key returns the same application on second call."""
    product = await _make_product(test_engine)

    idem_key = f"idem-{uuid.uuid4()}"
    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        actor = uuid.uuid4()
        first = await svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=actor,
            idempotency_key=idem_key,
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanApplicationService(session2)
        second = await svc2.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("200000"),  # different amount — ignored
            requested_term_periods=12,
            disbursement_destination="member_savings",
            submitted_by=uuid.uuid4(),
            idempotency_key=idem_key,  # same key
        )
        assert second.id == first.id
        assert second.requested_amount == Decimal("100000")  # original preserved
    finally:
        await session2.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_service.py -k "application or submit" -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.modules.credit.services.application'`

- [ ] **Step 3: Create `app/modules/credit/executors.py`**

```python
# app/modules/credit/executors.py
"""Maker-checker executors for credit operations.

Import this module at app startup to register executors in approval_registry.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from app.modules.maker_checker.registry import approval_executor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("credit.approve_application")
async def execute_approve_application(session: AsyncSession, payload: dict) -> dict:
    """Executor: called by ApprovalService.approve() when quorum is met.

    payload keys (all strings — JSON round-tripped through JSONB):
        application_id: str (UUID)
        approved_amount: str (Decimal)
        approved_term_periods: str (int)
    """
    from app.modules.credit.models import LoanApplication

    application_id = uuid.UUID(payload["application_id"])
    approved_amount = Decimal(payload["approved_amount"])
    approved_term_periods = int(payload["approved_term_periods"])

    application = await session.get(LoanApplication, application_id)
    if application is None:
        raise ValueError(f"LoanApplication '{application_id}' not found in executor")

    # Idempotency guard — already approved on a prior executor call.
    if application.status == "approved":
        return {
            "application_id": str(application_id),
            "status": "approved",
        }

    application.status = "approved"
    application.approved_amount = approved_amount
    application.approved_term_periods = approved_term_periods
    await session.flush()

    return {
        "application_id": str(application_id),
        "status": "approved",
    }
```

- [ ] **Step 4: Create `app/modules/credit/services/application.py`**

```python
# app/modules/credit/services/application.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import LoanApplication

_log = structlog.get_logger(__name__)


class LoanApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def submit(
        self,
        *,
        loan_product_id: uuid.UUID,
        member_id: uuid.UUID,
        requested_amount: Decimal,
        requested_term_periods: int,
        purpose: str | None = None,
        disbursement_destination: str,
        disbursement_account_id: uuid.UUID | None = None,
        submitted_by: uuid.UUID,
        idempotency_key: str,
    ) -> LoanApplication:
        """Submit a loan application and create a maker-checker approval request.

        Idempotent: returns the existing application if idempotency_key already used.
        """
        # Idempotency guard.
        existing = await self._session.scalar(
            select(LoanApplication).where(
                LoanApplication.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            _log.info(
                "credit.application.submit.idempotent_hit",
                idempotency_key=idempotency_key,
            )
            return existing

        # Validate product.
        from app.modules.credit.services.product import LoanProductService

        product_svc = LoanProductService(self._session)
        product = await product_svc.get(loan_product_id)
        if not product.is_active:
            raise ValueError(f"LoanProduct '{loan_product_id}' is not active")

        # Validate amounts and terms.
        if requested_amount < product.min_amount:
            raise ValueError(
                f"requested_amount {requested_amount} is below product min_amount {product.min_amount}"
            )
        if requested_amount > product.max_amount:
            raise ValueError(
                f"requested_amount {requested_amount} exceeds product max_amount {product.max_amount}"
            )
        if requested_term_periods > product.max_term_periods:
            raise ValueError(
                f"requested_term_periods {requested_term_periods} exceeds product max_term_periods "
                f"{product.max_term_periods}"
            )
        if disbursement_destination not in product.disbursement_destinations:
            raise ValueError(
                f"disbursement_destination '{disbursement_destination}' is not allowed by product. "
                f"Allowed: {product.disbursement_destinations}"
            )

        # Create application row.
        application = LoanApplication(
            loan_product_id=loan_product_id,
            member_id=member_id,
            requested_amount=requested_amount,
            requested_term_periods=requested_term_periods,
            purpose=purpose,
            disbursement_destination=disbursement_destination,
            disbursement_account_id=disbursement_account_id,
            status="submitted",
            idempotency_key=idempotency_key,
        )
        self._session.add(application)
        await self._session.flush()

        # Submit approval request.
        from app.modules.maker_checker.service import ApprovalService

        approval_svc = ApprovalService(self._session)
        request = await approval_svc.submit(
            operation_type="credit.approve_application",
            payload={
                "application_id": str(application.id),
                "approved_amount": str(requested_amount),
                "approved_term_periods": str(requested_term_periods),
            },
            requested_by=submitted_by,
            required_approvals=product.required_approvals,
        )
        application.approval_request_id = request.id
        await self._session.flush()

        _log.info(
            "credit.application.submitted",
            application_id=str(application.id),
            member_id=str(member_id),
            amount=str(requested_amount),
            approval_request_id=str(request.id),
        )
        return application

    async def get(self, application_id: uuid.UUID) -> LoanApplication:
        a = await self._session.get(LoanApplication, application_id)
        if a is None:
            raise ValueError(f"LoanApplication '{application_id}' not found")
        return a

    async def list(
        self,
        *,
        member_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[LoanApplication]:
        q = select(LoanApplication).order_by(LoanApplication.created_at.desc())
        if member_id is not None:
            q = q.where(LoanApplication.member_id == member_id)
        if status is not None:
            q = q.where(LoanApplication.status == status)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def withdraw(
        self,
        *,
        application_id: uuid.UUID,
        withdrawn_by: uuid.UUID,
    ) -> LoanApplication:
        """Withdraw a pending application.

        Delegates to ApprovalService.cancel() which enforces:
        - Only the original submitter can withdraw (self-check)
        - Cannot withdraw after any approver has acted
        """
        application = await self.get(application_id)

        if application.status in ("approved", "rejected", "withdrawn", "cancelled"):
            raise ValueError(
                f"Cannot withdraw application with status '{application.status}'"
            )

        if application.approval_request_id is not None:
            from app.modules.maker_checker.service import ApprovalService

            approval_svc = ApprovalService(self._session)
            await approval_svc.cancel(
                request_id=application.approval_request_id,
                requested_by=withdrawn_by,
            )

        application.status = "withdrawn"
        await self._session.flush()
        _log.info(
            "credit.application.withdrawn",
            application_id=str(application_id),
            withdrawn_by=str(withdrawn_by),
        )
        return application

    async def reject(
        self,
        *,
        application_id: uuid.UUID,
        rejected_by: uuid.UUID,
        reason: str | None = None,
    ) -> LoanApplication:
        """Reject a pending application via ApprovalService.

        ApprovalService.reject() enforces self-rejection is forbidden.
        """
        application = await self.get(application_id)

        if application.status not in ("submitted", "under_review"):
            raise ValueError(
                f"Cannot reject application with status '{application.status}'"
            )

        if application.approval_request_id is not None:
            from app.modules.maker_checker.service import ApprovalService

            approval_svc = ApprovalService(self._session)
            await approval_svc.reject(
                request_id=application.approval_request_id,
                actor_user_id=rejected_by,
                reason=reason,
            )

        application.status = "rejected"
        application.rejection_reason = reason
        application.decided_by = rejected_by
        application.decided_at = datetime.now(UTC)
        await self._session.flush()
        _log.info(
            "credit.application.rejected",
            application_id=str(application_id),
            rejected_by=str(rejected_by),
        )
        return application
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/modules/credit/test_service.py -k "application or submit" -v
```

Expected: 6 tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add app/modules/credit/executors.py app/modules/credit/services/application.py \
        tests/modules/credit/test_service.py
git commit -m "feat(credit): LoanApplicationService.submit + credit.approve_application executor"
```

---

## Task 2 — Withdraw, Reject, Approve Tests

**Files:**
- Modify: `tests/modules/credit/test_service.py`

- [ ] **Step 1: Append tests to `tests/modules/credit/test_service.py`**

```python
@pytest.mark.asyncio
async def test_approve_quorum_1(test_engine):
    """With required_approvals=1: single non-self approve → application.status=approved."""
    product = await _make_product(test_engine, required_approvals=1)

    submitter = uuid.uuid4()
    approver = uuid.uuid4()  # different actor

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)
        approval_svc = ApprovalService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"q1-{uuid.uuid4()}",
        )
        # Approve as a different actor.
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=approver,
        )
        await session.commit()

        # After executor ran, application.status should be 'approved'.
        assert application.status == "approved"
        assert application.approved_amount == Decimal("100000")
        assert application.approved_term_periods == 6
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_approve_quorum_2_requires_two_approvers(test_engine):
    """With required_approvals=2: first approve keeps pending; second approve triggers executor."""
    product = await _make_product(test_engine, required_approvals=2)

    submitter = uuid.uuid4()
    approver1 = uuid.uuid4()
    approver2 = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)
        approval_svc = ApprovalService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"q2-{uuid.uuid4()}",
        )

        # First approval — quorum not yet met.
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=approver1,
        )
        # Application should still be 'submitted' (executor not called yet).
        assert application.status == "submitted"

        # Second approval — quorum met, executor fires.
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=approver2,
        )
        await session.commit()

        assert application.status == "approved"
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_self_approval_raises(test_engine):
    product = await _make_product(test_engine, required_approvals=1)
    submitter = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)
        approval_svc = ApprovalService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"self-approve-{uuid.uuid4()}",
        )

        with pytest.raises(ValueError, match="[Ss]elf"):
            await approval_svc.approve(
                request_id=application.approval_request_id,
                actor_user_id=submitter,  # same as submitted_by
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_reject_application(test_engine):
    product = await _make_product(test_engine, required_approvals=1)
    submitter = uuid.uuid4()
    rejecter = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"reject-{uuid.uuid4()}",
        )

        rejected = await app_svc.reject(
            application_id=application.id,
            rejected_by=rejecter,
            reason="Insufficient collateral",
        )
        await session.commit()

        assert rejected.status == "rejected"
        assert rejected.rejection_reason == "Insufficient collateral"
        assert rejected.decided_by == rejecter
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_withdraw_application_success(test_engine):
    product = await _make_product(test_engine, required_approvals=1)
    submitter = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"withdraw-{uuid.uuid4()}",
        )

        withdrawn = await app_svc.withdraw(
            application_id=application.id,
            withdrawn_by=submitter,  # same actor as submitter
        )
        await session.commit()

        assert withdrawn.status == "withdrawn"
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_withdraw_non_originator_raises(test_engine):
    """Only the original submitter can withdraw."""
    product = await _make_product(test_engine, required_approvals=1)
    submitter = uuid.uuid4()
    other_actor = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"nonoriginator-{uuid.uuid4()}",
        )

        with pytest.raises(ValueError, match="[Mm]aker|[Oo]riginator|[Cc]ancel"):
            await app_svc.withdraw(
                application_id=application.id,
                withdrawn_by=other_actor,
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_withdraw_after_approval_action_raises(test_engine):
    """Cannot withdraw once a checker has acted on the approval request."""
    product = await _make_product(test_engine, required_approvals=2)
    submitter = uuid.uuid4()
    approver = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)
        approval_svc = ApprovalService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"after-action-{uuid.uuid4()}",
        )

        # First approve (quorum=2, so not yet approved).
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=approver,
        )

        # Submitter tries to withdraw — should fail because action_count > 0.
        with pytest.raises(ValueError, match="[Cc]hecker|[Aa]cted|[Cc]ancel"):
            await app_svc.withdraw(
                application_id=application.id,
                withdrawn_by=submitter,
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_list_applications_filter_by_member(test_engine):
    product = await _make_product(test_engine)
    member_a = uuid.uuid4()
    member_b = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        app_a = await svc.submit(
            loan_product_id=product.id,
            member_id=member_a,
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=member_a,
            idempotency_key=f"list-a-{uuid.uuid4()}",
        )
        app_b = await svc.submit(
            loan_product_id=product.id,
            member_id=member_b,
            requested_amount=Decimal("150000"),
            requested_term_periods=12,
            disbursement_destination="member_savings",
            submitted_by=member_b,
            idempotency_key=f"list-b-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanApplicationService(session2)
        member_a_apps = await svc2.list(member_id=member_a)
        assert len(member_a_apps) == 1
        assert member_a_apps[0].id == app_a.id
    finally:
        await session2.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run all application tests**

```bash
pytest tests/modules/credit/test_service.py -k "application or submit or approve or reject or withdraw or list_applic" -v
```

Expected: all 14 application tests `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add tests/modules/credit/test_service.py
git commit -m "test(credit): LoanApplicationService withdraw, reject, approve, list tests"
```

---

## Task 3 — Application Schemas

**Files:**
- Modify: `app/modules/credit/schemas.py`

- [ ] **Step 1: Append application schemas to `app/modules/credit/schemas.py`**

```python
# ── Loan Applications ─────────────────────────────────────────────────────────


class LoanApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_product_id: uuid.UUID
    member_id: uuid.UUID
    requested_amount: Decimal
    requested_term_periods: int
    purpose: str | None
    disbursement_destination: str
    disbursement_account_id: uuid.UUID | None
    status: str
    approval_request_id: uuid.UUID | None
    approved_amount: Decimal | None
    approved_term_periods: int | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    rejection_reason: str | None
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class LoanApplicationCreateIn(BaseModel):
    loan_product_id: uuid.UUID
    member_id: uuid.UUID
    requested_amount: Decimal
    requested_term_periods: int
    purpose: str | None = None
    disbursement_destination: str
    disbursement_account_id: uuid.UUID | None = None
    idempotency_key: str


class LoanApplicationApproveIn(BaseModel):
    comment: str | None = None


class LoanApplicationRejectIn(BaseModel):
    reason: str | None = None
```

- [ ] **Step 2: Verify schemas import**

```bash
python -c "
from app.modules.credit.schemas import (
    LoanApplicationOut, LoanApplicationCreateIn,
    LoanApplicationApproveIn, LoanApplicationRejectIn,
)
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/modules/credit/schemas.py
git commit -m "feat(credit): application Pydantic schemas"
```

---

## Task 4 — Application API Endpoints

**Files:**
- Modify: `app/modules/credit/api.py`

- [ ] **Step 1: Add imports to `app/modules/credit/api.py`**

At the top of `api.py`, extend the schema imports and add a new service import:

```python
from app.modules.credit.schemas import (
    LoanApplicationApproveIn,
    LoanApplicationCreateIn,
    LoanApplicationOut,
    LoanApplicationRejectIn,
    LoanProductCreateIn,
    LoanProductOut,
    LoanProductPatchIn,
)
from app.modules.credit.services.application import LoanApplicationService
from app.modules.maker_checker.service import ApprovalService
```

- [ ] **Step 2: Append application endpoints to `app/modules/credit/api.py`**

```python
# ── Loan Applications ─────────────────────────────────────────────────────────


@router.post("/applications", response_model=LoanApplicationOut, status_code=201)
async def submit_loan_application(
    body: LoanApplicationCreateIn, session: Session
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.submit(
            loan_product_id=body.loan_product_id,
            member_id=body.member_id,
            requested_amount=body.requested_amount,
            requested_term_periods=body.requested_term_periods,
            purpose=body.purpose,
            disbursement_destination=body.disbursement_destination,
            disbursement_account_id=body.disbursement_account_id,
            submitted_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.get("/applications", response_model=list[LoanApplicationOut])
async def list_loan_applications(
    session: Session,
    member_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[LoanApplicationOut]:
    svc = LoanApplicationService(session)
    applications = await svc.list(member_id=member_id, status=status)
    return [LoanApplicationOut.model_validate(a) for a in applications]


@router.get("/applications/{application_id}", response_model=LoanApplicationOut)
async def get_loan_application(
    application_id: uuid.UUID, session: Session
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.get(application_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.post("/applications/{application_id}/withdraw", response_model=LoanApplicationOut)
async def withdraw_loan_application(
    application_id: uuid.UUID, session: Session
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.withdraw(
            application_id=application_id,
            withdrawn_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.post("/applications/{application_id}/approve", response_model=LoanApplicationOut)
async def approve_loan_application(
    application_id: uuid.UUID, body: LoanApplicationApproveIn, session: Session
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.get(application_id)
        if application.approval_request_id is None:
            raise ValueError("Application has no pending approval request")
        approval_svc = ApprovalService(session)
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
            comment=body.comment,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)


@router.post("/applications/{application_id}/reject", response_model=LoanApplicationOut)
async def reject_loan_application(
    application_id: uuid.UUID, body: LoanApplicationRejectIn, session: Session
) -> LoanApplicationOut:
    try:
        svc = LoanApplicationService(session)
        application = await svc.reject(
            application_id=application_id,
            rejected_by=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
            reason=body.reason,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanApplicationOut.model_validate(application)
```

- [ ] **Step 3: Verify API imports without errors**

```bash
python -c "from app.modules.credit.api import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/modules/credit/api.py
git commit -m "feat(credit): application API endpoints — POST/GET /credit/applications + withdraw/approve/reject"
```

---

## Verification Criteria

Run all of the following before marking this sub-plan complete:

```bash
# 1. All application tests pass
pytest tests/modules/credit/test_service.py -k "application or submit or approve or reject or withdraw or list_applic" -v

# 2. Executor registered
python -c "
import app.modules.credit.executors
from app.modules.maker_checker.registry import approval_registry
assert 'credit.approve_application' in approval_registry, 'Executor not registered'
print('Executor registered OK')
"

# 3. All imports clean
python -c "
from app.modules.credit.services.application import LoanApplicationService
from app.modules.credit.executors import execute_approve_application
from app.modules.credit.schemas import LoanApplicationOut, LoanApplicationCreateIn
from app.modules.credit.api import router
print('All imports OK')
"

# 4. Full suite — no regressions
pytest -x -q
```

All commands must exit 0. Confirm these behaviors are tested:
- Submit → `status=submitted`, `approval_request_id` set
- Inactive product → `ValueError("not active")`
- Amount out of range → `ValueError`
- Term too long → `ValueError`
- Same idempotency_key → returns original application unchanged
- Quorum=1, one non-self approve → `status=approved`
- Quorum=2, first approve → still `submitted`; second approve → `approved`
- Self-approval → `ValueError("Self")`
- Reject → `status=rejected`, `rejection_reason` set
- Withdraw by originator → `status=withdrawn`
- Withdraw by non-originator → `ValueError`
- Withdraw after checker acted → `ValueError`
