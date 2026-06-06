"""Unit tests for ImpersonationService.

The service handles the lifecycle of an impersonation request:
    request → returns approval_request_id (no impersonation row yet)
    (checker approves via /platform/approvals, executor creates the row)
    end / revoke / queries → operate on the row

The executor is tested separately in test_executor.py.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.maker_checker.registry import approval_registry
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.service import ImpersonationService
from app.platform_.models import PlatformUser, Tenant


async def _seed(factory: async_sessionmaker[AsyncSession]) -> tuple[PlatformUser, Tenant]:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"u-{uuid.uuid4().hex[:6]}@test.example",
            full_name="U",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:6]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:6]}",
            name="T",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add_all([u, t])
    return u, t


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.support_impersonations"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


# Register a no-op stub for the executor — the real one lands in Task 6;
# the service tests do not exercise the executor.
approval_registry.setdefault(
    "platform.start_impersonation",
    AsyncMock(return_value={"impersonation_id": str(uuid.uuid4())}),
)


async def test_request_submits_approval(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user, tenant = await _seed(factory)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            approval = await ImpersonationService(s).request(
                platform_user_id=user.id,
                tenant_id=tenant.id,
                reason="Investigating reported balance discrepancy in tenant",
            )
            assert approval.operation_type == "platform.start_impersonation"
            assert approval.payload["platform_user_id"] == str(user.id)
            assert approval.payload["tenant_id"] == str(tenant.id)
            assert approval.payload["reason"].startswith("Investigating")
            assert approval.status == "pending"
    finally:
        await _cleanup(factory)


async def test_request_rejects_short_reason(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user, tenant = await _seed(factory)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            with pytest.raises(ValueError, match="reason"):
                await ImpersonationService(s).request(
                    platform_user_id=user.id,
                    tenant_id=tenant.id,
                    reason="short",
                )
    finally:
        await _cleanup(factory)


async def test_request_rejects_unknown_tenant(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user, _ = await _seed(factory)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            with pytest.raises(ValueError, match="not found"):
                await ImpersonationService(s).request(
                    platform_user_id=user.id,
                    tenant_id=uuid.uuid4(),
                    reason="Reason long enough to pass validation",
                )
    finally:
        await _cleanup(factory)


async def test_end_marks_ended(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user, tenant = await _seed(factory)
    # Create an impersonation row directly (simulating a post-approval state)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        imp = SupportImpersonation(
            platform_user_id=user.id,
            tenant_id=tenant.id,
            reason="r" * 10,
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(imp)
    imp_id = imp.id
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            await ImpersonationService(s).end(impersonation_id=imp_id, ended_by=user.id)

        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, imp_id)
            assert row is not None
            assert row.ended_at is not None
            assert row.ended_by == user.id
    finally:
        await _cleanup(factory)


async def test_revoke_marks_revoked_by_different_user(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, tenant = await _seed(factory)
    other, _ = await _seed(factory)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        imp = SupportImpersonation(
            platform_user_id=maker.id,
            tenant_id=tenant.id,
            reason="r" * 10,
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(imp)
    imp_id = imp.id
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            await ImpersonationService(s).revoke(
                impersonation_id=imp_id, revoked_by=other.id
            )
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, imp_id)
            assert row is not None
            assert row.revoked_at is not None
            assert row.revoked_by == other.id
    finally:
        await _cleanup(factory)


async def test_is_active_helper(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user, tenant = await _seed(factory)
    now = datetime.now(UTC)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        active = SupportImpersonation(
            platform_user_id=user.id, tenant_id=tenant.id, reason="r" * 10,
            started_at=now, expires_at=now + timedelta(minutes=10),
            created_at=now, updated_at=now,
        )
        expired = SupportImpersonation(
            platform_user_id=user.id, tenant_id=tenant.id, reason="r" * 10,
            started_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
            created_at=now, updated_at=now,
        )
        ended = SupportImpersonation(
            platform_user_id=user.id, tenant_id=tenant.id, reason="r" * 10,
            started_at=now, expires_at=now + timedelta(minutes=10),
            ended_at=now, ended_by=user.id,
            created_at=now, updated_at=now,
        )
        s.add_all([active, expired, ended])
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            svc = ImpersonationService(s)
            assert await svc.is_active(active.id) is True
            assert await svc.is_active(expired.id) is False
            assert await svc.is_active(ended.id) is False
    finally:
        await _cleanup(factory)


async def test_get_active_for_user_filters_correctly(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user_a, tenant = await _seed(factory)
    user_b, _ = await _seed(factory)
    now = datetime.now(UTC)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        # 2 active for user_a, 1 active for user_b
        for _ in range(2):
            s.add(
                SupportImpersonation(
                    platform_user_id=user_a.id, tenant_id=tenant.id, reason="r" * 10,
                    started_at=now, expires_at=now + timedelta(minutes=10),
                    created_at=now, updated_at=now,
                )
            )
        s.add(
            SupportImpersonation(
                platform_user_id=user_b.id, tenant_id=tenant.id, reason="r" * 10,
                started_at=now, expires_at=now + timedelta(minutes=10),
                created_at=now, updated_at=now,
            )
        )
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            svc = ImpersonationService(s)
            rows_a = await svc.get_active_for_user(platform_user_id=user_a.id)
            rows_b = await svc.get_active_for_user(platform_user_id=user_b.id)
            assert len(rows_a) == 2
            assert len(rows_b) == 1
    finally:
        await _cleanup(factory)
