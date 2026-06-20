from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import structlog
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.audit.service import PlatformAuditService, TenantAuditService
from app.core.outbox.publisher import EventPublisher
from app.modules.maker_checker.models.platform import (
    PlatformApprovalAction,
    PlatformApprovalRequest,
)
from app.modules.maker_checker.models.tenant import TenantApprovalAction, TenantApprovalRequest
from app.modules.maker_checker.registry import approval_registry
from app.workers.celery_app import celery_app

if TYPE_CHECKING:
    import uuid

    from app.modules.maker_checker.models.mixins import ApprovalRequestMixin

_log = structlog.get_logger(__name__)

VALID_STATUSES_FOR_ACTION = {"pending"}


def _audit_svc(session: AsyncSession) -> PlatformAuditService | TenantAuditService:
    if session.sync_session.info.get("is_platform"):
        return PlatformAuditService(session)
    return TenantAuditService(session)


def _request_models(
    session: AsyncSession,
) -> tuple[type[Any], type[Any]]:
    if session.sync_session.info.get("is_platform"):
        return PlatformApprovalRequest, PlatformApprovalAction
    return TenantApprovalRequest, TenantApprovalAction


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._req_cls, self._act_cls = _request_models(session)

    async def submit(
        self,
        *,
        operation_type: str,
        payload: dict[str, Any],
        requested_by: uuid.UUID,
        required_approvals: int = 1,
        expires_at: datetime | None = None,
    ) -> ApprovalRequestMixin:
        if operation_type not in approval_registry:
            raise ValueError(f"No executor registered for operation_type '{operation_type}'")

        request: ApprovalRequestMixin = cast(
            "ApprovalRequestMixin",
            self._req_cls(
                operation_type=operation_type,
                payload=payload,
                requested_by=requested_by,
                requested_at=datetime.now(UTC),
                required_approvals=required_approvals,
                status="pending",
                expires_at=expires_at,
            ),
        )
        self._session.add(request)
        await self._session.flush()

        await EventPublisher.publish(
            self._session,
            aggregate_type="approval_request",
            aggregate_id=request.id,
            event_type="ApprovalRequested",
            payload={"operation_type": operation_type, "requested_by": str(requested_by)},
        )
        await _audit_svc(self._session).record(
            table_name="approval_requests",
            record_id=request.id,
            operation="insert",
            actor_type="system",
            after_state={"status": "pending", "operation_type": operation_type},
        )
        return request

    async def approve(
        self,
        *,
        request_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        comment: str | None = None,
    ) -> ApprovalRequestMixin:
        request = await self._get_pending(request_id)
        if actor_user_id == request.requested_by:
            raise ValueError("Self-approval is forbidden")

        action = self._act_cls(
            approval_request_id=request.id,
            actor_user_id=actor_user_id,
            action="approve",
            acted_at=datetime.now(UTC),
            comment=comment,
        )
        self._session.add(action)
        await self._session.flush()

        count = await self.approval_count(request.id)
        await EventPublisher.publish(
            self._session,
            aggregate_type="approval_request",
            aggregate_id=request.id,
            event_type="ApprovalGranted",
            payload={"actor_user_id": str(actor_user_id), "approval_count": count},
        )

        if count >= request.required_approvals:
            request.status = "approved"
            await self._execute(request)

        return request

    async def reject(
        self,
        *,
        request_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        reason: str | None = None,
    ) -> ApprovalRequestMixin:
        request = await self._get_pending(request_id)
        if actor_user_id == request.requested_by:
            raise ValueError("Self-rejection is forbidden")

        action = self._act_cls(
            approval_request_id=request.id,
            actor_user_id=actor_user_id,
            action="reject",
            acted_at=datetime.now(UTC),
            comment=reason,
        )
        self._session.add(action)
        request.status = "rejected"
        request.rejection_reason = reason
        await self._session.flush()

        await EventPublisher.publish(
            self._session,
            aggregate_type="approval_request",
            aggregate_id=request.id,
            event_type="ApprovalRejected",
            payload={"actor_user_id": str(actor_user_id), "reason": reason},
        )
        return request

    async def cancel(
        self,
        *,
        request_id: uuid.UUID,
        requested_by: uuid.UUID,
    ) -> ApprovalRequestMixin:
        request = await self._get_pending(request_id)
        if request.requested_by != requested_by:
            raise ValueError("Only the maker can cancel their own request")

        action_count_result = await self._session.execute(
            select(func.count()).where(self._act_cls.approval_request_id == request.id)
        )
        if action_count_result.scalar_one() > 0:
            raise ValueError("Cannot cancel after a checker has acted — use reject instead")

        request.status = "cancelled"
        await self._session.flush()
        return request

    async def _get_pending(self, request_id: uuid.UUID) -> ApprovalRequestMixin:
        result = await self._session.execute(
            select(self._req_cls).where(self._req_cls.id == request_id)
        )
        request = result.scalar_one_or_none()
        if request is None:
            raise ValueError(f"Approval request {request_id} not found")
        row = cast("ApprovalRequestMixin", request)
        if row.status not in VALID_STATUSES_FOR_ACTION:
            raise ValueError(f"Request is in status '{row.status}', not 'pending'")
        return row

    async def approval_count(self, request_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count()).where(
                self._act_cls.approval_request_id == request_id,
                self._act_cls.action == "approve",
            )
        )
        return result.scalar_one()

    async def list_actions(self, request_id: uuid.UUID) -> list[Any]:
        result = await self._session.execute(
            select(self._act_cls)
            .where(self._act_cls.approval_request_id == request_id)
            .order_by(self._act_cls.acted_at.asc())
        )
        return list(result.scalars().all())

    async def _execute(self, request: Any) -> None:
        executor = approval_registry[request.operation_type]
        # Inject the request's id into the payload so executors can use it
        # for idempotency or for back-linking. Existing executors that ignore
        # the extra key are unaffected.
        enriched_payload = {**request.payload, "approval_request_id": str(request.id)}
        try:
            result = await executor(self._session, enriched_payload)
            request.status = "executed"
            request.executed_at = datetime.now(UTC)
            request.execution_result = result or {}
            await EventPublisher.publish(
                self._session,
                aggregate_type="approval_request",
                aggregate_id=request.id,
                event_type="ApprovalExecuted",
                payload={"operation_type": request.operation_type},
            )
        except Exception as exc:
            request.status = "execution_failed"
            request.execution_result = {"error": str(exc)}
            _log.error(
                "maker_checker.execution_failed",
                request_id=str(request.id),
                operation_type=request.operation_type,
                error=str(exc),
            )
            await EventPublisher.publish(
                self._session,
                aggregate_type="approval_request",
                aggregate_id=request.id,
                event_type="ApprovalExecutionFailed",
                payload={"error": str(exc)},
            )


async def _run_expiry() -> None:
    from app.core.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)

    try:
        # Expire platform requests
        async with factory() as session, session.begin():
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            await session.execute(
                update(PlatformApprovalRequest)
                .where(
                    PlatformApprovalRequest.status == "pending",
                    PlatformApprovalRequest.expires_at < now,
                )
                .values(status="expired")
            )

        # Expire per-tenant requests
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
                )
                schemas = [row[0] for row in result.fetchall()]
        except Exception as exc:
            _log.warning("maker_checker.expiry.tenant_list_unavailable", error=str(exc))
            schemas = []

        import re  # noqa: PLC0415

        _SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
        for schema in schemas:
            if not _SCHEMA_RE.match(schema):
                _log.error("maker_checker.expiry.invalid_schema", schema=schema)
                continue
            async with factory() as session, session.begin():
                await session.execute(
                    text(f"SET LOCAL search_path TO {schema}, platform")  # noqa: S608
                )
                await session.execute(
                    update(TenantApprovalRequest)
                    .where(
                        TenantApprovalRequest.status == "pending",
                        TenantApprovalRequest.expires_at < now,
                    )
                    .values(status="expired")
                )
    finally:
        await engine.dispose()


@celery_app.task(name="app.modules.maker_checker.service.expire_approval_requests")  # type: ignore[misc]
def expire_approval_requests() -> None:
    asyncio.run(_run_expiry())
