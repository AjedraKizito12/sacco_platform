"""HTTP tests: member self-service loans read endpoints (stub auth).

Loans are seeded directly (the full apply→approve→disburse flow is out of scope
for these read-endpoint tests); the member is activated via a direct DB write.
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
from app.modules.credit.models import Loan, LoanApplication, LoanProduct
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
        for tbl in (
            "loan_installments",
            "loans",
            "loan_applications",
            "loan_products",
            "members",
        ):
            await session.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        await session.commit()


def _member_headers(member_id: str) -> dict[str, str]:
    return {**HEADERS, "X-Member-Actor-ID": member_id}


async def _seed_member(engine: AsyncEngine, *, active: bool) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        m = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}",
            full_name="Loan Holder",
            date_of_birth=date(1990, 1, 1),
            gender="male",
            status="active" if active else "pending",
            email=f"m-{uuid.uuid4().hex[:6]}@example.com",
            portal_enabled=active,
        )
        session.add(m)
        await session.commit()
        return m.id


async def _seed_loan(engine: AsyncEngine, member_id: uuid.UUID) -> uuid.UUID:
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
            idempotency_key=uuid.uuid4().hex,
        )
        session.add(application)
        await session.flush()
        loan = Loan(
            loan_reference=f"L-{uuid.uuid4().hex[:8]}",
            loan_application_id=application.id,
            loan_product_id=product.id,
            member_id=member_id,
            status="disbursed",
            principal_amount=Decimal("1000.00"),
            interest_method="flat",
            annual_interest_rate=Decimal("12.00"),
            repayment_frequency="monthly",
            term_periods=12,
            repayment_allocation="INTEREST_PRINCIPAL",
            disbursement_destination="cash",
            gl_principal_receivable_id=uuid.uuid4(),
            gl_interest_receivable_id=uuid.uuid4(),
            gl_interest_income_id=uuid.uuid4(),
            gl_disbursement_account_id=uuid.uuid4(),
            disbursed_by=uuid.uuid4(),
            idempotency_key=uuid.uuid4().hex,
        )
        session.add(loan)
        await session.commit()
        return loan.id


async def test_member_loans_lists_only_own(client, test_engine: AsyncEngine) -> None:  # noqa: ANN001
    member_id = await _seed_member(test_engine, active=True)
    loan_id = await _seed_loan(test_engine, member_id)

    resp = await client.get("/member/loans", headers=_member_headers(str(member_id)))
    assert resp.status_code == 200, resp.text
    ids = [loan["id"] for loan in resp.json()]
    assert str(loan_id) in ids


async def test_member_cannot_read_other_members_loan(
    client, test_engine: AsyncEngine
) -> None:  # noqa: ANN001
    member_id = await _seed_member(test_engine, active=True)
    other_id = await _seed_member(test_engine, active=False)
    other_loan_id = await _seed_loan(test_engine, other_id)

    resp = await client.get(
        f"/member/loans/{other_loan_id}", headers=_member_headers(str(member_id))
    )
    assert resp.status_code == 404, resp.text
