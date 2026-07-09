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
    assert Decimal(row["min_amount"]) == Decimal("100.00")
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
