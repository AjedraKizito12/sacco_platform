"""Notifications HTTP APIs: self feed/read/preferences (3 audiences) + platform admin."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from app.core.db import get_platform_session, get_tenant_session
from app.core.notifications.seed_templates import seed_default_templates
from app.core.notifications.service import NotificationService
from app.main import app, lifespan
from app.modules.members.models import Member
from app.platform_.models import PlatformUser

SCHEMA = "tenant_test"
HEADERS = {"X-Tenant-Slug": "test-tenant"}


def _tenant_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    return _override


def _platform_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    return _override


async def _seed_admin(engine: AsyncEngine) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    admin_id = uuid.uuid4()
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(
            PlatformUser(
                id=admin_id,
                email=f"admin-{admin_id.hex[:6]}@p.test",
                full_name="Admin",
                is_active=True,
                is_superuser=False,
                role="admin",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    return admin_id


async def _seed_member(engine: AsyncEngine) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
        m = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}",
            full_name="Notify Member",
            date_of_birth=date(1990, 1, 1),
            gender="female",
            status="active",
            portal_enabled=True,
            email=f"m-{uuid.uuid4().hex[:6]}@example.com",
        )
        s.add(m)
        await s.flush()
        member_id = m.id
    return member_id


async def _publish_tenant(
    engine: AsyncEngine, *, kind: str, user_id: uuid.UUID, **overrides: object
) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
        await seed_default_templates(s)
        kwargs: dict = {
            "event_code": "system_announcement",
            "recipient_kind": kind,
            "recipient_user_id": user_id,
            "context": {"title": "Hello", "body": "World"},
        }
        kwargs.update(overrides)
        event = await NotificationService(s).publish(**kwargs)
        await s.commit()
        return event.id


async def _publish_platform(
    engine: AsyncEngine, *, user_id: uuid.UUID, **overrides: object
) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
        s.sync_session.info["is_platform"] = True
        await seed_default_templates(s)
        kwargs: dict = {
            "event_code": "system_announcement",
            "recipient_kind": "platform_user",
            "recipient_user_id": user_id,
            "context": {"title": "P", "body": "B"},
        }
        kwargs.update(overrides)
        event = await NotificationService(s).publish(**kwargs)
        await s.commit()
        return event.id


@pytest.fixture
async def client(test_engine: AsyncEngine, tenant_actor_id: uuid.UUID):  # noqa: ANN201
    admin_id = await _seed_admin(test_engine)
    app.dependency_overrides[get_tenant_session] = _tenant_override(test_engine)
    app.dependency_overrides[get_platform_session] = _platform_override(test_engine)
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = "test-tenant"
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        c.headers["X-Platform-Actor-ID"] = str(admin_id)
        c.admin_id = admin_id  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)
    app.dependency_overrides.pop(get_platform_session, None)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        for tbl in (
            f"{SCHEMA}.notification_deliveries",
            f"{SCHEMA}.notification_preferences",
            f"{SCHEMA}.notification_events",
            "platform.notification_deliveries",
            "platform.notification_preferences",
            "platform.notification_events",
        ):
            await s.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        await s.execute(
            text("DELETE FROM audit_log WHERE table_name = 'members'")
        )
        await s.execute(text("DELETE FROM members"))
        await s.execute(
            text("DELETE FROM platform.platform_users WHERE role = 'admin' AND email LIKE 'admin-%@p.test'")
        )
        await s.commit()


def _member_headers(member_id: uuid.UUID) -> dict[str, str]:
    return {**HEADERS, "X-Member-Actor-ID": str(member_id)}


# ── Self feed ─────────────────────────────────────────────────────────────────


async def test_member_feed_scoping_read_and_unread_only(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_a = await _seed_member(test_engine)
    member_b = await _seed_member(test_engine)
    first = await _publish_tenant(test_engine, kind="member", user_id=member_a)
    await _publish_tenant(test_engine, kind="member", user_id=member_a)
    other = await _publish_tenant(test_engine, kind="member", user_id=member_b)

    resp = await client.get("/member/notifications/me", headers=_member_headers(member_a))
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 2
    assert items[0]["title"] == "Hello"
    assert items[0]["body"] == "World"
    assert all(i["read_at"] is None for i in items)

    # Mark one read; unread_only then returns the other.
    read = await client.post(
        f"/member/notifications/me/{first}/read", headers=_member_headers(member_a)
    )
    assert read.status_code == 204
    unread = await client.get(
        "/member/notifications/me",
        params={"unread_only": "true"},
        headers=_member_headers(member_a),
    )
    assert [i["id"] for i in unread.json()] != [str(first)]
    assert len(unread.json()) == 1

    # Cross-member read -> 404.
    cross = await client.post(
        f"/member/notifications/me/{other}/read", headers=_member_headers(member_a)
    )
    assert cross.status_code == 404


async def test_tenant_operator_feed_and_read(
    client: AsyncClient, test_engine: AsyncEngine, tenant_actor_id: uuid.UUID
) -> None:
    event_id = await _publish_tenant(
        test_engine, kind="tenant_user", user_id=tenant_actor_id
    )
    resp = await client.get("/notifications/me", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert [i["id"] for i in resp.json()] == [str(event_id)]
    assert (
        await client.post(f"/notifications/me/{event_id}/read", headers=HEADERS)
    ).status_code == 204
    unread = await client.get(
        "/notifications/me", params={"unread_only": "true"}, headers=HEADERS
    )
    assert unread.json() == []


async def test_platform_feed(client: AsyncClient, test_engine: AsyncEngine) -> None:
    admin_id: uuid.UUID = client.admin_id  # type: ignore[attr-defined]
    await _publish_platform(test_engine, user_id=admin_id)
    resp = await client.get("/platform/notifications/me")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "P"


# ── Preferences ───────────────────────────────────────────────────────────────


async def test_preferences_roundtrip(client: AsyncClient) -> None:
    empty = await client.get("/notifications/me/preferences", headers=HEADERS)
    assert empty.status_code == 200
    assert empty.json() == []

    put = await client.put(
        "/notifications/me/preferences",
        json=[{"event_code": "system_announcement", "channel": "email", "enabled": False}],
        headers=HEADERS,
    )
    assert put.status_code == 200, put.text
    stored = put.json()
    assert len(stored) == 1
    assert stored[0]["enabled"] is False

    got = await client.get("/notifications/me/preferences", headers=HEADERS)
    assert got.json() == stored

    bad = await client.put(
        "/notifications/me/preferences",
        json=[{"event_code": "nope", "channel": "email", "enabled": False}],
        headers=HEADERS,
    )
    assert bad.status_code == 422


# ── Platform admin ────────────────────────────────────────────────────────────


async def test_admin_templates_list_create_conflict_patch(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        await seed_default_templates(s)
        await s.commit()
    listed = await client.get("/platform/notifications/templates")
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) > 0

    dup = listed.json()[0]
    conflict = await client.post(
        "/platform/notifications/templates",
        json={
            "code": dup["code"],
            "channel": dup["channel"],
            "locale": dup["locale"],
            "subject_template": "x",
            "body_text": "y",
            "variables": {},
        },
    )
    assert conflict.status_code == 409

    patched = await client.patch(
        f"/platform/notifications/templates/{dup['id']}",
        json={"body_text": "PATCHED BODY"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["body_text"] == "PATCHED BODY"


async def test_admin_events_search_and_resend(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    admin_id: uuid.UUID = client.admin_id  # type: ignore[attr-defined]
    event_id = await _publish_platform(test_engine, user_id=admin_id)

    found = await client.get(
        "/platform/notifications/events", params={"status": "queued"}
    )
    assert found.status_code == 200, found.text
    assert str(event_id) in [e["id"] for e in found.json()]

    # Resend on a queued event -> 409.
    conflict = await client.post(f"/platform/notifications/events/{event_id}/resend")
    assert conflict.status_code == 409

    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(
            text("UPDATE platform.notification_events SET status = 'failed' WHERE id = :i"),
            {"i": str(event_id)},
        )
        await s.commit()
    ok = await client.post(f"/platform/notifications/events/{event_id}/resend")
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "queued"

    missing = await client.post(
        f"/platform/notifications/events/{uuid.uuid4()}/resend"
    )
    assert missing.status_code == 404


async def test_member_cannot_reach_platform_admin_api(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member(test_engine)
    resp = await client.get(
        "/platform/notifications/templates",
        headers={**_member_headers(member_id), "X-Platform-Actor-ID": str(member_id)},
    )
    # The member id is not a platform user -> stub auth rejects.
    assert resp.status_code in (401, 403)
