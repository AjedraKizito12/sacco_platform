"""Integration: request → checker approves via ApprovalService.approve
→ platform.start_impersonation executor inserts the support_impersonations row.

The test calls ApprovalService.approve directly (not via HTTP) because we
want to validate the executor's behaviour in isolation. The HTTP path is
tested in 02b.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Importing this module registers the executor in approval_registry.
import app.platform_.impersonations.executors  # noqa: F401
from app.modules.maker_checker.service import ApprovalService
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.service import ImpersonationService
from app.platform_.models import PlatformUser, Tenant


async def _seed(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[PlatformUser, PlatformUser, Tenant]:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        maker = PlatformUser(
            email=f"maker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Maker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        checker = PlatformUser(
            email=f"checker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Checker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        tenant = Tenant(
            slug=f"t-{uuid.uuid4().hex[:6]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:6]}",
            name="T", is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add_all([maker, checker, tenant])
    return maker, checker, tenant


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


async def test_executor_creates_impersonation_row(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    try:
        # 1. Request the impersonation (creates pending ApprovalRequest)
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            approval = await ImpersonationService(s).request(
                platform_user_id=maker.id,
                tenant_id=tenant.id,
                reason="Investigating member balance issue reported by ops",
            )
            approval_id = approval.id

        # 2. Checker approves — executor runs inside the same tx
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            executed = await ApprovalService(s).approve(
                request_id=approval_id,
                actor_user_id=checker.id,
                comment="Verified ticket #1234",
            )
            assert executed.status == "executed"
            execution_result = executed.execution_result or {}
            impersonation_id = uuid.UUID(execution_result["impersonation_id"])

        # 3. Confirm a row exists and is well-formed
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, impersonation_id)
            assert row is not None
            assert row.platform_user_id == maker.id
            assert row.tenant_id == tenant.id
            assert row.tenant_user_id is None  # 02b populates this
            assert row.approval_request_id == approval_id
            assert row.ended_at is None
            assert row.revoked_at is None
            now = datetime.now(UTC)
            assert row.started_at <= now
            assert row.expires_at > now
            # Expires within 30 min by default
            assert row.expires_at <= now + timedelta(minutes=31)
    finally:
        await _cleanup(factory)


async def test_executor_idempotent_on_re_execution(test_engine: AsyncEngine) -> None:
    """If executor runs twice for the same approval payload (shouldn't happen
    but defensive), the second run should not create a duplicate row.

    The executor uses approval_request_id as the natural key for dedup.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, tenant = await _seed(factory)
    try:
        # Request + approve (creates row #1)
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            approval = await ImpersonationService(s).request(
                platform_user_id=maker.id,
                tenant_id=tenant.id,
                reason="Investigating member balance issue reported by ops",
            )
            approval_id = approval.id

        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            await ApprovalService(s).approve(
                request_id=approval_id, actor_user_id=checker.id,
            )

        # Call the executor again directly with the same payload
        from app.platform_.impersonations.executors import (
            execute_start_impersonation,
        )
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            result = await execute_start_impersonation(
                s,
                {
                    "platform_user_id": str(maker.id),
                    "tenant_id": str(tenant.id),
                    "reason": "Investigating member balance issue reported by ops",
                    "approval_request_id": str(approval_id),
                },
            )
            assert result.get("idempotent") is True

        # Still only one row
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            rows = (
                await s.execute(
                    select(SupportImpersonation).where(
                        SupportImpersonation.approval_request_id == approval_id
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
    finally:
        await _cleanup(factory)
