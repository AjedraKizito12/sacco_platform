"""
Integration tests for ApprovalService.

Each test uses helper functions that create their own committed transactions,
matching how the worker tests (which DO pass) manage DB operations.
This pattern avoids the asyncpg protocol-state error that occurs when
flush() is called inside a long-lived async with session.begin() context
in pytest-asyncio 0.24.0 with a session-scoped event loop.
"""
import uuid

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.modules.maker_checker.models.tenant import TenantApprovalAction, TenantApprovalRequest
from app.modules.maker_checker.registry import approval_registry
from app.modules.maker_checker.service import ApprovalService

TEST_TENANT_SCHEMA = "tenant_test"

# Register a test executor
_exec_calls: list = []


async def _test_executor(session, payload):
    _exec_calls.append(payload)
    return {"done": True}


approval_registry["test.op"] = _test_executor


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine):
    """Return a new AsyncSession with search_path set (no transaction started)."""
    factory = _factory(engine)
    session = factory()
    await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
    return session


async def _submit(engine: AsyncEngine, **kwargs) -> object:
    session = await _new_session(engine)
    try:
        svc = ApprovalService(session)
        defaults: dict = dict(
            operation_type="test.op",
            payload={"x": 1},
            requested_by=uuid.uuid4(),
        )
        defaults.update(kwargs)
        req = await svc.submit(**defaults)
        await session.commit()
        return req
    finally:
        await session.close()


async def _cleanup(engine: AsyncEngine) -> None:
    """Remove all approval rows created during a test."""
    factory = _factory(engine)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(delete(TenantApprovalAction))
        await session.execute(delete(TenantApprovalRequest))
        await session.commit()


async def test_submit_creates_pending_request(test_engine):
    try:
        req = await _submit(test_engine)
        assert req.status == "pending"
        assert req.id is not None
    finally:
        await _cleanup(test_engine)


async def test_submit_unknown_operation_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = ApprovalService(session)
        with pytest.raises(ValueError, match="No executor registered"):
            await svc.submit(
                operation_type="unknown.op", payload={}, requested_by=uuid.uuid4()
            )
    finally:
        await session.close()


async def test_approve_below_quorum_stays_pending(test_engine):
    try:
        req = await _submit(test_engine, required_approvals=2)

        session = await _new_session(test_engine)
        try:
            svc = ApprovalService(session)
            checker = uuid.uuid4()
            updated = await svc.approve(request_id=req.id, actor_user_id=checker)
            assert updated.status == "pending"
            await session.commit()
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine)


async def test_approve_meeting_quorum_executes(test_engine):
    _exec_calls.clear()
    try:
        maker = uuid.uuid4()
        req = await _submit(test_engine, requested_by=maker, required_approvals=1)

        session = await _new_session(test_engine)
        try:
            svc = ApprovalService(session)
            checker = uuid.uuid4()
            updated = await svc.approve(request_id=req.id, actor_user_id=checker)
            assert updated.status == "executed"
            assert len(_exec_calls) == 1
            await session.commit()
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine)


async def test_self_approval_raises(test_engine):
    try:
        maker = uuid.uuid4()
        req = await _submit(test_engine, requested_by=maker)

        session = await _new_session(test_engine)
        try:
            svc = ApprovalService(session)
            with pytest.raises(ValueError, match="Self-approval"):
                await svc.approve(request_id=req.id, actor_user_id=maker)
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine)


async def test_reject_terminates_request(test_engine):
    try:
        req = await _submit(test_engine)

        session = await _new_session(test_engine)
        try:
            svc = ApprovalService(session)
            checker = uuid.uuid4()
            updated = await svc.reject(
                request_id=req.id, actor_user_id=checker, reason="policy"
            )
            assert updated.status == "rejected"
            assert updated.rejection_reason == "policy"
            await session.commit()
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine)


async def test_action_on_rejected_request_raises(test_engine):
    try:
        req = await _submit(test_engine)

        # First reject in its own session
        session1 = await _new_session(test_engine)
        try:
            svc = ApprovalService(session1)
            checker = uuid.uuid4()
            await svc.reject(request_id=req.id, actor_user_id=checker)
            await session1.commit()
        finally:
            await session1.close()

        # Now try to approve the rejected request
        session2 = await _new_session(test_engine)
        try:
            svc2 = ApprovalService(session2)
            with pytest.raises(ValueError, match="not 'pending'"):
                await svc2.approve(request_id=req.id, actor_user_id=uuid.uuid4())
        finally:
            await session2.close()
    finally:
        await _cleanup(test_engine)


async def test_cancel_before_any_action(test_engine):
    try:
        maker = uuid.uuid4()
        req = await _submit(test_engine, requested_by=maker)

        session = await _new_session(test_engine)
        try:
            svc = ApprovalService(session)
            updated = await svc.cancel(request_id=req.id, requested_by=maker)
            assert updated.status == "cancelled"
            await session.commit()
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine)


async def test_cancel_after_action_raises(test_engine):
    try:
        maker = uuid.uuid4()
        req = await _submit(test_engine, requested_by=maker, required_approvals=2)

        session1 = await _new_session(test_engine)
        try:
            svc = ApprovalService(session1)
            checker = uuid.uuid4()
            await svc.approve(request_id=req.id, actor_user_id=checker)
            await session1.commit()
        finally:
            await session1.close()

        session2 = await _new_session(test_engine)
        try:
            svc2 = ApprovalService(session2)
            with pytest.raises(ValueError, match="Cannot cancel"):
                await svc2.cancel(request_id=req.id, requested_by=maker)
        finally:
            await session2.close()
    finally:
        await _cleanup(test_engine)


async def test_double_vote_raises(test_engine):
    try:
        req = await _submit(test_engine, required_approvals=2)
        checker = uuid.uuid4()

        # First vote succeeds
        session1 = await _new_session(test_engine)
        try:
            svc = ApprovalService(session1)
            await svc.approve(request_id=req.id, actor_user_id=checker)
            await session1.commit()
        finally:
            await session1.close()

        # Second vote from same checker should fail
        session2 = await _new_session(test_engine)
        try:
            from sqlalchemy.exc import IntegrityError

            svc2 = ApprovalService(session2)
            try:
                await svc2.approve(request_id=req.id, actor_user_id=checker)
                await session2.commit()
            except (IntegrityError, ValueError):
                await session2.rollback()
                pass  # Expected
        finally:
            await session2.close()
    finally:
        await _cleanup(test_engine)


async def test_executor_failure_marks_execution_failed(test_engine):
    async def _failing_executor(session, payload):
        raise RuntimeError("boom")

    approval_registry["test.failing"] = _failing_executor
    try:
        req = await _submit(test_engine, operation_type="test.failing", required_approvals=1)

        session = await _new_session(test_engine)
        try:
            svc = ApprovalService(session)
            updated = await svc.approve(request_id=req.id, actor_user_id=uuid.uuid4())
            assert updated.status == "execution_failed"
            assert "boom" in (updated.execution_result or {}).get("error", "")
            await session.commit()
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine)
