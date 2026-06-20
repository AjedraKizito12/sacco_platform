"""Read-only audit-log query service (schema-agnostic)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class AuditQueryService:
    """Queries an audit_log table. The model class (PlatformAuditLog or
    TenantAuditLog) is supplied by the caller so the service stays
    schema-agnostic, like ApprovalService."""

    def __init__(self, session: AsyncSession, model_cls: type[Any]) -> None:
        self._session = session
        self._m = model_cls

    async def query(
        self,
        *,
        table_name: str | None = None,
        record_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        actor_type: str | None = None,
        operation: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[Any], int]:
        conds = []
        if table_name:
            conds.append(self._m.table_name == table_name)
        if record_id is not None:
            conds.append(self._m.record_id == record_id)
        if actor_id is not None:
            conds.append(self._m.actor_id == actor_id)
        if actor_type:
            conds.append(self._m.actor_type == actor_type)
        if operation:
            conds.append(self._m.operation == operation)
        if occurred_from is not None:
            conds.append(self._m.occurred_at >= occurred_from)
        if occurred_to is not None:
            conds.append(self._m.occurred_at <= occurred_to)

        total = (
            await self._session.execute(
                select(func.count()).select_from(self._m).where(*conds)
            )
        ).scalar_one()

        rows = (
            (
                await self._session.execute(
                    select(self._m)
                    .where(*conds)
                    .order_by(self._m.occurred_at.desc(), self._m.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total
