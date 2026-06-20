"""Integration tests for the /platform/approvals/* router.

Mirrors tests/modules/maker_checker/test_api.py but in platform context.
Uses the test_engine session-scoped fixture from tests/conftest.py.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.modules.maker_checker.registry import approval_registry
from app.platform_.models import PlatformUser

# Register a no-op executor for the synthetic operation used by these tests.
# Other modules register their own executors via @approval_executor at import time.
approval_registry["platform.test.op"] = AsyncMock(return_value={"done": True})


def _make_platform_session_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


async def _create_platform_user(
    factory: async_sessionmaker[AsyncSession],
    email_prefix: str,
    *,
    is_superuser: bool = True,
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"{email_prefix}-{uuid.uuid4().hex[:6]}@test.example",
            full_name=email_prefix.title(),
            is_active=True,
            is_superuser=is_superuser,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


async def test_submit_returns_201(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        r = await client.post(
            "/platform/approvals",
            json={
                "operation_type": "platform.test.op",
                "payload": {"hello": "world"},
                "required_approvals": 1,
            },
            headers=_hdr(maker.id),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert body["operation_type"] == "platform.test.op"
        assert body["requested_by"] == str(maker.id)
    finally:
        await _cleanup(factory)


async def test_submit_unknown_operation_returns_400(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        r = await client.post(
            "/platform/approvals",
            json={"operation_type": "no.such.op", "payload": {}},
            headers=_hdr(maker.id),
        )
        assert r.status_code == 400, r.text
    finally:
        await _cleanup(factory)


async def test_list_and_filter(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        # Two pending requests of the same op_type
        for _ in range(2):
            await client.post(
                "/platform/approvals",
                json={"operation_type": "platform.test.op", "payload": {}},
                headers=_hdr(maker.id),
            )
        r = await client.get("/platform/approvals", headers=_hdr(maker.id))
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 2
        assert all(item["operation_type"] == "platform.test.op" for item in body)

        # Filter by operation_type
        r2 = await client.get(
            "/platform/approvals?operation_type=platform.test.op",
            headers=_hdr(maker.id),
        )
        assert r2.status_code == 200
        assert len(r2.json()) == 2

        # Filter by non-matching operation_type
        r3 = await client.get(
            "/platform/approvals?operation_type=no.such.op",
            headers=_hdr(maker.id),
        )
        assert r3.status_code == 200
        assert r3.json() == []

        # Filter by requested_by
        r4 = await client.get(
            f"/platform/approvals?requested_by={maker.id}",
            headers=_hdr(maker.id),
        )
        assert r4.status_code == 200
        assert len(r4.json()) == 2
    finally:
        await _cleanup(factory)


async def test_get_detail_and_404(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        post = await client.post(
            "/platform/approvals",
            json={"operation_type": "platform.test.op", "payload": {}},
            headers=_hdr(maker.id),
        )
        rid = post.json()["id"]
        r = await client.get(f"/platform/approvals/{rid}", headers=_hdr(maker.id))
        assert r.status_code == 200
        assert r.json()["id"] == rid

        r404 = await client.get(
            f"/platform/approvals/{uuid.uuid4()}",
            headers=_hdr(maker.id),
        )
        assert r404.status_code == 404
    finally:
        await _cleanup(factory)


async def test_approve_executes_on_quorum(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    checker = await _create_platform_user(factory, "checker")
    try:
        post = await client.post(
            "/platform/approvals",
            json={
                "operation_type": "platform.test.op",
                "payload": {},
                "required_approvals": 1,
            },
            headers=_hdr(maker.id),
        )
        rid = post.json()["id"]
        r = await client.post(
            f"/platform/approvals/{rid}/approve",
            json={"comment": "looks good"},
            headers=_hdr(checker.id),
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "executed"
    finally:
        await _cleanup(factory)


async def test_self_approval_rejected(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        post = await client.post(
            "/platform/approvals",
            json={"operation_type": "platform.test.op", "payload": {}},
            headers=_hdr(maker.id),
        )
        rid = post.json()["id"]
        r = await client.post(
            f"/platform/approvals/{rid}/approve",
            json={},
            headers=_hdr(maker.id),
        )
        assert r.status_code == 400, r.text
        assert "self-approval" in r.text.lower()
    finally:
        await _cleanup(factory)


async def test_reject_and_self_reject_blocked(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    checker = await _create_platform_user(factory, "checker")
    try:
        post = await client.post(
            "/platform/approvals",
            json={"operation_type": "platform.test.op", "payload": {}},
            headers=_hdr(maker.id),
        )
        rid = post.json()["id"]
        # Maker cannot self-reject
        r_self = await client.post(
            f"/platform/approvals/{rid}/reject",
            json={"reason": "nope"},
            headers=_hdr(maker.id),
        )
        assert r_self.status_code == 400

        # Checker can reject
        r = await client.post(
            f"/platform/approvals/{rid}/reject",
            json={"reason": "duplicate request"},
            headers=_hdr(checker.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "rejected"
        assert body["rejection_reason"] == "duplicate request"
    finally:
        await _cleanup(factory)


async def test_list_returns_current_approvals(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    try:
        created = await client.post(
            "/platform/approvals",
            json={"operation_type": "platform.test.op", "payload": {"x": 1}},
            headers=_hdr(maker.id),
        )
        assert created.status_code == 201, created.text
        listed = await client.get("/platform/approvals", headers=_hdr(maker.id))
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body[0]["current_approvals"] == 0
        assert body[0]["required_approvals"] == 1
    finally:
        await _cleanup(factory)


async def test_detail_returns_actions_trail(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    checker = await _create_platform_user(factory, "checker")
    try:
        created = await client.post(
            "/platform/approvals",
            json={"operation_type": "platform.test.op", "payload": {"x": 1}},
            headers=_hdr(maker.id),
        )
        rid = created.json()["id"]
        # Checker approves -> with required_approvals=1 this executes.
        approved = await client.post(
            f"/platform/approvals/{rid}/approve",
            json={"comment": "looks good"},
            headers=_hdr(checker.id),
        )
        assert approved.status_code == 200, approved.text

        detail = await client.get(f"/platform/approvals/{rid}", headers=_hdr(maker.id))
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["current_approvals"] == 1
        assert len(body["actions"]) == 1
        assert body["actions"][0]["action"] == "approve"
        assert body["actions"][0]["actor_user_id"] == str(checker.id)
        assert body["actions"][0]["comment"] == "looks good"
    finally:
        await _cleanup(factory)


async def test_detail_quorum_two_reports_one_of_two(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    checker = await _create_platform_user(factory, "checker")
    try:
        created = await client.post(
            "/platform/approvals",
            json={
                "operation_type": "platform.test.op",
                "payload": {"x": 1},
                "required_approvals": 2,
            },
            headers=_hdr(maker.id),
        )
        rid = created.json()["id"]
        await client.post(
            f"/platform/approvals/{rid}/approve",
            json={},
            headers=_hdr(checker.id),
        )
        detail = (await client.get(f"/platform/approvals/{rid}", headers=_hdr(maker.id))).json()
        assert detail["current_approvals"] == 1
        assert detail["required_approvals"] == 2
        assert detail["status"] == "pending"
        assert len(detail["actions"]) == 1
    finally:
        await _cleanup(factory)


async def test_cancel_maker_only(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_platform_user(factory, "maker")
    other = await _create_platform_user(factory, "other")
    try:
        post = await client.post(
            "/platform/approvals",
            json={
                "operation_type": "platform.test.op",
                "payload": {},
                "required_approvals": 2,
            },
            headers=_hdr(maker.id),
        )
        rid = post.json()["id"]

        # A different platform user cannot cancel
        r_other = await client.post(
            f"/platform/approvals/{rid}/cancel",
            json={},
            headers=_hdr(other.id),
        )
        assert r_other.status_code == 400

        # Maker can cancel
        r = await client.post(
            f"/platform/approvals/{rid}/cancel",
            json={},
            headers=_hdr(maker.id),
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"
    finally:
        await _cleanup(factory)
