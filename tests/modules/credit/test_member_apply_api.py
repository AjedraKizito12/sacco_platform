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
