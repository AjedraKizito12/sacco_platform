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
