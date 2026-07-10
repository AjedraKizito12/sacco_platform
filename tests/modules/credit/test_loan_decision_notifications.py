"""Loan decision notices to members (notifications increment 2, in_app only)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.notifications.models import TenantNotificationEvent
from app.core.notifications.seed_templates import seed_default_templates
from app.modules.credit.executors import execute_approve_application
from app.modules.credit.models import LoanApplication, LoanProduct
from app.modules.credit.services.application import LoanApplicationService
from app.modules.members.models import Member

SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture(autouse=True)
async def _clean(test_engine: AsyncEngine):  # noqa: ANN201
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        await seed_default_templates(s)
        await s.commit()
    yield
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text(f"DELETE FROM {SCHEMA}.notification_events"))  # noqa: S608
        await s.execute(text("DELETE FROM loan_applications"))
        await s.execute(text("DELETE FROM loan_products"))
        await s.execute(
            text(
                "DELETE FROM audit_log WHERE table_name IN "
                "('members', 'loan_applications', 'loan_products')"
            )
        )
        await s.execute(text("DELETE FROM members WHERE email LIKE 'ldn-%'"))
        await s.commit()


async def _seed_application(s: AsyncSession) -> LoanApplication:
    member = Member(
        member_number=f"M-{uuid.uuid4().hex[:8]}",
        full_name="Loan Member",
        date_of_birth=date(1990, 1, 1),
        gender="male",
        status="active",
        email=f"ldn-{uuid.uuid4().hex[:6]}@m.test",
    )
    s.add(member)
    await s.flush()
    product = LoanProduct(
        name=f"LDN {uuid.uuid4().hex[:6]}",
        interest_method="flat",
        annual_interest_rate=Decimal("12.00"),
        repayment_frequency="monthly",
        max_term_periods=24,
        min_amount=Decimal("100"),
        max_amount=Decimal("100000"),
        disbursement_destinations=["cash"],
        gl_principal_receivable_code="1300",
        gl_interest_receivable_code="1310",
        gl_interest_income_code="4100",
    )
    s.add(product)
    await s.flush()
    application = LoanApplication(
        loan_product_id=product.id,
        member_id=member.id,
        requested_amount=Decimal("5000"),
        requested_term_periods=6,
        disbursement_destination="cash",
        status="submitted",
        idempotency_key=f"ldn-{uuid.uuid4()}",
    )
    s.add(application)
    await s.flush()
    return application


async def test_approve_executor_publishes_in_app_notice(
    test_engine: AsyncEngine,
) -> None:
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        application = await _seed_application(s)
        await execute_approve_application(
            s,
            {
                "application_id": str(application.id),
                "approved_amount": "5000",
                "approved_term_periods": "6",
            },
        )
        await s.commit()
        member_id = application.member_id
        application_id = application.id
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.dedupe_key
                    == f"loan_approved:{application_id}"
                )
            )
        ).scalars().one()
    assert row.event_code == "loan_application_approved"
    assert row.recipient_kind == "member"
    assert row.recipient_user_id == member_id
    assert row.channels == ["in_app"]
    assert row.recipient_email is None
    assert row.context["amount"] == "5000"


async def test_service_reject_publishes_in_app_notice(
    test_engine: AsyncEngine,
) -> None:
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        application = await _seed_application(s)  # approval_request_id is None
        await LoanApplicationService(s).reject(
            application_id=application.id,
            rejected_by=uuid.uuid4(),
            reason="Insufficient savings history",
        )
        await s.commit()
        application_id = application.id
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.dedupe_key
                    == f"loan_rejected:{application_id}"
                )
            )
        ).scalars().one()
    assert row.event_code == "loan_application_rejected"
    assert row.channels == ["in_app"]
    assert row.context["reason"] == "Insufficient savings history"
