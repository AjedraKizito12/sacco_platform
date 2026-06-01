"""End-to-end integration test for the Phase 1 billing lifecycle.

Exercises the full flow without waiting for real time to pass:
  assign → invoice → record_payment → confirm → past_due → suspended → reactivate
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

import app.platform_.billing.executors  # noqa: F401
from app.modules.maker_checker.models.platform import PlatformApprovalRequest
from app.modules.maker_checker.service import ApprovalService
from app.platform_.billing.beat import (
    _run_assess_subscription_state,
)
from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Payment,
    Subscription,
    SubscriptionPlan,
)
from app.platform_.billing.services import (
    InvoiceService,
    PaymentService,
    SubscriptionService,
)
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL, "
                "subscription_status = 'pending'"
            )
        )
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(delete(Payment))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(delete(InvoiceLineItem))
        await s.execute(delete(Invoice))
        await s.execute(delete(Subscription))
        await s.execute(delete(SubscriptionPlan))
        await s.execute(delete(Tenant))
        await s.execute(delete(PlatformUser))
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.commit()


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture
def patched_beat(test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Wrapper:
        def __init__(self, engine: AsyncEngine) -> None:
            self._engine = engine

        async def dispose(self) -> None:
            pass

        def __getattr__(self, name: str) -> object:
            return getattr(self._engine, name)

    wrapper = _Wrapper(test_engine)
    monkeypatch.setattr(
        "app.platform_.billing.beat.create_async_engine",
        lambda *a, **kw: wrapper,
    )


@pytest.mark.anyio
async def test_full_billing_lifecycle(
    factory: async_sessionmaker[AsyncSession], patched_beat: None
) -> None:
    """Walk a single tenant through every Phase 1 billing transition."""
    # Setup actors and plan
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        maker = PlatformUser(
            email=f"maker-{uuid.uuid4().hex[:8]}@test.example",
            full_name="Maker",
            is_active=True,
            is_superuser=True,
            created_at=now,
            updated_at=now,
        )
        checker = PlatformUser(
            email=f"checker-{uuid.uuid4().hex[:8]}@test.example",
            full_name="Checker",
            is_active=True,
            is_superuser=True,
            created_at=now,
            updated_at=now,
        )
        tenant = Tenant(
            slug=f"e2e-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_e2e_{uuid.uuid4().hex[:8]}",
            name="E2E Test SACCO",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        plan = SubscriptionPlan(
            code=f"e2e-plan-{uuid.uuid4().hex[:8]}",
            name="E2E Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            grace_period_days=14,
        )
        s.add_all([maker, checker, tenant, plan])
        await s.commit()
        await s.refresh(maker)
        await s.refresh(checker)
        await s.refresh(tenant)
        await s.refresh(plan)
        maker_id, checker_id, tenant_id, plan_id = (
            maker.id, checker.id, tenant.id, plan.id
        )

    try:
        # 1. Assign subscription (active because plan has no trial)
        async with factory() as s:
            await _set_platform(s)
            sub = await SubscriptionService(s).assign(
                tenant_id=tenant_id, plan_id=plan_id
            )
            await s.commit()
            sub_id = sub.id
            assert sub.status == "active"

        # 2. Generate the first invoice
        async with factory() as s:
            await _set_platform(s)
            invoice = await InvoiceService(s).generate_for_subscription(
                subscription_id=sub_id
            )
            await s.commit()
            invoice_id = invoice.id
            assert invoice.status == "issued"
            assert invoice.amount_total == Decimal("50000.0000")

        # 3. Maker records a payment
        async with factory() as s:
            await _set_platform(s)
            pmt = await PaymentService(s).record(
                invoice_id=invoice_id,
                amount=Decimal("50000"),
                currency="UGX",
                payment_method="bank_transfer",
                recorded_by=maker_id,
                idempotency_key=f"e2e-{uuid.uuid4().hex}",
            )
            # Create the linked ApprovalRequest (simulating the API layer)
            approval_request = await ApprovalService(s).submit(
                operation_type="billing.confirm_payment",
                payload={"payment_id": str(pmt.id)},
                requested_by=maker_id,
            )
            pmt.approval_request_id = approval_request.id
            await s.commit()
            payment_id = pmt.id
            request_id = approval_request.id

        # 4. Checker approves — triggers executor → PaymentService.confirm
        async with factory() as s:
            await _set_platform(s)
            await ApprovalService(s).approve(
                request_id=request_id,
                actor_user_id=checker_id,
            )
            await s.commit()

        # 5. Verify: payment confirmed, invoice paid
        async with factory() as s:
            await _set_platform(s)
            pmt_check = await s.get(Payment, payment_id)
            assert pmt_check is not None
            assert pmt_check.status == "confirmed"
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            assert inv.status == "paid"
            assert inv.amount_paid == Decimal("50000.0000")
            req = await s.get(PlatformApprovalRequest, request_id)
            assert req is not None
            assert req.status == "executed"

        # 6. Force the subscription into past_due (period_end in past)
        async with factory() as s:
            await _set_platform(s)
            await s.execute(
                text(
                    "UPDATE platform.subscriptions SET current_period_end = :pe "
                    "WHERE id = :id"
                ),
                {"pe": date.today() - timedelta(days=1), "id": sub_id},
            )
            await s.commit()

        # 7. assess_subscription_state → past_due
        counts = await _run_assess_subscription_state()
        assert counts["past_due"] >= 1

        async with factory() as s:
            await _set_platform(s)
            sub_check = await s.get(Subscription, sub_id)
            assert sub_check is not None
            assert sub_check.status == "past_due"
            assert sub_check.grace_period_ends_at is not None
            t = await s.get(Tenant, tenant_id)
            assert t is not None
            assert t.subscription_status == "past_due"

        # 8. Force grace period expired
        async with factory() as s:
            await _set_platform(s)
            await s.execute(
                text(
                    "UPDATE platform.subscriptions SET grace_period_ends_at = :gpe "
                    "WHERE id = :id"
                ),
                {"gpe": date.today() - timedelta(days=1), "id": sub_id},
            )
            await s.commit()

        # 9. assess → suspended
        counts = await _run_assess_subscription_state()
        assert counts["suspended"] >= 1

        async with factory() as s:
            await _set_platform(s)
            sub_check2 = await s.get(Subscription, sub_id)
            assert sub_check2 is not None
            assert sub_check2.status == "suspended"
            t = await s.get(Tenant, tenant_id)
            assert t is not None
            assert t.subscription_status == "suspended"

        # 10. Reactivate
        async with factory() as s:
            await _set_platform(s)
            sub = await SubscriptionService(s).reactivate(subscription_id=sub_id)
            await s.commit()
            assert sub.status == "active"

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant_id)
            assert t is not None
            assert t.subscription_status == "active"

    finally:
        await _cleanup(factory)
