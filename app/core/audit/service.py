from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from app.core.audit.models import PlatformAuditLog, TenantAuditLog

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class _AuditServiceBase:
    # type[Any] because SQLAlchemy generates __init__ at runtime; mypy cannot
    # introspect the mapped constructor kwargs from the mixin base alone.
    _model_cls: ClassVar[type[Any]]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        table_name: str,
        record_id: uuid.UUID,
        operation: str,
        actor_type: str,
        actor_id: uuid.UUID | None = None,
        actor_label: str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        row = self._model_cls(
            table_name=table_name,
            record_id=record_id,
            operation=operation,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_label=actor_label,
            before_state=before_state,
            after_state=after_state,
            occurred_at=datetime.now(UTC),
            request_id=request_id,
        )
        self._session.add(row)


class PlatformAuditService(_AuditServiceBase):
    _model_cls = PlatformAuditLog


class TenantAuditService(_AuditServiceBase):
    _model_cls = TenantAuditLog
