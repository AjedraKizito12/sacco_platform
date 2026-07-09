"""HTTP tests: member KYC submission + operator review endpoints (stub auth)."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan

SCHEMA = "tenant_test"
HEADERS = {"X-Tenant-Slug": "test-tenant"}


async def _make_tenant_session_override(engine: AsyncEngine):  # noqa: ANN202
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {SCHEMA}, platform")
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
    app.dependency_overrides[get_tenant_session] = await _make_tenant_session_override(
        test_engine
    )
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = "test-tenant"
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM kyc_submissions"))
        await s.execute(text("DELETE FROM member_kyc_requirements"))
        await s.execute(text("DELETE FROM member_sessions"))
        await s.execute(
            text("DELETE FROM audit_log WHERE table_name IN ('members', 'kyc_submissions')")
        )
        await s.execute(text("DELETE FROM members"))
        await s.commit()


async def _create_active_member(
    client: AsyncClient, test_engine: AsyncEngine, **fields: Any
) -> dict[str, Any]:
    body = {
        "full_name": f"Member {uuid.uuid4().hex[:6]}",
        "date_of_birth": "1990-05-15",
        "gender": "female",
        "email": f"m-{uuid.uuid4().hex[:6]}@example.com",
        **fields,
    }
    resp = await client.post("/members", json=body, headers=HEADERS)
    assert resp.status_code == 201, resp.text
    member = resp.json()
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(
            text(
                "UPDATE members SET status='active', portal_enabled=true WHERE id = :mid"
            ),
            {"mid": member["id"]},
        )
        await s.commit()
    return member


def _member_headers(member_id: str) -> dict[str, str]:
    return {**HEADERS, "X-Member-Actor-ID": member_id}


async def test_member_submit_creates_pending(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    resp = await client.post(
        "/member/me/kyc",
        json={"phone": "+256700000001", "occupation": "Farmer"},
        headers=_member_headers(member["id"]),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["proposed"]["phone"] == "+256700000001"
    assert body["proposed"]["occupation"] == "Farmer"
    assert body["proposed"]["national_id_number"] is None


async def test_member_me_kyc_includes_values_and_latest_submission(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    headers = _member_headers(member["id"])
    resp = await client.get("/member/me/kyc", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["latest_submission"] is None
    assert body["values"]["email"] == member["email"]

    await client.post("/member/me/kyc", json={"phone": "+256700000001"}, headers=headers)
    body = (await client.get("/member/me/kyc", headers=headers)).json()
    assert body["latest_submission"]["status"] == "pending"


async def test_member_resubmit_supersedes_in_place(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    headers = _member_headers(member["id"])
    first = (
        await client.post("/member/me/kyc", json={"phone": "+25670000A"}, headers=headers)
    ).json()
    second = (
        await client.post("/member/me/kyc", json={"phone": "+25670000B"}, headers=headers)
    ).json()
    assert second["id"] == first["id"]
    assert second["proposed"]["phone"] == "+25670000B"


async def test_operator_queue_lists_and_filters(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    await client.post(
        "/member/me/kyc", json={"phone": "+256700000001"}, headers=_member_headers(member["id"])
    )
    # Route-order regression: literal segment must not be swallowed by /{member_id}.
    resp = await client.get("/members/kyc-submissions", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["member_number"] == member["member_number"]
    assert rows[0]["full_name"] == member["full_name"]

    filtered = await client.get(
        "/members/kyc-submissions", params={"status": "approved"}, headers=HEADERS
    )
    assert filtered.json() == []


async def test_operator_detail_shows_proposed_vs_current(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine, phone="+256700000000")
    sub = (
        await client.post(
            "/member/me/kyc",
            json={"phone": "+256700000009"},
            headers=_member_headers(member["id"]),
        )
    ).json()
    resp = await client.get(f"/members/kyc-submissions/{sub['id']}", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["submission"]["proposed"]["phone"] == "+256700000009"
    assert body["current"]["phone"] == "+256700000000"
    assert body["member_number"] == member["member_number"]


async def test_approve_applies_fields_and_is_terminal(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    sub = (
        await client.post(
            "/member/me/kyc",
            json={"phone": "+256700000009", "next_of_kin_name": "John Doe"},
            headers=_member_headers(member["id"]),
        )
    ).json()
    resp = await client.post(
        f"/members/kyc-submissions/{sub['id']}/approve", headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"

    updated = (await client.get(f"/members/{member['id']}", headers=HEADERS)).json()
    assert updated["phone"] == "+256700000009"
    assert updated["status"] == "active"  # approval never touches status

    again = await client.post(
        f"/members/kyc-submissions/{sub['id']}/approve", headers=HEADERS
    )
    assert again.status_code == 409


async def test_approve_duplicate_national_id_409(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    await _create_active_member(client, test_engine, national_id_number="CM999999")
    member = await _create_active_member(client, test_engine)
    sub = (
        await client.post(
            "/member/me/kyc",
            json={"national_id_number": "CM999999"},
            headers=_member_headers(member["id"]),
        )
    ).json()
    resp = await client.post(
        f"/members/kyc-submissions/{sub['id']}/approve", headers=HEADERS
    )
    assert resp.status_code == 409
    assert "national_id_number" in resp.json()["detail"]


async def test_reject_requires_reason_and_surfaces_to_member(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    headers = _member_headers(member["id"])
    sub = (
        await client.post("/member/me/kyc", json={"phone": "+256700000001"}, headers=headers)
    ).json()

    missing = await client.post(
        f"/members/kyc-submissions/{sub['id']}/reject", json={}, headers=HEADERS
    )
    assert missing.status_code == 422

    resp = await client.post(
        f"/members/kyc-submissions/{sub['id']}/reject",
        json={"reason": "ID number looks wrong"},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"

    me = (await client.get("/member/me/kyc", headers=headers)).json()
    assert me["latest_submission"]["status"] == "rejected"
    assert me["latest_submission"]["rejection_reason"] == "ID number looks wrong"


async def test_unknown_submission_404(client: AsyncClient) -> None:
    resp = await client.get(f"/members/kyc-submissions/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404
    resp = await client.post(
        f"/members/kyc-submissions/{uuid.uuid4()}/approve", headers=HEADERS
    )
    assert resp.status_code == 404
