"""Maker-checker lifecycle notifications (increment 2)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.notifications.models import (
    PlatformNotificationEvent,
    TenantNotificationEvent,
)
from app.core.notifications.seed_templates import seed_default_templates
from app.modules.iam.tenant_users.models import TenantUser
from app.modules.maker_checker.registry import approval_executor
from app.modules.maker_checker.service import ApprovalService
from app.platform_.models import PlatformUser

SCHEMA = "tenant_test"


@approval_executor("test.notify_noop")
async def _noop(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True}


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
        for tbl in (
            f"{SCHEMA}.notification_events",
            "platform.notification_events",
            f"{SCHEMA}.approval_actions",
            f"{SCHEMA}.approval_requests",
            "platform.approval_actions",
            "platform.approval_requests",
        ):
            await s.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        await s.execute(
            text("DELETE FROM tenant_users WHERE email LIKE 'mcnotify-%'")
        )
        await s.execute(
            text("DELETE FROM platform.platform_users WHERE email LIKE 'mcnotify-%'")
        )
        await s.execute(
            text(
                "DELETE FROM audit_log WHERE table_name IN "
                "('approval_requests', 'tenant_users')"
            )
        )
        await s.execute(
            text(
                "DELETE FROM platform.audit_log WHERE table_name IN "
                "('approval_requests', 'platform_users')"
            )
        )
        await s.commit()


async def _seed_tenant_user(s: AsyncSession, tag: str) -> TenantUser:
    user = TenantUser(
        email=f"mcnotify-{tag}-{uuid.uuid4().hex[:6]}@t.test",
        full_name=tag,
        hashed_password=None,
        is_active=True,
        is_admin=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    s.add(user)
    await s.flush()
    return user


async def test_submit_notifies_other_staff_not_maker(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        maker = await _seed_tenant_user(s, "maker")
        checker = await _seed_tenant_user(s, "checker")
        bystander = await _seed_tenant_user(s, "bystander")
        request = await ApprovalService(s).submit(
            operation_type="test.notify_noop",
            payload={},
            requested_by=maker.id,
        )
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        rows = list(
            (
                await s.execute(
                    select(TenantNotificationEvent).where(
                        TenantNotificationEvent.event_code == "maker_checker_pending",
                        TenantNotificationEvent.dedupe_key.like(f"mc_pending:{request.id}:%"),
                    )
                )
            ).scalars()
        )
    recipients = {r.recipient_user_id for r in rows}
    # Other suites may leave extra tenant_users behind — assert containment,
    # never exact equality.
    assert {checker.id, bystander.id} <= recipients
    assert maker.id not in recipients
    assert all(r.context["operation_type"] == "test.notify_noop" for r in rows)
    assert all(r.context["requested_by_label"] == maker.email for r in rows)


async def test_final_approval_notifies_maker(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        maker = await _seed_tenant_user(s, "maker")
        checker = await _seed_tenant_user(s, "checker")
        svc = ApprovalService(s)
        request = await svc.submit(
            operation_type="test.notify_noop", payload={}, requested_by=maker.id
        )
        await svc.approve(request_id=request.id, actor_user_id=checker.id)
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.dedupe_key == f"mc_approved:{request.id}"
                )
            )
        ).scalars().one()
    assert row.recipient_user_id == maker.id
    assert row.event_code == "maker_checker_approved"


async def test_reject_notifies_maker_with_reason(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        maker = await _seed_tenant_user(s, "maker")
        checker = await _seed_tenant_user(s, "checker")
        svc = ApprovalService(s)
        request = await svc.submit(
            operation_type="test.notify_noop", payload={}, requested_by=maker.id
        )
        await svc.reject(
            request_id=request.id, actor_user_id=checker.id, reason="Not today"
        )
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.dedupe_key == f"mc_rejected:{request.id}"
                )
            )
        ).scalars().one()
    assert row.recipient_user_id == maker.id
    assert row.context["reason"] == "Not today"


async def test_non_staff_maker_is_skipped_silently(test_engine: AsyncEngine) -> None:
    """Member-submitted operations: pending still fans out; no decided notice."""
    member_maker = uuid.uuid4()  # not a tenant_users row
    factory = _factory(test_engine)
    async with factory() as s:
        await _set_path(s)
        checker = await _seed_tenant_user(s, "checker")
        svc = ApprovalService(s)
        request = await svc.submit(
            operation_type="test.notify_noop", payload={}, requested_by=member_maker
        )
        await svc.approve(request_id=request.id, actor_user_id=checker.id)
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        pending = list(
            (
                await s.execute(
                    select(TenantNotificationEvent).where(
                        TenantNotificationEvent.dedupe_key.like(
                            f"mc_pending:{request.id}:%"
                        )
                    )
                )
            ).scalars()
        )
        decided = (
            await s.execute(
                select(TenantNotificationEvent).where(
                    TenantNotificationEvent.dedupe_key == f"mc_approved:{request.id}"
                )
            )
        ).scalars().first()
    pending_recipients = {r.recipient_user_id for r in pending}
    assert checker.id in pending_recipients
    assert member_maker not in pending_recipients
    assert all(
        r.context["requested_by_label"] == str(member_maker) for r in pending
    )
    assert decided is None


async def test_platform_scope_pending_targets_admin_tiers_only(
    test_engine: AsyncEngine,
) -> None:
    factory = _factory(test_engine)
    async with factory() as s:
        s.sync_session.info["is_platform"] = True
        await _set_path(s)
        now = datetime.now(UTC)
        maker = PlatformUser(
            email=f"mcnotify-pm-{uuid.uuid4().hex[:6]}@p.test", full_name="PM",
            is_active=True, is_superuser=False, role="admin",
            created_at=now, updated_at=now,
        )
        admin = PlatformUser(
            email=f"mcnotify-pa-{uuid.uuid4().hex[:6]}@p.test", full_name="PA",
            is_active=True, is_superuser=False, role="admin",
            created_at=now, updated_at=now,
        )
        support = PlatformUser(
            email=f"mcnotify-ps-{uuid.uuid4().hex[:6]}@p.test", full_name="PS",
            is_active=True, is_superuser=False, role="support",
            created_at=now, updated_at=now,
        )
        s.add_all([maker, admin, support])
        await s.flush()
        request = await ApprovalService(s).submit(
            operation_type="test.notify_noop", payload={}, requested_by=maker.id
        )
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        rows = list(
            (
                await s.execute(
                    select(PlatformNotificationEvent).where(
                        PlatformNotificationEvent.dedupe_key.like(
                            f"mc_pending:{request.id}:%"
                        )
                    )
                )
            ).scalars()
        )
    assert {r.recipient_user_id for r in rows} == {admin.id}
