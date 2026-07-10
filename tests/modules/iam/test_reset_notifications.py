"""password_reset notification notices from the four reset flows (increment 2)."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.notifications.models import (
    PlatformNotificationEvent,
    TenantNotificationEvent,
)
from app.modules.iam.member_auth.service import MemberAuthService
from app.modules.iam.passwords.service import hash_password
from app.modules.iam.platform_auth.service import PlatformAuthService
from app.modules.iam.tenant_auth.service import TenantAuthService
from app.modules.iam.tenant_users.models import TenantUser
from app.modules.members.models import Member
from app.platform_.models import PlatformUser
from app.platform_.tenant_users_admin.service import TenantUsersAdminService

SCHEMA = "tenant_test"
_SLUG = "test-tenant"
_HASHED = hash_password("CorrectHorseBatteryStaple!")


def _factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture(autouse=True)
async def _clean(test_engine: AsyncEngine):  # noqa: ANN201
    yield
    factory = _factory(test_engine)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text(f"DELETE FROM {SCHEMA}.notification_events"))  # noqa: S608
        await s.execute(text("DELETE FROM platform.notification_events"))
        await s.execute(
            text("DELETE FROM audit_log WHERE table_name IN ('tenant_users', 'members')")
        )
        await s.execute(
            text("DELETE FROM platform.audit_log WHERE table_name = 'platform_users'")
        )
        await s.execute(
            text("DELETE FROM tenant_users WHERE email LIKE 'resetnotify-%'")
        )
        await s.execute(text("DELETE FROM members WHERE email LIKE 'resetnotify-%'"))
        await s.execute(
            text("DELETE FROM platform.platform_users WHERE email LIKE 'resetnotify-%'")
        )
        await s.commit()


async def test_platform_reset_request_publishes_notice(test_engine: AsyncEngine) -> None:
    email = f"resetnotify-{uuid.uuid4().hex[:6]}@p.test"
    factory = _factory(test_engine)
    async with factory() as s:
        s.sync_session.info["is_platform"] = True
        await _set_path(s)
        user = PlatformUser(
            email=email, full_name="P Reset", hashed_password=_HASHED,
            is_active=True, is_superuser=False, role="support",
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(user)
        await s.flush()
        user_id = user.id
        svc = PlatformAuthService(db=s, key_service=MagicMock(), redis=None)
        assert await svc.reset_request(email) is None
        # Unknown email: still None, and no extra event.
        assert await svc.reset_request("resetnotify-ghost@nowhere.test") is None
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        rows = list(
            (
                await s.execute(
                    select(PlatformNotificationEvent).where(
                        PlatformNotificationEvent.event_code == "password_reset",
                        PlatformNotificationEvent.recipient_user_id == user_id,
                    )
                )
            ).scalars()
        )
    assert len(rows) == 1
    assert rows[0].recipient_kind == "platform_user"
    assert rows[0].recipient_user_id == user_id
    assert rows[0].recipient_email == email


async def test_tenant_reset_request_publishes_notice(test_engine: AsyncEngine) -> None:
    email = f"resetnotify-{uuid.uuid4().hex[:6]}@t.test"
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        user = TenantUser(
            email=email, full_name="T Reset", hashed_password=_HASHED,
            is_active=True, is_admin=False,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(user)
        await s.flush()
        user_id = user.id
        svc = TenantAuthService(
            db=s, key_service=MagicMock(), redis=None, tenant_slug=_SLUG
        )
        await svc.reset_request(email)
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.event_code == "password_reset",
                    TenantNotificationEvent.recipient_user_id == user_id,
                )
            )
        ).scalars().one()
    assert row.recipient_kind == "tenant_user"
    assert row.recipient_email == email


async def test_member_reset_request_publishes_notice(test_engine: AsyncEngine) -> None:
    email = f"resetnotify-{uuid.uuid4().hex[:6]}@m.test"
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        member = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}", full_name="M Reset",
            date_of_birth=date(1990, 1, 1), gender="female", status="active",
            email=email, portal_enabled=True, hashed_password=_HASHED,
        )
        s.add(member)
        await s.flush()
        member_id = member.id
        svc = MemberAuthService(
            db=s, key_service=MagicMock(), redis=None, tenant_slug=_SLUG
        )
        await svc.reset_request(email)
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.event_code == "password_reset",
                    TenantNotificationEvent.recipient_user_id == member_id,
                )
            )
        ).scalars().one()
    assert row.recipient_kind == "member"
    assert row.recipient_email == email


async def test_admin_initiated_reset_publishes_notice(test_engine: AsyncEngine) -> None:
    email = f"resetnotify-{uuid.uuid4().hex[:6]}@a.test"
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        user = TenantUser(
            email=email, full_name="Admin Reset Target", hashed_password=_HASHED,
            is_active=True, is_admin=False,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(user)
        await s.flush()
        user_id = user.id
        svc = TenantUsersAdminService(session=s, redis=None)
        _, token = await svc.initiate_password_reset(user_id=user_id)
        assert token
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.event_code == "password_reset",
                    TenantNotificationEvent.recipient_user_id == user_id,
                )
            )
        ).scalars().one()
    assert row.recipient_kind == "tenant_user"
